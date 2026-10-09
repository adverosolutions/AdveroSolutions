# Dossier - GoHighLevel Automation Expert Needed

url: https://www.upwork.com/jobs/~022103543418666995080

## Who they are
- First name: David (from the `client first name:` line)
- Company: unknown
- Industry: unknown. They run a GoHighLevel account with leads, appointments, calendars and pipelines ("We already have things running"); the post never says what they sell. No business type goes on the build.
- Location / timezone: client listed in Nigeria, timezone America/New_York
- Website read: none named

## Client
no client intel

## Tools they named
GoHighLevel (GHL), GHL Workflows, Triggers, If/Else Conditions, Opportunities, Pipelines, Calendars, Tags, Custom Fields, SMS and Email automation. Earlier hire: Twilio A2P 10DLC (so their SMS runs on a registered number).

## Every number in the post
- "Fixed $5 (placeholder budget)", "ongoing if a good fit"
- "more than just a simple trigger -> action workflow" (the one-step baseline they want exceeded)
- Metadata: 12 contracts, 12 jobs with hires, $95 spent, 5.0 over 12 reviews, 75% hire rate, 1 invite, 0 interviewing, recorded bids $5, 8 connects
- No lead volume, workflow count, calendar count or pipeline stage count. Those are their inputs ("your workflows", "your pipeline stages") and go under Ask before quoting.

## Their requirements, verbatim, in their order
1. "Lead follow-up through SMS and email"
2. "Workflows that stop when a lead replies, books, enters an opportunity, or is marked DND"
3. "Appointment reminders and follow-ups"
4. "Pipeline and opportunity automation"
5. "Lead routing and internal notifications"
6. "Forms, surveys, tags, and custom fields"
7. "Missed-call text back"
8. "Conditional workflows and branches"
9. "Reviewing existing workflows for conflicts or unnecessary steps"
10. "Testing the complete lead journey and fixing anything that doesn't behave as expected"

10 parts in the post, 5 sections on the canvas. The canvas follows one lead's journey (as Lorenzo's brief asked), so the entry points they listed 6th and 7th come first:
- Section 1: parts 6 and 7 (forms, surveys, tags, custom fields; missed-call text back)
- Section 2: parts 1, 2 and 8 (SMS and email follow-up, the stop rules, the if/else gate)
- Section 3: parts 3 and 4 (appointment reminders and follow-ups, pipeline and opportunity moves)
- Section 4: part 5 (lead routing and internal notifications)
- Section 5: parts 9 and 10 (review existing workflows, test the full journey)

## The odd ask only they would recognize
"We don't want a workflow that technically works but creates duplicate messages, continues following up after someone has booked, or triggers another automation unexpectedly." Three named failures: duplicate messages, follow-up after booking, surprise triggering. Also: "understands the logic behind GHL workflows, not just someone who knows where to click."

## What their hiring history implies
12 small fixed hires, $95 total, 5.0 reviews, 75% hire rate: a frequent hirer of cheap, quick jobs ($5 placeholder). Past hire of a Twilio A2P 10DLC specialist means SMS compliance is already handled or was a pain point. They judge by whether the thing works when they test it; "ongoing if a good fit" means the first piece is a trial.

## Their likely data
Illustrative only, no business type:
```json
{
  "contact": "Jordan Ellis",
  "phone": "+1 (404) 555-0182",
  "email": "jordan.ellis@gmail.com",
  "source": "Website form",
  "tags": ["new lead", "source: form"],
  "active_follow_up": "Lead Follow-Up (SMS + Email)",
  "replied": false,
  "appointment": "not booked",
  "opportunity_stage": "New Lead",
  "dnd": false
}
```

## Sizing
Not a volume job. The sizing is structural: every duplicate text and every after-booking message they describe comes from one of three causes in GHL: two workflows listening to the same trigger (form submitted, tag added, opportunity created), a tag or stage change in one workflow firing another workflow's trigger, and follow-ups without goal events or a "remove from workflow" on reply/book/DND. Fix: one follow-up workflow owns each lead, and one shared stop rule removes the lead from every follow-up workflow. The workflow count is their input ("your workflows").

## Three things they would recognize on screen
1. Their four stop conditions, in their words, as the gate: "Did They Reply, Book, Enter an Opportunity or Get Marked DND?" (step 4).
2. Their three failures as the test step: "each message once, nothing after booking, no surprise triggers" (step 11) and the review step (step 10).
3. Missed-call text back and forms/surveys/tags as the way in (steps 1 and 2).

## Beat 1 draft
"David, this is reliable follow-up for your GHL account, start to finish."
