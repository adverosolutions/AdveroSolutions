# Lead volume options: most verified leads at the lowest cost (pest control, commercial cleaning, PPC agencies)

Prepared 2026-10-20, about 9:45 PM CT, for the COO and Lorenzo. Research only: nothing was bought, signed up for or changed.
All prices are public list prices as fetched on 2026-10-20. Cost-per-verified-lead and yield figures are **estimates** unless a local file is cited. Run the free tests in section 6 before spending at scale.

## 0. Bottom line

1. **Use what's already paid for first.** QuickEnrich's web app is unlimited, and the 50,000 MillionVerifier credits bought on 2026-09-29 are probably mostly unused. Widening the QuickEnrich filters and using its **Domain/Title Finder** on new company domains costs $0 extra.
2. **Google Maps is the volume source for pest and cleaning.** These are local businesses that LinkedIn-based databases cover poorly, and that's why the QuickEnrich pest pool ran dry. Outscraper or Apify Maps scrapes give company domains for about $3–7 per 1,000 places. QuickEnrich's free Domain/Title Finder then finds the owner, with a website email (often a generic info@ address) as the fallback. Est. **$15–25 per 1,000 verified leads**. Our own 2026-09-22 pricing check came out at Apify $0.0222 and Google Maps $0.0250 per confirmed contact (GROK_ONBOARDING_PACK.md, "List factory").
3. **For PPC, use Clutch plus a database.** A one-time Clutch scrape (under $3 per 1,000 listings) gets agency domains for the free QuickEnrich domain lookup. For ongoing PPC volume, Prospeo is the cheapest verified B2B database ($10–25 per 1,000).
4. **Verify with what's already paid for, then Reoon.** Use the remaining MillionVerifier credits first. After that, Reoon is the cheapest at about $1.19 per 1,000.
5. **The real limit at 9,000 a week isn't leads.** Instantly Hypergrowth caps uploaded contacts at **25,000 total** (the cap doesn't reset), and 60 inboxes send about 1,500 emails a day. At 9,000 new leads a week you'd need Light Speed (+$261/mo) and about twice the inboxes.

Estimated new monthly spend: **about $280–320 a month at 4,500 leads a week**, and **about $650–700 a month at 9,000 a week**, plus $261 for Instantly Light Speed and more inboxes. Section 4 has the details.

## 1. Where we are (local files)

- QuickEnrich first run, 2026-10-20 (`state/quickenrich_pulls.csv`): 9,402 rows exported, 3,968 new after dedupe, **2,335 good fit** (pest 152, cleaning 1,267, PPC 916). Of the exports, 5,263 were already in final-leads, so QuickEnrich's LinkedIn-based pools are largely used up.
- final-leads (`state/leads/final-leads/`): pest 1,809, cleaning 1,971, PPC 4,403. They came from QuickEnrich searches (description, services and industry) and were MillionVerifier-checked in part, with ok and catch_all results.
- MillionVerifier: **50,000 credits bought 2026-09-29** (`state/finance/business/receipts.jsonl`). I couldn't find a usage log, so the remaining balance is unknown. Lorenzo or Lead Gen should check it in the MillionVerifier dashboard. MillionVerifier credits never expire.
- Earlier lead scrape: `~/advero/state/handoffs/20260928_cold_email_niches_apify.md` lists Apify Maps, Yellow Pages, BBB and Clutch actors. The onboarding pack's "List factory" section notes that on 2026-09-22 both sources priced above a $0.02-per-confirmed-contact cap: Apify $0.0222 and Google Maps $0.0250. It also notes that catch-alls run about a quarter of checks. The code folder `lead-scrape-2026/` is on Lorenzo's Mac (`/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026/`). I didn't open it. 09_company_and_process_overview.md lists "Apify, MillionVerifier" as the lead stack, so an Apify account probably exists.
- Instantly: Hypergrowth, $97/mo (receipts). Its limits are 25,000 uploaded contacts and 100k–125k emails a month.

## 2. Ranked recommendation table

Volume is new, good-fit, verified leads per week **after** dedupe against final-leads and the pool. All are estimates.

| Rank | Source | Est. cost per 1,000 verified leads | Pest / week | Cleaning / week | PPC / week | Effort | Risk |
|---|---|---|---|---|---|---|---|
| 1 | **QuickEnrich web app, wider filters + Domain/Title Finder** (current plan) | **~$1–2** (verification only) | +100–300 once, then ~20–50 | +500–1,500 once (incl. the 969 residential rows if Lorenzo opens that segment), then ~50–100 | +300–800 once, then ~30–80 | Low | Low. Already running; overlaps final-leads |
| 2 | **Google Maps (Outscraper or Apify) → QuickEnrich Domain/Title Finder → website email fallback → verify** | **~$15–20** (Outscraper) / **~$20–25** (Apify Free-plan rates) | **1,000–1,500** for ~8–12 weeks | **1,500–3,000**, months of supply | 100–300 (Maps covers agencies poorly) | Medium | Medium. A share of the emails are generic (info@ or office@). Google's terms forbid scraping (the vendor carries that). Role addresses get lower replies. |
| 3 | **Clutch.co (+ Google Partners directory) → QuickEnrich domain lookup** | **~$3–10** | – | – | **1,500–3,000 once** | Medium | Low–medium. Clutch's terms; small one-time pool |
| 4 | **Prospeo** (keyword/industry search, 1 credit per verified email) | **$10–25** | low (same data as QuickEnrich) | low–medium | **1,000–2,500** for ~4–8 weeks | Low | Low |
| 5 | **Icypeas** (email finder or domain scan for Maps domains QuickEnrich misses) | **~$5–9** per found email | booster | booster | booster | Low | Low. Needs names or domains as input |
| 6 | **Instantly SuperSearch** (Lead Finder credits) | **~$15–30** (≈1.5 credits per verified email) | low | low–medium | 1,000–2,000 | Lowest (loads straight into campaigns) | Low. Data overlaps QuickEnrich and Prospeo |
| 7 | **Hunter** (Discover + Finder) | **~$12–25** | low | low | 500–1,000 | Low | Low |
| 8 | **Apollo** Basic | **~$20–26**. The free plan gives only 75 credits a month | low | low | 500–1,500 | Medium (2,500 records max per search) | Low |
| 9 | **Leadsforge** | ~$21–25 if 1 credit ≈ 1 email (credit cost per contact not published) | low | low | 500–1,000 | Low | Low |
| 10 | **AnyMailFinder** | $32–73 per person email. "Company emails" mode is 1 credit for up to 20 emails per domain | booster | booster | booster | Low | Low |
| – | Sales Navigator bulk export | ruled out (scraping; LinkedIn Outreach rules) | – | – | – | – | High |

**How I estimated Maps yield (assumptions, check them with the free tests):** of 1,000 Maps places, about 75% have a website. After dedupe about 60% of those are new. QuickEnrich's Domain/Title Finder should find a named owner email for roughly 30–45%. Website scraping finds a generic email for about half of the rest. Then 65–75% pass verification. That's about **300–350 sendable verified emails per 1,000 places**, and it matches our 2026-09-22 cost check of about $22–25 per 1,000 confirmed contacts. Expect roughly half of them to be generic rather than the owner's address.

**Supply ceilings (public estimates):** US pest control has about 31,300 businesses (IBISWorld) or 32,700 (Smarfle). US janitorial has about 29,300 establishments (Claight), or about 103k for the broader NAICS 5617. Clutch lists about 19,000 PPC agencies worldwide, and its US list runs to more than 54 pages. The Google Partners directory shows about 3,100 partners worldwide. Pest is the tightest: after the 2,300+ already used, Maps can probably add about 10–20k verified pest emails in total. That's roughly 8–12 weeks at 1,000–1,500 a week.

## 3. Findings by area (with sources)

### 3.1 QuickEnrich: more filters, the credits, and the Email Finder
- **What the 25,034 credits are:** QuickEnrich credits are "1 credit = 1 contact with email and/or phone number", and the pricing page sets the API rate at **$0.004 per email or phone**. The $99 "Unlimited Web App, plus a metered API" tier includes **25,000 API credits a month, reset monthly**. Lorenzo's balance is 25,034, and web exports didn't lower it. So the credits are almost certainly that plan's **API allowance**, and they reset each month. Under Lorenzo's browser-only rule they go unused. *Inference: the plan name isn't on file. Lead Gen can confirm it on the Billing page, read-only.* Sources: https://quickenrich.io/pricing , https://quickenrich.io/free-email-finder-by-quickenrich
- **Unlimited in the web app:** the pricing pages list "Unlimited Emails & Mobile #s via WebApp, Contact Finder Bulk, Email and Phone Finder, **Domains/Title Finder**" on the WebApp Unlimited tier. Lead Gen already saw "You have unlimited Email Finder access on this page. API usage still requires credits" in the app (skill file). **The Email Finder is unlimited in the web app; only API use costs credits.** Bulk-tab limits still need a check in the app.
- **Biggest free win:** the **Domains/Title Finder** takes a company domain plus titles and returns contacts. That turns every Maps or Clutch domain into owner emails at no extra cost. It's the same lookup as the API endpoint `GET /api/employees/dataset-search` (company_url, title, has_email). Source: https://app.quickenrich.io/docs
- **Wider Contact Finder searches** (fields available: Company Name, Services Offered, Industry, LinkedIn Description, Title, Employee Size):
  - Pest: Company Name contains pest / termite / extermin / bug / mosquito / wildlife / bed bug; Services Offered = pest control or termite; add the "Environmental Services" and "Consumer Services" industries with a pest description.
  - Cleaning: Services Offered = commercial cleaning, janitorial, office cleaning, floor care, post-construction cleaning; Company Name contains janitorial / commercial cleaning / building maintenance; and Lorenzo's call on the 969 residential/exterior rows already tagged.
  - PPC: Services Offered = PPC, Google Ads, SEM, paid social; Company Name contains "ppc", "ads", "media"; Industry "Online Audience Measurement" / "Internet Marketing".
  - All niches: add the titles "Owner/Operator", "General Manager", "Director" for companies with fewer than 20 employees, and add the 100–249 size band for cleaning.
- **Optional, Lorenzo's call:** lifting the browser-only rule for a capped API job would put the **25,000 credits a month he already pays for** to work, for example running domain lookups over Maps domains. That's about 25k contacts a month at no extra cost. It needs an explicit change to his permanent rule.

### 3.2 Google Maps scrapers plus website email extraction
- **Apify Google Maps Scraper** (compass/crawler-google-places), pay-per-event: $4 per 1,000 places on the Free plan, going down to "from $1.50 per 1,000" with higher-plan discounts. Contact details from websites are **+$2 per 1,000 places**, and places without websites aren't charged. Filters are +$1 per 1,000 places per filter. Actor start is $0.007. Sources: https://help.apify.com/en/articles/10774732-google-maps-scraper-is-going-to-pay-per-event-pricing , https://apify.com/compass/crawler-google-places
  - The Free plan includes **$5 of usage a month**, no card (about 700–1,200 places): enough for a test. Starter is $19/mo with $19 of usage and a Bronze discount. Source: https://apify.com/pricing
  - A real-world rate is about **$6–7 per 1,000 places** with contacts. It can do whole-US runs per search term with category filters (Pest control service, Exterminator, Termite control service; Commercial cleaning service, Janitorial service, Cleaning service).
- **Outscraper**: Google Maps businesses are **free for the first 500**, then **$3 per 1,000** up to 100k and $1 per 1,000 after. **Emails & Contacts Scraper** is free for the first 500 domains, then **$3 per 1,000 domains**. Pay-as-you-go with a card on file, no subscription. Sources: https://outscraper.com/pricing/ , https://outscraper.com/emails-scraper/
  - Cheapest path: scrape places at $3 per 1,000, run QuickEnrich Domain/Title Finder first for free, and pay the $3 per 1,000 website contact scrape only for domains QuickEnrich misses. That works out to about **$4–5 per 1,000 places**.
- Pest and cleaning coverage is strong, because nearly every operator keeps a Google Business Profile. Coverage of PPC agencies is weak, because many are remote and categorized as generic "Marketing agency".

### 3.3 B2B databases: cost per verified email
- **Apollo:** the Free plan gives 900 credits a year (75 a month) with a 25-record selection limit. Basic is $49/seat/mo annual or $65 monthly for 30,000 credits a year (about 2,500 a month); 1 credit = 1 email. Each search shows at most 100 pages × 25 results (2,500 records). That's about **$20–26 per 1,000**. Sources: https://www.apollo.io/pricing , https://pipeline.zoominfo.com/sales/apollo-pricing , https://apolloexporter.com/guides/apollo-export-limits
- **Instantly SuperSearch:** 1 credit for a verified email Instantly finds itself, 2+ credits from partners, about 1.5 on average, and nothing if no email is found. Credit plans: Growth $47 for 1,500, Supersonic $97 for 5,000, Hyper $197 for 10,000, Hyper 2 $300 for 20,000, Hyper 3 $500 for 45,000, Hyper 4 $997 for 100,000. Monthly credits expire after 2 months. Verification costs 0.25 credits per lead. That's about **$15–30 per 1,000 verified**. Sources: https://help.instantly.ai/en/articles/11364248-supersearch , https://help.instantly.ai/en/articles/11381241-instantly-credit-system , https://instantly.ai/pricing
- **Leadsforge:** $49/mo for 2,000 credits, or $588/yr for 28,000. Credits never expire, and the credit cost depends on the enrichment level, so the per-email cost isn't published. Source: https://www.leadsforge.ai/pricing
- **Prospeo:** 1 credit = 1 verified email, and nothing is charged if none is found. Starter $49 for 2,000, Growth $99 for 5,000, Pro $249 for 15,000; yearly is 25% off, and credits roll over. **Add-on credits start at 1,000 for $10.** That's about **$10–25 per 1,000**. Up to 20,000 rows per selection. Free plan: 100 a month. Source: https://prospeo.io/pricing
- **Hunter:** Starter $49 for 2,000 credits, Growth $149 for 10,000, Scale $299 for 25,000 (30% off yearly). 1 credit per email found; verification is 0.5 credits. About **$12–25 per 1,000**. Source: https://hunter.io/pricing
- **AnyMailFinder:** 1 credit only when a verified email is found; 1 credit for up to 20 company emails per domain; verification 0.2 credits. Listed tiers: 1k credits at $0.049 each ($49/mo) and 12k credits at $0.032 each. About **$32–49 per 1,000 person emails**, cheaper in company-emails mode. It guarantees 97%+ delivery and verifies catch-alls. Source: https://anymailfinder.com/pricing
- **Icypeas:** Basic $19 for 1,000, Premium $39 for 4,000, Advanced $89 for 10,000, Hypergrowth $499 for 100,000 (+VAT). 1 credit per found email, verification 0.1 credit, domain scan 1 credit, people search 0.02 credit per result. Credits never expire. **About $5–9 per 1,000 found emails**, catch-all verification included. Sources: https://www.icypeas.com/pricing , https://www.revenueflow.com/blog/icypeas-pricing

### 3.4 Verification (price per 1,000)
| Verifier | 10k pack | ~50k–100k | 1M | Notes | Source |
|---|---|---|---|---|---|
| **Reoon** | **$1.19** ($11.90) | $1.18–1.16 | $0.97 | Never expires; unknowns refunded; 20 free a day | https://www.reoon.com/email-verifier/ |
| **MillionVerifier** | ~$3.90 | **$1.78 (50k for $89)** / $1.49 (100k) | $0.45 | Never expires; catch-all and unknown not charged; **Lorenzo already holds 50k credits** | https://www.millionverifier.com/ , https://www.reoon.com/blog/email-verification-pricing/ |
| **Bouncer** | $6.00 | $5.00 / $4.00 | $2.00 | Never expires; unknowns and duplicates free | https://www.usebouncer.com/pricing/ , https://emailverifiers.com/pricing/bouncer/ |
| **Instantly built-in** | 0.25 credits per lead ≈ **$4.40–4.90** at Hyper or Supersonic credit rates | | | Needs an Instantly credit plan; SuperSearch leads are already verified | https://help.instantly.ai/en/articles/6514690-how-to-verify-leads |

Recommendation: use up the MillionVerifier balance first, then buy Reoon. Keep catch-alls in a separate, slower campaign or drop them, as the List factory rule already says.

### 3.5 Agency directories for PPC
- **Clutch.co:** the US PPC list runs to more than 54 pages, with about 19k PPC agencies worldwide. Apify actors cost **$0.08–$2.90 per 1,000 listings** (for example danthedataman/clutch-agency-directory at $0.08/1k, piotrv1001 at $1.50/1k, and memo23 at $2.90/1k with email extraction). A full US PPC pull is a few dollars. You get company, website and size; owner emails come from QuickEnrich Domain/Title Finder. Sources: https://clutch.co/us/agencies/ppc , https://apify.com/danthedataman/clutch-agency-directory , https://apify.com/memo23/apify-clutch-cheerio/pricing , https://apify.com/piotrv1001/clutch-listings-scraper/pricing
- **Google Partners directory:** about 3,100 listed partners worldwide, filterable by US, Partner or Premier Partner. There's no dedicated actor; the closest general one, seeb/b2b-partner-page-lead-miner, costs $25 per 1,000. It's small but very well targeted (certified Google Ads shops). Lead Gen could also page through it in the browser. Sources: https://partnersdirectory.withgoogle.com/ , https://support.google.com/google-ads/answer/11410677 , https://apify.com/seeb/b2b-partner-page-lead-miner

## 4. Recommended stack and monthly cost

**The stack:**
1. **QuickEnrich web app (already paid):** wider Contact Finder searches each night, plus **Domain/Title Finder** for every new domain from Maps or Clutch.
2. **Outscraper Google Maps** for pest and cleaning: places at $3 per 1,000 (first 500 free), and its Emails & Contacts scraper ($3 per 1,000 domains) only on domains QuickEnrich misses. Apify is the alternative at about $6–7 per 1,000 places if Lorenzo already has an account and would rather keep one vendor.
3. **Clutch** (Apify actor, one-time) plus Google Partners for PPC domains, run through the QuickEnrich domain lookup.
4. **Prospeo** for ongoing PPC volume.
5. **Verification:** the remaining MillionVerifier credits, then Reoon.
6. Tag each row `email_type = owner | generic` and `source`. Load generic addresses into their own campaign.

**At 4,500 new leads a week (~19,500 a month)**, split as pest 1,200, cleaning 2,000 and PPC 1,300 a week:
| Item | Monthly |
|---|---|
| Outscraper Maps: about 42k places ($3/1k) + website contacts on about 17k QuickEnrich-miss domains ($3/1k) | ~$180 |
| Clutch scrape (one-time, then a monthly refresh) | ~$5 |
| Prospeo Growth (5,000 verified PPC emails) | $99 |
| Verification, about 28k checks a month (existing MillionVerifier credits cover about the first 7 weeks, then Reoon) | $0 now → ~$35 |
| **New spend** | **~$280–320 a month (~$15 per 1,000 verified)** |
| Instantly: stay on Hypergrowth **only if** finished leads are backed up and deleted each week to stay under 25k; otherwise Light Speed | $0 or +$261 |

**At 9,000 new leads a week (~39,000 a month)**, split as pest 1,500 (supply lasts about 10–12 weeks), cleaning 4,500 and PPC 3,000 a week:
| Item | Monthly |
|---|---|
| Outscraper Maps: about 78k places + about 33k contact-scrape domains | ~$335 |
| Prospeo Pro (15,000) or Instantly Hyper 2 credits ($300 for 20k ≈ 13k emails) | $249–300 |
| Verification, about 55k checks a month (Reoon 50k for $59, or a MillionVerifier 50k top-up at $89) | ~$65–90 |
| **New spend** | **~$650–725 a month (~$17–19 per 1,000 verified)** |
| Instantly Light Speed (100k uploaded contacts; 25k can't hold about 27k leads in active sequences) | +$261 (required) |
| More sending capacity: 9,000 new a week is about 3,000 emails a day vs 1,500 today, so roughly 60 more inboxes and domains (not priced here) | extra |

## 5. Who runs each piece
| Piece | Owner | Notes |
|---|---|---|
| Wider QuickEnrich searches, Domain/Title Finder, Email Finder | **Lead Generation Specialist** (browser) | Already its job. Add the new filters to `skills/quickenrich-lead-pulls.md` |
| Outscraper or Apify Maps runs, and Clutch actor runs, through the vendor's web console | **Lead Generation Specialist** (browser) | **The skill's Never list currently says "Export from any other lead tool."** The COO needs to amend it, with Lorenzo's OK |
| Prospeo exports (PPC) | **Lead Generation Specialist** (browser) | Same skill amendment |
| Dedupe, fit tagging, sheet append (`qe_dedupe.py`, `qe_fit.py`) | **Lead Generation Specialist** (box) | Extend `--source` to maps / clutch / prospeo, and add an `email_type` column |
| MillionVerifier or Reoon checks | **Lead Generation Specialist** | The skill says MillionVerifier runs only when Lorenzo or the COO says so. That needs a standing yes |
| Instantly cap (backup and delete finished leads, or upgrade), loading leads | **Lorenzo** (the COO tracks the count) | Deleting leads in Instantly is irreversible, so it needs his explicit OK each time or as a rule |
| Inbox expansion for 9k a week | Lorenzo, with whoever owns `skills/deliverability-and-inboxes.md` | Out of scope here |
| LinkedIn Outreach Manager | no role in volume | Stays on the 10-a-day connect list; the export bridge stays parked |

## 6. Free tests to run first (account sign-ups still need Lorenzo's OK)
- Outscraper: 500 free places + 500 free domains, about 250 pest + 250 cleaning places in 2–3 states. Check the website rate, how many QuickEnrich Domain/Title Finder hits, the generic-vs-owner split, and the verification pass rate.
- Apify Free ($5 a month, no card): the same test, if the existing Apify login is available.
- QuickEnrich Domain/Title Finder: run it on 100 of those domains and check that the credits counter stays at 25,034 (proves it's unlimited in the web app).
- Prospeo free plan (100 credits a month) or Icypeas (50 free credits): spot-check how many PPC emails are found and how many bounce.
- Reoon: 100 free + 20 a day to compare against MillionVerifier on the same 100 rows.

## 7. Needs Lorenzo's approval (purchases, sign-ups, rule changes)
1. **Sign-ups:** Outscraper (needs a card on file), Prospeo, Icypeas or Reoon trials, and Apify if there's no existing account.
2. **Spend:** Outscraper pay-as-you-go (~$180/mo at 4.5k a week, ~$335 at 9k), Prospeo $99–249/mo, Reoon packs or a MillionVerifier top-up once the current credits run out.
3. **Instantly:** either a weekly backup-and-delete of finished leads (irreversible) or upgrading to Light Speed at $358/mo (+$261). This is **required at 9k a week** and likely within about 5 weeks at 4.5k a week.
4. **Rule changes:** (a) let Lead Gen use Outscraper, Apify, Clutch and Prospeo (skill Never list); (b) a standing yes for MillionVerifier/Reoon verification; (c) optional: lift the QuickEnrich browser-only rule for capped API use of the 25k monthly credits he already pays for; (d) open the residential/exterior cleaning segment (969 rows, free).
5. **9k a week:** more inboxes and domains. Today's 60 inboxes can't send that volume.

## 8. Open checks
- Lorenzo's exact QuickEnrich plan and whether Domain/Title Finder Bulk is unlimited on it (Billing page, read-only).
- Remaining MillionVerifier balance.
- The current uploaded-contacts count in Instantly against the 25,000 cap.
- The real Maps yield per 1,000 places (section 6). Every Maps figure above is an estimate until then.
