---
name: pest-control-personalization-2026-10-10
description: "Pest control \"I know / Congrats on {specific}\" lines (2026-10-10), 1,331 + 329 + 146 rows in three folders; ~70% real site facts; lessons on specifics, colleagues, segment rule, wrong sites"
metadata:
  node_type: memory
  type: project
  originSessionId: 5fe6d258-b97d-4f9c-b2e6-28420503e8f4
  modified: 2026-10-11T00:48:37.170Z
---

Pest control leads from "Final three niches 2026-10-10" got the new template on 2026-10-10: "Hey {name}, I know that you do {x}. Congrats on {specific}. Was wondering if I can run something by you." ([[feedback-opener-certain-language]]). The outputs are `pest_control_personalized.csv` and `pest_control_not_personalized.csv` in three folders:

| Folder | Personalized / skipped | Note |
|---|---|---|
| recent-verification | 1,331 / 85 | 1,015 real facts |
| old-or-missing-verified/ok-plus-catch-all | 330 / 18 | 218 real facts; 135 of 140 catch-alls kept |
| fit-review-final-results | 148 / 11 | 112 real facts |

About 75% of lines carry a real site fact. The other 464 get a cold read Lorenzo picked (2026-10-10): "all the repeat customers you've built up over the years" or "the reputation you've built with homeowners around town" ("around town" without "homeowners" when the service is business-only). They rotate evenly, and colleagues never share one ([[feedback-opener-certain-language]]). The reviewer approved on round 3; rounds 1 and 2 were rejected for content (see lessons). Nothing was pushed to Instantly. The earlier template-mode version (Y "you must") was replaced. Same day as [[ppc-agencies-personalization-2026-10-10]]; the segment rule comes from [[fit-review-2026-10-10]] (pest-first only).

How the specifics were built:
- **Fetch:** deep fetch of the home page plus up to 4 proof pages (about, reviews, awards); a second pass reads 6 more pages.
- **Extract:** headless `claude -p --model sonnet` in chunks of 15 using the 8-rung ladder prompt.
- **Check by script:** the quote must be on the page; numbers must be in the quote; years = 2026 minus the founding year. The checker expands shorthand (15k, five-star, ★★★★★, decades).
- **Read every line by hand.**

A second deep fetch added only about 25 companies. A regex candidate re-pass over the fallback sites added 88 more rows (see lessons), so run that scan before accepting a fallback.

Lessons for the next niche:
- **Rating vs. count of five-star reviews:** "800+ 5-Star Reviews" is a count, not a rating. Write "over 800 five-star reviews", never "the 5-star rating across over 800 reviews". This was the most common extract error, about 15 per 1,800.
- **Other extract errors:**
  - A move year was read as a founding year ("In 2015 I moved to Pahrump").
  - A copyright year was read as a founding year.
  - An owner's personal stat was given to a different colleague (fixed with lead_pick).
  - Association charter membership was taken as an achievement.
  - Merger/acquired-by lines are dropped (company absorbed).
- **Colleagues:** each contact takes the best fact nobody at the company has yet. With none left, the second contact gets a second service X from the site (a claude -p pass with the quote checked). When the site has nothing, the two lines differ only by name.
- **Wrong site:** when the data's website is a different business than the email domain, re-point to the email domain's site. 18 leads were re-pointed this round. Skip leads whose email is at another business (H&R Block, Ecolab).
- **Years rule (main session decision, 2026-10-10):** "N years in business" counts only from a founding/since year, "in business for N years", "serving <area> for N years", a sentence whose subject is the company or "we", or a standalone header badge. It never counts from team/experts/technicians, "backed by", combined experience, a person's career or bio, or template boilerplate. Loose years were the round-2 reject.
- **Fallbacks need a regex re-pass:** the first extract missed "since 2004"-type facts on many fallback sites. A deterministic candidate scan (years, review counts, award names, credentials) plus a claude -p pick turned 88 fallback rows into real facts.
- **Staff, fleet and location counts are rung 8,** never "total served"; rank them below years and ratings.
- **Acquired companies:** when the email domain redirects to an acquirer (Viking, Cedar, Burns, Invader), give the general line and build X from the company name, not the acquirer's site.
- **Compressed page text:** about 13 sites were saved as raw gzip bytes and never read. Check for non-printable text and refetch with decoding.
- **Company cap refill:** a cap skip must name colleagues who are actually personalized. Refill the cap when a counted colleague is skipped later.
- **From the earlier round:** a deceased contact (memorial banner) is skipped. A company word in First Name is blanked only when Last Name is also a company word. Pin approved lines before late fixes.

**Why:** these were the defects found at volume in this batch and its review.
**How to apply:** run these checks before sending any "Congrats on {specific}" batch to review.
