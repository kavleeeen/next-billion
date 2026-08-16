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
    lookback_days: int = 365
    queries: tuple[str, ...] = ("agent", "LLM", "infrastructure", "developer tool")


@dataclass(frozen=True)
class PDLSettings:
    """People Data Labs. The free plan allows 100 lookups a month, so every
    response is stored on the founder row and never fetched twice."""

    token_env: str = "PDL_API_KEY"
    base_url: str = "https://api.peopledatalabs.com/v5/person/enrich"
    # Ceiling for one run, so a single mistake cannot drain the allowance.
    max_calls_per_run: int = 25

    @property
    def token(self) -> str | None:
        """Read at call time so .env loaded later still works."""
        return os.environ.get(self.token_env)


@dataclass(frozen=True)
class Settings:
    db_path: Path = ROOT / "data" / "next-billion.db"

    http_timeout: float = 20.0
    http_retries: int = 3

    # One block per source. GitHub is in docs/decisions/0001-sources.md as an
    # accepted source but is not built yet, so it has no settings block here —
    # config describes what the code does, not what it will do.
    yc: YCSettings = field(default_factory=YCSettings)
    hn: HNSettings = field(default_factory=HNSettings)
    pdl: PDLSettings = field(default_factory=PDLSettings)

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
