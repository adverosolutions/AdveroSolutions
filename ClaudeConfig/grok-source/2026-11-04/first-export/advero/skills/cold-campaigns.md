
---
name: cold-campaigns
description: How AdveroSolutions runs cold email in Instantly. Covers the six live 2026 campaigns (cleaning, bookkeeping, recruiting; reactivation plus outbound, one body each), what each email says, sending volume and schedule, how copy moves from the one Google Doc to Instantly through a change-set, verdict rules, Instantly API traps, and the legacy contractor SOPs (SOP-002, SOP-002R roofing). Use for "launch a campaign", "what did we send them", "change the cold email", "how are the campaigns doing", "add leads to a campaign".
---

# Cold campaigns

> Old templates retired 2026-10-20 (archive/templates_retired_20261020). No approved reply copy yet: every reply is a hold card until Lorenzo approves new copy.

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
  "Thanks, Lorenzo".
  The old six campaigns' verbatim copy (call asks, step 2 body, cleaning reactivation body,
  guarantee and no-risk lines) was retired 2026-10-20 with the old templates (old text in
  `skills/cold-campaigns.md.bak-20261020b`). Live copy lives only in the Instantly campaigns.
- **Step 2** has an empty subject (it lands in the same thread).

### Figures: cold copy versus everything else

The cold campaigns are Lorenzo's own copy and keep their guarantee lines. Every other email
the system sends (first replies, follow-ups, booking, show-rate, no-show) never states a
price, fee, commission percentage or guarantee amount (Lorenzo, 2026-09-24: "We never talk
numbers over email."). A price question gets the mechanism in one line and "The rest is
easier to cover on a quick call." Proof lines come only from the offer sheet.

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
before pointing anyone at a doc.

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
- Spintax must be Instantly form `{{RANDOM | option1 | option2}}` (double braces + `RANDOM`). Classic `{a|b}` is treated as literal text and will appear in previews and sends. Do not confuse with merge tags (`{{firstName}}`) or fallbacks (`{{firstName | there}}`). Fixed live 2026-10-02; see `state/handoffs/20261002_spintax_diagnosis.md`.
- Rate limit 100/s and 6,000/min per workspace; `GET /emails` is 20/min.

## Never

- Touch a live campaign's `email_list`, sequences, limits or schedule outside a reviewed
  change-set that Lorenzo applies.
- Edit copy in the Instantly editor, or overwrite his live edits. His copy is the source of
  truth for wording; the system is the source of truth for mechanics.
- Add a booking link to any email outside the reply-draft rule (Lorenzo, 2026-10-20: reply drafts offer two open times from his Google Calendar plus his direct booking link, https://scheduler.zoom.us/lorenzo-villarreal-4mp7rz/30-mins-with-lorenzo; ask-first, Lorenzo approves each send).
- Mention AI, automation or tools; use em dashes or exclamation marks (offer sheet rule 8).
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


---
