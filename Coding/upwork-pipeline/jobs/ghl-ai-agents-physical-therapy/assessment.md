# Assessment (private, never in the proposal)

## Time
- First clinic, done properly: AI agent (knowledge, guardrails, red-flag screen, handoff, tools for slots/booking/contact updates), four workflows (new inquiry, no-show recovery, plan-of-care drop-off, discharge review request), tool connections, reporting view: 35 to 45 hours, 2 to 3 calendar weeks including testing on real conversations.
- Each further clinic from the template (snapshot + clinic knowledge + calendars + numbers): 4 to 6 hours.
- Ongoing improvement: 3 to 5 hours a week reviewing conversations and adjusting prompts and workflow timing.

## Likelihood
- High for the GHL side: calendars, workflows, tags, pipeline stages, SMS and web chat are standard.
- Unverified for Lorenzo: whether they want GHL's native Conversation AI / Agent Studio or an external model (Claude) wired through webhooks and the GHL API. The external route gives real tool calls and guardrails; native is simpler to hand over. Ask first.
- EMR sync (WebPT or other) is the main risk: many PT EMRs have limited or partner-only APIs, so plan-of-care visit counts may need a scheduled export or manual stage moves.
- Healthcare: the agent must not diagnose; HIPAA posture of GHL (BAA availability on their plan) is the client's decision and should be raised, not promised.
- Sub-account access per clinic, LC Phone / A2P 10DLC registration per clinic for texting.

## Standard pricing
- Market for GHL + AI agent builds in healthcare: $60 to $120/hour, or $3,000 to $6,000 for a first-clinic build, plus $500 to $1,500 per extra clinic and a monthly optimisation retainer.
- Post's rate ($5-$20/hr) is far below market; recorded bids average $19.29.
- Recurring software: GHL plan (theirs), model API usage roughly $20 to $80 per clinic a month depending on volume, SMS costs.

## Ask before quoting
- How many clinics, how many locations each, and roughly how many new inquiries a month?
- GHL native AI or an external model? Agency plan with snapshots?
- Which EMR, and do they have API access?
- Is a BAA in place with GHL for PHI in conversations?
- What already exists: calendars, pipelines, current workflows?

## Flags
- Low rate, part time. No client metrics pulled.
- Healthcare compliance questions sit with the client.

## Pricing path (Lorenzo only)
- Value per clinic per year (assumption: 60 inquiries a month, the agent and no-show/drop-off recovery add 6 evaluations a month, each evaluation worth about $900 across a plan of care): 6 x 12 x $900 = about $64,800 a year per clinic.
- Price range at 10-20% of one clinic's value: $6,500 to $13,000 for the template plus first clinic; realistically quote the low end given the post.
- Land offer (milestone 1): the AI agent plus the new-inquiry-to-booked-evaluation workflow for one clinic.
- Upsell: no-show and plan-of-care workflows, review requests, each extra clinic, monthly optimisation retainer.
- Milestones:
  1. 35%: paid once the AI agent and the new-inquiry workflow for the first clinic are delivered and you've signed off.
  2. 25%: paid once no-show recovery and plan-of-care reactivation are delivered and you've signed off.
  3. 20%: paid once review requests, tool connections and the performance view are delivered and you've signed off.
  4. 20%: paid once the clinic template is rolled out to the second clinic and you've signed off.
