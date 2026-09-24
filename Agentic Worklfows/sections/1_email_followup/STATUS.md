# Section 1 status

## Done
- **2026-09-23 (split day):** sequence E1 to E10 drafted and edited (`sequence_final.md`), shown to Lorenzo in chat.
- **2026-09-23: `nurture.enroll` landed** (reviewed, APPROVE). `services/reply_engine/nurture.py`: `enroll(lead_email, reason, now, store=None, campaign_id=None, note=None)`, `get`, `is_enrolled`, `nurture_key`; reasons `no_reply_after_sequence`, `not_now_reply`, `no_show_no_rebook`. Own store key `nurture:<email>` (no LeadState change), idempotent, sends nothing. The cadence stops an enrolled lead with reason `nurture` before anything can send, and `resume()` refuses while enrolled. Runbook `runbooks/nurture.md`, tests `services/reply_engine/tests/test_nurture.py` (34). **Section 2 can call `nurture.enroll(lead_email, "no_show_no_rebook", now)` now.** Nothing calls it yet.

## In progress: walking Lorenzo through the sequence
- **E1:** Lorenzo already edited it in the one Google Doc (as `cadence.d1`, export 2026-09-23T18:15Z, via section 4): "The time slots from yesterday got filled. Here are 2 more, let me know if they work: {slots}." with no booking link. Asked him: (1) "from yesterday" is false when E1 lands Monday after a Friday reply; swap to "I sent" or send E1 the next calendar day; (2) does the booking link come out of all ten emails or only E1?
- **E2:** also edited in the doc (`cadence.d2`): body is `{research_line}` then "Fifteen minutes is enough for me to show you how this would run for {company}. Think this would really benefit {company name} let me know when a good time is to get a call on the books." No {slots}, no link. His note: the research line must tie back into the offer; the email is essentially "here's why I think this call is important". `{company name}` is not a real placeholder and a space is missing after "{company}."; confirm wording with him. The research-line rules in `sequence_final.md` assume it follows "I think this call will be really valuable for you."; they change if the line opens the email.
- He deleted both no-slots variants (`cadence.d1/no_slots`, `cadence.d2/no_slots`); they live in `cadence.py` `NO_SLOTS_BODIES` (~line 1303), not the prompt files. Fold into the engine rewrite.

## Next
1. Finish E1 with Lorenzo, then E2 (his doc edits above) and on through E10; write his edits into `sequence_final.md`, push after each sitting.
2. Section 4 handoff items for `cadence.py` (section 4 will not edit it):
   a. Pushes on a public ntfy topic still show the lead's company (`company_of(state)` at ~2172, 2839, 2878, 2938, 2984, 2997 on e67b68c). Follow `_resume_push` (~2371-2391): ids only unless `notify.topic_is_protected()`. Tests: company absent on public topic, present on protected.
   b. `_template_stop_reminder` (~2509-2559) pushes daily with no cap. Add a count/day cap on the hold record, then silence. Also skip it for a lead enrolled in nurture (reviewer gap c).
3. Engine rewrite after Lorenzo signs off the sequence (see README next steps 3).
4. Nurture follow-ups: wire the callers (end of ladder, "not now" reply), a way to leave nurture when a nurtured lead books or replies with interest (reviewer: must be settled before the `not_now_reply` caller lands, since approval re-arms the ladder via `arm()` and the next tick stops it again), then the 90-day content plan for Lorenzo.

## Parked (reviewer optional, not safety)
- `nurture.py` events grow if two callers alternate reasons A, B, A, B (no planned caller does).
- `ends_at` in the spring-forward hour stores a non-existent wall time with a valid offset (cosmetic).
- Race: a lead enrolled between the tick's check and the send still gets that send; `changed_in_store` does not read the nurture key. Every planned caller is covered by the existing pre-send re-read.
- `resume_after_recipient_hold` reports `resumed: True` once for an enrolled lead (the next tick stops it before sending).

## Waiting on Lorenzo
- The two E1 questions above, then E2 wording.
- The five open questions in `README.md` (wholesaler number, E2 approval model, "not now" goes to nurture, dropping E5, whether the engine still drafts a first reply for him).
