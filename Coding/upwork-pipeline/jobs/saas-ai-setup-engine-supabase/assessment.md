# Assessment (private, Lorenzo only)

## Time
- Working version, common areas (hours, bays, pricing, memberships, promos, import): 25-35 h, days 1-4. Depends on how clean their existing server functions are.
- Full 12-area coverage on the test account, gap flagging, change log with undo: 60-90 h more, weeks 2-4.
- Handoff (guide, 5 short videos, per-client checklist, training call): 8-12 h.
- Total first project: roughly 95-135 h over 3-4 weeks at their 30-40 h/week.

## Likelihood
- The core pattern (structured output from Claude with a strict schema per area, preview diff, apply via existing functions with idempotency keys) is well understood and buildable. High.
- Unverified: whether their platform already exposes validated server functions for every area. If some areas only exist as direct table writes today, those functions must be written first (that is itself a feature gap and extends scope).
- Undo is the hard part: reversing plans with live billing or imported members needs archive-not-delete and dependency ordering. Needs their data model.
- Multi-processor billing (Stripe and Square) adds risk to anything touching plans; keep plan creation behind an extra check.
- Lorenzo's fit: strong on Claude API, tool calling, MCP, agents on client databases. Their requirements list production Supabase (RLS, Edge Functions, migrations) and payments/billing idempotency experience; be honest on the call about what he has shipped in each.

## Standard pricing
- Market for this profile (senior TS + Supabase + LLM + billing): $60-$120/h. Their $25-$50 range is below market for "expert"; average recorded bid $51.18.
- Recurring software: Anthropic API usage per setup is small (a few dollars per client at most).
- Full-time post: pitch as a retainer.

## Ask before quoting
- Do validated server functions exist for all 12 areas today, or only some?
- How are Edge Functions authorized (service role vs user JWT under RLS)?
- Where does the old-system member CSV come from, and how varied are formats?
- What "undo" must mean for a membership plan once members are billed on it.
- Is there a test account seeded like production?

## Flags
- Rate well under market; full-time commitment 30-40 h/week.
- Client record not pulled.
- Requirements list production Supabase and billing experience; do not overclaim.

## Pricing path (Lorenzo only)
- Value: assumption of 4-8 h of founder/dev time saved per new client, one client a week (post: "signing new clients every week"), at an assumed $100/h fully loaded: $20k-$40k a year, plus dev capacity returned to product.
- Price range at 10-20%: $3,000-$8,000 for the first project, or the retainer at their hourly band.
- Land offer (milestone 1): working version on the test account for the most common areas.
- Upsell: build the flagged feature gaps, read-only AI DB access for support, help desk agent, code hardening around billing.
- Milestones:
  1. 30%: paid once the working version for hours, bays, pricing, memberships, promos and member import is delivered on the test account and you've signed off.
  2. 35%: paid once all 12 areas, preview, validation and feature-gap flagging are delivered and you've signed off.
  3. 20%: paid once the change log with undo and the idempotent re-run tests are delivered and you've signed off.
  4. 15%: paid once the written guide, walkthrough videos, per-client checklist and specialist training are delivered and you've signed off.
