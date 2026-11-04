# Creative free lead sources plan (Yellow Pages and beyond), 2026-11-01

Owner: Lead Gen Manager. For: Lorenzo via COO (GO Sun 11/1 7:53 PM CT: "design a Yellow Pages scraper and any other creative sources").
Status: DESIGN ONLY. Nothing scraped, bought, signed up for, or changed. No API keys. Stage only; nothing goes to Instantly.
Builds on: handoffs/leadgen/autonomous_scraping_plan_20261029.md (pest short about 550 to 750 a week; Maps top 200 pest metros nearly done).
Labels: every yield below is an ESTIMATE, untested. Terms and blocking notes are from general knowledge of each site and must be re-read on the live site before any build (one public page read per source, no scraping).

## 0. Bottom line
- Best new free sources are public government records, not directories: state pest control license lists, then Secretary of State business filings. They are public data, give OWNER NAMES (the thing Maps lacks), and have low terms risk.
- Yellow Pages works technically but its terms forbid automated collection, and it mostly repeats what Maps already gives us (name, phone, website, no owner, no email). Rank it mid, run it slow, as a domain discovery feed for QE.
- Yelp and BBB: high terms and blocking risk. Do not scrape. At most, use them as manual lookup, not a pipeline.
- Realistic added pest supply: about 300 to 600 new pest domains or owners a week for the first 6 to 10 weeks (estimate), most of it from license lists. That closes most of the pest gap, then tapers because US pest is a finite pool (about 31,000 to 33,000 firms).

## 1. Ranked sources

| Rank | Source | Niches | Yields | Est. new/week (estimate) | ToS / block risk |
|---|---|---|---|---|---|
| 1 | State pest control business and applicator license lists | Pest | Company, licensed owner or qualifier name, address, phone, sometimes email | 300 to 500 pest (first 8 weeks), then about 50 | Low (public records) |
| 2 | Secretary of State business entity search (officers, registered agent) | All | Owner or officer names for a known company; no email | Enrichment, about 200 to 400 owner names matched | Low to medium (some states block bots, captcha) |
| 3 | Other state trade license boards (HVAC, plumbing, electrical, contractor, landscape, pesticide applicator for lawn) | Adjacent home services | Company, license holder name, phone, address | 500 to 1,500 adjacent | Low |
| 4 | Industry association member directories (NPMA "Find a Pro", state pest associations, ISSA, BSCAI, ARCSI, IICRC) | Pest, cleaning | Company, website, sometimes owner | 100 to 300 (one time per site, then monthly diff) | Medium (terms vary) |
| 5 | Google Partners and Microsoft Advertising partner directories, Shopify/HubSpot/Semrush agency directories | PPC | Agency name, domain, city | 100 to 300 (one time), then low | Medium |
| 6 | Yellow Pages (yellowpages.com) | Pest, cleaning, adjacent | Name, phone, address, website, years in business | 200 to 600 new domains | High terms risk, medium block risk |
| 7 | Chambers of commerce member directories | All local | Name, phone, website, sometimes contact person | 50 to 200 | Low to medium, very manual per chamber |
| 8 | Manta, Superpages, Hotfrog, Angi or Thumbtack listings | Local | Name, phone, city, some websites | Low value, mostly Maps dupes | High |
| 9 | Yelp | Local | Name, phone, website (via redirect) | Not run | Very high (terms forbid, strong anti-bot) |
| 10 | BBB | Local | Name, phone, sometimes principal name | Not run | High (terms forbid, Cloudflare) |

Why this order: owner names and public-record status first (low risk, fills the Maps gap), domain-only directories last because Maps already covers them.

## 2. Source details

### 2.1 State pest control license lists (rank 1)
- What: state agriculture or structural pest boards publish licensed pest businesses and certified applicators. Examples to check: Texas TDA structural pest control license search, Florida FDACS pest control licensee search, California Structural Pest Control Board license lookup, North Carolina SPCD, Georgia Dept of Agriculture, Arizona, Louisiana, Virginia VDACS. Several states offer a downloadable CSV or Excel file or a public records request; others only a search form.
- Data: business name, license number, qualifier or certified operator (usually the owner in small firms), address, phone, sometimes email. Domain usually missing.
- Runs on the box: per-state adapter in ~/advero/bin/license_scrape/<state>.py. Priority order: states with bulk downloads (plain HTTP GET, one file, once a month), then search forms queried by county or city with Python requests, 1 request per 3 to 5 s, max 2,000 requests a night, headless, no desktop. Domain found by matching to Maps rows (name plus city plus phone) and, if no match, a free website guess from the phone or name via existing Maps data only (no paid finder). Then QE Domain w/Emails (0 credits) on domains found.
- Risk: public records, low. Some states rate limit or captcha; stop on captcha (no solving). Respect robots.txt. Monthly refresh catches new licensees (new businesses are good leads).
- Feed: output CSV in leads/license/pest_<state>_<date>.csv with columns matching maps_postprocess.py output (company, domain, email, phone, city, state, owner_first, owner_last, source=license_<state>). Dedupe with a new --source license option in qe_dedupe.py (or a thin wrapper calling the same key functions): client INDEX.csv, final-leads, all Lead Pool tabs, leads/maps, pool. Key order: email, then domain, then new key phone (digits) plus normalized company name, because many rows have no domain. Rows matching an existing Lead Pool row with no owner become an ENRICH update (owner name added), not a new row. Suppression via suppression.py, stop if file missing.

### 2.2 Secretary of State business search (rank 2)
- Use as enrichment, not discovery: for each pest and cleaning company with no owner, look up officers or registered agent. Many SOS sites have bulk data only for a fee, so use free search pages only, and only in states with no captcha (e.g. some offer open data portals such as Colorado, Oregon, Washington, New York open data on Socrata, which are free public downloads without a key).
- Yields owner name only. Then QE Contact Finder by owner name plus domain (browser Export, 0 credits) or the existing pattern step.
- Risk: low on open data portals; medium on search forms (captcha, rate limit). Stop on captcha.
- Feed: same as 2.1, updates owner columns on existing rows; logged as source=sos_<state>.

### 2.3 Other state trade license boards (rank 3)
- Same adapter pattern as 2.1 for HVAC, plumbing, electrical, roofing or general contractor, landscape and lawn pesticide applicators. Texas TDLR, Florida DBPR, California CSLB publish large free license data files.
- Big volume, but only useful once an adjacent campaign is approved (plan 10/29, decision 5). Build after pest.
- Feed: new or existing adjacent tabs (roofing, HVAC, plumbing, landscaping, lawn care), same dedupe keys.

### 2.4 Association member directories (rank 4)
- NPMA and state pest associations; ISSA, BSCAI, ARCSI for cleaning. Often public "find a member" pages by state or zip.
- Runs: one-time crawl per site, Python requests plus BeautifulSoup, 1 request per 5 s, then a monthly diff. Read each site's terms first; skip any that forbid it or need a login.
- Feed: domains to QE Domain w/Emails, then normal dedupe.

### 2.5 PPC partner directories (rank 5)
- Google Partners directory, Microsoft Advertising partners, Shopify Partners, HubSpot Solutions directory, Semrush agency partners. Yields agency name, domain, city, specialties.
- Runs: one-time, polite crawl or headless browser if the page is JS. Domains go to QE Domain w/Emails for owner emails.
- Feed: ppc tab, dedupe against ppc_agencies tab too (6,333 rows) since overlap will be high.

### 2.6 Yellow Pages scraper (rank 6, the asked-for design)
- Data: business name, phone, street address, website link, categories, years in business. No owner, rarely email.
- Design: ~/advero/bin/yp_scrape.py, Python requests plus BeautifulSoup (no desktop). Input: category term (pest control, exterminators, janitorial service, commercial cleaning, house cleaning, HVAC, etc.) times city list (reuse Maps metro list, then Census places 201+). URL pattern search?search_terms=<term>&geo_location_terms=<city, ST>&page=N, parse result cards, max 5 pages per term-city, 1 request per 6 to 10 s with jitter, one process, max about 1,500 pages a night, run 2:00 to 5:00 AM CT so it does not overlap Maps CPU peaks. Lock file plus heartbeat.py beat, runs.csv row like Maps.
- Stop rules: any 403, 429, captcha, "access denied" or empty page twice in a row means exit 3, mark cities not done, wait 24 h, halve rate; two blocks in a week means pause and tell COO. No proxies, no rotating user agents, no evasion.
- Risk: YP terms of use forbid automated scraping and robots.txt limits search paths (re-check before build). This is a terms risk Lorenzo should accept explicitly. Blocking is moderate at polite rates.
- Value: mostly overlaps Maps. Its value is listings without a Google profile and older firms. Estimate 15 to 30% new domains after dedupe vs Maps.
- Feed: yp_postprocess.py modeled on maps_postprocess.py (same normalize, GENERIC and FREEMAIL rules, dedupe and suppression), outputs leads/yp/<niche>_<date>.csv; no-email domains go to the QE Domain w/Emails queue; MV only on non-QE-verified emails.

### 2.7 Chambers of commerce (rank 7)
- Many use the same platforms (ChamberMaster or GrowthZone "business directory" pages), so one parser covers hundreds of chambers. Yields name, phone, website, sometimes a named contact.
- Low volume per chamber; run by metro after Maps covers it. Medium priority after pest work.

### 2.8 Manta, Superpages, Hotfrog, Angi, Thumbtack (rank 8)
- Mostly the same businesses as Maps, terms forbid scraping, Angi and Thumbtack hide contact info. Skip unless a test shows over 20% new.

### 2.9 Yelp and BBB (ranks 9 and 10): do not build
- Both forbid scraping in their terms and run strong bot defenses. Yelp's official API needs a key (not allowed). Recommendation: no pipeline. Manual spot checks only if a specific lead needs it.

## 3. Common pipeline on the box
1. Source adapter writes raw CSV to leads/<source>/raw/.
2. <source>_postprocess.py normalizes to the Maps output columns plus owner_first, owner_last, license_no, source.
3. Dedupe (qe_dedupe.py logic generalized, or extend maps_postprocess.py with --niche and --source): client INDEX.csv, final-leads, all Lead Pool tabs, leads/maps, leads/pool, prior QE files. Keys: email, domain (never freemail), then phone plus normalized name. Matches with new owner info become enrichment updates.
4. Suppression via suppression.py (stop if file missing).
5. No-email domains to the QE Domain w/Emails queue (0 credits). Non-QE emails to the MV queue (existing credits only).
6. Append to the niche Lead Pool tab after backup and read-back. Held rows (unknown fit) to handoffs/leadgen/.
7. KILL_SWITCH check before each run, decisions.jsonl line per pull, heartbeat and runs.csv for the 7:10 leak review.
Scheduling: headless, no desktop; license and YP jobs run 2:00 to 5:00 AM CT, never at the same time as Maps on CPU-heavy nights.

## 4. Build order (after Lorenzo's go on the plan)
1. Texas, Florida, California pest license adapters (bulk files where available). Test on one state, measure new rows.
2. Phone plus name dedupe key and owner-enrichment update path.
3. SOS open data owner lookup for pest and commercial cleaning rows with no owner.
4. PPC partner directories, one-time.
5. Yellow Pages, only if Lorenzo accepts the terms risk; start with a 10-city test.
6. Association and chamber directories.
7. Other trade boards when an adjacent campaign is approved.

## 5. Decisions for Lorenzo
1. Approve the build order, starting with pest license lists (low risk).
2. Yellow Pages: accept the terms risk or skip.
3. Confirm Yelp, BBB, Angi, Thumbtack stay off.
4. Whether owner names from license and SOS records may be paired with guessed or QE-found emails for cold email (normal for B2B, but a policy call).

## 6. Lorenzo's decisions (via COO, Sun 11/1 7:59 PM CT)
1. Yes, start the one-state pest license list test.
2. Scrape Yellow Pages anyway; he accepts the terms risk; keep it polite with a low rate and no logins.
3. Research Yelp, BBB, Angi and Thumbtack only: report feasibility, terms and yield before building. See yelp_bbb_angi_thumbtack_research_20261101.md.
4. Yes, pair owner names from public records with emails for cold email.
Everything stays staged, nothing goes into Instantly, nothing is bought.
