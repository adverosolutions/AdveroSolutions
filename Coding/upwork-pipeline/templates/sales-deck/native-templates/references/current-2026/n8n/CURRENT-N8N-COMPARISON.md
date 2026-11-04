# Current official n8n AI references

Captured and visually inspected 20 October 2026. This bounded reference task changed no specs, shared assets, locks or queue state.

- **n8n-ai-logs-2026-08.png**: official “Building AI Agent Observability for Production Workflows”, published 14 August 2026, https://blog.n8n.io/ai-agent-observability/ . Image URL is under /2026/08/ and source text describes a workflow canvas and logs. Full native workflow viewport with Editor/Executions/Evaluations, left application rail, Execute workflow, lower Chat/Logs/output panes, rectangular AI Agent and bottom diamond typed ports. This is the strongest current editor/chrome/AI-cluster reference. Dark theme; no edition or exact release assertion.
- **n8n-ai-memory-2026-07.png**: official “AI Agent Memory: Types, Storage, and How To Implement It”, published 7 July 2026, https://blog.n8n.io/ai-agent-memory/ . Image is under /2026/07/. Shows AI Agent with exactly Chat Model/Memory/Tool bottom ports, a direct circular OpenAI Chat Model node wired to Chat Model, and tools separately connected through dashed typed edges. It is a canvas crop without full chrome. This resolves the direct OpenAI connection requirement without relying on April 2025 images.
- **n8n-native-trace-2026-05.png**: official “How to debug failures or missteps in AI agent behavior?”, published 2 June 2026, https://blog.n8n.io/how-to-debug-failures-or-missteps-in-ai-agent-behavior/ . Image under /2026/05/. Shows full native Executions layout, Personal breadcrumb and workflow name, Published state, Editor/Executions/Evaluations, execution sidebar, timestamps/duration/ID, canvas, and Chat/Logs/INPUT/OUTPUT. A visible result in a node inspector is distinct from this run trace; do not imply one is the other.

Original URLs, publication dates, checked dates and SHA256 hashes are in sources.json. The files were downloaded directly from asset URLs discovered in the current official article HTML. Pixels were inspected, not inferred from image alt text. The source dates are explicit 2026 publication/asset paths, not dates guessed from the current webpage crawl.

## Candidate comparison for main/reviewer

The current evidence confirms the implemented split between main-flow connections and lower typed dashed model/tool wires, rectangular AI Agent and circular subnodes. July confirms a direct OpenAI Chat Model attachment and no mandatory Output Parser port when that option is absent. Memory can appear as an unused typed port.

The current official AI Agent icon is an overlapping rounded person/bust outline. The April 2025 robot glyph is outdated. Main should update that glyph before claiming current visual parity; this reference-only worker made no runtime edits. The candidate is light theme; saved light editor/inspector references remain the palette and chrome counterpart, while these new dark sources establish current AI node geometry and connection semantics. The new sources must not be relabeled as screenshots from a light target account.

Current header evidence also shows Published state in the Executions capture; the candidate's older generic Inactive switch may not match that release. The post supplies no target version. Main/reviewer should judge that mismatch explicitly rather than treating publication recency as blanket acceptance.
