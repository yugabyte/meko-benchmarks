#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Load the LiveSQLBench-Large PostgreSQL dumps into YugabyteDB, one database each (the lsb set).

The dumps are one pg_dump file per table (plus a *_full.sql per database, which for some databases
holds only part of the tables, so it is not used). Foreign keys are taken out of the table files
and added after every table is loaded, so file order does not matter. Each database gets hstore
and citext (as the BIRD team's init script does), a NOLOGIN role root owns the objects as in the
dumps, and t2s_agent gets read access. Databases are colocated: ~1,100 tables and their indexes
as separate tablets exceed a single node's tablet replica limit. Rows are single-row INSERTs, loaded with
yb_disable_transactional_writes for speed. Resumable: a database with a load marker is skipped.

  ./lsb_load.py [db ...]   (default: every database in the dumps)   Env: YB_HOST, YB_PORT, YB_PASSWORD, PARALLEL (3)
"""
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import DOWNLOADS, YB_HOST, YB_PORT  # noqa: E402

DUMPS = DOWNLOADS / "lsb-large" / "dumps" / "postgre_table_dumps_large"
LOGS = DOWNLOADS / "load-logs" / "lsb"
PSQL = ["psql", "-h", YB_HOST, "-p", str(YB_PORT), "-U", "yugabyte", "-X", "-q"]


DUP_TYPE = re.compile(r'ERROR:  type "[^"]+" already exists')
FK = re.compile(r"ALTER TABLE ONLY [^;]+?ADD CONSTRAINT [^;]+? FOREIGN KEY [^;]+;", re.S)


def tables(db):
    """Per-table files, with enum_definitions first: tables use its types, and it can sort after them."""
    files = (p for p in (DUMPS / f"{db}_template").glob("*.sql") if not p.stem.endswith("_full"))
    return sorted(files, key=lambda p: (not p.stem.startswith("enum"), p.name))


def psql(db, *args, env=None):
    return subprocess.run([*PSQL, "-d", db, *args], capture_output=True, text=True, env=env)


def load(db):
    log, tmp = LOGS / f"{db}.log", LOGS / f"{db}.part.sql"
    t0, errors, fks = time.time(), 0, []
    env = {**os.environ, "PGOPTIONS": "-c yb_disable_transactional_writes=on"}
    files = tables(db)
    with open(log, "w") as fh:
        for f in files:
            text = f.read_text()
            fks += FK.findall(text)
            tmp.write_text(FK.sub("", text))
            r = psql(db, "-v", "ON_ERROR_STOP=0", "-f", str(tmp), env=env)
            # Some table files create enum types that enum_definitions already made: harmless duplicates.
            errs = [line for line in r.stderr.splitlines() if "ERROR" in line and not DUP_TYPE.search(line)]
            errors += len(errs)
            fh.write(f"== {f.stem}: rc={r.returncode} errors={len(errs)}\n" + "\n".join(errs[:20]) + "\n")
        tmp.write_text("SET search_path = public;\n" + "\n".join(fks) + "\n")
        r = psql(db, "-v", "ON_ERROR_STOP=0", "-f", str(tmp))
        errs = [line for line in r.stderr.splitlines() if "ERROR" in line]
        errors += len(errs)
        fh.write(f"== {len(fks)} foreign keys: errors={len(errs)}\n" + "\n".join(errs[:50]) + "\n")
        done = [f"COMMENT ON DATABASE {db} IS 't2s_loaded'"] if not errors else []  # resume marker, outside the agent's view
        for sql in ("GRANT USAGE ON SCHEMA public TO t2s_agent", "GRANT SELECT ON ALL TABLES IN SCHEMA public TO t2s_agent",
                    "CREATE EXTENSION IF NOT EXISTS pg_stat_statements", "ANALYZE", *done):
            r = psql(db, "-c", sql)
            fh.write(f"== {sql}: {r.returncode} {r.stderr.strip()[:300]}\n")
    tmp.unlink(missing_ok=True)
    return f"{db}: {len(files)} tables, {len(fks)} foreign keys in {time.time() - t0:.0f}s, {errors} errors (log {log})"


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    dbs = sys.argv[1:] or sorted(p.name.removesuffix("_template") for p in DUMPS.iterdir() if p.is_dir())
    psql("yugabyte", "-c", "DO $$BEGIN CREATE ROLE root NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END$$;",
         "-c", "DO $$BEGIN CREATE ROLE t2s_agent LOGIN PASSWORD 't2s_agent'; EXCEPTION WHEN duplicate_object THEN NULL; END$$;")
    todo = []
    for db in dbs:  # YugabyteDB rejects concurrent CREATE DATABASE, so create them one at a time first
        if psql("yugabyte", "-tAc", f"SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                f"WHERE datname = '{db}'").stdout.strip() == "t2s_loaded":
            print(db, "already loaded")
            continue
        psql("yugabyte", "-c", f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
        r = psql("yugabyte", "-c", f"CREATE DATABASE {db} ENCODING 'UTF8' COLOCATION = true")
        if r.returncode:
            raise SystemExit(f"CREATE DATABASE {db}: {r.stderr}")
        psql(db, "-c", "CREATE EXTENSION IF NOT EXISTS hstore", "-c", "CREATE EXTENSION IF NOT EXISTS citext",
             "-c", f"ALTER DATABASE {db} SET default_text_search_config = 'pg_catalog.english'")
        todo.append(db)
    with ThreadPoolExecutor(int(os.environ.get("PARALLEL", "3"))) as pool:
        for line in pool.map(load, todo):
            print(line, flush=True)


if __name__ == "__main__":
    main()
