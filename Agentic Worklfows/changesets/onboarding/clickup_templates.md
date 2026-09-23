# ClickUp task templates, one per product

Workspace `90141659171`, space `90148701454`, list **Active Clients** `901421193684`. Nothing here is created: no ClickUp API token exists in any `.env`, and the ClickUp MCP inside a Claude session is a live write, which the controlled-environment rule forbids tonight.

Build them as ClickUp **task templates** (save a task as a template, subtasks included), not as a list template, so one template applied to a new client task produces the whole checklist under one parent.

Conventions for every template:

- Parent task name `{{Client}} - {{Product}}`, status `to do`, assignee Lorenzo, tag `client-{{slug}}`.
- Due dates are **relative to the kickoff call**, which is day 0. Not the Won date. A client who takes six days to book must not lose six days of the term.
- Every template ends with the three F4 retention tasks, so retention is never a thing someone remembers to do.
- Custom fields on the parent: `Product` (dropdown), `Deal type` (performance / setup plus monthly / flat), `Term end` (date), `Scorecard slug` (text, must match the slug in the client roster the F3 job reads).

## Reactivation build

| # | Task | Due | Notes |
| --- | --- | --- | --- |
| 1 | Import and clean the list | day 0 | Dedupe, drop current customers and the off-limits list, verify. Below 60 usable rows, stop and tell the client before spending anything |
| 2 | Verify emails | day 1 | Cost is the client's, quoted before the run |
| 3 | Write the sequence from the voice file | day 2 | Three emails, their name, their signature |
| 4 | Client approves the copy | day 3 | Nothing sends before this |
| 5 | Build the campaign and the schedule | day 4 | Their sending domain or ours, decided on the kickoff call |
| 6 | Test send to the client and to Lorenzo | day 4 | |
| 7 | Go live, first 50 | day 5 | |
| 8 | Attribution tracker seeded | day 5 | Every contact's first-touch date written down. Without it there is no invoice |
| 9 | Day 7 check-in | day 7 | F4 |
| 10 | Day 21 results snapshot and case-study draft | day 21 | F4 |
| 11 | Day 25 renewal conversation | day 25 | F4 |
| 12 | Day 30 referral and review ask | day 30 | F4 |

## Follow-up engine build

| # | Task | Due | Notes |
| --- | --- | --- | --- |
| 1 | Map their current bid or request flow | day 0 | Where requests land, who answers, what they say today |
| 2 | Build the tracker sheet from the template | day 1 | Bids tab and Templates tab, the sheet is the source of truth |
| 3 | Load their copy into the Templates tab | day 2 | Eight touches, their words |
| 4 | Import the workflow JSON and set the Config node | day 2 | Sheet id, business name, owner name, owner phone |
| 5 | Connect Google, email and SMS credentials | day 3 | SMS stays off until their 10DLC is registered |
| 6 | Test with three fake bids through every lane | day 3 | |
| 7 | Client watches one run end to end | day 4 | |
| 8 | Go live and hand over the sheet | day 5 | |
| 9 | Day 7 check-in | day 7 | F4 |
| 10 | Day 21 results snapshot and case-study draft | day 21 | F4 |
| 11 | Day 25 maintenance offer | day 25 | F4 |
| 12 | Day 30 referral and review ask | day 30 | F4 |

## Infrastructure build

| # | Task | Due | Notes |
| --- | --- | --- | --- |
| 1 | Pick and buy the domains | day 0 | Client's card, never ours. Count from their target daily volume |
| 2 | DNS: SPF, DKIM, DMARC, MX per domain | day 1 | |
| 3 | Create the inboxes, three personas per domain | day 1 | |
| 4 | Connect them to the sending platform | day 2 | |
| 5 | Start warm-up, record the go-live date | day 2 | Warm-up is three weeks. Say it on the kickoff call, not on day 20 |
| 6 | Tracking domain and unsubscribe handling | day 3 | |
| 7 | Write the runbook for their setup | day 4 | Their domains, their records, their dates |
| 8 | Handover call, walk the runbook | day 5 | |
| 9 | Day 7 check-in, warm-up health | day 7 | F4 |
| 10 | Day 21 placement test and results snapshot | day 21 | F4 |
| 11 | Day 25 ongoing-management offer | day 25 | F4 |
| 12 | Day 30 referral and review ask | day 30 | F4 |

## Content and lead system build

The one Mike at Man Transformed bought. It is not a kit yet: productize it after his day-21 results snapshot, when there is a number to sell it with.

| # | Task | Due | Notes |
| --- | --- | --- | --- |
| 1 | Voice file read and do-not-say list loaded | day 0 | |
| 2 | Content calendar for the term | day 1 | |
| 3 | First week's posts drafted and approved | day 2 | |
| 4 | Lead capture and routing live | day 3 | |
| 5 | Posting live | day 4 | |
| 6 | Weekly scorecard slug registered in the client roster | day 4 | Otherwise F3 cannot report on him |
| 7 | Day 7 check-in | day 7 | F4 |
| 8 | Day 21 results snapshot and case-study draft | day 21 | F4 |
| 9 | Day 25 renewal offer | day 25 | **Mike signed 2026-09-17, so this is due by 2026-10-12** |
| 10 | Day 30 referral and review ask | day 30 | F4 |
