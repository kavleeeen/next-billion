# 0003 — Data model, second pass

**Date:** 2026-08-16
**Status:** accepted
**Supersedes:** the "Two tables" section of [0002](0002-data-model.md)

`0002` deferred six tables and named the trigger for each. Three of those
triggers have now fired. This records what was added, and what the additions
changed about identity and cost.

```
companies                 as before
hn_stories       NEW      one row per Hacker News post
company_traction NEW      a view, aggregating hn_stories per company
founders         NEW      one row per person named as a founder
pdl_usage        NEW      credits spent, so a monthly budget survives a restart
analyses                  still empty; scoring is not built
```

---

## 1. A Hacker News post is an event, not a company

`0002` made identity `(source, source_key)`, and for Hacker News `source_key`
was the story id. That was wrong, and real data showed it:

```
name        stories  points        months
rowboat       3      66,205,219    2025-09, 2026-02, 2026-07
ctx           3      53,72,65      2026-04, 2026-04, 2026-07
onecli        2      161,110       2026-03, 2026-07
```

Ten of 519 Hacker News rows were repeat posts by the same company. Each became
a separate company, which produced three failures at once: duplicate rows in
the list, a separate memo per row, and — worst — traction split rather than
summed. Rowboat's real signal is 490 points across three launches in eleven
months, and the pipeline was reading 219.

**`source_key` for Hacker News is now the normalised company name.** Stories
live in their own table with a foreign key.

```sql
hn_stories        id, company_id, story_id UNIQUE, title, url,
                  points, comments, posted_at, raw_json

company_traction  VIEW: story_count, points, comments,
                        first_posted_at, last_posted_at
```

**Traction is a view, not columns.** An aggregate stored on `companies` can
drift from the rows behind it. A view is recomputed on read and cannot.

**Accepted cost:** two genuinely different companies sharing a name will merge.
Matching on website was considered and rejected in `0002` — six unrelated
companies share `github.com` because their Launch HN post links to their repo.

### The merge is field-wise

`parse()` groups stories by company, and the highest-scoring post supplies the
name and one-liner, since that is the version a reader recognises. An earlier
version replaced the whole record, which silently dropped any field the winning
post lacked:

```
"Launch HN: Acme (YC W25) - the thing"   40 pts, url=acme.dev
"Show HN: Acme - now faster"            300 pts, url=None
                    → batch=None, website=None
```

`website` is the only input to the founder search fallback, so a company whose
top post was a text post could never be enriched — leaving metric 1 uncited and
override 4 pinning it at Watch permanently. `batch`, `website` and
`description` are now carried across every post: first non-empty wins, and a
later post cannot erase them.

---

## 2. Founders, and which evidence tier they came from

`0002` deferred `founders` until "founders are scored separately". Metric 1 of
the thesis scores them, so the trigger fired.

```sql
founders  id, company_id, linkedin_slug, name, source_url,
          discovered_via, pdl_matched, current_title, current_company,
          prior_roles_json, raw_json
          UNIQUE (company_id, linkedin_slug)
```

Two strategies fill it, and `discovered_via` records which:

| Value | Meaning | Coverage |
|---|---|---|
| `yc_page` | The YC company page names this person as a founder | YC companies only. 9 of 9 tested published founder LinkedIn URLs, 19 founders. |
| `pdl_search` | Inferred from an owner-level job title at the company's domain | Any company with a website |

The distinction is not cosmetic. One is a statement by Y Combinator; the other
is an inference from a job title. A memo can say which, and metric 1's tiers
depend on it.

**LinkedIn is never fetched.** Only the slug is taken from the YC page, and
`source_url` on every row points at the page that named the person, so each
claim is citable without touching a site whose terms forbid automated access.

**`prior_roles_json` is the primary evidence for metric 1.** Measured: 4 of 4
founders matched in People Data Labs, each with 5 to 10 employment entries
carrying titles, employers and dates.

---

## 3. Credits are data, not a constant

> **Superseded in part by
> [0008](0008-behaviour-at-a-providers-limit.md).** The `pdl_usage` table and
> the two ceilings below were removed. The provider counts the allowance and
> refuses with a 402, so a second count could only disagree with it.

The People Data Labs free plan allows 100 lookups a month. That budget is
shared by every process, so it cannot live in a variable.

```sql
pdl_usage  id, called_at, calls
```

An earlier version had only `max_calls_per_run`, a local. Each HTTP request to
the on-demand endpoint got its own budget, so N requests allowed N × 25 lookups
against a 100/month plan. Four guards now:

| Guard | Prevents |
|---|---|
| Skip companies that already have founders | Re-buying what is already paid for |
| `max_calls_per_run` | One bad run draining the month |
| `monthly_credit_cap`, counted in `pdl_usage` | Many runs each getting a fresh budget |
| Token checked once before the loop | Paying for lookups that a missing key will discard |

**Spend is recorded and committed the moment it is consumed**, and each company
commits on its own. An earlier version wrote everything inside one transaction,
so a failure after 24 paid lookups rolled back all 24 — the credits were gone
and the data was not.

---

## 4. Why enrichment is on demand

```
companies                1,038
credits per company        ~2.5
credits to enrich all     ~2,600
free plan            100 / month
```

Enriching the whole database would take two years of free tier, so it cannot be
part of the nightly sync. `sync` runs on a schedule and is free; `enrich` runs
against an explicit list of companies someone asked about.

This is what makes scoring two-pass, and why override 4 exists in `THESIS.md`:
a company nobody has paid to enrich has no founder evidence, and cannot exceed
Watch.

---

## Consequences

1. `sync` is still idempotent, and now writes stories as well as companies.
2. Traction can never disagree with the stories behind it; it is derived on read.
3. Repeat launchers are visible as one company with a summed score and a date
   span, which is a stronger signal than any single post.
4. Every founder carries the URL that named them, and a flag saying whether that
   was a statement or an inference.
5. Credit spend is auditable — `SELECT SUM(calls) FROM pdl_usage`.
6. `analyses` remains empty. Scoring is the next stage.
