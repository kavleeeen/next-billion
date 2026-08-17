"""The rubric, as numbers. THESIS.md is the document; this is the same rubric
in a form code can apply.

Nothing else in the pipeline hardcodes a weight, a cap or a band. The two can
still drift apart, so `test_thesis_constants.py` parses THESIS.md and asserts
every number here appears there.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str        # the JSON key the model returns
    label: str      # the wording in THESIS.md, matched by the drift test
    weight: int     # percent


# Declaration order is memo order, so a reader meets the metrics in the same
# sequence as the document.
METRICS: tuple[Metric, ...] = (
    Metric("founder_signal", "Founder signal", 30),
    Metric("traction", "Traction evidence", 25),
    Metric("thesis_fit", "Thesis fit", 20),
    Metric("why_now", "Why now", 15),
    Metric("defensibility", "Defensibility", 10),
)

METRIC_KEYS: tuple[str, ...] = tuple(m.key for m in METRICS)
WEIGHTS: dict[str, int] = {m.key: m.weight for m in METRICS}

SCORE_MIN, SCORE_MAX = 0, 100

# Rule 3. A metric nobody can source is worth no more than a coin toss.
UNCITED_CAP = 50

# Metric 1, fallback tier. The 80+ band asserts operating a system at scale,
# which a public technical record cannot establish.
FALLBACK_CAP = 79
TIERS = ("primary", "fallback")

# Rule 1. Traction below this floor holds the total down.
TRACTION_FLOOR = 25
TRACTION_FLOOR_TOTAL = 60

# Rule 2. Thesis fit below this gate forces the verdict, not the total.
THESIS_GATE = 40

MEETING = "Take a meeting"
WATCH = "Watch"
PASS = "Pass"

MEETING_MIN = 70
WATCH_MIN = 45


def band(total: float) -> str:
    """Verdict from a total, before rules 2 and 4 run."""
    if total >= MEETING_MIN:
        return MEETING
    if total >= WATCH_MIN:
        return WATCH
    return PASS
