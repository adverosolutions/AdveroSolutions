---
name: linkedin-outreach
description: "Run or draft Advero LinkedIn outreach under current 35-per-day, shared-box, gate and stop rules. Use for connection requests, accepted connections, outreach queues or Loom DMs."
---

# LinkedIn outreach

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- LinkedIn Manager inherited Setter duties on November 4; Lead Gen Manager inherited Sales Nav duties. LinkedIn runs in the box browser, one operator at a time through linkedin_gate; Lorenzo’s Mac need not be online.
- Only Loom outreach is paused under the November 2 ruling. Connection requests ramp up to 35 per day with the current gate, pacing and warning rules. Existing November 4 stop records remain in force until cleared by the applicable instruction.
- Use direct /in/ profiles, confirm the target name in the top card and send dialog, and verify uncertain invites on Sent before any retry. Never send blind or use sidebar suggestions.
- First-message openers remain held until 200 connections per the Setter handoff. No unattended password, phone-2FA or CAPTCHA work; stop and report access or verification problems under the current tool policy.
- Use the current queue and handoffs rather than the historical rule below that Lorenzo performs every prospect-facing action himself.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)
- [linkedin-setter_to_linkedin-manager_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/linkedin-setter_to_linkedin-manager_20261104.md)
- [sales-nav-bot_to_lead-gen-manager_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/sales-nav-bot_to_lead-gen-manager_20261104.md)
- [linkedin_setter_hang_20261104_1029.md](../../grok-source/2026-11-04/first-export/advero/state/stops/linkedin_setter_hang_20261104_1029.md)
- [linkedin-manager.md](../../grok-source/2026-11-04/third-export/routine_exports/linkedin-manager.md)


Lorenzo finds owners in Sales Navigator, sends blank connection requests, and
sends each new connection a short personal Loom in a DM, followed by up to three
follow-ups and, months later, a voice note. Claude fills the copy templates
from rows he pastes and tells him what is due. No outreach on LinkedIn is
automated.

Positioning (Lorenzo, 2026-10-06): broad. Service businesses that close new
business on a call, a walkthrough or a quote, not one niche.

**Where numbers come from.** Every number below is tagged:
- **(Jonatan)**: the Maker School member whose Loom playbook Lorenzo chose to
  follow exactly (2026-10-06). It is his own account's experience. None of it
  is LinkedIn policy, and LinkedIn can change its limits at any time.
- **(Lorenzo)**: a rule Lorenzo set.
- **(skill default)**: filled in here where neither said; Lorenzo can change it.

## Files

- Copy (the only source of message text):
  `Agentic Worklfows/linkedin/outreach_copy.md` in the AdveroSolutions repo.
  It holds the blank connection request, Loom scripts variant A (Reactivation)
  and B (Reply and booking / outbound), the DM per variant, FU1, FU2, FU3, the
  voice note and the reply templates.
- Plan: `Agentic Worklfows/linkedin/PLAN.md` (phases, who does what, the
  connection-request decision).
- Profile: `Agentic Worklfows/linkedin/profile_kit.md` (headline, About,
  banner, services, checklist).
- Posts: the `linkedin-content` skill.
- SOP: `Agentic Worklfows/directives/USER/linkedin_outreach.md`.
- Voice: follow `~/.claude/skills/lorenzo-voice/SKILL.md` and
  `~/.claude/skills/claudeisms/SKILL.md` for anything Claude writes or fills.

Repo root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/` (worktrees
of it may sit elsewhere; use the one you are in). If a copy file is
missing, say so and stop. Never write stand-in copy.

## Who does what

| Step | Who |
|---|---|
| Approving all copy, including the profile kit | Lorenzo |
| Logging LinkedIn in on Grok's computer, starting the Sales Navigator trial (payment) | Lorenzo |
| One-time profile setup from the approved kit (Open to work off, banner, headline, About and top skills, experience, services, featured, custom URL) | Grok Bot's LinkedIn agent, Ask first on every write |
| Deleting the 10 old posts | Grok Bot's LinkedIn agent, after Lorenzo's yes on the list |
| Saved searches, one per starting industry, from the recipe below | Grok Bot's LinkedIn agent, after Lorenzo starts the trial |
| Sunday count: connections, pending sent invitations, followers (read only) | Grok Bot's LinkedIn agent |
| Posting | Lorenzo (drafts from `linkedin-content`) |
| Vetting each lead, sending connection requests | Lorenzo, from his own browser (2026-10-06) |
| Opening profiles, second ICP check, typing rows into his tracker | Lorenzo |
| Filling the Loom script, DM, follow-up, voice note and reply templates from his rows | Claude Opus 5.5 |
| Recording every Loom and voice note, sending every DM | Lorenzo |
| Working out what is due, stage and date updates, weekly numbers | Claude, from rows he pastes or exports |
| Picking the two call times | Claude proposes, Lorenzo checks his calendar and sends the invite |

Lorenzo's personal LinkedIn account cannot be replaced the way an email inbox
can (Lorenzo). Claude (Claude Code, Claude in Chrome, computer use) never
opens LinkedIn, never logs in, never reads a LinkedIn page and never acts on
the account.

Grok Bot's LinkedIn agent (PLAN.md Phase 0, 2026-10-06) does only its rows
above, in the browser on Grok's cloud computer, with Ask first on every
LinkedIn write and only when Lorenzo's yes for that exact action is recorded
(Grok's `linkedin_approvals.jsonl`, written by its Chief of Staff from his
own words). Its full rules are in Grok's onboarding file 03, section 5:
- Before the first write it saves a read-only before copy of every field the
  kit changes and of every post.
- Nothing is pasted until Lorenzo approves the profile kit. It pastes the
  approved text exactly, character for character, and never writes, edits or
  picks text (the `grok-operator` rule). Where LinkedIn's own list does not
  offer the exact name in the kit or the recipe, it asks Lorenzo.
- It never enters a password, a 2FA code or payment details.
- On a security check, captcha, restriction or "unusual activity" warning, it
  stops all LinkedIn work and pings Lorenzo.
- It sends no connection requests, messages or InMails, never comments,
  likes, follows or posts, never opens Messaging or notifications, never
  views prospect profiles in bulk and never scrapes or exports a list.
  Lorenzo sends the connection requests himself.
- Nothing on the never list turns on except through a new dated Grok
  update file that Claude Code builds after Lorenzo asks for it; for
  connection requests, that update carries PLAN.md's conditions (vetted
  leads only, the same caps, blank, spread through the day). Writing or
  editing text never turns on.

Lorenzo is building his own dashboard. Do not build a tracker, sheet, database
or script for this channel. Work from what he pastes and use the fields below.

## Setup weeks

Week 1 (Jonatan): profile, connection requests and posting. No Looms.

- [ ] Profile done from `profile_kit.md` (its checklist), by Grok's LinkedIn
  agent after Lorenzo approves the kit.
- [ ] Posting 4 times a week (Jonatan), drafts from `linkedin-content`.
- [ ] Sales Navigator free trial started on day 1 of week 1 (skill default).
  After the trial it is about $100 to $120 a month (Jonatan's figure). Lorenzo
  does not have it yet (2026-10-06). The recipe below assumes it; until the
  trial starts, use "Before Sales Navigator".
- [ ] Saved searches built per the recipe below.
- [ ] Connection requests started at the week-1 pace (see Connection rules).
- [ ] About 10 practice Loom recordings, not sent (Jonatan).

When Looms start:
- At about 200 connections (Jonatan). Lorenzo had 51 on 2026-10-06.
- The first two Loom days, about 50 each, for reps (Jonatan).
- After that, about as many Looms a week as new connections accepted that week.
  Jonatan sends about 50 a week.

Until Looms start, accepted connections wait at stage Accepted.

## Before Sales Navigator

(skill default) Until the Sales Navigator trial starts, find leads with
LinkedIn's free People search, using the filters it has:
- Connections: 2nd-degree.
- Locations: United States.
- Industry: one per search, from the same rotation and starting list as the
  recipe below.
- Title keywords: Owner, Founder, Partner, CEO (one search per keyword if the
  field won't take them together).

Free search can't filter for what Sales Navigator does, so during the
20-second vet (Jonatan) Lorenzo checks by hand:
- They posted on LinkedIn recently (their Activity section).
- The company has about 1 to 50 staff (the company page).
- He hasn't viewed or contacted them already.

If any of the three fails or is unclear, skip.

## Sales Navigator recipe

Filters (Jonatan unless tagged):
- **Recent updates: "Posted on LinkedIn".** The must-have filter. In the full
  filter list it sits under Recent updates.
- **Exclude** "People you interacted with", option "Viewed profile".
- **Exclude** 1st-degree connections.
- Seniority: Owner, Founder, Partner, CXO (Lorenzo). Use whatever the filter
  list calls these; if Founder is not a seniority option, add "Founder" as a
  title keyword.
- Company headcount: about 1 to 50 (Lorenzo).
- Geography: United States first (Lorenzo). Jonatan sees about 10% reply rate
  in the US and much higher in the UK and Dubai (up to 27% to 40% on some days).
  Moving past the US is Lorenzo's call.
- Industry: one industry per saved search, rotated across service businesses
  that close on a call, walkthrough or quote (Lorenzo). Starting list (skill
  default): staffing and recruiting, commercial cleaning, bookkeeping and
  accounting, insurance brokers, landscaping, marketing agencies, MSP and IT
  services, pest control. Log the industry on every row so results compare by industry.

A tighter list makes sending faster (Jonatan). Vet each lead for about 20
seconds (Jonatan): the company and what it does. If in doubt, skip (Jonatan).

## Connection rules

- **Blank request, no note** (Jonatan: about 30% acceptance blank, under 10%
  with long personalized notes). The connection request entry in
  `outreach_copy.md` is the reference.
- **Ramp** (Jonatan): start about 10 a day on weekdays. On Saturday and Sunday
  send more to find where the account gets capped, then raise the weekday
  count.
- **Never more than 50 in one day** (Jonatan: every time he did, he got
  restricted). This holds on the weekend test days too.
- **Target: 40 a day** (Jonatan's number). Raise the weekday count toward it
  as the account allows. Jonatan runs 40 a day and gets capped on Friday after
  10 to 20, so about 170 to 180 a week. Newer accounts land around 100 to 150
  a week, older active ones up to about 200 (Jonatan).
- The weekly limit resets on Monday, US time (Jonatan: what he sees on his
  account).
- Acceptance improves with acceptance rate, account age and, unconfirmed,
  commenting and engagement (Jonatan).
- True acceptance rate shows after about 2 weeks. Below 15%, fix the profile
  or the list (Jonatan).
- Withdraw requests pending more than 3 weeks. Keep pending under 600
  (Jonatan).

## The daily block

Order and method are Jonatan's. Claude's part is marked.

1. In My Network, go through new connections from the bottom, 10 at a time.
2. Open the 10 profiles. Second ICP check on each.
3. Put first name, role and company (plus what_they_do and the rest of the
   fields below) into the tracker.
4. **Claude:** Lorenzo pastes the 10 rows. Claude returns, per row, the Loom
   script and the DM from `outreach_copy.md` with placeholders filled, and
   flags any row with missing or doubtful data.
5. Open the proof website tab. Split screen.
6. Record each Loom: start on their LinkedIn profile, switch to the proof site
   for the proof beat, back to their profile. Hand gestures: wave, thumbs up,
   bye.
7. Download each video from Loom and embed it in the DM, then paste the DM
   text. An embedded video shows "Sent a video", gets more replies than a link,
   and some people don't click links (Jonatan).
8. **Claude:** due follow-ups. Lorenzo pastes rows (or an export); Claude lists
   every row whose next_touch_due is today or earlier, with the text for each.
   Lorenzo sends them.
9. The day's connection requests, each logged as a row at Connect sent.
10. Sundays: bulk-update who accepted (Jonatan). **Claude** can turn his
    pasted list of new connections into stage and date updates.

Repeat steps 1 to 7 in groups of 10 until the day's Loom count is done.

## Follow-up timing

Jonatan says FU1 at "48 hours", FU2 "4 days later", FU3 "7 days later". This
skill reads each gap as counted from the previous touch:

| Touch | Due | Notes |
|---|---|---|
| Loom DM | first block after accepted (once Looms have started) | |
| FU1 | DM date + 2 days | Goes even if the DM shows as seen (Jonatan) |
| FU2 | FU1 date + 4 days | More passive, offers to close the loop (Jonatan) |
| FU3 | FU2 date + 7 days | Last check-in (Jonatan) |
| No reply check | FU3 date + 7 days | No message; the row moves to No reply (skill default) |
| Voice note | FU3 date + 60 days (skill default) | Jonatan: "leave them a few months"; 30 seconds or less. He sometimes runs a voice-note-only week |

- Days are calendar days (skill default). If a touch falls on a day Lorenzo
  doesn't run the block, it goes out at his next block, and the next gap counts
  from the day it actually went out (last_touch_date).
- Any reply stops the ladder. Nothing more goes until Lorenzo answers.
- A row at Follow-up 3 whose FU3 is 7 or more days old with no reply becomes
  No reply, with next_touch_due = FU3 date + 60 days for the voice note (skill
  default). The 60 days count from FU3, not from the No reply check.
- The voice note goes only to rows that never replied.

## Tracker fields and stages

For Lorenzo's own dashboard. Claude reads rows with these names and returns
updates using them.

| Field | Holds |
|---|---|
| name | Full name as on the profile |
| first_name | First name (if the dashboard has no separate column, Claude takes it from name) |
| profile_url | LinkedIn profile URL |
| company | Company name as on the profile |
| role | Their title |
| what_they_do | 3 to 8 words on what the company does (rules under Drafting) |
| industry | The saved-search industry |
| country | Country; add state or city if known, for the time zone |
| connect_sent_date | Date the request went out |
| accepted_date | Date they accepted |
| dm_date | Date the Loom DM went out |
| loom_variant | A (Reactivation) or B (Reply and booking / outbound) |
| last_touch_date | Date of the latest message Lorenzo sent |
| next_touch_due | Date the next touch or check is due; blank when nothing is due |
| stage | One of the stages below |
| reply_type | Blank until they reply; then positive, price, more_info, what_is_this, not_now, not_interested, referral or other (the latest reply) |
| reply_date | Date of the lead's latest reply |
| reply_answered_date | Date Lorenzo sent his answer to that reply; blank while it is unanswered |
| meeting_booked | Blank or the call date and time |
| outcome | Blank, Closed won or Closed lost |
| slots_offered | Optional (skill default): the two times sent, so no time goes to two people the same day |

Stages: Connect sent, Accepted, DM sent, Follow-up 1, Follow-up 2,
Follow-up 3, No reply, Voice note sent, Reply, Positive reply, Meeting booked,
Closed won, Closed lost, Withdrawn. Jonatan's tracker has the first ten as
statuses, plus columns for closed won/lost, reply type and meeting booked.
Voice note sent, Meeting booked, Closed won, Closed lost and Withdrawn are
added here as stages.

| Event | stage | Dates set | next_touch_due |
|---|---|---|---|
| Request sent | Connect sent | connect_sent_date | connect_sent_date + 21 days (withdraw check) |
| Still pending at 21 days | Withdrawn (after Lorenzo withdraws) | | blank |
| Accepted | Accepted | accepted_date | next block, or blank until Looms start |
| Loom DM sent | DM sent | dm_date, last_touch_date | + 2 days |
| FU1 sent | Follow-up 1 | last_touch_date | + 4 days |
| FU2 sent | Follow-up 2 | last_touch_date | + 7 days |
| FU3 sent | Follow-up 3 | last_touch_date | + 7 days (No reply check) |
| No reply check due (FU3 + 7 days, no reply) | No reply | | FU3 date + 60 days (voice note) |
| Voice note sent | Voice note sent | last_touch_date | blank |
| Any reply | Reply, or Positive reply for positive | reply_type, reply_date | blank (Lorenzo answers) |
| Answer sent, two times (positive) | Positive reply | reply_answered_date, last_touch_date | + 2 business days (quiet check) |
| Answer sent, not_now | Reply | reply_answered_date, last_touch_date | the date they gave; blank until they give one |
| Answer sent, not_interested | Reply | reply_answered_date, last_touch_date | blank, and never set again |
| Answer sent, any other type | Reply | reply_answered_date, last_touch_date | blank |
| Invite accepted | Meeting booked | meeting_booked | blank |
| After the call | Closed won or Closed lost | outcome | blank |

## Drafting from pasted rows

Template mode only (Lorenzo): fill the placeholders in `outreach_copy.md`,
never write new sentences per lead. His freeform per-lead writing kept failing
his voice bar. Placeholders are fixed: {first_name}, {role}, {company},
{what_they_do}, {slot1}, {slot2}.

**Input:** rows pasted or exported from his dashboard, any column order, with
the field names above or close to them. Ask for today's date if it isn't
clear.

**Per row, work out what is due:**
- Accepted and Looms have started: Loom script plus DM for the row's
  loom_variant. If loom_variant is blank, ask Lorenzo which variant the block
  runs. Don't pick one.
- DM sent, Follow-up 1 or Follow-up 2 with next_touch_due today or earlier:
  the next follow-up (FU1, FU2 or FU3).
- Follow-up 3 with next_touch_due today or earlier: no message. Return stage
  No reply and next_touch_due = FU3 date (last_touch_date) + 60 days, the
  voice note date (skill default).
- No reply with next_touch_due today or earlier: the voice note script.
- Reply or Positive reply: see Replies. Draft only when Lorenzo has pasted
  the lead's reply text and reply_answered_date is blank or earlier than
  reply_date. Otherwise no draft; if next_touch_due is today or earlier, list
  the row under NEEDS_YOU (Replies says why).
- Connect sent older than 21 days: list it under "Withdraw".
- Anything else: nothing due; leave it out of the output.

**Filling the placeholders:**
- {first_name}: the first name as on the profile, normal capitalization, no
  credentials or emoji ("Dana Smith, CPA" gives Dana). If it is initials, a
  company name or unclear, flag the row.
- {company}: the spoken name. Drop LLC, Inc., Corp, Co., Ltd, PLLC, LLP and
  any tagline after " - ", " | " or ": ".
- {role}: their title as written, trimmed to the main title (the part before
  the first "|" or ","). Never reword it.
- {what_they_do}: 3 to 8 words for what the company does, taken from their
  LinkedIn company page or headline as pasted. Plain words only: no
  marketing words ("leading", "premier", "top", "best", "trusted", "innovative",
  "solutions", "world-class", "#1"), not the company name, and it must read
  naturally where the template puts it. Example: a headline "Owner at Brightline
  | Premier commercial cleaning for Dallas offices" gives "commercial cleaning
  for offices in Dallas". If the pasted text doesn't give a phrase that passes,
  flag the row. Never guess from the company name.
- {slot1}, {slot2}: see Two times for a call.

**Flag, don't draft,** any row missing a value its template uses, any value
that fails the rules above, and any row that looks outside the ICP from what
was pasted (not an owner, founder, partner or CXO, clearly over 50 staff, not a
service business). Lorenzo decides.

**Output, per row:**
1. A header: first name, company, stage, what is due.
2. The text to paste (and, for a Loom or voice note, the filled script to read).
3. For you: anything Lorenzo should know that is not in the message.
4. NEEDS_YOU: what he must fill or decide. Skip the line when empty.
5. After he says he sent it: the row's new stage, last_touch_date and
   next_touch_due.

Before handing anything over: no "{" or "}" left, no em or en dashes, no
added sentence, and the claudeisms delete test passes on any word Claude chose.
Text copied from `outreach_copy.md` is never reworded.

### Replies

Draft a reply only when Lorenzo pastes the lead's actual reply text. A row
at stage Reply with no text gets no draft: ask him for the text. Put the reply
in one reply_type and fill that entry in section 6 of `outreach_copy.md`,
using the row's loom_variant where the entry has an A and a B:

| reply_type | Their reply | Entry in section 6 |
|---|---|---|
| positive | a thumbs up or a yes | Thumbs up or "yes" (both variants) |
| price | asks what it costs | "What does it cost?" |
| more_info | asks for more info | "Send me more info" |
| what_is_this | asks what this is | "What exactly is this?" |
| not_now | not now, maybe later | "Not now" (both variants) |
| not_interested | says no | "Not interested" (both variants) |
| referral | someone else handles it | "Someone else handles this" (both variants) |
| other | anything that doesn't clearly match a row above | none |

An `other` reply gets no draft: list it under NEEDS_YOU with what they said.
A lead picking one of the two times gets no draft either: NEEDS_YOU, send the
invite to the email they gave. That row keeps reply_type positive.

After Lorenzo says he sent the answer, set reply_answered_date and
last_touch_date to that day, then:
- positive: stage Positive reply, next_touch_due = + 2 business days (skill
  default). Stage Meeting booked once they accept the invite. If
  next_touch_due comes with no answer from them and no meeting booked, they
  went quiet after the two times: NEEDS_YOU, no draft.
- not_now: next_touch_due = the date they gave, in this reply or in their
  answer to the "Not now" question (blank until they give one). When it is
  due: NEEDS_YOU, no draft, since there is no check-back template.
- not_interested: next_touch_due blank, and it is never set again. No
  follow-ups, no voice note, never moves to No reply.
- price, more_info, what_is_this, referral: next_touch_due blank.

A row whose reply_answered_date is on or after its reply_date is answered:
never redraft it. When the lead replies again, Lorenzo pastes the new text,
reply_type and reply_date are set for that reply, and it is drafted fresh.

No price figures by message (Lorenzo); the "What does it cost?" entry is the
whole answer. For call prep after a booking, see `sales-call`.

### Two times for a call

Lorenzo offers two specific times for a 15-minute call and sends the invite
himself. Never a booking link (Lorenzo). The text is the Thumbs up or "yes"
(both variants) entry in section 6 of `outreach_copy.md`.

Slot rules (Lorenzo's booking engine): 12:00 to 18:00 CT, Monday to Friday, at
least 4 hours out, within 5 business days, never the same time to two people
the same day. Write the times in the lead's time zone when known ("Thursday at
1pm ET"; a non-US lead gets their local zone name, such as "UK time"). Use CT
when the zone is unknown.

Where the times come from:
- `slots_daily.py` in `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026/`.
  From that folder run `/usr/bin/python3 slots_daily.py` (the macOS system
  Python; the default `python3` on this Mac is Homebrew 3.14, which has no
  pytz). No flags means a dry-run. Never add `--apply`.
- The dry-run is read-only (GETs plus a read-only POST `leads/list` on
  Instantly). Near the top it prints a `source:` line and two lists, `slot1
  day ...` and `slot2 day ...`: the free times on the first and the second
  business day after today that have a free time, from the GHL Discovery Call
  calendar. All times are CT, on the 12:00 to 17:30 start grid. Read only
  those lines.
- The same run prints counts and sample rows for the six Instantly campaigns.
  The samples include lead emails and personalization lines, so don't paste
  the output anywhere: not in the chat reply, a doc or a message.
- Trust the lists only when the line says `source: ghl`. An import error, any
  other `source:` value, or a `!! GHL CALENDAR NOT READ` banner (`fallback` or
  `fallback_empty`) means the calendar was not checked: Lorenzo picks the
  times from his calendar.
- Lorenzo can also pick real free times from his calendar instead.
- Those same times also go out to cold-email leads, so a LinkedIn time can
  clash with one an email lead picks. Lorenzo checks his calendar before he
  sends.
- Never offer a time already in slots_offered for another lead today. If his
  dashboard has no slots_offered column, never reuse a time within one batch,
  and ask Lorenzo which times already went out today.

UK and Dubai leads: 12:00 to 18:00 CT is evening in the UK and late night in
Dubai. Don't move outside Lorenzo's window on your own. Offer the earliest
times in it and flag the row under NEEDS_YOU.

## Weekly numbers

From his export or pasted rows, once a week:

| Number | How |
|---|---|
| Requests sent | rows with connect_sent_date in the week |
| Pending | Connect sent rows; flag if near 600 (Jonatan) |
| Acceptance rate | accepted / sent, counting only requests 14 or more days old; flag under 15% (Jonatan) |
| Looms sent, per variant | rows with dm_date in the week, by loom_variant |
| Reply rate, per variant | replies / Looms sent |
| Positive rate, per variant | positive replies / Looms sent |
| Calls booked | meeting_booked set in the week |
| Closed | Closed won and Closed lost |

Also split each by industry and country once there is enough volume.

Split-test rule (Jonatan): about 100 Looms per variant before judging. Judge
reply quality (positive replies and calls booked), not only reply rate. In his
tests, adding qualification lowered reply rate but raised lead quality.

## Hard don'ts

- No automation tools on LinkedIn (Lorenzo), and nothing prospect-facing
  done by any tool or bot. The one carve-out is Grok Bot's LinkedIn agent,
  for the Phase 0 setup, the saved searches and the Sunday count in "Who
  does what", Ask first on every write. Claude in Chrome, computer use and
  Claude Code never open, read or act on LinkedIn.
- Grok Bot's LinkedIn agent never sends connection requests, messages or
  InMails, never comments, likes, follows or posts, never opens Messaging or
  notifications, never views profiles in bulk, scrapes or exports lists, and
  never writes or edits text. Unlocking any of it follows the one rule
  under "Who does what"; writing or editing text never turns on.
- Never more than 50 connection requests in one day (Jonatan).
- No note on connection requests (Jonatan).
- No booking links. Two specific times only (Lorenzo).
- No price figures by message (Lorenzo).
- No invented proof, facts or results. Proof only as written in
  `outreach_copy.md`, `lorenzo-voice` and `Agentic Worklfows/config/offers.md`.
- No new sentences per lead. Template text only (Lorenzo).
- No tracker builds. His dashboard holds the data.

## Sources (for maintainers)

- `Agentic Worklfows/linkedin/PLAN.md` (2026-10-06): Grok Bot's LinkedIn
  agent and its Phase 0 scope; `agents/grokbot/onboarding/03_team.md`,
  section 5.
- Jonatan's Loom playbook (Maker School), as summarized by Lorenzo on
  2026-10-06: setup, Sales Navigator filters, connection limits, daily block,
  follow-up timing, tracker statuses, split tests, geography.
- Lorenzo, 2026-10-06: broad positioning, Lorenzo sends everything
  prospect-facing (connection requests from his own browser), own
  dashboard, template mode, two-times rule, no price figures, ICP filters.
- Slot rules: `quiet-lead-followup`, `cold-email-replies`;
  `Coding/lead-scrape-2026/SLOTS_RUNBOOK.md` and `slots_daily.py` (read
  2026-10-06; the script was not run for this skill).
