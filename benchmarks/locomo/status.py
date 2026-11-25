#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Live view of a run: which phase is active and how far each conversation is.

  ./status.py --run full            one snapshot
  ./status.py --run full --watch 10 refresh every 10 s (Ctrl-C to stop)

Reads runs/locomo/<run>/state.json (Phase 1), retrieval.jsonl (Phase 2) and
answers.jsonl (Phase 3). Memory counts come live from the API's datapack list
when it is reachable, so they are right even mid-run.
"""

import argparse
import json
import subprocess
import time
from collections import Counter, defaultdict
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import data
from report import Table

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"


def running(pattern):
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def live_memory_counts(datapack_ids):
    """{datapack_id: total memories} via memory_get_all's `total` (the datapack list's
    memory_count field is not maintained). {} if the server isn't reachable."""
    import asyncio

    async def fetch():
        from auth import Auth, load_env
        from meko import Meko
        cfg = load_env()
        async with Meko(cfg["url"], Auth(cfg), cfg["agent"], timeout=20) as m:
            totals = await asyncio.gather(*(m.memories(d, m.trace) for d in datapack_ids), return_exceptions=True)
        return {d: t[0] for d, t in zip(datapack_ids, totals) if isinstance(t, tuple)}

    try:
        return asyncio.run(fetch()) if datapack_ids else {}
    except Exception:
        return {}


SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def bar(done, total, width=24):
    """A thin progress bar: ████████░░░░░░░░ 33%"""
    if not total:
        return "░" * width + "   –"
    filled = round(width * min(done, total) / total)
    return "█" * filled + "░" * (width - filled) + f" {100 * done / total:3.0f}%"


def eta(done, total, rate):
    """HH:MM finish time from a units-per-second rate; '–' until a rate is known."""
    if not rate or done >= total:
        return "–"
    return time.strftime("%H:%M UTC", time.gmtime(time.time() + (total - done) / rate))


def snapshot(run, tick=0, rate=None):
    d = RUNS / run
    state = json.loads((d / "state.json").read_text())["conversations"] if (d / "state.json").exists() else {}
    ret, ans = jsonl(d / "retrieval.jsonl"), jsonl(d / "answers.jsonl")
    samples = {s["sample_id"]: s for s in data.load()}
    ks = sorted({r["k"] for r in ret})
    cats = {r["category"] for r in ret}

    phases = [("1 ingest", f"ingest.py --run {run}"), ("2 retrieve", f"retrieve.py --run {run}"), ("3 answer", f"answer.py --run {run}")]
    active = [name for name, pat in phases if running(pat)]
    live = live_memory_counts([r["datapack_id"] for r in state.values() if r.get("datapack_id")])
    ret_by, ans_by = Counter(r["conv"] for r in ret), defaultdict(list)
    for a in ans:
        ans_by[a["conv"]].append(a)

    rows, totals = [], Counter()
    for sid, s in samples.items():
        rec = state.get(sid)
        turns = sum(len(t) for _, _, t in data.sessions(s))
        n_sessions = len(data.sessions(s))
        expected = len([q for q in s["qa"] if q["category"] in cats]) * len(ks) if ks else 0
        if rec is None:
            rows.append([sid, f"{'▱' * 8} 0/{turns}", f"0/{n_sessions}", "pending", "–", "–", "–", "–"])
            continue
        sent, opened = rec.get("sent", 0), len(rec.get("sessions", {}))
        status = rec.get("status", "pending")
        if status == "failed":  # keep the row readable: tool name + error code only
            err = str(rec.get("error", ""))
            code = err.split("'error': '")[1].split("'")[0] if "'error': '" in err else err[:24]
            # an untouched conversation while an ingest is running is waiting for a worker, not failed
            status = f"queued (last: {code})" if sent == 0 and "1 ingest" in active else f"FAILED {err.split(':')[0]}: {code}"
        mem = live.get(rec.get("datapack_id"), rec.get("memories"))
        got = ans_by.get(sid, [])
        judged = [a["judge"] for a in got if a.get("judge") is not None]
        j = f"{100 * sum(judged) / len(judged):.0f}%" if judged else "–"
        mini = "▰" * round(8 * sent / turns) + "▱" * (8 - round(8 * sent / turns))
        rows.append([sid, f"{mini} {sent}/{turns}", f"{opened}/{n_sessions}", status, "–" if mem is None else str(mem),
                     f"{ret_by.get(sid, 0)}/{expected}" if expected else "–",
                     f"{len(got)}/{ret_by.get(sid, 0)}" if ret_by.get(sid) else "–", j])
        totals.update(sent=sent, turns=turns, done=int(status == "done"), retrieved=ret_by.get(sid, 0), answered=len(got))

    expected_rows = sum(len([q for q in s["qa"] if q["category"] in cats]) for s in samples.values()) * len(ks) if ks else 0
    spin = SPIN[tick % len(SPIN)] if active else "·"
    lines = [f"{spin} Run {run} · {time.strftime('%H:%M:%S UTC', time.gmtime())} · "
             + ("running: " + ", ".join(active) if active else "nothing running"),
             f"  ingest    {bar(totals['sent'], totals['turns'])}  {totals['sent']}/{totals['turns']} turns · "
             f"{totals['done']}/{len(samples)} conversations · ETA {eta(totals['sent'], totals['turns'], rate)}"]
    if ks:
        lines.append(f"  retrieve  {bar(totals['retrieved'], expected_rows)}  {totals['retrieved']}/{expected_rows} searches · ks {ks}")
        lines.append(f"  answer    {bar(totals['answered'], totals['retrieved'])}  {totals['answered']}/{totals['retrieved']} answered")
    table = Table("", ["conversation", "turns", "sessions", "ingest", "memories", "retrieved", "answered", "J so far"], rows)
    return "\n".join(lines) + "\n" + table.boxed(), totals["sent"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--watch", type=int, metavar="SECONDS")
    args = ap.parse_args()
    tick, last, rate = 0, None, None  # rate = turns/s between refreshes, lightly smoothed
    while True:
        out, sent = snapshot(args.run, tick, rate)
        if not args.watch:
            print(out)
            break
        print("\033[2J\033[H" + out + f"\n\nrefreshing every {args.watch}s · Ctrl-C to leave (the run keeps going)", flush=True)
        if last is not None and sent > last[0]:
            r = (sent - last[0]) / (time.time() - last[1])
            rate = r if rate is None else 0.7 * rate + 0.3 * r
        if last is None or sent > last[0]:
            last = (sent, time.time())
        tick += 1
        try:
            time.sleep(args.watch)
        except KeyboardInterrupt:
            print()
            break
