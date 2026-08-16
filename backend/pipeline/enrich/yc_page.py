"""Founder LinkedIn URLs from a Y Combinator company page.

The YC API returns no founders, but the company page publishes each founder's
LinkedIn URL. Measured coverage: 9 of 9 companies, 19 founders.

We take only the slug from the URL. LinkedIn itself is never fetched — its
terms forbid automated access, and the slug plus the YC page is enough to
identify a founder and cite where that came from.
"""
from __future__ import annotations

import logging
import re

from ..http import get_text

log = logging.getLogger(__name__)

PAGE_URL = "https://www.ycombinator.com/companies/{slug}"
_LINKEDIN = re.compile(r"linkedin\.com/in/([A-Za-z0-9\-_%]+)")

# LinkedIn slugs that belong to YC itself, not to a founder.
_NOT_A_FOUNDER = {"ycombinator", "y-combinator"}


def page_url(company_slug: str) -> str:
    """The citable source URL for anything found on this page."""
    return PAGE_URL.format(slug=company_slug)


def founder_slugs(company_slug: str) -> list[str]:
    """LinkedIn slugs for a company's founders, in page order, deduped.

    Returns [] when the page is missing or lists no founders — a normal
    outcome, not an error.
    """
    html = get_text(page_url(company_slug))
    if not html:
        return []

    slugs = [
        slug for slug in dict.fromkeys(_LINKEDIN.findall(html))
        if slug.lower() not in _NOT_A_FOUNDER
    ]
    log.info("yc page %s: %s founder slugs", company_slug, len(slugs))
    return slugs
