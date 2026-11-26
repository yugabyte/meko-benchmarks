# Text-to-SQL results: run `published`

Each cell: execution accuracy, then in brackets the change in percentage points against the scenario's baseline (`*` where the paired exact McNemar test gives p < 0.05), then the list-price cost per question. `-` means the arm was not run for that model.

## Small novel database with random names (pollination contractor, 10 tables)

120 questions. Baseline: no context (tools only).

| Arm | Haiku | Sonnet | Opus |
|-|-|-|-|
| No context (tools only) | 25.8% · $0.0043 | 54.2% · $0.0511 | 74.2% · $0.0958 |
| Comments | 89.2% (+63.3*) · $0.0014 | 89.2% (+35.0*) · $0.0181 | 90.8% (+16.7*) · $0.0433 |
| Documentation file in the prompt | 96.7% (+70.8*) · $0.0010 | 99.2% (+45.0*) · $0.0134 | 100.0% (+25.8*) · $0.0283 |
| Meko search | 94.2% (+68.3*) · $0.0019 | 94.2% (+40.0*) · $0.0256 | 96.7% (+22.5*) · $0.0599 |

## BIRD Mini-Dev with cryptic names (11 databases)

487 questions. Baseline: no context (tools only).

| Arm | Haiku | Sonnet | Opus |
|-|-|-|-|
| No context (tools only) | 44.6% · $0.0019 | 60.2% · $0.0212 | 76.2% · $0.0465 |
| Documentation file in the prompt | 48.5% (+3.9*) · $0.0013 | 64.7% (+4.5*) · $0.0157 | 77.2% (+1.0) · $0.0327 |
| Meko search | 46.2% (+1.6) · $0.0027 | 60.6% (+0.4) · $0.0323 | 78.9% (+2.7*) · $0.0717 |

## LiveSQLBench-Large (about 1,000 columns per database)

327 questions. Baseline: no context (tools only).

| Arm | Haiku | Sonnet | Opus |
|-|-|-|-|
| No context (tools only) | 10.4% · $0.0036 | 15.6% · $0.0472 | 17.7% · $0.0993 |
| Documentation file in the prompt | 24.8% (+14.4*) · $0.0422 | 30.0% (+14.4*) · $0.1324 | 34.3% (+16.5*) · $0.2042 |
| Meko search | 20.2% (+9.8*) · $0.0076 | 24.5% (+8.9*) · $0.0912 | 28.1% (+10.4*) · $0.1992 |
| Shortened file (~55k tokens) | 23.9% (+13.5*) · $0.0058 | - | - |
| Shortened file (~35k tokens) | 20.2% (+9.8*) · $0.0054 | - | - |
| Shortened file (~35k tokens) + Meko search | 22.9% (+12.5*) · $0.0063 | - | - |

## Fleet of 32 databases behind one agent

200 questions. Baseline: no context (tools only).

| Arm | Haiku | Sonnet | Opus |
|-|-|-|-|
| No context (tools only) | 3.5% · $0.0019 | 17.5% · $0.0323 | 17.5% · $0.0601 |
| Comments | 13.0% (+9.5*) · $0.0037 | 31.0% (+13.5*) · $0.0473 | 38.5% (+21.0*) · $0.0932 |
| Index of databases and tables in the prompt | 25.5% (+22.0*) · $0.0042 | 36.5% (+19.0*) · $0.0503 | 45.5% (+28.0*) · $0.0969 |
| One file of every table with descriptions, keys and some columns (~150k tokens) | 19.0% (+15.5*) · $0.0492 | 34.5% (+17.0*) · $0.1731 | 44.5% (+27.0*) · $0.2283 |
| One file of every table with descriptions and keys (~80k tokens) | 22.5% (+19.0*) · $0.0344 | 35.0% (+17.5*) · $0.1325 | 42.5% (+25.0*) · $0.1664 |
| The ~80k-token file + Meko search | 32.5% (+29.0*) · $0.0441 | 42.5% (+25.0*) · $0.1409 | 51.0% (+33.5*) · $0.2459 |
| Meko search | 27.0% (+23.5*) · $0.0059 | 40.0% (+22.5*) · $0.0765 | 53.0% (+35.5*) · $0.1588 |

## Learning from corrections (LiveSQLBench, 11 databases, Sonnet)

216 questions. Baseline: no learning.

| Arm | Haiku | Sonnet | Opus |
|-|-|-|-|
| No learning | - | 14.8% · $0.0590 | - |
| Lessons file in the prompt | - | 19.4% (+4.6) · $0.0911 | - |
| Meko memory | - | 20.4% (+5.6*) · $0.0845 | - |
| Meko knowledge base | - | 17.6% (+2.8) · $0.0813 | - |
