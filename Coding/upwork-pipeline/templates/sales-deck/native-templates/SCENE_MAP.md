# Private sales scene map

Each Quick pitch has 4–5 stops including cover and closing. Spend roughly
10 seconds opening, 20–35 seconds on each proof screen, and 10–15 seconds
on the reply/call ask; expand the narration for longer recordings.

## ghl

Opening: An enquiry comes in. Someone still has to assign it, create the opportunity and respond.
- ghl-workflow: The form assigns Maya, creates Avery in Contacted and sends both messages.
- ghl-messages: This is the SMS asking Avery about Thursday, followed by the acknowledgement email.
- ghl-pipeline: Here is Avery’s opportunity, assigned to Maya, with confirmation still pending.
- Closing: Reply here and I’ll send times for a 15-minute call.

## n8n

Opening: An enquiry arrives as a webhook. The team needs a usable CRM record.
- n8n-canvas: The enquiry comes through the webhook; these requests create the contact and opportunity.
- n8n-node: The returned record has Avery’s contact ID, the estimate value and an open status.
- Closing: Reply here and I’ll send times for a 15-minute call.

## zapier

Opening: Each new enquiry needs a spreadsheet record and a customer response.
- zapier-editor: This Zap catches the enquiry, creates the sheet row and sends the email.
- zapier-test: Row 42 keeps Avery’s name, email and estimate value together.
- zapier-email: Here is the email Avery receives, with Maya arranging the next step.
- Closing: Reply here and I’ll send times for a 15-minute call.

## claude

Opening: Confirmed details arrive in notes. Dispatch still needs a complete, checked brief.
- claude-skills: These instructions require a source for the visit details and flag missing information.
- claude-output: The brief keeps the confirmed time and gate note, and flags the missing address.
- Closing: Reply here and I’ll send times for a 15-minute call.
