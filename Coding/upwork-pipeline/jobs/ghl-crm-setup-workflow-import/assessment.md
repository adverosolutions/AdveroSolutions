# Assessment (private, never in the proposal)

## Time
- This one workflow in his account: 1 to 2 hours including a test contact run.
- Their real ask (full CRM setup: forms, pipeline stages, tags, several workflows for follow-up, tasks, notifications, nurture, testing): 15 to 25 hours, 1 to 2 calendar weeks, most of it waiting on their answers about stages, sources and who owns which lead.

## Likelihood
- High for the workflow itself. Every step type here has imported before in his sub-account.
- The gate reads one tag, lead-engaged. In their build, a small companion workflow (customer replied -> add tag lead-engaged) and the calendar's booking action set it. That companion is not in this prop; on camera, add the tag to the test contact by hand to show the Yes path.
- Unverified: whether their A2P/10DLC registration is done. Without it the texts do not send. Email needs their sending domain set up in LC Email or Mailgun.
- The form trigger has no form filter, so it fires on any form in the account. Pick their lead form in the trigger after import.
- Task assignee is "contact's assigned user": leads with no owner get tasks with no assignee unless they add round robin assignment.

## Standard pricing
- Market for a GHL CRM setup at this scope: $750 to $2,500 fixed, or $40 to $90 an hour. The post's $50 is a placeholder and far under market; the client has 206 contracts at about $38 each on average, so expect price pressure.
- Recurring: their GHL plan (they already have it); SMS and email usage billed by GHL.

## Ask before quoting
- How many lead sources and forms (website, Facebook, calls)?
- Their pipeline stages today, and who owns each lead?
- Monthly lead volume and team size.
- Is A2P registration done, and which email sending domain?
- Do they book calls in a GHL calendar?

## Flags
- Post asks for hourly rate and fixed budget: never answered in the proposal, that is for the call.
- Post asks for an example of a GHL automation: this workflow is the example.

## Lorenzo makes by hand
- Pipeline "Upwork Demo - Lead Pipeline" with stages, in order: New Lead, Engaged, Won, Lost. The key cannot create pipelines (401), so make it in Opportunities -> Pipelines before the prereqs dry run, then rerun the dry run to refresh the id map.

## What ghl_prereqs will create (dry run first)
- Tags: website-lead, lead-engaged (both new).
- Custom field: Lead Source (already exists, reused).
- Custom value: booking_link, which should resolve to the existing "Booking Link" value; if the dry run lists it as new, check the key match before applying.
- Pipeline: listed as needed; refused by the key, made by hand as above.
