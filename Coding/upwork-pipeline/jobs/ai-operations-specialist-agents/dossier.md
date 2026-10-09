# Dossier - Focus on Business Impact: AI Operations Specialist - Workflow Automation & Custom AI Agents

url: https://www.upwork.com/jobs/~022103206040938502805

## Who they are
- First name: unknown (no `client first name:` line, the post is unsigned)
- Company: unknown
- Industry: unknown from the post directly. Best reading: an operations, consulting or agency team, from "Prior experience in an operations, consulting, or agency environment is a plus" and the tasks they list ("client intake, project coordination, reporting, and follow-up"), which are service-business work.
- Location / timezone: Texas, US. US-only applicants.
- Website read: none named.

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
In order: "CRM, project management, communication platforms" (categories only, no product), "ChatGPT" (named as what they do NOT want: "not just prompting ChatGPT"), "n8n, Make, custom LLM pipelines, or similar" (orchestration examples).

Committed picks, and why:
- n8n: first orchestration tool they name.
- HubSpot (CRM): the default CRM for small B2B consulting and agency teams; its free tier is where most of them start.
- ClickUp (project management): the most common PM tool in agencies and ops consultancies; tasks, assignees and lists map straight onto "project coordination".
- Slack (communication platform, internal): the default team channel for this kind of team; the owner handoff lands there.
- Gmail (communication platform, client-facing): the client's reply goes from the team's inbox.
- Claude on the Anthropic API: the agent's model (Lorenzo uses it daily).
None of HubSpot, ClickUp, Slack or Gmail is confirmed by the post; the assessment asks.

## Every number in the post
Post body: no numbers at all (no volumes, headcount, tool count, budget or dates).
Metadata:
- "Hourly $35-$75", "expert", "part time"
- "Texas, US (US-only applicants)"
- "1 contract, 1 job with hires, $100 spent, 5.0 over 1 review"
- Their one hire: fixed, "2026-09-15 to 2026-09-17 (closed after 2 days)"
- "Posted about 2026-09-24", "0 invites, 0 interviewing, 0 hired"
- "Recorded bids avg $67.79, range $34-$180 (basis unspecified)"
- "Connects to apply: 18"
Missing numbers they obviously have (inquiries a week, team size, number of services and owners) go to "Ask before quoting" and appear on the build only as their inputs in Config.

## Their requirements, verbatim, in their order
1. "Audit current manual workflows and identify highest-value automation targets"
2. "Design and deploy AI agents for tasks like client intake, project coordination, reporting, and follow-up"
3. "Integrate agents with existing tools (CRM, project management, communication platforms)"
4. "Build documentation and handoff materials so the team can maintain systems after launch"
5. "Test, monitor, and iterate on agent performance post-deployment"

Deliverables list maps onto these: "Workflow audit and automation roadmap" = part 1; "Deployed and tested agent(s) solving the identified use case(s)" = parts 2, 3 and 5; "Documentation covering system architecture, maintenance, and troubleshooting" = part 4.

5 parts in the post, 3 sections on the canvas: part 2 (section 1, the client intake agent), part 3 (section 2, HubSpot, ClickUp, Slack and Gmail), part 5 (section 3, test, monitor and iterate). Parts 1 and 4 are written deliverables, not steps: they sit in the overview sticky ("Your part 1", "Your part 4") and in the assessment. Of the four agent tasks in part 2, client intake is built; project coordination, reporting and follow-up are named in the overview as room to add next on the same tools.

Application asks (answered in the assessment, for Lorenzo): "include examples of agentic workflows you've built (not just automations)" and "briefly describe a time you identified an automation opportunity a client or team hadn't asked for".

## The odd ask only they would recognize
They draw the agent-versus-automation line twice: "Proven track record building and deploying AI agents (not just prompting ChatGPT)" and "examples of agentic workflows you've built (not just automations)". The title also leads with "Focus on Business Impact". On screen: the agent node's note and the first overview line say it is an agent that decides which tools to call, not a fixed automation; beat 2 says it out loud.

## What their hiring history implies
One prior hire, $100 total, 5.0: "AI Operations & Agentic Workflow Expert: Automate Our Ops Layer (SOPs, Agents, Integrations)", fixed, closed after 2 days. Now they post the same kind of work again, hourly and part time. Reading: the first hire was a small fixed trial or a short consult that did not turn into the ongoing build; they want someone who stays and ships working agents over weeks. $100 of total spend says small budgets so far, so the first milestone has to be concrete and cheap to say yes to. Private: never mention the earlier hire to them.

## Their likely data
One inquiry from their website "work with us" form, from a prospective client of theirs (illustrative):

```json
{
  "first_name": "Marcus",
  "last_name": "Bell",
  "email": "marcus.bell@gulfcoastpropertygroup.com",
  "company": "Gulf Coast Property Group",
  "job_title": "Operations Manager",
  "website": "gulfcoastpropertygroup.com",
  "service_interest": "Automation build",
  "budget_range": "$5,000 - $10,000",
  "timeline": "Start within 30 days",
  "message": "We manage about 1,100 rental units with a team of 14. Maintenance requests come in by phone, text and email, and two coordinators re-type all of it into our property system and a spreadsheet. I'd like to see what can be automated before we hire a third coordinator.",
  "source": "Website - Work With Us form"
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job, and the post gives no volumes. Nothing to size from their numbers.

## Three things they would recognize on screen
1. The agent-versus-automation line: agent node note ("An agent, not a fixed automation: it decides which tools each inquiry needs") and the first "How it works" line of the overview.
2. Their own task list from part 2: the overview's "Room to add next: project coordination, reporting and follow-up agents, on the same tools"; section 1's label names client intake.
3. Part 5 in their words: section 3 is "3 - TEST, MONITOR AND ITERATE"; parts 1 and 4 (audit and roadmap, documentation) appear by name in the overview's Setup list.

## Beat 1 draft
"This is a client intake agent for your ops and consulting team."
