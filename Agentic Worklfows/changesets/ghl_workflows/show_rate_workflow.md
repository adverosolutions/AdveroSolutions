# GHL workflow build spec: "Show Rate: Discovery Call reminders"

Status: NOT BUILT. GHL workflows cannot be created through the public API (there is no POST /workflows; the API only lists workflows and adds contacts to them). The Fulfillment agent builds this in the GHL UI (Automation > Workflows > Create) from the steps below; the engine (`services/reply_engine/show_rate.py`) mirrors the same touches so either side can carry the sequence while the other is off.

Controlled-environment rule: build it in **Draft**, test with an internal contact (Lorenzo's own email and phone) through "Test workflow", and publish only after the runbook checklist in `runbooks/show_rate_and_no_show.md` is signed off. Until A2P 10DLC clears, SMS steps stay **disabled** (toggle off each SMS action; do not delete them).

## Ids (from `config/ids.json`)
- Location: `ebyNANPagaK7ycf1pfge` (AdveroSolutions)
- Calendar: Discovery Call `GDugwLmZNdsD13RBDnRu` (15-min slots, auto-confirm, Zoom NOT connected yet; connect Zoom under Profile > Calendar Settings > Video Conferencing first, otherwise `{{appointment.meeting_location}}` is a Google Meet link)
- Assigned user: `gIwBtPohHJXADQBuGAx8` (Lorenzo)
- Booking / reschedule URL: `https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu` (verify the public widget URL before publishing)

## Workflow settings
| Setting | Value | Why |
| --- | --- | --- |
| Name | Show Rate: Discovery Call reminders | |
| Allow Re-entry | ON | reschedules re-trigger the workflow; each entry is keyed to the new appointment time |
| Stop on response | OFF | a "C" reply must not end the reminders; it only confirms |
| Time window | 07:00 to 19:00 America/Chicago for steps 3 to 6 only (the T+0 confirmation and the pre-read); none for steps 7 onward | The reminders are relative to a time the lead chose, which is always inside 12:00 to 18:00 CT. The T+0 legs are relative to the booking, and the widget takes bookings at any hour: CLAUDE.md's engine rule is "sends only 07:00-19:00 CT". `show_rate.schedule_for` defers them the same way (hour only, not weekday, so a Friday-evening booking is confirmed on Saturday morning) |
| Timezone | Contact's timezone, fallback Account (America/Chicago) | the `{{appointment.start_time}}` merge field renders in the contact's tz |

## Steps (in order)

| # | Step | Type | Config | Notes |
| --- | --- | --- | --- | --- |
| 0 | Trigger | **Appointment Status** (not Customer Booked Appointment) | Filter: In calendar = Discovery Call (`GDugwLmZNdsD13RBDnRu`); Appointment status = **Confirmed** | Fires when a call becomes confirmed. See "Why the trigger is the status, not the booking" below |
| 1 | Wait 1 minute | Wait, Time delay | 1 minute | Lets the Zoom link populate on the appointment before the first message |
| 2 | Remove tag `call-confirmed` | Remove Contact Tag | call-confirmed | A reschedule needs a fresh C reply |
| 3 | Confirmation email | Send Email | Subject: `Confirmed: {{appointment.start_time}}, Lorenzo and {{contact.company_name}}`; body = show_rate.py `confirm_email` (3-bullet agenda per niche via If/Else on tag `niche-cleaning` / `niche-bookkeeping` / `niche-recruiting`, Loom link per niche) | From lorenzovillarreal@adverosolutions.com, plain text |
| 4 | Confirmation SMS | Send SMS (DISABLED until A2P) | body = `confirm_sms` | |
| 5 | Wait 15 minutes | Wait, Time delay | 15 minutes | |
| 6 | Pre-read email | Send Email | Subject `Before {{appointment.day_of_week}}: the one-page version`; body = prompts/show_rate_preread_<niche>[_<offer>].md via If/Else on the niche tag AND the offer tag (`offer-reactivation` / `offer-outbound`) | The offer tag is load-bearing: an outbound/trigger prospect must get their own guarantee and proof line, never the reactivation commission numbers. **Skip this step once the appointment has started** (a booking made inside 15 minutes would otherwise get "Before our call: the one-page version" during the call) |
| 7 | Wait until 24 h before | Wait, Event/Appointment time | Before appointment, 24 hours; **If the time has passed: Skip** (the past-time fallback) | Bookings made inside 24 h jump straight to step 10 |
| 8 | 24 h SMS | Send SMS (DISABLED until A2P) | `reminder_24h_sms` ("Reply C to confirm") | |
| 9 | 24 h email | Send Email | `reminder_24h_email` ("Reply C to confirm") | |
| 10 | Wait until 4 h before | Wait, Event/Appointment time | Before appointment, 4 hours; If the time has passed: Skip | |
| 11 | If/Else | Condition | Contact tag includes `call-confirmed` | The tag is added by the companion workflow "Reply C confirms" (below) |
| 11a | No branch: task for Lorenzo | Add Task | Title `Unconfirmed call at {{appointment.start_time}}: text or call {{contact.first_name}} ({{contact.company_name}})`; assigned `gIwBtPohHJXADQBuGAx8`; due now; body = `unconfirmed_task` script | Also an Internal Notification (email/app) to Lorenzo |
| 11b | Yes branch | (no action) | | |
| 12 | Wait until 1 h before | Wait, Event/Appointment time | Before appointment, 1 hour; If the time has passed: Skip | |
| 13 | 1 h SMS | Send SMS (DISABLED until A2P) | `reminder_1h_sms` with `{{appointment.meeting_location}}` | Highest-leverage message once SMS is on |
| 14 | Wait until 15 min before | Wait, Event/Appointment time | Before appointment, 15 minutes; If the time has passed: Skip | |
| 15 | 15 min SMS | Send SMS (DISABLED until A2P) | `reminder_15m_sms` ("Hopping on now") | |
| 16 | End | | | |

### Why the trigger is the status, not the booking
A booking made from a cold-email reply is on the calendar at **classification** time, before Lorenzo has seen the approval card. `booking.book()` creates it with `appointmentStatus: "new"` and `toNotify: false` (a hold), and only `approval.send_approved` moves it to `confirmed` with `toNotify: true`, which is the moment GHL releases the invite. A trigger on Customer Booked Appointment fires on the hold itself: the old spec did, and because the hold used to be created as GHL's default `confirmed`, this workflow would have emailed "Confirmed: <time>", the pre-read and every reminder a minute after classification, for a call Lorenzo might still veto. Triggering on the status change to Confirmed makes Approve the start of the sequence.

Before publishing, rehearse in the GHL UI with the internal test contact (see the test plan) that the trigger enters on each of these and on nothing else:
- a widget self-booking (created already confirmed by the calendar's auto-confirm): **must enter**;
- a reschedule of a confirmed call: **must re-enter** with the new time;
- an engine hold created through the API as `new`: **must NOT enter**, and must stay `new` (if the calendar's auto-confirm flips an API-created `new` to `confirmed`, the hold is unsafe: stop and turn auto-confirm off first);
- that hold moved `new` -> `confirmed`: **must enter**.
If GHL's Appointment Status trigger does not fire for a booking created already confirmed, or for a reschedule, add Customer Booked Appointment as a **second** trigger, filtered to status Confirmed, and repeat the `new` hold check above before publishing.

### Companion workflow: "Reply C confirms Discovery Call"
| # | Step | Config |
| --- | --- | --- |
| 0 | Trigger: Customer Replied | Reply channel: SMS or Email; Contains phrase: `C` (exact word; also accept "confirm", "confirmed", "yes") |
| 1 | If/Else | Contact has an upcoming appointment in Discovery Call (Appointment status = Confirmed, start in the next 48 h). **The status filter is load-bearing**: a lead's positive "yes" to a cold email is exactly what creates an unapproved `new` hold, and step 3 must never confirm that hold on the prospect's say-so |
| 2 | Add Contact Tag | `call-confirmed` |
| 3 | Update Appointment Status | Confirmed (already true; kept so the audit log shows the C) |
| 4 | Internal notification | "{{contact.name}} confirmed {{appointment.start_time}}" to Lorenzo |

The engine reads the `call-confirmed` tag (or `store['confirmed:<appointment_id>']`) to skip the 4 h task. `jobs/appointments_tick` refreshes the stored appointment snapshot from every GHL read, so the tag added after booking reaches `show_rate.is_confirmed`; the store flag records the start it refers to and is cleared on a reschedule, matching step 2 above.

## JSON representation (for the Fulfillment agent)
```json
{
  "name": "Show Rate: Discovery Call reminders",
  "status": "draft",
  "settings": {"allowReentry": true, "stopOnResponse": false, "timezone": "contact_fallback_account"},
  "trigger": {"type": "appointment_status", "filters": {"calendarId": "GDugwLmZNdsD13RBDnRu", "appointmentStatus": "confirmed"},
              "note": "status change to confirmed, NOT customer_booked_appointment: the engine's classification-time hold is created as new"},
  "steps": [
    {"id": 1, "type": "wait", "mode": "time_delay", "minutes": 1},
    {"id": 2, "type": "remove_tag", "tags": ["call-confirmed"]},
    {"id": 3, "type": "send_email", "template": "confirm_email", "branchOn": "niche_tag", "from": "lorenzovillarreal@adverosolutions.com"},
    {"id": 4, "type": "send_sms", "template": "confirm_sms", "enabled": false, "enableWhen": "A2P_10DLC_REGISTERED=1"},
    {"id": 5, "type": "wait", "mode": "time_delay", "minutes": 15},
    {"id": 6, "type": "send_email", "template": "preread_email", "branchOn": "niche_tag"},
    {"id": 7, "type": "wait", "mode": "before_appointment", "hours": 24, "ifTimePassed": "skip"},
    {"id": 8, "type": "send_sms", "template": "reminder_24h_sms", "enabled": false, "enableWhen": "A2P_10DLC_REGISTERED=1"},
    {"id": 9, "type": "send_email", "template": "reminder_24h_email"},
    {"id": 10, "type": "wait", "mode": "before_appointment", "hours": 4, "ifTimePassed": "skip"},
    {"id": 11, "type": "if_else", "condition": {"contactTagIncludes": "call-confirmed"},
      "no": [{"type": "add_task", "template": "unconfirmed_task", "assignedTo": "gIwBtPohHJXADQBuGAx8", "dueIn": "now"},
             {"type": "internal_notification", "to": "gIwBtPohHJXADQBuGAx8", "channel": ["email", "app"]}],
      "yes": []},
    {"id": 12, "type": "wait", "mode": "before_appointment", "hours": 1, "ifTimePassed": "skip"},
    {"id": 13, "type": "send_sms", "template": "reminder_1h_sms", "enabled": false, "enableWhen": "A2P_10DLC_REGISTERED=1"},
    {"id": 14, "type": "wait", "mode": "before_appointment", "minutes": 15, "ifTimePassed": "skip"},
    {"id": 15, "type": "send_sms", "template": "reminder_15m_sms", "enabled": false, "enableWhen": "A2P_10DLC_REGISTERED=1"}
  ],
  "companion": {
    "name": "Reply C confirms Discovery Call",
    "trigger": {"type": "customer_replied", "channels": ["sms", "email"], "containsPhrase": ["C", "confirm", "confirmed", "yes"]},
    "steps": [
      {"type": "if_else", "condition": {"hasUpcomingAppointment": {"calendarId": "GDugwLmZNdsD13RBDnRu", "withinHours": 48, "appointmentStatus": "confirmed"}}},
      {"type": "add_tag", "tags": ["call-confirmed"]},
      {"type": "update_appointment_status", "status": "confirmed"},
      {"type": "internal_notification", "to": "gIwBtPohHJXADQBuGAx8"}
    ]
  },
  "templatesSource": "services/reply_engine/show_rate.py render() and services/reply_engine/prompts/show_rate_preread_*.md"
}
```

## Who sends what (avoid double sends)
Exactly one of the two carries the sequence at any time:
- Phase 1 (now): the engine in MODE=shadow logs would_do; the GHL workflow stays Draft. Nothing is sent by either.
- Phase 2 (go-live option A, engine): engine MODE=live sends through `POST /conversations/messages`; the GHL workflow stays Draft.
- Phase 2 (go-live option B, GHL): publish the GHL workflow; set `SHOW_RATE_SENDER=ghl` so the engine keeps scheduling and logging but skips every dispatch with reason `sender_is_ghl` (implemented in `show_rate.dispatch_touch`; applies to recovery touches too).

## Test plan in the GHL UI (before publishing)
1. Create test contact "Lorenzo Test" with Lorenzo's email and phone, tag `niche-cleaning`.
2. Book a Discovery Call for tomorrow 14:00 CT from the public widget. Expect: confirmation email in 1 minute, pre-read in 16 minutes, 24 h email skipped (inside 24 h), task at 10:00 CT if no C reply, SMS steps disabled.
3. Reply "C" by email. Expect tag `call-confirmed`; at 10:00 CT no task is created.
4. Reschedule from the invite link. Expect re-entry with the new time and the tag removed.
5. The hold path: create an appointment for the test contact through the API (or the UI) with status **Unconfirmed / new**. Expect: no entry, no email, no reminder of any kind, and the status still `new` a few minutes later. Then set it to Confirmed. Expect: entry, the confirmation email in 1 minute. Reply "yes" to anything while it is still `new`: the companion must not confirm it.
6. Delete the test appointments and contact afterwards.
