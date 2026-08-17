# 0016 — The launch post is the description

**Date:** 2026-08-17
**Status:** accepted

## Decision

Read `story_text` from the Algolia hit into `companies.description`.

## What did not work

A Hacker News company held 61 characters of text — its title and nothing else:

```
name      : 18 Words
one_liner : Show HN: 18 Words
description: NULL
```

695 of 1224 companies looked like that. Search could not find them, and the
scoring prompt had almost nothing to read about them.

The obvious conclusion was that Hacker News gives us no description. It was
wrong. Algolia returns `story_text` — the founder's own launch post — in the
**same response** we already parse:

```
keys: [author, children, created_at, num_comments, objectID, points,
       story_id, story_text, title, updated_at, url, _tags]
```

`_to_company` read `title`, `url`, `points`, `num_comments`, `created_at_i` and
`author`. It never touched `story_text`. The field was stored in
`hn_stories.raw_json` and read by nothing.

## Change

`description=plain_text(hit.get("story_text")) or None`.

The existing rows were backfilled from `raw_json`, so this cost no requests.
Where a company has several posts the highest-scoring one wins, which is the
rule `parse()` already uses for `one_liner`.

| | Before | After |
|---|---|---|
| HN companies with a description | 0 | 531 |
| Average searchable text, HN | 61 chars | 1,350 chars |
| Corpus | 315 KB | 1,191 KB |

## One cleaner, not two

`hn_comments` already had `_plain` for the same job, because Hacker News serves
every body as HTML. It moved to `normalize.plain_text` and both sources use it.

Tags are stripped before entities are decoded. The other order would turn an
escaped `&lt;b&gt;` — text the founder typed — into a tag and delete it.

## Consequences

1. Scoring reads the founder describing their own company, which is the
   evidence metrics 3 and 4 ask for and mostly did not have.
2. Search over Hacker News companies works at all.
3. It changes nothing about *which* companies we hold. That is `0015`.
