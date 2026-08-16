"""Keyword search over companies already stored by sync(). No network calls."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .config import Settings, settings as default_settings
from .db import connect
from .repository import companies as companies_repo

DEFAULT_LIMIT = 25


@dataclass(frozen=True)
class SearchReport:
    term: str
    rows: list[sqlite3.Row]

    @property
    def found(self) -> bool:
        return bool(self.rows)

    def render(self) -> str:
        if not self.rows:
            return f"no matches for {self.term!r}. Run `sync` first?"

        lines = [
            f"{row['batch'] or '--':<5} {row['name'][:28]:<30} "
            f"{(row['website'] or '')[:34]:<36} {(row['one_liner'] or '')[:44]}"
            for row in self.rows
        ]
        lines.append(f"\n{len(self.rows)} matches")
        return "\n".join(lines)


def search(
    term: str,
    *,
    settings: Settings = default_settings,
    limit: int = DEFAULT_LIMIT,
    source: str | None = None,
    sort: str = "default",
) -> SearchReport:
    """Keyword search over the stored companies."""
    with connect(settings.db_path) as conn:
        return SearchReport(
            term,
            companies_repo.search(conn, term, limit=limit, source=source, sort=sort),
        )
