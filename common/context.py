"""How retrieved memories and conversation turns are shown to the answer model (mem0's rendering)."""

from datetime import datetime


def human_date(iso):
    """'2023-05-08T13:56:00+00:00' -> 'Monday, May 08, 2023' (mem0's rendering)."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%A, %B %d, %Y")
    except ValueError:
        return str(iso)[:10]


def memories_block(hits):
    """mem0 shows the hits oldest-first with dates and no ranks/scores, to avoid anchoring."""
    if not hits:
        return "(No relevant memories found)"
    lines = ["The following memories are presented in chronological order (oldest to newest).", ""]
    for h in sorted(hits, key=lambda h: h.get("created_at") or ""):
        lines.append(f"({human_date(h['created_at']) if h.get('created_at') else 'unknown date'}) {h['memory']}")
    return "\n".join(lines)


def conversation_turns(conv):
    """Verbatim turns from context_search: the matched chunks plus their expanded sessions,
    deduplicated and oldest-first. The server returns threads newest-first, so reverse them."""
    if not conv:
        return []
    seen, turns = set(), []
    for t in list(reversed(conv.get("thread") or [])) + (conv.get("hits") or []):
        key = t.get("message_id") or t.get("content")
        if key and key not in seen and t.get("content"):
            seen.add(key)
            turns.append(t)
    return sorted(turns, key=lambda t: t.get("session_date") or "")  # stable: keeps turn order within a session


def conversation_block(conv):
    """Raw turns as a second block under the memories. Each turn's text already starts with its date."""
    turns = conversation_turns(conv)
    if not turns:
        return ""
    return "\n".join(["", "", "The following are verbatim conversation turns from past sessions, oldest to newest.", ""]
                     + [t["content"] for t in turns])


def context_block(row):
    """Everything the answer model reads: memories first, then any conversation turns."""
    return memories_block(row.get("hits")) + conversation_block(row.get("conversation"))
