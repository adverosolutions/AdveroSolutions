# Dossier - AI/Automation Engineer: Build an AI Setup Engine for a SaaS Platform (Supabase + TypeScript)

url: https://www.upwork.com/jobs/~022104603594668896549

## Who they are
- First name: unknown (post is unsigned, no `client first name:` line)
- Company: unknown ("a fast-growing vertical SaaS company", no product name)
- Industry: vertical SaaS that "runs bookings, memberships, recurring billing, payments and customer communications for recreation and entertainment venues"
- Location / timezone: United States
- Website read: none named

## Client
no client intel

## Tools they named
React, TypeScript (Vite), Supabase (Postgres, Row Level Security, Edge Functions (Deno), scheduled jobs), payment processor APIs incl. Stripe and Square, GitHub, "AI coding tools", LLM APIs (tool calling, structured outputs), MCP servers, Claude Code, Cursor, Intercom Fin, Help Scout, CSV.

## Every number in the post
- Hourly $25-$50, expert, full time 30-40 h/week, contract to long-term
- "signing new clients every week"
- "Within the first few days ... a working version covering the most common setup areas"
- "Within the first few weeks ... full platform coverage, tested on a test account"
- 12 configuration areas listed (counted, not stated)
- Recorded bids avg $51.18 (metadata)

## Their requirements, verbatim, in their order
Configuration areas:
1. "business details, hours and holiday closures"
2. "bays/rooms, per-room hours and buffers"
3. "pricing: base rates, peak and off-peak windows, member rates, overage and guest fees"
4. "memberships, punch passes, lesson packages, commitment and annual-fee plans"
5. "promo codes, discounts and referral programs"
6. "instructors, lesson types, durations and schedules"
7. "events, leagues and packages"
8. "customer and member imports (CSV), including mapping existing members to new plans"
9. "waivers, membership agreements and cancellation policies"
10. "automated messages and notifications"
11. "booking page settings and branding"
12. "door access settings"
How it works:
13. "The onboarding specialist pastes in the client's requirements: an email, a document, notes from a call."
14. "AI converts them into structured configuration across all of the areas above."
15. "The system shows one clear preview of everything that will be created or changed."
16. "A human approves, and the system applies it through the platform's own validated server functions, never through direct database writes."
17. "Anything the platform doesn't support yet gets flagged as a feature gap with a clear description, instead of being guessed at."
18. "Every change is logged and can be undone."
Handoff:
19. "written guides", "short walkthrough videos", "a checklist for each new client"
Out of scope: "payment processor credentials (API keys and secrets). Clients always enter those themselves."

Grouping: 19 parts. Prototype screens: Overview, Intake (13), Configuration (1-12 and 14, one sub-view per area), Preview & approve (15, 17, validation, credentials exclusion), Apply (16, idempotency), Change log (18), Handoff (19).

## The odd ask only they would recognize
"You design for 'what if this runs twice' and 'what if the AI misreads the input.'" Both are live on screen: re-running the changeset replays every idempotency key with zero writes, and three validation errors from misread notes block approval until fixed.

## What their hiring history implies
Not pulled. The post reads like a technical founder: exact stack, safety language (idempotency, reconciliation), fast timeline. Judges on engineering judgement, not visuals alone.

## Their likely data
A new venue client's kickoff email. Sample (fictional, labelled sample): an indoor golf simulator venue with 6 bays.

```json
{ "venue": "Ridgeway Indoor Golf (sample)", "bays": 6, "buffer_min": 10, "off_peak_rate": 50.00, "peak_rate": 65.00, "peak": "Mon-Fri 17:00-22:00, Sat-Sun all day", "member_discount": 15.00, "guest_fee": 10.00, "overage_per_min": 1.00, "plans": ["Unlimited $199/mo, 6-mo commit, $99 annual", "Off-Peak $119/mo"], "import_rows": 412 }
```

## Sizing
Not a setup-sizing job. One changeset per client; the sample client produces 44 server-function calls across 12 areas (sample, illustrative).

## Three things they would recognize on screen
1. The 12 areas in their words and order: Intake extraction list and Configuration sub-nav.
2. "What if this runs twice": Apply screen, "Run the same changeset again" returns replayed keys, 0 writes.
3. "Never through direct database writes" and payment credentials out of scope: calls shown as applyPricingRule() with idempotency keys; Stripe keys in the email are excluded, not extracted.

## Beat 1 draft
"This is your AI setup engine, running a new venue's onboarding."
