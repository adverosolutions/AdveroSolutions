# Delivery assessment — NOT for the proposal

**Shape:** ongoing part-time technical partner, hourly $25-40, avg bid ~$39/hr, US client.
This is a retainer relationship, not a one-shot build. Phase 1 is the thing to scope.

**Time.** Phase 1 (one partner record synced across 3-4 systems + tier routing + one AI
deliverable type + activity log) is realistically 45-70 hours over 3-5 weeks, not the 25 the
canvas suggests. The n8n build is maybe a third of it. The rest is discovery of what their
current workflows actually do, field mapping across four schemas, and testing against real
partner data. After phase 1, expect a steady 8-15 hrs/week of iteration, which is what they
are actually buying.

**Likelihood — what breaks.**
- **The PRM is the wild card.** PartnerStack, Allbound, Crossbeam, Impartner all differ wildly:
  some are webhook-out only, some gate the API behind a higher plan, some have no write API for
  partner records at all. If the PRM cannot be written to, "one record" becomes "one record plus
  a manual PRM step" and the whole pitch changes. Find out before quoting.
- **Two-way sync echo loops.** Four systems writing to each other will ping-pong unless every
  update carries a source stamp and the flow drops its own echoes. This is the single most common
  way these builds go fragile, and it is exactly the "fragile chains" they said they want to avoid.
- **One system has to be master.** That is a business decision they may not have made. Pushing them
  to pick before building is the "simplify before building" they asked for, and it is the highest
  value hour of the project.
- **AI deliverable quality depends on their templates existing.** If the strategy docs and playbooks
  live in people's heads rather than written frameworks, half of phase 1 is extracting the template,
  not automating it. Reasonable, but it should be named as its own line item.
- **Account access.** Everything here happens in their tenants. Admin/API keys on CRM, PRM, PM tool,
  Notion, Google Workspace, Slack. Any one of those being slow to arrive stalls the calendar, not
  the hours.
- **The dashboard is out of scope for now.** They said "potentially, once the workflow is proven."
  Do not price it in. Let the activity log be the proto-dashboard.

**Standard pricing.** Senior multi-system automation architecture for a US client: $75-120/hr, or
$9k-16k fixed for a phase 1 of this shape. Small agencies quote $18k+. Their $25-40 band is well
below market, which they half-acknowledge ("not the cheapest person"). Bidding $40-45 is defensible
and still reads as economical to them. Recurring software: n8n Cloud ~$25-60/mo (or self-hosted),
Anthropic API roughly $30-120/mo at a few hundred deliverables, plus whatever the PRM charges for
API access.

**Ask before quoting.**
1. Which CRM exactly, which PRM exactly, which PM tool exactly, which outreach platform? Every hour
   estimate moves on these four answers.
2. What is the intended source of truth today, and are they willing to name one?
3. How many partners, how many tiers, how many activation types per tier?
4. Do the deliverable templates already exist as written frameworks, or do they need extracting?
5. Which plan tiers are they on (API access is gated on most PRMs and on HubSpot's ops features)?
6. Are they already on n8n / Make / Zapier, or is the platform choice open?

**Post mechanics (main session handles the copy).**
- They ask for 2-3 relevant examples (AI workflows, multi-tool business systems, custom dashboards)
  and years of experience. Do not answer as a screening list; use the case-study P.S.
- "Do not reach out outside Upwork" — everything stays in Upwork messaging. A Loom link inside the
  proposal is fine; no email, no LinkedIn, no calendar link.
- They want "build small, test, learn, iterate." Framing phase 1 as one tier and one deliverable
  type, proven with real users, matches their stated process better than pitching the whole hub.
