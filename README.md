# meko-benchmarks

Open, reproducible benchmarks for [Meko](https://github.com/yugabyte) context and memory retrieval. Today: **LoCoMo**.
Licensed under Apache 2.0.

The harness replays the ten LoCoMo conversations into a Meko deployment, retrieves context for all 1,986 questions
(memories plus verbatim conversation turns), has an LLM answer from that context, and scores the answers with the
paper's token F1 / BLEU-1 and the Mem0 paper's LLM judge (J), so the numbers are comparable with published systems.

Scores and the runs behind them: [docs/results.md](docs/results.md). Pipeline, prompts and scoring: [docs/locomo.md](docs/locomo.md).

## Reproduce

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

## Layout

```
benchmarks/locomo/   the phases (ingest, embed_turns, retrieve, answer, report, compare) and the scorer
common/              Meko client, auth, context rendering, published comparison numbers
datasets/locomo/     fetch script (data not bundled)
docs/                pipeline docs, results, per-run reports
```

## Licensing

Code: Apache 2.0 ([LICENSE](LICENSE), [NOTICE](NOTICE)). The LoCoMo dataset is CC BY-NC 4.0 and is not part of this
repository. Competitor figures in `common/published.py` are quoted from their papers or self-reports, with sources.
