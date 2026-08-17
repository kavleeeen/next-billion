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


def utcnow() -> str:
    """Timestamp for created_at / updated_at. Called by repository.companies."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hours_ago(hours: float) -> str:
    """Cutoff for a freshness test. Every timestamp column uses the format
    utcnow() writes, so a string comparison is also a time comparison."""
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat(timespec="seconds")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open, apply schema, commit on clean exit. Called by sync() and search()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
