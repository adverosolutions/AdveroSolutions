# Private assessment - Automation Expert (HighLevel, Google Sheets, Zapier)

Job: https://www.upwork.com/jobs/~022102065889977755181
Build: Your Sales Rep Scorecard (n8n spec, 18 flow nodes, 5 sections)

## Time
Realistic 8 to 14 hours, spread over 5 to 8 calendar days because most of the
clock is waiting on them: GHL workflow access, a test contact, a real
appointment on the shared calendar, and one night of live data before the
scorecard numbers can be trusted.

- 2 to 3 h: event capture. One webhook plus a GHL workflow per event type
  (new lead, appointment booked/updated, call outcome, contract sent, payment).
- 2 to 3 h: rep resolution. The calendar lookup for the appointment's assigned
  user, the opportunity-owner path, and the unassigned queue.
- 2 to 3 h: the Sheet itself. Events tab, Scorecard tab, one row per rep per
  day, formatting that a sales manager will actually read.
- 1 to 2 h: nightly rollup and ratios, timezone handling, backfill of the
  current week so day one does not look empty.
- 1 to 2 h: error path, Slack alert, handover doc and a loom walkthrough.
- Add 2 to 4 h if they want historical backfill from existing GHL data rather
  than starting the count from go-live.

## Likelihood
Good fit, with three real risks.

1. **GHL API access and plan tier.** Reading the appointment's assigned user
   needs the calendar/appointment endpoint on a v2 API key with the right
   scopes, in their sub-account. If they are on an agency plan that restricts
   this, the fallback is a GHL workflow that writes the assigned user into a
   contact custom field and posts that, which is less clean but works.
2. **Definitions, not code.** "Held", "contracts sent" and "revenue booked" are
   the whole job. If they cannot say precisely what those mean in their GHL
   today, the build finishes and the numbers still get argued about. Pin the
   definitions in writing before quoting.
3. **The client record.** 3.99 over 28 reviews on $111k spent, 82 contracts,
   36 active. The funnel builder contract ended 3.6 with the client giving 1
   star. That is an operator who runs a lot of freelancers hot and is willing
   to leave a 1. Mitigation: scope in writing in the Upwork message thread
   before any work, hourly with milestones or a capped weekly limit, and a
   hard definition of done per stage. Do not start on a vague "make us a
   scorecard" brief.

Honest-framing note: the video shows the logic in n8n because it is importable
and reads cleanly on camera. Say plainly that production can live in Zapier or
GHL workflows plus a Sheets script if they prefer their existing stack, the
decision points do not change. Do not assert a past client GHL-to-Sheets
project that has not actually been done.

## Standard pricing
- Fixed scope: $800 to $2,000 for the build as specced.
- Hourly: $50 to $85/h is the defensible market band for GHL plus Sheets plus
  a real rollup. Post is hourly with no budget shown, bids range 10 to 110,
  which tells us nothing except that the low end is offshore volume bidders.
- Recurring software: $0 extra if it runs on GHL workflows plus Apps Script.
  If it runs in n8n cloud, roughly $20 to $25/mo, or self-hosted for free.
- He bids under this on purpose; this is the reference number, not the bid.

## Ask before quoting
1. Which of these already exist as GHL workflows today: new lead, appointment
   booked, appointment status change, contract sent, payment? Every one that
   does not exist is a workflow I have to build, not just wire up.
2. One shared calendar or several? If several, do all reps sit on all of them?
3. What counts as "held"? Appointment status = showed, a call outcome a rep
   sets manually, or a call length threshold?
4. "Contracts sent" means a document sent from a document/proposal tool, or an
   opportunity moved to a stage? Which stage?
5. Revenue booked: from GHL payments/invoices, or entered by a rep by hand?
6. Which timezone is the day boundary, and what time do they want the nightly
   scorecard to land?
7. How many reps, and do they want a daily Slack leaderboard or just the Sheet?

## Screening answers (two mandatory boxes at submit)

**Q1 - Walk me through one GHL workflow you've built that sends data to Google
Sheets, what it did and how long it took.**

> the build i can actually walk you through is the one i made for this post,
> and it is in the loom. a ghl workflow fires on the event, posts to one
> webhook, the event gets normalized to the same shape whatever fired it, the
> rep is resolved, and it appends one row to an events tab in google sheets
> that a nightly rollup turns into the scorecard. that shape took me about an
> afternoon to lay out; a live one in your sub account is 8 to 14 hours
> depending on how many of those ghl workflows already exist. i run the same
> webhook to sheets pattern on my own business every day, my outbound sends
> 100k+ cold emails a month and the daily metrics scorecard behind it is a
> google sheet written to on a schedule exactly like this one.

**Q2 - A lead is assigned to one rep in GHL but books a call with a different
rep on a shared calendar; how do you make sure the sheet credits the rep who
took the call?**

> you credit the appointment's assigned user on the calendar event, not the
> contact owner. the contact owner is who owns the lead record, the assigned
> user on the appointment is who actually sat on the call, and on a shared
> calendar those are different people all the time. so on an appointment event
> i call ghl for that appointment and read its assigned user, and that is the
> rep the row is credited to. lead events still credit the contact owner, and
> contract and payment events credit the opportunity owner. if no rep resolves
> the row goes to an unassigned queue for a human instead of being guessed at.
> that is node 4b in the loom, "GHL: Read the Appointment's Assigned User From
> the Calendar".

## Flags
- Client in Ontario, Canada. No location claim in the copy.
- No portfolio link demanded, no off-Upwork restriction stated.
- Hourly with no budget: the proposal states no dollar figure, the 15 minute
  call decides scope and rate.
