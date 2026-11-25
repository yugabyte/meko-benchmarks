#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Score tables for a finished run.

  ./report.py --run conv26

Table 1: per retrieval depth k — answer F1 and gold-in-context recall by type.
Table 2: per k — F1, BLEU-1 and judge accuracy by type (adversarial excluded:
it has no gold answer to judge against).
Table 3: per k — session-level R@k.

Gold-in-context recall: share of the gold answer's words present somewhere in
the retrieved context (k memories plus any conversation turns) — did retrieval
surface the fact at all. Session R@k (a retrieved memory or turn carries the
evidence turn's session date) is kept for reference but saturates once the
context spans every ingested session.
"""

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import data
import prompts
import score
from tables import RULE, Table, kv_table, visible  # noqa: F401  (re-exported for status.py / compare.py)

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"
ORDER = [4, 1, 2, 3, 5]
NAME = {4: "Single-hop", 1: "Multi-hop", 2: "Temporal", 3: "Open-domain", 5: "Adversarial"}


# ---------------------------------------------------------------- scoring ----

def session_dates(samples):
    return {sid: {n: data.to_iso(d) for n, d, _ in data.sessions(s)} for sid, s in samples.items()}


def turns(row):
    """Conversation turns retrieve.py attached to the row (empty when the tier was off)."""
    return prompts.conversation_turns(row.get("conversation"))


def recall(row, dates):
    """Share of the question's evidence turns whose session is among the retrieved memories' and turns' dates."""
    if not row["evidence"]:
        return None
    got = {str(h.get("created_at", ""))[:19] for h in row["hits"]}
    got |= {str(t.get("session_date", ""))[:19] for t in turns(row)}
    hit = 0
    for ev in row["evidence"]:
        iso = dates[row["conv"]].get(int(ev[1:].split(":")[0]))
        hit += bool(iso) and iso[:19] in got
    return hit / len(row["evidence"])


@lru_cache(maxsize=None)
def stems(text):
    """Normalized, stemmed token set of one text. Cached: the same memory or turn shows up in many rows."""
    return frozenset(score._stem(w) for w in score.normalize(text).split())


def gold_in_context(row):
    """Share of the gold answer's tokens found in the retrieved memories or turns (None for adversarial)."""
    if row["category"] == 5 or row.get("gold") in (None, ""):
        return None
    gold = [score._stem(w) for w in score.normalize(score.gold_text({"category": row["category"], "answer": row["gold"]})).split()]
    if not gold:
        return None
    context = set()
    for text in [h.get("memory", "") for h in row["hits"]] + [t.get("content", "") for t in turns(row)]:
        context |= stems(text or "")
    return sum(1 for g in gold if g in context) / len(gold)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pct(v):
    return "–" if v is None else f"{v * 100:.1f}"


# -------------------------------------------------------------- rendering ----

def build(run):
    ret = [json.loads(l) for l in (RUNS / run / "retrieval.jsonl").read_text().splitlines() if l]
    ans_path = RUNS / run / "answers.jsonl"
    ans = [json.loads(l) for l in ans_path.read_text().splitlines() if l] if ans_path.exists() else []
    samples = {s["sample_id"]: s for s in data.load() if s["sample_id"] in {r["conv"] for r in ret}}
    dates = session_dates(samples)
    ks = sorted({r["k"] for r in ret})
    cats = [c for c in ORDER if any(r["category"] == c for r in ret)]
    coverage = {r["conv"]: r.get("coverage") for r in ret if r.get("coverage")}
    n_by_cat = {c: len({r["qid"] for r in ret if r["category"] == c}) for c in cats}

    n_turns = [len(turns(r)) for r in ret if r["k"] == ks[0]]
    context = (f"k memories + conversation turns (avg {sum(n_turns) / len(n_turns):.1f} turns per question, "
               f"{sum(1 for n in n_turns if not n)} with none)") if any(n_turns) else "k memories only"
    partial = any(v.split("/")[0] != v.split("/")[1].split()[0] for v in coverage.values())
    rows = [("benchmark", "LoCoMo (locomo10.json)"),
            ("questions", f"{len({r['qid'] for r in ret})} · " + ", ".join(f"{NAME[c]} {n_by_cat[c]}" for c in cats)),
            ("conversations", ", ".join(f"{c} {v}" for c, v in coverage.items())),
            ("context", context), ("retrieval depths", ", ".join(str(k) for k in ks))]
    if partial:
        rows.append(("caveat", "partial ingest: only questions whose evidence lies in fully ingested sessions are scored"))
    header = kv_table(f"Run {run}", [rows])

    rows_a, rows_c, summary = [], [], {"run": run, "coverage": coverage, "questions": n_by_cat, "by_k": {}}
    scored = [c for c in cats if c != 5]  # gold-in-context needs a gold answer
    for k in ks:
        rr = [r for r in ret if r["k"] == k]
        aa = {a["qid"]: a for a in ans if a["k"] == k}
        f1 = {c: mean([aa[r["qid"]]["f1"] for r in rr if r["category"] == c and r["qid"] in aa]) for c in cats}
        gc = {c: mean([gold_in_context(r) for r in rr if r["category"] == c]) for c in scored}
        rk = {c: mean([recall(r, dates) for r in rr if r["category"] == c]) for c in cats}
        f1_all = mean([aa[r["qid"]]["f1"] for r in rr if r["qid"] in aa])
        gc_all, rk_all = mean([gold_in_context(r) for r in rr]), mean([recall(r, dates) for r in rr])
        rows_a.append([str(k)] + [pct(f1[c]) for c in cats] + [pct(f1_all)] + [pct(gc[c]) for c in scored] + [pct(gc_all)])
        rows_c.append([str(k)] + [pct(rk[c]) for c in cats] + [pct(rk_all)])
        summary["by_k"][str(k)] = {"f1": {NAME[c]: f1[c] for c in cats}, "f1_all": f1_all,
                                   "gold_in_context": {NAME[c]: gc[c] for c in scored}, "gold_in_context_all": gc_all,
                                   "session_recall": {NAME[c]: rk[c] for c in cats}, "session_recall_all": rk_all}
    short = lambda cs: [NAME[c].split("-")[0] for c in cs]
    table_a = Table("Answer accuracy (F1) and gold-in-context recall by question type, per retrieval depth",
                    ["k"] + short(cats) + ["All"] + short(scored) + ["All"], rows_a,
                    groups=[("", 1), ("F1", len(cats) + 1), ("Gold in context", len(scored) + 1)])
    table_c = Table("Session-level recall (R@k) by question type, per retrieval depth",
                    ["k"] + short(cats) + ["All"], rows_c)

    tables = [table_a]
    judged = [c for c in cats if c != 5]
    if ans and judged:
        rows_b = []
        for k in ks:
            aa = [a for a in ans if a["k"] == k]
            row = [str(k)]
            for c in judged:
                g = [a for a in aa if a["category"] == c]
                f1, b1 = mean([a["f1"] for a in g]), mean([a.get("b1") for a in g])
                j = mean([a["judge"] for a in g if a.get("judge") is not None])
                row += [pct(f1), pct(b1), pct(j)]
                summary["by_k"][str(k)].setdefault("f1_b1_j", {})[NAME[c]] = {"f1": f1, "b1": b1, "j": j, "n": len(g)}
            rows_b.append(row)
        tables.append(Table("F1, BLEU-1 and judge accuracy by question type, per retrieval depth",
                            ["k"] + ["F1", "B1", "J"] * len(judged), rows_b,
                            groups=[("", 1)] + [(NAME[c], 3) for c in judged]))

    tables.append(table_c)
    tables.append(Table("How to read", ["column", "meaning"], [
        ["F1", "token overlap with the gold answer (the LoCoMo paper's scorer)"],
        ["B1", "BLEU-1"],
        ["J", "share judged correct by an LLM judge (mem0's protocol, lenient: one matching item suffices)"],
        ["Adversarial", "no gold answer: its F1 is an abstention rate, and it is excluded from J and gold in context"],
        ["Gold in context", "share of the gold answer's words found in the retrieved memories and turns"],
        ["Session R@k", "a retrieved memory or turn carries the evidence turn's session date; saturates once the context spans every session"],
    ]))
    return header, tables, summary


def main_for(run):
    header, tables, summary = build(run)
    print("\n" + header.boxed() + "\n\n" + "\n\n".join(t.boxed() for t in tables))
    md = "\n\n".join([header.markdown()] + [t.markdown() for t in tables])
    (RUNS / run / "report.md").write_text(md + "\n")
    (RUNS / run / "report.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    main_for(ap.parse_args().run)
