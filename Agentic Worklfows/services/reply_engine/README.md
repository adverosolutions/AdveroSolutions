# services/reply_engine — core (Blueprint S1, brief A1)

Classify every inbound reply, route it into GHL and Instantly, draft the answer,
and put that draft in front of Lorenzo. **Nothing is ever sent without his tap.**

The cadence (S2), booking (S3), show-rate (S4), no-show (S5) and pipeline
(S8) modules live beside this one and are documented in `runbooks/`. This file
covers the core: `models`, `classify`, `draft`, `router`, `approval`, `app`,
`poller`, `replay`.

## The pipeline

```
ReplyEvent ──► classify ──► route ──► draft ──► approval card on Lorenzo's phone
  (webhook /                 (GHL +    (offers.md      │
   poller /                  Instantly, copy + slots)   ├─ Approve  → Instantly reply, cadence armed
   replay)                   guarded)                   ├─ Book <time> as asked (when they asked for one)
                                                        ├─ Edit     → validated, then sent
                                                        └─ Veto     → nothing sent, slots released
```

`app.process_event(event)` is the single entrypoint for all three sources. It is
idempotent per `email_id` and persists one `LeadState` per lead under
**`lead:<campaign_id>:<email>`** — the key `jobs/cadence_tick.py` and
`jobs/pipeline_sweep.py` read.

## Modules

| Module | What it owns |
|---|---|
| `models.py` | `ReplyEvent` (webhook + `GET /emails` shapes), `Classification`/`Extracted`, `Draft`, `Action`, `Approval`, `LeadState`, the label taxonomy and the label → Instantly interest / GHL stage maps |
| `classify.py` | Four documented regex rules first (auto-reply, hostile, removal, short no), the `classify` model role for the rest, and the `escalate` role when that answer is under 0.8 confidence (both Claude Opus 5.5). The model only ever sees the lead's own words: `strip_quoted` + `core_text` remove the quoted cold email and the signature |
| `draft.py` | Answer → two afternoon slots → booking link → "Lorenzo", built from `config/offers.md`. `validate_draft` is the gate: no em dash, no exclamation mark, no mention of AI or automation, no dollar figure that is not in offers.md, no figure offers.md marks **TO CONFIRM**, must end with the signature, must carry the booking link |
| `router.py` | Guarded GHL contact/opportunity/note/task + Instantly interest status and blocklist, per label |
| `approval.py` | HMAC-signed approval tokens (48 h), the ntfy card, the slot reservation registry, `approve` / `veto` / `edit` / `accept_requested`, the out-of-hours queue and `flush_queued` |
| `app.py` | FastAPI service and `process_event`; the Instantly webhook, the approval endpoints, the cadence decision endpoints, the secret-gated `/state` |
| `poller.py` | The shadow transport: `GET /emails?email_type=received` instead of webhooks (none exist yet), cursor + seen-id dedupe |
| `replay.py` | Replays a recorded fixture through the whole pipeline in shadow and prints the summary |

## Endpoints

| Route | Purpose |
|---|---|
| `POST /webhooks/instantly` | Reply events; `X-Advero-Secret` is **mandatory** and is checked against `WEBHOOK_SECRET` **or**, when that is unset, `REPLY_ENGINE_SECRET` - which is the name the change-set, the runbook and `modal_app.SECRET_KEYS` actually set, so the two no longer disagree. The `?secret=` query form is accepted only when `MODE != live` (a secret in a query string lands in proxy logs and in the Referer). A payload whose `campaign_id` is missing or not in `ids.json` is ignored |
| `GET /approve/{token}` | Confirmation page only: renders the draft with a POST button. A GET can be fired by a link scanner or a prefetch, so it never sends |
| `POST /approve/{token}` | Send the draft (outside 07:00-19:00 CT it queues until the window opens). Status moves `pending`/`approved_queued` -> `sending` **before** the Instantly call, under a `set_if_absent` claim, so a double tap or a crash mid-send can never produce a second email |
| `GET /veto/{token}` | Confirmation page only, for the same reason as `/approve`: a veto cancels a real GHL appointment (GHL mails the lead) and rewrites the Instantly interest |
| `POST /veto/{token}` | Drop the draft, release the reserved slots, and cancel anything the reply had already booked (appointment cancelled, its slot reservation released, opportunity back to New Reply, Instantly interest back to 1) |
| `GET /retry/{token}` `POST /retry/{token}` | The operator path back to `pending` for a card stuck at `send_failed`, `stale_slots` or `sending`. Nothing retries those on its own |
| `GET /edit/{token}` `POST /edit/{token}` | Edit the body, re-validate, send. The POST reads urlencoded or JSON itself, so `python-multipart` is not a dependency |
| `GET /accept/{token}` | "Book the time they asked for" — see below |
| `GET /accept/{token}` + `POST /accept/{token}` | Same split: the GET confirms, the POST books the time the lead asked for and sends |
| `GET /cadence/veto/{campaign_id}/{email}?t=` + `POST` | The D1 30-minute veto window. The GET is a confirmation page only (one Veto button that POSTs to the same path with the token; it names no lead), and only for a token that verifies; the POST calls `cadence.record_veto` |
| `GET /cadence/approve/{campaign_id}/{email}?t=` + `POST` | The D6 calendar hold ("Send hold"). Same split: the GET confirms, the POST calls `cadence.record_invite_decision(..., 'approve')` |
| `GET /cadence/veto-invite/{campaign_id}/{email}?t=` + `POST` | The D6 "Email only". Same split: the POST calls `cadence.record_invite_decision(..., 'veto')`. On all three a missing, forged or expired token, an unknown lead or no `REPLY_ENGINE_SECRET` gets one neutral 403 "Not recorded" page (no lead data, no store key) and nothing is written |
| `GET /health`, `GET /state/{lead_email}` | Mode, auto-send status, whether `BASE_URL` is set, which channels can carry an approval card, and the `templates` block (template parity, kill switch, approved counts; no ids, no text); the state dump needs `DEBUG_SECRET` (header only in live) |

The base URL is read in one place, `approval.configured_base_url()`. It reads
`BASE_URL`, with `REPLY_ENGINE_BASE_URL` accepted as an alias. A value that is
unset or points at localhost, 127.0.0.1, 0.0.0.0 or ::1 counts as missing, and a
local-only `BASE_URL` does not hide a real alias. It answers None when neither
is usable.

Most links go through `approval.base_url()`, which wraps it: the approval card
buttons, the SLA chase buttons, the Keep / Release buttons on an expired-card
push, and the cadence links (the D1 Veto, the D6 "Send hold" / "Email only",
and the Resume link; `cadence.links_base_url()` and `cadence._decision_url()`
both call it). When no usable URL is set, shadow logs an ERROR and falls back
to `http://localhost:8000`, so the cadence runs as before. In live,
`approval.base_url()` **raises** `ApprovalUndeliverable` instead:
`create_approval` refuses the card, a chase or expired-card push goes out
without buttons and says so, the cadence holds D1 (no veto window, no send, one
alert, rechecked every tick) and skips the D6 hold card (one alert, no hold
booked, the no-hold follow-up still goes out).

The "I cancelled it" link (`approval.cancel_done_url()`) calls
`configured_base_url()` directly. With no usable URL (or, in live, no
`REPLY_ENGINE_SECRET`) there is no ERROR log, no localhost fallback in shadow
and no raise in live: the link is simply left out, and the alert says no link
could be signed. `/health` also reads `configured_base_url()`, only
to report whether a base URL is set.

Also in live, `create_approval` refuses
unless some channel can carry the Approve/Veto buttons: a protected ntfy topic
(`NTFY_TOKEN`, or `NTFY_ALLOW_SENSITIVE=1`) or a configured email leg
(`GMAIL_SENDER_EMAIL` + `GMAIL_APP_PASSWORD` + `NOTIFY_EMAIL`). An unprotected
topic makes `shared.notify` strip the action buttons while still answering
`sent=True`, so the "was NOT pushed" alarm never fired.
At startup `app.state.store` is set to the process store so the Zoom router and
the scheduled ticks share one instance.

## What happens when a reply names a time

`booking.evaluate_reply` decides, and the outcome reaches Lorenzo as a draft:

| Verdict | Draft |
|---|---|
| Bookable, nothing booked yet | `booking.book()` creates the GHL appointment, moves the opportunity to Call Booked, sets Instantly interest 2 (all guarded) and returns the confirmation: a card, unless it is an approved template the gate allows (see "What sends without a tap") |
| Bookable, already booked | The booking is restated. The engine does not book a second call |
| Blocked only by Lorenzo's own slot rule (before 12:00, weekend, under 4 h out, past 5 business days) | `booking.counter_proposal_text` is the draft **and** the card gains a "Book &lt;time&gt; as asked" action (`/accept/{token}`), which books what they asked for and sends the confirmation instead |
| No time in the reply | The normal answer + two fresh slots |

`zoom_not_connected` (the GHL calendar still has no Zoom app) is carried in the
draft rationale and on the card, never as a blocking validation problem.

## What sends without a tap

* Rule (2026-09-22): an engine email (first reply, counter-proposal, booking
  confirmation, cadence touch, show-rate or no-show message) is sent
  automatically only when its text is exactly a template Lorenzo approved with
  jobs/approve_templates.py and unchanged since, the template kill switch is
  off, and every send check passes (copy gate, opt-out marker, lead reply
  hold, 07:00-19:00 CT send window, recipient check, slot rules); anything else
  goes to Lorenzo as an approval card (replies) or is held (cadence, show-rate,
  no-show). The gate is `template_gate.py`. For a reply, `app._run_pipeline`
  stamps the draft, asks `template_gate.draft_verdict` and passes the verdict
  to `approval.create_approval(auto=...)`: an allowed card is stored with its
  push deferred, and once the lead row is saved `approval.auto_send_approved`
  sends it the way an Approve tap does (`_approve_loaded(actor="template")`,
  then `send_approved`, which runs the gate again on the exact subject and
  body right before the send, beside every other send check). When the send
  leaves the card `pending`, `blocked` or `stale_slots` and it is not a hold,
  the card is pushed once, with a "Not auto-sent: <reason>" line
  (`approval._after_template_send`, `approval.REASON_TEXT`). A lead reply hold
  or a recipient hold raises its own HELD alert instead, and a failed send
  (`send_failed`, or a card stuck at `sending`) is chased by the poller's
  stuck-card pushes. The poller pushes a card whose auto-send never
  ran (`push_orphaned_deferred`) and sends the auto-send FYI at most every 30
  minutes (`flush_auto_send_fyi`). The cadence, show-rate and no-show ladders
  ask the same gate and hold on a refusal. See `runbooks/template_approvals.md`.
* `auto_send_due()`, the old timer auto-approve, is **not** called from
  `poller.run_once` or anywhere else, and CT3 does not use it. It was on the
  every-5-minute tick, so `AUTO_SEND_AFTER_MINUTES` alone would have sent a
  first reply to a positive lead with no human in the loop. It still exists
  for a deliberate operator run: it defaults to **0** (disabled), returns immediately unless `MODE=live` **and**
  `ALLOW_LIVE_WRITES=1`, only considers `positive_interested`, refuses any card
  whose push did not actually reach Lorenzo, and logs a loud Job_Log row plus a
  push for every auto-send.
* `approve()` and `flush_queued()` gate on `slots.is_send_time` (business day
  **and** 07:00-19:00 CT), not `within_send_window`, which is hour-only and
  answers True on a Saturday. `_next_window_open` skips to the next business
  day's 07:00.
* `send_approved()` re-checks the offered times before the Instantly call: the
  approval TTL is 48 h while a slot only has to be 4 h out, so a card approved
  the next morning could otherwise offer a time that had already passed. It
  refuses with `stale_slots` (recoverable through `/retry` + `/edit`).
* A reply that arrived with no Instantly email id (a webhook payload with none,
  so `from_webhook` synthesised `wh:<email>:<ts>`) is never sent in thread: the
  card says to answer it by hand from the Instantly inbox.
* `send_approved()` carries **both** recipient belts the API contract requires:
  `to=<the thread's counterparty>` on `reply_to_email`, and, in live,
  `cadence.thread_recipient_ok` re-reading the email by id and refusing with
  `recipient_mismatch` unless `from_address_email` is that address.
* Every send path ends in `approval.approve(token, ...)`, and `approval.load()`
  rejects a token whose HMAC does not match the persisted approval, the current
  `REPLY_ENGINE_SECRET` and the draft's own hash. Editing a draft changes the
  hash, so the old token stops working.
* `instantly.reply_to_email` is called with `to=<the lead's address>`, so
  Instantly validates the recipient against the thread before it sends.
* `process_event` claims each reply with `store.set_if_absent` as **in flight**,
  not as processed, and marks it done only when the pipeline completes. Two
  overlapping poller ticks therefore process one reply once, and a reply whose
  classification raised is genuinely reprocessed on the retry instead of
  answering "duplicate" (which the poller counted as a success). A content
  fingerprint only collapses arrivals within `DEDUPE_WINDOW_HOURS` (6), so the
  same nudge three days later is answered rather than dropped.

## Cadence handover

* After an approved send, `approval.approve()` calls `cadence.arm(state, now)`:
  day 0 done, next touch the next business day at 10:00 CT.
* `cadence.arm()` copies the thread counterparty onto `state.cadence['reply_from']`
  when the state carries one, and `cadence.recipient_for(state)` is what every
  touch is addressed to. `LeadState` has no `reply_from` field yet (A1 owns
  `models.py`), so until it does, a lead who replied from a shared or assistant
  mailbox is only answered correctly if that address is on the cadence dict when
  it is armed. `lead_email` remains the store key either way.
* Any new inbound reply from an armed lead calls `cadence.stop(state,
  'inbound_reply', now)`, which sets `needs_fresh_draft=True` and leaves the
  rest of the cadence dict in place. The fresh draft is produced for approval,
  and approving it arms the cadence again. An **auto-responder** is the
  exception: `cadence.is_auto_reply_pause()` compares the inbound that caused the
  stop with `resumed_after_auto_reply_at`, so the second, third and fourth robot
  reply on the same thread each pause the ladder rather than killing it.
* A booking calls `cadence.stop(state, 'booked', now)` and writes
  `state.cadence['booking']`.

## Show-rate and no-show couplings

* **The ladder is held until the approval.** `booking.register_booking` writes
  `showrate_hold:<appointment_id>` and then arms the schedule, because booking
  happens at classification time: the first touch is the T+0 "Locked in for ..."
  confirmation, and without the hold the ten-minute tick mails it to the
  prospect before Lorenzo taps Approve, or after he vetoes. `send_approved`
  calls `show_rate.release_hold` next to the GHL invite release;
  `cancel_booking` calls `teardown_booking_records`, which deletes the
  schedules, the hold and the `appointment:`/`appt:`/`zoom_meeting:` rows.
  `no_show.process` returns `awaiting_approval` for a held call rather than
  chasing it. A widget booking is never held.
* A "C" / "confirm" / "yes" reply from a lead whose Discovery Call is still
  ahead calls `show_rate.mark_confirmed(store, appointment_id, now)`. The lead
  who replies C to the **GHL** 24 h reminder is read by
  `show_rate.scan_ghl_confirmations`, which the appointments tick runs before
  the 4 h "has not confirmed" task can be raised (it needs the GHL token).
* **Any** reply from a lead the engine marked `no_show` calls
  `no_show.cancel_recovery(store, appointment_id, 'replied')` so Lorenzo takes
  the conversation back.
* **CT3 template gate.** Every lead-facing show-rate and no-show email or SMS
  goes through `show_rate.dispatch_touch`, which skips a touch whose lead row
  carries the opt-out marker and holds (leaves pending) one whose text is not
  an approved template; a held touch that runs past its lateness limit
  (`MAX_LATENESS`) is dropped, not sent late. These messages are re-rendered and re-stamped at dispatch
  (`show_rate.refresh_copy`, `no_show.rerender_for_dispatch`), so a redeploy
  that changes their text holds them until the new text is approved.

Both need `state.cadence['booking']['appointment_id']`, which only exists once a
booking has run live (in shadow the GHL response is a `would_do` record with no id).

## Running it

```bash
cd "Agentic Worklfows"

# offline replay of the recorded September replies (no network, no model spend)
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m services.reply_engine.replay \
  --fixture services/reply_engine/tests/fixtures/instantly_replies_2026-09.json

# read-only poll against live Instantly (throwaway store, nothing sent)
python3 -m services.reply_engine.poller --dry-run --limit 20

# the service
uvicorn services.reply_engine.app:app --port 8000

python3 -m pytest services/reply_engine/tests -q
```

`poller.run_once()` takes no required arguments: that is the entrypoint
`modal_app.poller` calls on its 5-minute schedule.

## Environment

`MODE` (shadow), `ALLOW_LIVE_WRITES`, `INSTANTLY_API_KEY`,
`GHL_PRIVATE_INTEGRATION_TOKEN`, `ANTHROPIC_API_KEY`, `REPLY_ENGINE_SECRET`
(approval token HMAC), `WEBHOOK_SECRET`, `DEBUG_SECRET`, `BASE_URL`,
`REPLY_ENGINE_BASE_URL`, `NTFY_TOPIC`, `AUTO_SEND_TEMPLATES` (the template
auto-send kill switch: unset leaves it to `config/approved_templates.json`,
any value but 1/on/true/yes switches auto-send off), `AUTO_SEND_AFTER_MINUTES`
(0; the old timer, unused by CT3),
`LLM_FAKE` for offline runs - any spelling `shared.llm.is_fake()` accepts
(`1/true/yes/on`), because `classify`, `poller` and `replay` now use that
function instead of comparing to the exact string `"1"`.

## Open question for Lorenzo

The slot rule says 12:00-18:00 CT. On 2026-09-21 Ilmi asked to move to
"this Wednesday around 11:30 am" and Lorenzo took it. The engine now drafts the
counter-proposal **and** offers "Book Wed 11:30 CT as asked" on the same card,
so the answer is one tap either way. If mornings are genuinely fine for
reschedules, the rule itself should change (`shared.settings.SLOT_WINDOW`)
rather than being waived case by case.

## Repairs applied 2026-09-21 (A1 review)

Behaviour that changed, and the defect behind each change:

* **Ingestion.** `ReplyEvent.from_poller_item` reads `body.text` (then an
  HTML-to-text of `body.html`) and only falls back to `content_preview`, which
  the live API truncates to ~60 characters. `reply_from` carries
  `from_address_email` - the address that actually wrote the thread - and is
  what `instantly.reply_to_email` uses as `to`; `lead` stays the CRM/state key.
  `tests/fixtures/instantly_emails_api_shape_2026-09-21.json` is the wire shape.
* **Classification.** `core_text` only cuts at a sign-off when what follows is
  signature-shaped, so "Thanks, Tuesday at 2pm works for me." survives. R2/R3
  read the signature-stripped text and are gated on `_has_positive_cue`, and the
  bare `bot` / `damn` / `scam` / `stupid` / `lazy` alternatives are gone: a
  curious or buying-signal reply can no longer be blocklisted by one keyword.
  An auto-responder **subject** alone no longer decides when the body is a human
  reply. `router.route()` withholds the blocklist as a second line of defence.
* **Booking.** `evaluate_reply` and `booking.book` receive a real availability
  list (the Discovery Call grid minus `ids.json` busy blocks minus every slot
  held for another lead), so a collision counter-proposes instead of
  double-booking. A reply naming a third party or carrying a deferral cue never
  auto-books. A shadow booking gets a deterministic `shadow-appt-<sha1>` id so
  the show-rate / no-show hooks exercise in shadow.
* **Approval.** Interest status is derived from the approval label and skipped
  for a booking confirmation, so a booked call stays at 2 (`meeting_booked`).
  A newer reply supersedes the lead's still-open cards, but only after
  classification and only when it produces a replacement - an out-of-office
  arriving two minutes after a positive reply used to retire the positive card
  and put nothing in its place. `flush_queued` honours the TTL, isolates each
  lead (one Instantly 5xx no longer skips the rest of the queue), and both
  expiry paths cancel the call the reply had already booked. The queued
  `send_after` is re-localised, so it survives a DST change.
  `edit()` re-derives the offered slots from the edited body and re-reserves
  them, and validates with the card's `campaign_key`.
* **Poller.** The cursor only advances when the scan was not truncated by
  `--limit` or the page budget, and it advances to the newest row *seen* rather
  than the newest row processed, and a reply that fails `MAX_FAILED_ATTEMPTS`
  times stops holding it (it stays in `poller:failed` and raises an alarm).
  `pending_approvals()` surfaces cards that never reached Lorenzo (`notify()`
  returns `sent=False` rather than raising), cards stuck at
  `sending`/`send_failed`/`stale_slots` that nothing else would chase, and a
  lead whose only card is `superseded` with no successor; the last two, and a
  `pending` card whose deferred template push never went out (CT3), are
  pushed to him by `_push_stuck`. Every push is recorded, so a restart neither
  repeats nor forgets it: until one is delivered it repeats 5, 15, 30, 60 and
  120 minutes apart, then hourly, at any hour (urgent and titled UNANSWERED
  from attempt `approval.EXPIRY_PUSH_MAX_ATTEMPTS`); once one is delivered the
  card is only reminded, at most once per business day, inside sending hours.
  An expired card still holding a call is left to its own Keep / Release push. The tick also runs `approval.escalate_pending`, which
  is where the 5-minute reply SLA is **enforced** rather than measured: a card
  still `pending` gets one push per rung of `ESCALATION_LADDER` (5 / 15 / 30 /
  60 sending minutes, then hourly, `high` then `urgent`, capped at
  `ESCALATION_MAX_PUSHES`). Waiting time is counted in *sending* minutes
  (`sending_minutes_between`), so a card raised at 18:58 on a Friday is two
  minutes old on Monday morning, not 62 hours. It stops outside 07:00-19:00 CT
  Mon-Fri, the moment the card leaves `pending`, and at the TTL. It takes no
  Instantly client, so no rung of it can send; the push itself is a
  `guard_write`, so in shadow it is a `would_do` row.
* **Copy.** `validate_draft` takes a `campaign_key` and rejects the other offer
  type's proof line or figures **and the other offers' guarantee figures**
  (offers.md: "one per offer type, never mixed"), takes `allow_terms` so a
  prospect called "Automated Building Services" does not make every draft
  unsendable,
  and the banned list now catches `automat\w*`, "machine learning", "algorithm"
  and the en dash, matching `cadence.copy_problems`.
  `cadence.copy_problems` **is** `validate_draft` plus the cadence's own
  stricter rules, not a second implementation: `cadence.shared_problems` runs
  the same validator and translates its sentences into the cadence's short
  codes. That matters because the D1-D7 touches are the only path to a
  prospect with nobody reading first, and the cadence gate used to be the
  weaker of the two - it passed the `$2,500` retainer offers.md marks TO
  CONFIRM (`money_marked_to_confirm`) and cleaning's `$24,000` guarantee inside
  a bookkeeping thread (`guarantee_from_another_offer`). `Touch.campaign_key`
  (from `cadence.campaign_key_of`) is what arms the cross-offer half; without a
  key both validators are blind to it. If `draft` cannot be imported at all the
  gate returns `copy_validator_unavailable` and the touch is blocked, because a
  missing gate is not "no problems".
