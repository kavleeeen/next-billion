# 0002 — Data model and storage

**Date:** 2026-08-16
**Status:** accepted
**Decision:** SQLite, two tables, the database as the only store, no runtime
dependencies.

---

## The shape of the problem

A search like "SMB founders" must return a list instantly. Analysis is slow and
expensive. Those are different jobs, so they run at different times:

```
daily / on demand    sync    APIs ──► companies table
per query            search  companies table ──► list    (reads the DB only)
per shortlist        analyse companies ──► LLM + enrichment ──► analyses table
```

Only the third step costs money, and it only runs on companies someone asked
about. That split is why the list is instant and why nothing is analysed twice.

---

## SQLite, not Postgres or Mongo

The data has clear relationships — a company has founders, signals, an analysis
— so a relational store fits. Among relational options SQLite wins on setup cost:
it is one file and there is no server to run.

Volume is not a factor. A full sync produces about 1,000 companies. Any database
handles that; the tiebreaker is what a reader has to install to open it.

Mongo was considered and rejected. The flexibility it offers is only needed for
the untouched API payloads, and a `TEXT` column holding JSON covers that inside
SQLite. Every other field is a known column that gets filtered and sorted.

---

## Two tables, 

```sql
companies   id, source, source_key, name, website, one_liner,
            description, batch, team_size, raw_json, created_at, updated_at
            UNIQUE (source, source_key)

analyses    id, company_id, verdict, total, scores_json, model, created_at
```

---

## Identity is `(source, source_key)`

`source_key` is the YC slug or the Hacker News story id. Upsert on that pair, so
re-running `sync` never duplicates.

`website` is stored exactly as submitted. Whatever cross-source merging the
analysis stage needs will be built there, on stronger evidence than a shared
host — a matching name plus batch, or a resolved GitHub organisation.

---
## One parse function per source

Each source module exposes `parse(payloads) -> list[Company]`, and it is the only
place that raw JSON becomes a `Company`.

This was learned the hard way. An earlier version parsed inline in `sync.py`
and skipped deduplication:

```
raw hits across all searches : 928
distinct stories             : 738
```

The Hacker News searches overlap — one Show HN story matches both "agent" and
"LLM" — so 190 records were duplicates. `parse()` is now the only path into the
database, so the dedupe cannot be bypassed.

`sync.py` now knows no source JSON shapes at all. Adding a third source means
adding one line to `_plan()`.

---

## No runtime dependencies

`pyproject.toml` lists no runtime dependencies. HTTP is `urllib`, the database is
`sqlite3`, both standard library. `pytest` is the only development dependency.

The cost is a hand-written retry loop in `http.py` instead of using `httpx`. That
is about thirty lines. The benefit is that the project runs on a clean Python
3.11 with no install step, and there is no dependency that can break it later.

Revisit this if the analysis stage needs an SDK that is genuinely painful to
write by hand.

---

## What is filtered before writing

`Company.is_usable` rejects a record whose name is not a company name. A Show HN
title is often a sentence:

```
"Show HN: I built a sub-500ms latency voice agent from scratch"
```

Thresholds come from the observed distribution of parsed names: median 9
characters, 90th percentile 17, longest genuine name 29. The cut is 40 characters
or 6 words, plus a leading pronoun or question word.

On a full sync this rejects 219 of 738 Hacker News records and 2 of 531 YC
records. The count is a column in the sync report, so it is visible rather than
silent.

**A missing website does not reject a record.** Launch HN posts are frequently
text posts with no URL, and those are real companies — Onyx, AgentMail,
Trigger.dev. An earlier version required a domain and silently dropped 28 of 60
of them.

---

## Consequences

1. `sync` is idempotent. Two runs with the same arguments give the same rows.
2. Every `sync` hits the network — roughly 40 API calls and 5 seconds.
3. Deleting `data/*.db` loses everything and costs a full refetch to rebuild.
4. A company present in both YC and Hacker News is two rows until the analysis
   stage merges them. Nothing merges them today, and no column pretends to.
5. Six tables and any cross-source merge remain unbuilt, on purpose.
