# Dossier - AI Engineer - AI Agent , RAG & Automation

url: https://www.upwork.com/jobs/~022104560265691652492

## Who they are
- First name: unknown
- Company: unknown
- Industry: "our logistics company" (a logistics company looking at AI for its business processes)
- Location / timezone: Poland (CET/CEST)
- Website read: none named

## Client
no client intel

## Tools they named
None. The post names categories only: "AI agents", "workflow automations", "our existing systems", "RAG", "AI-powered internal tools".
Committed for the example build: n8n (runs the workflow), Claude (the agent's model), a vector store (Pinecone, the most common hosted one) with OpenAI embeddings for the RAG search, and an HTTP call into "your existing system" (called their shipment system / TMS on screen, the usual system of record in logistics; its URL is a PASTE-YOUR value).

## Every number in the post
- Hourly $20-$30, expert, part time (metadata)
- Recorded bids avg $26.67 (metadata)
- 0 invites, 0 interviewing, 0 hired (metadata)
- No business numbers in the post: no team size, shipment volume, number of systems or documents.

## Their requirements, verbatim, in their order
1. "Identify processes that can be automated with AI"
2. "Recommend practical AI solutions and tools"
3. "Design AI agents and workflow automations"
4. "Explore integrations with our existing systems"
5. "Advise on RAG and AI-powered internal tools"

5 parts in your post, 5 sections on the canvas. The build is one worked example of what discovery could lead to: an internal operations agent for the team.

## The odd ask only they would recognize
"understand business processes, ask the right questions, and translate business needs into practical AI solutions" and "initially a consulting / discovery engagement, with potential for further implementation". On screen: the overview sticky frames the canvas as an example of what discovery leads to, and the section 1 note is about finding the process first. The word "practical" goes on the section 2 label.

## What their hiring history implies
New account, no hires or reviews, posted today. First AI hire. They will judge on whether he understands logistics operations and asks good questions, not on a finished system. Keep it plain, show one concrete thing, and make the call about their processes.

## Their likely data
A team member's question in the internal chat and the answer the agent gives, with sources.

```json
{
  "sessionId": "ops-chat-4471",
  "chatInput": "Where is shipment PL-WAW-88213 and what do we do if the consignee refuses a damaged pallet on delivery?"
}
```
Output:
```json
{
  "answer": "PL-WAW-88213 is out for delivery, last scan at the Poznan cross-dock 07:42, ETA today 14:00-16:00. If the consignee refuses a damaged pallet: photograph it, note the damage on the CMR before the driver leaves, and open a claim within 7 days (Damage and Claims SOP, section 3.2).",
  "sources": ["Shipment system: PL-WAW-88213", "Damage and Claims SOP v4, section 3.2"],
  "needs_person": false
}
```

## Sizing
Not a setup job; no numbers to size. Team size, question volume and number of systems are asks for the call.

## Three things they would recognize on screen
1. Their five requirements as the five section labels, in their order (sections 1-5).
2. RAG and "existing systems" as real tool sub-nodes on the agent: the SOP search (vector store) and the shipment look-up in their system (node labels on the agent).
3. "Practical" and "ask the right questions": section 2 label and the overview sticky ("an example of what discovery leads to").

## Beat 1 draft
"This is an AI agent and RAG example for your logistics company"
