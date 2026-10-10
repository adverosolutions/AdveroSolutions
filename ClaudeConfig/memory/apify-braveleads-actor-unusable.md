---
name: apify-braveleads-actor-unusable
description: Apify actor braveleads/leads-finder bills $0.05 per refused run and has only 77 US electrical-contractor records — not viable for trade lead gen
metadata: 
  node_type: memory
  type: project
  originSessionId: 63f00c1f-8f3b-4309-8328-65421faa6d84
  modified: 2026-08-10T21:33:53.411Z
---

Tested `braveleads/leads-finder-linkedin-apollo-leads-generator` on 2026-08-10 for
electrical-contractor lead gen. Not viable. Three blockers:

1. **Bills for refused runs.** Rejects with "A run is already in progress for this
   account" even when nothing is running (proved with runs 90s apart over ~6 min),
   and charges the $0.05 start fee each time. 15 runs → only 3 returned data;
   $0.65 of $0.99 spent was pure waste. Also means no parallel sharding.
2. **SIC 1731 ("Electrical Work") pool = 77 leads for the entire US.** The filter
   works correctly (`organizationSIC` confirms), the database is just empty there.
3. **Loosening kills precision.** `industry: Construction` + `owner` → pool of
   43,864 with excellent contact fill (100% email, 100% website, 0 consumer
   domains), but the companies are single-family homebuilders and staffing
   agencies, and titles include software "Product Owner".

Actor input notes: `maxResults` minimum is 100. Location filters are country /
state-code / postal only — no city. `sic_codes` and `industry` AND together.

**Why:** Free-plan Apify credit is only $5/mo, so a $0.05-per-refusal actor drains
it fast with nothing to show.

**How to apply:** For local trades (HVAC/plumbing/electrical/roofing), use Google
Maps actors instead — `compass/crawler-google-places` ($0.004/place, 34M runs,
exact `categoryFilter`, 25 concurrent runs so city-sharding works) or
`lukaskrivka/google-maps-with-contact-details` ($0.005/place, crawls sites for
emails). Working code and raw results in
`Coding/apify-lead-engine/`. Related: [[project_architecture]]
