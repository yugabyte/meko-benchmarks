# meko-benchmarks

Open, reproducible benchmarks for [Meko](https://github.com/yugabyte) context and memory retrieval. Today: **LoCoMo** and **text-to-SQL**.
Licensed under Apache 2.0.

The harness replays the ten LoCoMo conversations into a Meko deployment, retrieves context for all 1,986 questions
(memories plus verbatim conversation turns), has an LLM answer from that context, and scores the answers with the
paper's token F1 / BLEU-1 and the Mem0 paper's LLM judge (J), so the numbers are comparable with published systems.

Scores and the runs behind them: [docs/results.md](docs/results.md). Pipeline, prompts and scoring: [docs/locomo.md](docs/locomo.md).

## Run it with an agent (or one command)

Point a coding agent at this repo: [AGENTS.md](AGENTS.md) tells it how to run the benchmark, what to do when a
check fails, and what to report. With a filled-in `.env` (copy `.env.example`) and the dataset fetched, the whole
pipeline is one command that stops at the first failed gate:

```bash
datasets/locomo/fetch.sh
cd benchmarks/locomo && ./run_all.py --run my-run
```

## Reproduce

The steps below are what `run_all.py` chains, for running one phase at a time.

Requirements: [`uv`](https://docs.astral.sh/uv/), an OpenAI API key (answering and judging), and a Meko deployment
you can reach over MCP and REST.

```bash
git clone <this repo> && cd meko-benchmarks
cp .env.example .env                  # set MEKO_*_URL, a token or login, OPENAI_API_KEY, MEKO_DB_URL
datasets/locomo/fetch.sh              # LoCoMo is CC BY-NC 4.0, so it is downloaded, not bundled

cd benchmarks/locomo
./ingest.py      --run smoke --smoke  # 3 turns, checks the stored date is 2023; keep its run id separate
./ingest.py      --run r1             # phase 1
./embed_turns.py --run r1             # vectors for the stored turns
./retrieve.py    --run r1 --ks 10,25,50 --categories 1,2,3,4,5   # phase 2
./answer.py      --run r1 --prompt two-step --judge cognis --judge-model gpt-4.1-2025-04-14
./report.py      --run r1             # score tables
./compare.py     --run r1             # next to published systems
```

Each phase resumes from `runs/locomo/<run>/`. Every run ingests its own datapacks, so runs never share memories;
use a new run id for each run.
`./baseline.py` gives the no-Meko floor (naive RAG) and ceiling (full conversation in context).

## Server settings that affect the numbers

The published numbers need a self-hosted Meko stack with specific server settings and backdating patches.
[docs/replication.md](docs/replication.md) lists all of them with exact values, the scores to expect, and a check
after each step. Record yours alongside any result you publish.

## Text-to-SQL

How much an agent that writes SQL against YugabyteDB gains from context about the database, and how best to
deliver it: catalog comments, a documentation file in the prompt, or Meko search. Five scenarios, from one
invented database to 32 databases behind one agent, on Claude Haiku, Sonnet and Opus 5.5, scored by execution
accuracy. It uses the BIRD team's [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) and
[LiveSQLBench](https://github.com/bird-bench/livesqlbench), plus an invented database bundled here.

Results: [docs/text-to-sql-results.md](docs/text-to-sql-results.md). Method: [docs/text-to-sql.md](docs/text-to-sql.md).
Data, licences and citations: [datasets/text-to-sql/README.md](datasets/text-to-sql/README.md).

Requirements: `uv`, Claude Code (logged in, or `ANTHROPIC_API_KEY`), `psql`, a YugabyteDB you can create
databases in, and a Meko deployment. The `novel` scenario needs no downloads:

```bash
cp .env.example .env                  # set YB_*, MEKO_MCP_URL and a Meko token or login
cd benchmarks/text-to-sql
./preflight.py
./prepare.sh novel                    # load the database, cache the answers, load the documentation into Meko
./run.py --scenario novel --run my-run
./report.py --run my-run              # runs/text-to-sql/my-run/report.md
```

[AGENTS.md](AGENTS.md#text-to-sql) has every scenario's steps, what each costs, and the steps a person must do
first (two LiveSQLBench files can't be downloaded by a script).

## Layout

```
benchmarks/locomo/   the phases (ingest, embed_turns, retrieve, answer, report, compare) and the scorer
benchmarks/text-to-sql/  the runner, tool servers, scorer, report, and build/ (data preparation)
common/              Meko client, auth, context rendering, published comparison numbers
datasets/locomo/     fetch script (data not bundled)
datasets/text-to-sql/  fetch script (BIRD data not bundled) and the bundled novel database
docs/                pipeline docs, results, per-run reports
```

## Licensing

Code: Apache 2.0 ([LICENSE](LICENSE), [NOTICE](NOTICE)). The LoCoMo dataset is CC BY-NC 4.0 and is not part of this
repository. BIRD Mini-Dev and LiveSQLBench are CC BY-SA 4.0 and are not part of this repository either. The
text-to-SQL novel database is part of it, under Apache 2.0. Competitor figures in `common/published.py` are quoted from their papers or self-reports, with sources.
