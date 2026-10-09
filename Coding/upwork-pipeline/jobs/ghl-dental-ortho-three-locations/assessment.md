# Assessment (private) - GHL dental/ortho, 3 locations, South Florida

Prop: chart only (`"platform": "diagram"`), 13 steps, 5 bands, nothing built in GoHighLevel.

## Time
Real hours by their five milestones (plan figure 90 h, range 75 to 110 h):

| Milestone (their wording) | Hours |
|---|---|
| 1. System architecture, account configuration and pipelines | 10-14 |
| 2. Lead sources, call tracking and Google/Meta attribution | 15-22 |
| 3. Workflows, appointment follow-up, no-show recovery and recall/reactivation | 22-30 |
| 4. PMS/integration work and offline conversion tracking | 15-28 (their PMS decides) |
| 5. Dashboard, testing, documentation and staff training | 12-16 |

Calendar: about 6 weeks, 5 to 8 realistic. What stretches it: A2P 10DLC SMS registration (file on day one; no follow-up texts go out before approval), their PMS route, waiting on Google Ads and Meta admin access, and real conversions flowing before the offline import can be checked end to end. Training across three front desks sits at the end and depends on their staff calendars.

## Likelihood
- Account, pipelines, fields, calendars, workflows, dashboard: high. All native GHL. Unverified for Lorenzo: no dental build of his exists, so the stage design and message copy get a review pass with their office manager in milestone 1.
- Call tracking: medium. Depends on their phone system and whether each office's main line is forwarded or ported to GHL (calls to a number GHL never sees are never tracked), on their website platform accepting the GHL tracking script and number pool, and on front desks marking the call outcome. The "did not schedule" follow-up fires off that outcome, so staff discipline is the weak point; a fallback rule (no appointment within a set window after a new-patient call) covers missed marks.
- Offline conversions: medium, and unverified for Lorenzo (never implemented from GHL). Open items to test, not assume:
  - GCLID capture on their website forms (GHL tracking script or hidden fields) and whether the number pool carries the click ID onto website calls.
  - Calls placed straight from an ad (call assets) carry no GCLID; they need Google forwarding numbers and Google's call conversion import, a separate path.
  - iOS clicks can arrive as gbraid/wbraid instead of gclid; check which import route accepts them.
  - Google accepts a conversion only inside the action's click window, 90 days at most. Ortho cases that start treatment later count on their dashboard only.
  - Smart bidding needs steady volume. Became Patient and Treatment Started may be too few per month to bid on (their volume is an input); start them as secondary goals.
  - Whether GHL's own Google Ads conversion feature covers this; fallback is a GHL stage-change workflow writing rows to a Google Sheet that Google Ads imports on a daily schedule, or the Google Ads API from n8n (developer token approval adds time).
  - Whoever runs their Google Ads (in-house or an agency) has to agree before bidding goals change.
- PMS integration: low to medium, fully dependent on which PMS they run (not named). Lorenzo has integrated none. Routes to check once named: the PMS's own API (Open Dental publishes one), a third-party sync service for Dentrix or Eaglesoft type systems (monthly fee, their account), a scheduled export, or the front desk moving stages by hand. The fixed price should assume an existing API or sync service, or the manual fallback; a custom connector to an on-premise PMS with no API is out of the fixed scope.
- PHI: the marketing CRM holds name, phone, email, location, service, source and stage only. Check whether HighLevel's HIPAA option and a BAA are available and active on their plan before live patient data goes in (unverified). Sending "became a patient" events tied to a person to Google is a disclosure question for their compliance advisor, not for Lorenzo; default to click ID, neutral stage and time, no names, no treatment details, no enhanced-conversion hashes until signed off. Never claim the build meets HIPAA.
- Reporting: GHL dashboards split by pipeline and source; confirm the widgets they need per location on their plan. Revenue attribution needs a case value from the PMS or the front desk.
- AI calling: design-ready only (named fields and stages); building an AI phone agent is outside this price.

Sharp points that are on the build and in a beat: 12 follow-up workflows for 3 offices instead of 36 copies (band 3 note, beat 6); what Google receives is signed off by their compliance advisor (band 2 note, beat 4); stop-on-status-change (gate 8, beat 5). The 90-day window is in the band 2 note and in answer 5.

## Standard pricing
- Market for this scope (multi-location GHL build with call tracking, Google Ads offline conversions, a PMS link, dashboards and training) from a GHL specialist with dental work to show: $7,000 to $12,000 fixed, roughly 90 h at $80 to $130 an hour. Dental marketing agencies usually add a monthly retainer on top.
- This post: hourly listing, no budget, bids avg $31.36 (range $8 to $85, basis unspecified). The field is far below market; the client is new to Upwork with $0 spent.
- Recurring software, all in their name: their own HighLevel plan (list $97/mo Starter or $297/mo Unlimited; confirm the plan covers API access and number pools), LC Phone numbers, minutes and SMS (usage-based), A2P 10DLC carrier fees, HighLevel's HIPAA option if their policy requires it (price unverified), a PMS sync service if their PMS needs one, n8n or Make only if a bridge is built.
- Suggested quote: $4,800 fixed [LORENZO: confirm], about $53 an hour at 90 h, below market on purpose.

## Milestone price split (their five milestones)

| Milestone | Price | Hours |
|---|---|---|
| 1. System architecture, account configuration and pipelines | $700 | 12 |
| 2. Lead sources, call tracking and Google/Meta attribution | $1,100 | 18 |
| 3. Workflows, appointment follow-up, no-show recovery and recall/reactivation | $1,300 | 26 |
| 4. PMS/integration work and offline conversion tracking | $1,000 | 20 |
| 5. Dashboard, testing, documentation and staff training | $700 | 14 |
| Total | $4,800 | 90 |

Milestone 4 assumes an existing PMS API or sync service, or the front-desk fallback [LORENZO: confirm].

## Ask before quoting
1. Which PMS does each office run, one shared database or one per location, cloud or on-site server? (moves milestone 4 most)
2. Do you have GoHighLevel today? Your own agency account or a sub-account under an agency? Anything to move over (contacts, numbers, workflows)?
3. Where are appointments booked: the PMS scheduler, GHL calendars or online booking?
4. Phone system and provider per office; will you forward or port the main lines; one call center or a front desk per location?
5. Who runs Google Ads and Meta, and can we get admin access? Do calls from ads use Google forwarding numbers today?
6. Your monthly new-patient leads and calls per location (sizes the number pool, the test plan, and which stage Google can bid on).
7. Website platform, and are forms on the site or in GHL?
8. Who signs off on compliance, and does your policy require a BAA with HighLevel?
9. Can the PMS export hygiene due/overdue and unscheduled treatment lists, and how many patients are on them?
10. How many staff users per location, and live training per office or one session?
11. Where does case value come from for revenue attribution: PMS production or the front desk?

## Flags
- New to Upwork: 0 contracts, 0 reviews, $0 spent; payment verification not shown.
- Portfolio demands: dental GHL count, a healthcare system to show, PMS integrations, offline conversion experience, AI phone agents. Every honest answer is "no" or "none"; the chart, the plan and the case studies carry the proposal.
- 14 questions, "Please do NOT send a generic proposal": the proposal answers all 14.
- Posted hourly, fixed price with milestones preferred.
- Scope fences to write down: "Other major services where appropriate", "Revenue attribution where technically feasible", AI calling (design-ready only), a custom PMS connector.
- PHI: no compliance claims of any kind.
- No US-only restriction stated; client in America/New_York.

## Their questions: draft answers for Lorenzo

1. **How many dental practices have you personally configured in GoHighLevel?**
None so far. The chart in my Loom is drawn from your post: your three offices, your 11 stages and the four events you want sent to Google Ads.

2. **Can you show us a dental GHL system or similar healthcare system you personally built?**
No, I have no dental or healthcare system to show. The nearest is a routing and follow-up system I built for a commercial roofing contractor: every estimate request is tracked and followed up, and $750M+ in annual bid volume runs through it. [LORENZO: confirm you can show a screen of it before offering to.]

3. **How would you structure GHL for 3 locations offering both general dentistry and orthodontics?**
One sub-account in a HighLevel account you own, with a pipeline each for Pembroke Pines, Boynton Beach and Royal Palm Beach carrying the same stages, a calendar and tracking numbers per location, and a Service field for General Dental, Orthodontics, Invisalign and Braces. One account keeps a patient as one contact across all three offices, lets the dashboard compare the locations, and turns your 12 follow-up situations into 12 workflows instead of 36. If each front desk must see only its own patients, we weigh three sub-accounts instead in milestone 1.

4. **Explain how you would track a patient from a Google Ads click or phone call all the way through becoming an actual patient.**
The Google click ID and UTM source are saved from your website forms, and a GHL number pool that swaps the phone number by visitor source ties website calls to their source (whether it carries the click ID too is checked in milestone 2), and calls placed straight from a Google ad carry no click ID, so they go through Google forwarding numbers and Google's call conversion import; the first source goes into fields nothing overwrites. Every call or form opens an opportunity in that location's pipeline, and the front desk or your PMS moves it from Appointment Scheduled through Showed and Became Patient to Treatment Started. Each move sends the matching conversion with the click ID to Google Ads and counts on the dashboard by location, source and campaign.

5. **Have you personally implemented Google Ads offline conversions or enhanced conversions for leads from GoHighLevel? Please describe the implementation.**
No, I haven't implemented Google Ads offline conversions or enhanced conversions for leads. I would create four conversion actions in your Google Ads account (Scheduled, Showed, Became Patient, Treatment Started), have a GHL workflow on each stage change send the click ID, conversion name and time through a scheduled Google Ads import or the Google Ads API from n8n, and check test conversions before any bidding change. Google only accepts a conversion inside the action's click window, 90 days at most, and bidding needs steady volume, so the deeper stages may start as secondary goals until your monthly numbers support them.

6. **How would you handle someone who calls the office but does NOT schedule an appointment?**
The front desk marks the call outcome, and "did not schedule" (or a missed call) starts a text-back from that location's number, then a short follow-up sequence. Every message checks the stage first, so the sequence stops the moment they reach Appointment Scheduled, and anyone who never replies moves to your reactivation list.

7. **Which dental practice-management systems have you integrated with GHL?**
None. Tell me which PMS each office runs and I'll confirm its route before milestone 4: its own API, an approved sync partner, a scheduled export, or, where none exists, the front desk moving the stage in GHL.

8. **How would you prevent duplicate patient/contact records?**
GHL's duplicate setting matches on phone and email, so a caller who later fills in a form stays one contact, and one account for all three offices keeps a patient who visits two locations as one record. Parents and children often share a phone number, so the contact is the person who called and each family member gets their own opportunity. Once a patient is in your PMS, their PMS ID goes on the contact and any sync matches on it first.

9. **Have you built recall/reactivation campaigns for dental practices?**
No. I'd build one campaign per list from your PMS (hygiene due or overdue, unscheduled treatment, orthodontic consults who didn't start), each stopping as soon as the patient books.

10. **Have you implemented AI inbound or outbound phone agents with GHL?**
No. I use Claude and the Anthropic API daily, and this build keeps stages, call outcomes and calendars in named fields so an AI agent, HighLevel's own or another provider's, can read and write them later without rebuilding the CRM.

11. **How would you handle HIPAA/PHI considerations?**
GHL holds what marketing needs (name, phone, email, location, service, source and stage); clinical notes, diagnoses, x-rays and insurance details stay in your PMS, and reminder texts name the office and time, not the treatment. Before patient data goes in, we check whether HighLevel's HIPAA option and a signed BAA are active on your account, and your compliance advisor signs off on what goes back to Google Ads; my default is click ID, stage and time, with no names or treatment details.

12. **Will the entire system be built inside accounts that we own and control?**
Yes. The HighLevel account, phone numbers, Google Ads and Meta connections, any n8n or Make bridge and the documentation all sit in accounts you own, and I work in them as a user you can remove at any time. If you are on an agency's sub-account today, moving to your own HighLevel account is the first step of milestone 1.

13. **What would you charge as a fixed project price for this implementation?**
$4,800 fixed [LORENZO: confirm], split over your five milestones: $700, $1,100, $1,300, $1,000 and $700. Software stays in your name and on your bill: your HighLevel plan, phone and SMS usage, and a PMS sync fee if your PMS needs one.

14. **Approximately how long would implementation and testing take?**
About 6 weeks [LORENZO: confirm], with milestone 1 done in week 1. SMS carrier registration (A2P 10DLC), which I'd file on day one, and your PMS's integration route are the two things that can stretch it.
