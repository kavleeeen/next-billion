"""THESIS.md is the document a reader is given. `scoring/thesis.py` is what the
code applies. These tests fail if the two stop agreeing.

Without them the document becomes a description of what the pipeline used to
do, and nobody notices until a memo cites a weight that is no longer used.
"""
from __future__ import annotations

import re

import pytest

from pipeline.config import ROOT
from pipeline.scoring import thesis

DOC = (ROOT / "THESIS.md").read_text(encoding="utf-8")


class TestWeights:
    def test_table_matches_constants(self):
        rows = re.findall(r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(\d+)%\s*\|$", DOC, re.M)
        assert rows, "no weight table found in THESIS.md"
        assert [(label, int(weight)) for label, weight in rows] == [
            (m.label, m.weight) for m in thesis.METRICS
        ]

    def test_weights_sum_to_100(self):
        assert sum(thesis.WEIGHTS.values()) == 100

    def test_score_range_matches(self):
        low, high = re.search(r"score from (\d+) to (\d+)", DOC).groups()
        assert (int(low), int(high)) == (thesis.SCORE_MIN, thesis.SCORE_MAX)


class TestBands:
    def test_meeting_and_watch_thresholds(self):
        assert re.search(rf"^\|\s*{thesis.MEETING_MIN} or more\s*\|", DOC, re.M)
        assert re.search(rf"^\|\s*{thesis.WATCH_MIN} to \d+\s*\|", DOC, re.M)
        assert re.search(rf"^\|\s*Below {thesis.WATCH_MIN}\s*\|", DOC, re.M)

    @pytest.mark.parametrize(
        "total,expected",
        [(100, thesis.MEETING), (70, thesis.MEETING), (69.9, thesis.WATCH),
         (45, thesis.WATCH), (44.9, thesis.PASS), (0, thesis.PASS)],
    )
    def test_band_boundaries(self, total, expected):
        assert thesis.band(total) == expected


class TestOverrides:
    def test_rule_3_uncited_cap(self):
        assert int(re.search(r"maximum score of (\d+)", DOC).group(1)) == thesis.UNCITED_CAP

    def test_rule_1_traction_floor(self):
        floor, total = re.search(
            r"traction score below (\d+) limits the \*total\* to (\d+)", DOC
        ).groups()
        assert (int(floor), int(total)) == (thesis.TRACTION_FLOOR, thesis.TRACTION_FLOOR_TOTAL)

    def test_rule_2_thesis_gate(self):
        gate = re.search(r"thesis fit below (\d+) forces the \*verdict\*", DOC).group(1)
        assert int(gate) == thesis.THESIS_GATE

    def test_fallback_cap(self):
        assert int(re.search(r"\*\*up to (\d+)\*\*", DOC).group(1)) == thesis.FALLBACK_CAP

    def test_fallback_cannot_reach_the_top_band(self):
        # The document's justification only holds while the cap sits below 80.
        assert thesis.FALLBACK_CAP < 80
