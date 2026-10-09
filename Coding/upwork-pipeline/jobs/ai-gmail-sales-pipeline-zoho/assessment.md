# Assessment (private, never shown to the client)

## Time
- Phase 1 (read, sort, next action, drafts to Gmail Drafts, Zoho sync, guardrails, approval step): 35 to 50 hours, about 2 to 3 calendar weeks at part time, including a week of shadow mode where nothing sends and every draft is compared against what the rep actually sent.
- Phase 2 (automated follow-up ladder with stop-on-reply, reminders, auto-send for approved low-risk types, weekly report): 20 to 30 hours, 1 to 2 weeks.
- Ongoing: 4 to 8 hours a month for rule tuning and new email types.

## Likelihood (what breaks)
- Gmail API access: needs a Google Workspace admin to approve an OAuth app or a service account with domain-wide delegation. Consumer Gmail works but with OAuth verification friction. Unverified which they have.
- Gmail push (watch + Pub/Sub) versus polling: push needs a GCP project; polling every 1 to 2 minutes is the fallback. Either is fine.
- Zoho CRM API: plan tier matters (API call limits per day scale with edition and licences; Zoho Standard and up have API access). Data centre region (.com / .eu / .in) changes the OAuth URLs. Unverified.
- Matching an email to the right Zoho contact and deal is the real risk: shared inboxes, personal addresses, multiple open deals per contact. Needs a rule set and a "not sure" path to a person.
- Zoho already has its own Gmail extension / email sync; if it is on, logging emails twice is a risk. Ask.
- Model: Claude (or OpenAI) for classification and drafts is reliable when outputs are structured JSON and validated. Tone matching needs 20 to 50 of their sent emails as examples.
- Guardrails: deterministic checks (recipient, thread, opt-out, stage, send window, rate limit, numbers match Zoho) are code, not prompts. The model only flags topics (pricing, legal, complaints) that route to a person.

## Standard pricing
- Post says $10 to $20 an hour; bids average $22.60. That is well under market for AI plus CRM integration work (market for this is $50 to $120 an hour, or $3,000 to $8,000 fixed for phase 1).
- Recurring software: n8n cloud about $24 to $60 a month (or self-host), LLM usage roughly $20 to $150 a month depending on email volume, Google Cloud Pub/Sub near zero, Zoho plan they already pay for.

## Pricing path (Lorenzo only)
- Value: assume 2 reps each spending 1.5 hours a day on inbox triage, follow-ups and CRM updates (assumption, not in the post). Saving half of it is about 375 hours a year per rep, 750 hours total. At an assumed $40 loaded hourly cost that is about $30,000 a year, before any revenue from fewer dropped follow-ups.
- Price range at 10 to 20% of that value: $3,000 to $6,000.
- Land offer (milestone 1): shadow-mode reader and sorter on their Gmail with Zoho matching, drafts only, nothing sends.
- Upsell path: follow-up ladder and auto-send for approved types, then weekly pipeline report, then more inboxes or channels, then a monthly retainer for new AI capabilities ("could become an ongoing project").
- Milestones:
  1. 25%: paid once the Gmail reader, lead sorting and Zoho matching are delivered in shadow mode and you've signed off.
  2. 30%: paid once reply drafting in your voice, the seven checks and the approval step are delivered and you've signed off.
  3. 30%: paid once the follow-up and reminder ladder with stop-on-reply and Zoho stage and task updates are delivered and you've signed off.
  4. 15%: paid once the run log, editable rules, handover docs and a live week of monitoring are delivered and you've signed off.

## Ask before quoting
- Google Workspace or consumer Gmail? One inbox or several reps' inboxes? Admin access for OAuth?
- Zoho CRM edition, data centre region, and whether Zoho's own Gmail sync is on.
- Rough volume: lead emails a day, open deals, reps.
- Their pipeline stages in Zoho and what should move a deal between them.
- Which emails may ever send without a person (none at first is the safe default)?
- Topics that must always go to a person (pricing, contracts, complaints, legal).
- Which workflow platform they already use, if any, and their model preference (OpenAI or Claude).

## Flags
- Rate far below market; "part time" and "possible ongoing work" suggest a trial.
- Client record not pulled; US client.
- The guardrail question is the deciding factor; lead with it.
