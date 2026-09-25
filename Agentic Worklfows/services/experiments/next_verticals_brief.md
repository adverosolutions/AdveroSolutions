# Next verticals after cleaning: five reactivation campaigns

Hand this to the list factory (A6). It defines what to build; it does not build anything.
Written 2026-09-22 against `REVENUE_AUTOMATION_BLUEPRINT.md` M4 ("Next verticals after cleaning is
proven ... One reactivation campaign each, 1,000 sends") and `config/offers.md`.

**No campaign in here exists yet, and none may be created until cleaning clears its verdict line.**
M4 puts cleaning first; these five are the queue behind it, one per month (Section 6, Monthly:
"one new vertical at 1,000 sends"). Creating a campaign is a live write.

## What every one of the five shares

| Item | Value | Source |
| --- | --- | --- |
| Campaign shape | One reactivation campaign. No trigger/outbound twin until the reactivation one clears 1,000 | M4 |
| Sequence | 3 steps: day 0, day 3, day 7. Step 1 carries variants A and B, step 3 is a new thread with a different subject | M3.3, M3.4 |
| Proof line (verbatim, do not paraphrase) | "I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months." | `config/offers.md`, Reactivation row |
| P.S. proof on step 3 only | One of: lender $5M pipeline on a $1.5k build; consultancy +35% reply rate; agency to $10k/mo | `config/offers.md`, "Other allowed proof" |
| Commercial shape | $0 up front, a commission on what comes back, $0 if nothing closes | `config/offers.md`, the three reactivation rows |
| Minimum list a prospect must have | 60+ lost, dormant or never-closed accounts | `config/offers.md` |
| Copy rules | No em dashes, no exclamation marks, never mention AI or automation, sign "Lorenzo", `{{personalization}}` alone on line 1 | root `CLAUDE.md`, `config/offers.md` rule 8 |
| Gate before anything is staged | `services.experiments.copy_validator.validate_copy(...)` green, `strict_readability=True` for new copy | brief A7 |

**Open before any of this is written into copy.** `config/offers.md` defines a commission number for
cleaning (20-30% of first-year contract value), bookkeeping (20-30% of first-year fees) and
recruiting (20-30% of the first placement fee). It defines nothing for these five. A new row in
`config/offers.md` has to exist before a draft may quote a percentage, because the offer sheet is
the only place pricing comes from. Until Lorenzo adds one, the copy says "a commission on the
accounts I bring back, nothing up front" and no number.

## Volume and cost per vertical

1,000 sends on a three-step sequence with `stop_on_reply` on is about **351 leads**: 1 + ~0.95 +
~0.90 is 2.85 sends per lead, and 1,000 / 2.85 = 351 (pull 360 and round up for bounces). At the M5
green line of $0.02 per verified contact that is **about $7 of list cost** to reach a verdict (up to about
$25 at the list factory's $0.07 cap, raised 2026-09-25 for worst-case Opus 5.5 thinking), plus the
sending capacity. At 50 sends/day 1,000 sends is **20 sending days**, about 24 calendar days on a
Mon-Sat schedule; at the post-2026-10-11 allocation (about 187/day per campaign) it is 6.

## 1. Commercial landscaping and grounds maintenance

| | |
| --- | --- |
| **ICP** | Commercial landscaping and grounds-maintenance contractors, $1M-$20M revenue, 15-150 crew, serving office parks, HOAs, retail centres, industrial parks and municipal contracts. Not residential mow-and-blow, not design/build studios. |
| **Who replies** | Owner, or the account manager who writes the renewal bids. |
| **Source** | Google Maps by metro (`google_maps_scraper.py`) filtered to "commercial landscaping", "grounds maintenance", "landscape maintenance"; the ICP scorer must answer "do they hold multi-site commercial contracts", not "do they cut grass". |
| **Why the dormant list exists** | Annual maintenance contracts that went out to bid and were lost on price, HOAs that switched providers after a board change, and snow-and-ice clients who never renewed the summer side. Most of these are still with a provider they are not happy with. |
| **Trigger (the why-now sentence)** | Contract renewal season. Commercial landscaping bids for the next year are written between January and March, so the reactivation run lands in the window when a lost account is deciding again. Second window: the end of the snow season, when a winter-only account can be converted to year-round. |
| **Proof point** | The canonical reactivation roofer line. It travels well here: the roofer and the landscaper both live on lost bids they never followed up. |
| **Icebreaker angle** | Service area and the property type they photograph most on their own site (office parks vs HOAs vs industrial). Per M4 the researched line, not a compliment. |
| **1,000-send test** | 360 leads across two metros so the metro is not a hidden variable. Step 1 A = call ask, B = "send me your list of bids you lost last season and I will tell you which are worth chasing". Verdict at 1,000: zero positives and it goes to `rework_copy`; one or more and it runs to 3,000. |
| **Watch for** | Seasonality. A run that lands in July reads as noise; do not judge a landscaping campaign on a summer 1,000. |

## 2. Commercial pest control

| | |
| --- | --- |
| **ICP** | Commercial pest control operators, $750k-$15M, serving restaurants, food processing, warehousing, property management and healthcare. Not residential-only, not termite-inspection-only. |
| **Who replies** | Owner or the branch manager who owns commercial accounts. |
| **Source** | Google Maps plus state pest-control licence registries by metro; the ICP scorer looks for "commercial", "food safety", "HACCP", "restaurant" on the site. |
| **Why the dormant list exists** | Monthly service contracts cancel constantly: a restaurant closes, a property manager consolidates vendors, a new GM cuts the line item. Cancelled accounts are in their software with a date and a reason, which is the cleanest dormant list of all five. |
| **Trigger** | A cancelled account with a named cancel reason, 6-18 months old. Second angle: a health-inspection failure at a building they used to service, which is public record in most counties. |
| **Proof point** | The canonical reactivation roofer line. |
| **Icebreaker angle** | The account type they lead with on their site (restaurants vs warehouses) and the metro. |
| **1,000-send test** | 360 leads. Step 1 A = call ask, B = "send me your cancelled-accounts export and I will tell you which ones are worth a second run". Same verdict rule. |
| **Watch for** | This is the vertical where the dormant list is most likely to be big and clean, which makes the 60-account minimum easy and the commission conversation easy. Expect the highest positive rate of the five. |

## 3. Security guard companies

| | |
| --- | --- |
| **ICP** | Contract security guard firms, 50-1,000 guards, serving construction sites, commercial real estate, events, healthcare and industrial. Not alarm installers, not electronic-security integrators, not executive protection boutiques. |
| **Who replies** | Owner or VP of business development. |
| **Source** | Google Maps plus state private-security licence boards; the ICP scorer must separate manned guarding from alarm/CCTV installation, which is the main false positive. |
| **Why the dormant list exists** | Guard contracts are won and lost on hourly rate and turn over yearly. Every firm has a stack of sites it lost to a cheaper bidder and a stack of construction sites that ended when the build finished and were never re-engaged. |
| **Trigger** | A construction site whose build completed (the contract ended, not the relationship) and a lost RFP anniversary: commercial real estate re-bids security roughly every 12-24 months, so the loss from last year is live again now. |
| **Proof point** | The canonical reactivation roofer line. Construction-adjacent, which reads as same-world to this buyer. |
| **Icebreaker angle** | The sector they lead with (construction vs CRE vs healthcare) and their licence state. |
| **1,000-send test** | 360 leads. Step 1 A = call ask, B = "send me the sites you bid and lost in the last two years and I will tell you which are back out to bid". Same verdict rule. |
| **Watch for** | Low margins and a price-led buyer. If the positives arrive but none of them can name a first-year contract value, the commission model does not fit and this vertical gets retired even with positives. That is a judgement call for Lorenzo, not a rule the verdict engine can make. |

## 4. Medical billing and revenue-cycle firms

| | |
| --- | --- |
| **ICP** | Outsourced medical billing / RCM companies, 10-200 staff, serving independent practices, surgery centres and small hospital groups. Not EHR vendors, not billing software, not single-biller solo shops. |
| **Who replies** | Owner or VP of sales. |
| **Source** | LinkedIn / Sales Navigator via HarvestAPI (M5 routes bookkeeping and recruiting this way; medical billing behaves the same), plus MGMA and state MGMA chapter member lists. |
| **Why the dormant list exists** | Long sales cycles and proposal-heavy selling. Practices that asked for a proposal and went quiet, practices that brought billing back in house and regretted it, and practices lost when the practice manager changed. |
| **Trigger** | The practice-manager change (a new manager re-opens every vendor decision), and the January payer contract and fee-schedule reset, which is when a practice notices its collection rate. |
| **Proof point** | The canonical reactivation roofer line. |
| **Icebreaker angle** | The specialty they name first on their site (orthopaedics, behavioural health, ASC) and the state, because payer mix is a state-level fact. |
| **1,000-send test** | 360 leads. Step 1 A = call ask, B = "send me the practices that asked for a proposal in the last two years and never signed". Same verdict rule. |
| **Watch for** | HIPAA nerves. Nothing in the copy should suggest we touch patient data; the sequences go to the billing company's own prospect list, which is ordinary business contact data. Say so plainly if asked on the call. |

## 5. Commercial insurance agencies

| | |
| --- | --- |
| **ICP** | Independent commercial P&C agencies and brokerages, 5-100 producers, writing commercial lines (contractors, trucking, habitational, manufacturing). Not personal-lines-only, not captive agents, not MGAs. |
| **Who replies** | Agency principal or the producer who owns new business. |
| **Source** | Google Maps by metro plus state agency licence lookup; the ICP scorer must reject captives (a site that leads with one carrier's brand) and personal-lines-only shops. |
| **Why the dormant list exists** | Commercial policies renew annually and every agency has a list of accounts it quoted and lost on price, plus accounts that left at renewal. The whole industry runs on the X-date, and almost nobody works the list of X-dates they already have. |
| **Trigger** | The X-date anniversary: an account lost at renewal last year is quotable again 60-90 days before the same date this year. This is the sharpest why-now sentence of the five. |
| **Proof point** | The canonical reactivation roofer line. |
| **Icebreaker angle** | The class of business they lead with (contractors vs trucking vs habitational) and the metro. |
| **1,000-send test** | 360 leads. Step 1 A = call ask, B = "send me your list of accounts you quoted and lost in the last two years with their X-dates and I will tell you which are worth working now". Same verdict rule. |
| **Watch for** | Compliance language. An agency cannot let an outside party contact an insured under the agency's name without care; the reactivation run here is to *prospects the agency already quoted*, not to current insureds, and the copy has to be explicit about that. Flag this one for Lorenzo before the first send. |

## Order and sequencing

1. **Commercial pest control** first: the cleanest dormant list and the cancel reason is already in their software.
2. **Commercial insurance agencies** second: the X-date is the strongest why-now line of the five.
3. **Commercial landscaping** third, timed so the 1,000 sends land January to March.
4. **Medical billing** fourth.
5. **Security guards** last, and only if the commission model survives the margin question.

One at a time. M4 says one new vertical per month at 1,000 sends, and Section 6 puts the verdict on
the Friday audit. Two new verticals at once and neither gets the inbox capacity to reach 1,000
before Lorenzo needs the answer.

## What the list factory needs back from this brief

For each vertical, `services/list_factory` (A6) should produce a niche definition file with: the ICP
description above, the accept/reject rules named in the **Source** row, the metro shards, the merge
variables the copy needs (`firstName`, `companyName`, `personalization`, plus any vertical variable
named in the icebreaker angle), and an `icebreaker_style` stamp on every lead so EXP-002 in
`config/experiments.json` can finally be counted.
