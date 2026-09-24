# Section 1 status

## Done
- **2026-09-23 (split day):** sequence E1 to E10 drafted and edited (`sequence_final.md`), shown to Lorenzo in chat.
- **2026-09-23: `nurture.enroll` landed** (reviewed, APPROVE). `services/reply_engine/nurture.py`: `enroll(lead_email, reason, now, store=None, campaign_id=None, note=None)`, `get`, `is_enrolled`, `nurture_key`; reasons `no_reply_after_sequence`, `not_now_reply`, `no_show_no_rebook`. Own store key `nurture:<email>` (no LeadState change), idempotent, sends nothing. The cadence stops an enrolled lead with reason `nurture` before anything can send, and `resume()` refuses while enrolled. Runbook `runbooks/nurture.md`, tests `services/reply_engine/tests/test_nurture.py` (34). **Section 2 can call `nurture.enroll(lead_email, "no_show_no_rebook", now)` now.** Nothing calls it yet.
- **2026-09-23: section 4 handoff items in `cadence.py` landed** (both reviewed, APPROVE):
  - Push privacy: new `_lead_push(state, public)`; seven pushes (D1 held, both D1 Veto pushes, slots_unavailable stop, D6 no-BASE_URL, D6 calendar-hold card, blocked copy) name no lead on a public ntfy topic; the lead line goes on the email leg only. Tests `test_cadence_push_privacy.py` (14); two title expectations in `test_send_safety_round4.py` updated.
  - Resume reminder cap: `TEMPLATE_STOP_REMINDER_MAX_PUSHES = 8`, `_MAX_DAYS = 14` (count in `cadence.template_hold.link_count`); the one-time "ready to resume" push bypasses the cap; no reminder for a nurtured lead. The hold itself stays. Tests `test_cadence_stop_reminder_cap.py` (13).

## In progress: walking Lorenzo through the sequence
- **E1:** Lorenzo already edited it in the one Google Doc (as `cadence.d1`, export 2026-09-23T18:15Z, via section 4): "The time slots from yesterday got filled. Here are 2 more, let me know if they work: {slots}." with no booking link. Asked him: (1) "from yesterday" is false when E1 lands Monday after a Friday reply; swap to "I sent" or send E1 the next calendar day; (2) does the booking link come out of all ten emails or only E1?
- **E2:** also edited in the doc (`cadence.d2`): body is `{research_line}` then "Fifteen minutes is enough for me to show you how this would run for {company}. Think this would really benefit {company name} let me know when a good time is to get a call on the books." No {slots}, no link. His note: the research line must tie back into the offer; the email is essentially "here's why I think this call is important". `{company name}` is not a real placeholder and a space is missing after "{company}."; confirm wording with him. The research-line rules in `sequence_final.md` assume it follows "I think this call will be really valuable for you."; they change if the line opens the email.
- He deleted both no-slots variants (`cadence.d1/no_slots`, `cadence.d2/no_slots`); they live in `cadence.py` `NO_SLOTS_BODIES` (~line 1303), not the prompt files. Fold into the engine rewrite.

## Next
1. Finish E1 with Lorenzo, then E2 (his doc edits above) and on through E10; write his edits into `sequence_final.md`, push after each sitting.
2. Engine rewrite after Lorenzo signs off the sequence (see README next steps 3).
3. Nurture follow-ups: wire the callers (end of ladder, "not now" reply), a way to leave nurture when a nurtured lead books or replies with interest (reviewer: must be settled before the `not_now_reply` caller lands, since approval re-arms the ladder via `arm()` and the next tick stops it again), then the 90-day content plan for Lorenzo.

## Parked (reviewer optional, not safety)
- Reminder cap: `runbooks/reply_engine_alerts.md` (~971-977, section 4's) still says a fresh Resume link comes "every morning"; the push texts at `cadence.py` ~2414 and ~3510 say "every morning" too. After the cap a held ladder shows up nowhere (no push, `already_stopped` is not in the digest). A failed save after a reminder can resend it once (the 14-day cap still bounds it). A row without `stopped_at` gets only the 8-push limit.
- Push privacy: four public-topic pushes lost their "(details in the email)" pointer; with email off, a public push names no lead at all (same as `_resume_push`); `reply_engine_alerts.md:190` heading still shows `{lead}`; the `topic_is_protected()`-raises fallback is untested; blocked-copy pushes still list `touch.problems` text.
- `nurture.py` events grow if two callers alternate reasons A, B, A, B (no planned caller does).
- `ends_at` in the spring-forward hour stores a non-existent wall time with a valid offset (cosmetic).
- Race: a lead enrolled between the tick's check and the send still gets that send; `changed_in_store` does not read the nurture key. Every planned caller is covered by the existing pre-send re-read.
- `resume_after_recipient_hold` reports `resumed: True` once for an enrolled lead (the next tick stops it before sending).

## Waiting on Lorenzo
- The two E1 questions above, then E2 wording. Booking link question is now three-way (section 4): the sentence he deleted from Day 1 is also draft.py's `BOOKING_LINE`, in 110 other emails (every first reply, 8 booking replies of section 2's). (a) Day 1 only, (b) E1 to E10, (c) every email (draft.py change, tell section 2).
- No-Claudeisms rule (2026-09-23) flags to raise per email: E2 "Think this would really benefit {company}"; E6 outbound "Each one is a ... reason ..." lines; E7 "Either answer is totally fine."; E9 "which is the right moment ..." clauses. The E2 research-line prompt must carry the rule in plain words.
- The five open questions in `README.md` (wholesaler number, E2 approval model, "not now" goes to nurture, dropping E5, whether the engine still drafts a first reply for him).
