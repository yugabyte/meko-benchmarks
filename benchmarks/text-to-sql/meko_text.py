#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0"]
# ///
"""Arm A4t: Meko knowledge-base search behind a thin stdio MCP server.

Exposes search_context(query, limit), calls Meko's knowledgebase_search for the configured datapack, and
returns only each hit's text rather than Meko's JSON envelope. The datapack and conversation ids stay in
the server, so the model does not have to repeat them on every call.

Env: MEKO_MCP_URL, MEKO_API_KEY, T2S_MEKO_DATAPACK, T2S_MEKO_CONVERSATION, T2S_LOG (JSONL of every call).
"""
import json
import os
import time

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.server.mcpserver import MCPServer

URL = os.environ["MEKO_MCP_URL"]
DATAPACK = os.environ["T2S_MEKO_DATAPACK"]
CONVERSATION = os.environ["T2S_MEKO_CONVERSATION"]
LOG = os.environ.get("T2S_LOG")
AGENT_ID = "t2s-bench"

mcp = MCPServer("meko")


async def knowledgebase_search(query, limit):
    client = create_mcp_http_client(headers={"Authorization": f"Bearer {os.environ['MEKO_API_KEY']}"}, timeout=120)
    async with client, streamable_http_client(URL, http_client=client) as st:
        async with ClientSession(st[0], st[1]) as s:
            await s.initialize()
            res = await s.call_tool("knowledgebase_search", {
                "query": query, "datapack_id": DATAPACK, "conversation_id": CONVERSATION,
                "agent_id": AGENT_ID, "limit": limit})
    raw = "".join(c.text for c in res.content if hasattr(c, "text"))
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        data = json.loads(data["result"])
    return raw, data.get("results", [])


@mcp.tool()
async def search_context(query: str, limit: int = 5) -> str:
    """Search the database documentation (table descriptions, column meanings and values, business terms,
    usual joins and example queries). Returns the best-matching documents."""
    t0 = time.time()
    raw, hits = await knowledgebase_search(query, max(1, min(int(limit), 10)))
    text = "\n\n---\n\n".join(h.get("chunk_text", "") for h in hits) or "(no matching documents)"
    if LOG:
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"tool": "search_context", "args": {"query": query, "limit": limit},
                                 "ms": round((time.time() - t0) * 1000), "out_chars": len(text),
                                 "meko_chars": len(raw), "hits": len(hits)}) + "\n")
    return text


if __name__ == "__main__":
    mcp.run()
