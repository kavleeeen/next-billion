"""Pull every source into the database. Called by cli.cmd_sync, or any caller.

The database is the only store. Each source fetches, parses and returns
companies; nothing is written to disk in between. Every run therefore hits the
network — see docs/decisions/0002-data-model.md for why that trade was taken.

This module knows no source JSON shapes. Each source owns its own parse().
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .config import Settings, settings as default_settings
from .db import connect
from .merge import merge_cross_source
from .models import Company
from .repository import companies as companies_repo
from .repository import hn_stories as stories_repo
from .repository import merged_rows as merged_repo
from .sources.coverage import Coverage
from .sources import hackernews, yc

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceReport:
    source: str
    fetched: int
    usable: int
    added: int
    updated: int
    coverage: Coverage = field(default_factory=lambda: Coverage.whole(0))

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

    @property
    def added(self) -> int:
        return sum(r.added for r in self.sources)

    @property
    def updated(self) -> int:
        return sum(r.updated for r in self.sources)

    @property
    def message(self) -> str:
        """One line a person can act on.

        The stage owns this sentence, not the page. A caller that assembled it
        from the parts would be a second copy, free to disagree — and the parts
        it needs are per source, so it got "0 new" every time.
        """
        counted = (f"{self.added} new, {self.updated} updated"
                   if self.added or self.updated else "nothing new")
        return ". ".join([counted, *self.truncated]) + "."

    @property
    def truncated(self) -> list[str]:
        """Sources that had more to give than we read."""
        return [line for r in self.sources
                if (line := r.coverage.describe(r.source))]

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
        # A silent cut is the defect 0015 removed from the points filter, so a
        # cut made by a page cap has to be stated too.
        lines.extend(self.truncated)
        lines.append(f"companies in database: {self.total_rows}")
        if self.total_stories:
            lines.append(f"hn stories written   : {self.total_stories}")
        if self.merged:
            lines.append(f"cross-source merges  : {self.merged}")
        return "\n".join(lines)


def _plan(
    settings: Settings, topic: str, batches: tuple[str, ...],
    limit: int | None, hn_since: int,
) -> list[tuple[str, Callable[[], list[Company]]]]:
    """Pair each source name with a zero-argument call that fetches it.

    Adding a source means adding one line here. Nothing else in this module
    refers to a specific source.
    """
    return [
        (yc.NAME,
         lambda: yc.fetch(topic, batches, limit, workers=settings.fetch_workers)),
        (
            hackernews.NAME,
            lambda: hackernews.fetch(
                topic, hn_since, limit, workers=settings.fetch_workers,
            ),
        ),
    ]


def sync(
    topic: str,
    *,
    settings: Settings = default_settings,
    batches: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> SyncReport:
    """Fetch every source and upsert into the database. Safe to re-run.

    `topic` is required. It is what a partner is looking for, and it decides
    what we collect rather than what we keep. See
    docs/decisions/0015-the-topic-decides-what-we-collect.md.
    """
    if not topic.strip():
        raise ValueError("sync needs a topic; it decides what we collect")
    settings.ensure_dirs()
    # No batches means the whole YC directory. The topic is the filter now, so
    # pinning three recent batches would only fight it.
    batches = batches or ()
    reports: list[SourceReport] = []
    stories = 0

    hn_since = hackernews.since_epoch(settings.hn.lookback_days)

    # The sources are independent, so fetch them at the same time. Writing stays
    # on this thread: a SQLite connection is not safe to share.
    plan = _plan(settings, topic, batches, limit, hn_since)
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        fetched = [(name, *call()) for name, call in
                   pool.map(lambda item: (item[0], item[1]), plan)]

    with connect(settings.db_path) as conn:
        for name, companies, coverage in fetched:
            usable = [company for company in companies if company.is_usable]
            if rejected := len(companies) - len(usable):
                log.info("%s: rejected %s records with a non-company name", name, rejected)

            # A row already folded into another company must not be re-created;
            # its stories are still stored, against the surviving company.
            folded = merged_repo.keys_for(conn, name)
            fresh = [c for c in usable if c.source_key not in folded]

            added, updated = companies_repo.upsert(conn, fresh)
            stories += _store_stories(conn, name, usable)
            reports.append(SourceReport(name, len(companies), len(usable),
                                        added, updated, coverage))

        # Both sources are in; fold any company that appears in both.
        merged = merge_cross_source(conn)
        total = companies_repo.count(conn)

    return SyncReport(reports, total, stories, merged)
