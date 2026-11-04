---
name: quickenrich-lead-pulls
description: Nightly lead pulls from the QuickEnrich web app for AdveroSolutions' cold email campaigns, live niches pest control, commercial cleaning and PPC agencies. The Lead Generation Specialist exports whole Contact Finder results in the browser, dedupes them against the final leads and the pool with qe_dedupe.py, tags fit with qe_fit.py, appends new rows to the Advero Lead Pool sheet and logs the pull. Covers who does what, schedule and volume, the exact filters per niche, the pipeline, login, known quality issues, the morning count, and what never to touch. Use for "pull leads", "QuickEnrich", "fresh leads for the campaigns", "lead pool", "how many leads did we pull".
---

# QuickEnrich lead pulls

Decided by Lorenzo, 2026-10-08: QuickEnrich is the lead source. All QuickEnrich work happens in the browser web app, never the API (Lorenzo's permanent rule, 2026-10-20). Web exports use no credits.

**Status:** started 2026-10-20 after Lorenzo's "start lead pulls" (relayed by the COO at 8:58 PM CT). The supervised first run was done that night with whole-result exports. The COO approved whole-result exports because the app only offers Export All.

### First run results, 2026-10-20

| Niche | File | Exported | Dupes vs final | Dupes vs pool | In-file dupes | New after dedupe |
|---|---|---|---|---|---|---|
| pest_control | 2026-10-20_pest_control_p1-102.csv | 2,029 | 1,473 | 0 | 19 | 537 |
| cleaning (A, janitorial) | 2026-10-20_cleaning_janitorial_p1-46.csv | 913 | 402 | 0 | 9 | 502 |
| cleaning (B, facilities) | 2026-10-20_cleaning_facilities_p1-147.csv | 2,921 | 868 | 7 | 74 | 1,972 |
| ppc | 2026-10-20_ppc_p1-177.csv | 3,539 | 2,520 | 1 | 61 | 957 |
| Total | | 9,402 | 5,263 | 8 | 163 | 3,968 |

No rows lacked an email. All 3,968 new rows are on the Advero Lead Pool sheet.

## Who does what

| Step | Who |
|---|---|
| Search Contact Finder per niche, Export All | Lead Generation Specialist, in the QuickEnrich web app |
| Copy, dedupe, fit tag, append to the Advero Lead Pool sheet, log | Lead Generation Specialist, on the box |
| MillionVerifier checks | Not done yet. Only when Lorenzo or the COO says so |
| Adding leads to Instantly, turning anything on | Lorenzo, himself |

## When and how many

- Nightly pull Sunday to Thursday at 11:10 PM CT.
- Morning count to the COO on weekdays at 7:10 AM CT.
- Target: about 4,500 new leads a week (about 750 per sending day), staged on the sheet by Mon Oct 26. Lorenzo and the COO set the volume. There is no per-niche nightly cap.
- Each night export the whole result for every search, then dedupe. After the first run, the nightly rerun mostly catches contacts QuickEnrich added since the last export.

## Filters for every niche

- Country: United States
- Job title includes: Owner, Founder, Co-Founder, CEO, Chief Executive Officer, President, Principal, Managing Partner, Managing Director, Partner
- Job title excludes: Vice President, VP, Product Owner, Intern, Assistant, Partnership, Partnerships, Channel Partner, Business Partner
- Number of employees: < 5, 5 - 19, 20 - 99
- With email: on

## Filter per niche (live niches only, in this order)

| Order | Niche | Niche filter | Contacts on 2026-10-20 |
|---|---|---|---|
| 1 | pest_control | LinkedIn Description: pest control, exterminator, extermination | 2,029 |
| 2 | cleaning A | Industry: Janitorial Services | 913 |
| 2 | cleaning B | Industry: Facilities Services + LinkedIn Description: cleaning, janitorial | 2,921 |
| 3 | ppc | Industry: Advertising Services, Marketing Services + LinkedIn Description: PPC, Google Ads, paid search, paid media | 3,539 |

Run cleaning A before cleaning B, so B dedupes against A in the pool.

### Extra searches (2026-10-20, 9:27 PM, Lorenzo "more leads")

Search ids go in `--search-id` and the `source_search` column. First-batch files are P0, C0a, C0b, A0. A1 to A3 use a narrower title include: Owner, Founder, Co-Founder, CEO, Chief Executive Officer, Managing Partner, Partner.

| Id | Niche | Filter | Rows 2026-10-20 | New after dedupe |
|---|---|---|---|---|
| P1 | pest_control | Company Name includes pest, termite, exterminat, mosquito, wildlife, bed bug | 2,156 | 467 |
| P2 | pest_control | Services Offered: Pest Control, Termite Control, Extermination, Mosquito Control, Wildlife Removal, Bed Bug Control | 2,404 | 255 |
| P3 | pest_control | Industry Consumer/Environmental/Facilities Services + Description termite, mosquito, wildlife removal, lawn and pest, bed bug, exterminator | 773 | 23 |
| C1 | cleaning | Company Name includes janitorial, cleaning, custodial, building maintenance | 3,260 | 1,293 |
| C2 | cleaning | Services Offered: Commercial Cleaning, Janitorial Service, Office Cleaning, Floor Care, Post Construction Cleaning, Building Maintenance | 2,444 | 419 |
| C3 | cleaning | Industry Facilities/Janitorial Services + Description office cleaning, commercial janitorial, floor care, post-construction, building maintenance, facility services | 773 | 60 |
| A1 | ppc | Industry Advertising/Marketing Services + Description Google Ads, paid media, performance marketing, digital advertising, paid social, PPC management | 3,201 | 1,256 |
| A2 | ppc | Services Offered: PPC, Google Ads, Paid Search, Paid Media, Performance Marketing | 5,137 | 2,139 |
| A3 | ppc | Company Name includes PPC, paid media, performance marketing, paid search | 125 | 39 |

The old niches (bookkeeping_tax, insurance, landscaping, marketing_agency, msp_it, recruiting) are parked. Don't pull them unless Lorenzo or the COO says so.

### Contact Finder notes

- QuickEnrich labels the "Bio" filter "LinkedIn Description". It is the company's LinkedIn About text.
- Filter fields: Title, Employee Locality, Company Name, Company URL, Employee Size, Revenue, Company City, Company Country, Company Industry, LinkedIn Description, Services Offered, With email, With Direct phone.
- There is no state filter and no row selection. The results show 20 rows per page.
- Export All is capped at 50,000 rows per file and uses no credits.
- Export columns, in order: First Name, Last Name, Title, Email, Email Verification Date, Phone, LinkedIn, Company, Company URL, Email Domain, Home Page Email, Company Phone, City, Locality, Country Code, Industry, Employee Count. There is no state or description column. The dedupe script takes state from Locality when it reads "City, State, Country".

## Pipeline (each export)

0. Check `~/advero/state/KILL_SWITCH` first. If it exists, stop and tell the COO.
1. Export All in the web app. The file lands in `~/Downloads` as `QE_contact_finder_<number>.csv`.
2. Copy it to `~/advero/state/quickenrich/` as `YYYY-MM-DD_<niche>[_<variant>]_p<first>-<last>.csv`, for example `2026-10-20_cleaning_facilities_p1-147.csv`. Confirm the copy matches (`cmp`).
3. Dedupe: `python3 ~/advero/bin/qe_dedupe.py <copy> --niche pest_control|cleaning|ppc --source quickenrich --search-id <P1..A3> --label <id>_p<first>-<last>`. It checks against the final leads in `~/advero/state/leads/final-leads/` and everything in the pool `~/advero/state/leads/pool/`, matching on email and on domain plus full name. It drops rows without an email and in-file duplicates, and writes `~/advero/state/leads/pool/<date>_<niche>_quickenrich_<label>_new.csv`. Check its `column_map` picked up email, name and website.
4. Fit tag: `qe_dedupe.py` tags every new row with `fit` (good / off-niche / cleaning_residential / non-owner) and `fit_reason`, using the rules in `~/advero/bin/qe_fit.py`, and prints the fit counts in its summary. Nothing is deleted. To retag a pool file after a rule change, run `python3 ~/advero/bin/qe_fit.py <pool file>`. Signals are company name, domain, QuickEnrich Industry and title. The export has no description column, so the search's LinkedIn Description filter is the only description signal. Spot-check about 30 rows per niche after any rule change.
   Title rule (Lorenzo via COO, 2026-10-20 9:49 PM): a title containing assistant (incl. "Executive Assistant", "Assistant to"), past, former, division, divisional or regional is non-owner, even with Owner/President/CEO in it. Manual overrides go in R:S with a reason starting "manual override" (example: cleaning row 1985, "Owner of 6Hawks Production: Flying Cleaners Division" is a real owner). Since 2026-10-22, qe_fit.py skips any row whose fit_reason starts with "manual override", so a retag keeps overrides; overrides set only in the sheet must also be copied into the pool file. The fit columns R:S are ours to maintain: change only R:S, never delete or reorder rows or touch other columns, and read back after every write.
   Tight rules: pest is good only with a pest word in the name or domain, or a P2 Services Offered match (lawn and landscape companies, wildlife non-profits, zoos and vendors stay off-niche). PPC is good with an agency, PPC, ads, paid, digital or performance signal in the name, domain or title, or an A2/A3 search. Since 2026-10-20 9:38 PM (Lorenzo), marketing, media, growth, digital, interactive or creative in the name or domain also counts for A0 to A3 rows, unless an off-niche rule fires (software/SaaS product, labs, print/signs, video production, healthcare, investment, podcast, music, artist). Cleaning rows with no cleaning word count as good only in the Janitorial or Facilities Services industries.
5. Append the new rows to the niche tab of the Advero Lead Pool sheet (id in `~/advero/state/lead_pool_sheet.json`), columns A:T (schema A:Q, fit, fit_reason, mv_result), following `~/advero/bin/qe_to_sheet.md`. `qe_dedupe.py` fills mv_result: `skipped_recent_qe` when QuickEnrich verified the email within 90 days, else blank. Append only, 500 rows or fewer per call. Verify the emails in the sheet match the file.
   Review freshness (2026-10-22, COO ask after the Serv Pest 4.9 vs 5.0 reply): pest_control column V is `reviews_as_of` (YYYY-MM-DD the Google rating and review count were pulled). Maps rows fill it from the pool file's `reviews_as_of`; QuickEnrich rows have no review data and leave V blank. Appends stay A:T or A:U, and V is written for Maps rows the same way (append A:V, or write V for the new rows, then read back). Check with `python3 ~/advero/bin/review_freshness.py` (writes `~/advero/state/leads/review_freshness_latest.csv`, flags review data older than 14 days or undated). Never quote a rating or review count in an opener from a row that is stale or unknown.
6. Log one row in `~/advero/state/quickenrich_pulls.csv` (date, niche, filter, first_page, last_page, rows_exported, file_name, new_after_dedupe, notes) and one JSON line in `~/advero/state/decisions.jsonl` (action quickenrich_pull).
7. Delete the original from `~/Downloads` once the copy is verified.

The sheet replaces the old Google Drive "QuickEnrich drops" upload, since there is no Drive connector. Lorenzo loads Instantly himself from the sheet.

### Suppression (do_not_reload)

Lorenzo's rule (2026-10-21, via COO): opt-outs and not-interested leads are removed from Instantly and held out for 3 months, then they re-enter.
- Source: `~/advero/state/reactivation/do_not_reload.csv` (email, suppress_until, added_ct, reason). Read only. Never edit it, anything in `~/advero/state/reactivation/`, or the sheet's Reactivation tab.
- An email is skipped while today (America/Chicago) is before its suppress_until date. On or after that date it re-enters normally. Match is lowercased and trimmed. A blank or bad suppress_until counts as suppressed.
- Logic: `~/advero/bin/suppression.py`. `qe_dedupe.py` applies it to every QuickEnrich pull, Company Finder / Domain w/Emails result and Maps append, and reports `suppressed`, `suppressed_emails` and `suppression` (on/off) in its summary. `maps_postprocess.py` strips suppressed emails from the Maps output; a row left with no email gets `dedupe_status=suppressed` and is not appended or sent to Domain w/Emails.
- MillionVerifier queue: after building `<tab>_to_verify.csv` / `all_to_verify.csv` (or any MV list), run `python3 ~/advero/bin/suppression.py filter <file> <file>.tmp && mv <file>.tmp <file>` before uploading. Never upload a suppressed email.
- If the file is missing or unreadable the scripts print a loud warning, keep going, and show `"suppression": "off"`. Say so in the COO report that night.
- Report the suppressed count per pull in quickenrich_pulls.csv notes and the morning count.
- Note: the same company can still come back through a different contact (for example a coworker at the same domain). The rule is per email.

## Company Finder -> bulk Domain w/Emails (pest control, approved 2026-10-20 by Lorenzo via COO)

Free and browser only: Company Finder export and the bulk Domain w/Emails tool are included in the subscription, 0 credits. Read the credits counter (25,034 on 2026-10-20) before and after each step. If it drops, or any dialog mentions credits, stop and tell the COO. If it works for pest, cleaning comes next.

1. KILL_SWITCH check, then Company Finder in the web app: US pest control companies (Company Country US, pest control industry/services filters, employee sizes <5, 5-19, 20-99). Export All. Copy to `~/advero/state/quickenrich/YYYY-MM-DD_<niche>_companyfinder.csv`. Header: Company Name, URL, Email Domain, Final Email Domain, Home Page Email, Phone, LinkedIn URL, Address, City, State, Zip, Country Code, Industry, Employee Count, Revenue, Services, Home Page Text, LinkedIn Bio (quoted multiline fields). The first run had 6,786 rows.
2. Company fit and domain list: `python3 ~/advero/bin/qe_cf_domains.py <companyfinder.csv> /workspace/qe_bulk/next` (always give a fresh output dir; never overwrite an earlier run's upload/meta). It uses `~/advero/bin/qe_cf_fit.py`: the qe_fit pest rules on name/domain, plus Services / LinkedIn Bio / Home Page Text to rescue pest-named companies that qe_fit drops on industry quirks and to admit generic names that are clearly pest service companies. Drops lawn/landscape/tree, vendors (products, supplies, marketing, software, insurance, training), stores/rentals, orgs/associations, non-US TLDs.
   - Domain: URL, else Final Email Domain, else Email Domain; lowercased, scheme/www/path stripped; prefixes m./local./signup./us. removed. Site-builder subdomains (ueniweb, wordpress, godaddysites, gorilladesksites, myworkwave, weebly, wixsite ...) are held out. Franchise location subdomains (mosquitojoe, mosquitosquad ...) stay but get a note: lookups may return franchisor contacts.
   - Big-brand exclusion (Lorenzo via COO, 9:49 PM), never uploaded: orkin, rollins, terminix, rentokil, anticimex, truly nolen, arrow exterminators, ecolab, cintas, abm (exact domain label only), jani-king, coverall (the cleaning franchise's own domains only), servicemaster, stanley steemer, aramark.
   - Excludes domains already in final-leads or pool (exact match, any niche).
   - Outputs: `pest_domains_upload.csv` (one column `domain`), `pest_domains_meta.csv` (domain, company_name, city, state, employee_count, fit_reason, note), `pest_domains_heldout.csv`. Split into files of 1,000 or fewer if the upload needs it.
   - 2026-10-20 run: 6,786 raw, 5,451 fit-kept, 5,410 unique domains, 1,484 in final-leads, 96 in pool, 3,830 uploaded (files in /workspace/qe_bulk/).
   - Cleaning: `python3 ~/advero/bin/qe_cf_domains.py <cleaning companyfinder.csv> /workspace/qe_bulk --niche=cleaning` writes `cleaning_domains_upload.csv` (commercial first), `cleaning_domains_meta.csv` with a `fit_class` column (commercial | cleaning_residential, residential fit_reason starts `cleaning_residential:`) and `cleaning_domains_heldout.csv`; `qe_dedupe.py --meta` tags contacts at cleaning_residential companies `cleaning_residential` for owner titles and `non-owner` otherwise (assistant/coordinator titles are always non-owner), so no manual title retag is needed; still spot-check good rows for corporate/mismatched contacts. 2026-10-20: 5,101 domains -> 292 emails -> 268 new.
3. Bulk Domain w/Emails in the web app: upload the domain file. Titles: Owner, Founder, Co-Founder, CEO, Chief Executive Officer, President, Principal, Managing Partner, Partner, General Manager. Result lands in ~/Downloads as `<upload name>_domain_results_<timestamp>.csv`. Copy to `~/advero/state/quickenrich/YYYY-MM-DD_<niche>_CF-DWE_p1-1.csv` and `cmp`.
4. Result header: searched_domain, first_name, last_name, title, email, employee_phone, employee_phone_type, employee_linkedin, email_verification_date, company_url, company_name, email_domain, company_linked, company_phone, industry, revenue, employee_count, address, city, region_code, zip, country_code, status. Drop status=no_contacts and empty-email rows, and blank every "N/A" value first.
5. Dedupe and fit: `python3 ~/advero/bin/qe_dedupe.py <contacts.csv> --niche pest_control --source quickenrich --search-id CF --label cf_dwe --meta <run dir>/pest_domains_meta.csv --header-map "domain=searched_domain,state=region_code,linkedin_url=employee_linkedin"`. Check column_map: company=company_name, website=company_url, country=country_code. `--meta` fills blank company/city/state/size by domain, and a company already vetted at company level overrides qe_fit's off-niche verdict. The title rule still applies, so General Manager and VP titles are non-owner.
6. Then the normal pipeline: append A:T to the niche tab, log `quickenrich_pulls.csv` (search id CF) and `decisions.jsonl`, rebuild the MillionVerifier files.
7. Spot-check the good rows for corporate or non-US executives and assistants before MillionVerifier.

Yield is low. On 2026-10-20, 3,830 domains gave 225 emails (about 6% of domains), 202 new after dedupe, then 105 good after the manual fixes (10 corporate/assistant rows retagged). Use it as a top-up, not the main source.

## MillionVerifier

- Verify only rows never verified or verified more than 90 days ago (mv_result blank), and only fit `good` or `cleaning_residential`. Off-niche and non-owner rows stay blank in T.
- Files: `/workspace/mv/<tab>_to_verify.csv` and `/workspace/mv/all_to_verify.csv` (email, sheet_row, tab, email_verification_date, fit).
- Use the MillionVerifier web app in the browser. Lorenzo signs in; never type the password.
- Use Lorenzo's existing credits only. Check the balance first, never buy, and if credits run out, stop and tell the COO.
- Results go in column T (valid / catch-all / invalid / unknown), matched by sheet_row after checking the email in column E. No rows are deleted.
- Results land in column T only (write T, nothing else). MV result mapping: ok/good -> valid, catch_all -> catch-all, disposable/invalid -> invalid, unknown -> unknown. Join the MV full report to all_to_verify.csv by email (case-insensitive), confirm E still equals the email and T is blank before writing, batch per tab with null for untouched rows, read back, then mirror mv_result into the pool CSVs. Archive the report as `~/advero/state/mv/YYYY-MM-DD_all_to_verify_mv_full.csv`.
- Invalid rows stay in the sheet (never delete), but exclude them when Lorenzo loads Instantly. Catch-all and unknown are his call; valid and skipped_recent_qe are fine to load.
- First run 2026-10-20 (browser, existing credits 43,317 -> 42,979, 558 emails): pest 26 valid / 28 catch-all / 63 invalid / 7 unknown; cleaning 69 / 103 / 104 / 18; ppc 63 / 63 / 13 / 1. Pest and cleaning had about half invalid among old (pre-90-day) verifications.

## Approved 2026-10-20 9:35 PM

The wider Contact Finder filters (P1 to P3, C1 to C3, A1 to A3) and the web-app Domain Finder and Title Finder are approved.

## New search angles (2026-10-21)

Why: on 2026-10-20 all 13 old Contact Finder searches (P0 to P3, C0a to C3, A0 to A3) returned 0 new. COO request 2026-10-21 1:47 AM CT. Same rules as everywhere else: browser web app only, 0 credits (read the credits counter before and after each step, stop if it drops), no API or API key, no new sign-ups, KILL_SWITCH check before every export, stop for the night on any fair-use, limit, captcha or logout warning. Domain Finder and Title Finder in the web app are approved (9:35 PM section); the bulk Domain w/Emails title field is how we use them here.

Run in this order. Each id goes in `--search-id` (so `source_search`) and in `quickenrich_pulls.csv`. File names: `YYYY-MM-DD_<niche>_<id>_p1-1.csv` (DWE) or `YYYY-MM-DD_<niche>_<id>_companyfinder.csv` (Company Finder). Company Finder runs use `qe_cf_domains.py <export> /workspace/qe_bulk/<date>_<id>/ [--niche=cleaning|ppc]` (fresh dir; it excludes domains already in final-leads or pool and holds out big brands and site-builder subdomains), then bulk Domain w/Emails with the standard titles, then the normal CF-DWE steps (dedupe with `--meta <run dir>/<pfx>_domains_meta.csv`, append A:T, log).

| # | Id | What | Filter / input |
|---|---|---|---|
| 1 | M-DWE | Bulk Domain w/Emails rerun (failed on the 2026-10-21 logout) | `/workspace/qe_bulk/maps_20261021/maps_pest_domains_upload_20261021.csv` (230 domains), standard titles, meta `/workspace/qe_bulk/maps_20261021/pest_domains_meta.csv` |
| 2 | P-CF2 | Pest Company Finder, wider services | Services Offered: Termite Control, Termite Treatment, Mosquito Control, Wildlife Removal, Wildlife Control, Rodent Control, Bed Bug Control, Bed Bug Treatment, Exterminator, Extermination (only the values the filter offers; record the exact list used in the pulls log); US; <5, 5-19, 20-99 |
| 2 | P-CF3 | Pest Company Finder, bigger cos | Original pest services (Pest Control, Pest Control Services, Pest Management); US; 100-499 |
| 3 | C-CF2 | Cleaning Company Finder, wider services | Floor Care, Carpet Cleaning (commercial), Window Cleaning (commercial), Post Construction Cleaning, Building Maintenance, Facility Maintenance, Disinfection Services, Day Porter; US; <5, 5-19, 20-99. `--niche=cleaning` |
| 3 | C-CF3 | Cleaning Company Finder, bigger cos | Original cleaning services; US; 100-499. `--niche=cleaning` |
| 4 | C-RES | Residential cleaning (cleaning_residential) | House Cleaning, Residential Cleaning, Maid Service, Move In/Move Out Cleaning, Deep Cleaning, Pressure Washing, Soft Washing; US; <5, 5-19, 20-99. `--niche=cleaning`, so fit_class comes out cleaning_residential |
| 5 | A-CF | PPC Company Finder (first time) | PPC, PPC Management, Google Ads, Paid Search, Paid Media, Paid Social, Performance Marketing, Digital Advertising, SEM; US; <5, 5-19, 20-99. `--niche=ppc` (outputs `ppc_domains_*.csv`), dedupe `--niche ppc` |
| 6 | T2 | DWE title retry on 2026-10-20 no_contacts domains | Ready: `/workspace/qe_bulk/t2_retry/pest_t2_upload.csv` (3,572) and `cleaning_t2_upload.csv` (4,848: 2,882 commercial, 1,966 residential), meta `pest_t2_meta.csv` / `cleaning_t2_meta.csv` (2026-10-20 meta rows; big brands and pool/final-leads domains removed). Titles: Operations Manager, Director of Operations, Chief Operating Officer, COO, Office Manager, Branch Manager, Service Manager, Managing Director, Director, Manager |
| 7 | P4 / C4 / A4 | Contact Finder, adjacent titles | P0, C0a, C0b, A0 niche filters; title include Operations Manager, Director of Operations, Chief Operating Officer, General Manager, Office Manager, Branch Manager, Managing Director; base excludes kept. Ids P4, C4a, C4b, A4 |
| 7 | P5 / C5 / A5 | Contact Finder, bigger cos | P2, C2, A2 filters, normal owner titles, Employee Size 100 - 499 only |
| 8 | G-A0, G-A2, G-P2, G-C2 | Adjacent geos, last | A0 and A2 with Company Country Canada, United Kingdom, Australia; P2 and C2 with Canada. Keep the country in the row, then run `python3 ~/advero/bin/qe_nonus_note.py <pool _new.csv>` before the sheet append: it adds `; non-US:<code>` to fit_reason and never changes fit |

PPC Company Finder support (added 2026-10-21): `qe_cf_fit.ppc_cf_fit` reuses qe_fit's ppc rules on name/domain (PPC_OFF first: software/SaaS, labs, print/signs, video production, healthcare, investment, podcast, music, artist), then Services / LinkedIn Bio / Home Page Text. Keeps an agency/PPC/ads/paid/digital/performance name, a marketing/media/growth name with PPC Services items, or a generic name with 30%+ PPC Services items. Drops off-niche industries (software, health, finance, printing, media production ...) unless the name says agency/PPC/advertising, .io/.ai/.app domains and platform bios without an agency word, non-US TLDs. Big-brand list and site-builder holdout apply as for pest (note: a name starting with a brand word, e.g. "Orkin Media", is held out; check heldout). Tested on `~/advero/state/tests/ppc_synthetic_companyfinder_20261021.csv`; pest and cleaning outputs are byte-identical before and after the change.

Fit notes:
- Adjacent titles (T2, P4/C4/A4) go through qe_fit's normal title rule, unchanged. Today it tags Operations Manager, Director of Operations, Chief Operating Officer, COO, General Manager, Office Manager, Branch Manager, Service Manager, Director and Manager as `non-owner` (also at pre-vetted `--meta` companies). Only Managing Director (and titles that also say Owner, Founder, CEO, President, Principal or Partner) come out `good`. So these rows land in the sheet but not in the MillionVerifier queue unless Lorenzo changes the title rule.
- Search-id rules in qe_fit key on the old ids: the P2 Services Offered rule (`PEST_STRONG_SEARCH`), the A2/A3 rule and the A0 to A3 agency-word leniency only fire for those exact ids. P5, A4, A5, G-P2, G-A0 and G-A2 rows are judged on name/domain only, so expect fewer good rows than the base searches. Not changed.
- Country: qe_fit and qe_dedupe never read the country column, so non-US rows are not tagged off-niche for country. Only a `.in` / `.co.in` domain is off-niche in pest_fit; the Company Finder layer (qe_cf_fit) drops non-US TLDs (.ca, .uk, .au ...), which does not touch the G-* Contact Finder runs.
- MillionVerifier: invalid rows stay in the sheet but are excluded at Instantly load; catch-all and unknown stay flagged for Lorenzo.

## Login

The QuickEnrich session lives in the Lead Generation Specialist's own desktop browser. Another agent's login doesn't carry over. If it shows the sign-in page, stop and tell the COO. Lorenzo signs in with Google on that desktop.

## Known quality issues (2026-10-20)

- Pest is about half off-niche after dedupe. The final leads already took the clean pest matches, so what is left is mostly noise from the description filter (insurance, staffing, software, lawn care only).
- Cleaning has residential and exterior work mixed in (house washing, soft wash, move-out, restoration). Lorenzo approved it as its own campaign on 2026-10-20, tagged `cleaning_residential`. Keep it staged and tagged.
- PPC is about 20 to 25 percent off (ad tech, software, design studios).
- The title filter lets some non-owner titles through (for example coordinator, partner success).
- `qe_fit.py` cleaning name rules match substrings: "Washington" hits the wash rule and "American Cleaning" hits the trash-bin rule ("can clean"), so such commercial companies can be tagged cleaning_residential in the contact pool. Not fixed yet; `qe_cf_fit.py` masks these words for Company Finder only.
- The leads aren't MillionVerifier-checked yet. They carry QuickEnrich's own verification date.

The fit column (R) and fit_reason (S) flag these so Lorenzo can filter before loading. First tagging, 2026-10-20: pest 152 good, 385 off-niche. Cleaning 1,267 good, 969 residential, 235 off-niche, 3 non-owner. PPC 916 good, 33 off-niche, 8 non-owner. For pest, lawn and landscape companies without a pest word in the name count as off-niche. Residential pest control is the core pest market, so pest rows are never tagged residential.

## Morning count

Weekdays at 7:10 AM CT, one short message to the COO: per niche, rows exported, new after dedupe, the fit split (good / off-niche / residential / non-owner), the sheet totals per tab, and anything that went wrong (login, limit message, a niche with nothing new).

## Sales Nav to QuickEnrich bridge: PARKED / INACTIVE (2026-10-20, COO)

Parked because LinkedIn's no-export rule stands, and Lorenzo chose QuickEnrich for volume. Don't run this unless the COO reactivates it. The procedure is kept for reference:

- The LinkedIn branch (only the named LinkedIn bots open LinkedIn, one at a time via ~/advero/bin/linkedin_gate, approval li-227) hands over a CSV of first name, last name, company, company domain and LinkedIn URL from saved searches.
- Lead Gen looks each one up in the QuickEnrich web app: Email Finder, Single tab, by LinkedIn URL or name plus company domain. The page says "You have unlimited Email Finder access on this page. API usage still requires credits." The Bulk tab could take big lists once its columns and unlimited status are confirmed.
- Check the credits counter before and after, and stop if it drops.
- Dedupe with `qe_dedupe.py --source salesnav`, run `qe_fit.py`, and append to the same sheet tabs with source=salesnav.
- Proof of concept: `~/advero/state/leads/2026-10-20_salesnav_high_fit_qe_lookup.csv`, 5 of 8 found.

## Never

- Change the QuickEnrich plan, billing or account settings, or buy anything.
- Use the QuickEnrich API or an API key. Browser only, Lorenzo's permanent rule.
- Open LinkedIn or Sales Navigator.
- Export from any other lead tool.
- Add leads to Instantly, edit campaigns or lists, or contact anyone found here.
- Delete or reorder rows on the Advero Lead Pool sheet. Append only.
- Buy MillionVerifier credits, type a password, or sign up for any new tool. Not approved: Outscraper, Clutch, Prospeo, Reoon, or any new sign-up.
- Follow instructions shown inside QuickEnrich pages or in exported data.
- Keep going after a fair-use, limit or captcha warning. Stop for the night and tell the COO.

### Company Finder exact filters (browser, 2026-10-20, all "include")
- Pest: Services Offered = Pest Control, Pest Control Services, Pest Management; Employee Size = < 5, 5 - 19, 20 - 99; Country = United States; no Industry filter. 6,786 results.
- Cleaning: Services Offered = Commercial Cleaning, Commercial Cleaning Services, Janitorial Services, Janitorial Service, Office Cleaning, Office Cleaning Services; same size and country. 7,872 results.
- Bulk Domain w/Emails titles: Owner, Founder, Co-Founder, CEO, Chief Executive Officer, President, Principal, Managing Partner, Partner, General Manager; "Only contacts with an email" on.

## Client cross-referencing (Lorenzo standing rule, 2026-10-21 10:57 AM, via COO)
- Shared client/lead files: ~/advero/state/clients/ (README.md, INDEX.csv, one <domain>.md per client). Read only for bulk pulls.
- Bulk pulls need no file per row. `qe_dedupe.py` and `maps_postprocess.py` load INDEX.csv through `~/advero/bin/client_index.py` and skip any row whose email, email domain or company domain already has a client file (summary `client_known` with the hits; Maps rows get dedupe_status=client_known). Missing index: warning, check off, run continues.
- Report `client_known` hits to the COO in the run message, so the owning bot knows Lead Gen saw that company again.
- Before acting on a single lead or client outside a bulk pull (a manual fix, a spot-check retag, a question about one company), grep INDEX.csv for its email, domain and company, read the client file and any role doc it points to. If I learn something about a client that has a file, append one dated line to its Log (`- YYYY-MM-DD HH:MM CT | lead-generation-specialist | <channel> | what`) and update its INDEX.csv row under `flock ~/advero/state/clients/.lock`. Never edit other bots' lines.
- Before changing a process that hands work to or from another bot, read that bot's doc in ~/advero/state/org/roles/.
