"""Stage 3: get a selected shortlist ready to score.

A partner picks up to 20 companies. Before any of them can be scored, three
kinds of evidence have to exist:

    launch threads   free      the founder's own words, for metrics 1 and 4
    repositories     free      stars, contributors, recency, for metric 2
    founders         credits   prior roles, the primary evidence for metric 1

All three are done here, in that order. The free work runs first, so a credit
ceiling reached during enrichment still leaves every free signal in place.

Sync deliberately does not pull threads. It could only cover 40 per run, 5% of
companies, chosen by points rather than by what anyone asked for.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .comments import fetch_comments
from .config import Settings, settings as default_settings
from .db import connect
from .enrich import enrich
from .repos import find_repos
from .repository import companies as companies_repo

log = logging.getLogger(__name__)

MAX_SELECTION = 20


class TooManySelected(ValueError):
    """Raised when a selection exceeds MAX_SELECTION."""


@dataclass(frozen=True)
class PrepareReport:
    companies: int
    threads_pulled: int
    comments_stored: int
    founder_comments: int
    repos_found: int
    repos_absent: int
    founders_found: int
    credits_used: int             # this run only; the provider holds the total

    def render(self) -> str:
        return "\n".join([
            f"companies prepared  : {self.companies}",
            f"threads pulled      : {self.threads_pulled}",
            f"comments stored     : {self.comments_stored} "
            f"({self.founder_comments} from founders)",
            f"repositories found  : {self.repos_found} "
            f"({self.repos_absent} with none public)",
            f"founders found      : {self.founders_found}",
            f"credits this run    : {self.credits_used}",
        ])


def prepare(
    company_ids: list[int],
    *,
    settings: Settings = default_settings,
    use_pdl: bool = True,
) -> PrepareReport:
    """Pull threads and founders for a selection. Safe to re-run.

    Neither step repeats work: a thread already fetched is skipped, and a
    company that already has founders is skipped unless enrich is forced.
    """
    if len(company_ids) > MAX_SELECTION:
        raise TooManySelected(
            f"{len(company_ids)} companies selected; the limit is {MAX_SELECTION}"
        )

    with connect(settings.db_path) as conn:
        known = [row["id"] for row in companies_repo.by_ids(conn, company_ids)]

    missing = set(company_ids) - set(known)
    if missing:
        log.warning("no such company: %s", sorted(missing))
    if not known:
        raise ValueError("none of the selected ids exist")

    # Free work first, so a credit ceiling reached during enrichment still
    # leaves every free signal in place.
    threads = fetch_comments(settings=settings, company_ids=known)
    repos = find_repos(known, settings=settings)
    founders = enrich(settings=settings, company_ids=known, use_pdl=use_pdl)

    return PrepareReport(
        companies=len(known),
        threads_pulled=threads.threads,
        comments_stored=threads.comments,
        founder_comments=threads.from_submitter,
        repos_found=repos.found,
        repos_absent=repos.absent,
        founders_found=founders.founders_found,
        credits_used=founders.pdl_calls,
    )
