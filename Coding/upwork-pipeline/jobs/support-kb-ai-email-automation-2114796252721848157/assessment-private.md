# Private notes, pick 7 (saved batch 2026-10-26)
Open check 3:14 PM CT: ACTIVE, can_apply true, 0 hired, 0 invites (read-only find_jobs get).
Client: Canada (ON), no name in post or reviews usable; personalization omitted, account shown as "Your support team".
Client index: no existing row; new file created.
Stack: unnamed helpdesk (open to change), OpenAI and Claude named. Deck uses n8n native editor with AI Agent (OpenAI Chat Model + HTTP Request Tool as KB search), Gmail desktop thread with unsent draft (support inbox stand-in), workbench outcome for KB article and VA lesson. No unsupported adapter needed.
Sample data (invented): PX-48 battery line, 3000 W inverter, Dana Whitfield, SUP-4182, KB-112, POL-07, VA Priya.
Similarity: difflib vs 53 deck specs; renamed metric and one node label that matched other decks exactly.

## Scene map
1. Cover (15s): problem = detailed product questions; promise = answers from own docs + VA training.
2. n8n editor (35s): new fact = email -> question -> AI agent with KB search tool -> draft. Evidence: agent node with two attached subnodes, status line.
3. Gmail thread (30s): new fact = human approves; draft cites KB-112 and POL-07. Evidence: unsent inline reply.
4. Workbench outcome (25s): new fact = same article becomes lesson + quiz. Evidence: stage bar, lesson, quiz question.
5. Close (15s): three directional metrics, baseline, 15-min CTA.
