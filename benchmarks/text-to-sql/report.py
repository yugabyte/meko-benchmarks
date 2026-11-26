#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Score tables for a run: accuracy, change against no context, significance and cost, per scenario.

  ./report.py --run my-run                    writes runs/text-to-sql/my-run/report.md and two CSV files
  ./report.py --run my-run --out docs/runs/text-to-sql/my-run

For each scenario the baseline is the arm with no context (A0; for learning, L-S, no learning). Per arm and
model: execution accuracy, the change against the baseline in percentage points with an exact McNemar test on
the paired questions (* where p < 0.05), list-price cost per question and per correct answer, and mean
seconds per question. Every number comes from the run's record.json files, so rerunning regenerates them.
results-long.csv has one row per scenario, arm and model; results-wide.csv one row per scenario and arm.
"""
import argparse
import csv
import json
import statistics as st
from math import comb
from pathlib import Path

RUNS = Path(__file__).resolve().parents[2] / "runs" / "text-to-sql"
MODELS = ["haiku", "sonnet", "opus"]
SCENARIOS = {  # title, baseline, arms in report order
    "novel": ("Small novel database with random names (pollination contractor, 10 tables)", "A0",
              ["A0", "A1", "A3", "A4t"]),
    "bird": ("BIRD Mini-Dev with cryptic names (11 databases)", "A0", ["A0", "A1", "A3", "A4t"]),
    "lsb": ("LiveSQLBench-Large (about 1,000 columns per database)", "A0",
            ["A0", "A3", "A4t", "A3c-55", "A3c-35", "A3c-35+M"]),
    "fleet": ("Fleet of 32 databases behind one agent", "A0",
              ["A0", "A1", "A3", "A3f-150", "A3f-80", "A3f-80+M", "A4t"]),
    "learn": ("Learning from corrections (LiveSQLBench, 11 databases, Sonnet)", "L-S", ["L-S", "L-F", "L-Mm", "L-Mk"]),
}
NAMES = {
    "A0": "No context (tools only)", "A1": "Comments", "A3": "Documentation file in the prompt",
    "A4t": "Meko search",
    "A3c-55": "Shortened file (~55k tokens)", "A3c-35": "Shortened file (~35k tokens)",
    "A3c-35+M": "Shortened file (~35k tokens) + Meko search",
    "L-S": "No learning", "L-F": "Lessons file in the prompt", "L-Mm": "Meko memory", "L-Mk": "Meko knowledge base",
}
FLEET_NAMES = {"A3": "Index of databases and tables in the prompt",
               "A3f-150": "One file of every table with descriptions, keys and some columns (~150k tokens)",
               "A3f-80": "One file of every table with descriptions and keys (~80k tokens)",
               "A3f-80+M": "The ~80k-token file + Meko search"}


def load(run, scenario, arm, model):
    out = {}
    for f in (RUNS / run / scenario / arm / model).glob("*/record.json"):
        r = json.loads(f.read_text())
        out[str(r["question_id"])] = r
    return out


def cell(rs):
    n = len(rs)
    ex = sum(r["ex"] for r in rs.values())
    cost = sum(r["cost_list_usd"] + r.get("correct_cost_usd", 0) for r in rs.values())
    return {"n": n, "ex": ex, "acc": 100 * ex / n, "per_q": cost / n, "per_correct": cost / ex if ex else None,
            "wall": st.mean(r["wall_s"] + r.get("correct_wall_s", 0) for r in rs.values()),
            "turns": st.mean(r.get("num_turns") or 0 for r in rs.values())}


def mcnemar(a, b):
    """Exact two-sided McNemar p for paired per-question results."""
    common = set(a) & set(b)
    up = sum(1 for q in common if a[q]["ex"] and not b[q]["ex"])
    dn = sum(1 for q in common if b[q]["ex"] and not a[q]["ex"])
    n = up + dn
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(up, dn) + 1)) / 2 ** n)


def rows(run):
    out = []
    for sc, (title, base_arm, arms) in SCENARIOS.items():
        for arm in arms:
            for m in MODELS:
                rs, bs = load(run, sc, arm, m), load(run, sc, base_arm, m)
                if not rs:
                    continue
                c = cell(rs)
                b = cell(bs) if bs else None
                is_base = arm == base_arm
                p = None if is_base or not bs else mcnemar(rs, bs)
                name = FLEET_NAMES[arm] if sc == "fleet" and arm in FLEET_NAMES else NAMES[arm]
                out.append({
                    "scenario": sc, "scenario_title": title, "arm": arm, "arm_name": name, "model": m.capitalize(),
                    "questions": c["n"], "correct": c["ex"], "accuracy_pct": round(c["acc"], 1),
                    "baseline_accuracy_pct": round(b["acc"], 1) if b else "",
                    "change_pts": "" if is_base or not b else round(c["acc"] - b["acc"], 1),
                    "p_value": "" if p is None else round(p, 4), "significant_p05": "" if p is None else int(p < 0.05),
                    "cost_per_question_usd": round(c["per_q"], 4),
                    "cost_per_correct_usd": "" if c["per_correct"] is None else round(c["per_correct"], 4),
                    "cost_per_correct_pct_of_baseline": "" if is_base or not b or not c["per_correct"] or not b["per_correct"]
                    else round(100 * c["per_correct"] / b["per_correct"], 1),
                    "seconds_per_question": round(c["wall"], 1), "turns_per_question": round(c["turns"], 1),
                })
    return out


def fmt(r):
    acc = f"{r['accuracy_pct']:.1f}%"
    if r["change_pts"] == "":
        return f"{acc} · ${r['cost_per_question_usd']:.4f}"
    star = "*" if r["significant_p05"] else ""
    return f"{acc} ({r['change_pts']:+.1f}{star}) · ${r['cost_per_question_usd']:.4f}"


def markdown(run, data):
    out = [f"# Text-to-SQL results: run `{run}`", "",
           "Each cell: execution accuracy, then in brackets the change in percentage points against the scenario's "
           "baseline (`*` where the paired exact McNemar test gives p < 0.05), then the list-price cost per question. "
           "`-` means the arm was not run for that model.", ""]
    for sc, (title, base_arm, arms) in SCENARIOS.items():
        sr = [r for r in data if r["scenario"] == sc]
        if not sr:
            continue
        n = max(r["questions"] for r in sr)
        out += [f"## {title}", "", f"{n} questions. Baseline: {NAMES[base_arm].lower()}.", "",
                "| Arm | " + " | ".join(m.capitalize() for m in MODELS) + " |", "|-|-|-|-|"]
        for arm in arms:
            ar = {r["model"]: r for r in sr if r["arm"] == arm}
            if not ar:
                continue
            name = next(iter(ar.values()))["arm_name"]
            out.append(f"| {name} | " + " | ".join(fmt(ar[m.capitalize()]) if m.capitalize() in ar else "-"
                                                   for m in MODELS) + " |")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", help="directory for report.md and the CSV files (default: the run's directory)")
    a = ap.parse_args()
    data = rows(a.run)
    if not data:
        raise SystemExit(f"no records under {RUNS / a.run}")
    out = Path(a.out) if a.out else RUNS / a.run
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(markdown(a.run, data))
    with open(out / "results-long.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)
    metrics = ["accuracy_pct", "change_pts", "p_value", "cost_per_question_usd", "cost_per_correct_usd"]
    wide = {}
    for r in data:
        wide.setdefault((r["scenario"], r["arm"], r["arm_name"]), {})[r["model"]] = r
    with open(out / "results-wide.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "arm", "arm_name"] + [f"{m.capitalize()} {k}" for k in metrics for m in MODELS])
        for key, by in wide.items():
            w.writerow(list(key) + [by[m.capitalize()][k] if m.capitalize() in by else "" for k in metrics for m in MODELS])
    print(f"wrote {out / 'report.md'}, results-long.csv ({len(data)} rows), results-wide.csv ({len(wide)} rows)")


if __name__ == "__main__":
    main()
