#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6", "sqlglot==30.25.0"]
# ///
"""Build the cryptic bird set: <db>_x databases with enterprise-style table and column names.

Every table becomes tbNN_<abbr> and every column c_<abbr> (one name per column name within a
database, as in a data dictionary); constraint, index and sequence names become opaque too, so no
original identifier survives in the catalog. Data is unchanged. All 500 gold statements are rewritten
with sqlglot, and a question is kept only if its rewritten gold returns exactly the original gold
result. Writes bird/mapping.json and bird/questions.json, then the gold cache runs/text-to-sql/gold/bird.

  T2S_SET=bird ./bird_cryptic.py   (reads the split dump in downloads/split, bird-plain's schema.json and gold)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import psycopg
import sqlglot
from sqlglot import exp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BIRD_DBS, DATA, DOWNLOADS, MINIDEV, YB_HOST, YB_PORT, canon, execute, gold, gold_dir, to_json  # noqa: E402,E501

OUT = DATA / "bird"
SPLIT = DOWNLOADS / "split"


def abbr(name, n):
    s = re.sub(r"[^a-z0-9]", "", name.lower())
    return (s[0] + re.sub(r"[aeiou]", "", s[1:]))[:n] if s else "x"


def mapping(db):
    schema = json.loads((DATA / "bird-plain" / db / "schema.json").read_text())
    tables, cols, used = {}, {}, set()
    for i, t in enumerate(sorted(schema), 1):
        tables[t] = f"tb{i:02d}_{abbr(t, 4)}"
    for c in sorted({c for t in schema.values() for c in t["columns"]}):
        base, k = f"c_{abbr(c, 6)}", 1
        name = base
        while name in used:
            k += 1
            name = f"{base}{k}"
        used.add(name)
        cols[c] = name
    return tables, cols


def conn(db, autocommit=True):
    return psycopg.connect(f"host={YB_HOST} port={YB_PORT} dbname={db} user=yugabyte", autocommit=autocommit)


def built(x):
    with conn("yugabyte") as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (x,)).fetchone():
            return False
    with conn(x) as c:
        return bool(c.execute("SELECT 1 FROM pg_class WHERE relname LIKE 'tb%%' AND relkind = 'r'").fetchone())


def build_db(db, tables, cols):
    x = f"{db}_x"
    if built(x):  # resumable: an earlier run finished this database
        return
    with conn("yugabyte") as c:
        c.execute(f"DROP DATABASE IF EXISTS {x}")
        c.execute(f"CREATE DATABASE {x}")
    subprocess.run(["psql", "-h", YB_HOST, "-p", str(YB_PORT), "-U", "yugabyte", "-X", "-q", "-d", x,
                    "-v", "ON_ERROR_STOP=1", "-f", str(SPLIT / f"{db}.sql")], check=True)
    with conn(x) as c:
        for i, (cname, rel) in enumerate(c.execute(
                "SELECT conname, conrelid::regclass::text FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace").fetchall(), 1):
            c.execute(f'ALTER TABLE {rel} RENAME CONSTRAINT "{cname}" TO k{i:03d}')
        for i, (iname,) in enumerate(c.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname NOT IN "
                "(SELECT conname FROM pg_constraint)").fetchall(), 1):
            c.execute(f'ALTER INDEX "{iname}" RENAME TO ix{i:03d}')
        for i, (sname,) in enumerate(c.execute(
                "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'").fetchall(), 1):
            c.execute(f'ALTER SEQUENCE "{sname}" RENAME TO sq{i:03d}')
        for t, meta_cols in ((t, [r[0] for r in c.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                (t,)).fetchall()]) for t in tables):
            for col in meta_cols:
                c.execute(f'ALTER TABLE "{t}" RENAME COLUMN "{col}" TO {cols[col]}')
            c.execute(f'ALTER TABLE "{t}" RENAME TO {tables[t]}')
        c.execute("GRANT USAGE ON SCHEMA public TO t2s_agent")
        c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO t2s_agent")
        c.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        c.execute("ANALYZE")


def rewrite(sql, tables, cols):
    tree = sqlglot.parse_one(sql, read="postgres")
    aliases = {t.alias.lower() for t in tree.find_all(exp.Table) if t.alias}
    selected = {a.alias.lower() for a in tree.find_all(exp.Alias)}
    for t in tree.find_all(exp.Table):
        if t.name.lower() in tables:
            t.set("this", exp.to_identifier(tables[t.name.lower()]))
    for c in tree.find_all(exp.Column):
        ident = c.this
        # Quoted identifiers keep their case (e.g. "Enrollment (K-12)"); unquoted ones fold to lower case.
        name = ident.name if getattr(ident, "quoted", False) else c.name.lower()
        if name in cols and not (name.lower() in selected and not c.table):
            c.set("this", exp.to_identifier(cols[name]))
        q = c.table.lower() if c.table else ""
        if q and q in tables and q not in aliases:
            c.set("table", exp.to_identifier(tables[q]))
    return tree.sql(dialect="postgres")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    maps, kept, dropped = {}, [], []
    qs = json.loads((MINIDEV / "mini_dev_postgresql.json").read_text())
    for db in BIRD_DBS:
        tables, cols = mapping(db)
        maps[db] = {"tables": tables, "columns": cols}
        build_db(db, tables, cols)
        print(db, "built:", len(tables), "tables,", len(cols), "column names")
    (OUT / "mapping.json").write_text(json.dumps(maps, indent=1))
    out_gold = gold_dir("bird")
    out_gold.mkdir(parents=True, exist_ok=True)
    conns = {}
    for q in qs:
        db = q["db_id"]
        m = maps[db]
        try:
            sql = rewrite(q["SQL"], m["tables"], m["columns"])
        except Exception as e:  # noqa: BLE001
            dropped.append((q["question_id"], f"rewrite: {e}"))
            continue
        conns.setdefault(db, conn(f"{db}_x", autocommit=False))
        rows, err = execute(conns[db], sql, timeout_ms=120000)
        orig = gold(q["question_id"], "bird-plain")
        same = rows is not None and {tuple(canon(v) for v in r) for r in rows} == \
            {tuple(canon(v) for v in r) for r in orig["rows"]}
        if not same:
            dropped.append((q["question_id"], err or "result differs"))
            continue
        kept.append({**q, "SQL": sql, "gold": "bird"})
        (out_gold / f"{q['question_id']}.json").write_text(json.dumps(
            {"rows": [[to_json(v) for v in r] for r in rows], "error": None, "n": len(rows)}, default=str))
    (OUT / "questions.json").write_text(json.dumps(kept, indent=1))
    print(f"{len(kept)} questions kept, {len(dropped)} dropped")
    for d in dropped:
        print("DROP", *d)


if __name__ == "__main__":
    main()
