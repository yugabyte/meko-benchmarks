#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Split BIRD Mini-Dev's single PostgreSQL dump into one YSQL script per BIRD database.

  ./bird_split.py <MINIDEV_postgresql/BIRD_dev.sql> <MINIDEV/dev_tables.json> <out_dir>

The official dump puts all 75 tables of the 11 databases in one `public` schema.
Each output file creates one database's tables, loads its data, then adds foreign keys and
indexes. Primary keys are moved into CREATE TABLE: on YugabyteDB the primary key is the
table's sharding key, and adding it afterwards rewrites the table.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HEADER = re.compile(r"^-- (?:Data for )?Name: (\S+)(?: (\S+))?; Type: ([A-Z ]+); Schema: public")


def blocks(path):
    """Yield (name, second_name, type, text) for each pg_dump object block."""
    cur, buf = None, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = HEADER.match(line)
            if m:
                if cur:
                    yield (*cur, "".join(buf))
                cur, buf = (m.group(1), m.group(2), m.group(3)), []
                continue
            if cur:
                buf.append(line)
    if cur:
        yield (*cur, "".join(buf))


def main(dump, tables_json, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    owner = {}
    for db in json.load(open(tables_json)):
        for t in db["table_names_original"]:
            owner[t.lower()] = db["db_id"]

    seq_table, parts = {}, defaultdict(lambda: defaultdict(list))
    items = list(blocks(dump))
    for name, _, typ, text in items:
        m = re.search(r'OWNED BY public\."?(\w+)"?\.', text)
        if typ == "SEQUENCE OWNED BY" and m:
            seq_table[name] = m.group(1)

    for name, second, typ, text in items:
        table = seq_table.get(name, name)
        if typ == "INDEX":
            table = re.search(r' ON public\."?(\w+)"? ', text).group(1)
        db = owner.get(table)
        if db is None:
            sys.exit(f"no database owns {typ} {name}")
        text = re.sub(r"^ALTER (TABLE|SEQUENCE) .* OWNER TO .*;\n", "", text, flags=re.M)
        if typ == "CONSTRAINT" and "PRIMARY KEY" in text:
            cols = re.search(r"PRIMARY KEY \((.+?)\);", text).group(1)
            parts[db]["pk"].append((table, second, cols))
        elif typ in ("TABLE", "SEQUENCE", "SEQUENCE OWNED BY", "DEFAULT"):
            parts[db]["ddl"].append((table, text))
        elif typ in ("TABLE DATA", "SEQUENCE SET"):
            parts[db]["data"].append((table, text))
        elif typ in ("FK CONSTRAINT", "CONSTRAINT", "INDEX"):
            parts[db]["post"].append((table, text))
        else:
            sys.exit(f"unhandled type {typ} for {name}")

    for db, p in parts.items():
        pks = {t: (n, c) for t, n, c in p["pk"]}
        ddl = []
        for table, text in p["ddl"]:
            if table in pks and re.search(rf'^CREATE TABLE public\.("?){table}\1 \(', text, re.M):
                n, c = pks.pop(table)
                text = re.sub(r"\n\);", f",\n    CONSTRAINT {n} PRIMARY KEY ({c})\n);", text, count=1)
            ddl.append(text)
        if pks:
            sys.exit(f"{db}: primary keys not inlined: {pks}")
        body = ["SET client_encoding = 'UTF8';\nSET standard_conforming_strings = on;\n"]
        body += ddl + [t for _, t in p["data"]] + [t for _, t in p["post"]]
        (out / f"{db}.sql").write_text("".join(body))
        print(db, len(p["ddl"]), "ddl", len(p["data"]), "tables of data", len(p["post"]), "post")


if __name__ == "__main__":
    main(*sys.argv[1:])
