# 0008 — Behaviour at a provider's limit

**Date:** 2026-08-16
**Status:** accepted

## Decision

Read which limit a refusal names. Retry only the limits that refill.

## What did not work

| Problem | Cost | Change |
|---|---|---|
| The Gemini key is in the URL. Retries logged the URL | Key printed on each try | `safe_url()` hides `key`, `api_key`, `token`, `access_token` |
| A per-day 429 was retried on a 1s ladder | 3 companies, 9 requests, no result | `is_daily_quota()` stops the run |
| The retry delay was guessed at 1s. The server states 10–27s in the body, not in a header | Ladder too short to clear the window | `_retry_after()` reads the body, up to 65s |
| A PDL 402 was read as "no match for this person" | 8 more refused requests | `pdl.AccountExhausted` stops the run |

## Rules

| Code | Meaning | Action |
|---|---|---|
| 404 | No record | Next |
| 429 per-minute, 500 | Temporary | Wait the stated delay, retry |
| 429 per-day | Allowance finished | Stop |
| 402 | Allowance finished | Stop |

## No second count of credits

Removed: the `pdl_usage` table, `spent_this_month()`, `monthly_credit_cap`,
`max_calls_per_run`, `may_spend()`, `spend()`.

We counted requests sent. PDL charges per person returned. One search returns
five people and costs five, or returns none and costs one. Our count was
therefore always wrong: too high, it stopped a run that had credits left; too
low, it did not stop at all. The 402 is exact.

Kept, and none of these needs a counter:

- `AccountExhausted` on a 402
- Skip a company that already has founders
- Check the token before the first call

## Pacing

Gemini free tier allows 15 requests a minute. Two workers at 4 seconds send 30.
The client paces at 12.

A refusal costs a request and returns nothing, so pacing below a ceiling is
cheaper than finding it. One pacer is shared by all workers, because the limit
is per account.

## Consequences

1. No secret in a log or an error.
2. A finished allowance stops the run.
3. A temporary fault waits the stated time.
4. Every rule has a test. No test needs a network.
