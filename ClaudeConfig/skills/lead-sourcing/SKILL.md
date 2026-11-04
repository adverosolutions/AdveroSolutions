---
name: lead-sourcing
description: "Find, fit-check, verify and stage Advero leads under current Lead Gen ownership, suppression and source rules. Use for scraping, lead counts, verification or import planning."
---

# Lead sourcing

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- Lead Gen Manager owns lead sourcing and all loads. Its November 4 handoffs absorb QuickEnrich, Maps and Sales Nav duties. Older notes saying COO or Claude owns loading are superseded.
- QuickEnrich is browser-only, never its API. Current pool lanes include pest control, commercial cleaning and PPC, with residential and adjacent niches separately tagged. Keep owner-title, identity, country, fit and company-dedupe checks.
- Use existing MillionVerifier credits only, preserve valid and catch-all outcomes, and skip recently verified QuickEnrich rows under the current source procedure. Never buy credits as part of a pull.
- Completed no-reply leads can be exported with all fields and a 90-day recontact date to free plan capacity, with count verification and suppression checks. This is a separate process from warm nurture and opt-out handling.
- Current Maps crawl is on a 72-hour hold until at least November 5 at 21:00 CT; the staged probe and stop records still control. Never restart from a historical nightly schedule. No campaigns resume through a sourcing task.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)
- [quickenrich-bot_to_lead-gen-manager_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/quickenrich-bot_to_lead-gen-manager_20261104.md)
- [maps-bot_to_lead-gen-manager_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/maps-bot_to_lead-gen-manager_20261104.md)
- [quickenrich-lead-pulls.md](../../grok-source/2026-11-04/first-export/advero/skills/quickenrich-lead-pulls.md)
- [lead-gen-manager.md](../../grok-source/2026-11-04/third-export/routine_exports/lead-gen-manager.md)


Every lead must be verified clean before any money goes into enrichment or personalization,
and every lead must pass suppression before it can be staged for a campaign.

## Who does what (decided 2026-09-25)

- **Grok Bot** only reports lead counts and run status. It never starts a scrape, never
  spends on Apify, MillionVerifier or Perplexity, never uploads leads, and never edits or
  deletes lead rows. Lorenzo does those (or, later, a connector tool built for it, used only
  when Opus decides to).
- **Claude Opus 5.5** decides ICP fit, which niche to source next and whether a sample is
  good enough to pay for the rest.
- **Lorenzo** approves spend (Apify, MillionVerifier, Perplexity) and any upload.

## Current niches (2026-09-01 decision)

| Niche | Status | Verified clean | Notes |
|---|---|---|---|
| Boutique perm recruiting | done, do not re-scrape | 1,437 | the weekly list factory does not feed recruiting (retires at 1,000 sends with zero positives); feeding it is Lorenzo's call |
| Commercial cleaning | done | 1,222 | needed the `c_suite` seniority pool to pass 876 |
| Bookkeeping and tax firms | done | 1,394 | 65% clean rate |

Total 4,053 verified clean; 6,466 sendable counting catch-all and unknown ("risky", kept in a
separate file). Target was about 1,250 clean per niche. Law (PI, immigration) and dental were
scraped in August, then dropped; do not re-scrape them. Vet and corporate events were only
$0.22 availability tests.

Lead sheet: `1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw`, tab `Leads`, rows in send order
(25 clean, then 5 catch-all, repeating; surplus catch-all then unknown at the tail).
The service account cannot create sheets (zero Drive quota): Lorenzo creates a sheet and
shares it with the service account.

## Mailbox provider and risky rows (Lorenzo, 2026-09-29)

- Only Google, "other" (GoDaddy, Rackspace, self-hosted) and Zoho mailboxes go to Instantly.
  The sending inboxes do not land in Microsoft; free Yahoo stays out. Provider comes from an
  MX lookup (`Coding/lead-scrape-2026/personalize/esp.py`, cache `output/mx_cache.json`);
  `instantly_push.py` ALLOWED_ESP enforces it on every push and `daily_pick.py --esp`
  defaults to the same set.
- Lorenzo said Microsoft leads may be sent from Monday 2026-10-12. ALLOWED_ESP and the
  `--esp` default still exclude Microsoft until someone changes them on or after that date.
- Risky rows (catch-all and unknown) are allowed for recruiting, bookkeeping and cleaning
  because supply is short. Lorenzo pauses a campaign himself if bounces climb.
- No more than 2 contacts per company (name and city) across every pushed day file
  (`personalize/tools/cap.py`).
- Stock after the 2026-09-29/30 push run (about 4,200 leads pushed): recruiting and cleaning
  have no Google/other/Zoho rows left; what remains is Microsoft or Yahoo. Bookkeeping still
  had stock.

## Apify: code_crafter/leads-finder (the one that works)

Account is on Starter ($29/mo, since 2026-08-17). Cycle resets on the 9th. Lorenzo raised
the cap to $45 once on 2026-09-01; budget is usually the binding constraint.

- **No offset, page or sort.** Identical filters return byte-identical leads. Parallel runs
  with the same filters pay N times for one list. Shard by `contact_location` per US state
  (`"texas, us"`); different states overlap 0%.
- **Billing:** $0.02 per run start plus $0.002 per lead returned. Under-delivery is free, so
  a generous per-shard quota costs nothing extra.
- **Killing the local script does not stop Apify runs.** 21 orphaned shards once billed
  $5.49. Abort remote runs through the API, or recover their datasets (reads are free).
- A run marked SUCCEEDED can hold one record that is an error. Always inspect the dataset.
- `seniority_level`: `owner/founder/partner` only matches people titled Owner. CEO and
  President founders sit under `c_suite`. That pool added about 350 clean cleaners.
- `email_status` does not partition people: a `not_validated` run returned about 85% the
  same contacts as `validated` (paid duplicates).
- `email_status: validated` is not a guarantee. Coalesce `email` then `personal_email`
  (business wins).
- `size` bands leak (a 2,700-staff Servpro passed a 21-50 filter). Enforce a `company_size`
  ceiling at export. The actor's company size is unreliable anyway.
- `company_keywords` is a loose OR. Broad industries (law, events, facilities) pull junk.
  Run a $0.22 nationwide 100-lead smoke test before any production pull.
- Cleaning needs `company_not_industry: consumer services` plus restoration exclusions
  (Servpro leaked badly).
- Quality falls with depth: the nationwide top N is the actor's best; cleaning went from 64%
  clean in the smoke to 44% in production.
- Actor id `IoSHqwTR9YGhzccez` needs a one-time full-permission approval in the Apify
  console by the account owner (403 until then, not billed).

Verified-clean rates seen (MillionVerifier): law 72%, recruiting 60%, vet 60%, dental 53%,
bookkeeping 65%, cleaning 44-46%.

## Actors that do not work

- **braveleads/leads-finder-linkedin-apollo-leads-generator:** charges $0.05 for runs it
  refuses ("a run is already in progress" when none is), so no sharding; only 77 US
  electrical-contractor records under SIC 1731; loosening to Construction pulls homebuilders,
  staffing firms and software "Product Owners". Do not use.
- For local trades (HVAC, plumbing, electrical, roofing) use Google Maps actors instead:
  `compass/crawler-google-places` ($0.004/place, exact `categoryFilter`, 25 concurrent runs,
  shard by city) or `lukaskrivka/google-maps-with-contact-details` ($0.005/place, crawls
  sites for emails).

## Verification

- MillionVerifier is the verifier. Trust verification over heuristics: name-in-email and
  domain-match patterns under-predict catch-alls.
- Catch-all domains accept any address, so a guessed address there is not confirmed. Keep
  them separate as "risky"; about a quarter of checks land here. Instantly imports them as
  `accept_all` anyway.
- Free mailbox providers (gmail, yahoo) on an owner lead are suspect: tag low.

## Owner email pipeline (for scraped businesses without a contact)

Cheapest gates first, so money is never spent on a dead lead:

1. Free: skip duplicates, rows missing name/city/state, off-category rows, no website or
   domain, and domains with no MX record.
2. Free: scrape the site for emails, graded high, medium, low or generic.
3. About $0.005: one Perplexity call for owner name plus research. Unknown owner: stop.
4. About $0.0006-0.003: 3-5 owner-name patterns (`first@`, `first.last@`, `flast@`,
   `firstlast@`), bulk-verified.
5. Free: pick the best address and a confidence tier. HIGH = scraped owner match or verified
   non-catch-all pattern. MEDIUM = catch-all or partial name match. LOW = generic inbox.
   REJECT = nothing deliverable.

Target cost about $0.013 per attempted lead, $0.018 per success. Perplexity sometimes
"corrects" a misspelled company into a different real company; the wrong-company guard has
to catch it. Cloudflare-walled sites fall through to patterns.

## Google Maps mass scraping (local businesses)

The free Playwright scraper covers about 450 locations (200 metros plus neighborhoods) at
up to 100 results per search, 4 browsers, resumable after a crash. Built for pest control,
garage door, landscaping and pool service. Learned: use `domcontentloaded`, not
`networkidle`; prefix phone numbers with `'` in Sheets; write to a sheet Lorenzo created and
shared. On CAPTCHAs, drop to 2-3 browsers; if they persist, restart after 30 minutes.

For med spas, a separate two-part cleaner turns an Instant Data Scraper export into a
Hunter or AnyMail list (drops under 25 reviews, under 4.0 rating, chains like Ideal Image
and LaserAway, shared booking domains) and then into an Instantly upload file (personal
emails only, role inboxes dropped).

## Location and data quality

- On Apify leads, `state` and `city` are the contact's LinkedIn location, not the company's.
  They differ for 25% of recruiting, 34% of cleaning, 16% of bookkeeping leads. Use
  `company_city` and `company_state` for anything location-based.
- Live websites in a random sample: bookkeeping about 81%, recruiting 76%, cleaning 65%.
- Off-niche rows leak (cleaning sample: a furniture installer, a sign company). Foreign
  firms slip through when `company_state` is blank.

## Loading leads and avoiding re-contact

- Before any upload, check every address against the Instantly workspace: all leads,
  bounces, unsubscribes, the blocklist, hostile replies, clients and our own domains. A
  domain already in a campaign is skipped before anything is paid for.
- Previously contacted leads wait before a new offer: the default is 2 weeks, 2-3 weeks is
  the suggested cooling period for cold outreach, and 4-6 weeks is worth considering for
  leads who never responded. Leads who replied get a human look before re-engagement.
- `POST /leads/list` silently ignores an unknown filter and returns everything; read
  statuses off a full pull instead.
- Uploads to live campaigns follow `cold-campaigns`; never touch a campaign's `email_list`.
- A client's domain goes into suppression the day they sign.

## AnyMail Finder (or any round-trip through an outside tool)

Never paste results back into a sheet by row position. A reordered or skipped row once put
one person's email on 100+ companies. Export with a unique key (phone or row id), merge back
on that key, check row counts match, spot-check 10-20 rows. Red flags: one email on 10+
companies, a Fortune 500 executive's address on a local business, email domain not matching
the website.

## Legacy (contractor era, 2025-early 2026)

The CRM import rule "industry must be HVAC, Roofing, Plumbing or Electrical", the
Yelp-plus-AnyMail discovery pipeline and the Discovery Staging sheet belong to the old
contractor pipeline. The 2026 niches do not use them.

## Gaps

- Weekly list factory runs are blocked on a cost decision (see `deliverability-and-inboxes`).
- The list factory has no Instantly upload method yet.
- No paid email finder account exists (the finder stage only prices what one would cost).
- The 2026 lead sheet's remaining uncontacted stock per niche is not tracked here.

## Sources (for maintainers)

- memory `lead-scrape-2026-niches.md` (2026-09-01/02): niches, counts, sheet id
- memory `apify-lead-actor-mechanics.md` (Aug-Sep 2026): actor mechanics
- memory `apify-braveleads-actor-unusable.md` (2026-08-10), `apify-free-plan-api-gate.md` (2026-08-10, Starter update 08-17)
- memory `cold-read-research-2026.md` (2026-09-02): location mismatch, dead sites
- `Agentic Worklfows/directives/USER/discover_and_enrich_leads.md`: owner pipeline and tiers
- `Agentic Worklfows/directives/USER/mass_scrape_leads.md`, `discover_leads.md`, `add_leads.md`: scraper, legacy import
- `Agentic Worklfows/directives/USER/separate_contacted_leads.md`, `prevent_anymail_data_corruption.md`
- `Agentic Worklfows/runbooks/list_factory.md` (2026-09-22): suppression, recruiting disabled
- `Agentic Worklfows/config/instantly_api_contract.md`: leads/list filter trap
- `Coding/med-spa-cold-email/README.md` (2026-06-24): med-spa list cleaner
- `Coding/lead-scrape-2026/` (runner, niches/*.json, output/FINAL/)
