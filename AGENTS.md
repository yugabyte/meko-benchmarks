# Running the benchmarks (instructions for agents)

This repository has two benchmarks. Follow the part for the one you are asked to run:

- [LoCoMo](#locomo): long-conversation memory, scored with an LLM judge
- [Text-to-SQL](#text-to-sql): how much context about a database helps an agent write SQL against YugabyteDB

## LoCoMo

You are asked to run the LoCoMo benchmark against a Meko deployment and report what it scores. The whole
pipeline is one command, `benchmarks/locomo/run_all.py`. It stops at the first check that fails and says why.
This part tells you how to run it, what to do when it stops, and what you may and may not claim.

### Rules

- **Never read, print or copy `.env` or `common/.token`.** They hold the user's credentials. `preflight`
  checks that the settings exist and work without showing them. If a setting is missing, tell the user which
  key name to add; do not look for it elsewhere.
- **Report the number as measured.** Do not edit the harness, prompts, scorer or judge to change a score, and do
  not rerun until a number looks better. If a result is outside the target band, say so (see "What to report").
- **Delete only what you created.** `./ingest.py --run <name> --delete` removes a run's datapacks. Use it only
  on a run you started, and only if the user asks. Never delete datapacks you did not create.
- **Use a new `--run` name for every run** (for example `cloud-2026-11-16`). Each run ingests its own datapacks.
- Keep the ingest at 3 workers (`run_all.py` does). More workers made the cloud drop connections and answer 502.

### Before you start

1. `uv` is installed (`uv --version`).
2. `.env` exists at the repo root, copied from `.env.example` and filled in by the user. It needs
   `MEKO_MCP_URL`, `OPENAI_API_KEY`, and either `MEKO_USER_TOKEN` or `MEKO_EMAIL` + `MEKO_PASSWORD`.
3. The dataset is fetched: `datasets/locomo/fetch.sh` (it is CC BY-NC 4.0, so it is downloaded, not bundled).

### Run it

```bash
cd benchmarks/locomo
nohup ./run_all.py --run <name> > ../../runs/locomo/<name>.log 2>&1 &
```

Use `caffeinate -i` in front of `./run_all.py` on macOS so the machine does not sleep. The run takes about 40
minutes and the answer stage costs OpenAI money (about 8 million input tokens at k=25, plus the judge). Tell the
user that before you start the answer stage if they have not already agreed to it.

Follow progress with `tail -f runs/locomo/<name>.log` and `runs/locomo/<name>/pipeline.json` (each stage's
status). `./status.py --run <name>` gives a table per conversation.

The run is resumable. If it stops for any reason, run the same command again: finished stages are skipped and
ingest continues from the last turn it saved. Do not start it twice at once.

### The stages and what to do when one fails

| Stage | What it does | If it fails |
|---|---|---|
| `preflight` | `.env` keys exist, dataset present, OpenAI models available, Meko reachable, no leftover datapacks for this run name, and whether the server accepts the benchmark's conversation gate | Fix what it names. A missing key: ask the user. Leftover datapacks: use a new `--run` name. |
| `ingest` | Sends all 5,882 turns, one Meko conversation per session, one datapack per LoCoMo sample (10 datapacks, 272 conversations). Reruns itself after crashes | If it ends without finishing after 30 attempts, read the log and `state.json`; a persistent server error is for the user to take to the Meko team. |
| `verify-ingest` | Meko holds exactly the dataset's turn count in every session | More than expected = a turn was written twice; fewer = a write was lost. Do not continue: the result would not be valid. |
| `wait-index` | Waits until the cloud has embedded the turns (it embeds in the background after ingest) | If it times out, rerun `./run_all.py --run <name> --from wait-index` later. Never skip it: searching early gives a partial index and a much lower score. |
| `retrieve` | k=25 memories and verbatim conversation turns for all 1,986 questions | A failed search: rerun; it skips finished rows. |
| `verify-retrieve` | No failed searches, 1,986 rows, 25 memories per question, about 50 to 57 conversation turns per question | A low turn count means the conversation gate was not applied or the index is incomplete. Rerun from `wait-index`. |
| `answer` | Answers with `gpt-5.6-terra` (two-step prompt) and judges with `gpt-4.1-2025-04-14` | Rerun; it resumes. A model not available to the key is caught in `preflight`. |
| `report` | `report.md`, the comparison table, and `result.json` | Read the message; it names the missing piece. |

### What to report

`runs/locomo/<name>/result.json` has the pooled J (weighted by the question counts of the four judged
categories), J per category, the conversation gate used, and whether the result is inside the target band.
Give the user:

- the pooled J and the four per-category J values;
- the run date, the Meko URL (not any credential), and `conversation_gate`;
- `index_probes_missing` from `wait_index.json`: a few percent is normal on a finished index, because some
  turns are not returned by a search for their own exact text;
- whether the result is inside the target band, and the number as measured either way.

The target is pooled J 85.4 ± 1.8 at k=25 (`docs/replication.md`, Run 1). That figure was measured on a
self-hosted stack with specific server settings. A cloud run can land outside it for reasons the harness cannot
control, and that is a measured result, not a failure of the run.

### Why two runs can differ

The benchmark gives the same procedure, not the same number. These vary between runs, and nothing in the
harness can fix them:

- `gpt-5.6-terra` has no dated snapshot, so the answer model can change.
- Memory extraction is not deterministic.
- The memory search applies the server's own relevance floor; this harness does not override it.
- The cloud's background embedding finishes at its own pace, which `wait-index` handles but cannot speed up.

`docs/replication.md` measured one end-to-end repeat of Run 1 at +0.4 J. Treat differences of about 2 points
pooled as ordinary variation, and do not claim a difference between two systems smaller than that.

### If the server has no conversation gate override

`preflight` prints `gate override: NOT supported` when the server does not accept `conversation_hit_distance`.
The run still works, but the server's default gate (0.35) gives conversation context to only about one question
in five, so J is well below the target, and `result.json` says the result is not comparable. Say this plainly
when you report it. Do not work around it by editing the server or the harness.

### What the stages call (for debugging)

`run_all.py` calls the single-purpose scripts in `benchmarks/locomo/`: `preflight.py`, `ingest.py`,
`wait_index.py`, `retrieve.py`, `answer.py`, `report.py`, `compare.py`. Each has `--help`. Start with the
log and `pipeline.json` before running one by hand. `docs/locomo.md` describes the pipeline and scoring;
`docs/replication.md` describes the self-hosted stack the published numbers came from.

## Text-to-SQL

You are asked to run the text-to-SQL benchmark, or some of its scenarios, and report the results. Everything is
in `benchmarks/text-to-sql/`. Run each command from that folder. The method, arms and scoring are in
`docs/text-to-sql.md`, and the published results to compare with are in `docs/text-to-sql-results.md`.

### Rules

- **Never read, print or copy `.env` or `common/.token`:** `preflight.py` checks the settings without showing
  them. If one is missing, tell the user which key name to add.
- **Keep LiveSQLBench's answer SQL private:** The BIRD team sends it by email on request, so that it stays out
  of model training data. Never print it, paste it into a message, commit it or upload it anywhere, and treat
  everything built from it the same way: `datasets/text-to-sql/lsb/questions.json`, `fleet/questions.json` and
  `runs/text-to-sql/gold/`. Git ignores all of these. Don't change that.
- **Ask before you spend:** Tell the user the cost from the table below and get their agreement before you
  start a full scenario. Run the smoke test first.
- **Report the numbers as measured:** Don't edit the prompts, tools, documentation, scorer or answer cache to
  change a score, and don't rerun cells until a number looks better
- **Delete only what you created, and only if the user asks:** `meko_load.py delete` removes only the
  datapacks that it created itself, and `run.py --delete-stores` removes only one run's learning datapacks.
  Never delete datapacks you did not create.
- **Use a new `--run` name for each run:** Running the same command again resumes the run: finished cells are
  skipped. Don't start the same run twice at once.
- **Rebuild the answer cache on the day you run:** Five answer queries use the current date, so run
  `T2S_SET=<set> ./verify_gold.py` before a run that is not on the same day as `prepare.sh`

### What a person must do first

You cannot do these steps. If one is missing, stop and tell the user which one, with the text below.

1. **Install the tools:** [`uv`](https://docs.astral.sh/uv/), [Claude Code](https://claude.com/claude-code),
   `git`, and the PostgreSQL client `psql`.
2. **Give Claude Code an account to bill:** Log in by running `claude` once, or set `ANTHROPIC_API_KEY` in the
   environment. Every question is a Claude Code session billed to that account
3. **Start a YugabyteDB** that the `yugabyte` user can create databases and roles in. The published results
   used YugabyteDB 2026.1.2 in one container, with these flags:

   ```bash
   docker run -d --name t2s-yb -p 5433:5433 yugabytedb/yugabyte:2026.1.2.0-b0 \
     bin/yugabyted start --background=false \
     --tserver_flags="ysql_pg_conf_csv={yb_enable_cbo=on,pg_stat_statements.track=all,pg_stat_statements.max=10000}"
   ```

   The `lsb` and `fleet` scenarios load about 2.6 GB of dumps, so give it at least 20 GB of disk.
4. **Fill in `.env`** at the repository root, copied from `.env.example`: `YB_HOST`, `YB_PORT`, `YB_PASSWORD`
   if the `yugabyte` user has one, `MEKO_MCP_URL`, and either `MEKO_USER_TOKEN` or `MEKO_EMAIL` and
   `MEKO_PASSWORD`. A variable already set in the shell takes priority over `.env`, so check that the shell
   has no stale `MEKO_MCP_URL`.
5. **For `lsb`, `fleet` and `learn` only:** download the LiveSQLBench dumps from Google Drive, and request
   the answer file from the BIRD team by email. `datasets/text-to-sql/README.md` says how and where to save
   them. The `novel` and `bird` scenarios don't need them.

### Run it

1. Check the setup. Fix each `FAIL` line it prints before going on.

   ```bash
   ./preflight.py
   ```

2. Download the BIRD and public LiveSQLBench data (not needed for `novel`). It prints a `TO DO` for each file
   a person still has to provide.

   ```bash
   ../../datasets/text-to-sql/fetch.sh
   ```

3. Build the set. It runs the build steps in order and stops at the first failure. `fleet` needs `bird` and
   `lsb` first, and `learn` uses `lsb`.

   ```bash
   ./prepare.sh novel        # or bird, lsb, fleet
   ```

4. Check the scenario's data, answer cache and Meko datapacks:

   ```bash
   ./preflight.py --scenario novel
   ```

5. Run a smoke test on Haiku. Every line should end in `completed`, with no `FAILED` lines. Some questions are
   hard, so a score of 0 on three questions is not a fault.

   ```bash
   ./run.py --scenario novel --run novel-smoke --models haiku --limit 3
   ```

6. With the user's agreement on cost, run the scenario. It can take hours, so run it in the background and
   follow the log. Put `caffeinate -i` in front of it on macOS so the machine does not sleep.

   ```bash
   mkdir -p ../../runs/text-to-sql
   nohup ./run.py --scenario novel --run novel-2026-12-01 -j 6 > ../../runs/text-to-sql/novel-2026-12-01.log 2>&1 &
   ```

7. Write the report, which creates `runs/text-to-sql/<run>/report.md`, `results-long.csv` and `results-wide.csv`:

   ```bash
   ./report.py --run novel-2026-12-01
   ```

8. For `learn`, and only if the user asks, delete the run's learning datapacks with
   `./run.py --scenario learn --run <run> --delete-stores`. Delete a set's documentation datapacks with
   `T2S_SET=<set> ./meko_load.py delete`, also only if the user asks.

### Cost and time of a full scenario

List prices for all of a scenario's arms and models, from the published runs, at `-j 6`. Building the data
costs nothing except `prepare.sh bird`, which has Claude Sonnet write the BIRD comments (about $1).

| Scenario | Cells | Cost | Time | Build time |
|-|-|-|-|-|
| `novel` | 1,440 | about $41 | about 1 hour | minutes |
| `bird` | 5,844 | about $130 | about 5 hours | about 1 hour |
| `lsb` | 3,924 | about $280 | about 6 hours | several hours (loading the dumps) |
| `fleet` | 4,200 | about $370 | about 5 hours | about 1 hour after `bird` and `lsb`, mostly Meko indexing 1,277 cards |
| `learn` | 864 | about $70 | about 4 hours | none after `lsb` |

To run less, pass `--models`, `--arms` or `--limit`. For example, `--models haiku` runs the cheapest model only.

### When something fails

| Message | What to do |
|-|-|
| `FAIL` from `preflight.py` | Fix what the line names. A missing setting or download is for the user. |
| `MCP server(s) not connected` | A tool server did not start. Read `transcript.stderr.txt` in the cell's folder named in the message. It is usually the database or the Meko URL or token. Fix it and run the same command again: the cell left no record, so it reruns. |
| `usage limit` | The Claude account has reached its limit. The run stops starting new cells. Run the same command again when the limit resets. |
| `no result from claude` | Claude Code exited without an answer. Read the cell's `transcript.stderr.txt`, then run the same command again. |
| `FAIL` or `SLOW` from `verify_gold.py` | The database is missing data or under load. Rerun that set's `prepare.sh` step that loads it. |
| `documents still not indexed` from `meko_load.py wait` | Meko is still indexing. Run `T2S_SET=<set> ./meko_load.py wait` again later. Never start a search arm before indexing finishes, because the search would find only part of the documentation. |
| `No answer file` from `prepare.sh lsb` | The LiveSQLBench answer file is missing: a step for a person. |

### What to report

Give the user:

- The tables from `report.md`, and the run name and date
- The Claude Code version (`claude --version`), the Meko URL (never a credential) and the YugabyteDB version
  that `preflight.py` prints
- How many cells failed and were not rerun (`FAILED` lines in the log)
- A comparison with `docs/text-to-sql-results.md` for the same scenario and arm, as measured either way

### Why two runs can differ

The benchmark repeats the procedure, not the numbers. The model aliases (`claude-haiku-5-5` and so on) can
move to newer snapshots, sampling is not deterministic, Meko's ranking and indexing can change between
deployments, Claude Code's own agent loop changes between versions, and five answers depend on the date. Each
cell runs once, so differences of a few points are ordinary unless the McNemar test marks them (`*` in the
report).
