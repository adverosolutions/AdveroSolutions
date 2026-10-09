# Private delivery assessment (not for the proposal)

**Read first.** Hourly $35-$75, part time, expert, US-only, Texas. The post names no company, industry, tool or volume, so every tool on the canvas (HubSpot, ClickUp, Slack, Gmail) is a committed guess for an ops / consulting / agency team. Their one prior hire ("AI Operations & Agentic Workflow Expert: Automate Our Ops Layer (SOPs, Agents, Integrations)") was fixed, $100, closed after 2 days, and they are hiring for the same work again. Private: never mention that hire to them. It reads as a small trial that did not become the ongoing build, so the first milestone has to be concrete, small and visibly tied to "business impact" (their title's first words). Recorded bids avg $67.79, range $34-$180. 18 connects.

**Time.** First phase (parts 1 to 5 for one agent): 25 to 40 hours, 2 to 4 calendar weeks at part-time pace, most of the spread from waiting on access and on their fit rules.
- Part 1, workflow audit and automation roadmap: 2 or 3 calls with the team, map the manual workflows, rank targets by hours saved and risk, write the roadmap: 8 to 14 h.
- Parts 2 and 3, the client intake agent on the canvas: form webhook 1 to 2 h; HubSpot private app, pipeline and stage ids, contact and deal tools 3 to 4 h; ClickUp tool 1 to 2 h; Slack tool 1 h; agent prompt, parser, safe-to-send gate and both Gmail steps 3 to 5 h; test against 15 to 20 of their real past inquiries and tune the prompt 4 to 6 h. About 14 to 20 h.
- Part 4, architecture, maintenance and troubleshooting doc plus a recorded walkthrough: 3 to 5 h.
- Part 5, error workflow 1 h, then 1 to 2 h a week in the first month reviewing runs and tuning.
Each further agent from their list (project coordination, reporting, follow-up) on the same tools: roughly 10 to 20 h each, depending on what the audit finds.

**Likelihood.** Very buildable; every piece is standard n8n. What can go wrong, weighted to their side:
- Tools are unconfirmed. If they run Pipedrive, Asana or Monday, Teams or Outlook, each tool node is an HTTP call with a different endpoint and body: 2 to 4 h per swap. The agent prompt barely changes.
- Inquiry source unknown: website form tool, email, referrals by phone. A form that can post a webhook is minutes; an email inbox needs a Gmail trigger instead of the webhook.
- HubSpot contact upsert by email (`/crm/v3/objects/contacts/batch/upsert` with `idProperty: email`) is unverified on their portal. Fallback: search by email, then create. The deal-to-contact association type id 3 is HubSpot's default for deal to contact.
- n8n HTTP Request Tool placeholders: how `{placeholder}` values are quoted inside JSON bodies (free text with quotes or new lines in the Slack handoff, the numeric ClickUp assignee) needs one test run. On a current n8n version the native HubSpot, ClickUp and Slack tool nodes (with `$fromAI`) are the cleaner production option; decide once we know their n8n version.
- Agent behaviour: tool order and duplicates. If the agent retries after a deal was created, HubSpot gets two deals. The prompt caps retries at one; production can add a "search deals by contact" guard. The client email itself is protected by the deterministic gate: only `safe_to_send` replies send, everything else is a Gmail draft.
- The Claude node needs a current model picked before recording; the node's default may show an older model name.
- The error trigger fires only when this workflow is set as its own error workflow in its settings, and failed executions must be saved (default on n8n Cloud).
- Data: prospect names, emails and messages go to the Anthropic API. Fine for most service businesses; ask if they serve regulated clients.
- Unverified for Lorenzo: nothing has run on their accounts. Present the canvas as the design he would build, not a delivered system. No past-project claims beyond the case-study bullets.

**Standard pricing.** Market for an expert who builds and deploys agents: $75 to $125 an hour. Fixed equivalents: audit and roadmap $1,000 to $2,500; first agent deployed, tested and documented $2,000 to $4,000; monitor-and-iterate retainer $500 to $1,500 a month. Their $35-$75 band is below that market; at $60 an hour the first phase is about $1,500 to $2,400. Recurring software: n8n Cloud starter tier about $20 to $25 a month or a $5 to $20 VPS self-hosted; Anthropic usage a few cents per inquiry on a Sonnet-class model with four tool calls (check current pricing before quoting); HubSpot private apps and the ClickUp and Slack APIs work on their free tiers; Gmail through their Workspace.

**Ask before quoting.**
- Which CRM, project management tool and chat tool does the team use today? (Canvas assumes HubSpot, ClickUp, Slack and Gmail.)
- Where do new client inquiries arrive (website form tool, shared inbox, referrals) and roughly how many a week?
- What makes someone a fit, which services do you offer, and who owns each?
- Which manual workflow costs the team the most hours right now? That seeds the audit.
- n8n Cloud or self-hosted, and is anything already built or documented we should start from?
- How many hours a week do you want on this, and who maintains it after launch (how technical are they)?
- Do any of your clients sit in regulated industries (health, finance, legal)?

**Flags.**
- US-only applicants: Lorenzo confirms eligibility; the copy asserts no location.
- Portfolio-style ask: "include examples of agentic workflows you've built (not just automations)". Only the case-study facts below may be used; Lorenzo fills the [LORENZO] gaps.
- No off-platform restriction in the post.
- Low total spend ($100) and a 2-day prior contract: expect price sensitivity and a short leash on the first milestone.

## Their questions: draft answers for Lorenzo

**"Include examples of agentic workflows you've built (not just automations)."**
My own outbound runs 100k+ cold emails a month on Instantly, with an agent researching and writing each message; Instantly's API is wired to Claude. I built the routing and follow-up system a commercial roofing contractor runs $750M+ in annual bid volume through, with every estimate request tracked and followed up on, and an outbound system for a software consultancy that personalizes each message instead of blasting a template, which raised their qualified lead volume 35%. [LORENZO: in each, name the step where an agent decides and the tools it calls, e.g. what it routes on and what it researches before writing.] I scaled my own AI agency to $10,000 a month on the same kind of system.

**"Describe a time you identified an automation opportunity a client or team hadn't asked for."**
[LORENZO: one real story in two or three sentences: what they asked for, what you noticed they had not asked for, what you built and the result.] Only if true: on the roofing contractor's bid routing, was following up on every estimate request your idea rather than theirs? If so, the draft is: "They asked me for [X]. I saw estimate requests being lost to manual chasing and added follow-up on every one; that system now carries $750M+ in annual bid volume."
