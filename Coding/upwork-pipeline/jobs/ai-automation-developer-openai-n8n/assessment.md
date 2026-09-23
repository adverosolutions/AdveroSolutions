# Private assessment - AI Automation Developer (OpenAI, n8n/Make/Zapier)

**Rate vs market.** The $20 fixed price is a placeholder (intermediate tag). Recorded bids
average $91.25, range $5 to $2,000. Client is in Ontario: 155 contracts, 148 jobs with
hires, 6 active, $9.0k spent, 4.99 over 145 reviews. That works out to about $60 a
contract: a high-volume hirer of small fixed jobs (website redesign, VA for client
follow-up, brand identity). They closed a "GoHighLevel (GHL) Expert Needed to Audit, Fix &
Automate Our System (GHL + n8n)" contract at 5 stars on 2026-09-19, three days before this
post. So they probably have GHL and an n8n instance someone just cleaned up, and now want
a cheap, reliable builder on call for small AI workflows. Expect price sensitivity. They
review well and close contracts.

**Time.** For the build on the canvas: 4 to 6 hours of real work. That covers 1 to 2 hours
of wiring, 1 to 2 hours tuning the prompt against 15 to 20 of their real past requests,
1 hour testing each arm and the error path, and 1 hour on the handover Loom and notes. 2 to
3 calendar days if access arrives on day one. Their real first workflow is unknown; most
"simple" ones land between 3 and 10 hours. Debugging someone else's workflow needs 1 to 2
hours of reading before a fix estimate means anything.

**Likelihood.** The build is routine for Lorenzo: he works in n8n every day and runs an
agent that writes every outbound message in his own system. What he hasn't verified: his
daily LLM work is on the Anthropic API, not OpenAI. The canvas runs on OpenAI as the post
asks, so the copy says "the video shows it on openai" and claims no OpenAI production
history. The post lists "basic Python/API knowledge"; don't claim Python projects unless he
confirms them. The real risks sit with the client: Gmail OAuth in n8n (self-hosted needs a
Google Cloud app), whether their n8n is cloud or self-hosted and who holds admin since the
last contractor, and a GHL private integration token if the first workflow touches GHL.
Prompt quality depends on real sample requests. The commercial risk is bigger than the
technical one: at about $60 a contract, "build and maintain" drifts into unpaid maintenance.

**Standard pricing.**
- First small workflow like this one, tested and handed over: $300 to $700 fixed.
- Ongoing maintenance: $40 to $75/hr as needed, or a $300 to $600/month retainer for about
  5 to 8 hours of fixes and small changes.
- This client's history anchors near $50 to $150 per job. A door-opener of $150 to $250 for
  the first workflow, then hourly for fixes and changes, keeps it paid. Don't match $20, and
  don't bundle "maintain" into a fixed price.
- Recurring software (the client pays): n8n Cloud starter around $25 to $30/month, or
  self-hosted on a $5 to $10 VPS (they likely already run n8n). OpenAI API usage stays under
  $5/month at a few thousand requests on a mini model. They probably already pay for Slack
  and Google Workspace.

**Ask before quoting.**
1. Which workflow first: what is done by hand today, who does it, and how long it takes.
2. Which tools: CRM (GHL?), Gmail or Outlook, Slack or Teams or SMS, and where requests arrive.
3. Volume: requests per day or month, and the peaks.
4. Their n8n: cloud or self-hosted, who has admin, and is last week's GHL + n8n work what
   needs maintaining?
5. OpenAI: their own API key and account, and any model preference.
6. Maintenance: how often things change, the response time they expect, hours per month.

**Flags.** The post asks for "a few examples of AI or workflow automations"; the four P.S.
case studies and the Loom cover that. There is no screening question box. Make no location
claim. 14 connects. Posted today with 1 invite and 0 interviewing, so we're early. Their
GHL + n8n stack is the likely home for the first real workflow. The canvas sticks to the
tools the post names (OpenAI, n8n, APIs and webhooks) and uses Sheets, Slack and Gmail as
stand-ins. The call confirms what they actually use.
