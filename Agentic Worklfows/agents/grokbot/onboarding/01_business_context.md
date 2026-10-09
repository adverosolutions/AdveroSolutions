# 01 Business context

## 1. The company

- **Name:** AdveroSolutions.
- **Founder:** Lorenzo Villarreal. He does the sales calls and the builds.
- **What it sells:** systems that bring back lost customers, or find new ones, for small service businesses. The work runs under the client's own name.
- **Time zone:** Central (America/Chicago). Every time in this pack is CT.
- **Where leads come from:** cold email in Instantly, and Upwork proposals.
- **Where the record lives:** GoHighLevel (GHL), the Sales pipeline (file 05).

## 2. The offers

Source: `config/offers.md` (the offer sheet, canonical since 2026-09-21, no-numbers rule 2026-09-24, price range in the pricing reply 2026-10-06). Nothing here may be changed or added to.

Six offers, two per niche, plus the AI agents offer (key `ai_agents`, one key for all eight AI agents campaigns, 2026-10-06). Reactivation wins back a client's past customers. Outbound (also called trigger) finds new ones when a trigger shows up.

| Key | What we build | How it is paid (no figures) | Minimum to start |
|---|---|---|---|
| cleaning_reactivation | Email and text sequences to every account that cancelled, stopped renewing or never closed; the ones ready to come back land on the calendar | Nothing up front, a commission on accounts brought back, nothing if nothing closes | A list of 60 or more lost or dormant accounts or lost proposals |
| bookkeeping_reactivation | Sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup | Nothing up front, a share of first-year fees from clients brought back, nothing if nothing closes | 60 or more former clients or lost inquiries |
| recruiting_reactivation | Sequences to dormant and near-miss client accounts | Nothing up front, a share of placement fees from accounts brought back, nothing if nothing closes | 60 or more dormant client accounts |
| cleaning_trigger | Watch new leases, office expansions, property manager changes and new construction; outreach under the client's name; walkthroughs on their calendar | Setup plus a monthly retainer, with a money-back guarantee | Service area and building types |
| bookkeeping_trigger | Watch new business formations, part-time bookkeeper job posts and second locations; outreach under the client's name | Setup plus a monthly retainer, with a money-back guarantee | The client profile they want more of |
| recruiting_outbound | Watch job boards for the agency's specialty roles; outreach to hiring managers under the agency's name | Setup plus a monthly retainer, with a money-back guarantee | Specialty and geography |
| ai_agents | AI agents for service businesses: a free custom AI agent plan (which tasks agents can take over, what each is worth, rollout order), the lead's to keep either way; then the build | A build price; no guarantee. The range goes only in the approved pricing first reply (section 3) | No minimum |

Other offers:
- **Med spas:** patient reactivation, pay per result. Confirmed 2026-07-25. No figures on the offer sheet, no case study, no live campaign. Do not pitch or quote it.
- **HVAC, plumbing, electrical, roofing:** the old contractor offers (MASTER_SOP, January 2025). Not running. Do not pitch them.

## 3. Pricing rules

1. **A price question gets a price range** (Lorenzo, 2026-10-06; replaces "we never talk numbers over email"). The range is fixed text inside each offer's approved `first_reply.<offer>.pricing.full` reply (AI agents: $400 to $5,300). Only that reply carries a figure: no other reply, follow-up, booked-call or nurture email has a price, fee, commission percentage, dollar amount, retainer or guarantee figure.
2. The range goes out only as the copy doc has it, inside that reply.
3. Exact prices are said on the call only, by Lorenzo. They are in the offer sheet and the `sales-call` skill for his use. You never write, say, draft or confirm a figure yourself.
4. The trigger offers' retainer figure is marked TO CONFIRM on the offer sheet. Nobody quotes it, even on a call, until Lorenzo confirms it.
5. **Upwork: never discuss billing** (Lorenzo, 2026-09-24, hard stop). No price, rate, retainer, budget, hours estimate or payment term in any Upwork draft, even when the client asks. List the question for Lorenzo instead.
6. The live cold campaigns in Instantly are Lorenzo's own copy and carry their guarantee lines. That does not make those figures usable anywhere else.

## 4. Niches and campaigns

Current niches: commercial cleaning, bookkeeping and tax, recruiting, plus the eight AI agents campaigns. Campaign ids from `config/ids.json` (the six offers 2026-09-21; the AI agents campaigns read from Instantly 2026-10-06):

| Key | Campaign name | Campaign id |
|---|---|---|
| cleaning_reactivation | 2026 Cleaning - Client Reactivation | 8086b41e-b546-4b36-9fa0-2d01f5cc119a |
| cleaning_trigger | 2026 Cleaning - Trigger Outbound | f347604e-48c7-4813-831c-dc7b9d4b50ae |
| bookkeeping_reactivation | 2026 Bookkeeping - Client Reactivation | f00c5e28-fdc4-4d84-a7e6-dfba9695f35d |
| bookkeeping_trigger | 2026 Bookkeeping - Trigger Outbound | 87ebb167-9b64-4b6f-b658-88f3d1af9980 |
| recruiting_reactivation | 2026 Recruiting - Client Reactivation | 1d4d5bb3-40a7-4333-bf34-b269d2cc9955 |
| recruiting_outbound | 2026 Recruiting - Outbound (specialty roles) | cd2e251c-3b5a-40d2-a3dc-d07c4004a48c |
| ai_agents | 2026 Bookkeeping & tax - AI Agents | e8867dbb-4f94-40ee-81c0-c11d7a256e2d |
| ai_agents | 2026 Service - AI Agents | d81f1d53-23d6-48a6-aea3-80c21192e17e |
| ai_agents | 2026 MSP - AI Agents | 9b82c9ce-b772-440a-b4a0-b984fe6a7a3f |
| ai_agents | 2026 Insurance brokers - AI Agents | 8a50b4e8-48e7-4db2-aa8f-b2e75187a8be |
| ai_agents | 2026 Landscaping - AI Agents | 891bf2b5-9351-4cde-a5c4-13dd1d8ffce8 |
| ai_agents | 2026 Recruiting - AI Agents | 59b20790-12bb-446d-bcd6-e3b6f9a61953 |
| ai_agents | 2026 Marketing agencies - AI Agents | 4eedb228-53c7-42ff-baf5-5b40c8646bd8 |
| ai_agents | 2026 Pest control - AI Agents | 21f5568a-d82e-4280-8437-04b0f8d6df37 |

- The six offer campaigns: two steps each (day 0 and day 3), text only, stop on reply, 50 a day per campaign, 12 sending inboxes at 25 a day each.
- A lead's offer is the offer of its campaign. Use the table to map a campaign id to its key. A campaign that is not in the table has no key: every email for that lead is a hold card and no call is booked for it: `ask_opus.py` checks that the key is one of the seven in this table. The key picks the email variant (for example `first_reply.cleaning_reactivation...` or `cadence.e6.preview.cleaning_reactivation`).
- In template ids, "outbound" is used for all three trigger offers (for example `cadence.e4.offer_proof.outbound`).
- Details: skill `cold-campaigns`. You read campaigns. You never change them.

## 5. Sales model

- **One-call close.** Price is presented on the call and a decision is asked for on the call. There is no "I'll send a proposal" and no "let me follow up with pricing".
- **The call:** 15 minutes, with Lorenzo, on the Discovery Call calendar, 12:00 to 18:00 CT, Monday to Friday.
- **How a lead books:** the email offers two specific times. The lead picks one, or names another time. A time that fits every slot rule is booked first on the Discovery Call calendar, the booking is checked, and only then does the "Locked in" confirmation go (file 02, section 4, rule 15). Lorenzo sends the calendar invite. The one email with a booking link is the approved `first_reply.<offer>.booking_link.full` reply, for a lead who asks for one. A lead can also book through that link: the booking confirms on its own and the calendar sends the invite.
- **Call link:** Zoom is connected on the GHL Discovery Call calendar (verified read-only 2026-10-06): a booking there gets a Zoom link and a Google invitation email. Some older calls were booked by hand on Lorenzo's Google Calendar.
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

Example, good: "Dana at Brightline replied: 'Saturday 10am works.' Calls are Monday to Friday. Counter ready: booking.counter.weekend. Send it, or book her time anyway?" followed by the full email.

Example, bad: "Great news! Dana is interested and ready to move forward. This is a big step toward closing another deal!"

## 8. Current clients

See skill `client-fulfillment`. Nothing in fulfillment is automated this month. If a client writes in, tell Lorenzo at once and do nothing else.
