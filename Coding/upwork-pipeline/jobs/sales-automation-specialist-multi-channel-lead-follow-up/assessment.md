# Delivery assessment (private, never in the proposal)

**The rate.** This is a $15 fixed-price post labelled "complex project" for a scope that is worth far more: workflow design across three pipeline stages, SMS and email drip sequences, CRM integration, end-to-end testing and written documentation. Bid range shows high $300, average $39.67. Market for this scope is $1,500-4,000. Treat it as a lead for a real-priced conversation, not a job to deliver at $15. Do not accept the $15 milestone as the whole project.

**Time.** 14-24 hours, 2-3 calendar weeks. The n8n canvas is a day. The rest is inside their accounts: CRM webhook and custom fields, Twilio number and messaging setup, copy for each touch, testing each stage with real contacts, then documentation.

**Likelihood.** The build itself is low risk. What overruns is all on their side:
- Which CRM they actually have. GoHighLevel has native workflows with SMS and email built in, so a "GHL to n8n" design may be the wrong call and the honest recommendation could be "do it inside GHL". HubSpot's answer depends on tier: Marketing Hub Starter has limited sequences, Professional has workflows. This decides the architecture before anything else.
- SMS compliance. Any US business SMS needs A2P 10DLC brand and campaign registration with Twilio (or the GHL LC Phone equivalent). Approval takes days to weeks and gets rejected for vague use-case descriptions. Nothing sends until it clears, and it is on the client's business entity, not on Lorenzo.
- Consent and quiet hours. Sequences need an opt-in record and STOP handling, plus no SMS at 2am. Missing that is a legal problem, not a bug.
- Reply detection for the exit rule. In GHL it is a conversation event; in HubSpot it is an email reply or meeting-booked property. Each is a different integration and needs testing against real inbound replies.

**Standard pricing.** $1,500-4,000 for design, build, test and docs at this scope. Recurring: Twilio around $1-2/month per number plus ~$0.0083 per SMS segment and the one-time 10DLC registration fees; n8n Cloud from $24/month or self-hosted; CRM tier as applicable. Lorenzo usually bids below market on purpose; the reference number is what matters here.

**Ask before quoting.**
1. Which CRM, exactly, and which tier or plan?
2. Do they already have a Twilio account or GHL phone number, and is 10DLC registration done?
3. How many pipeline stages need a sequence, and who writes the SMS and email copy?
4. What counts as "replied" for the exit rule: SMS reply, email reply, booked meeting, or any of the three?
5. Are they truly open to n8n or Make, or do they want it native inside the CRM?
6. Is the $15 a placeholder for a real budget, or the budget?
