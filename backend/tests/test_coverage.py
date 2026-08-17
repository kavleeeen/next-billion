"""A page cap that says nothing is the defect 0015 removed from the points filter.

Deleting `points > 30` moved all the bounding onto the topic, but the topic does
not bound anything the fetcher cannot already exhaust: `ai` matches 14,860 Show
HN posts and we read 1,000. A partner has to be told, not left to assume they
saw everything.
"""
from __future__ import annotations

import pytest

from pipeline.sources import hackernews, yc
from pipeline.sources.coverage import Coverage
from pipeline.sync import SourceReport, SyncReport


class TestCoverage:
    def test_reading_everything_is_not_truncated(self):
        assert not Coverage(read=222, available=222).truncated

    def test_reading_less_is(self):
        assert Coverage(read=1000, available=14860).truncated

    def test_nothing_available_counts_as_complete(self):
        # An empty result is not a truncated one.
        assert not Coverage(read=0, available=0).truncated
        assert Coverage(read=0, available=0).share == 1.0

    def test_share_is_capped_at_one(self):
        # nbHits can lag the hits actually returned; never report 130%.
        assert Coverage(read=13, available=10).share == 1.0

    def test_a_complete_read_describes_nothing(self):
        assert Coverage.whole(50).describe("yc") == ""

    def test_a_cut_read_names_both_numbers(self):
        line = Coverage(read=1000, available=14860).describe("hn")
        assert "1,000" in line and "14,860" in line and "7%" in line
        assert "too broad" in line


class TestTheReportSaysSo:
    def _report(self, coverage):
        return SyncReport(
            sources=[SourceReport("hn", 1000, 900, 900, 0, coverage)],
            total_rows=900,
        )

    def test_a_full_read_says_nothing(self):
        assert self._report(Coverage.whole(222)).truncated == []
        assert "too broad" not in self._report(Coverage.whole(222)).render()

    def test_a_cut_read_reaches_the_rendered_output(self):
        rendered = self._report(Coverage(read=1000, available=14860)).render()
        assert "hn: topic too broad" in rendered
        assert "1,000 of 14,860" in rendered

    def test_the_line_sits_above_the_totals(self):
        # A partner reads the last lines; the warning must not be buried.
        lines = self._report(Coverage(read=1000, available=14860)).render().splitlines()
        warning = next(i for i, l in enumerate(lines) if "too broad" in l)
        total = next(i for i, l in enumerate(lines) if "companies in database" in l)
        assert warning < total


class TestPacing:
    """Both APIs are public and unauthenticated. A 0.2s spacing used to sit in
    _search and was deleted by the concurrency change; this is it restored."""

    @pytest.mark.parametrize("module", [hackernews, yc])
    def test_each_source_paces_itself(self, module):
        assert module.REQUESTS_PER_MINUTE > 0
        assert module.PACER is not None

    def test_the_two_sources_do_not_share_a_pacer(self):
        # Different providers, different limits. One pacer would couple them.
        assert hackernews.PACER is not yc.PACER

    def test_hacker_news_waits_between_pages(self, monkeypatch):
        waited: list[int] = []
        monkeypatch.setattr(hackernews.PACER, "wait", lambda n: waited.append(n) or 0.0)
        monkeypatch.setattr(hackernews, "get_json",
                            lambda url: {"hits": [], "nbHits": 0, "nbPages": 1})
        hackernews._search({"query": "x"}, None)
        assert waited == [hackernews.REQUESTS_PER_MINUTE]

    def test_yc_waits_on_every_page(self, monkeypatch):
        waited: list[int] = []
        monkeypatch.setattr(yc.PACER, "wait", lambda n: waited.append(n) or 0.0)
        monkeypatch.setattr(yc, "get_json", lambda url: {"companies": [], "totalPages": 1})
        yc._page("W25", 1, "agents")
        assert waited == [yc.REQUESTS_PER_MINUTE]
