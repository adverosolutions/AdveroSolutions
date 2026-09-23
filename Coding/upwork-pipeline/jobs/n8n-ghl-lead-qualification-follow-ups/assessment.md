# Private assessment - n8n AI Automation Developer, GoHighLevel CRM, Lead Qualification and Follow-Ups

**Rate vs market.** Posted at $100 fixed, entry level. This is a five-part production
spec: capture and validation, AI qualification, full GHL CRM writes, a stop-aware
follow-up sequence, and monitoring with idempotency and retries. Market for that scope
is $800 to $2,000. The $100 is roughly a tenth of it and the tag is wrong for the ask.
Brand new client account, Punjab Pakistan, 0 contracts, 0 feedback, $0 spent, 0 hires,
0 invites, 90 to 150 bids, 7 connects to apply. Unproven payer on a crowded post.

**Time.** 14 to 20 hours of real work. Roughly: half a day on capture, normalization and
the idempotency guard; half a day on the Claude qualification prompt plus the parser and
the unclear path; a full day on GHL contacts, custom fields, tags, opportunities and
notes once the field ids are known; half a day on the follow-up workflow and the four
stop conditions; half a day on logs, retries, alerts and a duplicate/missing-field/API-down
test pass; then docs and the recorded handover. 1.5 to 2 calendar weeks with normal
client response time, faster if GHL access lands on day one.

**Likelihood.** The build itself is routine for Lorenzo - he runs n8n and the Anthropic
API daily. The risk is all on the client side. GHL needs a private integration token with
contacts, opportunities and workflows scopes; a sub-account owner has to generate it, and
custom field ids and pipeline stage ids have to be pulled from their account before any
mapping is real. The email-sending service is the client's, so deliverability and sender
setup are theirs, not his. Qualification criteria for hot/warm/cold and the approved
follow-up copy do not exist yet in the post, and the whole AI section is only as good as
those. Stop conditions depend on whether their GHL plan exposes the reply/booked/opt-out
events as webhooks. Biggest non-technical risk: a $100 brand new account treating a 20
hour build as an entry level task and scope-creeping to a second source or pipeline.

**Standard pricing.** $1,200 to $1,800 fixed for this exact scope, one source, one
pipeline, one follow-up sequence, with docs and handover included. Recurring software is
the client's: GHL sub-account, n8n cloud or self-host, Anthropic API for the qualification
step, their email sender, a Google Sheet for logs. Roughly $50 to $120 a month depending
on plan and volume.

**How to play it.** Either quote the real number against the real scope, or take the door
opener: one small milestone at their $100 for phase one only - capture, validation,
idempotency and the GHL contact upsert - with the AI qualification, follow-ups and
monitoring quoted separately once the account access is real. Do not deliver all five
parts for $100.

**Ask before quoting.**
- Which form tool is sending the enquiries, and can it post a webhook directly?
- GHL account access: which sub-account, and who can issue the private integration token?
- Which pipeline, and the exact stage names in the order they use them?
- Qualification criteria: what makes a lead hot, warm or cold in their business?
- Approved follow-up messaging and the booking link - do they exist, or is that on me?
- Which email sending service, and is the sender domain already authenticated?
- Who watches the manual review queue, and where do they want the alert - Slack or email?

**Flags.** Screening asks for one relevant automation example, his contribution, and how
he prevents duplicate records and handles failed executions. The Loom answers all three:
the idempotency node and the error trigger, retry and alert chain are both on camera.
No location claim in the copy.
