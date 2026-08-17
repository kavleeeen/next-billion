"""Connection and schema only; queries live in repository/.

Repositories take a connection and open none of their own, so the caller
decides what commits together.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# CREATE TABLE IF NOT EXISTS cannot add a column to a database that already
# exists, so columns added later are applied here instead of by the schema.
ADDED_COLUMNS = (
    ("companies", "industries", "TEXT"),
    ("hn_stories", "author", "TEXT"),
    ("hn_stories", "comments_fetched_at", "TEXT"),
    ("analyses", "prompt_version", "TEXT"),
)


def utcnow() -> str:
    """Timestamp for created_at / updated_at. Called by repository.companies."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hours_ago(hours: float) -> str:
    """Cutoff for a freshness test. Every timestamp column uses the format
    utcnow() writes, so a string comparison is also a time comparison."""
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat(timespec="seconds")


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Bring an older database up to the current schema. Adding a column is the
    only migration shape this needs; anything harder rebuilds from `sync`."""
    for table, column, declaration in ADDED_COLUMNS:
        present = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open, apply schema, commit on clean exit. Called by sync() and search()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _add_missing_columns(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
