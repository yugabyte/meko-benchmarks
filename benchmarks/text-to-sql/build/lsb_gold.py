#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Merge LiveSQLBench-Large's ground truth into lsb/questions.json.

The BIRD team sends the ground truth by email to keep it out of crawlers, so the merged
questions.json is gitignored. Each SELECT task gets its gold statement and the ids of the
knowledge-base entries it needs (kb_ids, for an oracle-knowledge condition).
  T2S_SET=lsb ./lsb_gold.py <livesqlbench_large_v1_gt_kg_testcases_*.jsonl>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS  # noqa: E402

gt = {r["instance_id"]: r for r in map(json.loads, Path(sys.argv[1]).read_text().splitlines())}
qs = json.loads((CORPUS / "questions.json").read_text())
kept = []
for q in qs:
    g = gt[q["question_id"]]
    # Every SELECT task in Large-v1 has one statement and no custom test case; anything else would
    # need the benchmark's own evaluator, so it is dropped and counted.
    if len(g["sol_sql"]) != 1 or g["test_cases"]:
        continue
    kept.append({**q, "SQL": g["sol_sql"][0].strip().rstrip(";").strip(), "kb_ids": g["external_knowledge"]})
(CORPUS / "questions.json").write_text(json.dumps(kept, indent=1))
print(f"{len(kept)} of {len(qs)} SELECT tasks have gold SQL")
