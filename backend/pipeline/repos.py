"""Stage 3b: find each selected company's public repository.

Free, and the third step of `prepare`. It feeds metric 2, whose top band was
unreachable while Hacker News was the only traction source, and metric 1's
fallback tier, which had no repositories to read. See
docs/decisions/0006-github-as-a-source.md.

Finding nothing is a result, not an error: it is stored, so a later run does
not look again, and THESIS.md treats a missing repository as the instrument not
applying rather than as weak traction.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import Settings, settings as default_settings
from .db import connect, hours_ago
from .repository import github_repos as repos_repo
from .sources import github

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReposReport:
    companies: int
    looked_up: int
    found: int
    absent: int
    websites_recovered: int
    total: int = 0
    total_found: int = 0
    by_tier: dict = field(default_factory=dict)

    def render(self) -> str:
        lines = [
            f"companies checked  : {self.looked_up} of {self.companies}",
            f"repositories found : {self.found}",
            f"no public repo     : {self.absent}",
        ]
        if self.websites_recovered:
            lines.append(f"websites recovered : {self.websites_recovered}")
        for tier, n in sorted(self.by_tier.items()):
            lines.append(f"  via {tier:<12}: {n}")
        lines.append("-" * 46)
        lines.append(f"in database        : {self.total_found} found of {self.total} checked")
        return "\n".join(lines)


def find_repos(
    company_ids: list[int],
    *,
    settings: Settings = default_settings,
) -> ReposReport:
    """Look up repositories for a selection. Safe to re-run.

    A company checked inside settings.refresh_after_hours is skipped, the same
    rule the launch threads use. Stars and contributors move slowly, so a fresh
    row is worth reusing.
    """
    with connect(settings.db_path) as conn:
        pending = repos_repo.needing_lookup(
            conn, company_ids, hours_ago(settings.refresh_after_hours)
        )

    if not pending:
        with connect(settings.db_path) as conn:
            return ReposReport(
                companies=len(company_ids), looked_up=0, found=0, absent=0,
                websites_recovered=0, total=repos_repo.count(conn),
                total_found=repos_repo.count_found(conn),
            )

    def lookup(row):
        try:
            return row["id"], github.find(row["name"], row["website"],
                                          settings=settings.github)
        except Exception as exc:  # noqa: BLE001 - one company must not stop the run
            log.warning("github lookup failed for %s: %s", row["name"], exc)
            return row["id"], None

    # Network-bound and rate-limited, so a small pool. GitHub counts requests
    # per hour, not per second, and 15 companies is a short queue anyway.
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lookup, pending))

    found = absent = recovered = 0
    tiers: dict[str, int] = {}

    with connect(settings.db_path) as conn:
        for company_id, facts in results:
            if facts is None:
                repos_repo.record_absent(conn, company_id)
                absent += 1
                continue
            repos_repo.upsert(conn, company_id, facts)
            if facts.missing:
                absent += 1
            else:
                found += 1
                tiers[facts.found_via] = tiers.get(facts.found_via, 0) + 1
            if facts.homepage:
                recovered += 1
        conn.commit()
        total, total_found = repos_repo.count(conn), repos_repo.count_found(conn)

    return ReposReport(
        companies=len(company_ids),
        looked_up=len(pending),
        found=found,
        absent=absent,
        websites_recovered=recovered,
        total=total,
        total_found=total_found,
        by_tier=tiers,
    )
