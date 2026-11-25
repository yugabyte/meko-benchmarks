### Run full-twostep-53

| setting | value |
|---|---|
| benchmark | LoCoMo (locomo10.json) |
| questions | 1986 · Single-hop 841, Multi-hop 282, Temporal 321, Open-domain 96, Adversarial 446 |
| conversations | conv-26 19/19 sessions, conv-30 19/19 sessions, conv-41 32/32 sessions, conv-42 29/29 sessions, |
|  | conv-43 29/29 sessions, conv-44 28/28 sessions, conv-47 31/31 sessions, conv-48 30/30 sessions, |
|  | conv-49 25/25 sessions, conv-50 30/30 sessions |
| context | k memories + conversation turns (avg 55.2 turns per question, 0 with none) |
| retrieval depths | 10, 25, 50 |

### Answer accuracy (F1) and gold-in-context recall by question type, per retrieval depth

| k | F1 Single | F1 Multi | F1 Temporal | F1 Open | F1 Adversarial | F1 All | Gold in context Single | Gold in context Multi | Gold in context Temporal | Gold in context Open | Gold in context All |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 63.9 | 44.1 | 55.8 | 37.8 | 70.6 | 60.0 | 94.3 | 71.8 | 77.6 | 38.3 | 83.2 |
| 25 | 63.5 | 47.4 | 56.4 | 33.0 | 70.0 | 60.1 | 94.9 | 74.9 | 81.7 | 41.1 | 85.1 |
| 50 | 63.8 | 47.4 | 58.7 | 32.2 | 68.8 | 60.2 | 95.8 | 78.1 | 83.6 | 44.1 | 86.8 |

### F1, BLEU-1 and judge accuracy by question type, per retrieval depth

| k | Single-hop F1 | Single-hop B1 | Single-hop J | Multi-hop F1 | Multi-hop B1 | Multi-hop J | Temporal F1 | Temporal B1 | Temporal J | Open-domain F1 | Open-domain B1 | Open-domain J |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 63.9 | 58.1 | 88.5 | 44.1 | 34.9 | 74.8 | 55.8 | 49.1 | 72.3 | 37.8 | 33.3 | 71.9 |
| 25 | 63.5 | 57.5 | 88.7 | 47.4 | 36.8 | 78.0 | 56.4 | 50.3 | 74.5 | 33.0 | 28.2 | 71.9 |
| 50 | 63.8 | 57.6 | 89.7 | 47.4 | 37.4 | 79.8 | 58.7 | 52.5 | 75.1 | 32.2 | 27.4 | 71.9 |

### Session-level recall (R@k) by question type, per retrieval depth

| k | Single | Multi | Temporal | Open | Adversarial | All |
|---|---|---|---|---|---|---|
| 10 | 98.2 | 82.6 | 96.7 | 78.9 | 96.0 | 94.3 |
| 25 | 98.5 | 90.2 | 98.2 | 84.9 | 97.5 | 96.4 |
| 50 | 98.8 | 94.7 | 98.8 | 91.9 | 98.7 | 97.9 |

### How to read

| column | meaning |
|---|---|
| F1 | token overlap with the gold answer (the LoCoMo paper's scorer) |
| B1 | BLEU-1 |
| J | share judged correct by an LLM judge (mem0's protocol, lenient: one matching item suffices) |
| Adversarial | no gold answer: its F1 is an abstention rate, and it is excluded from J and gold in context |
| Gold in context | share of the gold answer's words found in the retrieved memories and turns |
| Session R@k | a retrieved memory or turn carries the evidence turn's session date; saturates once the context spans every session |
