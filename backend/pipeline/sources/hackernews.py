"""Hacker News via the Algolia search API. No key needed.

Two pools, used for different jobs:
    Launch HN - low volume, high precision. Every post is a funded company.
    Show HN   - high volume, low precision. Catches non-YC and unfunded companies.

Several searches run per sync and their results overlap: one Show HN story can
match both "agent" and "LLM". parse() deduplicates, which removes about 190
duplicate records out of 928 on a full run.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any, Iterator

from ..http import get_json
from ..models import Company
from ..normalize import parse_hn_title

log = logging.getLogger(__name__)

NAME = "hn"
BASE_URL = "https://hn.algolia.com/api/v1/search"
PAGE_SIZE = 100
MAX_PAGES = 10


def _to_company(hit: dict[str, Any]) -> Company:
    """Map one Algolia hit onto a Company; the title carries name and batch."""
    name, batch = parse_hn_title(hit.get("title") or "")
    return Company(
        source=NAME,
        source_key=str(hit.get("objectID")),
        name=name,
        website=hit.get("url"),      # None for text posts, which are still real companies
        one_liner=hit.get("title"),
        batch=batch,
        raw=hit,
    )


def parse(payloads: list[dict[str, Any]]) -> list[Company]:
    """Raw pages -> companies, deduped by story id. Called by fetch().

    The searches overlap, so without this the same story is stored more than once.
    """
    companies: list[Company] = []
    seen: set[str] = set()

    for payload in payloads:
        for hit in payload.get("hits") or []:
            company = _to_company(hit)
            if company.source_key in seen:
                continue
            seen.add(company.source_key)
            companies.append(company)

    return companies


def _search(params: dict[str, str], limit: int | None) -> Iterator[dict[str, Any]]:
    """Yield one raw page at a time for a single Algolia query. Used by fetch()."""
    collected = 0
    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode({**params, "page": page, "hitsPerPage": PAGE_SIZE})
        payload = get_json(f"{BASE_URL}?{query}")
        hits = payload.get("hits") or []
        if not hits:
            return

        yield payload
        collected += len(hits)
        if (limit and collected >= limit) or page + 1 >= (payload.get("nbPages") or 1):
            return
        time.sleep(0.2)  # the API asks for no key; do not hammer it


def fetch(
    queries: tuple[str, ...],
    min_points: int,
    lookback_days: int,
    limit: int | None = None,
) -> list[Company]:
    """Run every search and return deduped companies. Called by sync()."""
    since = int(time.time()) - lookback_days * 86_400
    numeric = f"points>{min_points},created_at_i>{since}"

    searches: list[dict[str, str]] = [
        {"query": '"Launch HN"', "tags": "story", "numericFilters": f"created_at_i>{since}"},
        *({"query": q, "tags": "show_hn", "numericFilters": numeric} for q in queries),
    ]

    payloads: list[dict[str, Any]] = []
    for params in searches:
        for payload in _search(params, limit):
            payloads.append(payload)

        log.info("hn %r: %s distinct stories so far", params["query"], len(parse(payloads)))
        if limit and len(parse(payloads)) >= limit:
            return parse(payloads)[:limit]

    return parse(payloads)
