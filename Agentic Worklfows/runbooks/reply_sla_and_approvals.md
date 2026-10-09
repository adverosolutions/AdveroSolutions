# Runbook: the approval card and the 5-minute reply SLA (Blueprint S1; brief A1)

## Purpose
Rule (2026-09-22): an engine email (first reply, counter-proposal, booking confirmation, cadence touch,
show-rate or no-show message) is sent automatically only when its text is exactly a template Lorenzo
approved with jobs/approve_templates.py and unchanged since, the template kill switch is off, and every
send check passes (copy gate, opt-out marker, lead reply hold, 07:00-19:00 CT send window, recipient check,
slot rules); anything else goes to Lorenzo as an approval card (replies) or is held (cadence, show-rate,
no-show). Until he approves templates (`runbooks/template_approvals.md`), every first reply to a positive
lead is drafted and waits for him.

First replies are never sent by the engine (Lorenzo, 2026-09-23). `approval.draft_only` (reason
`first_reply_draft_only`) keeps every `first_reply.*` draft on a card, and keeps any other reply to a lead
we have not answered yet on a card too (booking confirmations excepted), whatever the gate says. The
draft carries two open times the engine holds for that lead and no booking link. Lorenzo copies it, edits
it if he likes, and sends it himself from the Instantly thread. That send is day 0 of the follow-up
ladder. Such a card is a first-contact card ("Reply to send yourself"): Mark sent and Veto, no Approve or
Edit. Tapping **Mark sent** after sending (`approval.mark_sent_manually`, which takes a pending
first-contact card) records a `reply_sent_manually` history event, closes the card, releases the lock and
arms E1 for the next business day. If he does not tap it, the hourly cadence tick finds his send in the
thread and records the same event (`runbooks/cadence_and_booking.md`, "How the ladder starts"), then
closes the pending card (`approval.mark_answered_in_thread`: status `sent_manually`, marked by "thread");
a `blocked` or `stale_slots` card stays as it is. Mark sent on a card already answered in the thread
closes it without a second event; Approve refuses it.

A card the template gate allowed is created with its push deferred and sent at once through the same
path an Approve tap takes (`approval.auto_send_approved`), in the same pipeline run, so it normally leaves
`pending` long before the chase's first rung. If the send leaves the card `pending`, `blocked` or
`stale_slots` and it is not a hold, the card is pushed once with a "Not auto-sent: <reason>" line and is
then an ordinary card (`approval._after_template_send`). If the send ends at `send_failed` (Instantly
raised, a recipient hold escalated, or the 07:00 flush raised), the card is pushed once as well, with its
"Not auto-sent: <reason>" line and the buttons that take a failed card (Retry, Veto, and Mark sent unless
the recipient check held it; Edit is in the email copy and works once Retry has run), and the stuck-card
pushes (`poller._push_stuck`) keep reminding. A lead reply hold raises its own HELD alert instead, and a
recipient hold that has not escalated retries on its own and is not pushed. If the auto-send never
ran (the engine stopped in between), the poller's orphan sweep pushes the card once it is 2 minutes old. This runbook covers the card's whole life: how it is raised, how it is chased while it sits unactioned, how it expires, and what to do
when one is stuck. The SLA in Blueprint Section 6 is **under 5 minutes to first reply in business
hours**, and until this was built that number was only *measured*, once a day, by the 07:30 sweep.

| Piece | File | What it does |
|---|---|---|
| Card | `services/reply_engine/approval.py` `create_approval` | Persists `approval:<id>` for `TTL_HOURS = 48`, pushes the draft with Approve / Veto / Edit buttons |
| Chase | `services/reply_engine/approval.py` `escalate_pending` | One rising push per rung while the card is still `pending` inside sending hours |
| Send | `approve(token)` | Replies from the original inbox and thread (guarded), sets interest status, arms the S2 cadence |
| Queue | `flush_queued` | An approval outside 07:00-19:00 CT is queued, not sent, and flushed when the window opens |
| Tick | `modal_app.approval_escalation` (`*/5`) and `modal_app.poller` (`*/5`) | Both run the chase; see "Why it runs twice" |

## The ladder

| Rung | Card has sat this long (sending minutes) | ntfy priority |
|---|---|---|
| 1 | 5 (`REPLY_SLA_MINUTES`) | high |
| 2 | 15 | high |
| 3 | 30 | urgent |
| 4 | 60 | urgent |
| 5+ | every further 60 (`ESCALATION_REPEAT_MINUTES`) | urgent |
| stop | `ESCALATION_MAX_PUSHES = 8`, about 7 sending hours of chasing | none (no more pushes) |

**Waiting time is counted in *sending* minutes**, not wall clock: `sending_minutes_between` only
accrues inside 07:00-19:00 CT, Mon-Fri. A card raised at 18:58 on a Friday is two minutes old on
Monday morning, not 62 hours old and already at the top of the ladder for time nobody could have
answered in.

The chase stops on all four conditions that should stop it: outside sending hours, the moment the
status leaves `pending`, once the card is expired (`_expire` owns it from there), and at the cap. After
the cap the card is still pending, still on every 07:30 sweep, and still expires on its own at 48 h.

**This ladder is taste, not correctness.** It is how hard Lorenzo's own phone nags him. Change it at
the top of the SLA escalation section of `approval.py`: `ESCALATION_LADDER`,
`ESCALATION_REPEAT_MINUTES`, `ESCALATION_MAX_PUSHES`.

## It chases and only chases
`escalate_pending` takes **no Instantly client** and calls nothing that sends; a test asserts that
structurally against its signature and its source. The only outbound call is `shared.notify.notify`,
which goes through `settings.guard_write` like every other write, so in `MODE=shadow` a chase is a
`would_do` record and no HTTP leaves the process. Buttons go in the ntfy `Actions` header and stay out
of the body, so a mail scanner following links cannot approve a reply.

## Why it runs twice
`approval_escalation` is its own `*/5` schedule **and** the poller runs the same chase on its own tick.
That is deliberate. `poller.run_once` calls `fetch_new_replies` long before it reaches the chase and
does not guard it, so any Instantly failure raises the whole tick and silently takes the SLA with it.
The most likely morning for that is the one where Lorenzo rotates the committed Instantly key
(`GO_LIVE_CHECKLIST.md` step 0) and has not yet updated the Modal secret, which is also a morning cards
are waiting.

Running from both places cannot double-push: each rung is claimed with `store.set_if_absent` under
`approval_escalation:<id>:<step>` before the push, so two overlapping ticks race and exactly one wins.
A card that Keep reopened after it expired (see "When a card expires" below) is chased as a new card:
its count goes back to 0, its clock starts at the Keep (`chase_started_at`), and its rungs are claimed
under `approval_escalation:<id>:r<generation>:<step>`, so the first life's keys cannot silence it.

## How to run (shadow)
```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

# what the tick does, against the current store; writes nothing live
MODE=shadow LLM_FAKE=1 python3 -c "import sys;sys.path.insert(0,'.');\
from services.reply_engine import approval;print(approval.escalate_pending())"

# what is waiting on Lorenzo right now, without pushing anything
MODE=shadow python3 -c "import sys;sys.path.insert(0,'.');\
from services.reply_engine.poller import pending_approvals;from shared import store,slots;\
import datetime;print(pending_approvals(store.get_store(), datetime.datetime.now(slots.TZ)))"
```

## How to test
```bash
python3 -m pytest services/reply_engine/tests/test_approval_sla_escalation.py -q
```

## How to go live (checklist)
1. **`BASE_URL` must be the deployed `modal.run` URL**, corrected in `runbooks/deployment.md` step 2b
   after the first deploy prints it. Unset, `base_url()` warns and every Approve / Veto / Edit button
   points at `http://localhost:8000`. **Escalating a card whose buttons are dead only tells Lorenzo
   something is stuck without letting him unstick it**, so this matters more now than it did before
   the chase existed.
2. `REPLY_ENGINE_SECRET` set (DECISIONS C1). Without it the token HMAC falls back to a dev secret.
3. `NTFY_TOPIC` chosen, and `NTFY_TOKEN` if the card should carry the lead's name and quoted text
   rather than withholding them (DECISIONS C2).
4. `NOTIFY_SHADOW_SEND=1` in the Modal secret during the 48-hour watch, or the chase is unobservable:
   a push is a guarded write, so without it the shadow container records the intent and delivers
   nothing.

## Rollback
Remove the `approval_escalation` entry from `modal_app.SCHEDULES` (and its function), run
`python3 changesets/schedules/build_schedules.py`, and redeploy; the poller keeps chasing. To stop the
chase entirely, set `ESCALATION_MAX_PUSHES = 0`. Neither is urgent: no rung of this can send.

## Known gaps / open items
- **The ladder is a judgement call** (see above). This is the one number here that is taste.
- **A card that expires at 48 h is not re-raised.** `_expire` releases the reserved slots and writes
  nothing to GHL; nothing drafts a fresh reply for the same lead afterwards. The 07:30 sweep is what
  surfaces it. See "When a card expires" for a card that holds a booked call.

## When the card changes while you act on it
Approve, Edit, Book as asked and Veto each read the card, then write it. The write goes through only
if the card is still at the status they read (a status-guarded write under the store's lock). If
something got there first (a send from another tap or device, the 07:00 queue, a newer reply that
superseded the card, the lead's own words holding it, the expiry), the button is refused and says
what the card is now: Approve with "the card changed before the send started (it is now {status});
nothing was sent", Edit, Book as asked and Veto with "the card changed meanwhile (it is now
{status}); ...". When the card is at `sending` and its send may still be running, the refusal from
Edit, Book as asked or Veto also says when it can be acted on (the 10-minute lease, under "When a
card expires" below). Open the card again to see where it stands.
- **Edit**: "the edit was not saved". The times your edit named are not held; the times the card's
  own reply offers stay held, and no Keep / Release choice is recorded.
- **Veto**: "nothing was vetoed". No call is cancelled and no time is released: a card at `sending`
  or `sent` keeps the call its reply confirms.
- **Book as asked**: "Book as asked was not applied". The call it had just booked is cancelled again
  without notifying the lead (shadow: recorded as would_do), and one push, "Book as asked undone for
  {lead}", says what was undone (`runbooks/reply_engine_alerts.md`). A `book_as_asked_undone`
  Job_Log row records it; it does not fail the deploy watch, but a cancel GHL refused writes
  `booking_cancel_failed` beside it, which does.

## When a card expires
`expire_overdue` runs on every poller tick (from `flush_queued`) and retires cards past their 48 h:
**only `pending`, `blocked` and `stale_slots` cards** (`EXPIRABLE_STATUSES`). These never expire:
- `sending` and `send_failed`: a send may have reached Instantly. They stay with **Retry**, which the
  poller's stuck list points at. A Retry past 48 h gives the card a fresh 48 h (and a new link). A
  `sending` card is retried only once its send started at least 10 minutes ago
  (`SEND_CLAIM_LEASE_MINUTES`): before that its send may still be going out, and approving the card
  again would send the lead a second reply, so Retry is refused and says when it becomes available. A
  `sending` card with no record of when its send started (no send claim) is retried as before. Approve,
  Edit, Book as asked and Veto refuse a `sending` card as always, and inside those 10 minutes say the
  same. A card whose reply did go out (`send_failed`, or `sending` past those 10 minutes) is closed
  with **Mark sent** instead (the button on the "Replies with no owner" push): it moves to
  `sent_manually`, which counts as sent, and keeps the call (`runbooks/reply_engine_alerts.md`). Mark
  sent or Retry on a `sending` card writes a `send_never_finished` Job_Log row, which fails the deploy
  watch: its send started and never finished, and the worker that ran it wrote nothing.
- any card holding a send claim (`approval_send_claim:<id>`), whatever its status says.
- `approved_queued`: you already approved it. The queue sends it when the window opens, and the send
  still refuses times that have passed, or a booked call that has passed.

Expiry **never cancels the call**. A card that owns the lead's unconfirmed booking keeps it on the
calendar, reminders held, and you get a **Keep / Release** push (`runbooks/reply_engine_alerts.md`,
"Card expired with a call still booked"). That push is recorded on the card
(`notify_result.expiry_push`). If it is not delivered, it is sent again 5, 15, 30, 60 and 120 minutes
apart. From the sixth attempt it is urgent, titled UNANSWERED, and repeats hourly until it is
delivered or you decide. Every undelivered attempt writes a `push_failed` Job_Log row, which fails the
deploy watch. Until you choose, the poller lists the card as stuck (`expired holding the call ...`) but
does not push it: the Keep / Release push is its only push.

- **Keep**: the card comes back for another 48 hours, still holding the call, with a fresh chase. It
  comes back as `pending`. If a send claim exists it comes back as `send_failed` instead: check the
  thread, then use Retry.
- **Release**: the call is cancelled in GHL without notifying the lead, and the card stays expired.

What the push and the pages say about the past comes from the card's send history (`card_history`:
the context row's `approved_at` and `send_attempts`, plus the live send claim). They say "never
approved" or "no reply has been sent" only when that history proves it. Otherwise they say what is
known, and tell you to check the Instantly thread.
- **The chase has never run against a real phone.** Every rehearsal was `MODE=shadow`, so what exists
  is a `would_do` record per rung, not a delivered push. First deploy is where that is verified.
