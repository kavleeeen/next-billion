"""Build the scoring prompt, and the schema its reply must satisfy.

The anchors are not copied into the template. They are read out of THESIS.md at
build time, so the wording the model scores against is the wording in the
document. Editing one edits both.

The response schema lives here and not with the client, because it mirrors the
Output section of the template. The two must change together.
"""
from __future__ import annotations

import re

from ..config import ROOT
from ..evidence import Bundle
from .thesis import METRIC_KEYS

THESIS_PATH = ROOT / "THESIS.md"
TEMPLATE_PATH = ROOT / "prompts" / "score_company.v1.md"

# Written on every analyses row, and part of the cache key. A new template is a
# new file and a new version, so an old score is never confused for a new one.
VERSION = "v1"

_HEADING = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.M)


def _sections(doc: str) -> list[tuple[int, str, int, int]]:
    """(level, title, body start, body end) for every heading in the document."""
    marks = [(len(m.group(1)), m.group(2), m.start(), m.end()) for m in _HEADING.finditer(doc)]
    out = []
    for index, (level, title, start, body_start) in enumerate(marks):
        end = len(doc)
        for later_level, _, later_start, _ in marks[index + 1:]:
            if later_level <= level:
                end = later_start
                break
        out.append((level, title, start, end))
    return out


def _section(doc: str, title: str, *, with_heading: bool = True) -> str:
    """One section by exact heading text, including its subsections."""
    for _, found, start, end in _sections(doc):
        if found == title:
            block = doc[start:end] if with_heading else doc[doc.index("\n", start):end]
            return block.strip()
    raise KeyError(f"THESIS.md has no section titled {title!r}")


def _between(doc: str, first: str, stop: str) -> str:
    """From one heading up to another. Used for the run of five anchor tables."""
    positions = {title: (start, end) for _, title, start, end in _sections(doc)}
    if first not in positions or stop not in positions:
        raise KeyError(f"THESIS.md is missing {first!r} or {stop!r}")
    return doc[positions[first][0]:positions[stop][0]].strip()


def thesis_parts(doc: str | None = None) -> dict[str, str]:
    """The three blocks the template asks for, taken from THESIS.md."""
    doc = THESIS_PATH.read_text(encoding="utf-8") if doc is None else doc
    return {
        "THESIS_BET": _section(doc, "The bet"),
        "THESIS_BUYS_AND_PASSES": (
            _section(doc, "What we buy")
            + "\n\n"
            + _section(doc, "What we pass on, regardless of quality")
        ),
        "THESIS_METRIC_ANCHORS": _between(
            doc, "1. Founder signal — 30%", "Verdict bands"
        ),
    }


_COMMENT = re.compile(r"<!--.*?-->", re.S)


def build(bundle: Bundle, *, template: str | None = None, doc: str | None = None) -> str:
    """The complete prompt for one company.

    HTML comments are removed. They explain the template to a person reading
    the repository, and the model has no use for our notes about the template.
    """
    text = TEMPLATE_PATH.read_text(encoding="utf-8") if template is None else template
    text = _COMMENT.sub("", text).strip()

    filled = {**thesis_parts(doc), "EVIDENCE": bundle.render()}
    for key, value in filled.items():
        text = text.replace("{{" + key + "}}", value)

    left = re.findall(r"\{\{(\w+)\}\}", text)
    if left:
        raise KeyError(f"prompt placeholders were not filled: {sorted(set(left))}")
    return text


def _claims_schema() -> dict:
    return {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING"},
                "evidence_id": {"type": "STRING"},
            },
            "required": ["text", "evidence_id"],
            "propertyOrdering": ["text", "evidence_id"],
        },
    }


def _metric_schema(key: str) -> dict:
    properties = {
        "score": {"type": "INTEGER"},
        "rationale": {"type": "STRING"},
        "claims": _claims_schema(),
    }
    required = ["score", "rationale", "claims"]
    if key == "founder_signal":
        # The tier decides the ceiling, so the schema makes it impossible to
        # omit rather than leaving it to the validator to catch.
        properties["tier"] = {"type": "STRING", "enum": ["primary", "fallback"]}
        required.append("tier")
    return {
        "type": "OBJECT",
        "properties": properties,
        "required": required,
        "propertyOrdering": required,
    }


def response_schema() -> dict:
    """Mirrors the Output section of the template. Built from METRIC_KEYS, so a
    metric added to the thesis cannot be missing from the schema."""
    return {
        "type": "OBJECT",
        "properties": {
            "metrics": {
                "type": "OBJECT",
                "properties": {key: _metric_schema(key) for key in METRIC_KEYS},
                "required": list(METRIC_KEYS),
                "propertyOrdering": list(METRIC_KEYS),
            },
            "summary": {"type": "STRING"},
            "would_change_the_call": {"type": "ARRAY", "items": {"type": "STRING"}},
            "not_found": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["metrics", "summary", "would_change_the_call", "not_found"],
        "propertyOrdering": ["metrics", "summary", "would_change_the_call", "not_found"],
    }
