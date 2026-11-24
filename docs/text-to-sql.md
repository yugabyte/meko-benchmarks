# Text-to-SQL benchmark

The benchmark asks how much an AI agent that writes SQL against YugabyteDB gains from being given context
about the database, and how that context is best delivered: as comments in the catalog, as a documentation
file in the prompt, or through Meko search. Each question is answered by an agent with database tools, and
its final query is executed and compared with the answer query's result.

Results: [text-to-sql-results.md](text-to-sql-results.md). Data sources, licences and citations:
[datasets/text-to-sql/README.md](../datasets/text-to-sql/README.md). Steps for running it: [AGENTS.md](../AGENTS.md#text-to-sql).

## Scenarios

| Scenario | Databases | Questions | Models | What it tests |
|-|-|-|-|-|
| `novel` | 1 invented database, 10 tables with random names, no foreign keys | 120 | Haiku, Sonnet, Opus | A database no model can have seen |
| `bird` | BIRD Mini-Dev's 11 databases, renamed to cryptic codes | 487 | Haiku, Sonnet, Opus | Small public databases with unhelpful names |
| `lsb` | LiveSQLBench-Large's 21 databases, about 1,000 columns each | 327 | Haiku, Sonnet, Opus | Large schemas with business terms that are defined only in documentation |
| `fleet` | All 32 `bird` and `lsb` databases behind one agent | 200 (100 from each) | Haiku, Sonnet, Opus | Finding the right database before the right table |
| `learn` | 11 LiveSQLBench databases | 216 | Sonnet | Learning from a user's corrections, with no documentation up front |

Question counts exclude questions whose answer is empty or all NULL, because any empty answer would match.

## Arms

Every arm has the same three database tools, `list_tables`, `describe_table` and `run_sql` (in `fleet`, each
takes a database name and `list_databases` is added). The arms differ only in the context the agent gets.

| Arm | Context |
|-|-|
| A0 | None. The tools hide catalog comments |
| A1 | Comments on every table and column, shown by `list_tables` and `describe_table` |
| A3 | The database's documentation in the system prompt (`fleet`: an index of databases and tables, because the documentation for all 32 databases is about 2.1 million tokens) |
| A4t | A `search_context` tool that searches the same documentation in a Meko knowledge base, one datapack per database (one for the whole fleet) |
| A3c-55, A3c-35 | `lsb`, Haiku only: the documentation shortened to about 55,000 or 35,000 tokens, so that a Haiku request stays under its 100,000-token price step |
| A3c-35+M | The 35,000-token file plus Meko search over the full documentation |
| A3f-150, A3f-80 | `fleet`: one file listing every table of every database with its description and keys, plus up to 10 column names (about 150,000 tokens) or none (about 80,000 tokens) |
| A3f-80+M | The 80,000-token fleet file plus Meko search |
| L-S | `learn`: comments only, no lessons |
| L-F | Lessons saved to a file that is put in the prompt |
| L-Mm | Lessons saved to and searched in Meko memory |
| L-Mk | Lessons saved as documents in a Meko knowledge base and searched there |

The documentation is the same content in every arm that uses it. It is one card per table, plus cards for
business terms where the set has them:

- **bird:** comments written by Claude Sonnet 5.5 from the schema, value profiles, sample rows and a query
  log (never from questions, evidence hints, answer SQL or BIRD's description files), value profiles from
  `pg_stats`, and a digest of the query log. The query log comes from replaying the answer SQL of the 1,036
  BIRD dev questions that are not in Mini-Dev.
- **lsb:** the column meanings and the business-term knowledge base that LiveSQLBench publishes, and value
  profiles
- **novel:** table cards with value profiles and usual joins, a glossary of business terms and example queries

## How a question is answered

Each cell is one question answered by one model in one arm, in its own headless Claude Code session
(`claude -p`):

- Models `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`, at `--effort medium`
- A short system prompt in place of Claude Code's own, and no built-in tools, user settings, hooks, plugins or
  `CLAUDE.md`. The session runs in an empty folder outside the repository
- At most 10 turns, 6 `run_sql` calls, 15 seconds per statement and 20 rows returned per statement
- The agent finishes with its query in a `sql` block. In `fleet`, it names the database in a comment on the
  first line, and a wrong or missing name scores zero

For `learn`, each database's questions run in order as one stream. After a wrong answer, the agent is told
the question's knowledge-base entries as a user would say them ("That's not right. Here is what we mean: …"),
never the answer, and saves lessons with its arm's store. Later questions in the stream can use them.

## Database

The published results used YugabyteDB 2026.1.2 on one node, with the cost-based optimiser on
(`yb_enable_cbo=on`) and `pg_stat_statements` tracking every statement (`track=all`, `max=10000`), which the
`bird` query history needs. LiveSQLBench databases are colocated, because about 1,100 tables with their
indexes as separate tablets exceed one node's tablet limit. [AGENTS.md](../AGENTS.md#what-a-person-must-do-first)
has the command that starts it.

## Scoring

- **Execution accuracy (EX):** the agent's query is executed (60-second limit) and its rows are compared with
  the answer query's rows as sets, as BIRD does. Numbers are compared after rounding to 4 decimal places, so
  `numeric` and `float` arithmetic agree. LiveSQLBench's per-task conditions tighten this where a task sets
  them: an ordered comparison, or rounding to fewer places
- **Significance:** each arm is paired with the scenario's baseline (A0, or L-S for `learn`) on the same
  questions, with an exact two-sided McNemar test. A `*` in the tables marks p < 0.05
- **Cost:** list price from the session's token usage: input, output, cache reads and 1-hour cache writes
  (twice the input price). Haiku's price for a request over 100,000 prompt tokens is five times the base
  price, and `run.py` applies that step per request. Prices are in `PRICES` in `run.py`. The `learn` arms
  include the correction turn's cost

## Limits

- Each cell runs once. With 120 to 487 questions, a difference of a few points between two arms is within
  the noise unless the McNemar test marks it.
- The `novel` documentation and questions were written by the same author, so the documentation covers
  what the questions need. Real documentation is less complete.
- Five answer queries use the current date (see the
  [data README](../datasets/text-to-sql/README.md#how-the-bird-data-is-changed)). Rebuild the answer cache on
  the day you run.
- Claude Code's own agent loop is part of every result. A different agent framework would give different
  numbers.
- Meko returns knowledge-base search results by its own relevance ranking, so the Meko arms measure Meko as
  it is configured on the deployment you test

## Scripts

All scripts are in `benchmarks/text-to-sql/` and run with `uv` (each lists its own dependencies). `T2S_SET`
selects the data set for the scripts that work on one.

| Script | What it does |
|-|-|
| `preflight.py` | Checks the tools, `.env`, the database, Meko and, with `--scenario`, that scenario's data |
| `prepare.sh <set>` | Runs a set's build steps in order, from the downloads to documentation indexed in Meko |
| `run.py` | Runs and scores a scenario's cells. It resumes, and `--limit`, `--qids`, `--arms` and `--models` select a subset |
| `report.py` | Writes `report.md` and two CSV files for a run |
| `verify_gold.py` | Executes every answer query and caches the result for scoring |
| `rescore.py` | Re-scores a run's saved queries against the current answer cache, without calling a model |
| `meko_load.py` | Loads the documentation into Meko, waits for indexing, and deletes the datapacks it created |
| `build/` | The build steps: loading dumps, renaming BIRD, profiles, query history, comments, documentation, the fleet and the shortened files |
