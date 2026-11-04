# 9. Offer test: B control vs new C (Lorenzo 10-27 12:57 PM CT)

*Lorenzo, 10-27 12:57 PM CT (relayed by COO): "B became like it just generated more leads than A. So I don't think there's a reason to continue running A across the board. And so we can make B the control and then create a C, which is a completely new offer, and see how the engagement goes on those. So, we're just going to be trying to split test our offer as much as possible going forward."*

Prepared by the Cold Email Manager agent, 10-27 about 1:00 to 1:30 PM CT. Read-only: no Instantly change was made, nothing was sent, nobody was messaged. Everything below is a proposal. The B vs C test replaces the other section 7 tests for now.

## What A and B are
- All six Launch campaigns make the same offer: custom automation, a discounted starter package and a 60-day refund. A and B differ only in the process automated: A is follow-up on open quotes or proposals, B is answering new inquiries (~/advero/state/reports/instantly_offer_audit_20261020.md, section 1, read from the live Instantly campaigns). So A vs B was an angle test. C would be the first test of the offer itself.
- **Gap:** the approved copy doc ("Advero emails: edit here", id 1bK3bkYfxYkhY0vFtHhB4RG6lMkKQrHvp6Qyasp8Pbt4, read 10-27) does not contain the Launch A/B emails. Its revision is unchanged since 10-21, and the offer audit found the Launch offer defined only in Instantly (~/advero/state/reports/instantly_offer_audit_20261020.md). So no A/B wording is quoted here.

## Current state: every live Launch campaign

Source: Instantly API read-only pull, about 1:00 PM CT 10-27 (/workspace/offer_20261027/raw/analytics_all.json, leads_*.json). All six are status 1 (active). Contacted = leads sent step 1. Not yet contacted = leads with no send yet. Mid-sequence = contacted and still active (step 2 still to come). Replies = unique human replies (Instantly reply_count_unique). Positives = leads Instantly labels interested or meeting booked.
- **Pest A**, Quote Follow-up, 6aaa096e-d344-4d44-a00a-5d907b9aca19: 764 contacted, 131 not yet contacted, 135 mid-sequence, 16 replies, 1 positive (Debby, Dependable Pest).
- **Pest B**, New Inquiry Response, f13b219a-c68e-4087-8ea1-a1c629605708: 762 contacted, 132 not yet contacted, 135 mid-sequence, 9 replies, 2 positives (Drew, Mosquito Squad Chicago, call Thu 10-29 2:00 PM CT; Marco, Quantum Pest, call Fri 10-30 1:00 PM CT).
- **PPC A**, Proposal Follow-up, 4e9f0b07-7854-4323-9084-20648a3998a0: 758 contacted, 1,438 not yet contacted, 131 mid-sequence, 6 replies, 0 positives.
- **PPC B**, New Inquiry Response, 49cd2de9-8f78-4543-b6d8-86106e46928d: 758 contacted, 1,437 not yet contacted, 131 mid-sequence, 4 replies, 2 positives (Dave, Velocity Marketing, pay-on-results only, which Lorenzo declined, closed Lost; Laura, Marketing Angle, a question, times sent).
- **Clean A**, Quote Follow-up, 1bd077f4-93ec-4854-929b-2e867905ad5a: 762 contacted, 210 not yet contacted, 134 mid-sequence, 7 replies, 1 positive (Angela, New Beginnings, times sent).
- **Clean B**, New Inquiry Response, 4d9998d5-4761-4290-b232-56237d774b32: 757 contacted, 215 not yet contacted, 131 mid-sequence, 8 replies, 1 positive (Leonardo, GDL, call held 10-23).
- Totals: 4,561 contacted, 3,563 not yet contacted (A 1,779, B 1,784), 797 mid-sequence (A 400, B 397). Call dates and outcomes come from the case files in ~/advero/state/cases/ and ~/advero/state/reports/cold_email_review_20261027.md (checks 2 and 5).

## A vs B rates and Fisher exact tests

Two-sided Fisher exact test, computed in /workspace/offer_20261027/stats.py (arithmetic on the counts above).
- **Pest:** positives A 1/764 (0.13%) vs B 2/762 (0.26%), p = 0.62. Replies A 16 (2.09%) vs B 9 (1.18%), p = 0.23.
- **PPC:** positives A 0/758 (0%) vs B 2/758 (0.26%), p = 0.50. Replies A 6 (0.79%) vs B 4 (0.53%), p = 0.75.
- **Cleaning:** positives A 1/762 (0.13%) vs B 1/757 (0.13%), p = 1.00. Replies A 7 (0.92%) vs B 8 (1.06%), p = 0.80.
- **Pooled:** positives A 2/2,284 (0.09%) vs B 5/2,277 (0.22%), p = 0.29. Replies A 29 (1.27%) vs B 21 (0.92%), p = 0.32.
- Booked calls, pooled: A 0 vs B 3 (Leonardo, Drew, Marco), p = 0.12 (case files above).
- Strict positives, leaving out Dave (declined, Lost) and Laura (a question): A 2 vs B 3, p = 0.69.
- Not-interested labels: A 24, B 14 (Instantly lt_interest_status, /workspace/offer_20261027/raw/leads_*.json).

**Verdict:** B is ahead on positives (5 vs 2) and booked calls (3 vs 0). A is ahead on raw replies (29 vs 21), but more of A's replies are no's. None of these differences is statistically significant (every p is above 0.05). So Lorenzo's premise is right on the counts, but the gap is within noise. The data also gives no sign that A beats B, so retiring A loses nothing we can measure.

## Change list for COO (proposal only, nothing done)

Every step below is a list or campaign change, so each needs Lorenzo's confirmation through COO before anyone makes it. Lead counts are from the 1:00 PM CT pull and will drift as sends go out.
1. **Prerequisite, no Instantly change:** Lorenzo picks a C concept (below). Copywriter writes the C emails, and Lorenzo approves them in the copy doc. Nothing after this starts until the copy is approved.
1. **Stop new first touches on A, but let A send its follow-up email (sequence step 2).** Move each A campaign's not-yet-contacted leads into a holding lead list per niche (Instantly "Move leads to a campaign or list"). Pest A 6aaa096e: 131 leads. PPC A 4e9f0b07: 1,438. Clean A 1bd077f4: 210. A's 400 mid-sequence leads (Pest 135, PPC 131, Clean 134) stay where they are and get the follow-up. The follow-up drew 2 of the 7 positives through 10-26 (~/advero/state/reports/campaign_retro_20261026.md, step table). Inboxes: A's 10 inboxes per campaign keep sending only the follow-up, then go idle. Reverse: move the leads from the holding lists back into the same A campaign. Instantly docs: https://developer.instantly.ai/api-reference/lead/move-leads-to-a-campaign-or-list (Instantly API docs, read 10-27).
1. **Alternative to step 2 (pick one):** pause the three A campaigns today. This stops the follow-up for the 400 mid-sequence leads. Reverse: resume the campaigns.
1. **Pause A when its follow-up tail is done,** that is, when no A lead is still active (about 3 days, since the follow-up goes 3 days after the first email: /workspace/offer_20261027/raw/campaigns.json, sequence delay). Ids: 6aaa096e-d344-4d44-a00a-5d907b9aca19, 4e9f0b07-7854-4323-9084-20648a3998a0, 1bd077f4-93ec-4854-929b-2e867905ad5a. Reverse: resume.
1. **Create three C campaigns as drafts, cloned from each niche's B** (B ids f13b219a, 49cd2de9, 4d9998d5). Clone the same settings: Mon to Sat 7am to 7pm Eastern, daily limit 250, 125 new leads a day, plain text, open and link tracking off, stop on reply and auto-reply (/workspace/offer_20261027/raw/campaigns.json). Use the approved C copy. Name them "Launch 2026-10 | <Niche> | C: <offer> | Live". Inboxes: give each C the retired A inboxes of the same niche, so no inbox's load changes (lists in campaigns.json). Do not activate yet. Depends on: the prerequisite. Reverse: delete the drafts.
1. **Load C from the holding lists:** Pest 131, PPC 1,438, Clean 210, into the matching C. B keeps its own 132, 1,437 and 215. Reverse: move them back to the lists.
1. **Activate the three C campaigns on the same day,** with B still running and both arms at 125 new leads a day. Reverse: pause C. Depends on: Lorenzo's go.
1. **Load more leads, split evenly between B and C in each niche.** A powered test needs this (sizes below). Depends on: Lorenzo's go on loading, which is not active (~/advero/state/reports/cold_email_runway_20261027.md). Pest also depends on MV clearing 1,071 rows, and the approved pest load is on hold for the opener rule (section 5). Reverse: move unsent leads out.
1. **Watch** (no Instantly change): fix the sample size per arm before the test starts and read daily, without stopping early on a lead.

**Runway warning:** at 125 new leads a day, Pest B's 132 and Clean B's 215 uncontacted leads last about 1 and 2 sending days (arithmetic). After that, Pest and Clean B send only follow-ups until more leads are loaded, and Pest C would start with only 131 leads. Without loading, B vs C is in effect a PPC test (1,437 vs 1,438).

## Sample size for B vs C

Method: NIST two-proportion formula, alpha 0.05 two-sided, power 0.8, B baseline 0.18% positives (7/3,815 through 10-26; today B alone is 0.22% and both arms pooled are 0.15%). Computed in /workspace/offer_20261027/stats.py. The formula is n = (1.96 x sqrt(2 x pbar x qbar) + 0.8416 x sqrt(p1q1 + p2q2))^2 / (p1 - p2)^2.
- **C at 0.36% (2x):** 13,045 per arm, 26,090 total.
- **C at 0.5%:** 5,193 per arm, 10,386 total.
- **C at 1.0%:** 1,368 per arm, 2,736 total.
- Pace: daily first touches are capped at 125 per campaign, 750 a day across six. They actually ran 750 a day on 10-20 to 10-24 and 746 on 10-27, but only 65 on 10-26 (a follow-up-heavy day). That averages 652 per sending day over 7 days (Instantly daily analytics, /workspace/offer_20261027/raw/daily_*.json). With C taking A's slots, each arm gets 375 a day.
- **Days to fill both arms (Mon to Sat sending days):** 2x: 34.8 days at 375 per arm (40.0 at the 652 average). 0.5%: 13.8 (15.9). 1.0%: 3.6 (4.2). This replaces the ~850-a-day estimate in section 5, which came from send mix rather than the per-campaign cap.
- Leads available: 3,563 uncontacted in the campaigns now, plus 6,928 loadable staged leads in the live niches (pest 1,138, cleaning 2,066, ppc 3,724). Loadable needs Lorenzo's go (~/advero/state/reports/cold_email_runway_20261027.md). All US good-fit unloaded in those niches is 10,333 (~/advero/state/reports/cold_email_runway_20261027.md).
- **What the current leads can detect:** the 3,563 uncontacted give about 1,780 per arm. At that size C must reach about 0.85% against 0.18% (about 4.7x) to be detected. With the loadable 6,928 added (about 5,245 per arm), C must reach about 0.50%, which is the 0.5% case. All good-fit leads (about 6,950 per arm) give about 0.45%. A 2x test needs about 12,200 more leads than all good-fit staged today (arithmetic).
- Split each niche evenly between B and C. Niches differ in size (Pest is small), so read the pooled result with that in mind.

## Offer C concepts (internal brief, not copy)

Each concept describes an offer: what is promised, the risk reversal, the deliverable and why. None of it is email wording. Price never goes in an email. Any refund, discount or payment-term change is a section 7(c) item and needs Lorenzo. Replies are quoted as data from the case files in ~/advero/state/cases/.

**C1. Free inquiry-response check, report with no call needed. CONCEPT for Lorenzo, not copy.**
- Promise: with the owner's OK, we time how fast their business answers one new inquiry and send a short written report of what happened and what an instant automated answer would change.
- Risk reversal: free, no obligation, and no call is needed to get the report.
- Deliverable: the report. Why: it keeps B's winning angle (new inquiries) and swaps the paid starter package for something they can see first.
- Own data: Marco (Pest B, booked): "If there is no obligation attached I would like to see what's that you offer." Angela (Clean A): "I would be interested in knowing more about your automated systems". Leonardo (Clean B, held call): "I would be interested in hearing about it."
- External: in 1,118,802 first emails, offering to send something got 0.76% replies vs 0.50% for asking for a call, and 0.24% vs 0.09% interested (Sales.co, updated 2026-10-26, https://sales.co/research/cold-email-best-practices). HBR audited 2,241 US companies with a web test lead. 23% never responded, and the average response time was 42 hours. Firms that tried to reach a lead within an hour were nearly 7 times as likely to qualify it (Oldroyd, McElheran and Elkington, Harvard Business Review, March 2011, https://hbr.org/2011/03/the-short-life-of-online-sales-leads; figures read from the article PDF at https://thedenmangroupselling.wordpress.com/wp-content/uploads/2011/03/the-short-life-of-online-sales-leads-harvard-business-review.pdf).
- Constraints: the check runs only after the owner says yes, never as an unannounced test inquiry. Lorenzo has to say who runs the checks and how many fit in a week. Offering a report instead of a call differs from how lorenzo-voice.md asks for a call (section 7(f)).

**C2. Build first, pay only if you keep it (pilot on their real inquiries). CONCEPT for Lorenzo, not copy.**
- Promise: we set up the inquiry-response system on their live inquiries for a fixed pilot window. They pay only if they keep it after the window.
- Risk reversal: nothing paid up front. This replaces pay-then-refund (the 60-day refund) with try-then-pay.
- Deliverable: the working system and a pilot summary of inquiries answered and response times. Why: our only payment-risk replies asked for less money at risk.
- Own data: Dave (PPC B): "If you are paid when we get a paying client, great. Otherwise, no thank you." Lorenzo declined pay-on-results (~/advero/state/reports/cold_email_review_20261027.md, check 2). C2 is not pay-on-results: payment is for the system, not tied to their revenue. Marco's "no obligation" line also applies.
- External: in experiments with 396 participants, free service trials were more likely to be accepted than cost-price or full-price trials. Perceived truthfulness and perceived obligation drove that, and the paper warns free trials may devalue a service (Bednall, Oppewal, Laochumnanvanit and Nguyen, Journal of Services Marketing, 2018-01-09, https://doi.org/10.1108/jsm-12-2016-0420; abstract read via OpenAlex). Caution: a single 10,000-contact split test found case study alone got 3 times the positives of case study plus money-back guarantee (OutboundPhD, 2024-10-28, section 8). Alchemail's case study credits a guarantee, but it was not isolated (2026-03-27, section 8).
- Constraints: pilot length, terms and what "keep" means are Lorenzo's call, and it is a payment-term change (7(c)). No price over email. Our files don't say how many pilots can run at once.

**C2 revised: small paid pilot (Lorenzo 10-27 3:07 PM CT). CONCEPT for Lorenzo, not copy.**

*Lorenzo, 10-27 3:07 PM CT (relayed by COO): "Could we incorporate C2 but with somehow that I make some upfront cash? Cause like just doing work for free hurts Even if it's a little amount of money that'll keep my business going for longer than zero"*

This revises C2. The original C2 above is kept for the record. The change: a small fee up front to build the first piece, and the rest paid only if they keep it. The email may only call it a small paid pilot. No price goes in any email; the fee comes up on the call. Nothing below is email wording, and the copy doc and Instantly were not touched.

**Framing option R1: paid pilot, fee credited toward the full build.**
- Promised: we set up the inquiry-response system on their live inquiries and run it for a fixed pilot window (same core as C2).
- The small upfront fee covers: building the pilot version and running it through the window.
- "Keep it" and when the rest is due: at the end of the window they decide whether to go ahead with the full build. If they go ahead by a set deadline, the fee is credited in full toward it and the rest is due then. If they don't, they owe nothing more. Practitioner sources tie the credit to a deadline: "Most deadlines are between 2-6 weeks" (Karl Sakas, Sakas and Company, 2019-08-28, updated 2025-05-31, https://sakasandcompany.com/start-using-paid-discovery/), and "make it conditional on the client signing the full project by a date stated in the discovery agreement" (Kurt Schmidt, Schmidt Consulting Group, 2026-10-10, https://www.schmidtconsulting.group/blog/paid-discovery-for-agencies/).
- Risk reversal left: the most they can lose is the small fee. Whether they keep what was built if they walk is Lorenzo's call. One agency's version: "If you do not, you keep everything we produced" (IGC, undated, https://www.intelligentgraphicandcode.com/services/build-roadmap).
- Why it should pull replies: it keeps C2's "see it work first" structure but pays for the work (Lorenzo's reason). Own data on upfront money: Tiffany (Flowerhill, September cleaning campaign, before Launch) asked "What is the upfront cost?"; Lorenzo answered with a price range and times, and the thread then stalled (~/advero/state/cases/tiffany_flowerhill_stalled_hold_20261022.json). That is one case, so no conclusion is drawn from it. Dave asked for less money at risk ("If you are paid when we get a paying client, great. Otherwise, no thank you.", ~/advero/state/cases/dave_velocityeffect_payonresults_20261026.json). Related research, not tested on paid offers: agreeing to a small first request made people more likely to agree to a larger one later (Freedman and Fraser, Journal of Personality and Social Psychology, 1966, DOI 10.1037/h0023552, abstract read via OpenAlex https://api.openalex.org/works/doi:10.1037/h0023552).

**Framing option R2: paid first piece, then keep-or-walk on the rest.** **NOT CHOSEN: Lorenzo picked R1 (10-27 3:25 PM CT, per COO's relay).**
- Promised: we build one defined piece of the system, the instant response to new inquiries (B's angle), for a small fee. It goes live on their real inquiries.
- The small upfront fee covers: that one piece, built and live. It is a standalone purchase, not a deposit.
- "Keep it" and when the rest is due: after it has run for the window, they decide whether to buy the rest of the system (for example the follow-up and booking parts). The rest is due only if they say yes. No credit is needed because the first piece was paid for on its own.
- Risk reversal left: they keep a working piece for the small fee, with no obligation to buy more. Whether the 60-day refund also covers the first piece is Lorenzo's call.
- Why it should pull replies: the small purchase is something they keep either way. Schmidt advises one fixed-price piece of work "named for what the client keeps" (https://www.schmidtconsulting.group/blog/paid-discovery-for-agencies/). Marco (Pest B, booked): "If there is no obligation attached I would like to see what's that you offer." (~/advero/state/cases/). The foot-in-the-door finding above applies here too, with the same caveat.

**What R1 and R2 both give up:** a free offer gets more takers than a low price. In experiments with 396 participants, "Free (as opposed to cost or full price) service trials were more likely to be accepted" (Bednall, Oppewal, Laochumnanvanit and Nguyen, Journal of Services Marketing, 2018, abstract via OpenAlex https://api.openalex.org/works/doi:10.1108/jsm-12-2016-0420). Moving from a low positive price to zero, "dramatically more participants choose the cheaper option" (Shampanier, Mazar and Ariely, Marketing Science, 2007, DOI 10.1287/mksc.1060.0254, abstract via OpenAlex https://api.openalex.org/works/doi:10.1287/mksc.1060.0254). The same Bednall abstract also warns "Free trials may actually devalue a service". No source found tests a paid pilot offer in cold email.

**Calls for Lorenzo (all are his; nothing here is decided):**
- Fee level. This is his number to set, so no recommendation is made. Benchmarks only, not recommendations: agencies commonly charge "between $500 to $2,500" for a paid first project, "roughly 5-10%" of a typical future project (Sakas, agency context, https://sakasandcompany.com/start-using-paid-discovery/). For enterprise software pilots, "10-30% of annual contract value", credited in full on conversion (Monetizely, undated, enterprise SaaS, no data shown behind the range, https://www.getmonetizely.com/articles/how-to-structure-enterprise-pilot-program-pricing-effective-proof-of-concept-strategies). Neither comes from local service businesses or cold email. Our files hold no price for the Launch starter package, so a percentage can't be applied.
- Is the fee refundable? Options: not refundable (one agency agreement lists "A client right to end the work at any time without a refund", per Schmidt, https://www.schmidtconsulting.group/blog/paid-discovery-for-agencies/), or covered by the existing 60-day refund. If it is refundable, it is no longer reliable upfront cash, which was the point of his change.
- What counts as "keep it": an active yes by a deadline, or continuing unless they cancel. Also how long the window and the deadline are (Sakas: credit deadlines "between 2-6 weeks").
- Payment timing and method: whether the fee is due before the build starts (Schmidt's checklist lists "Payment of the fee in advance"), when the rest is due, and how they pay. Our Launch files don't define either.
- Who brings up the fee on the call: Lorenzo, since price never goes in an email (standing rule, "Do not email prices", ~/advero/state/cases/ilmi_wed_pick_20260929_opus_in.json). A reply asking the price gets a call, not a number.
- Not the pay-on-results deal: Dave's request ties payment to their revenue ("when we get a paying client"), which Lorenzo declined (~/advero/state/reports/cold_email_review_20261027.md, check 2). R1 and R2 tie payment to the work being built and kept. Dave would still not fit: he said "Otherwise, no thank you."
- This is a 7(c) payment-terms item: for the C arm it replaces the Launch terms (discounted starter package and 60-day refund, per ~/advero/state/reports/instantly_offer_audit_20261020.md) with an upfront fee and the rest on keep.
- R1 or R2, and how many paid pilots can run at once (our files don't say).

**Effect on the B vs C test:**
- Both arms are now paid offers: B is the discounted starter package with a 60-day refund, C is a small paid pilot with the rest on keep. The test asks which payment structure draws more interest. Against a free C, a paid C is expected to draw fewer takers (Bednall; Shampanier, above), and that is the trade Lorenzo chose for upfront cash.
- The email names no price, so reply and positive rates measure the framing. Whether people pay is decided on the call.
- Primary metric stays the positive reply rate, using the sample sizes above.
- Also track per arm: booked calls, held calls, paid pilots (fee received) and keeps (rest paid). These are descriptive only. At B's booked-call rate (3/2,277 = 0.13%), detecting 2x needs 17,836 per arm and 3x needs 5,941 per arm (/workspace/offer_20261027/stats.py formula). That is more than the roughly 5,245 per arm available even with the loadable leads. Our case files and decisions log record no won Launch deal, so paid pilots have no baseline. If Lorenzo wants the verdict based on cash collected, the current leads can't give one.

**Final offer C concept (Lorenzo 10-27 3:25 PM CT). CONCEPT for Lorenzo, not copy.**

*Lorenzo, 10-27 3:25 PM CT (relayed by COO): "Okay, let's go ahead and build C around it."*

Per COO, "it" is COO's 3:21 PM CT recommendation. This agent has not seen the 3:21 text, so everything below is COO's description as relayed, not a reading of that message. Concept only: no email wording, and no price in any email.
- Offer: a paid pilot of the instant reply to new inquiries (B's angle), running on the lead's real inquiries for about 30 days (per COO's relay).
- Fee terms: non-refundable, and credited toward the full build if they upgrade. This is framing R1; R2 is not chosen (per COO's relay).
- Fee amount: about $300 to $500. COO suggestion, unconfirmed; fee is Lorenzo's call. Internal only, never in an email.
- Who raises the fee: Lorenzo, on the call. The email may only frame C as a small paid pilot.
- Why R1 over R2: Lorenzo said a "first piece" doesn't sound like a result to a buyer (per COO's relay).
- Risk left for the lead: the most they can lose is the fee, and nothing more is owed unless they upgrade. The relay doesn't say whether the 60-day refund still applies to the full build.
- This is a 7(c) payment-terms item. For the C arm it replaces the discounted starter package and 60-day refund.

**Still needed before launch:**
1. C copy, written by Lorenzo or put into the approved copy doc. No bot writes it.
1. The fee amount. COO's ~$300 to $500 is unconfirmed.
1. How A winds down: step 2 of the change list (move A's uncontacted leads to holding lists, so A's follow-up still sends) or step 3 (pause A now).
1. Lorenzo's go on loading the 6,928 staged leads (~/advero/state/reports/cold_email_runway_20261027.md).
1. The other open terms: what "keep it" (upgrade) means and its deadline, payment timing and method, and pilot capacity.
1. COO confirms the exact Instantly change list with Lorenzo before anything in Instantly is touched.

**Tracking:**
- Primary metric: the positive reply rate per arm (B vs C), using the sample sizes above.
- Tracked as counts per arm: paid pilots, booked calls, held calls and kept builds (upgrades).
- Caveat: these counts can't prove a winner at current volume. At B's booked-call rate (3/2,277 = 0.13%), detecting 2x needs 17,836 per arm and 3x needs 5,941 per arm, against about 5,245 per arm available even with the loadable leads. Paid pilots have no baseline, because our files record no won Launch deal.


**C3. Tune what you already run, no new software. CONCEPT for Lorenzo, not copy.**
- Promise: we review the follow-up and inquiry automations they already have in their current CRM, then fix the gaps inside those tools.
- Risk reversal: no switching, they keep their tools, and the review comes before any paid work.
- Deliverable: a findings list, then the fixes if they want them. Why: our most common reasoned no's say they already have automation or don't want a new service.
- Own data: Pamela (Clean A): "We already have all our automatizations in palace built in house." Layse (Clean B): "we aren't looking to move forward with any new automation services at this time." Scott (PPC A): "Thanks but all our needs are currently being met." Laura (PPC B, engaged): "Are you using gohighlevel?"
- External: Samuelson and Zeckhauser, "Status quo bias in decision making", Journal of Risk and Uncertainty, March 1988, https://doi.org/10.1007/BF00055564. Only the title and journal were confirmed (via Crossref); the abstract was not read, so no figure is claimed. No source was found that tests this kind of offer in cold email.
- Constraints: Lorenzo must confirm which CRMs we can work in. The review is free, so it is a discount-type item (7(c)). No price over email.

## Gaps
- The Launch A/B emails are not in the approved copy doc. They exist only in Instantly, so the C copy and a record of B should be added there.
- "Positive" uses Instantly's labels. Dave is still labeled interested in Instantly but is Lost in our files. Laura is a question.
- Every A vs B difference is within noise (all p above 0.05).
- Pest B and Clean B are about 1 to 2 sending days from running out of new leads. Loading is not active until Lorenzo's go.
- C2 and C3 touch refund, discount or payment terms, so they need Lorenzo (7(c)). C1 changes the call ask (7(f)).
- Section 7's other tests (CTA, step 3 and the rest) are paused behind B vs C, per Lorenzo's 10-27 call.
- C2 revised: the fee benchmarks come from agency and enterprise SaaS blogs, not local service businesses, and no source tests a paid pilot offer in cold email. Arkes and Blumer (1985, sunk cost) was left out because its abstract could not be read. The doi.org links for the Shampanier and Freedman papers return 403 to our checker, so the doc links their OpenAlex records (200) and gives the DOI as text.
