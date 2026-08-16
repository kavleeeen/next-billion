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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from datetime import datetime, timezone

from ..http import get_json
from ..models import Company, HNStory
from ..normalize import parse_hn_title

log = logging.getLogger(__name__)

NAME = "hn"
BASE_URL = "https://hn.algolia.com/api/v1/search"
PAGE_SIZE = 100
MAX_PAGES = 10

# Fields that only some posts carry. The highest-scoring post wins the name and
# one-liner, but these are merged across every post so a later, bigger launch
# cannot drop the batch or website an earlier one supplied.
CARRIED_FIELDS = ("batch", "website", "description")


def company_key(name: str) -> str:
    """Identity for an HN company: its name, normalised.

    A story id cannot be the identity — rowboat posted three times and would
    become three companies. Two genuinely different companies sharing a name
    would merge; that is the accepted cost.
    """
    return " ".join(name.lower().split())


def _to_story(hit: dict[str, Any]) -> HNStory:
    """One Algolia hit as a launch event."""
    return HNStory(
        story_id=str(hit.get("objectID")),
        title=hit.get("title") or "",
        url=hit.get("url"),
        points=hit.get("points"),
        comments=hit.get("num_comments"),
        posted_at=_posted_at(hit.get("created_at_i")),
        raw=hit,
    )


def _to_company(hit: dict[str, Any]) -> Company:
    """The company a hit refers to. Its stories are attached by parse()."""
    name, batch = parse_hn_title(hit.get("title") or "")
    return Company(
        source=NAME,
        source_key=company_key(name),
        name=name,
        website=hit.get("url"),      # None for text posts, which are still real companies
        one_liner=hit.get("title"),
        batch=batch,
        raw=hit,
    )


def _posted_at(epoch: int | None) -> str | None:
    """Unix seconds -> ISO date. Freshness for metric 2."""
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()


def parse(payloads: list[dict[str, Any]]) -> list[Company]:
    """Raw pages -> companies, each carrying every story that mentions it.

    Two levels of grouping happen here:
      * stories are deduped by story id, because the searches overlap
      * stories are grouped by company name, because one company can launch
        more than once — rowboat has three posts across eleven months

    The company keeps the details of its highest-scoring story, since that is
    the one a reader would recognise.
    """
    best: dict[str, tuple[int, Company]] = {}
    stories: dict[str, list[HNStory]] = {}
    carried: dict[str, dict[str, Any]] = {}
    seen_stories: set[str] = set()

    for payload in payloads:
        for hit in payload.get("hits") or []:
            story = _to_story(hit)
            if not story.story_id or story.story_id in seen_stories:
                continue
            seen_stories.add(story.story_id)

            company = _to_company(hit)
            key = company.source_key
            stories.setdefault(key, []).append(story)

            # Fields only some posts carry. A Show HN title has no batch, and a
            # text post has no url, so take the first non-empty value seen and
            # never let a later post erase it.
            slot = carried.setdefault(key, dict.fromkeys(CARRIED_FIELDS))
            for name in CARRIED_FIELDS:
                if slot[name] is None:
                    slot[name] = getattr(company, name)

            points = story.points or 0
            if key not in best or points > best[key][0]:
                best[key] = (points, company)

    return [
        replace(
            company,
            stories=stories[key],
            **{
                name: getattr(company, name) or carried[key][name]
                for name in CARRIED_FIELDS
            },
        )
        for key, (_, company) in best.items()
    ]


def _search(params: dict[str, str], limit: int | None) -> list[dict[str, Any]]:
    """Every page for one query. Sequential: the page count is only known after
    the first response."""
    payloads: list[dict[str, Any]] = []
    collected = 0

    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode({**params, "page": page, "hitsPerPage": PAGE_SIZE})
        payload = get_json(f"{BASE_URL}?{query}")
        hits = payload.get("hits") or []
        if not hits:
            break

        payloads.append(payload)
        collected += len(hits)
        if (limit and collected >= limit) or page + 1 >= (payload.get("nbPages") or 1):
            break

    return payloads


def fetch(
    queries: tuple[str, ...],
    min_points: int,
    lookback_days: int,
    limit: int | None = None,
    workers: int = 8,
) -> list[Company]:
    """Run every search and return deduped companies. Called by sync().

    The searches are independent, so they run concurrently.
    """
    since = int(time.time()) - lookback_days * 86_400
    numeric = f"points>{min_points},created_at_i>{since}"

    searches: list[dict[str, str]] = [
        {"query": '"Launch HN"', "tags": "story", "numericFilters": f"created_at_i>{since}"},
        *({"query": q, "tags": "show_hn", "numericFilters": numeric} for q in queries),
    ]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pages = list(pool.map(lambda p: _search(p, limit), searches))

    payloads = [payload for group in pages for payload in group]
    log.info("hn: %s searches, %s pages", len(searches), len(payloads))

    companies = parse(payloads)
    return companies[:limit] if limit else companies
