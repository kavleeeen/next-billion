"""A 402 from the people provider means the month's matches are gone.

Our own tally counts calls; the provider counts matches. The two disagreed in
a live run: the tally still showed headroom while the provider refused. Eight
more requests went out before anyone noticed, so the provider's refusal is now
treated as the authority.
"""
from __future__ import annotations

import pytest

from pipeline.enrich import pdl
from pipeline.http import FetchError


class _Settings:
    token = "test-key"
    token_env = "PDL_API_KEY"
    base_url = "https://api.peopledatalabs.com/v5/person/enrich"


def _raise(status):
    def fake(url, **kw):
        raise FetchError(f"HTTP {status} from {url}: refused", status=status)
    return fake


class TestFetchErrorCarriesStatus:
    def test_the_status_is_available(self):
        assert FetchError("boom", status=402).status == 402

    def test_it_is_optional(self):
        assert FetchError("boom").status is None


class TestEnrichPerson:
    def test_402_raises_account_exhausted(self, monkeypatch):
        monkeypatch.setattr(pdl, "get_json", _raise(402))
        with pytest.raises(pdl.AccountExhausted):
            pdl.enrich_person("ada", _Settings())

    @pytest.mark.parametrize("status", [404, 429, 500])
    def test_other_failures_are_still_just_a_miss(self, monkeypatch, status):
        # These are normal outcomes for one person, not a reason to stop.
        monkeypatch.setattr(pdl, "get_json", _raise(status))
        assert pdl.enrich_person("ada", _Settings()) is None

    def test_a_no_match_reply_is_not_exhaustion(self, monkeypatch):
        monkeypatch.setattr(pdl, "get_json", lambda url, **kw: {"status": 404})
        assert pdl.enrich_person("ada", _Settings()) is None


class TestSearchFounders:
    def test_402_raises_account_exhausted(self, monkeypatch):
        monkeypatch.setattr(pdl, "get_json", _raise(402))
        with pytest.raises(pdl.AccountExhausted):
            pdl.search_founders("acme.com", _Settings())

    @pytest.mark.parametrize("status", [404, 500])
    def test_other_failures_give_no_people(self, monkeypatch, status):
        monkeypatch.setattr(pdl, "get_json", _raise(status))
        assert pdl.search_founders("acme.com", _Settings()) == []


class TestReport:
    def _report(self, stopped):
        from pipeline.enrich import EnrichReport
        return EnrichReport(
            companies=3, skipped_existing=0, via_yc_page=1, via_pdl_search=0,
            founders_found=2, pdl_calls=2, pdl_matched=1, added=2, updated=0,
            stopped=stopped,
            total_founders=92, total_matched=81,
        )

    def test_exhaustion_is_explained_not_just_named(self):
        text = self._report("account_exhausted").render()
        assert "monthly matches" in text
        assert "fallback tier" in text
        assert "79" in text

    def test_a_clean_run_says_nothing_about_stopping(self):
        assert "stopped early" not in self._report(None).render()
