#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "httpx>=0.27"]
# ///
"""Learning arms: one lesson store per stream (one database's questions in order), behind the same two tools.

  save_lesson(topic, text)   L-F: appended to the lessons file; L-Mm: Meko memory_add, as shipped (no topic
                             replacement); L-Mk: the topic's Meko knowledge-base document is replaced (old one
                             deleted, new one uploaded, then waited on until indexed)
  search_lessons(query)      L-Mm: memory_search; L-Mk: knowledgebase_search.
                             L-F has no search: the harness puts the whole file in the system prompt.

Env: MEKO_MCP_URL, MEKO_API_KEY, T2S_LESSONS (file | mem | kb), T2S_STORE (stream id), T2S_LESSON_FILE (F), T2S_LESSON_DIR (Mk's
topic registry), T2S_MEKO_DATAPACK / T2S_MEKO_CONVERSATION (Mm, Mk), T2S_PHASE (answer: search only;
correct: save and search), T2S_LOG.
CLI: lessons_server.py init <store>  -> creates the stream's datapack and conversation (Mm, Mk), prints JSON
     lessons_server.py dump          -> prints the store's lessons as JSON (end of stream)
     lessons_server.py delete <datapack> <conversation>   -> deletes a stream's datapack
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

KIND = os.environ.get("T2S_LESSONS", "")
STORE = os.environ.get("T2S_STORE", "")
PHASE = os.environ.get("T2S_PHASE", "answer")
LOG = os.environ.get("T2S_LOG")
URL = os.environ.get("MEKO_MCP_URL", "")
DATAPACK = os.environ.get("T2S_MEKO_DATAPACK", "")
CONVERSATION = os.environ.get("T2S_MEKO_CONVERSATION", "")
AGENT_ID = "t2s-learn"
NIL = "00000000-0000-0000-0000-000000000000"
INDEX_WAIT_S = 300


def log(tool, args, out, t0, **extra):
    if LOG:
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"tool": tool, "args": args, "ms": round((time.time() - t0) * 1000),
                                 "out_chars": len(out), "store": KIND, **extra}) + "\n")


def norm(topic):
    return re.sub(r"\s+", " ", topic.strip().lower())[:120] or "general"


# ---- Meko ---------------------------------------------------------------------------------------------

async def _meko(tool, args):
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
    client = create_mcp_http_client(headers={"Authorization": f"Bearer {os.environ['MEKO_API_KEY']}"}, timeout=120)
    async with client, streamable_http_client(URL, http_client=client) as st:
        async with ClientSession(st[0], st[1]) as s:
            await s.initialize()
            res = await asyncio.wait_for(s.call_tool(tool, args), 180)
    raw = "".join(c.text for c in res.content if hasattr(c, "text"))
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        try:
            data = json.loads(data["result"])
        except ValueError:
            pass
    return data


async def meko(tool, args):
    """One Meko call, retried: connections drop and the token can be rate-limited."""
    for attempt in range(4):
        try:
            out = await _meko(tool, args)
            if isinstance(out, dict) and "RATE_LIMITED" in str(out.get("error", "")):
                raise RuntimeError(out)
            return out
        except Exception:  # noqa: BLE001 - retried, then raised
            if attempt == 3:
                raise
            await asyncio.sleep(65 if attempt else 10)


def ids(extra=None):
    return {"datapack_id": DATAPACK, "conversation_id": CONVERSATION, "agent_id": AGENT_ID, **(extra or {})}


def kb_registry():
    p = Path(os.environ["T2S_LESSON_DIR"]) / "kb_topics.json"
    return p, (json.loads(p.read_text()) if p.exists() else {})


async def kb_save(topic, text):
    """Replace the topic's document: find the old one's id by search (hits carry document_id, uploads do not)."""
    path, reg = kb_registry()
    deleted = 0
    if topic in reg:
        res = await meko("knowledgebase_search", ids({"query": f"Lesson: {topic}", "limit": 10}))
        for h in res.get("results", []) if isinstance(res, dict) else []:
            # Meko rewrites the "# " heading as "Section: " in chunk text.
            head = h.get("chunk_text", "").splitlines()[:1]
            if head and head[0] in (f"Section: Lesson: {topic}", f"# Lesson: {topic}") and h.get("document_id"):
                await meko("knowledgebase_delete_document", {"document_id": h["document_id"], "datapack_id": DATAPACK,
                                                             "conversation_id": CONVERSATION})
                deleted += 1
    # A heading is needed: without one Meko indexes the document as "completed" with no chunks.
    body = f"# Lesson: {topic}\n\n{text.strip()}\n".encode()
    name = re.sub(r"[^a-z0-9]+", "-", topic)[:60].strip("-") + ".md"
    up = await meko("knowledgebase_upload_document", ids({
        "filename": name, "size": len(body), "content_hash": hashlib.sha256(body).hexdigest(),
        "content_head_base64": base64.b64encode(body[:3072]).decode()}))
    if not isinstance(up, dict) or ("url" not in up and not up.get("already_uploaded")):
        raise RuntimeError(f"upload {name}: {up}")
    if not up.get("already_uploaded"):
        r = httpx.post(up["url"], data=up["fields"], files={"file": (name, body, "text/markdown")}, timeout=120)
        if r.status_code >= 300:
            raise RuntimeError(f"S3 upload {name}: {r.status_code}")
    t0, state = time.time(), "?"
    while time.time() - t0 < INDEX_WAIT_S:  # the next question must be able to find it
        st = await meko("knowledgebase_document_status", ids({"document_key": up["key"]}))
        state = st.get("state", "?") if isinstance(st, dict) else "?"
        if state in ("completed", "failed", "error"):
            break
        await asyncio.sleep(3)
    reg[topic] = up["key"]
    path.write_text(json.dumps(reg, indent=1))
    return {"deleted": deleted, "index_state": state, "index_wait_s": round(time.time() - t0, 1)}


# ---- tools ----------------------------------------------------------------------------------------------

def save(topic, text):
    topic = norm(topic)
    if KIND == "file":
        with open(os.environ["T2S_LESSON_FILE"], "a") as fh:
            fh.write(f"\n## {topic}\n{text.strip()}\n")
        return {}
    if KIND == "mem":
        out = asyncio.run(meko("memory_add", ids({"text": f"{topic}: {text.strip()}"})))
        return {"meko": str(out)[:300]}
    if KIND == "kb":
        return asyncio.run(kb_save(topic, text))
    raise SystemExit(f"unknown lesson store {KIND}")


def search(query, limit):
    limit = max(1, min(int(limit), 10))
    if KIND == "mem":
        res = asyncio.run(meko("memory_search", ids({"query": query, "limit": limit})))
        return [h.get("memory") or h.get("text") or "" for h in (res.get("results", []) if isinstance(res, dict) else [])]
    if KIND == "kb":
        res = asyncio.run(meko("knowledgebase_search", ids({"query": query, "limit": limit})))
        return [h.get("chunk_text", "") for h in (res.get("results", []) if isinstance(res, dict) else [])]
    return []


def serve():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("lessons")

    if KIND != "file":
        @mcp.tool()
        def search_lessons(query: str, limit: int = 5) -> str:
            """Search the lessons learned from the user's earlier corrections on this database (business rules,
            definitions and conventions). Returns the best-matching lessons."""
            t0 = time.time()
            hits = search(query, limit)
            text = "\n\n---\n\n".join(h for h in hits if h) or "(no matching lessons)"
            log("search_lessons", {"query": query, "limit": limit}, text, t0, hits=len(hits), phase=PHASE)
            return text

    if PHASE == "correct":
        @mcp.tool()
        def save_lesson(topic: str, text: str) -> str:
            """Save one lesson for future questions on this database: a short topic (the business term or rule)
            and the lesson itself. Saving a topic that already exists replaces it where the store allows."""
            t0 = time.time()
            extra = save(topic, text)
            log("save_lesson", {"topic": topic, "text": text}, "saved", t0, **extra)
            return "saved"

    mcp.run()


def init(store):
    """Mm / Mk: a datapack and conversation for this stream."""
    name = f"t2s-{store}"
    if len(name) > 60:  # Meko's limit; keep it unique with a hash of the full name
        name = name[:51] + "-" + hashlib.sha256(name.encode()).hexdigest()[:8]
    found = asyncio.run(meko("datapack_search", {"name": name, "conversation_id": NIL}))
    hits = [h for h in (found.get("datapacks", []) if isinstance(found, dict) else [])
            if (h.get("datapack_name") or h.get("name")) == name]  # the search also matches similar names
    if hits:
        dp = hits[0].get("datapack_id") or hits[0].get("id")
    else:
        made = asyncio.run(meko("datapack_create", {"name": name, "conversation_id": NIL}))
        dp = made.get("datapack_id") or made.get("id") if isinstance(made, dict) else None
        if not dp:
            raise SystemExit(f"datapack_create {name}: {made}")
    conv = asyncio.run(meko("conversation_create", {"agent_id": AGENT_ID, "datapack_id": dp, "title": name}))
    return {"datapack": dp, "conversation": conv.get("conversation_id") or conv.get("id")}


def dump():
    if KIND == "file":
        p = Path(os.environ["T2S_LESSON_FILE"])
        return {"text": p.read_text() if p.exists() else ""}
    if KIND == "mem":
        return {"memories": asyncio.run(meko("memory_get_all", ids()))}
    if KIND == "kb":
        return {"topics": kb_registry()[1]}
    return {}


if __name__ == "__main__":
    if sys.argv[1:2] == ["init"]:
        print(json.dumps(init(sys.argv[2])))
    elif sys.argv[1:2] == ["delete"]:  # a stream's datapack, by the ids its init recorded
        out = asyncio.run(meko("datapack_delete", {"datapack_id": sys.argv[2], "conversation_id": sys.argv[3]}))
        print(json.dumps(out, default=str)[:300])
        sys.exit(1 if not isinstance(out, dict) or out.get("error") else 0)
    elif sys.argv[1:2] == ["dump"]:
        print(json.dumps(dump(), default=str))
    else:
        serve()
