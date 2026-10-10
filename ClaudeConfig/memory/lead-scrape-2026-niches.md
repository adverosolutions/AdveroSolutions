---
name: lead-scrape-2026-niches
description: "Sept 2026 cold-email lead project — final niches are recruiting (done), commercial cleaning, bookkeeping/tax; law & dental were scraped then dropped; ~1,250-1,350 verified-clean per niche"
metadata:
  node_type: memory
  type: project
  originSessionId: 7cf0d1de-bf83-4dd0-b43e-acfe059e5808
  modified: 2026-10-01T02:24:32.277Z
---

Lead-scrape project lives in `Coding/lead-scrape-2026/` (runner.py, niches/*.json,
final_export.py, merge_verified.py; outputs in output/verified/). Apify actor
`code_crafter/leads-finder`, MillionVerifier key + Apify token both in that dir's `.env`.

**Niche history:** Aug 17 2026 scraped recruiting / PI+immigration law / dental to
4,034 verified-clean total. On 2026-09-01 Lorenzo re-optimized offers and pivoted the
final three to: **boutique perm recruiting** (already done, 1,437 clean), **commercial
cleaning** (new), **bookkeeping & tax firms** (new). Law and dental are no longer needed.
Vet and corporate-events were $0.22 availability tests only.

**Target:** ~1,250 verified-clean per niche (he said "1,250 or whatever"; earlier plan
was 1,350 / 4,000 total). Every lead must be MillionVerifier-clean before enrichment;
he keeps catch_all/unknown as a separate "risky" file. Next phases after scraping:
enrichment, then personalization built together.

**Why:** Offer/flow optimization changed the ICP; the three niches drive three
separate campaigns.

**How to apply:** Don't re-scrape recruiting/law/dental. Cleaning needs
`company_not_industry: consumer services` + restoration exclusions (Servpro leaked
badly). Apify Starter cap is $29/cycle, resets the 9th — budget was the binding
constraint on 2026-09-01. Related: [[apify-lead-actor-mechanics]], [[apify-free-plan-api-gate]]

**Outcome 2026-09-01 (final):** recruiting 1,437 / bookkeeping 1,394 (65%) / cleaning 1,222
(44-46%) verified-clean = 4,053; SENDABLE incl. risky = 6,466. Files in `output/FINAL/`
(CLEAN_3niches.csv, SENDABLE_3niches.csv, per-niche). Cleaning got to 1,222 only after adding
the `c_suite` seniority pool (CEO/President-titled owners) — owner/founder/partner alone
capped at 876. Lorenzo raised the Apify cap to $45 himself; ~$1.84 left, resets Sept 9.
Next phase: enrichment, then personalization built together. Google Sheet still not set up
(service account can't create sheets; he must create + share one).
**Live sheet (2026-09-02):** https://docs.google.com/spreadsheets/d/1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw
(id `1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw`, tab `Leads`, shared with
advero-crm-automation@adverosolutions.iam.gserviceaccount.com). Rows are in send order:
25 clean -> 5 catch-all blocks, surplus catch-all then unknown at the tail
(`arrange_send_order.py --clean N --risky M` regenerates). Personalization columns are
empty; `personalize/live_personalize.py <id>` writes them row-by-row live. Offers per
niche still unknown; Lorenzo wants research done by Claude on-plan, not Perplexity/API.

**Wave 4 (2026-09-16) and wave 5 (2026-09-28), unverified (no MillionVerifier credits):**
Wave 4 deepened the original three: bookkeeping +4,631, recruiting +1,906, cleaning +254
(cleaning is exhausted in every state and pool). Wave 5 added five split-test niches in the 12
big states only (owner+c_suite pools, $0.22 nationwide smokes first): msp 1,614,
marketing_agency 1,633, insurance_broker 1,622, landscaping 1,039, pest_control 765.
Marketing, insurance and MSP delivered at quota (deep supply); pest/landscaping under-delivered.
Configs in `niches/{msp,marketing_agency,insurance_broker,landscaping,pest_control}.json`;
scraper `wave4.py` (pipe-separated states, `--weighted=N`, `--seniority`, `--out`);
exports `wave4_export.py` / `wave5_export.py` (dedupe vs everything scraped, domain
suppression vs the sheet, on/off-niche regex, owner-title filter, precheck, sheet append).
Sheet rows: 19,930; new rows are block_type UNVERIFIED, mv_result "unverified", lead_id
prefixes MS/MA/IN/LA/PE. Apify usage this cycle $41.49 of the $45 cap (resets Oct 9); the
39 remaining states for the five new niches are next cycle. Lorenzo now has 45 inboxes.

## Personalization run 2026-09-28/29 (overnight)
- 14 batches of 100 verified-clean rows personalized on the sheet (1,277 lines): bookkeeping 173, recruiting 169, cleaning 76, insurance 193, landscaping 181, marketing 166, MSP 144, pest 175.
- Recruiting, bookkeeping and cleaning rows (418) were pushed to the six Instantly campaigns. The five new niches have lines on the sheet only: no Instantly campaign or offer exists for them yet, so `instantly_push.py` skips them by design.
- Recurring hand-fix patterns: Haiku fills invent client types not in X, use "by now" outside the desk line, region names (Long Island, central California, Treasure Coast), and competitor nouns (PR firms, recruiters). Foreign companies and off-niche rows (software devs, web designers, job boards, pool/pond/HVAC, salons) slip through the Apify filters and are skipped by hand each batch.
- The gate in daily_apply.py re-flags different rows after each approval (variety rules), so the loop-approve script in the session scratchpad ran until flagged=0; the loop is worth folding into daily_apply.py.
- Thousands of verified-clean rows remain unpersonalized; `daily_pick.py --n 100 --only-clean` continues from where it left off.

## Personalization run 2026-09-30 (AI agents offer, new niches)
- Every non-Microsoft verified/unverified row on the sheet was personalized: 8 batches (0207, 2038, 2040, 2045, 2050, 2056, 2111, 2114), send files `output/daily/day_20260930_<batch>.csv`. Nothing pushed to Instantly: the AI-agents campaigns from the Claude Doc copy are not created yet (blocked on Lorenzo's go-live and the doc's open questions).
- Lorenzo wants extraction and fill subagents on Sonnet 5.5 from now on (Agent `model: "sonnet"`, verified as claude-sonnet-5-5 in the transcripts). Haiku wrote keyword scripts and pasted page text.
- Tools in `personalize/tools/`: stage.py (merge / `FILL_N=40 ... fill <batch> mixed [restore ids]` / prompts_extract), prompts extract_mixed.txt + fill_mixed.txt, xcheck.py, review.py, applyfix.py (resets approved.json, so run it before the loop), approve_rest.py (now retries on an empty gate result: back-to-back daily_apply calls hit the Sheets rate limit and print nothing), cap.py + capskip.py (marks cap ids skip in select.json without touching approved.json).
- Later batches repeat companies heavily (same firm 3-4 contacts); run cap.py before hand review and check each kept row's Y against the line already sent to that company.

## Push run 2026-09-29/30 (night, recruiting/bookkeeping/cleaning to Instantly)
- Batches `20260929_2151` to `20260930_0035` (about 12 leads per extract chunk, Haiku extract + fill agents, hand review per batch) pushed roughly 4,200 leads to the six campaigns, split 50/50 per niche. Risky rows included, Google/other/Zoho only.
- Recruiting and cleaning ran out of Google/other/Zoho rows (picker returned EMPTY); what is left in those niches is Microsoft or Yahoo. Bookkeeping still had stock when the run stopped (picker task ended with the session).
- `cap.py` caps 2 contacts per (company, city) across every pushed day file; cap ids go into the man file's skip list as "duplicate company (already 2 contacts)".
- Per-batch hand rules: Y never uses vague verbs (file taxes, manage books), plural nouns or a missing "be able to"; X drops city/state names; foreign firms and off-niche rows (consulting, wealth management, software, job boards) are skipped; staffing, payroll and CFO firms that extract marked off-niche get restored.

## Mailbox-provider rule (Lorenzo, 2026-09-29)
- **Changing 2026-10-12 (Lorenzo, said 2026-10-08): Microsoft-hosted leads may be sent from Monday 2026-10-12.** `instantly_push.py` ALLOWED_ESP and `daily_pick.py --esp` default still exclude Microsoft until someone changes them on/after that date.
- No Microsoft-hosted leads go to Instantly: the sending inboxes cannot land in Microsoft (see [[deliverability-2026-09-25]]). Google, "other" (GoDaddy, Rackspace, self-hosted) and Zoho are fine; free Yahoo mailboxes stay out.
- Provider comes from an MX lookup (`personalize/esp.py`, cache in `output/mx_cache.json`). `instantly_push.py` ALLOWED_ESP enforces it on every push; `daily_pick.py --esp` defaults to the same set so no personalization is spent on excluded rows.
- 207 uncontacted Microsoft leads added 2026-09-28 were deleted from the six campaigns (list in `output/deleted_microsoft_20260929.json`). Already-contacted Microsoft leads were left in place.
- Risky (catch-all/unknown) rows are now allowed for recruiting, bookkeeping and cleaning because supply is short; Lorenzo auto-pauses on bounce rate.
