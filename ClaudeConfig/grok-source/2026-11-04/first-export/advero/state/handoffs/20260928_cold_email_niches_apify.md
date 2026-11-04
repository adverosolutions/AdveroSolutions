# Cold email as product  -  niches (Apify-scrapable)

## LOCKED WINNERS (Lorenzo via COO, 2026-09-28)
1. MSPs / managed IT
2. Digital marketing / SEO agencies
3. Commercial insurance brokers
4. Commercial landscaping
5. Commercial pest control

**Suppress:** landscaping and pest have light adjacency to commercial cleaning. Suppress against live cleaning lists before upload.

Date: 2026-09-28 CT
Status: DRAFT. 10 niches. Outside or only light overlap with live niches (commercial cleaning, bookkeeping/tax, recruiting agencies).
Top 3 marked with ★ (angles written in sibling file).

Apify path notes (public actor categories / examples as of search 2026-09-28): prefer cheap Maps/directory sources.
- Google Maps: e.g. `cirkit/google-maps-business-scraper`, `zen-studio/google-maps-scraper`
- Yellow Pages: e.g. `cirkit/yellow-pages-business-scraper`, `karamelo/yellow-pages-us-scraper`, `parseforge/yellowpages-scraper`
- Yelp: Yelp Business Scraper category
- BBB: e.g. `scrapesage/bbb-scraper`, `intelecta/bbb`
- Clutch (agencies): e.g. `procoders/clutch-scraper-pro`, clutch B2B lead scrapers
- Angi (home/commercial services): e.g. `fatihtahta/angi-scraper-with-contacts`
Actor names are examples of well-known categories; confirm live Apify store before spend.

---

## ★ 1. Managed IT / MSPs
1. **Niche name:** Managed Service Providers (MSPs) / managed IT firms
2. **Why it fits:** Sell recurring IT to local businesses; need outbound for net-new logos; owners will pay for booked discovery calls; list density is high but DIY scraping/copy is rare.
3. **Scrape path:** Google Maps (`managed it services`, `it support`, `msp` + metro); Yellow Pages IT category; BBB "Computers - Networks".
4. **Personalization signal:** Specialty line from Maps category or site ("managed Microsoft 365", "healthcare IT", city + "24/7 helpdesk") → `{{personalization}}`.
5. **Lead density (US):** High. Estimate: tens of thousands of MSPs nationwide (order of ~20k-50k listings depending on definition). Label: estimate.
6. **Suppression:** National franchise IT brands if any; exclude pure break-fix shops if ICP is managed-only. No live Advero niche overlap.

## ★ 2. Digital marketing / SEO agencies
1. **Niche name:** Digital marketing, SEO, and PPC agencies (SMB-focused)
2. **Why it fits:** They sell pipeline to clients but often under-invest in their own outbound; understand cold email; will buy a system that books agency-owner or marketing-lead calls.
3. **Scrape path:** Clutch (SEO / Digital Marketing categories); Google Maps `marketing agency` / `seo agency`; complementary Yellow Pages.
4. **Personalization signal:** Primary service from Clutch/Maps (`seo for dentists`, `ppc`, `web design + seo`) or city + niche focus.
5. **Lead density (US):** High. Estimate: tens of thousands of agencies (very noisy; filter by review count / team size signals). Label: estimate.
6. **Suppression:** Huge franchise/marketplace brands; agencies that only do pure creative with no sales calendar. Light overlap risk: some agencies also offer "lead gen" (message carefully so we are not pitching against their product). No live Advero niche overlap.

## ★ 3. Commercial insurance agencies / brokers
1. **Niche name:** Independent commercial insurance agencies / brokers
2. **Why it fits:** High ACV; growth depends on producer outbound; lists of local businesses are hard to work consistently; booked appointments with business owners are the currency.
3. **Scrape path:** Google Maps `commercial insurance` / `insurance agency`; Yellow Pages insurance; BBB insurance agencies.
4. **Personalization signal:** Lines of coverage or niche (`construction insurance`, `trucking`, `cyber`) from site/Maps categories.
5. **Lead density (US):** High. Estimate: tens of thousands of independent agencies. Label: estimate.
6. **Suppression:** Captive-only carrier storefronts if ICP is independent; national big-box brands. Compliance: no consumer spam angles; B2B agency owners only. No live Advero niche overlap.

## 4. Commercial real estate brokerages (office / industrial)
1. **Niche name:** Commercial real estate (CRE) brokerages, office and industrial focus
2. **Why it fits:** Brokers live on conversations with owners and tenants; outbound supplements sphere-of-influence; will pay for meetings.
3. **Scrape path:** Google Maps `commercial real estate` / `office broker`; niche directories where available; BBB real estate.
4. **Personalization signal:** Asset focus (`industrial`, `office leasing`, market name).
5. **Lead density (US):** Medium-high. Estimate: high thousands to low tens of thousands of CRE shops. Label: estimate.
6. **Suppression:** Residential-only brokerages; mega national brands if desired. No live Advero niche overlap.

## 5. Freight brokers / 3PL sales teams (SMB)
1. **Niche name:** Freight brokerage and small 3PL sales orgs
2. **Why it fits:** Constant need for shipper conversations; outbound culture already exists; booked calls convert to loads/accounts.
3. **Scrape path:** Google Maps `freight broker` / `trucking broker`; industry directories; BBB transportation.
4. **Personalization signal:** Lane or freight type (`refrigerated`, `flatbed`, region).
5. **Lead density (US):** Medium. Estimate: several thousand to ~10k+ licensed brokers (filter seriously). Label: estimate.
6. **Suppression:** Authority/compliance noise; one-truck carriers mis-tagged as brokers. No live Advero niche overlap.

## 6. Business / executive coaching firms (B2B)
1. **Niche name:** Business coaches and boutique consulting firms selling to owners
2. **Why it fits:** Product is conversations; cold email is a natural acquisition channel; buyers understand "booked calls."
3. **Scrape path:** Google Maps `business coach` / `executive coach`; Clutch consulting categories; directories.
4. **Personalization signal:** Niche they coach (`ecommerce`, `agencies`, `contractors`) from site/Maps.
5. **Lead density (US):** High but noisy. Estimate: tens of thousands of solo/boutique coaches; quality filter required. Label: estimate.
6. **Suppression:** Pure life-coaching / consumer wellness if ICP is B2B. No live Advero niche overlap.

## 7. Commercial landscaping / grounds maintenance
1. **Niche name:** Commercial landscaping and grounds maintenance companies
2. **Why it fits:** Contract accounts; need property-manager and facility conversations; Maps-dense; similar economics to cleaning but not the live cleaning niche.
3. **Scrape path:** Google Maps `commercial landscaping` / `grounds maintenance`; Angi/BBB landscaping; Yellow Pages.
4. **Personalization signal:** Commercial vs residential mix, HOA/campus focus, city.
5. **Lead density (US):** High locally. Estimate: tens of thousands nationwide. Label: estimate.
6. **Suppression:** Big franchise landscaping brands; pure residential lawn guys if ICP is commercial. **Light adjacency** to commercial cleaning (same buyer type sometimes). Do not merge lists with live cleaning campaigns without Lorenzo's suppress rule.

## 8. Commercial pest control
1. **Niche name:** Commercial pest control companies
2. **Why it fits:** Recurring B2B accounts (restaurants, warehouses, multi-family); outbound to facility managers books walkthroughs.
3. **Scrape path:** Google Maps `commercial pest control`; Yellow Pages; Angi; BBB.
4. **Personalization signal:** Vertical focus (`restaurants`, `warehouses`, `multifamily`) if visible.
5. **Lead density (US):** Medium-high. Estimate: high thousands to tens of thousands. Label: estimate.
6. **Suppression:** National franchises (Orkin-class) if ICP is independent. Light adjacency to cleaning facility buyers. No direct live niche overlap.

## 9. Security system / commercial alarm integrators
1. **Niche name:** Commercial security and alarm integrators
2. **Why it fits:** Project + monitoring revenue; need facility and GC conversations; outbound underperforms DIY.
3. **Scrape path:** Google Maps `commercial security system` / `alarm company`; Yellow Pages; BBB.
4. **Personalization signal:** Access control / CCTV / fire alarm focus from site/category.
5. **Lead density (US):** Medium. Estimate: thousands to low tens of thousands. Label: estimate.
6. **Suppression:** National monitoring brands' local dealers if list quality poor. No live Advero niche overlap.

## 10. Architecture firms (small/mid commercial)
1. **Niche name:** Architecture firms with commercial or mixed work
2. **Why it fits:** Need developer/owner conversations; slow sales cycle rewards booked intros; Maps + directory scrapable.
3. **Scrape path:** Google Maps `architect` / `architecture firm`; professional directories; BBB.
4. **Personalization signal:** Project type (`healthcare`, `multifamily`, `adaptive reuse`) from portfolio blurbs.
5. **Lead density (US):** Medium. Estimate: tens of thousands of firms, fewer with true commercial ICP. Label: estimate.
6. **Suppression:** Sole residential designers if ICP is commercial. No live Advero niche overlap.

---

## Explicitly deprioritized (overlap with live three)
- Commercial cleaning companies  -  live campaigns.
- Bookkeeping / tax / CPA shops  -  live campaigns (payroll/HR-only could be revisited later with clear ICP split).
- Recruiting / staffing agencies  -  live campaigns.

Legacy contractor offers (HVAC, plumbing, electrical, roofing) are not running per business context; not pitched as live Advero niches. Not used here unless Lorenzo reopens trades.

---

## Top 3 for angles file
1. ★ MSPs / managed IT
2. ★ Digital marketing / SEO agencies
3. ★ Commercial insurance agencies / brokers
