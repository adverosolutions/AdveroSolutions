---
name: cold-campaigns
description: How AdveroSolutions runs cold email in Instantly. Covers the six live 2026 campaigns (cleaning, bookkeeping, recruiting; reactivation plus outbound, one body each), what each email says, sending volume and schedule, how copy moves from the one Google Doc to Instantly through a change-set, verdict rules, Instantly API traps, and the legacy contractor SOPs (SOP-002, SOP-002R roofing). Use for "launch a campaign", "what did we send them", "change the cold email", "how are the campaigns doing", "add leads to a campaign".
---

# Cold campaigns

Lorenzo writes the cold copy. The system stages his edits and checks them. Nobody else
writes, rewrites or "improves" a cold email, and nothing reaches live Instantly until he
has said "done" on the doc and then, separately, "go live".

## Who does what (decided 2026-09-25)

- **Grok Bot** runs day to day and is Lorenzo's contact point. For cold campaigns it reads
  (analytics, lead status, campaign settings) and reports. It never edits campaign copy,
  settings, lead lists or `email_list`, and never writes or paraphrases an email.
- **Claude Opus 5.5** makes the decisions: classifying replies, reading verdicts, spotting
  drift, deciding what to propose to Lorenzo.
- **Lorenzo** owns the copy and applies every live campaign change himself.
- Reply handling after a lead answers is in `cold-email-replies` and `grok-operator`;
  reporting numbers is in `daily-reports-and-metrics`.

## The six live campaigns (Instantly workspace, as of 2026-09-21 snapshot)

Two per niche: a reactivation offer and an outbound (trigger) offer. One body per step, no
A/B variants. A niche's leads are split round-robin across its two campaigns.

| Key | Campaign name | Offer | Proof line used |
|---|---|---|---|
| cleaning_reactivation | 2026 Cleaning - Client Reactivation | win back cancelled or non-renewing accounts, commission only | $150M/yr commercial roofer, about $6M recovered in 6 months |
| cleaning_trigger | 2026 Cleaning - Trigger Outbound | watch new leases, expansions, PM changes, new construction | same roofer, about $180,000 in 90 days |
| bookkeeping_reactivation | 2026 Bookkeeping - Client Reactivation | sequences to lost inquiries and former clients, timed to tax season | reactivation proof |
| bookkeeping_trigger | 2026 Bookkeeping - Trigger Outbound | watch new formations, part-time bookkeeper posts, second locations | outbound proof |
| recruiting_reactivation | 2026 Recruiting - Client Reactivation | dormant and near-miss accounts, % of placement fees | reactivation proof |
| recruiting_outbound | 2026 Recruiting - Outbound (specialty roles) | watch `{{specialty}}` roles open on job boards | outbound proof |

Settings on all six: text only, open and link tracking off, stop on reply, `daily_limit` 50
per campaign, two steps with `delay: 3` (day 0, day 3). Schedule: five campaigns send
07:00-19:00 America/Detroit Monday to Saturday; recruiting outbound sends 08:00-17:00
America/Chicago Monday to Saturday. Always re-read live before trusting these numbers.

### Structure of every email

- **Step 1** subject: `{{firstName}}, question` (one shared subject across all six).
  Body opens with `{{personalization}}` (the per-lead line, see `cold-email-personalization`),
  then what he builds, one proof line, the offer or guarantee, a 15-minute call ask, signed
  "Thanks, Lorenzo". The call ask differs per campaign (2026-09-21 snapshot):
  - cleaning_trigger and bookkeeping_trigger: "If this interests you, let's hop on a short 15
    minute call. Just reply Yes and I can shoot you over a calendar invite."
  - bookkeeping_reactivation and recruiting_reactivation: "Would you be open to a quick 15
    minute call about this? If so just say yes and I'll shoot a calendar invite over."
  - recruiting_outbound: "Open to a quick 15 minute call? Just say yes and I'll send a calendar
    invite."
  - cleaning_reactivation has no call ask; it ends "Let me know." (body below).
- **Step 2** has an empty subject (it lands in the same thread) and the same shape in all six:

```
Hey {{firstName}},
Checking in, in case the first one got buried. Quick version:
- I want to build a <reactivation|outbound> system for {{companyName}}. Goal is ...
- I did this for a commercial roofer doing $150M/yr and <recovered about $6M in contracts in 6 months | generated about $180K in new contracts in 90 days>.
- <guarantee or commission line>
Worth a quick 15 minute call? Just reply yes and I'll send a calendar invite.
Thanks for the time,
Lorenzo
```

Cleaning reactivation step 1 is the one body with a different shape. Verbatim (2026-09-21):

```
{{personalization}}
Know this is out of left field, if I could help recover the money from accounts that cancelled or stopped renewing their contracts in exchange for a commission on the accounts I bring back, would you be open? I work mostly on performance and am building my network.
About me: I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months. Would cost you nothing upfront.
Let me know.
Thanks,
Lorenzo
```

Guarantee lines as they sit in the outbound campaigns (his copy, kept as written):
- cleaning_trigger: "at least $24,000 a year in new cleaning contracts signed within 90 days, or I give your money back and throw in a $200 gift card to your favorite steakhouse."
- bookkeeping_trigger: "at least $15,000 in new annual client fees signed within 90 days ..."
- recruiting_outbound: "at least $40,000 in new placement fees from those calls within 180 days, or I return your money and throw in a $200 gift card to your favorite steakhouse."

How the reactivation campaigns word the no-risk offer (verbatim, 2026-09-21 snapshot):
- bookkeeping_reactivation and recruiting_reactivation step 1: "I won't charge you a single
  cent up front, only a percentage of first-year fees from clients I bring back, $0 if nothing
  closes." (recruiting: "placement fees from accounts I bring back").
- Their step 2: "Nothing up front. I only take a percentage of first-year fees on clients I
  bring back, $0 if nothing closes." (recruiting: "placement fees on accounts I bring back").
- cleaning_reactivation: step 1 "Would cost you nothing upfront."; step 2 "Nothing up front. I
  only take a commission on the accounts I bring back."

"$0 up front" is the offer sheet's wording, not campaign copy.

### Figures: cold copy versus everything else

The cold campaigns are Lorenzo's own copy and keep their guarantee lines. A price question
gets the price range written into the offer's approved pricing first reply
(`first_reply.<offer>.pricing.full`, Lorenzo 2026-10-06; AI agents: $400 to $5,300). Every
other email the system sends (other first replies, follow-ups, booking, show-rate, no-show)
never states a price, fee, commission percentage or guarantee amount. Proof lines come only
from the offer sheet.

## Sending capacity

- 45 inboxes on 15 domains. 12 are in the six campaigns (every one of the 12 is in all six),
  33 started warming 2026-09-20 and finish 21 days of warm-up on 2026-10-11 (after about
  18:40 CT that day).
- 25 sends per inbox per day: 12 x 25 = 300/day, matching the campaign ceiling 6 x 50 = 300.
- From 2026-11-01 an inbox may go to 30/day only if its 7-day real reply rate is at least 2%.
- How many inboxes to run and when to buy more is Lorenzo's call. Inbox health is in
  `deliverability-and-inboxes`.

## Changing copy: the one Google Doc route

Every email lives in one Google Doc: the newest "Advero emails: edit here (build ...)". Today
that is build `170b09dd897430a9`, doc id `1bK3bkYfxYkhY0vFtHhB4RG6lMkKQrHvp6Qyasp8Pbt4`,
uploaded 2026-09-25, 365 tagged blocks: the engine templates plus the six campaigns' two
steps (all 24 `instantly.*` blocks, body and subject for each step). Lorenzo edits there,
never in the Instantly editor. When a new build is uploaded, the previous doc is renamed
"OLD, do not edit" and is never edited again; check the newest entry in the doc upload list
before pointing anyone at a doc. Build `e95a04557f8a8faa` (2026-10-06, 395 tagged blocks, adds
the AI agents first replies) is built and waits for upload; once uploaded it is the doc
Lorenzo says "done" on, and its Google Doc id goes into the upload list.

1. Export the doc as plain text and keep the export unchanged (later steps verify it by hash).
2. Route it: the router lists each changed block, who owns it, and `also_in` (every other
   block carrying an edited sentence). Only `instantly.*` blocks belong to cold campaigns.
3. Build the change-set offline. It refuses, and lists every problem, on: a dash or `--`,
   "!", `{first_name}` style variables, a variable inside a spin, a note or doc layout line
   inside an email, a variable the campaign lacks, a deleted step, a subject on step 2, a
   dollar figure or a new "N days/weeks/months" that is not in the offer sheet, two copies of
   a shared subject edited differently. Do not fix his text: tell him the block and the
   rule, he fixes it in the doc, export again.
4. Dry-run against live. `REFUSED: live no longer matches` means someone edited Instantly
   after the doc was built: show Lorenzo the drift and rebuild the doc, never force it.
5. Show Lorenzo, per campaign: the live-to-target diff, warnings (curly quotes, `{{ firstName }}`
   with spaces, removed variables), the `also_in` list, and that a step-1 subject edit reaches
   all six campaigns and leads already mid-sequence.
6. Apply is his own terminal step, one campaign at a time, after "done" and "go live". It
   backs up the campaign first and verifies the PATCH landed. Exit 3 means check the UI and
   re-run the dry-run before any retry; restore from the newest `landed_verified` backup.
7. After an apply, rebuild the doc from a fresh campaign snapshot, or every later edit reads
   as drift.

Formatting typed in the doc (links, bold) is not carried over; the export is plain text.

## Verdicts (when to keep, rework, retire, scale)

A positive = a lead that ever reached interested, booked, completed, closed, lost or no-show.

| Sends | Positives | Call |
|---|---|---|
| under 1,000 | any | keep running |
| 1,000+ | 0, recruiting | retire |
| 1,000-1,999 | 0, other niches | rework copy |
| 2,000+ | 0, other niches | retire |
| 1,000-2,999 | 1 or more | run to 3,000 |
| 3,000+ | rate 0.7% or more / 0.5-0.7% / under 0.5% | scale / hold / rework |

Zero positives while Instantly shows open opportunities is a data check, not a retirement.
The verdict job proposes; retiring a campaign is a live change Lorenzo applies. At
2026-09-22 all six sat at 300 sends; projected date to reach 1,000 was 2026-10-07.

Alert thresholds for bounces and inbox health are the 2026-09-22 ones in
`deliverability-and-inboxes` (Section 6): an inbox comes out at over 2% bounce once it has
50+ sends. No reply-rate verdict before 1,000 sends (table above). The old SOP-010 alert
lines are kept, marked superseded, under Legacy.

## Instantly API traps (verified on this workspace)

- `POST /leads/list` ignores `campaign_id`: group by each lead's `campaign` field. An
  unrecognised `filter` value is silently ignored and returns every lead. Check filter names
  against a known list.
- Moving leads: `POST /leads/move` with `ids`, source `campaign` and `to_campaign_id`.
  PATCHing a lead's `campaign` silently does nothing. The move is an async job; a second move
  while one runs returns 409, so wait and retry.
- Campaign bodies must be sent as HTML (`<div>line</div><div><br /></div>`). Plain-text
  PATCHes once left three of six bodies empty with no error. Read back and compare after
  any write.
- `PATCH /campaigns/{id}` replaces `email_list` and `sequences` whole. `status` cannot be
  patched; use the activate and pause endpoints. Status 1 = active, 2 = paused.
- DELETE needs a `{}` body. A rejected call can still have partly executed: audit before
  re-running.
- Lead `status` 1 = not yet contacted. `campaigns/analytics` with dates is a presence filter
  returning lifetime totals; use the daily analytics endpoints for windows.
- `reply_count_unique` already excludes automatic replies. Never subtract
  `replies_automatic`.
- `{{personaliztion}}` (typo) and `{{ firstName }}` (spaces) will not fill.
- Rate limit 100/s and 6,000/min per workspace; `GET /emails` is 20/min.

## Never

- Touch a live campaign's `email_list`, sequences, limits or schedule outside a reviewed
  change-set that Lorenzo applies.
- Edit copy in the Instantly editor, or overwrite his live edits. His copy is the source of
  truth for wording; the system is the source of truth for mechanics.
- Add a booking link to any email (2026-09-23 rule: the lead picks a time, Lorenzo sends the invite). The one exception is the approved `first_reply.<offer>.booking_link.full` reply to a lead who asks for a booking or Calendly link (2026-10-06).
- Tell or imply that a bot or AI wrote an email; use em dashes or exclamation marks (offer sheet rule 8). The word "AI" itself is fine (the AI agents offer, 2026-09-30).
- Add a Claudeism (see `claudeisms`).

## Legacy contractor SOPs (January 2025, not running)

Kept for reference if Lorenzo returns to trades. Their volume (~2,000/day, 50 accounts x
40/day), tracking-on settings and "AI" wording are superseded by the rules above.

- **SOP-002 (HVAC, plumbing, electrical):** 3 emails over 7-10 days (day 1, 4-5, 7-10):
  curiosity hook ("What top [industry] contractors are doing differently"), AI transformation
  plus scarcity, breakup with feedback request. Goal: book a call.
- **SOP-002R (roofing):** 4 emails, day 1, 3, 5, 7, goal is a reply. Subjects look personal
  (`{firstName}`, `Re: {firstName}`, "honest question", "no hard feelings"). 100-130 words,
  no links, never the word "AI", no bullets, "system" never "website", first person singular,
  ends with a question. One angle per email: traffic not converting, referrals still Google
  you, buyers decide in seconds, graceful exit. A reply gets the live roofing prototype link.
  No reply by day 7: calls on days 8, 10 and 13, then 30-day nurture. The prototype is an
  industry prototype; never imply it was built for that company.
- **SOP-010 alert lines (superseded 2026-09-22):** bounce over 5%, spam complaints above
  zero, sends under 80% of target, positive reply rate under 0.5% for 3 days. Replaced by the
  2% bounce rule in `deliverability-and-inboxes` and the 1,000-send verdict floor above; a
  3-day reply-rate alert at 50 sends per campaign per day reads noise as a result.

## Gaps

- Live copy after 2026-09-21 is not in this skill; re-read live before quoting.
- No Instantly webhook is registered yet; the Grok trigger plan assumes `reply_received`.
- Step-3 bumps and subsequences for the 2026 campaigns are not written.
- Pricing for the outbound offers is "TO CONFIRM" in the offer sheet.
- The Instantly copy tooling still points at the old doc: the copy runbook's step 1 and
  `copy_lib.DOC_ID` pin `1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U`, and the change-set
  reads the top-level manifest until build `170b09dd897430a9` is promoted. Before a dry-run,
  confirm which doc's export and which manifest the change-set is reading.

## Sources (for maintainers)

- `Agentic Worklfows/config/snapshots/instantly_campaigns_2026-09-21.json` (origin/main): live copy and settings
- `Agentic Worklfows/config/ids.json` (2026-09-21): campaign keys and ids
- `Agentic Worklfows/config/offers.md` (origin/main, 2026-09-24 edit): figures rule, proof lines, reply rules
- `Agentic Worklfows/runbooks/instantly_copy_from_doc.md` (2026-09-23): doc-to-Instantly change-set
- `Agentic Worklfows/sections/4_core_and_golive/README.md`, `STATUS.md` (origin/main, 2026-09-23/24; item 5: older doc renamed "OLD, do not edit")
- `Agentic Worklfows/tools/template_doc/uploads.json` and commit ba39a0c (origin/main, 2026-09-25T00:45Z): current doc build 170b09dd897430a9, 365 blocks
- `Agentic Worklfows/changesets/instantly_copy/copy_lib.py` (origin/main): `DOC_ID` still the old 1jTg doc
- `Agentic Worklfows/runbooks/capacity.md`, `deliverability.md` (2026-09-22): capacity numbers
- `Agentic Worklfows/runbooks/experiments.md` (2026-09-22): verdict rules
- `Agentic Worklfows/config/instantly_api_contract.md` (2026-09-21/22): API behaviour
- memory `instantly-2026-campaigns.md` (2026-09-09 to 09-14): API lessons, body HTML trap
- `Agentic Worklfows/MASTER_SOP.md` (v2.0, January 2025) and `directives/USER/start_cold_campaign.md`: SOP-002, SOP-002R, SOP-010 (SOP-010 alerts superseded by the 2026-09-22 runbooks)
- `~/.claude/skills/grok-operator/SKILL.md` (2026-09-25): operating model
