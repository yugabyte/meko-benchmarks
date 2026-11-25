#!/usr/bin/env bash
# Download LoCoMo-10 (Maharana et al., 2024) into datasets/locomo/locomo10/.
# The dataset is CC BY-NC 4.0 and is not redistributed with this Apache-2.0 repository.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p locomo10
curl -fsSL https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json -o locomo10/locomo10.json
python3 - <<'PY'
import json
d = json.load(open("locomo10/locomo10.json"))
n = sum(len(s["qa"]) for s in d)
print(f"{len(d)} conversations, {n} questions")
assert len(d) == 10 and n == 1986, "unexpected dataset contents"
PY
