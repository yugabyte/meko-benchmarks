#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "httpx>=0.27"]
# ///
"""Load the documentation into Meko for the search arms: one datapack per database (one for the whole fleet),
its knowledge base holding that database's table cards, one document per card.

  T2S_SET=novel ./meko_load.py setup [db ...]   create datapacks t2s-<set>-<db> if missing, upload the cards
  T2S_SET=novel ./meko_load.py status           each document's indexing state, and a count per state
  T2S_SET=novel ./meko_load.py wait [seconds]   until every document is indexed (default limit 3600 s)
  T2S_SET=novel ./meko_load.py search <db> <query>
  T2S_SET=novel ./meko_load.py delete           delete the datapacks this script created for the set

Settings come from .env (MEKO_MCP_URL and a token or login, see .env.example). Writes
runs/text-to-sql/meko-<set>.json ({datapacks, conversations, keys, created}), which run.py reads.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CORPUS, RUNS, SET, databases, meko_settings  # noqa: E402

AGENT_ID = "t2s-bench"
CONFIG = RUNS / f"meko-{SET}.json"
NIL = "00000000-0000-0000-0000-000000000000"


async def call(s, tool, args):
    # A call can hang with no reply; the upload loop retries a RuntimeError.
    try:
        res = await asyncio.wait_for(s.call_tool(tool, args), 180)
    except asyncio.TimeoutError:
        raise RuntimeError(f"{tool}: no reply in 180 s") from None
    text = "".join(c.text for c in res.content if hasattr(c, "text"))
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("result"), str):
            try:
                data = json.loads(data["result"])
            except ValueError:
                pass
        return data
    except ValueError:
        return text


def post_multipart(url, fields, filename, body):
    files = {"file": (filename, body, "text/markdown")}
    r = httpx.post(url, data=fields, files=files, timeout=120)
    if r.status_code >= 300:
        raise RuntimeError(f"S3 upload {filename}: {r.status_code} {r.text[:300]}")
    return r.status_code


TAG = re.compile(r"<(/?[A-Za-z][^<>]*)>")


def meko_safe(text):
    """Escape tag-like text, which Meko's ingestion strips; search returns it unescaped."""
    return TAG.sub(r"\\<\1\\>", text)


MAX_PART = 12000


def parts(path):
    """(filename, text) pieces of a card. Cards over MAX_PART bytes are split at paragraph boundaries,
    each part repeating the card's heading: Meko can fail to index a very large card."""
    text = meko_safe(path.read_text())
    if len(text.encode()) <= MAX_PART:
        return [(path.name, text)]
    paras = text.split("\n\n")
    head, out, cur = paras[0], [], []
    for para in paras[1:]:
        if cur and len("\n\n".join([head, *cur, para]).encode()) > MAX_PART:
            out.append(cur)
            cur = []
        cur.append(para)
    out.append(cur)
    stem = path.stem
    return [(f"{stem}.part{i}.md", "\n\n".join([f"{head} (part {i} of {len(out)})", *chunk]) + "\n")
            for i, chunk in enumerate(out, 1)]


async def upload(s, conv, dp, name, text):
    body = text.encode()
    up = await call(s, "knowledgebase_upload_document", {
        "filename": name, "size": len(body), "content_hash": hashlib.sha256(body).hexdigest(),
        "content_head_base64": base64.b64encode(body[:3072]).decode(), "conversation_id": conv,
        "datapack_id": dp, "agent_id": AGENT_ID})
    if not isinstance(up, dict) or "url" not in up and not up.get("already_uploaded"):
        raise RuntimeError(f"upload {name}: {up}")
    if up.get("already_uploaded"):
        return up.get("key"), "already"
    status = post_multipart(up["url"], up["fields"], name, body)
    return up["key"], status


async def main(argv):
    if not SET:
        raise SystemExit("set T2S_SET (bird, lsb, fleet or novel)")
    url, token = meko_settings()
    client = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}, timeout=120)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {"datapacks": {}, "keys": {}}
    cfg.setdefault("created", [])
    async with client, streamable_http_client(url, http_client=client) as st:
        async with ClientSession(st[0], st[1]) as s:
            await s.initialize()
            # conversation_create needs a datapack, and datapack_search / datapack_create need a
            # conversation, so setup calls use the nil UUID; each datapack then gets its own
            # conversation for the harness's searches.
            conv = NIL
            cfg.setdefault("conversations", {})
            cmd = argv[0]
            if cmd == "setup":
                for db in argv[1:] or databases():
                    name = f"t2s-{SET}-{db}"
                    if db not in cfg["datapacks"]:
                        found = await call(s, "datapack_search", {"name": name, "conversation_id": conv})
                        hits = [h for h in (found.get("datapacks", []) if isinstance(found, dict) else [])
                                if (h.get("datapack_name") or h.get("name")) == name]  # the search also matches similar names
                        if hits:
                            cfg["datapacks"][db] = hits[0].get("datapack_id") or hits[0].get("id")
                        else:
                            made = await call(s, "datapack_create", {"name": name, "conversation_id": conv})
                            if not isinstance(made, dict):
                                raise RuntimeError(f"datapack_create {name}: {made}")
                            cfg["datapacks"][db] = made.get("datapack_id") or made.get("id")
                            cfg["created"].append(db)
                        CONFIG.write_text(json.dumps(cfg, indent=1))
                    dp = cfg["datapacks"][db]
                    if db not in cfg["conversations"]:
                        made = await call(s, "conversation_create", {
                            "scope": "write", "agent_id": AGENT_ID, "datapack_id": dp,
                            "title": f"text-to-sql benchmark: {db}"})
                        cfg["conversations"][db] = made.get("conversation_id") or made.get("id")
                    sem = asyncio.Semaphore(int(os.environ.get("MEKO_PARALLEL", "6")))

                    async def one(db, dp, name, text):
                        async with sem:
                            for attempt in range(5):  # presign calls can time out and connections drop under load
                                try:
                                    key, st_ = await upload(s, conv, dp, name, text)
                                    break
                                except Exception as e:  # noqa: BLE001 - retried, then fatal
                                    print(db, name, "retry", attempt + 1, type(e).__name__, e, flush=True)
                                    await asyncio.sleep(65 if "RATE_LIMITED" in str(e) else 10 * (attempt + 1))
                            else:
                                raise RuntimeError(f"giving up on {db}/{name}")
                            cfg["keys"][f"{db}/{name}"] = key
                            print(db, name, st_, flush=True)

                    # Cards recorded as uploaded are not re-checked: each check is a call, and the token is rate-limited.
                    cards = [pt for path in sorted((CORPUS / db / "cards").glob("*.md")) for pt in parts(path)
                             if f"{db}/{pt[0]}" not in cfg["keys"]]
                    try:
                        await asyncio.gather(*(one(db, dp, name, text) for name, text in cards))
                    finally:
                        CONFIG.write_text(json.dumps(cfg, indent=1))
            elif cmd == "status":
                counts = {}
                for k, key in cfg["keys"].items():
                    db = k.split("/")[0]
                    st_ = await call(s, "knowledgebase_document_status", {
                        "document_key": key, "conversation_id": conv, "datapack_id": cfg["datapacks"][db]})
                    state = st_.get("state") if isinstance(st_, dict) else str(st_)[:60]
                    counts[state] = counts.get(state, 0) + 1
                    if state != "completed":
                        print(k, state)
                print(json.dumps(counts))
            elif cmd == "search":
                db, query = argv[1], " ".join(argv[2:])
                print(json.dumps(await call(s, "knowledgebase_search", {
                    "query": query, "datapack_id": cfg["datapacks"][db], "conversation_id": cfg["conversations"][db],
                    "agent_id": AGENT_ID, "limit": 5}), indent=1)[:4000])
            elif cmd == "wait":  # until every uploaded card is indexed: searching earlier finds only part of it
                pending, t0 = dict(cfg["keys"]), asyncio.get_running_loop().time()
                limit = float(argv[1]) if len(argv) > 1 else 3600
                while pending:
                    for k, key in list(pending.items()):
                        st_ = await call(s, "knowledgebase_document_status", {
                            "document_key": key, "conversation_id": conv, "datapack_id": cfg["datapacks"][k.split("/")[0]]})
                        state = st_.get("state") if isinstance(st_, dict) else None
                        if state == "completed":
                            del pending[k]
                        elif state in ("failed", "error"):
                            raise SystemExit(f"{k}: indexing {state}")
                    print(f"{len(cfg['keys']) - len(pending)} of {len(cfg['keys'])} documents indexed", flush=True)
                    if pending and asyncio.get_running_loop().time() - t0 > limit:
                        raise SystemExit(f"{len(pending)} documents still not indexed after {limit:.0f} s")
                    if pending:
                        await asyncio.sleep(30)
            elif cmd == "delete":  # only datapacks this script created, never ones it found by name
                for db in list(cfg["created"]):
                    out = await call(s, "datapack_delete", {"datapack_id": cfg["datapacks"][db],
                                                            "conversation_id": cfg["conversations"].get(db, NIL)})
                    print(db, cfg["datapacks"][db], str(out)[:120])
                    if not isinstance(out, dict) or out.get("error"):
                        continue  # keep it in the config, so a later delete can try again
                    for k in [k for k in cfg["keys"] if k.split("/")[0] == db]:
                        del cfg["keys"][k]
                    cfg["datapacks"].pop(db), cfg["conversations"].pop(db, None), cfg["created"].remove(db)
                    CONFIG.write_text(json.dumps(cfg, indent=1))
            elif cmd == "raw":
                print(json.dumps(await call(s, argv[1], json.loads(argv[2])), indent=1)[:4000])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
