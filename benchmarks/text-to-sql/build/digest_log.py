#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["sqlglot==30.25.0"]
# ///
"""C3: turn <set>/<db>/pgss.json into a per-table query-log digest (<set>/<db>/digest.json).

For each table: how often it is queried, which tables it joins to and on which columns, which
columns are filtered, grouped, sorted and aggregated, DocDB rows scanned per call, and the
shortest few normalised statements that touch it. Literals are already $n placeholders in
pg_stat_statements, so no values from the history questions leak into the digest.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import sqlglot
from sqlglot import exp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, databases  # noqa: E402


def analyse(sql, known):
    tree = sqlglot.parse_one(sql, read="postgres")
    alias = {}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if name in known:
            alias[(t.alias or t.name).lower()] = name

    def owner(col):
        q = col.table.lower() if col.table else None
        if q in alias:
            return alias[q]
        if len(set(alias.values())) == 1:
            return next(iter(alias.values()))
        return None

    joins, used = Counter(), defaultdict(Counter)
    for eq in tree.find_all(exp.EQ):
        l, r = eq.left, eq.right
        if isinstance(l, exp.Column) and isinstance(r, exp.Column):
            a, b = owner(l), owner(r)
            if a and b and a != b:
                joins[tuple(sorted([(a, l.name.lower()), (b, r.name.lower())]))] += 1
    for clause, kind in ((exp.Where, "filtered"), (exp.Group, "grouped"), (exp.Order, "sorted")):
        for node in tree.find_all(clause):
            for col in node.find_all(exp.Column):
                if owner(col):
                    used[owner(col)][(kind, col.name.lower())] += 1
    for agg in tree.find_all(exp.AggFunc):
        for col in agg.find_all(exp.Column):
            if owner(col):
                used[owner(col)][(f"aggregated ({agg.key})", col.name.lower())] += 1
    return set(alias.values()), joins, used


for db in databases():
    schema = json.loads((CORPUS / db / "schema.json").read_text())
    known = set(schema)
    stmts = json.loads((CORPUS / db / "pgss.json").read_text())
    per = {t: {"statements": 0, "calls": 0, "rows_scanned": 0, "joins": Counter(), "columns": Counter(),
               "examples": []} for t in known}
    failed = 0
    for s in stmts:
        try:
            tables, joins, used = analyse(s["query"], known)
        except Exception:  # noqa: BLE001
            failed += 1
            continue
        for t in tables:
            p = per[t]
            p["statements"] += 1
            p["calls"] += s["calls"]
            p["rows_scanned"] += s.get("docdb_rows_scanned") or 0
            p["examples"].append(" ".join(s["query"].split()))
            for (a, b), n in joins.items():
                if t in (a[0], b[0]):
                    mine, other = (a, b) if a[0] == t else (b, a)
                    p["joins"][f"{t}.{mine[1]} = {other[0]}.{other[1]}"] += n * s["calls"]
        for t, cols in used.items():
            for (kind, col), n in cols.items():
                per[t]["columns"][f"{col} ({kind})"] += n * s["calls"]
    digest = {}
    for t, p in per.items():
        if not p["statements"]:
            continue
        digest[t] = {
            "statements": p["statements"], "calls": p["calls"],
            "rows_scanned_per_call": round(p["rows_scanned"] / max(p["calls"], 1)),
            "joins": [f"{k} ({n} calls)" for k, n in p["joins"].most_common(8)],
            "columns": [f"{k}: {n} calls" for k, n in p["columns"].most_common(12)],
            "examples": sorted(p["examples"], key=len)[:3],
        }
    (CORPUS / db / "digest.json").write_text(json.dumps(digest, indent=1))
    print(db, len(stmts), "statements,", failed, "unparsed,", len(digest), "of", len(known), "tables seen")
