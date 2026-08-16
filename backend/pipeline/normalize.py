"""Small pure functions. No I/O, so they are cheap to test."""
from __future__ import annotations

import re

_HN_PREFIX = re.compile(r"^\s*(launch|show)\s+hn\s*:\s*", re.I)
# Batch codes are not only W/S/F. Real data contains P26, X25 too.
_BATCH = re.compile(r"\(\s*YC\s+([A-Z]\d{2})\s*\)", re.I)
_SEPARATOR = re.compile(r"\s+[–—-]\s+|\s*:\s+|\s{2,}")

# A Show HN title is often a sentence, not a company: "I built a sub-500ms
# voice agent from scratch". These bounds come from the real distribution of
# parsed Launch HN names: median 9 characters, 90th percentile 17, longest
# genuine name 29.
MAX_NAME_CHARS = 40
MAX_NAME_WORDS = 6
_SENTENCE_START = re.compile(
    r"^(i|we|my|our|you|your|how|why|what|when|introducing|building|making|"
    r"show|ask|help|looking|trying|just)\b",
    re.I,
)


def parse_hn_title(title: str) -> tuple[str, str | None]:
    """'Launch HN: RunAnywhere (YC W26) - Faster inference' -> ('RunAnywhere', 'W26').

    Called by sources.hackernews._to_company. Falls back to the whole cleaned
    title when the post has no recognisable company name; looks_like_company_name
    then rejects those.
    """
    text = _HN_PREFIX.sub("", title or "").strip()

    batch = None
    if match := _BATCH.search(text):
        batch = match.group(1).upper()
        text = _BATCH.sub("", text).strip()

    name = _SEPARATOR.split(text, maxsplit=1)[0].strip(" -–—:")
    return (name or text.strip(), batch)


def looks_like_company_name(name: str) -> bool:
    """False when a parsed title is a sentence rather than a company name.

    Called by Company.is_usable. The rejected count is the gap between `fetched`
    and `usable` in the sync report.
    """
    stripped = (name or "").strip()
    if not stripped:
        return False
    if len(stripped) > MAX_NAME_CHARS or len(stripped.split()) > MAX_NAME_WORDS:
        return False
    return not _SENTENCE_START.match(stripped)
