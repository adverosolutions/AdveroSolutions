---
name: ppc-agencies-personalization-2026-10-10
description: "PPC agencies niche enriched + personalized 2026-10-10 (4,403 lines, three source files + combined), \"I know that you do / Congrats on {specific}\" form, 68% real specifics, cold read for the rest; headless claude -p batch method; catch-all must be preserved"
metadata:
  node_type: memory
  type: project
  originSessionId: 0449f596-4d81-43e5-9db1-d7d9d3e7080f
  modified: 2026-10-10T23:40:09.524Z
---

On 2026-10-10 Lorenzo gave this chat the PPC agencies list only (other chats had cleaning and pest) from `madtom/Leads 2026-10-10/Final three niches 2026-10-10/`.

**Outputs (in place, next to each source):**
- `recent-verification/final_ppc_agencies_output.csv` (3,761) + `final_ppc_agencies_skipped.csv` (563, with skip_reason).
- `old-or-missing-verified/ok-plus-catch-all/final_ppc_agencies_ok_catch_all_output.csv` (347, 176 catch_all) + `..._skipped.csv` (51).
- `fit-review-final-results/final_ppc_agencies_fit_review_output.csv` (295) + `..._skipped.csv` (41).
- Combined: `final-leads/final_ppc_agencies_all_sources_output.csv` (shared final folder for all three niches) (4,403, `source_folder` column first).
- Line: `Hey {first}, I know that you do {x}. Congrats on {specific}. Was wondering if I can run something by you.` Real specific on 3,005 (client results, totals, awards, press, reviews, credentials, years in business); the other 1,398 get a rotating cold read routed by x (Lorenzo's call after review). Reviewer approved after 5 rounds: foreign shops with only a Sheridan/Wilmington agent address, cross-company duplicate people, K/M shorthand, comma'd years, client names, mailboxes at other businesses (check every row whose email domain differs from the site).

**Lorenzo's instruction mid-run:** "Make sure to preserve all catch-all within your output." Never filter on MV result; carry MV columns through unchanged.

**Method that worked (scripts lived in the session scratchpad only):**
- Python fetch of home + about + services page per company (48 threads, ~10 min for 3,685; ~6% dead). For specifics, a deep fetch adds full home text + up to 4 proof pages (case studies, testimonials, awards/press, about, clients): top-of-homepage only gave ~37% specifics.
- `claude -p --model sonnet --tools "" --system-prompt ... --output-format json` on his plan, 13-20 companies per call with page text inline, ~12 workers. One pass for facts + X, a second for the specific (8-rung ladder, evidence quote verified against page text).
- Opus rewrite pass for phrases that fail the style gate (over 14 words, "$220K", "50+", person-name start) rescued 62 of 64 instead of dropping them to generic.
- `--setting-sources ""` on a nested claude was blocked by the old guard hook; plain flags work. A `nohup ... &` runner died when its Bash call ended; use run_in_background.

**Reviewer caught (fix before cap):** one agency under two domains escapes a per-domain cap; group companies by fetched home host + shared non-free mailbox domain + identical page text, then cap 2 and collapse the same person. Substring country matching hit "New Mexico". QuickEnrich first-name field sometimes holds the company name ("Procept Marketing") or the email belongs to another person (dcurran@ for Steve); check name vs email local part.

**Gotchas seen:** QuickEnrich City has junk ("Digital", "Seo", "Ste 302A Over", "Phoenix, Las Vegas") and Delaware/Wyoming registered-agent cities (Lewes, Dover, Sheridan) on foreign shops; prefer the city from the site's own address; ~7% of "US" PPC agencies were foreign (India, UK, Israel, Pakistan...). A site naming an offshore office is not foreign if it also shows a US street address. Off-niche = PPC software, lead sellers, course sellers, publishers; but the fit-review file's own evidence overrides my off-niche call when it shows they sell ad services. The demographic filter must not match "white label" or "black car".

Related: [[lead-scrape-2026-niches]], [[list-builder-maps-quickenrich]], [[personalization-philosophy-2026]], [[feedback-opener-certain-language]].
