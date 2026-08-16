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
    industries: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    stories: list["HNStory"] = field(default_factory=list, repr=False)

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
            "industries": json.dumps(self.industries, ensure_ascii=False),
            "raw_json": json.dumps(self.raw, ensure_ascii=False),
        }



@dataclass(frozen=True, slots=True)
class HNStory:
    """One Hacker News post. Several can belong to the same company."""

    story_id: str
    title: str
    url: str | None = None
    points: int | None = None
    comments: int | None = None
    posted_at: str | None = None
    author: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_row(self, company_id: int) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "story_id": self.story_id,
            "title": self.title,
            "url": self.url,
            "points": self.points,
            "comments": self.comments,
            "posted_at": self.posted_at,
            "author": self.author,
            "raw_json": json.dumps(self.raw, ensure_ascii=False),
        }


@dataclass(frozen=True, slots=True)
class Founder:
    """One person named as a founder of one company."""

    company_id: int
    linkedin_slug: str
    source_url: str                  # the page that named them; every claim cites this
    discovered_via: str = "yc_page"  # 'yc_page' (authoritative) | 'pdl_search' (inferred)
    name: str | None = None
    pdl_matched: bool = False
    current_title: str | None = None
    current_company: str | None = None
    prior_roles: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def display_name(self) -> str:
        """PDL name when matched, otherwise the slug made readable."""
        return self.name or self.linkedin_slug.replace("-", " ").title()

    def to_row(self) -> dict[str, Any]:
        """Column values for repository.founders.upsert()."""
        return {
            "company_id": self.company_id,
            "linkedin_slug": self.linkedin_slug,
            "name": self.display_name,
            "source_url": self.source_url,
            "discovered_via": self.discovered_via,
            "pdl_matched": int(self.pdl_matched),
            "current_title": self.current_title,
            "current_company": self.current_company,
            "prior_roles_json": json.dumps(self.prior_roles, ensure_ascii=False),
            "raw_json": json.dumps(self.raw, ensure_ascii=False),
        }


@dataclass(frozen=True, slots=True)
class HNComment:
    """One comment in a launch thread. `is_op` marks the submitter's own words."""

    story_id: str
    comment_id: str
    text: str
    author: str | None = None
    is_op: bool = False
    posted_at: str | None = None

    @property
    def permalink(self) -> str:
        """Citable source for anything quoted from this comment."""
        return f"https://news.ycombinator.com/item?id={self.comment_id}"

    def to_row(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "comment_id": self.comment_id,
            "author": self.author,
            "text": self.text,
            "is_op": int(self.is_op),
            "posted_at": self.posted_at,
        }
