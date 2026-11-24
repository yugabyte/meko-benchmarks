#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""The fleet: every bird and lsb database behind one agent.

Run after the bird and lsb sets are built. Writes datasets/text-to-sql/fleet/:
- fleet_dbs.json: all 11 BIRD cryptic databases (<db>_x) and every LiveSQLBench database.
- questions.json: 100 bird and 100 lsb questions, stratified by database, db_id = the real database.
- fleet/cards/<database>__<card>.md: every card of both sets, headed with the real database name.
  meko_load.py uploads them to one datapack for the search arms.
- index.md: arm A3's index, each database with its tables (and a table comment's first sentence).
  T2S_SET=fleet ./fleet_prepare.py
"""
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BIRD_DBS, CORPUS, DATA, SEED  # noqa: E402

PER_SET = 100
SETS = {"bird": DATA / "bird", "lsb": DATA / "lsb"}


def real(set_, db):
    return f"{db}_x" if set_ == "bird" and db in BIRD_DBS else db


def sample(qs, n, rng):
    """n questions stratified by database (proportional, at least one each)."""
    by_db = defaultdict(list)
    for q in sorted(qs, key=lambda q: str(q["question_id"])):
        by_db[q["db_id"]].append(q)
    picked = []
    for db, items in sorted(by_db.items()):
        rng.shuffle(items)
        picked += items[:max(1, round(len(items) * n / len(qs)))]
    rng.shuffle(picked)
    return picked[:n]


def main():
    rng = random.Random(SEED)
    CORPUS.mkdir(exist_ok=True)
    cards = CORPUS / "fleet" / "cards"  # one "database" for meko_load.py: the shared datapack
    cards.mkdir(parents=True, exist_ok=True)
    dbs, qs, index, bodies = [], [], [], {}
    for set_, root in SETS.items():
        set_dbs = json.loads((root / "databases.json").read_text()) if (root / "databases.json").exists() else \
            sorted({q["db_id"] for q in json.loads((root / "questions.json").read_text())})
        for db in set_dbs:
            name = real(set_, db)
            dbs.append(name)
            schema = json.loads((root / db / "schema.json").read_text())
            comments = json.loads((root / db / "comments.json").read_text()).get("tables", {}) \
                if (root / db / "comments.json").exists() else {}
            lines = [f"## {name} ({len(schema)} tables)"]
            for t in schema:
                first = re.split(r"(?<=\.)\s", (comments.get(t) or {}).get("comment") or "", maxsplit=1)[0]
                lines.append(f"{t}" + (f": {first}" if first else ""))
            index.append("\n".join(lines))
            for f in sorted((root / db / "cards").glob("*.md")):
                body = f.read_text().replace(f"(database {db}", f"(database {name}")
                bodies[(name, f.stem)] = body
                (cards / f"{name}__{f.name}").write_text(body)
        set_qs = [q for q in json.loads((root / "questions.json").read_text()) if q.get("SQL") is not None]
        for q in sample(set_qs, PER_SET, rng):
            qs.append({**q, "question_id": f"{set_}-{q['question_id']}", "source_id": q["question_id"],
                       "db_id": real(set_, q["db_id"])})
    (CORPUS / "fleet_dbs.json").write_text(json.dumps(dbs, indent=1))
    (CORPUS / "databases.json").write_text(json.dumps(["fleet"]))
    (CORPUS / "questions.json").write_text(json.dumps(qs, indent=1))
    (CORPUS / "index.md").write_text("# Databases and their tables\n\n" + "\n\n".join(index) + "\n")
    print(len(dbs), "databases,", len(bodies), "cards,", len(qs), "questions; index",
          len((CORPUS / "index.md").read_text()), "chars")



if __name__ == "__main__":
    main()
