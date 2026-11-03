# LoCoMo results

As of 8 October 2026. Every number comes from a run directory named below; reports for the runs we keep are under [runs/locomo/](runs/locomo/).

10 conversations, 1,986 questions. Scored with the paper's token F1 and BLEU-1 against short gold answers, plus a judge (J): the Mem0 paper's CORRECT/WRONG grader, which Lyzr Cognis reprints, run on gpt-4.1.

All rows share one ingest and one retrieval (run `full`, 24 September 2026): k = 25 memories plus up to about 55 verbatim turns per question. Only the answer step differs.

| answer step | Single-hop (id 4) F1 / B1 / J | Multi-hop (id 1) | Temporal (id 2) | Open-domain (id 3) |
|---|---|---|---|---|
| two-step prompt, gpt-5.6-terra | 64.6 / 57.6 / 91.8 | 47.1 / 37.8 / 78.7 | 62.9 / 57.2 / 79.1 | 41.4 / 36.5 / 69.8 |
| two-step, gpt-5 | 64.3 / 57.2 / 90.0 | 46.7 / 38.2 / 78.4 | 64.2 / 58.6 / 79.4 | 38.6 / 33.4 / 68.8 |
| two-step, gpt-5.3-codex | 63.5 / 57.5 / 88.7 | 47.4 / 36.8 / 78.0 | 56.4 / 50.3 / 74.5 | 33.0 / 28.2 / 71.9 |
| two-step, gpt-4.1 | 60.8 / 54.5 / 89.8 | 49.4 / 36.1 / 84.0 | 60.0 / 53.5 / 81.0 | 29.5 / 25.2 / 67.7 |
| two-step, gpt-5-mini | 59.4 / 52.5 / 89.4 | 44.7 / 35.1 / 80.9 | 58.6 / 52.9 / 73.5 | 23.9 / 20.7 / 66.7 |
| two-step, gpt-4o | 58.5 / 51.9 / 88.0 | 45.4 / 34.2 / 77.0 | 59.3 / 53.0 / 77.3 | 29.0 / 24.7 / 62.5 |
| paper's short-answer prompt, gpt-5.6-terra | 64.5 / 58.6 / 92.0 | 40.7 / 34.8 / 75.9 | 53.5 / 44.6 / 90.3 | 26.0 / 21.9 / 64.6 |
| mem0's reasoning prompt, gpt-4.1-mini (first run) | 21.0 / 12.9 / 92.3 | 26.7 / 10.0 / 79.8 | 27.2 / 17.6 / 83.8 | 11.9 / 8.0 / 68.8 |
| Lyzr Cognis (their paper, GPT-4) | 54.8 / 45.1 / 85.9 | 48.7 / 35.8 / 72.0 | 62.7 / 59.0 / 77.3 | 31.5 / 23.2 / 51.0 |
| Mem0 (their paper, gpt-4o-mini) | 47.7 / 38.7 / 72.9 | 38.7 / 27.1 / 67.1 | 48.9 / 40.5 / 55.5 | 28.6 / 21.6 / 51.2 |

Category ids: the papers' column names and the dataset ids disagree. Cognis's Table 4 and the Mem0 paper's Table 1 print category 1 (282 questions) as Single-Hop, 3 (96) as Multi-Hop and 4 (841) as Open-Domain; this harness, Mem0's 2026 code and the data itself (96% of category-1 questions need more than one session, 0.1% of category 4) use 4 = single-hop, 1 = multi-hop, 3 = open-domain. Published rows are placed by category id, not by the papers' column names. Until 2026-10-12 these tables were keyed by name, which put three of four cells against the wrong question sets. 

Judge variants on the same answers (run `full-twostep`, re-judged on 2026-10-12 J over categories 1–4):

| judge | k=10 | k=25 | k=50 | per category at k=25 (SH / MH / TM / OD) | run |
|---|---|---|---|---|---|
| the paper's prompt on gpt-4.1 (the quoted rows) | 84.2 | 85.4 | 85.7 | 91.8 / 78.7 / 79.1 / 69.8 | `full-twostep` |
| the paper's prompt on gpt-4o-mini, the Mem0 paper's judge model | 81.5 | 82.3 | 83.9 | 89.4 / 74.8 / 76.9 / 59.4 | `full-twostep-judge-4omini` |
| strict prompt on gpt-4.1: every list item required, no vague dates, no credit for a less specific answer | 59.5 | 58.2 | 59.8 | 66.7 / 32.6 / 63.2 / 42.7 | `full-twostep-strict` |

The judge model alone moves J by 3 points (418 answers at k=25 go from CORRECT to WRONG under the strict prompt, none the other way). The strict prompt is an upper bound on strictness, not a protocol anyone publishes: it rejects "Rothfuss, Rowling, Martin, Coelho" for missing Tolkien, "last week" for "the week before 9 August 2023", and "March 2023" for "Friday before 13 March, 2023". Most of its losses are multi-hop lists (130 of 222 reference-correct answers) and single-hop answers that leave out a detail of the gold phrase.

What the table says, in order of importance:

- The first run scored F1 21 on single-hop because its answers were 24 words long against gold answers of four; 81% of the gold words were in there. The two-step prompt keeps mem0's reasoning and then compresses the answer to a few words in the context's own wording. That alone took single-hop F1 from 21 to 65. Nothing about the memories changed.
- Six answer models land within six F1 points of each other on single-hop. Against Cognis by category id, every model keeps the judge lead (single-hop 88.0 to 91.8 vs 85.9, multi-hop 77.0 to 84.0 vs 72.0, open-domain 62.5 to 71.9 vs 51.0), solid on single-hop and open-domain and within noise on multi-hop and temporal. The F1 lead is an answer-model effect: gpt-5.6-terra is +9.8 on single-hop, while gpt-4o, the model closest to Cognis's, trails Cognis on F1 for multi-hop, open-domain and temporal.
- The context is the larger lever: our model reads verbatim turns next to the memories, worth +12.6 J on a paired 820-question ablation, and the published systems answer from extracted memories alone. Memories-only Meko scores 70.9 J, the same band as the Mem0 paper.
- Judge scores from the first run under mem0's own lenient judge were higher (94.6 / 92.6 / 91.9 / 79.2). Every J above uses the stricter paper judge so the rows compare.

Runs:

| run | what |
|---|---|
| `full` | ingest and retrieval everything else reuses; first answers (mem0 prompt, gpt-4.1-mini) |
| `full-cj` | the first answers re-judged with the paper judge |
| `full-simple`, `full-twostep` | paper prompt and two-step prompt, gpt-5.6-terra |
| `full-twostep-53` | two-step, gpt-5.3-codex |
| `full-twostep-gpt5`, `-gpt5mini` | two-step, gpt-5 and gpt-5-mini |
| `full-twostep-gpt41`, `-gpt4o` | two-step, gpt-4.1 and gpt-4o |
| `full-terra` | a fresh end-to-end ingest on the current build; stopped at 9%, resumable |
