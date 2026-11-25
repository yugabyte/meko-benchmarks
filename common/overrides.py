"""Per-run prompt overrides: a JSON file {NAME: text} applied to the prompt modules before any call.

The console writes runs/<bench>/<run>/prompts.json when a prompt was edited for that run;
answer.py applies it with --prompts-file. Every run's answer.json still carries the sha of the
prompt text that actually ran (prompts.fingerprints), so an edited prompt is always visible later.
"""

import json
from pathlib import Path

INT_KEYED = {"FORMAT_RULES", "HINTS"}  # dicts keyed by LoCoMo category id; JSON turns the keys into strings


def apply(path, targets):
    """targets: {NAME: module whose attribute NAME is replaced}. Returns the names applied."""
    data = json.loads(Path(path).read_text())
    applied = []
    for name, value in data.items():
        mod = targets.get(name)
        if mod is None:
            raise SystemExit(f"{path}: unknown prompt {name!r}; known: {', '.join(sorted(targets))}")
        if name in INT_KEYED and isinstance(value, dict):
            value = {int(k): v for k, v in value.items()}
        setattr(mod, name, value)
        applied.append(name)
    return applied
