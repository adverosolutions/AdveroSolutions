# Assessment (private, never in the proposal)

## Time
- First production workflow (one inbound receptionist, one number, calendar + CRM + SMS + one n8n follow-up): 30 to 45 hours over 2 to 3 calendar weeks, most of it prompt and guardrail tuning against recorded test calls.
- Outbound follow-up campaign on top: 15 to 20 hours, 1 week.
- Each further agent (support line, sales assistant): 10 to 20 hours reusing the same tools.

## Likelihood
- Voice quality is the soft spot. Lorenzo's view (2026-09-25): AI call agents are poor right now. Latency, barge-in and accents break calls; do not promise conversion or "sounds human". Promise the loop: every call answered, recorded, handed off when it should be, and followed up.
- Vapi vs Retell: unverified which suits them; pick after one test call on their numbers. Both need a Twilio number imported (or their own SIP).
- Outbound calling is regulated (consent, calling hours, do-not-call registers, AI disclosure). Their jurisdiction's rules must be checked before any outbound goes live; the prototype shows the guardrails but the legal read is theirs.
- Unknown CRM and calendar. HubSpot and Google Calendar assumed; a field-service CRM (ServiceTitan, Jobber, etc.) changes the tool calls.
- Unverified for Lorenzo: he has not shipped a production voice agent per the facts list. Frame as n8n + Claude + CRM loop expertise, with the voice runtime as the piece tested first.

## Standard pricing
- Market: a single production voice receptionist with CRM/calendar/SMS wiring runs about $2,500 to $6,000 setup; ongoing tuning retainers $500 to $1,500 a month.
- Recurring software (their account): Vapi or Retell usage roughly $0.07 to $0.15 a minute all-in, Twilio number and minutes, LLM tokens, n8n cloud or self-hosted.
- The post's $15 fixed is a placeholder; bid avg $82.61. Treat as a scoping conversation, never price in the proposal.

## Ask before quoting
- What business or businesses is this for, and is it one company or an agency serving clients?
- Monthly inbound and outbound call volume; after-hours cover or all day?
- Which CRM and calendar; any field-service software?
- Vapi or Retell already chosen, or open? Existing Twilio numbers?
- Which country's calling rules apply to outbound?
- What must always go to a human (pricing, complaints, emergencies)?

## Flags
- $15 fixed budget (placeholder). Client record not pulled. Broad "what you'll build" list reads like a hiring post for an ongoing consultant.

## Pricing path (Lorenzo only)
- Value: assumption, 10 missed or after-hours calls a week recovered, 30% become jobs at an assumed $400 average job: about $62,000 a year. Plus front-desk time saved, assumed 10 hours a week at $30: about $15,600. Total about $78,000 a year (all assumptions).
- Price range at 10 to 20%: $7,800 to $15,600 for the full system; realistic first engagement lower.
- Land offer (milestone 1): the inbound receptionist on one number with booking and CRM note, $2,500 to $3,500.
- Upsell path: outbound lead follow-up, then a support line agent, then a monthly tuning retainer (call review, prompt updates, analytics).
- Milestones:
  1. 30%: paid once the receptionist answers test calls on your number, qualifies and books into your calendar are delivered and you've signed off.
  2. 30%: paid once the CRM record, SMS confirmation and n8n follow-up after every call are delivered and you've signed off.
  3. 25%: paid once the human handoff, guardrails and outbound follow-up campaign are delivered and you've signed off.
  4. 15%: paid once the analytics view, runbook and two weeks of live tuning are delivered and you've signed off.
