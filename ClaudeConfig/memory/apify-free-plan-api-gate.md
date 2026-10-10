---
name: apify-free-plan-api-gate
description: Apify actor code_crafter/leads-finder blocks API runs on the free plan (UI only) and needs a one-time full-permission approval in the console
metadata: 
  node_type: memory
  type: project
  originSessionId: 63f00c1f-8f3b-4309-8328-65421faa6d84
  modified: 2026-08-10T22:05:26.855Z
---

Two separate gates hit while building the Apify lead engine on 2026-08-10, both
invisible until you try to run:

1. **Full-permission approval.** `code_crafter/leads-finder` (actor id
   `IoSHqwTR9YGhzccez`) returns HTTP 403 `full-permission-actor-not-approved`
   until approved once at
   `https://console.apify.com/actors/IoSHqwTR9YGhzccez?approvePermissions=true`.
   Must be done by Lorenzo in the console — it grants account-wide access, and it
   only counts on the account owning the token (ZoMoney /
   lorenzovillarreal@adverosolutions.com). 403s are not billed.
2. **Free-plan API gate.** After approval, an API run "succeeds" but the dataset
   contains a single record: `{"error": "Users on the free Apify plan can run the
   actor through the UI and not via other methods."}` — and still bills the $0.02
   start fee. **The free plan can only run this actor from the Apify web UI.**

**Why:** The whole `scrape-leads-skill` is API-driven, so on the free plan it
cannot work at all regardless of code quality. Requires the ~$39/mo Starter plan
to automate.

**How to apply:** Validate ICP filters by pasting the payload JSON into the actor's
console UI (free plan allows this), export the dataset as JSON, and analyze
locally with `analyze.py`. Only upgrade to Starter once lead quality is proven.
A "SUCCEEDED" Apify run means nothing — always inspect dataset contents for an
`error` key. Related: [[apify-braveleads-actor-unusable]]

**Update 2026-08-17:** account is now on STARTER (\$29/mo); API runs work. The free-plan gate above is historical.
