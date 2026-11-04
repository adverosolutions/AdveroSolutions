---
name: client-fulfillment
description: "Prepare Advero onboarding, delivery, scorecards and retention work from the actual client scope and current package menu. Use for new clients, kickoff, invoices, renewals or case studies."
---

# Client fulfillment: onboarding, kits, scorecards, retention

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- Fit delivery to the package and actual signed scope. The November 4 official menu supersedes the old per-offer prices below; never change it based on a call without Lorenzo’s instruction.
- Use separate call and prep documents before the call, then the actual transcript and approved scope for proposal and onboarding. Include package-specific expected results and the software stack reference without inventing outcomes.
- Accounting and Revenue Operations retain their own seats. Treat their current handoffs as the source for billing, signature monitoring, CRM logging and unresolved items; do not mark a client won or an invoice paid from a bot summary alone.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)
- [Revenue_Operations_to_COO_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/Revenue_Operations_to_COO_20261104.md)
- [Accounting_to_COO_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/Accounting_to_COO_20261104.md)
- [client-fulfillment.md](../../grok-source/2026-11-04/first-export/advero/skills/client-fulfillment.md)
- [revenue-operations.md](../../grok-source/2026-11-04/third-export/routine_exports/revenue-operations.md)
- [accounting.md](../../grok-source/2026-11-04/third-export/routine_exports/accounting.md)


State as of 2026-09-22 to 2026-09-24: **nothing here is live.** The onboarding workflow, form, kickoff calendar, invoices and ClickUp templates are specs; the scorecard job only reads; no retention email has been sent by any system.

## Who does what (2026-09-25)
- Claude Opus 5.5 decides: which touch is due, which template, whether every number and price in it checks out.
- Grok Bot executes and reports. It sends only approved-template text, exactly as given, and never writes, edits or picks client-facing copy. Anything with numbers or money goes to Lorenzo first.
- Lorenzo sends scorecards and every numbers-bearing email himself.

## Rules for every client-facing word
- No em dashes, no exclamation marks, signed "Lorenzo". "AI" is fine (Lorenzo lifted the ban 2026-09-30); never tell or imply that a bot or AI wrote the message. No Claudeisms (see `claudeisms`).
- Numbers only from the client's scorecard. Prices only from the offer sheet. None of the three product prices (bid follow-up, cold-email infrastructure, content and lead system) is in the offer sheet yet, so none of them goes in writing.
- No Loom script names a price.
- Credentials: never a password field, never a password by email. A password-manager invite (1Password, Bitwarden or LastPass) to a vault that holds only this project, or a screen share where the client types it.

## Day 0 is the kickoff call, not the Won date
Every task due date and every retention touch counts from the kickoff call, so a client who takes six days to book loses nothing. A due date on a weekend rolls to the next business day.

## Onboarding (F1)
Trigger: the deal moves to Won in the GHL Sales pipeline. The product tag is set by hand on the call, before the stage moves: `product-reactivation`, `product-bid-follow-up`, `product-cold-email-infra` or `product-content-lead-system`. No tag means a task to Lorenzo ("Tag the product on {name} before onboarding can run"), nothing else.

On Won, in order:
1. Tags `client` and `client-{product}`.
2. Internal task: Drive folder `Clients/{client-slug}/` with `01 Raw`, `02 Review`, `03 Approved`, `kickoff-form-answers.md`, `do-not-say.md`, `voice-notes.md`. Made by hand for now (the service account has no Drive quota).
3. Kickoff email to the client (below), 07:00-19:00 CT.
4. Internal task: ClickUp project from the product's task template in Active Clients.
5. Invoice at Won: reactivation none (monthly against the scorecard); bid follow-up the setup fee due on the kickoff date, monthly from 30 days after go-live; infrastructure and content system the full amount due on the kickoff date. A task with the amount until Stripe is connected.
6. After 2 days without the form back: one nudge email, then a task for Lorenzo to chase. Never a third email.
7. After 5 days without a kickoff booked: task "{first_name} has not booked kickoff, call them".

The existing published workflow "Deal Won -> ClickUp project + client tag" stays untouched. The kickoff kit is a second workflow in Draft on the same trigger.

Kickoff call: its own 45-minute calendar, 2 a day, Mon-Fri 12:00-18:00, 24 h notice, 14-day horizon, separate from the 15-minute Discovery Call calendar. Connect Zoom first or the confirmation promises a link the booking does not create.

### Kickoff email (workflow step 4)
Subject: Welcome aboard, {company}
```
{first_name},

Good to have you. Here is everything I need from you, and it is short.

First, the form: {kickoff_form_url}

It asks which accounts I need access to, where the lists live, and what you
never want said in your name. Access to anything with a login comes through a
password manager invite, not typed into a form, and the form says how.

Second, the call: {kickoff_booking_url}

Forty five minutes, this week if you can. We walk through the form together,
I show you what the first version looks like, and you tell me what is wrong
with it. The clock on your term starts at that call, not today, so there is
no cost to taking a few days.

If the form is back before the call, the call is mostly me showing you
things. If it is not, we fill it in together.

Anything you want to ask before then, reply to this and it comes straight to
me.

Lorenzo
```
Nudge (2 days, once), subject "Two things still open, {company}": says the form is still open, repeats both links, and that access and the lists are the only parts that block the start.

Open conflict: both emails carry a booking link. Lorenzo's rule (2026-09-23, "Everywhere") allows a booking link in one email only since 2026-10-06: the `booking_link` first reply to a lead who asks for one (`cold-email-replies`). Until he says the kickoff is an exception too, neither is approved to send; hold them for him.

### Kickoff form, what it asks
1. Who to talk to: name, day-to-day email, phone, who else to copy, who has the final yes.
2. Accounts: website, email host, domain registrar, where the client list lives, the calendar address (shared with "Make changes to events"), scheduling tool.
3. Logins: a checkbox that the password-manager invite was sent, or "I need a vault set up".
4. Lists: export of past and lost customers (name, email, phone, last job date, amount), rough row count (60 is the floor for reactivation), lost proposals, who is off limits, service area, who they want more of.
5. Voice: 3-5 things they actually sent, or a two-minute recording; how they sign off.
6. Do-not-say: words to never use, promises we must not make, compliance lines that must appear. This becomes `do-not-say.md` and is pasted into every draft written for that client.
Submitting sets the tag `kickoff-form-done`.

## The kits (F2)
| Kit | Deliverable | Price | Proven on |
|---|---|---|---|
| Reactivation system | Sequences, attribution tracker, GHL snapshot description (snapshot not built) | 20-30% of first-year fees, nothing up front, $0 if nothing closes (offer sheet) | The three live reactivation campaigns |
| Bid and sales-request follow-up | n8n workflow (46 nodes, five lanes) + eight-touch templates, every SMS row off | Internal only, not in the offer sheet | A construction client build (the Upwork price is not the product price, never quote it) |
| Cold-email infrastructure | Filled runbook; setup done by hand | Internal only, not in the offer sheet | The Atlantic Labs build and Advero's own inboxes |
| Demo Library 011 (reply engine) | One-pager + Loom script | Not sold | The proof asset behind the other three |

### Reactivation build, from the kickoff call
| Day | Step |
|---|---|
| 0 | Import and clean: dedupe, drop current customers and the off-limits list. Under 60 usable rows, stop and tell the client before spending anything |
| 1 | Verify emails; the client's cost, quoted first |
| 2 | Three emails in the client's voice, their signature, nothing from do-not-say |
| 3 | Client approves the copy. Nothing sends before this |
| 4 | Build the campaign, 07:00-19:00 client time; test send to the client and Lorenzo, read on a phone |
| 5 | Go live with the first 50 only; seed the attribution tracker (first-touch date for every contact) |

Sequence timing: cleaning day 0/10/20 (renewal and budget season), bookkeeping day 0/7/16 (January, quarterly estimates, year-end), recruiting day 0/7/16 (hiring waves). These emails are the client writing to their own former customers: Advero's proof lines and guarantees never go in them. Decide on the kickoff call who answers replies in the client's inbox.

Texts in any kit ship switched off and carry "Reply STOP to opt out"; they go on the day the client's A2P 10DLC registration is confirmed. Any client build turned into a kit is scrubbed of the last client's name, owner and addresses.

## Weekly scorecard (F3)
Run Friday after 19:00 CT. "Week" is always the seven days ending yesterday. Two documents per client: the client card (table, invoice basis, next week's plan, caveats) and Lorenzo's operator notes (retention schedule, blockers, billing checks). Only the client card is ever sent, and Lorenzo sends it himself.

Columns: sent; replies from a person; automatic replies on their own row (never subtracted); interested, booked, held, closed (interest status 1-4 only, one record per email across campaigns); revenue attributed from GHL Won (absent until a GHL token exists, and the card says so).

It never:
- prints a zero it did not measure ("no source" instead);
- invoices an estimate: a close counts only with a first-touch date, a close date inside the week and a contract value a person wrote down;
- dates a close by the contact's last reply;
- defaults the attribution window (180 days for reactivation);
- judges a reply rate under 300 sends;
- gives a client somebody else's numbers;
- sends anything.

Invoicing is tracked by hand. There is no billing ledger, so the same close can land on two cards or none. Before billing, check every close on the invoice line, and every "earlier period" or "after this week's end" close in the operator notes, against Lorenzo's own records. A performance client's monthly invoice is that month's weekly invoice lines added by hand.

## Retention (F4)
| Day | Touch | Auto-send after approval? |
|---|---|---|
| 7 | Check-in and the fix window | Yes, it carries no numbers |
| 21 | Results snapshot + case-study draft | No: term-to-date numbers |
| 25 | Renewal or maintenance offer | No: numbers and a confirmed price |
| 30 | Referral ask + review request | No: cites one result |

A draft is ready only when every required number exists, the copy passes the rules and any money in it is in the offer sheet. Blocked drafts are still written with the gaps listed. A touch drops off when marked handled or 14 days past due.

**Day 7**, subject "One week in, {company}":
```
{first_name},

One week in. Two questions and one offer.

Is anything landing in front of you that should not be, and is anything
reaching you late.

The offer is the fix window. Anything you want changed in the copy, the
timing, or who it goes to, tell me this week and it is done inside five
business days at no cost. After that it is still done, it just joins the
queue.

If nothing needs changing, reply "all good" and I will leave you alone until
the numbers are worth reading.

Lorenzo
```
**Day 21**, "Three weeks of numbers, {company}": the term-to-date funnel through {metrics_through} ({days_measured} days), a headline, what to change next, and a case-study draft the client approves or asks to anonymise.
**Day 25**, "Where we go from here, {company}": three options: stop here (everything built is theirs, with a write-up so nothing depends on Lorenzo), keep it running ({renewal_terms}), or widen it ({expansion_line}).
**Day 30**, "Thanks, and one ask": one referral name and a review line at {review_link}.

## Case studies
Drafted on day 21 from the scorecard's term numbers: company and product, where they started, what was built, what happened in the first {days_measured} days, a quote in their words. The client approves it before use and can ask for it to run without their name. No number goes in that the scorecard did not measure.

## Current clients
- Man Transformed (Mike): signed 2026-09-17, 30-day content and lead system, flat. Day 0 taken as the signing date because the kickoff date is not recorded; term ends 2026-10-17, day 25 due 2026-10-12. His day-25 draft is blocked: no data source for his numbers, renewal terms unwritten, and his price is not in the offer sheet.
- Jennifer L. (Upwork, contract ended 2026-09-14): the review and testimonial ask was never sent. It goes through Upwork, by hand, by Lorenzo.

## Sources (for maintainers)
- `Agentic Worklfows/runbooks/fulfillment.md` (2026-09-22, origin/main ba39a0c): F1-F4, scorecard rules, retention, current clients.
- `Agentic Worklfows/changesets/onboarding/onboarding_spec.md`, `kickoff_email.md`, `kickoff_nudge_email.md`, `kickoff_form.md`, `clickup_templates.md`, `clients.seed.json` (2026-09-22).
- `Agentic Worklfows/changesets/onboarding/retention/README.md` and `day07_checkin.md`, `day21_results.md`, `day25_renewal.md`, `day30_referral_review.md`.
- `Agentic Worklfows/products/README.md`, `reactivation_system/SOP.md`, `reactivation_system/campaign_templates.md`, `bid_follow_up_system/SOP.md`, `cold_email_infrastructure/SOP.md`.
- `.claude/agents/fulfillment.md` (agent rules; model line predates the 2026-09-25 move to Opus 5.5).
- `Agentic Worklfows/config/offers.md` (pricing; 2026-09-24 no numbers over email).
- `Agentic Worklfows/sections/2_booked_calls/STATUS.md` (never a booking link, "Everywhere", 2026-09-23).
- `~/.claude/skills/grok-operator/SKILL.md` (operating model, 2026-09-25).
