# Dossier - AI Lead Intake & Qualification Automation with n8n and OpenAI

url: https://www.upwork.com/jobs/~022102822078003027245

## Who they are
- First name: unknown (no `client first name:` line; the post is unsigned)
- Company: unknown (no company, domain or product named)
- Industry: unknown. The post names no industry and no lead source. It only
  says they have leads coming in and more than one team to route them to
  ("routing qualified leads to the right team"). The build stays
  representative and says so plainly on the overview sticky.
- Location / timezone: Nevada (US), timezone America/New_York
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
1. "n8n"
2. "OpenAI"

Tools they did not name, and the one I commit to for each:
- Lead capture: one n8n webhook that their website form, an ad lead form or
  anything that sends a webhook posts to, then a clean-up step and a blank
  filter. One capture trigger on purpose: with a second one the Config node
  could not sit in front of the whole lead path.
- Lead status tracker: Google Sheets. A new buyer with a $100 budget and no
  named CRM; a sheet is the easiest thing for a non-technical team to keep up
  ("easy to maintain"), and the team changes a Status dropdown by hand.
- Routing to the team: Gmail (every team has an inbox; no Slack is named).
- Reporting dashboard: a "Dashboard" tab in the same Google Sheet, rebuilt by
  n8n every morning, plus a short summary email. One file, no extra login.
- Alerts when a step fails: Gmail to the owner.

## Every number in the post
- "$100" fixed price, intermediate level (metadata)
- Client record: "1 contract", "$30 spent", "no feedback yet" (metadata)
- "0 invites, 1 already invited to interview, 0 hired" (metadata)
- Recorded bids "avg $261.16, range $5-$2,000" (metadata)
- "Connects to apply: 10" (metadata)
- The post itself holds no numbers: no lead volume, no team count, no
  qualification criteria, no score cut-off. Each of those is a labelled input
  on the build (Config node) and a question in assessment.md.

## Their requirements, verbatim, in their order
1. "creating a lead capture flow"
2. "qualifying leads with AI"
3. "routing qualified leads to the right team"
4. "set up a lead status tracker"
5. "build a reporting dashboard"

Plus the standing ask across all five: "design the workflow, implement the
automation, and ensure the system is reliable and easy to maintain."

Five parts in your post, five sections on the canvas. An error-alert section
follows theirs (section 6), because "reliable" is their word.

## The odd ask only they would recognize
"ensure the system is reliable and easy to maintain." On screen: every
setting they would ever change (qualification rules, cut-off score, teams and
their inboxes, sheet, follow-up window) lives in the one "0 - Config: Your
Settings" node, so nobody edits a workflow node to change a rule; and section 6
emails them the failed step and the lead the moment anything breaks. Second
detail only they would recognize: "the right team" (plural teams), answered by
a routing table they fill in, not teams I made up.

## What their hiring history implies
A brand-new buyer: one contract ($30, a short-form video editor for reels /
TikTok ads / UGC, closed two days before this post), no feedback yet. They
likely run or are starting short-form video ads, and this post is the next
step: catching and sorting the leads those ads bring in. That is an inference
from history, never stated on the build or in a beat. They judge by "does it
work and can we run it ourselves", not by architecture talk. The $100 budget
is far below market for five parts; they are feeling out prices (bids range
$5-$2,000).

## Their likely data
Representative only (industry unknown). A lead as their form or webhook would
send it: name, email, phone, company, what they need, budget range, timeline,
source. Illustrative record, used for input_sample and the prompt sample:

```json
{
  "full_name": "Dana Whitfield",
  "email": "Dana@WhitfieldGroup.co",
  "phone": "(702) 555-0148",
  "company": "Whitfield Group",
  "need": "Saw your ad. We're a 12-person team and want to get started this month. What does it cost, and can someone call me Thursday afternoon?",
  "budget_range": "Not sure yet",
  "timeline": "This month",
  "source": "Website form",
  "utm_source": "paid_social"
}
```

The budget is deliberately missing, so the sample shows the missing-data rule
at work (score lowered, "Budget" in missing_info) instead of a perfect lead.
Output (tracker row after the flow): lead_id, received_at, cleaned contact
fields, source "Website form / paid_social", score 72, qualified true, team
"Sales", one-sentence reason, status "Sent to Sales", routed_at. "Sales" is an
illustrative team name only: their real teams come from the routing table they
type into Config. The "12-person team" in the sample is illustrative too, never
a claim about them.

## Sizing (setup / infrastructure / method jobs only)
Not a setup job. No volume in the post, so nothing to size. Their lead volume
per day is an input ("your leads per day") that moves OpenAI cost and Google
Sheets limits; asked in assessment.md, never stated.

## Three things they would recognize on screen
1. Their five parts, in their order, as the five section labels: capture,
   qualify with AI, route to the right team, lead status tracker, reporting
   dashboard (section labels and the overview sticky).
2. "Reliable and easy to maintain": the title, the "0 - Config: Your
   Settings" node holding every rule and inbox, and section 6 "RELIABLE: IF
   ANYTHING BREAKS, YOU HEAR ABOUT IT" (title, config node, section 6,
   overview sticky "setup" lines).
3. "The right team": node "6 - Match the Lead to the Right Team From Your
   Routing Table", with the teams they type into Config (section 3 label and
   the routing node's note).

## Beat 1 draft
"This is your automated lead intake and qualification system, n8n and OpenAI."
