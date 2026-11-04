# Handoff: Appointment Setter -> Cold Email Manager (027f41ab-4ca3-4daa-afb1-708ab41d36a3)
Requested by Lorenzo via COO, Wed 11/4/2026 1:21 PM CT. Written 11/4 about 1:30 PM CT. All times CT (UTC-6).
Appointment Setter agent id: bd8d5b35-c4bc-43bd-bebc-dffeb32b1838. Nothing was deleted, paused or changed to write this.
Rules order: state/org/LEAN_ORG.md (THE ONE RULEBOOK) wins over org/roles/appointment-setter.md and skills/booked-calls.md.

## 1. Role and processes
Single job: get every lead from "times offered" to a held call. Owns discovery calls; COO owns pricing calls (I book Zoom/calendar when COO asks).
- Offering times (LEAN_ORG E11, F2): two open Zoom slots, 12:00-18:00 CT Mon-Fri (Tue/Thu preferred), at least 1 day out, never a time already offered to anyone, written in the lead's time zone (CT if unknown). Check Lorenzo's calendar free. Log each slot in offered_times.jsonl as held; release on new offer, a no, or a booking. Lorenzo's booking link (https://scheduler.zoom.us/lorenzo-villarreal-4mp7rz/30-mins-with-lorenzo) is allowed only inside approved copy that offers times.
- Times refresh: no pick after 1 business day gets booking.times_refresh word for word. Interested leads now mostly ride copy/interested_lead_sequence_v2.md (daily Mon-Sat until book or decline; Days 2-6 approved by Lorenzo 10/29).
- Booking (Zoom only): create Zoom (web UI, box browser), then Google Calendar event on <REDACTED:email> (location = Zoom URL, "USE ZOOM ONLY" in description, addGoogleMeetUrl false, notificationLevel NONE). Meet still auto-attaches: strip in Calendar UI (Edit, Remove conference, Save, Don't send) or API PATCH conferenceData null with conferenceDataVersion=1&sendUpdates=none. Verify with get_event (conferenceData empty, location Zoom) before notifying. Write cases/<lead>_booked_<date>.json and queue/<lead>_precall_<date>.json. Lorenzo sends calendar invites.
- Confirmation (Locked-in): Instantly reply in the lead's thread, same inbox, "Re: <subject>", reply_to = lead's newest inbound id. Never a 15-minute or length promise.
- Reminders (skills/booked-calls.md): 24h+ out: R2 -24h and R4 -1h; later but not same day: R3 morning-of and R4; same day: R4. R2 skipped weekends/outside 7-19 CT (and until no-question R2 text approved). Standing (Lorenzo 10/22): auto-arm at booking, no_call_link variant, lead-local time only, no questions; R4 = "See you in an hour. I'll be on a couple minutes early." Before every fire re-read the thread: any lead reply after a check-in cancels later reminders; reschedule/cancel starts a new ladder. New COO rule: no reminder that promises a Zoom link goes out until the link is on the invite (hold instead).
- Pre-call brief: to COO 60 minutes before each call (one screen: facts, warnings, objections, call skeleton).
- Outcome: log outcome and next step same day in the case file, client file and decisions.jsonl. COO audit rule: 30 min after a call ends, send COO (priority) one line asking for the outcome. Every held call has an outcome within 24h.
- Stalled-leads decision (weekdays ~8:15 AM CT): process stalled/queue.csv status=new rows. Review client file, thread (read-only), Upwork/LinkedIn notes, cases. (A) Reactivation: append to 'Reactivation' tab of CRM sheet 'Advero CRM & Accountability' (<REDACTED:long_token>), type stalled, next contact today + 3 months, status "reactivation queued - stalled" (Lorenzo loads Instantly himself). (B) Warm signal / past call / Upwork / big / unclear: one-line hold card up to COO. Plain no / unsubscribe / pause: route and log, no card (ONLY YESES). September leads: nurture, no card. Then log client file + INDEX, set queue status. No emails/Upwork/LinkedIn messages from this flow.
- No-show recovery (LEAN_ORG F2, autonomous under ops-247): Lorenzo's reschedule template verbatim, fields from THAT lead's calendar event (never another lead's weekday, never GHL Call Time alone), 3 open Zoom slots, calendar-link sentence dropped until Lorenzo gives the link, never apologize, one per missed call. Without Zoom join data, start only when Lorenzo marks the no-show.

## 2. Routines (all on the Appointment Setter bot; they STOP when the bot is deleted, so CEM must recreate any it wants)
| Routine | When (CT) | What | Status |
|---|---|---|---|
| Stalled leads decision (stalled-leads-decision) | Weekdays 8:15 AM (+/-15) | Reads stalled/queue.csv new rows; reactivation rows or hold cards | Enabled, recurring. Recreate. |
| marco-r3-morning-of-wed-nov-4 | Wed 11/4 9:00 AM | R3 to Marco | Fired 9:14, HELD (no Zoom on event). CEM: skip if no go by noon. Not sent; treat as done/skipped. |
| marco-r4-one-hour-wed-nov-4 | Wed 11/4 3:00 PM | R4 "See you in an hour" to Marco (Lorenzo yes via COO 11/3 9:42) | Enabled |
| marco-pre-call-brief-wed-nov-4 | Wed 11/4 3:00 PM | Brief to COO | Enabled |
| shelley-r3-morning-of-wed-nov-4 | Wed 11/4 9:30 AM | R3 to Shelley | Fired 9:38, HELD (no event/Zoom then). Not sent. |
| shelley-r4-one-hour-wed-nov-4 | Wed 11/4 1:30 PM | R4 to Shelley | Due/fired 1:30 PM; check sent_log for result |
| shelley-pre-call-brief-wed-nov-4 | Wed 11/4 1:30 PM | Brief to COO | Due/fired 1:30 PM; confirm COO got it |
| wania-brief-readback (Fri 11/6) | Fri 11/6 9:00 AM | Readback of Wania brief | Enabled, but see Wania below: call CANCELLED |
| wania-pre-call-brief-fri-nov-6 | Fri 11/6 ~11:52 AM | Brief to COO | Enabled, but call CANCELLED; do not recreate |
Every reminder routine: check KILL_SWITCH and CAMPAIGNS_PAUSED, then INDEX row, client file, thread, event; hold if Zoom link missing; send only with standing approval on record, else hold card to CEM (priority). Pausing any routine needs a routine_pause line in decisions.jsonl (LEAN_ORG F b).

## 3. State files and paths (~/advero/state unless noted)
- org/LEAN_ORG.md: the one rulebook; wins over everything.
- org/roles/appointment-setter.md: this seat's running doc and decisions log.
- ~/advero/GROK_ONBOARDING_PACK.md: onboarding pack for bots.
- ~/advero/skills/booked-calls.md: booking SOP, reminder timing and copy, Zoom-only, no-15-min rule. Related: cold-email-replies.md, quiet-lead-followup.md, sales-call.md, lorenzo-voice.md, claudeisms.md.
- copy/interested_lead_sequence_v2.md: interested-lead Days 1-6 (Day 5 approved 10/29 5:10 PM, Day 6 5:19 PM).
- clients/INDEX.csv: one row per lead (key, name, company, email, client_file, owner, last note). Some rows CRLF.
- clients/<domain>.md: per-lead context and dated Log; read before, append after.
- clients/.lock: flock lock for INDEX and client file edits.
- cases/: payloads, booked and hold files per lead (e.g. marco_booked_20261104.json, angela_day5_payload_20261104.json).
- queue/: precall files <lead>_precall_<date>.json.
- stalled/queue.csv: RevOps-flagged quiet leads; status new/reactivated/lorenzo/nurture/lost.
- offered_times.jsonl: every offered slot with hold/released/booked status.
- sent_log.jsonl: send key <lead>|<template>|<date> per send; check before every send.
- handled.jsonl: inbound replies handled and by whom.
- decisions.jsonl: decisions, holds, routine pauses (append-only; .lock).
- approvals.jsonl: Lorenzo approvals (append-only), e.g. ops-247-autonomous-20261030, marco-timesrefresh-20261102.
- KILL_SWITCH: if it exists send nothing. Currently ABSENT (lifted 11/3 7:29; see KILL_SWITCH.lifted-20261103-0729).
- CAMPAIGNS_PAUSED: present. All 16 Instantly campaigns paused; only follow-ups to leads in conversation.
- overnight_reply_queue.jsonl: replies outside send window.
- handoffs/20261006_followup_process.md: follow-up ownership doc.
- ~/advero/bin/instantly: `emails <lead>` reads thread, `reply <payload.json>` sends. ~/advero/bin/ghl: GHL stage updates.

## 4. Open items (checked from files 11/4 ~1:30 PM CT)
- Shelley, ASAP Pest Solutions (contactus@ / <REDACTED:email>, ET). Call TODAY 2:30-3:00 PM CT (3:30 PM ET). Thread f1-CrfEnQKK8SOeHp9rbHWl2fW from <REDACTED:email>; newest inbound 01a1a31a (her pick). Locked-in sent 11/3 2:36 PM (no_zoom_link variant). At 9:38 no event/Zoom, R3 held. RevOps 11:30: event "Lorenzo Villarreal and Shelley (ASAP Pest Solutions)" now on calendar with Zoom, attendee needsAction. Todo: confirm R4 1:30 and brief went; outcome ping to COO ~3:30 PM; log outcome today.
- Marco, Quantum Pest (<REDACTED:email>, PT). Call TODAY 4:00-4:30 PM CT, event dtrmq2m8e35uervd7bfamelfog, thread f1-Oc6yrbk4Z429xvE0AvqX27g from <REDACTED:email>. R3 held 9:14 (no Zoom). RevOps 11:30: Zoom link now on event. R4 + brief at 3:00 PM. Outcome ping ~5:00 PM; log today. Earlier 10/30 call was a no-show (cases/marco_noshow_rebook_payload_20261030.json).
- Angela, New Beginnings (<REDACTED:email>, ET). Thread 1b-lzdb_PcBsk5jpY3uli9v-Ib from <REDACTED:email>, reply_to her inbound 01a159df-7522-7a03-be53-787084c704d9, INDEX row 16 (CRLF). Day 3 sent 11/2, Day 4 sent 11/3. Day 5 NOT SENT, approval card expired (final). Draft cases/angela_day5_payload_20261104.json; Thu 11/5 3 PM and Fri 11/6 2:30 PM drafts released. Goes out only if Lorenzo says send, relayed via COO. No inbound since 10/20. Old Day 3 Tue 11/3 and Wed 11/4 3 PM CT slots are both still hold:true, released:false in offered_times.jsonl (Tue 11/3 is past). Release when appropriate. If she picks: book Zoom, strip Meet, confirm.
- Laura, Marketing Angle (<REDACTED:email>): owned by interested-lead runner (<REDACTED:email>). Day 5 sent 11/3 (Thu 11/5 12 PM / Fri 11/6 3 PM held), Day 6 due 11/4 9:15. Not Setter work.
- Wania Sheikh (Upwork autonomous AI sales agent): she paused the project 11/2 12:11; Fri 11/6 call CANCELLED, stage nurture, next step 12/4. The Wania readback and brief routines are stale; do not recreate. Bots never send Upwork messages.
- Older open notes (role doc): Dawnn Clisby Oct 5 outcome never logged; stale Dawnn one-shots deletable when COO says; Ilmi/Dawnn have no client files.

## 5. Logins and accounts (names only, no secrets)
- Sending inboxes (Instantly): <REDACTED:email> (Angela), <REDACTED:email> (Marco), <REDACTED:email> (Shelley), <REDACTED:email> (older cold threads). Always reply from the inbox that first emailed the lead.
- Calendar: <REDACTED:email> via Google Calendar connector; Meet strip in Calendar UI on box browser.
- Zoom: web UI on box browser (no API app, not connected to GHL); scheduler link above.
- Instantly: ~/advero/bin/instantly, env INSTANTLY_API_KEY (loaded by ~/advero/bin/_load_box_secrets.py from /home/box/sand-data/box-secrets.json).
- GHL: ~/advero/bin/ghl, env GHL_API_KEY, GHL_LOCATION_ID (same loader).
- Vault logins per LEAN_ORG "Logins" (bots re-sign in themselves; ask Lorenzo only for SMS 2FA).

## 6. Gotchas and rules
- reply_to_uuid = lead's NEWEST INBOUND id, never our outbound (outbound uuid sends to ourselves; F1 incident 9/29). Recipient check: newest inbound sender must be the lead.
- Zoom only. Meet auto-attaches; strip via conferenceData null and verify before notifying.
- No 15-minute/length promise in Locked-in. No price, fees, %, guarantees. No dashes (em/en), no "!", no emojis, no new wording; signed "Lorenzo".
- Sends 7 AM-7 PM CT only (queue to 7 AM), one retry max same text/inbox/thread, one follow-up per lead per day, re-read thread right before every send.
- No out-of-office follow-ups ever (unless Lorenzo restarts them). September leads go to nurture.
- ONLY YESES: no's/unsubscribes/pauses routed and logged, no card. ONE YES: Lorenzo's yes in COO chat (and COO's own yes, per Lorenzo 10/22) is approval for exactly what it covers; his stops and later words win.
- Expired approval card is final: no retry, no re-raise, no other channel.
- No reminder promising a Zoom link until the link is on the invite.
- Log after acting: client file Log line + INDEX row under `flock ~/advero/state/clients/.lock`, keep CRLF. approvals.jsonl and decisions.jsonl append-only.
- Never write to the Lead Pool sheet (incl. its Reactivation tab).
- CAMPAIGNS_PAUSED: nothing to new leads; only follow-ups/replies/confirmations to leads in conversation until Lorenzo himself says.
- Duplicate risk with the interested-lead runner (check sent_log key before sending; e.g. Laura is runner-owned). Watch days stacking (Angela Day 3 and Day 4 on consecutive days while holds still open).
- Bots never send Upwork messages (drafts only).
- No team room posts 9 PM-6 AM.
