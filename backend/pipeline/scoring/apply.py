"""Turn a checked model reply into a total and a verdict.

Python does every calculation here. The model supplies five judgments and the
evidence behind them; it never sees a weight, a total or a band.

The rules run in the order THESIS.md fixes. Each one can only lower a result,
so the sequence is not an implementation detail: applying the traction floor
before the tier limit would give a different number.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..evidence import Bundle
from .thesis import (
    FALLBACK_CAP,
    MEETING,
    METRICS,
    PASS,
    THESIS_GATE,
    TRACTION_FLOOR,
    TRACTION_FLOOR_TOTAL,
    UNCITED_CAP,
    WATCH,
    band,
)

# Least to most positive. Rule 4 uses this to lower a verdict without needing
# to know which verdict it started from.
RANK = {PASS: 0, WATCH: 1, MEETING: 2}


@dataclass(frozen=True)
class Claim:
    text: str
    evidence_id: str
    source_url: str | None


@dataclass(frozen=True)
class MetricResult:
    key: str
    label: str
    weight: int
    raw: int                     # what the model returned
    score: int                   # after the limits
    rationale: str
    claims: tuple[Claim, ...]
    tier: str | None = None
    limits: tuple[str, ...] = () # which rules lowered this metric, and why

    @property
    def contribution(self) -> float:
        return self.score * self.weight / 100


@dataclass(frozen=True)
class Analysis:
    company_id: int
    name: str
    total: float
    verdict: str
    metrics: tuple[MetricResult, ...]
    summary: str
    would_change_the_call: tuple[str, ...]
    not_found: tuple[str, ...]
    model: str
    prompt_version: str
    # Every rule that changed a result, in the order it ran. The memo prints
    # these, so an override is visible instead of unexplained.
    flags: tuple[str, ...] = ()
    dropped_claims: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict:
        """What goes into analyses.scores_json."""
        return {
            "metrics": [
                {
                    "key": m.key,
                    "label": m.label,
                    "weight": m.weight,
                    "raw": m.raw,
                    "score": m.score,
                    "tier": m.tier,
                    "rationale": m.rationale,
                    "limits": list(m.limits),
                    "contribution": round(m.contribution, 2),
                    "claims": [
                        {"text": c.text, "evidence_id": c.evidence_id,
                         "source_url": c.source_url}
                        for c in m.claims
                    ],
                }
                for m in self.metrics
            ],
            "summary": self.summary,
            "would_change_the_call": list(self.would_change_the_call),
            "not_found": list(self.not_found),
            "flags": list(self.flags),
            "dropped_claims": list(self.dropped_claims),
        }


def _claims(raw_claims: list, bundle: Bundle) -> tuple[list[Claim], list[str]]:
    """Keep claims that cite a real item. Report the rest.

    A claim can only get here with an unknown id if the correction turn also
    failed, so dropping it is the last step of the provenance rule rather than
    a silent filter.
    """
    kept: list[Claim] = []
    dropped: list[str] = []

    for claim in raw_claims or []:
        evidence_id = (claim or {}).get("evidence_id", "")
        url = bundle.url_for(evidence_id)
        if url is None:
            dropped.append(f"{evidence_id!r}: {(claim or {}).get('text', '')[:80]}")
            continue
        kept.append(Claim(claim.get("text", ""), evidence_id, url))

    return kept, dropped


def apply(payload: dict, bundle: Bundle, *, model: str, prompt_version: str) -> Analysis:
    """The whole calculation. `payload` has already passed `validate`."""
    metrics: list[MetricResult] = []
    dropped_all: list[str] = []
    flags: list[str] = []

    for spec in METRICS:
        raw_metric = payload["metrics"][spec.key]
        raw_score = int(raw_metric["score"])
        score = raw_score
        limits: list[str] = []

        claims, dropped = _claims(raw_metric.get("claims"), bundle)
        dropped_all += dropped

        # Rule 3, per metric. An unsourced judgment is worth no more than a
        # coin toss, whatever the model wrote.
        if not claims and score > UNCITED_CAP:
            score = UNCITED_CAP
            limits.append(f"rule 3: no citation, limited to {UNCITED_CAP}")

        tier = raw_metric.get("tier") if spec.key == "founder_signal" else None
        if tier == "fallback" and score > FALLBACK_CAP:
            score = FALLBACK_CAP
            limits.append(f"fallback tier, limited to {FALLBACK_CAP}")

        metrics.append(MetricResult(
            key=spec.key, label=spec.label, weight=spec.weight,
            raw=raw_score, score=score, rationale=raw_metric.get("rationale", ""),
            claims=tuple(claims), tier=tier, limits=tuple(limits),
        ))

    by_key = {m.key: m for m in metrics}
    total = round(sum(m.contribution for m in metrics), 1)

    # Rule 1. A company nobody uses cannot reach a meeting on narrative alone.
    if by_key["traction"].score < TRACTION_FLOOR and total > TRACTION_FLOOR_TOTAL:
        total = float(TRACTION_FLOOR_TOTAL)
        flags.append(
            f"rule 1: traction {by_key['traction'].score} is below "
            f"{TRACTION_FLOOR}, total limited to {TRACTION_FLOOR_TOTAL}"
        )

    verdict = band(total)

    # Rule 2. Outside the thesis is a Pass however good the company is. The
    # total keeps its value so the memo can show both.
    if by_key["thesis_fit"].score < THESIS_GATE and verdict != PASS:
        verdict = PASS
        flags.append(
            f"rule 2: thesis fit {by_key['thesis_fit'].score} is below "
            f"{THESIS_GATE}, verdict forced to Pass"
        )

    # Rule 4. Read from the evidence, not from the model: if enrichment found
    # no founder, nobody has looked at the team.
    if not bundle.has("founder") and RANK[verdict] > RANK[WATCH]:
        verdict = WATCH
        flags.append("rule 4: no founder record, verdict limited to Watch")

    if dropped_all:
        flags.append(f"{len(dropped_all)} claim(s) dropped: citation not in the evidence")

    return Analysis(
        company_id=bundle.company_id,
        name=bundle.name,
        total=total,
        verdict=verdict,
        metrics=tuple(metrics),
        summary=payload.get("summary", ""),
        would_change_the_call=tuple(payload.get("would_change_the_call") or []),
        not_found=tuple(payload.get("not_found") or []),
        model=model,
        prompt_version=prompt_version,
        flags=tuple(flags),
        dropped_claims=tuple(dropped_all),
    )
