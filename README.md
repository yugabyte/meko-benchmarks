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
cp .env.example .env                  # set MEKO_*_URL, a token or login, OPENAI_API_KEY
datasets/locomo/fetch.sh              # LoCoMo is CC BY-NC 4.0, so it is downloaded, not bundled

cd benchmarks/locomo
./ingest.py   --run r1 --smoke        # 3 turns, checks the stored date is 2023
./ingest.py   --run r1                # phase 1
./retrieve.py --run r1 --ks 10,25,50  # phase 2
./answer.py   --run r1 --prompt two-step
./report.py   --run r1                # score tables
./compare.py  --run r1                # next to published systems
```

Each phase resumes from `runs/locomo/<run>/`. Every run ingests its own datapacks, so runs never share memories.
`./baseline.py` gives the no-Meko floor (naive RAG) and ceiling (full conversation in context).

## Server settings that affect the numbers

The published runs used `text-embedding-3-small` embeddings, mem0 extraction, `MEMORY_SEARCH_MIN_SCORE=0` and
`CONVERSATION_HIT_DISTANCE=2.0` (keep every hit up to k). Record yours alongside any result you publish.

## Layout

```
benchmarks/locomo/   the five phases (ingest, retrieve, answer, report, compare) and the scorer
common/              Meko client, auth, context rendering, published comparison numbers
datasets/locomo/     fetch script (data not bundled)
docs/                pipeline docs, results, per-run reports
```

## Licensing

Code: Apache 2.0 ([LICENSE](LICENSE), [NOTICE](NOTICE)). The LoCoMo dataset is CC BY-NC 4.0 and is not part of this
repository. Competitor figures in `common/published.py` are quoted from their papers or self-reports, with sources.
