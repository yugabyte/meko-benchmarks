#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Phase 2 — retrieve memories for every question of an ingested run.

  ./retrieve.py --run conv26                    memory_search at k=10 and k=50, plus conversation turns
  ./retrieve.py --run conv26 --ks 10,50,200     mem0 publishes at 200
  ./retrieve.py --run conv26 --no-conversation  memories only
  ./retrieve.py --run conv26 --ks 25 --tool meko_search [--pipeline cognis|raw] [--search-limit N]

Two sources per question. memory_search gives k memories. context_search with
force_source="conversation" gives verbatim turns; the server ignores limit there
(10 candidate chunks, best 3 sessions, 50 turns), so it is called once per
question and the same result is attached to every k row.

Reads runs/locomo/<run>/state.json (Phase 1), writes one line per (question, k) to
runs/locomo/<run>/retrieval.jsonl. Read-only against Meko and resumable: rows
already written are skipped. Isolation is the per-sample datapack: a sample's
turns are spread over one Meko conversation per session, so run_id (one
conversation) must NOT be passed or you'd search one session only.

--tool meko_search replaces both calls with one meko_search per question (per k without --search-limit):
one ranked list across memory, the knowledge base and the conversation cache. Its memory results become the
row's hits and its conversation results the turn tier (no thread), each keeping its place in the list as
`rank`; the response's query_analysis, by_source and debug are kept on the row.
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

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def questions(sample, categories):
    for i, qa in enumerate(sample["qa"]):
        if qa["category"] in categories:
            yield f"{sample['sample_id']}:q{i}", qa


def covered_sessions(sample, sent):
    """Sessions whose every turn has been sent, given a flat turn count."""
    covered, seen = set(), 0
    for num, _, turns in data.sessions(sample):
        seen += len(turns)
        if seen <= sent:
            covered.add(num)
    return covered


def answerable(qa, covered):
    """A question is fair game only if every evidence turn lies in a fully ingested session."""
    sessions = {int(e[1:].split(":")[0]) for e in data.evidence_ids(qa)}
    return bool(sessions) and sessions <= covered


def slim(hit):
    """Keep what Phase 3 needs from a memory_search hit."""
    return {k: hit.get(k) for k in ("id", "memory", "created_at", "updated_at", "score", "raw_similarity_score")}


def slim_turn(t):
    """Keep what Phase 3 needs from a context_search conversation hit or thread turn."""
    return {k: t.get(k) for k in ("content", "session_date", "conversation_id", "message_id", "distance")}


def meko_split(res):
    """meko_search's one ranked list as the row's two tiers: memory results as hits, conversation results as
    turns (no thread). Each keeps its place in the list as `rank`; knowledge-base results have no tier here."""
    hits, turns = [], []
    for r in res.get("results") or []:
        meta = r.get("metadata") or {}
        if r.get("source") == "memory":
            hits.append({"id": r.get("id"), "memory": r.get("text"), "created_at": meta.get("created_at"),
                         "updated_at": meta.get("updated_at"), "score": r.get("score"),
                         "raw_similarity_score": r.get("raw_similarity"), "rank": r.get("rank")})
        elif r.get("source") == "conversation":
            turns.append({"content": r.get("text"), "session_date": meta.get("session_date") or meta.get("created_at"),
                          "conversation_id": meta.get("conversation_id"), "message_id": meta.get("message_id"),
                          "distance": meta.get("distance"), "rank": r.get("rank")})
    return hits, {"hits": turns, "thread": []}


def meko_summary(res):
    rs = res.get("results") or []
    qa = res.get("query_analysis") or {}
    return {"results": len(rs), "by_source": {s: (v or {}).get("count") for s, v in (res.get("by_source") or {}).items()},
            "history": qa.get("history"), "temporal_span": qa.get("temporal_span"),
            "top_score": rs[0].get("score") if rs else None, "ids": [f"{r.get('source')}:{r.get('id')}" for r in rs]}


def ctx_summary(res):
    c = (res.get("results") or {}).get("conversation") or {}
    hits, thread = c.get("hits") or [], c.get("thread") or []
    d = [h.get("distance") for h in hits if h.get("distance") is not None]
    return {"chunk_hits": len(hits), "thread_turns": len(thread), "closest_distance": min(d) if d else None}


def mem_summary(res):
    hits = res.get("results") or []
    sc = [h.get("score") for h in hits if h.get("score") is not None]
    return {"memories": len(hits), "top_score": max(sc) if sc else None, "low_score": min(sc) if sc else None,
            "ids": [h.get("id") for h in hits]}


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--ks", default="10,50", help="retrieval depths, one memory_search call each")
    ap.add_argument("--categories", default="1,2,3,4", help="5 = adversarial, off by default")
    ap.add_argument("--limit", type=int, help="max questions per conversation")
    ap.add_argument("--workers", type=int, default=4, help="concurrent searches (reads, but pools are small)")
    ap.add_argument("--no-conversation", action="store_true", help="skip context_search's verbatim-turn tier")
    ap.add_argument("--include-partial", action="store_true",
                    help="use parked (not finished) ingests too; only questions whose evidence is fully ingested")
    ap.add_argument("--reference-date", action="store_true",
                    help="pass each conversation's last session date to memory_search as reference_date, so the "
                         "temporal stage resolves 'recently' / 'last year' against 2023, not today (experiment servers only)")
    ap.add_argument("--reuse-conversation", metavar="RUN",
                    help="take the context_search tier from RUN's retrieval.jsonl instead of calling it again; "
                         "it does not depend on memory search settings, so arms of an ablation share it")
    ap.add_argument("--tool", choices=["memory_search", "meko_search"], default="memory_search",
                    help="memory_search: context_search's turn tier plus memory_search per k (default); meko_search: "
                         "one ranked list across memory, knowledge base and conversations per question")
    ap.add_argument("--pipeline", choices=["cognis", "raw"], default="cognis", help="meko_search's ranking pipeline")
    ap.add_argument("--search-limit", type=int, metavar="N",
                    help="meko_search's limit, one call per question shared by every k (default: one call per k, limit k); "
                         "--limit stays the questions per conversation")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    meko_search = args.tool == "meko_search"
    if meko_search and (args.no_conversation or args.reuse_conversation):
        sys.exit("--tool meko_search searches the conversation cache itself; --no-conversation and --reuse-conversation do not apply")
    if args.search_limit and not meko_search:
        sys.exit("--search-limit is meko_search's limit; memory_search uses each k")

    ks = [int(k) for k in args.ks.split(",")]
    cats = {int(c) for c in args.categories.split(",")}
    state_path = RUNS / args.run / "state.json"
    if not state_path.exists():
        sys.exit(f"no {state_path} — run ingest.py --run {args.run} first")
    state = json.loads(state_path.read_text())["conversations"]
    usable = lambda rec: rec.get("status") == "done" or (args.include_partial and rec.get("datapack_id") and rec.get("sent"))
    done = {sid: rec for sid, rec in state.items() if usable(rec)}
    samples = {s["sample_id"]: s for s in data.load() if s["sample_id"] in done}

    plan, coverage = [], {}
    for sid, s in samples.items():
        qs = list(questions(s, cats))
        total_sessions = len(data.sessions(s))
        if done[sid].get("status") != "done":
            covered = covered_sessions(s, done[sid]["sent"])
            qs = [(qid, qa) for qid, qa in qs if answerable(qa, covered)]
            coverage[sid] = f"{len(covered)}/{total_sessions} sessions"
            log(f"{sid}: PARTIAL — {coverage[sid]} fully ingested · {len(qs)} questions have all their evidence in them")
        else:
            coverage[sid] = f"{total_sessions}/{total_sessions} sessions"
        plan += [(sid, qid, qa) for qid, qa in qs[: args.limit]]
    out_path = RUNS / args.run / "retrieval.jsonl"
    have = set()
    if out_path.exists():
        have = {(r["qid"], r["k"]) for r in map(json.loads, out_path.read_text().splitlines()) if r}
    todo = [(sid, qid, qa, [k for k in ks if (qid, k) not in have]) for sid, qid, qa in plan]
    todo = [t for t in todo if t[3]]
    reuse = {}
    if args.reuse_conversation:
        src = RUNS / args.reuse_conversation / "retrieval.jsonl"
        reuse = {r["qid"]: r["conversation"] for r in map(json.loads, src.read_text().splitlines()) if r and r.get("conversation") is not None}
        log(f"context_search tier reused from {args.reuse_conversation}: {len(reuse)} questions")
    ref_of = {sid: data.to_iso(data.sessions(s)[-1][1])[:10] for sid, s in samples.items()} if args.reference_date else {}
    n_calls = sum(len(t[3]) for t in todo) + (0 if args.no_conversation else sum(1 for t in todo if t[1] not in reuse))
    if meko_search:
        n_calls = sum(len({args.search_limit or k for k in t[3]}) for t in todo)
    log(f"run {args.run} · {len(done)} conversations · {len(plan)} questions · ks {ks} · {len(todo)} questions to search "
        f"({n_calls} calls)")
    if args.dry_run or not todo:
        for sid, qid, qa in plan[:3]:
            print(f"  {qid} [{data.CATEGORIES[qa['category']]}] {qa['question']}")
        return

    from auth import Auth, load_env
    from meko import Meko, MekoError
    from spans import Spans

    cfg = load_env()
    spans = Spans(RUNS / args.run, "retrieve")
    gate = asyncio.Semaphore(args.workers)
    out = out_path.open("a")
    lock = asyncio.Lock()
    failed = 0

    async with Meko(cfg["url"], Auth(cfg), cfg["agent"]) as meko:
        async def meko_rows(qid, sid, want_ks, base, common, qtrace):
            """One meko_search per distinct limit (per k, or once with --search-limit); a row per k."""
            extra = {"reference_date": ref_of[sid]} if args.reference_date else {}
            replies, rows = {}, []
            for k in want_ks:
                lim = args.search_limit or k
                if lim not in replies:
                    replies[lim] = await spans.mcp(qid, meko, "meko_search", k=None if args.search_limit else k,
                                                   summary=meko_summary, limit=lim, force_source="auto",
                                                   pipeline=args.pipeline, **common, **extra)
                res = replies[lim]
                hits, conversation = meko_split(res)
                rows.append({**base, "k": k, "hits": hits, "conversation": conversation, "trace": qtrace,
                             "tool": "meko_search", "pipeline": args.pipeline, "search_limit": lim,
                             "query_analysis": res.get("query_analysis"), "by_source": res.get("by_source"),
                             "debug": res.get("debug")})
            return rows

        async def one(sid, qid, qa, want_ks):
            nonlocal failed
            rec = done[sid]
            base = {"conv": sid, "qid": qid, "category": qa["category"], "question": qa["question"],
                    "gold": qa.get("answer", qa.get("adversarial_answer")), "evidence": data.evidence_ids(qa),
                    "coverage": coverage[sid]}
            # conversation_id is only the Langfuse trace; the datapack does the filtering. One trace per
            # question keeps the memory server's spans for it together (spans/<qid>.jsonl records the id).
            qtrace = uuid.uuid4().hex
            common = dict(read_only=True, query=qa["question"], conversation_id=qtrace,
                          datapack_id=rec["datapack_id"], agent_id=cfg["agent"])
            rows = []
            async with gate:
                try:
                    if meko_search:
                        rows = await meko_rows(qid, sid, want_ks, base, common, qtrace)
                    else:
                        conversation = None
                        if not args.no_conversation and qid in reuse:
                            conversation = reuse[qid]
                        elif not args.no_conversation:
                            cs = await spans.mcp(qid, meko, "context_search", summary=ctx_summary, limit=max(want_ks), force_source="conversation", **common)
                            c = (cs.get("results") or {}).get("conversation") or {}
                            conversation = {"hits": [slim_turn(t) for t in c.get("hits") or []],
                                            "thread": [slim_turn(t) for t in c.get("thread") or []]}
                        for k in want_ks:
                            extra = {"reference_date": ref_of[sid]} if args.reference_date else {}
                            hits = await spans.mcp(qid, meko, "memory_search", k=k, summary=mem_summary, limit=k, **common, **extra)
                            rows.append({**base, "k": k, "hits": [slim(h) for h in hits.get("results", [])],
                                         "conversation": conversation, "trace": qtrace})
                except MekoError as e:
                    failed += len(want_ks)
                    log(f"{qid} FAILED — {str(e)[:120]}")
                    return
            async with lock:
                for row in rows:
                    out.write(json.dumps(row) + "\n")
                out.flush()

        started = time.time()
        await asyncio.gather(*(one(*t) for t in todo))

    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l]
    for k in ks:
        sub = [r for r in rows if r["k"] == k]
        if sub:
            avg = sum(len(r["hits"]) for r in sub) / len(sub)
            empty = sum(1 for r in sub if not r["hits"])
            log(f"k={k:<4} {len(sub)} questions · avg {avg:.1f} {'memory ' if meko_search else ''}hits · {empty} with none"
                + ("  ← server drops hits under MEMORY_SEARCH_MIN_SCORE (0.5 default)" if avg < k * 0.5 and not meko_search else ""))
    if rows and not args.no_conversation:
        import prompts
        turns = [len(prompts.conversation_turns(r.get("conversation"))) for r in rows if r["k"] == ks[0]]
        if turns:
            log(f"conversation tier: avg {sum(turns) / len(turns):.1f} turns per question · "
                f"{sum(1 for t in turns if not t)} questions with none")
    total = sum(len(t[3]) for t in todo)
    log(f"{total - failed}/{total} (question, k) rows done in {time.time() - started:.0f}s · {failed} failed · {out_path}")
    (RUNS / args.run / "retrieve.json").write_text(json.dumps({  # what this phase ran with, for `status.py`
        "finished": time.strftime("%Y-%m-%d %H:%M"), "mcp_url": cfg["url"], "agent_id": cfg["agent"], "trace": meko.trace, "trace_per_question": True,
        "ks": ks, "categories": sorted(cats), "conversation_tier": not args.no_conversation,
        "questions": len(plan), "rows": len(rows), "failed": failed, "tool": args.tool,
        **({"pipeline": args.pipeline, "search_limit": args.search_limit} if meko_search else {})}, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
