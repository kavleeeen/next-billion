"""The one record every source must produce."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .normalize import looks_like_company_name


@dataclass(frozen=True, slots=True)
class Company:
    source: str                      # 'yc' | 'hn'
    source_key: str                  # yc slug, or hn story id
    name: str
    website: str | None = None
    one_liner: str | None = None
    description: str | None = None
    batch: str | None = None
    team_size: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_usable(self) -> bool:
        """Whether sync() should store this record.

        Rejects sentence-like names ("I built a voice agent"). A missing website
        does NOT reject: Launch HN text posts are real companies (Onyx, AgentMail).
        """
        return looks_like_company_name(self.name)

    def to_row(self) -> dict[str, Any]:
        """Column values for repository.companies.upsert()."""
        return {
            "source": self.source,
            "source_key": self.source_key,
            "name": self.name.strip(),
            "website": self.website,
            "one_liner": self.one_liner,
            "description": self.description,
            "batch": self.batch,
            "team_size": self.team_size,
            "raw_json": json.dumps(self.raw, ensure_ascii=False),
        }

