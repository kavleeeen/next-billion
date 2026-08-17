# Analysis stage — plan

**Date:** 2026-08-16
**Status:** The stage is built and it runs. Six companies have a score. The
memo renderer and the calibration record are not built.

The sourcing stage and the evidence stage are complete. For each selected
company, `prepare` collects this data: the description, the industries, the
traction, the prior roles of the founders, and the words of the founders in
their launch thread. No code gives a score yet. The `analyses` table is empty.

This plan starts with the memo. It then shows how we check the scores. These
two items decide the quality of the work. The modules come from them.

---

## 1. The memo, specified first

A partner must understand the call in 60 seconds. This is a specification, not
a target. The memo has these properties:

- One page.
- The verdict and the total are in the first line.
- Each claim has a link to its source.
- The five metric scores are in one table, with the weight of each metric.

Two sections are easy to omit. Both are necessary:

- **What would move this company to a meeting.** Each item is specific and a
  person can check it.
- **What we could not find.** Each item is data that we looked for and did not
  find.

A memo that shows the missing data is more reliable than a memo that hides it.
These two sections also make the override rules visible to the reader.

The memo footer gives the model name, the thesis version and the date. The same
evidence gets different scores from different models. Refer to §7.

---

## 2. How we check the scores

A score is not correct because a model produced it. There are five checks. All
are cheap. The first check is the most important.

**a. Hand-scores, before the model runs.** The author gives scores to five
companies by hand. The author uses the anchors in `THESIS.md`. Then we compare
the two sets of scores. We record each disagreement. We also record which score
was wrong, and why. This is the only evidence that the rubric has a meaning.

**b. Stability.** Give a score to the same company two times at temperature 0.
If the scores change, the prompt is not sufficiently specific. Gemini accepts
the `temperature` parameter, thus this check operates as written. But
temperature 0 does not guarantee the same result. Therefore the output of this
check is a measurement of the difference, not a statement that there is none.

**c. Difficult companies.** Some companies must fail. Examples: a consumer
application, a company after Series A, a company with no founders. If the
thesis gate does not operate, the rubric is wrong.

**d. Distribution.** Give scores to 20 companies. Then examine the range. If
all the results are Watch, the anchors do not separate the companies. A flat
set of results is a failure, even when each score looks correct.

**e. Difficult JSON.** We send the validator replies that have the correct
shape but bad content. Examples: an invented evidence id, a fallback tier with
a score of 85, a total that the prompt prohibits. This check is built and has
48 tests. It does not need the model, and it did not wait for the model.

---

## 3. Robustness

| Failure | Behaviour |
|---|---|
| No founder is found | Metric 1 has no citation. Rule 3 limits it to 50. Rule 4 limits the verdict to Watch. The memo gives the reason. |
| No launch thread | Metric 4 uses the description only. The memo records this. |
| No description | Thesis fit has no citation, thus it becomes 50. The result is usually a Pass, which is correct. |
| The JSON has the wrong shape | This is not possible. `responseSchema` controls the shape. §7 gives the test on five models. |
| **The model invents an evidence id** | The validator refuses it. The model gets one opportunity to correct it. We remove each claim that keeps an unknown id. Rule 3 then limits that metric to 50. |
| The model returns a total | The validator refuses the reply. Python calculates the total. |
| The correction turn also fails | Stop work on that company. Record the reason. Continue with the other companies. |
| The API refuses the request | `http.py` sends the request again, with an increasing delay. §7 gives the free-tier limits. |
| The provider has no record for one founder | The other founders keep their data. The tier is recorded for each founder. |
| **The company website is a shared host** | No founder search runs. The company keeps no founder, and rule 4 limits the verdict to Watch. See §3a. |

We write a test for each row.

### 3a. Shared hosts, found by a live test

The first end-to-end test showed ten founders for Airweave. None of them work
at Airweave. All ten work at GitHub.

The cause is the company website. Airweave stores
`https://github.com/airweave-ai/airweave`, so the founder search used the
domain `github.com` and returned people employed by GitHub. The search cost ten
credits and bought ten wrong records.

The problem is not rare. Of the 1171 companies that have a website:

| Domain | Companies |
|---|---|
| `github.com` | 289 |
| `github.io` | 16 |
| `vercel.app` | 5 |
| `npmjs.com` | 3 |

That is 313 companies, or 27%. Each one would attach the staff of a platform to
a company, and spend credits to do it.

**The fix.** `_domain()` returns nothing for a shared host, so no search runs.
The company keeps no founder record, metric 1 has no primary evidence, and rule
4 limits the verdict to Watch. That result is correct: nobody has identified
the team.

The ten wrong records were deleted from the database.

This is why metric 1 has two tiers. A company on a shared host can still score
on the fallback tier, from what the founders say in their own launch thread,
and that tier cannot reach 80.

---

## 4. The provenance rule

`THESIS.md` says that each score needs a minimum of one source. A model invents
a source easily.

**The model does not receive a URL, and it does not return a URL.** Each
evidence item has an `id`. The model cites the ids. Python then changes each id
back to its source URL for the memo. The model cannot invent a citation that
operates, because we control the ids.

**We compare each id in the reply with the evidence bundle.** An unknown id
fails the check. The model gets one opportunity to correct it. We remove each id
that is still unknown. If a metric then has no claims, rule 3 limits it to 50.
Without this check the citations have no value, and a reader cannot examine a
memo.

---

## 5. The prompt is an artifact

`prompts/score_company.v1.md` is in the repository. The anchor tables come from
`THESIS.md` at build time. Thus the prompt and the document cannot become
different.

Each version that fails the calibration stays in the repository. These versions
are cheap evidence of the method, because the work produces them.

There is one change from the first draft of v1. The last instruction was
"Return only JSON matching this shape". A `responseSchema` on the request
replaces it. The API controls the shape. Thus the instruction is not necessary,
and the prompt uses its words for judgment and not for format.

---

## 6. Architecture

```
evidence.build(id)     → items, each with an id and a source URL
gemini.score(evidence) → JSON, shape controlled by responseSchema
validate(reply, ids)   → problems; repair_message() sends them back, one time
scoring.apply()        → rule 3, tier limit, weights, rules 1/2/4 → verdict
memo.render()          → memos/<slug>.md
```

Python does all the arithmetic. The model does not return a total, and it does
not see a total.

`THESIS.md` sets the sequence of the override rules:

```
rule 3, for each metric   no citation → 50
metric 1 tier limit       fallback tier → 79
weighted sum              → total
rule 1                    traction below 25 → total limited to 60
rule 2                    thesis fit below 40 → verdict becomes Pass
rule 4                    no founder record → verdict limited to Watch
```

The numbers are in `scoring/thesis.py`. `test_thesis_constants.py` reads
`THESIS.md` and checks that each number is still there. Thus the document and
the code cannot become different without a test failure.

The cache keys are the company, the prompt version and the model id. Thus a
change to the memo template does not cause a new analysis.

**Two small additions to existing modules.** Both keep the zero-dependency
rule:

- `http.py` gets `post_json`. Today it has GET only. The Gemini REST API is a
  JSON POST. This addition is approximately 20 lines, and it uses the existing
  retry code. There is no vendor SDK, thus the count of runtime dependencies
  stays at zero.
- `config.py` gets a `GeminiSettings` block. Its structure is the same as
  `PDLSettings`: the key name, the base URL, the model id, and the maximum
  number of calls for one run.

---

## 7. The model

We chose the model with a test on the key. We did not use a published table.

**Gemini Pro is not available on the free tier.** These are measurements:

| Model | Result |
|---|---|
| `gemini-3.1-pro-preview` | 429. Each free-tier quota reports `limit: 0`. |
| `gemini-2.5-pro` | 404. "No longer available to new users." |

Pro needs a billing account. The brief permits free tiers. Thus the pipeline
uses Flash and has no cost. If you enable billing later, only the model id
changes.

**We sent the same scoring task to five Flash models. Each request had a JSON
schema. All five models that answered returned valid JSON with the correct
shape.**

| Model | Score | Thinking tokens |
|---|---|---|
| `gemini-3.7-flash` | no answer (503, high demand) | — |
| **`gemini-3.6-flash`** | **25** | **430** |
| `gemini-3.5-flash` | 15 | 514 |
| `gemini-3-flash-preview` | 18 | 508 |
| `gemini-2.5-flash` | 15 | 314 |
| `gemini-3.1-flash-lite` | 15 | none |

### The allowance decides the model

The account dashboard gives the numbers. The documentation does not: it says
only that "rate limits ... can be viewed in Google AI Studio".

| Model | RPM | TPM | RPD |
|---|---|---|---|
| Gemini 2.5 / 3.5 / 3.6 / 3.7 Flash | 5 | 250K | **20** |
| **Gemini 3.5 Flash Lite** | **15** | 250K | **500** |
| Gemini 3.1 Flash Lite | 15 | 250K | 500 |

**A full Flash model allows 20 requests each day.** One call for each company
means a selection of 20 spends the whole day allowance and leaves nothing for a
correction turn. A full Flash model cannot do the work.

**The pipeline uses `gemini-3.5-flash-lite`.** It allows 500 requests each day
and 15 each minute. It answers in 4 seconds, which is faster than the full
Flash models. `docs/decisions/0005-selection-cap-of-fifteen.md` holds this
decision and the selection cap that comes from it.

The cost is zero. A run of 15 companies is 15 requests of the 500 for that day.

### The pacer

The limit for each minute is 15 requests. Two workers at 4 seconds each would
send 30. Thus the client paces its own requests at 12 for each minute, which is
20% below the limit.

A refusal is not free: it spends a request and returns nothing. To stay below
the ceiling costs less than to find it.

A refusal that names a **per-day** quota is never repeated. A day does not
refill inside a run, so each repeat spends more of the allowance that just ran
out. A refusal that names a **per-minute** quota is repeated, after the delay
the server states.

### How much the model changes a score

Six companies were scored by `gemini-3.6-flash` and then again by
`gemini-3.5-flash-lite`, on the same evidence.

| Company | 3.6 Flash | 3.5 Flash Lite | Difference |
|---|---|---|---|
| bitrig | 73.0 | 75.0 | +2.0 |
| AgentMail | 59.8 | 69.2 | **+9.4** |
| Airweave | 66.8 | 66.8 | 0.0 |
| Luminal | 65.0 | 62.0 | −3.0 |
| Adam | 50.0 | 52.0 | +2.0 |
| Mosaic | 46.0 | 47.0 | +1.0 |

The mean absolute difference is **2.9 points**.

An earlier measurement on a one-line test prompt gave 15, 15, 18 and 25 for the
same input. That test was too small to be a guide, and it made the models look
more different than they are. On complete evidence they agree closely.

**But a verdict can still change.** Adam moved from Pass to Watch. The score
moved only 2 points; the verdict moved because thesis fit crossed the gate at
40. A gate is a sharp edge, thus a company near one can change verdict on a
small difference. The memo shows the metric and the flag, so a reader can see
when this happens.

This does not replace the hand-scores in §2a. Two models that agree can still
both be wrong.

### 7a. Measured on real companies

Three companies scored in 23.5 seconds with three workers. That is about eight
seconds for each company, and about one minute for twenty.

Six companies have a score:

| Company | Total | Verdict |
|---|---|---|
| bitrig | 73.0 | Take a meeting |
| Airweave | 66.8 | Watch |
| Luminal | 65.0 | Watch |
| AgentMail | 59.8 | Watch |
| Adam | 50.0 | Pass |
| Mosaic | 46.0 | Pass |

The range is 46 to 73, and all three verdicts occur. Check (d) in §2 asks for
this: a flat set of results is a failure, and this set is not flat.

Rule 2 operated two times. Mosaic scored 15 on thesis fit and Adam scored 35,
so both verdicts became Pass. Both companies are design tools and not
infrastructure, thus the rule is correct.

No claim was dropped, and no problem remained after the checks. The correction
turn did not run.

---

## 7b. The 1-hour rule

A company selected a second time is not prepared and scored again from the
start. Work done recently is used again.

| Work | Cost | Rule |
|---|---|---|
| Hacker News threads | free | Read again after 1 hour. Replies keep arriving after a launch. |
| The score | free | Produced again after 1 hour, and only for the same model and prompt version. |
| **Founder data** | **~2 credits each** | **Never bought again on a timer.** Only `--force` buys it a second time. |

The founder data is the exception on purpose. The allowance is 100 credits for
each month. A 1-hour rule on 20 companies would cost about 40 credits each time
someone selected them again, and two such runs would finish the month.

A score is compared with its model and its prompt version. A score from a
different model is not a fresh score. It is a different opinion, and to use it
again would hide the change.

The window is `settings.refresh_after_hours`.

---

## 8. Sequence

| # | Commit | Result | State |
|---|---|---|---|
| 1 | Scoring constants, and a test against `THESIS.md` | The rubric in code. It cannot become different from the document. | **built** |
| 2 | Response validator and correction message | The check for an invented citation | **built** |
| 3 | Evidence bundle | Model input that is the same at each run, and that a person can examine | **built** |
| 4 | `post_json`, Gemini settings, client with the correction turn | The call, still with no dependency | **built** |
| 5 | Prompt v1 with `responseSchema` | The artifact | **built** |
| 6 | Scorer, override rules, tests | The arithmetic | **built** |
| 7 | Shared-host fix, and the score in the list and the viewer | A partner sees the verdict beside the company | **built** |
| 8 | **Calibration record** | Five hand-scored companies against the model | |
| 9 | Memo renderer | The deliverable | |
| 10 | The memos and the score distribution | Output that nobody must produce again | |

Commits 1 and 2 do not need the model or the key. Thus we built them while the
model decision was open. The calibration comes before the memos. Thus the memos
use a rubric that we checked, and not a rubric that we assumed.

The tests count 223 and they run in 0.5 seconds. No test uses the network.

---

## 9. Decisions

**One call for each company. Not one call for each metric.** One call costs
less, and the model sees all the evidence together. The risk is the halo
effect: the model gives all five scores from one general opinion. The control
is a comparison. We score two companies with both methods, and we record the
difference. We record this risk here, and not later. A known risk that nobody
records is the same as a hidden risk.

**Gemini, on the free tier, with one Flash model.** Refer to §7.

**The validator is Python code. It is not a tool that the model calls.** The
test showed that `responseSchema` already controls the shape. Thus a tool that
checks the shape has no value. Also, a model can decide not to call a tool, but
Python code always operates. The model still does the correction, because the
problems go back to the model in a second turn.

**The correction is one turn. It is not a loop.** A model that fails the rules
at the second attempt also fails at the fifth attempt. An unlimited loop on a
rate-limited free tier fails slowly. One turn fails quickly.

---

## 10. Open questions

**Do we enable billing to get Pro?** The deliverable does not need it. Ask this
question only if the calibration in §2a shows that Flash disagrees with the
hand-scores, and if better reasoning can correct this.

**Who gives the hand-scores to the five companies?** This must be the author.
We calibrate the judgment of the author. Also, the brief gives a low mark to
reflective work that a model wrote.

---

## What this plan does not include

- There is no automatic ranking stage. Refer to `0004-prepare-a-selection.md`
  §1.
- There is no agent loop and no tool call during the scoring. Python collects
  the evidence first. Thus a person can repeat a run, and a missing tool call
  cannot limit a metric without a record.
- There is no second model as a judge. The citation check is deterministic and
  stronger.
- There is no vendor SDK. The API is a JSON POST, thus the count of runtime
  dependencies stays at zero.
