"""Y Combinator company directory.

Undocumented but public and stable:
    GET https://api.ycombinator.com/v0.1/companies?batch=W25&page=2&q=agents
Returns {"companies": [...], "page", "nextPage", "totalPages"}. No key needed.

`q` is the directory's own search, and the partner's topic goes there. See
docs/decisions/0015-the-topic-decides-what-we-collect.md.
"""
from __future__ import annotations

import logging
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..http import get_json
from ..pacing import Pacer
from .coverage import Coverage
from ..models import Company

log = logging.getLogger(__name__)

NAME = "yc"
BASE_URL = "https://api.ycombinator.com/v0.1/companies"
# `q=agents` alone reports 50 pages, so this is a real ceiling for ordinary
# topics, not just a runaway-loop backstop. Coverage reports when it bites.
MAX_PAGES = 50

# Undocumented and unauthenticated, so we do not hammer it.
REQUESTS_PER_MINUTE = 300
PACER = Pacer()


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


ALL_BATCHES = ""   # no batch parameter: the whole directory


def _page(batch: str, page: int, topic: str) -> dict[str, Any]:
    """One page of the directory, narrowed by the topic and maybe a batch.

    `q` is the directory's own search. Undocumented like the rest of this API,
    but it filters: `q=agents` returns 50 pages where an unfiltered call
    returns 248.
    """
    params = {"page": page, "q": topic}
    if batch:
        params["batch"] = batch
    PACER.wait(REQUESTS_PER_MINUTE)
    return get_json(f"{BASE_URL}?{urllib.parse.urlencode(params)}")


def fetch(
    topic: str,
    batches: tuple[str, ...] = (),
    limit: int | None = None,
    workers: int = 8,
) -> tuple[list[Company], Coverage]:
    """Every company matching the topic. Called by sync().

    No batches searches the whole directory, which is what a topic asks for.
    Naming batches narrows to them, for the "a feed like YC W25" seed input.

    Two waves. The first page of each batch is fetched concurrently and also
    reports `totalPages`; every remaining page across every batch is then
    fetched in one concurrent wave. Pagination is a known range once page 1 is
    in hand, so there is no reason to walk it one request at a time.
    """
    with ThreadPoolExecutor(max_workers=workers) as pool:
        wanted = batches or (ALL_BATCHES,)
        firsts = list(pool.map(lambda b: (b, _page(b, 1, topic)), wanted))

        payloads = [payload for _, payload in firsts if payload.get("companies")]

        # The directory counts pages, not companies, so coverage is in pages.
        offered = sum(payload.get("totalPages") or 1 for _, payload in firsts)
        reachable = sum(min(payload.get("totalPages") or 1, MAX_PAGES)
                        for _, payload in firsts)
        coverage = Coverage(read=reachable, available=offered)

        if limit and len(parse(payloads)) >= limit:
            return parse(payloads)[:limit], coverage

        rest = [
            (batch, page)
            for batch, payload in firsts
            for page in range(2, min(payload.get("totalPages") or 1, MAX_PAGES) + 1)
        ]
        where = ", ".join(batches) if batches else "whole directory"
        log.info("yc: %r in %s, %s of %s pages", topic, where, reachable, offered)
        if coverage.truncated:
            log.warning("%s", coverage.describe("yc"))
        payloads += [p for p in pool.map(lambda bp: _page(*bp, topic), rest)
                     if p.get("companies")]

    companies = parse(payloads)
    return (companies[:limit] if limit else companies), coverage
