# 0011 — Evidence is a fixed id space

**Date:** 2026-08-17
**Status:** accepted

## Decision

The model never sees a URL. Each item gets a short id, the model cites ids, and
the bundle turns them back into links afterwards. The id set is complete before
the request is sent.

## What did not work

Putting the source URL beside each fact and asking the model to cite it. A
model that writes `news.ycombinator.com/item?id=43173378` produces a string
that looks correct whether or not it read anything. No test can tell the two
apart.

## Change

```
### story-1
Launch HN: Airweave — 259 points, 120 comments
```

The model writes `"evidence_id": "story-1"`. `validate()` compares every cited
id with `bundle.ids()`. An invented id does not resolve, and the claim is
dropped.

Ids: `profile`, `traction`, `story-N`, `github`, `founder-N`, `comment-N`.

This works only because the set is fixed before the call. That is why GitHub is
collected in `prepare` and not offered as a tool (`0006`) — a tool adds evidence
during the request, so there is nothing stable to check against.

## Limits

`MAX_COMMENTS = 25`, `MAX_COMMENT_CHARS = 1200`. The submitter's own words sort
first, so a cut removes strangers before it removes the founder.

## Consequences

1. A bundle reads only the database, so the same evidence always produces the
   same prompt and 15 companies stay comparable.
2. `bundle.has(kind)` lets a rule ask what was collected — rule 4 holds the
   verdict at Watch when no founder was identified.
3. A memo can still link every claim, because `url_for` knows the source.
