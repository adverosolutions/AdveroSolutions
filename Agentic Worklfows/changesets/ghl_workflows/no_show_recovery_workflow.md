# GHL workflow build spec: "No-show recovery: Discovery Call"

> Superseded, do not build from this file. It predates the 2026-09-23 email-only rebuild and the 2026-09-24 go-live timing (N1 at S+5; days 1, 2, 3, 5 and 7 in business days). Template ids below are the old ones (`ns_d3_value_email`, `ns_d7_yes_no_email`, `ns_d14_breakup_email` are now `ns_d2_value_email`, `ns_d5_yes_no_email`, `ns_d7_breakup_email`, plus the new `ns_d3_retry_email`). The engine's ladder in `services/reply_engine/no_show.py` and `runbooks/show_rate_and_no_show.md` is authoritative.

Status: NOT BUILT. GHL workflows cannot be created through the public API; the Fulfillment agent builds this in the GHL UI from the steps below. Detection is NOT done by GHL (it never marks no-shows itself): `services/reply_engine/no_show.py` flips the appointment to `noshow` through `PUT /calendars/events/appointments/{id}` (guarded; shadow-only until go-live), and that API change is the trigger here.

Controlled-environment rule: build in **Draft**, test with an internal contact, publish only after the runbook checklist. SMS steps disabled until A2P 10DLC clears. Never run both the GHL workflow and the engine's `run_recovery` live at the same time (see "Who sends what").

## Ids
- Calendar: Discovery Call `GDugwLmZNdsD13RBDnRu`
- Pipeline Sales `GCBkIzFpung73cIDVPzn`; stages Follow Up Later `ce219fc8-3caa-45e5-bc81-622a1625a23b`, Lost `6ce29ed4-fab0-4244-938f-758ef8688cd8`
- Assigned user `gIwBtPohHJXADQBuGAx8`
- Booking / reschedule URL `https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu` (inside the workflow prefer `{{appointment.reschedule_link}}`)

## Workflow settings
| Setting | Value |
| --- | --- |
| Name | No-show recovery: Discovery Call |
| Allow Re-entry | ON (a contact can no-show more than once) |
| Stop on response | ON for the email/SMS legs after +1 h (a reply means Lorenzo takes over); the engine mirrors this by pausing on any inbound reply |
| Time window | Emails and SMS 07:00 to 19:00 America/Chicago **Mon to Fri** (steps falling outside wait for the next weekday in the window; the +5 min "still on?" is exempt because the call itself is inside 12:00 to 18:00 on a weekday) | The weekday half matters: a Thursday no-show puts the day-3 email on a Sunday and a Friday-evening miss puts "I was on the line at 6:30 CT" on a Saturday morning. `no_show.recovery_touches` defers with `weekdays_only=True` |

## Repeat policy (SOP-005)
Custom field `no_show_count` (number) on the contact, incremented at step 1. Branch: 1 -> full sequence; 2 -> steps up to +1 h then note "second no-show pattern"; 3+ -> +5 min touch only, then move opportunity to Lost.

## Steps

| # | Step | Type | Config |
| --- | --- | --- | --- |
| 0 | Trigger | Appointment Status | Filter: Calendar = Discovery Call; Appointment status = No Show; Modified by = API (the engine) or User (Lorenzo marking by hand) |
| 1 | Increment `no_show_count` | Update Contact Field | `no_show_count` = `{{contact.no_show_count}}` + 1 (use the Math action) |
| 2 | Add note | Add Note | "No-show #{{contact.no_show_count}} at {{appointment.start_time}}. Recovery started. Pipeline unchanged." |
| 3 | Wait 5 minutes | Wait, Time delay | 5 minutes (from the flag at start + 10 min, so this lands at start + 15 min) |
| 4 | "Still on?" SMS | Send SMS (DISABLED until A2P) | body = no_show.py `ns_still_on_sms` with `{{appointment.meeting_location}}` |
| 5 | "Still on?" email | Send Email | subject `Still on?`, body = `ns_still_on_email` |
| 6 | Wait 5 minutes | Wait | 5 minutes |
| 7 | Call task | Add Task + Internal notification | Title `No-show at {{appointment.start_time}}: call {{contact.first_name}} ({{contact.company_name}}) + voicemail`; body = `ns_call_task` (30-second voicemail script); assigned Lorenzo; due now |
| 8 | If/Else on `no_show_count` | Condition | `>= 3` -> go to step 20 (Lost). `== 2` -> continue to 9, then jump to 19. `== 1` -> continue |
| 9 | Wait 50 minutes | Wait | brings us to +1 h from the flag |
| 10 | Reschedule email | Send Email | subject `Missed you on our call`; body = `ns_reschedule_email` with `{{appointment.reschedule_link}}`. Two fresh slots are NOT available as GHL merge fields; the engine's version adds them, the GHL version is link-only |
| 11 | If `no_show_count == 2` | Condition | Yes -> step 19 |
| 12 | Wait 1 day | Wait | inside time window |
| 13 | Day 1 second channel | Send SMS (DISABLED until A2P) or Add Task "LinkedIn note / text by hand" | body = `ns_d1_other_channel` / `ns_d1_other_channel_task` |
| 14 | Wait 2 days | Wait | |
| 15 | Day 3 value email | Send Email | subject `One thing worth knowing before you decide`; body = `ns_d3_value_email` (offer-sheet proof line by offer tag `offer-reactivation` / `offer-outbound`). **Re-render the two offered times at send, never at trigger:** slots frozen when the miss was flagged have already passed by day 1 and day 3 |
| 16 | Wait 4 days | Wait | |
| 17 | Day 7 yes/no email | Send Email | subject `Should I close your file?`; body = `ns_d7_yes_no_email` |
| 18 | Wait 7 days, then Day 14 breakup | Wait + Send Email | subject `Closing your file`; body = `ns_d14_breakup_email`; then Update Opportunity: stage = Follow Up Later (`ce219fc8-...`) ; then End |
| 19 | Second no-show close | Add Note | "Second no-show; limited to two touches per SOP-005. Watch for a pattern." Then End |
| 20 | Third no-show | Update Opportunity | Pipeline Sales, stage Lost (`6ce29ed4-...`), status lost; Add Note "Third no-show, closed Lost per SOP-005"; End |

Goal / exit: "Appointment booked in Discovery Call" removes the contact from this workflow (Workflow settings > Goal event: Appointment Booked). The engine mirrors it in three places, none of which depends on brief A2 shipping a hook: `no_show.process` cancels the recovery as `rebooked` when the appointment start moves (a widget rebooking keeps the appointment id), `no_show.run_recovery` skips any contact the tick just read with a call still ahead of them, and `jobs/appointments_tick` calls `no_show.cancel_recovery_for_rebooking` for a flagged contact who turns up in the window on a new appointment id.

## Detection precondition (do not publish before this is true)
The trigger above is the appointment status going to No Show, and the engine only sets it when there is real evidence: a Zoom join record for that meeting inside its own window, a Zoom meeting started/ended event, a Fireflies transcript length, or a status Lorenzo set by hand. With none of those (today: the Discovery Call calendar is on Google Meet and no Zoom app exists) `no_show.detect` returns `unknown`, nothing is flagged, and the engine creates one task asking Lorenzo to mark the call showed or noshow. Marking it by hand is what starts this workflow until Zoom is connected.

## JSON representation
```json
{
  "name": "No-show recovery: Discovery Call",
  "status": "draft",
  "settings": {"allowReentry": true, "stopOnResponse": true, "timeWindow": {"start": "07:00", "end": "19:00", "timezone": "America/Chicago"}},
  "goal": {"type": "appointment_booked", "calendarId": "GDugwLmZNdsD13RBDnRu", "action": "remove_from_workflow"},
  "trigger": {"type": "appointment_status", "filters": {"calendarId": "GDugwLmZNdsD13RBDnRu", "status": "noshow", "modifiedBy": ["api", "user"]}},
  "steps": [
    {"id": 1, "type": "update_field", "field": "no_show_count", "op": "increment", "by": 1},
    {"id": 2, "type": "add_note", "template": "no_show_flag_note"},
    {"id": 3, "type": "wait", "mode": "time_delay", "minutes": 5},
    {"id": 4, "type": "send_sms", "template": "ns_still_on_sms", "enabled": false, "enableWhen": "A2P_10DLC_REGISTERED=1", "ignoreTimeWindow": true},
    {"id": 5, "type": "send_email", "template": "ns_still_on_email", "ignoreTimeWindow": true},
    {"id": 6, "type": "wait", "mode": "time_delay", "minutes": 5},
    {"id": 7, "type": "add_task", "template": "ns_call_task", "assignedTo": "gIwBtPohHJXADQBuGAx8", "dueIn": "now", "notify": true},
    {"id": 8, "type": "if_else", "field": "no_show_count", "branches": {">=3": "goto:20", "==2": "continue", "==1": "continue"}},
    {"id": 9, "type": "wait", "mode": "time_delay", "minutes": 50},
    {"id": 10, "type": "send_email", "template": "ns_reschedule_email", "mergeFields": ["appointment.reschedule_link"]},
    {"id": 11, "type": "if_else", "field": "no_show_count", "branches": {"==2": "goto:19", "default": "continue"}},
    {"id": 12, "type": "wait", "mode": "time_delay", "days": 1},
    {"id": 13, "type": "send_sms_or_task", "sms": {"template": "ns_d1_other_channel", "enabled": false, "enableWhen": "A2P_10DLC_REGISTERED=1"}, "task": {"template": "ns_d1_other_channel_task"}},
    {"id": 14, "type": "wait", "mode": "time_delay", "days": 2},
    {"id": 15, "type": "send_email", "template": "ns_d3_value_email", "branchOn": "offer_tag"},
    {"id": 16, "type": "wait", "mode": "time_delay", "days": 4},
    {"id": 17, "type": "send_email", "template": "ns_d7_yes_no_email"},
    {"id": 18, "type": "sequence", "steps": [
      {"type": "wait", "mode": "time_delay", "days": 7},
      {"type": "send_email", "template": "ns_d14_breakup_email"},
      {"type": "update_opportunity", "pipelineId": "GCBkIzFpung73cIDVPzn", "stageId": "ce219fc8-3caa-45e5-bc81-622a1625a23b"},
      {"type": "end"}]},
    {"id": 19, "type": "sequence", "steps": [{"type": "add_note", "template": "second_no_show_pattern"}, {"type": "end"}]},
    {"id": 20, "type": "sequence", "steps": [
      {"type": "update_opportunity", "pipelineId": "GCBkIzFpung73cIDVPzn", "stageId": "6ce29ed4-fab0-4244-938f-758ef8688cd8", "status": "lost"},
      {"type": "add_note", "template": "third_no_show_lost"},
      {"type": "end"}]}
  ],
  "customFields": [{"name": "no_show_count", "type": "number", "default": 0}],
  "templatesSource": "services/reply_engine/no_show.py render()"
}
```

## Detection wiring (outside GHL)
1. Zoom app (Marketplace > Build App > Webhook Only) with events `meeting.participant_joined`, `meeting.ended`; endpoint `POST https://<reply-engine-host>/webhooks/zoom`; secret token -> `ZOOM_WEBHOOK_SECRET` in `.env`. Not created yet (Zoom is not even connected to GHL).
2. `services/reply_engine/zoom_webhook.py` stores joins; `jobs/appointments_tick.py` (every 5 minutes) runs `no_show.process` at start + 10 min and issues the guarded `PUT .../appointments/{id}` with `appointmentStatus: noshow`, which fires this workflow.
3. Fallback when Zoom webhooks are down: Fireflies recap with an empty transcript after the end time (pass `fireflies_transcript_len` to `detect`).

## Who sends what
Same rule as the show-rate spec: shadow now (nothing sent by anyone); at go-live choose the engine (`run_recovery` live, workflow Draft) or GHL (workflow published, engine only flips the appointment status and logs). Default recommendation: engine, because it inserts two fresh calendar slots into the +1 h email and GHL cannot.

## Test plan in the GHL UI
1. Test contact with `no_show_count` empty, an opportunity in Sales / Call Booked, and a Discovery Call appointment 20 minutes in the past.
2. Mark the appointment No Show by hand. Expect: note, `no_show_count` = 1, "Still on?" email after 5 min, task after 10 min, "Missed you" email after 1 h, then the day 1/3/7/14 legs (fast-forward with "Skip wait" in the workflow tester).
3. Book a new appointment for the test contact mid-sequence. Expect removal by the goal event.
4. Repeat with `no_show_count` = 2 (two touches then note) and 3 (one touch then Lost).
5. Delete test data afterwards.
