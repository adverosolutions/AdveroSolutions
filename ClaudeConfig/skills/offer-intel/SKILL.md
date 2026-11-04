---
name: offer-intel
description: "'Offer Intel, the \"Offer Intel: Maker School Wins\" Google Sheet that ranks which industry x offer combinations other Maker School members are closing. Covers the sheet''s tabs and columns, how patterns are ranked, the current top patterns, how to rerun or refresh it, and the hard rule that none of it is proof in Lorenzo''s copy. Use when Lorenzo asks \"what offers are working in Maker School\", \"what should I test next\", \"check the wins sheet\", \"rerun offer intel\", or when picking a new niche or offer.'"
---

# Offer Intel (Maker School wins)

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- The existing Maker School wins methodology remains research, never proof of Lorenzo’s outcomes. No new Grok handoff changes its ranking method.
- Use the current November 4 official offer menu for Lorenzo’s prices. A successful member’s price or offer is evidence for a test proposal, not authority to change that menu or written copy.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)


Market research from the Wins category of Nick Saraev's Maker School community.
Each win post is read, the offer facts are pulled out only where the post
states them word for word, and wins are grouped into industry x mechanism
patterns ranked by how many different members won with them.

It is research for choosing what to sell and test. It is never proof:
other members' clients and numbers never go in an email, a reply, a proposal
or a LinkedIn post. Lorenzo's proof comes only from his offer sheet and his
own case studies.

## The sheet

"Offer Intel: Maker School Wins", Google Sheet id
`1ZjV3CbOqoembImFLEAD8M1PgCtrT6SMDzx7av2lTeyc`. Owned by Lorenzo, shared to
the service account as writer.

| Tab | What it holds |
|---|---|
| Summary | counts for the run and the headline picks |
| Patterns | one row per industry x mechanism, ranked |
| Industries | wins rolled up by client industry |
| Offer types | wins rolled up by mechanism and pricing model |
| Wins | one row per analyzed post |
| Winners | one row per member: wins, patterns, channels, first and last win |

### Patterns columns

`rank, pattern, industry, mechanism, winners, winners_90d, wins, wins_30d,
wins_prev_30d, trend, median_setup_usd, median_monthly_usd, median_deal_usd,
cold_email_share, with_numbers, crowded, fit, complete, last_win_at, post_urls`

- **Ranked by `winners_90d`**: different members who won with it in the last 90
  days. One member posting five wins counts once.
- **trend**: rising, steady, fading or new, from wins in the last 30 days
  against the 30 before.
- **Medians** (setup, monthly, deal) count only `new_client` and `first_client`
  wins. Month totals ("first $10k month") and call quotes are not one client's
  price and are left out.
- **fit** flags when the pattern's industry or mechanism is one Lorenzo already
  sells. His mechanisms: lead reactivation, trigger outbound. His industries:
  commercial cleaning, accounting, recruiting, HVAC, plumbing, electrical,
  roofing.
- **crowded** marks a pattern with many recent winners.

### Wins columns worth knowing

`win_type`: first_client, new_client, revenue_milestone, booked_calls,
reply_rate, other_win.

`pricing_model`:

| Value | Means |
|---|---|
| setup_plus_retainer | a setup fee and a monthly fee, both stated |
| retainer | monthly fee, no setup stated |
| rev_share | percentage of the client's revenue or profit |
| pay_per_meeting | paid per booked or attended call |
| pay_per_lead | paid per lead delivered |
| performance | paid per closed deal or sale |
| one_off_build | one fixed price for one job |
| other | hourly, salary, equity, anything else |

A fixed fee plus pay per result takes the per-result model.

Other fields: offer_one_line, mechanism, industry (the client's), buyer_role,
geo, setup/monthly/deal USD, emails_sent, reply_rate_pct, positive_replies,
calls_booked, guarantee, list_source, tools, copy_angle, time_to_result,
experience, evidence_strength, fields_dropped (facts removed because the post
did not state them word for word).

Industry list: dental, med_spa, chiropractic, veterinary, senior_care,
medical_clinic, hvac, plumbing, electrical, roofing, solar, pest_control,
landscaping, home_services, construction, commercial_cleaning, real_estate,
property_management, mortgage_lending, insurance, legal, accounting,
financial_advisory, recruiting, it_msp, saas, marketing_agency, consulting,
ecommerce, restaurants, fitness, beauty, education, auto, logistics,
manufacturing, events, nonprofit, b2b_services.

Mechanism list: lead_reactivation, ai_voice, speed_to_lead, ai_chatbot,
review_generation, trigger_outbound, appointment_setting, pay_per_lead,
recruiting_outreach, content_ghostwriting, crm_setup, paid_ads, seo,
data_enrichment, ai_training, custom_automation.

## Where it stands (first run, 2026-09-23)

90 days of Wins: 257 posts read, 256 analyzed, 223 business wins (21 from cold
email), 140 different winners, 70 wins that state no industry or offer (mostly
screenshots). Model cost $2.15.

Top patterns in that run:

| # | Pattern | Winners 90d | Trend | Median setup | Median monthly | Cold email |
|---|---|---|---|---|---|---|
| 1 | Agencies x CRM / pipeline setup | 3 | rising | $400 | $975 | 0% |
| 2 | Agencies x Outbound appointment setting / lead gen | 3 | rising | $580 | $300 | 67% |
| 3 | SaaS / software x Custom automation build | 3 | new | - | - | 0% |
| 4 | Consulting / coaching x Custom automation build | 3 | fading | $550 | $250 | 0% |
| 5 | Construction / GC x AI consulting / training | 2 | steady | - | - | 0% |
| 6 | Real estate x CRM / pipeline setup | 2 | new | $12,000 | $750 | 0% |

The medians above are recomputed from that run's `wins.csv` with the
closed-deal rule (only `new_client` and `first_client` wins). The first run's
digest and the live Sheet were written before that rule existed, so they still
show $6,500 monthly for row 3 (one revenue_milestone win) and $4,125 for row 6
(the median of a $750 first client and a $7,500 month total). Running `report`
again rewrites them from the stored wins at no model cost.

Read these as small samples: the top pattern has 3 winners. Open the
`post_urls` before acting on any row.

## How to use it

1. **Picking what to test.** Start from the Patterns tab. Prefer rising or new
   patterns with several different winners and numbers stated. Open every post
   URL for the row and read it before believing the medians.
2. **Checking a niche Lorenzo already runs.** Filter `fit`. A fit pattern that
   is fading or has one winner is a signal to look harder, not a verdict.
3. **Shaping a new offer.** The next build is an "offer card": for a pattern
   Lorenzo picks, a draft in his offer-sheet shape plus an ICP draft and the
   evidence posts. It is never written into his offer sheet or ICP files
   automatically; he decides.
4. **Never** quote a member's result, client or price as if it were
   Lorenzo's, and never put it in copy.

## Refreshing it

Runs on Lorenzo's Mac only (the Skool login lives there). Steps, all
read-only against Skool:

1. `collect --via mcp` with the Wins category URL and `--since` 90 days back
   (about 270 Skool calls, 25-35 minutes, 2.5-4.5 s between calls).
2. `analyze --preflight` to price it (spends nothing), then the billed
   `analyze` with paid calls allowed. About $6 per 1,000 posts. The shared
   model budget is $10 across every job; a big backfill needs Lorenzo to raise
   it.
3. `report` (free) writes wins, patterns and winners CSVs and a digest.
4. Write to the same Sheet id. The first Sheet was written by a scratch script,
   not repo code.

A weekly Sunday 06:00 CT refresh (last 14 days, re-reading comments on young
posts) is proposed and not installed. It needs Lorenzo's OK.

Collect statuses: `ok`, `logged_out` (log skool-mcp back in), `fetch_failed`,
`mcp_unavailable`, `bad_url`.

## Known limits (as of 2026-09-24)

- Comments come 25 top-level per call and the paging parameter is unknown; 39
  of 256 threads had more (`threads_partial`).
- "Pay per closed call" is ambiguous between pay_per_meeting and performance.
- Warm deals can be tagged `cold_call` as the channel.
- The fixed prompt from 2026-09-24 has not been tested on a paid run.
- The refresh code, including `collect --via mcp`, is on the local branch
  `claude/confident-cohen-1d1cda` at commit a22912e. The branch
  `claude/maker-school-wins-tracking-153w0r` stops at 71d4adc and has no mcp
  path. Neither is on `main`.

Related: the `maker-school` skill digests new Maker School posts for the Upwork
system; this skill is only the Wins sheet.

## Sources (for maintainers)

- Memory `offer-intel.md` (modified 2026-09-24): run facts, Sheet id and tabs, fixes, open items.
- `Agentic Worklfows/runbooks/offer_intel.md` at commit a22912e (2026-09-23, branch `claude/confident-cohen-1d1cda`; origin's `claude/maker-school-wins-tracking-153w0r` stops at 71d4adc and lacks the mcp path).
- `Agentic Worklfows/services/offer_intel/extract.py` and `gate.py` at a22912e (pricing models, win types, field list); `config/offer_intel/taxonomy.json` at a22912e (industries, mechanisms, "our" lists).
- `Agentic Worklfows/.tmp/offer_intel/out/digest_2026-09-24.md` and `patterns.csv` (top patterns table).
- Proof rule: `Agentic Worklfows/config/offers.md` on origin/main; memory `lorenzo-case-studies.md`.
