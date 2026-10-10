---
name: list-builder-maps-quickenrich
description: "2026-10-08 lead-volume plan: free 12M Google Maps export (coldoutboundskills repo) + QuickEnrich domain search + MillionVerifier, screening by Claude on his plan (not API); current cost baseline"
metadata:
  node_type: memory
  type: project
  originSessionId: a19da11f-8676-481c-b05d-1e4a1318a1fb
  modified: 2026-10-08T23:34:02.654Z
---

On 2026-10-08 Lorenzo asked to cost and test the `list-builder` skill from the public repo github.com/growthenginenowoslawski/coldoutboundskills (copy of SKILL.md in ~/Downloads). Goal: far more emails than the Apify actor gives.

**What he wants (his words, 2026-10-08):** every email from QuickEnrich ("that plan is just cheaper"); Claude as the harness/judge **on his paid plan, not the API**; asked whether MillionVerifier is still needed and whether a free Prospeo key exists.

**Facts established:**
- Baseline (waves 4+5): about $90 for 7,715 MV-ok emails = $0.012/clean, about $0.019/clean non-Microsoft. About 40% of domains are Microsoft-hosted. Cleaning and recruiting are near exhausted in code_crafter/leads-finder.
- Repo bundles "Google Maps Scrape - 12M US Businesses" (13 zips, about 470 MB; columns title, link, phone, category_titles, zip_code, normalized_display_link; no emails or owner names). It has 12.3M rows and 3.79M distinct domains. Distinct domains per niche: insurance 70k, bookkeeping/tax 61k, landscaping 36k, marketing agency 35k, MSP/IT 27k, cleaning 26k (16k commercial/janitorial), recruiting 17k, pest 8k. Unzipped copy was in the 2026-10-08 session scratchpad only.
- QuickEnrich (quickenrich.io): `GET /api/employees/dataset-search?company_url=&title=` returns up to 20 contacts/page with email. It charges 1 credit per contact returned with email/phone and nothing on no result. Growth is $99/mo for 25k API credits ($0.004). WebApp Unlimited ($83) has no API. Free tier is 300 lookups/mo. The response has NO verification status or catch-all flag (only `email_verification_date`), so MillionVerifier stays the gate. Domain search is limited to 300 req/min.
- The list-builder repo as published can't produce emails without GetLeads/Blitz: Prospeo person rows carry no email (contacts.ts:180), there is no MillionVerifier script, there is a Blitz column bug, and run-lane has no limit flag. Its judge is GPT-5-nano over the API.

**QuickEnrich-only test, 2026-10-08 (free tier, 299 credits):** results are in `Coding/lead-scrape-2026/output/quickenrich_test_20261008/`, including the script `qe_test.py`, which loads the key from that folder's env file and hard-caps credits.
- Contact Finder is free (0 credits). It reports `meta.total` and `remaining_credits`, and the lookups are public. US owner-titled contacts with email at companies under 100 staff: marketing 68k, IT services 43k (MSP-described 3.8k), insurance 32k, bookkeeping 28k, recruiting 15k, landscaping 3.5k, cleaning 0.9k janitorial + 2.9k facilities/cleaning, pest 2k. Overlap with the sheet was 2-20%.
- A Claude screen via `claude -p --model sonnet --tools ""` ran on the plan (authMethod claude.ai). It took 20 s for 400 rows and failed 12.5%. It costs about 100k context tokens per call, so batch about 1k rows per call.
- `/api/employees/search` (linkedin_url, or company_url+first+last) charges 1 credit per email found and 0 on a miss. 280 lookups gave 264 emails for 264 credits. 91% were on the company domain, and 94% had verification dates from Jun-Oct 2026. 40% were Microsoft-hosted (60% for bookkeeping and MSP), leaving 155 sendable under his rule.
- Contact Finder returns `email_domain` for free, so MX-filter before paying.
- MillionVerifier on the 155 sendable emails (`mv_check.py`, single API): ok 48%, catch_all 43%, unknown 5%, invalid 5%. Apify waves had ok 57-59% and invalid 6-9%. Ok rate was weakest for insurance (29%) and pest (30%), best for bookkeeping (64%) and cleaning (60%). The MV balance read 44,169 both before and after the run (it may lag). Microsoft-hosted QuickEnrich emails (105) came back ok 89%, catch_all 9%, invalid 3%. Across all 260: ok 64%, catch_all 29%, invalid 4%, better than Apify (57%). From 2026-10-12 Microsoft is allowed, so no MX pre-filter is needed.

**How to apply:** For his local-SMB niches the Maps file replaces Prospeo discovery. Sequence: dedupe vs the sheet, MX-filter out Microsoft domains before paying, Claude screens in batches on his plan (Claude Code headless with ANTHROPIC_API_KEY unset), then QuickEnrich, then MV. Run a 100-domain test before scaling. See [[lead-scrape-2026-niches]], [[apify-lead-actor-mechanics]], [[deliverability-2026-09-25]].

**Decision, 2026-10-08 (later):** QuickEnrich is the lead source for now, pulled through the **web app by Grok Bot** rather than the API ("we wouldn't be using API credits"). Grok exports 80 per niche per night, Sunday to Thursday, into the Drive folder "QuickEnrich drops". Claude does the rest: dedupe, screen, MillionVerifier, sheet, personalization.
- Grok skill: `~/.claude/skills/quickenrich-lead-pulls/SKILL.md`. Grok update: `Agentic Worklfows/agents/grokbot/updates/2026-10-08_quickenrich-lead-pulls.md`, written in the madtom worktree and uncommitted. grok-operator got job 6.
- The pack was NOT rebuilt: the grok-operator source already carried unpacked 2026-10-06 changes, so rebuild on main covering both. build_pack SKILLS doesn't list the new skill yet.
- Still open: which QuickEnrich web plan (WebApp Unlimited $83 or Contact Finder Unlimited $99) allows bulk Contact Finder exports with emails, creating the Drive folder, the supervised first run, and building Claude's intake.
