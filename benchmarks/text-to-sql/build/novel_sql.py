#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""Render logical SQL for the novel set ([table] and [table.column] placeholders) and optionally run it.

  ./novel_sql.py "<sql>"      run and print up to 30 rows
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from novel_db import COLS, DB, TABLES  # noqa: E402

PH = re.compile(r"\[([a-z_*]+)(?:\.([a-z0-9_]+))?\]")


def render(sql):
    def sub(m):
        t, c = m.group(1), m.group(2)
        if c is None:
            return TABLES[t]
        return COLS[(t, c)]
    return PH.sub(sub, sql)


if __name__ == "__main__":
    import psycopg
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from common import dsn, execute
    sql = render(sys.argv[1])
    with psycopg.connect(dsn(DB), autocommit=False) as c:
        rows, err = execute(c, sql)
    print(err or "\n".join(" | ".join(map(str, r)) for r in rows[:30]) + f"\n({len(rows)} rows)")
