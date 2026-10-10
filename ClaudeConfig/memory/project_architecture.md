---
name: AdveroSolutions 3-layer architecture
description: Directive/orchestration/execution architecture — directives in Markdown, orchestration by AI, execution via deterministic Python scripts
type: project
originSessionId: cee7a0c3-bf45-4668-957d-6c4809e64328
---
AdveroSolutions uses a 3-layer architecture to separate concerns:

1. **Directives** (`Agentic Worklfows/directives/`) — SOPs in Markdown, split into USER/ (manually triggered) and AUTOMATED/ (webhook-triggered)
2. **Orchestration** — AI agent reads directives, calls execution scripts in order, handles errors, updates directives with learnings
3. **Execution** (`Agentic Worklfows/execution/`) — Deterministic Python scripts handling API calls, data processing, deployments

**Why:** Pushing complexity into deterministic code prevents compounding LLM errors (90% accuracy/step = 59% over 5 steps).

**Self-annealing loop:** When something breaks → fix script → test → update directive → system is stronger.

**Key integrations:** Instantly (email), Google Sheets (CRM), Modal (cloud webhooks), GitHub Pages (free-value pages), Claude/Anthropic API (AI responses), AnyMail Finder (email verification).

**How to apply:** Always check existing `execution/` scripts before writing new ones. Don't create or overwrite directives without asking. Deliverables go to cloud services, intermediates go in `.tmp/`.
