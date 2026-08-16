"""Credit spend against the People Data Labs plan.

The allowance is monthly and shared by every process, so the count has to live
in the database. A per-run ceiling alone bounds one call; several HTTP requests
would each get their own budget.
"""
from __future__ import annotations

import sqlite3

from ..db import utcnow

RECORD = "INSERT INTO pdl_usage (called_at, calls) VALUES (?, ?)"

THIS_MONTH = """
SELECT COALESCE(SUM(calls), 0) FROM pdl_usage
WHERE substr(called_at, 1, 7) = substr(?, 1, 7)
"""

TOTAL = "SELECT COALESCE(SUM(calls), 0) FROM pdl_usage"


def record(conn: sqlite3.Connection, calls: int) -> None:
    """Log credits spent. Called immediately after the API call, so a later
    failure cannot lose the record of money already spent."""
    if calls > 0:
        conn.execute(RECORD, (utcnow(), calls))


def spent_this_month(conn: sqlite3.Connection) -> int:
    return conn.execute(THIS_MONTH, (utcnow(),)).fetchone()[0]


def spent_total(conn: sqlite3.Connection) -> int:
    return conn.execute(TOTAL).fetchone()[0]
