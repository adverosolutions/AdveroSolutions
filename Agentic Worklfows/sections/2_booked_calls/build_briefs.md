# Build briefs for the new reminder and no-show sequences (section 2, 2026-09-23)

Copy: `copy_signed_off.md` (verbatim, including no-link variants and fallback subjects). Code map: `build_map.md`. Rules: root `CLAUDE.md` and `../README.md` (shadow only, no live flags, no template approvals, Python 3.9, tests on mocked transports with zero HTTP in shadow).

Waves: **1** = A1 (reviewer-max) and C (reviewer) in parallel. **2** = A2 and B in parallel after A1 is approved (each reviewer). Then the full suite, runbook, push, and the id list to section 4.

## Template keys (fixed here so the pieces agree)
| Message | Key | Status |
|---|---|---|
| Widget-booking confirmation | `confirm_email` | keep (unchanged copy) |
| R2 | `reminder_24h_email` | keep key, new copy |
| R3 | `reminder_morning_email` | new |
| R4 | `reminder_1h_email` | new |
| removed | `confirm_sms`, `preread_email`, `reminder_24h_sms`, `unconfirmed_task`, `reminder_1h_sms`, `reminder_15m_sms` | delete |
| N1 | `ns_still_on_email` | keep key, new timing (S+3) and copy |
| N3 / second miss | `ns_reschedule_email` / `ns_reschedule_email.repeat` | keep keys, new copy |
| N4 | `ns_d1_email` | new |
| N5 | `ns_d3_value_email` | keep key, new copy |
| N6 | `ns_d7_yes_no_email` | keep key, new copy |
| N7 | `ns_d14_breakup_email` | keep key, new copy |
| N8 | `ns_third_miss_email` | new |
| removed | `ns_still_on_sms`, `ns_call_task`, `ns_d1_other_channel`, `ns_d1_other_channel_task` | delete |

## A1: in-thread transport (new module `services/reply_engine/thread_reply.py`) [worker-heavy, reviewer-max]
Goal: one function both ladders call to send a lead-facing email as a reply in the lead's Instantly thread, falling back to a GHL email only when the lead has no thread.
- `find_thread(store, appointment)`: resolve the lead's `lead:<campaign_id>:<email>` row: from `appointment["campaign_id"]` + `email`; else the `appointment:<id>` row (as `no_show._lead_identity`); else scan `store.keys("lead:")` for the email (as `show_rate.lead_opted_out`). More than one match and no way to tell which thread is current: return none with reason `ambiguous_thread` (never guess).
- `send_lead_email(store, appointment, subject, body, now, *, instantly, ghl, contact_id)`: with a thread (eaccount, last_email_id, recipient via `cadence.recipient_for`), reply with `instantly.reply_to_email(last_email_id, eaccount, "Re: <thread subject>", body, to=recipient)` behind `cadence.thread_recipient_ok` (model: `cadence._send`, 1731-1791): live sends only on a True verdict; False/None holds with `recipient_mismatch` / `recipient_unverified` and does NOT fall back to GHL. No thread ids at all: `ghl.send_message(contact_id, type="Email", subject, message=body)` as today. Returns a record `{transport: "instantly_thread"|"ghl_email"|None, sent, skipped, reason, result}`.
- Send window: refuse outside `slots.is_send_time(now)` with reason `outside_send_window` (retryable; the caller keeps the touch pending).
- Shadow: every write goes through the clients' guarded `_write`; zero HTTP in shadow (assert with the MockTransport recorder like existing tests).
- Tests: thread found via each of the three routes; ambiguous; recipient True/False/None; no thread -> GHL; outside window; shadow makes no requests; the `to=` is always the lead.
- Out of scope: template gate (callers keep it), schedule changes.

## C: booking replies without the booking link (`services/reply_engine/booking.py`) [worker, reviewer]
- Remove the booking-link line (`draft.BOOKING_LINE`, "Or if it's easier, grab a time here: {booking_url}") from the 8 counter-proposal replies: booking.counter.window_no_fit, outside_window_early, outside_window_late, weekend, too_soon, beyond_horizon, slot_taken, booking.slot_already_taken. Everything else in those replies stays word for word. Stop importing `BOOKING_LINE`.
- Update tests that pin that copy. In the report, list each of the 8 replies before and after (Lorenzo sees them).
- Do not touch the "Locked in" confirmation.

## A2: reminders (`services/reply_engine/show_rate.py`, `jobs/appointments_tick.py` if needed) [worker-heavy, reviewer]
- SEQUENCE: `confirm_email` (T+0, widget bookings only, unchanged), `reminder_24h_email` (-24 h), `reminder_morning_email` (08:30 lead local on the call day; CT when the zone is unknown), `reminder_1h_email` (-1 h). Delete the removed keys, their copy, `load_preread`/`preread_path` and `prompts/show_rate_preread_*.md`. Keep `AGENDA` (the widget confirmation uses it).
- Rules: R2 is skipped (reason `booked_late`) when the booking moment is later than R2's time minus 6 h, or R2's time is past, or R2's time falls on a Saturday or Sunday (send window is weekdays; a Monday call gets R3 instead); R3 is scheduled only when R2 was skipped and the call is not on the booking's own (lead-local) day. Booking moment: `min(appointment["booked_at"], now)` when `booked_at` is present, else `now` at schedule creation.
- `{time}` gets the lead's local time in brackets when the zone is known and not CT (same as `fmt_when`).
- Copy: exactly `copy_signed_off.md`, with the no-link variants; subjects only matter for the GHL fallback.
- `MAX_LATENESS`: `reminder_24h_email` 6 h (as today), `reminder_morning_email` 3 h, `reminder_1h_email` 30 min.
- `dispatch_touch`: email goes through `thread_reply.send_lead_email` (A1). Outside the send window the touch stays pending (retry next tick). Template gate, opt-out and placeholder checks unchanged and still before the send.
- `shared:` commit (its own commit): in `template_approvals.py` set `SHOW_RATE_LEAD_FACING` and `NO_SHOW_LEAD_FACING` to the keys in the table above (both tuples, so B does not touch this file). Do not edit `config/template_catalogue_hashes.json` or `config/approved_templates.json`.
- Tests: update the pinned schedule/copy tests; add: 3-days-out booking (R2, R4), next-day booking after the 24 h mark (R3, R4), booked 26 h out (R2 skipped for the 6 h rule, R3), Monday call (R3), same-day (R4 only), local time in `{time}`, dispatch via thread and GHL fallback, window deferral.

## B: no-show ladder (`services/reply_engine/no_show.py`, `jobs/appointments_tick.py`) [worker-heavy, reviewer]
- N1 `ns_still_on_email`: a pre-flag nudge at S+3 when there is Zoom evidence (meeting started or host joined) and the lead has not joined; once per appointment+start (claim key); `MAX_LATENESS` 7 min (never after S+10). Add a light `--no-show-watch` mode to `jobs/appointments_tick.py` that runs only N1 and detection for calls started in the last 30 minutes, so it can be scheduled every minute in call hours; do not edit the Modal or launchd schedule files (section 4 adds the entry; note it in the report).
- Ladder after the no-show flag (count 1): N3 at `max(flagged_at, start + 25 min)`; N4 next business day 10:00 lead local; N5 3 business days after the miss at 10:00 lead local; N6 7 days after (moved to the next weekday) at 10:00 lead local; N7 14 days after, same rule. After N7 is sent: `nurture.enroll(lead_email, "no_show_no_rebook", now, note=<appointment id>)` plus the existing `stage:follow_up_later` move.
- Count 2: N1, `ns_reschedule_email.repeat` at start+25, N6 3 business days after; after N6 is sent, nurture.enroll. Count 3+: N1, N8 at start+25; after N8, nurture.enroll plus the existing `stage:lost` move.
- N5 with no campaign/offer on file: skip N5 (reason `no_niche_point`); never a generic line.
- Slots: N3, N3.repeat, N4, N5, N6 each claim two fresh slots (`claim_recovery_slots`) and release the lead's previously offered recovery slots, so the "taken" line is true. No booking link anywhere; delete `grab_line` / booking usage in this module's copy.
- Reply stop for every booking: before dispatching any ladder touch, look up the lead's thread (`thread_reply.find_thread`); if the lead has replied since the no-show flag, cancel the rest with reason `replied`.
- Dispatch: emails through `thread_reply.send_lead_email`; delete SMS legs, the call task and the day-1 other-channel task. Keep the `unknown` "mark it by hand" task (internal, Meet calls).
- `MAX_LATENESS` for new keys: `ns_d1_email` 1 day, `ns_third_miss_email` 6 h; keep the others sensible (N3 6 h).
- Tests: update ladder/repeat-policy/cancel-count tests; add N1 at S+3 with and without Zoom evidence, N3 timing, business-day moves, count 2 and 3 flows, nurture called once (idempotent), reply-stop, slot release, no booking link in any rendered copy.
