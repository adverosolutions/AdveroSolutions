# LinkedIn plan

Written 2026-10-06. Channel 3, next to cold email (Instantly) and Upwork. Method: Jonatan's Maker School Loom playbook (connection request, then a 1-minute Loom per accepted connection, three follow-ups, a voice note later). Positioning: AI agents for service businesses, broad.

Jonatan's results, for scale: 3,000+ connection requests, about 100 posts and 700+ Looms since May gave 70+ positive replies and $10k. About 30% of blank requests were accepted. US leads replied about 10% of the time, UK and Dubai more.

## Who does what

| Role | Does |
|---|---|
| Lorenzo | Approves all copy before anyone uses it. Starts the Sales Navigator trial (payment). Sends the connection requests from his own browser (decision below). Records every Loom and voice note. Posts. Takes the calls. |
| Grok Bot (LinkedIn agent; since 2026-10-21 the named LinkedIn bots LinkedIn Outreach Manager, LinkedIn Setter and Sales Nav Bot, one at a time via ~/advero/bin/linkedin_gate, approval li-227) | Works in the browser. Phase 0 only: one-time profile setup with the approved copy, deleting old posts, Sales Navigator saved searches, read-only counts. Every write is "Ask first" and needs Lorenzo's recorded yes. Never writes or changes any text. Sends no connection requests or messages and takes no other prospect-facing action (the never list in `agents/grokbot/onboarding/03_team.md`, section 5.4). Tracker updates are a later phase that needs its own Grok update. |
| Claude Opus 5.5 | Drafts posts from real material, fills the message templates, vets leads against the ICP, drafts replies (routed to Opus automatically through the harness). |
| Claude Code | Builds: skills, Grok update files, dashboard fields. |

## Phase 0: Foundation (Oct 6 to Oct 12)

Goal: the profile looks like the right person for the job before anyone clicks it.

1. Lorenzo approves the profile kit (`profile_kit.md`). He picked the headline on 2026-10-06.
2. Grok applies the profile kit checklist in this order:
   - save a read-only before copy of every field the kit changes and of every post, and report it to Lorenzo;
   - turn off Open to work;
   - upload the banner;
   - paste the headline, About with top skills, experience, services and featured;
   - try the custom URLs;
   - delete the 10 old posts, after Lorenzo's yes on the list.
3. Lorenzo starts the Sales Navigator free trial. Grok then saves one lead search per starting industry with the recipe's filters (`linkedin-outreach` skill).
4. Opus drafts the first week of 4 posts from real material. Lorenzo gives the material, edits and posts.
5. Lorenzo starts connection requests from his own browser at about 10 a day on weekdays, maxed out on the weekend to find the cap (see the decision below).

Done when: the profile is live with the new copy, the old posts are gone, the saved searches exist, 4 posts are up and the first requests are out.

## Phase 1: Warm-up (Oct 13 to about Nov 7)

Goal: 51 to about 200 connections, with no Looms yet (Jonatan).

- Raise requests toward 40 a day, never more than 50 in one day. Blank requests only.
- Withdraw requests pending longer than 3 weeks and keep fewer than 600 pending.
- 4 posts a week, with a personal post about every 2 weeks.
- Check acceptance at 2 weeks. Below 15%, fix the profile or the lead list before sending more.
- Lorenzo records about 10 practice Looms from `outreach_copy.md` (scripts A and B).
- LinkedIn judgement (fill `{what_they_do}`, ICP vet, reply drafts) routes to Opus automatically through the harness; no `ask_opus.py` LinkedIn case needs building. Claude Code builds the Grok routine that lists what is due each morning. Lorenzo's dashboard gets the fields and stages from the skill.

The date is an estimate. At about 30% acceptance, 150 more connections takes roughly 500 requests, or 3 to 5 weeks while the account is new.

## Phase 2: Loom launch (at about 200 connections)

- First two Loom days: about 50 each, for reps (Jonatan). After that, about as many Looms a week as new connections accepted (Jonatan: about 50 a week, 20 to 30 minutes per 10).
- Split test: script A (reactivation) and script B (reply and booking), about 100 each before judging.
- Follow-ups at 2, 4 and 7 days. Reply drafts offer two open times from Lorenzo's Google Calendar plus his direct booking link (https://scheduler.zoom.us/lorenzo-villarreal-4mp7rz/30-mins-with-lorenzo); ask-first, Lorenzo approves each send (2026-10-20). If the lead picks a time, Lorenzo sends the invite.
- The daily block runs as written in the `linkedin-outreach` skill.

Planning math, not a promise: about 170 requests a week at 30% acceptance gives about 50 new connections and 50 Looms a week. A 10% reply rate gives about 5 replies a week.

## Phase 3: Verdict and iterate (after about 100 Looms per script)

- Pick the winning script by positive replies and call quality, not reply rate alone.
- Test a non-US English-speaking market. UK and Australia need call times outside the 12:00 to 18:00 CT window, so Lorenzo decides the hours first.
- Voice-note week for leads who never replied, from 60 days after their FU3.
- Calls turn into post material: each transcript gives about 10 angles through Opus.

## Decision: who sends the connection requests (Lorenzo, 2026-10-06)

Lorenzo sends them himself, from his own browser, for now. About 10 minutes a day (Jonatan). His account can't be replaced like an inbox, and LinkedIn restricts accounts that look automated, especially from a cloud computer.

Grok sends none. Nothing on the never list turns on except through a new dated Grok update file that Claude Code builds after Lorenzo asks for it; for connection requests, that update carries these conditions: vetted leads only, the same caps, blank, spread through the day. Writing or editing text never turns on.

## Numbers to watch each week

Requests sent, acceptance rate (true after about 2 weeks), connections, posts, Looms sent per script, reply rate, positive replies, calls booked, closed.

## Cap update 2026-10-26 (li-232-amend-cap-20261026)
From Tue 2026-10-27: up to 20 blank connection requests per weekday, 10 AM to 12 PM CT, spaced 60 to 120 s. Never over 100 in any rolling 7 days (each day's cap = min(20, 100 minus sends in the prior 6 days)). If pending invites pass 300, cut back and tell COO. Mon 10/26 stays at 10. Does not approve new queue rows or any message to a lead. Approved by Lorenzo on a voice call with COO, 10:10-10:11 AM CT.
