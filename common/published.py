"""Published LoCoMo numbers we compare against, keyed the way this harness labels question types.

LoCoMo: the Mem0 paper (arXiv 2504.19413, Table 1) and the Cognis paper (arXiv 2604.19771, Table 4) print
category id 1 as "Single-Hop", id 3 as "Multi-Hop" and id 4 as "Open-Domain". The dataset ids, this harness
and Mem0's 2026 code have 4 = single-hop (841 questions), 1 = multi-hop (282), 3 = open-domain (96),
2 = temporal (321). Rows here are placed by id, so "Single-hop" is the same 841 questions for every system
Vendor pages are self-reports.
"""

LOCOMO_TYPES = ["Single-hop", "Multi-hop", "Open-domain", "Temporal"]
LOCOMO_N = {"Single-hop": 841, "Multi-hop": 282, "Open-domain": 96, "Temporal": 321}


def _paper(single_hop, multi_hop, open_domain, temporal):
    """A row as the papers print it (Single-Hop = id 1, Multi-Hop = id 3, Open-Domain = id 4), placed by id."""
    return {"Multi-hop": single_hop, "Open-domain": multi_hop, "Single-hop": open_domain, "Temporal": temporal}


MEM0_PAPER = "Mem0 paper, arXiv 2504.19413 Table 1 (gpt-4o-mini answers and judge, memories only)"
LOCOMO = {  # name -> meta + by[type] = (F1, B1, J); None where the source prints none
    "LoCoMo (no memory)": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "–", "context": "full conversation",
                           "by": _paper((25.02, 19.75, None), (12.04, 11.16, None), (40.36, 29.05, None), (18.41, 14.77, None))},
    "A-Mem": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "paper", "context": "memories",
              "by": _paper((20.76, 14.90, 39.79), (9.22, 8.81, 18.85), (33.34, 27.58, 54.05), (35.40, 31.08, 49.91))},
    "LangMem": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "paper", "context": "memories",
                "by": _paper((35.51, 26.86, 62.23), (26.04, 22.32, 47.92), (40.91, 33.63, 71.12), (30.75, 25.84, 23.43))},
    "Zep": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "paper", "context": "memories (graph)",
            "by": _paper((35.74, 23.30, 61.70), (19.37, 14.82, 41.35), (49.56, 38.92, 76.60), (42.00, 34.53, 49.31))},
    "OpenAI memory": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "paper", "context": "memories",
                      "by": _paper((34.30, 23.72, 63.79), (20.09, 15.42, 42.92), (39.31, 31.16, 62.29), (14.04, 11.25, 21.71))},
    "Mem0": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "paper", "context": "memories",
             "by": _paper((38.72, 27.13, 67.13), (28.64, 21.58, 51.15), (47.65, 38.72, 72.93), (48.93, 40.51, 55.51))},
    "Mem0 graph": {"source": MEM0_PAPER, "answer_model": "gpt-4o-mini", "judge": "paper", "context": "memories (graph)",
                   "by": _paper((38.09, 26.03, 65.71), (24.32, 18.82, 47.19), (49.27, 40.30, 75.71), (51.55, 40.28, 58.13))},
    "Lyzr Cognis": {"source": "Cognis paper, arXiv 2604.19771 Table 4 (\"GPT-4\" answers and judge, memories only)",
                    "answer_model": "GPT-4", "judge": "paper", "context": "memories",
                    "by": _paper((48.66, 35.76, 71.99), (31.51, 23.22, 51.04), (54.77, 45.12, 85.85), (62.68, 58.95, 77.26))},
    "Mem0 2026 platform": {"source": "mem0ai/memory-benchmarks README (self-report; J averaged over top-10..200; its code labels ids the harness way)",
                           "answer_model": "unstated (gpt-5 by code default)", "judge": "mem0 2026 lenient", "context": "memories",
                           "by": {"Single-hop": (None, None, 91.2), "Multi-hop": (None, None, 91.3), "Open-domain": (None, None, 72.7), "Temporal": (None, None, 92.0)}},
}
