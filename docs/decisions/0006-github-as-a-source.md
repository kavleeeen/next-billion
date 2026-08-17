# 0006 — GitHub becomes a source

**Date:** 2026-08-16
**Status:** accepted
**Relates to:** `0001-sources.md`, which accepted GitHub and never built it

## Decision

Build GitHub. Do not change the weights.

## What did not work

Across 47 scored companies, metric 2 never reached its top band. Median 0,
maximum 79, top band used 0%.

The band asks for "two or more independent signals". `THESIS.md` accepts six
kinds of traction evidence and we collected one, Hacker News. Two signals
cannot agree when there is one source, so the band was not hard to reach, it
was impossible.

Metric 1 broke the same way. Its fallback tier reads "repositories,
contributions, or a launch thread" and should reach 51–79. With no repositories
and no thread, the 5 companies on that tier averaged **2.0**.

The weights state what the thesis values. Lowering one because the instrument
is broken would hide the defect.

## Matching, and the test that makes it safe

| Tier | Method | Test | Companies |
|---|---|---|---|
| 1 | The website **is** a GitHub URL | none needed | 289 |
| 2 | A GitHub link on the company site | repo `homepage` = company domain | 2 of 6 |
| 3 | Search **organisations** by name | org `blog` = company domain | recovers Emergent |

Repository search by name is rejected: "emergent" returns
`emergent-misalignment` and `boson-ai/EmergentTTS-Eval`. A name is not an
identity.

Organisation search with the test is accepted: `emergentbase` has
`blog = https://app.emergent.sh` and passes. `emergent-company` has no `blog`
and is refused. A wrong match is worse than no match, because it credits
somebody else's traction.

## What we read

**Contributors and `pushed_at`.** 3 contributors against 95 separates a founding
team from a project other people build on. Commit statistics need an extra
request that often answers 202; `pushed_at` says the same thing free.

**Organisation followers.** Emergent is the control case in `THESIS.md`: 4
repos, 6 stars, 455 followers. Stars alone would call it dead.

**The `homepage` field.** 289 companies give a GitHub URL as their website, so
we never knew their real address. `homepage` supplies it — 10 of 12 correct on
test — which also restores the founder search those companies lost in `0007`.

## Collected before the call, not given as a tool

- Citations stay checkable: `validate()` needs an id set fixed before the
  request. A tool adds evidence during it.
- Runs stay repeatable: 15 companies cannot be ranked unless both runs saw the
  same evidence.
- Failure stays visible: a model that skips a tool returns a low score for a
  reason nobody can see.

## Consequences

1. `prepare` gets a third step, free, before founders.
2. A 404 records "no public repository". Per `THESIS.md` §2 the instrument does
   not apply; it is not a penalty.
3. 15 companies cost about 45 requests against an anonymous limit of 60 an hour,
   so no token is needed.

## Open

`Needle` and `Cactus` both give `github.com/cactus-compute/…`. One is wrong.
That is a sourcing defect, not a matching one.
