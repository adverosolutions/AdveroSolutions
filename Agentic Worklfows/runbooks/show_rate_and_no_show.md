# Runbook: show-rate sequence and no-show recovery (Blueprint S4, S5; brief A3)

Owner: Sales agent. Status: built 2026-09-21, MODE=shadow, nothing live.

## Purpose
Push Discovery Call show rate above 90% and rebook 35 to 50% of no-shows without Lorenzo touching anything but the 4 h "unconfirmed" task and the +10 min call task.

| Piece | File | What it does |
| --- | --- | --- |
| Show-rate sequence | `services/reply_engine/show_rate.py` | T+0 confirmation email (+SMS), T+15 m pre-read per niche, 24 h before "Reply C" SMS+email, 4 h before task if no C, 1 h SMS with link, 15 m "Hopping on now" SMS |
| Pre-reads | `services/reply_engine/prompts/show_rate_preread_<niche>[_outbound].md` | One-page pre-read per (niche, offer), rendered to plain text. Reactivation and outbound carry different mechanisms, different pricing answers and the offer's own proof line |
| No-show detection + recovery | `services/reply_engine/no_show.py` | Zoom-join based detection at start + 10 min **only when there is telemetry** (otherwise `unknown` and a task for Lorenzo); recovery +5 m / +10 m / +1 h / +1 d / +3 d / +7 d / +14 d; SOP-005 repeat policy; late-show reversal; rebooking cancels the sequence |
| Zoom webhook | `services/reply_engine/zoom_webhook.py` | `POST /webhooks/zoom`: URL-validation challenge, HMAC signature check, stores joins under `joins:<meeting_id>` |
| Scheduled job | `jobs/appointments_tick.py` | Every 5 min: fetch appointments (GHL or fixture), schedule + send due touches, run no-show checks, Job_Log, digest |
| GHL build specs | `changesets/ghl_workflows/show_rate_workflow.md`, `no_show_recovery_workflow.md` | Step-by-step UI build + JSON; GHL workflows cannot be created via API |

## How it works (state in the store, `.tmp/store.json` locally, Modal Dict in the cloud)
| Key | Value |
| --- | --- |
| `showrate:<appt_id>:<start_iso>` | the 8 touches with sent/skipped flags; re-entry safe (a reschedule creates a new key and marks the old pending touches `rescheduled`) |
| `confirmed:<appt_id>` | set by `show_rate.mark_confirmed` when the lead replies C (or contact tag `call-confirmed`); carries the `start_iso` it refers to, so a reschedule needs a fresh C; cancels the 4 h task |
| `joins:<meeting_id>`, `joins_by_appt:<appt_id>` | Zoom participant joins (host and notetaker bots are filtered out in detection) |
| `appt:<appt_id>` -> `{zoom_meeting_id}` | written by booking.py (brief A2); maps Zoom meeting to appointment; absence tolerated |
| `noshow_state:<appt_id>` | pending / showed / no_show / late_show / done, plus the `start_iso` the state refers to. When the appointment start moves, the recovery for the old start is cancelled (`rebooked`) and the state machine starts again, so a rescheduled call on the same id can be flagged again |
| `no_show_count:<contact_id>` | SOP-005 repeat counter (1 full, 2 two touches, 3 one touch then Lost) |
| `recovery:<appt_id>:<start_iso>` | recovery touches; last touch carries `after: stage:follow_up_later` (1st) / `note` (2nd) / `stage:lost` (3rd) |
| `offered_slots_recovery` | slots already offered in recovery emails (plain ISO strings). Every reservation is ALSO written into `approval.py`'s `offered_slots`, in approval's own `{slot, lead, at, source}` row shape, because `approval.offered_slots()` and `cadence.fresh_slots()` read only that key: one registry with one reader is what makes "never double-offered" true in both directions. `no_show.fresh_two_slots` reads the union and prunes times already past; `release_recovery_slots` gives a slot back when the copy that advertised it is re-rendered |
| `noshow_flag:<appt_id>:<start_iso>` | the claim that makes one missed call count once. Written with `set_if_absent` **before** the counter, the recovery record and the GHL writes, so a GHL 5xx in the middle cannot make the next tick count the same miss again and serve the second-no-show copy |
| `touch_sent:<touch_key>` | per-touch dispatch claim (`set_if_absent` before the send, deleted again only for a retryable failure). A container killed between the send and the bookkeeping cannot re-send the message |
| `showrate_hold:<appt_id>` | **the approval hold.** Written by `booking.register_booking` for every call the engine books from a reply, because that happens at classification time and the prospect has been told nothing. While it exists, `ensure_scheduled` stamps `held` on the schedule, `run()` dispatches nothing from it (the touches stay pending, unburned) and `no_show.process` returns `awaiting_approval` without chasing anybody. `approval.send_approved` calls `show_rate.release_hold` once the approved reply is out, which clears it and re-anchors the T+0 touches to that moment; `approval.cancel_booking` tears the whole schedule down instead. A widget booking has no marker and is never held. Fail-closed: a hold nobody releases sends nothing |
| `showrate_bootstrap`, `showrate_seen:<appt_id>:<start_iso>` | freshness bookkeeping. The bootstrap marker is claimed once per run: a store that has never been bootstrapped is a cold start (first deploy, or a rebuild after a corrupt store was quarantined), and every booking already on the 30-day calendar is treated as old news |

Every outbound action goes through `shared.ghl.GHL` writes (`send_message`, `create_task`, `update_appointment_status`, `create_note`, `update_opportunity_stage`), each of which calls `shared.settings.guard_write` first. In shadow the result is a `{"shadow": true}` record in `.tmp/shadow_log.jsonl` and no HTTP request.

## Gates that stay closed until told otherwise
| Gate | Env | Effect while closed |
| --- | --- | --- |
| Live writes | `MODE=live` + `ALLOW_LIVE_WRITES=1` | everything is `would_do` |
| SMS legs | `A2P_10DLC_REGISTERED=1` | SMS touches generated, `skipped=a2p_not_registered`; day-1 recovery SMS becomes a task for Lorenzo |
| Loom links | `LOOM_URL_CLEANING`, `LOOM_URL_BOOKKEEPING`, `LOOM_URL_RECRUITING` (or `LOOM_URL_GENERIC`) | the Loom sentence is simply left out of the confirmation email. The email still goes. The unresolved-placeholder guard stays for real unrendered `{{variables}}` |
| Sender switch | `SHOW_RATE_SENDER=ghl` | engine schedules and logs only, every dispatch skipped `sender_is_ghl` (use when the GHL workflows are published; default `engine`) |
| GHL access | `GHL_PRIVATE_INTEGRATION_TOKEN` | reads return None (fixture fallback), writes still log intent in shadow |
| Zoom webhook | `ZOOM_WEBHOOK_SECRET` | endpoint answers 503 `zoom_secret_missing`; nothing stored, so `detect` returns `unknown` for every call and Lorenzo gets a "mark it by hand" task instead of a no-show flag |
| Zoom URL validation | `ZOOM_URL_VALIDATION` (default on) | set to `off` once the subscription is validated. The challenge branch answers before signature verification, so it refuses any plainToken that is not a short base64url token (it must never sign a `v0:<ts>:<body>` message) |

## How to run (shadow)
```
cd "Agentic Worklfows"
python3 -m jobs.appointments_tick --dry-run --appointments jobs/tests/fixtures/appointments_2026-09-21.json
# replay a moment in time and a set of Zoom joins
python3 -m jobs.appointments_tick --dry-run --now 2026-09-23T11:41:00-05:00 \
  --appointments jobs/tests/fixtures/appointments_2026-09-21.json --joins joins.json --store .tmp/showrate_demo_store.json
```
`--dry-run` forces MODE=shadow for the process even if `.env` says live, **and** points the store at
`.tmp/dryrun_store.json` unless `--store` says otherwise: a dry run used to gate HTTP only, so the
documented replay above wrote to the production store. A fixture is never authoritative either: the
GHL read error is kept (`replay: true`), `active_ids` stays `None`, and nothing outside the fixture
is treated as cancelled. Output: a digest (also sent through `shared.notify`, which is a no-op with `NOTIFY=off`), a `Job_Log` row (`.tmp/job_log.csv`, plus the sheet tab when `JOB_LOG_SHEET_ID` is set), and shadow records in `.tmp/shadow_log.jsonl`.

Zoom webhook locally: mount `zoom_webhook.router` in the reply-engine FastAPI app (`app.include_router(zoom_webhook.router)`; `app.state.store` optional). Validate with a signed request (see `tests/test_showrate_zoom_webhook.py` for the exact header math).

## How to test
```
cd "Agentic Worklfows" && python3 -m pytest services/reply_engine/tests/test_showrate_schedule.py \
  services/reply_engine/tests/test_showrate_no_show.py services/reply_engine/tests/test_showrate_zoom_webhook.py \
  jobs/tests/test_appointments_tick.py -q
```
Plus `services/reply_engine/tests/test_showrate_confirmation_hook.py`, which pins the
`confirmation_skipped` guard in `app.py::_appointment_hooks` (the only caller of
`show_rate.mark_confirmed`): an out-of-office and Ilmi's "Sure Let's get together on Monday at 2
CTS" must not switch off the 4 h unconfirmed-call task.

Covers: exact sequence and offsets, DST (2026-03-08 spring forward, 2026-11-01 fall back: "24 h before" is 24 real hours), past-time skips for bookings inside 24 h, A2P gating, night-time SMS deferral to 07:00 CT, re-entry on reschedule, C-reply cancelling the 4 h task, copy rules (no em dashes, signed Lorenzo, no automation talk, 3-bullet agenda), host-only join -> no_show, lead join at +3 m -> showed, join at +12 m after the flag -> late_show, notetaker bot ignored, Fireflies fallback, recovery timings and copy, SOP-005 repeat policy incl. Lost move, rebooking cancels recovery, Zoom challenge + signature + stale timestamp, meeting->appointment mapping, tick fixture fallback, `--dry-run` forcing shadow, Job_Log row. Every test asserts zero HTTP requests in shadow (httpx.MockTransport recorder).

## Go-live checklist (do not skip a line)
1. [ ] 48 h shadow: `appointments_tick` on a 5-minute schedule with real GHL events (needs `GHL_PRIVATE_INTEGRATION_TOKEN` read scopes: calendars, calendars/events, contacts, conversations, opportunities). Review `.tmp/shadow_log.jsonl`: every `would_do` is a message you would have sent yourself.
2. [ ] Zoom connected to Lorenzo's GHL user; Discovery Call conferencing switched from Google Meet to Zoom; a test booking shows a unique Zoom link.
3. [ ] Zoom Marketplace webhook-only app created; `ZOOM_WEBHOOK_SECRET` set; URL validation passes against the deployed `/webhooks/zoom`; a test meeting produces `joins:<id>` entries.
4. [ ] booking.py writes `appt:<appointment_id> -> {zoom_meeting_id}` (brief A2) or the Zoom link on the appointment carries the meeting id.
5. [ ] Three Looms recorded, URLs in `.env` (`LOOM_URL_*`). No `[Loom:` placeholder left in any would_do body.
6. [ ] Booking widget URL verified in the browser (`config/ids.json` note) and used as the reschedule link.
7. [ ] A2P 10DLC: registration submitted (Low-Volume Standard). Leave `A2P_10DLC_REGISTERED` unset until GHL shows the campaign approved.
8. [ ] Decide the sender per sequence: engine (recommended; fresh slots in recovery emails) or GHL workflow (build from the changeset specs, test in Draft). Never both.
9. [ ] Test end-to-end in live mode against a test contact (Lorenzo's own email/phone), one booking: confirmation, pre-read, reply C, then a deliberate no-show at start + 10 min -> `noshow` status, "Still on?" email, call task; then join late -> `showed` and recovery cancelled.
10. [ ] Lorenzo approves the diff of the shadow log; set `MODE=live` and `ALLOW_LIVE_WRITES=1` only for the tick process; `guard_live_writes.sh` stays in place for the interactive session.
10a. [ ] Before the watch starts, confirm the evidence file is clean:
    `python3 -c "import csv,collections;print(collections.Counter(r['mode'] for r in csv.DictReader(open('.tmp/job_log.csv'))))"`
    must print `{'shadow': N}`. Anything else means something wrote live. Dry runs and the replay write
    into `.tmp/scratch/<run>/` instead (`shared.job_log.use_scratch_logs`), so they never pollute it.
11. [ ] First live week: Lorenzo reviews the daily digest; the Friday retro reports show rate (showed / booked) and rebook rate (rebooked / no_show).

## Rollback
- Immediate: unset `ALLOW_LIVE_WRITES` (or `MODE=shadow`) on the tick process. Pending touches keep being computed and logged, nothing is sent.
- Stop one appointment: `store.set('confirmed:<appt_id>', ...)` is not a stop; instead delete the `showrate:<appt_id>:*` and `recovery:<appt_id>:*` keys, or set `state=done` in `noshow_state:<appt_id>`.
- Undo a wrong no-show flag: `GHL.update_appointment_status(id, 'showed')` (guarded) and `no_show.cancel_recovery_for_rebooking(store, appt_id)`.
- GHL side: unpublish the workflow (Draft) removes all contacts from it.
- Nothing here deletes data; the store and logs are append-or-overwrite only.

## Thresholds and alerts
| Metric | Target | Alert |
| --- | --- | --- |
| Show rate (showed / booked, weekly) | > 90% | < 80% for a week: check reminder deliverability and the 1 h SMS once A2P is on |
| Confirmation (C replies / 24 h reminders) | > 60% | < 40%: change the 24 h copy, add the 4 h call task earlier |
| No-show flagged with a later join (late_show / no_show) | < 10% | > 20%: the 10-minute rule is too tight or the webhook is delayed; check Zoom event latency |
| Rebooked within 7 days (rebooked / no_show) | 35 to 50% | < 25%: review the +1 h email slots and the +10 m call task completion |
| Tick errors in Job_Log | 0 | any `error` row -> ntfy high priority |
| Touches skipped `unresolved_placeholder` in live | 0 | any -> record the Loom or unset the placeholder line |

## Known gaps and requests for other briefs
- **This job covers GHL bookings only.** Ilmi (Wed 11:30 CT) and Sopio (Thu 15:00 CT) are hand-made Zoom events on Lorenzo's own Google Calendar, so no confirmation, pre-read, reminder, "reply C" or no-show check runs for either. They are manual this week. The tick prints `NOT COVERED: ...` for each on every run (`manual_calendar_calls`). Feeding the `config/ids.json` seed in as an appointment source was considered and rejected: it carries no GHL contact id and would mail a ladder of reminders to two prospects who agreed those times with Lorenzo directly.
- **The "reply C" loop needs the token.** `scan_ghl_confirmations` reads GHL conversations before the 4 h task is raised, but the GHL `GET /conversations/search` envelope is unverified, so the parser is tolerant and fails closed. One real payload turns it into an exact one.
- booking.py (A2) now calls `show_rate.hold(...)` and then `ensure_scheduled(...)` right after creating an appointment, and writes `appt:<id> -> {zoom_meeting_id, contact_id, opportunity_id}`. The rebooking hook is no longer a dependency: the tick cancels a recovery itself when the appointment start moves, when the contact has a call in the window, or through `no_show.cancel_recovery_for_rebooking` on a new appointment id.
- The reply engine (A1) calls `show_rate.mark_confirmed(store, appt_id, now)` when a lead with an upcoming call replies "C" (or "confirm", "yes") and `no_show.cancel_recovery(store, appt_id, "replied")` when any inbound reply arrives from a contact in recovery. The GHL side of the same question is `scan_ghl_confirmations`.
- `appointments_tick` normalises GHL calendar events with `contact` fields when present; without a token the fixture file is the only source.

## What changed in the 2026-09-21 review pass (brief A3)
| Was | Now |
| --- | --- |
| No Zoom data was read as "nobody joined", so every held call was flagged a no-show | `detect` returns `unknown` unless there is a usable evidence channel (a join inside the meeting window, a Zoom started/ended event, a Fireflies transcript length, or a hand-set GHL `appointmentStatus`). `process` then raises one task for Lorenzo and flags nothing |
| Any join under the meeting id counted, however old | Joins are filtered to start - 30 min .. end + 30 min, in `zoom_webhook.joins_for_appointment` and again in `detect`. A late show also needs a join *after* the flag |
| A rebooked lead kept receiving the recovery, ending in "Closing your file" and Follow Up Later | The start moving cancels the recovery (`rebooked`); `run_recovery` skips contacts with a call ahead; the tick calls `cancel_recovery_for_rebooking` for a new appointment id |
| Sent flags were persisted once per appointment, after the whole touch loop | Each touch is written back immediately after dispatch, and the stage move runs after the loop, so a GHL 500 cannot un-send a message |
| The final touch being *skipped* still moved the opportunity | A stage move needs a real send; a skip creates a task for Lorenzo instead |
| `no_show_count` never went down | Reset to 0 on a held call, decremented on a late show |
| Recovery wrote ISO strings into `offered_slots`, which `approval.py` owns | Recovery uses `offered_slots_recovery` **and** writes an approval-shaped row into `offered_slots`, so the one registry every other reader consults sees recovery's reservations too |
| A cancelled or deleted appointment kept getting reminders | The tick passes the live appointment ids and the read window into `show_rate.run`; a failed GHL read passes `None` and cancels nothing |
| A failed calendar read looked like "zero appointments" and logged `ok` | `fetch_appointments` reports the error, the Job_Log row is `partial` and the digest goes out at `high` priority |
| `--dry-run` still POSTed the digest to ntfy.sh | `--dry-run` also sets `NOTIFY=off`: no outbound request at all |
| 7-day lookahead against a 30-day booking horizon | `LOOKAHEAD = 30 days`; a booking first seen more than 2 h after it was made skips the T+0 touches (`stale_booking`) rather than sending "Locked in" days late |
| The pre-read was chosen by niche only | Chosen by (niche, offer): `show_rate_preread_<niche>_outbound.md` carries the guarantee, the outbound proof line and no commission number |
| No Loom URL meant a `[Loom: ...]` placeholder that live mode silently dropped | The sentence is omitted; the confirmation always goes |
| A missing token or a transport error burned the touch | Retryable: the touch stays pending and counts as an error, so the tick reports `partial` |
| SMS deferral only knew Central | The confirmation SMS respects the lead's own 07:00-19:00 and Mon-Fri; reminders anchored to the call are never pushed past it |
| `reminder_15m_sms` was a bare link and the lead's first name | It names Lorenzo |
| The cleaning guarantee lost its `/yr` | "$24,000 a year in new cleaning contracts signed within 90 days" |
| Two overlapping ticks could dispatch the same touch twice | `jobs/appointments_tick` takes an exclusive lock file for the whole run; the slot registry uses the store's atomic `append` |


## What changed in the completeness review pass (2026-09-22, third round)
| Was | Now |
| --- | --- |
| `register_booking` armed the ladder at classification time and `SEQUENCE` puts `confirm_email` at T+0, so the ten-minute tick mailed the prospect "Locked in for ..." **before the approval card was tapped**, and after a veto | The schedule is created **held** (`showrate_hold:<appt_id>`). Nothing dispatches from a held schedule; `approval.send_approved` releases it with the approved reply and re-anchors the T+0 touches to the release moment, so a late approval still gets its confirmation instead of a `too_late` drop |
| `approval.cancel_booking` cancelled the GHL event, the opportunity, the Instantly interest and the slot, but left the ladder armed and the `appointment:`/`appt:` rows in place, and the tick could not clean up (it only cancels what GHL reports cancelled, and nothing is authoritative without a token) | `approval.teardown_booking_records` deletes the schedules, the hold, `appointment:<id>`, `appt:<id>`, `zoom_meeting:<id>` and the first-seen markers. Pinned by `test_a_vetoed_booking_leaves_zero_armed_touches_and_no_appointment_row` |
| `no_show.process` chased a call the prospect had never been told about | A held appointment returns `awaiting_approval` and does nothing |
| `register_booking` called `cancel_recovery_for_rebooking` with the id of the call it had just created, which wrote `state=done`; `process()` returns immediately on done, so **no-show detection never ran for any engine-made booking** | `cancel_recovery_for_rebooking` refuses to invent a state record: it only marks done when something was actually cancelled or the state is already `no_show` |
| A call that was held left the Instantly lead at interest 2 (`meeting_booked`) for ever, because nothing in S4/S5 touched Instantly. Blueprint S3 item 4 asks for 3 | The `showed` and `late_show` branches call `no_show.mark_meeting_completed`, a guarded `update_interest_status(..., 3)`. The lead email and campaign id come from the appointment or from the `appointment:<id>` row |
| The 24 h "reply C" reminder goes out through GHL, and only the Instantly poller read confirmations, so the 4 h "has not confirmed" task fired on essentially every booking | `show_rate.scan_ghl_confirmations` reads the GHL conversation for every call still waiting on a C, before the task can be raised, using the same `_looks_like_confirmation` / `_body_is_out_of_office` / "names another time" checks as the Instantly path (imported, not copied). Needs the token; without one it reports how many calls are waiting and the task still fires |
| Nothing said that the two calls actually on the books are Google Calendar events the engine cannot see | `jobs.appointments_tick.manual_calendar_calls` reads the `config/ids.json` seed and the digest prints "NOT COVERED: ..." for each one on every run. They are deliberately **not** scheduled: the ladder would mail reminders to prospects who agreed those times with Lorenzo directly |
| `ZOOM_WEBHOOK_SECRET`, `A2P_10DLC_REGISTERED`, `NTFY_TOKEN` and `CADENCE_D6_HOLD` were in no Modal secret, so four runbook steps could not be performed in the container | All six keys (plus `ZOOM_URL_VALIDATION`, `NTFY_ALLOW_SENSITIVE`) are in `modal_app.SECRET_KEYS` and in deployment step 2a, and `test_every_env_key_is_deployable` walks the AST so it cannot recur |

## What changed in the 2026-09-22 review pass (brief A3, second round)
| Was | Now |
| --- | --- |
| `BOT_NAME_MARKERS` matched as bare substrings of the name AND the whole email, so "Fred Wilson" and `manuel@gongoraservices.com` were notetaker bots | Whole tokens in the display name, a known product phrase, or a known notetaker email **domain**. The appointment's own contact address always wins over the heuristic |
| One failing appointment aborted the whole tick, so every other started appointment and the recovery sweep for every older no-show were skipped, on every tick, forever | `tick()` isolates each appointment and the recovery sweep in their own `try/except`; failures land in `result["errors"]`, the Job_Log row is `partial` and the digest names the appointment |
| The SOP-005 counter was bumped before the GHL writes and the state record written after, so a 5xx made the retry count the same miss twice | `noshow_flag:<appt>:<start>` is claimed with `set_if_absent` first; the counter and every store record are written before any GHL call |
| Touches were dispatched before the sent flag was persisted | `touch_sent:<touch_key>` is claimed before the send and released only for a retryable failure |
| Staleness was decided once, at scheduling time | `dispatch_block_reason()` re-checks at dispatch: nothing in S4 goes out once the call has started, and each template has a max lateness (`too_late`) so an outage cannot deliver "Tomorrow at 2:00 CT" on the day of the call |
| A missing `booked_at` meant "freshly booked", so the first tick after deploy mailed "Locked in ... the calendar invite is on its way" to every booking in the 30-day window | Fail closed: `_staleness()` treats a cold start with no `booked_at` as an existing booking. A **reschedule** is always fresh, because GHL keeps `dateAdded` and only moves `dateUpdated` |
| The 14-day ladder wrote the opportunity stage with no read | `_apply_after` reads the opportunity first and leaves `proposal_sent` / `won` / `lost` alone; the ladder also stops once the appointment is `showed` / `late_show` |
| Only SMS was held to 07:00-19:00 CT | Proactive email touches (`confirm_email`, `preread_email`) are too. Weekends still hold for SMS only, so a Friday-evening booking is confirmed on Saturday morning rather than Monday |
| Recovery emails were deferred by hour only | `weekdays_only=True`, so "Missed you on our call" and the day-3 email never land on a Saturday or Sunday |
| Every recovery touch was rendered once, at flag time, so the +1 day and +3 day copy quoted slots that had already passed | The slot line is re-rendered at dispatch (`_refresh_slot_copy`); dead reservations are released so they stop blocking other leads |
| A join delivered late but timed before the flag was not a late show | Any lead join inside the appointment's own window is a show; idempotency is keyed on a seen-join id set, not on the join time |
| `meeting_signals` returned started/ended for the reusable Personal Meeting ID with no window filter, turning "no telemetry" into a no-show | Signals are filtered to the appointment's own window, so silence stays `unknown` |
| A Fireflies transcript with words in it could still produce `no_show` before the meeting end | Length > 0 answers `showed` immediately; only an empty transcript waits for the end |
| The "mark it by hand" task was recorded as created even when the GHL write was dropped | `unknown_task_at` is only set when the action is `done` or `would_do`; otherwise the tick reports the failure |
| `no_contact_id` permanently burned a touch | Retryable, with a `MAX_TOUCH_ATTEMPTS` cap, and the contact id is resolved from the refreshed snapshot at dispatch time |
| `mark_confirmed(store, id, now)` stored GHL's raw start while `is_confirmed()` compared a normalised one | Both branches normalise, and `_appointment_snapshot` stores one canonical form |
| A booking with `appointmentStatus: "new"` was dropped as a cadence hold | Only the `HOLD: ` title prefix marks a hold, and a dropped event is logged at WARNING |
| `normalise_ghl_event` dropped the contact's timezone, offer and niche tags | `lead_tz`, `offer` and `niche` come from the contact, so the lead-local SMS window, the "(1:00 ET)" clarifier and the correct offer copy all work for a real GHL booking |
| The third-no-show Lost move wrote no reason, so S8 mirrored it as not_interested (-1) | The move carries "No show x3 (SOP-005)" when `shared.ghl.update_opportunity_stage` accepts a `lost_reason` (feature-detected; see the cross-cutting request) |
| `show_rate.appointments_tick(dry_run=True)` ignored the flag and ran live | It calls `jobs.appointments_tick._force_shadow()`, and a string `now` is parsed instead of raising |

Still open (not this component's files, see the report's cross-cutting requests):
`shared.ghl.update_opportunity_stage` gaining an optional `lost_reason` (the Lost move
feature-detects it today), `shared.ghl` gaining a `get_opportunity(id)` read (the stage guard falls
back to `search_opportunities`), `app.py` treating an out-of-office BODY as non-confirming whatever
the classifier label says, `shared/slots._shift_days` DST handling for fixed-offset datetimes, and
`poller.run_once` advancing its cursor past unprocessed replies. `Store.mutate` / `set_if_absent` /
`add_once` now exist and this component uses them for every read-modify-write of a touch schedule,
a recovery record, the repeat counter and the slot registries.
