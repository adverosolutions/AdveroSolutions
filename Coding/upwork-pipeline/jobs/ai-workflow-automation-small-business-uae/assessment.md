# Assessment (private) - AI workflow automation for a small business

## Time
- The canvas as shown (inbox sort, lead follow-up, support drafts, daily report, error alert): 8 to 12 hours including prompt tuning on 30 to 50 of their real emails and a week of watching the log. 1 to 1.5 calendar weeks at part time.
- Discovery (their part 1, "analyze our existing business processes"): 2 to 4 hours of calls and notes before building anything else.
- Every further workflow from their list (content generation, internal operations, a CRM hook): 4 to 15 hours each depending on the tools. As a long-term part-time engagement this is realistically 10 to 20 hours a week for the first month.

## Likelihood
- High for the build itself: n8n IMAP/Gmail, Google Sheets and the Anthropic or OpenAI node are routine.
- What breaks: auto-sending the lead follow-up before prompts are tuned on their real mail (a wrong price or promise goes to a buyer). Mitigation: run lead replies as drafts for the first week, then switch to send. Mixed Arabic/English mail is handled by "reply in the sender's language" but is unverified on their data.
- Unknowns for Lorenzo: their inbox provider (Google Workspace vs Outlook/Microsoft 365 changes the send nodes), whether they already have a CRM, whether they self-host n8n or need n8n Cloud.
- Unverified: gmail draft node's sendTo option and the error trigger's execution.url field compile as written; check on first import.

## Standard pricing
- Market for this kind of first workflow: $800 to $2,000 fixed, or $35 to $75 an hour for an intermediate n8n/AI automation specialist.
- Their posted rate, $15 to $20 hourly, is well below market; recorded bids average $21.59. The long-term, part-time angle is the draw.
- Recurring software: n8n Cloud Starter about $24 a month (or self-host on a $5 to $10 VPS), Claude or OpenAI usage roughly $5 to $30 a month at small-business email volume, Google Workspace they likely already pay for.

## Ask before quoting
- Which inbox do leads and customers write to (Gmail/Google Workspace, Outlook, a website form)?
- Roughly how many emails a day, and what share are leads vs support?
- Do you use a CRM today, or is a sheet fine to start?
- Which replies may send on their own, and which must a person check?
- n8n Cloud or self-hosted, or open to Make/Zapier?
- What are the 2 or 3 repetitive tasks eating the most time right now?

## Flags
- The proposal must START with the word "AUTOMATE" (main session).
- They ask for 2 or 3 examples of AI automation projects (problem, tools, what was automated): use only the four case-study bullets and Lorenzo's own outbound system; no invented projects.
- No US-only, portfolio-link or off-platform restriction in the post.
