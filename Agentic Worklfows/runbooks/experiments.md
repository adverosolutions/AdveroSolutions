# Runbook: copy experiments and campaign verdicts (M3, M4; brief A7)

## Purpose
Answer three questions every Friday, from live Instantly data, without touching anything:

1. **Which campaigns get the Oct 11 inboxes?** `jobs/campaign_verdicts.py` applies the M4 rules
   (no verdict before 1,000 sends; with a positive at 1,000 run to 3,000; recruiting retires at
   1,000 with zero positives) and projects the date each campaign reaches its next decision point.
2. **Which copy is winning?** The same job refreshes `config/experiments.json`, the one place that
   says what is being tested, how much sample it has and whether it has an answer.
3. **Is new copy allowed out?** `services.experiments.copy_validator.validate_copy()` is the gate
   for new copy, and the Phase 0 change-set's apply script runs it on every campaign it applies. See
   "The copy validator".

Everything here is read-only against every live system. The job makes GET calls and one POST-shaped
read (`leads/list`); it has no write path, and the only file it changes is
`config/experiments.json` in this repo. `--dry-run` does not change that one either.

## How to run
From `Agentic Worklfows/`:

```bash
# read live analytics, print the verdict table, write no experiment log
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m jobs.campaign_verdicts --dry-run

# one campaign, machine-readable (a subset run never writes the experiment log)
MODE=shadow NOTIFY=off python3 -m jobs.campaign_verdicts --dry-run --json --campaign cleaning_trigger

# what the table looks like after Oct 11
MODE=shadow NOTIFY=off python3 -m jobs.campaign_verdicts --dry-run --as-of 2026-10-24
```

The Friday run, which writes `config/experiments.json` and one Job_Log row:

```bash
MODE=shadow LLM_FAKE=1 python3 -m jobs.campaign_verdicts \
    --out .tmp/campaign_verdicts_$(date +%F).md
```

**The scheduled run keeps notifications ON.** `NOTIFY=off` short-circuits `shared.notify.notify()`
into an in-process list, so a Friday pull that fails because the Instantly key rotated would write
its `failed` Job_Log row, exit 1 and reach nobody, leaving a stale verdict table on the desk.
`NOTIFY=off` belongs on the dry runs above and nowhere else.
`jobs/tests/test_experiments_job.py::test_the_runbook_friday_command_does_not_disable_notifications`
reads this file and fails if a non-dry-run command here ever sets it again.

Schedule: turned off on 2026-09-22. Lorenzo runs the Friday command above by hand; nothing schedules
it (`config/turned_off_jobs.json`, `changesets/schedules/README.md`). It used to run Fri 15:00 CT,
before the 16:00 retro, which now shows it as "turned off" instead of waiting for it.

### Flags worth knowing
| Flag | Effect |
| --- | --- |
| `--dry-run` | does not write `config/experiments.json`. `--out` is still honoured: a markdown file at a path you asked for is the point of the flag, and it is not a live write |
| `--campaign KEY` | narrows the pull **and suppresses the experiment-log write entirely**, dry run or not. The experiments span all six campaigns and `experiment_log.update()` rebuilds `current_sample` from scratch, so a one-campaign run would throw the other five campaigns' sample away and could drag a decided test back under its sample line. The job prints "experiments log NOT written" and why |
| `--as-of` | evaluates at another date. Past 2026-10-11 the capacity multiplier stops being applied, because by then the observed rate already contains the step |

## The verdict rules

| Sends | Positives | Recommendation | Next point |
| --- | --- | --- | --- |
| < 1,000 | any | `keep_running` | 1,000 |
| >= 1,000 | 0, but Instantly reports open opportunities | `hold` (data check, never a retirement) | decided |
| >= 1,000 | 0, recruiting | `retire` | decided |
| 1,000-1,999 | 0, any other niche | `rework_copy` | 2,000 |
| >= 2,000 | 0, any other niche | `retire` (the rework had its 1,000 sends) | decided |
| 1,000-2,999 | >= 1 | `run_to_3000` | 3,000 |
| >= 3,000 | rate >= 0.7% | `scale` | decided |
| >= 3,000 | 0.5% <= rate < 0.7% | `hold` | decided |
| >= 3,000 | rate < 0.5% | `rework_copy` | decided |

**A positive is a lead that ever reached a positive status**, not one that is positive today.
`lt_interest_status` is current state: 1-4 are interested/booked/completed/closed, and **-3 (lost)
and -4 (no show) are counted as positives too**, because they are downstream sales outcomes of a
positive reply and the question this table answers is "did this copy produce a positive reply". On
2026-09-22 rob@cjsglobal.com is -3 on cleaning_reactivation and held his discovery call on Sept 18;
counting current state only would have printed 1 positive for a campaign the blueprint audit credits
with two, and a campaign's positive count would fall every time a call closed or fell through. The
`Positives` cell prints "incl N lost/no-show" so the split is visible. Only -1 (not interested) and
-2 (wrong person) count as negatives.

**Zero counted positives with open opportunities is a data check, not a retirement.** If
`total_opportunities` is non-zero while the replied-lead list carries no positives, the two numbers
disagree (a parsing fault, a status type change, a truncated walk) and the job returns `hold` with
the discrepancy in the flags rather than proposing that inboxes be released.

**Retiring a campaign does not free inboxes today.** All six live campaigns carry the *identical*
12-inbox `email_list`, so the retire text reports what is actually released: that campaign's
`daily_limit` of sending headroom (50/day), plus the count of inboxes no surviving campaign uses,
which is 0. An operator who detached "its 12 inboxes" would destroy the sending capacity of
cleaning and bookkeeping. `verdicts.released_capacity(stats, peers)` computes it; without `peers`
it says the overlap was not computed instead of guessing.

Section 6 thresholds ride along as **flags**. They never change the recommendation; they are there
so the Friday audit sees them in the same row.

**The job proposes. It never retires anything.** A retirement is a live write (campaign pause plus
an `email_list` change), so it goes through a change-set that Lorenzo approves.

### The real-reply flag is campaign-level, not the Section 6 inbox rule
Blueprint Section 6 and M1 level 3 define the reply-rate line as **"< 1% real replies after 100 sent
per inbox"**, measured off `GET /accounts/analytics/daily`, and its remedy is removing that inbox
from the campaign `email_list`. This job only has campaign-level numbers, so:

- the sample gate is scaled by the inbox count (`100 x inboxes`, i.e. 1,200 sends for these
  campaigns), because 300 sends over 12 inboxes is 25 per inbox - a quarter of the threshold's own
  precondition, on one reply;
- the flag text says in so many words that it is a copy signal and that the Section 6 inbox rule
  belongs to `jobs/deliverability_monitor.py`, which reads the per-inbox endpoint.

Before this, the report flagged both bookkeeping campaigns as "below the 1% line" while all 12
inboxes were at 100% warm-up health and the workspace was at ~1.2%, with an inbox-removal action
attached.

## The three projected dates

| Column | Means | Use it for |
| --- | --- | --- |
| ETA now | today's rate, forever | what happens if Oct 11 slips |
| ETA at Oct 11 volume | the same line at the post-2026-10-11 rate, **floored at 2026-10-11** | the floor; this is the "at the 2026-10-11 volume" column the brief asks for |
| ETA blended | today's rate until 2026-10-11, the higher rate after | the date to actually plan against |

The Oct 11 column is a counterfactual, so it is clamped: it can never print a date before the
capacity step it is named after. Unclamped it read 2026-09-25 for all six campaigns, sixteen days
before the step, sitting next to two columns that are real dates.

The rate is the **median of the days the campaign actually sent** over the last 14 days, falling
back to the campaign's `daily_limit`. The mean is wrong here: a launch day or a Sunday with the
schedule off drags it down and pushes every date out. Non-sending days are skipped using the
campaign's own schedule map, which is why 700 sends at 50/day lands on 2026-10-07 and not
2026-10-04: two Sundays fall inside the span.

**A campaign that is not sending gets no date.** Instantly does not zero `daily_limit` on a paused
campaign, so the fallback used to hand a stopped campaign a confident decision date. The rate is 0 -
and every ETA becomes "not at this rate" - when the campaign `status` is not 1 (active), or when it
has sent before and sent nothing across the whole 14-day window. Both cases carry a flag saying
which.

The Oct 11 rate is today's rate times the capacity multiplier from `config/ids.json`: 12 active
inboxes at 25/day is 300/day now, 45 inboxes is 1,125/day, a 3.75x step. **The multiplier stops
being applied once `--as-of` is on or after 2026-10-11**, because by then the observed rate already
contains the step; multiplying again projected 705 sends/day per campaign, 4,230/day across six,
against a real ceiling of 1,125. Change `active_inboxes` or `warming_domains` in ids.json and every
date here moves; the capacity line in the report carries a `WARNING` line when the numbers stop
matching the blueprint's 300 and 1,125, when ids.json lists no active inboxes at all (every rate
reads 0 and the three ETA columns collapse to one number), and when a run after 2026-10-11 still
finds warming inboxes that were never moved into `active_inboxes`. Those warnings are printed in the
document, not only logged, because a `logger.warning` on a cron run reaches nobody.

## Where it stands on 2026-09-22 (first live run)

All six campaigns sit at exactly 300 sends, so **every one is below the verdict line and nothing can
be decided yet**. Blended ETA to 1,000 for all six: **2026-10-07**.

| Campaign | Sends | Real replies | Positives | Opportunities |
| --- | --- | --- | --- | --- |
| cleaning_reactivation | 300 | 4 (1.33%) | 2 (0.67%), one of them lost/no-show | 1 / $1,000 |
| cleaning_trigger | 300 | 5 (1.67%) | 2 (0.67%) | 2 / $2,000 |
| bookkeeping_reactivation | 300 | 1 (0.33%) | 1 (0.33%) | 1 / $1,000 |
| bookkeeping_trigger | 300 | 1 (0.33%) | 0 | 0 |
| recruiting_reactivation | 300 | 3 (1.00%) | 0 | 0 |
| recruiting_outbound | 300 | 3 (1.00%) | 0 | 0 |

Flags: both recruiting campaigns have three negative replies each and no positives, which is the
shape M4 predicted; cleaning_reactivation carries one positive that later closed out. Cleaning holds
4 of the 5 positives in the workspace. No real-reply flag fires: at 25 sends per inbox the Section 6
precondition is not met.

## Three live-shape traps, all load-bearing

**1. `reply_count_unique` already excludes automatic replies.** The obvious reading of M1 level 3
("real replies, exclude auto-replies and OOO") is unique minus automatic. That is wrong and it goes
negative: on 2026-09-22 bookkeeping_reactivation reported 1 unique and 4 automatic, bookkeeping_trigger
1 and 6. The two are disjoint buckets, proved by the fact that they sum to the replied-lead count on
all six campaigns (4+3=7, 5+3=8, 1+4=5, 1+6=7, 3+3=6, 3+3=6). `analytics.real_replies()` returns the
field unchanged and the test
`test_real_plus_auto_replies_equals_the_replied_lead_count_on_every_campaign` pins it. When the
unique field is missing the fallback is `reply_count` **minus** the automatic count, never
`reply_count`, which is the human+automatic total.

**2. `POST /leads/list` silently ignores a filter value it does not recognise.** `FILTER_VAL_LEAD_INTERESTED`
(plausible, and not a real value) returns the same rows as no filter at all, which would have counted
every contacted lead as a positive. `analytics.LEAD_FILTERS` is the verified allow-list and
`replied_leads()` raises rather than sending anything outside it.

**3. Numbers come back as strings often enough to assume they always can.** The steps endpoint
returns `step` and `variant` as **strings, zero-based**, and its totals row is `step: null` on four
campaigns and the *string* `"null"` on recruiting_reactivation. Every numeric field read off this
API goes through `analytics.as_int()`: a string-typed `lt_interest_status` would otherwise zero
every campaign's positives silently and hand recruiting a retirement recommendation. The replied-lead
walk is also de-duplicated on lead id (falling back to lowercased email), because an overlapping
`starting_after` page returns the same lead twice and every counter here counts rows.

## The experiment log: `config/experiments.json`

One document, one list. Hand-written: id, campaigns, hypothesis, what changed, sample needed, arms,
how to measure. Machine-written on every run: `current_sample`, `current_sample_by_campaign`,
`observed`, `observed_by_campaign`, `sample_gate`, `status`, `result`.

Two measurement kinds:

- `campaign_variant` - the arms are Instantly variants of one step, so the numbers come straight
  from the steps analytics and the replied-lead list. This is the only kind the job can count.
- `lead_variable` - the arms are a property of the lead (which icebreaker style it got). Instantly
  has no per-lead-variable analytics, so the job reports the test as **blocked** with the reason
  instead of reporting 0 of 1,500, which would read as "running and losing".

Statuses: `planned` (fewer than two arms have sent anything), `running`, `blocked`, `undecidable`
(every campaign carrying the test is out of it, see below), `decided`.

### `sample_rule` is read, not decoration
`sample_needed` is per arm. `sample_rule` says per *what*, and `experiment_log.sample_gate()`
implements each rule explicitly:

| `sample_rule` | Gate |
| --- | --- |
| `per arm, per campaign` (EXP-001a and EXP-001b, and what M3.3 means) | every campaign running the test needs `sample_needed` sends **on every arm** |
| `per arm, pooled across campaigns of one niche` (EXP-002) | the niche's campaigns are pooled, and every niche group must clear the line |
| `per arm, pooled` | the pooled total must clear `sample_needed x campaigns`, because pooling across niches buys noise, not sample |
| anything else | refused: the job will not decide a rule it does not implement |

Only campaigns that are running **every** arm are compared (`sample_gate.scope`), so the pooled
numbers never put one campaign's control against another campaign's treatment.

**Campaigns that can no longer gather sample are left out (owner decision R12, 2026-09-22).** A
campaign whose status is not active (paused or retired), that sent nothing in the pulled window, or
that `verdicts.decide` puts at `retire` is dropped from the decision, and the reason is recorded in
`sample_gate.excluded` and printed in the "Where it stands" column. Its numbers stay in
`observed_by_campaign` but count on neither side. If every campaign in a test is out, the test is
`undecidable` and the reason names each campaign. The case that forced this is recruiting: M4 runs
it to 1,000 sends and then retires it, which is roughly 250 to 300 step-1 sends per variant, so a
test that kept it in scope under "per arm, per campaign" could never reach 500 on it and could never
be decided. Until its 1,000-send verdict, a recruiting campaign stays in scope and its shortfall line
says that M4 will take it out if it still has zero positives; if it earns a positive and keeps
running, it stays in and has to reach the line like everyone else. `current_sample`
still reports the pooled sample across every campaign, because that is the honest answer to "how
much data exists"; the gate reads `current_sample_by_campaign`.

Why this matters: six campaigns at 90 sends per arm pool to 540, which clears 500. Pooling would
have declared a winner for the old pooled EXP-001 on a sixth of the required sample, across three different niches,
while the Variants table in the same document said `insufficient_sample` for every one of those
steps, because `verdicts.judge_step` applies the line per campaign.

### A decided test is frozen
Once `result.decided_at` is set, the winner, loser, p-value and date stay put. `update()` keeps
refreshing `current_sample` and `observed`, and writes any later recomputation to `post_decision`
(the report shows `decided (frozen)`). Without this, a Friday run with more sample flipped a closed
test back to `running`, erased the winner Lorenzo had already acted on and re-stamped `decided_at`
with the latest run date; removing the losing arm from the campaigns did the same thing a different
way, because its cell then disappears from the steps analytics. **To re-open a test, clear
`result.decided_at` by hand.**

`start_date` is the first run that saw every arm sending, which is not the same as the day the
change-set was applied: `start_date_source` records that, and `start_date_warning` fires when an arm
jumped from nothing to a full sample in one run (a missed run). Reconciling it against the
change-set apply record is open (see the A7 report).

### The seeded tests

EXP-001 used to be one record, "call ask against the low-friction list ask, everything else the
same", pooled over all six campaigns. The staged B variants do not match that (MKT-8), so on
2026-09-22 it was split by what each B actually changes (owner decision R12). Both halves are
**whole-email rewrites**, and a winner credits the rewrite, not the ask alone.

**EXP-001a-reactivation-rewrite** (`cleaning_reactivation`, `bookkeeping_reactivation`,
`recruiting_reactivation`). Step 1 B opens on a niche-specific line ("I build reactivation systems
for commercial cleaning companies"), restates the mechanism for `{{companyName}}`, shortens the
no-risk line and ends on a request for the prospect's list: "send me your list of lost bids or former
clients" (cleaning), "former clients or inquiries that never signed" (bookkeeping), "dormant client
accounts" (recruiting), "and I'll show you which ones are worth chasing". A is the copy live today: a
15-minute call ask in bookkeeping and recruiting; in cleaning a commission-only "would you be open to
it? Let me know" with a different opening.

**EXP-001b-trigger-rewrite** (`cleaning_trigger`, `bookkeeping_trigger`, `recruiting_outbound`).
Step 1 B opens on a niche-specific line, restates the trigger mechanism for `{{companyName}}`
(cleaning uses `{{metro}}` and `{{buildingType}}`; recruiting frames roles open more than three
weeks), adds a one-line benefit, words the guarantee as a condition and ends on an **offer to send
the prospect a list**: "Want me to send over the trigger list I'd start with? ... Reply yes and I'll
get it over". A ends on a 15-minute call ask. This is the opposite direction from EXP-001a, where
the prospect sends the list.

**Status today: both `planned`**, EXP-001a A 596 sends, EXP-001b A 594 (the old record's 1,190 split
by campaign), B 0 on both, because the Phase 0 change-set has not been applied. Each rule is 500 per
arm **in each of its three campaigns**, with the R12 exclusions above.

**EXP-002-icebreaker-style.** Compliment icebreaker against the ten-minute-research standard against
no icebreaker at all. **Status today: `blocked`.** No lead carries an `icebreaker_style` variable, so
the arms cannot be told apart. The list factory (A6) has to stamp it at personalization time and
Instantly has to carry it as a custom variable. Until then the job will keep saying blocked, on
purpose.

### Judging a variant
A variant is judged at **500 sends or more per variant** (M3.3). Below that the answer is
`insufficient_sample` and the job says how many sends are missing. At or above it, a two-proportion
z-test on positives decides: p < 0.05 gives a winner and a loser, anything else is `no_difference`.
The p-value is a tie-breaker on top of the 500-send rule, never a licence to judge a smaller sample.
Positives are attributed to the variant that earned them using the lead's own `email_replied_step`
and `email_replied_variant`; a positive whose reply step is unreadable is left unattributed rather
than parked on step 1, because a mis-attributed positive is how an A/B test gets decided wrongly.

## The copy validator

```python
from services.experiments.copy_validator import validate_copy
report = validate_copy(key, sequence_doc, live_campaign, settings_doc, settings.OFFERS_MD)
if not report.ok:
    raise SystemExit(report.summary())
```

**Wiring status: wired in.** `changesets/instantly_phase0/apply_instantly_phase0.py` imports
`validate_copy` (line 63) and calls it with its defaults for every campaign it applies (line 214), so
the rules below run on the only code path that can PATCH a live campaign. With the defaults, rules 1
and 2 are errors and the readability and new-variable rules are warnings; the strict options
(`strict_readability=True`, `require_known_vars=True`) are not passed there, so pass them yourself
when checking new copy by hand.

It returns a `phase0_lib.Report`, so `.ok`, `.errors`, `.warnings` and `.summary()` behave exactly as
the change-sets already expect. It runs `phase0_lib.validate_sequence` first (balanced braces, 3-5
spin points, known merge variables, the offers.md proof and money rules, no em dash, no exclamation
mark, no AI, signed Lorenzo, thread rules, non-identical A/B variants) and adds:

| Rule | Severity | Why |
| --- | --- | --- |
| A merge variable anywhere inside a spin option | error | phase0_lib catches neither shape: its option check is `VAR_NAME_RE.match(option)` and that pattern never matches the string `{{firstName}}`. This rule is the only guard there is |
| Two proof families in one campaign | error | offers.md allows one proof point per campaign: $6M in 6 months for reactivation, $180K in 90 days for outbound, never both |
| A sentence over 30 words | **warning** | 15 sentences in the already-staged Phase 0 copy are over 30 words in their longest rendering. A gate that turns a Phase 0 apply red on a style rule just gets switched off. Pass `strict_readability=True` for new copy |
| A variable in `new_variables` but not on the live campaign | warning, or error with `require_known_vars=True` | Phase 0 ships `{{buildingType}}` and `{{metro}}` before any lead carries them; the list factory should run the strict version |

The proof markers are **derived** from `phase0_lib.OFFER_MARKERS` (minus the `$150M` both families
share, plus alternative spellings such as `$6,000,000` and `180,000`), so a change to offers.md
moves them instead of silently switching the two campaign-level proof rules off. A family with no
distinguishing marker raises at import rather than passing everything.

Every sentence is measured on the **longest** rendering of the spintax, because the worst case is the
one that lands in an inbox one time in three.

`validate_email(subject, body, known_variables=...)` is the same rules for a single body with no
campaign or offer sheet in hand (a new step, a subsequence body, a draft pasted into a runbook).

### The 15 long sentences in the staged Phase 0 copy
cleaning_reactivation step1/A (40 words); cleaning_trigger step1/A (36), step1/B (33 and 32),
step2/A (34), step3/A (31); bookkeeping_reactivation step1/A (33), step1/B (33);
bookkeeping_trigger step1/A (31), step1/B (37); recruiting_reactivation step1/A (33), step1/B (34),
step3/A (31); recruiting_outbound step1/A (36 and 33).

Most of them are the guarantee sentence, which is long because it carries the number, the window and
the gift card in one breath. Splitting them is a copy decision for Lorenzo, not a code change, and it
belongs in the same pass that applies Phase 0. The change-set is not mine to edit.

## Next verticals
`services/experiments/next_verticals_brief.md` is the brief M4 asks for: commercial landscaping,
commercial pest control, security guards, medical billing and commercial insurance agencies, one
reactivation campaign each with the ICP, the trigger, the proof point and the 1,000-send test, ready
to hand to the list factory. **No campaign in it exists and none may be created**; creating one is a
live write and cleaning has not cleared its verdict line yet.

One thing in it is blocked on Lorenzo: `config/offers.md` defines a commission number for cleaning,
bookkeeping and recruiting and nothing for these five. Until a row exists, copy for a new vertical
says "a commission on the accounts I bring back, nothing up front" and quotes no percentage, because
the offer sheet is the only place pricing comes from.

## Tests
```bash
cd "Agentic Worklfows" && python3 -m pytest jobs/tests/test_experiments_verdicts.py \
    jobs/tests/test_experiments_copy_validator.py jobs/tests/test_experiments_job.py -q
```
All on the fixtures recorded read-only from the live workspace on 2026-09-22
(`services/experiments/fixtures/`). `services/experiments/fakes.py` is the stand-in client; it has
no write methods at all, so a regression that reached for one fails loudly instead of shadow-logging
quietly.

## Failure modes
| Symptom | Cause | Fix |
| --- | --- | --- |
| Every campaign shows hundreds of positives | someone changed the lead filter | `analytics.LEAD_FILTERS`: an unknown filter returns the unfiltered list |
| Negative reply rate | someone subtracted automatic replies | use `analytics.real_replies()` |
| Every campaign shows zero positives | `lt_interest_status` came back as a type `as_int()` cannot read | the campaigns with open opportunities flip to `hold` with the discrepancy flagged; read the raw lead list before acting |
| Every ETA moved by weeks | `config/ids.json` inbox lists changed | check the WARNING lines under the capacity line in the report; it is usually correct, Lorenzo bought inboxes |
| `ExperimentLogError: not valid JSON` | `config/experiments.json` was hand-edited badly | fix the JSON. Do **not** delete it: starting from an empty log resets every running test to zero sample and lets the next run re-decide it |
| A campaign projects to "not at this rate" | it is paused, its daily limit is 0, or it sent nothing in 14 days | expected; the flag says which |
| A decided test shows `decided (frozen)` and a `post_decision` block | working as intended; later data is recorded without touching the decision | clear `result.decided_at` by hand to re-open it |
| "experiments log NOT written" | the run named `--campaign` | expected; run without `--campaign` to refresh the log |
| The job exits 1 with an ntfy alert | the pull failed | the Job_Log `failed` row carries the traceback tail |
