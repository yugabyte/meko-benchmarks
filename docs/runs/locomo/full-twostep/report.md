### Run full-twostep

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
| 10 | 65.1 | 47.0 | 64.9 | 38.6 | 68.6 | 62.0 | 94.3 | 71.8 | 77.6 | 38.3 | 83.2 |
| 25 | 64.6 | 47.1 | 62.9 | 41.4 | 68.8 | 61.7 | 94.9 | 74.9 | 81.7 | 41.1 | 85.1 |
| 50 | 65.2 | 48.1 | 64.7 | 37.6 | 66.4 | 61.6 | 95.8 | 78.1 | 83.6 | 44.1 | 86.8 |

### F1, BLEU-1 and judge accuracy by question type, per retrieval depth

| k | Single-hop F1 | Single-hop B1 | Single-hop J | Multi-hop F1 | Multi-hop B1 | Multi-hop J | Temporal F1 | Temporal B1 | Temporal J | Open-domain F1 | Open-domain B1 | Open-domain J |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 65.1 | 58.6 | 90.8 | 47.0 | 37.8 | 74.8 | 64.9 | 59.3 | 80.1 | 38.6 | 32.9 | 66.7 |
| 25 | 64.6 | 57.6 | 91.8 | 47.1 | 37.8 | 78.7 | 62.9 | 57.2 | 79.1 | 41.4 | 36.5 | 69.8 |
| 50 | 65.2 | 58.1 | 91.2 | 48.1 | 40.1 | 81.6 | 64.7 | 59.1 | 80.1 | 37.6 | 32.1 | 68.8 |

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
