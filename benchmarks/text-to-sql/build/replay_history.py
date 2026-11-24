#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""C3 source: replay the history split's gold SQL so pg_stat_statements holds a real query log.

Resets pg_stat_statements, runs each history question's gold statement 1-5 times (a random
frequency, so the log has a usage signal), then saves each database's statements, with
YugabyteDB's DocDB columns, to <set>/<db>/pgss.json. Test questions are never replayed.
"""
import json
import random
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, SEED, databases, dbname, dsn, execute  # noqa: E402

rng = random.Random(SEED)
history = json.loads((CORPUS / "history.json").read_text())  # written by bird_history.py
with psycopg.connect(dsn("yugabyte", user="yugabyte"), autocommit=True) as c:
    c.execute("SELECT pg_stat_statements_reset()")

conns, failed = {}, 0
for q in history:
    db = q["db_id"]
    conns.setdefault(db, psycopg.connect(dsn(db, user="t2s_agent", app="t2s-history"), autocommit=False))
    for _ in range(rng.randint(1, 5)):
        _, err = execute(conns[db], q["SQL"], timeout_ms=120000)
        if err:
            failed += 1
            break
for c in conns.values():
    c.close()

with psycopg.connect(dsn("yugabyte", user="yugabyte"), autocommit=True) as c:
    cols = [r[0] for r in c.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'pg_stat_statements' "
        "ORDER BY ordinal_position").fetchall()]
    keep = [k for k in ("query", "calls", "rows", "mean_exec_time", "total_exec_time", "docdb_read_rpcs",
                        "docdb_rows_scanned", "docdb_read_operations", "docdb_wait_time") if k in cols]
    for db in databases():
        rows = c.execute(
            f"SELECT {', '.join('s.' + k for k in keep)} FROM pg_stat_statements s "
            "JOIN pg_database d ON d.oid = s.dbid JOIN pg_roles r ON r.oid = s.userid "
            "WHERE d.datname = %s AND r.rolname = 't2s_agent' AND s.query NOT ILIKE 'SET %%' "
            "AND s.query NOT ILIKE 'BEGIN%%' AND s.query NOT ILIKE 'COMMIT%%' ORDER BY s.calls DESC", (dbname(db),)).fetchall()
        out = CORPUS / db
        out.mkdir(parents=True, exist_ok=True)
        (out / "pgss.json").write_text(json.dumps([dict(zip(keep, r)) for r in rows], indent=1, default=float))
        print(db, len(rows), "statements")
print(f"{len(history)} history statements, {failed} failed")
print("DocDB columns captured:", [k for k in keep if k.startswith("docdb")])
