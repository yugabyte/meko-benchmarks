#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""One documentation file for the whole fleet that fits a context window, built the way a user would.

The fleet's cards are about 2.1M tokens, so no file holds them. This writes the file that does fit a budget
(thousand tokens, at 2.55 characters per token as in lsb_capped.py): every table of every database with its
one-sentence description, primary and foreign keys, then as many column names (no types or meanings) per table as
the budget allows, the same number for every table so no database is favoured. Business terms are left out: they
alone are about 160k tokens.
  ./fleet_capped.py dump bird && ./fleet_capped.py dump lsb   (once per set)
  ./fleet_capped.py build 150 && ./fleet_capped.py build 80   (combine both into fleet/context_fleet_c<budget>.md)
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLEET = HERE.parents[2] / "datasets" / "text-to-sql" / "fleet"
CHARS_PER_TOKEN = 2.55


def dump(set_):
    os.environ["T2S_SET"] = set_
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parent))
    import lsb_capped as b
    from common import BIRD_DBS, databases
    out = {}
    for db in databases():
        schema, _, comments = b.load(db)
        name = f"{db}_x" if set_ == "bird" and db in BIRD_DBS else db
        tabs = []
        for t, meta in schema.items():
            k = b.keys(meta)
            c = comments.get(t, {})
            tabs.append({"t": t, "desc": b.first_sentence(c.get("comment", "")),
                         "pk": meta["primary_key"], "fk": meta["foreign_keys"],
                         "keys": [[col, m["type"]] for col, m in meta["columns"].items() if col in k],
                         "other": [col for col in meta["columns"] if col not in k]})
        out[name] = tabs
    FLEET.mkdir(parents=True, exist_ok=True)
    (FLEET / f"capped_dump_{set_}.json").write_text(json.dumps(out))
    print(set_, len(out), "databases", sum(len(v) for v in out.values()), "tables")


def render(dbs, n):
    parts = ["# Databases, tables and columns (shortened: the full documentation is far too large to include)\n"]
    for db, tabs in sorted(dbs.items()):
        parts.append(f"\n## Database {db}\n")
        for t in tabs:
            line = f"{t['t']}: {t['desc']}" if t["desc"] else t["t"]
            keys = ", ".join(f"{c} {ty}" for c, ty in t["keys"])
            fk = "; ".join(t["fk"])
            cols = ", ".join(t["other"][:n])
            more = f" (+{len(t['other']) - n} more)" if len(t["other"]) > n else ""
            parts.append(f"- {line}\n  keys: {keys or 'none'}{(' | FK: ' + fk) if fk else ''}"
                         f"{(chr(10) + '  columns: ' + cols + more) if cols else ''}")
    return "\n".join(parts) + "\n"


def build(budget):
    dbs = {}
    for s in ("bird", "lsb"):
        dbs.update(json.loads((FLEET / f"capped_dump_{s}.json").read_text()))
    limit = int(budget * 1000 * CHARS_PER_TOKEN)
    best = None
    for n in range(0, 200):
        text = render(dbs, n)
        if len(text) > limit:
            break
        best = (n, text)
    if best is None:
        raise SystemExit(f"even keys only ({len(render(dbs, 0))} chars) exceed {limit}")
    n, text = best
    (FLEET / f"context_fleet_c{budget}.md").write_text(text)
    print(f"c{budget}: {len(text)} chars (~{len(text) / CHARS_PER_TOKEN / 1000:.0f}k tokens), "
          f"up to {n} non-key columns per table, {len(dbs)} databases")


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2])
    else:
        build(int(sys.argv[2]))
