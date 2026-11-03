#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Bearer token for Meko without hand-copying keys from the UI.

Order of preference: MEKO_USER_TOKEN from .env → the key cached in common/.token →
log in with MEKO_EMAIL / MEKO_PASSWORD and mint a fresh API key (mko_tkn_…).
When the MCP client gets a 401 it calls refresh(), which mints again, so an
expired or revoked key heals itself mid-run.

  ./auth.py        fetch (or mint) a token and print its prefix + expiry
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent          # the repo
ENV_FILES = [ROOT / ".env"]  # the repo-root .env (copy .env.example)
CACHE = ROOT / "common" / ".token"
KEY_NAME = "locomo-harness"   # one named key per user; old ones are revoked before minting


class AuthError(RuntimeError):
    pass


def _parse(ts):
    """api_server dates look like 2026-12-23T08:06:17.66098Z — trim the fraction
    to microseconds and spell out UTC so every Python version parses them."""
    head, _, tail = ts.partition(".")
    if tail:
        digits = tail.rstrip("Z").split("+")[0].split("-")[0]
        tail = digits[:6].ljust(6, "0") + tail[len(digits):]
        ts = f"{head}.{tail}"
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_env():
    """The repo-root .env, KEY=VALUE per line; the process environment wins."""
    env_file = next((f for f in ENV_FILES if f.exists()), ENV_FILES[-1])
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    g = os.environ.get
    url = g("MEKO_MCP_URL", "http://127.0.0.1:8000/mcp")
    return {"url": url,
            # MEKO_MCP_URLS=url1,url2 spreads the ingest over several MCP server replicas (one Python process is CPU-bound)
            "urls": [u.strip() for u in g("MEKO_MCP_URLS", url).split(",") if u.strip()],
            "api": g("MEKO_API_URL", "http://127.0.0.1:25433/api/v1").rstrip("/"),
            "agent": g("MEKO_AGENT_ID", "meko"),
            "static": g("MEKO_USER_TOKEN", ""),
            "email": g("MEKO_EMAIL", ""), "password": g("MEKO_PASSWORD", "")}


class Auth:
    def __init__(self, cfg):
        self.cfg = cfg
        self.static_failed = False

    def token(self):
        if self.cfg["static"] and not self.static_failed:
            return self.cfg["static"]
        cached = self._cached()
        return cached or self.refresh()

    def refresh(self):
        """Called after a 401. Logs in, revokes this harness's old keys, mints a new one."""
        if self.cfg["static"] and not self.static_failed:
            self.static_failed = True          # fall through to the login path once
            if self._cached():
                return self._cached()
        if not (self.cfg["email"] and self.cfg["password"]):
            why = "the key was rejected" if self.cfg["static"] else "no key is cached"
            raise AuthError(f"{why}, and .env has no MEKO_EMAIL / MEKO_PASSWORD to mint one")
        jwt = self._login()
        with httpx.Client(base_url=self.cfg["api"], timeout=30,
                          headers={"Authorization": f"Bearer {jwt}"}) as api:
            for key in self._data(api.get("/me/meko-tokens")) or []:
                if key.get("name") == KEY_NAME and not key.get("revoked_at"):
                    api.delete(f"/me/meko-tokens/{key['id']}")
            minted = self._data(api.post("/me/meko-tokens", json={"name": KEY_NAME, "ttl_days": 90}))
        token = minted["token"]
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"token": token, "expires_at": minted["token_record"]["expires_at"],
                              "minted_at": datetime.now(timezone.utc).isoformat()})
        fd = os.open(CACHE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # never world-readable, even briefly
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        CACHE.chmod(0o600)
        return token

    def _login(self):
        r = httpx.post(f"{self.cfg['api']}/auth/login", timeout=30,
                       json={"email": self.cfg["email"], "password": self.cfg["password"]})
        data = self._data(r)
        if data.get("challenge"):
            raise AuthError(f"login needs '{data['challenge']}' first — finish it once in the UI")
        return data["access_token"]

    def _cached(self):
        if not CACHE.exists():
            return None
        c = json.loads(CACHE.read_text())
        if _parse(c["expires_at"]) < datetime.now(timezone.utc) + timedelta(days=1):
            return None
        return c["token"]

    @staticmethod
    def _data(r):
        """api_server wraps everything as {"data": ..., "error": {...}}."""
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code >= 400 or body.get("error"):
            msg = (body.get("error") or {}).get("message") or r.text[:200]
            raise AuthError(f"{r.request.method} {r.request.url.path} → HTTP {r.status_code}: {msg}")
        data = body.get("data", body)
        return data.get("tokens", data) if isinstance(data, dict) and "tokens" in data else data


if __name__ == "__main__":
    try:
        token = Auth(load_env()).token()
    except AuthError as e:
        sys.exit(f"auth failed: {e}")
    expiry = json.loads(CACHE.read_text())["expires_at"][:10] if CACHE.exists() else "n/a (static key)"
    print(f"token ok: {token[:8]}…  expires {expiry}")
