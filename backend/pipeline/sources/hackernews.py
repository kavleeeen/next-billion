"""Hacker News via the Algolia search API. No key needed.

Two pools, used for different jobs:
    Launch HN - low volume, high precision. Every post is a funded company.
    Show HN   - high volume, low precision. Catches non-YC and unfunded companies.

No topic filter. Four keyword searches returned 509 stories where an unfiltered
Show HN search returns 1,820 — an editorial guess made at fetch time and
invisible afterwards. The thesis gate decides that later, by a stated rule.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

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
        author=hit.get("author"),
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


def since_epoch(newest_stored: str | None, lookback_days: int, refresh_days: int) -> int:
    """The `created_at_i` floor for this run.

    Starts before the newest story held, not at it: points keep rising after a
    post appears, so a strictly-newer floor would freeze traction.
    """
    if not newest_stored:
        return int(time.time()) - lookback_days * 86_400
    try:
        seen = datetime.fromisoformat(newest_stored).replace(tzinfo=timezone.utc)
    except ValueError:
        return int(time.time()) - lookback_days * 86_400
    return int(seen.timestamp()) - refresh_days * 86_400


def fetch(
    min_points: int,
    since: int,
    limit: int | None = None,
    workers: int = 8,
) -> list[Company]:
    """Both searches, from `since` onward. Called by sync().

    Independent, so they run concurrently; parse() deduplicates the overlap.
    """
    searches: list[dict[str, str]] = [
        {"query": '"Launch HN"', "tags": "story",
         "numericFilters": f"created_at_i>{since}"},
        {"tags": "show_hn",
         "numericFilters": f"points>{min_points},created_at_i>{since}"},
    ]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pages = list(pool.map(lambda p: _search(p, limit), searches))

    payloads = [payload for group in pages for payload in group]
    log.info("hn: %s searches, %s pages, since %s", len(searches), len(payloads), since)

    companies = parse(payloads)
    return companies[:limit] if limit else companies
