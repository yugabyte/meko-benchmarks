"""The slice of MCP this harness needs, plus the Meko calls it makes.

Speaks JSON-RPC over streamable HTTP (initialize -> tools/call). Responses may
come back as plain JSON or as an SSE body; both are handled.
"""

import asyncio
import json
import random
import uuid

import httpx

RETRY_STATUS = {429, 503}


class ConversationGone(RuntimeError):
    """The conversation cannot be written to and never will be.

    Meko keeps conversations as Langfuse traces and checks ownership by reading the trace
    back. When Langfuse drops the create event — it did for 336 questions on 2026-09-28,
    under load — the id the server handed out belongs to no trace, so every write to it
    answers `not_found` forever. `agent_id_mismatch` is the same thing half-ingested.
    The caller's remedy is a fresh conversation, not a longer wait.
    """


class MekoError(RuntimeError):
    pass


class Unauthorized(MekoError):
    pass


class Meko:
    def __init__(self, url, auth, agent_id, timeout=300.0):
        """`auth` is an auth.Auth: token() for the current key, refresh() after a 401."""
        self.url = url.rstrip("/")
        self.auth = auth
        self.agent_id = agent_id
        self.http = httpx.AsyncClient(timeout=timeout, headers={
            "Authorization": f"Bearer {auth.token()}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        })
        self.session = None
        self.rpc_id = 0
        # datapack_* tools insist on a conversation_id, but only use it to nest
        # their Langfuse trace — one id per client run keeps those traces together.
        self.trace = uuid.uuid4().hex

    async def __aenter__(self):
        try:
            await self._initialize()
        except Unauthorized:
            await self._relogin()
        return self

    async def _initialize(self):
        await self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                       "clientInfo": {"name": "locomo-harness", "version": "0.1"}})
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _relogin(self):
        """Swap in a fresh key and start a new MCP session; a second 401 is fatal."""
        self.http.headers["Authorization"] = f"Bearer {self.auth.refresh()}"
        self.session = None
        try:
            await self._initialize()
        except Unauthorized:
            raise MekoError("MCP still returns 401 after minting a new key — check MEKO_EMAIL/MEKO_PASSWORD and the stack")

    async def __aexit__(self, *exc):
        await self.http.aclose()

    # -- transport -------------------------------------------------------------

    async def _post(self, payload, read_only=False):
        headers = {"mcp-session-id": self.session} if self.session else {}
        last = None
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(random.uniform(0, min(20, 2 ** attempt)))
            try:
                r = await self.http.post(self.url, json=payload, headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
                last = e  # never reached the server: safe to retry even a write
                continue
            except httpx.HTTPError as e:
                if read_only:
                    last = e
                    continue
                raise MekoError(f"write may have landed before {type(e).__name__}; not retrying") from e
            if r.status_code == 401:
                raise Unauthorized("401 from MCP")
            if r.status_code in RETRY_STATUS or (read_only and r.status_code >= 500):
                last = MekoError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            if "mcp-session-id" in r.headers:
                self.session = r.headers["mcp-session-id"]
            return self._body(r, payload.get("id"))
        raise MekoError(f"MCP request failed after retries: {last}")

    @staticmethod
    def _body(r, want_id):
        """Decode a plain JSON or SSE reply. Events are split on newlines only: str.splitlines()
        also breaks on U+2028 and friends, which are legal inside a JSON string, and one such
        character in a replayed turn cut an event in two on every retry (2026-10-02)."""
        try:
            if "text/event-stream" not in r.headers.get("content-type", ""):
                return r.json() if r.content else None
            for line in r.text.split("\n"):
                line = line.rstrip("\r")
                if line.startswith("data:"):
                    event = json.loads(line[5:])
                    if event.get("id") == want_id:
                        return event
        except ValueError as e:  # a truncated or malformed body: let the caller's retry handle it
            raise MekoError(f"undecodable MCP reply ({e}); timed out mid-body?") from e
        return None

    async def _rpc(self, method, params, read_only=False):
        self.rpc_id += 1
        reply = await self._post({"jsonrpc": "2.0", "id": self.rpc_id, "method": method, "params": params}, read_only)
        if not reply or "error" in reply:
            raise MekoError(f"{method}: {reply and reply.get('error')}")
        return reply["result"]

    async def call(self, tool, read_only=False, **args):
        """Call one tool and return its decoded JSON payload. One 401 → new key, retry once.
        The API server rate-limits each key (60/min, burst 10 by default) and says so in the
        payload; that is waited out, not raised — nothing was written."""
        for attempt in range(6):
            try:
                return await self._call_once(tool, read_only, args)
            except MekoError as e:
                if "PAT_RATE_LIMITED" not in str(e) or attempt == 5:
                    raise
                await asyncio.sleep(61)

    async def _call_once(self, tool, read_only, args):
        try:
            result = await self._rpc("tools/call", {"name": tool, "arguments": args}, read_only)
        except Unauthorized:
            await self._relogin()
            result = await self._rpc("tools/call", {"name": tool, "arguments": args}, read_only)
        text = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "")
        if result.get("isError") or text.startswith("Error"):
            raise MekoError(f"{tool}: {text[:300]}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(payload, dict) and payload.get("error"):
            raise MekoError(f"{tool}: {payload}")
        return payload

    # -- operations ------------------------------------------------------------

    _create_lock = asyncio.Lock()  # one datapack create at a time, process-wide

    async def create_datapack(self, name):
        """Return a usable datapack with this name, creating it only if none exists.

        Serialized: api_server assigns the universe with FOR UPDATE SKIP LOCKED
        and provisions a Langfuse project inside the request, so two creates in
        flight make the second see "no universe with capacity" and the MCP's
        30 s timeout fires while the row is still being provisioned — leaving a
        datapack the caller never learned about. Adopting by name recovers those.
        """
        async with Meko._create_lock:
            usable, taken = await self._datapacks_named(name)
            if usable:
                return usable
            # Names are unique per user, and a half-provisioned row can't be deleted
            # through Meko — so step past it with a suffix rather than fail forever.
            if taken:
                for n in range(2, 10):
                    usable, taken = await self._datapacks_named(f"{name}-{n}")
                    if usable:
                        return usable
                    if not taken:
                        name = f"{name}-{n}"
                        break
            for attempt in range(6):
                try:
                    return (await self.call("datapack_create", name=name, conversation_id=self.trace))["datapack_id"]
                except MekoError as e:
                    if "timed out" in str(e):        # created server-side; wait for it to finish provisioning
                        for _ in range(12):
                            await asyncio.sleep(10)
                            if (found := (await self._datapacks_named(name))[0]):
                                return found
                        raise
                    if "capacity" not in str(e):    # lock contention reads as "no capacity"; anything else is real
                        raise
                    await asyncio.sleep(15)
            raise MekoError(f"datapack_create for {name}: universe still reports no capacity after retries")

    async def _datapacks_named(self, name):
        """(usable_id, taken): the id of a datapack with this exact name whose Langfuse
        project exists, and whether the name is occupied at all (usable or not)."""
        taken = False
        for dp in await self.call("datapack_list", read_only=True, conversation_id=self.trace) or []:
            if dp.get("datapack_name") == name or dp.get("name") == name:
                taken = True
                dp_id = dp.get("datapack_id") or dp.get("id")
                try:
                    await self.call("datapack_describe", read_only=True, datapack_id=dp_id, conversation_id=self.trace)
                    return dp_id, True
                except MekoError as e:
                    if "Langfuse" not in str(e):
                        raise                          # half-provisioned rows fail here; keep looking
        return None, taken

    async def delete_datapack(self, datapack_id):
        await self.call("datapack_delete", datapack_id=datapack_id, conversation_id=self.trace)

    async def disable_conversation_index(self, datapack_id):
        """Skip the per-turn search-cache embedding; each one costs a quota unit."""
        await self.call("datapack_update", datapack_id=datapack_id, conversation_search_opt_out=True,
                        conversation_id=self.trace)

    @staticmethod
    def _transient(e):
        """Errors worth waiting out: the owner lookup 404s while Langfuse ingestion lags
        behind conversation_create, and the MCP server's upstream timeouts under load."""
        s = str(e).lower()
        return "not_found" in s or "timed out" in s or "timeout" in s

    async def create_conversation(self, datapack_id, title, metadata):
        for attempt in range(4):
            try:
                reply = await self.call("conversation_create", agent_id=self.agent_id, datapack_id=datapack_id,
                                        title=title, metadata=json.dumps(metadata))
                return reply["id"]
            except MekoError as e:
                if "timed out" not in str(e).lower() or attempt == 3:
                    raise
                await asyncio.sleep(20)  # a timed-out create may leave an orphan trace; harmless

    async def add_turn(self, datapack_id, conversation_id, text, session_iso, seed, **meta):
        """One speaker turn, always as `input`: only `input` reaches memory
        extraction, so speaker_b must never sit in `output`."""
        args = dict(conversation_id=conversation_id, datapack_id=datapack_id, agent_id=self.agent_id,
                    input=text, output="", seed=seed,
                    metadata=json.dumps({"session_date": session_iso, **meta}))
        # `not_found` means the ownership read did not see the conversation's Langfuse
        # trace. Usually that is ingestion lag and a moment's wait fixes it; when the
        # create event was dropped it is permanent, so after ~45 seconds of it we stop
        # waiting and tell the caller to make a new conversation. (Measured on 2026-10-01
        # with the ingestion queue empty: a dropped create never becomes readable, while
        # a slow one does within seconds, so two minutes of waiting only cost worker time:
        # at six drops a minute it was 15% of an 80-worker ingest.) Timeouts are retried
        # throughout: nothing is written on either, and `seed` makes the write idempotent.
        for delay in (0.25, 0.5, 1, 2, 4, 8, 15, 15, None):
            try:
                return await self.call("conversation_add_message", **args)
            except MekoError as e:
                text = str(e)
                if "agent_id_mismatch" in text:
                    raise ConversationGone(f"{conversation_id}: {text[:120]}") from e
                if "not_found" in text and delay is None:
                    raise ConversationGone(f"{conversation_id}: never became readable") from e
                if not self._transient(e) or delay is None:   # last attempt: let a timeout surface
                    raise
                await asyncio.sleep(delay)

    async def memories(self, datapack_id, conversation_id):
        """(total, first page) from the API server's paginated listing. The page is
        ~20 rows — count with `total`, never len(page). Rows carry the API's own
        insert time, not the memory's created_at — use memory() for real dates."""
        for attempt in range(4):
            try:
                reply = await self.call("memory_get_all", read_only=True, datapack_id=datapack_id,
                                        conversation_id=conversation_id, agent_id=self.agent_id)
                break
            except MekoError as e:
                if "timed out" not in str(e).lower() or attempt == 3:
                    raise
                await asyncio.sleep(20)
        page = reply.get("memories", [])
        return reply.get("total", len(page)), page

    async def memory(self, memory_id, datapack_id, conversation_id):
        """mem0's own view of one memory: text under `memory`, backdated `created_at`."""
        return await self.call("memory_get_by_id", read_only=True, memory_id=memory_id,
                               datapack_id=datapack_id, conversation_id=conversation_id, agent_id=self.agent_id)
