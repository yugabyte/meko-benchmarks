#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Checks that must pass before a LoCoMo run starts. Reads no secret values: it only asks whether each
setting is present and whether the services accept it.

  ./preflight.py --run cloud1

What it checks:
  .env          the key names this harness needs are set (never printed)
  dataset       datasets/ has LoCoMo
  meko          the MCP server answers and the credentials work
  openai        the key works and both models (answer and judge) are available
  gate override whether this server accepts context_search's conversation_hit_distance
  leftovers     no datapacks from an earlier run with this name

It writes runs/locomo/<run>/preflight.json; run_all.py reads `gate_override` from it. Exit code 1 if
anything required fails. A server without the gate override is NOT a failure: the run still works, but the
conversation tier then fires for only about a fifth of questions and the result is not comparable with the
published target, and the report says so.
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))

RUNS = Path(__file__).resolve().parents[2] / "runs" / "locomo"
ANSWER_MODEL, JUDGE_MODEL = "gpt-5.6-terra", "gpt-4.1-2025-04-14"


def line(status, name, detail=""):
    print(f"  {status:<5} {name:<14} {detail}", flush=True)
    return status != "FAIL"


async def probe_gate_override(meko, agent):
    """True if the server accepts context_search's conversation_hit_distance. A deliberately out-of-range value
    is validated before any datapack lookup, so the answer is unambiguous: a server that has the argument
    rejects the value, a server that does not rejects the argument."""
    from meko import MekoError
    try:
        await meko.call("context_search", read_only=True, query="probe", conversation_id=uuid.uuid4().hex,
                        datapack_id=uuid.uuid4().hex, agent_id=agent, limit=1, force_source="conversation",
                        conversation_hit_distance=3)
    except MekoError as e:
        text = str(e)
        if "invalid_conversation_hit_distance" in text:
            return True
        if "nexpected keyword" in text or "extra_forbidden" in text or "not permitted" in text:
            return False
        return None  # some other error: unknown
    return None


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    ok = True
    result = {"run": args.run, "checked": time.strftime("%Y-%m-%d %H:%M"), "gate_override": None}
    print(f"preflight for run {args.run}", flush=True)

    # .env: names only
    from auth import Auth, AuthError, load_env
    cfg = load_env()
    missing = []
    if not (cfg["static"] or (cfg["email"] and cfg["password"])):
        missing.append("MEKO_USER_TOKEN, or MEKO_EMAIL + MEKO_PASSWORD")
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if "MEKO_MCP_URL" not in os.environ:
        missing.append("MEKO_MCP_URL")
    ok &= line("FAIL" if missing else "ok", ".env", ("missing: " + "; ".join(missing)) if missing else f"url {cfg['url']}")
    if missing:
        return finish(args, result, ok)

    # dataset
    try:
        import data
        n = sum(len(s["qa"]) for s in data.load())
        ok &= line("ok" if n == 1986 else "FAIL", "dataset", f"{n} questions" + ("" if n == 1986 else " (expected 1986)"))
    except Exception as e:  # noqa: BLE001
        ok &= line("FAIL", "dataset", str(e)[:120])

    # openai: both models must be listed for this key
    import httpx
    for label, model in (("answer model", ANSWER_MODEL), ("judge model", JUDGE_MODEL)):
        try:
            r = httpx.get(f"https://api.openai.com/v1/models/{model}", timeout=20,
                          headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
            ok &= line("ok" if r.status_code == 200 else "FAIL", "openai", f"{label} {model}: HTTP {r.status_code}")
        except httpx.HTTPError as e:
            ok &= line("FAIL", "openai", f"{label}: {type(e).__name__}")

    # meko
    from meko import Meko, MekoError
    try:
        async with Meko(cfg["url"], Auth(cfg), cfg["agent"]) as meko:
            packs = await meko.call("datapack_list", read_only=True, conversation_id=meko.trace) or []
            ok &= line("ok", "meko", f"reachable, {len(packs)} datapacks visible to this account")
            left = [p.get("datapack_name") or p.get("name") for p in packs
                    if str(p.get("datapack_name") or p.get("name") or "").startswith(f"locomo-{args.run}-")]
            state = RUNS / args.run / "state.json"
            if left and not state.exists():
                ok &= line("FAIL", "leftovers", f"{len(left)} datapacks named locomo-{args.run}-* exist but this run has no state; "
                           "use a new --run name, or delete them in the UI")
            else:
                line("ok", "leftovers", "none" if not left else f"{len(left)} from this run (resume)")
            support = await probe_gate_override(meko, cfg["agent"])
            result["gate_override"] = support
            if support:
                line("ok", "gate override", "supported: the benchmark's conversation gate (2.0) will be used")
            elif support is False:
                line("warn", "gate override", "NOT supported by this server: the default gate (0.35) applies, so the conversation "
                     "tier fires for ~1 in 5 questions and J will be well below the published target")
            else:
                line("warn", "gate override", "could not be determined; treating as unsupported")
                result["gate_override"] = False
    except (AuthError, MekoError, httpx.HTTPError) as e:
        ok &= line("FAIL", "meko", f"{type(e).__name__}: {str(e)[:140]}")
    return finish(args, result, ok)


def finish(args, result, ok):
    result["ok"] = ok
    d = RUNS / args.run
    d.mkdir(parents=True, exist_ok=True)
    (d / "preflight.json").write_text(json.dumps(result, indent=1))
    print("preflight " + ("passed" if ok else "FAILED"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
