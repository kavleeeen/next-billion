"""The only place a query is built from Python values.

SQLite has no list parameter, so an `IN` clause has to be widened to match the
values it receives. Every repository did that widening itself, with `.format()`
and a hand-built run of `?`, and each one then had to pass its parameters in
the right order to match. That is where a query and its values drift apart.

`expand` does the widening and the naming together, so they cannot disagree.
Everything is named, so positional and named parameters are never mixed.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# A named placeholder. Trailing \b stops :company matching inside :company_ids.
_NAME = ":{}\\b"


class EmptyList(ValueError):
    """An IN clause was given no values. SQL has no way to express that."""


def expand(query: str, params: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Widen every list-valued parameter into its own named placeholders.

    Write `IN (:company_ids)` and pass a list. The list becomes
    `:company_ids__0, :company_ids__1, ...` and each value gets its own name.
    """
    out: dict[str, Any] = {}
    for name, value in params.items():
        if not isinstance(value, (list, tuple, set, frozenset)):
            out[name] = value
            continue

        values = list(value)
        if not values:
            raise EmptyList(f"{name} is empty; callers must return early")

        names = [f"{name}__{i}" for i in range(len(values))]
        marks = ", ".join(f":{n}" for n in names)
        query, found = re.subn(_NAME.format(re.escape(name)), lambda _: marks, query)
        if not found:
            raise KeyError(f"{name} is not used by the query")
        out.update(zip(names, values))
    return query, out


def run(conn, query: str, params: Mapping[str, Any] | None = None) -> Iterable:
    """Execute a query whose list parameters are expanded first."""
    text, values = expand(query, params or {})
    return conn.execute(text, values)
