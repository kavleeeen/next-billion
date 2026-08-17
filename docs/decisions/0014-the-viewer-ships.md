# 0014 — The viewer ships

**Date:** 2026-08-17
**Status:** accepted

## Decision

Commit the local viewer. It is a way to read what the pipeline produced, not a
part of the pipeline.

## What it is not

The brief says to stop if you are building a React frontend. This is not one.

| | |
|---|---|
| Server | `http.server` from the standard library, 211 lines |
| Page | One HTML file, 665 lines, no framework |
| Build step | None |
| Dependencies | None |
| Bound to | `127.0.0.1`, on purpose |

It reads the same SQLite database the CLI reads, through the same repository
functions. It holds no state and no logic of its own: `POST /api/prepare` and
`POST /api/score` call `prepare()` and `score()` unchanged, and the reuse
sentence a partner sees is `ScoreReport.message`, written in `score.py`
(`0013`).

Delete it and the pipeline is unaffected.

## Why commit it

Every score carries five metrics, a tier, a rationale, and cited claims that
resolve to real URLs. Reading that as CLI output is possible and unpleasant.

A reviewer is asked to spot-check one analysis and trust where its claims came
from. Clicking a claim through to the Hacker News comment it came from answers
that question faster than any document.

## How to run it

```
python -m pipeline.server --port 8000
```

It is not a CLI subcommand. The pipeline runs end to end without it, and
`cli.py` importing a file that is only for demonstration would make the entry
point depend on it.
