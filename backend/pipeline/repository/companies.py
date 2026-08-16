"""Queries against the `companies` table."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from ..db import utcnow
from ..models import Company

UPSERT = """
INSERT INTO companies (source, source_key, name, website, one_liner,
                       description, batch, team_size, raw_json, created_at, updated_at)
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

SEARCH = r"""
SELECT * FROM companies
WHERE name        LIKE :pattern ESCAPE '\'
   OR one_liner   LIKE :pattern ESCAPE '\'
   OR description LIKE :pattern ESCAPE '\'
ORDER BY (batch IS NULL), batch DESC, name
LIMIT :limit
"""

COUNT = "SELECT COUNT(*) FROM companies"

GET_BY_ID = "SELECT * FROM companies WHERE id = ?"


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


def search(conn: sqlite3.Connection, term: str, limit: int = 50) -> list[sqlite3.Row]:
    """Keyword search over name, one-liner and description. Called by search.search()."""
    return conn.execute(
        SEARCH, {"pattern": f"%{_escape_like(term.strip())}%", "limit": limit}
    ).fetchall()


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]


def get(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    return conn.execute(GET_BY_ID, (company_id,)).fetchone()
