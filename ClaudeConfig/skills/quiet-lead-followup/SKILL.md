---
name: quiet-lead-followup
description: The follow-up ladder E1 to E10 for a lead who replied interested, got our first reply with two times, then went quiet. Covers when it starts (day 0 is the first reply), the timing of every email, the exact agreed text and its per-offer lines, no links, releasing earlier times, what happens with no free times, holds and stops, the hand-off to nurture, and the E2 research line status. Use for "follow up with a quiet lead", "which follow-up is due", "E1".."E10", "the lead went quiet", "cadence", "touch due".
---

# Quiet-lead follow-up (E1 to E10)

A lead said "interested", our first reply offered two call times, and the lead went silent. Ten emails follow in the same thread until they book, reply, or the ladder ends. All ten were agreed with Lorenzo on 2026-09-23.

Who does what (2026-09-25; see `grok-operator`): the engine timer wakes Grok only when a touch is due. Claude Opus 5.5 decides whether it goes (checks below) and returns the template id and filled text. Grok sends exactly that text in the thread and verifies it. Grok never writes or picks the words. A touch whose text is not an approved template is held, never rewritten.

## When the ladder starts

- **Day 0 is the first reply** to the lead (Lorenzo, 2026-09-23; since 2026-10-06 the AI agents first replies auto-send from approved templates for an `ai_agents` lead who never had a call, the rest go to Lorenzo, see `cold-email-replies`).
- Day 0 is recorded in one of four ways: a first reply that auto-sent, an approved send from a hold card, Lorenzo tapping Mark sent after sending it himself, or the engine finding his hand-sent reply in the Instantly thread (a manual email from the same inbox, in the same thread, after the reply the draft answered, within 14 days of that reply).
- When day 0 is found, the two times in that reply are recorded as offered to this lead, the lead leaves nurture if enrolled (`re_engaged`), and GHL gets Sequence `followup`, Next Email `cadence.e1` and Next Due Date the next business day at 10:00 CT (a Friday reply means a Monday E1), written after the send's own records. A held first reply records Sequence `reply_waiting` until a first reply goes out; Lorenzo's own reply, once sent, is day 0 the same way.
- A lead who wrote again after the first reply, or has another open draft, is not armed.

## Schedule

| Email | When | Offers times | Template id (plus per-lead line) |
|---|---|---|---|
| E1 | next business day after day 0, 10:00 CT | yes | `cadence.e1` |
| E2 | next business day | no, on purpose | `cadence.e2` + `cadence.e2.research_fallback.<reactivation or outbound>` |
| E3 | next business day | yes | `cadence.e3` |
| E4 | next business day | yes | `cadence.e4` + `cadence.e4.offer_proof.<reactivation or outbound>` |
| E5 | next business day | yes | `cadence.e5` + `cadence.e5.offer_line.<reactivation, reactivation_bookkeeping or outbound>` |
| E6 | next business day | yes | `cadence.e6` + `cadence.e6.preview.<niche>_<offer>` |
| E7 | next business day | yes | `cadence.e7` |
| E8 | 14 days after E7 | yes | `cadence.e8` |
| E9 | 7 days after E8 | yes | `cadence.e9` + `cadence.e9.observation.<niche>_<offer>` |
| E10 | 7 days after E9 | yes | `cadence.e10` |

Every touch goes at 10:00 CT on a business day, never on weekends, never before 10:00, only inside the 07:00 to 19:00 CT send window, one touch per lead per day (`ask_opus.py` holds a second `cadence.*` touch to the same lead on the same CT day). Subject "Re: {original_subject}" in the same thread from the same inbox (no subject: "Re: {first_name}, question", then "Re: your reply").

E1 goes out at 10:00 CT like every other touch, with no heads-up or veto first (Lorenzo, 2026-10-06).

## Rules for every email (Lorenzo, 2026-09-23)

1. No link in any of the ten emails (the one booking link is in the `booking_link` first reply, `cold-email-replies`). The lead picks one of the two times; it is booked first, then the Locked in confirmation goes (`cold-email-replies`, step 5).
2. Any email that offers new times says the earlier times got taken, in different words each time. The engine makes that true: when a touch offers new times, this lead's earlier held times are released first.
3. Email only. No texts, no calls.
4. No Claudeisms (`claudeisms` skill). Normal capitalization. No exclamation marks, no em or en dashes, no prices or guarantee figures. "AI" is fine (Lorenzo, 2026-09-30), but never tell or imply to a lead that a bot or AI wrote the email.
5. Opens "Hey {first_name}," ("Hey there," when unknown), closes "Lorenzo".

## The text (exact, as agreed)

**E1**
> The time slots I sent got filled. Here are 2 more, let me know if they work: {slots}.

**E2**
> {research_line}
>
> Fifteen minutes is enough for me to show you how this would run for {company}. Let me know when a good time is to get a call on the books.

{research_line} fallback lines (used today for every lead):
- Reactivation: "The quickest place to start is usually the accounts that already know you and went quiet."
- Outbound: "The quickest place to start is usually the prospects who are in market right now."

**E3**
> I really want to get this call on the books with you. Those last two times got taken too.
>
> Would {slots} work instead?

**E4**
> I really think there's a lot of room for growth at {company}. I've built these systems across numerous industries. A few of my favorites:
>
> - {offer_proof}
> - an outbound system that raised a software consultancy's qualified lead volume 35%
> - $5M in loan applications in 30 days on $1,500 of ad spend for a lender
>
> The first one is the same kind of system I'd build for {company}. Those last two times got booked. Would {slots} work to go over it?

{offer_proof}, one per offer type, never mixed:
- Reactivation: "a win-back system for a commercial roofer doing $150M a year that recovered about $6M worth of contracts within 6 months"
- Outbound: "an outbound system for a commercial roofer doing $150M a year that brought in about $180,000 in new contracts in 90 days"

**E5**
> Haven't heard back yet, no worries. It's a busy time of year and the slots keep getting filled.
>
> I'd still like to show you how we'd {offer_line}. Would {slots} work?

{offer_line}: cleaning and recruiting reactivation "win back {company}'s past accounts"; bookkeeping reactivation "win back {company}'s past clients"; outbound "get {company} in front of new clients right when they need you".

**E6**
> Here's a preview of what I'd show you on the call.
>
> {preview}
>
> The rest takes about 15 minutes. Those last two times are gone, but I've got {slots} open.

{preview} by campaign:
- Cleaning, reactivation: The first two messages I'd send accounts that cancelled or never signed: "Quick question, who's handling your cleaning these days?" and "Happy to take another look at the space and send a fresh quote. Want me to set that up?"
- Bookkeeping, reactivation: The first two messages I'd send former clients and old inquiries: "Checking in, who's keeping your books these days?" and "Want us to get everything caught up before your next quarterly estimate is due?"
- Recruiting, reactivation: The first two messages I'd send clients who've gone quiet: "Anything you're hiring for this quarter that we could help with?" and "If a role's been open longer than you'd like, send it over and we'll take a first pass."
- Cleaning, outbound: The three things I'd watch for in your area: new office leases, companies moving into bigger space, and buildings that just changed property managers. The outreach goes out under your name.
- Bookkeeping, outbound: The three things I'd watch for in your area: newly registered businesses, companies posting for a part-time bookkeeper, and businesses opening a second location. The outreach goes out under your name.
- Recruiting, outbound: What I'd watch for in your market: specialty roles hitting the job boards, especially ones that sit open for weeks or get reposted. The outreach goes out under your name.

**E7**
> Last one from me this week. Should I keep trying to find a time, or is now just not the right moment?
>
> Those last two times went too. If it's still on your list, I can do {slots}.

**E8**
> Been a couple of weeks. Was hoping now was a good time to get a call on the books.
>
> The times I sent before are long gone. How about {slots}?
>
> Let me know if right now is a bad time, or if this just isn't a priority.

**E9**
> Quick thought for you. {observation}
>
> That's where I'd start with you. The last times I sent are gone, but I'm free {slots}.

{observation} by campaign:
- Cleaning, reactivation: An account that cancelled or never signed already knows your name, so it's usually an easier conversation than a brand-new lead.
- Bookkeeping, reactivation: Quarterly estimates, year-end and tax season each give you a natural reason to check back in with former clients and old inquiries.
- Recruiting, reactivation: Clients who hired through you before, or almost did, already know how you work, so they're an easier conversation than any cold account.
- Cleaning, outbound: A company moving into new space has to sort out cleaning around move-in.
- Bookkeeping, outbound: A company posting a part-time bookkeeper job has already said out loud it needs help with its books.
- Recruiting, outbound: An open specialty role on a job board is a hiring manager saying in public they need someone.

**E10**
> You wrote back that you were interested, so I didn't want to just go quiet on you.
>
> I'll give you some room and check back in a few months. If you'd rather talk sooner, those last two times are gone, but {slots} would work.

## Placeholders

- {first_name}: "there" when unknown.
- {company}: the spoken name, with LLC, Inc., Corp, Co., Ltd, PLLC, LLP and any tagline after " - ", " | " or ": " removed. Used in E2, E4, E5. If it is unknown, the touch is held (`missing_lead_data`), never sent with a blank.
- {slots}: two free times on different days, written like "Tue 12:05pm or Thu 4:30pm CT", under the slot rules: 12:00 to 18:00 CT Monday to Friday, at least 4 hours out, within 5 business days, never offered to this lead or any other lead before. Live, only times read from the Discovery Call calendar.

## When it stops

- **Any reply from the lead stops the ladder.** The reply goes through `cold-email-replies`; an answer to it re-arms the ladder.
- **"Not now", "bad time", "not a priority"** (any follow-up): stop, GHL Follow Up Later, and enrol in the 90-day nurture with reason `not_now_reply` (`nurture-90-day`).
- **Booked**: stop. Before every touch, check for a future appointment on the GHL Discovery Call calendar and on Lorenzo's Google Calendar (some older calls were booked there by hand): leads can book themselves through the calendar link. If there is one, send nothing, release the lead's held times, set GHL Call Booked, Sequence `booked` (not stopped) and Instantly interest 2. Everything after, including the booking confirmation, is in the `booked-calls` skill.
- **Unsubscribe, hostile, not a fit, wrong person, or any opt-out on record**: stop for good. Nothing more is sent.
- **Any appointment, past or future, Do Not Disturb (overall, for email, or a `dnd`, `do-not-disturb` or `do not disturb` tag), a GHL Sequence other than `followup`, or an Instantly interest status other than 1 (interested) or 0 (out of office)**: no touch goes; `ask_opus.py` holds E1 to E10 for such a lead, and also when one of these facts is missing (2026-10-06).
- **Out-of-office reply**: a pause, not a stop. The ladder resumes the business day after the return date (next business day if none given).
- **After E10 with no reply**: GHL Follow Up Later, and nurture with reason `no_reply_after_sequence`.
- **Lead already in nurture**: the ladder stops with reason `nurture` before anything sends, and cannot be resumed while enrolled.
- **Recipient not confirmed**: before every touch the thread is re-read; the last inbound email must be from the lead. If it cannot be confirmed after three tries, the touch is held and Lorenzo gets a Resume link. If the thread belongs to someone else, the ladder stops and cannot be resumed.

## No free times

A touch that needs two times and finds fewer than two waits and retries the next business day. On the 2nd miss in a row Lorenzo gets one alert; on the 5th the ladder stops as `slots_unavailable`. Live with no calendar read (guessed times only), the ladder stops after 2 days. E1 and E2 have no no-free-times version (Lorenzo deleted them).

## Holds

A touch is held (not sent, day not advanced) when its template or per-lead line is not approved at its current text, the copy check refuses it, or a lead value does not fit its placeholder. A hold that covers everyone at once (kill switch on, template mismatch after a deploy, approvals unreadable) never counts against the lead; the touch goes out late once it clears. Any other hold counts once per business day; after 3 counted days the ladder stops as `template_unapproved` and Lorenzo gets a Resume link (fresh one daily for up to 8 reminders or 14 days). Resume sends nothing by itself: the next due touch runs every check again.

Status on 2026-09-24: none of the `cadence.*` ids is approved yet, so every touch would be held. They are in the go-live emails doc for Lorenzo's "done".

## E2 research line

Research is **off** (`E2_RESEARCH_MODE = "fallback"`): E2 uses the fixed fallback line, reads no page and calls no model. Turning it on needs all three: Lorenzo's OK for paid model calls (about $0.01 per lead), the E2 gate path finished by section 4, and Lorenzo approving `cadence.e2.research_rules` in the emails doc. The per-lead researched line itself can never be approved as text: it may go out only when it passes the approved rules, and any failed check sends E2 with the fallback line instead. Until the gate path exists, a researched line is never sent.

The rules, when it is turned on (agreed 2026-09-23):
- One or two sentences, 35 words or fewer: one to three facts about their business, then what that means we could do for them under their offer. Stop there.
- It must tie back to the offer (reactivation: a base of past clients to win back; outbound: the triggers we would watch).
- Facts only from their own website, reviews or listing, after confirming the name and the city or phone match. Every fact has a source page.
- Numbers exactly as found or rounded down. No guesses ("must be", "probably"), no praise-only line, nothing negative, no pricing or results, no names of people or competitors, no quoted reviews, no mention of research, tools, AI or automation, no URLs.
- Do not start with "I think", do not open with "I saw" or "I noticed", no question, no times.
- Return NONE when identity cannot be confirmed, the site is down, nothing connects to the offer, or it would need a guess. NONE beats a stretch; NONE means the fallback line.

Example (made-up business, style only): "Brightline has been cleaning offices around Tampa since 2011 and has over 200 Google reviews, so there's a long list of past accounts we could win back for you."

## Gaps

- The Grok-side trigger (engine timer posting a due touch to Grok) and the send tool are not built; the current engine runs an hourly tick.
- Few leads can be researched even with research on: the lead record has no website, city or metro, so identity rests on the email domain plus a phone number.
- Nurture sends nothing yet, so "check back in a few months" in E10 is not backed by a scheduled email (see `nurture-90-day`).
- A "not now" as the very first reply (ladder never armed) enrols the lead nowhere.
- Holidays count as retry days for the no-free-times count.

## Sources (for maintainers)

- `Agentic Worklfows/sections/1_email_followup/sequence_final.md` (all ten AGREED 2026-09-23), `README.md`, `STATUS.md` (2026-09-24, build complete)
- `Agentic Worklfows/runbooks/cadence_and_booking.md` (origin/main 945a384, 2026-09-24)
- `Agentic Worklfows/services/reply_engine/cadence.py` (DAY_SEQUENCE, LONG_GAP_DAYS, VETO_WINDOW_MINUTES, E2_RESEARCH_MODE, TEMPLATE_HOLD_STALL_DAYS, NO_SLOTS_ALERT_MISSES 2, NO_SLOTS_STOP_MISSES 5, SKIP_STALL_DAYS 2, stop_reason, terminal_reason, resume_after_auto_reply), `prompts/cadence_e1.md`..`cadence_e10.md`
- Go-live emails doc export `tools/template_doc/exports/2026-09-25T0045Z_build_170b09dd897430a9.txt` (doc `1bK3bkYfxYkhY0vFtHhB4RG6lMkKQrHvp6Qyasp8Pbt4`)
- `Agentic Worklfows/runbooks/template_approvals.md` ("Cadence holds, stalls and resume")
- Memory `grokbot-orchestrator.md` (2026-09-25)
