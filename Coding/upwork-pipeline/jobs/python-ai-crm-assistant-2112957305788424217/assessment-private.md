# Private assessment, job 2 (urgent batch 2026-10-21, U-022 control template)
- CRM vendor not named in the post, so no native CRM screen. All scenes use the custom workbench (Custom project workspace). No requires_adapter.
- Personalization: client reviews say "Hakims" in 4 separate reviews (2026-08-28 to 2026-09-28). Reads like a username or company handle, not clearly one person's first name, so omitted per U-006 (ambiguous). Greeting stays "Hey there". Lorenzo can confirm.
- Approved facts that fit: builds AI agents on a client's existing database for numerous companies; deploys systems daily; works daily with MCP tools on live APIs. NOT approved: Python, FastAPI, PostgreSQL, AWS experience claims. Left as placeholders.
- No screening questions in the post.

## Scene map (Standard 2 min)
| Stop | Purpose | New fact | Visible evidence | Seconds |
| cover | problem + promise | lead in, clean record out | anchors, 3 preview steps | 15 |
| pipeline (architecture, required) | how the assistant runs | webhook to FastAPI, Postgres checks, LLM API, REST write-back | 5 connected nodes, one sample lead path | 30 |
| duplicate (record, required) | duplicate detection + validation | incoming lead matches existing contact; phone fixed; merge held for a person | incoming vs existing fields, check events | 25 |
| history (messages, optional, Detailed) | what the summary reads | 3 past interactions | email, call note, reply | 20 |
| crm-update (outcome, required) | result | CRM record updated with category, summary, merge flag | stages, record fields, sample metrics | 30 |
| close | metrics + CTA | 3 directional metrics | blue CTA | 15 |
