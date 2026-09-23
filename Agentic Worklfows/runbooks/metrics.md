# Runbook: daily metrics, the Maker School post and the KPI dashboard (O3, O4)

Brief A9. Two scheduled jobs plus the Section 6 dashboard they share.

| Job | ID | Schedule (CT) | What it does | Writes |
| --- | --- | --- | --- | --- |
| `jobs/positive_sweep.py` | O3 | 07:30 daily (and Wed) | Calls `jobs/pipeline_sweep.py`, optionally appends the KPI dashboard | none (ntfy digest + Job_Log) |
| `jobs/daily_metrics.py` | O4 | 18:00 daily | Pulls the day, renders the DAILY UPDATE block, writes the tracker row, stages the Skool post, renders the KPI dashboard | Google Sheets row (guarded), Skool post (staged, never sent by the job) |

Everything is read-only against live systems except the sheet row, which goes through `shared.settings.guard_write`; `MODE=shadow` (the default) records a would_do and touches nothing. The Skool post is never sent by the job in any mode, so it is recorded as a plain would_do (`job_log.shadow`) and does **not** call `guard_write`: in live mode `guard_write` opens a `live_write_intent` Job_Log row that a real write is expected to close, and a post that never happens left that row hanging open on every run (re-review OPS-15).

---

## 1. Run them

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

# O4, read-only: pull, render, print. Scratch Job_Log row, no sheet row, no post.
MODE=shadow python3 jobs/daily_metrics.py --dry-run

# O4 for real (still shadow => would_do records + staged files in .tmp/)
MODE=shadow python3 jobs/daily_metrics.py --now

# A specific day, or a replayed clock
python3 jobs/daily_metrics.py --dry-run --date 2026-09-21
python3 jobs/daily_metrics.py --dry-run --as-of 2026-09-21T18:00:00-05:00

# Offline, on the recorded pulls (no network at all)
python3 jobs/daily_metrics.py --dry-run --fixtures --as-of 2026-09-21T18:00:00-05:00

# The KPI dashboard on its own
python3 jobs/daily_metrics.py --dry-run --kpi-only

# O3, the morning list, with the dashboard under it
python3 jobs/positive_sweep.py --dry-run --kpi
python3 jobs/positive_sweep.py --now            # same plus the ntfy digest

# Tests
python3 -m pytest jobs/tests/test_metrics_sources.py jobs/tests/test_metrics_render.py \
                  jobs/tests/test_metrics_sheet.py jobs/tests/test_metrics_kpi.py \
                  jobs/tests/test_metrics_jobs.py -q
```

Flags: `--no-sheet` and `--no-skool` turn off either half of a `--now` run. `--json` prints the whole result.

---

## 2. O3: why there is no second sweep

`jobs/positive_sweep.py` **delegates to `jobs/pipeline_sweep.py`** and adds nothing to the sweep itself.

Phase 1 already built pipeline_sweep as O3 in full: positives with no outbound from Lorenzo in 24 h, booked calls inside 24 h with no confirmation, proposals older than 7 days with no touch, the Upwork rooms waiting, ordered booked > positive > proposal > upwork and inside a kind by pipeline value then age. Its email pagination is budgeted against the 20 requests/minute limit on `GET /emails`, its auto-reply and outbound detection are pinned by tests on the 44 recorded September replies, and its ntfy digest is already redacted for a public topic.

Writing a second sweep would mean two answers to "is this reply positive", two pagination budgets against one rate limit, and two digests that can disagree on the same morning. So positive_sweep is an entry point, not an engine. It adds exactly two things:

1. `--kpi` appends the Section 6 dashboard, so 07:30 says both "what is waiting" and "what is off", **and stages it** to `.tmp/kpi_dashboard_<date>.md` (`.dryrun.md` from a dry run). Printing it to stdout alone meant the scheduled run put it in a process log: `pipeline_sweep` sends its own digest and that digest carries no dashboard, so the "what is off" half never reached Lorenzo on the only run that matters;
2. its own `positive_sweep` Job_Log row recording the delegation, the counts and the staged path, so a scheduled run leaves one row of its own even though the work is logged under `pipeline_sweep`. A crash writes a `failed` row and a high-priority push.

**Two Job_Log rows per O3 run is expected**: `pipeline_sweep` (the work) then `positive_sweep` (`delegated_<status>`). If you only ever see `pipeline_sweep`, something is calling the sweep directly and the schedule is not running.

---

## 3. O4: where each number comes from

| Tracker column | Source | Notes |
| --- | --- | --- |
| Cold Emails Sent | Instantly `GET /accounts/analytics/daily`, summed over the 12 active inboxes | chunked, 12 per call |
| Replies | same, `unique_replies` | |
| Email Reply Rate | `unique_replies / sent` for the day | |
| Email View Rate | **never written** | open tracking is off on all six campaigns, so any value would measure the switch, not the leads |
| Positive Replies | reply engine Job_Log (`reply_engine.process_event`, label `positive*`), **counted per lead** | written only on a day the classifier actually ran; a `reply_engine.poller` row is not evidence. A lead who sends two positive replies is one positive (OPS-14) |
| Calls Booked / Calls Held | store `appointment:*` (`booked_at`) and `noshow_state:*` verdicts | written only when the booking machinery left a trace on that day |
| Proposals Sent / Closes | GHL opportunities whose **stage changed on that CT day**: `lastStageChangeAt`, plus `lastStatusChangeAt` for Won and Lost only. **Never `updatedAt`** | needs a Private Integration token; none exists yet. Without a stage-change date both columns stay blank with a note, and a column with even one undated opportunity in its stage is left blank rather than written short |
| Upwork Proposals / Connects / rates / Hires | `.tmp/upwork_daily.json` | written by a Claude session with the Upwork MCP |
| DMs, Community, Cash, MRR, Active Clients | Lorenzo types them | the job never writes these and never clears them |

**A number the job did not measure is never written and prints `n/a`.** A zero in this tracker is indistinguishable from a real zero day, and both the Dashboard's rolling averages and the streak formula treat it as a logged value.

**And a measured zero never overwrites a number Lorenzo typed.** For `Calls Booked`, `Calls Held`, `Positive Replies`, `Proposals Sent` and `Closes` (`sheet.NO_ZERO_OVER_MANUAL`), a measured 0 against a non-empty cell keeps the cell and the run notes it. The engine books nothing in shadow, so its "calls booked today" is 0 every evening; on a day he had typed 2 booked calls the row used to be rewritten to 0 and the post read "0 booked, 2 held, 0 booked all-time". A non-zero measurement still wins, and an empty cell still takes the zero.

**Stage occupancy is not a daily flow.** `Proposals Sent` and `Closes` are flow columns that `all_time_totals` sums, so writing "4 opportunities sit in Won" into them made two September clients into two closes a day forever. Only opportunities whose stage changed on the reported CT day are written, and when no opportunity carries a stage-change timestamp the columns stay blank and the run says so.

**An edit is not a stage change.** `updatedAt` moves on any edit: a note, a tag, a value change, the nightly mirror touching the record. The first version fell back to it, so two August Won deals and an August proposal edited on 09-21 were written into the 09-21 row as `Closes 2, Proposals Sent 1`, and the retro showed a phantom $10,000 week. The date now comes only from `lastStageChangeAt` (and `lastStatusChangeAt` for Won and Lost, because marking a deal won does not always move its stage). `services/retro/metrics.count_opportunities` applies the same rule and prints "not available" for a stage that holds an undated opportunity (re-review OPS-4).

### The Upwork handoff

`.tmp/upwork_daily.json`, written by a session that has the Upwork MCP (a job process does not):

```json
{"date": "2026-09-22", "proposals": 3, "connects": 120, "views": 2, "replies": 1,
 "hires": 0, "proposals_7d": 20, "replies_7d": 3}
```

`date` is **required**; every other field is optional. `view_rate` / `reply_rate` are derived when not given. **A file whose `date` is not the day being reported, or which carries no `date` at all, is ignored**, because a stale handoff logged as today is worse than a blank. (The guard used to be "has a date AND it does not match", so a dateless file sailed past it and the same proposals and the same Connects spend were logged as every day's activity.)

`.tmp/upwork_rooms.json` is the same file `pipeline_sweep` already reads; the dashboard's "Upwork response time" is the longest wait among rooms marked as awaiting Lorenzo, **and it names the room**. The file's own `generated_at` is checked: more than 6 hours old and the metric degrades to `no data` with a note, because answering a room does not rewrite the file and the wait would otherwise keep climbing past the 4 h line forever.

---

## 4. The sheet: one row, found by date, never appended

Tracker: **"AdveroSolutions - Daily Metrics"**, id `1GuJBW_FSZJsJZ9gmN37EmTGo65DH695BtwhFkBXWDj0` (override with `DAILY_METRICS_SHEET_ID`). Tabs: Daily Update / Daily Progress / Dashboard / Daily Log.

The service account `advero-crm-automation@adverosolutions.iam.gserviceaccount.com` has **zero Drive quota**, so it cannot create a spreadsheet. This job never tries: it opens the tracker Lorenzo already owns and which is shared with the service account as Editor.

The Daily Log holds 400 pre-filled date rows starting 2026-08-03 in row 2, so writing a day is an **update of one row**, not an append. The row is found by reading column A unformatted: the displayed value is `Tue, Sep 22` with no year and cannot be matched safely. 2026-09-22 is row 52.

The write range is `B<row>:Y<row>`: the 23 metric columns plus Notes. Column Z ("Logged") holds a formula that drives the streak and must never be written.

Merge rules:
- a measured number overwrites the cell (the job is the source of truth for what it measures);
- an unmeasured cell keeps whatever Lorenzo typed;
- a manual flow metric with an empty cell renders 0 in the post but is **not written**;
- a stock metric (Total MRR, Active Clients) with an empty cell carries the last restated value forward, for the render only.

**Credentials.** `GOOGLE_CREDENTIALS_JSON` in `.env` is still the placeholder `{"type": "service_account", "paste_your_json_here": "..."}`. It is valid JSON and useless. `services/metrics/sheet.service_account_info()` validates `client_email` + `private_key` on every candidate and falls through to `credentials.json`. `shared/job_log.py::_service_account_info` does **not** do this and returns the placeholder, so the Job_Log sheet mirror cannot authenticate today (see the cross-cutting request in the A9 report).

---

## 5. The streak and the 40-day gap

The last logged day is **2026-08-12** and the streak is **zero**.

`sheet.streak_and_day` counts back day by day from the day being logged. With a 40-day gap the honest answer is **day 5, streak 1**: four logged days plus today, one consecutive day. The job writes today's row and nothing else. No missed day is backfilled, ever. The gap appears as a note in the run output and in the Job_Log row (`gap_days`).

**The evening restatement only corrects a row the 18:00 run wrote.** O4 runs before sending stops at 19:00, so the next evening rewrites yesterday's send count with the finished day. It used to do that for any day Instantly reported, including a day that was never logged, which backfilled the tracker and repaired the public streak for a day nobody posted. Now a day whose row is not logged (the `Logged` formula is 0 or `Cold Emails Sent` is empty) is left alone, with the note `<date> was not restated: it was never logged, and this job does not backfill a missed day` (re-review OPS-13).

---

## 6. The DAILY UPDATE block and the Skool post

The block is the same one the tracker's "Daily Update" tab builds from formulas, rendered in Python so the job can hand it straight to the post. Two deliberate differences:

- **no em dash in the header** (the sheet uses one; the copy rules forbid them in anything a prospect or client reads, and a Skool post is exactly that). The separator is ` | `, which the header already used;
- **`n/a` instead of 0** for anything unmeasured.

Every section prints every day even at zero, so the post keeps the same shape and stays skimmable. The block is signed `Lorenzo`.

`render.copy_violations()` runs on every generated block: em dash, exclamation mark, and any mention of AI, automation or a model name. **A violation blocks the post outright** rather than staging text that breaks Lorenzo's voice.

### The post is staged, never sent

The Skool MCP exists only inside a Claude session, so the job cannot post even in live mode. It returns `mcp_handoff` and writes:

- `.tmp/skool_post_<date>.md`: read this first;
- `.tmp/skool_post_<date>.json`: `{"tool": "skool_posts_create", "group_slug": "maker-school", "arguments": {...}}`. The arguments match the tool schema exactly (`groupId`, `title`, `content`, optional `label`); the schema is `additionalProperties: false`, so nothing else is in there.

Group: Maker School, `groupId` `e256cd9ef1ac4dbe9197634db46e9e3b` (read read-only from `skool_community_info` on 2026-09-22). `skool_community_labels` answered **401 Unauthorized** on the same pull, so the optional category `label` is unset until a session with working Skool auth can read the label list.

To post, in a session with the Skool MCP, after Lorenzo has read the file:

```
skool_posts_create(groupId=..., title=..., content=<the staged markdown>)
```

---

## 7. The KPI dashboard

`services/metrics/kpi.py` renders all thirteen Section 6 metrics as one markdown block: green threshold, alert threshold, today's value, the window it covers, the trend against last week, and the state.

- `green` / `watch` / `ALERT` / `no data`. **A metric with no source reads `no data`, never green.** Ten of the thirteen depend on GHL, the reply engine log or a handoff file that may be absent.
- **Four** metrics are "lower is better" (bounce rate, time to first reply, Upwork response time, cost per verified lead) and their thresholds render with the direction (`<= 1.0%`, `> 2.0%`) so a red cannot be read as a green.
- The trend says "better" or "worse", not "up" or "down".
- **"Positive reply rate" alerts on three days, not one.** Section 6 says "< 0.5% for 3 days". The job computes the trailing seven-day rate as of today, yesterday and the day before (`daily_metrics.positive_rate_by_day`) and the row reaches ALERT only when all three are under the line (`kpi.SUSTAIN_DAYS`). One or two readings under it are `watch`, and the note says how many days in a row it has been. A day whose rate cannot be computed breaks the run: an unknown day is not evidence of a dip. Positives are distinct leads, not events (re-review OPS-14).
- **"Time to first reply" is reply landed to reply sent.** It pairs each `reply_engine.approval` / `sent` row (a real send; a shadow `would_send` is not one) with the lead's reply time, read from that row's `reply_at` or from the `created` row for the same approval. It used to read `created` rows, which is reply to draft queued, and no row carried the reply time, so the row could never produce a value. It still reads `no data` today, because nothing is sent in shadow. The engine logs both ends: `reply_at` (the lead's reply's received time, recorded on the card when it is raised) and `sent_at` on the `sent` row, `reply_at` on the `created` row, and the card's `approval` id on both, so a `sent` row without `reply_at` is paired through its `created` row (`services/reply_engine/approval.py`, re-review OPS-10 and R1 item 5). A later answer in the same thread (`first_reply: false`) is left out. A send with no recorded reply time is skipped, not estimated from the engine's processing time. A `sent_manually` row (a card stuck at `send_failed`, or at `sending` past its 10-minute lease, whose reply did go out, closed with Mark sent) counts as a draft sent, on the day it was marked, but is left out of this metric: its `sent_at` is when Lorenzo pressed Mark sent, and the reply left somewhere between `send_failed_at` (`send_started_at` for a card taken from `sending`) and then. Its `first_reply` is null when the lead's row could not be read.
- **Every row's window is the window its value was computed over.** Three rows used to mix them: "Positive reply rate" divided one day's positives by the week's sends (about a sevenfold understatement, and an ALERT whose Section 6 action is "rework or kill the campaign"), "Show rate" printed one day's one or two calls under a "7 days" label, and "Proposal to close" divided two stage snapshots and could read 133% green. Positives and the show rate now cover the same seven days as their denominators, and "Proposal to close" reads `no data` with the reason.
- **Sends/day vs plan is read three ways, and the window column says which.** After a quarter of the 07:00-19:00 CT send window has passed, it is today's sends against the plan *scaled to the elapsed fraction* (at the 18:00 run the day is 92% done, and comparing 276 sends against the whole 300 printed a 72% ALERT on a day exactly on pace). Before that, and on a day Instantly has not reported at all, it is the last day that finished, because 20 sends divided by 4% of a window is 1,600% of plan. Without either of these the 07:30 run showed a volume ALERT every morning.
- **A row that cannot catch what its Section 6 action asks for says so.** Bounce rate is the aggregate over twelve inboxes while the action ("> 2% remove inbox") is per inbox, so the row's note names the worst inbox and points at `jobs/deliverability_monitor.py`. The warm-up row names every inbox under 98, in the dashboard, in the Job_Log row and in the alert email, because "pause the inbox" needs an address. The Upwork row names the room. Those names never go on a public ntfy card (section 8).
- **Under the table, a per-campaign breakdown of the day.** The job already pays for `GET /campaigns/analytics` on every run; the verdict line in Section 6 is per campaign.
- Two rows are derived from the engine's own artifacts rather than GHL, and their notes say so: "Positive to booked" is bookings in the window over positives classified in the window, "No-show rebooked" reads `done_reason: rebooked` and `previous_state: no_show` out of the store's `noshow_state:*` rows. "Proposal to close" is the only Section 6 row with no implementation, and its note says that rather than blaming the missing token.

Plan volume comes from `ids.json`: 12 active inboxes x 25/day = 300/day. When the 33 warming inboxes go live on 2026-10-11, `active_inboxes` in `ids.json` must grow or "Sends/day vs plan" will read 375%.

Measured read-only on 2026-09-22 for the Sept 15-21 week: bounce 1.1% (watch), real reply rate 1.1% (green), warm-up 100 on every active inbox (green), Upwork response time 178 h (ALERT, Jennifer Lawson's room since Sept 14).

**The "vs last week" column is empty on the recorded fixtures, and that is the truth, not a bug.** A read-only `GET /accounts/analytics/daily` for 2026-09-01..14 over the twelve active inboxes returns **zero rows**: the workspace has no per-inbox history before 2026-09-15. The prior-week code path is exercised instead by `services/metrics/fixtures/instantly_daily_account_prior_week_synthetic_2026-09-08_14.json`, which is **synthetic and named so**; `test_the_trend_column_is_populated_from_the_prior_week` drives the window boundaries (prior_start = day-13, prior_end = day-7) and both trend directions off it. The column fills itself for real from 2026-09-22 onwards.

### One caveat worth knowing

**`unique_replies_automatic` is not subtracted from `unique_replies`.** It is not a subset: on 2026-09-18 the day totals were 4 unique replies and 7 automatic, and on 2026-09-19 they were 0 and 7. The first version of this code subtracted and reported a 0.0% real reply rate for a week that really ran at about 1.1%. Both counters are reported side by side and the automatic one is never used as a deduction. Exact auto-reply exclusion needs the message bodies, which `pipeline_sweep.is_auto_reply` already classifies; that is where to tighten it.

---

## 8. What a failure looks like

| Symptom | Meaning | Do |
| --- | --- | --- |
| status `dry_run_partial` / `partial` | a chunk of account analytics failed, the sheet was unreadable, or the block broke a copy rule | read `notes` in the Job_Log row |
| note `Daily Log unreadable` | no usable service account, or the sheet is not shared with it | check `credentials.json`; the block still renders and is still staged |
| note `ghl_token_missing` | expected today | four KPI rows stay `no data` until Lorenzo mints the Private Integration token |
| note `the reply engine has no rows` | the engine left no artifact on that CT day (no `reply_engine.*` row, no booking, no call verdict) | positives, drafts and bookings are unknown, not zero |
| note `kept what was already in the tracker` | a measured 0 met a cell Lorenzo had filled in | expected while the engine is in shadow; his number stays |
| note `restated <date>` | yesterday's row was rewritten with the finished day's send count | expected every evening after a partial day |
| note `<date> was not restated: it was never logged` | yesterday has no logged row | expected after a missed day; the job never backfills it |
| note `... in proposal_sent carries no stage-change date ... left blank` | GHL returned an opportunity in a flow stage with no `lastStageChangeAt` | that column stays blank for the day |
| note `the run is N% through the ... send window` | O4 runs at 18:00 and sending stops at 19:00 | expected; the plan is scaled and the next run restates the day |
| note `no GHL opportunity carries a stage-change timestamp` | GHL gave occupancy, not dated transitions | `Proposals Sent` and `Closes` stay blank rather than repeating the census |
| note `the Upwork handoff carries no date field` | a session wrote the handoff without `date` | add `"date": "<the CT day>"`; the file is ignored until then |
| `Daily Log has N non-empty row(s) but no readable date in column A` | column A came back as display text, not serials | the run degrades like an unreadable sheet instead of publishing a fake "Day 1" |
| `no_row_for_date` | the day is outside the 400 pre-filled rows (past 2027-09-06) | extend the Daily Log, or rebuild it with `execution/build_daily_metrics_tracker.py --id <id>` (note: a rebuild drops the typed data) |
| KPI `Sends/day vs plan` ALERT at 18:00 | a real volume problem | check O1 / the deliverability monitor for paused inboxes |

A degraded run or any KPI alert sends one notification (`--now` only): an ntfy card and, when Gmail SMTP is configured, an email. **On an unprotected ntfy topic (the default; `NTFY_TOKEN` unset) the card carries counts only**: how many KPI alerts and run notes there are, and that the detail went by email. The alert lines and notes, which can name a client whose Upwork room is waiting or an inbox, go on the email leg only (`email_message`). With `NTFY_TOKEN` set the card carries the full detail too (re-review OPS-2). The same split applies to the failure push below: the error text goes by email.

**A run that dies still says so.** Both jobs wrap the run: any exception writes a `failed` Job_Log row and a high-priority push before it re-raises, so a rotated `INSTANTLY_API_KEY` or a store fault is a message on Lorenzo's phone rather than a traceback in a log nobody opens and a streak that breaks days later.

---

## 9. Before this goes live

1. Lorenzo reads `.tmp/daily_update_<date>.dryrun.txt` and `.tmp/kpi_dashboard_<date>.dryrun.md` for two or three days and confirms the numbers match what he sees in Instantly and on Upwork. (A `--dry-run` writes `.dryrun` files; a `--now` run writes the un-suffixed ones. They used to share names, so previewing a day overwrote the artifact the real run had produced.)
2. A session writes `.tmp/upwork_daily.json` so the Upwork columns stop reading `n/a`.
3. Only then: `MODE=live ALLOW_LIVE_WRITES=1 python3 jobs/daily_metrics.py --now`, which writes the one row. Check the row in the sheet and check the Dashboard's streak cell moved.
4. The Skool post stays a manual paste until Lorenzo says otherwise. It is public writing under his name.
5. To schedule it on Modal, `services/reply_engine/modal_app.py` needs `services/metrics` in `LOCAL_DIRS`, the three env keys (`DAILY_METRICS_SHEET_ID`, `SKOOL_GROUP`, `SKOOL_GROUP_ID`) in `SECRET_KEYS`, and the two cron entries. None of those files belong to this brief; the requests are in the A9 report.

**The cron entries are not fixed UTC.** The blueprint prescribes O3 at 12:30 UTC and O4 at 23:00 UTC, which are 07:30 and 18:00 CT only while Central is on daylight time. After **2026-11-01** the same UTC times resolve to 06:30 and 17:00 CT (verified with the code's own `sources.ct_day` and pytz: `2026-11-01T23:00:00+00:00` is `2026-11-01 17:00:00-06:00`), and O4 would then miss the last hour of the sending day. Schedule in `America/Chicago` where the scheduler supports it; otherwise move the two crons to **13:30 and 00:00 UTC on 2026-11-01** and back to 12:30 and 23:00 on **2027-03-14**.
