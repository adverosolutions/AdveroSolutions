# 09 Company and process map

One page. It says who owns each step and where the step is covered. Files 00 to 07 win if anything here seems to differ. Offers, niches and pricing rules: file 01 (prices are said on calls, never in email).

```
Leads (Apify, MillionVerifier) -> Instantly cold email, 6 campaigns
  -> lead replies -------------------> not a fit, unsubscribe, hostile: stop
  -> first reply by Lorenzo, 2 times -> quiet: E1 to E10 -> no answer: 90-day nurture
  -> call booked -> confirmation, reminders R2 R3 R4 -> missed: no-show ladder -> nurture
  -> 15-minute call, one-call close ---> lost or not now: Follow Up Later, nurture
  -> won -> onboarding -> delivery -> weekly scorecard -> day 7/21/25/30 -> referral, case study

Upwork: saved job -> prop + Loom -> proposal -> client opens chat -> drafts T1 to T7 -> call -> won
```

## 1. The steps

| # | Step | Owner | Covered in |
|---|---|---|---|
| 1 | Lead sourcing and verification | Lorenzo (spend, uploads); Opus judges fit; Claude Code keeps the scripts | Not your job |
| 2 | Campaign sending | Lorenzo owns copy and every change; Instantly sends; Grok reads | File 01, section 4; skill `cold-campaigns` |
| 3 | Reply handling | Grok gathers and acts; Opus decides; Lorenzo sends first replies | File 02; skill `cold-email-replies` |
| 4 | Follow-up E1 to E10 | Grok sends; Opus decides | Skill `quiet-lead-followup` |
| 5 | Booking | Opus picks two times; Grok creates the appointment (Ask first); Lorenzo sends the invite | File 05, section 3; skill `cold-email-replies`, step 5 |
| 6 | Confirmation, reminders, no-shows | Grok sends; Opus decides; Lorenzo marks a no-show | Skill `booked-calls` |
| 7 | The call | Lorenzo; Opus builds the brief; Grok delivers it | Skill `sales-call` |
| 8 | Won: onboarding and delivery | Lorenzo (nothing automated this month) | Skill `client-fulfillment` |
| 9 | Weekly client scorecard | Lorenzo sends it | Skill `client-fulfillment` |
| 10 | Retention and referrals, day 7/21/25/30 | Lorenzo | Skill `client-fulfillment` |
| 11 | Case study | Opus drafts on day 21; the client approves; Lorenzo | Skill `client-fulfillment` |
| 12 | Lost or not now: 90-day nurture | Grok records it in GHL; nothing sends yet | File 05; skill `nurture-90-day` |

Routines: file 00, section 10. Reports, KPIs and targets: file 07 and skill `daily-reports-and-metrics`. North star: discovery calls held per week.

## 2. The Upwork flow

1. Lorenzo saves the jobs he wants, in batches. (Lorenzo)
2. Claude Code builds the prop (n8n, Make, GoHighLevel or a flowchart) and the proposal draft. (Claude Code)
3. Lorenzo records the Loom and sends the proposal. Never touched by you. (Lorenzo)
4. The client opens a chat. Your Upwork drafting assistant gets drafts from Opus; Lorenzo sends each one. (Grok, Opus, Lorenzo; skill `upwork-followups`)
5. Call and win: Lorenzo. Delivery follows step 8. He asks for the review and testimonial himself.

## 3. The tools

| Tool | What it is for |
|---|---|
| Instantly | Cold campaigns, lead threads, replies, interest status, inbox health |
| GoHighLevel | The record of every lead (Sales pipeline), the Discovery Call calendar, the Deal Won workflow |
| Google Docs, Sheets, Drive | The copy doc; the Daily Metrics sheet, lead sheet, Offer Intel and LinkedIn queue; client folders |
| Gmail, Google Calendar | Lorenzo's inbox and calendar |
| Google Meet, Zoom | Call links. Meet is the default; Zoom is not connected to GHL |
| Upwork, Loom | Freelance jobs, proposals, client chats; the proposal videos |
| n8n, Make | Upwork props and client builds |
| Apify, MillionVerifier | Finding leads and verifying their emails |
| ClickUp | Client projects, created by the Deal Won workflow |
| Modal | Cloud host for the engine (never deployed) and one old sync job. Never touch |
| Claude Code | Builds and maintains the back office: the repo, this pack, the skills, the copy doc builds, scripts |
| Grok Bot (you) | The daily operator and Lorenzo's one contact |
| Claude Opus 5.5 | Every judgement call through `ask_opus.py`; drafts and LinkedIn posts |

## 4. Open items (all Lorenzo's call)

1. Access items: file 06, section 8.
2. The trigger offers' retainer figure is TO CONFIRM (file 01, section 3).
3. Deposit rule, where the signed agreement lives, the payment link (skill `sales-call`, "Open with Lorenzo").
4. Lender and consultancy proof wording (file 01, section 6).
5. Nurture: how often, what each touch offers, what happens at day 90, engine or Instantly (skill `nurture-90-day`).
6. The kickoff emails carry a booking link, against the no-booking-link rule (skill `client-fulfillment`).
7. The current content client's day-25 renewal draft is blocked (skill `client-fulfillment`).
8. How many of the 33 warmed inboxes join the campaigns after 2026-10-11 (skill `cold-campaigns`).
9. Whether the 09:30 CT heads-up before E1 stays (skill `quiet-lead-followup`).
10. Clients' domains added to suppression (the list was empty on 2026-09-22).
11. Med-spa figures, before that offer can run.
12. List factory: cap raised to $0.07 per confirmed contact on 2026-09-25; first measured run pending. Recruiting stays off by default until its 1,000-send verdict.
13. Upwork: one overdue review and testimonial ask (skill `client-fulfillment`).
