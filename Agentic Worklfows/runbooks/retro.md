# Runbook: the Friday retro packet (O6, brief A10)

Every Friday at 16:00 CT the packet generates itself. You edit it for ten
minutes and then you post it. It never posts anything on its own, and it never
writes to Instantly, GHL, Skool or anything else. It only reads.

The same generator produces the weekly client scorecard (F3, brief A12); see
[The client scorecard](#the-client-scorecard) at the bottom.

---

## Friday in four commands

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

# 1. Stage the call recaps (needs a Claude session; see "Staging the inputs")
#    and, if you want hours, export the week from Rize:
export RIZE_EXPORT_PATH=~/Downloads/rize-2026-09-21.csv

# 2. Look at it first. Reads live, writes nothing, stages nothing, PAYS NOTHING.
#    A dry run never calls the expensive model. If the week is already
#    answered it prints those lessons; if it is not, the lessons section says
#    the dry run did not pay. Add --pay if you want a dry run to buy them.
MODE=shadow python3 jobs/retro_packet.py --dry-run

# 3. Generate it for real (still shadow: a markdown file plus a would_do).
#    This is the one call to Opus 5 for the week.
MODE=shadow python3 jobs/retro_packet.py --now

# 4. Open it, edit for ten minutes, then post the Skool draft by hand.
open .tmp/retro/retro_$(date -v-mon +%Y-%m-%d).md
```

The file lands at `.tmp/retro/retro_<monday>.md`. The Maker School draft is at
the bottom of the shadow log:

```bash
python3 -c "import json;print([json.loads(l)['payload']['body'] for l in open('.tmp/shadow_log.jsonl') if '\"skool\"' in l][-1])"
```

### Other switches

| Flag | What it does |
| --- | --- |
| `--as-of 2026-09-25T16:00:00-05:00` | run at a fixed clock (replay, or catching up on a missed Friday) |
| `--weeks-back 1` | regenerate an earlier week |
| `--fixtures` | offline replay, from `services/retro/fixtures/week_2026-09.json`; touches no API and never calls the model, in any mode. **A replay is never this week's packet**: see "A replay is stamped and isolated" below |
| `--no-llm` | render the numbers only, skip the model entirely |
| `--refresh` | ask the model again for a week that is already answered (**this costs money**) |
| `--pay` | let a `--dry-run` buy the lessons when the week is not answered yet (**this costs money**). It writes the claim too, so the week still costs one call. `--dry-run --refresh` without it is an error, not a silent no-op |
| `--force` | overwrite this week's markdown instead of writing a second file beside it |
| `--json` | print the summary as JSON instead of the table |
| `--scorecard "<client>" --campaigns key1,key2` | render the client scorecard instead; this path never calls the model, because the scorecard has no lessons in it |

An unknown `--campaigns` key is an error, not an empty report. `--campaigns
cleaning` (the key is `cleaning_reactivation`) used to render a perfectly valid
client-facing document reading "Interested 0, Calls booked 0, Signed 0".

### Running it twice

A second run for the same week does **not** overwrite `retro_<monday>.md`. It
writes `retro_<monday>_<HHMMSS>.md` beside it and says so, because the file
whose whole purpose is ten minutes of hand editing is the thing a retry would
destroy. `--force` overwrites on purpose. The Skool would_do is claimed in the
store under `retro:skool:<monday>`, so a retry stages nothing new and whoever
posts from the shadow log never sees the same week twice.

### A replay is stamped and isolated

`--fixtures` renders recorded (and partly synthetic) weeks, with lessons from
an offline stand-in rather than the model. `--fixtures --now` used to write this
week's canonical `retro_<monday>.md`, record a Skool would_do in the real shadow
log and claim `retro:skool:<monday>` in the store, all without a stamp, and with
`--force` it overwrote the packet Lorenzo had been editing. Now a `--fixtures`
run (re-review OPS-12):

- stamps the packet: the title reads `# REPLAY: ...` and the line under it says
  `FIXTURES REPLAY, NOT A REAL WEEK`, recorded and synthetic numbers, lessons
  from a stand-in, do not edit, post or quote;
- writes `retro_<monday>.replay.md` under `.tmp/retro/replay/` (or
  `<--out-dir>/replay/`), never the canonical name and never the real packet's
  folder, so even `--force` cannot touch the real packet;
- stages no Skool would_do and claims nothing in the store: the stamped Skool
  body is returned in the summary for reading only, and the week's proposal
  claim is not written either;
- sends its own Job_Log row and anything it might record in the shadow log to
  `.tmp/scratch/retro_packet_replay/`, like a dry run.

The offline stand-in also no longer proposes a bet that cannot be met, such as
"Cut bounced below 0" for a metric already at zero.

---

## What it reads, and what happens when it cannot

Nothing missing is ever printed as a zero. A source that fails leaves its
metric as "not available" with the reason beside it, and the reason is repeated
under **Read this before you trust a number** at the end of the packet.

This is enforced in three places, and it is worth knowing where, because each
of them broke it once. `collect._window_data` passes `None` rather than a
zeroed dict for a bucket whose read failed, so `metrics.build_funnel` leaves
those rows unavailable; `pull_positive_leads` and `pull_campaign_daily` mark
their source ok only when a sub-pull really succeeded; and
`collect.standing_caveats` copies every entry of `week.errors` into the
caveats. Pinned by
`jobs/tests/test_retro.py::test_a_dead_accounts_endpoint_renders_not_available_and_a_caveat`.
The public Skool draft goes further: if any of sent, reply rate, positives or
booked is unavailable it refuses to state the week's numbers at all.

| Input | Source | When it is missing |
| --- | --- | --- |
| Sends, bounces, replies | Instantly `accounts/analytics/daily`, per inbox per day | the funnel rows read "not available" with the HTTP error beside them, and the error is repeated in the caveats and in the Job_Log row |
| Per-campaign sends and replies | Instantly `campaigns/analytics/daily`, one call per campaign | that campaign's row reads "not available" in every cell, never "0 sent", and a client card that includes the campaign prints its sends and replies as not available with the reason (re-review OPS-3) |
| Lifetime sends for the verdict lines | Instantly `campaigns/analytics`, no date range, one call | no verdict table |
| Positives, booked, held, closes | Instantly leads, the four positive interest filters, one record per email, statuses 1 to 4 only | all four filters down: "not available"; some down: the counts are printed as floors and the caveats say which filter failed. They are only as fresh as the S8 mirror. A custom lead label (its own value in -30000..30000) is ignored, and the same person on two campaigns counts once (re-review OPS-6) |
| No-shows | nothing today | **always "not available"**: the lead pull reads statuses 1 to 4 only, and Instantly has no verified list filter for no-show (-4); an unverified filter name silently returns the whole workspace. "Calls booked" carries a note that it is a floor, because a lead who booked and then did not show has left status 2 (re-review OPS-11) |
| Proposals, revenue | GHL opportunities, walked with `startAfterId`, dated by `lastStageChangeAt` (and `lastStatusChangeAt` for Won), **never `updatedAt`** | **blank today**: no Private Integration token exists. If the walk is cut short the numbers are labelled floors, not totals. A Proposal Sent or Won opportunity with no stage-change date makes that row "not available", because an edit time put August closes into a September week (re-review OPS-4) |
| System changes | `git log` over the repo | git is always there; the audit logs are not (below) |
| Instantly / GHL audit entries | a staged file, entries inside the window only | the section says "git log only"; a stale file says how old its newest entry is |
| Wins, objections, calls | a staged Fireflies pull | the wins and objections sections say "Nothing the call notes support" |
| Hours by category | `RIZE_EXPORT_PATH`, rows inside the window only | the section says "Not available" and names the variable; a file with no row in the window says so rather than printing last month's hours |
| What the machine did | `.tmp/job_log.csv` | the section says "Not available" |

Live read cost per run: 1 accounts-daily call, 6 campaign-daily calls, 1
campaign-totals call, 4 paginated `leads/list` reads, and 1 GHL search once a
token exists. Every one is a GET or a POST-shaped read. No paid third-party API
is touched: no Apify, no MillionVerifier, no LeadMagic.

### Two numbers that are easy to get wrong

**`campaigns/analytics` with a date range does not filter by date.** Verified
read-only on 2026-09-22: asked for 2026-09-15 to 2026-09-21,
`cleaning_reactivation` answered `emails_sent_count: 300`, which is its
all-time total; asked for the week before, it answered an empty list. It is a
presence filter, not a window filter. Week-over-week numbers come from the
**daily** endpoints and nowhere else. The only thing the undated call is used
for is the cumulative send count behind the 1,000 and 3,000-send verdict lines.

**`replies_automatic` is not a subset of `replies`.** In this workspace,
`replies` already excludes auto-responders, and `replies_automatic` is a
parallel counter. 17 recorded account-daily rows carry `replies: 0` with
`replies_automatic: 1` or more, and "2026 Bookkeeping - Trigger Outbound" sits
at `reply_count: 1` lifetime with `reply_count_automatic: 6`. Subtracting one
from the other removes the auto-responders twice: it reported 2 real replies
for a week that really had 17. The real reply rate is
`unique_replies / sent`, and auto-responders get their own row.

That rule applies to the **lifetime** verdict table too, and it did not use to.
`campaign_verdicts` subtracted `reply_count_automatic_unique` from
`reply_count_unique`, so one document printed two different rates for the same
campaign: 2.50% in the Campaigns table and 0.67% in Campaign verdicts for
"2026 Cleaning - Trigger Outbound". Replayed at the 1,000-send line it labelled
**all six** campaigns "kill or rewrite", including the two cleaning campaigns
that produced 4 of 6 positives and 2 of 3 booked calls. Pinned by
`test_campaign_verdicts_use_unique_replies_and_never_subtract_automatic`.

**The real reply rate this packet prints is `unique_replies / sent`.** For
Sept 15-21 that is 19 / 1,800 = 1.06%. The raw `replies` counter for the same
week is 22, which is 1.22%, the figure measured by hand; the difference is the
three leads who replied more than once. Section 6's 1% line is a per-lead rule,
so unique is the right numerator. `test_real_reply_rate_matches_the_hand_measured_week`
asserts on `metrics.real_replies`, which is the number the row actually shows.

**Timestamps are UTC and the windows are CT.** Instantly stamps interest
changes as `2026-09-21T19:01:33.148Z`; the Job_Log writes UTC; GHL writes UTC.
`Window.contains_date` converts before taking the date, so a positive at 20:30
CT on Friday counts on Friday. Taking the first ten characters of the UTC
string put it on Saturday, and at a Friday cutoff that dropped it out of both
windows: with three positives in a week, one lost is a 33% error on the
headline row.

---

## Staging the inputs a cron job cannot fetch

Two inputs only exist inside a Claude session, the same way `pipeline_sweep`
reads `.tmp/upwork_rooms.json` for the Upwork MCP.

### Call recaps (Fireflies, through the Gmail connector)

In a Claude session, search Gmail for `from:fred@fireflies.ai newer_than:7d`,
read each thread with `messageFormat=PLAIN_TEXT`, and write
`.tmp/retro/call_recaps.json` (override with `RETRO_RECAPS_PATH`):

```json
{"messages": [
  {"id": "...", "date": "2026-09-18T13:31:11Z", "sender": "fred@fireflies.ai",
   "subject": "Catch up on yesterday in 2 minutes", "plaintextBody": "..."}
]}
```

**Know what you are getting.** Fireflies sends two kinds of mail and only one of
them is useful:

- **"Your meeting recap - ..."**, one per call. The body has no notes in it at
  all: it is table pipes and a link to app.fireflies.ai, and the content sits
  behind the link in an image block. The packet lists these as proof of which
  calls happened, and nothing else.
- **"Catch up on yesterday in 2 minutes"**, the Daily Brief, one per day. This
  one carries ACTION ITEMS, POPULAR TOPICS with sub-headings, BLOCKERS and OPEN
  QUESTIONS as bullets. This is where wins and objections come from. An empty
  day reads "No action items identified for today." and is parsed as empty
  rather than as a bullet.

So a week of calls with no Daily Briefs produces no wins and no objections, and
the packet says exactly that. Getting the transcript itself needs the Fireflies
app or its API, which is not connected.

### Instantly and GHL audit logs

`shared.instantly` has no audit-log read method and there is no GHL token, so a
cron run cannot fetch these. In a session, pull them with the Instantly MCP and
write `.tmp/retro/audit_logs.json` (override with `RETRO_AUDIT_PATH`):

```json
{"instantly": [{"ts": "...", "actor": "...", "action": "...", "target": "..."}],
 "ghl": []}
```

### Rize

Export the week from Rize as CSV and set `RIZE_EXPORT_PATH`. The parser finds a
category column (`category`, `type`, `project`, `label`, `bucket`, `tag`) and a
duration column (`duration`, `hours`, `duration (minutes)`, ...). Durations
read as `h:mm:ss`, as decimal hours, or as seconds/minutes when the column name
says so. The unit comes from the column name and the format, never from the
size of the number, so 45 minutes never becomes 45 hours.

---

## The rubric for the three lessons

This is the only expensive model call in the system: `role="retro"` maps to
Opus 5 in `shared/llm.MODEL_POLICY`, once a week, two calls at the very most
(one proposal, one repair). The judge runs in code, not in the prompt, so a
model that ignores the rubric gets rejected anyway.

**A lesson is accepted only if all four hold:**

1. **NUMBER.** It names one metric from the funnel table **that moved this
   week**, and quotes that metric's value exactly as the table prints it. A
   lesson about a flat number is rejected. A number the table does not print is
   rejected.
2. **CAUSE.** It names the specific change that plausibly moved the number, and
   cites it: a commit hash from the system-changes list, a campaign name, or a
   call item as `recap:<index>`. A citation that is not in this week's inputs is
   rejected, **and so is a cause that does not talk about what it cites**: the
   sentence has to repeat a distinctive word from the commit subject, the
   campaign name or the call item. "Emails sent moved to 1200 this week",
   citing an unrelated campaign, is a restatement of the number with a citation
   stapled to it, and it used to pass every other rule.
3. **ACTION.** It ends in one instruction that starts with a verb, has an owner
   from the allowed list, and carries either a target number or a date. "We
   should look at this" fails the verb test; "Fix the copy" fails for having no
   target.
4. **NOT GENERIC.** Advice that would read the same in any week of any business
   is rejected by pattern: keep doing, continue to, stay consistent, double
   down, best practice, consider testing, monitor closely, keep an eye,
   maintain momentum, test more, in general, going forward, leverage, be
   patient, **hold it above N, hold it at or above this week's level, review it
   again next Friday**. The last three are restatement with a number stapled on;
   they fooled the NUMBER check, and the package's own offline fixture was made
   entirely of them.
5. **DIRECTION.** `bounced`, `bounce_rate`, `no_shows` and `negative` are
   metrics where up is bad. An action or a target that asks to hold, raise or
   beat one of them is rejected. Without this rule "Hold bounced above 17 next
   Friday" was an accepted lesson and the Skool draft rendered "Next week: hold
   bounced at or above this week's level (17 or better)" as a public commitment
   to bounce more email.

**A bet is accepted only if** it states the bet, names an owner, carries a
target with a number in it, names the funnel metric it will be scored by next
Friday, has a date inside next week, and obeys rule 5.

**A win or objection is accepted only if** it cites a call item by index from
this week's Daily Briefs. An item the model invented has no index, so it is
dropped.

Rejected items are **printed in the packet's appendix with the reason**, not
deleted. If the rubric is throwing out something good, that is where you see
it, and the rubric is in `services/retro/lessons.py` (`RUBRIC`,
`validate_lesson`, `validate_bet`). If fewer than three survive, the packet
says so rather than padding the list.

### Cost control

**Which commands cost money.** Exactly one does on a normal Friday: step 3,
`--now`. `--dry-run`, `--fixtures`, `--no-llm` and `--scorecard` all reach the
model zero times. `--refresh` and `--pay` cost money and say so in `--help`.

| Command | Calls Opus 5? |
| --- | --- |
| `--dry-run` | no. Reuses this week's answer if there is one, otherwise renders the numbers and says the dry run did not pay |
| `--dry-run --pay` | yes, once, and it writes the claim, so the week still costs one call |
| `--dry-run --refresh` | refused. `--refresh` asks to pay again and a dry run does not pay; add `--pay` or use `--now --refresh` |
| `--now` | yes, once a week; a re-run reuses the claim |
| `--now --refresh` | yes, again, deliberately |
| `--fixtures` (with anything) | no, in any mode. It answers from the recorded context |
| `--no-llm` | no |
| `--scorecard` | no. The client scorecard renders the week and has no lessons in it |

One weekly run is roughly 4k input and 1k output tokens on Opus 5, about $0.045
at the prices in `shared/llm.PRICES_USD_PER_MTOK`; the repair call doubles that
at worst. The documented Friday flow costs that once, not twice.

**How the cap works.** The week is claimed in the store under
`retro:proposal:<monday>` with `set_if_absent` after the call. Before the call
the store is probed for writability and the run **raises**
`ClaimNotWritable` if it cannot hold a claim, because a cap that cannot be
written is not a cap: catching that failure and logging a warning left every
run that Friday paying again, silently.

A stored proposal is **re-judged against the numbers of the run that reuses
it** before it is printed, and anything that no longer validates goes to the
appendix. The claim is keyed by the Monday, so a proposal written by a mid-week
run used to be handed back verbatim on Friday: the funnel table said "Emails
sent 1200" while the lessons underneath quoted "sent 300".

A failed model call is **not** claimed. A 529 from Anthropic is routine, and
writing it into the store as the week's answer meant one blip permanently
emptied the one section the packet is for.

`LLM_FAKE=1` bills nothing and installs an offline stand-in built from the real
week, so `--fixtures` runs still show a filled-in packet. A claim written by a
faked run is tagged `faked: true` and is **never served to a real run**: the
real run ignores it, pays for a real answer and overwrites it. "Faked" is a
property of the process, not of who passed the callable, so an evidence run or
a replay harness that injects its own stand-in under `LLM_FAKE=1` is tagged
too. Otherwise a demo on Friday morning would leave invented lessons in the
store for the 16:00 run to print under Lorenzo's name.

---

## The inbox and domain audit

Section 6's Friday rule is "at least 100 sent and under 1% real replies, or a
bounce rate over 2%, removes the inbox". Two things about how it is applied
here.

**It runs over the trailing pull, not over the retro week.** At 25 sends a day
an inbox has about 100 to 125 sends by Friday 16:00, where the 1% line *is* one
reply. The job already pulls `last_window.start` through today for the
week-over-week comparison, so the audit uses that whole range (about twelve
days) and drops the partial run day. `collect.audit_window`.

**A verdict is "remove" only when the 95% range clears the line.** At 100 sends
a genuinely healthy 1.2% inbox shows zero replies about a third of the time.
Applied to the point estimate over one partial week the rule named 5 of 12
inboxes as removals on the recorded week the workspace measured at 1.2%
bounces and 1.2% real replies with nothing failing a threshold: three for "a
real reply rate of 0.00%" on 100 sends, two for "3.00%" bounces on 3 bounces
out of 100. That is a standing instruction to retire 42% of the sending
capacity, every Friday, forever.

So the rule now asks for confidence in the direction of the removal: the Wilson
upper bound on the reply rate must still be under 1% (0 of 100 gives 3.7% and
reads "watch"; 0 of 400 gives 0.95% and reads "remove"), and the Wilson lower
bound on the bounce rate must still be over 2% (3 of 100 gives 1.03% and reads
"watch"; 20 of 400 gives 3.26% and reads "remove"). "watch" is the honest
middle. Pinned by `test_the_inbox_audit_does_not_flag_a_healthy_recorded_week`.

Nothing is paused by this job in any case. That is A4's deliverability
monitor, and it needs your approval.

## The campaign verdicts

Verdict lines at 1,000 and 3,000 lifetime sends, and **blueprint M4's second
half is applied**: with at least one positive at 1,000, a campaign runs to
3,000 before it is judged. `total_opportunities` used to be collected,
displayed and never read, so a campaign that crossed 1,000 with positives and a
rate just under 1% was killed at the first line. Only a campaign at 1,000 with
no positives at all gets the kill test early.

---

## The Skool post

The packet ends with a draft for Maker School. The job records it as a
would_do in `.tmp/shadow_log.jsonl` (`system: "skool"`, `action:
"post_create"`) and **never posts it, in any mode, including `MODE=live` with
`ALLOW_LIVE_WRITES=1`**. That is pinned by
`jobs/tests/test_retro.py::test_the_job_never_posts_to_skool_even_with_the_live_flags_set`.

It deliberately does not go through `settings.guard_write`: in live mode that
opens a `live_write_intent` Job_Log row which the caller is meant to close with
`live_write_ok` or `live_write_failed`, and a job that never posts would leave
that row open forever and poison every reconciliation.

Copy rules on the draft: no em dashes, no exclamation marks, signed Lorenzo.
The AI/automation word ban from `config/offers.md` rule 8 is **not** applied to
the Skool post, because that ban exists to keep those words out of prospect
email and Maker School is a community of people building exactly that. It is
applied in full to the client scorecard.

---

## Schedule and alerting

Friday 16:00 CT. Not yet registered on Modal: `services/reply_engine/modal_app.py`
belongs to another brief, so adding `"retro_packet": ("0 16 * * 5", "Friday
16:00 CT")` to its `SCHEDULES` (plus the four environment keys below) is a
cross-cutting request, not something this brief changed. Until then, run it by
hand, or from a Claude Code scheduled task.

Environment keys this job reads, which must be added to `modal_app.SECRET_KEYS`
or `ENV_NOT_IN_SECRET` before it can run in a container:
`RETRO_STAGE_DIR`, `RETRO_RECAPS_PATH`, `RETRO_AUDIT_PATH`, `RIZE_EXPORT_PATH`.
All four belong in `ENV_NOT_IN_SECRET` (they are local paths, not secrets).
Until they are there, `shared/tests/test_settings.py::test_every_env_key_is_deployable`
stays red and this job cannot be deployed.

Every run writes one `retro_packet` row to the Job_Log: `ok`, `partial` (fewer
than three lessons survived the rubric), `errors` (a source failed) or `failed`
(the run raised). A failure sends a high-priority push through
`shared.notify`; a run that completed with missing sources sends a normal one
naming them. Both go to Lorenzo only.

---

## When it looks wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every funnel number reads "not available" | no `INSTANTLY_API_KEY`, or the account endpoint answered 413 | the reason is in the Source column, in the caveats and in the Job_Log row; `daily_account_analytics` needs an `emails` filter in this workspace |
| A funnel number reads 0 | that is a real zero, measured | if you think it is wrong, check the caveats: a failed source never renders as 0 |
| Two files for the same week | you ran it twice; the first one was left alone in case you had edited it | keep the one you edited, or re-run with `--force` |
| "the dry run did not pay" | `--dry-run` never calls the model | run `--now`, or `--dry-run --pay` |
| `ClaimNotWritable` | the store cannot hold the weekly claim, so the cost cap is not there | fix the store (check `STORE_PATH` and its permissions) before running the retro |
| "Calls booked: 0" but you know you booked one | Instantly interest status only moves when the S8 mirror runs, and it is in shadow | mirror GHL to Instantly, or read booked from GHL once a token exists |
| Proposals and revenue always blank | no GHL Private Integration token | mint it in GHL Settings > Private Integrations |
| Sends look halved on a Friday | the run day is counted whole in both weeks but the day is not over | the caveat says so; run again after 19:00 CT for a complete Friday |
| No lessons at all | the model failed, or nothing passed the rubric | the appendix says which. A failed call is not claimed, so the next `--now` asks again; `--refresh` forces it |
| The same lessons as the last run | the week is claimed in the store | `--refresh`. They were re-judged against this run's numbers first, so anything stale is in the appendix |
| A lesson vanished between runs | it no longer quotes a number this week's funnel prints | the appendix says "no longer true of these numbers" |
| A lead pull says "floors, not totals" | a `leads/list` filter hit the 20-page cap | raise `collect.LEADS_MAX_PAGES` |

---

## The client scorecard

`build_client_scorecard` renders the same collected week, filtered to one
client's campaigns, in Nick's agenda shape: the numbers, wins, next steps, open
questions, next week's plan. For performance deals it is the invoice basis, so
it prints the same numbers the internal packet prints. Nothing unmeasured is
shown as a zero: a metric with no source is left out and named in the closing
note.

```python
from services.retro import collect, scorecard

week = collect.collect_week(now, instantly=client, ghl=ghl)
card = scorecard.build_client_scorecard(
    week, client_name="Shining Armor Cleaning",
    campaign_keys=["cleaning_reactivation"],
    wins=[...], next_steps=[...], open_questions=[...],
    attributed_revenue=None)
markdown = scorecard.render_client_scorecard(card)   # raises on a copy violation
numbers = scorecard.scorecard_numbers(week, ["cleaning_reactivation"])  # for an invoice line
```

`render_client_scorecard` runs the offer-sheet copy rules over the finished
markdown and raises `render.ClientCopyError` rather than handing back a
document that says "automation", carries an em dash or an exclamation mark, or
is not signed Lorenzo.

The card ends with **How to read these numbers**, a client-safe subset of the
internal caveats. It carried none at all, which mattered because booked, held
and signed come from Instantly interest status while the S8 mirror is in
shadow: a client whose call Lorenzo booked and held received a card reading
"Calls booked 0, Calls held 0, Signed 0", and on a pay-per-result deal that
either under-bills Lorenzo or gets disputed by somebody who was on the call.
The note says those three rows are a floor and asks the client to check them
against their own calendar. No internal vocabulary reaches it: "mirror",
"shadow" and `lt_interest_status` are not client words.

An unknown campaign key raises `scorecard.UnknownCampaign` naming the valid
keys, rather than filtering to nothing and rendering a report of a total
failure week.

Or from the command line:

```bash
MODE=shadow python3 jobs/retro_packet.py --now \
  --scorecard "Shining Armor Cleaning" --campaigns cleaning_reactivation
```

---

## Tests

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m pytest jobs/tests/test_retro.py -q
```

83 tests, all offline, against a real read-only pull of the live Instantly
workspace and Lorenzo's Gmail recorded on 2026-09-22 in
`services/retro/fixtures/`. Re-record them with the snippet in the A10 report
if the API shapes change; `test_replies_automatic_is_not_a_subset_so_it_is_never_subtracted`
fails loudly if a new pull no longer proves the point.

`week_2026-09.json` holds **two** weeks. 2026-09-15 onwards is the recorded
pull; 2026-09-07 to 2026-09-11 is a synthetic prior week in the same shape,
added because at the tests' Friday the last-week window was empty and every
Change cell in every rendered packet read "new", "flat" or "not available", so
the week-over-week comparison the deliverable exists for was never rendered end
to end. `test_a_week_over_week_delta_renders_from_two_populated_weeks` pins
concrete `-50`, `+0.62pp` and `-0.42pp` cells.

Repo-wide `python3 -m pytest -q` is currently red on
`shared/tests/test_settings.py::test_every_env_key_is_deployable`, which is a
cross-cutting request, not something this brief can close: sixteen environment
keys from five briefs are in neither `modal_app.SECRET_KEYS` nor
`ENV_NOT_IN_SECRET`, four of them this one's (`RETRO_STAGE_DIR`,
`RETRO_RECAPS_PATH`, `RETRO_AUDIT_PATH`, `RIZE_EXPORT_PATH`). Adding them is a
change to `services/reply_engine/modal_app.py`, which belongs to another brief.
