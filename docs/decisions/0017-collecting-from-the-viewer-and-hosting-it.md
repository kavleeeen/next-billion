# 0017 — Collecting from the viewer, and hosting it

**Date:** 2026-08-17
**Status:** accepted

## Decision

The viewer can start a collect. It is hosted on Cloud Run, where reading is
open and writing needs a token.

## The search box is the topic box

`0015` made the topic the thing that decides what we collect. The viewer
already had a box a partner types a topic into, so **Collect** uses it. One
field, two jobs: filter what we hold, or go and fetch more.

Enter runs it as well.

## Writing is gated by where we are bound, not by a flag

`POST` collects, buys PDL credits and spends Gemini quota.

| Bound to | Writing |
|---|---|
| `127.0.0.1` | Open. The only caller is the person who started the process |
| Anything else | Needs `X-Write-Token` to match the `WRITE_TOKEN` secret |

An unset `WRITE_TOKEN` on a hosted instance means read-only. That is the safe
default: a public URL that can spend money is a bill, not a demo.

Keying on the bind address rather than on a setting means the local viewer
cannot be broken by forgetting to configure something, and a hosted one cannot
be opened by forgetting to configure something. The dangerous direction needs
the deliberate act.

## Hosting

Cloud Run, in its own project. The pipeline has no runtime dependencies, so the
image is the interpreter, the source, and the database — 9.6 MB of SQLite baked
in at build time.

`gcloud --source` falls back to `.gitignore` when there is no `.gcloudignore`,
and `.gitignore` excludes `data/*.db`. The first build failed on exactly that,
so `.gcloudignore` exists to include the one file the image is for.

**Writes on Cloud Run do not persist.** The filesystem is ephemeral, so a score
made against the hosted instance disappears when the instance restarts. That is
fine for showing the pipeline work; anything meant to last is scored locally and
the image rebuilt. Real persistence would mean Cloud SQL, which is far past what
this needs.

`--max-instances 1`, so everyone watching a demo sees the same instance.

## Consequences

1. A reviewer can read every score and follow every citation without cloning
   anything.
2. Nobody but the token holder can spend the account's credits.
3. The hosted database is a snapshot. It is only as current as the last deploy.
