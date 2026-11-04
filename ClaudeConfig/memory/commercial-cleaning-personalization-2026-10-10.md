---
name: commercial-cleaning-personalization-2026-10-10
description: "Commercial cleaning \"I know / Congrats on {specific}\" lines (2026-10-10), 1,120 + 307 + 544 rows in three folders; 63% real site facts, rest cold reads; lessons on franchise facts, team tenure, redirects, experience wording"
metadata:
  node_type: memory
  type: project
  originSessionId: 5ca8ef22-83f5-431d-a59b-7c76e31b629a
  modified: 2026-10-11T01:18:34.903Z
---

Commercial cleaning leads from "Final three niches 2026-10-10" got the new template on 2026-10-10 ([[feedback-opener-certain-language]]). Outputs are `commercial_cleaning_FINAL_OUTPUT.csv` + `commercial_cleaning_FINAL_OUTPUT_skipped.csv` (skip_reason + skip_detail on every row) in three folders:

| Folder | Output / skipped | Note |
|---|---|---|
| recent-verification | 1,120 / 744 | 386 specialty-only segment skips, 146 already contacted |
| old-or-missing-verified/ok-plus-catch-all | 307 / 69 | 125 of 153 catch-alls kept |
| fit-review-final-results | 544 / 69 | |

1,232 of 1,971 lines carry a real site fact. The other 739 get a rotating cold read ([[feedback-cold-read-not-skip]]), including 90 dead-site leads that were first skipped as unconfirmed. A web lookup pilot (BBB, Angi, Expertise.com) found a fact for 2 of 16 fallback sites, so it was not scaled. Nothing was pushed to Instantly. The work files and tools (fetch3.py, spec_check.py, final2.py, qa.py) were in the session scratchpad, so they are not kept. Three independent review rounds were run: 48/60, 52/59, then 20/24, with every flagged row fixed. Same day as [[pest-control-personalization-2026-10-10]] and [[ppc-agencies-personalization-2026-10-10]]. The segment rule (specialty-only cleaners such as pressure washing, carpet and windows are left out; residential + commercial is allowed) comes from [[fit-review-2026-10-10]].

Lessons the reviewers caught, for the next cleaning or franchise-heavy niche:
- **Franchise owners get only local facts.** A brand's founding year, awards or size never go on a franchisee (Anago, Jan-Pro, City Wide, Corporate Cleaning Group, System4, Office Pride). Without a local fact, use a cold read.
- **Team tenure is not company age.** "Our management team has nearly 40 years" and "Owner X and her team, with over 25 years" are not "N years in business".
- **A bare "N years of experience" with no founding year** is worded "over N years of experience", never "in business". A stale badge ("23 Years of Experience") loses to a founding year on the same site ("since 2002" = 24 years).
- **Record mismatch:** the site redirects to another company and the email is at that company (RJS → Clean Team, GDI on bpair.com). Skip it. A rebrand where the email matches the new domain (Marsden, 4M, Legacy MN) is kept.
- **Not achievements:** staff training certificates (IICRC tech, GBAC-trained, CHESP), service-area coverage, Cleaning for a Reason sign-ups, and a headline award that belonged to a partner (a landscaper's award on a cleaner's news page).
- **X stitched from menu items** ("data centers" for a relocation firm) means the company is off-niche, or the X needs a hand rewrite.

**Why:** these were the defects found across three review rounds of this batch.
**How to apply:** check these before sending any "Congrats on {specific}" batch to review.
