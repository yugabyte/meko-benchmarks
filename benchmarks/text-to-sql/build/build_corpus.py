#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""Package the documentation for each arm from the same table cards, so every arm gets the same content.

- <set>/<db>/cards/<table>.md   one card per table (comments, value profiles and query-log digest), plus
                                the business-term cards when the set has a knowledge base
- <set>/<db>/context.md         all cards concatenated: the documentation file for arm A3
- COMMENT ON in each database    the comments, shown by the tools in every arm except A0
meko_load.py uploads the same card files to Meko for arm A4t.
  T2S_SET=bird ./build_corpus.py
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_lib import card, kb_cards, load, q  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, databases, dsn  # noqa: E402


def lit(s):
    return "'" + s.replace("'", "''") + "'"


def apply_comments(db, comments, schema):
    with psycopg.connect(dsn(db, user="yugabyte", app="t2s-comments"), autocommit=True) as c:
        ver = lambda: c.execute(  # noqa: E731
            "SELECT current_version FROM pg_yb_catalog_version WHERE db_oid = "
            "(SELECT oid FROM pg_database WHERE datname = current_database())").fetchone()[0]
        v0, t0, n = ver(), time.time(), 0
        for t, tc in comments.items():
            if t not in schema:  # shipped documentation can name tables the dump does not have
                continue
            if tc.get("comment"):
                c.execute(f"COMMENT ON TABLE {q(t)} IS {lit(tc['comment'])}")
                n += 1
            for col, text in tc.get("columns", {}).items():
                if col in schema[t]["columns"]:
                    c.execute(f"COMMENT ON COLUMN {q(t)}.{q(col)} IS {lit(text)}")
                    n += 1
        return {"statements": n, "seconds": round(time.time() - t0, 1), "catalog_version_before": v0,
                "catalog_version_after": ver()}


def main():
    manifest = {}
    for db in databases():
        schema, _, comments = load(db)
        cards_dir = CORPUS / db / "cards"
        cards_dir.mkdir(exist_ok=True)
        bodies = {**{t: card(db, t) for t in schema}, **kb_cards(db)}
        for t, body in bodies.items():
            (cards_dir / f"{t}.md").write_text(body + "\n")
        context = f"# Database {db}: tables, columns, value profiles, query history and business terms\n\n" + \
            "\n\n".join(bodies.values()) + "\n"
        (CORPUS / db / "context.md").write_text(context)
        manifest[db] = {"tables": len(bodies), "context_chars": len(context),
                        "corpus_sha256": hashlib.sha256(context.encode()).hexdigest()[:16],
                        "comments": apply_comments(db, comments, schema)}
        print(db, json.dumps(manifest[db]))
    (CORPUS / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
