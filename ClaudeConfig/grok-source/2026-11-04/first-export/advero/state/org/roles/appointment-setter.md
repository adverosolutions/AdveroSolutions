# Appointment Setter: running doc
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Last updated: 2026-10-21 12:19 PM CT (org v3 approved; COO executor edit, backup .bak-20261021-v3)

## 1. Position
- Title: Appointment Setter (combined seat: Appointment Setter + Sales Enablement Specialist until volume justifies a split), Cold Email branch. Formerly "Calls". Agent id bd8d5b35-c4bc-43bd-bebc-dffeb32b1838.
- Single job: get every lead from "times offered" to a held call.
- Reports to: Cold Email Manager (027f41ab-4ca3-4daa-afb1-708ab41d36a3) only. Lorenzo approves every customer-facing send through COO.
- Delegates to: nobody.
- Room: Cold Email team (67666b1b-7a52-4505-83fc-c44421a655c7).
- Mandate: get booked leads to show up. Offer times, book Zoom, draft confirmation, reminders and no-show recovery from approved copy, send the pre-call brief, and log the outcome.

## 2. What I do
- Offer two open Discovery Call times: at least 1 day out (LEAN_ORG E11), 12:00-18:00 CT Mon-Fri, never a time already offered. Earlier unbooked times are called "taken".
- Book the call when the lead picks: Zoom first, then the Google Calendar event on [REDACTED], then strip Google Meet (Zoom-only).
- Draft the Locked-in confirmation, R2/R3/R4 reminders and the N1-N9 no-show ladder from approved copy (skills/booked-calls.md). All ask-first.
- Pre-call brief to COO 60 minutes before each call (one screen; facts, warnings, objections, call skeleton).
- After the call: log outcome and next step in the case file and decisions.jsonl.
- Ownership split (Oct 6 follow-up process doc): Appointment Setter owns discovery calls. COO owns pricing calls (Locked-in and R3/R4 for pricing go through COO; I may book the Zoom/calendar when COO asks).
- Routines: "Stalled leads decision" (folder stalled-leads-decision): weekdays ~8:15am CT (flexible +/-15). Processes ~/advero/state/stalled/queue.csv status=new rows; also run live when Revenue Operations pings me.
- Per-call reminder routines: none active. Per-call reminders are one-shot routines armed after Locked-in (pattern: `<lead>-r3-morning-reminder`, `<lead>-r4-1h-reminder`). The two Dawnn one-shots (dawnn-r3-morning-reminder, dawnn-r4-1h-reminder, Oct 5) were paused on Oct 5 and are stale; they can be deleted when COO says.

## Org v3 changes (approved 2026-10-21)
- I own every lead from "times offered" on: no pick after 1 business day gets a times-refresh draft from approved copy; a booking gets confirmation plus the pre-call brief.
- Tasks come from the Cold Email Manager, including LinkedIn bookings (state/handoffs/<YYYYMMDD_HHMM>_<lead>_linkedin_booking.json, pinged by the LinkedIn Outreach Manager to the Cold Email Manager).
- Sender duty: I send booking confirmations and reminders on Lorenzo's yes (KILL_SWITCH, 7 AM to 7 PM CT, own thread, same inbox, one retry max, sent_log.jsonl).
- Routine (CT): stalled decision 8:15 AM; proposed "times offered, no pick" check 11:00 AM weekdays.
- Leak checks: every booked call has a Zoom meeting, calendar event with Meet stripped, Locked-in confirmation and pre-call brief; every held call has an outcome within 24h.

## 3. Processes
### Booking (Zoom-only, hard)
1. Create the Zoom meeting in the Zoom web UI (box browser; computerUse) with topic, start CT, duration and invitees. Capture join URL, meeting id, passcode.
2. Google Calendar connector `create_event` on [REDACTED]: location = Zoom URL, description "USE ZOOM ONLY" + join link + id + passcode, attendees, addGoogleMeetUrl false, notificationLevel NONE.
3. Meet still auto-attaches. Strip it in the Calendar UI: Edit, Remove conference (`button#xRemRtcBu`), Save, Don't send. Calendar MCP cannot remove conferenceData. API alternative: PATCH conferenceData null with conferenceDataVersion=1&sendUpdates=none.
4. Verify with `get_event`: conferenceData {}, no conferenceUrl, location is Zoom. Only then notify the lead.
5. Write the case file (state/cases/<lead>_booked_<date>.json) and the precall queue file.
- Duration: book the real length (pricing and longer discovery 30-60 min). 15 min only when Lorenzo says so.
### Confirmation
- Instantly reply in the lead's thread from the same inbox, under "Re: <thread subject>". `reply_to_uuid` = the lead's NEWEST INBOUND email id, never our outbound (an outbound uuid sends to lorenzo@ itself). `to` = the lead/thread address (info@ when that is the pattern).
- Locked-in text with Zoom link. Never a 15-minute promise.
### Reminders (conditional, ask-first)
- Schedule per booked-calls.md: 24h+ out gets R2 -24h and R4 -1h; later but not same day gets R3 morning-of and R4; same day gets R4. R2 skipped on weekends or outside 07:00-19:00 CT.
- Before arming or drafting any R2/R3/R4: re-read the Instantly thread. Any lead reply after a check-in cancels all later reminders and deletes their routines. Short confirms ("okay", "yes") need no reply. Reschedule or cancel starts a new ladder. Never send because a timer fired.
- Each fire produces a hold (draft + payload file). Sent only on Lorenzo's yes: `~/advero/bin/instantly reply <payload.json>`.
### No-show
- Read THAT lead's calendar event for the weekday/time; never copy another lead's day and never trust GHL Call Time alone. N1 needs Zoom join data; otherwise start only when Lorenzo marks the no-show.
### Stalled-lead decision (Lorenzo 2026-10-21)
1. Revenue Operations flags leads quiet on every channel into ~/advero/state/stalled/queue.csv and pings me.
2. For each status=new row, review the client file, Instantly thread (read-only), Upwork notes, LinkedIn log, case files, and teammate docs.
3. (A) Reactivation: append to the 'Reactivation' tab of the CRM sheet 'Advero CRM & Accountability' (162UL8KgMo2U--ArMl0ieBE19LqcOWjmkYdFbBbqXj9s), same columns, type = 'stalled', next contact = today + 3 months unless the file suggests sooner, status "reactivation queued - stalled". Lorenzo loads Instantly himself.
   Never write to the Lead Pool Reactivation tab.
   (B) Lorenzo call (warm signal, past call, Upwork client, big account, unclear): one-line hold card to COO.
4. Log a dated line in the client file and update INDEX.csv; set the queue status to reactivated or lorenzo. No emails, Upwork or LinkedIn messages.
5. Only yeses rule (Lorenzo 2026-10-22 9:27 AM CT): a stalled lead whose last message is a plain no, unsubscribe, block or pause is routed (nurture, suppression, lost or sequence stop per cold-email-replies.md) and logged, not held. No hold card for it.
### Shared client context
- Before acting on a lead: grep ~/advero/state/clients/INDEX.csv and read the client file. After acting: append a dated log line and update INDEX.csv (flock .lock).

## 4. Rules and limits
- Never send to a lead without Lorenzo's yes (draft mode default). Only approved-template text unchanged since approval may go without his review, and no booked-call template is approved yet.
- Out-of-office leads (Lorenzo 2026-10-21 12:19): never send or draft manual follow-ups, even after they return. They are only emailed again if Lorenzo restarts them in the sequence himself.
- Email only. No texts, calls or pre-reads. Lorenzo sends calendar invites. Booking link: allowed in reply drafts that offer two open times, per pack file 02 s10 and file 04 rule 5 (Oct 20). Nowhere else. Discovery call is 15 min per file 01, but never promise a length in Locked-in confirmations.
- Never talk price, guarantee or numbers over email.
- No em or en dashes, no exclamation marks, no emojis, no Claudeisms. Signed "Lorenzo".
- Zoom only. Never Meet alongside Zoom.
- Send window 07:00-19:00 CT.
- Booked-call reminders were paused by Lorenzo on Oct 5 ("no reminders Mon Oct 5"). Whether that pause still holds is unconfirmed: ask COO before arming any new reminder.
- Check ~/advero/state/KILL_SWITCH before live ops.
- ONLY YESES RULE (Lorenzo, voice call with COO, 2026-10-22 9:27 AM CT). Unsubscribes, blocks, plain no's and pauses from any lead are routed automatically to nurture, suppression, lost or a sequence stop per cold-email-replies.md, and logged. No hold card goes to COO or Lorenzo for them. Only yeses get flagged: interest, a call, or a question toward a call. The never-rules still apply: no sends without approval, and no campaign, list or inbox changes.
- ONE YES RULE (Lorenzo 2026-10-22 9:22 AM CT, 'Yes, my yes in COO chat counts for every bot, no second ask'). A yes Lorenzo gives in the COO chat, relayed by COO with his exact words and time, is approval. It covers only what his words cover.

## 5. Decisions log (append-only)
- 2026-09-23: Email only, never a booking link, earlier times "taken", replies in-thread only.
- 2026-09-24: Never talk numbers over email.
- 2026-09-25: No em/en dashes in outbound. No-show weekday must come from that lead's own calendar event (Ilmi N3 wrongly said Thursday).
- 2026-09-28: Reminder ladder is conditional; a lead reply cancels later touches.
- 2026-09-29: Instantly reply_to_uuid must be the lead's newest inbound (F1 self-send incident). Never put a 15-minute promise in Locked-in. Zoom-only invites; strip Meet before notifying.
- 2026-09-30: Ilmi Mon Oct 5 pricing call, Lorenzo approved reading B (literal 2:00pm ET = 1:00pm CT). I booked Zoom + calendar; COO sent Locked-in and armed R3/R4.
- 2026-10-04/05: Dawnn R3/R4 confirmed armed, then paused on Lorenzo's "don't send reminders today (Mon Oct 5)".
- 2026-10-05 09:16 CT: Lorenzo cancelled Ilmi's Oct 5 pricing call (not enough stuck-proposal volume for a performance deal; free-work risk; should have been flagged on discovery).
- 2026-10-06: Follow-up process doc: Appointment Setter owns discovery, COO owns pricing; reminders listed as paused.
- 2026-10-21: Running role doc rule (this file).
- 2026-10-21 11:00: COO: the canonical reactivation list is the CRM sheet's Reactivation tab (162UL8Kg...), type 'stalled'. Not the Lead Pool tab. Routine prompt updated.
- 2026-10-21 10:59: Lorenzo approved deleting the stale paused Dawnn R3/R4 one-shots. Both deleted. Dawnn Oct 5 outcome and the reminder-pause question are with Lorenzo via COO.
- 2026-10-21 10:58: Stalled-lead flow: I own the decision step (reactivate to the Lead Pool Reactivation tab, or a hold card to Lorenzo via COO). Routine created at 8:15am CT on weekdays.
- 2026-10-21 10:57: Cross-reference rule: check clients/INDEX.csv and client file before acting, log back after. Baked into skills/booked-calls.md (Shared client context section) and required in every new reminder routine prompt.
- 2026-10-21 11:20: First stalled queue run (RevOps flag 11:14): 0 reactivated, 3 to Lorenzo (Ignacio/Aria: asked to touch base in Oct, promised check-in unsent; Tiffany/Flowerhill: price question answered with call offer, no reply; Adrilani: live Upwork Coordinator cadence, T6 10-26). Reactivation tab already has a Type column (E), so no rows written.

- 2026-10-21 12:21: Lorenzo rule: no manual follow-ups to OOO leads. Juan Carlos (TIG) and Brad (pimnj) OOO return cards cancelled, never sent.
- 2026-10-21 12:20: Correction (Cold Email Manager): per pack files 02 s10 and 04 rule 5 (Oct 20), Lorenzo's booking link is allowed in reply drafts that offer two open times. The 2026-09-23 'never a booking link' rule is superseded for those drafts. The no-15-minute rule applies only to Locked-in confirmations.
- 2026-10-21 12:15: Now report to Cold Email Manager (org chart approved 2026-10-21); hold cards go up through Cold Email Manager to COO. OOO return cards for Juancarlos and Brad drafted. offered_times cleaned for Angela Haskins and Leonardo Herrera. Times-refresh hold cards pending the Copywriter template.
- 2026-10-21 12:26: Times-refresh hold cards (booking.times_refresh, word for word) for Angela Haskins (Thu Oct 22 2:00pm CT, Fri Oct 23 1:00pm CT, written in ET) and Leonardo Herrera (Thu Oct 22 3:00pm CT, Fri Oct 23 2:00pm CT, written in PT), planned send Thu Oct 22 9:00am CT. Neither lead replied since the Oct 20 times email. Cards built for COO; nothing sent to the leads. Slots logged proposed in offered_times.jsonl.
- 2026-10-22 09:22: ONE YES RULE (Lorenzo, 'Yes, my yes in COO chat counts for every bot, no second ask'). A yes Lorenzo gives in the COO chat, relayed by COO with his exact words and time, is approval, covering only what his words cover. Added to Rules.
- 2026-10-22 09:27: ONLY YESES RULE (Lorenzo, voice call with COO). Unsubscribes, blocks, plain no's and pauses are routed per cold-email-replies.md and logged, no hold card. Only yeses (interest, a call, a question toward a call) get flagged. Never-rules unchanged. Added to Rules and the stalled-lead section.
## 6. Ongoing work
- No live bookings or armed reminders on my side as of 2026-10-21.
- Open: Dawnn Clisby (Dc Workforce Solutions) Oct 5 11:00 CT discovery outcome is not logged in my files. Need COO/Lorenzo to confirm held, no-show or rebook.
- Open: confirm whether the Oct 5 reminder pause is permanent or was for that day only.
- Open: Ilmi and Dawnn have no client files under ~/advero/state/clients/ yet; create them on next touch.
- Note: cold campaigns are live (per Cold Email Manager 2026-10-21), so new inbound and bookings are expected.

## 7. Files and state
- Skills: ~/advero/skills/booked-calls.md (copy, timing, Zoom-only SOP), cold-email-replies.md, quiet-lead-followup.md, sales-call.md, lorenzo-voice.md, claudeisms.md, grok-operator.md.
- Process doc: ~/advero/state/handoffs/20261006_followup_process.md (Google Doc 1QUHhH2oJR9sLXubiOI03iM-I6Mk7HdQHmDhRzbrXkKE).
- Cases: ~/advero/state/cases/<lead>_* (e.g. ilmi_booked_20261005.json, dawnn_booked_20261005.json). Queue: ~/advero/state/queue/<lead>_precall_<date>.json.
- Logs: ~/advero/state/decisions.jsonl, ~/advero/state/sent_log.jsonl.
- Tools: ~/advero/bin/instantly (Instantly reply from payload), ~/advero/bin/ghl.
- Instantly inbox for cold threads: [REDACTED] Calendar: [REDACTED]
- GHL: pipeline stages New Reply, Call Booked, Follow Up Later, Lost; Sequence field (booked / reply_waiting).

## 8. Handoff notes
- Start by reading booked-calls.md in full, then this doc's section 3.
- Every customer email is a hold until Lorenzo says yes, relayed by COO.
- The two traps that bit us: Instantly reply_to_uuid pointing at our own outbound, and Google Meet auto-attaching to calendar events. Check both every time.
- Booking needs the box browser (Zoom web UI and the Calendar UI Meet strip); background executors cannot drive it.
- Calendar auto-add Meet setting could not be found in Calendar settings (Sep 29). Until Lorenzo turns it off, the strip step is mandatory.

## Shared context
- revenue-operations.md: feeds ~/advero/state/stalled/queue.csv.
- upwork-coordinator.md, linkedin-outreach-manager.md: Upwork and LinkedIn history for stalled-lead review.
- coo.md: approvals, pricing-call ownership, hold cards, reminder pause status.
- copywriter.md: approved copy changes for confirmation/reminder/no-show templates.
- revenue-operations.md: GHL stage and field rules.
- deliverability-specialist.md: inbox and campaign status (affects inbound volume and which inbox a thread uses).
- ~/advero/state/clients/: per-lead context before any booking or reminder.

- 2026-10-22 21:26 CT: Lorenzo (direct, Appointment Setter chat): "A yes from the coo counts as a yes from me". COO approval alone now counts as Lorenzo approval (widens ONE YES RULE). His stops and later words win; never-rules still apply.

## Global rules
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

## Audit changes 2026-10-22 9:30 PM CT (COO)
- Your routines were paused at the 9:30 AM stop. Resuming them is Lorenzo's call (his approval cards). Until then COO keeps a backup of time-critical items, such as Leonardo's pre-call brief at ~/advero/state/clients/leonardo-herrera_precall_brief_20261023.md.
- Log every send in sent_log.jsonl in the same step (Leonardo's Locked-in send was missing).
- Post-call: 30 minutes after each call's end time, send COO (priority) one line asking for the outcome.

- 2026-10-22 23:22 CT: Lorenzo standing rule (relayed by COO): missing reminder setup is "another leak that should've been auto setup". Every booked call gets reminders armed automatically at booking, without waiting to be asked.
- 2026-10-22 23:24 CT: Lorenzo (COO chat, relayed by COO 23:25): "No asking and we only need to mention his time not ours" and "No zoom link". R2/R3/R4 auto-arm with no yes needed, using the no_call_link variant with the lead-local time only. All pre-send checks and reply-cancels-later-touches still apply. Logged in state/approvals.jsonl and skills/booked-calls.md. First use: Leonardo R3 Fri 10:30 AM CT, R4 1:00 PM CT.
- 2026-10-22 23:26 CT: Lorenzo "No questions": final R3/R4 wording (no link, lead-local time, no questions) in booked-calls.md; Leonardo routines updated to it. R2 skipped until no-question text approved.
- 2026-10-22 23:28 CT: Lorenzo changed standing R4 to "See you in an hour. I'll be on a couple minutes early." Leonardo R4 routine updated.
- 2026-10-23 11:22 CT | Standing rule (Lorenzo, COO chat 11:00 AM CT, relayed by Cold Email Manager): "Tiffany needs to be moved to a nurture sequence sep leads are now updated and have had no follow ups we are prioritizing October and newer". September leads get no follow-up cards and no stalled-queue hold cards; they go to nurture. October and newer leads get priority. Tiffany and Ignacio cards dropped (queue rows set to nurture by CEM); Tiffany's held Mon Oct 26 3 PM / Tue Oct 27 1 PM CT slots released 11:04 CT, never sent.

## 24/7 autonomous ops and no-show template
See LEAN_ORG.md sections E and F (verbatim template there). My duty: send the Day 1 times email and the no-show template as those sections say.
