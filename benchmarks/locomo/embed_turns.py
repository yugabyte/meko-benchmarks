#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40", "psycopg[binary]>=3.1", "httpx>=0.27"]
# ///
"""Embed the conversation turns Meko stored without vectors.

  ./embed_turns.py --run <run_id>              rows of this LoCoMo run's datapacks
  ./embed_turns.py --state <path/to/state.json> the datapacks in any state.json
  ./embed_turns.py --all                       every unembedded row in the table
  ./embed_turns.py --run <run_id> --dry-run    count only

conversation_add_message writes each turn into datapacks.conversation_history_search
with embeddings=NULL and expects a database-side worker to fill them in. YugabyteDB
2026.1.0.0 build 118 has no such worker, so context_search's conversation tier
never finds anything. This fills the column directly with the same model and width
the server's contract row declares (text-embedding-3-small, 1536), so query and
rows share one vector space. Re-runnable: only NULL rows are touched.

Needs OPENAI_API_KEY in .env; MEKO_DB_URL there overrides the stack default.
"""

import argparse
import json
import os
import time
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

import psycopg
from openai import OpenAI

from auth import load_env

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"
TABLE = "datapacks.conversation_history_search"
MODEL, DIMS, BATCH = "text-embedding-3-small", 1536, 100
# The stack's YugabyteDB listens on the host's LAN address, not loopback, and that
# address differs per machine — a hardcoded one silently points at another host's
# database and times out. Derive it, and let MEKO_DB_URL override.
def _default_db():
    host = os.getenv("MEKO_DB_HOST")
    if not host:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))        # no packet is sent; picks the egress interface
            host, _ = s.getsockname()
            s.close()
        except OSError:
            host = "127.0.0.1"
    return f"postgresql://yugabyte:yugabyte@{host}:5433/yugabyte"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def datapacks(state_path):
    """Every datapack_id anywhere in a run's state.json, whatever the layout."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("datapack_id"):
                found.append(x["datapack_id"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(json.loads(Path(state_path).read_text()))
    return sorted(set(found))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="restrict to this LoCoMo run's datapacks (runs/locomo/<run>/state.json)")
    ap.add_argument("--state", help="restrict to the datapacks in this state.json (any harness)")
    ap.add_argument("--all", action="store_true", help="every unembedded row, any datapack")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (args.run or args.state or args.all):
        ap.error("pass --run <name>, --state <path> or --all")

    load_env()
    scope, params = "", []
    state_path = args.state or (RUNS / args.run / "state.json" if args.run else None)
    if state_path:
        scope, params = " AND tenant_id = ANY(%s::uuid[])", [datapacks(state_path)]
    where = f"WHERE embeddings IS NULL{scope}"

    with psycopg.connect(os.getenv("MEKO_DB_URL") or _default_db(), autocommit=True) as conn:
        pending = conn.execute(f"SELECT count(*) FROM {TABLE} {where}", params).fetchone()[0]
        log(f"{pending} turns without embeddings" + (f" in {len(params[0])} datapacks" if state_path else ""))
        if args.dry_run or not pending:
            return

        client = OpenAI()
        done, started = 0, time.time()
        while True:
            rows = conn.execute(f"SELECT tenant_id, id, chunk_text FROM {TABLE} {where} ORDER BY created_at LIMIT {BATCH}",
                                params).fetchall()
            if not rows:
                break
            vectors = client.embeddings.create(model=MODEL, input=[r[2] for r in rows], dimensions=DIMS).data
            with conn.cursor() as cur:
                cur.executemany(f"UPDATE {TABLE} SET embeddings = %s::vector WHERE tenant_id = %s AND id = %s",
                                [(json.dumps(v.embedding), r[0], r[1]) for r, v in zip(rows, vectors)])
            done += len(rows)
            if done % 500 < BATCH or done == pending:
                log(f"embedded {done}/{pending}")
        log(f"done: {done} turns in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
