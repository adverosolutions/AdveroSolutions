# AI agents split-test prep — live Instantly pull
Pulled: 2026-09-30 14:39 CT · **READ ONLY** (no Instantly mutations).

Win metric: **interested / sent** (`total_interested` via overview `expand_crm_events=true`). Unique replies are context only.

## Campaigns (all 6 live, status=active)

| Rank | Key | Niche | Status | Life sent | Life uniq | **Life int** | **Int rate** | 7d sent | 7d uniq | **7d int** | Today sent | Today uniq | Today int |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `cleaning_reactivation` | cleaning | active | 641 | 8 | **5** | **0.780%** | 241 | 2 | **4** | 50 | 1 | 2 |
| 2 | `cleaning_trigger` | cleaning | active | 637 | 5 | **2** | **0.314%** | 237 | 0 | **0** | 50 | 0 | 0 |
| 3 | `recruiting_reactivation` | recruiting | active | 644 | 4 | **1** | **0.155%** | 244 | 1 | **1** | 50 | 0 | 0 |
| 4 | `recruiting_outbound` | recruiting | active | 625 | 6 | **0** | **0.000%** | 225 | 3 | **0** | 50 | 0 | 0 |
| 5 | `bookkeeping_reactivation` | bookkeeping | active | 637 | 3 | **0** | **0.000%** | 237 | 1 | **0** | 50 | 1 | 0 |
| 6 | `bookkeeping_trigger` | bookkeeping | active | 641 | 2 | **0** | **0.000%** | 241 | 1 | **0** | 50 | 0 | 0 |

Org totals — today: 300 sent / 2 uniq / 2 int · 7d: 1425 / 8 / 5 · life: 3825 / 28 / 8

### vs Sep 28 ranking
- **cleaning_reactivation** pulled ahead: life interested **5** (was 2 on Sep 28) — now clear #1; 4 of 5 in trailing 7d, 2 today.
- **cleaning_trigger** still #2 by life interested (2) but **0 interested in trailing 7d** — hold as control skeleton, watch.
- **recruiting_reactivation** still the only non-cleaning with any interested (1).
- bookkeeping_* + recruiting_outbound still **0 interested** at ~625–641 sends.

## Step-0 / variant (lifetime) — unique replies only (API has no interested-by-variant)

| Campaign | Var | Subject (live) | Life sent | Life uniq replies | 7d sent | 7d uniq |
|---|---:|---|---:|---:|---:|---:|
| `cleaning_reactivation` | 0 | `{{firstName}}, question` | 341 | 6 | 127 | 2 |
| `cleaning_reactivation` | 1 | `cancelled accounts` | 47 | 0 | 47 | 0 |
| `cleaning_trigger` | 0 | `{{firstName}}, question` | 342 | 4 | 125 | 0 |
| `cleaning_trigger` | 1 | `walkthroughs` | 44 | 0 | 44 | 0 |
| `recruiting_reactivation` | 0 | `{{firstName}}, question` | 402 | 1 | 194 | 0 |
| `recruiting_outbound` | 0 | `{{firstName}}, question` | 382 | 6 | 162 | 3 |
| `bookkeeping_reactivation` | 0 | `{{firstName}}, question` | 401 | 0 | 187 | 0 |
| `bookkeeping_trigger` | 0 | `{{firstName}}, question` | 405 | 1 | 189 | 0 |

_Note: Instantly steps analytics expose sent/replies by variant, not interested. Cleaning has subject A/B live (question vs walkthroughs / cancelled accounts); body shared across variants. Var 1 subject A/B is newer/smaller sample (~47 sends)._

## Live Email-1 (step 1) vs AI-agents draft

All live campaigns still sell **cold-email / reactivation / outbound systems** with roofing proof + guarantees/commission language. **AI-agents offer is NOT live anywhere.**

### `cleaning_reactivation` — subjects: `{{firstName}}, question`, `cancelled accounts`
```
{{personalization}}

{Know this is out of left field|This is a bit out of left field}, if I could help recover the money from accounts that cancelled or stopped renewing their contracts in exchange for a commission on the accounts I bring back, {would you be open|are you open}? I work mostly on performance and am building my network.

{About me:|Quick background:} I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months. Would cost you nothing upfront.

{Let me know.|Curious if this lands.}

{Thanks|Thanks for the time},
Lorenzo
```

### `cleaning_trigger` — subjects: `{{firstName}}, question`, `walkthroughs`
```
{{personalization}}

I build outbound acquisition systems. I recently implemented the same system for a commercial roofing company doing around $150M/yr and was able to generate around $180,000 in 90 days.

I do this by watching for triggers (new leases, office expansions, property management changes, new construction) and run outreach under {{companyName}}'s name. All the walkthroughs would land straight on your calendar.

I'm so confident that I guarantee at least $24,000 a year in new cleaning contracts signed within 90 days, or I give your money back and throw in a $200 gift card to your favorite steakhouse.

{If this interests you|If this is of interest}, {let's hop on|happy to jump on} a short 15 minute call. Just reply {Yes|yes} and I can {shoot you over|send} a calendar invite.

{Thanks|Thanks for the time},
Lorenzo
```

### `recruiting_reactivation` — subjects: `{{firstName}}, question`
```
{{personalization}}

I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

TLDR: I'd recover lost revenue by building email and text sequences that would go out to any dormant or near miss candidate accounts.

I'm so certain this would work for you that I won't charge you a single cent up front, only a percentage of placement fees from accounts I bring back, $0 if nothing closes. I truly believe I can benefit {{companyName}}.

{Would you be open to|Open to} a quick 15 minute call about this? If so just {say yes|reply yes} and I'll {shoot|send} a calendar invite over.

{Thanks|Thanks for the time},
Lorenzo
```

### `recruiting_outbound` — subjects: `{{firstName}}, question`
```
{{personalization}}

I build outbound systems for recruiting agencies. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

Here's what this would look like for {{companyName}}: I watch for {{specialty}} roles sitting open on job boards, run outreach to the hiring managers under your name, and put the intro calls straight on your calendar.

I'm so confident this works that I guarantee at least $40,000 in new placement fees from those calls within 180 days, or I return your money and throw in a $200 gift card to your favorite steakhouse.

{Worth a quick 15 minute call|Open to a quick 15 minute call}? Just {say yes|reply yes} and I'll {send|shoot over} a calendar invite.

{Thanks|Thanks for the time},
Lorenzo
```

### `bookkeeping_reactivation` — subjects: `{{firstName}}, question`
```
{{personalization}}

I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

TLDR: I'd recover lost revenue by building email sequences that would go out to any lost inquiries and former clients, timed to tax season, quarterly estimates, and year-end cleanup. Booked straight onto your calendar.

I'm so certain this would work for you that I won't charge you a single cent up front, only a percentage of first-year fees from clients I bring back, $0 if nothing closes. I truly believe I can benefit {{companyName}}.

{Would you be open to|Open to} a quick 15 minute call about this? If so just {say yes|reply yes} and I'll {shoot|send} a calendar invite over.

{Thanks|Thanks for the time},
Lorenzo
```

### `bookkeeping_trigger` — subjects: `{{firstName}}, question`
```
{{personalization}}

I build outbound acquisition systems. I recently implemented the same system for a commercial roofing company doing around $150M/yr and was able to generate around $180,000 in 90 days.

I do this by watching for triggers (new business formations, companies posting part time bookkeeper or admin roles, second location openings) and run outreach under {{companyName}}'s name. All the discovery calls land straight on your calendar.

I'm so confident that I guarantee at least $15,000 in new annual client fees signed within 90 days, or I give your money back and throw in a $200 gift card to your favorite steakhouse.

{If this interests you|If this is of interest}, {let's hop on|happy to jump on} a short 15 minute call. Just reply {Yes|yes} and I can {shoot you over|send} a calendar invite.

{Thanks|Thanks for the time},
Lorenzo
```

### AI draft (not live) — from `20260928_ai_agents_offer_split_variants.md`
- **2A** Mirror cleaning_reactivation: ops cleanup + revenue plug, soft Let me know, `[PROOF TO CONFIRM]`
- **2B** Mirror cleaning_trigger: agents on busywork/follow-up + revenue, soft Yes / calendar

## Underperform → pause+replace candidates

| Key | Life sent | Life int | Life uniq | Evidence | Action |
|---|---:|---:|---:|---|---|
| `recruiting_reactivation` | 644 | 1 | 4 | meaningful_borderline | watch_or_soft_replace |
| `recruiting_outbound` | 625 | 0 | 6 | meaningful | pause_and_replace_candidate |
| `bookkeeping_reactivation` | 637 | 0 | 3 | meaningful | pause_and_replace_candidate |
| `bookkeeping_trigger` | 641 | 0 | 2 | meaningful | pause_and_replace_candidate |

- **Clear pause+replace (0 interested, meaningful ~630 sends):** `bookkeeping_reactivation`, `bookkeeping_trigger`, `recruiting_outbound`.
- **Borderline keep/watch:** `recruiting_reactivation` (1 interested) — do not kill for volume unless needed for AI lane.
- **Do NOT pause:** `cleaning_reactivation`, `cleaning_trigger` (winning skeletons / control).
- 7d alone is thin for kill calls on any single niche (~225–244 sends each); **lifetime** is the judgment window.

## Recommended split approach

**Add AI lane as A/B (positioning plug), not a full replace of winning campaigns.**

1. Keep cleaning_reactivation + cleaning_trigger as **control** (Mirror A / Mirror B structures).
2. Free volume from **bookkeeping_* + recruiting_outbound** (0 interested) — those are the pause+replace slots for AI 2A/2B **or** stand up new campaigns on the five locked niches (MSP / SEO agency / insurance / landscaping / pest) using the same skeletons.
3. Once live, A/B **AI agents (2A/2B)** vs **cold-email DFY (1A/1B)** on the same list — structure stays, plug changes only.
4. Do **not** invent a third skeleton. Do **not** go live until Lorenzo gaps below are closed.

## Gaps still needing Lorenzo (unchanged from Sep 28 draft)

- Exact product name for AI-agents offer (working: 'AI agent systems')
- Approve or replace [PROOF TO CONFIRM]
- Confirm 'under how you already operate' vs 'under your name'
- Whether AI-agents lane suppresses against same cleaning lists for landscaping/pest

## Explicit non-actions this pass
- No Instantly step create/update/pause.
- Copywriter not briefed.
- User not messaged.

JSON: `/home/box/advero/state/handoffs/20260930_ai_agents_split_prep.json`

