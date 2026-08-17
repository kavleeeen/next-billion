"""Stage 2: attach founders to companies already in the database.

Two strategies, tried in that order:

    yc_page     YC company page -> linkedin.com/in/<slug> -> PDL enrich
                Authoritative: YC states who the founders are.
                Free to find them, 1 credit each to get their history.

    pdl_search  company website domain -> PDL search, owner-level titles only
                Inferred: the title says founder, nobody vouched for it.
                Works for any company with a website, YC or not.
                1 credit per record returned.

Feeds metric 1 of the thesis. Where PDL has no record the founder is still
stored, and metric 1 falls back to its second tier, which caps at 79.

Credits are the constraint, and the provider counts them. We keep no tally of
our own: a second count can only disagree with the authoritative one. A company
that already has founders is skipped unless force=True, the token is checked
before any call, and a 402 ends the run.

Each company commits on its own. A failure part-way through keeps the founders
already bought instead of rolling the whole run back.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Settings, settings as default_settings
from ..db import connect
from ..models import Founder
from ..normalize import registrable_domain
from ..repository import companies as companies_repo
from ..repository import founders as founders_repo
from . import pdl, yc_page

log = logging.getLogger(__name__)

# How many founders PDL search may return per company. Not a cap on how many
# are stored — a company with eight founders gets eight rows.
SEARCH_PAGE_SIZE = 10

# Hosts that belong to a platform, not to the company linking from them. A
# search keyed on one returns the platform's staff: github.com gave Airweave
# ten "founders" who work at GitHub, and cost ten credits to do it. 289 of the
# 1171 companies with a website point at github.com alone.
# See docs/decisions/0007-shared-hosts-are-not-company-domains.md.
_SHARED_HOSTS = frozenset({
    "github.com", "github.io", "gitlab.com", "bitbucket.org", "sourceforge.net",
    "npmjs.com", "pypi.org", "crates.io", "hex.pm", "rubygems.org",
    "vercel.app", "netlify.app", "herokuapp.com", "fly.dev", "render.com",
    "pages.dev", "firebaseapp.com", "web.app", "replit.app", "streamlit.app",
    "notion.site", "notion.so", "gitbook.io", "readthedocs.io", "substack.com",
    "medium.com", "wordpress.com", "webflow.io", "framer.website", "carrd.co",
    "google.com", "docs.google.com", "apple.com", "apps.apple.com",
    "play.google.com", "huggingface.co", "producthunt.com", "ycombinator.com",
    "x.com", "twitter.com", "linkedin.com", "youtube.com", "reddit.com",
    "discord.com", "discord.gg", "t.me", "telegram.me", "typeform.com",
})


@dataclass(frozen=True)
class EnrichReport:
    companies: int
    skipped_existing: int
    via_yc_page: int
    via_pdl_search: int
    founders_found: int
    pdl_calls: int
    pdl_matched: int
    added: int
    updated: int
    stopped: str | None          # None, or 'account_exhausted'
    total_founders: int
    total_matched: int

    def render(self) -> str:
        """Human-readable summary. Called by cli.cmd_enrich."""
        rate = f"{self.pdl_matched / self.pdl_calls * 100:.0f}%" if self.pdl_calls else "--"
        lines = [
            f"companies processed : {self.companies}"
            f"   (yc page {self.via_yc_page}, pdl search {self.via_pdl_search})",
            f"already had founders: {self.skipped_existing}",
            f"founders found      : {self.founders_found}",
            f"credits this run    : {self.pdl_calls}",
            f"with prior roles    : {self.pdl_matched}  ({rate})",
            f"rows added/updated  : {self.added}/{self.updated}",
        ]
        if self.stopped == "account_exhausted":
            lines.append(
                "stopped early: the provider refused - the plan's monthly matches "
                "are gone. Founders already stored are kept; companies without one "
                "score metric 1 on the fallback tier, which cannot exceed 79."
            )
        lines.append("-" * 46)
        lines.append(
            f"founders in database   : {self.total_founders} "
            f"({self.total_matched} with prior roles)"
        )
        return "\n".join(lines)


def _domain(url: str | None) -> str | None:
    """Registrable domain, for matching PDL's `job_company_website`.

    Subdomains must be stripped. A Launch HN post may link to
    `app.propolis.tech`, while PDL stores `propolis.tech`.

    Returns None for a shared host. No domain means no search, so the company
    keeps no founders and rule 4 holds its verdict at Watch — which is correct,
    because nobody has identified its team.
    """
    domain = registrable_domain(url)
    return None if domain in _SHARED_HOSTS else domain


def _from_slug(company_id: int, slug: str, source_url: str, person: dict | None) -> Founder:
    """A founder YC named, optionally with PDL history attached."""
    if not person:
        return Founder(
            company_id=company_id, linkedin_slug=slug,
            source_url=source_url, discovered_via="yc_page",
        )
    return Founder(
        company_id=company_id,
        linkedin_slug=slug,
        source_url=source_url,
        discovered_via="yc_page",
        name=person.get("full_name"),
        pdl_matched=True,
        current_title=person.get("job_title"),
        current_company=person.get("job_company_name"),
        prior_roles=pdl.prior_roles(person),
        raw=person,
    )


def _from_search(company_id: int, person: dict, source_url: str) -> Founder:
    """A founder PDL search inferred from an owner-level title."""
    slug = person.get("linkedin_username") or person.get("id") or person.get("full_name", "")
    return Founder(
        company_id=company_id,
        linkedin_slug=str(slug),
        source_url=source_url,
        discovered_via="pdl_search",
        name=person.get("full_name"),
        pdl_matched=True,
        current_title=person.get("job_title"),
        current_company=person.get("job_company_name"),
        prior_roles=pdl.prior_roles(person),
        raw=person,
    )


def enrich(
    *,
    settings: Settings = default_settings,
    limit: int = 5,
    use_pdl: bool = True,
    source: str | None = None,
    company_ids: list[int] | None = None,
    force: bool = False,
) -> EnrichReport:
    """Find founders for companies that have none yet.

    limit counts *companies*, not credits. Budget roughly 2 to 3 credits each,
    and stop when the provider says the allowance is finished.
    company_ids targets an explicit list, for on-demand enrichment from the UI.
    force re-buys founders for companies that already have them.
    use_pdl=False finds YC founders by name only and spends nothing.
    """
    settings.ensure_dirs()

    # Fail before spending anything if the key is missing.
    if use_pdl and not settings.pdl.token:
        raise pdl.MissingToken(
            f"{settings.pdl.token_env} is not set. Put it in .env at the repo root."
        )

    calls = matched = found = added = updated = skipped = 0
    via_yc = via_search = 0
    stopped: str | None = None

    with connect(settings.db_path) as conn:
        companies = (
            companies_repo.by_ids(conn, company_ids) if company_ids
            else founders_repo.companies_needing_founders(conn, limit, source)
        )

        for company in companies:
            # The explicit-id path bypasses the "needs founders" query, so the
            # check has to happen here too, or a repeated POST re-buys them.
            if not force and founders_repo.for_company(conn, company["id"]):
                skipped += 1
                continue

            batch: list[Founder] = []
            slugs = (
                yc_page.founder_slugs(company["source_key"])
                if company["source"] == "yc" else []
            )

            # No ceiling of our own. The provider knows what is left, and its
            # refusal is the only signal that cannot be wrong.
            try:
                if slugs:
                    via_yc += 1
                    source_url = yc_page.page_url(company["source_key"])
                    for slug in slugs:
                        person = None
                        if use_pdl:
                            person = pdl.enrich_person(slug, settings.pdl)
                            calls += 1
                        batch.append(_from_slug(company["id"], slug, source_url, person))
                        matched += bool(person)

                elif use_pdl and (domain := _domain(company["website"])):
                    people = pdl.search_founders(
                        domain, settings.pdl, size=SEARCH_PAGE_SIZE
                    )
                    calls += 1
                    if people:
                        via_search += 1
                        matched += len(people)
                        batch += [
                            _from_search(company["id"], person, company["website"])
                            for person in people
                        ]
            except pdl.AccountExhausted as exc:
                log.warning("pdl account exhausted: %s", exc)
                stopped = "account_exhausted"

            found += len(batch)
            company_added, company_updated = founders_repo.upsert(conn, batch)
            added += company_added
            updated += company_updated
            conn.commit()   # keep what this company bought, whatever happens next

            if stopped == "account_exhausted":
                break

        total = founders_repo.count(conn)
        total_matched = founders_repo.count_matched(conn)

    return EnrichReport(
        companies=len(companies),
        skipped_existing=skipped,
        via_yc_page=via_yc,
        via_pdl_search=via_search,
        founders_found=found,
        pdl_calls=calls,
        pdl_matched=matched,
        added=added,
        updated=updated,
        stopped=stopped,
        total_founders=total,
        total_matched=total_matched,
    )
