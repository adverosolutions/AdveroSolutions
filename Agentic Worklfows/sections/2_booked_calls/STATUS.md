# Section 2 status

**2026-09-23 (evening):** research done for both sequences; Lorenzo picked both cadences; reminder copy signed off (`reminders_final.md`, with one rework pending, see below); no-show copy walkthrough in progress (N1, N3, N4 done). No engine code changed yet. Nothing approved in the template registry or live.

## Resume here (next chat)
1. Rework the reminder outs for the no-link rule and show Lorenzo each one: R2 "If the time doesn't work anymore, just reply and I'll send a couple of other times." R3 "If something came up, just reply and we'll find another time." (R4 already has no link.)
2. Continue the no-show walkthrough with the reworked texts (below): N3 second-no-show variant (now two times, no link), N5, N6, N7, N8. One message per question, **the full rendered message inside the question** (Lorenzo's rule).
3. Then the build (see "Build plan").

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
Signed off: R2, R3, R4 (texts in `reminders_final.md`; their "grab a new slot here: {booking_url}" outs must still be reworked per the no-link rule, item 1 above).

No-show (`no_show_final.md` has the editor's set; these overrides win):
- N1 (approved): "Hey {first_name},\n\nI'm on the call now, no rush. Here's the link:\n{call_link}\n\nIf now doesn't work anymore, just reply and we'll find another time.\n\nLorenzo" (no-link: "I'm on the call now, no rush. The link is on your calendar invite.")
- N3 (approved opener; link removed per the new rule, show again): "Hey {first_name},\n\nLooks like I missed you on our call today.\n\nCould we do {slots}? Just reply with the one that works.\n\nLorenzo". Lorenzo: never "All good" after the miss ("It's not all good").
- N3 second-no-show variant: Lorenzo approved the link-only text, but the no-link rule overrides it. Proposed: "Hey {first_name},\n\nToday didn't line up, and no problem if now is a bad time.\n\nIf you still want to talk, I can do {slots}. Just reply with the one that works.\n\nLorenzo" (show him).
- N4 (approved): "Hey {first_name},\n\nThose two times got taken, but I can do {slots} if you still want to find 15 minutes. Just reply with the one that works.\n\nLorenzo"
- N5, N6, N7 need the no-link and "taken" rework before showing; N8 has no link already. Proposals: N5 ask "If that's worth 15 minutes, the times I sent got taken, but I've got {slots} open. Just say which one works."; N6 "...If it's later, just tell me roughly when. If you still want to chat, the last two times got taken, but I can do {slots}."; N7 "I'll leave this with you for now. If the timing gets better later on, just reply here and I'll send over a couple of times."
- Subjects (no-thread fallback only) capitalized.

## Build plan (after copy sign-off; worker-heavy + reviewer)
Map: `build_map.md`. In order:
1. `show_rate.py`: new SEQUENCE (R2, R3, R4 only; drop confirm_sms, preread, 24 h SMS, unconfirmed task, 1 h and 15 m SMS), the 6 h skip rule, R3 at 08:30 lead time, `MAX_LATENESS` for new keys, local time in `{time}`, new copy, send window at dispatch.
2. In-thread sending: resolve the lead's `lead:` row (campaign id, appointment row, or email scan), send with `instantly.reply_to_email(..., to=)` behind `cadence.thread_recipient_ok`, GHL email fallback when no thread.
3. `no_show.py`: new ladder and keys, N1 at S+3 off Zoom join data (needs a per-minute check in call hours or a webhook trigger), repeat rules, reply-stop for all bookings, `nurture.enroll` (on main, 41e50d9), slots with "taken" copy, no booking link anywhere.
4. `shared:` commit: register new template keys in `template_approvals.py` tuples; hand section 4 the id list for parity and the Google Doc.
5. Tests, runbook `runbooks/show_rate_and_no_show.md`, Job_Log rows, shadow replay.

## Waiting on Lorenzo
- Connect Zoom in GHL.
- The remaining copy sign-offs above.

## For other sections
- Section 1: `nurture.enroll` is called after N7, after N6 on a second no-show, after N8 on a third. Research suggests the first nurture touch no sooner than 3 to 4 weeks after the hand-off.
- Sections 1 and 4: no booking link anywhere; earlier times always "taken" (Lorenzo, 2026-09-23).
