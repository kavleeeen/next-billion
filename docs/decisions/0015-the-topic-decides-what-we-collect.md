# 0015 — The topic decides what we collect

**Date:** 2026-08-17
**Status:** accepted
**Supersedes:** the "no topic filter" reasoning in `0001-sources.md`

## Decision

`sync` requires a topic. It bounds Show HN, and the points filter is deleted.

## What did not work

A partner searched "AI agents for SMBs" and got nothing. The cause was not the
search. Only **7 of 1224** companies mentioned anything SMB-like, so no ranking
method could have helped.

We filtered Show HN to posts above 30 points. Measured against every Show HN
post on Hacker News about SMB topics:

```
492   posts on Hacker News
137   ...still there after our 365-day window
  5   ...still there after "points > 30"
```

The reason is in the distribution. Of those 137 posts the **median score is 2**:

| Points | Posts |
|---|---|
| 0–5 | 123 |
| 6–30 | 9 |
| 31+ | 5 |

**A Show HN post about invoicing for plumbers gets about 2 points. Hacker News
upvotes developer tools.** So the threshold did not measure whether a company
was worth collecting; it measured whether developers liked it. Our corpus read
`api` 346 times and `plumber` zero.

`0001` claims we avoided exactly this — *"an editorial guess made at fetch time
and invisible afterwards"*. We avoided the keyword guess and then made a
popularity guess that did the same damage, just as invisibly.

## Why the filter could not simply be deleted

Show HN is a firehose, and something has to bound it.

| Threshold | Posts in 365 days | We could keep | Sample |
|---|---|---|---|
| points > 30 | 1,820 | 1000 | 55% |
| points > 1 | 29,268 | 1000 | 3% |
| none | 418,048 | 1000 | **0.24%** |

Deleting the filter alone swaps a biased 55% sample for an arbitrary 0.24% one.
Lowering it does not help either: catching the median SMB post needs
`points > 1`, which is 29,268 stories and a corpus of mostly weekend projects.

**The topic is the bound.** "AI agents for SMBs" returns 222 Show HN hits, well
inside one fetch, and it selects on what the partner asked for rather than on
what an audience liked.

## What each source does with the topic

| Source | Topic | Why |
|---|---|---|
| YC | `q=<topic>` | The directory's own search. `q=agents` returns 50 pages against 248 unfiltered |
| **Launch HN** | **not used** | 119 posts a year. Small enough to take whole, and asking a topic of it returns 8 |
| Show HN | `query=<topic>`, no points filter | 418,048 a year. This is the pool that needs bounding |

Two more narrowings went with it, both leftovers from a topic-less sync:

- **YC batches.** Pinning W25/S25/W26 fought the topic — 11 companies instead
  of 51. No batch now means the whole directory. `--batch W25` still narrows,
  which is the brief's "a feed like the YC W25 batch" seed input.
- **The incremental window.** The floor came from the newest story held, which
  was cheap for one repeated broad sync and wrong here: each topic is a new
  question, and a floor set by the last topic hides every older post that
  answers this one. Always the full window now.

## Result

One run of `sync "AI agents for SMBs"`:

```
yc     51 fetched   40 added
hn    337 fetched  121 added
```

and the companies that arrive are the ones that were missing:

```
Certus AI    Replacing the restaurant phone line with Voice AI
GlitchWard   Active defense and CIS hardening for neglected SMB servers
Harbera      Helps clinics keep their doctors credentialed
```

## The page cap is now the only other bound, so it has to speak

Deleting the points filter put all the bounding on the topic. But the topic
does not bound anything the fetcher cannot already exhaust:

| Topic | Matches | We read | Share |
|---|---|---|---|
| `AI agents for SMBs` | 222 | 222 | 100% |
| `smb` | 4,834 | 1,000 | 21% |
| `agent` | 8,706 | 1,000 | 11% |
| `ai` | 14,860 | 1,000 | **7%** |

A cap that says nothing is the same defect this document removed from the
points filter: a cut made at fetch time and invisible afterwards. So each
source now reports what it reached, and `sync` prints it:

```
hn: topic too broad — read 1,000 of 14,860 (7%). Narrow it to see the rest.
```

Silent on a narrow topic, so it is a signal rather than noise.

## Both public APIs are paced again

`_search` used to sleep 0.2s between pages, with the comment *"the API asks for
no key; do not hammer it"*. Commit `63662c9` — "fetch sources and pages
concurrently" — deleted the sleep and the comment with it.

That mattered less when a repeat sync read three pinned batches and an
incremental floor. It matters now: every run reads the whole YC directory and a
full 365-day window on both Hacker News pools, eight workers at a time, against
two unauthenticated APIs. Re-running a topic is free in money, not in requests.

`Pacer` already existed for this, with `0008` behind it, and was wired only to
Gemini. Each source now holds its own, at 300 requests a minute — the rate the
old sleep produced. Separate pacers because the limits belong to separate
providers.

## Consequences

1. `sync` cannot run without a topic. There is no "collect everything" mode,
   because there was never an honest one.
2. Sourcing is now a stage a partner drives, which is what the brief describes:
   the topic decides what we collect, and `THESIS.md` decides how we judge it.
3. Repeating a topic re-reads the same window, which refreshes points as they
   rise. That costs no money and roughly 60 requests, which is why both
   sources are paced.
4. A broad topic is reported, not silently truncated. `ai` says so; `AI agents
   for dental clinics` says nothing, because it read everything.
