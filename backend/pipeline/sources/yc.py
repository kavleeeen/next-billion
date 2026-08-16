"""Y Combinator company directory.

Undocumented but public and stable:
    GET https://api.ycombinator.com/v0.1/companies?batch=W25&page=2
Returns {"companies": [...], "page", "nextPage", "totalPages"}. No key needed.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
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
        # YC's own tagging. Direct input to metric 3, and free — it was already
        # in the payload, just never pulled out.
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


def _page(batch: str, page: int) -> dict[str, Any]:
    return get_json(f"{BASE_URL}?batch={batch}&page={page}")


def fetch(
    batches: tuple[str, ...], limit: int | None = None, workers: int = 8
) -> list[Company]:
    """Pull every page of each batch. Called by sync().

    Two waves. The first page of each batch is fetched concurrently and also
    reports `totalPages`; every remaining page across every batch is then
    fetched in one concurrent wave. Pagination is a known range once page 1 is
    in hand, so there is no reason to walk it one request at a time.
    """
    with ThreadPoolExecutor(max_workers=workers) as pool:
        firsts = list(pool.map(lambda b: (b, _page(b, 1)), batches))

        payloads = [payload for _, payload in firsts if payload.get("companies")]
        if limit and len(parse(payloads)) >= limit:
            return parse(payloads)[:limit]

        rest = [
            (batch, page)
            for batch, payload in firsts
            for page in range(2, min(payload.get("totalPages") or 1, MAX_PAGES) + 1)
        ]
        log.info("yc: %s batches, %s further pages", len(batches), len(rest))
        payloads += [p for p in pool.map(lambda bp: _page(*bp), rest) if p.get("companies")]

    companies = parse(payloads)
    return companies[:limit] if limit else companies
