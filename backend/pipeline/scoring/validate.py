"""Check a model's scoring reply before anything trusts it.

`responseSchema` already guarantees the *shape* of the JSON, so this exists for
what a schema cannot express: that every citation points at an evidence item we
actually supplied, that a score is inside its range, and that metric 1 declares
a tier it does not then contradict.

The provenance check is the reason this module exists. A model will invent a
plausible source without hesitation, and an invented citation is worse than a
missing one because it survives review.

Pure: no network, no database. `validate` reports; it never repairs. The caller
decides whether to ask the model again or to give up.
"""
from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from .thesis import FALLBACK_CAP, METRIC_KEYS, SCORE_MAX, SCORE_MIN, TIERS

# The model is told not to produce these; Python owns the arithmetic. Their
# presence means it ignored the instruction, so the whole reply is suspect.
FORBIDDEN_KEYS = ("total", "weighted_total", "verdict", "band", "call")

_LIST_FIELDS = ("would_change_the_call", "not_found")


@dataclass(frozen=True)
class Problem:
    path: str        # where it is, e.g. "metrics.traction.claims[1].evidence_id"
    message: str     # what is wrong, worded so the model can act on it

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def validate(payload: object, evidence_ids: Collection[str]) -> list[Problem]:
    """Every problem found, in reading order. An empty list means usable.

    evidence_ids is the set of ids handed to the model. Anything cited outside
    it was invented.
    """
    problems: list[Problem] = []

    if not isinstance(payload, dict):
        return [Problem("<root>", f"expected a JSON object, found {type(payload).__name__}")]

    for key in FORBIDDEN_KEYS:
        if key in payload:
            problems.append(Problem(key, "must not be present; the total and the verdict are computed outside this prompt"))

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        problems.append(Problem("metrics", "missing, or not a JSON object"))
    else:
        for key in METRIC_KEYS:
            if key not in metrics:
                problems.append(Problem(f"metrics.{key}", "missing; all five metrics are required"))
        for key in metrics:
            if key not in METRIC_KEYS:
                problems.append(Problem(f"metrics.{key}", f"unknown metric; expected only {', '.join(METRIC_KEYS)}"))
        for key in METRIC_KEYS:
            if key in metrics:
                problems += _check_metric(f"metrics.{key}", key, metrics[key], evidence_ids)

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append(Problem("summary", "missing or empty; two or three sentences are required"))

    for field in _LIST_FIELDS:
        value = payload.get(field)
        if not isinstance(value, list):
            problems.append(Problem(field, "missing, or not a JSON array"))
        elif any(not isinstance(item, str) or not item.strip() for item in value):
            problems.append(Problem(field, "every entry must be a non-empty string"))

    return problems


def _check_metric(
    path: str, key: str, metric: object, evidence_ids: Collection[str]
) -> list[Problem]:
    problems: list[Problem] = []

    if not isinstance(metric, dict):
        return [Problem(path, f"expected a JSON object, found {type(metric).__name__}")]

    score = metric.get("score")
    # bool is a subclass of int, so `True` would otherwise pass as score 1.
    if not isinstance(score, int) or isinstance(score, bool):
        problems.append(Problem(f"{path}.score", f"expected a whole number, found {score!r}"))
        score = None
    elif not SCORE_MIN <= score <= SCORE_MAX:
        problems.append(Problem(f"{path}.score", f"{score} is outside {SCORE_MIN}-{SCORE_MAX}"))

    rationale = metric.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        problems.append(Problem(f"{path}.rationale", "missing or empty"))

    problems += _check_tier(path, key, metric, score)

    claims = metric.get("claims")
    if not isinstance(claims, list):
        # An empty list is correct when the evidence supports nothing; rule 3
        # caps that metric downstream. A missing list is still an error.
        problems.append(Problem(f"{path}.claims", "missing, or not a JSON array; use [] when the evidence supports no claim"))
        return problems

    for index, claim in enumerate(claims):
        problems += _check_claim(f"{path}.claims[{index}]", claim, evidence_ids)

    return problems


def _check_tier(path: str, key: str, metric: dict, score: int | None) -> list[Problem]:
    """Metric 1 only. The tier decides the ceiling, so it cannot be omitted."""
    if key != "founder_signal":
        return []

    tier = metric.get("tier")
    if tier not in TIERS:
        return [Problem(f"{path}.tier", f"expected one of {', '.join(TIERS)}, found {tier!r}")]
    if tier == "fallback" and score is not None and score > FALLBACK_CAP:
        return [Problem(
            f"{path}.score",
            f"{score} exceeds {FALLBACK_CAP}, the ceiling for the fallback tier. "
            f"Either score at or below {FALLBACK_CAP}, or use the primary tier if prior roles support it.",
        )]
    return []


def _check_claim(path: str, claim: object, evidence_ids: Collection[str]) -> list[Problem]:
    if not isinstance(claim, dict):
        return [Problem(path, f"expected a JSON object, found {type(claim).__name__}")]

    problems: list[Problem] = []

    text = claim.get("text")
    if not isinstance(text, str) or not text.strip():
        problems.append(Problem(f"{path}.text", "missing or empty"))

    evidence_id = claim.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        problems.append(Problem(f"{path}.evidence_id", "missing or empty; every claim cites one evidence id"))
    elif evidence_id not in evidence_ids:
        # The invented-citation case. Named explicitly so the repair turn can
        # tell the model the id does not exist rather than that it is malformed.
        problems.append(Problem(
            f"{path}.evidence_id",
            f"{evidence_id!r} is not in the evidence. Cite an id that was supplied, or drop the claim.",
        ))

    return problems


def repair_message(problems: Sequence[Problem]) -> str:
    """The reply sent back to the model when validation fails.

    Names every problem at once. Sending them one at a time costs a round trip
    each and lets the model fix one thing while breaking another.
    """
    if not problems:
        raise ValueError("repair_message called with no problems")

    lines = [
        "The output JSON does not match the required format.",
        "",
        f"{len(problems)} problem(s) were found:",
    ]
    lines += [f"  - {problem}" for problem in problems]
    lines += [
        "",
        "Return the corrected JSON only. Keep every score you can still support, "
        "and do not invent evidence to satisfy a rule.",
    ]
    return "\n".join(lines)
