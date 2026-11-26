#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The lsb set (LiveSQLBench-Large), the parts that need no database.

- lsb/databases.json: every database in the dumps (18 with tasks + those without, the
  fleet's distractors), named without the dumps' _template suffix.
- lsb/questions.json: the SELECT ("Query") tasks, in the users' phrasing; gold SQL is merged
  in by lsb_gold.py once the BIRD team's ground-truth file is available (it is gated).
- lsb/<db>/comments.json: the shipped column meanings as column comments (JSONB columns get
  their field meanings too). These are documentation the benchmark ships, not generated comments.
- lsb/<db>/kb.jsonl: the shipped knowledge base (business terms and calculations).
  T2S_SET=lsb ./lsb_prepare.py
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, DOWNLOADS  # noqa: E402

LSB = DOWNLOADS / "lsb-large"
META, DUMPS = LSB / "meta", LSB / "dumps/postgre_table_dumps_large"


def flatten(meaning):
    if isinstance(meaning, str):
        return meaning
    text = meaning.get("column_meaning", "")
    fields = []

    def walk(prefix, d):
        for k, v in d.items():
            if isinstance(v, dict):
                walk(f"{prefix}{k}.", v)
            else:
                fields.append(f"{prefix}{k}: {v}")
    walk("", meaning.get("fields_meaning", {}))
    return text + (" Fields: " + " | ".join(fields) if fields else "")


dbs = sorted(p.name.removesuffix("_template") for p in DUMPS.iterdir() if p.is_dir())
CORPUS.mkdir(parents=True, exist_ok=True)
(CORPUS / "databases.json").write_text(json.dumps(dbs, indent=1))
for db in dbs:
    out = CORPUS / db
    out.mkdir(exist_ok=True)
    if not (META / db).exists():
        print(db, "distractor (no tasks, no shipped documentation)")
        continue
    tables = {}
    for key, meaning in json.loads((META / db / f"{db}_column_meaning_base.json").read_text()).items():
        _, t, c = key.split("|")
        tables.setdefault(t, {"columns": {}})["columns"][c] = flatten(meaning)
    (out / "comments.json").write_text(json.dumps({"tables": tables}, indent=1, ensure_ascii=False))
    shutil.copy(META / db / f"{db}_kb.jsonl", out / "kb.jsonl")
    print(db, len(tables), "tables,", sum(len(t["columns"]) for t in tables.values()), "column meanings")

rows = [json.loads(line) for line in (META / "livesqlbench_large_v1_data.jsonl").read_text().splitlines()]
qs = [{"question_id": r["instance_id"], "db_id": r["selected_database"], "question": r["query"],
       "SQL": None, "conditions": r["conditions"], "difficulty": "high_level" if r["high_level"] in (True, "True") else "base",
       "gold": "lsb"} for r in rows if r["category"] == "Query"]
(CORPUS / "questions.json").write_text(json.dumps(qs, indent=1))
print(len(qs), "SELECT tasks")
