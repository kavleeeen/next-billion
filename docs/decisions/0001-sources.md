# 0001 — Data sources

**Date:** 2026-08-15
**Status:** accepted

**Decision:** Discovery from the **YC companies API** and **Hacker News**. Enrichment from
**GitHub**, plus **npm/PyPI** where a package exists.

Every number below came from a live call made while deciding. Commands to reproduce them are in
§7. Sources that were tested and could not be used are in §8.

---

## 1. YC companies API — discovery

```
GET https://api.ycombinator.com/v0.1/companies?batch=W25   → 200
```

Undocumented but stable and public, and it needs no key. Returns
`{companies, page, nextPage, totalPages}`, 20 per page. Each record carries `name`, `website`,
`oneLiner`, `longDescription`, `batch`, `industries`, `locations`, `teamSize`, `status`, `slug`.

This is the entire sourcing requirement in one call, with no scraping. Two fields do double duty:

- `batch` gives the vintage, which enforces the thesis's "past Series A" exclusion without any
  funding data.
- `industries` pre-filters thesis fit before spending an LLM call.

The brief names "a feed like the YC W25 batch" as an example seed input.

**Cost:** YC companies only. Hacker News Show HN is the correction, and the bias is recorded in
the thesis blind spots.

---

## 2. Hacker News — discovery and traction

```
GET https://hn.algolia.com/api/v1/search?tags=show_hn&numericFilters=points>30   → 200
GET https://hacker-news.firebaseio.com/v0/topstories.json                        → 200
```

No key on either. The official Firebase docs state "there is currently no rate limit". Algolia
supports `tags` (`show_hn`, `ask_hn`, `front_page`, `author_*`) and `numericFilters` on `points`,
`num_comments` and `created_at_i`.

Volume over the last 12 months:

| Query | Stories |
|---|---|
| Show HN, "agent", >30 points | 396 |
| Show HN, "LLM", >30 points | 339 |
| Show HN, "infrastructure", >30 points | 50 |
| Launch HN, all topics | **125** |

The two tags behave very differently, and sampling showed why:

```
Show HN     687p  Forge – Guardrails ...              github.com
            570p  I built a sub-500ms voice agent     ntik.me          ← personal site
            386p  Continue? Y/N: a 60-second game     llmgame.scalex.dev
            340p  AI agent on a $7/month VPS          georgelarson.me  ← personal site

Launch HN   322p  Freestyle – Sandboxes for Agents    freestyle.sh
            240p  RunAnywhere (YC W26)                github.com
            215p  Adam (YC W25) – Open-Source AI CAD  github.com
            169p  AgentMail (YC S25)                  (text post)
```

Show HN is high recall and low precision — largely side projects on personal domains. Launch HN
is low volume and high precision — every item is a funded company, with the batch code in the
title. Both are used, for different jobs.

Hacker News is also the only free source of **founder voice**. On a launch thread the founders
reply in the comments with where they worked and what they built before, each reply carrying a
permalink. That is metric 1 evidence with a citable source.

---

## 3. GitHub — enrichment, and secondary discovery

Repo search yield:

| Query | Repos |
|---|---|
| `topic:llm created:>2025-01-01 stars:>100` | 2,366 |
| `topic:ai-agents created:>2025-01-01 stars:>100` | 1,747 |
| `topic:vector-database created:>2025-01-01 stars:>100` | 76 |

Applying a cheap public company filter — owner is an Organization, declares a real domain (not
`github.io` or similar), org created after 2023 — to 44 owners across five topics:

```
look like seed-stage companies : 19  (43%)
personal / side projects       : 19
incumbents / pre-2023 orgs     :  6

browser-use   browser-use.com  109k★ gh-verified   ComposioHQ  composio.dev  72k★ gh-verified
getzep        getzep.com        30k★ gh-verified   simstudioai sim.ai        29k★
tensorzero    tensorzero.com    12k★               maximhq     getmaxim.ai    7k★
```

43% is a usable yield for finding non-YC companies. **But GitHub search can only find companies
that chose to be open**, which is a structural bias, not a tuning problem.

### npm and PyPI

The traction signal that survives a closed-source posture — a package can be public while the
source is private.

```
npm  @modelcontextprotocol/sdk   198,046,096 downloads/month
npm  langchain                    11,309,530 downloads/month
PyPI langchain                   276,617,423 downloads/month
```

Free, no key, and a real usage number rather than a proxy.

---

## 4. Linking a company to its GitHub org

There is no public registry mapping a company to its repository. The link has to be inferred
from public signals and then verified. Four iterations:

| Version | Method | Rate | Problem found |
|---|---|---|---|
| v1 | Company homepage HTML → `github.com/<org>` links | 14% | Most sites are JavaScript-rendered; the served HTML has no links |
| v2 | + guessed org slugs, verified by exact host match | 29% | Guessing is weak; exact host fails on subdomains |
| v3 | Same, on a thesis-filtered pool | 31% | Keyword filter was crude |
| v4 | + registrable-domain match, + GitHub org search | 59% | **3 false positives** — accepted `is_verified` alone |
| **v4 corrected** | Require domain agreement; `is_verified` only strengthens | **41%** | — |

The false positives are worth recording, because the failure is subtle:

```
Artifact  artifact.engineer → slsa-framework   accepted on "github-verified" alone
Dex       joindex.com       → chainflip-io     accepted on "github-verified" alone
Ergo      joinergo.com      → ergo-services    accepted on "github-verified" alone
```

`is_verified` means GitHub confirmed the org owns *some* domain. It says nothing about *this*
company's domain.

**Accepted rule:**

```
A. company site HTML     → github.com/<org> links
B. GitHub org search by company name, top 8
C. HN launch URL, when it points at github.com
D. npm / PyPI package "repository" field

ACCEPT only when registrable_domain(org.blog) == registrable_domain(company.website)
is_verified and README links raise confidence; neither accepts on its own
otherwise → unresolved, and record that the search ran
```

`registrable_domain` matters: `app.emergent.sh` and `emergent.sh` are the same company.

---

## 5. The finding that shaped the thesis

Emergent (emergent.sh) was used as a control: a YC company that is doing well.

Guessing failed. Org search plus the corrected domain rule found it:

```
login    emergentbase
name     Emergent
blog     https://app.emergent.sh
created  2024-04
```

Its four public repos:

```
metabase-helm         ★2   a fork of someone else's helm charts
emergentintegrations  ★2   small LLM chat client
cub                   ★2   telegram assistant
godotenv              ★0   a fork of joho/godotenv
```

None is the product. The product is closed.

**A correct resolution can still carry zero information.** Resolution is not signal. A company
with no meaningful public code has not demonstrated weak traction — the instrument simply does
not apply to it.

This makes GitHub unusable as a load-bearing traction metric for any thesis that includes
closed-source companies, and it is the reason the metric 2 anchors are written in
source-agnostic language rather than in terms of commits and repositories.

**Consequences carried into the pipeline:**

1. Metric 2 accepts any of: repository activity, launch discussion, package downloads, named
   customers, team size. No single source is load-bearing.
2. A resolution attempt that finds nothing is recorded as *searched, not found* — distinct from
   *not searched*, which is what the uncited-score override is for.
3. Every resolved GitHub org carries its evidence list, so a reviewer can check the match.

---

## 6. Corrections made along the way

Recorded because the corrections are the reasoning:

1. **"YC has no API; it needs a scraper."** False — asserted before testing. There is a free
   JSON API.
2. **"Block `github.com` as a non-company host."** Wrong for this thesis. Half the sampled
   Launch HN posts point directly at the company's own repository.
3. **"No repository found is evidence of absence, so a low traction score is defensible."**
   Emergent disproves this.
4. **Exact host comparison** instead of registrable domain — missed `app.emergent.sh`.
5. **Accepted `is_verified` alone** as proof of a match — produced three wrong companies.
6. **Recommended Hacker News + Product Hunt before testing YC** — recommended before measuring.

### Known gaps

- **Founder extraction is untested**, and metric 1 is the heaviest weight at 30%. If founder
  names and one verifiable prior role cannot be found reliably, that weight is capped by the
  uncited-score override for most candidates.
- **Hacker News thread coverage is unmeasured.** If most YC companies have no Launch HN or Show
  HN thread, the founder-voice advantage largely disappears.
- **Website fetchability is unmeasured.** The 14% v1 result suggests many company sites return
  little useful text without a browser. That decides whether a headless browser is needed —
  scope worth avoiding.

---

## 7. Reproduce

```bash
# YC
curl -s "https://api.ycombinator.com/v0.1/companies?batch=W25" | head -c 400

# Hacker News
curl -s "https://hn.algolia.com/api/v1/search?tags=show_hn&query=agent&numericFilters=points>30" | head -c 300
curl -s "https://hn.algolia.com/api/v1/search?query=%22Launch+HN%22&tags=story" | head -c 300

# GitHub
gh api "search/repositories?q=topic:llm+created:>2025-01-01+stars:>100" --jq .total_count
gh api orgs/emergentbase --jq '{login,name,blog,public_repos}'

# npm / PyPI
curl -s "https://api.npmjs.org/downloads/point/last-month/langchain"
curl -s "https://pypistats.org/api/packages/langchain/recent"
```

---

## 8. Appendix — sources tested and not used

| Source | Result | Reason |
|---|---|---|
| Crunchbase | `401` on live call | Closed. No free tier, no trial key. |
| Twitter/X | Pay-per-use only | Closed to new self-serve projects. |
| Product Hunt | Not tested | Needs a developer token. |
| Hugging Face | 200 | Applies only to model-publishing companies. |
| SEC EDGAR (Form D) | 200 | Real funding data, but company-name matching is too noisy for the payoff. |

**Crunchbase** was called live on both documented URL forms:

```
GET https://api.crunchbase.com/v4/data/autocompletes?query=freestyle
→ [{"status":401,"code":"LA401","message":"Unauthorized user_key"}]
```

The Basic plan is discontinued and no new Basic API keys are issued. There is no trial key and
no sandbox; the 7-day Pro trial covers the website only. Entry-level API access runs roughly
$588–1,188/year behind a signed licence. Beyond cost, it sells funding and narrative — which
this thesis deliberately does not score.

**Twitter/X** no longer offers Basic or Pro to new projects; only pay-per-use self-serve remains,
with Enterprise required above 2M monthly reads. A reviewer could not run the pipeline without
paying.

**Product Hunt** is the only free source that surfaces closed-source non-YC companies, which is
a real gap the selected sources leave. It is deferred rather than rejected, and should be
measured the same way as everything else here before adoption.
