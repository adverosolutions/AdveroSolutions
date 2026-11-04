---
name: fit-review-2026-10-10
description: "Website fit check of the 3,256 fit-review leads (cleaning, pest, PPC), 2026-10-10; results in final-results/, method and audited accuracy, pest-rule lesson"
metadata:
  node_type: memory
  type: project
  originSessionId: 807c9103-f2f5-4a57-89ea-3b0d1d0ebf3f
  modified: 2026-10-10T19:32:41.502Z
---

On 2026-10-10 Lorenzo asked to vet every company in `madtom/Leads 2026-10-10/Final three niches 2026-10-10/fit-review/` (3 CSVs, 3,256 contacts, 2,766 company/niche pairs) as a real operator in its niche, output as "final results" for another agent to verify and enrich.

**Output:** `fit-review-final-results/` next to fit-review, three CSVs only: cleaning 613 contacts/540 cos, pest 159/135, PPC 336/277 (1,108 total). Audit trail (every row, reason, Segment, In Final List) + README in `audit/fit-review-check/`. CSVs are gitignored, nothing committed.

**Segment rule (Lorenzo, 2026-10-10), who we target:** cleaning = janitorial/commercial cleaners only (no pressure washing, carpet, window specialists); pest = pest-first companies only (no lawn/landscaping + pest, no multi-service with a pest line); PPC = marketing/PPC agencies + Amazon ad agencies (no web/dev shops with PPC on the side). Apply this to future lists in these niches.

**Method that worked:** requests fetch (homepage + 2 subpages) → `claude -p --model sonnet --tools ""` batch judge on his plan (25/batch, 8 jobs, ~15 min for 2,766) → web-search pass with `--tools WebSearch,WebFetch` for dead/thin/unclear (6/batch) → headless Chrome `--dump-dom` for blocked/JS sites (needs per-process user-data-dir and a hard timeout; it hangs otherwise). Scripts lived in session scratchpad only.

**Audited accuracy:** reviewer on 45 random verdicts: cleaning 15/15, PPC 15/15, pest 12/15. Pest misses were lawn/multi-service companies; fixed with pest-page-preferring fetch + rules (side-service pest counts; lawn needs perimeter/mosquito/tick/flea/termite; turf insects alone don't). Re-audit 23/25, no false fits.

**Why:** LinkedIn profiles were not crawled (logged-out blocks; his account is used for [[linkedin-outreach-channel]] and could get restricted); LinkedIn-derived fields and search snippets were used instead.

**How to apply:** reuse this pipeline for future QuickEnrich drops ([[list-builder-maps-quickenrich]], [[quickenrich-lead-pulls]]); give pest control the stricter lawn rule from the start.
