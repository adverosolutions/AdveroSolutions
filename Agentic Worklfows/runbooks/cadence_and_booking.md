# Runbook: daily follow-up cadence and booking (Blueprint S2, S3; brief A2)

## Purpose
Once Lorenzo's first reply to a positive lead has gone out (day 0), this system keeps the thread alive every business day with fresh calendar times until the lead books, replies, or asks to stop, and books the call the moment a reply names a workable time.

| Piece | File | What it does |
|---|---|---|
| Cadence engine | `services/reply_engine/cadence.py` | `arm`, `due`, `build_touch` (D1..D7, D14, D30), `tick_lead`, fresh-slot selection, stop rules, D1 veto window, D6 invite OK |
| Touch copy | `services/reply_engine/prompts/cadence_d*.md`, `cadence_research.md` | One template per day; by default (`cadence.D2_RESEARCH_MODE = "fallback"`) the day-2 research line is the fixed fallback line, and `shared.llm` role `research` (Sonnet, faked in tests) is called only with `research_mode="llm"` |
| Booking | `services/reply_engine/booking.py` | `match_reply_to_slot`, `evaluate_reply` (verdict + counter-proposal), `book` (GHL appointment + Call Booked + Instantly status 2 + confirmation draft) |
| Hourly job | `jobs/cadence_tick.py` | Sweeps `lead:*` in the store, sends due touches (guarded), Job_Log row, one digest to Lorenzo |
| Static fallback | copy: `changesets/instantly_phase0/subsequence_interested_quiet.json`; applier: `changesets/instantly_subsequences/apply_subsequences.py` | "Interested-quiet" subsequence per campaign (lands day 1 / 3 / 7, link only) for when the service is down. The create enrols nobody: `conditions` ships with empty matchers |

The cadence (Eric's framework extended to 7 days):

| Day | Intent | Slots | Approval (and the day's template must be approved, see below) |
|---|---|---|---|
| 1 | "I lost both of those times" + two new slots + link | fresh | live: auto-send after a 30-minute veto window (ping at 09:30 CT with a Veto action: the tap opens a confirm page, and pressing Veto on it records the veto) |
| 2 | Research line about their business (the fixed fallback line by default) + two slots | fresh | auto |
| 3 | "Those times went too" + two slots + link | fresh | auto |
| 4 | Matching case study from `config/offers.md` (reactivation: roofer $6M in 6 months; outbound: $180K in 90 days) + two slots | fresh | auto |
| 5 | Free work ("I pulled 15 lost-bid candidates ..." for cleaning; bookkeeping and recruiting variants) + two slots | fresh | auto |
| 6 | Calendar hold for slot 1 (OFF by default) + second-channel note | fresh | the hold needs Lorenzo's one-tap OK **and** `CADENCE_D6_HOLD=1`; unset, day 6 sends the no-hold wording and writes nothing to the calendar |
| 7 | Yes/no close | none | auto |
| 14, 30 | Re-touch with two slots, then the lead stays in GHL Follow Up Later | fresh | auto |

Rule (2026-09-22): an engine email (first reply, counter-proposal, booking confirmation, cadence touch, show-rate or no-show message) is sent automatically only when its text is exactly a template Lorenzo approved with jobs/approve_templates.py and unchanged since, the template kill switch is off, and every send check passes (copy gate, opt-out marker, lead reply hold, 07:00-19:00 CT send window, recipient check, slot rules); anything else goes to Lorenzo as an approval card (replies) or is held (cadence, show-rate, no-show). So "auto" above means auto once the day's template (`cadence.d<day>`, `cadence.d6_noinvite`, and the spliced day 2, 4 and 5 lines) is approved (`runbooks/template_approvals.md`). A day whose template is not approved, or whose text is not an auto-sendable form of it, is **held** (`held_template`), never a card: the touch is not sent, the hold is recorded on the lead (`cadence["template_hold"]`), reported once a day in the digest and counted in the auto-send FYI. A held D1 also drops its Veto ping, so a fix opens a fresh 30-minute window rather than sending behind an old ping. In live, D1 gets the full check (exact subject and body, the lead's values bound) before its Veto window opens, so a D1 the gate would refuse sends no "sends at" ping; after a refused check the window opens again only once something the check looks at has changed (the gate's rules version and catalogue included), or after a Resume, which drops the refusal. A gate-wide hold (`kill_switch`, `parity_failed`, `registry_error`) holds every ladder, never counts toward a stall and never stops a ladder: the day goes out late once it clears. Any other hold counts once per business day toward `cadence.TEMPLATE_HOLD_STALL_DAYS` (3), whatever the reasons and in any order (a gate-wide hold in between neither counts nor resets the count), and the next such hold after 3 counted days stops the ladder as `template_unapproved`, with one high-priority push ("Cadence stopped: template <id> not auto-sendable") worded for the reason that stopped it: ids and counts on ntfy, and the lead and a signed Resume link (`/cadence/resume`, confirm page then POST) in the push itself on a protected topic, else on the email leg only; with neither, the push says what to set and no link is recorded. While it stays stopped a fresh link is sent the same way every day, and at once when the held ids pass the gate, unless the lead is done with the ladder (opted out, blocklisted, booked, hostile or not now). After Resume the next tick runs the gate and every send check again. See `runbooks/template_approvals.md`, "Cadence holds, stalls and resume". The gate runs in shadow too, so the shadow preview is the live run.

Rules enforced in code: slots 12:00-18:00 CT Mon-Fri, at least 4 h out, within 5 business days, never a slot already offered to this lead or to any lead (reservations are keyed on the slot itself in the rolling `offered_slots` registry that `approval.py` also writes; `offered:<date>` is an audit trail only); one touch per lead per day; no weekends; sends only 07:00-19:00 CT and never before 10:00; stop on booking, on any inbound reply after arming (flags `needs_fresh_draft` for A1), on unsubscribe/hostile; `negative_notnow` moves the opportunity to Follow Up Later. Copy: no em dashes, no exclamation marks, never mentions AI or automation, signed "Lorenzo", same thread and inbox (`reply_to_uuid` = the lead's last inbound email id, `eaccount` = the original sending inbox).

## How to run (shadow)
`MODE=shadow` is the default. Every send is a `would_do` record in `.tmp/shadow_log.jsonl`; no HTTP write is made to Instantly or GHL.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

# plan only: no store writes, no sends, no notifications
python3 -m jobs.cadence_tick --dry-run --bodies
python3 -m jobs.cadence_tick --dry-run --now 2026-09-22T10:05:00-05:00 --store /path/to/store.json

# shadow tick (what the hourly job does): persists cadence state, writes would_do records, sends Lorenzo a "[shadow]" digest
python3 -m jobs.cadence_tick
tail -5 .tmp/shadow_log.jsonl; tail -3 .tmp/job_log.csv

# static fallback subsequences: read-only diff against live Instantly (GET /subsequences only)
python3 changesets/instantly_subsequences/apply_subsequences.py --dry-run
```

How the ladder starts (day 0 = Lorenzo's own first reply, Lorenzo 2026-09-23): the engine never sends a first reply; it drafts one (two held times, no booking link) on a card and Lorenzo sends it himself from the Instantly thread. The hourly tick finds that send: for every unarmed lead with no `reply_sent` / `reply_sent_manually` on its history, a `thread_id` and inbox, an inbound in the last 14 days and a newest card still `pending`, `blocked`, `stale_slots` or `expired`, and no booking (a booked lead's card stays with approval.py), it makes one read-only `GET /emails` (`email_type=manual`, the inbox, the campaign; at most `cadence.FIRST_REPLY_MAX_READS` = 10 per tick, newest reply first) and looks for an email of ours in the same thread sent after `last_inbound_at` (`cadence.detect_manual_first_reply`). On a find it records what Mark sent records (`last_outbound_at` = the email's time, the card's two held times on `offered_slots`, a `reply_sent_manually` history entry with `source: "thread"` and the Instantly email id), takes the lead out of the 90-day nurture (`re_engaged`) if enrolled, and arms the ladder with day 0 = the send time, so E1 is the next business day at 10:00 CT (Friday 16:30 -> Monday). The write is under the lead row's lock and re-checks that no reply was recorded meanwhile (the card's Mark sent, or an approved send), so the ladder is armed once; `approval.arm_refusal` still applies (the lead wrote again or opted out: recorded, not armed). The digest says "N ladders started after your reply" (counts only); an Instantly error is counted, makes the Job_Log row `errors` and is retried next tick. The other ways in are unchanged: an approved engine send (`approval.send_approved`) or the card's Mark sent (`approval.mark_sent_manually`) arm it at their own time. The card itself still reads pending until it expires (approval.py does not retire it yet), so do not also tap Approve on a card whose reply you sent by hand; the ladder ignores a card whose reply is on the history (`cadence.answered_card_ids`). Booking is called from A1's reply handler when `booking.evaluate_reply(text, state.offered_slots, now, free_slots).bookable` is true: `booking.book(state, match.slot, ghl, instantly, now=now, lead_tz=match.lead_tz)` returns the confirmation `Draft`; otherwise `booking.counter_proposal_text(match, state)` is the draft. Either one is sent automatically only under the rule above (its template id is `booking.confirmation.zoom_link` or `booking.confirmation.no_zoom_link`, or a `booking.counter.*` id); otherwise it is an approval card. A counter to a time the lead asked for that only the slot rules refuse, and `booking.slot_already_taken`, are always cards.

Without a GHL token (today), free slots fall back to a 30-minute grid over the calendar's open hours (12:00-18:00 CT) and each touch is tagged `slots_source=default_grid`. In live mode the tick refuses to send default-grid times (`skipped_unverified_slots`); it only sends times read from the Discovery Call calendar.

Schedule (when live): every hour 07:00-19:00 CT on weekdays. Cron in UTC for CDT: `0 12-23 * * 1-5`; the 09:30 CT veto ping needs a half-hour run as well: `30 14 * * 1-5`.

## How to test
```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows" && python3 -m pytest services/reply_engine/tests/test_cadence_engine.py services/reply_engine/tests/test_cadence_booking.py services/reply_engine/tests/test_cadence_subsequences.py jobs/tests/test_cadence_tick.py -q
```
59 tests: day math across a weekend (arm Fri 16:00 -> D1 Mon 10:00), due/send-window/one-per-day rules, stop on inbound reply (with the fresh-draft flag), stop on status, not-now -> Follow Up Later, no double-offer of slots across two leads the same day, every day's copy is clean, D4 proof line matches the offer type, D5 per niche, D6 approval flag (shadow record + live waits for the OK), D1 live veto window then send via `httpx.MockTransport`, veto stops, a full nine-touch week in shadow with a transport that raises on any HTTP request, the real September replies for booking ("Thursday 4pm Eastern time" -> 2026-09-24T15:00 CT, "Monday at 2 CTS" -> 2026-09-28T14:00 CT, "this Wednesday around 11:30 am" -> outside window + counter-proposal Wed 12:00/12:30, "Friday. Afternoon. How's 2pm EST?" -> 2026-09-25T13:00 CT, "every day 3pm-6pm Estern time" -> earliest compliant Tue 14:00 CT), `book()` in shadow with zero HTTP and the exact GHL/Instantly payloads, `book()` live with a Zoom link (mocked), tick dry-run purity, Job_Log row, digest once per tick, and the change-set (payload shape, JSON in sync with config, dry-run reads only, apply refused in shadow, live apply backs up then creates missing only).

`conftest.py` forces `MODE=shadow`, `LLM_FAKE=1`, `NOTIFY=off` and redirects every file to a temp dir. Never run the tests with live flags.

## How to go live (checklist)
1. A1 is live and has run 48 h in shadow: the approval endpoint calls `cadence.arm()` after approval and `cadence.record_veto()` / `cadence.record_invite_decision()` from the Veto/Approve actions (the links are `approval.base_url()` + `/cadence/{veto|approve|veto-invite|resume}/<campaign_id>/<email>?t=<signed token>`, built by `cadence._decision_url`). `approval.base_url()` is the one resolver for every link the engine sends (approval cards, SLA chases, cadence links): it reads `BASE_URL` first and `REPLY_ENGINE_BASE_URL` second (an alias; `changesets/deploy/modal_secret.py` writes both from `--base-url`), and treats an unset or local-only value (localhost, 127.0.0.1, 0.0.0.0, ::1) as missing. Missing in shadow: it logs an ERROR and the links point at `http://localhost:8000`. Missing in live: it raises `ApprovalUndeliverable`, so no approval card is created and the cadence holds D1 (no veto window, no send; `cadence.links_base_url`). See `services/reply_engine/README.md`.
2. Mint the GHL Private Integration token (calendars, calendars/events, opportunities, contacts) into `Agentic Worklfows/.env`; confirm `GHL().get_free_slots(...)` returns the Discovery Call slots and that `cadence.resolve_free_slots()` reports `source=ghl`.
3. Connect Zoom to Lorenzo's GHL user and switch Discovery Call from Google Meet to Zoom (ids.json says `isZoomAdded=false`). Until then every confirmation draft carries `zoom_not_connected` as a note in its rationale (not a blocking problem) and says "the invite with the video link follows"; that no-Zoom wording is its own template (`booking.confirmation.no_zoom_link`), approved separately from the Zoom one.
4. Verify the public booking URL (`ids.json` `booking_url_note`) opens the widget; it is in every touch.
5. Run the tick in shadow for 48 h against the real store; Lorenzo reads `.tmp/shadow_log.jsonl` and the daily `[shadow]` digests and confirms every `would_do` is a touch he would have sent (times, copy, day math).
6. Confirm the ntfy topic on Lorenzo's phone receives the digest and that the Veto, Send hold and Email only actions open a confirm page on the approval endpoint. Opening the page records nothing; the decision is recorded only when the button on the page is pressed (a POST).
7. D6 hold: **decided, off by default.** GHL appointments have no "free" transparency flag, and a hold on the Discovery Call calendar would be read by `jobs/appointments_tick.py` as a booked call. The tick skips events whose title starts `HOLD: ` (`appointments_tick.is_cadence_hold` is **title-only**, on purpose: it does not filter on `appointmentStatus=new`, because the reply-booking hold below is also `new` and is a real call that the show-rate and no-show jobs must see, held). `shared.ghl.create_appointment(..., to_notify=False)` stops GHL emailing the prospect a booking notice, so turning the hold on is safe: set `CADENCE_D6_HOLD=1`. Leave it unset for the no-hold wording.
7b. **Reply-booking hold status: rehearse in GHL before the first live booking.** `booking.book()` creates the classification-time appointment with `appointmentStatus: "new"` and `toNotify: false`; `approval.send_approved` moves it to `confirmed` with `toNotify: true`. Nothing of this is verified against live GHL. With the test contact, confirm all three before any live booking, and stop if one fails:
    - a `new` appointment **blocks** its time: `GHL().get_free_slots(...)` no longer returns it (otherwise the widget or the cadence can double-book the slot);
    - `new` -> `confirmed` with `toNotify=true` **sends the invite** (otherwise an approved prospect never gets the calendar invite);
    - **no calendar-level notification or reminder fires for `new`** (Calendar settings > Notifications: the booking confirmation and every reminder must be status-conditioned, or off in favour of the show-rate workflow), and the calendar's auto-confirm does **not** flip an API-created `new` to `confirmed`.
    The GHL workflows that react to bookings trigger on the status change to Confirmed, not on Customer Booked Appointment (`changesets/ghl_workflows/show_rate_workflow.md`, `proposal_follow_up.md`).
8. Only then: run the job with `MODE=live` and `ALLOW_LIVE_WRITES=1` for a single lead (D1 first, watch the 09:30 ping, the 10:00 send in the Instantly thread, the Job_Log `live_write` row), then widen.
9. Static fallback: `apply_subsequences.py --dry-run --campaign <key>` diff approved by Lorenzo (it prints the conditions, the schedule, the day each email lands and the full text of all three emails), then `--apply --campaign <key>` with the live flags and the typed confirmation, **one campaign per run**. The key is `subsequence_schedule`, not `campaign_schedule` (`config/instantly_api_contract.md`). The create enrols nobody; afterwards open it in the Instantly UI and confirm it shows **0 enrolled leads** before applying a second campaign, then move in by hand only the positives who were offered times and went quiet (check each one's thread in the Instantly inbox; section 3 of `runbooks/PHASE1_SHADOW_REPORT.md` covers the real positives from the shadow week and what each was offered), one lead per call (`POST /leads/subsequence/move {"id", "subsequence_id"}`), and never a lead who already holds a call.
10. Pass the decision token through: `services/reply_engine/app.py`'s `/cadence/{veto|approve|veto-invite}` routes read `?t=` and verify it before anything else. A GET is only a confirm page (link scanners and chat previewers fetch URLs with GET, and a signed decision must not be recorded without a human): a token that verifies gets a page with one button that POSTs to the same path with the token, naming no lead. The POST verifies the token again and only then hands it to `record_veto` / `record_invite_decision`. A missing, forged or expired token, an unknown lead, or no `REPLY_ENGINE_SECRET` gets one neutral 403 "Not recorded" page on GET and POST alike, and nothing is written (the routes used to write a `token_ok=False` record at the same key, which the tick ignores, so a forged request after a real Veto undid it). Without the secret no decision can be recorded at all; live refuses to run without it anyway.
10b. **The D1 Veto link must actually be deliverable.** `shared/notify.py` strips action buttons from an unauthenticated ntfy topic. Its email leg now renders the formatted action URLs too (`_action_lines`), so Approve/Veto survive there; the cadence still passes the veto URL as `click=` as a second belt, and refuses to open the veto window at all (`action=veto_undeliverable`, said once) when neither leg carried it. Set `NTFY_TOKEN` (or `NOTIFY_EMAIL` + `GMAIL_SENDER_EMAIL` + `GMAIL_APP_PASSWORD`) before the first live D1, or D1 will never auto-send.
11. Expect these digest actions alongside the old ones: `send_failed`, `blocked_copy`, `blocked_copy_stalled`, `veto_undeliverable`, `already_sent`, `awaiting_fresh_draft`, `resumed_after_auto_reply`. Repeats are marked `quiet` and stay out of the digest: a copy block, a slot skip and a held veto are each reported once per lead per day, not once per hourly tick.
12. Two stalls now end the cadence instead of looking like a running ladder: `slots_unavailable` after `cadence.SKIP_STALL_DAYS` (2) consecutive days of `skipped_no_slots` / `skipped_unverified_slots`, and `blocked_copy` after `cadence.BLOCKED_COPY_STALL_DAYS` (3) days of the same copy failure. Both send one high-priority push. `recipient_mismatch` stops on the first occurrence. A third, from CT3: `template_unapproved` after `cadence.TEMPLATE_HOLD_STALL_DAYS` (3) business days of `held_template` on the same day, not counting gate-wide holds (see the rule under the cadence table); it is resumable from the signed Resume link in its push (protected topic) or email.

## Rollback
- Unset `ALLOW_LIVE_WRITES` (or `MODE=shadow`) and restart the tick: every send returns to `would_do` immediately; no code change.
- Stop one lead: `cadence.record_veto()` (a veto stops the whole cadence for that lead, not just one day), or set `cadence.stopped_reason = "paused_by_lorenzo"` on its store record. Booking writes are individually listed as `live_write` rows in `.tmp/job_log.csv` with their payloads: cancel the GHL appointment by hand, move the opportunity back, `update_interest_status` back to 1.
- Subsequences: the pre-apply backup is in `changesets/instantly_subsequences/backups/`; delete the created subsequences in the Instantly UI (the library exposes no delete endpoint on purpose).

## Thresholds
| Rule | Value | Where |
|---|---|---|
| Cadence send target | 10:00 CT, business days | `settings.CADENCE_HOUR`, `cadence.due` |
| Send window | 07:00-19:00 CT (touches never before 10:00) | `slots.within_send_window`, `cadence.due` |
| D1 veto window | 30 minutes (ping at 09:30 CT) | `cadence.VETO_WINDOW_MINUTES` |
| D6 fallback | no OK by 18:00 CT -> no-hold variant | `cadence.D6_FALLBACK_HOUR` |
| Slot rules | 12:00-18:00 CT Mon-Fri, >= 4 h out, <= 5 business days, never double-offered | `shared.slots`, `cadence.fresh_slots` |
| Touches per lead per day | 1 | `cadence.touched_today` |
| Cadence length | D1-D7 daily, D14, D30, then Follow Up Later | `cadence.DAY_SEQUENCE`, `schedule_after` |
| Booking status | Instantly interest 2 (Meeting Booked); GHL stage Call Booked | `booking.INTEREST_MEETING_BOOKED`, `settings.GHL_STAGES` |
| Positive -> booked (KPI) | green >= 50%, alert < 40% | Blueprint Section 6; measured from GHL stages |
| Copy gate on every touch | `validate_draft` (the human-approved gate) **plus** the cadence's own stricter rules | `cadence.copy_problems`, `cadence.shared_problems` |
| Consecutive blocked days before the ladder stops | `BLOCKED_COPY_STALL_DAYS` | `cadence.py` |

## The copy gate on the unattended path
D1 to D30 are the only path to a prospect with nobody reading first, so the gate on them is now the
**superset** of the two gates that exist, not a second implementation of one of them.

`cadence.copy_problems` calls `cadence.shared_problems`, which runs `draft.validate_draft` (the same
validator that gates the first reply Lorenzo approves by hand) and translates its sentences into the
cadence's short-code vocabulary. It then still runs every original cadence check on top: verbatim
money and percentage match against `config/offers.md`, leftover `{placeholder}`, and the blanket
refusal of the word "guarantee" in any touch. Two codes are new: `money_marked_to_confirm` and
`guarantee_from_another_offer` / `proof_from_another_offer`.

Two real holes closed: the cadence used to pass the `$2,500` retainer that `offers.md` marks
**TO CONFIRM**, and cleaning's `$24,000` guarantee quoted inside a bookkeeping thread. The cross-offer
half only arms when the touch knows whose offer row the lead is on, so `Touch` carries a
`campaign_key` (from `cadence.campaign_key_of`: an explicit key, else the campaign id's row in
`config/ids.json`, else a niche guess) and the two `booking.py` call sites pass it too.

**The gate fails closed.** If `services.reply_engine.draft` cannot be imported, or `validate_draft`
raises, `copy_problems` returns `copy_validator_unavailable` and the touch is blocked. A
`copy_rule:<sentence>` fallback means a rule `draft.py` grows later blocks the touch even before
anybody maps it to a short code here, so the two gates cannot drift apart silently.

**What this changes in practice:** all 54 shipped templates (6 campaigns x 9 touch days) still pass,
asserted by a test. But a hand-written or model-polished line that quotes a neighbouring offer's
number will now end the day at `blocked_copy` and push a card instead of going out. That is intended,
and it is also a new way for a ladder to stall: `BLOCKED_COPY_STALL_DAYS` stops the ladder entirely
after enough consecutive blocked days.

## Known gaps / open items
- **D6's calendar hold is not the blueprint's D6.** The blueprint asks for an invite in the prospect's calendar marked free. `_create_hold` writes a private `HOLD: ` block on Lorenzo's own calendar with `to_notify=False`; the prospect receives nothing, because a GHL appointment carries no transparency flag. `CADENCE_D6_HOLD` (off by default) turns the private block on and nothing more. The real touch needs an ICS attachment with `TRANSP:TRANSPARENT` sent from the Instantly reply: a design change, recorded as out of scope for Phase 1 in `runbooks/PHASE1_SHADOW_REPORT.md` section 9. The dependency the old comment was waiting on (appointments_tick filtering holds out of the appointment list) shipped: `is_cadence_hold` matches the title prefix.
- **A booking made from a reply is held until the approval.** `booking.register_booking` writes `showrate_hold:<appt_id>` before arming the show-rate ladder, so no S4 touch and no no-show chase can reach a prospect before Lorenzo's approved reply goes out. `approval.send_approved` releases it; `approval.cancel_booking` tears it down. The GHL appointment itself is created `new` (not GHL's default `confirmed`) so no status-triggered GHL workflow or reminder fires before the approval (checklist 7b). A store error while reading that marker counts as held: the schedule keeps its `held` flag and nothing is sent from it that tick (`show_rate.read_hold`; `no_show._show_rate_held` answers held too). No-show recovery times are claimed through `approval.claim_slots`, all or nothing; a conflict re-picks from the same free-slot list and falls back to link-only copy. Tests: `services/reply_engine/tests/test_hold_status_and_hold_checks.py`. See `runbooks/show_rate_and_no_show.md`.
- **"next <weekday>" is never auto-booked** (past the 5-business-day horizon), so the lead is counter-proposed and waits for the "Book as asked" button. DECISIONS F4; pinned by tests on both sides.
- GHL free-slots response shape is handled for both `{date: {slots: [...]}}` and `{_dates_: {...}}`; verify with the first token-backed call.
- Lead phone numbers are not on `LeadState`; the D6 second-channel note only names a number when `phone` is present on the state (A1 could copy it from the extracted classification).
- `research_line` uses company + niche only until the list factory (A6) adds `website` / scraped facts to the state; the fake path returns a deterministic line.
- `LeadState` has no `reply_from` field yet (A1 owns `models.py`). The cadence keeps its own copy on `state.cadence['reply_from']` and `recipient_for()` prefers it, so a lead who replied from a shared or assistant mailbox is answered at the address that wrote. Until A1 persists `ReplyEvent.reply_to_address` onto the state, that copy has to be seeded when the cadence is armed.
- `services/reply_engine/app.py` calls `booking.evaluate_reply(...)` with no `subject=`, so booking's auto-responder guard runs on the body alone. It now does (signature and office-hours blocks are stripped before an availability window is parsed, and automated acknowledgements are recognised), but passing the subject through is still the stronger fix.
- An unconfirmed send marker from an EARLIER day is retried rather than escalated: a day-old POST that never got an answer is more likely lost than delivered. Same-day it is held and the digest says "confirm by hand in the Instantly inbox".
- Subsequence `conditions` is sent with empty matchers so the create enrols nobody. Whether Instantly reads an empty `crm_status` as "nobody" or as "everybody" is **not** verified against a live create: confirm 0 enrolled leads in the UI immediately after the first one.
