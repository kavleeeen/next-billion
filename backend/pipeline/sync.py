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
from .comments import fetch_comments
from .db import connect
from .merge import merge_cross_source
from .models import Company
from .repository import companies as companies_repo
from .repository import hn_stories as stories_repo
from .repository import merged_rows as merged_repo
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
    """Write each company\'s child records. Only Hacker News has any today.

    A company whose row was folded into another has no row of its own, so its
    stories are attached to the company that absorbed it.
    """
    written = 0
    for company in companies:
        if not company.stories:
            continue
        company_id = (
            companies_repo.id_for(conn, source, company.source_key)
            or merged_repo.target_for(conn, source, company.source_key)
        )
        if company_id is not None:
            written += stories_repo.upsert(conn, company_id, company.stories)
    return written


@dataclass(frozen=True)
class SyncReport:
    sources: list[SourceReport]
    total_rows: int
    total_stories: int = 0
    merged: int = 0
    threads_pulled: int = 0
    comments_stored: int = 0

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
        if self.merged:
            lines.append(f"cross-source merges  : {self.merged}")
        if self.threads_pulled:
            lines.append(
                f"hn threads pulled    : {self.threads_pulled} "
                f"({self.comments_stored} comments)"
            )
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
    comments: int | None = None,
) -> SyncReport:
    """Fetch every source and upsert into the database. Safe to re-run.

    `comments` caps how many Hacker News threads are pulled at the end;
    defaults to settings.hn.comments_per_sync, and 0 skips them. A full
    backfill is ~518 threads, so the ceiling keeps any single run short while
    the backlog drains over several.
    """
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

    # The sources are independent, so fetch them at the same time. Writing stays
    # on this thread: a SQLite connection is not safe to share.
    plan = _plan(settings, batches, limit, hn_since)
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        fetched = list(pool.map(lambda item: (item[0], item[1]()), plan))

    with connect(settings.db_path) as conn:
        for name, companies in fetched:
            usable = [company for company in companies if company.is_usable]
            if rejected := len(companies) - len(usable):
                log.info("%s: rejected %s records with a non-company name", name, rejected)

            # A row already folded into another company must not be re-created;
            # its stories are still stored, against the surviving company.
            folded = merged_repo.keys_for(conn, name)
            fresh = [c for c in usable if c.source_key not in folded]

            added, updated = companies_repo.upsert(conn, fresh)
            stories += _store_stories(conn, name, usable)
            reports.append(SourceReport(name, len(companies), len(usable), added, updated))

        # Both sources are in; fold any company that appears in both.
        merged = merge_cross_source(conn)
        total = companies_repo.count(conn)

    # Outside the connection above: fetch_comments opens its own, and two write
    # connections to one SQLite file would contend.
    budget = settings.hn.comments_per_sync if comments is None else comments
    threads = stored = 0
    if budget:
        report = fetch_comments(settings=settings, limit=budget)
        threads, stored = report.threads, report.comments

    return SyncReport(reports, total, stories, merged, threads, stored)
