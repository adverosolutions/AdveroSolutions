---
name: apify-lead-actor-mechanics
description: Hard-won mechanics of code_crafter/leads-finder — deterministic results (no offset), shard by US state, billed per lead returned, killed local runs still bill, size gate leaks
metadata:
  type: project
---

Verified on real runs, Aug–Sep 2026:

- **No offset/page/sort.** Identical filters return byte-identical leads (100% overlap).
  Parallel same-filter runs pay N× for one list. Shard on `contact_location` by US
  state (`"texas, us"` etc.) — different states returned 0% overlap.
- **Billing:** $0.02/run start + $0.002/lead *returned*. Under-delivery is free, so
  generous per-shard quotas are free insurance; only over-delivery costs.
- **Cancelling the local process does NOT abort Apify runs** — 21 orphaned shards
  billed $5.49 once. Abort remote runs via API, or recover datasets (reads are free).
- `email_status: validated` ≠ guaranteed email; coalesce `email` → `personal_email`
  (business wins) and reachability hits ~99%.
- `size` bands leak (2,700-staff Servpro passed a 21-50 gate); enforce a
  `company_size` ceiling at export.
- `company_keywords` is a loose OR; broad industries (law, events, facilities)
  contaminate — validate with a $0.22 nationwide 100-lead smoke before production.
- Verified-clean rates (MillionVerifier): law 72%, recruiting 60%, vet 60%, dental 53%.
  Pattern signals (name-in-email, domain match) under-predict catch_all — trust
  verification, not heuristics.

- **`seniority_level` is the biggest hidden supply lever.** `owner/founder/partner` only
  matches contacts literally titled Owner; founders titled CEO/President live under
  `c_suite`. For cleaning, c_suite unlocked ~+350 clean after owners were exhausted.
- **`email_status` does NOT partition contacts.** A `not_validated/unknown` run returned
  ~85% the same people as the `validated` run (paid dupes). Don't use it as a second pool.
- Nationwide top-N is the actor's *best* records; quality and reachability fall at state
  depth (cleaning smoke 64% clean / 100% reachable -> production 44% / 57%).

Related: [[lead-scrape-2026-niches]]
