# 0005 — A selection holds 15 companies, not 20

**Date:** 2026-08-16
**Status:** accepted
**Supersedes:** the cap of 20 in `0004-prepare-a-selection.md`

## Decision

`MAX_SELECTION` is 15, because the model accepts 15 calls in one minute.

The number is not a judgment about how many companies a partner can read. It is
the largest selection one run can finish without waiting.

## The measurement

Scoring is one call per company. Google does not publish the free-tier limits;
these come from the account dashboard on 2026-08-16.

| Model | RPM | RPD |
|---|---|---|
| Gemini 2.5 / 3.5 / 3.6 / 3.7 Flash | 5 | **20** |
| **Gemini 3.5 Flash Lite** | **15** | **500** |

Two limits bind at once.

- Every full Flash model allows **20 requests a day**. A selection of 20 spends
  the whole day and leaves nothing for a correction turn. It cannot work.
- Flash Lite allows **15 a minute**, so a selection of 15 fits in one window.

Limits are per project, per model. The day resets at midnight Pacific.

## What we rejected

**A cap of 20 with a pacer.** 20 needs two minute-windows, so the second half
waits. The wait buys no better analysis.

**Mixing models inside a run.** A run with two models cannot be ranked, so a
selection uses one. Measured on real evidence, `gemini-3.6-flash` and
`gemini-3.5-flash-lite` differ by 2.9 points on average — small, but the
ordering is the product. The per-company table is in `ANALYSIS-PLAN.md` §7.

**A larger cap with billing enabled.** The brief permits free tiers.

## Consequences

1. `prepare` and `score` both apply `MAX_SELECTION`, and the CLI help is derived
   from it rather than typed.
2. A full run is 15 of the 500 calls a day allows, so more than 30 runs fit.
3. The brief asks for 10 to 20 candidates. 15 is inside that range.
4. `0004` keeps its text. This record supersedes only the number.
