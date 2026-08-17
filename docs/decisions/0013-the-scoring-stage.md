# 0013 — The scoring stage

**Date:** 2026-08-17
**Status:** accepted

## Decision

One model call for each company. The bundle is built from the database, the
reply is checked, the rules run in Python, and a row is appended.

Rows are never replaced, so a company keeps the history of what it scored and
when.

## One call, not several

A call per metric was the alternative. Five calls means five chances to refuse,
five times the quota, and five judgments that never saw each other — a founder
claim that contradicts the traction claim cannot be noticed if the two were
written by separate calls.

One call also means one correction turn, not five.

## The cache key is model plus prompt version

A score is reused inside `refresh_after_hours` only when the model **and** the
prompt version match.

A score from a different model is not a stale score, it is a different opinion.
Mixing two models in one run makes 15 companies unrankable, which is the whole
purpose of the list.

`prompt_version` is a new column, applied on connect. See below.

## Reuse is reported by the server, not the browser

`ScoreReport.message` states what happened, including the case where every
selected company already had a fresh score. The viewer prints the sentence it
is given.

The frontend does not know the window, the model or the prompt version, so a
message written there would be a guess that drifts.

## No ceiling of our own on Gemini calls

An early version stopped a run at `gemini.max_calls_per_run = 25`. It was
removed. `MAX_SELECTION` is 15, so the branch was unreachable, and the number
counted companies while the quota counts requests — a correction turn makes one
company cost two.

That is the drift `0008` describes. Google counts the day and answers 429 with
a per-day `quotaId`; `is_daily_quota()` ends the run on it. One count, kept by
the party that enforces it.

## The newest score is a view

`latest_analysis` joins into the company list like `company_traction` already
does. `MAX(id)` and not `MAX(created_at)`: two runs inside the same second
would otherwise tie.

The schema now states what "newest" means, once, instead of a query being
pasted into another query (`0010`).

## Schema changes reach an existing database

Two silent failures, both fixed on connect.

| Shape | Rule |
|---|---|
| A new column | `ADDED_COLUMNS` adds it. `CREATE TABLE IF NOT EXISTS` cannot |
| An edited view | Dropped and rebuilt. `CREATE VIEW IF NOT EXISTS` would keep the old definition for ever |

Neither failure errors, so neither is visible. `ADDED_COLUMNS` lists every
column added after its table was first written, and a test asserts each one
exists in `schema.sql`.

Adding a column is the only migration shape this needs. Anything harder rebuilds
from `sync`.

## Consequences

1. The list sorts by score in both directions. Unscored companies sort last
   either way.
2. A failed company does not stop the run. It is counted and reported.
3. Re-selecting a prepared company inside the hour costs nothing.
