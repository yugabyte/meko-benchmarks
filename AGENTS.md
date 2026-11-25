# Running the LoCoMo benchmark against Meko (instructions for agents)

You are asked to run the LoCoMo benchmark against a Meko deployment and report what it scores. The whole
pipeline is one command, `benchmarks/locomo/run_all.py`. It stops at the first check that fails and says why.
This file tells you how to run it, what to do when it stops, and what you may and may not claim.

## Rules

- **Never read, print or copy `.env` or `common/.token`.** They hold the user's credentials. `preflight`
  checks that the settings exist and work without showing them. If a setting is missing, tell the user which
  key name to add; do not look for it elsewhere.
- **Report the number as measured.** Do not edit the harness, prompts, scorer or judge to change a score, and do
  not rerun until a number looks better. If a result is outside the target band, say so (see "What to report").
- **Delete only what you created.** `./ingest.py --run <name> --delete` removes a run's datapacks. Use it only
  on a run you started, and only if the user asks. Never delete datapacks you did not create.
- **Use a new `--run` name for every run** (for example `cloud-2026-11-16`). Each run ingests its own datapacks.
- Keep the ingest at 3 workers (`run_all.py` does). More workers made the cloud drop connections and answer 502.

## Before you start

1. `uv` is installed (`uv --version`).
2. `.env` exists at the repo root, copied from `.env.example` and filled in by the user. It needs
   `MEKO_MCP_URL`, `OPENAI_API_KEY`, and either `MEKO_USER_TOKEN` or `MEKO_EMAIL` + `MEKO_PASSWORD`.
3. The dataset is fetched: `datasets/locomo/fetch.sh` (it is CC BY-NC 4.0, so it is downloaded, not bundled).

## Run it

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

## The stages and what to do when one fails

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

## What to report

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

## Why two runs can differ

The benchmark gives the same procedure, not the same number. These vary between runs, and nothing in the
harness can fix them:

- `gpt-5.6-terra` has no dated snapshot, so the answer model can change.
- Memory extraction is not deterministic.
- The memory search applies the server's own relevance floor; this harness does not override it.
- The cloud's background embedding finishes at its own pace, which `wait-index` handles but cannot speed up.

`docs/replication.md` measured one end-to-end repeat of Run 1 at +0.4 J. Treat differences of about 2 points
pooled as ordinary variation, and do not claim a difference between two systems smaller than that.

## If the server has no conversation gate override

`preflight` prints `gate override: NOT supported` when the server does not accept `conversation_hit_distance`.
The run still works, but the server's default gate (0.35) gives conversation context to only about one question
in five, so J is well below the target, and `result.json` says the result is not comparable. Say this plainly
when you report it. Do not work around it by editing the server or the harness.

## What the stages call (for debugging)

`run_all.py` calls the single-purpose scripts in `benchmarks/locomo/`: `preflight.py`, `ingest.py`,
`wait_index.py`, `retrieve.py`, `answer.py`, `report.py`, `compare.py`. Each has `--help`. Start with the
log and `pipeline.json` before running one by hand. `docs/locomo.md` describes the pipeline and scoring;
`docs/replication.md` describes the self-hosted stack the published numbers came from.
