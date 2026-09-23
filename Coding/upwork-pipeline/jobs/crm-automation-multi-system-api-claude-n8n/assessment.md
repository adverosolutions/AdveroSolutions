# Private delivery assessment (not for the proposal)

**Price flag, read first.** The listed $5 fixed is a placeholder, not a budget, but the client record says to take price sensitivity seriously: 548 contracts and only $5.7k spent in total, about $10 a contract, across small fixed jobs (VAs, research, a chatbot MVP, a designer). Recorded bids average $37.40 on a $5 to $500 range. Expect them to anchor very low. The call has to put a real number on a first milestone before any work starts. Never start on the $5. Posted today, 1 invite, 0 interviewing, 11 connects.

**Time.** A first integration of the shape shown (one CRM, one event type, three connected systems, Claude step, ledger, error path, docs) is 20 to 35 hours, 1.5 to 2.5 calendar weeks. Most of that time goes on waiting for access and testing against real records, not on building. Rough split: validation, ledger and error path 6h; Claude step, schema and a test set 5h; three connectors and their auth 8 to 10h; write-back and loop guard 3h; testing on real records 4 to 6h; documentation 3h. The post reads like an ongoing role (integrations plural, documentation). Once the ledger, error path and conventions exist, each added event type or system is roughly 6 to 12 hours.

**Likelihood.** The build is very doable and the patterns are his daily work. What overruns is on the client side:

- The CRM is unnamed, and that is the biggest swing. HubSpot and Pipedrive have native n8n nodes. GoHighLevel and Zoho are HTTP calls. Salesforce needs a connected app and an admin. Some CRMs send only an id in the webhook, which adds a fetch call per event. Several CRMs put webhook or API access behind higher plans, so confirm the tier.
- Write-back loops. Writing back to the deal can fire the webhook again if the subscription is broad. The build listens to the stage change only and writes sync fields only. The ledger is the second guard.
- One-way push vs two-way sync. The post says "synchronizing". Two-way needs a source-of-truth rule per field and costs 2 to 3 times as much as a one-way push. This is the decision beat in the Loom.
- The Claude step is kept to judgment work (clean names, read plan terms, write the summary) with a forced schema. Ids, emails and amounts go around the model. It still needs 20 to 30 of their real records to test before go-live.
- QuickBooks, if they use it: a customer match by email before the invoice (one more call, not drawn), OAuth token refresh, and testing against a sandbox company rather than their books.
- Canvas simplifications to state honestly if asked. The back-off loop gets a try counter in production so it cannot loop forever. The Error Trigger needs this workflow set as the error workflow in n8n settings. The CRM gets its acknowledgement right after the ledger claim instead of at the end. That is deliberate: CRMs resend slow webhooks, and the ledger makes the early answer safe.
- Hosting and ownership: n8n Cloud or self-hosted, and who owns the credentials, still unknown.

**Claude Code framing (verified fact).** Claude Code is how Lorenzo builds and documents day to day. The post lists Claude, Claude Code and n8n, and the clean split is this. Claude Code is the dev tool: it writes and tests the code nodes and SQL, drives test payloads, and produces the runbook and field-mapping docs from the workflow JSON. n8n is the runtime that runs in production. Claude, through the Anthropic API, is the model inside the workflow. Do not imply Claude Code runs in their production. No claim of past HubSpot or QuickBooks client builds. Frame it as "i build this pattern in n8n, the video shows it".

**Standard pricing.** A competent freelancer charges $1,500 to $4,000 fixed for a first production CRM integration of this shape. Agencies charge $5,000 and up. A smaller first slice (one event, two systems, no AI step) is $600 to $1,200. Hourly equivalent is $60 to $120. If it becomes ongoing, a $1,000 to $2,500 monthly retainer covers maintenance plus new flows. Given this client's history, the realistic path is a small first milestone at a real number, with the rest earned by delivering it. Recurring software: n8n Cloud starter tier or a $10 to $20 VPS, Postgres for the ledger (a free tier is fine at this volume), and Claude API usage well under 5 cents an event on a mid-tier model. Their CRM, Airtable, QuickBooks and Slack are already paid for.

**Ask before quoting.**
- Which CRM, and which plan or edition?
- Which systems on the other side? One-way push or two-way sync, and which system wins a conflict?
- Which business events should trigger work, how many a day, and is there a historical backfill?
- Access: admin rights, API keys or OAuth apps for each system, and sandboxes or test accounts?
- n8n Cloud or self-hosted, an existing instance, and who owns the credentials?
- What exactly should Claude do (transform, enrich, classify, summarize), and is there data that must not go to an LLM?
- Documentation format: README, Notion, or a Loom walkthrough?
- Is the $5 a stand-in for a first milestone, and is this one build or an ongoing role?

**Flags.** No US-only language, no portfolio-link demand, and no off-platform restriction in the post. Client is in California but set to the New York timezone.
