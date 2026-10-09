# Dossier - AI Agent for Database Interaction

url: https://www.upwork.com/jobs/~022103574753133070901

## Who they are
- First name: Moshon (from the `client first name:` line)
- Company: Lendersa, plainly inferable from the hiring history (a Wikitia page for Lendersa, lender lists, a training manual for lenders, finance/mortgage link building). The post itself names no company, so the build says "your Lendersa database" and never claims anything about the business beyond what the history shows.
- Industry: lender marketplace (lenders, their loan programs, borrower loan requests); history leans to land loans, Puerto Rico lending and mortgage content
- Location / timezone: California, US (Pacific)
- Website read: none named in the post

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
None. The post says only "my existing database" and "the current database system".
Committed: Postgres (the most common engine behind a marketplace web app, and n8n's Postgres node covers read, update and query with parameters). Agent model: Claude (Anthropic), per the brief. Chat front end: n8n's chat trigger (embeddable on an internal page). The engine is confirmed on the call; MySQL or SQL Server swap node-for-node.

## Every number in the post
- "Fixed $2,000" budget, intermediate level (metadata)
- Bids avg $1,977.84, range $1,360-$3,000 (metadata)
- 48 contracts, 41 hires, 7 active, $136,990.80 spent, 4.96 over 33 reviews, 80% hire rate (metadata, private)
- No numbers about the database itself (table count, row count, users, queries a day). All of those are inputs, asked in the assessment.

## Their requirements, verbatim, in their order
1. "build an AI agent that can interact with my existing database"
2. "retrieve, update, and manage data efficiently"
3. "providing a smooth user experience"
4. "integrate the AI with the current database system"
5. "ensure reliable performance"

5 parts in the post, 4 sections on the canvas: parts 2 and 3 share section 2 (retrieving and updating is the smooth experience: one chat, answers in plain English, a change shown back before it happens). Section notes name the grouping.

## The odd ask only they would recognize
"retrieve, update, and manage" on an *existing* database: they want write access, not a read-only chatbot. The build answers it with the guarded write: the agent stages every change and shows old value vs new value, and nothing touches a live row until they type yes. Every applied change lands in a change log.

## What their hiring history implies
A high-volume, repeat hirer ($137k spent, 48 contracts, 80% hire rate, many "30 minute consultation" hires). Runs Lendersa's content, SEO and data work through freelancers. Judges by whether it works on his real data, fast. A fixed $2,000 build with a clear scope, not a strategy deck. Owner-operator who will use the chat himself.

## Their likely data
Tables `lenders`, `loan_programs`, `borrower_requests`. One record (illustrative):

```json
{
  "lender": {"lender_id": 3127, "name": "Caribe Land Capital", "type": "private lender", "states_served": ["PR", "FL"], "status": "active"},
  "loan_program": {"program_id": 8841, "lender_id": 3127, "program_name": "Raw Land Loan - Puerto Rico", "loan_type": "land", "max_ltv": 60, "min_loan": 150000, "max_loan": 2500000, "updated_at": "2026-08-14"},
  "borrower_request": {"request_id": "BR-20418", "loan_type": "land", "property_state": "PR", "property_city": "Rincon", "loan_amount": 420000, "ltv": 55, "status": "new"}
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job. No sizing numbers in the post.

## Three things they would recognize on screen
1. Lendersa tables by name: lenders, loan programs, borrower requests (title, agent label, tool labels, samples).
2. Puerto Rico land loan lenders in the sample question and answer (input_sample and output_sample), echoing the lists he has hired for.
3. "Updates Wait for Your Yes" (section 2 label and branch label): his "update, and manage" answered with a guard, plus the change log.

## Beat 1 draft
"Moshon, this is an AI agent for your Lendersa database"
