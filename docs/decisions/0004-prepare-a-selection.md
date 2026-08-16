# 0004 — Evidence is gathered for a selection, not for everything

**Date:** 2026-08-16
**Status:** accepted
**Supersedes:** the sync-time thread pulling added in `cc583ed`

A partner selects up to 20 companies. Everything expensive happens to those 20
and nothing else. This records why, including the version we built first and
then removed.

```
sync       nightly    all companies      free        name, description, batch, traction
select     a person   up to 20           —           judgment, not a ranking
prepare    on demand  the 20 only        ~40 credits launch threads + founders
score      on demand  the 20 only        LLM         five metrics, then the overrides
```

---

## 1. Why there is no automatic ranking

The obvious design is a cheap pass that scores every company on the evidence
that is free for all of them, then takes the top 20. We planned it, and dropped
it before writing any of it.

The free evidence is a description, a batch code and a points count. Metric 1 —
founder signal, the heaviest at 30% — has nothing to read until someone pays.
So a ranking would be an ordering produced almost entirely by metrics 3, 4 and
5, presented as if the thesis had spoken.

It would also be the thing that decides which companies get looked at properly.
That decision is the partner's job, and it is cheap for them to do: the list is
searchable and instant.

The consequence is written into `THESIS.md` as override 4 — a company with no
founder record cannot exceed Watch — so a score can never be produced for a
company nobody has examined.

---

## 2. Why threads left `sync`

The first version pulled Hacker News launch threads at the end of every sync,
capped at 40, highest-scoring first. The reasoning was that comments are free
and the fetch is incremental, so the backlog would drain over a couple of weeks
and steady state would cost seconds.

Measured after one run:

```
stories                                   735
threads fetched                            40
companies with at least one thread        729
companies with comments                    40   (5%)
```

Two problems, and the second is the real one.

**It is slow to converge.** 735 threads at 40 per run is roughly 18 nightly
runs before coverage is complete.

**It fetches the wrong things.** The cap is ordered by points, so it collects
the loudest threads on Hacker News. A partner selecting by topic, batch or name
has a 95% chance of picking a company with no comments — and the pipeline has
already spent its effort on companies nobody asked about.

Sorted by name, the first ten companies in the database look like this:

```
18 Words                       1160 pts   thread pulled
1Code                            75 pts   no
30u30.fyi                       256 pts   no
3D Mahjong, Built in CSS        138 pts   no
A CSS-Only Terrain Generator    371 pts   no
```

Doing it for a selection instead costs about five seconds for 20 companies and
gives complete coverage of exactly the companies that matter.

---

## 3. Why `prepare` is one step, not two

Threads and founders are gathered together, in that order.

| Step | Cost | Feeds |
|---|---|---|
| Launch threads | free | Metric 4, and metric 1's fallback tier |
| Founders | ~2 credits each | Metric 1's primary tier |

They are one operation because a company missing either is not ready to score,
and two separate buttons invite a half-prepared company that scores lower than
it should for reasons nobody can see.

**Threads run first because they are free.** If the credit ceiling is reached
part-way through enrichment, the free evidence is already stored, and the run
reports how far it got.

**A selection gets every thread its companies have**, ignoring the points
ordering `sync` used. Rowboat launched three times across eleven months; a
scorer should see all three, because what changed between them is the signal.

---

## 4. What re-running costs

Nothing. Both halves skip work already done:

```
first run    threads 4   comments 267 (72 from founders)   founders 9   credits 9
second run   threads 0   comments 0                        founders 0   credits 0
```

A thread is marked fetched whether or not it held usable comments, so an empty
one is not re-read. A company with founders is skipped unless `--force`.

---

## Consequences

1. `sync` is free, fast and complete. It never spends credits and never fetches
   a thread.
2. Complete evidence exists for exactly the companies someone selected.
3. The 20-company limit is enforced in code, not by convention.
4. Unknown ids are dropped with a warning rather than failing the batch; an
   all-unknown selection raises.
5. `pipeline comments --limit N` remains, as a manual way to warm the cache.
6. Nothing ranks companies automatically. If that turns out to be wrong, the
   evidence for a ranking pass is in §1, not in this file's absence.
