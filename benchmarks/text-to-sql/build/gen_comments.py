#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""C1: draft table and column comments with an LLM, from structure, profiles and the query log.

  T2S_SET=bird ./gen_comments.py [db ...]   (default: every database). Writes <set>/<db>/comments.json and
<set>/<db>/comments.usage.json. The generator never sees benchmark questions, evidence, gold SQL
or BIRD's database_description files. Uses headless Claude Code.
"""
import json
import os
import subprocess
import tempfile
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_lib import generator_input  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, databases  # noqa: E402

MODEL = os.environ.get("COMMENT_MODEL", "claude-sonnet-5-5")
EMPTY = Path(tempfile.gettempdir()) / "t2s-empty"  # no CLAUDE.md or project settings
EMPTY.mkdir(exist_ok=True)
SYSTEM = """You document databases so that an AI agent can write correct SQL against them without guessing.
Write a comment for every table and every column you are given. Each comment should say what the
object represents and anything an analyst would trip over: units and scales, what codes and
abbreviations mean, how values are encoded (case, language, numbers or dates stored as text, flags),
what NULL or 0 means, which column holds a human-readable name versus an id, how the table relates
to others, and which of two similar columns to use for what. Base every statement on the evidence
given (names, types, value profiles, sample rows and the query log). When you infer a meaning, say
"probably". Never invent values that are not in the evidence. Plain text only: no backticks, no
markdown. Table comments at most 400 characters, column comments at most 250.{style}

Reply with a single JSON object and nothing else:
{{"tables": {{"<table>": {{"comment": "...", "columns": {{"<column>": "...", ...}}}}, ...}}}}"""
# Comments describe and never prescribe: advice such as "exclude 0 and NULL when averaging" is followed by the
# agent even where the question means otherwise.
STYLES = {"v2": """

Describe, do not prescribe. State what values mean and how they are encoded, with their frequencies
when that helps, but never tell the reader what to filter, exclude, prefer or how to write a query.
Write "0 in 12% of rows, probably meaning unknown", not "exclude 0 when averaging"; write "missing
values are stored as 'N/A' (40 rows) and '-' (3 rows)", not "use 'N/A' for missing". When the same thing is
encoded several ways, list every encoding with its frequency."""}
STYLE = "v2"
SYSTEM = SYSTEM.format(style=STYLES[STYLE])


def generate(db):
    prompt = f"Database {db} (YugabyteDB YSQL, PostgreSQL-compatible).\n\n{generator_input(db)}"
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--system-prompt", SYSTEM, "--tools", "",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}',
           "--setting-sources", "project", "--no-session-persistence", "--effort", "medium",
           "--output-format", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=EMPTY, stdin=subprocess.DEVNULL)
    out = json.loads(res.stdout)
    text = out["result"].strip()
    text = text[text.index("{"): text.rindex("}") + 1]
    comments = json.loads(text)
    (CORPUS / db / "comments.json").write_text(json.dumps(comments, indent=1, ensure_ascii=False))
    (CORPUS / db / "comments.usage.json").write_text(json.dumps({"model": MODEL, "style": STYLE, "usage": out["usage"],
                                                                 "cost_usd_cli": out.get("total_cost_usd")}))
    n = sum(len(t.get("columns", {})) for t in comments["tables"].values())
    return f"{db}: {len(comments['tables'])} tables, {n} column comments, ${out.get('total_cost_usd', 0):.3f}"


if __name__ == "__main__":
    dbs = sys.argv[1:] or databases()
    with ThreadPoolExecutor(4) as pool:
        for line in pool.map(generate, dbs):
            print(line)
