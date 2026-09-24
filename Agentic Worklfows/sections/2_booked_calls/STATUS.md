# Section 2 status

**2026-09-24 (handoff to a cloud chat; Lorenzo ran out of local usage).** Copy is signed off. Piece C (booking replies without the booking link) is on main (294dc2c + 2c8d34f). Everything else is built but NOT reviewed and NOT on main: it lives on the GitHub branch **`wip/section-2-build`** (one WIP commit on top of the pre-rebase section branch).

## Resume here (cloud chat)
1. Check out `wip/section-2-build`, make a working branch from it, and rebase it onto `origin/main`. Expect conflicts or test fallout from: section 4's unanswered-lead lock (62dbac4, 8e48570: an engine reply auto-sends only after a `reply_sent`/`reply_sent_manually` history event on the lead row; seed that event in any of our tests that expect a counter to auto-send), section 1 deleting `draft.BOOKING_LINE`, and section 4's `tools/template_doc` changes. Keep main's version for files we do not own unless our change is listed below.
2. Finish the integration (a worker was stopped part-way; check each item, some may be done already):
   a. `services/reply_engine/template_approvals.py`, `_no_show_entries`, in the `for niche, offer in NICHE_COMBOS:` loop: `if key == "ns_d3_value_email" and niche not in show_rate.NICHES: continue` (no generic N5).
   b. `tests/test_template_approvals.py`: in `FALLBACK_EDITS` replace the two stale no_show cases with `("no_show", "I'm on the call now, no rush. The link is on your calendar invite.", "I'm on the call now. The link is in the invite.", "no_show.ns_still_on_email", ())` and `("no_show", "Today didn't line up, and no problem if now is a bad time.", "Today didn't work out, and no problem if now is a bad time.", "no_show.ns_reschedule_email.repeat", ())`; in `test_catalogue_hashes_do_not_depend_on_the_environment` delete the `monkeypatch.setattr(ns_mod, "BOOKING_URL", ...)` line.
   c. Already-booked reply (Lorenzo approved in full, 2026-09-23): in `app.py` `_already_booked_body` drop the booking-link sentence entirely (each variant ends at its first sentence, e.g. "We are already set for Thu, Oct 1 at 2:00pm CT and the invite is on your calendar."); `_already_booked_bindings` without `booking_url`; build/validate that draft with `booking_link=None` (like 2c8d34f); drop the catalogue's now-identical `no_booking_link` variant. The stopped worker had started this (app.py is modified).
   d. `tools/template_doc/route_doc.py` (section 4's): minimal change so removed ids (show_rate.preread_email.*, confirm_sms, reminder_*_sms, unconfirmed_task, ns_still_on_sms, ns_call_task, ns_d1_other_channel*) are not routed; `tools/template_doc/tests/test_route_doc.py` must pass. The stopped worker had started this.
   e. `runbooks/show_rate_and_no_show.md`: rewrite briefly for the new system (email only; R2/R3/R4 timing and skip rules; N1 at S+3 needing Zoom join data and the `--no-show-watch` schedule; N3-N8 timing; repeat rules; nurture hand-off; reply stop; in-thread sending with GHL fallback only when no thread; outcomes would_do/sent/deferred/needs_attention/maybe_sent = check by hand, never retried; Lorenzo approves the new template ids before anything auto-sends). The stopped worker had started this.
3. Full suite green (command in `../README.md`; 0 failed, 0 egress).
4. ONE combined review (reviewer-max once, because it wires lead-facing sends): A1 `thread_reply.py` (reviewed twice; last round's only blocker was the contact-id route, now removed, plus small fixes), A2 `show_rate.py`, B `no_show.py` + `jobs/appointments_tick.py`, and the integration changes. Specs: `build_briefs.md`, copy `copy_signed_off.md`. Lorenzo's rule: lean, a fix round only for a real blocker (wrong recipient, unapproved text to a lead, duplicate send, live write); park everything else here.
5. Commit by path: `shared:` template_approvals.py; `shared:` app.py (already-booked); `shared:` tools/template_doc; then the section 2 commit (thread_reply.py + tests, show_rate.py, no_show.py, appointments_tick.py, deleted `prompts/show_rate_preread_*.md`, tests, runbook, this STATUS). Root check, push `section/2-booked-calls`, full suite, push to main (README rule 3). Delete the `wip/section-2-build` branch after it is on main.
6. Tell section 4 (a cloud chat cannot message local sessions; write it into this file's "For other sections" if messaging fails): the new template id list (from the catalogue), the Doc/parity rebuild, and the schedule entry `python3 -m jobs.appointments_tick --no-show-watch`, every minute weekdays 12:00-18:59 CT (`* 17-23 * * 1-5` UTC on CDT), one container.
7. Report to Lorenzo in plain words, with the parked list below. He wants the full message text in any approval question.

## What was built (unreviewed parts)
- **A1 `services/reply_engine/thread_reply.py`**: sends a lead email as a reply in the lead's Instantly thread (`instantly.reply_to_email(..., to=)` behind `cadence.thread_recipient_ok`), GHL email only when the lead is known and has no thread anywhere. Checks the lead row's own `lead_email` against the appointment email on every route (holds `lead_row_mismatch`, never GHL). Record fields: transport, sent, skipped, reason, result, shadow, route, lead_key, request_issued, maybe_sent, retryable, needs_attention; tuples RETRYABLE_REASONS, NEEDS_ATTENTION_REASONS, MAYBE_SENT_REASONS, GHL_FALLBACK_REASONS. No contact-id lookup (Lorenzo's call): a booking with no email holds `no_lead_email` and is flagged.
- **A2 `show_rate.py`**: SEQUENCE confirm_email (widget bookings), reminder_24h_email (R2), reminder_morning_email (R3), reminder_1h_email (R4); 6 h, weekend and same-day rules; local time in `{time}`; dispatch through thread_reply; retryable -> pending, needs_attention -> hold + Job_Log, maybe_sent -> closed, never retried; the in-thread "Re:" subject gets the gate's subject rules (`thread_subject_refused`). Old removed-key touches close as `retired_template`.
- **B `no_show.py`, `jobs/appointments_tick.py`**: N1 at S+3..S+10 with Zoom evidence (claim key, `--no-show-watch` mode); N3 at max(flag, S+25), N4 next business day, N5 3 business days (skipped with no campaign), N6 day 7, N7 day 14, 10:00 lead time; second miss N3.repeat + N6 at 3 business days; third miss N8; nurture.enroll after the last one (idempotent) plus the existing stage moves; fresh slots per email, old pair released after send; "taken" emails only after an earlier slot email reached the lead; reply stop on `last_inbound_at` after the call start; one email per lead per run.

## Parked (not blocking; tell Lorenzo)
- An out-of-office auto-reply counts as a reply and stops the no-show ladder.
- A no-show Lorenzo marks by hand hours later still says "today" in N3; later touches whose day passed may go on consecutive runs.
- Widget-booking confirmation made on a weekend goes Monday 07:00 lead time; a rescheduled call counts as newly booked (6 h rule uses the reschedule time).
- A1: non-ASCII case folding in email comparison; a thread stored under an odd key is not found (falls back to GHL, correct recipient).
- Tests test_send_safety_round3.py:165, round4.py:76, round5.py:619 paste a None `draft.booking_link` into edited bodies (harmless).
- `show_rate.scan_ghl_confirmations` is a no-op stub; drop it once nothing calls it.
- Lorenzo's actions: connect Zoom in GHL (N1 needs it); approve the new/changed template ids (nothing auto-sends before that).

## Lorenzo's rules from this walkthrough (apply everywhere)
- **Email only.** No texts, no phone calls, no call tasks in either sequence. Every lead has an email; phone is hit or miss. SMS legs and call/voicemail tasks come out of the code (not "off until A2P").
- **Never a booking link.** The lead picks one of the two times offered, then Lorenzo sends the calendar invite. Applies to every section (Lorenzo, 2026-09-23: "Everywhere"; relayed to sections 1 and 4).
- **Earlier times are always "taken".** Any email that offers new times after an earlier email offered times the lead did not book says those times got taken, every time, in varied wording.
- **No Claudeisms**; normal capitalization (subjects too).
- Show the full message inside every approval question.

## Decisions (2026-09-23)
- Reminders: "Locked in" confirmation unchanged; **no pre-read** (R1 dropped, `prompts/show_rate_preread_*.md` go); R2 at -24 h (skip it and send R3 when the booking came less than 6 h before R2's time); R3 at 08:30 lead time on the call day when R2 was skipped, never same-day; R4 at -1 h to everyone; **no 4 h personal call** (R5 dropped).
- Time-only lines show the lead's local time in brackets when not CT: "2:00pm CT (3:00pm ET)".
- Zoom: Lorenzo connects it in GHL (his action). Without it, `no_show.detect` returns `unknown` on Meet and nothing starts until he marks the no-show.
- All reminder and no-show emails go as replies in the lead's cold-email thread, same inbox; GHL email only when no thread exists.
- No-show cadence: N1 at S+3 (not joined, needs Zoom); N3 at about S+25; N4 next business day; N5 day 3-4; N6 day 7; N7 day 14, then `nurture.enroll(lead_email, "no_show_no_rebook", now)`. Second no-show: N1, N3 second variant, N6 on day 3-4, then nurture. Third: N1, then N8, then nurture. Any reply stops the ladder. N2 (Lorenzo's call) dropped. Two times per email.

## Copy status
Every reminder (R2, R3, R4) and no-show message (N1, N3 and its second-miss variant, N4 to N8) was shown to Lorenzo in full and approved on 2026-09-23. Texts: `copy_signed_off.md`. Dropped: R1 pre-read, R5 personal call, N2 call/voicemail, every SMS.

## Build plan (after copy sign-off; worker-heavy + reviewer)
Map: `build_map.md`. In order:
1. `show_rate.py`: new SEQUENCE (R2, R3, R4 only; drop confirm_sms, preread, 24 h SMS, unconfirmed task, 1 h and 15 m SMS), the 6 h skip rule, R3 at 08:30 lead time, `MAX_LATENESS` for new keys, local time in `{time}`, new copy, send window at dispatch.
2. In-thread sending: resolve the lead's `lead:` row (campaign id, appointment row, or email scan), send with `instantly.reply_to_email(..., to=)` behind `cadence.thread_recipient_ok`, GHL email fallback when no thread.
3. `no_show.py`: new ladder and keys, N1 at S+3 off Zoom join data (needs a per-minute check in call hours or a webhook trigger), repeat rules, reply-stop for all bookings, `nurture.enroll` (on main, 41e50d9), slots with "taken" copy, no booking link anywhere.
4. `booking.py`: drop the booking-link line (`draft.BOOKING_LINE`, section 1's constant) from the 8 counter-proposal replies (booking.counter.window_no_fit, outside_window_early, outside_window_late, weekend, too_soon, beyond_horizon, slot_taken, booking.slot_already_taken); then tell section 1 we no longer import it so it can delete the constant. Show Lorenzo the changed replies.
5. `shared:` commit: register new template keys in `template_approvals.py` tuples; hand section 4 the id list for parity and the Google Doc.
6. Tests, runbook `runbooks/show_rate_and_no_show.md`, Job_Log rows, shadow replay.

## Waiting on Lorenzo
- Connect Zoom in GHL.
- Approve the new and changed template ids once they are on main.

## For other sections
- Section 1: `nurture.enroll` is called after N7, after N6 on a second no-show, after N8 on a third. Research suggests the first nurture touch no sooner than 3 to 4 weeks after the hand-off.
- Sections 1 and 4: no booking link anywhere; earlier times always "taken" (Lorenzo, 2026-09-23).
