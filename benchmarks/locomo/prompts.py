"""Prompts copied verbatim from mem0's public LoCoMo suite so our numbers are comparable.
Source: github.com/mem0ai/memory-benchmarks, benchmarks/locomo/prompts.py (J-score method:
binary CORRECT/WRONG judge on categories 1-4)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from context import context_block, conversation_block, conversation_turns, human_date, memories_block  # noqa: F401,E402

MEM0_ANSWER = """You are answering a question using retrieved memories from past conversations. Follow these reasoning steps IN ORDER.

## Step 1: SCAN ALL MEMORIES
Read EVERY memory below from first to last. For each one that contains information relevant to the question, note it. Do NOT stop after finding the first relevant memory — important details are often scattered across many memories, including ones far down the list. Give equal weight to ALL memories regardless of position — a memory near the end is just as likely to contain the answer as one near the beginning. In these memories, "User" refers to the main person whose memories these are.

## Step 2: ENTITY VERIFICATION
Confirm each relevant memory is about the correct person/entity. If the question asks "What does Person A like?" and a memory says "Person B likes X", do NOT use that memory to answer about Person A. In two-person conversations, both speakers' actions are relevant — if the question asks about person A and a memory attributes an action to person B (the other speaker), that information is still valid evidence from their shared conversations, but always check the attribution is correct.

## Step 3: COMBINE AND CROSS-REFERENCE
- COMBINE facts from multiple memories about the same topic. If one memory says "won first place" and another says "performed a piece titled X," those describe the same event — connect them.
- For listing/counting questions, extract EVERY distinct item from ALL memories. A single memory may contain multiple items. Think about what CATEGORIES of answers the question could have, then re-scan specifically for each category.
- For counting questions ("how many times", "how many X"), enumerate each distinct instance explicitly with its date or context BEFORE giving a final count. Do not estimate — list them out, then count the list.
- DECOMPOSE complex sentences: "an immersive X with Y, enjoys Z" contains multiple distinct facts. Each could be the answer.
- Connect related facts across memories: if one says "nearby lake" and another says "Lake Tahoe is great for kayaking", the nearby lake IS Lake Tahoe. If one says "bought X in Paris", infer the country is France.

## Step 4: SELECT THE BEST ANSWER
- Do NOT assume the highest-ranked memory is correct. Multiple memories may describe different events for the same topic. Compare each candidate's relevance to the SPECIFIC question, not its retrieval score. A lower-ranked memory that directly answers the question beats a higher-ranked one that is only tangentially related.
- ALWAYS choose the MOST SPECIFIC detail available. A proper name, title, or number beats a generic description. Rate each candidate as HIGH specificity (name, title, number, specific activity) or LOW (generic description), and prefer HIGH.
- Report what someone actually DID, not what was offered or available to them. "Has not tried X yet" means X was NOT done — disqualify it. "Joined X" or "has done X" means it WAS done — prefer it.
- When multiple memories repeat the same generic fact, that repetition does NOT make it more correct than a single memory with a more specific answer.
- Photos depict what was IN the photo, not facts about someone's daily life. Prefer direct statements over photo descriptions for inferences.
- Re-read the question carefully before answering. If it asks "what aspect/type/kind", answer with the specific aspect. If it asks "what did they discover they both enjoy", answer with the specific thing, not the setting.

## Step 5: TEMPORAL GROUNDING
These conversations took place around {reference_date}. All events occurred in 2022-2024.
- Calculate time relative to this date, NOT today. Never output 2025 or 2026.
- Use dates explicitly stated in memory text. Do not invent or estimate dates.
- When a question asks what someone "shared" or "mentioned" on a date, that date is when they TALKED about it — look for events shortly BEFORE that date.
- For "how long" questions, find the start and end dates explicitly, then compute the duration. Do not guess.
- TEMPORAL DISAMBIGUATION: When you find MULTIPLE instances of similar events at different dates, enumerate them all with their dates before picking. If the question uses past tense + "the" → select the instance closest to (and before) the reference date. If future tense ("plans to", "going to") → select the earliest planned date. NEVER default to the first-mentioned or highest-scored instance — the DATE determines the answer.

## Step 6: INCLUSION CHECK (for lists and counts)
If you found items during reasoning that you're tempted to exclude from your answer — STOP. Include them unless you have STRONG evidence they are wrong. The most common mistake is finding relevant items but then dropping them due to overly strict filtering. More items is better than fewer when there is supporting evidence.
- For counting: after enumerating, re-verify each item. Check for duplicates (same event described differently) and ensure you haven't missed items from memories late in the list.
- The question assumes something happened. Find WHAT happened, don't say nothing happened.

## Step 7: COMMIT AND ANSWER
Give a direct, specific answer. NEVER say "not specified", "not mentioned", "no record", or "the memories don't say" — if ANY memory contains relevant information, give the best answer from available evidence. No hedging, no caveats. If the question asks for a list, include ALL items found. NEVER return an empty answer when relevant memories exist.
- NEVER generate specific names, titles, places, or dates that do not appear in any memory above. If no memory contains the specific detail the question asks for, answer with what the memories DO contain rather than guessing.
- For open-domain/opinion questions ("Would X do Y?", "Is X considered Z?"):
  * Follow the DIRECT causal reasoning in the memories. Do NOT construct elaborate counter-arguments.
  * "Would X still do Y without Z?" — If memories show X does Y BECAUSE of Z, then without Z, answer "likely no."
  * "Would X do Y again soon?" — If the most recent attempt involved a bad experience (accident, scare, trauma), answer "likely no." A recent negative experience outweighs historical positive patterns.
  * For trait questions ("Is X considered Z?"): weigh ALL evidence including symbolic/indirect references. If there is SOME but not strong evidence, answer with a qualified degree ("somewhat") rather than flat "no."

# Instructions

## Misc

1. Make reasonable deductions based on your memories. Memory shows store with a lot of working people -> store employs a lot of people
2. If a memory describes something recognizable (e.g., "romantic drama about memory and relationships"), you may name it (e.g., "Eternal Sunshine of the Spotless Mind").
3. Use domain knowledge to connect facts: a game exclusive to one platform implies ownership of that platform. An unnamed company deal can be linked to a previously expressed brand preference.

{memories}

Question: {question}

Work through Steps 1-7, then give your final answer after "ANSWER:".
"""

JUDGE_SYSTEM = "You are evaluating conversational AI memory recall. Return JSON only with the format requested."

MEM0_JUDGE = """Label the generated answer as CORRECT or WRONG.

## Rules
1. **PARTIAL CREDIT**: If the generated answer includes AT LEAST ONE correct item from the gold answer's list, mark CORRECT. Getting 1 out of 2, 2 out of 4, etc. is always acceptable. Only mark WRONG if NONE of the gold answer items appear.
2. **PARAPHRASES COUNT**: Same concept in different words is CORRECT. "Chocolate raspberry tart" = "chocolate cake with raspberries". "Shelter meal service" = "volunteering at a homeless shelter". Emotions and sentiments in the same positive/negative family count as paraphrases: "proud" = "fulfilled" = "accomplished"; "huge success" = "relieved" = "thrilled" (all express positive achievement). Judge semantic meaning, not exact wording.
3. **EXTRA DETAIL IS FINE**: A longer answer that includes the gold answer's key facts plus additional information is CORRECT. Never penalize for being more detailed or specific. If the generated answer adds extra descriptive details beyond the gold answer while still referencing the same core entity or concept, mark CORRECT.
4. **DATE TOLERANCE**: Dates within 14 days of each other are CORRECT. Durations within 50% are CORRECT (e.g., "5 months" matches "six months"; "19 days" matches "two weeks"). Relative dates ("few days before November") match specific dates in the same window. A specific date (e.g., "February 2020") that is consistent with a vague reference (e.g., "a few years ago" relative to 2023) is CORRECT. Converting "last year" to the actual year (e.g., "2022" when conversations are in 2023) is CORRECT.

5. **SEMANTIC OVERLAP**: Judge whether the generated answer addresses the same topic and captures the core idea of the gold answer. Different wording, phrasing, or level of detail should not result in WRONG if the underlying concept matches. For EMOTIONS and FEELINGS questions, answers expressing sentiments in the same valence (positive/negative) about the same event are CORRECT — do not require the exact same emotion word.
6. **SAME REFERENT**: If the generated answer mentions or references the same named entity, character, person, or concept as the gold answer, mark CORRECT — even if the generated answer provides a different physical description or includes additional details. The key question is: does the generated answer identify the same core entity? If yes, it is CORRECT.
7. **FOCUS ON KNOWLEDGE, NOT WORDING**: The goal is to assess whether the system recalled the right fact. Minor differences in specificity, phrasing, or scope should not result in WRONG. Only mark WRONG when the generated answer demonstrates a genuinely different or incorrect understanding.

## ONLY mark WRONG if:
- The generated answer contains ZERO correct items from the gold answer
- The answer addresses a completely different topic

## Question
Question: {question}
Gold answer: {answer}
Generated answer: {response}

Return JSON with "reasoning" (one sentence) and "label" (CORRECT or WRONG). Do NOT include both labels."""


JUDGES = {"mem0": ("mem0 judge prompt (MEM0_JUDGE)", lambda: MEM0_JUDGE),
          "cognis": ("Lyzr Cognis judge (COGNIS_JUDGE)", lambda: COGNIS_JUDGE),
          "strict": ("strict judge, no partial credit (STRICT_JUDGE)", lambda: STRICT_JUDGE)}


def judge_prompt(judge, question, gold, response):
    text = {"cognis": COGNIS_JUDGE, "strict": STRICT_JUDGE}.get(judge, MEM0_JUDGE)
    return text.format(question=question, answer=gold, response=response)


def fingerprints(style, judge="mem0"):
    """Name, source and a short hash of every prompt a run used, so `status.py` can show them
    and a later edit to a prompt is detectable against old runs."""
    import hashlib
    import json
    import score
    h = lambda text: hashlib.sha256(text.encode()).hexdigest()[:8]
    if style == "mem0":
        answer = ("mem0 answer prompt (MEM0_ANSWER)", "prompts.py", h(MEM0_ANSWER))
    elif style == "two-step":
        answer = ("mem0 answer prompt (MEM0_ANSWER), then the compression step (COMPRESS_PROMPT + FORMAT_RULES)",
                  "prompts.py", h(MEM0_ANSWER + COMPRESS_PROMPT + json.dumps(FORMAT_RULES, sort_keys=True)))
    else:
        answer = ("LoCoMo paper short-answer prompt (QA_PROMPT)", "score.py", h(score.QA_PROMPT))
    return {"answer": dict(zip(("name", "file", "sha"), answer)),
            "adversarial": {"name": "LoCoMo paper short-answer prompt + abstain hint", "file": "score.py",
                            "sha": h(score.QA_PROMPT + score.HINTS[5])},
            "judge": {"name": JUDGES[judge][0], "file": "prompts.py", "sha": h(JUDGES[judge][1]())}}


# Lyzr Cognis's published judge (arXiv 2604.19771, Appendix A.1), verbatim. Their paper
# calls it "adapted from Mem0's evaluation methodology": a deliberately generous CORRECT/WRONG
# grader that accepts any answer touching the same topic, and any equivalent date format.
# This is the prompt they publish for their own LoCoMo evaluation, so on LoCoMo it is theirs.
COGNIS_JUDGE = """Your task is to label an answer to a question as \'CORRECT\' or \'WRONG\'. You will be given the following data:
    (1) a question (posed by one user to another user),
    (2) a \'gold\' (ground truth) answer,
    (3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations. The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT.

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it\'s the same date.

Now it\'s time for the real question:
Question: {question}
Gold answer: {answer}
Generated answer: {response}

First, provide a short (one sentence) explanation of your reasoning, then finish with CORRECT or WRONG.
Do NOT include both CORRECT and WRONG in your response, or it will break the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label"."""


# Ours: the strict counterpart of the two graders above. No partial credit on lists, no date
# tolerance beyond the gold answer's own precision, no credit for hedged or more generic answers.
# Used to bound how much of a J score the judge's generosity is worth.
STRICT_JUDGE = """Label the generated answer as CORRECT or WRONG. Be strict: the generated answer must state the same fact as the gold answer, completely and unambiguously.

## Rules
1. NO PARTIAL CREDIT. If the gold answer lists several items, every item must be present in the generated answer. Missing any item is WRONG. Extra items that are not in the gold answer make it WRONG too.
2. NO HEDGING. An answer that offers several candidates, or says "either X or Y", is WRONG unless the gold answer is the only thing it asserts.
3. SAME SPECIFICITY. A more generic answer than the gold answer is WRONG ("a book" for "Becoming Nicole"; "a city in Italy" for "Rome"). A paraphrase that names the same specific entity, event or quantity is CORRECT.
4. EXACT DATES. A date must match the gold answer at the gold answer's precision: the same day when the gold gives a day, the same month when it gives a month, the same year when it gives a year. A relative expression is CORRECT only if it resolves to exactly that date. A duration must be the same number of units ("two weeks" is WRONG for "19 days"; "six months" is WRONG for "five months").
5. EXTRA DETAIL. Additional detail is allowed only when it is consistent with the gold answer; any additional claim that contradicts the gold answer makes it WRONG.
6. NO INFERENCE CREDIT. If the gold answer is a specific fact and the generated answer gives a related but different fact (the reason instead of the thing, the place instead of the event), it is WRONG.

## Question
Question: {question}
Gold answer: {answer}
Generated answer: {response}

Return JSON with "reasoning" (one sentence) and "label" (CORRECT or WRONG). Do NOT include both labels."""


# Second step of `--prompt two-step`. The model first reasons with MEM0_ANSWER above (that is where
# the accuracy comes from); this call then turns that reasoning into the short phrase the LoCoMo
# scorer compares with a three-to-six-word gold answer. The format rule is chosen by question type,
# which the official scorer also does (its temporal and adversarial hints in score.HINTS).
COMPRESS_PROMPT = """Below are a question about past conversations, the reasoning an assistant wrote while answering it from memories, and the memories and conversation turns it used.

Write the final answer as a short phrase, the way a person fills in a quiz blank.
- At most 6 words. No sentence, no explanation, do not repeat the question.
- Use the exact words from the memories or turns whenever possible.
- {format_rule}
- If the reasoning ends with a final answer, keep its meaning: shorten it, do not change it.

Question: {question}

Reasoning:
{reasoning}

Memories and turns:
{context}

Short answer:"""

FORMAT_RULES = {
    4: "Give the single most specific thing asked for: a name, title, number, place or activity.",
    1: "If the answer is several things, list them separated by commas, and nothing else.",
    2: "Answer with a date or a duration only, as precise as the evidence allows: like '7 May 2023', "
       "'May 2023', '2022' or 'two weeks'. Do not add what happened.",
    3: "Give one short phrase that names the answer. Do not justify it.",
}
