---
name: linkedin-content
description: "Draft or review Lorenzo’s LinkedIn content from real material and approved proof. Use for posts, content-calendar work and LinkedIn drafts; Lorenzo approves and publishes."
---

# LinkedIn content

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- LinkedIn Manager inherited the content seat on November 4. The current handoff keeps this lane drafts-only: Lorenzo approves and publishes LinkedIn posts.
- Use real material and approved proof, no invented client results or sprint claims. The current guidance favors a useful, honest recommendation and a closing question rather than a comment-keyword CTA.
- The November 2 v2 post and content dashboard are source records with pending approval. Do not treat a scheduled draft or an image as a published or approved post. The generic four-post cadence below is not evidence that those posts were sent.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)
- [linkedin-content-bot_to_linkedin-manager_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/linkedin-content-bot_to_linkedin-manager_20261104.md)
- [linkedin_content_plan.md](../../grok-source/2026-11-04/first-export/advero/state/linkedin_content_plan.md)
- [linkedin-manager.md](../../grok-source/2026-11-04/third-export/routine_exports/linkedin-manager.md)


Posts that make Lorenzo, founder of AdveroSolutions, look like a builder who is
in the middle of it right now. They go into a Google Sheet queue. Lorenzo reads
them, edits, and pastes them into LinkedIn's own scheduler. Nothing here posts
to LinkedIn.

Why he posts (2026-10-06): LinkedIn outreach is his third acquisition channel
(connection requests plus personal Loom DMs). Prospects who keep seeing his
posts about the offer and the buyer recognize him when the DM lands. So every
post is about what he sells, who he sells it to, how he builds it, or him.

## The rule: real material only (Lorenzo, 2026-10-06)

Opus drafts only from real material. Every number and every story in a draft
traces to a named source from the list in "Allowed sources" below. No
invented stats, tests, sample sizes, client anecdotes, conversations or quotes.

His old posts broke this ("I tracked 847 leads", "I've tested 47 different sequences",
"I tested this on three contractors"). None of those happened, and he is
deleting them. Never write a line like them.

- An opinion needs no source. A fact, a number or an event does.
- If a post needs a number and no source has one, write it without the number.
- If there is not enough real material for the batch, stop and ask Lorenzo for
  it (a call, a build, a campaign number, something that happened this week).
  Do not fill the gap with a made-up story or a softer invented one.
- Each queued row records its source in the Source column (H). No row is ever
  queued without its source.
- Never run `execution/linkedin_content_generator.py` or the
  `generate_linkedin_content.md` directive for posts, and never use
  `execution/linkedin_post_profile.json` or `execution/linkedin_swipe_file.json`
  as a source. The profile's `what_you_can_fabricate` and `believable_numbers`
  sections are void, and the swipe file's example results are invented.

## Who does what

| Step | Who |
|---|---|
| Write the posts | Claude Opus 5.5 |
| Put them in the sheet queue | whoever runs the batch (Claude Code or Grok Bot), with the exact text Opus wrote |
| Edit, schedule, post | Lorenzo, by hand in LinkedIn |
| Engagement numbers | Lorenzo types them in the sheet after posting |

Grok Bot never writes, rewrites, shortens or picks a post. If a post needs a
change, it goes back to Opus or to Lorenzo.

## Positioning

From his website (`Desktop/AdveroSolutions/Website/index.html`): "AI agents
for service businesses. Leads in. Calls booked. One team builds and runs every
AI agent your business needs."

The buyer is a service business that closes new business on a call, a
walkthrough or a quote: staffing and recruiting, commercial cleaning,
bookkeeping, insurance brokers, landscaping, marketing agencies, MSPs, pest
control, roofing, and the like. The line is how they sell, not what they sell.

The agents: reply and booking, lead research, follow-up and win-back,
receptionist (text and chat), ops, and custom agents.

Never make it read as "we specialize in everything". A post is about one
buyer's problem or one agent at a time. Name an industry only as an example of
the "close on a call, walkthrough or quote" buyer, and never stack a long list
of industries in a post.

## Allowed sources

For any fact, number or story:

1. Lorenzo's call notes and call transcripts.
2. Builds he did, including Upwork builds (what was built, for what kind of
   business, what it does). No client names.
3. His own campaign numbers (Instantly, the daily metrics tracker), when he
   supplies them or they are read from his own tracker for that post.
4. His own wins, as he tells them.
5. Anything he tells Claude for the batch.
6. The approved proof list below.

### Approved proof (exact; only these numbers unless Lorenzo supplies new ones)

- A commercial roofer doing $150M a year recovered about $6M in contracts
  within 6 months (reactivation).
- The same roofer got about $180,000 in new contracts in 90 days (outbound).
- $750M+ in annual bid volume runs through a routing and follow-up system he
  built for a commercial roofing contractor.
- $5M in loan applications in 30 days on $1,500 of ad spend, for a lender.
- A software consultancy's qualified leads up 35%.
- His own agency to $10,000 a month.
- His own business runs on the system: 100k+ emails a month, with an agent
  researching and writing each message.

Keep "about" where the list has it. The wording can be shortened to fit a
post, but every number and fact stays exact. No prices, retainers or
guarantee amounts from his offers, ever.

### Transcript to angles

After a discovery call, Lorenzo can hand over the transcript or notes. Opus
pulls about 10 post angles from it, each tied to the moment in the call it came
from. Lorenzo picks the real ones. Only picked angles become drafts. No names,
company names or identifying details from the call go into a post unless
Lorenzo clears them.

### Off limits

Revenue claims above the list, a client count, a headcount or named hires,
years of track record, awards, press, investors, any client or company name,
prices or guarantee figures. "We" for the team that builds is fine, as on the
website.

## Cadence

- 4 posts a week, on 4 different days.
- A personal post about every 2 weeks (so about 1 in 8). Personal posts did
  about 5x better than the rest in the playbook Lorenzo follows. Personal means
  his own life and journey as he tells it, not a business lesson in disguise.
- A personal post is Pillar 5 and its Source starts with "personal:" (e.g.
  "personal: Lorenzo, chat 2026-10-06"). Before a batch, the writer reads the
  previous week's rows. If none of them is personal, this week needs one.
- A personal post needs Lorenzo's material, so ask him for it. Never write one
  without it.
- Post about the offer and the buyer consistently, so connections keep seeing
  the same thing from him.

## The 5 pillars

| # | Pillar | Share of posts | Voice | Topic seeds |
|---|---|---|---|---|
| 1 | Speed to lead, replies and booking | 25% | builder who has watched leads go cold | the gap between a lead coming in and someone answering, what a reply agent says first, booking the call in the reply, after-hours and weekend leads, quote requests that sit, the receptionist agent on text and chat |
| 2 | Reactivation of past customers and lost proposals | 20% | operator who knows where the money is already sitting | the list of past customers nobody emails, quotes and proposals that went quiet, why old leads answer, win-back timing, the roofer reactivation result |
| 3 | Building AI agents in public | 25% | builder showing the real system | his own system (100k+ emails a month, research agent per message), what an agent does step by step, what broke this week and the fix, a recent Upwork or client build, research, follow-up and ops agents, custom agents for one odd job |
| 4 | Sales | 15% | closer who respects the buyer | one-call close, the 15-minute call, "let me think about it", "too expensive", follow-up that is not annoying, angles from his own discovery calls |
| 5 | Founder journey | 15% | raw, honest founder | the personal post every 2 weeks, why he started AdveroSolutions, the move to AI agents, LinkedIn as a new channel, early failures, balancing building with selling |

Every pillar 1-4 post draws its facts from the Allowed sources list. Pillar 5 draws
only from what Lorenzo tells Claude about his life and business.

## The 7 post types

| Type | Structure | Share | Best pillars |
|---|---|---|---|
| Hook + Story | scroll-stopping first line, 2-3 short paragraphs of a real story (sourced), the lesson, a question | 25% | Founder journey, Reactivation, Sales |
| Hot Take | contrarian line, 2-3 lines of reasoning, a reframe | 20% | Speed to lead, Sales, Building |
| Listicle | "X mistakes / lessons", numbered items of 1-2 lines, one closing thought | 15% | Speed to lead, Sales, Reactivation |
| Data / Results | a number from the proof list or a sourced campaign number, what was done, why it worked, the takeaway | 15% | Reactivation, Building |
| Question / Poll | provocative question, 2-3 lines of context, invite answers | 10% | Sales, Speed to lead |
| How-To | the problem, 3-5 steps, the result | 10% | Speed to lead, Building |
| Behind-the-Scenes | what he is building right now, why, early results or snags, what is next | 5% | Building, Founder journey |

Mix types across a week. Do not repeat an angle from the last 50 posts in the
sheet: read them first.

## Hooks that fit

Contrarian Open, Specific Number Open, Confession, Bold Claim, Before/After,
Question Hook, Pattern Break List, Unpopular Opinion, This vs That, One Line
Story. The first ~210 characters show before LinkedIn's "see more" fold, so
the hook and the line after it have to earn the click.

A Specific Number Open uses a number from the proof list or a named source,
never one made up for the hook. Examples that pass:

- "A roofer doing $150M a year recovered about $6M in contracts from accounts he already had."
- "$750M+ in bids a year, and every one gets a follow-up."
- "100k+ emails a month go out of my own business, and an agent researches and writes every one."

## Format rules

- First line is the hook. Never start the post with the word "I".
- One thought per line. Break after every 1-2 sentences, blank line between
  paragraphs.
- 800 to 1,500 characters is the target; never over 1,800.
- Bold (`**text**`) at most 2-3 times. Bullets use "•" unless it is a sequence.
- End with a question or one bold line, never both.
- Hashtags: 0 to 3, on the last line only, after a blank line. None in the body.
- Emojis: 0 to 2, only where natural. Zero is fine.
- No em dashes or en dashes. Use a period or a comma.
- No Claudeisms: follow the `claudeisms` skill. No closing line that restates
  or sells the point just made. A closing question is fine; "That's the whole
  point." is not.
- Normal capitalization. Contractions, fragments, mixed sentence length.

Closers that work: "Which one hit hardest?", "Agree or disagree?", "What's your
experience with <topic>?", or a bold line some will disagree with.

## Voice

Follow the `lorenzo-voice` skill for the base rules (the bar test, peer not
vendor, never invent, no dashes) and the `claudeisms` skill. LinkedIn adds the
following on top.

Where this skill's format rules differ from lorenzo-voice's email mechanics
(plain text, no bold, no bullets, greeting, sign-off), this skill wins for
posts.

Early-stage founder, solo, grinding, present tense. Confident, not arrogant.
Opinionated. Builder who ships. Direct. Shares what he is learning instead of
teaching from a pedestal.

Does not sound like: a guru, a LinkedIn influencer farming engagement, someone
who has "made it", corporate polish, a lecture.

His hot takes (adapted from his 2026-04 list to the broad positioning; they are
opinions, so they need no source):
- AI will replace the service businesses that refuse to adapt.
- Cold email works better than ads for most service businesses.
- The service businesses that win are the ones that answer first.
- One-call close is the only model that makes sense when you sell on a call.
- Better systems for the leads you already have beat more leads.
- Building in public is the best sales strategy nobody in this space is doing.
- Referrals are great, but you can't plan a business around them.
- "I get all my work from word of mouth" is one bad month away from panic.
- Showing up consistently beats being talented inconsistently.

New, needs Lorenzo's OK before use:
- Your past customers and lost quotes are the cheapest leads you will ever get.

## The sheet

Tab "LinkedIn Queue" in the LinkedIn content calendar sheet. One row per post:

| Column | Value |
|---|---|
| Date | YYYY-MM-DD (default days in "Batch defaults" below) |
| Time Slot | default 7:00 AM; one of 7:00 AM, 8:30 AM, 10:00 AM, 11:30 AM, 12:30 PM, 2:00 PM, 3:30 PM, 5:00 PM, 6:30 PM, 8:00 PM |
| Pillar | 1-5 |
| Post Type | one of the 7 types |
| Content | the full post, ready to paste |
| Status | Generated, then Lorenzo moves it to Scheduled and Posted |
| Engagement | Lorenzo types it after posting |
| Source | where every fact and story came from, e.g. "proof list: roofer $6M reactivation", "call transcript 2026-10-08 (cleaning co)", "Upwork build: recruiting follow-up agent", "Lorenzo, chat 2026-10-06", or "opinion, no facts" |

The Source column is new (2026-10-06). No row is ever queued without its
source. If the tab has no Source header yet, the writer puts the header
"Source" in the first empty header cell after Engagement (H1), and fills
column H for every row it writes.

Batch defaults: one week = 4 posts, one each on Monday, Tuesday, Wednesday
and Thursday of the target week, each at 7:00 AM (the first slot in the Time
Slot list). If Lorenzo gives other days or times, use his for that batch, and
record them here as the standing default only if he says so. A personal post
goes in when the previous week's rows have none (see Cadence).

A test batch is 3 posts, shown in chat, not written to the sheet. The service account cannot create a sheet
(zero Drive quota), so if the sheet does not exist, Lorenzo creates it and
shares it with the service account as Editor.

## Checklist before a post goes in the queue

1. Hook in line one, not starting with "I".
2. Under 1,800 characters, short lines, blank lines between paragraphs.
3. Every number and story traces to a named source; the Source field says
   which. Nothing invented.
4. No contractor-only framing; one buyer or one agent per post.
5. No em or en dashes, at most 2 emojis, 0 to 3 hashtags only on the last line.
6. Ran the Claudeism test on every closing line.
7. Not a repeat of an angle in the last 50 rows.

## Sources (for maintainers)

- Positioning and sourcing rule, cadence, playbook advice: Lorenzo, 2026-10-06
  (LinkedIn outreach as third channel, following a Maker School member's
  playbook); website copy `Desktop/AdveroSolutions/Website/index.html`.
- Directive: `Agentic Worklfows/directives/USER/generate_linkedin_content.md` (retired 2026-10-06; original pillars, post types, sheet columns, workflow; undated, in the 2026-09-23 fresh-start snapshot; contractor pillars there are superseded by this skill).
- Generator: `Agentic Worklfows/execution/linkedin_content_generator.py` (pillar weights, topics, voices, time slots, Haiku default), `execution/linkedin_post_profile.json` (Apr 21 2026: identity, claims, off-limits, hot takes, voice), `execution/linkedin_swipe_file.json` (Apr 20 2026: hook formulas, formatting rules, engagement closers; `user_swipes` is empty). Both still hold the old contractor pillars and 7-a-day default.
- Proof: Lorenzo's approved list of 2026-10-06 (matches the website results); memory `lorenzo-case-studies.md`; `Agentic Worklfows/config/offers.md` on origin/main (2026-09-24 no-numbers rule).
- Voice rules: `claudeisms` skill (2026-09-23); `lorenzo-voice` skill; `Agentic Worklfows/sections/README.md` voice rules (2026-09-23: no invented facts, results or client names; no em or en dashes); memory `feedback-claudeisms.md`.
- Operating model (Opus 5.5 writes, Grok never writes): Lorenzo, 2026-09-25; `grok-operator` skill.
- Sheet quota: memory `daily-metrics-tracker.md` (2026-08-03).
