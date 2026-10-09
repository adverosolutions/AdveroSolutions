# Assessment (private) - AI Agent for Database Interaction (Moshon, Lendersa)

## Time
- Discovery and schema read (tables, columns, which ones are editable, who approves): 3-4 h
- Read tool sub-workflow (parameterised SELECTs across lenders, loan programs, borrower requests, filter mapping): 5-7 h
- Stage tool, agent_pending_changes and agent_change_log tables, apply_agent_change() function with the column allow-list, one transaction: 6-8 h
- Agent prompt tuning on his real questions (land loans, Puerto Rico, LTV, borrower request status), ambiguity handling, the yes-only apply rule: 5-7 h
- Chat embed on an internal page, error alerts, test on a staging copy, handover video: 4-5 h
- Total: 23-31 h, about 2 calendar weeks including his feedback rounds (1.5 if he answers same day).

## Likelihood
- Main unknown: the engine. The post never names it. Built on Postgres; MySQL and SQL Server swap node-for-node in n8n, but the apply function is Postgres SQL and would be rewritten (2-3 h). A proprietary backend (Airtable, Firebase, a Bubble or no-code DB, or a hosted platform with only an API) changes the tools from SQL to HTTP calls: say so on the call before quoting.
- Access: needs a network path from n8n to the database (IP allow-list, SSH tunnel, or a read replica). Hosted databases behind a VPC can cost a day. Unverified until he answers.
- Data risk is the real risk: an agent with write access to a live marketplace. Mitigations are on the canvas and in a beat: staged changes, old vs new shown, apply only on his yes in the same chat, allow-listed columns, no hard deletes (archive only), one transaction, change log to undo from. Recommend a DB login that cannot write directly to tables, only execute the apply function.
- Schema quality: messy column names or free-text fields (states served as text, not arrays) degrade search. Budget time for a view layer.
- Model: Claude through n8n's Anthropic node is solid for tool calling; latency 3-8 s per answer. Unverified on his row counts: large tables need indexed filters and a row limit (set to 50 in the tool).
- Unverified for Lorenzo: no prior build on this schema. Frame as "I have deployed Claude agents with tools on live software" (true), not "I built this for another lender marketplace".

## Standard pricing
- Market for a scoped AI agent with read, guarded write and audit log on an existing database: $2,500-$5,000 fixed (freelance), $8k+ agency.
- His $2,000 fixed sits below market but inside what this scope can be built for at 23-31 h. Bids avg $1,977.84 (range $1,360-$3,000), so competitors cluster at his number.
- Recurring: n8n Cloud Starter about $24/mo or self-hosted $5-20/mo VPS; Anthropic API likely $10-60/mo at internal-team volume (depends on his query volume, unknown).

## Ask before quoting
1. Which database engine and host (Postgres, MySQL, SQL Server, Supabase, something else)? Is there a staging copy or read replica?
2. Which tables and columns should the agent change, and which stay read-only?
3. Who will use the chat (just him, his team, lenders, borrowers)? Internal only or customer-facing? Customer-facing changes the scope a lot.
4. Roughly how many rows in the main tables, and how many questions a day?
5. Does he need a specific front end (Slack, his admin panel, a web page), or is an embedded chat page fine?

## Flags
- Screening asks for "certifications": Lorenzo has none to list; answer with the build itself and his Claude agent deployments, no invented certs.
- "Preferred: $1,000+ earned" is fine.
- No US-only flag, no off-platform restriction stated.
- The client is a heavy consultation buyer (several "30 minute consultation" hires): the Loom plus a clear yes/apply guard is the pitch.
