# Dossier - AI Automation Developer for Business Systems

url: https://www.upwork.com/jobs/~022103558841932303752

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: unknown from the post. Hiring history (AI UGC video ads, a sales-focused Shopify specialist, social media managers, a B2B outbound campaign manager, a website copywriter for a personal development brand) points to a small direct-to-consumer online brand selling on Shopify. Used as the likely business for samples only; never stated as fact.
- Location / timezone: Delaware, US (Eastern)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
Claude, Claude Code, n8n, APIs, webhooks, "CRM platforms, databases, communication tools, and other business applications" (no specific CRM, database or chat tool named).
Committed picks for the build: HubSpot (CRM), Supabase Postgres (orders database), Slack (communication tool), Anthropic Claude (model). Shopify is in their hiring history, so the orders table holds Shopify orders.

## Every number in the post
- None in the post body.
- Metadata: "Fixed $5 (placeholder budget)", intermediate level. 58 contracts, 61 jobs with hires, 9 active, "$435 spent", 5.0 over 37 reviews, 88% hire rate, 55 open jobs, 1 invite, 0 interviewing. Bids avg $66.55, range $5-$1,500. 11 connects.
- No volumes (messages a day, orders, team size, refund policy). All of those are labelled inputs on the build and questions in the assessment.

## Their requirements, verbatim, in their order
Deliverables sentence, in order:
1. "AI agent workflows"
2. "Claude/Claude Code integrations"
3. "connected CRM and business system automations"
4. "n8n orchestration workflows"
5. "API and webhook integrations"
6. "automated data retrieval and updates"
7. "error handling"
8. "workflow monitoring"
9. "testing, optimization, and documentation"

Context lines: "designing an automation layer that enables AI agents to interact with CRM platforms, databases, communication tools, and other business applications"; "Experience building production AI agents, integrating multiple systems, and troubleshooting workflows is important."

9 parts in your post, grouped into 3 sections on the canvas:
- Section 1 (parts 1 and 2): the Claude agent workflow.
- Section 2 (parts 3 to 6): CRM, database and Slack, connected by API and webhook, data read and updated automatically (the agent's tools hang under the agent; the webhook reply lives here).
- Section 3 (parts 7 to 9): error handling, monitoring (run log), testing and docs.

## The odd ask only they would recognize
"an automation layer that enables AI agents to interact with CRM platforms, databases, communication tools" plus "Claude Code integrations". On screen: the overview sticky calls this the first piece of their automation layer, and names Claude Code as the second door into the same tools (n8n's MCP Server Trigger), listed as the next add-on.

## What their hiring history implies
A very high-volume hirer of small fixed jobs: 58 contracts for $435 total (about $7.50 a contract), 55 open jobs, 5.0 rating. Placeholder $5 budget. They hire lots of cheap specialists and judge by "does it work". They are unlikely to read a strategy deck; they want to see a working thing. Big price-sensitivity risk for a real build. The post is generic (likely a template), so one concrete system that maps to their list, plus "where do we start", is the right frame.

## Their likely data
One customer message into a small Shopify brand's inbox:

```json
{
  "body": {
    "channel": "email",
    "from_name": "Dana Whitfield",
    "from_email": "dana.whitfield@gmail.com",
    "subject": "Order #1047 still not here",
    "message": "Hi, I ordered the starter bundle 9 days ago and tracking hasn't moved since Monday. It was a birthday gift for Saturday. Can you check or send a replacement?",
    "received_at": "2026-09-25T14:12:00Z"
  }
}
```

Orders row (Supabase): order_number 1047, customer_email, status "shipped", total 64.00, carrier "USPS", tracking_number, shipped_at 2026-09-17, delivered_at null.
HubSpot contact: email, firstname, lifecyclestage customer, custom props last_support_topic, open_issue.

## Sizing (setup / infrastructure / method jobs only)
Not a setup job. No volumes in the post, so no sizing. Their inputs: messages a day, refund limit the agent may approve, who in Slack takes hand-offs.

## Three things they would recognize on screen
1. Their list, in their order: the three section labels name their parts 1-2, 3-6 and 7-9 ("CLAUDE AGENT WORKFLOW", "CRM, DATABASE AND SLACK", "ERROR HANDLING, MONITORING AND TESTING").
2. "Automation layer" and "Claude Code" in the overview sticky: this build is the first piece of the layer; Claude Code reaches the same tools next.
3. Their tools: the agent's four tools hang under the Claude agent and read "HubSpot - Find the Customer", "Orders Database - Look Up Their Shopify Orders", "HubSpot - Update the Contact", "Slack - Hand It to the Team".

## Beat 1 draft
"This is your AI automation layer, built for your online store."
