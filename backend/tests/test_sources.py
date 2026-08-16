"""Parsing tests. Each source is checked against a real response shape."""
from pipeline.sources import hackernews, yc

from .conftest import HN_PAYLOAD, YC_PAYLOAD


class TestYC:
    def _first(self):
        return yc._to_company(YC_PAYLOAD["companies"][0])

    def test_maps_core_fields(self):
        company = self._first()
        assert company.source == "yc"
        assert company.name == "Browser Use"
        assert company.batch == "W25"
        assert company.team_size == 4

    def test_uses_slug_as_key(self):
        assert self._first().source_key == "browser-use"

    def test_keeps_the_raw_record(self):
        assert self._first().raw["industries"] == ["B2B", "Engineering"]

    def test_every_record_is_usable(self):
        assert all(yc._to_company(r).is_usable for r in YC_PAYLOAD["companies"])


class TestHackerNews:
    def _companies(self):
        """Through parse(), not _to_company — parse() is what groups and attaches."""
        return hackernews.parse([HN_PAYLOAD])

    def test_extracts_name_and_batch_from_title(self):
        company = self._companies()[0]
        assert company.name == "Browser Use"
        assert company.batch == "W25"

    def test_uses_normalised_name_as_key(self):
        """Identity is the company, not the post — one company can launch twice."""
        assert self._companies()[0].source_key == "browser use"

    def test_attaches_the_story(self):
        company = self._companies()[0]
        assert [s.story_id for s in company.stories] == ["43173378"]
        assert company.stories[0].points == 259

    def test_text_post_without_url_is_still_usable(self):
        """The bug this guards: text posts are real companies (AgentMail, Onyx)."""
        company = self._companies()[1]
        assert company.name == "AgentMail"
        assert company.website is None
        assert company.is_usable

    def test_show_hn_has_no_batch(self):
        company = self._companies()[2]
        assert company.name == "Semble"
        assert company.batch is None

    def test_keeps_full_title_as_one_liner(self):
        assert self._companies()[0].one_liner.startswith("Launch HN:")
