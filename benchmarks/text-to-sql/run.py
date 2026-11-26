#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "psycopg[binary]==3.3.6", "httpx>=0.27"]
# ///
"""Run and score one scenario's cells.

  ./run.py --scenario novel --run my-run                       every arm and model of the scenario
  ./run.py --scenario novel --run smoke --models haiku --limit 3 --arms A0,A3
  ./run.py --list                                              the scenarios, their arms and question counts

Each cell is one question answered by one model in one arm: an isolated headless Claude Code session (no user
settings, hooks, plugins or CLAUDE.md, only the arm's MCP servers, and a short system prompt replacing Claude
Code's own). The final ```sql block is executed and compared with the gold result (execution accuracy, EX).
Records land in runs/text-to-sql/<run>/<scenario>/<arm>/<model>/<question_id>/record.json, and a cell that
already has a record is skipped, so a stopped run resumes when started again.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ALL = ["haiku", "sonnet", "opus"]
CAPPED = {"A3c-55", "A3c-35", "A3c-35+M"}
LEARN_DBS = ["cross_border_large", "exchange_traded_funds_large", "fake_account_large",
             "labor_certification_applications_large", "mental_healths_large", "planets_data_large",
             "polar_equipment_large", "reverse_logistics_large", "solar_panel_large", "sports_events_large",
             "virtual_idol_large"]
SCENARIOS = {
    "bird": {"set": "bird", "arms": ["A0", "A1", "A3", "A4t"], "models": ALL},
    "lsb": {"set": "lsb", "arms": ["A0", "A3", "A4t", "A3c-55", "A3c-35", "A3c-35+M"], "models": ALL,
            "haiku_only": CAPPED},
    "fleet": {"set": "fleet", "arms": ["A0", "A1", "A3", "A3f-150", "A3f-80", "A3f-80+M", "A4t"], "models": ALL},
    "learn": {"set": "lsb", "arms": ["L-S", "L-F", "L-Mm", "L-Mk"], "models": ["sonnet"], "dbs": LEARN_DBS},
    "novel": {"set": "novel", "arms": ["A0", "A1", "A3", "A4t"], "models": ALL},
}

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--scenario", choices=SCENARIOS)
ap.add_argument("--run", help="run name; records go to runs/text-to-sql/<run>/")
ap.add_argument("--arms", help="comma-separated subset of the scenario's arms")
ap.add_argument("--models", help="comma-separated subset of haiku,sonnet,opus")
ap.add_argument("--qids", default="", help="comma-separated question ids (default: every scored question)")
ap.add_argument("--limit", type=int, default=0, help="first N questions only (smoke tests)")
ap.add_argument("-j", type=int, default=6, help="cells run in parallel")
ap.add_argument("--list", action="store_true")
ap.add_argument("--delete-stores", action="store_true",
                help="delete the Meko datapacks this run's learning streams created, then exit")
A = ap.parse_args()
if A.list:
    for k, v in SCENARIOS.items():
        print(f"{k:6s} set={v['set']:6s} models={','.join(v['models']):17s} arms={','.join(v['arms'])}")
    sys.exit(0)
if not (A.scenario and A.run):
    ap.error("--scenario and --run are required")
SC = SCENARIOS[A.scenario]
os.environ["T2S_SET"] = SC["set"]

import psycopg  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "build"))
from common import CORPUS, RUNS, SET, degenerate_gold, dsn, execute, extract_sql, gold, meko_settings, questions, same_result  # noqa: E402,E501
from corpus_lib import kb_entries  # noqa: E402

MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
# USD per million tokens: input, output, cache read. Cache writes are billed at the 1-hour TTL the CLI uses:
# 2x input. Haiku 5.5 steps up 5x for requests over 100k prompt tokens.
PRICES = {"claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-sonnet-5-5": (2.0, 10.0, 0.20),
          "claude-opus-5-5": (4.0, 20.0, 0.20)}
LONG_PROMPT = {"claude-haiku-5-5": (100_000, 5.0)}
FLEET = SET == "fleet"
DB_LINE = re.compile(r"^\s*--\s*database:\s*([A-Za-z0-9_]+)", re.M | re.I)
PY = sys.executable  # this script's environment has every server's dependencies
MAX_TURNS = 10
# An empty working directory outside the repository, so no CLAUDE.md or project settings reach the agent.
EMPTY = Path(tempfile.gettempdir()) / "t2s-empty"
EMPTY.mkdir(exist_ok=True)

BASE = """You are a data analyst who answers questions by writing SQL for a YugabyteDB database (YSQL, which is
PostgreSQL 15 compatible). {tools}
Finish with your final query in one ```sql block. The query must return exactly the columns the question asks
for, in the order it asks for them, and nothing else. Do not ask clarifying questions: make the most reasonable
assumption and answer."""
TOOLS_TEXT = "Use the tools to inspect the schema and check values before you answer."
FLEET_TEXT = ("You can query several databases; the question does not say which one it is about. Use the tools to "
              "find the right database and tables and check values before you answer. Put the database name on the "
              "first line of your final sql block as a comment: -- database: <name>.")
SEARCH_HINT = (" Search the database documentation (table descriptions, column meanings and values, business terms, "
               "usual joins and example queries) with search_context.")
LEARN = {"L-S": "", "L-F": "file", "L-Mm": "mem", "L-Mk": "kb"}
LESSONS_TEXT = (" Lessons learned from the user's corrections of your earlier answers on this database are kept "
                "for you: search them with search_lessons before you answer.")
CORRECT_SYS = """You answered a question about a YugabyteDB database and the user says the answer was wrong. Save what
you should remember for future questions on this database with save_lesson: short, general business rules,
definitions and conventions, one topic per lesson, in your own words. Do not save the answer to this question or a
query for it. {extra}When you have saved your lessons, reply "done"."""
_MEKO = {}


def meko_env():
    if not _MEKO:
        url, token = meko_settings()
        _MEKO.update({"MEKO_MCP_URL": url, "MEKO_API_KEY": token})
    return dict(_MEKO)


def fleet_dbs():
    return json.loads((CORPUS / "fleet_dbs.json").read_text())


def meko_cfg():
    """Datapack and conversation per database (or "fleet"), written by meko_load.py."""
    p = RUNS / f"meko-{SET}.json"
    if not p.exists():
        raise SystemExit(f"{p} is missing: run T2S_SET={SET} ./meko_load.py setup first")
    return json.loads(p.read_text())


def meko_server(key, run_dir):
    cfg = meko_cfg()
    return {"meko": {"command": PY, "args": [str(HERE / "meko_text.py")], "env": {
        "T2S_MEKO_DATAPACK": cfg["datapacks"][key], "T2S_MEKO_CONVERSATION": cfg["conversations"][key],
        "T2S_LOG": str(run_dir / "tools.jsonl"), **meko_env()}}}


def lessons_server(stream, phase, log):
    env = {"T2S_LESSONS": LEARN[stream["arm"]], "T2S_STORE": stream["store"], "T2S_PHASE": phase, "T2S_LOG": str(log),
           "T2S_LESSON_FILE": str(stream["dir"] / "lessons.md"), "T2S_LESSON_DIR": str(stream["dir"]),
           "T2S_MEKO_DATAPACK": stream.get("datapack", ""), "T2S_MEKO_CONVERSATION": stream.get("conversation", ""),
           "T2S_SET": SET, **(meko_env() if LEARN[stream["arm"]] in ("mem", "kb") else {})}
    return {"lessons": {"command": PY, "args": [str(HERE / "lessons_server.py")], "env": env}}


def lessons_file(stream):
    p = stream["dir"] / "lessons.md"
    return p.read_text().strip() if p.exists() else ""


def arm_setup(arm, db, run_dir, stream=None):
    """Return (system_prompt, mcp_servers, allowed_tools) for one arm."""
    own = lambda comments: {"db": {  # noqa: E731
        "command": PY, "args": [str(HERE / "tools_server.py")],
        "env": {**({"T2S_DBS": ",".join(fleet_dbs())} if FLEET else {"T2S_DB": db}),
                "T2S_COMMENTS": comments, "T2S_APP": f"t2s-{arm}", "T2S_LOG": str(run_dir / "tools.jsonl"),
                "T2S_SET": SET}}}
    own_tools = ["mcp__db__list_tables", "mcp__db__describe_table", "mcp__db__run_sql"] + \
        (["mcp__db__list_databases"] if FLEET else [])
    tools_text = FLEET_TEXT if FLEET else TOOLS_TEXT
    search_tools = own_tools + ["mcp__meko__search_context"]
    if arm == "A0":  # tools only, catalog comments hidden
        return BASE.format(tools=tools_text), own("0"), own_tools
    if arm == "A1":  # comments; bird and novel serve them from a file, so nothing reaches A0 through SQL
        src = f"file:{CORPUS / db / 'comments.json'}" if SET in ("bird", "novel") else "1"
        return BASE.format(tools=tools_text), own(src), own_tools
    if arm == "A3" and FLEET:  # the whole fleet's documentation cannot fit: an index of databases and tables
        index = (CORPUS / "index.md").read_text()
        return (BASE.format(tools=tools_text + " An index of the databases and their tables is below.")
                + f"\n\n<index>\n{index}</index>", own("1"), own_tools)
    if arm == "A3":  # the database's documentation in the prompt
        context = (CORPUS / db / "context.md").read_text()
        return (BASE.format(tools=TOOLS_TEXT + " The database's documentation is below.")
                + f"\n\n<documentation>\n{context}</documentation>", own("1"), own_tools)
    if arm == "A4t":  # Meko knowledge-base search over the same documentation
        return (BASE.format(tools=tools_text + SEARCH_HINT), {**own("1"), **meko_server("fleet" if FLEET else db, run_dir)},
                search_tools)
    if arm in CAPPED:  # a shortened documentation file, alone or with Meko search over the full documentation
        k, plus = arm[4:].partition("+")[::2]
        doc = f"\n\n<documentation>\n{(CORPUS / db / f'context_c{k}.md').read_text()}</documentation>"
        lead = TOOLS_TEXT + " A shortened version of the database's documentation is below."
        if plus == "M":
            return BASE.format(tools=lead + SEARCH_HINT) + doc, {**own("1"), **meko_server(db, run_dir)}, search_tools
        return BASE.format(tools=lead) + doc, own("1"), own_tools
    if arm.startswith("A3f-"):  # one file for the whole fleet that fits a window, alone or with Meko search
        k, plus = arm[4:].partition("+")[::2]
        doc = f"\n\n<documentation>\n{(CORPUS / f'context_fleet_c{k}.md').read_text()}</documentation>"
        lead = tools_text + " A shortened list of the databases, tables and columns is below."
        if plus == "M":
            return BASE.format(tools=lead + SEARCH_HINT) + doc, {**own("1"), **meko_server("fleet", run_dir)}, search_tools
        return BASE.format(tools=lead) + doc, own("1"), own_tools
    if arm in LEARN:  # comments, no documentation, plus the stream's lessons
        kind = LEARN[arm]
        if kind == "":
            return BASE.format(tools=tools_text), own("1"), own_tools
        if kind == "file":
            lessons = lessons_file(stream) or "(none yet)"
            return (BASE.format(tools=tools_text + " Lessons learned from the user's corrections of your earlier "
                                "answers on this database are below.") + f"\n\n<lessons>\n{lessons}\n</lessons>",
                    own("1"), own_tools)
        return (BASE.format(tools=tools_text + LESSONS_TEXT),
                {**own("1"), **lessons_server(stream, "answer", run_dir / "tools.jsonl")},
                own_tools + ["mcp__lessons__search_lessons"])
    raise SystemExit(f"unknown arm {arm}")


def parse_stream(path, expected=()):
    tool_calls, result, failed, requests = [], {}, [], {}
    for line in path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            failed = [m["name"] for m in ev.get("mcp_servers", []) if m.get("status") != "connected"]
            # A server whose config Claude Code rejects is left out of the list rather than reported failed.
            failed += sorted(set(expected) - {m["name"] for m in ev.get("mcp_servers", [])})
        elif ev.get("type") == "assistant":
            if ev["message"].get("id") and ev["message"].get("usage"):  # one usage per API request
                requests[ev["message"]["id"]] = ev["message"]["usage"]
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    tool_calls.append(c["name"])
        elif ev.get("type") == "result":
            result = ev
    return tool_calls, result, failed, list(requests.values())


def cost(model, u, requests=()):
    """List-price cost from the session's total usage, plus the long-prompt step on requests above it.

    The stream's per-request usage has the real prompt tokens but only the first output tokens of each
    message, so output is shared evenly across requests when a request crosses the step.
    """
    pin, pout, pcr = PRICES[model]
    base = (u.get("input_tokens", 0) * pin + u.get("cache_creation_input_tokens", 0) * 2 * pin
            + u.get("cache_read_input_tokens", 0) * pcr + u.get("output_tokens", 0) * pout) / 1e6
    step = LONG_PROMPT.get(model)
    over = [r for r in requests if step and prompt_tokens(r) > step[0]]
    if not over:
        return base
    out_each = u.get("output_tokens", 0) / len(requests)
    return base + (step[1] - 1) * sum(cost(model, {**r, "output_tokens": out_each}) for r in over)


def prompt_tokens(u):
    return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)


LIMITED = threading.Event()


def correction(q):
    """The user's correction: the question's knowledge-base entries, as the user would say them.

    Built from the public knowledge base only, identical for every arm, never SQL or the expected result.
    """
    kb = kb_entries(q["db_id"])
    terms = [kb[i] for i in q.get("kb_ids") or [] if i in kb]
    if not terms:
        return None
    return "That's not right. Here is what we mean:\n" + "\n".join(
        f"- {e['knowledge']}: {e['description']} {e['definition']}" for e in terms)


def claude(cmd, run_dir, name):
    with open(run_dir / f"{name}.jsonl", "w") as out, open(run_dir / f"{name}.stderr.txt", "w") as err:
        return subprocess.run(cmd, cwd=EMPTY, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                              env=os.environ, timeout=900).returncode


def correct(model, q, sql, stream, run_dir):
    """The correction turn after a wrong answer: the agent saves lessons with its arm's store."""
    text = correction(q)
    if not text:
        return {"corrected": False}
    kind = LEARN[stream["arm"]]
    extra = "" if kind == "file" else "Search the saved lessons first, so you update a topic rather than repeat it. "
    prompt = f"Question: {q['question']}\n\nYour final query:\n{sql or '(none)'}\n\nThe user: {text}"
    if kind == "file":
        prompt += f"\n\nLessons already saved:\n{lessons_file(stream) or '(none yet)'}"
    servers = lessons_server(stream, "correct", run_dir / "correct_tools.jsonl")
    (run_dir / "correct_mcp.json").write_text(json.dumps({"mcpServers": servers}))
    allowed = ["mcp__lessons__save_lesson"] + ([] if kind == "file" else ["mcp__lessons__search_lessons"])
    cmd = ["claude", "-p", prompt, "--model", model, "--system-prompt", CORRECT_SYS.format(extra=extra), "--tools", "",
           "--strict-mcp-config", "--mcp-config", str(run_dir / "correct_mcp.json"), "--setting-sources", "project",
           "--no-session-persistence", "--effort", "medium", "--max-turns", "6", "--output-format", "stream-json",
           "--verbose", "--permission-mode", "default", "--allowedTools", *allowed]
    t0 = time.time()
    claude(cmd, run_dir, "correct")
    tool_calls, result, failed, requests = parse_stream(run_dir / "correct.jsonl", servers)
    if failed:
        raise RuntimeError(f"MCP server(s) not connected in the correction turn: {failed}")
    if result.get("api_error_status") == 429:
        LIMITED.set()
        raise RuntimeError(f"usage limit: {result.get('result', '')[:120]}")
    log = [json.loads(x) for x in (run_dir / "correct_tools.jsonl").read_text().splitlines()] \
        if (run_dir / "correct_tools.jsonl").exists() else []
    return {"corrected": True, "correct_cost_usd": round(cost(model, result.get("usage", {}), requests), 5),
            "correct_turns": result.get("num_turns"), "correct_wall_s": round(time.time() - t0, 1),
            "lessons_saved": sum(1 for t in log if t["tool"] == "save_lesson"),
            "lesson_searches_in_correction": sum(1 for t in log if t["tool"] == "search_lessons"),
            "lesson_save_ms": sum(t["ms"] for t in log if t["tool"] == "save_lesson")}


def run_cell(arm, model_key, q, stream=None):
    model = MODELS[model_key]
    run_dir = RUNS / A.run / A.scenario / arm / model_key / str(q["question_id"])
    rec_path = run_dir / "record.json"
    if rec_path.exists():
        return json.loads(rec_path.read_text())
    if LIMITED.is_set():
        raise RuntimeError("skipped: usage limit reached earlier in this run")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tools.jsonl").unlink(missing_ok=True)
    db = q["db_id"]
    system, servers, allowed = arm_setup(arm, db, run_dir, stream)
    (run_dir / "mcp.json").write_text(json.dumps({"mcpServers": servers}))
    prompt = f"Question: {q['question']}" if FLEET else f"Database: {db}\nQuestion: {q['question']}"
    cmd = ["claude", "-p", prompt, "--model", model, "--system-prompt", system, "--tools", "",
           "--strict-mcp-config", "--mcp-config", str(run_dir / "mcp.json"), "--setting-sources", "project",
           "--no-session-persistence", "--effort", "medium", "--max-turns", str(MAX_TURNS),
           "--output-format", "stream-json", "--verbose", "--permission-mode", "default", "--allowedTools", *allowed]
    t0 = time.time()
    rc = claude(cmd, run_dir, "transcript")
    wall = time.time() - t0
    tool_calls, result, failed, requests = parse_stream(run_dir / "transcript.jsonl", servers)
    if failed:  # infrastructure, not model behaviour: leave no record so the cell reruns
        raise RuntimeError(f"MCP server(s) not connected: {failed} (see {run_dir}/transcript.stderr.txt)")
    if result.get("api_error_status") == 429:  # account usage limit: stop the run, rerun these cells later
        LIMITED.set()
        raise RuntimeError(f"usage limit: {result.get('result', '')[:120]}")
    if not result:
        raise RuntimeError(f"no result from claude (exit {rc}, see {run_dir}/transcript.stderr.txt)")
    sql = extract_sql(result.get("result", ""))
    gold_id = q.get("source_id", q["question_id"])  # fleet ids wrap the source set's id
    g = gold(gold_id, q.get("gold"))
    pred_rows, pred_err, pred_db = (None, "no sql block", db)
    if sql and FLEET:  # the agent names the database; a wrong or missing name scores 0
        m = DB_LINE.search(sql)
        pred_db = m.group(1) if m else None
        if pred_db not in fleet_dbs():
            sql, pred_err = None, f"no valid database named: {pred_db}"
    if sql:
        with psycopg.connect(dsn(pred_db, app="t2s-score"), autocommit=False) as c:
            pred_rows, pred_err = execute(c, sql, timeout_ms=60000)
    tools_log = [json.loads(x) for x in (run_dir / "tools.jsonl").read_text().splitlines()] \
        if (run_dir / "tools.jsonl").exists() else []
    u = result.get("usage", {})
    rec = {
        "run": A.run, "scenario": A.scenario, "set": SET, "arm": arm, "model": model_key,
        "question_id": q["question_id"], "db_id": db, "gold": q.get("gold") or SET, "gold_id": gold_id,
        "conditions": q.get("conditions"), "pred_db": pred_db,
        "difficulty": q.get("difficulty", "n/a"), "rc": rc, "terminal_reason": result.get("terminal_reason"),
        "subtype": result.get("subtype"), "ex": bool(sql) and same_result(pred_rows, g["rows"], q.get("conditions")),
        "sql": sql, "pred_error": pred_err, "pred_rows": None if pred_rows is None else len(pred_rows),
        "num_turns": result.get("num_turns"), "wall_s": round(wall, 1), "duration_api_ms": result.get("duration_api_ms"),
        "usage": {k: u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                            "cache_read_input_tokens", "output_tokens")},
        "cost_list_usd": round(cost(model, u, requests), 5), "cost_cli_usd": result.get("total_cost_usd"),
        "requests": len(requests), "max_prompt_tokens": max((prompt_tokens(r) for r in requests), default=None),
        "tool_calls": tool_calls,
        "sql_runs": sum(1 for t in tool_calls if t == "mcp__db__run_sql"),
        "sql_errors": sum(1 for t in tools_log if t["tool"] == "run_sql" and t.get("error") and not t.get("budget")),
        "search_calls": sum(1 for t in tool_calls if "search" in t),
        "tool_ms": sum(t["ms"] for t in tools_log),
    }
    if stream:
        rec["stream_pos"] = stream["pos"]
        rec["lesson_searches"] = sum(1 for t in tools_log if t["tool"] == "search_lessons")
        rec["lessons_chars"] = len(lessons_file(stream)) if LEARN[arm] == "file" else None
        if LEARN[arm] and not rec["ex"]:
            rec.update(correct(model, q, sql, stream, run_dir))
    rec_path.write_text(json.dumps(rec, indent=1, default=str))
    return rec


def qid_key(qid):
    stem, _, n = str(qid).rpartition("_")
    return (stem, int(n)) if n.isdigit() else (str(qid), 0)


def run_stream(arm, model_key, qs):
    """One database's questions in order, one at a time, the lesson store carried from each to the next."""
    db = qs[0]["db_id"]
    d = RUNS / A.run / A.scenario / arm / model_key / "_streams" / db
    d.mkdir(parents=True, exist_ok=True)
    stream = {"arm": arm, "store": f"{A.run}-{arm}-{model_key}-{db}".lower().replace("_", "-"), "dir": d}
    ids_path = d / "store.json"
    if LEARN[arm] in ("mem", "kb") and not ids_path.exists():  # a new stream starts with an empty store
        env = {**os.environ, **lessons_server(stream, "init", d / "init.jsonl")["lessons"]["env"]}
        out = subprocess.run([PY, str(HERE / "lessons_server.py"), "init", stream["store"]], env=env,
                             capture_output=True, text=True, timeout=900)
        made = json.loads(out.stdout or "{}") if not out.returncode else {}
        if not (made.get("datapack") and made.get("conversation")):
            raise RuntimeError(f"lesson store init {stream['store']}: {out.stderr[-500:] or out.stdout[:300]}")
        ids_path.write_text(out.stdout)
    if ids_path.exists():
        stream.update(json.loads(ids_path.read_text()))
    recs = []
    for pos, q in enumerate(sorted(qs, key=lambda q: qid_key(q["question_id"])), 1):
        recs.append(run_cell(arm, model_key, q, {**stream, "pos": pos}))
    if LEARN[arm]:
        env = {**os.environ, **lessons_server(stream, "answer", d / "dump_tools.jsonl")["lessons"]["env"]}
        out = subprocess.run([PY, str(HERE / "lessons_server.py"), "dump"], env=env, capture_output=True,
                             text=True, timeout=900)
        (d / "dump.json").write_text(out.stdout or json.dumps({"error": out.stderr[-500:]}))
    return recs


def delete_stores():
    for p in sorted((RUNS / A.run / A.scenario).glob("*/*/_streams/*/store.json")):
        ids = json.loads(p.read_text())
        if not ids.get("datapack"):
            continue
        env = {**os.environ, **meko_env()}
        out = subprocess.run([PY, str(HERE / "lessons_server.py"), "delete", ids["datapack"], ids["conversation"]], env=env,
                             capture_output=True, text=True, timeout=300)
        print(p.parent.relative_to(RUNS / A.run), ids["datapack"], (out.stdout or out.stderr).strip()[:160])
        if not out.returncode:
            p.rename(p.with_name("store.deleted.json"))


def main():
    if A.delete_stores:
        return delete_stores()
    qs = {str(q["question_id"]): q for q in questions()}
    if A.qids:
        ids = [x for x in A.qids.split(",") if x]
    else:  # every question with gold SQL whose gold result is not degenerate (empty or NULL)
        ids = [i for i, q in qs.items() if q.get("SQL") and not degenerate_gold(q.get("source_id", i), q.get("gold"))]
        if "dbs" in SC:
            ids = [i for i in ids if qs[i]["db_id"] in SC["dbs"]]
    ids = ids[:A.limit] if A.limit else ids
    # Database-major order inside each arm and model keeps a database's cached prompt warm.
    ids = sorted(ids, key=lambda i: (qs[i]["db_id"], i))
    arms = A.arms.split(",") if A.arms else SC["arms"]
    models = A.models.split(",") if A.models else SC["models"]
    bad = [x for x in arms if x not in SC["arms"]] + [m for m in models if m not in MODELS]
    if bad:
        raise SystemExit(f"not in scenario {A.scenario}: {bad}")
    cells = [(arm, m, qs[i]) for m in models for arm in arms for i in ids
             if not (arm in SC.get("haiku_only", ()) and m != "haiku")]
    print(f"{A.scenario}: {len(ids)} questions, {len(cells)} cells -> {RUNS / A.run / A.scenario}", flush=True)
    if any(arm in LEARN for arm, _, _ in cells):  # learning arms run as streams: one database's questions in order
        groups = {}
        for arm, m, q in cells:
            groups.setdefault((arm, m, q["db_id"]), []).append(q)
        with ThreadPoolExecutor(A.j) as pool:
            futs = {pool.submit(run_stream, arm, m, g): (arm, m, db) for (arm, m, db), g in groups.items()}
            for n, f in enumerate(as_completed(futs), 1):
                arm, m, db = futs[f]
                try:
                    rs = f.result()
                    print(f"[{n}/{len(futs)}] {arm} {m} {db} ex={sum(r['ex'] for r in rs)}/{len(rs)} "
                          f"saved={sum(r.get('lessons_saved', 0) for r in rs)} "
                          f"${sum(r['cost_list_usd'] + r.get('correct_cost_usd', 0) for r in rs):.3f}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[{n}/{len(futs)}] {arm} {m} {db} FAILED {type(e).__name__}: {e}", flush=True)
        return
    done = 0
    with ThreadPoolExecutor(A.j) as pool:
        futs = {pool.submit(run_cell, arm, m, q): (arm, m, q["question_id"]) for arm, m, q in cells}
        for f in as_completed(futs):
            done += 1
            arm, m, qid = futs[f]
            try:
                r = f.result()
                print(f"[{done}/{len(cells)}] {arm} {m} {qid} ex={int(r['ex'])} turns={r['num_turns']} "
                      f"${r['cost_list_usd']:.4f} {r['wall_s']}s {r['terminal_reason']}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[{done}/{len(cells)}] {arm} {m} {qid} FAILED {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
