"""Queries against the `companies` table."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from ..db import utcnow
from ..models import Company

UPSERT = """
INSERT INTO companies (source, source_key, name, website, one_liner,
                       description, batch, team_size, raw_json,
                       created_at, updated_at)
VALUES (:source, :source_key, :name, :website, :one_liner,
        :description, :batch, :team_size, :raw_json, :now, :now)
ON CONFLICT (source, source_key) DO UPDATE SET
    name        = excluded.name,
    website     = excluded.website,
    one_liner   = excluded.one_liner,
    description = excluded.description,
    batch       = excluded.batch,
    team_size   = excluded.team_size,
    raw_json    = excluded.raw_json,
    updated_at  = excluded.updated_at
"""

EXISTS = "SELECT 1 FROM companies WHERE source = ? AND source_key = ?"

# Traction is joined in so the list can sort by it without a second query.
SEARCH = r"""
SELECT c.*,
       COALESCE(t.story_count, 0)  AS story_count,
       COALESCE(t.points, 0)       AS points,
       COALESCE(t.comments, 0)     AS comments,
       t.last_posted_at
FROM companies c
LEFT JOIN company_traction t ON t.company_id = c.id
WHERE (c.name        LIKE :pattern ESCAPE '\'
    OR c.one_liner   LIKE :pattern ESCAPE '\'
    OR c.description LIKE :pattern ESCAPE '\')
  AND (:source IS NULL OR c.source = :source)
ORDER BY
  CASE :sort
    WHEN 'points' THEN -COALESCE(t.points, 0)
    WHEN 'recent' THEN 0
    ELSE 0
  END,
  CASE WHEN :sort = 'recent' THEN t.last_posted_at END DESC,
  (c.batch IS NULL), c.batch DESC, c.name
LIMIT :limit
"""

COUNT = "SELECT COUNT(*) FROM companies"

GET_BY_ID = "SELECT * FROM companies WHERE id = ?"

ID_FOR_KEY = "SELECT id FROM companies WHERE source = ? AND source_key = ?"


def upsert(conn: sqlite3.Connection, companies: Iterable[Company]) -> tuple[int, int]:
    """Insert or update by (source, source_key). Returns (added, updated)."""
    now = utcnow()
    added = updated = 0

    for company in companies:
        row = company.to_row() | {"now": now}
        already_present = conn.execute(
            EXISTS, (row["source"], row["source_key"])
        ).fetchone()
        conn.execute(UPSERT, row)
        if already_present:
            updated += 1
        else:
            added += 1

    return added, updated


def _escape_like(term: str) -> str:
    r"""Neutralise LIKE wildcards so "50%" and "a_b" are searched literally."""
    for char in ("\\", "%", "_"):
        term = term.replace(char, f"\\{char}")
    return term


def search(
    conn: sqlite3.Connection,
    term: str,
    limit: int = 50,
    source: str | None = None,
    sort: str = "default",
) -> list[sqlite3.Row]:
    """Keyword search with traction joined in. Called by search.search().

    sort: 'points' (most traction), 'recent' (latest launch), or 'default'.
    """
    return conn.execute(SEARCH, {
        "pattern": f"%{_escape_like(term.strip())}%",
        "limit": limit,
        "source": source,
        "sort": sort,
    }).fetchall()



def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]


def get(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    return conn.execute(GET_BY_ID, (company_id,)).fetchone()


def id_for(conn: sqlite3.Connection, source: str, source_key: str) -> int | None:
    """Row id for a company\'s natural key. Used to attach child records."""
    row = conn.execute(ID_FOR_KEY, (source, source_key)).fetchone()
    return row["id"] if row else None
