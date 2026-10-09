# Assessment (private, never in the proposal)

## Time
- Clio developer app and OAuth2 credential, Lawmatics API access, n8n hosting decision: 5-6 h
- 1 New client intake (Lawmatics -> Clio contact + matter -> Sheet -> engagement letter PDF -> welcome email): 8-10 h
- 2 Document drafting: converting their Word templates to tagged Google Docs (depends on template count and how many conditional clauses they carry) 6-12 h; drafting prompt tuned on 5-10 real questionnaires 8-10 h
- 3 Follow-ups (Clio stages, reminder copy approved by the attorney, cadence): 5-6 h
- 4 Email routing (Gmail trigger, routing rules tuned on a week of real mail): 6-8 h
- Error alert, documentation, team walkthrough (they asked: "build it, document it, and show my team"): 5-6 h
- Review rounds with the attorney and paralegal: 6-8 h
- Total: about 50-65 hours. Calendar: 4-6 weeks part time; attorney sign-off on templates and client-facing copy is the pacing item.

## Likelihood
Good overall; all four pieces use tools they already have. Unverified for Lorenzo, and weighted by how much they could move the build:
- Lawmatics and Clio may already sync. Lawmatics has a native Clio integration; if it is on, steps 3-4 must look up the existing Clio contact/matter instead of creating one, or they get duplicates. Ask first.
- Lawmatics trigger: that a Lawmatics automation can POST a webhook to n8n on form submit is not verified here, nor the exact `/v1/prospects/{id}` response shape or whether API access needs their plan tier or a request to Lawmatics. Fallback is polling the Lawmatics API on a schedule.
- Lawmatics and Clio both have document automation of their own (Lawmatics documents, Clio Draft). If they own either, the drafting section may be better built on that; the Claude fill-in step stays the same. Ask which they pay for.
- Template reality: Google Docs `replaceAllText` fills blanks only. Conditional clauses (married vs single, trust vs no trust, minors) need template variants per case or a smarter fill step. Their templates decide the hours.
- Clio API: OAuth2 tokens expire, so production uses an n8n OAuth2 credential rather than the static Bearer header shown on canvas. `matter_stage` exists only if they use Clio Matter Stages; otherwise the three follow-up reasons come from custom fields or tags. "Quiet" is read from the matter's `updated_at`, a rough signal; unpaid retainers may be better read from Clio bills/trust requests. Confirm on the call.
- Claude Pro is the chat subscription; automations need an Anthropic API key billed per use. Say so plainly (it is on the sticky).
- Confidentiality: data passes through n8n and the Anthropic API. Say only what is true: records stay in their Google Workspace, Clio and Lawmatics; n8n can be set not to save execution data and can be self-hosted; Claude is reached through the firm's own API key. Lorenzo should read Anthropic's current commercial data terms before stating anything about retention or training, and be aware the Florida Bar has issued ethics guidance on lawyers using generative AI (confidentiality, supervision). Do not quote either from memory in the proposal.
- Nodes 6 and 9 are Code nodes calling the Google Drive and Docs APIs with `httpRequestWithAuthentication`. That reads well on the canvas, but production swaps them for HTTP Request nodes using a Google credential (copy, batchUpdate, export), because credential access from Code nodes is not reliable across n8n versions and hosting.
- Email routing sends a copy of the attorney's mail to the paralegal's inbox; some firms prefer a Gmail label or delegated access instead. A call decision.

## Standard pricing
- Market for this scope (four automations, law-firm data, documentation and training): $7,000-$12,000 at $110-150/h expert rates, or $5,000-$8,000 from a mid-market n8n freelancer.
- Recurring software: n8n Cloud about $24-60/mo or self-hosted about $10-20/mo; Anthropic API likely $10-40/mo at a 4-person firm's volume (assumption); Clio, Lawmatics and Google Workspace they already pay for.
- Post rate $50-$150/h hourly, part time, recorded average bid $81.98: squarely in market. The paid 1-hour scoping call is their stated first step.

## Ask before quoting
1. Is the Lawmatics-to-Clio sync already turned on? Do you own Clio Draft or Lawmatics document automation?
2. How many templates (will, trust, POA, health care surrogate, others), and how many variants per client type?
3. Is the intake questionnaire the same Lawmatics form as the first lead form, or a second form after the consult?
4. Should drafts start at intake or only after the engagement letter is signed and the retainer paid?
5. Do you use Clio Matter Stages? What are the stage names for signing, documents and retainer?
6. How many days quiet before a client should hear from you, and who signs the reminders?
7. New clients per month, open matters, and roughly how many emails a day hit your inbox?
8. n8n Cloud or self-hosted on the firm's own account? Any IT or cyber-insurance rules about client data in third-party tools?

## Flags
- US-only applicants required: Lorenzo confirms eligibility; copy asserts no location.
- Screening question asks for "one specific example of an automation you built for a law firm, medical practice, or similar office - what it did and what happened after." Allowed fact: Lorenzo has worked with dental practices. No specific automation or outcome detail is on file: the main session must not invent one; ask Lorenzo for the real example.
- They also ask how confidential client information is handled: answer only with what is true (see Likelihood).
- Paid scoping call first; build phase after. Client history: 81 contracts, 61% hire rate, $147.6k spent, 4.99 feedback (history is for a different kind of business).
- They reject AI tool lists; the proposal should show a build, not recommend software.

## Pricing path (Lorenzo only, never in the proposal or chats)
- Value per year (all assumptions, none in the post): paralegal saves 8 h/week of typing and retyping at $35/h loaded = $14,560; intake coordinator saves 3 h/week at $25/h = $3,900; attorney wins back 4 h/week of inbox at a $350/h billable value = $72,800. About $91,000 a year, before any retainer or matter saved by the follow-ups.
- Price range (10-20%): $9,000-$18,000.
- Land offer (milestone 1): the new client intake automation, live on their Lawmatics, Clio and Sheet, after the paid 1-hour scoping call.
- Upsell path: drafting, then follow-ups and email routing, then an ongoing monthly retainer for new automations (they said "I'd expect to keep working with you as we add things").
- Milestones:
  1. 25% - paid once the new client intake (Lawmatics to Clio contact and matter, Google Sheet, welcome email and engagement letter) is delivered and you've signed off.
  2. 35% - paid once first drafts of your will, trust, POA and health care surrogate templates from the intake questionnaire, with the Clio review task for your paralegal, are delivered and you've signed off.
  3. 25% - paid once the quiet-client reminders (signing appointments, missing documents, unpaid retainers) and email routing to your paralegal are delivered and you've signed off.
  4. 15% - paid once the written runbook, the failure alerts and the team walkthrough so your paralegal runs it without you are delivered and you've signed off.
