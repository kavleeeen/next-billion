"""Hacker News via the Algolia search API. No key needed.

Two pools, treated differently because their sizes differ by 3,500x:

    Launch HN  119 a year. Taken whole; the thesis gate decides relevance.
    Show HN    418,048 a year. Bounded by the partner's topic.

Show HN has no points filter. See
docs/decisions/0015-the-topic-decides-what-we-collect.md.
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
from ..pacing import Pacer
from .coverage import Coverage
from ..models import Company, HNStory
from ..normalize import parse_hn_title, plain_text

log = logging.getLogger(__name__)

NAME = "hn"
BASE_URL = "https://hn.algolia.com/api/v1/search"
PAGE_SIZE = 100
MAX_PAGES = 10          # Algolia refuses page*hitsPerPage above 1000 anyway

# No key is asked for, so we do not hammer it. One pacer for the module: the
# limit belongs to the address, not to a worker. See docs/decisions/0008.
REQUESTS_PER_MINUTE = 300
PACER = Pacer()

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
        # The founder's own launch post. A title is 61 characters; this is the
        # only real description an HN company has, and it arrives in the same
        # response. See docs/decisions/0016-the-launch-post-is-the-description.md.
        description=plain_text(hit.get("story_text")) or None,
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


def _search(
    params: dict[str, str], limit: int | None
) -> tuple[list[dict[str, Any]], Coverage]:
    """Every page for one query, and how much of the match we reached.

    Sequential: the page count is only known after the first response.
    """
    payloads: list[dict[str, Any]] = []
    collected = available = 0

    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode({**params, "page": page, "hitsPerPage": PAGE_SIZE})
        PACER.wait(REQUESTS_PER_MINUTE)
        payload = get_json(f"{BASE_URL}?{query}")
        hits = payload.get("hits") or []
        available = payload.get("nbHits") or available
        if not hits:
            break

        payloads.append(payload)
        collected += len(hits)
        if (limit and collected >= limit) or page + 1 >= (payload.get("nbPages") or 1):
            break

    return payloads, Coverage(read=collected, available=available)


def since_epoch(lookback_days: int) -> int:
    """The `created_at_i` floor for this run.

    Always the full window. An earlier version started from the newest story
    held, which was cheap for one repeated broad sync but wrong here: each
    topic is a new question, and a floor set by the last topic hides every
    older post that answers this one.
    """
    return int(time.time()) - lookback_days * 86_400


def fetch(
    topic: str,
    since: int,
    limit: int | None = None,
    workers: int = 8,
) -> tuple[list[Company], Coverage]:
    """Both searches, from `since` onward. Called by sync().

    Independent, so they run concurrently; parse() deduplicates the overlap.
    The topic bounds Show HN only: Launch HN is 119 posts a year, and asking a
    topic of it returns 8, which throws away companies for no gain.
    """
    if not topic.strip():
        raise ValueError("sync needs a topic; it decides what we collect")

    searches: list[dict[str, str]] = [
        {"query": '"Launch HN"', "tags": "story",
         "numericFilters": f"created_at_i>{since}"},
        {"query": topic, "tags": "show_hn",
         "numericFilters": f"created_at_i>{since}"},
    ]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: _search(p, limit), searches))

    payloads = [payload for group, _ in results for payload in group]
    coverage = Coverage(
        read=sum(c.read for _, c in results),
        available=sum(c.available for _, c in results),
    )
    log.info("hn: topic %r, %s pages, %s of %s matches, since %s",
             topic, len(payloads), coverage.read, coverage.available, since)
    if coverage.truncated:
        log.warning("%s", coverage.describe("hn"))

    companies = parse(payloads)
    return (companies[:limit] if limit else companies), coverage
