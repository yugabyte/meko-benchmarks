#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40", "httpx>=0.27"]
# ///
"""The exact calls one (question, k) row made, reconstructed from the run's files: the two MCP searches with their
arguments and what came back, and the OpenAI calls with their prompts rendered exactly as answer.py renders them.

  ./calls.py --run full-twostep --qid conv-26:q16 --k 25      JSON on stdout (the console's "Calls" panel)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import answer as ans  # the answer phase's own prompt builders
import data
import prompts

RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--qid", required=True)
    ap.add_argument("--k", type=int, required=True)
    a = ap.parse_args()
    d = RUNS / a.run
    row = None
    needle = json.dumps(a.qid)
    for line in (d / "retrieval.jsonl").open():
        if needle in line:
            r = json.loads(line)
            if r.get("qid") == a.qid and r.get("k") == a.k:
                row = r
                break
    if not row:
        sys.exit(f"no retrieval row for {a.qid} at k={a.k}")
    answers = [json.loads(l) for l in (d / "answers.jsonl").open() if l.strip()] if (d / "answers.jsonl").exists() else []
    arow = next((x for x in answers if x["qid"] == a.qid and x["k"] == a.k), None)
    cfg = json.loads((d / "run.json").read_text()) if (d / "run.json").exists() else {}
    ainfo = json.loads((d / "answer.json").read_text()) if (d / "answer.json").exists() else {}
    state = json.loads((d / "state.json").read_text()) if (d / "state.json").exists() else {}
    rec = state.get("conversations", {}).get(row["conv"], {})
    style, judge = ainfo.get("prompt") or cfg.get("prompt") or "mem0", ainfo.get("judge") or cfg.get("judge") or "mem0"
    ret = json.loads((d / "retrieve.json").read_text()) if (d / "retrieve.json").exists() else {}
    ks = sorted({int(x) for x in str(cfg.get("ks", "10,25,50")).split(",")})
    common = {"query": row["question"], "datapack_id": rec.get("datapack_id", "?"), "agent_id": ret.get("agent_id", "meko"),
              "conversation_id": ret.get("trace", "<the client run's trace id: a uuid per retrieve.py process>"), "read_only": True}
    conv = row.get("conversation") or {}
    hits = row.get("hits") or []
    calls = [
        {"phase": "retrieve", "kind": "mcp", "tool": "context_search", "args": {**common, "limit": max(ks), "force_source": "conversation"},
         "result": f"{len(conv.get('hits') or [])} chunk hits · thread of {len(conv.get('thread') or [])} turns"
                   + (f" · closest distance {min((h.get('distance') or 9) for h in conv['hits']):.3f}" if conv.get("hits") and any(h.get("distance") is not None for h in conv["hits"]) else ""),
         "note": "one call per question, shared by every k; the server ignores limit for this source (10 candidates, top 3 conversations, 50 turns)"},
        {"phase": "retrieve", "kind": "mcp", "tool": "memory_search", "args": {**common, "limit": a.k},
         "result": f"{len(hits)} memories" + (f" · scores {hits[0].get('score'):.3f} … {hits[-1].get('score'):.3f}" if hits and hits[0].get("score") is not None else ""),
         "hits": [{"memory": h.get("memory"), "created_at": h.get("created_at"), "score": h.get("score"), "raw_similarity_score": h.get("raw_similarity_score")} for h in hits],
         "note": "one call per (question, k)"},
    ]
    samples = {s["sample_id"]: s for s in data.load() if s["sample_id"] == row["conv"]}
    ref = ans.reference_dates(list(samples.values()))[row["conv"]] if samples else "?"
    model, judge_model = ainfo.get("answer_model") or cfg.get("answer_model") or "?", ainfo.get("judge_model") or cfg.get("judge_model") or "?"
    rejudged = ainfo.get("rejudged_from")
    if not rejudged:
        p1 = ans.build_prompt(row, style, ref)
        calls.append({"phase": "answer", "kind": "openai", "tool": f"chat.completions · {model}", "args": {"max_completion_tokens": 8000 if ans.reasoning_model(model) else 800,
                      "temperature": None if ans.reasoning_model(model) else 0, "prompt": "MEM0_ANSWER" if style in ("mem0", "two-step") and row["category"] != 5 else "QA_PROMPT (paper) + hint"},
                      "prompt_text": p1, "reply": (arow or {}).get("long_answer") or (arow or {}).get("answer"),
                      "note": "the reply shown is what the run kept: the text after the last ANSWER: (reasoning before it is not stored)"})
        if style == "two-step" and row["category"] != 5:
            calls.append({"phase": "answer", "kind": "openai", "tool": f"chat.completions · {model} · compression", "args": {"reasoning_effort": "low", "max_completion_tokens": 4000 if ans.reasoning_model(model) else 40},
                          "prompt_text": ans.compress_prompt(row, (arow or {}).get("long_answer") or ""), "reply": (arow or {}).get("answer"),
                          "note": "rendered with the stored reasoning answer in place of the full reasoning text, which the run does not keep"})
    else:
        calls.append({"phase": "answer", "kind": "kept", "tool": f"answers kept from run {rejudged}", "args": {}, "reply": (arow or {}).get("answer"), "note": "re-judge: no answer call"})
    if arow and row["category"] != 5 and arow.get("judge") is not None:
        calls.append({"phase": "judge", "kind": "openai", "tool": f"chat.completions · {judge_model} · {judge} judge", "args": {"system": prompts.JUDGE_SYSTEM, "max_completion_tokens": 2000 if ans.reasoning_model(judge_model) else 400},
                      "prompt_text": prompts.judge_prompt(judge, row["question"], row["gold"], arow["answer"]),
                      "reply": f"{'CORRECT' if arow['judge'] else 'WRONG'}" + (f" · {arow.get('judge_reason')}" if arow.get("judge_reason") else ""), "note": "categories 1–4 only"})
    print(json.dumps({"qid": a.qid, "k": a.k, "datapack_id": rec.get("datapack_id"), "sessions": rec.get("sessions", {}), "calls": calls}, ensure_ascii=False))


if __name__ == "__main__":
    main()
