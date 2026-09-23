# Deliverable: GHL snapshot "Advero Reactivation"

A GHL snapshot is exported from a sub-account and loaded into the client's. This describes what the snapshot must contain. **It has not been created:** GHL snapshots are made in the UI and nothing here writes to GHL.

Built from the live AdveroSolutions location `ebyNANPagaK7ycf1pfge`, stripping everything specific to Advero's own outbound.

## Pipeline: Reactivation

Modelled on the live Sales pipeline `GCBkIzFpung73cIDVPzn`, renamed for a client who is watching their own list come back.

| Stage | Meaning | Enters when |
| --- | --- | --- |
| Contacted | The sequence has touched them | First send |
| Replied | Any human reply | Reply received |
| Interested | They want to talk | Positive classification or a human marks it |
| Booked | On the calendar | Appointment created |
| Held | The call happened | Appointment status showed |
| Won | Signed | Client moves it, or the client's own CRM does |
| Lost | Explicit no | |
| Later | Not now, with a date | |

Won carries `monetaryValue` = first-year contract value. That field is the invoice basis, so the snapshot sets it required on the Won stage.

## Calendar: Client Consultation

15 minutes, 15-minute buffer, the client's own working hours, auto-confirm on, booking horizon 30 days, minimum notice 4 hours. Assigned to whoever at the client actually takes the call, which is a kickoff-call question and gets it wrong often enough to be worth asking twice.

## Tags

`reactivation`, `reactivation-positive`, `reactivation-booked`, `reactivation-won`, `do-not-contact`, plus one per list source (`lost-proposal`, `former-client`, `cold-enquiry`) so the scorecard can show which slice of the list is producing.

## Custom fields on the contact

| Field | Type | Why |
| --- | --- | --- |
| `first_touch_date` | date | The attribution clock starts here. Written once and never overwritten |
| `last_job_date` | date | How dormant they actually are |
| `last_job_value` | number | Sorts the list, and it is how you pick who gets the calls |
| `list_source` | dropdown | former client, lost proposal, cold enquiry |
| `attribution_deadline` | date | first_touch_date plus 180 days, so a close can be judged without arithmetic |
| `booked_date` | date | Written by the booked workflow below |
| `closed_date` | date | Written by the won workflow below. The scorecard does not read it: it dates a close from the Won stage change |

## Workflows in the snapshot

| Workflow | Trigger | What it does |
| --- | --- | --- |
| Reactivation: reply routing | Customer replied | Moves the opportunity to Replied, tags, notifies whoever owns replies |
| Reactivation: booked | Appointment booked | Moves to Booked, writes `booked_date` |
| Reactivation: held or no-show | Appointment status changed | Moves to Held, or starts the recovery ladder |
| Reactivation: won | Stage moves to Won | Writes `closed_date` and checks `attribution_deadline`, so an out-of-window close is visible on the record rather than argued about later |
| Reactivation: opt out | Reply contains stop, remove, unsubscribe | Tags `do-not-contact`, sets DND, removes from every sequence, same day |

SMS legs stay switched off until the client's own 10DLC registration clears. Advero's is not registered either as of 2026-09-21.

## Email templates

The three sequence emails from `campaign_templates.md`, loaded as templates so the client can read them in their own account.

## What the snapshot must NOT contain

Advero's own campaigns, inboxes, lead lists, proof points or pricing. The Discovery Call calendar `GDugwLmZNdsD13RBDnRu`. Any contact record. A snapshot carrying another client's contacts is the worst thing in this file and it is an easy mistake: export from a clean sub-account, never from the working one.

## Loading it

1. Create the client's sub-account.
2. Load the snapshot.
3. Set the calendar hours and the assigned user to the client's.
4. Import the cleaned list with `first_touch_date` blank. It is written by the first send, not by the import.
5. Send yourself a test through every workflow before the client sees it.
