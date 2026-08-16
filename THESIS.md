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
| 1 | Founder signal | 30% |
| 2 | Traction evidence | 25% |
| 3 | Thesis fit | 20% |
| 4 | Why now | 15% |
| 5 | Defensibility | 10% |

### 1. Founder signal — 30%

| Score | Anchor |
|---|---|
| 0–20 | No founders named anywhere public |
| 21–50 | Founders named. No prior role in this domain, and no public technical record. |
| 51–79 | Either: built a version of this internally at a company that needed it — or has a public technical record in this domain: repositories, contributions, a launch thread explaining the problem in their own words |
| 80–100 | Owned this system at scale, or exited in this category |

This weight is the highest. At seed, the team is the only input that does not change.

**Two kinds of evidence, ranked.** Career history is the better evidence and is
read first. A public technical record is the substitute when career history is
unavailable.

| Tier | Evidence | Source | Reaches |
|---|---|---|---|
| Primary | Prior titles, employers and dates | People Data Labs, keyed on the LinkedIn URL published on the YC company page | up to 100 |
| Fallback | Repositories, contributions, a founder's own account of prior work in a launch thread | GitHub, Hacker News, the company team page | **up to 79** |

**The fallback cannot reach 80.** The top band asserts that a founder ran this
system at scale, and a GitHub profile does not establish that. A company scored
on the fallback alone is capped at 79, and the memo says which tier was used.

### 2. Traction evidence — 25%

| Score | Anchor |
|---|---|
| 0–20 | Landing page or waitlist only. No launch, no named users, no usage number. |
| 21–50 | A launch happened. Engagement was thin. One weak signal only. |
| 51–79 | One strong signal: an active repository, real launch discussion, named customers, or measurable package usage |
| 80–100 | Two or more independent signals agree |

**Accepted evidence, any of:** Hacker News launch points and comment count;
npm or PyPI monthly downloads; repository commit activity and contributor
count; named customers on the company site; team size and its growth; open
engineering roles.

**No public repository is not a penalty.** Closed source is a business choice,
not a traction signal. Score the company on whatever evidence does exist.

This rule came from a control case. Emergent is a Y Combinator company that is
doing well, and its public GitHub organisation holds four repositories: two
forks, a small chat client, and a Telegram bot, none above two stars. Under
anchors written in terms of commits and repositories it would have scored near
zero on a quarter of the total. A missing repository means the instrument does
not apply, not that traction is absent.

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

**First, on each metric:**

**Rule 3 — Uncited score.** A metric with an empty evidence list takes a
maximum score of 50 for that metric. The limit applies to the metric only. It
does not limit the total directly. The reduced metric score then enters the
weighted sum. The memo names each limited metric.

**Then, on the result:**

**Rule 1 — Traction floor.** A traction score below 25 limits the *total* to 60.

**Rule 2 — Thesis gate.** A thesis fit below 40 forces the *verdict* to Pass.
The total keeps its value. The memo shows both.

**Rule 4 — No founder evidence.** A company with no founder record cannot
exceed **Watch**, whatever the total. The memo names the reason.

Rule 4 exists because founder data is the one input that costs money to obtain.
It is not fetched for every company, so a score could otherwise be produced for
a company whose founders nobody has looked at. Without the rule, metric 1 is
uncited, rule 3 caps it at 50, and the other four metrics alone still reach 70:

| Metric | Score | Weight | Contribution |
|---|---|---|---|
| Founder signal | 50 (capped, uncited) | 30% | 15.0 |
| Traction evidence | 79 | 25% | 19.8 |
| Thesis fit | 100 | 20% | 20.0 |
| Why now | 100 | 15% | 15.0 |
| Defensibility | 100 | 10% | 10.0 |

Total 79.8, which would otherwise read **Take a meeting** for a company whose
founders we never looked at. Rule 4 holds it at Watch until someone does.

## What gets scored

Nothing is scored automatically. A partner searches the collected companies,
reads the list, and selects **up to 20**. Only those are analysed.

```
search        →  candidates from the database, instant, no AI
select        →  a person picks up to 20
enrich        →  founders and launch threads for those 20 only
score         →  all five metrics, then the overrides
memo          →  one per company
```

There is no automatic ranking pass. Ranking a thousand companies on the
evidence that is free for all of them — a description and a points count —
would produce an ordering the thesis cannot defend, and it would decide which
companies get looked at properly. That decision stays with the partner.

The consequence is that every scored company has been enriched first, so
metric 1 is normally cited and rule 4 rarely fires. When it does fire it means
something specific: enrichment ran and found nothing — no YC page, no website
to search, or no record at the provider. That is worth seeing in a memo rather
than hiding behind a number.

## Blind spots

These are stated so a reader interprets the scores correctly.

- **Bias toward launched companies.** A stealth company scores near zero on
  traction. It cannot clear the floor. This is a real cost of the thesis.
- **No market score.** Market size at seed is mostly fiction. Market appears
  as context in the memo. It carries no weight.
