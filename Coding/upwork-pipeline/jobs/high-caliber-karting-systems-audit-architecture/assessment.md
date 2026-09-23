# Assessment (private, never in the proposal) - High Caliber Karting stack audit

## Time
- Their estimate is "approximately 10-20 hours". Realistic for a deliverable Lorenzo would stand behind: 16-20 hours over 2-3 calendar weeks. Calendar time depends on getting logins or screen-share walkthroughs, not on the work.
  - Kickoff and inventory validation against their list: 2-3 h
  - Walkthroughs: one venue day (BMI Leisure booking to Toast at the Bar & Bistro to close-out) and one event request (form to contract and deposit), with the GM or events lead and the bookkeeper: 3-4 h
  - Access research per platform, deep on Toast, BMI Leisure, HubSpot, QuickBooks, Stripe, PayPal, Deputy, MaintainX: 4-6 h
  - Flow map, source-of-truth decisions, security and failure requirements: 3-4 h
  - Verdict table, phased roadmap, write-up and a review call: 3-4 h
- At the 10-hour floor the audit has to run in triage mode (see Sizing): inventory-only for Ubiquiti/UniFi, Google Admin and the lighting and facility-control apps.
- Follow-on implementation ("POS and booking integrations, pricing synchronization, website automation, CRM workflows, reporting, kiosks...") is months of part-time work if the audit lands. That is the real prize.

## Sizing (from their numbers only)
- 10-20 hours for "dozens of platforms". Just the 13 named: 10 h / 13 = about 46 min each, 20 h / 13 = about 92 min each. The real inventory is larger, so an even split is under an hour per platform.
- So the audit must triage: deep where bookings and money move, list-only for the rest. On the chart (step 1) and in beat 3.
- Pricing is typed twice (WordPress pricing page and the BMI Leisure shop, from their site), and "pricing synchronization" is already on their own future list: the natural Phase 1 candidate. On the chart (steps 5 and 10) and in beat 5.
- Guest records probably live in both BMI Leisure and HubSpot; which one is the source of truth is their call. On the chart (step 7) and in beat 7.

## Likelihood (what breaks)
- BMI Leisure API access: unverified for Lorenzo. BMI does not look like a self-serve public API; access may need a request to BMI, a partner arrangement or a fee. If there is no API, pricing sync and booking data fall back to BMI reports/exports or browser automation, which is more fragile. This single fact shapes half the roadmap; say so plainly on the call.
- Toast API access: unverified. Toast's APIs are largely partner-gated; restaurant-level access may be limited or read-only depending on their plan. Same framing: "checked first" (step 3).
- QuickBooks: Online vs Desktop changes everything (Desktop has a weak API). Unknown. The "native first, like Stripe and PayPal into QuickBooks" line on the chart assumes QuickBooks Online; confirm before the call or say it as a question.
- Money comes in through several places (Toast, the BMI Leisure shop, Stripe, PayPal). Reconciliation into QuickBooks is likely a real pain point and a real risk to their books; do not promise a figure.
- Lighting, facility controls and Ubiquiti/UniFi: often local, proprietary or safety-relevant. Recommend they remain human-controlled (read-only monitoring at most). Do not scope automation there in the audit.
- The rest (HubSpot, Stripe, PayPal, Deputy, MaintainX, Twilio, Jotform, WordPress) have documented APIs and webhooks, but plan tiers can gate them (HubSpot workflow webhooks, MaintainX API on higher plans). Unverified per their plans.
- Lorenzo's fit: builds n8n and Make daily, REST APIs, Claude/Anthropic API with MCP tools. No venue, POS or BMI Leisure experience to claim; the chart is labelled as a first pass from their post and public site, which is the honest frame. No past-project claims.
- Competition: 3 invites, 2 already in interviews, 0 hired. Speed and a concrete first pass are the edge.

## Standard pricing
- Market for a 10-20 hour systems audit and automation architecture from an engineer who also builds: about $100-175/h, so $1,500-3,500 for the audit. Agencies package this at $2,500-5,000 fixed.
- The post's range is $35-$75/h: $350-$1,500 for 10-20 hours. Recorded bids average $46.17 (range $12-$100). The post's rate sits below market; it is a foot-in-the-door rate for a client with a long implementation tail.
- Suggested: bid at the top of their band ($70-75/h) or offer the audit fixed at about 20 hours, and make implementation the conversation.
- Recurring software for the implementation phase (not the audit): n8n self-hosted on a small VPS (roughly $5-20/mo) or n8n Cloud (check current pricing), Make if they prefer it (low tens of dollars a month), a small database if needed (free tier to about $25/mo), Twilio usage for alerts. Possible BMI Leisure or Toast API fees: unknown.

## Ask before quoting
1. The full inventory: they say "dozens"; 13 are named. Who owns the admin login for each?
2. QuickBooks Online or Desktop?
3. BMI Leisure: which modules (online shop, POS, racing), and do they have an API agreement or a BMI account rep?
4. Toast: Bar & Bistro only, or front counter too? Which plan?
5. Which payments go through Stripe, PayPal, Toast and the BMI Leisure shop?
6. Where does the Event Request Form go today (Jotform, HubSpot, email)? Who retypes it where?
7. Who joins the walkthroughs: GM, events lead, bookkeeper, the long-term EA?
8. Access during the audit: read-only admin seats, or screen-share walkthroughs?
9. The three places staff re-type the most today.
10. Names of the lighting and facility-control apps.
11. Deliverable format they want (document, diagram, spreadsheet) and hourly vs fixed for the audit.

## Flags
- US client (Michigan); the post does not say US-only. No location claims in the copy.
- No portfolio demand; no stated rule on contact outside Upwork.
- Their only hire is a long-running Executive Assistant (3,204 hours, $67.3k): they keep people, so a good audit very likely becomes ongoing work. That EA probably holds operational knowledge and logins; ask to include them.
- "a builder and systems thinker, not just an advisor": the proposal should offer to build the Phase 1 item, not only deliver a document.
