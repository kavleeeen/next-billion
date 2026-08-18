# 0018 — A citation must resolve

**Date:** 2026-08-18
**Status:** accepted

## What did not work

`0011` guarantees the model cannot invent a citation: it cites an id, and an id
outside the bundle is dropped. That held. What broke was underneath it — the
URL we built for an id that was perfectly valid.

For a Hacker News company, `source_key` is the normalised **name**, not an item
id. `_profile` used it as one:

```
https://news.ycombinator.com/item?id=statewright   ->  "No such item"
```

All 1,606 Hacker News companies were affected, and `profile` is the most cited
item in a bundle.

## Change

The profile item takes the company's newest thread id. Two fallbacks, neither
of which can 404:

| Case | Link |
|---|---|
| Has a launch thread | That thread |
| No thread | Its own website |
| Neither | No link at all, rather than a fake permalink |

The tests checked that ids were present and cited. They never checked that a
URL pointed at anything. One now asserts every `item?id=` in a real bundle ends
in digits — the class of fault, not the instance.

## The stored URL froze the bug into history

`scores_json` keeps `source_url` beside `evidence_id`, so fixing the builder
repaired nothing already written: 16 claims across 8 analyses stayed broken.
They were repaired by deriving the right thread, with no re-scoring, because
the correct URL is a function of data we already hold.

Resolving the URL from the bundle at read time would have self-healed. It was
not adopted: a stored URL records what was cited *at the time*, and a
re-resolved one can silently point somewhere else after a later collect. The
duplication is the price of that, and this is what it costs.

## Consequences

1. Every citation in the viewer resolves.
2. A company with no public thread still cites something checkable.
3. A future builder fault needs a data repair as well as a code fix, and
   nothing in the repo automates that.
