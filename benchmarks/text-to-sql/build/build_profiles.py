#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""C0 + C2: capture each database's schema, keys, indexes, sharding and value profiles.

Writes <set>/<db>/schema.json. Profiles come from pg_stats (run ANALYZE first), plus a few
sample values per column. Nothing here sees benchmark questions, evidence or descriptions.
"""
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, databases, dsn  # noqa: E402


def short(v, n=60):
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def profile(db):
    with psycopg.connect(dsn(db, user="yugabyte", app="t2s-profile"), autocommit=True) as c:
        tables = {}
        for (t, est) in c.execute(
                "SELECT c.relname, c.reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1").fetchall():
            tables[t] = {"rows_estimate": est, "columns": {}, "primary_key": [], "foreign_keys": [], "indexes": []}
        for t, col, typ, nullable in c.execute(
                "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position").fetchall():
            if t in tables:
                tables[t]["columns"][col] = {"type": typ, "nullable": nullable == "YES"}
        for t, cname, ctype, cdef in c.execute(
                "SELECT conrelid::regclass::text, conname, contype, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace AND contype IN ('p', 'f')").fetchall():
            t = t.strip('"')
            if ctype == "p":
                tables[t]["primary_key"] = [x.strip().strip('"') for x in cdef.split("(", 1)[1].split(")")[0].split(",")]
                tables[t]["primary_key_def"] = cdef
            else:
                tables[t]["foreign_keys"].append(cdef)
        for t, idef in c.execute(
                "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'public'").fetchall():
            tables[t]["indexes"].append(idef.replace("public.", ""))
        for t, col, null_frac, n_distinct, mcv, mcf, hist in c.execute(
                "SELECT tablename, attname, null_frac, n_distinct, most_common_vals::text, most_common_freqs::text, "
                "histogram_bounds::text FROM pg_stats WHERE schemaname = 'public'").fetchall():
            if t not in tables or col not in tables[t]["columns"]:
                continue
            p = tables[t]["columns"][col]
            p["null_frac"] = round(null_frac, 3)
            rows = max(tables[t]["rows_estimate"], 1)
            p["distinct"] = int(n_distinct if n_distinct >= 0 else -n_distinct * rows)
            if mcv:
                vals = c.execute("SELECT unnest(%s::text::text[])", (mcv,)).fetchall()
                freqs = json.loads(mcf.replace("{", "[").replace("}", "]")) if mcf else []
                p["top_values"] = [[short(v[0]), round(f, 3)] for v, f in zip(vals[:8], freqs[:8])]
            if hist:
                b = c.execute("SELECT (x)[1], (x)[array_length(x, 1)] FROM (SELECT %s::text::text[] x) s",
                              (hist,)).fetchone()
                p["range"] = [short(b[0]), short(b[1])]
        for t, meta in tables.items():
            cols = list(meta["columns"])
            q = 'SELECT {} FROM public."{}" LIMIT 3'.format(", ".join(f'"{x}"' for x in cols), t)
            meta["sample_rows"] = [[short(v, 40) for v in r] for r in c.execute(q).fetchall()]
    return tables


for db in databases():
    out = CORPUS / db
    out.mkdir(parents=True, exist_ok=True)
    schema = profile(db)
    (out / "schema.json").write_text(json.dumps(schema, indent=1, default=str))
    print(db, len(schema), "tables", sum(len(t["columns"]) for t in schema.values()), "columns")
