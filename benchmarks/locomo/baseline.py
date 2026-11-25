"""Reference harness without Meko: full-context and naive-RAG answers, official scoring.

  python3 baseline.py --mode fullcontext --conversations 0 --limit 20
  python3 baseline.py --mode rag --top-k 10 --dry-run

Useful as the ceiling (fullcontext) and floor (rag) that a memory system is measured against.
"""

import argparse
import json
from collections import Counter

import data
import score


def render(turn):
    line = f'{turn["speaker"]} said, "{turn["text"]}"'
    return line + (f" and shared {turn['blip_caption']}." if turn.get("blip_caption") else "")


class FullContext:
    """Upper bound: the whole conversation in the prompt."""

    def ingest(self, sample):
        self.ids, lines = [], []
        for _, date, turns in data.sessions(sample):
            lines.append(f"DATE: {date}\nCONVERSATION:")
            lines += [render(t) for t in turns]
            self.ids += [t["dia_id"] for t in turns]
        self.text = "\n".join(lines)

    def context(self, question, top_k):
        return self.text, self.ids


class NaiveRag:
    """TF-IDF over single turns. A floor, not a target."""

    def ingest(self, sample):
        self.docs = [{"id": t["dia_id"], "date": d, "text": render(t)} for _, d, ts in data.sessions(sample) for t in ts]
        self.vecs = [Counter(_tok(d["text"])) for d in self.docs]
        self.df = Counter(w for v in self.vecs for w in v)

    def context(self, question, top_k):
        q = Counter(_tok(question))
        scored = sorted(((sum(v[w] / (1 + self.df[w]) for w in q), d) for d, v in zip(self.docs, self.vecs)),
                        key=lambda x: -x[0])
        hits = [d for s, d in scored[:top_k] if s]
        return "\n".join(f"DATE: {h['date']}\n{h['text']}" for h in hits), [h["id"] for h in hits]


def _tok(s):
    return [score._stem(w) for w in score.normalize(s).split()]


def answer(prompt, model):
    from openai import OpenAI
    r = OpenAI().chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                         temperature=0, max_tokens=64)
    return r.choices[0].message.content.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="rag", choices=["fullcontext", "rag"])
    ap.add_argument("--conversations", default="all")
    ap.add_argument("--categories", default="1,2,3,4", help="5 = adversarial, off by default")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="baseline_results.json")
    args = ap.parse_args()

    dataset = data.load()
    idxs = range(len(dataset)) if args.conversations == "all" else [int(i) for i in args.conversations.split(",")]
    cats = {int(c) for c in args.categories.split(",")}
    system = FullContext() if args.mode == "fullcontext" else NaiveRag()

    rows = []
    for i in idxs:
        sample = dataset[i]
        system.ingest(sample)
        for qa in [q for q in sample["qa"] if q["category"] in cats][: args.limit]:
            ctx, ids = system.context(qa["question"], args.top_k)
            prompt = score.build_prompt(qa["question"], qa["category"], ctx)
            if args.dry_run:
                print("=" * 70, "\n", prompt[:1200])
                continue
            pred = answer(prompt, args.model)
            rows.append({"conv": sample["sample_id"], "question": qa["question"], "category": qa["category"],
                         "gold": qa.get("answer"), "prediction": pred, "f1": score.score(qa, pred),
                         "evidence_recall": score.evidence_recall(data.evidence_ids(qa), ids),
                         "context_chars": len(ctx)})
    if args.dry_run:
        return
    json.dump(rows, open(args.out, "w"), indent=2)

    print(f"\n{'category':<12}{'n':>5}{'F1':>8}{'recall':>8}")
    for cat in sorted(cats):
        sub = [r for r in rows if r["category"] == cat]
        rec = [r["evidence_recall"] for r in sub if r["evidence_recall"] is not None]
        if sub:
            print(f"{data.CATEGORIES[cat]:<12}{len(sub):>5}{sum(r['f1'] for r in sub) / len(sub):>8.3f}"
                  f"{(sum(rec) / len(rec) if rec else float('nan')):>8.3f}")
    print(f"{'overall':<12}{len(rows):>5}{sum(r['f1'] for r in rows) / len(rows):>8.3f}")


if __name__ == "__main__":
    main()
