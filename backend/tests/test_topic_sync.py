"""The topic decides what we collect.

The old rule kept Show HN posts above 30 points. Hacker News upvotes developer
tools, so that quietly collected a developer-tools corpus: 7 of 1224 companies
mentioned anything SMB-like, while Hacker News held hundreds. Points measure
what readers liked, not what a company is.
"""
from __future__ import annotations

import pytest

from pipeline.sources import hackernews, yc
from pipeline.sources.coverage import Coverage
from pipeline.sync import sync

TOPIC = "AI agents for SMBs"


class TestTopicIsRequired:
    @pytest.mark.parametrize("topic", ["", "   ", "\n"])
    def test_sync_refuses_an_empty_topic(self, settings, topic):
        with pytest.raises(ValueError, match="topic"):
            sync(topic, settings=settings)

    @pytest.mark.parametrize("topic", ["", "  "])
    def test_the_source_refuses_it_too(self, topic):
        # Belt and braces: sync is not the only caller of fetch().
        with pytest.raises(ValueError, match="topic"):
            hackernews.fetch(topic, since=0)


class TestHackerNewsSearches:
    def _searches(self, monkeypatch, topic=TOPIC):
        seen: list[dict] = []
        monkeypatch.setattr(hackernews, "_search",
                            lambda params, limit:
                                (seen.append(params), ([], Coverage.whole(0)))[1])
        hackernews.fetch(topic, since=1_700_000_000)
        return seen

    def test_show_hn_carries_the_topic(self, monkeypatch):
        show = [s for s in self._searches(monkeypatch) if s.get("tags") == "show_hn"]
        assert len(show) == 1
        assert show[0]["query"] == TOPIC

    def test_show_hn_has_no_points_filter(self, monkeypatch):
        # This is the whole point of the change.
        show = [s for s in self._searches(monkeypatch) if s.get("tags") == "show_hn"]
        assert "points" not in show[0]["numericFilters"]

    def test_launch_hn_does_not_take_the_topic(self, monkeypatch):
        # 119 posts a year. Asking a topic of it returns 8 and drops companies
        # the thesis gate should have judged.
        launch = [s for s in self._searches(monkeypatch) if s.get("tags") == "story"]
        assert len(launch) == 1
        assert launch[0]["query"] == '"Launch HN"'

    def test_both_pools_keep_the_date_window(self, monkeypatch):
        for search in self._searches(monkeypatch):
            assert "created_at_i>1700000000" in search["numericFilters"]


class TestYCSearches:
    def test_the_topic_goes_to_the_directory_search(self, monkeypatch):
        urls: list[str] = []
        monkeypatch.setattr(yc, "get_json",
                            lambda url: urls.append(url) or {"companies": [], "totalPages": 1})
        yc.fetch(TOPIC, ("W25",))
        assert urls, "no request was made"
        assert "q=AI+agents+for+SMBs" in urls[0]
        assert "batch=W25" in urls[0]


class TestTheLaunchPostIsKept:
    """Algolia returns the founder's own post in the same response as the title.

    We parsed six fields from that response and ignored this one, so 695
    companies held 61 characters of text. See 0016.
    """

    def _company(self, **hit):
        return hackernews._to_company({"objectID": "1", "title": "Show HN: Acme", **hit})

    def test_the_post_becomes_the_description(self):
        c = self._company(story_text="Hey HN! Acme does bookkeeping for salons.")
        assert c.description == "Hey HN! Acme does bookkeeping for salons."

    def test_html_is_stripped_and_entities_decoded(self):
        c = self._company(story_text='We&#x27;re <a href="https://acme.dev">Acme</a> &amp; co.')
        assert c.description == "We're Acme & co."

    def test_a_post_with_no_body_leaves_it_unset(self):
        # A link submission has no story_text. NULL, not "".
        assert self._company().description is None
        assert self._company(story_text="   ").description is None

    def test_the_title_still_becomes_the_one_liner(self):
        c = self._company(story_text="A long post")
        assert c.one_liner == "Show HN: Acme"
