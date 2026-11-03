"""LoCoMo dataset access: one conversation in, chronological sessions out."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "datasets" / "locomo" / "locomo10" / "locomo10.json"
CATEGORIES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}

_EVIDENCE = re.compile(r"D:?(\d+):(\d+)")


def load(path=DATA):
    return json.loads(Path(path).read_text())


def sessions(sample):
    """[(number, date_text, turns)] oldest first.

    Keyed off the turn arrays, not the date keys: conv-26 carries 16 date keys
    for sessions that have no turns.
    """
    conv = sample["conversation"]
    nums = sorted(int(k.split("_")[1]) for k in conv if re.fullmatch(r"session_\d+", k))
    return [(n, conv[f"session_{n}_date_time"], conv[f"session_{n}"]) for n in nums]


def to_iso(date_text):
    """'1:56 pm on 8 May, 2023' -> '2023-05-08T13:56:00+00:00'.

    Meko only honours ISO-8601; anything else is silently stamped now().
    """
    parsed = datetime.strptime(date_text, "%I:%M %p on %d %B, %Y")
    return parsed.replace(tzinfo=timezone.utc).isoformat()


def turn_text(turn, images="caption"):
    """Speaker-attributed line, with the image caption folded in unless images='drop'."""
    text = f'{turn["speaker"]}: {turn["text"]}'
    if images == "caption" and turn.get("blip_caption"):
        text += f" [shared a photo: {turn['blip_caption']}]"
    return text


def evidence_ids(qa):
    """Normalised turn ids. Nine dataset entries are malformed ('D8:6; D9:17',
    'D:11:26', 'D30:05', a bare 'D'), so parse rather than compare strings."""
    return [f"D{int(s)}:{int(t)}" for item in qa.get("evidence") or [] for s, t in _EVIDENCE.findall(str(item))]
