"""Pull every source into the database. Called by cli.cmd_sync, or any caller.

The database is the only store. Each source fetches, parses and returns
companies; nothing is written to disk in between. Every run therefore hits the
network — see docs/decisions/0002-data-model.md for why that trade was taken.

This module knows no source JSON shapes. Each source owns its own parse().
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from .config import Settings, settings as default_settings
from .db import connect
from .models import Company
from .repository import companies as companies_repo
from .repository import hn_stories as stories_repo
from .sources import hackernews, yc

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceReport:
    source: str
    fetched: int
    usable: int
    added: int
    updated: int

    @property
    def rejected(self) -> int:
        """Records dropped because the name was not a company name."""
        return self.fetched - self.usable


def _store_stories(conn, source: str, companies: list[Company]) -> int:
    """Write each company\'s child records. Only Hacker News has any today."""
    written = 0
    for company in companies:
        if not company.stories:
            continue
        company_id = companies_repo.id_for(conn, source, company.source_key)
        if company_id is not None:
            written += stories_repo.upsert(conn, company_id, company.stories)
    return written


@dataclass(frozen=True)
class SyncReport:
    sources: list[SourceReport]
    total_rows: int
    total_stories: int = 0

    def render(self) -> str:
        """Human-readable table. Called by cli.cmd_sync."""
        lines = [
            f"{'source':<8}{'fetched':>9}{'usable':>8}{'rejected':>10}"
            f"{'added':>7}{'updated':>9}",
            "-" * 51,
        ]
        for report in self.sources:
            lines.append(
                f"{report.source:<8}{report.fetched:>9}{report.usable:>8}"
                f"{report.rejected:>10}{report.added:>7}{report.updated:>9}"
            )
        lines.append("-" * 51)
        lines.append(f"companies in database: {self.total_rows}")
        if self.total_stories:
            lines.append(f"hn stories written   : {self.total_stories}")
        return "\n".join(lines)


def _plan(
    settings: Settings, batches: tuple[str, ...], limit: int | None, hn_since: int
) -> list[tuple[str, Callable[[], list[Company]]]]:
    """Pair each source name with a zero-argument call that fetches it.

    Adding a source means adding one line here. Nothing else in this module
    refers to a specific source.
    """
    return [
        (yc.NAME, lambda: yc.fetch(batches, limit, workers=settings.fetch_workers)),
        (
            hackernews.NAME,
            lambda: hackernews.fetch(
                settings.hn.min_points,
                hn_since,
                limit,
                workers=settings.fetch_workers,
            ),
        ),
    ]


def sync(
    *,
    settings: Settings = default_settings,
    batches: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> SyncReport:
    """Fetch every source and upsert into the database. Safe to re-run."""
    settings.ensure_dirs()
    batches = batches or settings.yc.batches
    reports: list[SourceReport] = []
    stories = 0

    # Incremental: the floor comes from the newest story held, so a nightly run
    # reads a handful of posts rather than a year of them.
    with connect(settings.db_path) as conn:
        newest = stories_repo.newest_posted_at(conn)
    hn_since = hackernews.since_epoch(
        newest, settings.hn.lookback_days, settings.hn.refresh_days
    )

    # Independent, so fetch together. Writing stays on this thread: a SQLite
    # connection is not safe to share.
    plan = _plan(settings, batches, limit, hn_since)
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        fetched = list(pool.map(lambda item: (item[0], item[1]()), plan))

    with connect(settings.db_path) as conn:
        for name, companies in fetched:
            usable = [company for company in companies if company.is_usable]
            if rejected := len(companies) - len(usable):
                log.info("%s: rejected %s records with a non-company name", name, rejected)

            added, updated = companies_repo.upsert(conn, usable)
            stories += _store_stories(conn, name, usable)
            reports.append(SourceReport(name, len(companies), len(usable), added, updated))

        total = companies_repo.count(conn)

    return SyncReport(reports, total, stories)
