# No-show recovery for booked discovery calls

Research note, 2026-09-23. Question: what gets a no-show rebooked when the call is a 15-minute Google Meet discovery call, booked from a cold email by the owner of a small US service firm? This note picks up where `reminder_cadence.md` stops. That note owns everything up to 3 minutes after the start time.

**Evidence caveat.** No published study measures B2B no-show rebook rates; an analyst who collected every public B2B no-show figure found none for recovery [15], and vendor "25 to 40% recovered" claims give no sample or method [25]. The evidence below is indirect (lead-response timing, scheduling data, healthcare trials, commitment experiments) and marked as extrapolation where it applies.

## 1. Bottom line

S = scheduled start. The no-show is declared at S+10 (call that D).

- **Move the live save inside the slot.** Today's "still on?" fires at D+5, which is S+15, when the 15-minute call is already over. Recommended sequence:
  1. **S+3, email (plus SMS after A2P):** "I'm on, here's the link, or want me to just call you?" This step is already in `reminder_cadence.md`, so send it once only.
  2. **S+5 to S+8, Lorenzo calls.** Create the task at S+3 so he sees it in time. Leave a 15-second voicemail that names the email thread. After A2P, follow the call with a text.
  3. **D+10 to D+20 (about S+20 to S+30): reschedule email in the same thread.** No blame. Offer 2 or 3 specific times in the next 1 or 2 business days, soonest first, with the booking link as a fallback: "Reply with the one that works."
  4. **Next business day, mid-morning in the lead's time zone:** a one-line SMS repeating the times, updated if any have gone.
  5. **Business day 3 or 4:** a short email with one useful thing specific to their niche and the same soft ask.
  6. **Day 7:** a one-question email with three easy answers: "still want to chat / later (when?) / not a fit".
  7. **Day 14:** close the loop, with no ask beyond the link, then hand off to nurture.
- **Email-only variant (before A2P):** the same steps, with every SMS replaced by a two-line email in the same thread. Keep the S+5 call and add an optional second call task on day 1, since calls need no A2P registration.
- **Any reply stops the sequence.** "Later" goes to nurture, dated to what they said; "not a fit" stops everything and suppresses the lead.
- **Second no-show:** the S+3 nudge, the S+5 call, then one reschedule email with just the link (they pick the time) and a plain "no problem if now is a bad time". One yes/no email on day 3 or 4, then nurture. Any rebook needs a typed "yes" to confirm.
- **Third no-show:** the S+3 nudge only, then a one-line sign-off with no guilt, and nurture. The sequence stops offering times. Lorenzo can still take the call if they reach out.
- **Nurture handoff:** day 14 with no reply (day 4 or 5 after a second no-show; the same day after a third). The first nurture touch comes no sooner than 3 to 4 weeks later, or on the date the lead named.

## 2. Compared with today's sequence

| Today | Verdict | What changes and why | Evidence |
|---|---|---|---|
| 1. D+5 "still on?" SMS + email | **Change (move)** | Fire at S+3, inside the slot. At D+5 the call has ended, so the lead can no longer jump on. Practitioners nudge within 2 to 5 minutes [18]. | Opinion (timing logic), weak (practitioners) |
| 2. D+10 call task | **Change (move)** | Call at S+5 to S+8 and leave a voicemail: 81% of US adults ignore unknown numbers, but 67% check voicemail [11]. | Moderate (voicemail), weak (timing) |
| 3. D+1h reschedule email | **Change** | Send at D+10 to D+20 with 2 or 3 specific times in the next 1 or 2 business days, plus the link. Faster contact and nearer slots both help [1][2][9][16]. | Moderate (extrapolated) |
| 4. Day 1 SMS, other channel | **Keep** (after A2P); email plus optional call before A2P | Text reminders work about as well as phone calls and cost less [5]. | Moderate for reminders (healthcare), weak for rebooking |
| 5. Day 3 value email | **Keep, tighten** | One specific item for their niche plus the same ask. No generic content. | Opinion |
| 6. Day 7 yes/no | **Keep, add a "later" option** | Questions raise reply rates [3]. In one practitioner's data, most replies to final emails asked for a better time [23]. | Weak |
| 7. Day 14 breakup | **Keep as the handoff** | Final emails draw outsized replies in small datasets [23]. The widely quoted "76%" has no sample [24]. Explicit guilt backfires [12]. | Weak |
| Repeat rule (2nd: pair + reschedule; 3rd: pair only) | **Keep the shape, add** a call on the 2nd, a yes/no then nurture, a typed "yes" on any rebook, and nurture straight after the 3rd | Past no-shows are among the strongest predictors of the next one [8]. Model clinics dismissed patients after a third no-show in six months [10]. | Moderate (healthcare) |
| (new) Stop rules | **Add** | Any reply pauses the sequence; "later" sets a nurture date; "not a fit" suppresses. | Opinion |
| (new) Commitment on rebook | **Add** | The lead picks the time, replies "yes" and gets the normal reminders. Active commitment cut missed appointments 18% [6]; writing down a date and time raised follow-through [7]. | Moderate (extrapolated) |

## 3. Findings by question

### Speed and channel
- **Lead response.** In the 2007 MIT/InsideSales study (15,000+ leads, six companies), calling within 5 minutes instead of 30 gave 100x the odds of contact and 21x of qualifying; HBR's 2011 audit of 2,241 US firms found firms trying within an hour nearly 7x as likely to qualify [1]. These were inbound web leads, pre-smartphone. What carries over is "the window closes fast", not the multipliers.
- **Scheduling data:** across 3.5M times proposed through Boomerang, people picked the slots nearest to when the invite arrived, and most booked within 24 hours [2].
- **Practitioners work in minutes.** Aitken emails at 5 minutes and calls at 10 [18]; HeyReach touches at 30 minutes, 24 hours and 72 hours [19]; Cleverly says within a few hours [20]. None publishes outcomes.
- **Channel.** Text reminders raised attendance compared with none (risk ratio 1.14; 7 trials, 5,841 people) and matched phone calls (0.99; 3 trials, 2,509) at lower cost [5] (healthcare, extrapolated). 81% of US adults ignore unknown numbers but 67% check voicemail (n=10,211) [11], so leave a voicemail and text who called. Velocify's 2012 data (about 3.5M lead records) reportedly found texting before any phone contact cut contact odds 39%, while texts after contact raised conversion [13]: B2C inbound, **unverified**. **Recommendation:** email first (it carries the Meet link), then call, then SMS.

### Tone and framing
- **Most no-shows are not a no.** Al Davidson surveyed 330 no-shows over two years, all of whom later agreed to reschedule; 56% said internal events had overwhelmed them [17]. The sample leaves out everyone who never rescheduled, so it overstates the good news.
- **Guilt:** a meta-analysis (26 studies, 7,512 people) found guilt appeals only weakly persuasive (g = 0.19), and appeals that blamed the reader barely worked (g = 0.08, against 0.36 for those that did not) [12]. It also cites an earlier review in which more explicit guilt meant less persuasion [12]. Every practitioner source agrees: assume something came up [18][19][20].
- **What backfires** (practitioner consensus, opinion): passive-aggressive lines, "I waited on the call", "I guess you're not interested", long apologies, and several messages stacked into one hour.

### Specific times, a booking link, or "reply with a time"
- **Boomerang (3.5M proposed times):** one slot got booked 21.6% of the time, two 43.4%, three 51.0%, peaking just above 50% at 7 to 14 [2]. The big jump is from one option to two or three.
- **Gong (304,174 emails):** a specific day and time loses in cold emails but wins in active deals (37% against 15% in Gong's summary) [4]. A lead who already booked is closer to the deal stage.
- **Practitioners disagree.** Cleverly says don't ask prospects to suggest times, since most never do [20]; Aitken proposes times in the next couple of days, while Chili Piper favours letting the lead pick [18]. **Recommendation:** 2 or 3 specific times, link as fallback.
- **Nearer slots get more shows.** Among 2,454 clinic patients, no-shows were 23% within 30 days of booking and 47% beyond [9]; one sales leader's 6,414 meetings showed show rates falling with booking distance [16].

### How many follow-ups, spacing, breakup and value emails
- **Cold-email data** (strangers, so extrapolated): Belkins (7.5M emails, 2025) found steps 2 to 6 produced 58.6% of replies, step 6 added little, and recommends 3 to 5 steps [22]; Instantly suggests 4 to 7 touches, 3 to 4 days apart [21]. Today's 7 touches over 14 days sits at the top of that range: fine for leads who already said yes once, but it should not grow.
- **Breakup emails:** in Lift Enablement's 2,500 emails, breakup emails got 5x the response of mid-sequence follow-ups, and about 55% of replies asked for a better time [23]. HubSpot's "76%" close-the-file figure has no sample, and its author warns it can read as threatening [24].
- **Yes/no emails:** emails asking 1 to 3 questions were 50% more likely to get a reply (40M emails, personal and business mixed) [3].
- **Value emails vs plain asks:** no data. Practitioners use one mid-sequence value touch [19]; Instantly says touches past the seventh need new value [21]. **Opinion.**

### Repeat no-shows and commitment
- Healthcare reviews rank past no-shows among the strongest predictors of the next [8]. Model family-medicine practices called after every no-show and dismissed patients after a third in six months [10]. HeyReach gives repeat no-shows a polite exit [19].
- A deposit does not fit a free 15-minute call (opinion); free commitment does. NHS patients who wrote their own appointment card missed 18% fewer appointments; repeating it aloud cut misses only 3.5% (before/after) [6]. Writing down a date and time for a flu shot raised uptake 4.2 points [7]. So the lead picks the new time and types "yes".

### Nurture handoff
- HeyReach sends early-stage, cold-sourced no-shows to nurture and ends active recovery at 72 hours [19]; Cleverly stops after 2 or 3 attempts over one or two weeks [20]. No study compares handoff points. Day 14 sits in that range; a "later" answer hands off at once.

### Cold-outbound and small-business specifics
- **Expect more no-shows than inbound benchmarks.** RevenueHero's 6,428 mostly inbound meetings had 6.5% no-shows, but 15 to 18% in real estate and education [14]. One sales leader puts average SDR show rates near 60% [16]. The common "25 to 35%" cold-outbound figure is unsourced [25].
- **Owners' schedules** (opinion). Cleaning owners are often on job sites, where phone and text beat email. For bookkeeping and tax firms, a no-show near a filing deadline (March 15, April 15, September 15, October 15) is almost always workload: offer times "after the 15th" and keep nurture out of those weeks.

## 4. Open risks and what to test
- **No baseline.** Per no-show, log: rebooked or not, which touch got the reply, days to rebook, whether the rebooked call happened, closed or not. A rebook that no-shows again is not a recovery.
- **"Never double-offered" rule.** Holding 2 or 3 slots per no-show blocks the calendar. Set a hold time (for example, end of the next business day) and release on reply.
- **Template rule.** Emails with filled-in slot times must still match an approved template exactly; approve templates with slot variables or they fall back to approval cards.
- **Too many touches early.** S+3 email, S+5 call, voicemail, text and D+15 email is five contacts in about 30 minutes. Test folding the reschedule offer into the post-call text.
- **Tests** (40+ no-shows per arm): reschedule email at D+15 vs D+60; 2 times vs 3 vs link only; with vs without the day-3 value email; day-7 email with vs without "later".
- **SMS consent and hours.** Text only a number the lead gave at booking, between 07:00 and 19:00 Central and in the lead's local time.

## 5. Sources
1. AInora, 2026, summary of the MIT/InsideSales Lead Response Management study (Oldroyd, 2007) and HBR's audit (Oldroyd, McElheran, Elkington, 2011). https://ainora.lt/blog/lead-response-time-statistics-every-study-2026 ; HBR original: https://hbr.org/2011/03/the-short-life-of-online-sales-leads (article body not retrieved). Response-time odds, sample sizes and caveats.
2. Boomerang (Brendan Burke), 2023-06-12. https://blog.boomerangapp.com/2023/06/4-myths-and-1-truth-about-scheduling-meetings/ . 3.5M proposed times: booking rate by number of slots offered; people prefer the nearest slots.
3. Boomerang, 2016-02-12. https://blog.boomerangapp.com/2016/02/7-tips-for-getting-more-responses-to-your-emails-with-data/ . 40M emails: 1 to 3 questions lift replies 50%; 50 to 125 words works best.
4. Gong (Devin Reed), 2020, updated 2026. https://www.gong.io/blog/this-surprising-cold-email-cta-will-help-you-book-a-lot-more-meetings . 304,174 emails: interest asks win in cold emails, specific times win in the deal stage.
5. Gurol-Urganci et al., Cochrane Review, 2013. https://www.cochrane.org/evidence/CD007458_mobile-phone-messaging-reminders-attendance-healthcare-appointments . 8 trials, 6,615 people: text reminders compared with none and with phone calls.
6. Martin, Bassi, Dunbar-Rees, JRSM, 2012. https://journals.sagepub.com/doi/full/10.1258/jrsm.2011.110250 (summary: https://thedecisionlab.com/intervention/how-social-norms-reduced-missed-hospital-appointments-by-31-7). Commitment: 18% and 3.5% fewer missed appointments.
7. Milkman et al., PNAS, 2011. https://www.pnas.org/doi/10.1073/pnas.1103170108 (summary: https://chibe.upenn.edu/news/converting-intention-into-action-prompting-people-to-write-down-the-date-and-time-they-planned-to-get-a-flu-vaccine-increased-vaccination-rates/). Writing down a date and time: +4.2 points over a 33.1% baseline.
8. Carreras-García et al., Entropy, 2020. https://pmc.ncbi.nlm.nih.gov/articles/PMC7517206/ . Review of 50 studies: past no-shows and lead time predict no-shows.
9. Drewek et al., The Health Care Manager, 2017. https://journals.lww.com/healthcaremanagerjournal/Fulltext/2017/01000/Lead_Time_to_Appointment_and_No_Show_Rates_for_New.2.aspx . 2,454 patients: 23% vs 47% no-shows by lead time (abstract only).
10. Annals of Family Medicine, 2007, exemplar practices study. https://pmc.ncbi.nlm.nih.gov/articles/PMC2094019/ . A call after every no-show; dismissal after the third in six months.
11. Pew Research Center, 2020-12-14. https://www.pewresearch.org/short-reads/2020/12/14/most-americans-dont-answer-cellphone-calls-from-unknown-numbers/ . n=10,211: 81% don't answer unknown numbers; 67% check voicemail.
12. Peng et al., Frontiers in Psychology, 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC10568480/ . Guilt-appeal meta-analysis; also cites O'Keefe (2000) on explicit guilt.
13. Velocify (Leads360), 2013 press release. https://velocify.com/blog/press-release/study-finds-text-messaging-can-boost-sales-by-328-percent/ . Timing of texts relative to phone contact; site offline, figures from search snippets, **unverified**.
14. RevenueHero, 2024-12. https://www.revenuehero.io/reports/no-show-benchmark-december-02-2024 . 6,428 meetings, 6.5% no-shows, spread by industry.
15. Ivristech, 2026. https://ivristech.com/meeting-no-show-rate/ . Catalogues B2B no-show figures; finds no published recovery rates; flags unsourced ones.
16. Florin Tatulea, 2023-04-22. https://salesflo.substack.com/p/the-data-backed-method-to-reduce . 6,414 meetings: show rate falls the further out a meeting is booked; average SDR show rate about 60%.
17. Al Davidson, MarketingProfs, 2019. https://www.marketingprofs.com/articles/2019/40805/sales-meeting-no-shows-its-not-you-its-them-and-what-you-should-do-next . 330 no-shows who rescheduled: 56% overwhelmed by internal events (page blocked; figures from the search snippet and [19]).
18. Will Aitken, Chili Piper, 2024-05-15. https://www.chilipiper.com/post/will-aitken-guide-no-shows ; also https://www.chilipiper.com/article/how-to-handle-no-shows (2020). Email at 5 minutes, call at 10, empathetic tone, propose near-term times.
19. HeyReach (Nađa Komnenić), 2026-08-04. https://www.heyreach.io/blog/the-no-show-playbook . 30-minute, 24-hour and 72-hour touches; routing by deal stage; polite exit for repeat no-shows.
20. Cleverly (Nick Verity), 2026-08-04. https://www.cleverly.co/blog/no-show-follow-up-templates . Include a booking link, don't ask the lead to suggest times; 2 or 3 attempts, then a breakup email.
21. Instantly, Cold Email Benchmark Report 2026. https://instantly.ai/cold-email-benchmark-report-2026 . 42% of replies come from follow-ups; 4 to 7 touches, 3 to 4 days apart.
22. Belkins, 2026. https://belkins.io/blog/sales-follow-up-statistics . 7.5M emails (2025): 58.6% of replies from steps 2 to 6; 3 to 5 steps recommended.
23. Lift Enablement (Doug Davidoff), 2018-09-27. https://www.liftenablement.com/blog/5-rules-to-effective-breakup-emails . 2,500 emails: breakup emails get 5x the response; most replies ask for a better time.
24. HubSpot (Bryan Kreuzberger), updated 2025-05-08. https://blog.hubspot.com/sales/close-file-email-template . The "76%" close-file claim, no sample; warns it can read as threatening.
25. SalesHive, 2026-07-12. https://saleshive.com/blog/how-to-reduce-b2b-meeting-no-shows . Unsourced claims: 25 to 35% cold-outbound no-shows, and 25 to 40% recovered by re-engaging within 90 minutes.
