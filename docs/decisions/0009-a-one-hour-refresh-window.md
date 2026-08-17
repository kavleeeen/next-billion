# 0009 — A one hour refresh window

**Date:** 2026-08-16
**Status:** accepted

## Decision

Evidence read inside the last hour is reused. Older evidence is read again.
`settings.refresh_after_hours = 1.0`.

## What did not work

`stories_for_companies` selected only `comments_fetched_at IS NULL`, so a
thread was read once and never again.

- A launch thread keeps getting replies for days. Metric 4 scored the snapshot
  taken on day one.
- A re-prepared company was skipped forever, not for an hour.

## Change

A thread qualifies if it was never read, or was read before the cutoff.

```sql
WHERE s.comments > 0
  AND (s.comments_fetched_at IS NULL OR s.comments_fetched_at < ?)
```

`db.hours_ago()` builds the cutoff in the format `utcnow()` writes, so the
comparison stays a string compare and the index still works. Passing no cutoff
keeps the old rule: `""` is older than any timestamp.

## Why one hour

Short enough that a wrong number is fixed by waiting. Long enough that a
partner working through a shortlist never re-fetches.

## Scope

Free work only. PDL founders are never re-bought on a timer: credits do not
come back, and past roles do not change in an hour. `force=True` is the only
way.
