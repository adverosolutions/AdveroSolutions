# Assessment - GoHighLevel Automation Expert Needed (private)

## Time
- Audit of existing workflows (triggers, re-entry settings, goal events, tags that fire other workflows): 4 to 8 hours, depends on how many workflows they have (unknown).
- Rebuild the core journey (entry and missed-call text back, one owner follow-up workflow with stop rules, booking reminders and after-appointment follow-up, pipeline moves, routing and internal notifications): 10 to 16 hours.
- Full-journey testing with test contacts across form, missed call, reply, book, no-show and DND paths, plus fixes: 4 to 6 hours.
- Total about 18 to 30 hours, 1.5 to 3 calendar weeks with their review in between. Ongoing work after that.

## Likelihood
- High for the build itself: everything asked is native GHL (workflow triggers, if/else, goal events, "remove from workflow", DND, calendars, opportunities, internal notifications).
- What breaks: hidden cross-triggers (a tag or stage added in one workflow fires another), "allow re-entry" left on, multiple forms mapped to the same trigger, reply detection across SMS and email, calendar reminders duplicated by both the calendar's own notifications and a workflow.
- Missed-call text back needs a GHL/LC Phone number with call forwarding set up; A2P 10DLC status unverified (they hired an A2P specialist in 2026-07, so likely done, confirm). Unregistered SMS gets filtered, which would look like "the workflow broke".
- Unverified for Lorenzo: size and state of their account, whether they use LC Phone or Twilio, sub-account access level. Lorenzo has not seen this account; the chart describes how he would structure it, not a claim about their current setup.

## Standard pricing
- Market for a GHL workflow audit plus rebuild of a lead journey at this depth: about $1,000 to $2,500 fixed, or $35 to $75/hr for an ongoing GHL specialist. Recurring: their existing GHL plan and SMS/email usage, nothing new.
- Post rate: "$5 (placeholder budget)" and recorded bids of $5. Their history is $95 across 12 hires, so expect price pushback; this is far under market, the real number gets set in chat.

## Ask before quoting
- How many workflows are live now, and which ones send SMS or email?
- Which forms, surveys and calendars feed leads in, and how many pipelines and stages?
- LC Phone or their own Twilio, and is A2P 10DLC approved?
- Who should leads route to (one person, round robin, by source)?
- An example of a duplicate message or an after-booking follow-up that already happened.
- Collaborator or agency-level access to the sub-account?

## Flags
- $5 placeholder budget; frequent low-spend hirer.
- They ask for "a GHL automation you've built or fixed that required more than just a simple trigger -> action workflow": answer from Lorenzo's own facts only, no invented past project.
- Client listed in Nigeria with a New York timezone; no location claims either way.
- Sharp point also on the chart (step 3, step 10) and in beat 4: duplicates come from two workflows on one trigger, so one workflow owns each lead.
