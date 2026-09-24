# Runbook: 90-day nurture enrollment (section 1)

Owner: Sales agent. Status: enrollment hook built 2026-09-23, MODE=shadow, nothing sends.

## What it is for
A lead who is not buying now should not be dropped. Nurture keeps them on a slow, 90-day track so they hear from us again later, instead of getting more daily follow-ups or nothing at all. This piece only records who is in nurture and why. It sends nothing.

## Who enrolls a lead, and why
Nothing calls `enroll` yet (2026-09-23); the callers below are planned.

| Reason | Called by (planned) | When |
| --- | --- | --- |
| `no_reply_after_sequence` | the follow-up cadence (section 1) | the ladder ran out (D30 went out) and the lead never answered |
| `not_now_reply` | the reply handling (section 1) | the lead answered "not now" / "maybe later" |
| `no_show_no_rebook` | booked-calls section (section 2) | the lead missed the call and never rebooked |

## The call
```python
from services.reply_engine import nurture

nurture.enroll(lead_email, reason, now)   # the positional contract, section 2 calls exactly this
nurture.enroll(lead_email, reason, now, store=None, campaign_id=None, note=None)
nurture.get(lead_email, store=None)          # the stored record, or None
nurture.is_enrolled(lead_email, store=None)  # True only while status is "active"
```
- `now` must be timezone-aware. Times are stored as Central Time ISO strings.
- The email is trimmed and lowercased. An empty email, one without "@", a reason not in the table above, or a naive `now` raises `ValueError`.
- `store` defaults to the shared engine store (`shared.store.get_store()`).
- It returns the stored record plus `created` (True only when this call started a new enrollment). `created` is not stored.

## Where it lives
Its own store key, `nurture:<email>`, not the lead row. Enrolling never writes a `lead:` row and needs no campaign id. The record holds `lead_email`, `status` ("active"), `reason` (the first one), `enrolled_at`, `ends_at` (90 calendar days later, same clock time), `campaign_id`, `events` (one per reason: `reason`, `at`, `campaign_id`, `note`) and `touches` (empty, kept for the nurture emails).

## Safe to call twice
- Already active: nothing resets. `enrolled_at`, `reason` and `ends_at` stay. A different reason adds one event; the same reason again adds nothing, so a job that retries does not grow the record. A missing `campaign_id` is filled in.
- A record with any other status (later: "ended" or "left") starts a fresh enrollment and keeps the old events.
- A broken value at the key is replaced with a fresh record.

## What the follow-up cadence does with it
On every tick, before anything can send, the cadence checks the lead. If the lead is enrolled, the ladder stops with reason `nurture` (no touch, `next_send_at` cleared). An out-of-office pause is not resumed for an enrolled lead either. `nurture` is not a resumable stop, and `cadence.resume` refuses to re-arm an enrolled lead. If the nurture record cannot be read, the lead is held that tick (`action: error`), never sent to.

## Shadow safety
Enrolling makes no network call and does not go through `guard_write`. It only writes the engine's own store, which shadow mode allows.

## Not built yet
- The nurture emails themselves.
- The nurture tick job that would send them.
- The callers: the cadence enrolling a lead when the ladder runs out, the reply handling enrolling on a "not now" reply, and section 2's no-show job.
- Leaving nurture when a lead books or replies with interest (and ending it after 90 days). Until then, a nurtured lead whose reply re-arms the ladder is stopped again as `nurture` on the next tick; to take a lead out by hand, delete its `nurture:<email>` key.
