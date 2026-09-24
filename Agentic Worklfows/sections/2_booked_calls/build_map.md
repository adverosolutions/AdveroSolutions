# Build map for the new reminder and no-show sequences (scout, 2026-09-23)

Paths under `Agentic Worklfows/`. Line numbers as of `e67b68c`; re-check before editing.

## Reminders (`services/reply_engine/show_rate.py`)
- `SEQUENCE` (83-92), `RELATIVE_TO_BOOKING` (93), `MAX_LATENESS` (69-78; a key with no entry never expires, so every new key needs one).
- `schedule_for` (707-778): `base = now if key in RELATIVE_TO_BOOKING else start` (734), so the booking moment is the `now` when the schedule is created. Booking-relative touches are moved into the 07:00-19:00 window for CT and the lead's zone (753-763). Skips: `stale_booking`, `past_time` (771, 773). Unconfirmed gate at schedule time (775) and at dispatch (1766-1770).
- `booked_at` on the appointment: GHL `dateAdded` (appointments_tick:146) or `cad["booked_at"]` (booking.py:1106); it does not change on a reschedule. The schedule row also has `scheduled_at` / `first_seen` (919-920).
- `ensure_scheduled` (851-931): one schedule per `showrate:<id>:<start_iso>`; a reschedule marks old pending touches `rescheduled` and clears confirmation.
- `run` (1674-1804) -> `dispatch_block_reason` (1655-1671: `appointment_started`, `too_late`) -> `refresh_copy` -> `dispatch_touch` (1539-1599), the single choke point: sender, A2P, placeholders, contact id, opt-out, template gate, then **`ghl.send_message(type="Email")` (1583); there is no Instantly path yet.** No send-window check at dispatch.
- Confirmation: `is_confirmed` (1352), `mark_confirmed` (1316), called from `app._appointment_hooks` (Instantly replies) and `scan_ghl_confirmations` (1470). What counts: `app._looks_like_confirmation` (291-298; starts with c/yes/ok/sure/sounds good/see you then/works for me..., or "confirmed" with no "?"); rejected for out-of-office, non-confirming labels, or a different time named.

## In-thread sending (decision 4)
- The "Locked in" reply path: `booking.register_booking` (1110) -> `approval.send_approved` (3183) -> `instantly.reply_to_email(email_id, eaccount, subject, body, to=recipient)` (approval 3428).
- Thread ids live on `LeadState` at `lead:<campaign_id>:<lead_email>` (models.py:585): `eaccount` (560), `thread_id` (561), `last_email_id` (562), `last_subject` (563); recipient via `cadence.recipient_for` (~1690-1705).
- The show-rate appointment dict has no thread ids (`booking.show_rate_appointment` 1071-1107; `appointments_tick.normalise_ghl_event` 121-147). Route: `campaign_id` + `email` -> `lead:` row; else the `appointment:<id>` row (as `no_show._lead_identity`, 802-818); widget bookings: scan `store.keys("lead:")` by email suffix (as `show_rate.lead_opted_out`, 599-603); several matches possible.
- Safety to reuse: `shared/instantly.py:646 reply_to_email(..., to=...)` raises without `to`; `cadence.thread_recipient_ok` (1708-1728); model on `cadence._send` (1731-1791: `missing_thread_ids` skip, only a True verdict sends live). Send window: `slots.is_send_time` (weekday + hour). `settings.guard_write` (settings.py:124).

## Template gate and catalogue (section 4 owns these files)
- `template_approvals.py`: `SHOW_RATE_LEAD_FACING` (743-744), `NO_SHOW_LEAD_FACING` (745-746), `_show_rate_entries` (778-832, iterates `show_rate.SEQUENCE`), `_no_show_entries` (835-869, iterates `no_show.FULL_SEQUENCE` + `ns_reschedule_email.repeat`). A new key must be in SEQUENCE, in the matching tuple, and handled by `render()`, or the touch is held.
- Parity: `config/template_catalogue_hashes.json` via `changesets/deploy/template_parity.py --write`; Google Doc builder `tools/template_doc/build.py` (738-770) places ids by hand. Section 4 re-runs both after we hand over the id list.

## No-show (`services/reply_engine/no_show.py`)
- `NO_SHOW_GRACE` 10 min (74); `detect` (270-308): no evidence -> `unknown` -> "mark by hand" task (971-987). Joins from `zoom_webhook` `joins:<meeting_id>` (178), `joins_for_appointment` (230), `meeting_signals` (272).
- `FULL_SEQUENCE` (108-117), `SECOND_SEQUENCE_KEYS` (118), `THIRD_SEQUENCE_KEYS` (119), `sequence_for_count` (404). Offsets from `flagged_at` (688), at least start+10. Own `MAX_LATENESS` (1341-1349).
- SOP-005: `noshow_flag:` claim, `_bump_no_show_count` (1008-1016); last touch `meta["after"]` (722-730); `_apply_after` (1541-1572) is where `nurture.enroll` goes.
- Slots: `claim_recovery_slots` (568-626) picks and holds atomically.
- Stops: `cancel_recovery_for_rebooking` (1170-1189); `cancel_recovery(..., "replied")` (1155) only from `app._appointment_hooks` (app.py:351), engine bookings only. Widget bookings and GHL replies have no reply-stop today.

## Tick timing
- Modal: `appointments_tick` every 10 min (`modal_app.py:129`); launchd `changesets/schedules/schedules.json:58-63`. Nothing acts at start+3 today; needs a finer schedule during call hours or a trigger off the Zoom webhook.

## Tests that pin today's behaviour
`services/reply_engine/tests/test_showrate_schedule.py` (order, offsets, "Reply C"), `test_showrate_no_show.py` (ladder, repeat policy, cancel counts == 7), `test_ct3_ladders.py`, `test_zc_show_rate_copy.py`, `test_template_approvals.py`, `test_template_gate*.py`, `template_fixtures.py`, `jobs/tests/test_appointments_tick.py`, `changesets/tests/test_phase0.py` (check).
