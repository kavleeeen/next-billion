"""Paths and tunable defaults; nothing else hardcodes them.

Values that change between runs live here. Facts about an API (base URL, page
size) stay in its source module. Secrets never live here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# backend/pipeline/config.py -> repo root
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class YCSettings:
    batches: tuple[str, ...] = ("W25", "S25", "W26")


@dataclass(frozen=True)
class HNSettings:
    min_points: int = 30
    lookback_days: int = 365
    queries: tuple[str, ...] = ("agent", "LLM", "infrastructure", "developer tool")


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

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
