"""Paths and tunable defaults; nothing else hardcodes them.

Values that change between runs live here. Facts about an API (base URL, page
size) stay in its source module. Secrets never live here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# backend/pipeline/config.py -> repo root
ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Copy KEY=value lines from .env into os.environ, without overwriting.

    Runs once on import. Keeps secrets out of the repo and avoids a dependency
    on python-dotenv for what is six lines.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()


@dataclass(frozen=True)
class YCSettings:
    """The topic filters the directory now, so there is no default batch list.
    `sync --batch W25` still narrows, for the "a feed like YC W25" seed input."""


@dataclass(frozen=True)
class HNSettings:
    lookback_days: int = 365   # first run only; later runs start from the newest story held

    comment_workers: int = 8   # writes stay serial; a SQLite connection is not shareable


@dataclass(frozen=True)
class PDLSettings:
    """People Data Labs. The provider counts the allowance and refuses with a
    402 when it ends, so we keep no count of our own. Every response is stored
    on the founder row and never fetched twice."""

    token_env: str = "PDL_API_KEY"
    base_url: str = "https://api.peopledatalabs.com/v5/person/enrich"

    @property
    def token(self) -> str | None:
        """Read at call time so .env loaded later still works."""
        return os.environ.get(self.token_env)


@dataclass(frozen=True)
class GitHubSettings:
    """Public API, no key required. A selection of 15 costs about 45 requests
    and the anonymous limit is 60 an hour; a token raises it to 5000."""

    token_env: str = "GITHUB_TOKEN"
    base_url: str = "https://api.github.com"
    timeout: float = 20.0
    # Tier 3 costs two extra requests for each candidate. Turn it off to keep a
    # run inside the anonymous limit when a selection is large.
    search_orgs: bool = True

    @property
    def token(self) -> str | None:
        """Optional. Absent means the anonymous limit applies."""
        return os.environ.get(self.token_env)


@dataclass(frozen=True)
class GeminiSettings:
    """Google AI Studio, free tier. Pro has no free tier at all, and every full
    Flash model allows only 20 requests a day, which one run would spend.
    Flash Lite allows 500 a day and 15 a minute. See
    docs/decisions/0005-selection-cap-of-fifteen.md."""

    token_env: str = "GEMINI_API_KEY"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    # One model for a whole run, so the companies stay comparable. The same
    # evidence scores differently on different models, thus a mixed run cannot
    # be ranked. Each model has its own budget, per project.
    model: str = "gemini-3.5-flash-lite"

    temperature: float = 0.0
    # A scoring call thinks before it answers, so it outlives the 20s used for
    # plain data fetches.
    timeout: float = 120.0
    # The model accepts 15 requests a minute. Pace below that rather than
    # discover the ceiling: a refusal costs a request and returns nothing.
    requests_per_minute: int = 12
    # The pacer sets the rate; the workers only overlap the waiting.
    workers: int = 2
    # Enough to outlast a per-minute window. A daily refusal is not retried at
    # all, so a bigger number cannot drain the day's allowance.
    retries: int = 4

    @property
    def token(self) -> str | None:
        """Read at call time so .env loaded later still works."""
        return os.environ.get(self.token_env)


@dataclass(frozen=True)
class Settings:
    db_path: Path = ROOT / "data" / "next-billion.db"

    http_timeout: float = 20.0
    http_retries: int = 3

    fetch_workers: int = 8   # network-bound, so concurrency buys latency, not CPU

    # How long collected evidence and a score stay fresh. Re-selecting a
    # company inside this window reuses what is stored instead of fetching.
    # Applies to free work only: PDL founders are never re-bought on a timer.
    refresh_after_hours: float = 1.0

    # One block per source.
    yc: YCSettings = field(default_factory=YCSettings)
    hn: HNSettings = field(default_factory=HNSettings)
    pdl: PDLSettings = field(default_factory=PDLSettings)
    github: GitHubSettings = field(default_factory=GitHubSettings)
    gemini: GeminiSettings = field(default_factory=GeminiSettings)

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
