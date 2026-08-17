"""Queries against the `analyses` table.

A scoring run appends a row. Nothing updates or deletes one, so a company keeps
the history of what it scored and when, and the list reads the newest row.
"""
from __future__ import annotations

import json
import sqlite3

from ..db import hours_ago, utcnow
from . import sql

INSERT = """
INSERT INTO analyses (company_id, verdict, total, scores_json, model,
                      prompt_version, created_at)
VALUES (:company_id, :verdict, :total, :scores_json, :model,
        :prompt_version, :created_at)
"""

# MAX(id) and not MAX(created_at): two runs inside the same second would
# otherwise tie, and the tie-break would be arbitrary.
LATEST = """
SELECT * FROM analyses a
WHERE a.company_id = :company_id
ORDER BY a.id DESC
LIMIT 1
"""

FRESH = """
SELECT DISTINCT company_id FROM analyses
WHERE company_id IN (:company_ids)
  AND model = :model
  AND prompt_version = :prompt_version
  AND created_at >= :cutoff
"""

COUNT = "SELECT COUNT(*) FROM analyses"
COUNT_SCORED = "SELECT COUNT(DISTINCT company_id) FROM analyses"


def insert(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    verdict: str,
    total: float,
    scores: dict,
    model: str,
    prompt_version: str,
) -> int:
    """Append one scoring run. Returns the new row id."""
    cursor = conn.execute(INSERT, {
        "company_id": company_id,
        "verdict": verdict,
        "total": total,
        "scores_json": json.dumps(scores),
        "model": model,
        "prompt_version": prompt_version,
        "created_at": utcnow(),
    })
    return int(cursor.lastrowid)


def latest(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    """The newest score for one company, or None."""
    return sql.run(conn, LATEST, {"company_id": company_id}).fetchone()


def fresh_company_ids(
    conn: sqlite3.Connection,
    company_ids: list[int],
    *,
    model: str,
    prompt_version: str,
    within_hours: float,
) -> set[int]:
    """Which of these companies were scored recently enough to reuse.

    The model and the prompt version are part of the test. A score from a
    different model is not a fresh score, it is a different opinion.
    """
    if not company_ids or within_hours <= 0:
        return set()

    rows = sql.run(conn, FRESH, {
        "company_ids": company_ids,
        "model": model,
        "prompt_version": prompt_version,
        "cutoff": hours_ago(within_hours),
    }).fetchall()
    return {row["company_id"] for row in rows}


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]


def count_scored(conn: sqlite3.Connection) -> int:
    """Companies with a score, not runs."""
    return conn.execute(COUNT_SCORED).fetchone()[0]
