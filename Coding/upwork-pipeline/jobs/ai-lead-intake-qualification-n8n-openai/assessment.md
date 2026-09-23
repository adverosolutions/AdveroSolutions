# Private delivery assessment (not for the proposal)

**Price flag, read first.** $100 fixed for five parts (capture, AI qualification, routing, status tracker, reporting dashboard) plus "reliable and easy to maintain" is a token number, not a budget for this scope. The client is a brand-new buyer: 1 contract ($30, a short-form video editor for reels / TikTok ads / UGC, closed 2026-09-21), no feedback yet. Recorded bids average $261.16 on a $5 to $2,000 range, and 1 freelancer is already invited to interview. Expect a low anchor. The call has to put a real number on a first milestone before any work starts; never build the whole system for $100. Posted about 2026-09-23, 10 connects.

**Time.** 14 to 22 hours of real work, 1 to 2 calendar weeks, most of the spread coming from waiting on their access and their rules, not from building. Rough split:
- Capture: webhook, clean-up, blank filter, and wiring their actual form or ad lead source: 2 to 4 h (more if the form builder cannot send webhooks, see below).
- Qualification: prompt and schema against their written rules, then a test pass on 20 to 30 of their real past leads and one round of rule tuning with them: 4 to 6 h.
- Routing table, team emails, default inbox: 1.5 to 2 h.
- Tracker sheet (tabs, headers, Status dropdown, protected columns): 1.5 to 2 h.
- Dashboard tab, morning code, report email, optional chart on the tab: 3 to 4 h.
- Error workflow, retries, end-to-end test, short handover doc or Loom: 2 to 4 h.

**Likelihood.** Very doable; every piece is standard n8n. What overruns is on their side:
- Lead source is unknown and is the biggest swing. A website form that can post a webhook (Webflow, WordPress with a forms plugin, Typeform, Jotform, Tally) is minutes. Some site builders only send form data through Zapier or their own email notification, which adds a bridge. Meta lead ads have a native n8n trigger; TikTok lead forms usually need their CRM sync or an API app. Their only hire so far was an ad-creative editor, so paid-social lead forms are plausible, but that is an inference, never stated to them.
- Qualification rules do not exist in the post. The AI step is only as good as the rules they write. The build forces rules into Config in plain English and never lets the model invent criteria; missing fields lower the score rather than being guessed. Calibrating needs their real past leads.
- "The right team": teams, what each handles and their inboxes are unknown. The routing table in Config covers any number of teams. If routing depends on hard fields (territory, product line) a code rule may beat the model; decide after seeing their teams.
- Google Sheets as tracker is right for a new buyer with no named CRM, but it has limits: Sheets API quotas (about 300 read requests a minute per project, far above a lead form's pace), and the morning read of the whole Tracker tab gets slow in the tens of thousands of rows. If volume is high or they already have a CRM, the tracker belongs there instead.
- Honest canvas limits to state if asked: n8n expressions can only read nodes that ran in the same execution, so the morning report path (steps 10 and 13) and the error alert (step 15) cannot read the Config node. The Sheet ID and owner email are set there too; the overview sticky says so. In production this can move to n8n Variables (paid plans) or a small settings sub-workflow. The Error Trigger needs this workflow set as its own Error Workflow, and failed-execution saving must stay on (default on n8n Cloud) for the "lead waits in the run" retry to hold.
- Duplicates: the tracker appends one row per submission. Upserting on email would overwrite a status the team set by hand, so dedupe is a follow-up decision, not the default.
- Status is moved by hand in the sheet. If they want a status change to trigger something (Won notifies finance, Lost starts a nurture email), that is extra scope.
- Data: lead details go to the OpenAI API. Fine for most businesses; ask if their industry is regulated (health, finance, legal).
- Unverified for Lorenzo: none of this has been run on their account. Present the canvas as the design he would build, not a delivered system. No past-client claims.

**Standard pricing.** A competent freelancer charges $1,200 to $2,500 fixed for this five-part scope with testing and a handover; agencies $3,000 and up. A thin first milestone (capture, AI qualification, tracker row, team email; no dashboard) is $400 to $700. Hourly equivalent $60 to $110. Their $100 is roughly a tenth of the low end. Recurring software: n8n Cloud starter tier (about $20 to $25 a month) or a $5 to $20 VPS self-hosted; OpenAI usage is well under 1 cent per lead on gpt-4.1 for a prompt this size, less on the mini model (check current OpenAI pricing before quoting a figure); Google Sheets and Gmail are free or already paid through Workspace.

**Ask before quoting.**
- Where do leads come from today (website form tool, landing page builder, Meta or TikTok lead forms), and roughly how many a day?
- What makes a lead qualified for you? Any hard rules (budget, location, service, company size)?
- Which teams get leads, what does each handle, and does each work from an inbox, Slack or a CRM?
- Do you already use a CRM? If yes, the status tracker should live there.
- Is a Google Sheets dashboard plus a morning email enough, or do you want charts (Looker Studio) or a web dashboard?
- n8n Cloud or self-hosted, and do you have an OpenAI API account already?
- What industry, and is any of the lead data regulated?
- Is the $100 a first milestone or the whole budget?

**Flags.** No US-only language, no portfolio-link demand and no off-platform restriction in the post. New buyer, no feedback history. Client in Nevada (US) with the New York timezone set; the build states no location claims.
