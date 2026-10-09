# Dossier - AI Automation Consultant Needed for Claude Code & n8n Project

url: https://www.upwork.com/jobs/~022104598728603613794

## Who they are
- First name: unknown
- Company: unknown
- Industry: unknown. The post describes the work, not the business ("implementing and configuring AI automation workflows").
- Location / timezone: United States
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
Claude Code, n8n (in that order). Also "APIs and third-party tools" and "LLM-based applications" without names.
Committed for the prototype (most common, post names none): HubSpot as the CRM, Gmail and a web form as intake, Slack for team alerts, Google Sheets as the shared log, a REST Orders API as the business system, Postgres for the audit table.

## Every number in the post
- "Fixed $20" (metadata: budget)
- "short project"
- Recorded bids avg $133.52 (metadata)
No volumes, dates or counts about their business. Every run count, rate and duration on the Monitoring screen is labelled illustrative.

## Their requirements, verbatim, in their order
1. "Build and customize AI agents"
2. "Work confidently with Claude Code"
3. "Create AI-powered automation workflows"
4. "Integrate APIs and third-party tools"
5. "Use n8n for workflow automation"
6. "Understand LLM-based applications and agent workflows"
6 parts in your post, 6 screens in the prototype (plus Overview): Agent, Claude Code, Workflows, Integrations, n8n, Monitoring. Part 6 is shown as the Monitoring screen: runs, failures, retries and the full trace of each agent run.

## The odd ask only they would recognize
"The selected freelancer will work on legitimate, authorized systems and integrations and will be expected to follow applicable platform and service terms." On screen: the Integrations screen shows each connection's auth method and scopes (read or write), and CLAUDE.md states that side effects only go through the n8n webhook.

## What their hiring history implies
Client record not pulled. $20 fixed against an average bid of $133.52 suggests a first paid test or a placeholder budget ahead of a larger scope ("potential for additional work").

## Their likely data
Unknown business, so the prototype uses a neutral online-store support request (labelled sample):

```json
{ "request_id": "req_28091", "channel": "email", "from": "maya.ortiz@example.com", "subject": "Order 10482 arrived damaged", "order_id": "10482", "order_total_usd": 84.00, "delivered": "2026-09-26", "asks": "replacement before Friday" }
```

## Sizing
Not a setup job; no sizing. Policy threshold on screen ($150 auto-replace limit) is a sample setting the client changes.

## Three things they would recognize on screen
1. Claude Code: a real project view with CLAUDE.md, typed tool definitions and evals (Claude Code tab, header says "Built with Claude Code").
2. n8n: the side-effects workflow drawn as a canvas that runs (n8n tab), plus "Runs on n8n" in the Overview journey.
3. "AI agents" with visible tool calls and "APIs and third-party tools" as a map with auth and scopes (Agent and Integrations tabs).

## Beat 1 draft
"This is a working prototype of your Claude Code agent with n8n."
