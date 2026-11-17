#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Run the whole LoCoMo benchmark against Meko, stopping at the first gate that fails.

  ./run_all.py --run cloud1                 every stage, in order
  ./run_all.py --run cloud1                 run again after a stop: finished stages are skipped
  ./run_all.py --run cloud1 --from retrieve start at a stage (earlier ones are assumed done)
  ./run_all.py --run cloud1 --only report   one stage
  ./run_all.py --list                       the stages

Needs a filled-in .env (see .env.example) and nothing else. It takes about 40 minutes and writes
runs/locomo/<run>/ (pipeline.json = stage status, result.json = the outcome). Run it with nohup if your
shell can be interrupted: it is resumable, so a rerun picks up where it stopped.

Stages and their gates (a stage that fails stops the run, and says why):
  preflight       .env keys, services, models, and whether the server accepts the benchmark's conversation gate
  ingest          every turn sent; reruns itself after a crash (resumes from state.json)
  verify-ingest   every conversation done; Meko holds exactly the dataset's turn count for every session
  wait-index      the cloud has embedded the turns (see wait_index.py); retrieving earlier gives a partial index
  retrieve        k=25, memories and conversation turns for all 1,986 questions
  verify-retrieve no failed searches; 25 memories per question; the conversation tier at the size it should be
  answer          answer with gpt-5.6-terra (two-step prompt), judge with gpt-4.1-2025-04-14. This is the
                  paid stage: about 8M input tokens at k=25.
  report          report.md, the comparison table, and result.json (pooled J against the published target)
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "common"))
sys.path.insert(0, str(HERE))
RUNS = HERE.parents[1] / "runs" / "locomo"

STAGES = ["preflight", "ingest", "verify-ingest", "wait-index", "retrieve", "verify-retrieve", "answer", "report"]
QUESTIONS = 1986
TARGET_J, TARGET_BAND = 85.4, 1.8        # docs/replication.md: Run 1 pooled J at k=25 and its 95% sampling interval
CAT_N = {4: 841, 1: 282, 2: 321, 3: 96}  # the questions that are judged (adversarial has no gold answer)
CAT_NAME = {4: "single-hop", 1: "multi-hop", 2: "temporal", 3: "open-domain"}


class GateFailed(RuntimeError):
    pass


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def sh(script, *args, check=True):
    log("$ " + " ".join([script, *args]))
    r = subprocess.run([str(HERE / script), *args])
    if check and r.returncode:
        raise GateFailed(f"{script} exited with {r.returncode}")
    return r.returncode


class Pipeline:
    def __init__(self, run):
        self.run, self.dir = run, RUNS / run
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "pipeline.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"stages": {}}

    def done(self, stage):
        return self.state["stages"].get(stage, {}).get("status") == "done"

    def mark(self, stage, status, **extra):
        self.state["stages"][stage] = {"status": status, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **extra}
        self.path.write_text(json.dumps(self.state, indent=1))

    def json(self, name):
        p = self.dir / name
        return json.loads(p.read_text()) if p.exists() else {}

    @property
    def gate_override(self):
        return bool(self.json("preflight.json").get("gate_override"))


# -- stages --------------------------------------------------------------------

def stage_preflight(p):
    sh("preflight.py", "--run", p.run)


def ingest_finished(p):
    c = p.json("state.json").get("conversations", {})
    return len(c) == 10 and all(v.get("status") == "done" for v in c.values())


def stage_ingest(p):
    """Rerun ingest until every conversation is done. The server can drop connections or answer 502 under load;
    ingest saves its position after every turn, so each rerun continues where the last stopped."""
    for attempt in range(1, 31):
        log(f"ingest attempt {attempt}")
        sh("ingest.py", "--run", p.run, "--workers", "3", check=False)
        if ingest_finished(p):
            return
        time.sleep(30)
    raise GateFailed("ingest did not finish in 30 attempts; see the log above and runs/locomo/%s/state.json" % p.run)


async def server_counts(p, expected):
    from auth import Auth, load_env
    from meko import Meko, MekoError
    cfg = load_env()
    state = p.json("state.json")["conversations"]
    sem, bad = asyncio.Semaphore(4), []
    async with Meko(cfg["url"], Auth(cfg), cfg["agent"]) as meko:
        async def one(sid, session, want):
            async with sem:
                cid = state[sid]["sessions"].get(str(session))
                got = None
                for attempt in range(5):  # the server resets connections now and then (see ingest); a read is safe to repeat
                    try:
                        got = await meko.message_count(state[sid]["datapack_id"], cid) if cid else None
                        break
                    except MekoError:
                        await asyncio.sleep(2 ** attempt)
                if got != want:
                    bad.append((sid, session, want, got))
        await asyncio.gather(*(one(sid, n, w) for (sid, n), w in expected.items()))
    return bad


def stage_verify_ingest(p):
    import data
    from ingest import turns_of
    state = p.json("state.json")["conversations"]
    expected, problems = {}, []
    for s in data.load():
        turns = turns_of(s, "caption")
        rec = state.get(s["sample_id"], {})
        if rec.get("status") != "done" or rec.get("sent") != len(turns):
            problems.append(f"{s['sample_id']}: status {rec.get('status')}, sent {rec.get('sent')} of {len(turns)}")
        for t in turns:
            expected[(s["sample_id"], t["session"])] = expected.get((s["sample_id"], t["session"]), 0) + 1
    if problems:
        raise GateFailed("ingest is incomplete: " + "; ".join(problems))
    for attempt in range(1, 5):  # a count read right after ingest can lag the writes; a count that stays wrong is a real gap
        bad = asyncio.run(server_counts(p, expected))
        log(f"server holds the expected turn count for {len(expected) - len(bad)}/{len(expected)} sessions")
        if not bad:
            return
        time.sleep(30)
    raise GateFailed(f"{len(bad)} sessions hold a different number of turns than the dataset (session, expected, found): {bad[:8]}"
                     " . More than expected means a turn was written twice; fewer, a write was lost.")


def stage_wait_index(p):
    import wait_index
    done, passes, secs, missing = asyncio.run(wait_index.wait(p.run))
    (p.dir / "wait_index.json").write_text(json.dumps({"complete": done, "passes": passes, "seconds": round(secs), "probes_missing": missing}))
    if not done:
        raise GateFailed("the conversation index was still changing after the maximum wait; rerun from wait-index later")


def stage_retrieve(p):
    args = ["--run", p.run, "--ks", "25", "--categories", "1,2,3,4,5", "--memory-via", "context_search", "--workers", "6"]
    if p.gate_override:
        args += ["--conversation-hit-distance", "2.0"]
    else:
        log("WARNING: this server has no conversation_hit_distance argument; using its default gate (0.35). "
            "Conversation context will reach only ~1 in 5 questions and the result is not comparable with the target.")
    sh("retrieve.py", *args)


def stage_verify_retrieve(p):
    import prompts
    rows = [json.loads(l) for l in (p.dir / "retrieval.jsonl").read_text().splitlines() if l]
    meta = p.json("retrieve.json")
    problems, notes = [], []
    if meta.get("failed"):
        problems.append(f"{meta['failed']} searches failed")
    if len(rows) != QUESTIONS:
        problems.append(f"{len(rows)} retrieval rows, expected {QUESTIONS}")
    if rows:
        mem = sum(len(r["hits"]) for r in rows) / len(rows)
        turns = [len(prompts.conversation_turns(r.get("conversation"))) for r in rows]
        avg = sum(turns) / len(turns)
        log(f"memories per question {mem:.1f} · conversation turns per question {avg:.1f} · "
            f"{sum(1 for t in turns if not t)} questions with no turns")
        if mem < 24:
            problems.append(f"only {mem:.1f} memories per question; the memory search is returning fewer than asked for")
        if p.gate_override and not 45 <= avg <= 62:
            problems.append(f"{avg:.1f} conversation turns per question; the benchmark gate gives about 50 to 57")
        if p.gate_override and sum(1 for t in turns if not t) > 0.01 * len(rows):
            problems.append("more than 1% of questions got no conversation turns")
    if problems:
        raise GateFailed("; ".join(problems))
    for n in notes:
        log(n)


def stage_answer(p):
    sh("answer.py", "--run", p.run, "--ks", "25", "--prompt", "two-step", "--model", "gpt-5.6-terra",
       "--judge", "cognis", "--judge-model", "gpt-4.1-2025-04-14", "--workers", "16")


def stage_report(p):
    sh("report.py", "--run", p.run)
    sh("compare.py", "--run", p.run, "--k", "25", check=False)
    rows = [json.loads(l) for l in (p.dir / "answers.jsonl").read_text().splitlines() if l]
    judged = {c: [int(r["judge"]) for r in rows if r["category"] == c and r["judge"] is not None] for c in CAT_N}
    if any(not v for v in judged.values()) or len(rows) != QUESTIONS:
        raise GateFailed(f"{len(rows)} answers, expected {QUESTIONS}; some categories have no judged answers")
    per = {CAT_NAME[c]: round(100 * sum(v) / len(v), 1) for c, v in judged.items()}
    pooled = sum(CAT_N[c] * sum(v) / len(v) for c, v in judged.items()) / sum(CAT_N.values()) * 100
    within = abs(pooled - TARGET_J) <= TARGET_BAND
    result = {"run": p.run, "finished": time.strftime("%Y-%m-%d %H:%M"), "pooled_J": round(pooled, 1), "per_category_J": per,
              "target": f"{TARGET_J} +/- {TARGET_BAND} (docs/replication.md, Run 1, k=25)", "within_target_band": within,
              "conversation_gate": "2.0 (benchmark)" if p.gate_override else "server default 0.35 (override not available)",
              "index_probes_missing": p.json("wait_index.json").get("probes_missing")}
    (p.dir / "result.json").write_text(json.dumps(result, indent=1))
    print("\n" + json.dumps(result, indent=1))
    if not p.gate_override:
        print("\nNOTE: this server does not accept the conversation_hit_distance argument, so this result is not comparable "
              "with the published target. It measures what Meko returns with its default conversation gate.")
    elif not within:
        print(f"\nNOTE: pooled J {pooled:.1f} is outside {TARGET_J} +/- {TARGET_BAND}. Run-to-run variation is real: "
              "gpt-5.6-terra has no dated snapshot and memory extraction is not deterministic (docs/replication.md). "
              "Report this number as measured.")


FUNCS = {"preflight": stage_preflight, "ingest": stage_ingest, "verify-ingest": stage_verify_ingest,
         "wait-index": stage_wait_index, "retrieve": stage_retrieve, "verify-retrieve": stage_verify_retrieve,
         "answer": stage_answer, "report": stage_report}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a name for this run; its files go in runs/locomo/<run>/")
    ap.add_argument("--from", dest="start", choices=STAGES, help="start at this stage")
    ap.add_argument("--only", choices=STAGES, help="run just this stage")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list or not args.run:
        print("\n".join(STAGES))
        return 0 if args.list else 2
    p = Pipeline(args.run)
    todo = [args.only] if args.only else STAGES[STAGES.index(args.start):] if args.start else STAGES
    for stage in todo:
        if p.done(stage) and not (args.only or args.start):
            log(f"{stage}: done earlier, skipping")
            continue
        log(f"=== {stage}")
        started = time.time()
        p.mark(stage, "running")
        try:
            FUNCS[stage](p)
        except GateFailed as e:
            p.mark(stage, "failed", reason=str(e))
            log(f"GATE FAILED at {stage}: {e}")
            log(f"fix the cause, then rerun: ./run_all.py --run {args.run}")
            return 1
        p.mark(stage, "done", seconds=round(time.time() - started))
    log("all stages passed" if not args.only else f"{args.only} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
