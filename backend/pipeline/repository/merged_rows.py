"""Rows folded into another company by the cross-source merge.

Consulted by sync() so a folded row is never re-created, and so its child
records still reach the company that absorbed it.
"""
from __future__ import annotations

import sqlite3

TARGET = "SELECT company_id FROM merged_rows WHERE source = ? AND source_key = ?"

KEYS_FOR_SOURCE = "SELECT source_key FROM merged_rows WHERE source = ?"

COUNT = "SELECT COUNT(*) FROM merged_rows"


def target_for(conn: sqlite3.Connection, source: str, source_key: str) -> int | None:
    """The surviving company a folded row belongs to, or None if not folded."""
    row = conn.execute(TARGET, (source, source_key)).fetchone()
    return row["company_id"] if row else None


def keys_for(conn: sqlite3.Connection, source: str) -> set[str]:
    """Every folded key for one connector. Used to filter before upserting."""
    return {r["source_key"] for r in conn.execute(KEYS_FOR_SOURCE, (source,))}


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(COUNT).fetchone()[0]
