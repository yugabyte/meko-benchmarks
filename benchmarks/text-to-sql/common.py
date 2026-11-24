"""Shared paths, question sets, database access and result comparison for the text-to-SQL benchmark.

T2S_SET picks the data set every script works on:
  bird        BIRD Mini-Dev with cryptic table and column names (databases <db>_x)
  bird-plain  BIRD Mini-Dev as published: only used while building the cryptic set
  lsb         LiveSQLBench-Large
  fleet       every bird and lsb database behind one agent
  novel       the invented database bundled with this repository
"""
import decimal
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = REPO / "datasets" / "text-to-sql"
DOWNLOADS = Path(os.environ.get("T2S_DOWNLOADS", DATA / "downloads"))
MINIDEV = DOWNLOADS / "minidev" / "MINIDEV"
RUNS = REPO / "runs" / "text-to-sql"
SET = os.environ.get("T2S_SET", "")
CORPUS = DATA / SET if SET else DATA
DB_SUFFIX = "_x" if SET == "bird" else ""
BIRD_DBS = ("california_schools", "card_games", "codebase_community", "debit_card_specializing",
            "european_football_2", "financial", "formula_1", "student_club", "superhero",
            "thrombosis_prediction", "toxicology")
SEED = 20261027


def _env():
    """The repo-root .env (KEY=VALUE per line); the process environment wins."""
    f = REPO / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_env()
if os.environ.get("YB_PASSWORD"):  # psql and libpq read it for the yugabyte user; t2s_agent passes its own
    os.environ.setdefault("PGPASSWORD", os.environ["YB_PASSWORD"])
YB_HOST = os.environ.get("YB_HOST", "localhost")
YB_PORT = int(os.environ.get("YB_PORT", "5433"))


def meko_settings():
    """(MCP URL, bearer token) for the Meko deployment in .env, through the repo's shared auth helper."""
    sys.path.insert(0, str(REPO / "common"))
    from auth import Auth, load_env
    cfg = load_env()
    return cfg["url"], Auth(cfg).token()


def dbname(db):
    """The database holding a BIRD db_id in the current set; other names are already databases."""
    return db + DB_SUFFIX if db in BIRD_DBS else db


def dsn(db, user="t2s_agent", app="t2s"):
    """Connection string for a BIRD db_id (mapped to its set's database) or any other database."""
    db = dbname(db)
    pw = "t2s_agent" if user == "t2s_agent" else os.environ.get("YB_PASSWORD", "")
    return f"host={YB_HOST} port={YB_PORT} dbname={db} user={user} password={pw} application_name={app}"


def questions():
    """The current set's questions; bird-plain reads Mini-Dev's own file.

    Records may carry "gold" (the gold cache under runs/text-to-sql/gold/) and "conditions"
    (LiveSQLBench's decimal / distinct / order rules for comparing results).
    """
    if SET == "bird-plain":
        return json.loads((MINIDEV / "mini_dev_postgresql.json").read_text())
    return json.loads((CORPUS / "questions.json").read_text())


def gold_dir(name=None):
    return RUNS / "gold" / (name or SET)


def gold(qid, name=None):
    return json.loads((gold_dir(name) / f"{qid}.json").read_text())


def degenerate_gold(qid, name=None):
    """Gold results that any empty or NULL answer would match (excluded from every scored sample)."""
    g = gold(qid, name)
    return g["error"] is not None or not g["rows"] or all(all(v is None for v in r) for r in g["rows"])


def databases():
    """The set's databases: databases.json when the set has databases without questions."""
    if (CORPUS / "databases.json").exists():
        return json.loads((CORPUS / "databases.json").read_text())
    return sorted({q["db_id"] for q in questions()})


def execute(conn, sql, timeout_ms=60000, max_rows=None):
    """Run one statement read-only; return (rows, error)."""
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(sql)
                if cur.description is None:
                    return [], None
                rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
                return rows, None
    except Exception as e:  # noqa: BLE001 - every failure is a scored outcome
        return None, f"{type(e).__name__}: {str(e).strip().splitlines()[0][:300]}"


def canon(v):
    """One normal form for a result value, used for the cached gold rows and for predictions alike.

    Numbers (int, float, numeric) compare as floats rounded to 4 places, so float and numeric
    arithmetic agree (BIRD compares exactly); arrays as tuples; dates and other types as text.
    """
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (int, float, decimal.Decimal)):
        return round(float(v), 4)
    if isinstance(v, (list, tuple)):
        return tuple(canon(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True, default=str)
    return str(v)


def to_json(v):
    """Store a canonical value in JSON (tuples become lists; canon() turns them back)."""
    c = canon(v)
    return list(c) if isinstance(c, tuple) else c


def same_result(pred_rows, gold_rows, conditions=None):
    """BIRD's execution accuracy (EX): the predicted and gold result sets are equal (as sets of rows).

    Values are compared in canon() form. LiveSQLBench conditions tighten this: "order" compares the
    row lists in order, "decimal" rounds numbers to that many places instead of 4.
    """
    if pred_rows is None or gold_rows is None:
        return False
    cond = conditions or {}
    places = cond.get("decimal")
    fix = (lambda v: round(v, places) if isinstance(v, float) else v) if isinstance(places, int) and places >= 0 \
        else (lambda v: v)
    row = lambda r: tuple(fix(canon(v)) for v in r)  # noqa: E731
    if cond.get("order"):
        return [row(r) for r in pred_rows] == [row(r) for r in gold_rows]
    return {row(r) for r in pred_rows} == {row(r) for r in gold_rows}


SQL_BLOCK = re.compile(r"```sql\s*(.+?)```", re.S | re.I)


def extract_sql(text):
    """The last ```sql block in the agent's final message, or None."""
    blocks = SQL_BLOCK.findall(text or "")
    return blocks[-1].strip().rstrip(";").strip() if blocks else None
