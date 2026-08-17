"""Queries against the `github_repos` table."""
from __future__ import annotations

import json
import sqlite3

from ..db import utcnow
from . import sql

UPSERT = """
INSERT INTO github_repos (company_id, owner, repo, full_name, found_via, homepage,
                          description, language, stars, forks, open_issues,
                          contributors, org_followers, is_fork, archived,
                          gh_created_at, pushed_at, missing, raw_json,
                          checked_at, created_at, updated_at)
VALUES (:company_id, :owner, :repo, :full_name, :found_via, :homepage,
        :description, :language, :stars, :forks, :open_issues,
        :contributors, :org_followers, :is_fork, :archived,
        :gh_created_at, :pushed_at, :missing, :raw_json, :now, :now, :now)
ON CONFLICT (company_id) DO UPDATE SET
    owner=excluded.owner, repo=excluded.repo, full_name=excluded.full_name,
    found_via=excluded.found_via, homepage=excluded.homepage,
    description=excluded.description, language=excluded.language,
    stars=excluded.stars, forks=excluded.forks, open_issues=excluded.open_issues,
    contributors=excluded.contributors, org_followers=excluded.org_followers,
    is_fork=excluded.is_fork, archived=excluded.archived,
    gh_created_at=excluded.gh_created_at, pushed_at=excluded.pushed_at,
    missing=excluded.missing, raw_json=excluded.raw_json,
    checked_at=excluded.checked_at, updated_at=excluded.updated_at
"""

FOR_COMPANY = "SELECT * FROM github_repos WHERE company_id = :company_id"

# Which of these companies still need a look. A row already checked inside the
# refresh window is left alone, exactly like a launch thread.
NEEDING = """
SELECT c.id, c.name, c.website FROM companies c
LEFT JOIN github_repos g ON g.company_id = c.id
WHERE c.id IN (:company_ids)
  AND (g.company_id IS NULL OR g.checked_at < :stale_before)
"""

COUNT = "SELECT COUNT(*) FROM github_repos"
COUNT_FOUND = "SELECT COUNT(*) FROM github_repos WHERE missing = 0"


def upsert(conn: sqlite3.Connection, company_id: int, facts) -> None:
    """Record one company's repository, or the fact that it has none."""
    conn.execute(UPSERT, {
        "company_id": company_id,
        "owner": facts.owner,
        "repo": facts.repo,
        "full_name": facts.full_name,
        "found_via": facts.found_via,
        "homepage": facts.homepage,
        "description": facts.description,
        "language": facts.language,
        "stars": facts.stars,
        "forks": facts.forks,
        "open_issues": facts.open_issues,
        "contributors": facts.contributors,
        "org_followers": facts.org_followers,
        "is_fork": int(facts.is_fork),
        "archived": int(facts.archived),
        "gh_created_at": facts.created_at,
        "pushed_at": facts.pushed_at,
        "missing": int(facts.missing),
        "raw_json": json.dumps(facts.raw) if facts.raw else None,
        "now": utcnow(),
    })


def record_absent(conn: sqlite3.Connection, company_id: int) -> None:
    """Nothing public was found. Stored so the next run does not look again."""
    conn.execute(UPSERT, {
        "company_id": company_id, "owner": "", "repo": None, "full_name": None,
        "found_via": "none", "homepage": None, "description": None,
        "language": None, "stars": 0, "forks": 0, "open_issues": 0,
        "contributors": 0, "org_followers": 0, "is_fork": 0, "archived": 0,
        "gh_created_at": None, "pushed_at": None, "missing": 1,
        "raw_json": None, "now": utcnow(),
    })


def for_company(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    return sql.run(conn, FOR_COMPANY, {"company_id": company_id}).fetchone()


def needing_lookup(
    conn: sqlite3.Connection, company_ids: list[int], stale_before: str
) -> list[sqlite3.Row]:
    if not company_ids:
        return []
    return sql.run(conn, NEEDING, {
        "company_ids": company_ids,
        "stale_before": stale_before,
    }).fetchall()


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]


def count_found(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT_FOUND).fetchone()[0]
