# Master build report

> **Updated 2026-09-22 evening, after the re-review and its fixes.** Read `REREVIEW_2026-09-22.md` first. Figures marked "morning snapshot" were not re-derived after the fixes.

Written 2026-09-22, early morning, and corrected the same evening. It says what exists, what each
piece would have done this week on your real numbers, and what is still missing.

Where a figure comes from an artifact on disk rather than a fresh run, the file is named so you can
open it yourself.

---

## Re-review fix plan (2026-09-22)

Six reviewers rejected the overnight build. The fixes so far, one line per commit on
`revenue-automation`:

- `a800799` ops and fulfillment tier (OPS-1 to OPS-15).
- `2e27bd9` marketing tier (MKT-1 to MKT-9, R7, R10, R12, R13).
- `653a4d9` test isolation: tests cannot read real credentials or reach live systems (SAF-2, SAF-5, SAF-8).
- `8654401` change-set rollback, including `changesets/capacity/apply_capacity.py` for Oct 11.
- `6769f4d` inbox inventory and deliverability monitor: health alerts only.
- `9fd4383` and `684e4e2` reply-engine send safety.
- `9b7d01a` deploy tooling and schedules.
- `450d3b1` metrics-sheet test fix.

In progress: reply-engine follow-ups, live-write guard, read-only keys, docs.

Nothing has been deployed or pushed. Everything runs in shadow.

## What went wrong overnight

One block, so none of it is buried further down. Detail and evidence are in `REREVIEW_2026-09-22.md`.

1. **The test suite emailed you.** Every full `pytest` run sent one message from your Gmail to
   yourself ("Pipeline sweep: 1 waiting on you"). Fixed; see "The short version" below.
2. **Two evidence runs set live mode with notifications on**, at 00:18 and 00:22 to 00:23 CDT on
   Sep 22. They may have emailed you and pushed to the ntfy topic. Nobody can confirm that from here:
   check your inbox and the ntfy app for 00:15 to 00:30 CDT on Sep 22.
3. **48 `mode=live` rows reached the Job_Log**, written between 04:00:36Z and 05:23:10Z by evidence
   scripts that set the live flags inside their own process: 19 `live_write_intent`, 8
   `live_write_ok`, 2 `live_write_failed`, 18 `errors`, 1 `refused`. The Instantly and GHL transports
   were mocked. 9 of the 48 are `notify.push_email` rows, and for those "nothing reached a live API"
   is not proven (item 2). The file is quarantined at
   `.tmp/quarantine/job_log_polluted_2026-09-22.csv`.
4. **The live-write hook never guarded the build.** It is registered only in the repo-root
   `.claude/settings.json`, and the build ran from `Coding/`. What protected production was the
   code-level `guard_write`.
5. **The tests would have reached live GHL and Google Sheets** once the GHL token and sheet id went
   into `.env`. Fixed in `653a4d9`.
6. **More credentials and apps than the hand-off listed.** Both April Modal apps matter (the
   test-mode app reads the named secret `instantly-email-responder`), and `execution/.env` holds more
   keys. `advero-lead-sync`, the daily Instantly to CRM sync, is not deployed.

---

## Proof that nothing is live

Morning snapshot: read-only checks run on the final pass, early on 2026-09-22. Nothing was created
to test any of this. The re-review re-checked production later the same day and found it unchanged
(`REREVIEW_2026-09-22.md`, "Bottom line").

```
$ MODE=shadow python3 -c "... Counter(r.get('mode') for r in job_log.read_shadow_log())"
   records: 1203
   mode counter: {'shadow': 1203}
   rows with mode=live: 0

$ MODE=shadow python3 -c "... Counter(r['mode'] for r in csv.DictReader(open('.tmp/job_log.csv')))"
   rows: 49
   mode counter: {'shadow': 49}
   live_write_intent/ok/failed rows: 0

$ Instantly GET /custom-webhooks      -> []          (no webhook exists)
$ Instantly GET /custom-tags          -> []          (no lead label exists)
$ Instantly GET /inbox-placement-tests-> []          (the level 2 create was staged, never fired)

$ Instantly campaigns (6), subsequences + daily_limit + last update:
   2026 Bookkeeping - Client Reactivation        daily_limit=50 updated=2026-09-18T11:32:39Z subsequences=0
   2026 Bookkeeping - Trigger Outbound           daily_limit=50 updated=2026-09-17T11:49:15Z subsequences=0
   2026 Cleaning - Client Reactivation           daily_limit=50 updated=2026-09-16T13:33:23Z subsequences=0
   2026 Cleaning - Trigger Outbound              daily_limit=50 updated=2026-09-19T11:06:57Z subsequences=0
   2026 Recruiting - Client Reactivation         daily_limit=50 updated=2026-09-16T13:33:48Z subsequences=0
   2026 Recruiting - Outbound (specialty roles)  daily_limit=50 updated=2026-09-18T13:25:46Z subsequences=0
   SUM of campaign daily_limit: 300

$ Instantly accounts: 45, status {1: 45}, warmup_status {1: 45}, paused/warmup-off: []

$ Instantly leads: 4,000 scanned over 40 pages, newest timestamp_created 2026-09-16T16:23:31Z

$ git remote -v      -> (empty)
```

What that says, claim by claim:

- **Every shadow record is `mode: shadow`.** 1,203 of them, zero live. Same for the 49 Job_Log rows,
  and not one `live_write_intent`, `live_write_ok` or `live_write_failed` row exists.
- **No Instantly webhook, lead label, subsequence or placement test exists.** All four read empty.
- **No campaign was patched.** Every campaign's `timestamp_updated` predates the start of this build
  (the newest is 2026-09-19; the build began the evening of 2026-09-21), and the six `daily_limit`
  values still sum to exactly 300.
- **No inbox was paused and none was added.** All 45 accounts read `status: 1` and
  `warmup_status: 1`.
- **No lead was uploaded.** The newest `timestamp_created` in 4,000 leads is 2026-09-16, six days
  before the build. The stronger local proof: the only code path that can upload leads is the list
  factory, and its six `create_lead_batch` records in the shadow log are all `mode: shadow`.
- **Nothing was posted.** The Skool post exists as `.tmp/skool_post_2026-09-21.json` and three
  `post_create` shadow records. The job never auto-publishes, even in live mode.
- **Nothing from this build was deployed to Modal.** See the next section, which is not a clean
  result and is the reason it gets its own heading.
- **Git has no remote and nothing was pushed.** `git remote -v` is still empty on the evening of
  2026-09-22, so every commit on `revenue-automation` is local.

An independent check of three live objects, run by the main session against Instantly and GHL after
an earlier polluted Job_Log named them, is in
`runbooks/evidence/live_systems_untouched_2026-09-22.md`. It covers Instantly and GHL only. It does
not cover notifications, so it cannot rule out item 2 of "What went wrong overnight".

### And nothing prospect-facing carries a copy defect

70 content files were scanned on the final pass: the six staged Instantly sequences (36 variant
bodies), the 26 reply-engine prompt templates, the Interested-quiet subsequence, the onboarding and
product copy, and every draft the dry runs generated (9 proposals, 4 client retention drafts, 3
scorecards, the public DAILY UPDATE block). **Zero em dashes, zero en dashes, zero exclamation
marks**, with HTML developer comments excluded, since `<!--` contains a `!` and reads as a hit.

No unconfirmed figure can reach an email. The only price `config/offers.md` marks TO CONFIRM is the
`$2,500-5,000/mo` retainer on the three trigger rows. It appears in **no** staged sequence, and both
gates now refuse it if a model or a hand ever writes it:

```
cadence gate (the unattended D1-D30 path): ['money_marked_to_confirm', 'guarantee_from_another_offer']
draft gate (the human-approved path):      ['dollar figure $2500 is marked TO CONFIRM in offers.md; ...']
```

No **executable** file carries a `claude-fable-*` id, and `shared/tests/test_llm.py` pins that closed
in both directions. The word itself still appears in prose and comments:

- `REVENUE_AUTOMATION_BLUEPRINT.md` - 8. Seven of them (lines 406, 412, 413, 414, 416, 417, 448) are
  live prose telling the reader to run the orchestrator and three of the four collective agents on
  "Fable 5.1". They are retired by the note at line 404, which says every "Fable 5.1" below reads as
  "Opus 5" and leaves the prose as written so the original tiering reasoning stays legible. That note
  is easy to miss if you land mid-document; the blueprint is the file a future reader will follow.
- `shared/llm.py` (3) and `shared/tests/test_llm.py` (8) - comments about the removal and the test
  that pins the price table, plus `runbooks/shared_library.md` (1), one historical line in
  `PHASE1_SHADOW_REPORT.md`, this report and the re-review notes.

Model routing itself is not affected: `shared/llm.py` MODEL_POLICY is the only authority the deployed
services read. One thing I did not change, because it is Claude Code configuration rather
than part of this build: `.claude/agents/ops.md` still says "The Friday retro packet is the one job
that calls Fable". Its `model:` field is correct (`claude-sonnet-5`); only that sentence is stale.

### One thing this check found that nobody had looked at

`modal app list` returns two apps, and neither of them is this build:

```
ap-778CwG4VwkU1BQQtmH3FmK  instantly-email-responder-test-mode  deployed  2026-04-02 14:52 CDT
ap-tAN6CCpIOutZdIbFH5U4cX  instantly-email-responder-v2         deployed  2026-04-02 14:55 CDT
```

`advero-reply-engine` is **not** there, which is the claim this section set out to make: none of the
schedules in this build is registered and nothing of mine runs on its own. `advero-lead-sync`, the
daily Instantly to CRM sync that `CLAUDE.md` calls the only live webhook, is not there either, so that
sync is not running.

But `instantly-email-responder-v2` **is deployed right now**, and it is the app declared by
`execution/modal_reply_handler_v2.py`, the file that hard-codes four live credentials in a
`modal.Secret.from_dict({...})` literal. So those four values are not only in git history: they are
baked into a Modal deployment that has been up since April and exposes a POST web endpoint. Deleting
the file from the working tree does not touch that deployment. The test-mode app matters too: it
reads the named Modal secret `instantly-email-responder`, which needs rotating as well.

This changes the urgency of Stage 0.1 in `GO_LIVE_CHECKLIST.md` and nothing else in this build. It is
written up there and in `DECISIONS_FOR_LORENZO.md` section 0.1.

---

## The short version

There are **16 staged schedules** (8 for Modal, 8 for the laptop) in
`changesets/schedules/schedules.json`. Three more jobs are turned off and run by hand
(`campaign_verdicts`, `upwork_rooms_am`, `upwork_rooms_pm`, listed in `config/turned_off_jobs.json`);
their code stays. The morning snapshot was **2,233 tests, all green**; the re-review fixes have added
tests since, and that count was not re-derived here.

**No campaign, calendar, CRM record or deployment was touched**, with the evidence above. Every job
runs in shadow, which means it reads live data, works out what it would do, writes that down as a
proposal, and stops. Nothing is scheduled on Modal and nothing on the laptop is installed, so none of
it is running on its own. The path to that is `GO_LIVE_CHECKLIST.md`.

**One exception, found on 2026-09-22 and now fixed: the test suite was sending you real email.**
An earlier version of this line said "nothing has touched a live system" without qualification, and
that was wrong. `services/reply_engine/tests/test_sync_modal_app.py` sets `NOTIFY=on` and
`NOTIFY_SHADOW_SEND=1` to exercise the push leg, but patched only `_send_ntfy`. `notify()` then fell
through to `_send_email`, and because `shared/settings.load_env()` also reads the parent
`AdveroSolutions/.env` (which carries `NOTIFICATION_EMAIL`, `GMAIL_SENDER_EMAIL` and
`GMAIL_APP_PASSWORD`), `_email_config()` returned your real credentials. Every full `pytest` run
opened an authenticated session with `smtp.gmail.com:465` and sent one message to yourself, subject
"Pipeline sweep: 1 waiting on you". **The messages in your inbox overnight are from the test suite,
not from the engine** - no lead, client or third party ever received anything.

Fixed in three places: that test now patches the email leg too; `conftest.py` drops the Gmail
credentials after `load_env()` has run and replaces the `shared.notify._smtp_factory` seam with a
recorder that raises, so no test can open an SMTP socket whatever it does to `NOTIFY`; and
`shared/tests/test_notify.py` has a regression test that fails if either lock is removed. Verified by
running the whole suite with `smtplib` intercepted below the seam: **2,231 passed, zero connection
attempts**. One test (`test_the_first_reply_carries_both_recipient_belts`) had been passing only
because those ambient credentials made an approval card deliverable; it now supplies its own dummy
leg.

**Later on 2026-09-22 (re-review R1, Slice 4a): a `.env` file no longer sets the gate flags for the
process that loads it.** `load_env()` no longer takes the gate flags (`settings.GATE_FLAGS`, which is
`MODE` and `ALLOW_LIVE_WRITES`) from a `.env` file. After each file is read, any gate flag the file
put into the environment is removed again and a WARNING names the key and the file, never the value.
A flag that was already in the process environment before `load_env()` ran (the Modal secret, or one
exported in your terminal) is left as it was, and the file cannot change it because the load never
overrides. Covered by `shared/tests/test_load_env_gate_flags.py`. There is one deliberate exception:
`LAPTOP_LIVE_TIERS` in `.env` is the laptop scheduler's documented switch
(`changesets/schedules/laptop_runner.py`, `runbooks/deployment.md`). The runner reads it from the
saved `.env` files and starts the scheduled laptop jobs of a named tier with `MODE=live
ALLOW_LIVE_WRITES=1`. Those laptop jobs hold no Instantly or GHL write key, by design
(`runbooks/read_only_keys.md`).

**What is yours first.** `GO_LIVE_CHECKLIST.md` sets the order; this is a summary, not a second
checklist. Do not start its Stage 3 or later until the live-write guard (Stage 0.4) is in and you have
signed off the fix plan.

1. **Rotate the four committed credentials** (`GO_LIVE_CHECKLIST.md` Stage 0.1,
   `DECISIONS_FOR_LORENZO.md` 0.1), plus the Modal secret `instantly-email-responder`. An Instantly
   API key, a GitHub token, a Slack webhook and a Google service-account private key are in the repo
   history *and* in a Modal app that is deployed today. Rotation is yours; I did not touch any of
   them. Do not add a git remote before this is done.
2. **Check your inbox and the ntfy app** for 00:15 to 00:30 CDT on Sep 22 ("What went wrong
   overnight", item 2).
3. **Mint the GHL Private Integration token** (GO_LIVE 2.1). Nothing in the sales tier can go live
   without it: the engine cannot read or write the calendar. GO_LIVE 2.1 says where it goes and which
   copy agents may see.
4. **Fill the four missing prices in `config/offers.md`** (GO_LIVE 1.2, DECISIONS M1). Four drafts
   are blocked and correctly refuse to name a number. The cadence copy gate uses the same validator, so a figure
   marked TO CONFIRM, or another vertical's guarantee number, stops a follow-up touch outright.
5. **Decide the Oct 11 capacity shape** (GO_LIVE 1.1, DECISIONS L1) **and the campaign
   `daily_limit` raise** (L2; applied in GO_LIVE Stage 7). How many inboxes to run and whether to buy
   more is your call; this report does not define the options. Either way, **without raising the six campaign daily limits, the 33 warming inboxes
   ship zero additional email on Oct 11**: the limits sum to exactly 300/day.
   `changesets/capacity/apply_capacity.py` applies the raise and the `email_list` additions from a
   plan file you fill in, one campaign at a time, with a dry run and a backup.

Two more worth knowing before you open anything else:

- **In the morning run, four of your twelve inboxes failed the Section 6 reply rule**, all on thin
  evidence, and my recommendation is to ignore that until Oct 11. Section K1.
- **The reply SLA is now enforced rather than measured.** A card you have not actioned gets a rising
  push at 5, 15, 30 and 60 sending minutes, then hourly, capped at 8. The ladder is taste, not
  correctness, and it is yours to change. `runbooks/reply_sla_and_approvals.md`.

---

## What exists, tier by tier

**Morning snapshot.** The table and the note under it describe the build before the re-review fixes,
which changed many of these files; the counts were not re-derived. Code files are the non-test
Python files in each component, excluding `__init__.py`; lines are raw line counts. Tests are
attributed by test file (`python3 -m pytest -q --collect-only`, grouped by the path left of `::`).

| Tier | Component | Code files | Lines | Tests |
|---|---|---|---|---|
| Library | `shared/` | 12 | 4,415 | 221 |
| Sales | `services/reply_engine/` + `cadence_tick`, `appointments_tick`, `precall_tick`, `pipeline_sweep` | 21 | 18,218 | 913 |
| Marketing | deliverability: `deliverability_monitor`, `inbox_placement`, `autoresponder_canary` | 3 | 3,329 | 155 |
| Marketing | capacity: `inbox_inventory` | 1 | 1,727 | 85 |
| Marketing | list factory: `services/list_factory/` + `list_factory` | 12 | 4,891 | 147 |
| Marketing | experiments: `services/experiments/` + `campaign_verdicts` | 7 | 2,641 | 106 |
| Ops | metrics: `services/metrics/` + `daily_metrics`, `positive_sweep` | 7 | 2,892 | 118 |
| Ops | retro: `services/retro/` + `retro_packet` | 11 | 4,201 | 83 |
| Ops | Upwork rooms: `upwork_rooms` | 1 | 1,291 | 70 |
| Fulfillment | `client_scorecard` + `changesets/onboarding/` | 2 | 2,710 | 126 |
| All | the other change-sets (Phase 0, webhooks, subsequences, capacity, inbox actions, schedules) | 8 | 3,834 | 178 |
| All | integration: one store, one log, one notifier, shadow safety per job | 0 | 0 | 31 |
| | **Total** | **85** | **50,153** | **2,233** |

These counts were taken on the morning verification pass and are kept as a record of the overnight
build, not as a current figure.

### The library: `shared/`

One set of plumbing that every job uses, so a rule lives in one place instead of nine. It owns the
shadow contract (`guard_write`), the Instantly and GoHighLevel clients, the store, the job log, the
notifier, the model wrapper, the slot and business-day maths, the Section 6 thresholds, one chunked
and cached reader for Instantly's analytics, and a recorded offline client for rehearsals.

Four pieces are new and exist because the same code was being written four times, or because nothing
bounded a cost:

- **`shared/analytics.py`.** Four components read the same daily-analytics endpoint and each carried
  its own chunking loop, its own idea of what to do with a chunk that fails, and its own answer to the
  HTTP 413 your workspace returns on an unfiltered pull. Now there is one, with a five-minute cache so
  a single run cannot pay for the same window twice, and one rule about failure: an inbox nobody could
  read is reported as **unread**, never as "sent nothing", because "sent nothing" reads as a 0% reply
  rate and that is a removal proposal.
- **`shared/offline.py`.** A recorded Instantly that subclasses the real client and replaces only the
  transport, so every guard and every payload shape in a rehearsal is the production code path.
- **`shared/instantly.default_client()`.** The one place a job builds its client. There were eighteen
  inline constructions, which meant eighteen places to patch to run offline.
- **A spend ceiling on the model calls.** `shared/llm.py` now refuses to bill past a cumulative
  ceiling (`config/llm_budget.json`, $10.00 today). It reserves the pending call at `max_tokens`
  under a lock before making it, keeps the charge if the call fails, and turns off the SDK's own
  retries, so neither one large call nor several at once can jump the cap; over it, `complete()`
  raises without contacting the model and you get one push and one `llm.budget` / `refused` row. `LLM_FAKE` calls cost nothing
  and are neither counted nor refused. The running total lives in the store, not a local CSV, so it
  accumulates across Modal containers instead of resetting every five minutes. Checking and
  resetting it during the watch is `GO_LIVE_CHECKLIST.md` 3.1.

### The sales tier: `services/reply_engine/` (Phase 1, reviewed earlier)

Reads new replies every five minutes, classifies them, drafts a reply for your approval, and never
auto-sends a first reply to a positive. If the reply names a workable time it books the call, holds the
slot so nobody else is offered it, and keeps the confirmation as a draft until you tap approve.

Beyond that it runs the nine-touch follow-up cadence, the show-rate confirmation ladder, the no-show
recovery ladder, the nightly pipeline mirror, and the pre-call brief and proposal generator.

Two things changed in this tier on the final pass:

- **The cadence copy gate is now the superset, not the weaker sibling.** `cadence.copy_problems` runs
  `draft.validate_draft`, the same validator that gates the reply you approve by hand, and then its
  own stricter rules on top. It used to be the weaker of the two, and it passed both a `$2,500`
  figure `offers.md` marks TO CONFIRM and a cleaning guarantee quoted inside a bookkeeping thread.
  The gate fails closed: if the validator cannot be imported, the touch is blocked rather than sent
  unchecked. All 54 shipped templates still pass. `runbooks/cadence_and_booking.md`.
- **The 5-minute reply SLA is enforced.** `approval.escalate_pending` chases an unactioned card on a
  rising ladder, counted in sending minutes so a Friday-evening card is not already at the top of the
  ladder on Monday. It takes no Instantly client and can never send.
  `runbooks/reply_sla_and_approvals.md`.

### The marketing tier

**`services/experiments/` plus `jobs/campaign_verdicts.py`.** Decides, per campaign, whether to keep
running, rework the copy or retire, at the 500 / 1,000 / 3,000-send lines, and tracks the copy
experiments. It also carries the extended copy validator, which is wired into the Phase 0 change-set
so the only path that can patch a live campaign runs the strict gate.

**`services/list_factory/` plus `jobs/list_factory.py`.** Sources businesses, scores them against a
written ICP rubric, finds the owner, guesses and verifies the email, builds the suppression list,
personalises, and stages the result. It has **no fallback source**: the blueprint's O8 backstop
(Instantly's Lead Finder agent) is not wired, so an empty Sunday from Apify or PDL means an empty run.
See the not-built list. It is the only job gated by `ALLOW_PAID_CALLS`, and that flag alone decides
its paid calls (Apify, MillionVerifier, Perplexity and this job's model calls). Shadow stops the
Instantly writes but not the spend: a shadow run with `ALLOW_PAID_CALLS=1` does pay.

It is **not** the only job that can spend money. Anthropic is a paid vendor too, and `precall_tick.py`
and `retro_packet.py` reach `shared/llm.complete()` with no `ALLOW_PAID_CALLS` check anywhere in the
path - that gate exists only in `services/list_factory/`. Their spend is bounded by `LLM_FAKE` and by
the $10 ceiling in `config/llm_budget.json`, nothing else. This matters for the 48-hour watch in
GO_LIVE Stage 3: a deployed container never fakes the model (`LLM_FAKE` is kept out of the Modal
secret), so the watch bills real tokens. See the weaknesses section and DECISIONS C8.

**`jobs/deliverability_monitor.py`, `jobs/inbox_placement.py`, `jobs/autoresponder_canary.py`.** The
five-level deliverability monitor. Level 1 is warm-up health and DNS vitals, level 2 is seed placement
tests, level 3 is the reply and bounce audit, level 4 is the auto-responder canary, level 5 is a
positive-behaviour baseline campaign. It proposes and never applies; every proposal lands in a dated
change-set you can read.

**`jobs/inbox_inventory.py`.** Every inbox, its domain, its age, its health and its role, with alerts
for poor health and for inboxes that are paused, disconnected or erroring. Health alerts only: it
does not count a reserve, size a domain order or plan capacity for a date. It writes
`config/inbox_inventory.json` and, when asked to swap an inbox in (`--promote`), a change-set under
`changesets/capacity/` that you apply by hand. Nothing else.

### The ops tier

**`services/metrics/` plus `jobs/daily_metrics.py` and `jobs/positive_sweep.py`.** The 18:00 daily
scorecard row, the public DAILY UPDATE block, and the thirteen-row Section 6 KPI dashboard with a
week-over-week column. The 07:30 sweep tells you what is waiting on you, ordered by money.

**`services/retro/` plus `jobs/retro_packet.py`.** The Friday packet: the week against last week, an
inbox audit, wins and objections from call recaps, hours by category, system changes from the git log,
and three bets for next week. The model is used once, for the lessons, behind a claim so a dry run
cannot pay twice.

**`jobs/upwork_rooms.py`.** Run by hand now (its two daily schedules are turned off): what is waiting on you in Upwork and which finished contracts
still have no review, testimonial or retainer ask. Read only, and it says plainly when its data is
stale rather than pretending.

### The fulfillment tier

**`jobs/client_scorecard.py`, `changesets/onboarding/`, `products/`.** The kickoff kit, the weekly
client card, the retention touches at day 7, 21, 25 and 30, and the product kits. A card cell reads
"no source" when nothing was measured, which is not the same as zero, and every draft that would quote
a price refuses when the price is not in the offer sheet.

---

## What it would have done this week, on your real numbers

Every figure below is read back from an artifact these jobs left on disk during their 2026-09-21 and
2026-09-22 dry runs, and the file is named. **They were not re-run on the final pass**: a dry run is
read-only but it still calls live endpoints, and re-running them at 05:00 to refresh a report is not
worth the calls. Anything that changes by the hour is described rather than quoted to two decimals.

**Two exceptions to "your real numbers", both called out where they appear:** the Friday client card
is a fixtures replay of Advero's own data under a client label (the fulfillment tier has never seen a
client's real numbers), and the Friday retro packet's Lessons and Bets predate the rubric that now
rejects them.

### The 07:00 deliverability card

From `changesets/inbox_actions/2026-09-22.json` (generated 2026-09-22T08:31Z, `mode: shadow`,
levels 1 to 5) and the two sidecars beside it. The monitor is now health alerts only: the card no
longer counts insurance inboxes or a reserve ratio. The capacity line below is shown in today's
format.

```
45 inboxes, 5 proposals
sending 12 (300/day)  paused 0  the rest warming or idle (not in any campaign)

L1 warm-up + vitals: 45/45 ok, 15 domains checked, 0 DNS faults
L3 reply+bounce audit: 4 inboxes failing, all four THIN EVIDENCE at 150 sends
    lorenzo@myadvero.com              0.00% reply on 150 sends
    lorenzovillarreal@theadvero.com   0.00% reply on 150 sends
    lorenzo@proadvero.com             0.67% reply on 150 sends  (2.0% bounce)
    lorenzov@adveromedia.com          0.67% reply on 150 sends
Sudden drop: NOT EVALUATED, every scope abstained
L2 placement: 0 tests exist, a new one is due, BLOCKED on seed addresses  (1 LOW proposal)
L4 canary: 29 addresses harvested, 17 usable after suppression, 0 planned (pool too small)
L5 baseline campaign: not configured
```

Five proposals, not four: the four inbox removals are MEDIUM and every one is tagged **THIN
EVIDENCE**, because 150 sends is under the 300 this monitor wants before it trusts a rate, and one
more reply moves each of them across the line. The fifth is a LOW proposal to create this week's
placement test, and it is staged with an empty `emails` list because no read-only endpoint lists your
seed addresses.

On their face the four say the same thing: **applying all four removes 100 of 300 sends/day**, and
each carries "NO replacement available". That is the monitor telling you its own rule is firing
early, which is what I wanted it to do.

The DNS side is clean: 15 domains, no missing MX, SPF, DKIM or DMARC.

Note that level 4 reports 17 usable addresses, not 0. The pool is real; it is just too small for
twelve inboxes, which is why the round refuses to plan rather than mailing the same prospects from
several domains. Section J11.

### The 07:00 inbox health report

From `config/inbox_inventory.json`. Since `6769f4d` the inventory reports inbox and domain health
only. It no longer counts a reserve, sizes a domain order or plans capacity for Oct 11; how many
inboxes to run and when to buy more is your call (DECISIONS L1).

What the file on disk says: 45 inboxes on 15 domains, 12 active, 33 warming, 0 retired. 300/day
goes out from the 12 active inboxes, which is also the sum of the six campaign daily limits. 4
domains carry an unhealthy inbox and 5 inboxes are flagged. No capacity alert is raised.

The 300/day ceiling still matters for Oct 11: the campaign daily limits have to rise before the 33
warming inboxes can add any volume (see "What is yours first", item 5).

Two inboxes (`lorenzov@proadvero.com`, `lorenzovillarreal@proadvero.com`) already clear the 2%
seven-day real reply rate and are the only two eligible for the 30/day limit. That raise is dated
**2026-11-01** in the ramp plan, not Oct 11, and it is recomputed from that week's data on the day.

### The Friday verdicts

From `.tmp/campaign_verdicts_2026-09-22.md`. The verdicts job is now turned off and run by hand
(`config/turned_off_jobs.json`).

All six campaigns read `keep_running`: every one is at **300 lifetime sends** and the first verdict
line is 1,000 (ETA 2026-10-07 on today's rate, 2026-09-25 at Oct 11 volume). Cleaning trigger leads on
positives (2, $2,000 of opportunity); cleaning reactivation and bookkeeping reactivation have 1 each.

Two carry a standing note: `recruiting_reactivation` and `recruiting_outbound` have **zero positives
and three negative replies each**, and at 1,000 with still zero they are proposed for retirement.
Retiring either one releases 50 sends/day of limit headroom and **no inboxes**, because all six
campaigns share all twelve.

Neither experiment is running. EXP-001 has been split into EXP-001a (reactivation step 1: the live
email against a rewrite that asks for the list) and EXP-001b (trigger step 1: the live call ask
against a rewrite that offers the trigger list). Both are planned, not started. EXP-002 is blocked
because no lead carries an `icebreaker_style` variable, so the arms cannot be told apart.
`config/experiments.json`.

### The 18:00 KPI dashboard

From `.tmp/kpi_dashboard_2026-09-21.md`.

Thirteen rows. **Five carry a value, eight read "no data"**, and the eight say why rather than
printing a zero.

| Metric | Value | State |
|---|---|---|
| Sends/day vs plan | 109.1% | green |
| Warm-up health per inbox | 100 | green |
| Bounce rate | 1.1% | watch |
| Real reply rate | 1.1% | green |
| **Upwork response time** | **171.2 h** | **ALERT** (green ≤ 1 h, alert > 4 h) |
| Positive reply rate, time to first reply, positive to booked, show rate, no-show rebooked, proposal to close, Upwork reply rate, cost per verified lead | no data | |

The Upwork row is the only alert on the board and it was a real one: the longest wait was one room at
171 hours. The scheduled rooms check is now turned off, so this row is only as current as the last
time you ran `python3 -m jobs.upwork_rooms --now`. If the `generated_at` stamp in
`.tmp/upwork_rooms.json` is more than 6 hours old, the row is blank with a note that the rooms handoff
was written that many hours ago and so is not measured. It reads "turned off" only when there is no
rooms snapshot file at all (or one that cannot be read).

Why the eight blanks are blank:

- **Positive to booked, show rate, no-show rebooked**: read from the reply engine's own records, so
  they fill once the engine books real calls, which needs the GHL token.
- **Proposal to close**: blank even with the token. The code leaves it empty until something records
  dated stage transitions; that is a code change, not a credential.
- **Positive reply rate**: counts the reply engine's classifications, so it waits on the engine
  running on its schedule.
- **Time to first reply**: needs replies actually sent, plus a reply-engine logging change that is
  still in progress (OPS-10).
- **Upwork reply rate, cost per verified lead**: the Upwork proposals list and the list-factory
  ledger, which has never run.

Sends/day reads 109.1% because the day was not finished: 300 sent against 275 planned by that hour,
not against the full 300. The bounce row named its own worst inbox, `lorenzo@proadvero.com` at 2.0%
(3 of 150), and said in the same breath that the row is an aggregate so one bad inbox cannot move it
far.

### The 07:30 sweep

One item waiting on you: a positive reply from a bookkeeping lead, offering afternoon availability,
with no answer from you. `runbooks/PHASE1_SHADOW_REPORT.md` records that run at 7 hours of waiting;
the number grows by the hour, so read the hours from a fresh run, not from here. That is the sweep
doing exactly its job.

### The Upwork check (now run by hand)

The scheduled twice-daily check is turned off; you run `python3 -m jobs.upwork_rooms --now` by hand
(`config/turned_off_jobs.json`). What the last snapshot said, from `.tmp/upwork_rooms.json`
(ingested 2026-09-22T00:45 CT from a Claude session's MCP pull; rooms and contracts both came back):

Three rooms were awaiting a reply from you: two from contracts that have ended (last messages
2026-09-14 and 2026-09-17) and one interview room from 2026-09-22 with 2 unread. Two more are carried
as manual checks that do not clear themselves, a call request and an invitation, because both sit in
the Invitations tab, which the API does not expose.

Both closed contracts still show `review_asked`, `testimonial_asked` and `retainer_asked` as false,
which is what drives the 48-hour post-contract reminder.

The snapshot is only as fresh as the last session that ran the MCP pull; when it is stale the digest
says so on its face and names the command that refreshes it, rather than reporting zero rooms.

### The Friday client card

From the card under `.tmp/scorecards/`.

**These are not the client's numbers, and this tier has never been run against a client's real
data.** The card is a fixtures replay of Advero's own campaign data under a client label, and it says
so itself at the bottom: nothing on it may be sent to anyone. The arithmetic confirms it - the 1,800
sent is Advero's own six campaigns at 300 each (`.tmp/campaign_verdicts_2026-09-22.md`), and the 4
interested is Advero's own positive count (1+2+1). Nothing on this card may be sent to the client.

What the replay produced, as a shape test of the renderer only: **1,800 sent, 22 replies, 6 of them
not automatic, 4 interested, 0 booked, 0 held, 0 closed**, against a blank previous week, with the
next-week note "4 people replied wanting to talk and did not get on the calendar. That is the whole
week's loss, and it is a speed problem, not a copy problem." Read that as a sentence about Advero's
pipeline, which is what the underlying data is, not about a client's first three weeks.

The day-7/21/25/30 readiness verdicts below are unaffected: they are computed from the client roster
and `config/offers.md`, not from the replayed numbers.

The day 7 check-in draft is READY. Day 21, day 25 and day 30 are all **NOT READY**, with the reason
printed on each: unfilled placeholders, and on day 25 the line that matters, `price 2000 is not in
config/offers.md, so it cannot be quoted in writing`.

### The Friday retro

**Ignore the Lessons and Bets sections of the packet on disk, and re-run it.** The file was written at
02:35 on 2026-09-22; the rubric that judges its output landed in `services/retro/lessons.py` at 03:08,
33 minutes later. Under the shipped validator all three of its lessons and all three of its bets are
**rejected**: `lessons.is_generic()` matches every one of them on `\bhold it (at or )?above\b` and
`\bhold [^.]{0,40}at or above\b`. Worse, `bounced` and `bounce_rate` are both in `LOWER_IS_BETTER`, so
two of the bets as written tell you to "Hold bounced at or above this week's level" - advice to keep
bounces **up**, which is the exact failure the 03:08 change exists to block. The artifact now carries a
banner saying so.

The code is fine; only the artifact is stale. To see the current rubric at work offline, run
`python3 jobs/retro_packet.py --fixtures --dry-run`: it reaches no API, bills nothing and writes no
file. `test_the_compliant_fixture_is_not_made_of_the_advice_the_rubric_rejects` in
`jobs/tests/test_retro.py` pins that the offline stand-in passes the rubric.

Do not use `--fixtures` to replace the real packet. A `--fixtures` run is a replay: it is stamped
"FIXTURES REPLAY, NOT A REAL WEEK", and when it writes at all it writes only under
`.tmp/retro/replay/`, with no Skool claim and no entry in the real logs. The real packet comes from
the next real run (`python3 jobs/retro_packet.py --now`), which reads live data and bills Anthropic
unless `LLM_FAKE=1`.

Everything else in the packet stands, and it printed its caveats instead of hiding them: proposals and revenue read "not available" with the reason attached (no GHL
Private Integration token), closes and held calls fall back to Instantly interest status which
under-reports, hours are missing because `RIZE_EXPORT_PATH` is unset, and system changes are the git
log only because the Instantly audit log is reachable only from a Claude session. Every inbox in its
audit reads "not enough data" at 25 sends against a rule that needs 100.

---

## What is not built, and why

Checked against `REVENUE_AUTOMATION_BLUEPRINT.md` on the final pass. The re-review still found gaps
in it (DOC-6); they are added under "Also not built" below.

### A blueprint item that contradicts itself: S9

**S9 asks for Upwork conversations to run on the same machine as email**: "Same 1-hour SLA, same
drafted replies, same booking flow (keep messaging on-platform)", plus a post-contract review,
testimonial and retainer ask within 48 hours.

**The blueprint forbids the first half of that in three other places.** M6 says Upwork stays manual
and "nothing in this plan automates or alters it", and that the only two things touching Upwork are
read-only and outside the application flow. A8 says the rooms check "never drafts or sends on
Upwork". `CLAUDE.md` puts the Upwork application flow on the do-not-touch list. S9's own SLA number
disagrees with itself too: it says "same" SLA while S1's is 5 minutes and Section 6's Upwork target
is 1 hour.

**What is built is M6 and A8, not S9.** `jobs/upwork_rooms.py` lists the rooms waiting on you and the
48-hour post-contract asks when you run it by hand (both daily schedules are turned off in
`config/turned_off_jobs.json`), read-only, and has no Upwork write path at all, and a test
fails if one appears. So the post-contract half of S9 exists. **The drafted-replies and booking half
does not exist and was not attempted.**

I did not resolve the contradiction myself, because resolving it means deciding whether an agent may
write in your Upwork inbox, and that is not a build decision. It is written up as your call in
`DECISIONS_FOR_LORENZO.md` section 0.2. The previous version of this report resolved it silently by
leaving S9 out of both lists, which is how a gap becomes invisible.

### Blocked on a credential you have to create

| Missing | What it blocks |
|---|---|
| **GHL Private Integration token** | Booking itself, and with it three of thirteen KPI rows (positive to booked, show rate, no-show rebooked, which read the engine's own booking records). Also the retro's revenue section, the client scorecard's funnel, the list factory's client suppression, and the onboarding change-set's ability to diff workflows against live. A fourth row, proposal to close, stays blank even with the token: it needs a code change. |
| **Zoom connected to GHL** | Real join telemetry. Without it the no-show machine answers "unknown" for every call, so every proposal carries "No Zoom telemetry: nothing proves this call happened". |
| **A2P 10DLC registration** | Every SMS leg in the show-rate and no-show ladders returns `skipped/a2p_not_registered`. |
| **`PAYMENT_LINK_URL`** | Every SOP-009 "here is the link to get started" draft is permanently unsendable with a visible placeholder. |
| **`NTFY_TOPIC` and `NTFY_TOKEN`** | The topic in `.env` is public and not the generated form, so names, company names and quoted prospect text are stripped from every push. This now costs more than it did: the SLA chase pushes more often, and a redacted chase is harder to act on. |
| **`REPLY_ENGINE_SECRET`** | Unset, shadow signs approval tokens with a development secret that is in the repo, and live refuses to sign at all. |
| **`BASE_URL`** | Unset or local-only, every Approve / Veto / Edit button in shadow points at `http://localhost:8000`, and live refuses to build the card. It cannot be known until the first deploy prints the modal.run URL, which is why deployment is a two-pass step. |
| **A real `GOOGLE_CREDENTIALS_JSON`** | The Job_Log sheet mirror. The placeholder in `.env` parses as JSON, which is why it used to win over the real credentials file; both loaders now validate properly, but the value still has to be pasted. |
| **A fresh Skool token** | The daily post has no category label. Reads work, the write-side auth is stale. |
| **`RIZE_EXPORT_PATH`, `FIREFLIES_API_KEY`** | The retro's hours section and the objections-in-their-own-words section. |

### Blocked on a decision, not on code

| Missing | The decision |
|---|---|
| **Seed addresses for level 2** | No read-only endpoint lists Instantly's seed list (three guesses all returned HTTP 400). Start one test by hand in the UI and copy them. |
| **A send mechanism for level 4** | Instantly v2 has no endpoint for an arbitrary outbound email. The fallback is one throwaway campaign per inbox, which is 45 campaigns per round at the Oct 11 fleet size. There may be a "send a test email" endpoint; nobody has confirmed its path and I would not guess at a send endpoint. |
| **A usable canary pool** | 17 addresses survive suppression; 12 inboxes at 5 each needs 60. |
| **The level 5 baseline campaign** | Fully specified in `changesets/inbox_actions/level5_baseline_campaign.json`; it needs a real campaign id. |
| **Prices in `config/offers.md`** | Four things you sell have no quotable price, so four drafts are blocked, and since the cadence gate was tightened, a TO CONFIRM figure now blocks a follow-up touch as well. |
| **The client suppression list** | `client_domains` is empty. A live client receiving a cold pitch is the one suppression failure that costs revenue. |
| **The Oct 11 plan** | Which warmed inboxes join which campaign, and each campaign's new `daily_limit`. `changesets/capacity/apply_capacity.py` applies it one campaign at a time, with a dry run and a backup, but the plan file is yours to fill in; the example it ships with is refused on apply. |
| **Whether an agent may write on Upwork (S9)** | See above. Today the answer is no, in code and in three blueprint sections. |

### Deliberately not built

| Not built | Why |
|---|---|
| **Instantly webhooks** | The reply engine's shadow poller reads replies with GET calls instead. A webhook is a live write and needs your sign-off. |
| **Any Modal deployment of this build** | `modal deploy` is a live change. The complete schedule is staged as data in `changesets/schedules/` with an install script that is documented and not run. (Two unrelated apps from April are deployed; see the evidence section.) |
| **A Google Calendar read** | The pre-call brief reads a hand-maintained block in `config/ids.json` instead. The service account has zero Drive quota and a calendar read likely needs its own OAuth, which is a new credential decision. |
| **A first-touch stamp on leads** | Nothing in the repo writes one, so every close falls back to last-contact date and is excluded from the performance invoice with the reason printed. |
| **A GHL create-document endpoint** | It does not exist in the API, so a proposal is a manual paste. The text that may be sent is generated and ready. |
| **A paid email finder** | No LeadMagic or Prospeo account. The stage is a stub that only prices itself: about $1.15 per 3,300-lead run. |
| **Demo Library slot 011** | The one-page description and the Loom script are written in `products/`, but nothing was copied into the library because that loop is on the do-not-touch list. |
| **The D6 calendar hold as the blueprint describes it** | The blueprint wants a transparent hold the prospect can see. A GHL appointment carries no transparency flag, so that needs a real ICS attachment sent from the Instantly reply. What exists is a private hold on your own calendar, off by default. |
| **M7's referral / partner campaign** | The blueprint's "agencies and freelancers who need cold-email infrastructure" revenue line has no campaign, no list and no copy. The product kit exists in `products/`; the outbound motion for it does not. |
| **M4's next verticals, as campaigns** | Commercial landscaping, pest control, security guards, medical billing and commercial insurance are named in the blueprint as the campaigns after cleaning is proven. What exists is a written spec, `services/experiments/next_verticals_brief.md`: the ICP, sequence shape, proof line and copy rules for each. No campaign, list or copy exists, and none should until the 1,000-send line answers for cleaning. |
| **F5's Rize time data in the retro** | The hours-by-category section exists in code and prints "not available" because `RIZE_EXPORT_PATH` is unset. |
| **Instantly's Lead Finder agent as the list-factory backstop (O8)** | Not wired, and not mentioned anywhere else in this report - `grep -ri 'lead.finder'` over `jobs/`, `services/`, `shared/`, `changesets/`, `runbooks/` and `config/` finds only this report. The blueprint's O8 row (line 343) asks for it as the fallback source. If Apify or PDL come back empty on a Sunday run, nothing backfills: the factory has no fallback, and O8's rule "every campaign has >=5 days of uncontacted leads" fails silently rather than degrading. The MCP tools for it exist (`lead_finder_agent_*`), so this is wiring, not research. |

### Also not built (found by the re-review, DOC-6)

| Not built | Detail |
|---|---|
| **S7 Proposal Follow-up Sequence** | The D1 to D21 sequence after a proposal. GHL workflows cannot be created through the API, so it exists only as a UI build spec, `changesets/ghl_workflows/proposal_follow_up.md`; the GHL draft is still empty. |
| **S4 and S5 GHL workflows** | The show-rate and no-show workflows are build specs only (`changesets/ghl_workflows/show_rate_workflow.md`, `no_show_recovery_workflow.md`). Today the engine sends those touches itself (`SHOW_RATE_SENDER` defaults to `engine`). If a GHL workflow is ever published while the engine is also sending, the prospect gets every touch twice. Only one side may send. |
| **The monthly jobs** | Placement and spam-word test, domain rotation, Upwork pricing review, case study, new vertical. None is scheduled. |
| **The blueprint's PostToolUse and send-window hooks** | Not built as hooks. The send window (07:00 to 19:00 CT) is enforced in code, and each job writes its own Job_Log row. |
| **F2 GHL snapshots and setup scripts** | The reactivation snapshot exists only as a description of what it must contain (`products/reactivation_system/snapshot.md`); the snapshot itself has not been created. The bid follow-up snapshot does not exist in any form, not even a description; that kit ships the n8n workflow and `templates.csv` only. The reactivation lead import script and the cold-email infrastructure setup script are not built; `products/README.md` lists both. |
| **A1 auto-send** | Brief A1 asks for auto-send after 5 minutes on `positive_interested`. `CLAUDE.md` says the first reply to a positive is never auto-sent. The code follows `CLAUDE.md`: `AUTO_SEND_AFTER_MINUTES` defaults to 0, works only in live, and is not wired into the scheduled poller. Superseded 2026-09-22 by CT3 (approved templates auto-send): see `runbooks/template_approvals.md`. |
| **Slack** | The blueprint sends cards and alerts to Slack. This build uses ntfy pushes and email instead. |
| **A4 Friday audit CSV per domain** | Brief A4's definition of done lists a per-domain CSV from the Friday audit. Nothing writes one. The per-domain level 3 verdicts (reply and bounce rate, failing inboxes) are on the card. Per inbox, the card's level 3 line gives a failing count, and each failing inbox appears in the card's PROPOSALS section as a `remove_from_email_list` proposal whose reason gives the figures it failed on; an inbox on a domain being retired is covered by that domain's `retire_domain` proposal, which gives the domain's figures. Passing inboxes appear only under `--full` and in `--json`: `python3 jobs/deliverability_monitor.py --dry-run --level 3 --json` prints both tables, passing rows included (`level3.per_domain`, `level3.per_inbox`). The Job_Log row and the day's change-set file carry only the proposals that failing verdicts produce, and no change-set file is written on a day with no proposal. See `runbooks/deliverability.md`. |

**Phase 0 status.** Nothing in Phase 0 has been applied. `changesets/PHASE0_MANUAL_CHECKLIST.md` has
the steps.

| Item | Status |
|---|---|
| Campaign settings, sequences and the new step 3 | Staged, not applied |
| Lead labels and the Interested-quiet subsequence | Not created |
| Instantly webhooks | Not created |
| GHL Private Integration token | Not created |
| Zoom connected to GHL | Not connected |
| A2P 10DLC | Not registered |
| ntfy | Topic set, no token, treated as public |
| New domains and inboxes | None bought; how many is your call |
| Instantly UI-only toggles | Not checked in this report |

### Known weaknesses I would fix next

- **The sudden-drop alert cannot fire until about 2026-09-29.** Sending began 2026-09-15, so the
  28-day baseline and the 7-day window are the same data. The card says NOT EVALUATED rather than
  "0 flagged", so it never reads as a passed health check. It is also domain-only for now (R13):
  one inbox sends too little for the per-inbox check to ever fire.
- **The paid-call gate lives in the caller, not the library.** Only the list factory checks
  `ALLOW_PAID_CALLS` before a model call. Every other service would bill real tokens the moment
  `LLM_FAKE` is unset. The new spend ceiling bounds the damage but does not close the hole: it stops
  the tenth dollar, not the first. The gate belongs one level down, next to the model policy. I did
  not move it because it is a default-deny change across five components, **and because moving it
  breaks the GO_LIVE Stage 3 watch**: deployed containers never set `LLM_FAKE`, so a
  `require_paid` in `complete()` would make every tick raise `PaidCallBlocked` and the watch would run
  blind. That trade-off is yours to make: `DECISIONS_FOR_LORENZO.md` C8. The two summary lines that
  used to contradict this bullet (`jobs/README.md` and the list-factory paragraph above) now agree
  with it.
- **The live-write guard is two environment variables, checked in code by `guard_write`.** The hook
  never guarded the build: it is registered only at the repo root and fails open from `Coding/`
  (SAF-1). A Python process that sets `MODE=live` on itself runs unblocked. That already happened once
  and polluted the Job_Log (`.tmp/quarantine/`). The guard rework and read-only keys (R1, R2) are in
  progress.
- **Proposal to close is structurally blank** until something records dated stage transitions.
- **The retro and the client scorecard can compute their week with different code**, because they
  disagree about what a week is on any day except Sunday.
- **The SLA chase has never reached a real phone.** Every rehearsal was shadow, so what exists is a
  `would_do` record per rung. The first deploy is where that is verified.

---

## How to look at any of this yourself

Nothing below **writes** to a live system. Two caveats, because "safe" was doing too much work in an
earlier draft of this line:

- The `--dry-run` jobs still make **read-only GET calls to live APIs** (Instantly, GHL). They are
  reads, not writes, but they are not offline.
- `retro_packet.py` reaches `shared/llm.complete()`, which **bills Anthropic** unless `LLM_FAKE=1`.
  That is the gap described in the weaknesses section: `ALLOW_PAID_CALLS` does not cover Anthropic.
  The `LLM_FAKE=1` in the exports below is what keeps this block free; drop it and the retro costs
  about $0.125.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
export MODE=shadow LLM_FAKE=1 NOTIFY=off    # offline model, no push, no writes

# the whole suite
python3 -m pytest -q

# what each job would do, against live data, writing nothing
python3 jobs/deliverability_monitor.py --dry-run --all-levels
python3 jobs/inbox_inventory.py --dry-run
python3 jobs/campaign_verdicts.py --dry-run
python3 jobs/daily_metrics.py --dry-run
python3 jobs/pipeline_sweep.py --dry-run
python3 jobs/retro_packet.py --dry-run
python3 jobs/client_scorecard.py --dry-run
python3 jobs/upwork_rooms.py --dry-run

# the same, with no network at all, on recorded responses
python3 -m pytest jobs/tests/test_one_system.py -q

# every would_do record a run left behind, and its mode
python3 -c "import sys;sys.path.insert(0,'.');from shared import job_log;import collections;\
print(collections.Counter(r.get('mode') for r in job_log.read_shadow_log()))"

# what the model spend ceiling says
python3 -c "import sys;sys.path.insert(0,'.');from shared import llm;print(llm.budget_status())"
```

Every proposal lands in `changesets/`. Every run leaves one row in `.tmp/job_log.csv`. The complete
schedule is `changesets/schedules/schedules.json`, and the ordered path from here to a live system is
`runbooks/GO_LIVE_CHECKLIST.md`.
