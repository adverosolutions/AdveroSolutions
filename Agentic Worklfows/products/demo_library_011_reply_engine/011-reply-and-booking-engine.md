# 011 Reply And Booking Engine

Turns a reply to a cold email into a booked call, with a person approving the first answer and nothing sending outside business hours.

**What comes in:** A reply to an outbound email: whatever the person typed, the thread it belongs to, and which sequence it came from.
**What goes out:** A drafted answer waiting for approval, a pipeline row moved to the right stage, and a call held on the calendar.

**Pick this when** the posting says: reply handling, lead response time, speed to lead, inbox management for outreach, appointment setting, follow up on interested leads, booking calls from email

**Don't pick this when:** It is a contact form on a website with no sequence behind it, that is 001. It is triaging a general inbox rather than replies to a known sequence, that is 002. It is moving an existing booking, that is 004.

## Node map

| Node | Type | What it does |
| --- | --- | --- |
| New Reply | Webhook | Catches the reply event from the sending platform. A scheduled read of the same inbox stands in while no webhook exists. |
| Claim This Reply | Data Store | Claims the reply id before anything else runs. Two copies of this running at once must produce one answer, not two. |
| Read The Reply | Code | Strips the quoted thread below the reply, blanks phone numbers, and keeps only what the person actually wrote this time. |
| Sort The Reply | Language model | Interested, a question, not now, not a fit, wrong person, out of office, or hostile. Returns a confidence with the label. |
| Sure Enough? | Switch | Under the confidence line, it goes to a second, stronger pass rather than guessing. |
| Hostile Or Remove | Code | Stop, remove and unsubscribe never get an answer. Blocklist and do-not-contact the same day, and no draft is written. |
| Out Of Office | Code | Reads the return date out of the message and parks the sequence until then. |
| Find Two Times | Code | Two real openings from the calendar: afternoons only, at least four hours out, inside five working days, and never a slot already offered to somebody else today. |
| Write The Answer | Language model | Answers the question first, in two sentences, then offers the two times. Prices and proof come from one approved sheet, nothing else. |
| Check The Draft | Code | Rejects a draft that invents a number, misses the sign-off, or writes outside the approved answers. A rejected draft is not sent, it is escalated. |
| Ask The Owner | Push notification | The draft, with approve and change. The first answer to an interested person is never sent without a person seeing it. |
| Send In The Thread | Email | Same thread, same address the first email went from. Business hours only. |
| Move The Pipeline Row | CRM | Interested, booked, not now with a date, or lost with the reason. |
| Book It | Calendar | Creates the call, and the confirmation and reminders run from there. |
| Chase For Seven Days | Schedule | An interested person who goes quiet gets a touch a day for a week, then stops. |
| Nothing Happened | Code | Names the step that stopped it and who has to look, rather than failing quietly. |

## Stand-in swaps

| On the canvas | Stands in for |
| --- | --- |
| New Reply | Any sending platform's reply event, or a scheduled read of the inbox |
| Move The Pipeline Row | GoHighLevel, HubSpot, Pipedrive, Close |
| Book It | The owner's own calendar, or a scheduling tool's booking link |
| Ask The Owner | Push, text, Slack, or an email with two links |
| Sort The Reply | Any model. The labels and the confidence line matter, the provider does not |

## Assumptions to verify

- The reply event carries the thread id and the address the original email was sent from. The answer goes back in the same thread from the same address, and without both of those it cannot.
- Prices and proof points come from one approved sheet. The draft step reads it and rejects anything that quotes a number not in it. Without that sheet, this should not run.
- The first answer to an interested person waits for approval. That is a decision, not a limitation. Everything after the first answer can run unattended once the owner trusts it.
- Sending hours, the offered window and the booking horizon are settings, and they are the settings most often wrong on the first build. Confirm them before go-live, not after.
- Two of these running at once (a webhook and a scheduled read seeing the same reply) will both try to answer unless the claim step is a single operation. It is the least visible part of the build and the most expensive to get wrong.

## Where it is proven

Lorenzo built it for Advero's own outbound. It has been running in shadow since 2026-09-21: it proposes and logs everything, and nothing reaches a live system until each piece is signed off. Code in `services/reply_engine/`.
