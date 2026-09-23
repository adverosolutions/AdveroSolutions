# GoHighLevel job analysis — 2026-09-16

Sources: `applications-scoring-log-ARCHIVED.csv` (151 scored jobs, Aug 13–17), Upwork MCP
(31 submitted proposals Aug 11–Sep 9, 2 contracts), 16 full job descriptions re-fetched,
and a live title search on "GoHighLevel" / "GHL" / "HighLevel" (30 posts, Sep 9–17).

## Headline numbers

| Platform named in scored jobs | Count / 151 |
|---|---|
| GoHighLevel | 29 |
| Make.com | 17 |
| n8n | 16 |
| HubSpot | 6 |
| Zapier | 3 |

| Your GHL funnel so far | Count |
|---|---|
| GHL jobs scored | 29 |
| GHL jobs applied to (all $5–$20 placeholder budgets, Aug 24–26) | 6 |
| GHL jobs won | 0 |
| Contracts won overall (both n8n/Make or cold-email infra) | 2 |

Live market: roughly 10+ new GHL-titled posts per day. Proposal counts on the good ones run
25–110, so the prop has to be visibly real, not a diagram.

## What GHL clients actually ask for (34 historical jobs, multi-label)

| Component in the ask | Jobs | Share |
|---|---|---|
| Workflow automation (follow-up drips, missed-call, reminders, stage triggers) | 16 | 47% |
| Integration glue (Instantly, Apollo, Monday, Notion, Vapi, ManyChat, Calendly, Sheets via n8n/Make/Zapier/API) | 15 | 44% |
| CRM structure (pipelines, fields, tags, calendars, sub-account, migration, snapshot) | 11 | 32% |
| Ongoing VA / QA / training / admin | 8 | 24% |
| Funnels / landing pages / sites | 4 | 12% |

Answer to the CRM-vs-automation question: **automation wins, and CRM setup almost never
ships alone.** Standalone "set up my CRM" appeared 3 times (the $100 recurring account-setup
job, a $250 UK real-estate CRM, the $1,500 Michigan sub-account migration). Every other
CRM-structure ask was bundled with follow-up workflows. Standalone automation *fixes*
("one new-lead follow-up isn't firing") are the most common low-ticket GHL job.

Money sits in the mixed builds: Singapore $550 + $2,000 (Instantly → GHL → WhatsApp),
Canada $500 (full CRM + AI + Reply.io), Michigan $1,500 (migration + Medicare pipeline),
Wellness $18–50/hr (GHL + Calendly + Square scheduling), healthcare snapshot builder $50–75/hr.
The $5–$20 posts you applied to were task-farm placeholders and none converted.

## The specific automations that recur (ranked by frequency)

1. **New-lead multi-channel follow-up** — SMS + email drip, delays, branch on reply,
   exit on booked/replied/DNC. Named in 12+ posts. You already have the n8n version
   (`crm-stage-trigger-to-sms-email-follow-up-with-exit-rules`).
2. **Appointment booking + reminders + no-show recovery** — 7 posts, includes the wellness
   scheduling job and the UK client that just closed an "Appointment Booking Automation" hire.
3. **Pipeline-stage automation** — move opportunity, create task, notify owner, tag.
   Real-estate acquisitions/dispositions pack is the recurring vertical shape (5 RE posts).
4. **Missed-call text-back + speed-to-lead notification** — 4 posts, all home services /
   roofing / agencies. Your vertical.
5. **Inbound lead source → GHL** — Instantly, Apollo, Meta lead forms, ManyChat, webhooks.
   6 posts. This is the one part that demos better in n8n; keep that prop, add the GHL-side
   Inbound Webhook workflow.
6. **Database reactivation campaign** — 3 posts. Same mechanic as your med-spa reactivation
   offer, so it doubles as your own sales asset.
7. **AI layer** — Conversation AI, voice receptionist, WhatsApp agent. 8 posts and growing,
   but needs paid GHL add-ons to demo. Pair with the n8n + Vapi prop for now.
8. **Snapshot / sub-account template for agencies** — 5 live posts this week. Agency-side
   buyers, higher rates, and a snapshot is exactly what the library below produces.

Verticals by frequency: real estate (wholesale, realtor), home services / roofing,
wellness / med spa / healthcare, coaching / Skool, dental, auto.

## Why the rubric capped GHL and what changes it

RUBRIC.md v2.1 caps GHL-native at D2=5 because "GHL has no import format, so the prop is
a static mockup." That premise is half right. GHL has no *workflow JSON* import, but it has
**snapshots**: an agency account exports a whole sub-account (pipelines, fields, workflows,
calendars, forms, templates) as a shareable link, and any GHL account imports it in one
click. A snapshot import on camera *is* a working build on camera, and the client can
receive the exact link after the call. That is a stronger prop than an n8n JSON because
the client does not have to run anything.

## Build plan: a GHL snapshot library

**Prerequisite:** a GHL Agency account. Starter is $97/mo (3 sub-accounts, 14-day trial).
No account or key exists in `.env` or memory today, so this is a decision for Lorenzo.

**Three sub-accounts = three vertical packs**, each exported as one snapshot:

| Pack | Workflows inside | Serves posts like |
|---|---|---|
| Home Services (roofing/HVAC) | missed-call text-back, speed-to-lead notify, new-lead SMS+email drip, quote follow-up, reactivation | roofing missed-call, GHL VA speed-to-lead, contractor asks |
| Real Estate (wholesale/realtor) | acquisitions + dispositions pipelines, stage-trigger tasks, seller follow-up drip, DNC/STOP handling, buyer-marketing sequence | wholesale RE CRM, RE CRM test, Realtor master system, Wavv dialer |
| Wellness / Med spa | booking + reminders + no-show recovery, membership/package tags, database reactivation, review request | wellness scheduling, med-spa migration, healthcare snapshot |

Shared across packs: standard custom fields, lead-source tagging, internal notification
workflow, Inbound Webhook workflow that pairs with the existing n8n Instantly/Apollo props.

**Who builds it:**

- CRM structure (pipelines, stages, custom fields, tags, calendars) — scriptable through the
  GHL API v2 with a Private Integration token. Deterministic Python in `execution/`, matches
  the 3-layer architecture, re-runnable per client sub-account.
- Workflows — no public create-workflow endpoint, so this is UI work. A browser agent
  (in-app browser or Chrome) can drive the workflow builder: add trigger, add action, set
  delays, set branch conditions, save, publish. Expect 20–60 clicks per workflow, brittle
  selectors, and a review pass by you before export. Run it as a one-time library build
  (roughly 15 workflows across 3 packs), not per job.
- Per job — import the pack snapshot into a fresh sub-account named after the client,
  rename, swap copy for their vertical, record. Five minutes of prep, which is the same beat
  the n8n path already has.

**Loom beat for a GHL post:** open the client-named sub-account, show the snapshot import
already applied, open the one workflow their post names, walk the trigger → delay → branch
→ exit, then say the snapshot link ships with the proposal.

**Rubric change once the library exists:** GHL-native jobs with a matching pack score
D2=10 (importable, working build on camera). GHL jobs that need something outside the packs
score 7. Remove the 5 cap.

## Ordering

1. Decide on the GHL agency account.
2. Script the CRM structure via API for the Home Services pack first (your vertical, the
   missed-call and follow-up asks are the most frequent, and the reactivation workflow is
   your own offer).
3. Browser-agent the five Home Services workflows, you review, export snapshot, test-import
   into a second sub-account on camera.
4. Repeat for Real Estate, then Wellness.
5. Patch RUBRIC.md D2 and `PROCESS.md` props table.
