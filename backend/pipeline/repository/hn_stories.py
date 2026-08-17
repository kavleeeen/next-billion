"""Queries against `hn_stories` and the `company_traction` view."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from ..db import utcnow
from ..models import HNStory

UPSERT = """
INSERT INTO hn_stories (company_id, story_id, title, url, points, comments,
                        posted_at, author, raw_json, created_at, updated_at)
VALUES (:company_id, :story_id, :title, :url, :points, :comments,
        :posted_at, :author, :raw_json, :now, :now)
ON CONFLICT (story_id) DO UPDATE SET
    company_id = excluded.company_id,
    title      = excluded.title,
    url        = excluded.url,
    points     = excluded.points,
    comments   = excluded.comments,
    posted_at  = excluded.posted_at,
    author     = excluded.author,
    raw_json   = excluded.raw_json,
    updated_at = excluded.updated_at
"""

FOR_COMPANY = "SELECT * FROM hn_stories WHERE company_id = ? ORDER BY posted_at DESC"

TRACTION = "SELECT * FROM company_traction WHERE company_id = ?"

COUNT = "SELECT COUNT(*) FROM hn_stories"

NEWEST = "SELECT MAX(posted_at) AS newest FROM hn_stories"

# Companies with more than one launch — the signal a single story hides.
REPEAT_LAUNCHERS = """
SELECT c.name, t.story_count, t.points, t.first_posted_at, t.last_posted_at
FROM company_traction t JOIN companies c ON c.id = t.company_id
WHERE t.story_count > 1
ORDER BY t.points DESC
LIMIT :limit
"""


def upsert(conn: sqlite3.Connection, company_id: int, stories: Iterable[HNStory]) -> int:
    """Insert or update stories for one company. Returns how many were written."""
    now = utcnow()
    written = 0
    for story in stories:
        conn.execute(UPSERT, story.to_row(company_id) | {"now": now})
        written += 1
    return written


def for_company(conn: sqlite3.Connection, company_id: int) -> list[sqlite3.Row]:
    return conn.execute(FOR_COMPANY, (company_id,)).fetchall()


def traction(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    """Aggregated launch traction. What metric 2 reads."""
    return conn.execute(TRACTION, (company_id,)).fetchone()


def repeat_launchers(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(REPEAT_LAUNCHERS, {"limit": limit}).fetchall()


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]
