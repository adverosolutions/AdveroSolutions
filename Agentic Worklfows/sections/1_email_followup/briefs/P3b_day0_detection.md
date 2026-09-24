# Brief P3b: detect Lorenzo's own first reply as day 0 (worker-heavy, then one reviewer round)

Paths are relative to `Agentic Worklfows/`. Lorenzo's priority: a working system now, rigorous testing later: one or two focused tests per behaviour, one review round, park non-blockers.

## Hard rules
Never read `.env`, `credentials.json`, `token.json`, `~/.advero/`, `~/.modal.toml`, `.tmp/`. Never set MODE=live / ALLOW_LIVE_WRITES=1 outside monkeypatched tests. No network (mock Instantly), no paid model calls. Edit only `services/reply_engine/cadence.py`, `jobs/cadence_tick.py`, new tests, and the few lines of `runbooks/cadence_and_booking.md` about how the ladder starts. Do NOT edit `approval.py`, `app.py`, `template_gate.py`, `template_approvals.py`, `draft.py`, `shared/**`, `tools/template_doc/**` (other sections own them). Python 3.9.

## The flow (Lorenzo's decisions, 2026-09-23)
A lead replies "interested". The engine never sends a first reply: it drafts one with two held times and no booking link, and shows Lorenzo a card. Section 4's lock in `approval.py` keeps every `first_reply.*` draft from auto-sending; a lead counts as "unanswered" until a `reply_sent` or `reply_sent_manually` history event exists (`REPLY_SENT_EVENTS` / `_is_first_reply`). Lorenzo copies the draft and sends it himself from the Instantly thread. The engine must detect that send and treat its time as day 0, then arm the follow-up ladder (E1 = next business day).

## What exists (check before relying on it)
- `approval.py` `mark_sent_manually` (~6000): the card's "Mark sent" path. It sets `last_outbound_at`, appends the draft's slots to `state.offered_slots`, writes a `reply_sent_manually` history entry, arms via `_arm_under_lock` -> `_arm_cadence` -> `cadence.arm(state, now)`. Only callable from a card.
- Reading threads: `shared/instantly.py` `list_emails(email_type, campaign_id, limit, starting_after, eaccount, **extra)`, `get_email(id)`. Direction detection lives only in `jobs/pipeline_sweep.py` `is_outbound` (~237: `ue_type` 3 outbound / 2 inbound, else `from_address_email == eaccount`, else all `to_address_email_list` differ from `eaccount`) and `find_awaiting_replies` (~315, `email_type=received` vs `email_type=manual` rows per `thread_id`). Fixture: `services/reply_engine/tests/fixtures/instantly_manual_sent_2026-09.json`. API contract: `config/instantly_api_contract.md` (authoritative for filters).
- LeadState: `thread_id`, `eaccount`, `last_inbound_at`, `last_outbound_at`, `offered_slots`, `history`, `status`, `drafts`, `cadence`.
- The shared "offered_slots" registry holds the card's held times; the ladder releases this lead's earlier rows when E1 sends (P2b).
- `nurture.leave(lead_email, reason, now, store=None)` (reasons `booked`, `re_engaged`).

## Build
1. `cadence.py`: `detect_manual_first_reply(state, now, instantly, store, dry_run=False)` for a lead with no `reply_sent`/`reply_sent_manually` event, a pending first-reply draft, `thread_id` and `eaccount`, and an unarmed ladder. One read-only `list_emails` call per candidate per tick, filtered as narrowly as the contract allows; find an outbound email in the same `thread_id` sent after `last_inbound_at` (reuse `pipeline_sweep.is_outbound` if importing it has no side effects).
2. On detection (not dry run): record what `mark_sent_manually` records (`last_outbound_at` = the email's time; the draft's two held times appended to `state.offered_slots`; a `reply_sent_manually` history event of the same shape plus `"source": "thread"` and the email id), arm the ladder with day 0 = the send time (honour `approval.arm_refusal` if it applies, by calling the existing public function), and `nurture.leave(email, "re_engaged", now)` if enrolled. If retiring the pending card (so it stops being chased) needs an `approval.py` change, don't make it: list what's needed for section 4.
3. `jobs/cadence_tick.py`: include candidate rows in the per-lead loop under the same claim/lock and `save_stale_write`; add a count "N ladders started after your reply" (counts only). Instantly errors: log, count, never crash, retry next tick.
4. Shadow: GET calls are allowed (the poller already does them); only the engine's own store is written.

## Tests (mocked Instantly)
Detects an outbound in the same thread after the lead's reply (history event, `last_outbound_at`, offered slots, armed, next send = next business day after the send); ignores an outbound before the reply, one in another thread, an inbound; does nothing when `reply_sent` exists; dry run writes nothing; nurture leave for an enrolled lead; Instantly error doesn't crash; one run through `jobs/cadence_tick.run`.

## Verify
`PYTHONPATH=tools/netguard python3 -c "import netguard, pytest, sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider','services/reply_engine/tests/','jobs/tests/']))"`: all pass, `NETGUARD: 0 blocked egress attempts`, `credential-file opens refused: 0`. Then the full suite before pushing to main.
