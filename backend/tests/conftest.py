"""Shared fixtures. No test touches the network or the real database."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.config import Settings
from pipeline.db import connect

# Trimmed copies of real API responses, so parsing is tested against the
# shapes the sources actually return.

YC_PAYLOAD = {
    "page": 1,
    "totalPages": 1,
    "companies": [
        {
            "id": 30368,
            "slug": "browser-use",
            "name": "Browser Use",
            "oneLiner": "Leading open-source web agent project",
            "longDescription": "Make websites accessible for AI agents.",
            "website": "https://www.browser-use.com",
            "batch": "W25",
            "teamSize": 4,
            "status": "Active",
            "industries": ["B2B", "Engineering"],
        },
        {
            "id": 30369,
            "slug": "red-barn-robotics",
            "name": "Red Barn Robotics",
            "oneLiner": "A Roomba for weeds on a farm.",
            "longDescription": "Autonomous weeding robot.",
            "website": "https://www.redbarnrobotics.com",
            "batch": "W25",
            "teamSize": 5,
            "status": "Active",
            "industries": ["Industrials"],
        },
    ],
}

HN_PAYLOAD = {
    "nbPages": 1,
    "hits": [
        {
            "objectID": "43173378",
            "title": "Launch HN: Browser Use (YC W25) - Open-source web agent",
            "url": "https://browser-use.com",
            "points": 259,
            "num_comments": 120,
            "author": "MagMueller",
        },
        {
            # Text post: no URL. These are real companies and must survive.
            "objectID": "44100001",
            "title": "Launch HN: AgentMail (YC S25) - An API that gives agents an inbox",
            "url": None,
            "points": 169,
            "num_comments": 169,
            "author": "haakon",
        },
        {
            "objectID": "44100002",
            "title": "Show HN: Semble - Code search for agents",
            "url": "https://semble.dev",
            "points": 445,
            "num_comments": 151,
            "author": "someone",
        },
    ],
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at a temporary database."""
    return Settings(db_path=tmp_path / "test.db")


@pytest.fixture
def conn(settings: Settings):
    """An open connection to an empty, schema-applied database."""
    with connect(settings.db_path) as connection:
        yield connection


@pytest.fixture
def stub_sources(monkeypatch):
    """Replace both fetchers with the fixture payloads, so no test hits the network.

    Returns the list of source names that were called, in order.
    """
    from pipeline import sync as sync_module
    from pipeline.sources import hackernews, yc

    calls: list[str] = []

    def fake_yc(batches, limit=None):
        calls.append("yc")
        companies = yc.parse([YC_PAYLOAD])
        return companies[:limit] if limit else companies

    def fake_hn(queries, min_points, lookback_days, limit=None):
        calls.append("hn")
        companies = hackernews.parse([HN_PAYLOAD])
        return companies[:limit] if limit else companies

    monkeypatch.setattr(sync_module.yc, "fetch", fake_yc)
    monkeypatch.setattr(sync_module.hackernews, "fetch", fake_hn)
    return calls
