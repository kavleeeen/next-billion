"""The sentence a person reads lives with the rule it describes.

The freshness window belongs to the scoring stage. If the viewer built its own
sentence it would hold a second copy of the rule, free to disagree with the
first after a settings change.
"""
from __future__ import annotations

import pytest

from pipeline.score import ScoreReport


def report(**kw) -> ScoreReport:
    base = dict(companies=10, scored=0, reused=0, failed=0,
                problems_remaining=0, dropped_claims=0, refresh_hours=1.0)
    return ScoreReport(**{**base, **kw})


class TestNothingToDo:
    def test_everything_reused_says_so_plainly(self):
        message = report(scored=0, reused=10).message
        assert message.startswith("Nothing to score")
        assert "all 10" in message
        assert "the last hour" in message
        assert "reused" in message

    def test_one_company_reads_as_singular(self):
        message = report(companies=1, reused=1).message
        assert "all 1 selected company was" in message

    def test_the_window_follows_the_setting(self):
        # A changed refresh window must change the sentence, or the sentence
        # becomes a lie the next time someone edits config.
        assert "the last 6 hours" in report(reused=3, refresh_hours=6).message
        assert "the last 0.5 hours" in report(reused=3, refresh_hours=0.5).message


class TestWorkHappened:
    def test_scored_only(self):
        assert report(scored=4).message == "4 scored."

    def test_scored_and_reused(self):
        message = report(scored=4, reused=6).message
        assert "4 scored" in message
        assert "6 reused a score from the last hour" in message

    def test_a_failure_is_named(self):
        assert "2 failed" in report(scored=3, failed=2).message

    def test_dropped_claims_say_why(self):
        message = report(scored=3, dropped_claims=2).message
        assert "2 claim(s) dropped" in message
        assert "citation not in the evidence" in message

    @pytest.mark.parametrize("kw", [
        dict(scored=1), dict(reused=1), dict(scored=1, reused=1, failed=1),
    ])
    def test_the_sentence_ends_with_a_full_stop(self, kw):
        assert report(**kw).message.endswith(".")


class TestEdges:
    def test_an_empty_run_still_says_something(self):
        assert report(companies=0).message == "Nothing to do."

    def test_a_failure_alone_is_not_reported_as_nothing_to_score(self):
        # Every company failed and none was reused: that is not "nothing to do".
        message = report(scored=0, failed=3).message
        assert "Nothing to score" not in message
        assert "3 failed" in message

    def test_the_render_leads_with_the_message(self):
        assert report(reused=10).render().splitlines()[0].startswith("Nothing to score")
