# Bid and Follow-Up Automation System (n8n)

One n8n workflow plus one Google Sheet. Import the JSON, connect three credentials, fill in the single Config node, and turn it on.

## What is in this folder

| File | What it does |
|---|---|
| `n8n/bid-follow-up-system.json` | The whole system in one workflow. Five triggers on the left all pass through one **Config** node, and a **Which lane?** switch routes each run to its lane: |
| | **Intake lane.** Website form posts a new bid to a webhook. It is normalized, given a bid_id, and logged in the tracker with status **Sent**. An optional (disabled) Gmail trigger can parse the form's notification email instead. |
| | **Scheduler lane.** Runs hourly, 9am to 5pm Central, Mon to Fri. Sends whichever touch is due for every bid in **Sent** or **Following Up**, then advances the bid. Marks **No Response** three days after the last touch. |
| | **Text reply lane.** Twilio webhook for customer texts. Matches by phone, marks **Replied** (or **Opted Out** on STOP), stops the sequence, alerts the team by text and email. |
| | **Email reply lane.** Watches the sending Gmail inbox. Matches by Gmail thread, then by sender address. Marks **Replied**, stops the sequence, alerts the team. Unrelated mail is ignored. |
| | **Summary lane.** 8am Central daily email: replies in the last 24 hours and every bid still in follow-up with its next touch. |
| `sheets/Bids.csv` | Header row for the **Bids** tab (the tracker). |
| `sheets/Templates.csv` | The **Templates** tab: 4 emails + 4 texts with days and copy. Edit copy and timing here, never in n8n. |
| `build_workflows.py` | Regenerates everything above. Not needed by the client. |

## How the sequence works

The tracker sheet is the source of truth. There are no long-running waits inside n8n, so nothing breaks if n8n restarts and any status change takes effect on the next hourly run.

Default cadence (days after `date_sent`, sent at the first business-hour run at or after 9am CT):

| Step | Day | Channel |
|---|---|---|
| 1 | 1 | email |
| 2 | 2 | text |
| 3 | 3 | email |
| 4 | 5 | text |
| 5 | 7 | email |
| 6 | 9 | text |
| 7 | 12 | text |
| 8 | 14 | email |

Rules the scheduler enforces:

- One touch per bid per run, never two on the same day. A late-entered bid gets its next touch the next business morning, not all at once.
- A step is skipped (not sent) when the bid has no phone for a text step or no email for an email step.
- Only rows with status **Sent** or **Following Up** are touched. Any other status (Replied, Booked, Declined, No Response, Opted Out) stops the sequence instantly. Change the status by hand in the sheet to pause or stop a customer.
- To restart a customer, set status back to **Sent** and `touch_index` to 0 (or to the step you want to resume from) and clear `next_touch_at`.
- `opt_out` = TRUE also stops everything, regardless of status.

Template placeholders: `{{first_name}}`, `{{customer_name}}`, `{{project}}`, `{{bid_amount}}` (formatted as $18,500), `{{business_name}}`, `{{owner_name}}`, `{{owner_phone}}`. Set `enabled` to FALSE on a Templates row to drop that step without deleting it.

## Setup (about 30 minutes)

### 1. Google Sheet
1. Create a new Google Sheet named `Bid Tracker`.
2. Rename the first tab **Bids** and paste the header row from `sheets/Bids.csv` into row 1.
3. Add a second tab named **Templates** and import `sheets/Templates.csv` into it (File > Import > Upload > Replace current sheet).
4. Copy the sheet ID from the URL (the long string between `/d/` and `/edit`).

### 2. Import the workflow
In n8n: Workflows > Add workflow > Import from File > `bid-follow-up-system.json`.

### 3. Credentials (one time each, n8n picks them up in every node)
- **Google Sheets OAuth2** with the Google account that owns the tracker.
- **Gmail OAuth2** with the business email the follow-ups send from.
- **Twilio** with Account SID and Auth Token from the Twilio Console home page.

Open each workflow and click through the red-bordered nodes to select the credential. n8n remembers the choice per node type.

### 4. Config node (one node, edit once)
Open **Config** (the node every trigger feeds into) and fill in:

| Field | Value |
|---|---|
| `sheet_id` | the ID from step 1 |
| `business_name`, `owner_name`, `owner_phone` | used inside the templates |
| `from_email` | the Gmail address the follow-ups send from (used to ignore your own mail) |
| `team_email`, `team_phone` | where reply alerts and the daily summary go. Phone in +1 format |
| `twilio_from` | your Twilio number in +1 format |
| `timezone` | `America/Chicago` |
| `no_response_grace_days` | days after the last touch before a bid is marked No Response (3) |

Also confirm the workflow's Settings > Timezone shows America/Chicago (the JSON sets it, but check after import).

### 5. Website form
Point the form's webhook / integration at the production URL shown on the **New Bid (Website Form)** node, e.g. `https://YOUR-N8N/webhook/new-bid`, method POST. Field names are matched loosely (Name / Full Name, Phone / Phone Number, Email, Project / Service / Job Type, Amount / Estimate / Total all work). If the form cannot send a webhook, enable the **Form Notification Email** trigger instead and adjust its subject filter.

You can also add a bid by hand: type the customer into the Bids tab with a `date_sent` and status **Sent**. The scheduler takes it from there.

### 6. Twilio connection (do this when your Twilio account is ready)
1. Twilio Console > Phone Numbers > Manage > Active numbers > your number.
2. Under **Messaging Configuration**, set "A message comes in" to **Webhook**, URL = the production URL on the **Twilio Inbound SMS** node (`https://YOUR-N8N/webhook/twilio-inbound`), method **HTTP POST**. Save.
3. Put the number in `twilio_from` in the Config node.
4. With the workflow active, send yourself a test bid and reply STOP from your own phone to confirm the round trip.

A2P 10DLC: US carriers require business numbers to be registered before texts deliver reliably. Twilio Console > Messaging > Regulatory Compliance > Brand + Campaign. Approval is usually 1 to 7 business days. Email follow-ups are not affected.

### 7. Activate
Toggle the workflow Active. The two webhooks go live, the two schedules start, and the Gmail poll runs each minute. To pause one lane (say the daily summary) without stopping the rest, right-click its trigger node and choose Deactivate.

## Test plan (matches the acceptance criteria)

1. **Intake**: POST a test bid (your own phone and email) to the new-bid webhook. Expect a new row with status Sent and a bid_id.
2. **First touches**: temporarily set `date_sent` on that row to yesterday, then click the **Every hour, business hours CT** trigger and choose Test step / Execute. Expect the day-1 email from the business inbox, status Following Up, touch_index 1, next_touch_at tomorrow 9am. Run again after setting `next_touch_at` to a past time to see the day-2 text arrive through Twilio.
3. **Text reply**: reply to the text. Expect status Replied, last_reply_text filled, a text and an email to the team. Run the scheduler trigger again: nothing sends.
4. **Email reply**: on a second test bid, reply to the follow-up email. Same result via the email reply lane.
5. **STOP**: on a third test bid, reply STOP. Expect status Opted Out, opt_out TRUE, team alerted, and Twilio itself blocks further texts to that number.
6. **Summary**: execute the **Every day 8am CT** trigger and check the email.

## Statuses

Sent, Following Up, Replied, Booked, Declined, No Response, plus **Opted Out** for a STOP reply (added so a carrier-mandated opt-out is visibly different from a decline).

## Notes for handoff
- Credentials are not included in the JSON. Nothing depends on the builder's accounts.
- Gmail's send node returns the thread ID, which the tracker stores in `thread_id`. That is how an email reply is matched even if the customer replies from a different address.
- If the business inbox is Outlook rather than Gmail, swap the Gmail nodes for Microsoft Outlook nodes (send + trigger). The rest is unchanged.
