### Run locomo-terra-recheck

| setting | value |
|---|---|
| benchmark | LoCoMo (locomo10.json) |
| questions | 1986 · Single-hop 841, Multi-hop 282, Temporal 321, Open-domain 96, Adversarial 446 |
| conversations | conv-26 19/19 sessions, conv-30 19/19 sessions, conv-41 32/32 sessions, conv-42 29/29 sessions, |
|  | conv-43 29/29 sessions, conv-44 28/28 sessions, conv-47 31/31 sessions, conv-48 30/30 sessions, |
|  | conv-49 25/25 sessions, conv-50 30/30 sessions |
| context | k memories + conversation turns (avg 55.2 turns per question, 0 with none) |
| retrieval depths | 25 |

### Answer accuracy (F1) and gold-in-context recall by question type, per retrieval depth

| k | F1 Single | F1 Multi | F1 Temporal | F1 Open | F1 Adversarial | F1 All | Gold in context Single | Gold in context Multi | Gold in context Temporal | Gold in context Open | Gold in context All |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | 64.3 | 48.2 | 63.6 | 40.9 | 70.4 | 62.1 | 95.1 | 76.7 | 83.8 | 42.5 | 86.1 |

### F1, BLEU-1 and judge accuracy by question type, per retrieval depth

| k | Single-hop F1 | Single-hop B1 | Single-hop J | Multi-hop F1 | Multi-hop B1 | Multi-hop J | Temporal F1 | Temporal B1 | Temporal J | Open-domain F1 | Open-domain B1 | Open-domain J |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | 64.3 | 57.5 | 91.6 | 48.2 | 38.3 | 77.3 | 63.6 | 57.8 | 81.9 | 40.9 | 35.3 | 74.0 |

### Session-level recall (R@k) by question type, per retrieval depth

| k | Single | Multi | Temporal | Open | Adversarial | All |
|---|---|---|---|---|---|---|
| 25 | 99.0 | 92.0 | 97.5 | 86.4 | 98.4 | 97.1 |

### How to read

| column | meaning |
|---|---|
| F1 | token overlap with the gold answer (the LoCoMo paper's scorer) |
| B1 | BLEU-1 |
| J | share judged correct by an LLM judge (mem0's protocol, lenient: one matching item suffices) |
| Adversarial | no gold answer: its F1 is an abstention rate, and it is excluded from J and gold in context |
| Gold in context | share of the gold answer's words found in the retrieved memories and turns |
| Session R@k | a retrieved memory or turn carries the evidence turn's session date; saturates once the context spans every session |
