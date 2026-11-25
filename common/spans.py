"""Every call one question makes, as it happens: runs/<bench>/<run>/spans/<qid>.jsonl, one line per call.

The console's trace view reads these and hangs the memory server's own Langfuse spans under the MCP calls.
A line: phase (retrieve | answer | judge), kind (mcp | llm), name, k (None when shared by every k), start and
end (epoch seconds), the arguments, the prompt and the raw reply in full, token usage, the Langfuse trace id
(retrieval only), and the error if the call failed. Retries and resumed runs add lines; nothing is rewritten.
"""

import json
import time
from pathlib import Path


def fname(qid):
    return str(qid).replace("/", "_").replace(":", "_") + ".jsonl"


class Spans:
    def __init__(self, run_dir, phase):
        self.dir = Path(run_dir) / "spans"
        self.dir.mkdir(exist_ok=True)
        self.phase = phase

    def write(self, qid, span):
        line = json.dumps({"phase": self.phase, **span}, ensure_ascii=False, default=str)
        with open(self.dir / fname(qid), "a") as f:
            f.write(line + "\n")

    async def mcp(self, qid, meko, tool, k=None, summary=None, **args):
        """meko.call(tool, **args), recorded. `summary(result)` keeps a short description, not the whole payload."""
        t0, err, res = time.time(), None, None
        try:
            res = await meko.call(tool, **args)
            return res
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:400]}"
            raise
        finally:
            s = None
            if res is not None and summary:
                try:
                    s = summary(res)
                except Exception:
                    pass
            self.write(qid, {"kind": "mcp", "name": tool, "k": k, "start": t0, "end": time.time(), "args": args,
                             "trace": args.get("conversation_id"), "result": s, "error": err})


def usage_of(r):
    """Token counts from a chat.completions or responses reply."""
    u = getattr(r, "usage", None)
    if not u:
        return None
    get = lambda o, *names: next((getattr(o, n) for n in names if o is not None and getattr(o, n, None) is not None), None)
    det = get(u, "completion_tokens_details", "output_tokens_details")
    cached = get(get(u, "prompt_tokens_details", "input_tokens_details"), "cached_tokens")
    return {"input": get(u, "prompt_tokens", "input_tokens"), "output": get(u, "completion_tokens", "output_tokens"),
            "reasoning": get(det, "reasoning_tokens"), "cached": cached, "total": get(u, "total_tokens")}


def llm_span(name, k, model, t0, params, system, user, r=None, text=None, err=None):
    """One model call as a span line; `r` is the API reply object when there is one."""
    span = {"kind": "llm", "name": name, "k": k, "model": model, "start": t0, "end": time.time(), "args": params,
            "system": system, "prompt": user, "reply": text, "error": err}
    if r is not None:
        span.update(usage=usage_of(r), served_model=getattr(r, "model", None), response_id=getattr(r, "id", None))
        ch = getattr(r, "choices", None)
        if ch:
            span["finish_reason"] = getattr(ch[0], "finish_reason", None)
        elif getattr(r, "status", None):
            span["finish_reason"] = r.status
    return span
