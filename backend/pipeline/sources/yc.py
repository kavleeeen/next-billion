"""Y Combinator company directory.

Undocumented but public and stable:
    GET https://api.ycombinator.com/v0.1/companies?batch=W25&page=2
Returns {"companies": [...], "page", "nextPage", "totalPages"}. No key needed.
"""
from __future__ import annotations

import logging
from typing import Any

from ..http import get_json
from ..models import Company

log = logging.getLogger(__name__)

NAME = "yc"
BASE_URL = "https://api.ycombinator.com/v0.1/companies"
MAX_PAGES = 50  # backstop against a pagination bug looping forever


def _to_company(record: dict[str, Any]) -> Company:
    """Map one API record onto a Company. Called by parse() only."""
    return Company(
        source=NAME,
        source_key=str(record.get("slug") or record.get("id")),
        name=record.get("name") or "",
        website=record.get("website"),
        one_liner=record.get("oneLiner"),
        description=record.get("longDescription"),
        batch=record.get("batch"),
        team_size=record.get("teamSize"),
        # YC's own tagging, already in the payload. Input to metric 3.
        industries=record.get("industries") or [],
        raw=record,
    )


def parse(payloads: list[dict[str, Any]]) -> list[Company]:
    """Raw pages -> companies, deduped by slug. Called by fetch()."""
    companies: list[Company] = []
    seen: set[str] = set()

    for payload in payloads:
        for record in payload.get("companies") or []:
            company = _to_company(record)
            if company.source_key in seen:
                continue
            seen.add(company.source_key)
            companies.append(company)

    return companies


def fetch(batches: tuple[str, ...], limit: int | None = None) -> list[Company]:
    """Pull every page of each batch. Called by sync()."""
    payloads: list[dict[str, Any]] = []

    for batch in batches:
        page = 1
        while page <= MAX_PAGES:
            payload = get_json(f"{BASE_URL}?batch={batch}&page={page}")
            if not (payload.get("companies") or []):
                break

            payloads.append(payload)
            log.info("yc %s page %s: %s companies", batch, page, len(payload["companies"]))

            if limit and len(parse(payloads)) >= limit:
                return parse(payloads)[:limit]
            if page >= (payload.get("totalPages") or page):
                break
            page += 1

    return parse(payloads)
