#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Shortened documentation files for lsb, so a Haiku session stays under its 100k-token price step.

From the same schema, profiles, column meanings and knowledge base as the full context.md, trimmed in a
fixed order until the file fits its budget; the business terms are always kept whole:
  level 1: value profiles cut to the type and up to three listed values; column meanings to their first sentence
  level 2: listed values only for columns with at most 10 distinct values
  level 3: in the widest tables first, columns other than keys lose their meaning (name and type only)
Writes lsb/<db>/context_c<k>.md for each budget k (thousand tokens), at 2.55 characters per token
(measured on the first requests of sessions given these files), and prints the level each file needed.
  T2S_SET=lsb ./lsb_capped.py [budget ...]   (default 55 35)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_lib import kb_cards, load  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CORPUS, databases  # noqa: E402

CHARS_PER_TOKEN = 2.55
HEAD = "# Database {db}: tables, columns and business terms (shortened)\n\n"


def first_sentence(text):
    text = re.sub(r"^[A-Z ]+(\([^)]*\))?\.\s*", "", text or "")  # drop the leading "TEXT." type echo
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text).strip()


def profile(m, level):
    bits = [m["type"]]
    if m.get("top_values") and m.get("distinct", 99) <= (30 if level == 1 else 10):
        bits.append("values: " + ", ".join(f"'{v}'" for v, _ in m["top_values"][:3 if level == 1 else 10]))
    return "; ".join(bits)


def keys(meta):
    fk_cols = {c.strip('" ') for fk in meta["foreign_keys"]
               for c in re.findall(r"FOREIGN KEY \(([^)]*)\)", fk)[0].split(",")} if meta["foreign_keys"] else set()
    return set(meta["primary_key"]) | fk_cols


def card(t, meta, c, level, bare):
    lines = [f"# Table {t}", f"Primary key: {', '.join(meta['primary_key']) or 'none'}."]
    if c.get("comment"):
        lines.insert(1, first_sentence(c["comment"]))
    lines += [f"Foreign key: {fk}." for fk in meta["foreign_keys"]]
    k = keys(meta)
    for col, m in meta["columns"].items():
        desc = first_sentence(c.get("columns", {}).get(col, ""))
        if bare and col not in k:
            desc = ""
        lines.append(f"{col} ({profile(m, level)}){': ' + desc if desc else ''}")
    return "\n".join(lines)


def render(db, level, bare_tables=()):
    schema, _, comments = load(db)
    cards = [card(t, meta, comments.get(t, {}), level, t in bare_tables) for t, meta in schema.items()]
    return HEAD.format(db=db) + "\n\n".join(cards + list(kb_cards(db).values())) + "\n"


def capped(db, budget_chars):
    for level in (1, 2):
        text = render(db, level)
        if len(text) <= budget_chars:
            return text, str(level)
    schema = load(db)[0]
    widest = sorted(schema, key=lambda t: -len(schema[t]["columns"]))
    for n in range(1, len(widest) + 1):
        text = render(db, 2, set(widest[:n]))
        if len(text) <= budget_chars:
            return text, f"3 ({n} tables bare)"
    return text, "3 (over budget)"


def main():
    budgets = [int(b) for b in sys.argv[1:]] or [55, 35]
    for db in databases():
        out = []
        for b in budgets:
            text, level = capped(db, int(b * 1000 * CHARS_PER_TOKEN))
            (CORPUS / db / f"context_c{b}.md").write_text(text)
            out.append(f"c{b}: {len(text)} chars, level {level}")
        print(db, len((CORPUS / db / "context.md").read_text()), "->", "; ".join(out))


if __name__ == "__main__":
    main()
