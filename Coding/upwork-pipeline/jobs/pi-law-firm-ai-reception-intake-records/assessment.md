# Assessment (private) - Personal injury firm, first call to settlement in 3 languages

## Honesty line (read before the proposal and the call)
Lorenzo has no personal injury law firm work, no legal practice management software integrations, no medical records or medical billing processing, and no Haitian Creole voice agent behind him. Nothing on the chart, in a beat or in the proposal may imply otherwise. The post's applicant questions 1 to 5 ask exactly this; the honest answer is "not for a PI firm; here is how I would build and test it", backed by what is true: Claude and Grok agents deployed in his agency and for client companies, n8n and Make daily, Claude Code and the Anthropic API daily with MCP tools wired into live software, consulting for very large companies.

## Time (by the three phases they asked about)
- Initial assessment: 25 to 40 hours over 2 to 3 calendar weeks. Map their current intake, records and demand workflow with staff; confirm their case management and document systems and what their APIs allow; test Haitian Creole voice (two or three voice platforms) with a Creole speaker they trust; write the roadmap and security plan.
- First implementation phase (parts 1 and 2: AI receptionist and intake to signed agreement, synced to their case management system): 120 to 200 hours over 6 to 10 calendar weeks, including a supervised pilot on one line or after-hours only.
- Full-office automation (adds parts 3 to 6: records requests and chasing, record and bill extraction with page citations, demand drafting from their templates with the attorney gate, Word and PDF export with exhibit index, case stage automation, dashboards, multilingual client updates): another 350 to 600 hours over 4 to 7 months, phased so each part runs in shadow before staff rely on it.
- Realistic total: 6 to 9 months from kickoff to full office, part time as the post says.

## Likelihood (what breaks)
- Haitian Creole voice: the weakest link. Speech recognition and natural voice for Haitian Creole are far less mature than English or Spanish; unverified for Lorenzo. Plan: test before promising, with fallbacks (Creole text by SMS, or voice menu then a callback from a Creole-speaking staff member). This goes on the chart (band 1 note) and in a beat.
- Case management system API: unknown system. Some legal systems have solid APIs and webhooks, others are closed or partner-only. This decides whether band 5 is a direct integration or a workaround. Unverified for Lorenzo.
- Medical records: providers answer by fax, portal, mail or a records vendor; many records arrive as scans. OCR quality and handwriting limit extraction. Chasing is automatable; receiving is messy. Unverified for Lorenzo.
- Demand drafts: citation to page is achievable with page-level extraction and a strict "no source, no sentence" rule, but attorneys will still edit. The gate is non-negotiable.
- Compliance: medical information means HIPAA-grade handling where it applies, vendors that will sign a BAA or equivalent, access controls and audit logs. Florida Bar guidance on generative AI use (confidentiality, supervision, billing) must be checked by the firm. Lorenzo does not give legal advice on this; the firm's attorneys sign off.
- Scope creep: the post describes a legal-tech product. Phasing and a written phase scope are the only protection.

## Standard pricing (reference, never in the proposal)
- Assessment and roadmap: $3,000 to $8,000 market.
- First phase (receptionist plus intake): $15,000 to $40,000 market.
- Full office: $60,000 to $150,000+ market for custom work of this scope; agencies specialised in legal AI quote at the top of this.
- Recurring software (their accounts): voice AI platform billed per minute plus a phone number, LLM API usage, e-signature, secure document storage, automation platform (self-hosted n8n or cloud), their case management seats. Rough band $500 to $2,500 a month depending on call minutes and document volume; confirm after the assessment.
- Retainer for support and improvements after launch: market $1,500 to $5,000 a month.
- Post: hourly, rate not given; recorded bids average $38.72 (range $7 to $300). The scope is expert-level and the average bid is far below market for it.

## Ask before quoting
1. Which case management system, document management platform and e-signature tool do you use today, and do you have API access?
2. Roughly how many calls a day, new cases a month and open cases right now?
3. What share of callers speak Spanish and Haitian Creole, and does anyone on staff speak Haitian Creole to test with?
4. How do providers send records today (fax, portal, mail, a records vendor)?
5. Do you have firm-approved templates for intake forms, engagement agreements, records requests and demand letters?
6. Which part hurts most today, so phase one starts there?
7. Who signs off on AI use and data handling on your side (managing attorney, compliance)?

## Flags
- US client (Florida), handles medical and legal confidential data. Lorenzo confirms he can meet their data handling needs; copy asserts no location.
- Question 2 asks for "demonstrations or examples" of multilingual voice receptionists, and question 1 asks for PI examples. He has neither for this niche; the chart plus an honest answer is the play, no invented demos.
- No contact-outside-Upwork restriction in the post.
- 26 connects, 0 hired so far.
