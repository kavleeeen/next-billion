"""People Data Labs person enrichment, keyed on a LinkedIn slug.

This is the only paid dependency in the project. The free plan allows 100
lookups a month, so callers must budget: `enrich()` counts every call and stops
at settings.pdl.max_calls_per_run.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ..config import PDLSettings
from ..http import FetchError, get_json

log = logging.getLogger(__name__)


class MissingToken(RuntimeError):
    """Raised when no PDL key is configured."""


def enrich_person(linkedin_slug: str, settings: PDLSettings) -> dict[str, Any] | None:
    """One lookup. Returns the person record, or None when PDL has no match.

    Costs one credit per call. A 404 (no match) is a normal result.
    """
    if not settings.token:
        raise MissingToken(
            f"{settings.token_env} is not set. Put it in .env at the repo root."
        )

    profile = urllib.parse.quote(f"linkedin.com/in/{linkedin_slug}")
    try:
        payload = get_json(
            f"{settings.base_url}?profile={profile}",
            headers={"X-Api-Key": settings.token},
        )
    except FetchError as exc:
        log.warning("pdl %s -> %s", linkedin_slug, exc)
        return None

    if payload.get("status") != 200:
        log.info("pdl %s -> no match", linkedin_slug)
        return None

    return payload.get("data")


def prior_roles(person: dict[str, Any]) -> list[dict[str, str | None]]:
    """Past positions, most recent first, excluding the current one.

    This is what metric 1's primary tier scores: did they build this before?
    """
    roles = []
    for entry in person.get("experience") or []:
        if entry.get("is_primary"):
            continue
        company = entry.get("company") or {}
        title = entry.get("title") or {}
        roles.append({
            "title": title.get("name"),
            "company": company.get("name"),
            "start": entry.get("start_date"),
            "end": entry.get("end_date"),
        })
    return roles


SEARCH_URL = "https://api.peopledatalabs.com/v5/person/search"

# Server-side filter, not client-side. Measured on two companies:
#   browser-use.com  unfiltered 11 records, owner-level 2
#   composio.dev     unfiltered 61 records, owner-level 2
# Search bills per record returned, so filtering here is the difference between
# 2 credits and 61 for one company. It is also more precise: composio's first
# unfiltered result is a forward deployed engineer, not a founder.
FOUNDER_SQL = (
    "SELECT * FROM person "
    "WHERE job_company_website = '{domain}' AND job_title_levels = 'owner'"
)


def search_founders(
    domain: str, settings: PDLSettings, size: int = 3
) -> list[dict[str, Any]]:
    """Founders at a company, found by its website domain.

    Used for companies with no YC page. Costs one credit per record returned,
    so `size` is the per-company ceiling.
    """
    if not settings.token:
        raise MissingToken(
            f"{settings.token_env} is not set. Put it in .env at the repo root."
        )

    query = urllib.parse.urlencode({
        "sql": FOUNDER_SQL.format(domain=domain.replace("'", "")),
        "size": size,
    })
    try:
        payload = get_json(
            f"{SEARCH_URL}?{query}", headers={"X-Api-Key": settings.token}
        )
    except FetchError as exc:
        log.warning("pdl search %s -> %s", domain, exc)
        return []

    if payload.get("status") != 200:
        log.info("pdl search %s -> no match", domain)
        return []

    return payload.get("data") or []
