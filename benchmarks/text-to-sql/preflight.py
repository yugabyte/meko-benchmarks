#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "psycopg[binary]==3.3.6", "httpx>=0.27"]
# ///
"""Checks before building data or running a scenario. Reads no secret values: it only asks whether each setting
is present and whether the services accept it.

  ./preflight.py                      tools, settings, database and Meko
  ./preflight.py --scenario novel     also the scenario's data, answer cache and Meko datapacks

Exit code 1 if anything required fails. Each FAIL line says what to do.
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = {"novel": "novel", "bird": "bird", "lsb": "lsb", "fleet": "fleet", "learn": "lsb"}
ok = True


def line(status, name, detail=""):
    global ok
    ok = ok and status != "FAIL"
    print(f"  {status:<5} {name:<16} {detail}", flush=True)


def tools():
    for t, why in (("uv", "runs every script"), ("claude", "Claude Code answers the questions"),
                   ("psql", "loads the BIRD and LiveSQLBench dumps")):
        line("ok" if shutil.which(t) else "FAIL", t, why if shutil.which(t) else f"not on PATH ({why})")
    if shutil.which("claude"):
        out = subprocess.run(["claude", "-p", "Reply with the word ready.", "--model", "claude-haiku-5-5",
                              "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}',
                              "--setting-sources", "project", "--no-session-persistence", "--output-format", "json"],
                             capture_output=True, text=True, timeout=180, cwd="/", stdin=subprocess.DEVNULL)
        try:
            res = json.loads(out.stdout)
            good = not res.get("is_error") and "ready" in res.get("result", "").lower()
        except ValueError:
            good, res = False, {"result": (out.stderr or out.stdout)[:120]}
        line("ok" if good else "FAIL", "claude login", "a Haiku call works" if good else
             f"Claude Code cannot answer: log in with `claude` or set ANTHROPIC_API_KEY ({str(res.get('result'))[:100]})")


def database(common):
    import psycopg
    try:
        with psycopg.connect(common.dsn("yugabyte", user="yugabyte"), connect_timeout=10) as c:
            v = c.execute("SELECT version()").fetchone()[0]
            agent = c.execute("SELECT 1 FROM pg_roles WHERE rolname = 't2s_agent'").fetchone()
        line("ok", "yugabytedb", f"{common.YB_HOST}:{common.YB_PORT} {v.split(' on ')[0][:60]}")
        line("ok" if agent else "info", "role t2s_agent", "exists" if agent else "created by the first build step")
    except Exception as e:  # noqa: BLE001
        line("FAIL", "yugabytedb", f"cannot connect to {common.YB_HOST}:{common.YB_PORT} as yugabyte: "
             f"{str(e).splitlines()[0][:100]}. Set YB_HOST, YB_PORT and YB_PASSWORD in .env")


async def meko_check(common):
    try:
        url, token = common.meko_settings()
    except Exception as e:  # noqa: BLE001
        line("FAIL", "meko", f"no token: set MEKO_USER_TOKEN, or MEKO_EMAIL and MEKO_PASSWORD, in .env ({e})")
        return
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
    try:
        client = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}, timeout=60)
        async with client, streamable_http_client(url, http_client=client) as st:
            async with ClientSession(st[0], st[1]) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
        need = {"knowledgebase_search", "knowledgebase_upload_document", "datapack_create", "memory_add"}
        line("ok" if need <= names else "FAIL", "meko", url if need <= names else f"missing tools: {sorted(need - names)}")
    except Exception as e:  # noqa: BLE001
        line("FAIL", "meko", f"{url}: {type(e).__name__} {str(e)[:100]}. Check MEKO_MCP_URL and the token")


def scenario(common, name):
    set_ = SETS[name]
    corpus = common.DATA / set_
    q = corpus / "questions.json"
    if not q.exists():
        line("FAIL", f"{set_} data", f"{q} is missing: run ./prepare.sh {set_}")
        return
    qs = json.loads(q.read_text())
    with_sql = [x for x in qs if x.get("SQL")]
    line("ok" if with_sql else "FAIL", f"{set_} data", f"{len(qs)} questions, {len(with_sql)} with answer SQL"
         if with_sql else "no answer SQL: merge the LiveSQLBench answer file (./prepare.sh lsb)")
    missing = [x for x in with_sql if not (common.gold_dir(x.get("gold")) /
                                          f"{x.get('source_id', x['question_id'])}.json").exists()]
    line("ok" if not missing else "FAIL", "answer cache", "complete" if not missing else
         f"{len(missing)} answers not cached: T2S_SET={set_} ./verify_gold.py")
    if name != "learn":
        cfg = common.RUNS / f"meko-{set_}.json"
        line("ok" if cfg.exists() else "FAIL", "meko datapacks", "loaded (check indexing with meko_load.py wait)"
             if cfg.exists() else f"not loaded: T2S_SET={set_} ./meko_load.py setup && ... wait")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=SETS)
    a = ap.parse_args()
    if a.scenario:
        os.environ["T2S_SET"] = SETS[a.scenario]
    sys.path.insert(0, str(HERE))
    import common
    env = common.REPO / ".env"
    line("ok" if env.exists() else "FAIL", ".env", "present" if env.exists() else "copy .env.example to .env")
    tools()
    database(common)
    asyncio.run(meko_check(common))
    if a.scenario:
        scenario(common, a.scenario)
    print("\npreflight", "passed" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
