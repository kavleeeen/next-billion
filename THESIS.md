# Investment Thesis — Seed AI Infrastructure

## The bet

We back **seed-stage AI infrastructure and developer tooling sold to technical
buyers**, where the founding team has operated the problem before, and where
usage is observable today rather than promised.

At seed there is no revenue to underwrite. The only two honest signals are who
builds it and whether anyone uses it yet. Both are externally verifiable.
Market size, roadmap, and projections are narrative. Narrative is free.

We buy a narrow slice on purpose. A great company outside it is still a Pass.

## What we buy

- Infrastructure, tooling, or agent runtime sold to engineers or technical operators
- Founders who built or ran this exact system before, at scale
- Evidence a stranger can verify today: commits, a launch, unprompted user reports
- A dependency on a capability that became true in the last 18 months

## What we pass on, regardless of quality

- Consumer apps and prosumer productivity
- Vertical SaaS where the wedge is workflow, not technology
- Thin wrappers over one model API, with no data or distribution advantage
- Non-technical buyer motions
- Any company past Series A

This list is the thesis. A thesis that rejects nothing is not a thesis.

## Scoring

Five metrics, weighted. Each metric takes a score from 0 to 100 against the
anchors below. Each score needs at least one source URL. Python computes the
total. The model never returns a total.

| # | Metric | Weight |
|---|---|---|
| 1 | Founder–market fit | 30% |
| 2 | Traction evidence | 25% |
| 3 | Thesis fit | 20% |
| 4 | Why now | 15% |
| 5 | Defensibility | 10% |

### 1. Founder–market fit — 30%

| Score | Anchor |
|---|---|
| 0–20 | No named founders, or no relevant background |
| 21–50 | Strong generalists. Adjacent domain. First time on this problem. |
| 51–79 | Built a version of this internally, at a company that needed it |
| 80–100 | Owned this system at scale, or exited in this category |

This weight is the highest. At seed, the team is the only input that does not change.

### 2. Traction evidence — 25%

| Score | Anchor |
|---|---|
| 0–20 | Landing page and waitlist only |
| 21–50 | A launch happened. Low engagement. The repo is quiet. |
| 51–79 | Regular commits, real launch discussion, named users |
| 80–100 | Several independent signals agree |

### 3. Thesis fit — 20%

| Score | Anchor |
|---|---|
| 0–20 | Consumer, vertical SaaS, or non-technical buyer |
| 21–50 | Technical-adjacent buyer. The product is an application. |
| 51–79 | Developer tooling with a clear technical buyer |
| 80–100 | Core infrastructure that other companies build on |

### 4. Why now — 15%

| Score | Anchor |
|---|---|
| 0–20 | Buildable in 2019. Nothing external changed. |
| 21–50 | It follows a general trend. No specific unlock. |
| 51–79 | It depends on a capability that recently became cheap or reliable |
| 80–100 | Impossible 18 months ago, for a specific reason |

### 5. Defensibility — 10%

| Score | Anchor |
|---|---|
| 0–20 | One API key from replication |
| 21–50 | Speed of execution only |
| 51–79 | Data, integrations, or switching costs accrue |
| 80–100 | The advantage widens with use |

This weight is the lowest on purpose. At seed, a claimed moat is usually
retrofitted. We prefer to pay for founders.

## Verdict bands

| Total | Call |
|---|---|
| 70 or more | **Take a meeting** |
| 45 to 69 | **Watch** |
| Below 45 | **Pass** |

## Overrides

The rules run in this order. Each rule can only lower a result.

**Rule 3 runs first, on each metric.**

3. **Uncited score.** A metric with an empty evidence list takes a maximum
   score of 50 for that metric. The limit applies to the metric only. It does
   not limit the total directly. The reduced metric score then enters the
   weighted sum. The memo names each limited metric.

**Rules 1 and 2 run second, on the result.**

1. **Traction floor.** A traction score below 25 limits the *total* to 60.
2. **Thesis gate.** A thesis fit below 40 forces the *verdict* to Pass. The
   total keeps its value. The memo shows both.

## Blind spots

These are stated so a reader interprets the scores correctly.

- **Bias toward legible founders.** A public GitHub profile is a proxy for
  competence, not competence. Strong founders with a small public record score low.
- **Bias toward launched companies.** A stealth company scores near zero on
  traction. It cannot clear the floor. This is a real cost of the thesis.
- **No market score.** Market size at seed is mostly fiction. Market appears
  as context in the memo. It carries no weight.
