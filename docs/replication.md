# Replicating the published LoCoMo scores

Everything a run needs to reproduce the published LoCoMo numbers, in order: the Meko stack and its settings, the patches its build needs, the harness settings, and the commands. Set the stack up first. The harness cannot see most of these settings, and a stack left at its defaults runs without errors and scores lower.

## Target scores

At retrieval depth k = 25. J, F1 and BLEU-1 are pooled over the 1,540 questions in categories 1–4; abstention is the share of the 446 adversarial questions (category 5) that the model declines to answer.

| Run | Protocol | Context | J | F1 | BLEU-1 | Abstention |
|---|---|---|---|---|---|---|
| 1 | A | memories + verbatim turns | 85.4 | 59.6 | 52.6 | 68.8 |
| 2 | A | memories only | 72.2 | 48.2 | 42.3 | 78.5 |
| 3 | B | memories + verbatim turns | 92.7 | 22.8 | 13.0 | 60.5 |
| 4 | B | memories only | 83.7 | 19.2 | 11.2 | 78.9 |
| 5 | A | memories + verbatim turns; a fresh ingest repeating Run 1 | 85.8 | 59.7 | 52.7 | 70.4 |

- **Protocol A**: a reasoning prompt, then a compression prompt that cuts the answer to a short phrase, both on `gpt-5.6-terra`; a binary CORRECT/WRONG judge on `gpt-4.1`.
- **Protocol B**: Mem0's answer prompt on `gpt-4.1-mini`; Mem0's partial-credit judge on `gpt-4.1-mini`. Its answers are full sentences, which is why its F1 and BLEU-1 are low.

Run 1 scores J 84.2 / 85.4 / 85.7 at k = 10 / 25 / 50. Per category at k = 25 (single-hop / multi-hop / temporal / open-domain) it scores J 91.8 / 78.7 / 79.1 / 69.8 and F1 64.6 / 47.1 / 62.9 / 41.4. The reports are in `docs/runs/locomo/`: `full-twostep` is Run 1, `full` is Run 3 and `terra-recheck` is Run 5.

**How close to expect.** Two things vary between runs even on an identical stack: `gpt-5.6-terra` has no dated snapshot, and memory extraction is not deterministic. Run 5 repeated Run 1 end to end on the stack described here and landed +0.4 J (per category −0.2 / −1.4 / +2.8 / +4.2). Treat a pooled J within ±1.8 of 85.4, the 95% sampling interval over 1,540 questions, as a replication.

## 1. Configure the stack

Use a self-hosted Meko stack. Hosted Meko runs the product defaults, which cannot be changed there, and enforces per-account quotas.

| Component | Version |
|---|---|
| Meko MCP server | 3.1.0, with the backdating patch (section 2) |
| Meko memory engine | 2.0.14.4, with the backdating patches (section 2). It has to be the 2.0 line; 1.x extracts and searches differently |
| YugabyteDB | 2026.1.0.0 build 118, with the `vector` and `pg_dist_rag` extensions |
| Extraction model | OpenAI `gpt-5.6-terra` |
| Embedding model | OpenAI `text-embedding-3-small`, 1,536 dimensions |

Start from an empty database. `memory_search` slows down with everything else stored in the cluster, the harness gives each call 300 seconds, and a question whose calls time out is left out of the run.

### 1.1 Server settings

| Variable | Container | Value | Default |
|---|---|---|---|
| `LLM_PROVIDER` | `meko-mcp-server` | `openai` | `aws_bedrock` |
| `LLM_MODEL` | `meko-mcp-server` | `gpt-5.6-terra` | `gpt-4.1-nano-2025-04-14` (on OpenAI) |
| `EMBEDDER_PROVIDER` | `meko-mcp-server` | `openai` | `aws_bedrock` |
| `EMBEDDER_MODEL` | `meko-mcp-server` | `text-embedding-3-small` | `amazon.titan-embed-text-v2:0` (on Bedrock) |
| `MEMORY_SEARCH_MIN_SCORE` | `meko-mcp-server` | `0` | `0.2` |
| `CONVERSATION_HIT_DISTANCE` | `meko-mcp-server` | `2.0` | `0.35` |
| `PAT_RATE_LIMIT_PER_MIN` | `meko-api-server` | `600` | `60` |
| `PAT_RATE_LIMIT_BURST` | `meko-api-server` | `100` | `10` |

`MEMORY_SEARCH_MIN_SCORE=0` keeps every memory hit up to k. `CONVERSATION_HIT_DISTANCE=2.0` lets the verbatim-turn tier answer every question; at 0.35 it fires on about a fifth of them. The rate limits only affect speed.

Leave these at their defaults, and record them with any result:

| Variable | Value |
|---|---|
| `CONVERSATION_MATCH_TOP_K` | `3` |
| `CONVERSATION_MAX_THREAD_TURNS` | `50` |
| `CONVERSATION_CHUNK_SIZE` | `1024` |
| `CONVERSATION_CHUNK_OVERLAP` | `256` |
| `CONVERSATION_MIN_CHARS` | `40` |
| `RERANK_MODEL` | unset (`cross-encoder/ms-marco-MiniLM-L-6-v2`) |
| `ENABLE_ASYNC_MEMORY_EXTRACTION` | unset (memories are extracted inside each `conversation_add_message` call) |
| `MEKO_FREE_TIER_QUOTA_ENABLED` | unset |
| `MEM0_CREATE_TABLES` | `true` |

The verbatim-turn tier reranks its candidates with `RERANK_MODEL`, which the MCP server downloads from Hugging Face the first time it is used. If the model can't be loaded, the server logs `rerank failed` and keeps vector order, which selects different sessions. Let the server reach huggingface.co, or put the model in its Hugging Face cache beforehand.

### 1.2 Getting the settings into the containers

Meko's Docker Compose deployment (`scripts/local-deploy`) gives each container an explicit list of environment variables. The `LLM_*` and `EMBEDDER_*` settings are on the list, so set them in the deployment's `.env`:

```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.6-terra
EMBEDDER_PROVIDER=openai
EMBEDDER_MODEL=text-embedding-3-small
```

`MEMORY_SEARCH_MIN_SCORE`, `CONVERSATION_HIT_DISTANCE` and `PAT_RATE_LIMIT_*` are not on it, so in `.env` they have no effect. Put them in an override file next to `docker-compose.yml`, for example `docker-compose.eval.yml`:

```yaml
services:
  meko-mcp-server:
    environment:
      MEMORY_SEARCH_MIN_SCORE: "0"
      CONVERSATION_HIT_DISTANCE: "2.0"
  meko-api-server:
    environment:
      PAT_RATE_LIMIT_PER_MIN: "600"
      PAT_RATE_LIMIT_BURST: "100"
```

`start.sh` passes `-f docker-compose.yml` explicitly, so it never reads the override. Once the stack is up, recreate the two services with both files, from the local-deploy directory (on Linux, export `HOST_GATEWAY_IP` first, as the deployment's README describes):

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.eval.yml \
  up -d --no-deps --force-recreate meko-mcp-server meko-api-server
```

Running `start.sh` again recreates the containers without the override, so apply it again afterwards. Then check what the containers actually run:

```bash
docker exec meko-mcp-server env | grep -E '^(LLM_PROVIDER|LLM_MODEL|EMBEDDER_PROVIDER|EMBEDDER_MODEL|MEMORY_SEARCH_MIN_SCORE|CONVERSATION_HIT_DISTANCE)='
docker exec meko-api-server env | grep -E '^PAT_RATE_LIMIT_'
docker exec meko-mcp-server env | grep -E '^(CONVERSATION_(MATCH_TOP_K|MAX_THREAD_TURNS|CHUNK_SIZE|CHUNK_OVERLAP|MIN_CHARS)|RERANK_MODEL|ENABLE_ASYNC_MEMORY_EXTRACTION|MEKO_FREE_TIER_QUOTA_ENABLED)='
```

The first two print the values in the table above. The third must print nothing.

### 1.3 One-time database and account steps

1. **Register the conversation index's embedding contract.** Without it, `context_search` never searches conversations. Run this once against the stack's database:

   ```sql
   INSERT INTO dist_rag.vector_indexes (index_name, schema_name, index_creation_status, ai_provider, embedding_model_params)
   VALUES ('conversation_history_search', 'datapacks', 'INIT', 'OPENAI', '{"model": "text-embedding-3-small", "dimensions": 1536}')
   ON CONFLICT (index_name) DO NOTHING;
   ```

   Then restart the MCP server, which caches a missing row for 24 hours: `docker restart meko-mcp-server`.

2. **Check that nothing overrides the score floor at runtime.** A `memory_search_min_score` row in `meko_system.runtime_config` takes precedence over `MEMORY_SEARCH_MIN_SCORE`. This query must return no row (an error saying the table does not exist is also fine):

   ```sql
   SELECT config_value FROM meko_system.runtime_config WHERE config_key = 'memory_search_min_score';
   ```

3. **Move the harness account to the pro tier.** A free account can create 10 datapacks over its lifetime, and a replication creates 11 (the smoke test plus ten conversations):

   ```bash
   curl -X PATCH http://localhost:25433/api/v1/admin/users/<user_id>/tier \
     -H "X-Meko-Admin-Secret: <the API server's ADMIN_API_KEY>" \
     -H "X-Meko-Admin-Actor-Email: <your email>" \
     -H 'Content-Type: application/json' -d '{"tier": "pro"}'
   ```

4. **Plan to embed the stored turns yourself.** This YugabyteDB build stores each turn with an empty embedding and has no worker that fills it in. `embed_turns.py` does it after the ingest (section 4, step 3).

## 2. Apply the backdating patches

LoCoMo's conversations took place in 2023. A stock build stores every replayed turn, and every memory extracted from it, under the date of the ingest, so "last week" and "next month" resolve against the wrong year and temporal questions fail. The published runs used builds with backdating patches in two components. Apply them to both before ingesting:

- **Meko MCP server**: a replayed turn keeps the session date it was sent with (`metadata.session_date`) wherever it is stored, and returns it with the turn.
- **Meko memory engine**: memories added or updated from a turn carry that turn's date, and extraction resolves relative dates against it instead of the current date.

The smoke test (section 4, step 1) checks that new memories carry 2023 dates.

## 3. Configure the harness

Copy `.env.example` to `.env` at the repository root and set:

```bash
MEKO_MCP_URL=http://127.0.0.1:8000/mcp
MEKO_API_URL=http://127.0.0.1:25433/api/v1
MEKO_AGENT_ID=meko
MEKO_EMAIL=<the pro-tier account>
MEKO_PASSWORD=<its password>
OPENAI_API_KEY=<a key with access to gpt-5.6-terra, gpt-4.1 and gpt-4.1-mini>
MEKO_DB_URL=postgresql://yugabyte:yugabyte@<host YugabyteDB listens on>:5433/yugabyte
```

`MEKO_DB_URL` is read only by `embed_turns.py`.

Answers and judgments come from OpenAI, with these model ids:

| Role | Protocol A | Protocol B |
|---|---|---|
| Answer | `gpt-5.6-terra` (no dated snapshot exists) | `gpt-4.1-mini-2025-04-14` |
| Judge | `gpt-4.1-2025-04-14` | `gpt-4.1-mini-2025-04-14` |

The published runs requested `gpt-4.1` and `gpt-4.1-mini`, which were served as the snapshots above; passing the snapshot ids keeps them fixed.

The harness fixes the rest, so no flag is needed for it:

- The reasoning call is capped at 8,000 output tokens, and the compression call at 4,000 with low reasoning effort.
- `gpt-5.6-terra` gets no temperature; the `gpt-4.1` models get temperature 0. Protocol B's single call is capped at 800 tokens.
- The answer prompt's reference date is the date of the conversation's last session.
- Every search is read-only.

The scripts' own defaults are not the published setup: `retrieve.py` defaults to `--ks 10,50 --categories 1,2,3,4`, and `answer.py` to protocol B's judge. Pass every flag exactly as written in section 4.

Run each script directly (`./answer.py …`), so that `uv` builds its environment from the dependencies the script declares. The published F1 and BLEU-1 use unstemmed tokens: `score.py` applies Porter stemming only when `nltk` is importable, and these environments don't include it.

## 4. Run

From the repository root:

```bash
cp .env.example .env                 # then fill it in as in section 3
datasets/locomo/fetch.sh
shasum -a 256 datasets/locomo/locomo10/locomo10.json
# expect 79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4
cd benchmarks/locomo
```

Use a new run id for every replication and a separate one for the smoke test. Datapacks are named `locomo-<run>-<conversation>` and an existing one is reused, and the smoke test marks `conv-26` as done after three turns, so a full ingest under the same id would skip it.

1. **Smoke test.** It must end with `SMOKE PASS`.

   ```bash
   ./ingest.py --run smoke --smoke
   ```

2. **Ingest** the ten conversations: 272 sessions, 5,882 turns, one extraction call per turn. It is finished when it logs `10/10 conversations done`.

   ```bash
   ./ingest.py --run rep1
   ```

3. **Embed the stored turns**, then confirm none are left:

   ```bash
   ./embed_turns.py --run rep1
   ./embed_turns.py --run rep1 --dry-run      # expect: 0 turns without embeddings in 10 datapacks
   ```

4. **Retrieve** for all 1,986 questions:

   ```bash
   ./retrieve.py --run rep1 --ks 10,25,50 --categories 1,2,3,4,5
   ```

   The log must include these lines, and `runs/locomo/rep1/retrieve.json` must show `"failed": 0`:

   ```
   k=10   1986 questions · avg 10.0 hits · 0 with none
   k=25   1986 questions · avg 25.0 hits · 0 with none
   k=50   1986 questions · avg 50.0 hits · 0 with none
   conversation tier: avg 55.2 turns per question · 0 questions with none
   ```

   The turn average can move a little with a fresh ingest; Runs 1 and 5 both had 55.2. Fewer than k hits means `MEMORY_SEARCH_MIN_SCORE` is not 0 in effect (check the container and `runtime_config`). An average of 0 means the index contract or the turn embeddings are missing. Most questions with no turns means `CONVERSATION_HIT_DISTANCE` is not 2.0.

5. **Answer and judge** with protocol A (Runs 1 and 5):

   ```bash
   ./answer.py --run rep1 --prompt two-step --model gpt-5.6-terra --judge cognis --judge-model gpt-4.1-2025-04-14
   ```

   `runs/locomo/rep1/answer.json` lists the prompt hashes: `d3bc517c` (answer), `889303a1` (adversarial) and `dc670903` (judge).

6. **Score:**

   ```bash
   ./report.py --run rep1
   ./compare.py --run rep1
   ```

   `report.md` gives F1, BLEU-1 and J per category and depth. The pooled numbers in the target table weight the four categories by their question counts:

   ```bash
   python3 -c "import json,sys; s=json.load(open(sys.argv[1]))['by_k']['25']['f1_b1_j']; n=sum(v['n'] for v in s.values()); print({m: round(100*sum(v[m]*v['n'] for v in s.values())/n,1) for m in ('f1','b1','j')})" ../../runs/locomo/rep1/report.json
   ```

### Runs 2 to 4

They answer from Run 1's retrieval with different settings. Give each its own run directory holding a link to that retrieval:

```bash
for r in rep1-memories rep1-b rep1-b-memories; do
  mkdir -p ../../runs/locomo/$r && ln -s ../rep1/retrieval.jsonl ../../runs/locomo/$r/retrieval.jsonl
done

# Run 2: protocol A, memories only
./answer.py --run rep1-memories --memories-only --prompt two-step --model gpt-5.6-terra --judge cognis --judge-model gpt-4.1-2025-04-14
# Run 3: protocol B
./answer.py --run rep1-b --prompt mem0 --model gpt-4.1-mini-2025-04-14 --judge mem0 --judge-model gpt-4.1-mini-2025-04-14
# Run 4: protocol B, memories only
./answer.py --run rep1-b-memories --memories-only --prompt mem0 --model gpt-4.1-mini-2025-04-14 --judge mem0 --judge-model gpt-4.1-mini-2025-04-14

for r in rep1-memories rep1-b rep1-b-memories; do ./report.py --run $r; done
```

Protocol B's prompt hashes are `79c9f09b` (answer) and `d8b9db0c` (judge).

## 5. Record with any result

- The harness commit (`git rev-parse HEAD`).
- The Meko MCP server and memory engine versions, and that the backdating patches were applied.
- The output of the `docker exec … env` checks in section 1.2.
- The YugabyteDB version.
- `runs/locomo/<run>/run.json`, `retrieve.json`, `answer.json` and `report.md`.
