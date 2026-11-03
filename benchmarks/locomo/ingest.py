#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Phase 1 — replay LoCoMo conversations into a local Meko stack.

  ./ingest.py --run r1 --smoke               3 turns of conv-26, then check created_at
  ./ingest.py --run r1                       all 10 conversations
  ./ingest.py --run r1 --conversations 1,3   just those (indices 0-9)
  ./ingest.py --run r1 --dry-run             print payloads, call nothing
  ./ingest.py --run r1 --delete              drop this run's datapacks

One datapack per LoCoMo sample and one Meko conversation per *session*: Meko
keeps a conversation as a single Langfuse trace and re-reads it on every
add_message, and a whole LoCoMo conversation (369-689 turns) blows Langfuse's
80 MB per-trace limit around turn 275. Sessions are 14-35 turns. Isolation
between samples is the datapack, not the conversation id.

Every turn goes in as `input` (only `input` reaches memory extraction) with the
session date both in the text and in metadata.session_date. Turns are sent in
order, one at a time, per sample; --workers runs samples side by side.
Progress is kept in runs/locomo/<run>/state.json, so a stopped run resumes.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import data

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def save(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def turns_of(sample, images):
    """Flat, chronological list of everything one conversation sends."""
    out = []
    for num, date_text, turns in data.sessions(sample):
        iso = data.to_iso(date_text)
        for t in turns:
            out.append({"dia_id": t["dia_id"], "session": num, "date": date_text, "iso": iso,
                        "speaker": t["speaker"], "text": f"[{date_text}] {data.turn_text(t, images)}"})
    return out


async def settle(meko, rec, every=10, patience=2, max_wait=180):
    """Wait until the memory count stops moving. Extraction can lag the add call."""
    counts, started = [], time.time()
    while time.time() - started < max_wait:
        total, page = await meko.memories(rec["datapack_id"], meko.trace)
        counts.append(total)
        if len(counts) > patience and len(set(counts[-patience - 1:])) == 1:
            return total, page
        await asyncio.sleep(every)
    return total, page


async def ingest_one(meko, sample, turns, rec, run, state_path, state, no_index):
    sid = sample["sample_id"]
    if not rec.get("datapack_id"):
        rec["datapack_id"] = await meko.create_datapack(f"locomo-{run}-{sid}")
        if no_index:
            await meko.disable_conversation_index(rec["datapack_id"])
        save(state_path, state)
    sessions = rec.setdefault("sessions", {})  # session number -> Meko conversation id
    rec.update(total=len(turns), status="ingesting")
    log(f"{sid}: {len(turns)} turns, resuming at {rec['sent']}")

    for i in range(rec["sent"], len(turns)):
        t = turns[i]
        key = str(t["session"])
        if key not in sessions:
            n = sum(1 for x in turns if x["session"] == t["session"])
            log(f"{sid}: session {t['session']} · {t['date']} · {n} turns")
            sessions[key] = await meko.create_conversation(
                rec["datapack_id"], f"{sid} session {t['session']}",
                {"source": "locomo", "run": run, "sample_id": sid, "session": t["session"], "session_date": t["iso"]})
            save(state_path, state)
        await meko.add_turn(rec["datapack_id"], sessions[key], t["text"], t["iso"],
                            seed=f"locomo:{run}:{sid}:{t['dia_id']}",
                            source="locomo", sample_id=sid, dia_id=t["dia_id"], speaker=t["speaker"])
        rec["sent"] = i + 1
        save(state_path, state)  # tiny file; keeps status.py live and a kill loses nothing

    rec["status"] = "settling"
    save(state_path, state)
    total, page = await settle(meko, rec)
    rec.update(memories=total, status="done")
    rec.pop("error", None)
    save(state_path, state)
    log(f"{sid}: done · {rec['sent']} turns sent · {total} memories")
    return page


async def smoke_check(meko, rec, turns, memories):
    """The whole point of Phase 1: memories must carry the session date, not today.

    Reads each memory back through mem0 (memory_get_by_id): the memory_get_all
    listing is served by the API server and shows its own insert time instead.
    """
    if not memories:
        return False, "no memories came back — extraction not running, or still async"
    month = turns[0]["iso"][:7]
    bad = 0
    for m in memories:
        full = await meko.memory(m["id"], rec["datapack_id"], meko.trace)
        created = str(full.get("created_at", ""))
        bad += created[:7] != month
        print(f"   {created[:19]}  {full.get('memory', '')[:90]}")
    if bad:
        return False, f"{bad}/{len(memories)} memories are not dated {month} — backdating is not taking effect"
    return True, f"all {len(memories)} memories dated {month}"


async def delete_run(meko, state):
    for sid, rec in state["conversations"].items():
        if rec.get("borrowed_from"):  # another run's datapack, reused read-only: never ours to drop
            log(f"{sid}: datapack {rec['datapack_id']} belongs to {rec['borrowed_from']}; kept")
        elif rec.get("datapack_id"):
            await meko.delete_datapack(rec["datapack_id"])
            log(f"{sid}: deleted datapack {rec['datapack_id']}")


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="name; state lives in runs/locomo/<run>/")
    ap.add_argument("--conversations", default="all", help="comma-separated indices 0-9")
    ap.add_argument("--limit", type=int, help="max turns per conversation")
    ap.add_argument("--workers", type=int, default=2, help="conversations in flight (mem0 pools are small)")
    ap.add_argument("--images", choices=["caption", "drop"], default="caption")
    ap.add_argument("--no-index", action="store_true", help="skip search-cache embedding (saves quota)")
    ap.add_argument("--smoke", action="store_true", help="conv 0, 3 turns, then verify created_at")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delete", action="store_true", help="delete this run's datapacks and exit")
    args = ap.parse_args()
    if args.smoke:
        args.conversations, args.limit = "0", 3

    dataset = data.load()
    idxs = range(len(dataset)) if args.conversations == "all" else [int(i) for i in args.conversations.split(",")]
    plan = [(dataset[i], turns_of(dataset[i], args.images)[: args.limit]) for i in idxs]

    if args.dry_run:
        for sample, turns in plan:
            print(f"\n{sample['sample_id']}: {len(turns)} turns")
            for t in turns[:3]:
                print(json.dumps({"input": t["text"], "metadata": {"session_date": t["iso"], "dia_id": t["dia_id"]}}, indent=2))
        return

    from auth import Auth, AuthError, load_env  # need httpx; --dry-run above works without it
    from meko import Meko, MekoError

    cfg = load_env()
    if not (cfg["static"] or (cfg["email"] and cfg["password"])):
        sys.exit(".env needs MEKO_EMAIL + MEKO_PASSWORD (the harness mints its own key) or a MEKO_USER_TOKEN")
    try:
        auth = Auth(cfg)
        auth.token()
    except AuthError as e:
        sys.exit(f"auth failed: {e}")

    run_dir = RUNS / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"run": args.run, "conversations": {}}

    async with Meko(cfg["url"], auth, cfg["agent"]) as meko:
        if args.delete:
            await delete_run(meko, state)
            state_path.unlink(missing_ok=True)
            return

        if args.smoke:  # always a fresh datapack: a re-run must prove ingestion, not skip it
            old = state["conversations"].pop(plan[0][0]["sample_id"], {})
            if old.get("datapack_id"):
                try:
                    await meko.delete_datapack(old["datapack_id"])
                    log(f"smoke: deleted previous datapack {old['datapack_id']}")
                except MekoError as e:  # cleanup only — never the reason a smoke test can't run
                    log(f"smoke: could not delete old datapack {old['datapack_id']} ({str(e)[:80]}); leaving it")

        # Anything not finished is about to be retried: say "queued" instead of
        # showing last run's failure until a worker slot frees up.
        for sample, _ in plan:
            rec = state["conversations"].setdefault(sample["sample_id"], {"sent": 0})
            if rec.get("status") != "done":
                rec["status"], _ = "queued", rec.pop("error", None)
        save(state_path, state)

        gate = asyncio.Semaphore(args.workers)
        results = {}

        async def worker(sample, turns):
            sid = sample["sample_id"]
            rec = state["conversations"].setdefault(sid, {"sent": 0})
            if rec.get("status") == "done":
                log(f"{sid}: already done, skipping")
                return
            async with gate:
                try:
                    results[sid] = await ingest_one(meko, sample, turns, rec, args.run, state_path, state, args.no_index)
                except MekoError as e:
                    rec.update(status="failed", error=str(e))
                    save(state_path, state)
                    log(f"{sid}: FAILED at turn {rec['sent']} — {e}")

        log(f"run {args.run} → {cfg['url']} · agent {cfg['agent']} · {len(plan)} conversations · workers {args.workers}")
        await asyncio.gather(*(worker(s, t) for s, t in plan))

        if args.smoke:
            sid = plan[0][0]["sample_id"]
            if sid in results:
                ok, why = await smoke_check(meko, state["conversations"][sid], plan[0][1], results[sid])
            else:
                ok, why = False, "ingest failed, see above"
            log(("SMOKE PASS — " if ok else "SMOKE FAIL — ") + why)
            sys.exit(0 if ok else 1)

    done = [r for r in state["conversations"].values() if r.get("status") == "done"]
    log(f"{len(done)}/{len(plan)} conversations done · state in {state_path}")


if __name__ == "__main__":
    asyncio.run(main())
