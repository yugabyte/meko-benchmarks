#!/usr/bin/env bash
# Download the third-party data for the text-to-SQL benchmark into datasets/text-to-sql/downloads/.
#
#   ./fetch.sh          BIRD Mini-Dev, BIRD dev and the public LiveSQLBench-Large files
#
# The data are not redistributed with this Apache-2.0 repository; see README.md for licences and citations.
# Two LiveSQLBench files cannot be fetched by a script. The script says what to do when they are missing.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p downloads && cd downloads

if [[ ! -f minidev/MINIDEV/mini_dev_postgresql.json ]]; then
  echo "== BIRD Mini-Dev (about 800 MB)"
  curl -fL --retry 3 -o minidev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip
  unzip -q -o minidev.zip && rm minidev.zip
fi

if [[ ! -f bird-dev/dev_20240627/dev.json ]]; then
  echo "== BIRD dev, for the query history the comments are written from (about 350 MB)"
  mkdir -p bird-dev
  curl -fL --retry 3 -o bird-dev/dev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip
  (cd bird-dev && unzip -q -o dev.zip -x 'dev_20240627/dev_databases.zip' && rm dev.zip)
fi

mkdir -p lsb-large
if [[ ! -f lsb-large/meta/livesqlbench_large_v1_data.jsonl ]]; then
  echo "== LiveSQLBench-Large: tasks, schemas, column meanings and knowledge base (Hugging Face)"
  git clone -q https://huggingface.co/datasets/birdsql/livesqlbench-large-v1 lsb-large/meta
fi

python3 - <<'PY'
import json
mini = json.load(open("minidev/MINIDEV/mini_dev_postgresql.json"))
dev = json.load(open("bird-dev/dev_20240627/dev.json"))
lsb = sum(1 for _ in open("lsb-large/meta/livesqlbench_large_v1_data.jsonl"))
print(f"BIRD Mini-Dev {len(mini)} questions, BIRD dev {len(dev)} questions, LiveSQLBench-Large {lsb} tasks")
assert len(mini) == 500 and len(dev) == 1534, "unexpected BIRD contents"
PY

missing=0
if [[ ! -d lsb-large/dumps/postgre_table_dumps_large ]]; then
  if [[ -f lsb-large/postgre_table_dumps_large.zip ]]; then
    (cd lsb-large && unzip -q -o postgre_table_dumps_large.zip -d dumps)
  else
    missing=1
    cat <<'EOF'

TO DO (a person): download the LiveSQLBench-Large PostgreSQL dumps, postgre_table_dumps_large.zip (about 330 MB),
from the Google Drive link in the dataset card (https://huggingface.co/datasets/birdsql/livesqlbench-large-v1),
save it as datasets/text-to-sql/downloads/lsb-large/postgre_table_dumps_large.zip, then run ./fetch.sh again.
EOF
  fi
fi
if ! ls lsb-large/livesqlbench_large_v1_gt_kg_testcases_*.jsonl >/dev/null 2>&1; then
  missing=1
  cat <<'EOF'

TO DO (a person): the answer SQL for LiveSQLBench is not public. Email the BIRD team at bird.bench25@gmail.com
as https://github.com/bird-bench/livesqlbench describes, and save the file they send
(livesqlbench_large_v1_gt_kg_testcases_<date>.jsonl) in datasets/text-to-sql/downloads/lsb-large/.
Do not commit it or share it: the BIRD team keeps it private so the benchmark stays out of training data.
EOF
fi
[[ $missing -eq 0 ]] && echo "All downloads present." || echo "The bird and novel sets can be built now. lsb, fleet and learn need the files above."
