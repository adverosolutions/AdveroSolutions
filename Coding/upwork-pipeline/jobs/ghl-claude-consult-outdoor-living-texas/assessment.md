# Assessment (private) - GoHighLevel Workflow Expert with Claude AI Integration

Prop: chart only (`"platform": "diagram"`), 12 steps, 2 gates, 4 bands = their 4
asks in their order, each with its share of the 60 minutes (20 / 15 / 15 / 10).
Nothing is built in GoHighLevel.

## Time
- Prep: 30 to 60 min reading their 9 workflows (1 intake/lead-routing + 8
  follow-ups) and the older ones, from a login or screenshots. Without prep the
  review is about 2 minutes per workflow (20 min / 9), triggers and collisions
  only.
- The call: 60 min.
- Written prioritized list after the call: 45 to 60 min.
- Total: 2.5 to 3 real hours, done inside one calendar week (the call slot is
  theirs to pick).
- Likely follow-on (quote separately if they ask): entry tag on each of the 9
  workflows, If/Else blank-field checks before sends in the 8 follow-ups,
  retiring colliding older workflows, a scheduled Claude audit with one report.
  About 12 to 20 hours, 1 to 2 weeks.

## Likelihood
- The call: high odds of a useful hour if they share screen or give access
  first. Screen share only means a surface review.
- Their connector, by their own words, "can read and write contacts, tags and
  opportunities". It does not show workflow steps or who is enrolled, so Claude
  can only audit what workflows leave behind. That is why the chart makes every
  workflow stamp an entry tag (step 6).
- Verify before the call (not verified by Lorenzo in their account):
  - GHL API v2 workflows endpoint lists names and status only, not steps.
  - Contacts can be added to a workflow by API (`POST
    /contacts/{contactId}/workflow/{workflowId}`), useful for re-enrolling
    leads that never entered one.
  - A tag added through the API fires GHL's "Contact Tag" trigger (step 5
    relies on it).
  - GHL v2 rate limits (burst per 10 seconds, daily cap): ~2,400 contacts is a
    small sweep either way.
- Cost trap: Claude reading every one of the ~2,400 contact records through MCP
  on each audit run burns context and API spend. Filter first, Claude reads
  only the flagged contacts (step 8).
- Who built it: the active "Construction Company Claude AI Setup" contract
  (since 2026-07-06) very likely connected Claude to GHL. The call reviews that
  work; keep it constructive.
- Unverified for Lorenzo, say so if asked: Buildertrend (no experience, never
  claim it), GHL marketplace custom actions, GHL's native AI steps in depth.
  What he can state: he runs Claude through the Anthropic API in his own sales
  system (Haiku classification, Sonnet drafts) and connects Claude to
  GoHighLevel through the API and MCP in his own sub-account.

## Standard pricing
- Their range: $15 to $35 an hour. Recorded bids avg $26.74, range $10 to
  $89.76. Their range is well under market for a GHL + Claude specialist.
- Market: $75 to $150 an hour for a GHL + LLM consultant; a paid 60-minute
  strategy call with a written summary commonly runs $100 to $250.
- Suggested bid: $35 an hour (top of their range). Bill the call plus the
  written list, about 2 hours. Whether prep is billed is Lorenzo's call. The
  value here is the follow-on: 18 active contracts and 3,148.83 hours on this
  account say they keep freelancers who deliver.
- Follow-on market reference: $1,500 to $3,500 for the 12 to 20 hours above.
- Recurring software: nothing new for the call. A scheduled audit adds
  Anthropic API usage (small when Claude reads only flagged contacts; size it
  once the filter volume is known) and a place to run it on a schedule.

## Ask before quoting
1. The post lists 8 follow-up workflows but names 7 (speed-to-lead, consult
   reminders, proposal chase, nurture, reactivation, reviews, referrals). Which
   is the 8th? Is "consult reminders" two, one per calendar?
2. How many older workflows are still published, and which share triggers with
   the new ones?
3. A user login or screenshots of each workflow before the call? Is prep paid?
4. Which connector: GHL's official MCP server or a custom one? What scopes does
   its token have beyond contacts, tags and opportunities?
5. Where does Claude run today (a chat app with the connector, or a scheduled
   job)? "Monitor, audit and maintain over time" needs something on a schedule.
6. Will the freelancer who built the connector be on the call?
7. Buildertrend: should won jobs move from the sales pipeline into it?

## Flags
- Portfolio demand: "Please share examples or screenshots." Lorenzo's honest
  proof is this chart and screenshots of Claude connected to GHL in his own
  sub-account. No client screenshots.
- No US-only line and no ban on contact outside Upwork. Client in Texas: book
  the call in Central time.
- Low rate range; the account history makes the follow-on worth it.
- Buildertrend appears once, in band 4's note, as a list item only.

## Their questions: draft answers for Lorenzo

1. How would you audit an existing set of GHL workflows to find problems
   before they affect leads?

   I push one test lead through your intake/lead-routing workflow and note every
   workflow it enters, then line up the triggers of the 8 follow-ups against
   your older workflows to find any two firing on the same event. Next I check
   the waits against your discovery and in-home consult calendars, and every
   If/Else for a path where a lead drops out with nothing after it. For silent
   failures, each workflow adds an entry tag so a lead with none shows up in a
   filter, and an If/Else before each send holds any message with a blank merge
   field.

2. Have you worked with Claude's MCP connector or the Anthropic API? How did
   you use it?

   Yes. I run Claude through the Anthropic API in my own sales system, with
   Haiku for classification and Sonnet for drafts. I also connect Claude to
   GoHighLevel through the API and MCP in my own sub-account.

3. What is your rate for the consultation, and what is your availability over
   the next week?

   My rate for the consultation is [LORENZO: rate, suggested $35] an hour. Over
   the next week I can do [LORENZO: days and times, Central time] on Zoom or
   Google Meet. [LORENZO: keep only if prep is included] If you can share a
   login or screenshots of your workflows the day before, I'll come in with the
   collisions already marked.
