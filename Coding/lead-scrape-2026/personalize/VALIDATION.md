# Personalization validation — 2026-11-01

The writer and copy self-review ran in the current Codex session. No Claude or
Opus call is required by this implementation. The review was not independent.

112 local tests pass across personalization and the existing upload/slot suites.
Tests cover no-name rendering, proof-page discovery and size limits, wrong quotes
and URLs, changed numbers, spoken amounts, review-count thresholds, unsupported
fallbacks, duplicate company content, historical caps, missing/duplicate ids,
manual fixes, review invalidation and refusal before live access.

Twelve real existing leads were researched with read-only website requests.
Local evidence and full sample records are in
`.tmp/personalization-validation-20261101/` (not committed). These are validation
candidates, not a new send list. Source QA separately checked the intended copy;
normal review retained the historical-company cap. No human approval, Sheets
write, Instantly upload, activation or campaign change was performed.

| Company | Source QA outcome | Evidence or reason |
| --- | --- | --- |
| Grey Search + Strategy | Researched | [Company homepage](https://grey-search.com/) states “People Placed Across 25 States in 2023.” Used coverage only, not the broken zero-valued animated counters. |
| Business Development Partner | Skipped | [Company homepage](https://businessdp.pl/) identifies a Polish address and +48 phone. |
| Cameron Smith & Associates | Researched | [Company homepage](https://csarecruiters.com/) states placements in 43 states and 9 countries. |
| My Elite Clean | Researched | [About page](https://myeliteclean.com/top-rated-house-cleaning-company-in-kansas-city/) states more than 12 years in business. |
| Commercial Cleaning Services | Held | Website fetch failed; no approved cleaning cold-read variant. |
| Elite Commercial Cleaning | Researched | [About page](https://www.elitecommercialcleaning.com/about) states over 13 years serving businesses. |
| Padgett Farmington | Held | Retained [home](https://www.battontax.com) and [about](https://www.battontax.com/about.php) pages did not yield a distinctive attributable achievement; no approved bookkeeping cold-read variant. |
| May & Company | Researched | [Company homepage](https://www.maycpa.com) states “100+ Years” and founded in 1922; rendered “over 100 years,” without inventing an anniversary date. |
| Cain Ellsworth | Researched | [Company homepage](https://cainellsworth.com/) states over 50 years helping closely held businesses. |
| Legacy Media | Cold read | Site unavailable; X grounded in the saved company description. Used an already-approved marketing-agency fallback. |
| MoJo Active | Cold read | [Company homepage](https://www.mojoactive.com) supports SEO and paid media advertising. Did not turn a client's own product count into an agency achievement. |
| Marketing116 | Cold read | Thin site; X grounded in the saved company description. Used an already-approved marketing-agency fallback. |

Representative output:

> Hey Scott, I know that you do executive search for the consumer goods industry. Congrats on making placements in 43 states and 9 countries. Was wondering if I can run something by you.

> Hey Darrin, I know that you do commercial and office cleaning. Congrats on more than 12 years in business. Was wondering if I can run something by you.

> Hey Todd, I know that you do tax preparation and small business accounting. Congrats on over 100 years in business. Was wondering if I can run something by you.

Readiness limits: quote matching and numeric checks do not establish claim
meaning or attribution. Every line still needs human review. Niches without
approved fallback wording remain held when no usable achievement exists. The
scripts stage and verify JSON; Codex supplies extraction and writing within the
session. This is not a scheduled autonomous model service.
