# Assessment (private) - AI Automation Developer for Business Systems

## Time
- The canvas build (one webhook, Claude agent, four tools, run log, error alert), wired to their real HubSpot, database and Slack: 10 to 14 hours, including the test set of past messages and prompt tuning.
- Their full list (several agent workflows across CRM, database, chat and "other business applications", plus Claude Code integration, monitoring and docs) is an ongoing build, not one job: realistically 4 to 8 weeks part-time for the first 3 to 5 workflows.
- Calendar for the first workflow: 1 to 1.5 weeks, most of it waiting on access and test data.

## Likelihood
- The pattern is solid: n8n AI Agent with HTTP tools on HubSpot, Supabase REST and Slack is standard and works.
- What breaks: the post names no systems. If their CRM is not HubSpot or their orders live only in Shopify (no database), the tools change; the agent shape stays. Shopify Admin API as the orders tool is the likely swap.
- HubSpot custom properties (last_support_topic, open_issue, last_order_number) have to be created in their portal; private app token needs crm.objects.contacts read and write.
- Supabase HTTP Request with the predefined supabaseApi credential: expected to work; verify on first run. Fallback is a header auth credential with the apikey header.
- Agent tool-calling order is a prompt instruction, not enforced. Test on 20+ real messages; if it skips the order lookup, move the lookup before the agent as a fixed step.
- Unverified for Lorenzo: no production claim beyond his own agency agents and client Claude/Grok deployments. Frame as "the pattern I use", not "I built this for a store".

## Standard pricing
- Market for the first production agent workflow like this: $1,500 to $3,500 fixed. An ongoing automation-layer retainer: $2,000 to $5,000 a month.
- Recurring software: n8n cloud $24 to $60 a month (or self-host about $10 to $20 on a VPS), Anthropic API usage roughly $20 to $150 a month at small-store volumes depending on message count and model, HubSpot free CRM works for the API calls, Supabase free tier to $25.
- Their posted $5 is a placeholder, and their history is 58 contracts for $435 total (about $7.50 each). Their spend pattern is far below market for this work. Expect heavy price pressure; the call has to establish scope and budget before any build.

## Ask before quoting
- Which CRM, database and chat tool do you run today?
- Which one workflow should go first (support replies, lead follow-up, order ops, reporting)?
- Rough message or lead volume a day, and the refund or approval limit a bot may act on.
- n8n cloud or self-hosted? Anthropic API account already open?
- Do you want Claude Code to call these tools too (MCP), or is n8n the only runner?
- Budget range, since the post shows a placeholder.

## Flags
- Placeholder $5 budget and a very low average spend per contract: price risk.
- 55 open jobs: may be a mass-posting pattern; 1 invite, 0 interviewing so far.
- No US-only flag, no portfolio demand, no off-platform restriction stated.
- Sharp point also on the build and in a beat: the agent answers only from their database, and anything over their refund limit goes to a person in Slack.
