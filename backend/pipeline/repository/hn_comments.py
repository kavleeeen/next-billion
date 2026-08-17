"""Queries against `hn_comments`."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from ..db import utcnow
from ..models import HNComment

UPSERT = """
INSERT INTO hn_comments (story_id, comment_id, author, text, is_op, posted_at, created_at)
VALUES (:story_id, :comment_id, :author, :text, :is_op, :posted_at, :now)
ON CONFLICT (comment_id) DO UPDATE SET
    text   = excluded.text,
    is_op  = excluded.is_op,
    author = excluded.author
"""

MARK_FETCHED = "UPDATE hn_stories SET comments_fetched_at = ? WHERE story_id = ?"

# Highest-signal threads first: most points, and never re-fetch one already done.
STORIES_NEEDING_COMMENTS = """
SELECT s.story_id, s.author, s.title, s.points, s.company_id
FROM hn_stories s
WHERE s.comments_fetched_at IS NULL AND s.comments > 0
ORDER BY s.points DESC
LIMIT :limit
"""

# Every thread belonging to a named set of companies that is unfetched or
# stale. No points ordering and no cap: a selected company needs all of its
# threads, not the loudest one. A thread keeps getting replies after it is
# first read, so a selection made a day later should see them.
STORIES_FOR_COMPANIES = """
SELECT s.story_id, s.author, s.title, s.points, s.company_id
FROM hn_stories s
WHERE s.comments > 0
  AND (s.comments_fetched_at IS NULL OR s.comments_fetched_at < ?)
  AND s.company_id IN ({placeholders})
ORDER BY s.points DESC
"""

# What the LLM reads. The submitter's own words first, then the rest.
FOR_COMPANY = """
SELECT c.* FROM hn_comments c
JOIN hn_stories s ON s.story_id = c.story_id
WHERE s.company_id = :company_id
ORDER BY c.is_op DESC, length(c.text) DESC
LIMIT :limit
"""

COUNT = "SELECT COUNT(*) FROM hn_comments"
COUNT_OP = "SELECT COUNT(*) FROM hn_comments WHERE is_op = 1"


def upsert(conn: sqlite3.Connection, comments: Iterable[HNComment]) -> int:
    now = utcnow()
    written = 0
    for comment in comments:
        conn.execute(UPSERT, comment.to_row() | {"now": now})
        written += 1
    return written


def mark_fetched(conn: sqlite3.Connection, story_id: str) -> None:
    """Record that a thread was pulled, so it is never pulled twice."""
    conn.execute(MARK_FETCHED, (utcnow(), story_id))


def stories_needing_comments(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(STORIES_NEEDING_COMMENTS, {"limit": limit}).fetchall()


def stories_for_companies(
    conn: sqlite3.Connection,
    company_ids: list[int],
    stale_before: str | None = None,
) -> list[sqlite3.Row]:
    """Threads for these companies that need a read. Used before scoring.

    stale_before is an ISO timestamp: a thread read before it is fetched again.
    Passing None keeps the original rule, which is to read each thread once.
    """
    if not company_ids:
        return []
    marks = ",".join("?" * len(company_ids))
    query = STORIES_FOR_COMPANIES.format(placeholders=marks)
    # "" is older than any ISO timestamp, so it selects only unfetched threads.
    return conn.execute(query, [stale_before or "", *company_ids]).fetchall()


def for_company(conn: sqlite3.Connection, company_id: int, limit: int = 20) -> list[sqlite3.Row]:
    """Comments on any of a company's threads, submitter's own first."""
    return conn.execute(
        FOR_COMPANY, {"company_id": company_id, "limit": limit}
    ).fetchall()


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]


def count_op(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT_OP).fetchone()[0]
