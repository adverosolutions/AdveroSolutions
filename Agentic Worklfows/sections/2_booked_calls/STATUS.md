# Section 2 status

**2026-09-23 (evening):** research done for both sequences; Lorenzo picked both cadences; reminder copy signed off (`reminders_final.md`, with one rework pending, see below); no-show copy walkthrough in progress (N1, N3, N4 done). No engine code changed yet. Nothing approved in the template registry or live.

## Resume here (next chat)
All copy is signed off: **`copy_signed_off.md` is the source of truth** (supersedes `reminders_final.md` and `no_show_final.md`). Build briefs: `build_briefs.md`.

**Build progress (2026-09-23 night).** Unreviewed work in progress is snapshotted to the GitHub branch `wip/section-2-build` (not the section branch). If this chat died, check that branch out into a worktree, diff it against `section/2-booked-calls`, and continue the review loop below.
- Wave 1, piece C (booking replies without the booking link): **approved on re-review and committed** (a `shared:` commit for 3 lines in section 4's app.py, then booking.py + tests). The 8 counter replies lost the "Or if it's easier, grab a time here" line; the no-open-slots case now asks "Could you send me a couple of times that work for you next week?" (Lorenzo approved it in full); counter, slot-taken and "Locked in" confirmation drafts no longer store a booking link, so editing them never demands one (a behaviour change on the confirmation card; its text is unchanged). Lorenzo must re-approve the counter/slot-taken templates (text changed). Parked polish: tests test_send_safety_round3.py:165, round4.py:76, round5.py:619 paste a now-None `draft.booking_link` into edited bodies (harmless "None" in test text). Section 4 follow-up: `booking.already_booked.*` replies (app.py:424) and first replies still carry a booking link.
- Wave 1, piece A1 (`thread_reply.py`): built; reviewer-max REJECTED (row not checked against the appointment email, so a mis-keyed row could email another person; possibly-sent failures looked retryable, so duplicates were possible; plus 6 smaller items). Being fixed by worker-heavy; then back to reviewer-max.
- Wave 2 (A2 reminders, B no-show ladder) starts after A1 is approved. Note for A2 from the A1 review: the subject actually sent in-thread is `cadence.subject_for(state)`, not the touch subject the gate checks; A2 must gate the subject actually sent or accept it explicitly. A2/B must not auto-retry A1's "maybe sent" reasons.
- After C lands on main: tell section 1 that booking.py no longer imports `draft.BOOKING_LINE`.

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
- The remaining copy sign-offs above.

## For other sections
- Section 1: `nurture.enroll` is called after N7, after N6 on a second no-show, after N8 on a third. Research suggests the first nurture touch no sooner than 3 to 4 weeks after the hand-off.
- Sections 1 and 4: no booking link anywhere; earlier times always "taken" (Lorenzo, 2026-09-23).
