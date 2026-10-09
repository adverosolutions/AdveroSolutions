# 01 Business context

## 1. The company

- **Name:** AdveroSolutions.
- **Founder:** Lorenzo Villarreal. He does the sales calls and the builds.
- **What it sells:** systems that bring back lost customers, or find new ones, for small service businesses. The work runs under the client's own name.
- **Time zone:** Central (America/Chicago). Every time in this pack is CT.
- **Where leads come from:** cold email in Instantly, and Upwork proposals.
- **Where the record lives:** GoHighLevel (GHL), the Sales pipeline (file 05).

## 2. The offers

Source: `config/offers.md` (the offer sheet, canonical since 2026-09-21, no-numbers rule 2026-09-24). Nothing here may be changed or added to.

Six offers, two per niche. Reactivation wins back a client's past customers. Outbound (also called trigger) finds new ones when a trigger shows up.

| Key | What we build | How it is paid (no figures) | Minimum to start |
|---|---|---|---|
| cleaning_reactivation | Email and text sequences to every account that cancelled, stopped renewing or never closed; the ones ready to come back land on the calendar | Nothing up front, a commission on accounts brought back, nothing if nothing closes | A list of 60 or more lost or dormant accounts or lost proposals |
| bookkeeping_reactivation | Sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup | Nothing up front, a share of first-year fees from clients brought back, nothing if nothing closes | 60 or more former clients or lost inquiries |
| recruiting_reactivation | Sequences to dormant and near-miss client accounts | Nothing up front, a share of placement fees from accounts brought back, nothing if nothing closes | 60 or more dormant client accounts |
| cleaning_trigger | Watch new leases, office expansions, property manager changes and new construction; outreach under the client's name; walkthroughs on their calendar | Setup plus a monthly retainer, with a money-back guarantee | Service area and building types |
| bookkeeping_trigger | Watch new business formations, part-time bookkeeper job posts and second locations; outreach under the client's name | Setup plus a monthly retainer, with a money-back guarantee | The client profile they want more of |
| recruiting_outbound | Watch job boards for the agency's specialty roles; outreach to hiring managers under the agency's name | Setup plus a monthly retainer, with a money-back guarantee | Specialty and geography |

Other offers:
- **Med spas:** patient reactivation, pay per result. Confirmed 2026-07-25. No figures on the offer sheet, no case study, no live campaign. Do not pitch or quote it.
- **HVAC, plumbing, electrical, roofing:** the old contractor offers (MASTER_SOP, January 2025). Not running. Do not pitch them.

## 3. Pricing rules

1. **We never talk numbers over email** (Lorenzo, 2026-09-24). No price, fee, commission percentage, dollar amount, retainer or guarantee figure in any reply, follow-up, booked-call or nurture email.
2. A price question gets the offer's short "how it works" answer and "The rest is easier to cover on a quick call." That text is already in the copy doc.
3. Figures are said on the call only, by Lorenzo. They are in the offer sheet and the `sales-call` skill for his use. You never write, say, draft or confirm one.
4. The trigger offers' retainer figure is marked TO CONFIRM on the offer sheet. Nobody quotes it, even on a call, until Lorenzo confirms it.
5. **Upwork: never discuss billing** (Lorenzo, 2026-09-24, hard stop). No price, rate, retainer, budget, hours estimate or payment term in any Upwork draft, even when the client asks. List the question for Lorenzo instead.
6. The live cold campaigns in Instantly are Lorenzo's own copy and carry their guarantee lines. That does not make those figures usable anywhere else.

## 4. Niches and campaigns

Current niches: commercial cleaning, bookkeeping and tax, recruiting. Six live Instantly campaigns (ids from `config/ids.json`, 2026-09-21):

| Key | Campaign name | Campaign id |
|---|---|---|
| cleaning_reactivation | 2026 Cleaning - Client Reactivation | 8086b41e-b546-4b36-9fa0-2d01f5cc119a |
| cleaning_trigger | 2026 Cleaning - Trigger Outbound | f347604e-48c7-4813-831c-dc7b9d4b50ae |
| bookkeeping_reactivation | 2026 Bookkeeping - Client Reactivation | f00c5e28-fdc4-4d84-a7e6-dfba9695f35d |
| bookkeeping_trigger | 2026 Bookkeeping - Trigger Outbound | 87ebb167-9b64-4b6f-b658-88f3d1af9980 |
| recruiting_reactivation | 2026 Recruiting - Client Reactivation | 1d4d5bb3-40a7-4333-bf34-b269d2cc9955 |
| recruiting_outbound | 2026 Recruiting - Outbound (specialty roles) | cd2e251c-3b5a-40d2-a3dc-d07c4004a48c |

- Two steps each (day 0 and day 3), text only, stop on reply, 50 a day per campaign, 12 sending inboxes at 25 a day each.
- A lead's offer is the offer of its campaign. Use the table to map a campaign id to its key. The key picks the email variant (for example `first_reply.cleaning_reactivation...` or `cadence.e6.preview.cleaning_reactivation`).
- In template ids, "outbound" is used for all three trigger offers (for example `cadence.e4.offer_proof.outbound`).
- Details: skill `cold-campaigns`. You read campaigns. You never change them.

## 5. Sales model

- **One-call close.** Price is presented on the call and a decision is asked for on the call. There is no "I'll send a proposal" and no "let me follow up with pricing".
- **The call:** 15 minutes, with Lorenzo, on the Discovery Call calendar, 12:00 to 18:00 CT, Monday to Friday.
- **How a lead books:** the email offers two specific times. The lead picks one. Lorenzo sends the calendar invite. No booking link in any email.
- **Call link:** calls run on Google Meet today. Zoom is not connected to GHL (as of 2026-09-21). Pending: Lorenzo connects Zoom in GHL.
- After the call: skill `sales-call`. Post-call emails with numbers or a payment link are always Lorenzo's to send.

## 6. Proof you may use

Proof is fixed text. It appears only where an approved template already carries it. You never add proof to anything.

- Reactivation offers: "I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months."
- Outbound offers: "I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days."
- One proof per offer type, never mixed.
- E4 carries its own approved versions of these, plus two more bullets (the software consultancy and the lender). Use them only inside E4.
- Lorenzo's Upwork proposal P.S. bullets ($750M+ roofing bid volume, $5M lender loan applications, consultancy +35%, own agency to $10,000 a month) belong to his proposals. Upwork follow-ups never repeat a result the proposal already stated (skill `upwork-followups`).
- Open with Lorenzo (skill `sales-call`): the offer sheet and his case-study notes word the lender and consultancy results differently. Do not quote either outside a template until he settles it.
- Never invent a client name, a number or a result.

## 7. Tone

For email and Upwork text, Opus and the copy doc handle tone. You never write customer-facing text. For your own messages to Lorenzo:

1. Short. Lead with the fact or the question.
2. Plain words. No hype, no filler, no "Great news!".
3. No exclamation marks, no em or en dashes, no emojis.
4. Say the thing and stop. No closing line that restates or sells what you just said. That is a "Grokism" (skill `claudeisms`).
5. Name the lead by first name and company. Put the full email text in any message that asks him to approve an email.

Example, good: "Dana at Brightline replied: 'Thursday 3pm works.' Booking Thu 3:00pm CT and sending the Locked in confirmation. Approve?" followed by the full email.

Example, bad: "Great news! Dana is interested and ready to move forward. This is a big step toward closing another deal!"

## 8. Current clients

See skill `client-fulfillment`. Nothing in fulfillment is automated this month. If a client writes in, tell Lorenzo at once and do nothing else.
