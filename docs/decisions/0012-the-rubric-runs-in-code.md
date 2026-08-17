# 0012 — The rubric runs in code

**Date:** 2026-08-17
**Status:** accepted

## Decision

The model supplies five judgments and the evidence for each. Python does every
calculation: the weights, the caps, the override rules and the verdict.

The model never sees a weight, a total or a band.

## What did not work

Asking for a total. A model given the weights will return a number that is
close to right and cannot be reproduced. Two runs on the same evidence
disagreed, and neither could be checked, because the arithmetic happened
somewhere nobody can read.

## Change

`thesis.py` holds the rubric as numbers. Nothing else hardcodes a weight, a cap
or a band.

```
founder_signal 30   traction 25   thesis_fit 20   why_now 15   defensibility 10
```

`THESIS.md` and `thesis.py` can still drift, so `test_thesis_constants.py`
parses the document and asserts every number here appears there.

## The order the rules run in

Each rule can only lower a result, so the sequence is part of the rubric, not
an implementation detail.

| # | Rule | Effect |
|---|---|---|
| 3 | A metric with no citation | Capped at 50 |
| — | Metric 1 on the fallback tier | Capped at 79 |
| — | Weighted sum | The total |
| 1 | Traction below 25 | Total held to 60 |
| 2 | Thesis fit below 40 | Verdict forced to Pass |
| 4 | No founder identified | Verdict held at Watch |

Applying the traction floor before the tier limit gives a different number.

## The validator

`validate()` checks the reply before any of this runs, and returns problems
rather than raising. It refuses:

- a total, a verdict or a band — those are ours to compute
- a missing metric, or a score outside 0–100
- a fallback score above 79
- **any `evidence_id` not in the bundle** (`0011`)

`repair_message()` sends the problems back to the model once. Anything still
wrong after that turn has its claim dropped, not the whole reply.

## Consequences

1. The same evidence always gives the same total, so 15 companies can be ranked.
2. A verdict can be recomputed from a stored reply without calling the model.
3. Changing a weight is a one-line edit that the drift test guards.
