#!/usr/bin/env bash
# Build one data set, from the downloads to documentation loaded into Meko, stopping at the first failure.
#
#   ./prepare.sh novel    the bundled invented database (no downloads needed)
#   ./prepare.sh bird     BIRD Mini-Dev, renamed to cryptic names (needs the Mini-Dev and BIRD dev downloads)
#   ./prepare.sh lsb      LiveSQLBench-Large (needs the dumps and the answer file from the BIRD team)
#   ./prepare.sh fleet    every bird and lsb database behind one agent (run bird and lsb first)
#
# Each step can be run again on its own: see docs/text-to-sql.md for what each script does.
# The learn scenario uses the lsb set and needs no extra step.
set -euo pipefail
cd "$(dirname "$0")"
SET=${1:?usage: ./prepare.sh novel|bird|lsb|fleet}
DL=../../datasets/text-to-sql/downloads
step() { echo; echo "== $*"; "$@"; }
meko() { step env T2S_SET="$1" ./meko_load.py setup && step env T2S_SET="$1" ./meko_load.py wait; }

case "$SET" in
  novel)
    step build/novel_db.py build
    step build/novel_questions.py build
    step build/novel_docs.py
    step env T2S_SET=novel ./verify_gold.py
    meko novel
    ;;
  bird)
    step build/bird_split.py "$DL/minidev/MINIDEV_postgresql/BIRD_dev.sql" "$DL/minidev/MINIDEV/dev_tables.json" "$DL/split"
    step build/bird_load.sh
    step env T2S_SET=bird-plain ./verify_gold.py
    step env T2S_SET=bird-plain build/build_profiles.py
    step env T2S_SET=bird build/bird_cryptic.py
    step env T2S_SET=bird build/bird_history.py
    step env T2S_SET=bird build/replay_history.py
    step env T2S_SET=bird build/build_profiles.py
    step env T2S_SET=bird build/digest_log.py
    step env T2S_SET=bird build/gen_comments.py
    step env T2S_SET=bird build/build_corpus.py
    meko bird
    ;;
  lsb)
    gt=$(ls "$DL"/lsb-large/livesqlbench_large_v1_gt_kg_testcases_*.jsonl 2>/dev/null | head -1 || true)
    [[ -n "$gt" ]] || { echo "No answer file in $DL/lsb-large/: see datasets/text-to-sql/README.md" >&2; exit 1; }
    step build/lsb_load.py
    step env T2S_SET=lsb build/lsb_prepare.py
    step env T2S_SET=lsb build/lsb_gold.py "$gt"
    step env T2S_SET=lsb ./verify_gold.py
    step env T2S_SET=lsb build/build_profiles.py
    step env T2S_SET=lsb build/build_corpus.py
    step env T2S_SET=lsb build/lsb_capped.py
    meko lsb
    ;;
  fleet)
    step env T2S_SET=fleet build/fleet_prepare.py
    step build/fleet_capped.py dump bird
    step build/fleet_capped.py dump lsb
    step build/fleet_capped.py build 150
    step build/fleet_capped.py build 80
    step env T2S_SET=fleet ./verify_gold.py
    meko fleet
    ;;
  *) echo "unknown set $SET" >&2; exit 2 ;;
esac
echo; echo "== $SET is ready"
