#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6", "sqlglot==30.25.0"]
# ///
"""A query history for the bird set from the rest of BIRD dev.

- bird/history.json: the BIRD dev questions not in Mini-Dev, their SQLite gold transpiled to
  PostgreSQL with sqlglot and renamed to the cryptic schema. replay_history.py replays these (the
  statements that fail are skipped and counted), so no test question's SQL reaches the query log.
  T2S_SET=bird ./bird_history.py   (after bird_cryptic.py)
"""
import json
import sys
from pathlib import Path

import sqlglot

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, DOWNLOADS, MINIDEV  # noqa: E402
from bird_cryptic import rewrite  # noqa: E402

DEV = DOWNLOADS / "bird-dev" / "dev_20240627" / "dev.json"

qs = json.loads((CORPUS / "questions.json").read_text())
maps = json.loads((CORPUS / "mapping.json").read_text())
mini = json.loads((MINIDEV / "mini_dev_sqlite.json").read_text())
# Mini-Dev keeps BIRD dev's question ids, sometimes with lightly edited wording, so exclude by id: the
# dev version of an edited question is a near-duplicate of a test question.
mini_ids = {q["question_id"] for q in mini}
history, failed = [], 0
for q in json.loads(DEV.read_text()):
    if q["question_id"] in mini_ids:
        continue
    try:
        pg = sqlglot.transpile(q["SQL"], read="sqlite", write="postgres")[0]
        m = maps[q["db_id"]]
        history.append({"question_id": f"dev{q['question_id']}", "db_id": q["db_id"],
                        "SQL": rewrite(pg, m["tables"], m["columns"])})
    except Exception:  # noqa: BLE001 - untranslatable statements are simply not in the history
        failed += 1
(CORPUS / "history.json").write_text(json.dumps(history, indent=1))
print(f"{len(qs)} test questions; {len(history)} history statements, {failed} could not be transpiled")
