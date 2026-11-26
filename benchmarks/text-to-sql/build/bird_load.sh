#!/usr/bin/env bash
# Load the split BIRD Mini-Dev databases into YugabyteDB, one database each, then ANALYZE.
# Usage: ./bird_load.sh [db ...]   (default: every file in $SPLIT_DIR)
# Env: YB_HOST (localhost), YB_PORT (5433), YB_PASSWORD (the yugabyte user's), PARALLEL (3);
#      read from the repo-root .env when it is there.
set -euo pipefail
DL="$(cd "$(dirname "$0")/../../../datasets/text-to-sql" && pwd)/downloads"
ENV_FILE="$(dirname "$0")/../../../.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r k v; do
    [[ "$k" =~ ^(YB_HOST|YB_PORT|YB_PASSWORD)$ && -z "${!k:-}" ]] && export "$k=${v//[\"\']/}"
  done < <(grep -E '^(YB_HOST|YB_PORT|YB_PASSWORD)=' "$ENV_FILE")
fi
YB_HOST=${YB_HOST:-localhost}; YB_PORT=${YB_PORT:-5433}; export PGPASSWORD=${YB_PASSWORD:-}
SPLIT_DIR=${SPLIT_DIR:-$DL/split}; PARALLEL=${PARALLEL:-3}
LOG_DIR=${LOG_DIR:-$DL/load-logs}; mkdir -p "$LOG_DIR"
PSQL=(psql -h "$YB_HOST" -p "$YB_PORT" -U yugabyte -X -q)

"${PSQL[@]}" -d yugabyte -c "DO \$\$BEGIN CREATE ROLE t2s_agent LOGIN PASSWORD 't2s_agent'; EXCEPTION WHEN duplicate_object THEN NULL; END\$\$;"

load_one() {
  local db=$1
  local t0=$SECONDS
  "${PSQL[@]}" -d "$db" -f "$SPLIT_DIR/$db.sql" >"$LOG_DIR/$db.log" 2>&1 || true
  "${PSQL[@]}" -d "$db" -c "GRANT USAGE ON SCHEMA public TO t2s_agent" \
    -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO t2s_agent" \
    -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements" -c "ANALYZE" >>"$LOG_DIR/$db.log" 2>&1
  echo "$db loaded in $((SECONDS - t0))s, $(grep -c ERROR "$LOG_DIR/$db.log" || true) errors (log $LOG_DIR/$db.log)"
}
export -f load_one; export YB_HOST YB_PORT SPLIT_DIR LOG_DIR
export PSQL_CMD="${PSQL[*]}"

dbs=("$@"); [[ ${#dbs[@]} -gt 0 ]] || dbs=($(cd "$SPLIT_DIR" && ls *.sql | sed 's/\.sql$//'))
# YugabyteDB rejects concurrent CREATE DATABASE, so create them one at a time first.
for db in "${dbs[@]}"; do
  "${PSQL[@]}" -d yugabyte -c "DROP DATABASE IF EXISTS $db" -c "CREATE DATABASE $db" 2>&1 | grep -v 'does not exist, skipping' || true
done
# Bash arrays don't export, so rebuild PSQL inside each worker.
printf '%s\n' "${dbs[@]}" | xargs -P "$PARALLEL" -I{} bash -c 'PSQL=($PSQL_CMD); load_one {}'
