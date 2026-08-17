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
    batches: tuple[str, ...] = ("W25", "S25", "W26")


@dataclass(frozen=True)
class HNSettings:
    min_points: int = 30
    lookback_days: int = 365   # first run only; later runs start from the newest story held
    refresh_days: int = 7      # re-read this far back, so recent points stay current

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
class Settings:
    db_path: Path = ROOT / "data" / "next-billion.db"

    http_timeout: float = 20.0
    http_retries: int = 3

    fetch_workers: int = 8   # network-bound, so concurrency buys latency, not CPU

    # How long collected evidence stays fresh. Re-selecting a company inside
    # this window reuses what is stored instead of fetching it again. Applies
    # to free work only: PDL founders are never re-bought on a timer.
    refresh_after_hours: float = 1.0

    # One block per source.
    yc: YCSettings = field(default_factory=YCSettings)
    hn: HNSettings = field(default_factory=HNSettings)
    pdl: PDLSettings = field(default_factory=PDLSettings)
    github: GitHubSettings = field(default_factory=GitHubSettings)

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
