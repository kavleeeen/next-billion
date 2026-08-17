"""The validator stands between the model and every number in a memo.

The case that matters most is the invented citation: a well-formed reply that
cites an evidence id nobody supplied.
"""
from __future__ import annotations

import copy

import pytest

from pipeline.scoring import repair_message, validate
from pipeline.scoring.validate import Problem

EVIDENCE_IDS = {"yc-1", "hn-1", "hn-2", "founder-1"}


def _metric(score: int = 60, **extra) -> dict:
    return {
        "score": score,
        "rationale": "Two founders ran ingestion infrastructure at Palantir.",
        "claims": [{"text": "Both founders worked at Palantir", "evidence_id": "founder-1"}],
        **extra,
    }


def payload(**overrides) -> dict:
    base = {
        "metrics": {
            "founder_signal": _metric(82, tier="primary"),
            "traction": _metric(55),
            "thesis_fit": _metric(75),
            "why_now": _metric(60),
            "defensibility": _metric(30),
        },
        "summary": "Agent search infrastructure. Two ex-Palantir founders. No named users.",
        "would_change_the_call": ["A named customer on the site"],
        "not_found": ["No package downloads"],
    }
    base.update(overrides)
    return base


def paths(problems: list[Problem]) -> list[str]:
    return [problem.path for problem in problems]


class TestAccepts:
    def test_a_correct_reply_has_no_problems(self):
        assert validate(payload(), EVIDENCE_IDS) == []

    def test_empty_claims_is_allowed(self):
        # Rule 3 caps an uncited metric downstream. That is the intended
        # behaviour, so it must not be reported here.
        body = payload()
        body["metrics"]["defensibility"]["claims"] = []
        assert validate(body, EVIDENCE_IDS) == []

    def test_fallback_tier_at_the_cap_is_allowed(self):
        body = payload()
        body["metrics"]["founder_signal"] = _metric(79, tier="fallback")
        assert validate(body, EVIDENCE_IDS) == []

    def test_boundary_scores_are_allowed(self):
        body = payload()
        body["metrics"]["traction"]["score"] = 0
        body["metrics"]["why_now"]["score"] = 100
        assert validate(body, EVIDENCE_IDS) == []


class TestProvenance:
    def test_unknown_evidence_id_is_rejected(self):
        body = payload()
        body["metrics"]["traction"]["claims"] = [
            {"text": "Raised a seed round", "evidence_id": "crunchbase-9"}
        ]
        problems = validate(body, EVIDENCE_IDS)
        assert paths(problems) == ["metrics.traction.claims[0].evidence_id"]
        assert "crunchbase-9" in problems[0].message
        assert "not in the evidence" in problems[0].message

    def test_a_url_in_place_of_an_id_is_rejected(self):
        # The model citing a source URL rather than an id is the same failure:
        # the string was not supplied, so it cannot be checked.
        body = payload()
        body["metrics"]["traction"]["claims"] = [
            {"text": "Launched on HN", "evidence_id": "https://news.ycombinator.com/item?id=1"}
        ]
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.traction.claims[0].evidence_id"]

    def test_missing_evidence_id_is_rejected(self):
        body = payload()
        body["metrics"]["traction"]["claims"] = [{"text": "Launched on HN"}]
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.traction.claims[0].evidence_id"]

    def test_every_bad_claim_is_reported(self):
        body = payload()
        body["metrics"]["traction"]["claims"] = [
            {"text": "a", "evidence_id": "nope-1"},
            {"text": "b", "evidence_id": "hn-1"},
            {"text": "c", "evidence_id": "nope-2"},
        ]
        assert paths(validate(body, EVIDENCE_IDS)) == [
            "metrics.traction.claims[0].evidence_id",
            "metrics.traction.claims[2].evidence_id",
        ]


class TestScores:
    @pytest.mark.parametrize("score", [-1, 101, 1000])
    def test_out_of_range_is_rejected(self, score):
        body = payload()
        body["metrics"]["why_now"]["score"] = score
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.why_now.score"]

    @pytest.mark.parametrize("score", ["60", 60.5, None, True])
    def test_non_integer_is_rejected(self, score):
        body = payload()
        body["metrics"]["why_now"]["score"] = score
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.why_now.score"]

    def test_missing_rationale_is_rejected(self):
        body = payload()
        body["metrics"]["why_now"]["rationale"] = "   "
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.why_now.rationale"]


class TestTier:
    def test_missing_tier_is_rejected(self):
        body = payload()
        del body["metrics"]["founder_signal"]["tier"]
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.founder_signal.tier"]

    def test_unknown_tier_is_rejected(self):
        body = payload()
        body["metrics"]["founder_signal"]["tier"] = "secondary"
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.founder_signal.tier"]

    def test_fallback_above_the_cap_is_rejected(self):
        body = payload()
        body["metrics"]["founder_signal"] = _metric(85, tier="fallback")
        problems = validate(body, EVIDENCE_IDS)
        assert paths(problems) == ["metrics.founder_signal.score"]
        assert "79" in problems[0].message

    def test_other_metrics_may_omit_a_tier(self):
        assert validate(payload(), EVIDENCE_IDS) == []


class TestShape:
    def test_non_object_payload_is_rejected(self):
        assert paths(validate([1, 2], EVIDENCE_IDS)) == ["<root>"]

    def test_missing_metric_is_rejected(self):
        body = payload()
        del body["metrics"]["traction"]
        assert "metrics.traction" in paths(validate(body, EVIDENCE_IDS))

    def test_unknown_metric_is_rejected(self):
        body = payload()
        body["metrics"]["market_size"] = _metric()
        assert "metrics.market_size" in paths(validate(body, EVIDENCE_IDS))

    def test_missing_claims_list_is_rejected(self):
        body = payload()
        del body["metrics"]["traction"]["claims"]
        assert paths(validate(body, EVIDENCE_IDS)) == ["metrics.traction.claims"]

    @pytest.mark.parametrize("key", ["total", "verdict", "band"])
    def test_a_computed_field_is_rejected(self, key):
        # Python owns the arithmetic. A total in the reply means the model
        # ignored that instruction, so the rest of the reply is suspect too.
        assert key in paths(validate(payload(**{key: 71}), EVIDENCE_IDS))

    def test_missing_summary_is_rejected(self):
        assert "summary" in paths(validate(payload(summary=""), EVIDENCE_IDS))

    def test_not_found_must_be_a_list_of_strings(self):
        assert "not_found" in paths(validate(payload(not_found="none"), EVIDENCE_IDS))
        assert "not_found" in paths(validate(payload(not_found=[""]), EVIDENCE_IDS))

    def test_validate_does_not_mutate_its_input(self):
        body = payload()
        before = copy.deepcopy(body)
        validate(body, EVIDENCE_IDS)
        assert body == before


class TestRepairMessage:
    def test_opens_with_the_failure_sentence(self):
        problems = validate(payload(total=71), EVIDENCE_IDS)
        assert repair_message(problems).startswith(
            "The output JSON does not match the required format."
        )

    def test_names_every_problem(self):
        body = payload()
        body["metrics"]["traction"]["claims"] = [{"text": "x", "evidence_id": "ghost-1"}]
        body["metrics"]["why_now"]["score"] = 400
        message = repair_message(validate(body, EVIDENCE_IDS))
        assert "ghost-1" in message
        assert "metrics.why_now.score" in message
        assert "2 problem(s)" in message

    def test_refuses_to_run_on_a_valid_reply(self):
        with pytest.raises(ValueError):
            repair_message([])
