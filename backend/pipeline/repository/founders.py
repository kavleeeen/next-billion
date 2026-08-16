"""Queries against the `founders` table."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from ..db import utcnow
from ..models import Founder

UPSERT = """
INSERT INTO founders (company_id, linkedin_slug, name, source_url, discovered_via,
                      pdl_matched, current_title, current_company, prior_roles_json,
                      raw_json, created_at, updated_at)
VALUES (:company_id, :linkedin_slug, :name, :source_url, :discovered_via,
        :pdl_matched, :current_title, :current_company, :prior_roles_json,
        :raw_json, :now, :now)
ON CONFLICT (company_id, linkedin_slug) DO UPDATE SET
    name             = excluded.name,
    source_url       = excluded.source_url,
    discovered_via   = excluded.discovered_via,
    pdl_matched      = excluded.pdl_matched,
    current_title    = excluded.current_title,
    current_company  = excluded.current_company,
    prior_roles_json = excluded.prior_roles_json,
    raw_json         = excluded.raw_json,
    updated_at       = excluded.updated_at
"""

EXISTS = "SELECT 1 FROM founders WHERE company_id = ? AND linkedin_slug = ?"

FOR_COMPANY = "SELECT * FROM founders WHERE company_id = ? ORDER BY id"

# Work list for `enrich`: any company with no founder row yet, that we have some
# way of resolving — a YC slug (authoritative) or a website (PDL search).
COMPANIES_WITHOUT_FOUNDERS = """
SELECT c.* FROM companies c
LEFT JOIN founders f ON f.company_id = c.id
WHERE f.id IS NULL
  AND (c.source = 'yc' OR c.website IS NOT NULL)
  AND (:source IS NULL OR c.source = :source)
GROUP BY c.id
ORDER BY (c.source = 'yc') DESC, c.batch DESC, c.name
LIMIT :limit
"""

COUNT = "SELECT COUNT(*) FROM founders"
COUNT_MATCHED = "SELECT COUNT(*) FROM founders WHERE pdl_matched = 1"


def upsert(conn: sqlite3.Connection, founders: Iterable[Founder]) -> tuple[int, int]:
    """Insert or update by (company_id, linkedin_slug). Returns (added, updated)."""
    now = utcnow()
    added = updated = 0

    for founder in founders:
        row = founder.to_row() | {"now": now}
        already_present = conn.execute(
            EXISTS, (row["company_id"], row["linkedin_slug"])
        ).fetchone()
        conn.execute(UPSERT, row)
        if already_present:
            updated += 1
        else:
            added += 1

    return added, updated


def for_company(conn: sqlite3.Connection, company_id: int) -> list[sqlite3.Row]:
    return conn.execute(FOR_COMPANY, (company_id,)).fetchall()


def companies_needing_founders(
    conn: sqlite3.Connection, limit: int, source: str | None = None
) -> list[sqlite3.Row]:
    """Companies with no founder row yet. Called by enrich().

    source filters to one connector ('yc' or 'hn'); None takes both. YC rows
    sort first because their founders are stated rather than inferred.
    """
    return conn.execute(
        COMPANIES_WITHOUT_FOUNDERS, {"limit": limit, "source": source}
    ).fetchall()


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]


def count_matched(conn: sqlite3.Connection) -> int:
    """Founders PDL had a record for. The rest fall back to metric 1's second tier."""
    return conn.execute(COUNT_MATCHED).fetchone()[0]
