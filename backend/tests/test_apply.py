"""The override rules decide what a memo says. Each row of the robustness
table in docs/ANALYSIS-PLAN.md has a test here.

The rules may only lower a result, and they run in a fixed order. Both
properties are tested, because a rule that fires in the wrong place produces a
number that still looks reasonable.
"""
from __future__ import annotations

import pytest

from pipeline.evidence import Bundle, Item
from pipeline.scoring.apply import apply
from pipeline.scoring.thesis import MEETING, PASS, WATCH

FOUNDER = Item("founder-1", "founder", "https://yc/x", "A founder")
PROFILE = Item("profile", "profile", "https://yc/x", "A company")
STORY = Item("story-1", "story", "https://hn/1", "A launch")


def bundle(*, with_founder: bool = True) -> Bundle:
    items = [PROFILE, STORY] + ([FOUNDER] if with_founder else [])
    return Bundle(company_id=1, name="Acme", items=tuple(items))


def metric(score: int, *, cited: bool = True, tier: str | None = None) -> dict:
    body = {
        "score": score,
        "rationale": "because of the evidence",
        "claims": [{"text": "a specific claim", "evidence_id": "profile"}] if cited else [],
    }
    if tier:
        body["tier"] = tier
    return body


def payload(founder=80, traction=80, fit=80, why=80, defence=80, **kw) -> dict:
    return {
        "metrics": {
            "founder_signal": kw.get("founder_metric", metric(founder, tier="primary")),
            "traction": kw.get("traction_metric", metric(traction)),
            "thesis_fit": kw.get("fit_metric", metric(fit)),
            "why_now": metric(why),
            "defensibility": metric(defence),
        },
        "summary": "A summary.",
        "would_change_the_call": ["a named customer"],
        "not_found": ["usage numbers"],
    }


def run(body: dict, b: Bundle | None = None):
    return apply(body, b or bundle(), model="test-model", prompt_version="v1")


class TestWeightedSum:
    def test_all_eighty_gives_eighty(self):
        assert run(payload()).total == 80.0

    def test_weights_are_applied_per_metric(self):
        # 100*30 + 0*25 + 100*20 + 0*15 + 0*10, all over 100.
        result = run(payload(founder=100, traction=0, fit=100, why=0, defence=0))
        assert result.total == 50.0

    def test_contributions_sum_to_the_total(self):
        result = run(payload(founder=91, traction=64, fit=73, why=48, defence=22))
        assert round(sum(m.contribution for m in result.metrics), 1) == result.total

    @pytest.mark.parametrize("scores,expected", [
        ((100, 100, 100, 100, 100), MEETING),
        ((70, 70, 70, 70, 70), MEETING),
        ((60, 60, 60, 60, 60), WATCH),
        ((45, 45, 45, 45, 45), WATCH),
        ((40, 40, 40, 40, 40), PASS),
    ])
    def test_bands(self, scores, expected):
        assert run(payload(*scores)).verdict == expected


class TestRule3Uncited:
    def test_an_uncited_metric_is_limited_to_fifty(self):
        result = run(payload(founder_metric=metric(90, cited=False, tier="primary")))
        founder = result.metrics[0]
        assert (founder.raw, founder.score) == (90, 50)
        assert "rule 3" in founder.limits[0]

    def test_an_uncited_metric_below_the_limit_is_untouched(self):
        result = run(payload(founder_metric=metric(30, cited=False, tier="primary")))
        assert result.metrics[0].score == 30
        assert result.metrics[0].limits == ()

    def test_the_limit_changes_the_total(self):
        # 90 -> 50 on a 30% weight removes 12 points.
        full = run(payload(founder=90)).total
        capped = run(payload(founder_metric=metric(90, cited=False, tier="primary"))).total
        assert full - capped == 12.0


class TestFallbackTier:
    def test_fallback_is_limited_to_seventy_nine(self):
        result = run(payload(founder_metric=metric(95, tier="fallback")))
        assert result.metrics[0].score == 79
        assert "fallback" in result.metrics[0].limits[0]

    def test_primary_tier_may_exceed_it(self):
        assert run(payload(founder_metric=metric(95, tier="primary"))).metrics[0].score == 95

    def test_rule_3_runs_before_the_tier_limit(self):
        # Uncited and fallback: 50 is the lower of the two, and the tier limit
        # must not raise it back to 79.
        result = run(payload(founder_metric=metric(95, cited=False, tier="fallback")))
        assert result.metrics[0].score == 50


class TestRule1TractionFloor:
    def test_traction_below_the_floor_limits_the_total(self):
        result = run(payload(traction=20))
        assert result.total == 60.0
        assert "rule 1" in result.flags[0]

    def test_the_floor_does_not_raise_a_lower_total(self):
        result = run(payload(founder=10, traction=20, fit=10, why=10, defence=10))
        assert result.total < 60.0
        assert result.flags == ()

    def test_traction_at_the_floor_does_not_fire(self):
        assert run(payload(traction=25)).flags == ()


class TestRule2ThesisGate:
    def test_thesis_fit_below_the_gate_forces_pass(self):
        result = run(payload(fit=30))
        assert result.verdict == PASS
        assert "rule 2" in result.flags[0]

    def test_the_total_keeps_its_value(self):
        # The memo shows a high total next to a Pass, which is the point.
        result = run(payload(fit=30))
        assert result.total > 45
        assert result.verdict == PASS

    def test_thesis_fit_at_the_gate_does_not_fire(self):
        assert run(payload(fit=40)).verdict != PASS


class TestRule4NoFounderRecord:
    def test_no_founder_item_limits_the_verdict_to_watch(self):
        result = run(payload(), bundle(with_founder=False))
        assert result.total >= 70
        assert result.verdict == WATCH
        assert "rule 4" in result.flags[-1]

    def test_it_does_not_lower_a_pass(self):
        result = run(payload(founder=10, traction=10, fit=10, why=10, defence=10),
                     bundle(with_founder=False))
        assert result.verdict == PASS

    def test_a_founder_item_lets_a_meeting_through(self):
        assert run(payload()).verdict == MEETING

    def test_the_rule_reads_the_evidence_not_the_model(self):
        # The model claimed the primary tier. Without a founder item, nobody
        # has looked at the team, so the verdict is still limited.
        result = run(payload(founder_metric=metric(100, tier="primary")),
                     bundle(with_founder=False))
        assert result.verdict == WATCH


class TestDroppedClaims:
    def test_a_claim_citing_an_unknown_id_is_dropped(self):
        body = payload()
        body["metrics"]["traction"]["claims"] = [
            {"text": "raised a round", "evidence_id": "crunchbase-1"}
        ]
        result = run(body)
        traction = result.metrics[1]
        assert traction.claims == ()
        assert result.dropped_claims
        assert "crunchbase-1" in result.dropped_claims[0]

    def test_dropping_the_last_claim_triggers_rule_3(self):
        body = payload(traction=90)
        body["metrics"]["traction"]["claims"] = [
            {"text": "raised a round", "evidence_id": "nowhere"}
        ]
        result = run(body)
        assert result.metrics[1].score == 50
        assert "rule 3" in result.metrics[1].limits[0]

    def test_a_kept_claim_carries_its_source_url(self):
        claim = run(payload()).metrics[0].claims[0]
        assert claim.evidence_id == "profile"
        assert claim.source_url == "https://yc/x"


class TestSerialisation:
    def test_to_json_round_trips_through_json(self):
        import json
        body = json.loads(json.dumps(run(payload(traction=10)).to_json()))
        assert len(body["metrics"]) == 5
        assert body["flags"]
        assert body["metrics"][0]["contribution"] == 24.0
