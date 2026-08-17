"""Launch-thread comments from the Algolia search API. No key needed.

    GET /api/v1/search?tags=comment,story_<id>

Founders answer questions in their own thread — where they worked, why the
problem is solvable now, who is using it. That is the only free place a founder
speaks for themselves, and every comment has a permalink, so a claim taken from
one is citable.

Comments written by the story's submitter are marked `is_op`. Those are the
ones metric 1's fallback tier and metric 4 read.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..http import get_json
from ..models import HNComment
from ..normalize import plain_text

log = logging.getLogger(__name__)

BASE_URL = "https://hn.algolia.com/api/v1/search"
PER_STORY = 100          # Algolia's page size; one page is plenty per thread
MIN_LENGTH = 40          # "Congrats!" is not evidence
MAX_LENGTH = 4000        # keep prompts bounded



def fetch(story_id: str, submitter: str | None = None) -> list[HNComment]:
    """Every usable comment on one story. Free, one request.

    Very short comments are dropped — they are congratulation noise, and they
    would only dilute the prompt.
    """
    query = urllib.parse.urlencode({
        "tags": f"comment,story_{story_id}",
        "hitsPerPage": PER_STORY,
    })
    payload = get_json(f"{BASE_URL}?{query}")

    comments: list[HNComment] = []
    for hit in payload.get("hits") or []:
        text = plain_text(hit.get("comment_text"))
        if len(text) < MIN_LENGTH:
            continue
        author = hit.get("author")
        comments.append(HNComment(
            story_id=story_id,
            comment_id=str(hit.get("objectID")),
            text=text[:MAX_LENGTH],
            author=author,
            is_op=bool(submitter and author == submitter),
            posted_at=(hit.get("created_at") or "")[:10] or None,
        ))

    log.info("hn thread %s: %s comments, %s from the submitter",
             story_id, len(comments), sum(c.is_op for c in comments))
    return comments


def fetch_many(
    stories: list[tuple[str, str | None]], workers: int = 8
) -> dict[str, list[HNComment]]:
    """Fetch several threads at once. `stories` is (story_id, submitter) pairs.

    The work is network-bound, so a small pool turns a 13-minute backfill into
    about two. Results come back keyed by story id and are written by the
    caller on a single thread — a SQLite connection is not safe to share.

    A thread that fails is skipped rather than failing the run; it stays
    unfetched and the next sync retries it.
    """
    results: dict[str, list[HNComment]] = {}

    def one(pair: tuple[str, str | None]) -> tuple[str, list[HNComment]]:
        story_id, submitter = pair
        try:
            return story_id, fetch(story_id, submitter)
        except Exception as exc:  # noqa: BLE001 - one bad thread must not stop the rest
            log.warning("hn thread %s failed: %s", story_id, exc)
            return story_id, []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for story_id, comments in pool.map(one, stories):
            if comments:
                results[story_id] = comments

    return results
