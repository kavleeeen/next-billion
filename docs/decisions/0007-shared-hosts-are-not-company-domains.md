# 0007 — A shared host is not a company domain

**Date:** 2026-08-16
**Status:** accepted
**Language:** ASD-STE100 Simplified Technical English

## In short

Some companies write a GitHub link where their website should be, so when we
asked "who works at this website?", we got people who work at **GitHub**
instead of the company's founders.

Now we skip those links, so we stop paying for records of the wrong people.

---

The founder search uses a company's website domain. When that domain belongs to
a platform and not to the company, the search returns the platform's staff.

---

## What happened

The first end-to-end test showed ten founders for Airweave. All ten work at
**GitHub**.

Airweave stores `https://github.com/airweave-ai/airweave` as its website. The
code took the registrable domain, `github.com`, and asked the people provider
for owner-level people at that domain. The provider answered correctly. The
question was wrong.

The search cost ten credits and bought ten records of people who have no
connection to the company.

---

## How large the problem is

Of the 1171 companies that have a website:

| Domain | Companies |
|---|---|
| `github.com` | 289 |
| `github.io` | 16 |
| `vercel.app` | 5 |
| `npmjs.com` | 3 |

**313 companies, or 27%.** Each one would attach a platform's employees to a
company, and spend credits to do it.

---

## The decision

`_domain()` gives no domain for a shared host. No domain means no search.

The company then keeps no founder record. Metric 1 has no primary evidence, and
rule 4 holds the verdict at Watch. That result is correct: nobody has
identified the team.

The parsing and the judgment are now separate:

| Function | Answers |
|---|---|
| `normalize.registrable_domain()` | What is the domain? |
| `enrich._domain()` | Is it a domain we may search? |

The GitHub matcher needs the first question only, because it compares a
repository's homepage with a company's website. It must not receive `None` for
`github.com`.

---

## What the rule does not do

It matches the **whole registrable domain**, never a part of a name. A company
at `github-tools.io` or `mygithub.com` keeps its domain, because those are its
own. A test holds this.

---

## Consequences

1. 313 companies get no founder search, thus they spend no credits on people
   who work somewhere else.
2. Those companies score metric 1 on the fallback tier, which cannot exceed 79.
3. The ten incorrect records were deleted from the database.
4. `0006-github-as-a-source.md` recovers the true company domain from the
   repository `homepage` field, thus many of these 313 companies can be
   searched again, with the correct domain.
