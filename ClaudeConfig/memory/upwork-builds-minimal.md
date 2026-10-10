---
name: upwork-builds-minimal
description: n8n/Make Upwork props aim for 10-15 nodes, no fluff, but go over when the post needs it; GHL posts default to a chart
metadata:
  type: feedback
---

n8n and Make builds for Upwork Looms aim for 10 to 15 nodes on the canvas (Config, AI sub-nodes and error path count), every node one the flow needs to run. It is a target, not a cap: every requirement the post names gets its steps even past 15. Nothing added for polish (logging, formatting, double checks). Not so bare it stops making sense: each thing the post asks for still gets its step. Only extras the post did not ask for go in the overview sticky as "room to add next". GoHighLevel posts get a chart unless the post is just one automation; account setups are always charts.

**Why:** 2026-09-24 Lorenzo said the personalization overhaul went "to an extreme": the healthcare build (23 nodes) was "extremely hard to demo". He wants to say "I put this together for you, there's room to add a couple of things." On GHL: "Talking through an entire account setup is just something I don't want to do," and he doesn't want his account crowded.

**How to apply:** Enforced in `_AGENT_BRIEF.md` Shape, `_REVIEWER_BRIEF.md` item 9, `_GHL_BUILDER_BRIEF.md`, both SKILL.md copies, and `verify_job` (WARN above 15, `MAX_CANVAS_NODES`). See [[upwork-quality-overhaul-2026-09]] and [[upwork-ghl-demo-disadvantage]].

Same day, correction: "I didn't want it to be a rigorous rule that it has to be between 10 and 15. I just wanted it to be understandable and not take all day, but if the workflow requires it, it can go over." The first pass (a hard cap) produced a HubSpot/Shopify build that pushed abandoned checkout, a named requirement, to "next".

2026-09-25: an "agent" on an n8n canvas must be an ai.agent with real tool sub-nodes doing visible work. The PI demand-package canvas used two bare Claude LLM steps and he dropped it: "It makes the agent look like it does nothing. You didn't give it any tools." Rule in `_AGENT_BRIEF.md` ("An agent has tools").
