"""Evidence younger than the refresh window is reused, not fetched again.

A selection is prepared repeatedly while a partner works through it. Without a
window, every click re-reads the same threads.
"""
from __future__ import annotations

import pytest

from pipeline.db import hours_ago, utcnow
from pipeline.models import Company, HNStory
from pipeline.repository import companies as companies_repo
from pipeline.repository import hn_comments as comments_repo
from pipeline.repository import hn_stories as stories_repo


@pytest.fixture
def company_id(conn):
    companies_repo.upsert(conn, [Company(source="yc", source_key="acme", name="Acme")])
    return companies_repo.id_for(conn, "yc", "acme")


def _story(conn, company_id, story_id, fetched_at=None):
    stories_repo.upsert(conn, company_id, [
        HNStory(story_id=story_id, title=f"Launch HN: {story_id}", comments=5)
    ])
    if fetched_at:
        conn.execute(comments_repo.MARK_FETCHED, (fetched_at, story_id))


def _pending(conn, company_id, hours=1.0):
    rows = comments_repo.stories_for_companies(conn, [company_id], hours_ago(hours))
    return {row["story_id"] for row in rows}


class TestHoursAgo:
    def test_it_is_earlier_than_now(self):
        assert hours_ago(1) < utcnow()

    def test_it_matches_the_stored_format(self):
        # Timestamps are compared as strings, so the formats must agree.
        assert len(hours_ago(1)) == len(utcnow())

    def test_a_larger_number_is_further_back(self):
        assert hours_ago(2) < hours_ago(1)


class TestStaleThreads:
    def test_an_unread_thread_is_always_pending(self, conn, company_id):
        _story(conn, company_id, "1")
        assert _pending(conn, company_id) == {"1"}

    def test_a_thread_read_just_now_is_not(self, conn, company_id):
        _story(conn, company_id, "1", fetched_at=utcnow())
        assert _pending(conn, company_id) == set()

    def test_a_thread_read_before_the_window_is(self, conn, company_id):
        # Replies keep arriving after a launch, so an old read is worth redoing.
        _story(conn, company_id, "1", fetched_at=hours_ago(2))
        assert _pending(conn, company_id) == {"1"}

    def test_the_window_is_read_from_the_argument(self, conn, company_id):
        _story(conn, company_id, "1", fetched_at=hours_ago(2))
        assert _pending(conn, company_id, hours=3) == set()
        assert _pending(conn, company_id, hours=1) == {"1"}

    def test_no_cutoff_keeps_the_original_rule(self, conn, company_id):
        # "" is older than any ISO timestamp, so only unread threads qualify.
        _story(conn, company_id, "1", fetched_at=hours_ago(99))
        _story(conn, company_id, "2")
        assert {r["story_id"] for r in
                comments_repo.stories_for_companies(conn, [company_id])} == {"2"}

    def test_a_thread_with_no_comments_is_never_pending(self, conn, company_id):
        stories_repo.upsert(conn, company_id, [
            HNStory(story_id="3", title="Launch HN: quiet", comments=0)
        ])
        assert _pending(conn, company_id) == set()
