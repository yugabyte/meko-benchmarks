"""Render schema, profiles, digest and comments as text: DDL for the prompt arms, cards for the corpus."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS  # noqa: E402


def load(db):
    d = CORPUS / db
    schema = json.loads((d / "schema.json").read_text())
    digest = json.loads((d / "digest.json").read_text()) if (d / "digest.json").exists() else {}
    comments = json.loads((d / "comments.json").read_text()) if (d / "comments.json").exists() else {}
    return schema, digest, comments.get("tables", {})


def q(name):
    plain = re.fullmatch(r"[a-z_][a-z0-9_]*", name) and name not in ("order", "user", "date", "time")
    return name if plain else '"' + name.replace('"', '""') + '"'


def ddl(db, with_comments):
    """CREATE TABLE statements, optionally followed by COMMENT ON statements (arm A2)."""
    schema, _, comments = load(db)
    out = []
    for t, meta in schema.items():
        cols = [f"  {q(c)} {m['type']}{'' if m['nullable'] else ' NOT NULL'}" for c, m in meta["columns"].items()]
        if meta.get("primary_key_def"):
            cols.append(f"  {meta['primary_key_def']}")
        cols += [f"  {fk}" for fk in meta["foreign_keys"]]
        out.append(f"CREATE TABLE {q(t)} (\n" + ",\n".join(cols) + "\n);")
        if with_comments and t in comments:
            c = comments[t]
            out.append(f"COMMENT ON TABLE {q(t)} IS '{c['comment']}';".replace("''", "'"))
            for col, text in c.get("columns", {}).items():
                out.append(f"COMMENT ON COLUMN {q(t)}.{q(col)} IS '{text}';")
    return "\n".join(out)


def profile_line(m):
    bits = [m["type"]]
    if m.get("null_frac"):
        bits.append(f"{round(m['null_frac'] * 100)}% null")
    if "distinct" in m:
        bits.append(f"~{m['distinct']} distinct")
    if m.get("top_values") and m.get("distinct", 99) <= 30:
        bits.append("values: " + ", ".join(f"'{v}' ({round(f * 100)}%)" for v, f in m["top_values"][:6]))
    elif m.get("top_values"):
        bits.append("common: " + ", ".join(f"'{v}'" for v, _ in m["top_values"][:4]))
    if m.get("range"):
        bits.append(f"range '{m['range'][0]}' to '{m['range'][1]}'")
    return "; ".join(bits)


def generator_input(db):
    """What the comment generator sees: structure, profiles, samples and the query-log digest."""
    schema, digest, _ = load(db)
    out = []
    for t, meta in schema.items():
        out.append(f"TABLE {t} (~{meta['rows_estimate']} rows); primary key: {', '.join(meta['primary_key']) or 'none'}")
        for fk in meta["foreign_keys"]:
            out.append(f"  {fk}")
        for c, m in meta["columns"].items():
            out.append(f"  - {c}: {profile_line(m)}")
        out.append("  sample rows (column order as above): " + json.dumps(meta["sample_rows"], ensure_ascii=False))
        if t in digest:
            d = digest[t]
            out.append(f"  query log: {d['calls']} calls; joins: {'; '.join(d['joins']) or 'none'}; "
                       f"columns used: {'; '.join(d['columns'])}")
        out.append("")
    return "\n".join(out)


def card(db, t):
    """One table card: the unit of the corpus for the file, Meko and catalog arms (C1 + C2 + C3)."""
    schema, digest, comments = load(db)
    meta, c = schema[t], comments.get(t, {})
    lines = [f"# Table {t} (database {db})", ""]
    if c.get("comment"):
        lines += [c["comment"], ""]
    lines.append(f"About {meta['rows_estimate']} rows. Primary key: {', '.join(meta['primary_key']) or 'none'}.")
    for fk in meta["foreign_keys"]:
        lines.append(f"Foreign key: {fk}.")
    lines += ["", "Columns:"]
    for col, m in meta["columns"].items():
        desc = c.get("columns", {}).get(col, "")
        lines += ["", f"{t}.{col} ({profile_line(m)}){': ' + desc if desc else ''}"]
    if t in digest:
        d = digest[t]
        lines += ["", f"Query history: {d['statements']} distinct statements, {d['calls']} calls."]
        if d["joins"]:
            lines += ["", "Usual joins: " + "; ".join(d["joins"]) + "."]
        if d["columns"]:
            lines += ["", "Columns most used: " + "; ".join(d["columns"]) + "."]
        lines += ["", "Example statements from the log:"]
        for e in d["examples"]:
            lines += ["", e]
    # Paragraphs, not Markdown lists: Meko's ingestion joins list items with no separator.
    return "\n".join(lines).replace("`", "")


KB_PART = 6000


def kb_entries(db):
    """The database's shipped knowledge base (LiveSQLBench) as {id: entry}."""
    path = CORPUS / db / "kb.jsonl"
    if not path.exists():
        return {}
    # The shipped JSON writes LaTeX unescaped, so \frac, \text, \bar decode as form feed, tab, backspace: undo that.
    latex = str.maketrans({"\f": "\\f", "\t": "\\t", "\b": "\\b", "\r": "\\r"})
    entries = [{k: v.translate(latex) if isinstance(v, str) else v for k, v in json.loads(line).items()}
               for line in path.read_text().splitlines() if line.strip()]
    return {e["id"]: e for e in entries}


def kb_cards(db):
    """The database's shipped knowledge base (LiveSQLBench, tier C4) as cards of ~6 KB: {name: body}.

    Each entry keeps its id, so "builds on" references between entries stay resolvable.
    """
    entries = list(kb_entries(db).values())
    if not entries:
        return {}
    names = {e["id"]: e["knowledge"] for e in entries}
    paras = []
    for e in entries:
        kids = e.get("children_knowledge")
        built = f" Builds on: {'; '.join(names.get(k, str(k)) for k in kids)}." if isinstance(kids, list) and kids else ""
        paras.append(f"Term {e['id']}: {e['knowledge']} ({e['type'].replace('_', ' ')}). {e['description']} "
                     f"Definition: {e['definition']}{built}")
    cards, cur = [], []
    for p in paras:
        if cur and len("\n\n".join(cur + [p])) > KB_PART:
            cards.append(cur)
            cur = []
        cur.append(p)
    if cur:
        cards.append(cur)
    return {f"kb_part{i}": "\n\n".join([f"# Business terms and calculations (database {db}, part {i} of {len(cards)})",
                                        *chunk]).replace("`", "")
            for i, chunk in enumerate(cards, 1)}
