# The follow-up sequence (no reply yet)

Read in order: the lead said "interested", Lorenzo replied by hand with two times, silence, then these ten in the same thread. E1 to E7 go out on consecutive business days, E8 two weeks after E7, E9 and E10 weekly. Every email offers {slots} and {booking_url}, opens "Hey {first_name}," and closes "Lorenzo". The scarcity idea builds across E1, E3 and E5 (gone, gone again, they keep filling) rather than repeating.

## Lorenzo's rules for this sequence (2026-09-23, apply to every email)
1. No booking link anywhere. The lead picks one of the two times offered and Lorenzo sends the calendar invite. {booking_url} is gone from every email (set in the section 2 chat, "everywhere").
2. Any email that offers new times after earlier unbooked ones says the earlier times got taken, every time, in different words each time.
3. Email only: no texts or phone steps.
4. No Claudeisms: no sentence or tacked-on clause that restates, sums up or sells the point just made. Test: delete it; if no fact, question or next step is lost, it goes.
5. Normal capitalization.

Walkthrough status: E1 to E7 agreed 2026-09-23. E8 onward still show the editor's drafts below; rules 1 and 2 are applied as each email is walked through.

## E1 · Day 1 · Two fresh times, lightest nudge (AGREED 2026-09-23)
Hey {first_name},

The time slots I sent got filled. Here are 2 more, let me know if they work: {slots}.

Lorenzo

Agreed with Lorenzo 2026-09-23: his own edit from the Google Doc (cadence.d1), with "from yesterday" changed to "I sent" because E1 goes out the next business day (a Friday reply means a Monday E1). No booking link. No no-slots variant (he deleted it).

## E2 · Day 2 · Why this call matters for them (AGREED 2026-09-23)
Hey {first_name},

{research_line}

Fifteen minutes is enough for me to show you how this would run for {company}. Let me know when a good time is to get a call on the books.

Lorenzo

Agreed with Lorenzo 2026-09-23, from his Google Doc edit (cadence.d2): typos fixed ("{company name}" is {company}, missing space), and his "I think this would really benefit {company}" cut because the research line already gives the reason (no-Claudeisms). No times on purpose (his call); E3 brings two times back. No booking link. No no-slots variant (he deleted it).
Approval (his call, 2026-09-23): he approves this frame plus the research-line rules below once. E2 then sends on its own when the line passes every check; any failed check or NONE uses the fixed fallback line for the offer. This is the one engine email whose text is not an exact approved template, so the template gate needs a "frame plus validated research line" path (section 4's `template_gate.py`).
His note on the doc: the research line must tie back into the offer; the email is essentially "here's why I think this call is important".

## E3 · Day 3 · I want this booked (AGREED 2026-09-23)
Hey {first_name},

I really want to get this call on the books with you. Those last two times got taken too.

Would {slots} work instead?

Lorenzo

Agreed with Lorenzo 2026-09-23 (the editor's pick, booking link removed). "Those last two" are E1's times, since E2 offers none. Not chosen: his original wording "Looks like those slots got grabbed up again. I really want to get this call on the books. Do either of these work: {slots}?", because it opens the same way E1 does.

## E4 · Day 4 · Proof it works (AGREED 2026-09-23)
Hey {first_name},

I really think there's a lot of room for growth at {company}. I've built these systems across numerous industries. A few of my favorites:

- {offer_proof}
- an outbound system that raised a software consultancy's qualified lead volume 35%
- $5M in loan applications in 30 days on $1,500 of ad spend for a lender

The first one is the same kind of system I'd build for {company}. Those last two times got booked. Would {slots} work to go over it?

Lorenzo

{offer_proof} by offer type (config/offers.md: one proof per offer type, never mixed):
- Reactivation (cleaning, bookkeeping, recruiting): a win-back system for a commercial roofer doing $150M a year that recovered about $6M worth of contracts within 6 months
- Outbound (cleaning, bookkeeping, recruiting): an outbound system for a commercial roofer doing $150M a year that brought in about $180,000 in new contracts in 90 days

Agreed with Lorenzo 2026-09-23, in three steps: (1) his own list with the industries kept, framed as favorites so it doesn't read as the closest match to their industry (he rejected an industry-free version: "they get confused, like they're garbage"); (2) every item tied back to the offer by naming the system, plus "The first one is the same kind of system I'd build for {company}" ("they need to be applicable to the offer, or else they're useless"); (3) two versions, reactivation and outbound. Wholesaler line dropped (no number on file). "Those last two times" are E3's. Note: config/offers.md words the consultancy proof as "+35% reply rate"; Lorenzo's own case-study wording (used here) is qualified lead volume up 35%.

## E5 · Day 5 · Busy season, two more, what the call is for (AGREED 2026-09-23)
Hey {first_name},

Haven't heard back yet, no worries. It's a busy time of year and the slots keep getting filled.

I'd still like to show you how we'd {offer_line}. Would {slots} work?

Lorenzo

{offer_line} by offer type:
- Reactivation, cleaning and recruiting: win back {company}'s past accounts
- Reactivation, bookkeeping: win back {company}'s past clients
- Outbound (cleaning, bookkeeping, recruiting): get {company} in front of new clients right when they need you

Agreed with Lorenzo 2026-09-23: his wording plus one line tying it to the offer. "The slots keep getting filled" covers the earlier times being gone. Kept (not dropped).

## E6 · Day 6 · A preview of the call (AGREED 2026-09-23)
Hey {first_name},

Here's a preview of what I'd show you on the call.

{preview}

The rest takes about 15 minutes. Those last two times are gone, but I've got {slots} open.

Lorenzo

{preview} by campaign (six fixed templates; Claudeism kickers cut from the outbound lines 2026-09-23):
- Cleaning, reactivation: The first two messages I'd send accounts that cancelled or never signed: "Quick question, who's handling your cleaning these days?" and "Happy to take another look at the space and send a fresh quote. Want me to set that up?"
- Bookkeeping, reactivation: The first two messages I'd send former clients and old inquiries: "Checking in, who's keeping your books these days?" and "Want us to get everything caught up before your next quarterly estimate is due?"
- Recruiting, reactivation: The first two messages I'd send clients who've gone quiet: "Anything you're hiring for this quarter that we could help with?" and "If a role's been open longer than you'd like, send it over and we'll take a first pass."
- Cleaning, outbound: The three things I'd watch for in your area: new office leases, companies moving into bigger space, and buildings that just changed property managers. The outreach goes out under your name.
- Bookkeeping, outbound: The three things I'd watch for in your area: newly registered businesses, companies posting for a part-time bookkeeper, and businesses opening a second location. The outreach goes out under your name.
- Recruiting, outbound: What I'd watch for in your market: specialty roles hitting the job boards, especially ones that sit open for weeks or get reposted. The outreach goes out under your name.

Agreed with Lorenzo 2026-09-23: the preview version (not the priority check, which E7 and E8 carry). Booking link removed; "Those last two times are gone" added (rule 2). The sample messages are the editor's draft of his first touch per niche.

## E7 · Day 7 · Close the week's loop (AGREED 2026-09-23)
Hey {first_name},

Last one from me this week. Should I keep trying to find a time, or is now just not the right moment?

Those last two times went too. If it's still on your list, I can do {slots}.

Lorenzo

Agreed with Lorenzo 2026-09-23 (the editor's pick): "Either answer is totally fine." cut (Claudeism), booking link removed, "Those last two times went too" added (rule 2). "Last one from me this week" kept.
Stop logic (his call, 2026-09-23): a "not now", "bad time" or "not a priority" reply to any follow-up stops the run at once and moves the lead to the 90-day nurture (`nurture.enroll(email, "not_now_reply", now)`).

## E8 · Two weeks later · Relaxed restart, easy out
Hey {first_name},

Been a couple of weeks. Was hoping now was a good time to get a call on the books.

How about {slots}? Or grab any time here: {booking_url}

Let me know if right now is a bad time, or if this just isn't a priority.

Lorenzo

Alternate: none

## E9 · One week later · One observation, two times
Hey {first_name},

Quick thought for you. An account that cancelled or never signed already knows your name, so it's usually an easier conversation than a brand-new lead.

That's where I'd start with you. I'm free {slots}, or grab whatever's open here: {booking_url}

Lorenzo

Alternate: none
Per-offer lines (the observation sentence swaps per campaign; each is true of any business in that niche and claims nothing about the lead; the email above shows Cleaning, reactivation):
Cleaning, reactivation: An account that cancelled or never signed already knows your name, so it's usually an easier conversation than a brand-new lead.
Bookkeeping, reactivation: Quarterly estimates, year-end and tax season each give you a natural reason to check back in with former clients and old inquiries.
Recruiting, reactivation: Clients who hired through you before, or almost did, already know how you work, so they're an easier conversation than any cold account.
Cleaning, outbound: A company moving into new space has to sort out cleaning around move-in, which is the easiest time to be the one they hear from.
Bookkeeping, outbound: A company posting a part-time bookkeeper job has already said out loud it needs help with its books, which is the right moment to show up.
Recruiting, outbound: An open specialty role on a job board is a hiring manager saying in public they need someone, which is the right moment to reach them.

## E10 · One week later · The pause, door open
Hey {first_name},

You wrote back that you were interested, so I didn't want to just go quiet on you.

I'll give you some room and check back in a few months. If you'd rather talk sooner, either {slots} works, or grab any time here whenever you're ready: {booking_url}

Lorenzo

Alternate (shorter, no reminder that they raised their hand):
Hey {first_name},

I'll stop filling your inbox for now and check back in a few months.

If the timing changes before then, either {slots} works, or grab any time here whenever you're ready: {booking_url}

Lorenzo

## Research line (E2): instructions for the AI step (rewritten 2026-09-23 for the agreed E2)
Inputs: the lead's company name, website, city, and which campaign they came from (cleaning, bookkeeping or recruiting; reactivation or outbound). Output: the line only, or the single word NONE. For the log only, never in the email, list the page URL each fact came from.

Where it sits: it is the first thing in the email, right after "Hey {first_name},", and the next sentence is "Fifteen minutes is enough for me to show you how this would run for {company}." So the line is the whole reason for the email: here's why a call is worth it for you.

Rules
1. One or two sentences, 35 words or fewer. One to three facts about their business, then what that means we could do for them under this offer. Stop there.
2. It must tie back into the offer. Reactivation: the facts point to a base of past or lost clients we could win back (years in business, review count, service areas, seasonal or recurring work, stated client counts or partner lists, the specialties they place in). Outbound: the facts point to the triggers we'd watch turning into work for them (cleaning: office or commercial clients, post-construction, property managers, areas covered; bookkeeping: setup packages, monthly books, clients with more than one location, catch-up work; recruiting: the exact roles and industries they place). The tie-back may state the obvious conclusion of a fact (years in business means past clients) but may not add a new claim about their business (churn, revenue, headcount, problems, plans).
3. Lorenzo's first person, plain and spoken, the way he'd say it out loud. Contractions are fine. Normal capitalization. Don't start with "I think", don't open every line with "I saw" or "I noticed", don't mention times, calls or booking (the next sentence does), don't ask a question.
4. No Claudeisms. After the tie-back, stop. Never add a sentence or clause that restates, sums up or sells the point just made. Test: delete it; if no fact is lost, it goes. Wrong: "...so there's a long list of past accounts we could win back for you. That's a real opportunity." Wrong: "...which means more revenue without more ad spend."
5. Facts only from their own website, their reviews, or their listing (Google, Yelp, BBB), after confirming the name and the city or phone number match this lead. Every fact must have a page you can point to.
6. Numbers exactly as found ("since 2011", "180 Google reviews") or rounded down ("over 200"), never up. Quote the year, don't do date math. Review counts, not star ratings.
7. Never: guess ("must be", "probably", "I bet", "looks like you"); market facts not on their own pages; a line that is only praise; anything negative; pricing, fees, percentages, guarantees or results; names of competitors, owners, staff, reviewers or their clients; quoted reviews; dates that could be wrong on the day it sends; any mention of research, tools, AI or automation; URLs, placeholders, em or en dashes, exclamation marks, emojis.
8. Company name the way a person says it: drop LLC, Inc. and taglines.
9. Return NONE when the business can't be confirmed as theirs, the site is down or empty, the only facts are generic, nothing connects to the offer, or the line would need a guess. NONE always beats a stretch.
10. Final check: 35 words or fewer, a source URL per fact, at least one fact tied to the offer, ends at the tie-back, nothing from the Never list.

One example per offer (made-up businesses, for style only; never reuse these names or facts)
- Cleaning, reactivation: Brightline has been cleaning offices around Tampa since 2011 and has over 200 Google reviews, so there's a long list of past accounts we could win back for you.
- Bookkeeping, reactivation: You offer quarterly estimates and monthly books for contractors and restaurants, so every quarterly deadline is a reason we could get your past clients back in touch.
- Recruiting, reactivation: Northgate has been placing accounting and finance people around Charlotte since 2009, so there's a long list of clients who've hired through you before that we could bring back.
- Cleaning, outbound: You handle post-construction cleanup and nightly janitorial for offices around Denver, so every new lease and buildout in town is a job we could put in front of you.
- Bookkeeping, outbound: Tallgrass has a setup package for brand-new businesses in Omaha, so every new business filing there is an owner we could get talking to you.
- Recruiting, outbound: Ironclad places controls engineers and maintenance techs for manufacturers, so every plant that posts one of those roles is a hiring manager we could get you in front of.

Fallback lines (used when the step returns NONE or any check fails; neither claims anything about their business). AGREED 2026-09-23 (the lines already in the Google Doc, tags cadence.d2.research_fallback.*):
- Reactivation (cleaning, bookkeeping, recruiting): The quickest place to start is usually the accounts that already know you and went quiet.
- Outbound (cleaning, bookkeeping, recruiting): The quickest place to start is usually the prospects who are in market right now.

## Notes for Lorenzo
- What changed across the set: E3 now leads with your "I really want to get this call on the books" and E5 keeps your "slots keep getting filled, busy time of year", so the scarcity builds (gone, gone again, they keep filling) instead of repeating E1's line three times. E6 is the value version rather than the priority check, because E7 ("is now the right moment") and E8 ("bad time or not a priority") already carry that beat. Every opener, slot line and booking line is worded differently. E2 drops "in particular" so the fallback version never claims research that didn't happen.
- To fill in: the wholesaler result lives only in E4's alternate, so fill the bracket or delete that line before approving it. {company} is used only in E4; confirm it's never blank for these leads. The E6 sample messages are my draft of your first touch per niche; swap in your real copy if it differs.
- E2 can never match an approved template word for word, because {research_line} is new for every lead. Either approve the E2 frame plus the research rules as one unit, or hold E2 for your OK each time. The NONE version (fixed fallback line) is a normal template and can be approved as usual.
- Stop logic: a "not now", "bad time" or "not a priority" reply to any email has to end the run and move the lead to nurture, or E7's "either answer is fine", E8's "let me know if this isn't a priority" and E10's "check back in a few months" stop being true. E10's "a few months" assumes nurture waits about 90 days; change it if nurture emails sooner.
- Optional wording: E7 opens "Last one from me this week", which tells them the daily run is over and makes the two-week gap feel deliberate. Cut those five words if you'd rather not name the rhythm.
- Structural suggestion, not a change: if the daily week feels heavy once real replies come in, E5 is the one to drop, since E1 and E3 already carry the scarcity and E4 and E6 carry the value.
