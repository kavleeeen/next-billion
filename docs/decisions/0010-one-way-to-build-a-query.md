# 0010 — One way to build a query

**Date:** 2026-08-17
**Status:** accepted

## Decision

SQL text is never built at a call site. `repository/sql.py` widens list
parameters, and every parameter is named.

No ORM. The project has no runtime dependencies, and the repository layer
already keeps SQL out of every other module.

## What did not work

SQLite has no list parameter, so an `IN` clause has to be widened by hand.
Each repository did it separately:

```python
marks = ",".join("?" * len(company_ids))
query = STORIES_FOR_COMPANIES.format(placeholders=marks)
conn.execute(query, [stale_before or "", *company_ids])
```

Two things must agree here, and nothing makes them: the number of marks, and
the order of the values. A query written with a named mark and a positional one
mixed together was accepted by SQLite and answered wrongly.

The same four lines appeared in four repositories.

## Change

```python
STORIES_FOR_COMPANIES = "... WHERE at < :stale_before AND id IN (:company_ids)"

sql.run(conn, STORIES_FOR_COMPANIES, {
    "stale_before": stale_before or "",
    "company_ids": company_ids,
})
```

`expand()` turns `:company_ids` into `:company_ids__0, :company_ids__1, …` and
gives each value the matching name. The marks and the values are produced by
the same loop, so they cannot disagree. Parameters arrive as a dict, so order
carries no meaning.

Refused, loudly:

| Case | Result |
|---|---|
| An empty list | `EmptyList`. SQL cannot express `IN ()`, so the caller must return early |
| A name the query does not use | `KeyError` |

`:company` does not match inside `:company_ids`, which a plain `str.replace`
would.

## Scope

Converted now: `companies.by_ids`, `hn_comments.stories_for_companies`.

The repositories still to be committed — `analyses`, `github_repos`, and the
`SEARCH` query — arrive in this form. `SEARCH` also stops pasting one query
into another: the newest score becomes a view, as `company_traction` already
is, so the schema states what "newest" means.

## Consequences

1. `.format()` never touches SQL text.
2. Values are always marks, so a value that looks like SQL stays data.
3. A new repository has one obvious way to write an `IN` clause.
