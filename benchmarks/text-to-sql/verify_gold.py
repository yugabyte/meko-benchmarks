#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""Run every gold statement of a set on YugabyteDB and cache its result for scoring.

  T2S_SET=novel ./verify_gold.py

Writes runs/text-to-sql/gold/<gold>/<question_id>.json ({rows, error, ms, n}), where <gold> is the question's
"gold" field (fleet questions keep their source set's) or the set's name, and prints failures and slow
statements. Questions whose gold SQL is not available yet (LiveSQLBench before its answer file is merged)
are skipped.
"""
import json
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dsn, execute, gold_dir, questions, to_json  # noqa: E402

conns, fails, slow = {}, [], []
qs = [q for q in questions() if q.get("SQL")]
for q in qs:
    out = gold_dir(q.get("gold"))
    out.mkdir(parents=True, exist_ok=True)
    db = q["db_id"]
    if db not in conns:
        conns[db] = psycopg.connect(dsn(db, app="t2s-gold"), autocommit=False)
    t0 = time.time()
    rows, err = execute(conns[db], q["SQL"], timeout_ms=120000)
    ms = round((time.time() - t0) * 1000)
    rec = {"rows": [[to_json(v) for v in r] for r in (rows or [])], "error": err, "ms": ms,
           "n": None if rows is None else len(rows)}
    (out / f"{q['question_id']}.json").write_text(json.dumps(rec, default=str))
    if err:
        fails.append((q["question_id"], db, err))
    if ms > 5000:
        slow.append((q["question_id"], db, ms))
print(f"{len(qs)} gold statements, {len(fails)} failed, {len(slow)} slower than 5 s")
for f in fails:
    print("FAIL", *f)
for s in slow:
    print("SLOW", *s)
