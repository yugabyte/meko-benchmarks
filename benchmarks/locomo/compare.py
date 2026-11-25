#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""A run next to the published LoCoMo results (F1 / BLEU-1 / judge per question type).

  ./compare.py --run <run_id>            largest k in the run's report
  ./compare.py --run <run_id> --k 25     a specific retrieval depth
  ./compare.py --run <run_id> --markdown for docs

Published rows: the Mem0 paper's Table 1 (arXiv 2504.19413) plus Lyzr Cognis's row, placed by
category id (common/published.py). The last line is the run relative to the best published value
per column. Read the caveats it prints: a placement, not a like-for-like score.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import report

RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"
from published import LOCOMO, LOCOMO_TYPES

TYPES = LOCOMO_TYPES  # the harness's order; published rows are placed by category id (see common/published.py)

# name -> 12 numbers: (F1, B1, J) for each type in TYPES; None where the paper has "–".
PUBLISHED = {name: [v for t in TYPES for v in row["by"][t]] for name, row in LOCOMO.items() if name != "Mem0 2026 platform"}

CAVEATS = [
    "Published rows are placed by category id: the Mem0 and Cognis papers print id 1 as Single-Hop and id 4 as Open-Domain,",
    "this harness has 4 = single-hop, 1 = multi-hop, 3 = open-domain. Their answers are gpt-4o-mini / GPT-4 on memories only;",
    "this run's answer model, judge and context are in answer.json. Same questions, different protocol: a placement, not a rank.",
]


def run_row(run, k):
    s = json.loads((RUNS / run / "report.json").read_text())
    ks = sorted(s["by_k"], key=int)
    k = str(k) if k else ks[-1]
    if k not in s["by_k"] or "f1_b1_j" not in s["by_k"][k]:
        sys.exit(f"run {run} has no scored answers at k={k} (have {', '.join(ks)})")
    cells = s["by_k"][k]["f1_b1_j"]
    vals = []
    for t in TYPES:
        c = cells.get(t, {})
        vals += [None if c.get(m) is None else c[m] * 100 for m in ("f1", "b1", "j")]
    return k, vals


def fmt(v, digits=2):
    return "–" if v is None else f"{v:.{digits}f}"


GREEN, RED, END = "\x1b[32m", "\x1b[31m", "\x1b[0m"


def delta(meko, best, colour):
    if meko is None or not best:
        return "–"
    d = (meko - best) / best * 100
    text = f"{'+' if d >= 0 else '−'}{abs(d):.1f}%"
    return f"{GREEN if d >= 0 else RED}{text}{END}" if colour else text


def build(run, k, colour=False):
    k, meko = run_row(run, k)
    best = [max((r[i] for r in PUBLISHED.values() if r[i] is not None), default=None) for i in range(12)]
    rows = [[name] + [fmt(v) for v in vals] for name, vals in PUBLISHED.items()]
    rows.append(report.RULE)
    rows.append([f"Meko · {run} · k={k}"] + [fmt(v, 1) for v in meko])
    rows.append(report.RULE)
    rows.append(["Δ vs best"] + [delta(m, b, colour) for m, b in zip(meko, best)])
    return report.Table(f"LoCoMo: run {run} against published systems (k={k})",
                        ["Method"] + ["F1", "B1", "J"] * len(TYPES), rows,
                        groups=[("", 1)] + [(t, 3) for t in TYPES])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--k", type=int, help="retrieval depth (default: the largest in the report)")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--color", action="store_true", help="colour the Δ row even when piping (e.g. into less -R)")
    a = ap.parse_args()
    if not (RUNS / a.run / "report.json").exists():
        sys.exit(f"no report for run {a.run} yet")
    t = build(a.run, a.k, colour=not a.markdown and (a.color or sys.stdout.isatty()))
    if a.markdown:
        print(t.markdown())
        print("\n" + " ".join(CAVEATS))
    else:
        print(t.boxed())
        print("\n" + "\n".join(CAVEATS))


if __name__ == "__main__":
    main()
