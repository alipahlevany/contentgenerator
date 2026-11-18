"""Frozen English CTA catalogue; saved templates rotate through it transactionally.

IDs are positions in this versioned list. Do not reorder an existing version:
that would cause repeats for installations partway through their rotation.
"""
import json
from pathlib import Path

BUTTON_BANK_VERSION = "english-v1"
BUTTON_LABELS = tuple(json.loads(
    (Path(__file__).parent / "data" / "warmup_button_labels_en_v1.json").read_text(encoding="utf-8")
))
BUTTON_LABEL_SET = frozenset(BUTTON_LABELS)
if len(BUTTON_LABELS) != 1000 or len({label.casefold() for label in BUTTON_LABELS}) != 1000:
    raise ValueError("The English button catalogue must contain exactly 1,000 unique labels.")
