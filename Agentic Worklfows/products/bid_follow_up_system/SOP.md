# SOP: Bid and sales-request follow-up system

**Internal.** Client-facing copy is `loom_script.md`.

## What it is

A contractor sends a quote and then the quote sits there. The customer meant to reply, then a week went past, then someone else turned up who chased. This system chases for them: eight touches over fourteen days, email and text, in the owner's voice, stopping the moment the customer replies.

The same engine sells twice. Bids, for anyone who quotes work. Sales requests, for anyone whose website form fills up faster than they answer it.

## Proven on

Delivered as five n8n workflows plus a Google Sheet and Twilio to a construction client for 528.64 dollars. `bid-follow-up-system.n8n.json` in this directory is that build, consolidated into one workflow with five lanes and with the client's name and contact details replaced by placeholders. 46 nodes.

Three GHL draft workflows exist for the same product in the live location: "Your Bid Follow-Up System" `d58ae7f9-4768-4be0-ab99-9f5cd6ca9388` and the two sales-request drafts recorded in `config/ids.json` under `sales_request_follow_up_demo`. They are demos, and they are drafts. Do not publish them into a client's account. The blueprint's GHL snapshot for this kit is **not built yet**, so the deliverable is the n8n workflow below and nothing in GHL.

## Pricing

**Internal, and not yet in `config/offers.md`.** 1,500 to 2,500 setup, 300 to 500 a month for maintenance, from Blueprint F2.

The 528.64 was an Upwork price on an Upwork job, set to win the contract and the review. It is not the price of this product and it must never be quoted as one. Until these numbers are in the offer sheet they do not go in writing to anyone.

## What the client provides

Where bids currently land (website form, an email notification, or typed in by hand), the address the follow-ups should come from, a phone number for the texts, their eight touches or permission to write them, and their own 10DLC registration if texts are in scope.

## The deliverable

| File | What it is |
| --- | --- |
| `bid-follow-up-system.n8n.json` | The workflow. Import, set the Config node, connect credentials |
| `templates.csv` | The eight touches. Loaded into the Templates tab of the client's sheet |

### The five lanes

| Lane | Trigger | What happens |
| --- | --- | --- |
| Intake | Website form webhook, or a parsed notification email | Normalises the bid and writes a row in the Bids tab |
| Scheduler | Hourly, 09:00 to 17:00 Monday to Friday | Reads Bids and Templates, works out which touches are due, sends the email or the text, writes back |
| Text reply | Twilio inbound webhook | Matches the number to a bid, marks it replied or opted out, tells the team |
| Email reply | Gmail trigger on the inbox | Matches the sender to a bid, marks it replied, tells the team |
| Daily summary | 08:00 daily | One email: what went out, what came back, what is still open |

### The Config node

Ten values, set once: `sheet_id`, `business_name`, `owner_name`, `owner_phone`, `from_email`, `team_email`, `team_phone`, `twilio_from`, `timezone`, `no_response_grace_days`. The node's eleventh field, `lane`, is filled in by the workflow and is not edited. Everything else reads from those. A client who renames themselves changes one node.

The one exception is the clock. The two schedule triggers (hourly 09:00 to 17:00 Monday to Friday, and the 08:00 daily summary) run on the workflow's own Settings timezone, which ships as `America/Chicago`, not on the Config `timezone`. For a client outside Central time, change both.

### The sheet is the source of truth

Two tabs. **Bids** is the tracker: one row per quote, with the status. **Templates** holds the copy and the cadence, one row per touch, with an `enabled` column. The client edits copy in the sheet, not in the workflow, which is the whole reason they can run it without Lorenzo.

Any status other than Sent or Following Up stops that customer's touches. That is the client's own kill switch and it is worth showing them on the handover call.

### The cadence in `templates.csv`

Eight touches across fourteen days: email day 1, text day 2, email day 3, text day 5, email day 7, text day 9, text day 12, email day 14. The last email closes the file and says the price holds for thirty days, which is the one that gets replies.

**The four SMS rows ship with `enabled` FALSE, and that is not an oversight.** It is the same prevention this SOP's own failure table names: texting from an unregistered number ends in carrier filtering and then a suspended number. Flip them to TRUE on the day the client's 10DLC registration is confirmed, not before, and never as part of the initial load. Every SMS body carries "Reply STOP to opt out" because the opt-out line is a carrier requirement on every message, not only the first.

## Build, day by day from the kickoff call

| Day | Step | Watch for |
| --- | --- | --- |
| 0 | Map the current flow | Where requests actually land today. Owners are often wrong about this |
| 1 | Build the sheet from the template | |
| 2 | Load their copy into Templates | Their words. The defaults are a starting point, not a deliverable |
| 2 | Import the JSON, set Config | |
| 3 | Connect Google, Gmail and Twilio | Texts stay off until their 10DLC is registered. Do not enable them and hope |
| 3 | Three fake bids through every lane | Including a reply, to prove the sequence stops |
| 4 | Client watches one run end to end | |
| 5 | Go live, hand over the sheet | |

## How it goes wrong

| Failure | What it looks like | Prevention |
| --- | --- | --- |
| Texts sent before 10DLC clears | Carrier filtering, then a suspended number | `enabled` FALSE on every SMS row until the registration is confirmed |
| A reply that does not stop the sequence | The customer replies, then gets a chasing text two days later. This is the one that loses the client | Test the reply lanes before the send lanes. Both of them |
| Timezone drift | Texts at 6am | `timezone` in Config **and** the workflow's Settings timezone, which the schedule triggers use. The hourly scheduler is business hours only |
| The sheet gets reorganised | Someone renames a column header or a tab, and reads or writes quietly miss the field | The workflow finds tabs by name and columns by header, so adding a column is safe and renaming one is not. There are no named ranges. Say it out loud on the handover call |
| Follow-ups from the wrong address | Replies go to an inbox nobody reads | `from_email` and `team_email` are different fields for a reason |

## Redeploy time

Half a day of building, five days of elapsed time because of credential access and the client approving copy.
