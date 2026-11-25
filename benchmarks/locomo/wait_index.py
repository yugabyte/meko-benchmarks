#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Wait until the cloud has indexed every ingested turn, so retrieval does not start early.

  ./wait_index.py --run cloud1
  ./wait_index.py --run cloud1 --interval 120 --max-wait 120

Meko embeds conversation turns in background workers, after conversation_add_message returns. A search
that starts before they finish runs over a partial index: the first full LoCoMo run on cloud retrieved the
evidence turn for 45% of single-hop questions, and 85% when repeated hours later, with nothing else changed.
Nothing in the API reports the queue, so this probes it directly.

Probe: the last turn of every session (272 of them; the last turn of a session is the last one embedded
for it), searched by its own exact text. A turn that is embedded comes back as the closest hit at
distance ~0, well inside any gate; one that is not embedded does not come back at all.

Not every probe is found even on a finished index: on conv-26, 3% of turns (13 of 419, spread through the
whole conversation) are not returned by their own exact text, hours after ingest, with the same turn found on
one pass and not on another. So the test is not "all found". The index counts as complete when at least 90%
of probes are found AND the set of missing probes is the same on two passes in a row: a filling index keeps
changing between passes, a finished one does not. The final missing count is recorded in wait_index.json.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import data
from ingest import turns_of

RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def probes(state):
    """(sample_id, datapack_id, session, text) for the last turn of each ingested session."""
    out = []
    for s in data.load():
        rec = state.get(s["sample_id"])
        if not rec or not rec.get("datapack_id"):
            continue
        last = {}
        for t in turns_of(s, "caption"):
            last[t["session"]] = t
        out += [(s["sample_id"], rec["datapack_id"], n, t["text"]) for n, t in last.items() if str(n) in rec.get("sessions", {})]
    return out


async def one_pass(meko, agent, plan, workers=8):
    gate, missing = asyncio.Semaphore(workers), []

    async def probe(sid, dp, session, text):
        async with gate:
            r = await meko.call("context_search", read_only=True, query=text[:1500], conversation_id=uuid.uuid4().hex,
                                datapack_id=dp, agent_id=agent, limit=10, force_source="conversation")
            hits = ((r.get("results") or {}).get("conversation") or {}).get("hits") or []
            needle = text[:80]
            if not any(needle in (h.get("content") or "") for h in hits):
                missing.append((sid, session))

    await asyncio.gather(*(probe(*p) for p in plan))
    return missing


async def wait(run, interval=120, max_wait=120, need=2, floor=0.9):
    """Returns (complete, passes, seconds, missing). Importable by run_all.py."""
    from auth import Auth, load_env
    from meko import Meko
    state = json.loads((RUNS / run / "state.json").read_text())["conversations"]
    plan = probes(state)
    cfg, started, streak, passes, prev = load_env(), time.time(), 0, 0, None
    log(f"probing {len(plan)} sessions (last turn of each, searched by its own text)")
    async with Meko(cfg["url"], Auth(cfg), cfg["agent"]) as meko:
        while True:
            missing = await one_pass(meko, cfg["agent"], plan)
            passes += 1
            now = frozenset(missing)
            level = (len(plan) - len(now)) / len(plan)
            streak = streak + 1 if (prev is not None and now == prev and level >= floor) else (1 if level >= floor and prev is None else 0)
            prev = now
            by = {}
            for sid, _ in missing:
                by[sid] = by.get(sid, 0) + 1
            log(f"pass {passes}: {len(plan) - len(missing)}/{len(plan)} found" + (f" · missing by sample {by}" if by else "")
                + f" · stable passes in a row {streak}/{need}")
            if streak >= need:
                return True, passes, time.time() - started, len(missing)
            if time.time() - started + interval > max_wait * 60:
                return False, passes, time.time() - started, len(missing)
            await asyncio.sleep(interval)


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--interval", type=int, default=120, help="seconds between passes")
    ap.add_argument("--max-wait", type=int, default=120, help="give up after this many minutes")
    args = ap.parse_args()
    done, passes, secs, missing = await wait(args.run, args.interval, args.max_wait)
    log(("index complete" if done else "index NOT complete") + f" after {passes} passes, {secs:.0f}s")
    (RUNS / args.run / "wait_index.json").write_text(json.dumps(
        {"finished": time.strftime("%Y-%m-%d %H:%M"), "complete": done, "passes": passes, "seconds": round(secs), "probes_missing": missing}, indent=1))
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
