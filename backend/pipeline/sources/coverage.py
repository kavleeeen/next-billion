"""How much of what a source offered we actually read.

Every fetcher stops at a page cap. A cap that is silent is the same defect
`0015` removed from the points filter: an editorial cut made at fetch time and
invisible afterwards. `ai` matches 14,860 Show HN posts and we read 1,000 of
them; a partner has to be told that, not left to assume they saw everything.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Coverage:
    read: int
    available: int

    @property
    def truncated(self) -> bool:
        return self.available > self.read

    @property
    def share(self) -> float:
        """Fraction read, 0.0 to 1.0. Zero available counts as complete."""
        return 1.0 if self.available <= 0 else min(self.read / self.available, 1.0)

    def describe(self, source: str) -> str:
        """One line for the sync report, or empty when nothing was cut."""
        if not self.truncated:
            return ""
        return (
            f"{source}: topic too broad — read {self.read:,} of {self.available:,} "
            f"({self.share:.0%}). Narrow it to see the rest."
        )

    @classmethod
    def whole(cls, read: int) -> "Coverage":
        return cls(read=read, available=read)
