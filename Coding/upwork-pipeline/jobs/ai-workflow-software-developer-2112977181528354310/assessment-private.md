# Private assessment, job 9 (urgent batch 2026-10-21, U-022 sales-deck control)
- Client: Corwen (business name stated in post), AI consulting/implementation, Salt Lake City. No person name in post; no reviews (0 hires). Personalization: none (account name Corwen, recipient falls back to business name).
- Buyer: lead engineer at an agency hiring a builder. Wants to see: messy data (scanned PDFs, exports) to LLM structured output to plain-code checks, tests (pytest), git review, knowing where LLMs break, client data care, local Ollama option, handoff docs.
- Adapter choice: no prescribed client-facing vendor UI. Post names Claude Code -> claude-code transcript (supported). Custom system -> workbench architecture (supported). Result -> workbench outcome (supported). Optional held-invoice record -> workbench record. No unsupported vendor screen needed; no requires_adapter.
- Sample (invented, illustrative): construction firm client "Basalt & Pine Builders" (fictional), subcontractor pay applications as scanned PDFs checked against the PO export. One invoice held when the model's line items do not add up to the printed total.
- Not claimed: past Corwen-like work, Python/TS years, Flask/React/Postgres experience, Microsoft Graph, any shipped invoice checker. Q1, Q2, Q4 and availability need Lorenzo.

## Scene map (Standard 2 min; Detailed adds the record)
| Stop | Purpose | New fact | Visible evidence | Sec |
| cover | Frame | One scanned invoice in, checked AP entry or a held item out | preview steps | 12 |
| architecture (req) | How one invoice moves | PDF read to a fixed schema, checked against PO and math, approve or hold; Claude API or local Ollama per client | 5-node path ending at held for PM | 30 |
| claude-code (req) | How I build it | pytest fixtures from real-looking scans; a failing test for the misread; fix is a check, not a better prompt; PR for review | 6-stage transcript ending at PR | 30 |
| record (optional) | The held invoice | extracted vs printed total, the line that's off, who decides | source fields vs extracted fields | 15 |
| outcome (req) | Week's batch result | 23 invoices: 19 approved to AP, 3 held, 1 duplicate (illustrative) + handoff docs | stages + metrics | 25 |
| close | Goals + CTA | three directional metrics | metrics + blue CTA | 15 |
