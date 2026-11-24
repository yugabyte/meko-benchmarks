#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""Re-score every recorded cell of a run from its saved SQL, without calling any model.

  ./rescore.py --run <run> [--scenario novel] [--check]

Use after a change to the gold cache or to result comparison. --check reports differences without writing.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True)
ap.add_argument("--scenario", default="*")
ap.add_argument("--check", action="store_true", help="report changes, do not write them")
a = ap.parse_args()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RUNS  # noqa: E402

conns, changed, total = {}, 0, 0
for p in sorted((RUNS / a.run).glob(f"{a.scenario}/*/*/*/record.json")):
    r = json.loads(p.read_text())
    os.environ["T2S_SET"] = r["set"]
    import common  # re-read per record: the set decides how a db_id maps to a database
    import importlib
    importlib.reload(common)
    total += 1
    ex = False
    if r["sql"]:
        db = r.get("pred_db") or r["db_id"]
        key = (r["set"], db)
        if key not in conns:
            conns[key] = psycopg.connect(common.dsn(db, app="t2s-score"), autocommit=False)
        rows, _ = common.execute(conns[key], r["sql"], timeout_ms=60000)
        ex = common.same_result(rows, common.gold(r.get("gold_id", r["question_id"]), r.get("gold"))["rows"],
                                r.get("conditions"))
    if ex != r["ex"]:
        changed += 1
        print(f"{r['scenario']} {r['arm']} {r['model']} {r['question_id']}: {int(r['ex'])} -> {int(ex)}")
        if not a.check:
            r["ex"] = ex
            p.write_text(json.dumps(r, indent=1, default=str))
print(f"{total} records rescored, {changed} changed" + (" (not written)" if a.check else ""))
