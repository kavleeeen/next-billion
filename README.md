# next-billion

An AI-augmented investment pipeline. It collects seed-stage companies, gathers
evidence about them, and scores that evidence against a written thesis, ending
in **Pass**, **Watch**, or **Take a meeting**.

Four stages, each a separate command, each safe to re-run:

```
sync      →  pull YC and Hacker News into SQLite
search    →  find candidates, no AI, instant
prepare   →  gather evidence for a selection: threads, repositories, founders
score     →  one model call per company, then the rules run in Python
```

The thesis is in [`THESIS.md`](THESIS.md). Every decision behind the code is in
[`docs/decisions/`](docs/decisions/), and the working notes for the analysis
stage are in [`docs/ANALYSIS-PLAN.md`](docs/ANALYSIS-PLAN.md).

## Requirements

Python **3.10 or newer**, verified on 3.10 and 3.13. Nothing else: the
pipeline has **no runtime dependencies**, standard library only, on purpose.
`pytest` is needed for the tests and for nothing else.

## Setup

```bash
git clone <repo> && cd next-billion
python3 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"          # pytest only
```

## Environment

Create a file named `.env` **in the repository root** — beside this README, not
inside `backend/`. It is read on import and never overwrites a variable that is
already set.

```bash
# Required to score. Free tier, no billing needed.
# https://aistudio.google.com/apikey
GEMINI_API_KEY=...

# Required to buy founder records. Free plan allows 100 lookups a month.
# https://dashboard.peopledatalabs.com
# Skip it and pass --no-pdl: everything else still runs, and companies
# without a founder record score metric 1 on the fallback tier.
PDL_API_KEY=...

# Optional. Raises the GitHub limit from 60 requests an hour to 5000.
# A selection of 15 costs about 45, so the anonymous limit is usually enough.
# https://github.com/settings/tokens  (no scopes required)
GITHUB_TOKEN=...
```

| Variable | Needed for | Without it |
|---|---|---|
| `GEMINI_API_KEY` | `score` | `score` stops before spending anything |
| `PDL_API_KEY` | `prepare`, `enrich` | Use `--no-pdl`. Founders are scraped by name only |
| `GITHUB_TOKEN` | nothing | The anonymous rate limit applies |

`sync` and `search` need no key at all.

## Running it

All commands run from `backend/`.

```bash
cd backend
```

**1. Collect.** Pulls the YC batches in `config.py` and Hacker News launch
threads above 30 points. Takes a few minutes on a first run, and is idempotent.

```bash
python -m pipeline.cli sync
```

**2. Search.** No AI, no network. This is where a partner picks a shortlist.

```bash
python -m pipeline.cli search "agents" --limit 20 --sort points
```

Sort by `points` (most HN traction), `recent` (latest launch), `score` or
`score_asc` once anything has been scored, or `default` (newest batch, then
name).

**3. Prepare.** Gathers evidence for the ids you chose. Free work runs first,
so a credit ceiling still leaves the free signals in place.

```bash
python -m pipeline.cli prepare 12,44,91
```

**4. Score.** One model call per company, then the rules run in Python.

```bash
python -m pipeline.cli score 12,44,91
```

A selection holds **15 companies**, because the model accepts 15 requests a
minute ([`0005`](docs/decisions/0005-selection-cap-of-fifteen.md)). Evidence and
scores collected in the last hour are reused rather than fetched again
([`0009`](docs/decisions/0009-a-one-hour-refresh-window.md)); pass `--force` to
score anyway.

## Reading the results

```bash
python -m pipeline.server --port 8000
```

Then open <http://127.0.0.1:8000>. The viewer shows each company's score, the
five metrics behind it, and every claim the model made with a link to the
Hacker News comment or repository it came from.

It is a read-only local viewer, bound to `127.0.0.1`, and the pipeline does not
depend on it ([`0014`](docs/decisions/0014-the-viewer-ships.md)).

## How the score is produced

The model returns five judgments and the evidence for each. It never sees a
weight, a total, or a band — Python does every calculation
([`0012`](docs/decisions/0012-the-rubric-runs-in-code.md)).

| Metric | Weight |
|---|---|
| Founder signal | 30% |
| Traction evidence | 25% |
| Thesis fit | 20% |
| Why now | 15% |
| Defensibility | 10% |

The model cannot cite a URL, only an id from the evidence bundle it was given,
so an invented citation does not resolve and the claim is dropped
([`0011`](docs/decisions/0011-evidence-is-a-fixed-id-space.md)).

Four override rules can only lower a result: an uncited metric caps at 50,
traction below 25 holds the total to 60, thesis fit below 40 forces a Pass, and
a company with no identified founder cannot rise above Watch.

## Tests

```bash
cd backend && python -m pytest -q
```

## Where things are

```
backend/pipeline/
  sources/      one module per source: yc, hackernews, hn_comments, github
  repository/   every SQL query in the project lives here, and nowhere else
  scoring/      thesis.py (the rubric as numbers), prompt, validate, apply, gemini
  evidence.py   everything known about one company, as citable items
  score.py      stage 4
  server.py     the local viewer
docs/decisions/ one file per decision, in the order they were taken
prompts/        the scoring prompt, versioned
```

The database is a single SQLite file at `data/next-billion.db`. It is not
committed; `sync` rebuilds it.
