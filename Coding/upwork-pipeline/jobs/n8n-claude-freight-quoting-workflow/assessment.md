# Private delivery assessment (not for the proposal)

**Time.** 45 to 65 hours, 3 to 4 calendar weeks. The n8n build itself is maybe 20 hours because the spec is already written. The rest is Graph API auth, agent reply parsing against real messy emails, and the negotiation/follow-up state machine not double firing.

**Likelihood.** The build is very doable. What overruns lives in the client's accounts:

- Microsoft Graph app registration. Reading and sending from a shared mailbox needs an Azure AD app with Mail.Read / Mail.Send and tenant admin consent. If their IT is slow or the mailbox is a personal Outlook.com account rather than Microsoft 365, this alone can eat a week. Highest schedule risk.
- Wafeq API access. Wafeq is not a first party n8n node, so it is an HTTP call, and I have not confirmed which plan exposes an API key or whether invoice creation needs a pre-existing contact record. Unverified until they hand over docs or a sandbox key.
- Agent rate replies. If agents reply with rates in the email body, extraction is reliable. If they reply with PDF or Excel attachments, or scanned scans, reliability drops hard and that is a separate parsing sub-project. Ask early.
- 24 hour wait nodes. Fine on n8n Cloud. Self hosted needs the execution to survive a restart, so queue mode and DB persistence must be configured or the whole quote is lost mid flight.
- Dangerous goods classification. Claude should propose the UN number and class, never assert it unreviewed. There is real liability there. Keep the human checkpoint on it.
- Idempotency. Duplicate agent replies, a client replying twice, a retried run. Every stage needs to key off the quote reference or the same quote goes out twice.
- The stack has no Slack in it. The human approval checkpoint is built on Slack because that is the cleanest approve/reject surface, but if the ops team lives in Teams or Outlook it swaps to a Teams message or an actionable Outlook email. Cosmetic change, worth saying on camera.

**Standard pricing.** $5,000 to $9,000 for this scope from a competent freelancer against a written spec, $12,000+ from an agency. $1,000 fixed is well under market, roughly a fifth. It reads as a paid trial for the contract-to-hire, which is the only frame in which it makes sense to take. If he takes it, scope it explicitly as phase one (intake, extraction, logging, rate requests out) and let phases two and three be separate contracts, otherwise it is 60 hours at $17/hr.

**Recurring costs to flag.** Claude API a few dollars a day at normal inquiry volume. n8n Cloud starter tier or a self hosted VPS. Wafeq and Microsoft 365 they already pay for.

**Ask before quoting.**
- Is the quoting mailbox on Microsoft 365 with an admin who can grant app consent, or is it a personal Outlook account?
- Which Wafeq plan, and can they get an API key plus sandbox before kickoff?
- n8n Cloud or self hosted, and who owns and pays for the instance?
- How many agents per lane, how many lanes, how many inquiries a day?
- Do agents send rates in the email body or as attachments?
- Where does the approval checkpoint live: Slack, Teams, or an email the ops person clicks?
- Is the $1,000 the whole build or phase one of the contract-to-hire?
