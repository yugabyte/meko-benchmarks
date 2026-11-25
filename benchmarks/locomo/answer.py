#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40", "httpx>=0.27"]
# ///
"""Phase 3 — answer each question from its retrieved memories, then score.

  ./answer.py --run conv26                         all ks in retrieval.jsonl
  ./answer.py --run conv26 --ks 50 --prompt simple official short-phrase prompt instead of mem0's
  ./answer.py --run conv26 --prompt two-step       mem0's reasoning, then a call that compresses it to a short phrase
  ./answer.py --run conv26 --per-category 40       trial on 40 random questions of each type (seeded)
  ./answer.py --run conv26 --no-judge              F1 only, no judge calls
  ./answer.py --run full-cj --rejudge-from full --judge cognis   score another run's answers again with this judge
  ./answer.py --run x --prompts-file runs/locomo/x/prompts.json  use edited prompts ({NAME: text}, see common/overrides.py)
  ./answer.py --run conv26 --dry-run               print one prompt, call nothing

The model reads the retrieved memories and, when retrieve.py fetched them,
the verbatim conversation turns too (prompts.context_block).
Two scores per answer: the paper's token F1 (score.py) and mem0's binary
LLM judge (prompts.py), so results line up with published LoCoMo numbers.
Writes runs/locomo/<run>/answers.jsonl (resumable) and prints a table per k.
Needs OPENAI_API_KEY in .env.
"""

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import data
import overrides
import prompts
import score
from spans import Spans, llm_span

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"

STYLES = ("mem0", "simple", "two-step")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def reasoning_model(model):
    """Reasoning models reject `temperature` and count their thinking against the token cap."""
    return model.startswith(("gpt-5", "o1", "o3", "o4")) or "terra" in model


def responses_api(model):
    """OpenAI serves the codex models only through the Responses endpoint, not chat completions."""
    return "codex" in model


def reference_dates(samples):
    """mem0 anchors temporal reasoning to when the conversations took place; we use each one's last session."""
    return {s["sample_id"]: prompts.human_date(data.to_iso(data.sessions(s)[-1][1])) for s in samples}


def subset(rows, per_category, seed):
    """The question ids of a seeded trial: `per_category` of each type, the same set on every machine."""
    keep = set()
    for cat in sorted({r["category"] for r in rows}):
        qids = sorted({r["qid"] for r in rows if r["category"] == cat})
        keep.update(random.Random(f"{seed}-{cat}").sample(qids, min(per_category, len(qids))))
    return keep


def build_prompt(row, style, ref_date):
    """The first (for `two-step`, the only reasoning) call. mem0's prompt forbids "not mentioned",
    so adversarial questions always get the paper's short prompt with its abstain hint."""
    if style in ("mem0", "two-step") and row["category"] != 5:
        return prompts.MEM0_ANSWER.format(memories=prompts.context_block(row),
                                          question=row["question"], reference_date=ref_date)
    return score.build_prompt(row["question"], row["category"], prompts.context_block(row))


def compress_prompt(row, reasoning):
    return prompts.COMPRESS_PROMPT.format(question=row["question"], reasoning=reasoning.strip(),
                                          context=prompts.context_block(row),
                                          format_rule=prompts.FORMAT_RULES[row["category"]])


def final_answer(text, style, category=None):
    """mem0's prompt ends with the answer after "ANSWER:"; like mem0's own runner, take the text after
    the last marker (the reasoning may mention the word earlier). No marker: the whole reply is scored."""
    if style in ("mem0", "two-step") and category != 5:
        head, sep, tail = text.rpartition("ANSWER:")
        return (tail if sep else text).strip()
    return text.strip()


def clean_short(text):
    """The compression reply, minus a quoted or labelled wrapper the model sometimes adds."""
    t = text.strip().splitlines()[0].strip() if text.strip() else ""
    for label in ("Short answer:", "Answer:", "ANSWER:"):
        if t.startswith(label):
            t = t[len(label):].strip()
    return t.strip('"“”‘’\' ').rstrip(".")


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--ks", help="subset of the ks in retrieval.jsonl")
    ap.add_argument("--prompt", choices=STYLES, default="mem0",
                    help="mem0 = mem0's reasoning prompt; simple = the paper's short-answer prompt; "
                         "two-step = mem0's reasoning, then a second call that compresses it to a short phrase")
    ap.add_argument("--model", default="gpt-5.6-terra", help="answer model (both calls of two-step)")
    ap.add_argument("--judge", choices=["mem0", "cognis", "strict"], default="mem0",
                    help="judge prompt: mem0 = mem0's 2026 lenient grader; cognis = the Mem0 paper's grader as Cognis reprints it; "
                         "strict = no partial credit, no date tolerance")
    ap.add_argument("--judge-model", default="gpt-4.1-mini")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--rejudge-from", metavar="RUN", help="take RUN's answers as they are and only run the judge again")
    ap.add_argument("--memories-only", action="store_true", help="drop the retrieved conversation turns from the context (ablation)")
    ap.add_argument("--per-category", type=int, help="trial: answer only this many random questions of each type")
    ap.add_argument("--seed", type=int, default=42, help="seed of --per-category")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--prompts-file", help="JSON {NAME: text} of edited prompts to use for this run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    applied = overrides.apply(args.prompts_file, {**{n: prompts for n in ("MEM0_ANSWER", "COMPRESS_PROMPT", "FORMAT_RULES", "JUDGE_SYSTEM",
                                                                        "MEM0_JUDGE", "COGNIS_JUDGE", "STRICT_JUDGE")},
                                                 "QA_PROMPT": score, "HINTS": score}) if args.prompts_file else []
    if applied:
        log(f"prompt overrides from {args.prompts_file}: {', '.join(applied)}")

    ret_path = RUNS / args.run / "retrieval.jsonl"
    if args.rejudge_from:
        src = RUNS / args.rejudge_from / "answers.jsonl"
        if not src.exists():
            sys.exit(f"no {src} to re-judge")
        rows = [json.loads(l) for l in src.read_text().splitlines() if l]
        (RUNS / args.run).mkdir(parents=True, exist_ok=True)
        if not (ret_path.exists() or ret_path.is_symlink()):  # the report reads retrieval rows; share the source run's
            ret_path.symlink_to(Path("..") / args.rejudge_from / "retrieval.jsonl")
    else:
        if not ret_path.exists():
            sys.exit(f"no {ret_path} — run retrieve.py --run {args.run} first")
        rows = [json.loads(l) for l in ret_path.read_text().splitlines() if l]
    if args.ks:
        keep = {int(k) for k in args.ks.split(",")}
        rows = [r for r in rows if r["k"] in keep]
    if args.per_category:
        keep = subset(rows, args.per_category, args.seed)
        rows = [r for r in rows if r["qid"] in keep]
    if args.memories_only:
        for r in rows:
            r["conversation"] = None  # the answer model sees the k memories alone, as memory-only systems do
    ref = {} if args.rejudge_from else reference_dates([s for s in data.load() if s["sample_id"] in {r["conv"] for r in rows}])

    out_path = RUNS / args.run / "answers.jsonl"
    have = {(r["qid"], r["k"]) for r in map(json.loads, out_path.read_text().splitlines())} if out_path.exists() else set()
    todo = [r for r in rows if (r["qid"], r["k"]) not in have]
    log(f"run {args.run} · {len(rows)} (question, k) rows" + (f" · trial of {args.per_category} per type" if args.per_category else "")
        + (f" · {len(todo)} to re-judge from {args.rejudge_from} with judge={args.judge}" if args.rejudge_from
           else f" · {len(todo)} to answer · prompt={args.prompt} model={args.model}")
        + (" · memories only" if args.memories_only else ""))

    if args.dry_run:
        r = todo[0] if todo else rows[0]
        if args.rejudge_from:
            print(prompts.judge_prompt(args.judge, r["question"], r["gold"], r["answer"])[:3000])
            return
        print(build_prompt(r, args.prompt, ref[r["conv"]])[:3000])
        if args.prompt == "two-step" and r["category"] != 5:
            print("\n\n=== second call ===\n" + compress_prompt(r, "<reasoning from the first call>")[:1500])
        return

    from auth import load_env
    load_env()  # puts OPENAI_API_KEY from .env into the environment
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    gate = asyncio.Semaphore(args.workers)
    out = out_path.open("a")
    lock = asyncio.Lock()

    from openai import BadRequestError, RateLimitError
    paused = {"since": None}

    async def call(fn, **kw):
        """Run one API call; when the account is out of credits, wait five minutes and try again
        rather than crash the run, so a top-up lets it continue by itself (gives up after a day)."""
        for _ in range(288):
            try:
                r = await fn(**kw)
                if paused["since"]:
                    log(f"credits are back after {time.time() - paused['since']:.0f}s; continuing"); paused["since"] = None
                return r
            except RateLimitError as e:
                if "insufficient_quota" not in str(e) and "credit" not in str(e):
                    raise
                if not paused["since"]:
                    paused["since"] = time.time(); log("OpenAI reports no credits remaining; pausing, retrying every 5 minutes")
                await asyncio.sleep(300)
        raise RuntimeError("no OpenAI credits for 24 hours; giving up")

    spans = Spans(RUNS / args.run, "answer")

    async def ask(model, system, user, max_tokens, effort=None, tag=None):
        """One model call. A reasoning model that spends its whole budget thinking answers with a
        400 "max_tokens or model output limit was reached" instead of an empty message, so that
        error is retried once with three times the budget; `effort` asks a reasoning model to
        think less (the compression call needs none) and is dropped if the model rejects it.
        `tag` = (qid, call name, k): every attempt goes to spans/<qid>.jsonl with its prompt and raw reply."""
        def rec(t0, params, r=None, text=None, err=None):
            if tag:
                sp = llm_span(tag[1], tag[2], model, t0, params, system, user, r, text, err)
                sp["phase"] = "judge" if tag[1] == "judge" else "answer"
                spans.write(tag[0], sp)
        if responses_api(model):
            t0, params = time.time(), {"api": "responses", "max_output_tokens": max_tokens}
            try:
                r = await call(client.responses.create, model=model, input=user, max_output_tokens=max_tokens,
                               **({"instructions": system} if system else {}))
            except Exception as e:
                rec(t0, params, err=f"{type(e).__name__}: {str(e)[:400]}"); raise
            rec(t0, params, r, r.output_text or "")
            return r.output_text or ""
        kw = {} if reasoning_model(model) else {"temperature": 0}
        if effort and reasoning_model(model):
            kw["reasoning_effort"] = effort
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        for attempt in range(3):
            t0, params = time.time(), {"api": "chat.completions", "max_completion_tokens": max_tokens, **kw}
            try:
                r = await call(client.chat.completions.create, model=model, max_completion_tokens=max_tokens, messages=messages, **kw)
                text = r.choices[0].message.content or ""
                rec(t0, params, r, text)
                return text
            except BadRequestError as e:
                text = str(e)
                rec(t0, params, err=f"BadRequestError: {text[:400]}")
                if "max_tokens or model output limit" in text and attempt < 2:
                    max_tokens *= 3
                    continue
                if "reasoning_effort" in text and "reasoning_effort" in kw:
                    kw.pop("reasoning_effort")
                    continue
                raise
            except Exception as e:
                rec(t0, params, err=f"{type(e).__name__}: {str(e)[:400]}")
                raise

    async def one(row):
        async with gate:
            if args.rejudge_from:
                answer, long_answer = row["answer"], row.get("long_answer")
            else:
                raw = await ask(args.model, None, build_prompt(row, args.prompt, ref[row["conv"]]),
                                8000 if reasoning_model(args.model) else 800,  # a reasoning model's thinking counts
                                tag=(row["qid"], "answer", row["k"]))  # a reasoning model's thinking counts
                long_answer = final_answer(raw, args.prompt, row["category"])
                answer = long_answer
                if args.prompt == "two-step" and row["category"] != 5:
                    short = await ask(args.model, None, compress_prompt(row, raw),
                                      4000 if reasoning_model(args.model) else 40, effort="low",
                                      tag=(row["qid"], "compress", row["k"]))
                    answer = clean_short(short) or long_answer
            verdict, reason = None, None
            if not args.no_judge and row["category"] != 5:
                j = await ask(args.judge_model, prompts.JUDGE_SYSTEM,
                              prompts.judge_prompt(args.judge, row["question"], row["gold"], answer),
                              2000 if reasoning_model(args.judge_model) else 400,
                              tag=(row["qid"], "judge", row["k"]))
                try:
                    parsed = json.loads(j[j.index("{"):j.rindex("}") + 1])
                    verdict, reason = parsed.get("label", "").upper() == "CORRECT", parsed.get("reasoning")
                except (ValueError, json.JSONDecodeError):
                    verdict, reason = "WRONG" not in j.upper() and "CORRECT" in j.upper(), j[:200]
        result = {k: row[k] for k in ("conv", "qid", "k", "category", "question", "gold")}
        qa = {"category": row["category"], "answer": row["gold"]}
        result.update(answer=answer, f1=score.score(qa, answer), b1=score.bleu1(answer, score.gold_text(qa)),
                      judge=verdict, judge_reason=reason)
        if args.rejudge_from:
            result.update({k: row.get(k) for k in ("hits", "turns", "context_chars")})
        else:
            result.update(hits=len(row["hits"]), turns=len(prompts.conversation_turns(row.get("conversation"))),
                          context_chars=len(prompts.context_block(row)))
        if long_answer is not None and long_answer != answer:
            result["long_answer"] = long_answer  # what the reasoning call ended with, before compression
        async with lock:
            out.write(json.dumps(result) + "\n")
            out.flush()

    started = time.time()
    await asyncio.gather(*(one(r) for r in todo))
    log(f"answered {len(todo)} in {time.time() - started:.0f}s")
    info = {  # what this phase ran with, for `status.py`
        "finished": time.strftime("%Y-%m-%d %H:%M"), "answer_model": args.model,
        "temperature": None if reasoning_model(args.model) else 0, "prompt": args.prompt,
        "trial": {"per_category": args.per_category, "seed": args.seed} if args.per_category else None,
        "rejudged_from": args.rejudge_from,
        "context": "memories only" if args.memories_only else "memories+turns",
        "judge": None if args.no_judge else args.judge,
        "judge_model": None if args.no_judge else args.judge_model,
        "prompts": prompts.fingerprints(args.prompt, args.judge), "prompt_overrides": applied, "rows": len(rows)}
    if args.rejudge_from:  # the answers are the source run's: record its answer setup, not this invocation's defaults
        src_info = RUNS / args.rejudge_from / "answer.json"
        if src_info.exists():
            src = json.loads(src_info.read_text())
            info.update({k: src.get(k) for k in ("answer_model", "temperature", "prompt", "trial", "context") if k in src})
            info["prompts"] = {**src.get("prompts", {}), "judge": info["prompts"]["judge"]}
    (RUNS / args.run / "answer.json").write_text(json.dumps(info, indent=1))

    import report
    report.main_for(args.run)


if __name__ == "__main__":
    asyncio.run(main())
