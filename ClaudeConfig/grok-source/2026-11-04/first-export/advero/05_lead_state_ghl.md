
# 05 Where each lead is: GoHighLevel and Instantly

GHL is the record of where a lead stands. Instantly holds the email threads and mirrors the GHL stage as an interest status. Your own files in `~/advero/state/` hold what GHL cannot hold yet.

## 1. GHL location

- Location: AdveroSolutions, id `ebyNANPagaK7ycf1pfge`.
- Ids below are from `config/ids.json`, pulled read-only on 2026-09-21. If GHL shows a different id, GHL wins. Tell Lorenzo.

## 2. The Sales pipeline

Pipeline "Sales", id `GCBkIzFpung73cIDVPzn`. Cold-email leads only.

| Stage | Stage id | Means | Instantly interest to match |
|---|---|---|---|
| New Reply/Lead | `f000f05d-5732-40c1-866a-bd71cd0f95b6` | The lead replied with interest or a question; no call booked yet | 1 interested |
| Call Booked | `f12615dc-66e1-412d-902b-4d1adab812c9` | A discovery call is on the calendar | 2 meeting booked |
| Proposal Sent | `fcf3359e-f8e0-4354-92ee-2d7b396b769e` | The call happened; a proposal or payment link is out | 3 meeting completed |
| Won | `48eca719-502a-46cc-9e39-7db0aeffb41e` | Client signed. Set with status won and the real contract value, never a guessed value | 4 won |
| Lost | `6ce29ed4-fab0-4244-938f-758ef8688cd8` | Said no, unsubscribed, hostile, wrong person, or third no-show. Reason in the lost reason and a note | -1 not interested; -4 when the lost reason says no-show or ghosted; -2 when it says wrong person or no longer with |
| Follow Up Later | `ce219fc8-3caa-45e5-bc81-622a1625a23b` | Not now, or the follow-up ladder ran out. Always with a dated task | -1 not interested |

Rules:
1. One opportunity per contact. If a contact has two, use the one furthest along (Lost, Follow Up Later, New Reply, Call Booked, Proposal Sent, Won) and tell Lorenzo about the other.
2. Never move an opportunity that is in Proposal Sent, Won or Lost, except when Lorenzo says so.
3. A lead with a reply but no opportunity: create the contact and a New Reply/Lead opportunity (skill `cold-email-replies`, step 3). Tag the contact `cold-email`, `instantly-positive-reply`, the niche and the campaign key.
4. Stage dates come from GHL's "last stage change" time, never "updated at".

## 3. Booked calls

- There is no separate "Call Booked" pipeline in `config/ids.json`. Booked calls use the Sales stage Call Booked plus the Discovery Call calendar. Pending, Lorenzo: confirm whether another pipeline for booked calls exists in GHL.
- Discovery Call calendar: id `GDugwLmZNdsD13RBDnRu`, 15-minute slots, Monday to Friday 12:00 to 18:00, bookings at least 4 hours out, auto-confirm on. Conferencing: Zoom (`zoom_conference`, connected 2026-09-25). Primary invite path is still Zoom direct so the lead does not get a second calendar invite.
- Some calls were booked by hand on Lorenzo's Google Calendar (`[REDACTED]`), not through the GHL widget. Read both calendars.
- Pending, not verified against live GHL: whether creating an appointment sends the lead an invite on its own. Until verified, create appointments only with Ask first, and tell Lorenzo to send the invite.

## 4. The Upwork pipeline

- Not created yet. `config/ids.json` has no id for it. Pending, Lorenzo: create a GHL pipeline named "Upwork" with stages New reply, Proposal sent, Call booked, Follow up later, Won, Lost. Then give the ids to the Chief of Staff.
- Until then, the Upwork assistant keeps each room's stage in `~/advero/state/upwork_threads.json`. Never put Upwork clients in the Sales pipeline.

## 5. The five contact fields

Status: **pending creation.** They do not exist in GHL yet. Lorenzo creates them, or tells you to create them with Ask first. Until they exist, write the same five values into a GHL note after every step (section 6).

| Field | Type | Values |
|---|---|---|
| Sequence | Dropdown | `none`, `reply_waiting` (a reply of ours is due or held), `followup` (E1 to E10 running), `booked` (call on the calendar), `no_show` (recovery running), `nurture`, `stopped` (a no, an opt-out, or Lorenzo stopped it) |
| Last Email Sent | Text | Template id of the last email we sent, for example `cadence.e3`. For a first reply Lorenzo sent himself: `first_reply.manual` |
| Last Email Date | Date and time | When it went, CT |
| Next Email | Text | Template id due next, for example `cadence.e4`, or `none` |
| Next Due Date | Date and time | When the next email is due, CT. Empty when Next Email is `none` |

## 6. After every send (and every step with no send)

In this order:
1. Write the send key to `~/advero/state/sent_log.jsonl` (file 02, section 6).
2. Update the five fields from Opus's `field_updates`. If Opus left one out, fill it from what happened: Last Email Sent = the template id, Last Email Date = the send time.
3. Move the stage if `ghl_stage` is not `no_change`.
4. Set the Instantly interest status if `instantly_interest` is not null. Instantly answers 202; that is success.
5. Add a GHL note in this exact format:

```
Sent cadence.e3 on 2026-09-28 10:00 CT from [REDACTED]
Sequence followup. Next: cadence.e4 due 2026-09-29 10:00 CT.
Why: <Opus reason>. Decision cost $0.05.
```

For a step with no send, start the note with what was done: "Recorded reply as negative_notnow. Stage Follow Up Later. Task set for 2026-10-28."

6. Re-read the contact and the opportunity to confirm the writes landed. If one did not, retry once, then tell the Chief of Staff.

## 7. Working out where a lead is

Read these, in this order:
1. GHL opportunity stage and the five fields (or the last note in that format).
2. The Instantly thread: who wrote last, and when.
3. The calendars: any call booked for this lead.
4. `~/advero/state/sent_log.jsonl` for this lead.

Then use this table to pick the `case_type` and the question for Opus. Opus decides what is due.

| What you see | case_type | Question for Opus |
|---|---|---|
| The lead wrote last, and no email of ours came after it | `reply` | "The lead replied. Classify and decide what we do." |
| Sequence `followup` and Next Due Date is today or past | `followup_due` | "Is the next follow-up due for this lead, and which one?" |
| Lorenzo's own first reply is in the thread and Sequence is `none` or `reply_waiting` | `followup_due` | "Lorenzo sent a first reply by hand. Record day 0 and set the next follow-up." |
| A new booking on a calendar, or Sequence `booked` | `booked_call` | "A call is booked. What is due: confirmation, reminder, or nothing yet?" |
| Lorenzo marked a no-show, or Sequence `no_show` | `no_show` | "Which no-show step is due, if any?" |
| Sequence `nurture` | `nurture` | "The lead is in nurture. Is anything due?" (Today the answer is always no.) |
| GHL and Instantly disagree about the stage (you see it here, or the 06:30 pipeline check in file 07, section 8 lists it) | `pipeline` | "GHL and Instantly disagree for this lead. Which is right, and what do we change?" |
| Sequence `stopped`, or the lead is blocklisted or DND | none | Do nothing. Never email this lead. |

## 8. Instantly interest status

Values: 0 out of office, 1 interested, 2 meeting booked, 3 meeting completed, 4 won, -1 not interested, -2 wrong person, -3 lost, -4 no show.

Rules (from `runbooks/pipeline_hygiene.md`):
1. The GHL stage decides the interest status, by the table in section 2.
2. **Negative values are sticky.** Never turn a negative Instantly value back into a positive one unless GHL shows real progress (Call Booked, Proposal Sent, Won) and GHL moved after the negative was set. Never replace one negative with another unless the GHL lost reason names it (wrong person, no show).
3. -4 no show is about attendance, not interest. A no-show who writes back to rebook is handled as a reply.
4. When GHL and Instantly disagree and you cannot tell which is newer, change nothing. Put it in the 06:30 pipeline check for Lorenzo.

## 9. Your own state files

All in `~/advero/state/`. Bots share files. One JSON object per line in `.jsonl` files. Never delete a line: add a new one.

| File | Holds |
|---|---|
| `approval.json` | Lorenzo's "done", "go live" and Ask first settings (file 02, section 9) |
| `KILL_SWITCH` | Exists only while everything is stopped |
| `sent_log.jsonl` | One line per email sent: key, lead, template id, inbox, time, email id |
| `offered_times.jsonl` | One line per time offered: time, lead, offered at, released (true/false) |
| `decisions.jsonl` | One line per Opus decision and what you did |
| `upwork_threads.json` | Upwork room stages until the GHL Upwork pipeline exists |
| `cases/`, `decisions/`, `handoffs/`, `reports/` | Case files, raw Opus outputs, hand-offs between agents, reports |

## 10. Known leads

Last recorded counts, now out of date:
- 2026-09-21: 3 open opportunities in the Sales pipeline (2 New Reply/Lead, 1 Call Booked).
- 2026-09-22: 4 Instantly leads with a positive status; 1 of them had no GHL opportunity.

On day 1, count again from the live systems and report the real numbers to Lorenzo.


---
