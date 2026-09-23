# F1 onboarding build spec: Deal Won fires the kickoff kit

Brief A12, Blueprint F1. Status: **NOTHING BUILT**. This is a specification and a plan-only change-set. `apply.py` reads `manifest.json`, diffs what it can read against live, records every intended object as a `would_do` through `shared.settings.guard_write`, and refuses `--apply`.

Why it refuses, per target:

| Target | System | Why it cannot be applied tonight |
| --- | --- | --- |
| Kickoff workflow | GHL | No public create API for workflows. Built by hand in the UI. |
| Drive client folder | Google Drive | The service account has **zero Drive storage quota**, so it cannot create a folder anywhere. |
| Kickoff form | GHL | No public create API for forms. |
| Kickoff calendar | GHL | No public create API for calendars. |
| First-installment invoice | Stripe | No `STRIPE_SECRET_KEY` in any `.env`. |
| ClickUp task template | ClickUp | No ClickUp API token in any `.env`. |

Read `runbooks/fulfillment.md` before building any of it. The controlled-environment rule stands: build in Draft, test against Lorenzo's own contact record, publish only after the runbook checklist is signed off.

## What exists today

`config/ids.json` records one published workflow, `Deal Won -> ClickUp project + client tag`, id `e0593495-a88e-46f0-a9ac-611fabf7f0f9`. It is live and it works. **Do not edit it.** The extension is a second workflow in Draft on the same trigger, so a half-finished kickoff kit can never break the tag and the ClickUp project that already fire. Merging the two is a separate, deliberate step once the new one has run clean for two clients.

Ids used below, all from `config/ids.json`:

- Location `ebyNANPagaK7ycf1pfge`, user (Lorenzo) `gIwBtPohHJXADQBuGAx8`
- Sales pipeline `GCBkIzFpung73cIDVPzn`, Won stage `48eca719-502a-46cc-9e39-7db0aeffb41e`
- Discovery Call calendar `GDugwLmZNdsD13RBDnRu` (**not** the kickoff calendar, see section 4)
- ClickUp workspace `90141659171`, space `90148701454`, Active Clients list `901421193684`

## 1. The workflow

**Name:** `Client Onboarding: kickoff kit`  **Status:** Draft

| Setting | Value | Why |
| --- | --- | --- |
| Allow re-entry | OFF | A deal that moves Won, Lost, Won again must not raise a second invoice or a second folder. |
| Stop on response | OFF | Nothing here is a sales sequence. |
| Time window | 07:00 to 19:00 America/Chicago on the client-facing email steps only | Same send window the engine obeys. Internal tasks fire at any hour. |
| Timezone | Contact's timezone, fallback account (America/Chicago) | |

| # | Step | Type | Config | Notes |
| --- | --- | --- | --- | --- |
| 0 | Trigger | Opportunity Status Changed | Pipeline `GCBkIzFpung73cIDVPzn`, stage becomes Won `48eca719-502a-46cc-9e39-7db0aeffb41e` | Same trigger as the published workflow |
| 1 | If/Else: which product | Condition on contact tag | `product-reactivation`, `product-bid-follow-up`, `product-cold-email-infra`, `product-content-lead-system` | The tag is set on the call, by hand, before the stage moves. A deal with no product tag falls to step 1z |
| 1z | No product tag | Add Task + Internal Notification | Title `Tag the product on {{contact.name}} before onboarding can run`, assigned `gIwBtPohHJXADQBuGAx8` | Fail loud. An untagged deal gets the wrong task template and the wrong invoice |
| 2 | Add tag `client` and `client-{{product}}` | Add Contact Tag | | The published workflow already adds its own client tag; this adds the product tag it does not |
| 3 | Internal task: make the Drive folder | Add Task | Title `Drive folder for {{contact.company_name}} (Raw / Review / Approved)`, body = the template in section 2, due today | Stays a task until the Drive credential in section 2 is solved |
| 4 | Send the kickoff email | Send Email | From `lorenzovillarreal@adverosolutions.com`, plain text, body = `kickoff_email.md` | Carries the form link and the kickoff booking link, nothing else |
| 5 | Internal task: ClickUp project from the product template | Add Task | Title `ClickUp: create {{product}} project for {{contact.company_name}} in Active Clients`, body = the template in `clickup_templates.md` | The published workflow creates a generic project; this names which template |
| 6 | If/Else: invoice at Won | Condition on tag `product-reactivation` | Yes branch (reactivation): no invoice | Performance deals invoice monthly against the F3 scorecard. A zero-dollar invoice at Won is the failure this branch exists to prevent |
| 6a | No branch | Add Task | Title `Stripe: first installment for {{contact.company_name}}, due on the kickoff date`, body carries the amount from the product row in `manifest.json` | Becomes a Stripe API step once a key exists |
| 7 | Wait 2 days | Wait, time delay | 2 days | |
| 8 | If/Else: form returned | Condition: contact has tag `kickoff-form-done` | | The form sets the tag on submit |
| 8a | No branch | Send Email | body = `kickoff_nudge_email.md` | One nudge, then a task for Lorenzo. Never a third email |
| 8b | No branch, second leg | Add Task | `Chase the kickoff form from {{contact.first_name}}` due tomorrow | |
| 9 | Wait until the kickoff call is booked | Wait, appointment booked on the Kickoff Call calendar, max 5 days | | |
| 9a | Timed out | Add Task | `{{contact.first_name}} has not booked kickoff, call them` | |
| 10 | End | | | |

**Day 0 of the term is the kickoff call, not the Won date.** The F4 retention clock in `jobs/client_scorecard.py` reads `start_date` from the client roster, and the roster is filled from the kickoff call, so a client who takes six days to book does not burn six days of a 30-day term. Mike's roster row is the worked example.

## 2. Drive client folder

Template, created under a `Clients/` parent that Lorenzo owns:

```
Clients/{client_slug}/
  01 Raw/           work in progress, nothing here is client-ready
  02 Review/        waiting on the client
  03 Approved/      signed off, safe to publish or send
  kickoff-form-answers.md
  do-not-say.md
  voice-notes.md
```

`{client_slug}` is lowercase, hyphenated, from the company name: `Man Transformed` becomes `man-transformed`.

**The blocker, stated plainly.** `credentials.json` is a service account with zero Drive storage quota. It cannot create a folder or a file anywhere it is not already a member, which is why the daily metrics tracker had to be built into an existing sheet. Two ways out, both Lorenzo's call:

1. He creates `Clients/` and shares it with the service account as Content Manager. A service account can then create children inside a folder owned by a real user, because the storage is charged to the owner. This needs testing before it is trusted.
2. The job runs under OAuth as `adveroadvertising@gmail.com` with a `token.json`, the same way the existing Sheets tooling does.

Until one of those is done, step 3 of the workflow is an internal task and the folder is made by hand. That is a two-minute job per client and it is not the bottleneck.

## 3. Kickoff form

Fields, copy and the GHL build are in `kickoff_form.md`. Summary of what it asks for:

accounts and access, logins **through a password manager invite only**, the lists, a voice file, calendar access, and the do-not-say list.

**Logins.** The form never has a password field. It asks for a 1Password (or Bitwarden, or LastPass) guest invite to a single shared vault. A form field that collects a password puts the client's credentials in GHL's database and in every workflow log that touches the submission, and Lorenzo has no way to rotate them. If a client insists on sending a password another way, the answer is the password manager or a screen share where they type it themselves.

## 4. Kickoff call calendar

A **separate** calendar named `Kickoff Call`, not the Discovery Call calendar `GDugwLmZNdsD13RBDnRu`.

| Setting | Discovery Call (live) | Kickoff Call (to build) |
| --- | --- | --- |
| Slot | 15 min | 45 min |
| Per day | 6 | 2 |
| Buffer | 15 min | 15 min |
| Open hours | Mon-Fri 12:00-18:00 | Mon-Fri 12:00-18:00 |
| Minimum notice | 4 h | 24 h |
| Booking horizon | 30 days | 14 days |
| Auto confirm | yes | yes |

Why separate: discovery sells and kickoff delivers, and they compete for the same afternoons. One calendar means a 45-minute kickoff eats three discovery slots on the day a campaign is landing replies. Two calendars also give F5 capacity protection something to measure: sales hours against fulfillment hours, per week, without reading a transcript.

**Conferencing.** Zoom is not connected to GHL (`isZoomAdded=false` as of 2026-09-21), so a widget booking produces a Google Meet link. Lorenzo's real calls are hand-made Zoom events on his own Google Calendar. Connect Zoom under Profile > Calendar Settings > Video Conferencing before publishing, or the kickoff email promises a Zoom link the booking does not create.

## 5. Stripe first-installment invoice

| Product | Deal type | Invoice at Won |
| --- | --- | --- |
| Reactivation system | performance | **No.** Monthly against the F3 scorecard |
| Bid and sales-request follow-up | setup plus monthly | Setup fee, due on the kickoff date; the monthly starts 30 days after go-live |
| Cold-email infrastructure | flat | Full amount, due on the kickoff date |
| Content and lead system | flat | Full amount, due on the kickoff date |

Amounts live in the product rows of `manifest.json` and in each kit's SOP. They are **internal**: `config/offers.md` is the only source for a number Lorenzo puts in front of a prospect, and it does not yet carry these three. See the cross-cutting request in the report.

No `STRIPE_SECRET_KEY` exists, so this is a task with the amount and the due date on it. When a key exists, the step becomes `POST /v1/invoiceitems` then `POST /v1/invoices` with `collection_method=send_invoice` and `days_until_due` set from the kickoff date, and it goes through `guard_write('stripe', 'create_invoice', ...)` like every other write.

## 6. ClickUp task template per product

Full task lists per product in `clickup_templates.md`. They are created in Active Clients `901421193684` under space `90148701454`.

The template names, which the workflow's step 5 task body references:

| Product tag | Template |
| --- | --- |
| `product-reactivation` | Reactivation build |
| `product-bid-follow-up` | Follow-up engine build |
| `product-cold-email-infra` | Infrastructure build |
| `product-content-lead-system` | Content and lead system build |

## What a run looks like when it works

Deal moves to Won at 15:40 on a Tuesday. Inside a minute: the product tag is set, three internal tasks appear on Lorenzo's list (folder, ClickUp project, invoice), and the client has one email with a form link and a kickoff booking link. Two days later, if the form is not back, one nudge and one task. Five days later, if no kickoff is booked, a task to call them. The client sees two emails. Lorenzo sees a checklist.

## Verify before publishing

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 changesets/onboarding/apply.py --dry-run --json
```

It prints the plan, what it could read from live, and the reason each target is not applicable. It exits 2 on `--apply`.
