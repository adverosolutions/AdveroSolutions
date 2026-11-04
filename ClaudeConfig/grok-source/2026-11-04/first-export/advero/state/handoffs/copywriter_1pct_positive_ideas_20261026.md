# Copywriter section: 1% positive reply goal (v2, cited). 2026-10-26 12:10 CT

Ideas only. Nothing goes into Instantly or the approved copy doc without Lorenzo's own yes. No example email copy in this file. Pricing is left out of every idea. Earlier speculative version kept at `copywriter_1pct_positive_ideas_20261026.md.bak-v1`.

Labels used for our own data (every line names one):
- **retro** = `~/advero/state/reports/campaign_retro_20261026.md` (Instantly API pull, 2026-10-26 11:30 to 11:35 CT)
- **raw** = `/workspace/retro_20261026/raw/campaigns.json` (live step bodies) and `.../raw/steps_*.json` (per-step sends and replies)
- **leads** = `/workspace/retro_20261026/raw/leads_*.json` (per-lead `{{personalization}}` lines)
- **voice** = `~/advero/skills/lorenzo-voice.md`
- **CEM brief** = Cold Email Manager's requirements relayed 2026-10-26 (Deliverability constraints)

External sources carry publisher, date and URL inline. Full list at the bottom. Anything without a source is marked **UNSOURCED**.

Small-sample warning (applies to every idea): each live campaign has 4 to 13 replies and 0 to 2 positives (retro, main table). The retro itself says differences between campaigns "are not statistically solid yet" (retro, Notes per campaign).

---

## Top 3 angle or offer directions

**1. Make "new inquiry response" the main angle.**
- Why: B campaigns got 5 positives of 17 replies, A campaigns 2 of 24, with 19 of the A replies marked not interested (retro, Takeaways). Retro calls this "a lean, not proof" (retro).
- External: no source found that tests this angle against a quote or proposal follow-up angle. Own data only.
- Fits: PPC first. PPC A has 0 positives on 635 contacted and 1,561 leads not yet contacted (retro, PPC A row). Moving those leads to a B-style campaign is a lead list change and needs Lorenzo's yes (retro, PPC A note).

**2. Swap the meeting ask for an offer to send something (a short Loom walkthrough, sent only after they reply).**
- Why, own data: every live step 1 and step 2 ends with an offer of two times plus a calendar link for a 15-minute chat (raw, all six campaigns). Our positive share is 7 of 41 replies, 17% (retro, totals).
- Why, external: in 1,118,802 first emails, offering to send something got 0.76% human replies per email against 0.50% for asking for a call, and 0.24% vs 0.09% interested replies (Sales.co, updated 2026-10-26, https://sales.co/research/cold-email-best-practices). Gong Labs found the interest CTA was the best cold email CTA in 304,174 emails, with success defined as a meeting booked within 10 days (Gong, published 2020-05-27, https://www.gong.io/blog/this-surprising-cold-email-cta-will-help-you-book-a-lot-more-meetings). Gong's own post gives the figures as 30% for interest CTAs against 15% specific and 13% open-ended (Gong on the Sales 3.0 Conference blog, 2020-10-08, https://www.sales30conf.com/blog/these-email-ctas-will-help-you-book-more-meetings/). Hunter reports that open-ended asks such as offering more info are preferred by decision makers over scheduling a meeting upfront (Hunter, State of Email Outreach 2026, no date on page, 2025 data, https://hunter.io/state-of-cold-email).
- Constraint: no link in the email. The Loom is offered as "reply and I'll send it". Any link in a later step needs Deliverability's sign-off first (CEM brief).
- Constraint: voice says email asks are always a 15-minute call with two open times plus the booking link (voice, "How he asks for a call"). Changing the ask is Lorenzo's call.
- Fits: all six. Best sample is PPC B, which has 1,560 leads not yet contacted (retro, PPC B row).

**3. Add a step 3 that brings a different angle, not a reminder.**
- Why, own data: the sequence stops at step 2. Step 2 drew 10 of 41 replies and 2 of 7 positives (retro, step table).
- Why, external: Instantly found 58% of replies come from step 1 and 42% from follow-ups, recommends 4 to 7 touchpoints, and says each follow-up should add a new value or angle and never be just "checking in" (Instantly, updated 2026-01-12, https://instantly.ai/cold-email-benchmark-report-2026). Belkins found step 3 books more meetings than steps 1 and 2 combined, with 53.5% of email-sourced meetings coming from steps 3 to 5, and recommends 3 to 5 steps (Belkins, updated 2026-06-26, https://belkins.io/blog/sales-follow-up-statistics). Hunter found three messages total was best and that following up three or more times lowered the average reply rate (Hunter, https://hunter.io/state-of-cold-email).
- Fits: A campaigns first (Pest A, Clean A), where step 3 can carry the new inquiry angle that leans better in our data (retro, Takeaways).

---

## The math (arithmetic, a scenario, not a benchmark)

- Today: 7 positives / 3,815 contacted = 0.18% (retro, totals).
- 1% of 3,815 = about 38 positives (arithmetic).
- Funnel today: 41 replies / 3,815 = 1.07% replies x 7/41 = 17% positive (retro, totals; arithmetic).
- 1% = 2.5% replies x 40% positive (arithmetic, not sourced). The **40% positive** figure is **UNSOURCED**. It is one way to make the product equal 1%, nothing more.
- At today's 17% positive share, 1% needs about 5.9% replies (arithmetic). At today's 1.07% replies, 1% needs about 93% of replies positive (arithmetic). So both numbers have to move.
- External context, different denominators: Sales.co's 2M+ email set shows 14.1% of all replies positive (auto-replies included) and an interested rate of about 0.64% of contacts emailed (Sales.co, published 2026-02-04, updated 2026-09-03, https://sales.co/research/cold-email-statistics). Our comparable share with auto-replies included is 7 / 82 = 8.5% (retro, 41 replies + 41 auto-replies; arithmetic).
- Woodpecker's A/B calculator labels a 1% interested rate "top campaigns", as an illustrative baseline rather than a percentile (Woodpecker, 2026-08-27, https://woodpecker.co/cold-email-ab-test-calculator/). So 1% is a top-tier target, not an average.

## How to read the tests (sample size)

- Woodpecker's table says that at a 0.5% interested rate, detecting a +100% lift needs about 3,556 prospects per version, and +200% needs about 985 (Woodpecker, 2026-08-27, https://woodpecker.co/cold-email-ab-test-calculator/).
- Our arms are about 635 contacted each (retro, main table), and 4,309 leads are left uncontacted across the six (retro, "Not yet contacted" column; arithmetic).
- So no single-campaign test can confirm a positive-rate win. Pool the same change across campaigns, or read replies first and positives as a lean (arithmetic from the figures above).
- Change one variable per test (Woodpecker, same page: "Change one thing at a time").
- Send cap is 1,500 a day (CEM brief). Today's six campaigns send about 245 to 250 a day each (retro, daily sends), which is about 1,470 to 1,500 a day (arithmetic). A step 3 shares those slots with first touches, so new leads get contacted more slowly.

---

## Ideas (each with own data, external sources, and one test)

### 1. Angle: new inquiry response over quote or proposal follow-up
- (a) Own data: B 5 positives of 17 replies vs A 2 of 24 (retro, Takeaways). Pest A has the most replies (13) but 11 are not interested (retro, Pest A note). PPC A has 0 positives (retro, PPC A row). Small sample (retro).
- (b) External: none found that tests this angle. Own data only.
- (c) Test: put a B-style body on PPC A's 1,561 uncontacted leads, compared against PPC B. The only change is the angle. This needs Lorenzo's yes for the list change (retro, PPC A note).

### 2. CTA: offer to send a Loom on reply instead of times plus a calendar link
- (a) Own data: all live steps use the two-times-plus-calendar-link ask (raw). Positive share is 17% (retro). History can't isolate the CTA, because the old campaigns changed offer, list and bounce rate together (raw, historical bodies; retro, paused table, bounce 1.02% to 5.21%).
- (b) External: Sales.co 0.76% vs 0.50% replies, 0.24% vs 0.09% interested (https://sales.co/research/cold-email-best-practices, 2026-10-26). Gong interest CTA 30% vs 15% and 13% (Gong 2020-05-27 and 2020-10-08 URLs above). Hunter says low-pressure asks are preferred (https://hunter.io/state-of-cold-email).
- Earlier claim "a Loom ask is lower friction": now sourced to Sales.co (offering to send something), Gong (interest CTA) and Hunter. A Loom specifically is **UNSOURCED**. Sales.co's measured offers include "a short video", so it is the closest match (Sales.co page above).
- (c) Test: same body, CTA only. Control keeps the current ask. Variant offers a short Loom sent after they reply, with no link (CEM brief). Start on PPC B (1,560 uncontacted; retro).

### 3. Step 3 (and possibly step 4)
- (a) Own data: step 2 gave 10 replies and 2 positives (retro). Per send, step 1 got 31 replies on 3,815 sends (0.81%) and step 2 got 10 on 2,892 (0.35%) (retro step table; arithmetic). In the paused campaigns, step 2 drew 10 of 31 replies (raw, `steps_*.json` for the six paused campaigns; arithmetic).
- (b) External: Instantly says 4 to 7 touches and at least 4 emails (https://instantly.ai/cold-email-benchmark-report-2026, 2026-01-12). Belkins says 3 to 5 steps, with step 3 as the top meeting step (https://belkins.io/blog/sales-follow-up-statistics, 2026-06-26). Hunter says 3 total is best and more lowers the average (https://hunter.io/state-of-cold-email). Sales.co's 2M set found 79.4% of replies came from the first message (https://sales.co/research/cold-email-statistics, 2026-09-03).
- Earlier claim "extra steps lift replies": sourced for step 3 (Instantly, Belkins and Hunter agree). Step 4 is contested (Instantly and Belkins for, Hunter against). Our data **cannot show it** because we have never sent a step 3.
- (c) Test: add step 3 to Pest A and Clean A, with a new angle and no new proof (one approved proof per offer type; voice, proof rules). Compare step 3's reply and positive counts against step 2's. Mind the 1,500 a day cap (CEM brief).

### 4. Rewrite step 2 as a new angle, not a "got buried" reminder
- (a) Own data: step 2 opens by saying the first email may have got buried, then repeats the step 1 proof word for word (raw, step 2, all six). It still produced 2 of 7 positives (retro).
- (b) External: Instantly says each follow-up should add new value, never just check in, and that step 2 emails that feel like replies do about 30% better than formal follow-ups (https://instantly.ai/cold-email-benchmark-report-2026). Our step 2 already sends in the same thread (raw, step 2 has no subject; `copy_doc_approved.txt` note).
- (c) Test: on one campaign, change only the step 2 body to a new angle or pain, with the same CTA as step 1.

### 5. Personalization line: open question with Lorenzo, hold any test
- **Open question with Lorenzo:** the pest openers are already an open item with him. The live form is "I know that you do {x}. Congrats on ...", and the pack's template is different (CEM brief). The live lines start "Hey {name}, I know that you do" on 100% of leads in all six campaigns (leads, 8,120 of 8,120). voice's final form (2026-09-07) is a different fixed sentence (voice, "Personalization lines").
- (a) Own data: none are empty (leads, 0 empty). In the pest campaigns, the most common praise sentence is the same on 123 of 894 Pest A leads and 104 of 893 Pest B leads (leads, `6aaa096e`, `f13b219a`). Median personalization is 31 to 35 words (leads).
- (b) External: Backlinko and Pitchbox found personalized bodies got a 32.7% better response rate (20.3% vs 15.3%) in 12M emails (Backlinko, 2019-04-16, https://backlinko.com/email-outreach-study). Hunter found two custom attributes gave a +56% reply rate over none (5.6% vs 3.6%) (https://hunter.io/state-of-cold-email). Neither tests our two forms against each other.
- The personalization audit (comparing positives against not-interested replies line by line) is **UNSOURCED**. It is a proposed check, not yet done, and 7 positives is too few to read on its own (retro).
- (c) Test: none until Lorenzo settles the form. After that, change the opener form only.

### 6. Subject lines: stop the tie test, try a descriptive subject
- (a) Own data: v0 "{{firstName}}, quick question" got 16 replies and v1 "{{firstName}}, quick one?" got 15, on about 1,900 sends each, with identical bodies (retro). The two subjects barely differ, so the test can't say anything more (retro).
- (b) External: Hunter found "quick question" subjects underperform, 2.5% reply vs 2.9% for other subjects (https://hunter.io/state-of-cold-email). Sales.co found 5 to 7 word subjects beat 1 to 2 words (0.78% vs 0.49%), and that the first name in the subject helps (0.30% vs 0.18% interested) (https://sales.co/research/cold-email-best-practices). Backlinko found 36 to 50 characters best, at 22.3% (https://backlinko.com/email-outreach-study, 2019).
- (c) Test: keep the first name, change only the subject to a 5 to 7 word line naming their workflow. Low priority, because subjects move replies more than the positive share.

### 7. Length and layout (sources conflict, lower priority)
- (a) Own data: step 1 bodies are 94 to 102 words before the opener (raw), or about 124 to 136 words with the median opener (leads; arithmetic). There are 4 paragraphs before the sign-off (raw, HTML `<p>` blocks).
- (b) External: Instantly says elite first touches stay under 80 words (https://instantly.ai/cold-email-benchmark-report-2026). Gong says 30 to 150 words books more meetings than shorter emails (Gong, 2021-10-20, https://www.gong.io/blog/cold-email-stats). Sales.co found word count made no clear difference, but 1 to 2 paragraphs beat 7 or more (0.83% vs 0.55%) (https://sales.co/research/cold-email-best-practices). Hunter found both 61 to 80 and 181 to 200 words did well (https://hunter.io/state-of-cold-email). Lavender found mobile-friendly emails get 83% more replies on average (Lavender, 2026-02-23, https://lavender.ai/blog/5-takeaways-from-our-latest-cold-email-benchmark-report).
- (c) Test: only after ideas 2 and 3. A shorter body with the same proof and the same CTA.

---

## Flags for Lorenzo

- **Proof relevance and ROI framing (his call, approved proof stays word for word).** Our only launch proof is a roofing dollar result, sent to pest, PPC and cleaning (raw; `~/advero/state/communities/approved_proof.md`, item 3). Gong found ROI language in cold emails cut success rates by 15% (https://www.gong.io/blog/cold-email-stats, 2021-10-20). Lavender says proof without relevance doesn't convert (https://lavender.ai/blog/5-takeaways-from-our-latest-cold-email-benchmark-report, 2026-02-23). Sales.co found % or Nx stats lowered replies, but our proof is a dollar figure, not a % or Nx (https://sales.co/research/cold-email-best-practices). No change is proposed. Testing without the proof, or with different proof, is only his decision.
- **The CTA change (idea 2)** goes against voice's standing rule on how he asks for a call (voice). It needs his yes.
- **Lead list moves (idea 1)** need his yes (retro).

## Decision for Lorenzo (yes / no)

Live step 1 in all six campaigns includes a "discounted starter package" and a 60-day full refund if the client is unhappy (raw, step 1, all six). Step 2 includes neither (raw).

- **Test step 1 without the refund guarantee? Yes / No.**
  - External: one 10,000-contact split test (5,000 per arm, a Facebook ads offer) found case study alone got 3 times the positive responses of case study plus money-back guarantee (OutboundPhD on LinkedIn, 2024-10-28, https://www.linkedin.com/posts/outboundphd_we-sent-two-campaigns-as-a-split-test-heres-activity-7256758515803865088-D9Vz). That is a single anecdotal test from another offer.
  - Counterpoint: Alchemail's case study says a guarantee helped its campaign, but it was not isolated as a test (Alchemail, 2026-03-27, https://alchemail.io/blog/how-we-booked-40-meetings-90-days-loyalty-app).
- **Test step 1 without "discounted starter package"? Yes / No.** No external source found on discount framing in cold email (**UNSOURCED**).
- If yes to either, change one at a time, on pooled campaigns (see sample size above).

## Combine or cut from Split Test Bot's tests (pending their list)

_Placeholder. To fill when Split Test Bot's list arrives: map each of their tests to ideas 1 to 7 above, merge overlaps, and keep one variable per arm under the 1,500 a day cap._

---

## Dropped, and why
- Historical CTA comparison (old "reply yes" asks vs live asks): confounded by different offers, lists and bounce rates of 1.02% to 5.21% (retro, paused table).
- Discount framing as an idea: no source found. It appears only in the Decision section.
- Lavender's "25 to 50 word" LinkedIn claim: not fetched from a primary page, so not used.
- BusySeed percentage-proof study: observational, and our proof is not a percentage.
- Backlinko's multi-contact finding: not a copy lever.

## Sources (all fetched 2026-10-26 by WebFetch or curl, HTTP 200, finding present)
1. Instantly, "Cold Email Benchmark Report: Reply Rates, Deliverability and Trends", updated 2026-01-12. https://instantly.ai/cold-email-benchmark-report-2026
2. Belkins, "Sales follow-up statistics in B2B: Belkins' 2026 study", updated 2026-06-26. https://belkins.io/blog/sales-follow-up-statistics
3. Hunter, "State of Email Outreach 2026" (2025 data, no date on page). https://hunter.io/state-of-cold-email
4. Gong, "Cold Email CTA That Books More Meetings", published 2020-05-27. https://www.gong.io/blog/this-surprising-cold-email-cta-will-help-you-book-a-lot-more-meetings
5. Gong (on the Sales 3.0 Conference blog), "These Email CTAs Will Help You Book More Meetings", 2020-10-08. https://www.sales30conf.com/blog/these-email-ctas-will-help-you-book-more-meetings/
6. Gong, "Analyzing Cold Email Statistics for Better Sales Engagement", published 2021-10-20. https://www.gong.io/blog/cold-email-stats
7. Sales.co, "Cold email best practices: 11 rules from 1,118,802 emails we sent", updated 2026-10-26. https://sales.co/research/cold-email-best-practices
8. Sales.co, "Cold Email Statistics (2026)", published 2026-02-04, updated 2026-09-03. https://sales.co/research/cold-email-statistics
9. Woodpecker, "Free cold email A/B test calculator", 2026-08-27. https://woodpecker.co/cold-email-ab-test-calculator/
10. Backlinko, "We Analyzed 12 Million Outreach Emails", 2019-04-16. https://backlinko.com/email-outreach-study
11. Lavender, "5 Takeaways from Our Latest Cold Email Benchmark Report", 2026-02-23. https://lavender.ai/blog/5-takeaways-from-our-latest-cold-email-benchmark-report
12. OutboundPhD (LinkedIn post), money-back guarantee split test, 2024-10-28. https://www.linkedin.com/posts/outboundphd_we-sent-two-campaigns-as-a-split-test-heres-activity-7256758515803865088-D9Vz
13. Alchemail, "How We Booked 40+ Meetings in 90 Days for a Loyalty App Company", 2026-03-27. https://alchemail.io/blog/how-we-booked-40-meetings-90-days-loyalty-app
