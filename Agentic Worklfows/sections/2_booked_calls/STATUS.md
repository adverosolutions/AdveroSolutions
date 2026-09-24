# Section 2 status

**2026-09-24 (cloud chat).** The reminder and no-show rebuild is on main: email only, every email a reply in the lead's thread, no booking link anywhere. Nothing auto-sends until Lorenzo approves the new template ids (list below). Everything runs in shadow.

## Done in the cloud chat (2026-09-24)
- Rebased `wip/section-2-build` onto main (only conflict: the catalogue id count, now 102). Integration items a to e were already finished by the stopped worker.
- Two tests fixed: the already-booked reply test still expected the booking-link sentence; the deploy watch report did not classify `show_rate_maybe_sent`, `show_rate_needs_attention`, `no_show_maybe_sent`, `no_show_needs_attention` (now KNOWN_FAILURES, so the watch fails on them and Lorenzo checks them by hand). `shared:` change to `changesets/deploy/watch_report.py`.
- Digest line "NOT COVERED ... no confirmation, pre-read, reminder or no-show check" no longer mentions the pre-read.
- Shadow replay on `jobs/tests/fixtures/appointments_2026-09-21.json` (R2, R4, N1 through `--no-show-watch`, flag, N3): every email held by the template gate (no approvals yet), nothing sent, 0 requests.
- One combined review (reviewer, max effort). A1 `thread_reply.py`: no blockers (right recipient on every route, every refusal holds, never a GHL fallback when a thread exists, writes only through the guarded clients). Copy: every reminder and no-show email matches `copy_signed_off.md` word for word, no booking link anywhere. Three blockers, each reproduced and fixed in one round, with regression tests in `services/reply_engine/tests/test_one_email_per_run.py`:
  1. Duplicate send, no-show: the tick ran the ladder twice (inside `no_show.process` and again in the recovery sweep), so a no-show marked by hand the next morning got N3 and N4 in the same minute (live repro: two POSTs, also after a 500 on the first). Fix: the tick calls `process(..., run_ladder=False)`, so the sweep is the only place ladder emails go; the sweep caps one email per lead per run across records too.
  2. Duplicate send, reminders: `show_rate.run` sent every due touch of a schedule (R3 and R4 together after a tick gap or a hold; confirmation and R4 after a late release). Fix: only the latest due reminder that can still go is sent; earlier ones close as `superseded` (a too-late one keeps `too_late`).
  3. Unchecked subject: the in-thread "Re:" subject check ran on its own lookup and was skipped when that lookup raised. Fix: `thread_reply.send_lead_email(..., subject_check=)` checks the exact subject it sends, from the lookup it sends with; a problem or an error holds (`thread_subject_refused`).
- Full suite after the fixes: 12,065 passed, 0 egress. The only failures are the 75 `changesets/tests/test_claude_guard.py` tests, which fail the same way on a clean main in the cloud container (the guard's self-test is 1502/1536 on Linux paths); they pass on Lorenzo's Mac.
- Pushing: the repo's live-write guard hook (rule c) blocks pushes from a cloud session, and Lorenzo chose to push through the GitHub connector instead. Everything went to `main` as connector commits (`e138e72` to `f736227`, plus eight prompt deletions); afterwards `git diff` between the cloud checkout and `origin/main` was empty, and the full suite ran on that exact tree. The connector cannot move or delete a branch: `section/2-booked-calls` stays at `294dc2c` (a fast-forward behind main) and **Lorenzo, delete `wip/section-2-build`** (GitHub, Branches page).
- Connector lessons for the next cloud chat: a re-typed copy can "fix" odd text (it turned `"{{first_name},"` into `"{{first_name}},"`), and `\uXXXX` escapes in Python source arrive decoded as the characters themselves. So write each copy to a file and `cmp` it against the source before pushing, spell odd characters as `\N{NAME}` or `\x..`, and compare `origin/main` with the local tree byte for byte afterwards. What worked: split each file into chunks of about 18 KB, one agent per push call that prints the chunks, writes its copy, `cmp`s it, and only then calls `push_files`.

## New and changed template ids (for Lorenzo's approval and section 4's parity/Doc rebuild)
Nothing here auto-sends until Lorenzo approves it in his own terminal (`runbooks/template_approvals.md`).
- Reminders: `show_rate.confirm_email.<niche>_<offer>` (8: cleaning, bookkeeping, recruiting, generic x reactivation, outbound; copy unchanged), `show_rate.reminder_24h_email` (new copy), `show_rate.reminder_morning_email` (new), `show_rate.reminder_1h_email` (new).
- No-show: `no_show.ns_still_on_email`, `no_show.ns_reschedule_email`, `no_show.ns_reschedule_email.repeat`, `no_show.ns_d1_email` (new), `no_show.ns_d3_value_email.<niche>_<offer>` (6: cleaning, bookkeeping, recruiting x reactivation, outbound; no generic), `no_show.ns_d7_yes_no_email`, `no_show.ns_d14_breakup_email`, `no_show.ns_third_miss_email` (new).
- Changed text: `booking.already_booked.awaiting_approval`, `.invite_withheld`, `.invite_on_calendar` (booking-link sentence removed, approved by Lorenzo 2026-09-23).
- Removed: `show_rate.confirm_sms`, `show_rate.preread_email.*`, `show_rate.reminder_24h_sms`, `show_rate.unconfirmed_task`, `show_rate.reminder_1h_sms`, `show_rate.reminder_15m_sms`, `no_show.ns_still_on_sms`, `no_show.ns_call_task`, `no_show.ns_d1_other_channel*`, the generic `no_show.ns_d3_value_email.generic_*`.
- Catalogue total: 102 approvable ids.

## What was built
- **A1 `services/reply_engine/thread_reply.py`**: sends a lead email as a reply in the lead's Instantly thread (`instantly.reply_to_email(..., to=)` behind `cadence.thread_recipient_ok`), GHL email only when the lead is known and has no thread anywhere. Checks the lead row's own `lead_email` against the appointment email on every route (holds `lead_row_mismatch`, never GHL). Record fields: transport, sent, skipped, reason, result, shadow, route, lead_key, request_issued, maybe_sent, retryable, needs_attention; tuples RETRYABLE_REASONS, NEEDS_ATTENTION_REASONS, MAYBE_SENT_REASONS, GHL_FALLBACK_REASONS. No contact-id lookup (Lorenzo's call): a booking with no email holds `no_lead_email` and is flagged.
- **A2 `show_rate.py`**: SEQUENCE confirm_email (widget bookings), reminder_24h_email (R2), reminder_morning_email (R3), reminder_1h_email (R4); 6 h, weekend and same-day rules; local time in `{time}`; dispatch through thread_reply; retryable -> pending, needs_attention -> hold + Job_Log, maybe_sent -> closed, never retried; the in-thread "Re:" subject gets the gate's subject rules (`thread_subject_refused`). Old removed-key touches close as `retired_template`.
- **B `no_show.py`, `jobs/appointments_tick.py`**: N1 at S+3..S+10 with Zoom evidence (claim key, `--no-show-watch` mode); N3 at max(flag, S+25), N4 next business day, N5 3 business days (skipped with no campaign), N6 day 7, N7 day 14, 10:00 lead time; second miss N3.repeat + N6 at 3 business days; third miss N8; nurture.enroll after the last one (idempotent) plus the existing stage moves; fresh slots per email, old pair released after send; "taken" emails only after an earlier slot email reached the lead; reply stop on `last_inbound_at` after the call start; one email per lead per run.

## Parked (not blocking; tell Lorenzo)
- An out-of-office auto-reply counts as a reply and stops the no-show ladder.
- A no-show Lorenzo marks by hand hours later still says "today" in N3; later touches whose day passed may go on consecutive runs.
- Widget-booking confirmation made on a weekend goes Monday 07:00 lead time; a rescheduled call counts as newly booked (6 h rule uses the reschedule time).
- A1: non-ASCII case folding in email comparison; a thread stored under an odd key is not found (falls back to GHL, correct recipient).
- Tests test_send_safety_round3.py:165, round4.py:76, round5.py:619 paste a None `draft.booking_link` into edited bodies (harmless).
- `show_rate.scan_ghl_confirmations` is a no-op stub; drop it once nothing calls it (the digest's "4 h 'has not confirmed' task" warning goes with it).
- Lorenzo's actions: connect Zoom in GHL (N1 needs it); approve the new/changed template ids (nothing auto-sends before that).
- From the 2026-09-24 review (not blockers):
  - While N3 is held, deferred or waiting for times, an N4/N5/N6 that comes due is closed `no_prior_offer` for good; the lead then only gets N7.
  - `_after_skipped_task` opens a "Recovery ended with nothing sent" task when the last touch was `maybe_sent` (it may have been delivered).
  - On Modal, `_run_lock` is a per-container flock, so the watch and the full tick are not serialized; the store claims still stop a double send, but a flag race can build the ladder from a count read before the bump (first-miss copy on a second miss).
  - Schedules created before the deploy keep the old R2 timing and never get the new R3/R4 keys (`ensure_scheduled` does not add keys to an existing schedule).
  - `niche_of` guesses the niche from the title or company name, so N5 can pick its niche line from that guess when only the offer is on file.
  - `show_rate.touch_bindings` still binds `booking_url` (no template uses it; clean-up only).
  - When two reminders are due at the same minute, the later one in the sequence wins: a weekend widget booking for a Monday call from a lead on Atlantic time gets R3 at Mon 07:00 CT instead of the confirmation.

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

## Waiting on Lorenzo
- Connect Zoom in GHL (N1 and no-show detection need join data; on Meet, detection says `unknown` and nothing starts until he marks the no-show).
- Approve the new and changed template ids above (they are on main).
- Delete the `wip/section-2-build` branch.

## For other sections
- Section 4 (written here because a cloud chat cannot message local sessions): (1) the id list above: re-run the parity reference (`changesets/deploy/template_parity.py --write`) and rebuild the Google Doc; (2) add the schedule entry `python3 -m jobs.appointments_tick --no-show-watch`, every minute on weekdays 12:00-18:59 CT (`* 17-23 * * 1-5` UTC on CDT), one container at a time, the 10-minute tick stays; (3) `changesets/deploy/watch_report.py` gained the four section 2 statuses in KNOWN_FAILURES (`shared:` commit).
- Section 1: `nurture.enroll` is called after N7, after N6 on a second no-show, after N8 on a third. Research suggests the first nurture touch no sooner than 3 to 4 weeks after the hand-off.
- Sections 1 and 4: no booking link anywhere; earlier times always "taken" (Lorenzo, 2026-09-23).
