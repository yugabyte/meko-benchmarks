"""Official LoCoMo QA scoring (ported from snap-research/locomo task_eval/evaluation.py) and the answer prompt."""

import math
import re
import string
import unicodedata
from collections import Counter

try:
    from nltk.stem import PorterStemmer
    _stem = PorterStemmer().stem
except Exception:
    _stem = lambda w: w  # scores drift slightly from the paper without stemming

QA_PROMPT = """{context}

Based on the above context, write an answer in the form of a short phrase for the following question. Answer with exact words from the context whenever possible.

Question: {question} Short answer:
"""
HINTS = {2: " Use DATE of CONVERSATION to answer with an approximate date.",
         5: " If no information is available to answer the question, write 'No information available'."}


def build_prompt(question, category, context):
    return QA_PROMPT.format(context=context, question=question + HINTS.get(category, ""))


_PUNCT = str.maketrans("", "", string.punctuation)
_ARTICLES = re.compile(r"\b(a|an|the|and)\b")


def normalize(s):
    s = unicodedata.normalize("NFD", str(s)).replace(",", "").lower().translate(_PUNCT)
    return " ".join(_ARTICLES.sub(" ", s).split())


def f1(prediction, gold):
    p, g = [_stem(w) for w in normalize(prediction).split()], [_stem(w) for w in normalize(gold).split()]
    same = sum((Counter(p) & Counter(g)).values())
    if not same:
        return 0.0
    precision, recall = same / len(p), same / len(g)
    return 2 * precision * recall / (precision + recall)


def bleu1(prediction, gold):
    """BLEU-1: unigram precision with the brevity penalty, no smoothing (the Mem0 paper's B1)."""
    p, g = normalize(prediction).split(), normalize(gold).split()
    if not p or not g:
        return 0.0
    overlap = sum((Counter(p) & Counter(g)).values())
    if not overlap:
        return 0.0
    brevity = 1.0 if len(p) >= len(g) else math.exp(1 - len(g) / len(p))
    return brevity * overlap / len(p)


def gold_text(qa):
    """Gold answer as the paper scores it: first ';' clause for open-domain."""
    gold = str(qa["answer"])
    return gold.split(";")[0].strip() if qa["category"] == 3 else gold


def score(qa, prediction):
    """Per-category rule: adversarial rewards abstaining; multi-hop averages
    over comma-separated gold parts; open-domain takes the first ';' clause."""
    cat = qa["category"]
    if cat == 5:
        low = prediction.lower()
        return 1.0 if "no information available" in low or "not mentioned" in low else 0.0
    gold = str(qa["answer"])
    if cat == 3:
        gold = gold.split(";")[0].strip()
    if cat == 1:
        preds, golds = [x.strip() for x in prediction.split(",")], [x.strip() for x in gold.split(",")]
        return sum(max(f1(p, g) for p in preds) for g in golds) / len(golds)
    return f1(prediction, gold)


def evidence_recall(wanted, retrieved):
    """Share of gold turn ids present in the retrieved ids; None when there is nothing to check."""
    if not wanted or retrieved is None:
        return None
    got = set(retrieved)
    return sum(1.0 for e in wanted if e in got) / len(wanted)
