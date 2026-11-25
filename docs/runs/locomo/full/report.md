### Run full

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
| 10 | 21.7 | 25.4 | 27.4 | 13.0 | 61.9 | 31.7 | 94.3 | 71.8 | 77.6 | 38.3 | 83.2 |
| 25 | 21.0 | 26.7 | 27.2 | 11.9 | 60.5 | 31.3 | 94.9 | 74.9 | 81.7 | 41.1 | 85.1 |
| 50 | 19.7 | 26.0 | 26.4 | 9.5 | 63.0 | 30.9 | 95.8 | 78.1 | 83.6 | 44.1 | 86.8 |

### F1, BLEU-1 and judge accuracy by question type, per retrieval depth

| k | Single-hop F1 | Single-hop B1 | Single-hop J | Multi-hop F1 | Multi-hop B1 | Multi-hop J | Temporal F1 | Temporal B1 | Temporal J | Open-domain F1 | Open-domain B1 | Open-domain J |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 21.7 | 13.4 | 94.1 | 25.4 | 10.9 | 93.3 | 27.4 | 17.8 | 92.2 | 13.0 | 9.1 | 70.8 |
| 25 | 21.0 | 12.9 | 94.6 | 26.7 | 10.0 | 92.6 | 27.2 | 17.6 | 91.9 | 11.9 | 8.0 | 79.2 |
| 50 | 19.7 | 12.1 | 93.3 | 26.0 | 9.6 | 93.3 | 26.4 | 17.0 | 93.5 | 9.5 | 6.5 | 71.9 |

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
