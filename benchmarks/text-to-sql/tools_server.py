#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "psycopg[binary]==3.3.6", "httpx>=0.27"]
# ///
"""The agent's database tools (stdio MCP server), identical in every arm except for what they reveal.

Env:
  T2S_DB        database to answer against
  T2S_DBS       fleet: comma-separated databases; every tool takes a database argument,
                list_databases is added, and T2S_DB is unset
  T2S_COMMENTS  1: list_tables / describe_table show catalog comments; file:<comments.json>: comments
                from that file instead; 0: hidden (arm A0)
  T2S_MAX_SQL   run_sql budget per question (default 6)
  T2S_APP       application_name, so pg_stat_statements attributes the agent's queries per arm
  T2S_LOG       JSONL file recording every tool call with its latency
"""
import json
import os
import sys
import time
from pathlib import Path

import psycopg
from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dsn, execute  # noqa: E402

DB = os.environ.get("T2S_DB", "")
FLEET = [d for d in os.environ.get("T2S_DBS", "").split(",") if d]
# "1": catalog comments; "file:<path>": comments from a comments.json instead; else none.
_COMMENTS = os.environ.get("T2S_COMMENTS", "0")
COMMENTS = _COMMENTS == "1" or _COMMENTS.startswith("file:")
FILE_COMMENTS = json.loads(Path(_COMMENTS[5:]).read_text())["tables"] if _COMMENTS.startswith("file:") else None


def table_comment(name, catalog):
    if FILE_COMMENTS is None:
        return catalog
    return (FILE_COMMENTS.get(name) or {}).get("comment")


def column_comment(table, col, catalog):
    if FILE_COMMENTS is None:
        return catalog
    return ((FILE_COMMENTS.get(table) or {}).get("columns") or {}).get(col)


MAX_SQL = int(os.environ.get("T2S_MAX_SQL", "6"))
LOG = os.environ.get("T2S_LOG")
ROW_CAP = 20

mcp = MCPServer("db")
state = {"sql": 0}
conns = {}


def conn(db):
    if db not in conns:
        conns[db] = psycopg.connect(dsn(db, app=os.environ.get("T2S_APP", "t2s-agent")), autocommit=False)
    return conns[db]


def log(tool, args, out, t0, **extra):
    if LOG:
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"tool": tool, "args": args, "ms": round((time.time() - t0) * 1000),
                                 "out_chars": len(out), **extra}) + "\n")


def rows(db, sql, params=()):
    c = conn(db)
    with c.transaction():
        return c.execute(sql, params).fetchall()


def unknown_db(db):
    return None if db in FLEET else f"No database named {db}. Call list_databases to see the databases."


def _list_tables(db) -> str:
    t0 = time.time()
    out = []
    for name, est, comment in rows(db,
            "SELECT c.relname, c.reltuples::bigint, obj_description(c.oid, 'pg_class') FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1"):
        comment = table_comment(name, comment)
        out.append(f"{name} (~{est} rows)" + (f": {comment}" if COMMENTS and comment else ""))
    text = "\n".join(out)
    log("list_tables", {"database": db} if FLEET else {}, text, t0)
    return text


def _describe_table(db, table_name) -> str:
    t0 = time.time()
    args = {"database": db, "table_name": table_name} if FLEET else {"table_name": table_name}
    name = table_name.strip().strip('"')
    # Exact name first (LiveSQLBench has mixed-case tables), then case-insensitively.
    oid = rows(db, "SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                   "WHERE n.nspname = 'public' AND c.relkind = 'r' AND lower(c.relname) = lower(%s) "
                   "ORDER BY c.relname = %s DESC", (name, name))
    if not oid:
        text = f"No table named {table_name}. Call list_tables to see the tables."
        log("describe_table", args, text, t0, error=True)
        return text
    oid, relname = oid[0]
    shown = relname if relname == relname.lower() else f'"{relname}"'
    c = table_comment(relname, rows(db, "SELECT obj_description(%s, 'pg_class')", (oid,))[0][0])
    out = [f"Table {shown}" + (f": {c}" if COMMENTS and c else ""), "Columns:"]
    for name, typ, notnull, comment in rows(db,
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, col_description(a.attrelid, a.attnum) "
            "FROM pg_attribute a WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum", (oid,)):
        comment = column_comment(relname, name, comment)
        out.append(f"  {name} {typ}{' NOT NULL' if notnull else ''}" + (f" -- {comment}" if COMMENTS and comment else ""))
    for kind, d in rows(db, "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s "
                        "AND contype IN ('p', 'f', 'u') ORDER BY contype DESC", (oid,)):
        out.append(f"{'Primary key' if kind == 'p' else 'Unique' if kind == 'u' else 'Foreign key'}: {d}")
    for src, d in rows(db, "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) FROM pg_constraint "
                       "WHERE confrelid = %s AND contype = 'f'", (oid,)):
        out.append(f"Referenced by: {src} {d}")
    for (d,) in rows(db, "SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid = %s", (oid,)):
        out.append(f"Index: {d.replace('public.', '')}")
    text = "\n".join(out)
    log("describe_table", args, text, t0)
    return text


def _run_sql(db, sql) -> str:
    t0 = time.time()
    args = {"database": db, "sql": sql} if FLEET else {"sql": sql}
    state["sql"] += 1
    if state["sql"] > MAX_SQL:
        text = f"SQL budget exhausted ({MAX_SQL} statements). Give your final answer now."
        log("run_sql", args, text, t0, error=True, budget=True)
        return text
    result, err = execute(conn(db), sql, timeout_ms=15000, max_rows=ROW_CAP + 1)
    if err:
        text = f"ERROR: {err}"
    else:
        shown = result[:ROW_CAP]
        text = "\n".join(" | ".join("NULL" if v is None else str(v)[:80] for v in r) for r in shown)
        text = (text or "(no rows)") + (f"\n... more than {ROW_CAP} rows" if len(result) > ROW_CAP else
                                        f"\n({len(result)} rows)")
    log("run_sql", args, text, t0, error=bool(err), empty=(not err and not result))
    return text


if FLEET:
    @mcp.tool()
    def list_databases() -> str:
        """List the databases you can query, with their number of tables."""
        t0 = time.time()
        out = [f"{db} ({rows(db, 'SELECT count(*) FROM pg_tables WHERE schemaname = %s', ('public',))[0][0]} tables)"
               for db in FLEET]
        text = "\n".join(out)
        log("list_databases", {}, text, t0)
        return text

    @mcp.tool()
    def list_tables(database: str) -> str:
        """List the tables in one database with their approximate row counts."""
        return unknown_db(database) or _list_tables(database)

    @mcp.tool()
    def describe_table(database: str, table_name: str) -> str:
        """Describe one table: columns and types, primary key, foreign keys in and out, and indexes."""
        return unknown_db(database) or _describe_table(database, table_name)

    @mcp.tool()
    def run_sql(database: str, sql: str) -> str:
        """Run one read-only SQL statement in one database and return up to 20 rows. Use it to check values and
        test your query."""
        return unknown_db(database) or _run_sql(database, sql)
else:
    @mcp.tool()
    def list_tables() -> str:
        """List the tables in the database with their approximate row counts."""
        return _list_tables(DB)

    @mcp.tool()
    def describe_table(table_name: str) -> str:
        """Describe one table: columns and types, primary key, foreign keys in and out, and indexes."""
        return _describe_table(DB, table_name)

    @mcp.tool()
    def run_sql(sql: str) -> str:
        """Run one read-only SQL statement and return up to 20 rows. Use it to check values and test your query."""
        return _run_sql(DB, sql)


if __name__ == "__main__":
    mcp.run()
