# Assessment (private, never in the proposal)

## Time
- First 2 weeks: discovery with the team (processes, volumes, current tools, access), opportunity map with real hours, audit of the existing automations. About 20-25 hours.
- Weeks 2-5: the first flagship agent workflow end to end (intake, classification, tool lookups against their order/account data, drafted reply, confidence gate, record update), in shadow mode first, then live. About 40-60 hours.
- Weeks 3-6, in parallel: harden 2-3 existing workflows (validation, retries with backoff, idempotency, dead-letter queue, alerts). About 15-25 hours.
- From week 4: logging, run dashboard, alerting and the Monday weekly report. About 10-15 hours, then ongoing.
- Full time after that means a steady queue from the opportunity map: roughly one new workflow every 1-2 weeks plus upkeep.

## Likelihood
- High for the build itself: this is Lorenzo's daily work (n8n, Claude API, agents with tools).
- Unverified: what their business is, which systems hold orders and customer data, whether those systems have APIs, and what "existing systems" are built on (Zapier, Make, n8n, scripts). If the core data sits in spreadsheets or a tool without an API, the agent's lookup tools need a sync layer first (add 1-2 weeks).
- Risk: a vague post often means an unclear owner inside the team. Ask who signs off and who the agent escalates to.
- Nothing about their volumes is known; every number on the prototype is illustrative.

## Standard pricing
- Market for a dedicated AI automation developer on retainer: roughly $3,000-$6,000 a month for a senior builder at full-time capacity; $25-$60/hr hourly.
- Post range $10-$40/hr, bids average $28.10. At full time (about 160 h/month) that is $1,600-$6,400 a month. The low end is below market for agent work; aim for the upper half.
- Recurring software (client pays): n8n cloud or self-hosted ($20-$60/mo or a small VPS), Claude API usage (likely $30-$200/mo at small-business volumes), logging/alerting (free tier to $20/mo).

## Ask before quoting
- What does the business do, and where does manual work pile up today?
- Which tools hold customers, orders and requests? API access and admin logins?
- What automations exist already, on what platform, and which ones break?
- Request volume per day/week, and who handles escalations?
- Full time as in 40 h/week hourly, or a fixed monthly retainer?

## Flags
- Client record not pulled; 1 invite; Nigeria; no business named. Metrics are flags, not a reason to skip.
- Full time: pitch as a retainer.

## Pricing path (Lorenzo only)
- Value per year (assumption, the post gives none): 38.5 hours a week of manual work removed (the prototype's illustrative total) x an assumed $8/hr loaded staff cost x 50 weeks = about $15,400 a year in time; more if requests answered faster lift sales, not counted.
- 10-20% of value: $1,500-$3,100 for the first build block. Given the full-time framing, anchor the retainer on the post's rate instead: $30-$40/hr, or $3,500-$4,500 a month fixed.
- Land offer (milestone 1): discovery + opportunity map + audit of existing automations, one week.
- Upsell path: flagship agent workflow -> hardening existing systems -> monthly retainer with reliability dashboard and weekly report -> next workflows from the map.
- Milestones for the first month (if fixed rather than hourly):
  1. 20% paid once the discovery session, opportunity map and existing-systems audit are delivered and you've signed off.
  2. 40% paid once the flagship agent workflow is running in shadow mode on your data and you've signed off.
  3. 25% paid once the flagship workflow is live and 2-3 existing workflows are hardened with retries and alerts and you've signed off.
  4. 15% paid once the run dashboard, alerting and first weekly report are delivered and you've signed off.
