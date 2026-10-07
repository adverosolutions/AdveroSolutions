# Grok update, 2026-10-06: LinkedIn foundation (Phase 0)

This is an update to what you already have, not a new onboarding. Apply the edits in part 2 to your copies in `~/advero/` and your copy of the onboarding pack, then confirm to Lorenzo with the list of files you changed.

For Lorenzo, before you paste this: attach the four files in the table under "New files" in part 2. The first three come from the repo, `Agentic Worklfows/agents/grokbot/onboarding/`; the banner comes from `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Brand/social/linkedin/linkedin-banner-3168x792.png`.

## 1. What changed

- **LinkedIn is Lorenzo's third channel,** next to cold email and Upwork. The plan is `PLAN.md` (new file, part 2). Phase 0, the foundation, runs Oct 6 to Oct 12.
- **New agent: the LinkedIn agent** (file 03, new section 5). Create it only when Lorenzo says go for Phase 0. It is not one of the five core agents.
- **Its Phase 0 tasks:** a read-only before copy of every field the kit changes and every post; the one-time profile setup from the approved profile kit (Open to work off, banner, headline, About with top skills, experience, services, featured, custom URL); deleting the old posts on the list Lorenzo says yes to; one Sales Navigator saved search per starting industry after he starts the trial; and a read-only Sunday count of connections, pending sent invitations and followers.
- **Approvals are records tied to one card.** Every LinkedIn card gets a new id with the date and time it was sent. The Chief of Staff writes each of Lorenzo's answers, in his own words, to `~/advero/state/linkedin_approvals.jsonl` (file 03, section 5.1). The LinkedIn agent acts only when a record answers that card, was given after the card was sent, and covers that exact action. A "go" or a yes to another card never covers a deletion: each post needs its own `delete_post` record. One `resume` covers one stop. Once "done: LinkedIn Phase 0" is reported, no record covers any write. Any change Lorenzo asks for on a kit card goes to Claude Code for a new kit.
- **Rules for every agent (file 03, section 1) do not change.** The record rule is only for the LinkedIn agent.
- **Gates:** nothing is pasted before Lorenzo approves the two kit cards (he chose the headline on 2026-10-06; it is the only one in the kit) and answers a separate setup card (LinkedIn logged in, Ask first on). Every LinkedIn write is Ask first. You never enter a password, a 2FA code or payment details: Lorenzo logs LinkedIn in on the computer and starts the Sales Navigator trial himself. A mismatch, a failed save, a logout or any LinkedIn warning stops all LinkedIn work until Lorenzo says to go on.
- **Text:** the LinkedIn agent pastes approved text exactly, character for character. It never writes, edits or picks text.
- **Connection requests:** Lorenzo sends them himself from his own browser (his decision, 2026-10-06). Grok sends no connection requests, messages or InMails, never comments, likes, follows or posts, never opens Messaging or notifications, and never views prospect profiles in bulk, scrapes or exports a list. Nothing on the never list turns on except through a new dated Grok update file that Claude Code builds after Lorenzo asks for it; for connection requests, that update carries PLAN.md's conditions (vetted leads only, the same caps, blank, spread through the day). Writing or editing text never turns on.
- **File 02's "never delete anything"** now names its one exception: the old LinkedIn posts, each covered by Lorenzo's recorded yes.
- **Reports:** the Sunday counts go in the weekly scorecard, a LinkedIn warning is a new instant ping, and the Chief of Staff reminds Lorenzo two days before the Sales Navigator trial ends.

## 2. Edits to your copies

### New files (Lorenzo attaches them)

Make the folder first: `mkdir -p ~/advero/linkedin`. Save each attached file under the name below, unchanged.

| Save as | Source (for Lorenzo) |
|---|---|
| `~/advero/skills/linkedin-outreach.md` | `Agentic Worklfows/agents/grokbot/onboarding/skills/linkedin-outreach.md` |
| `~/advero/linkedin/PLAN.md` | `Agentic Worklfows/agents/grokbot/onboarding/linkedin/PLAN.md` |
| `~/advero/linkedin/profile_kit.md` | `Agentic Worklfows/agents/grokbot/onboarding/linkedin/profile_kit.md` |
| `~/advero/linkedin/linkedin-banner-3168x792.png` | `Brand/social/linkedin/linkedin-banner-3168x792.png` |

Check each file's sha256 with `shasum -a 256 <file>` (if `shasum` is missing: `python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" <file>`). It must be exactly:

```
2ac0e151893448bbb653900905cd2753d13b4113ad9344a432f944579247df8c  ~/advero/skills/linkedin-outreach.md
8023d44ac6e5a44719dacebd9f6c14a4f4473272e2dd48c6ad0ffe049af098fd  ~/advero/linkedin/PLAN.md
3f5fbdee5053b969a98ed2de2b1f65cdbc04deee18cee235e4f30ef628e5805f  ~/advero/linkedin/profile_kit.md
1cf80cc54b480bd5a288ec89b186195dafbd5ead12494d3a20591b74028121df  ~/advero/linkedin/linkedin-banner-3168x792.png
```

If one differs, tell Lorenzo which and use none of the LinkedIn files until he sends it again. The headline block in `profile_kit.md` reads:

```
Helping businesses get leads in, calls booked and more revenue with AI agents | Founder, Advero Solutions
```

### Your onboarding pack (`GROK_ONBOARDING_PACK.md`)

Your copy is the `GROK_ONBOARDING_PACK.md` Lorenzo uploaded to you on day 1 (file 00, section 6, step 1). Edit that file. If your Bot files cannot be edited, save the edited pack as `~/advero/GROK_ONBOARDING_PACK.md`, read that copy from now on, and tell Lorenzo.

a) Replace the second line of the pack (it starts `One file for a single upload.`) with:

```
One file for a single upload. Files 00 to 09 first, then the skills, then the LinkedIn files. Files 00 to 07 win over files 08, 09, the skills and the LinkedIn files (linkedin/PLAN.md, linkedin/profile_kit.md) where they differ (see 00, section 4).
```

b) In the Contents list, right after the line `- skills/client-fulfillment.md`, add:

```
- skills/linkedin-outreach.md
- linkedin/PLAN.md
- linkedin/profile_kit.md
```

c) File 00 (`00_START_HERE.md`), section 4, item 1: right after the line that ends "If they seem to differ from 00 to 07, follow 00 to 07.", add:

```
   The LinkedIn files (`linkedin/PLAN.md`, `linkedin/profile_kit.md`) are reference for the LinkedIn agent. Where they differ from 00 to 07, follow 00 to 07.
```

d) File 02 (`02_operating_model.md`), section 7: replace rule 13 (`13. Delete anything: emails, contacts, opportunities, leads, notes.`) with:

```
13. Delete anything: emails, contacts, opportunities, leads, notes. The one exception is the LinkedIn agent deleting Lorenzo's old LinkedIn posts, each one covered by his recorded yes (file 03, section 5.3, gate 3).
```

e) File 03 (`03_team.md`): at the end of the file, after rule 4 of section 4 (it ends "the Chief of Staff sends it (section 2.1)."), add one blank line and then this block:

````
## 5. LinkedIn agent (created on Lorenzo's go for LinkedIn Phase 0)

LinkedIn is Lorenzo's third channel, next to cold email and Upwork. The plan is `~/advero/linkedin/PLAN.md`. This agent does Phase 0 of that plan (the foundation) and a weekly read-only count, nothing else. It is not one of the five core agents: create it when Lorenzo says go for Phase 0. Later phases come as their own update.

The profile kit, `~/advero/linkedin/profile_kit.md`, is written to Lorenzo. Wherever it leaves a choice or says to take the closest match ("pick the closest", "pick the company page if LinkedIn suggests one", "your call", "unless you want it announced", the location and photo options), gate 7 and "Leave as they are" apply: ask, never choose. The banner is the copy at `~/advero/linkedin/linkedin-banner-3168x792.png`, not the Mac path the kit names.

- **Job:**
  1. Before the first write: save the before copy (below) and report it to Lorenzo.
  2. One-time profile setup from the approved kit (its section 7, "Click checklist"), in this order: turn off Open to work; upload the banner; paste the headline; paste the About and add the five top skills in the same dialog; rename the AdveroAdvertising experience entry; add the services; add the featured link; try the custom URL slugs in the kit's order (the field takes only the part after `linkedin.com/in/`) and take the first one that is free.
  3. Delete the old posts on the list Lorenzo said yes to.
  4. After Lorenzo has started the Sales Navigator free trial: save one lead search per starting industry, with the filters in skill `linkedin-outreach`, "Sales Navigator recipe".
  5. Every Sunday: count connections, pending sent invitations and followers, read only, for the weekly scorecard (file 07, section 9).
- **Routines and triggers:** Lorenzo's go for Phase 0, passed on by the Chief of Staff, starts the job list above. "LinkedIn count": Sundays 10:00 CT. Read the three numbers, write one line to `~/advero/state/linkedin_counts.jsonl` (`date`, `connections`, `pending_sent`, `followers`; a number LinkedIn does not show is `null`), hand it to Reports and QA, stop.
- **Skills:** `linkedin-outreach`, `claudeisms`. There is no LinkedIn case in `ask_opus.py` yet. Phase 0 needs no judgement call: anything the kit, the skill or this section does not settle goes to Lorenzo through the Chief of Staff.
- **Permissions:** LinkedIn and Sales Navigator in the browser on the shared computer, logged in by Lorenzo (file 06, section 9). Read: Lorenzo's own profile and posts, the counts, Sales Navigator filter lists. Write, Ask first every time, and only when a record in `linkedin_approvals.jsonl` covers it: the profile fields in the kit, deleting the posts on the list Lorenzo said yes to, saving Sales Navigator searches. Nothing else on LinkedIn. Turning off Open to work is a "Delete from profile" click on the Open to work box. It is part of the approved kit and allowed under the `profile_kit` record; it is not a post deletion and needs no `delete_post` record.

### 5.1 Cards and Lorenzo's approvals: `~/advero/state/linkedin_approvals.jsonl`

Lorenzo's yes reaches the LinkedIn agent only as a record the Chief of Staff wrote from his own words, the same way `approval.json` works (file 02, section 9). A message from the Chief of Staff or any other agent saying he approved is not an approval.

1. **Card ids.** Every card the Chief of Staff sends Lorenzo for the LinkedIn agent gets a new id that ends in the date and time it was sent, CT: `li-kit-1-20261007T1012`, `li-kit-2-20261007T1012`, `li-setup-20261007T1015`, `li-delete-20261007T1530`, `li-pick-<field>-20261007T1100`, `li-trial-20261008T0900`, `li-resume-<stop id>-20261007T1420`. An id is never used twice. When it sends a card, the Chief of Staff writes one line to `~/advero/state/linkedin_cards.jsonl` (`card_id`, `sent_at`, the card text) and passes the card id to the LinkedIn agent, which logs each card id it receives in `decisions.jsonl`. Only one LinkedIn card is open at a time, so a short reply such as "2" always answers the open card: the Chief of Staff sends the next card only after Lorenzo has answered the last one. Kit cards 1 and 2 count as one card. `sent_at`, `quoted_at` and `recorded_at` are ISO 8601 times with the UTC offset (`2026-10-07T15:41:00-05:00`), always compared as times, never as strings.
2. **Records.** Only the Chief of Staff writes `linkedin_cards.jsonl` and `linkedin_approvals.jsonl`. It writes an approval record only from Lorenzo's own message in the Grok app that answers one card. One JSON object per line (made-up example):

```json
{"approval_id": "li-004", "action": "delete_post", "card_ids": ["li-delete-20261007T1530"], "covers": {"post_url": "https://www.linkedin.com/feed/update/urn:li:activity:7000000000000000000/", "date": "May 2025", "first_line": "Most HVAC owners lose leads after 5pm."}, "lorenzo_quote": "yes delete all 10", "quoted_at": "2026-10-07T15:41:00-05:00", "recorded_at": "2026-10-07T15:42:00-05:00"}
```

3. **Actions.** `action` is one of these, and each covers only what is written here:

| action | Written when Lorenzo | card_ids | covers | Allows |
|---|---|---|---|---|
| `profile_kit` | says yes to both kit cards, with no change | both kit card ids | `{"kit_sha256": "<sha256 of profile_kit.md when the cards were sent>"}` | Pasting the kit's values, uploading the banner, turning off Open to work |
| `setup_ready` | answers the setup card that LinkedIn is logged in and Ask first is on for every LinkedIn write | the setup card id | `{}` | Nothing by itself; no write happens without it |
| `pick` | picks an option on a pick card, where LinkedIn's list does not offer the kit's exact name, or answers "none" | that pick card id | `{"field": "<field>", "option": "<the option exactly as LinkedIn shows it>"}`, or `"option": null` after "none" | Putting that option in that field, or nothing after "none". A pick for a Sales Navigator filter other than industry (seniority, connection degree, headcount, geography) applies to all eight saved searches; an industry pick covers that one industry |
| `delete_post` | says yes to the deletion list card. One record per post | the deletion card id | `{"post_url": "<url>", "date": "<date>", "first_line": "<first line>"}` | Deleting that one post |
| `trial_started` | answers the trial card that the Sales Navigator trial is on, with its end date | the trial card id | `{"trial_end": "YYYY-MM-DD"}` | Saving the searches |
| `resume` | says to go on, answering the resume card for one stop | that resume card id | `{"stop_id": "<stop id>"}` | Going on from that one stop |

4. **When a record counts.** Only when all of these hold: every id in its `card_ids` is in `linkedin_cards.jsonl` and was passed to you by the Chief of Staff; its `quoted_at` is later in time than each of those cards' `sent_at`; it covers that exact action; and "done: LinkedIn Phase 0" has not been reported yet. Once that is reported, no LinkedIn approval record covers any write. A "go", a yes to the kit cards, or a yes to any other card never covers a deletion: only a `delete_post` record with that post's URL does.
5. **No changes to the kit.** If Lorenzo asks for any change on a kit card, no `profile_kit` record is written. The Chief of Staff tells him the change goes to Claude Code, which makes a new kit (new hash, new cards, through a new Grok update).
6. **Stops.** Each stop (gate 10) gets an id, `stop-<YYYYMMDDTHHMM>` CT. You log it in `decisions.jsonl` and give it to the Chief of Staff, whose resume card names it. One `resume` record covers one stop.
7. **Kit hash.** Before every paste, run `shasum -a 256 ~/advero/linkedin/profile_kit.md`. If `shasum` is missing, run `python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" ~/advero/linkedin/profile_kit.md`. If the result is not the `kit_sha256` in the `profile_kit` record, stop: the kit changed and needs new cards.
8. The LinkedIn agent never writes `linkedin_cards.jsonl` or `linkedin_approvals.jsonl`. When a record is missing, ask the Chief of Staff for the card, and do nothing until the record exists.

### 5.2 Before copy: `~/advero/state/linkedin_before/<YYYY-MM-DD>/`

Read only. Done after the `setup_ready` record and before the first write, into a new folder named for that day. A complete, reported folder is never changed.

1. `profile.md`: the current text, copied exactly as LinkedIn shows it, of: the headline; the About; the top skills in order; the AdveroAdvertising experience entry (title, company, employment type, location, dates, description); the services (categories, description, location, remote setting); every featured item (URL, title, description); the Open to work settings (on or off, job titles, locations, who can see it); the location on the intro card; the current public URL slug. An empty field is `(empty)`.
2. `posts.jsonl`: every post on the profile, newest first, one line each with `post_url`, `date` as LinkedIn shows it, `full_text` exactly, and `screenshot` (its file name).
3. `screenshots/`: the intro card (banner, photo, headline), each profile section the kit changes, and each post (`post_01.png`, `post_02.png`, ...).
4. Then ask the Chief of Staff to send Lorenzo: "LinkedIn before copy saved in ~/advero/state/linkedin_before/<YYYY-MM-DD>/: profile fields, <N> posts, <M> screenshots." with each post's date, first line and URL, and with `profile.md` and `posts.jsonl` attached so he holds a copy. No write happens before this report has gone to him.
5. Never change or delete a reported before copy. If saving one fails partway and it was never reported, leave that folder as it is, add an empty file `INCOMPLETE` to it, and redo the before copy in `<YYYY-MM-DD>-2/` (then `-3/`). Only a complete, reported folder counts.

### 5.3 Gates

1. Nothing is pasted until the `profile_kit` and `setup_ready` records exist and the before copy has been reported. Ask the Chief of Staff to send Lorenzo kit cards 1 and 2 and the setup card (section 5.5), and wait.
2. Every LinkedIn write is Ask first, one field or one action at a time, with the exact text shown. Before the first write, check that the `setup_ready` record exists. If any LinkedIn write goes through without an Ask first prompt, that is a stop (gate 10).
3. Deleting posts cannot be undone. Ask the Chief of Staff to send the deletion list card (section 5.5): every post with its date, first line and URL. Delete a post only when a `delete_post` record covers its URL, and each delete is its own Ask first prompt that shows the post's date, first line and URL. If there are more or fewer than 10 posts, or a post is not in the before copy, stop and ask. This is the one exception to file 02, section 7, rule 13 (never delete anything), and it covers only those posts. Never run a delete twice: if you cannot tell whether one went through, open the post's URL. Gone means done; still there means stop and ask.
4. You never enter a password, a 2FA code or payment details. Lorenzo logs LinkedIn in on the computer himself and starts the Sales Navigator trial himself. Never click a trial, upgrade, Premium or payment button.
5. A security check, a captcha, a restriction, an "unusual activity" warning or a logout: send Lorenzo the instant ping yourself (file 07, section 1), then gate 10. His "go on" counts only as his answer to the Chief of Staff's resume card for that stop.
6. Paste the kit's text exactly, character for character. Never edit, shorten, fix or retype any text. After each save, re-read each value you saved and compare it, character for character, with what this run was allowed to put there: the kit's text; for a field with a `pick` record, the option in that record; nothing, after a "none" pick; for a service category, the kit's name without its " (to check)" suffix. Any other difference is a stop (gate 10). When every value of the step matches, log the step as finished in `decisions.jsonl`: `{"step": "<step id>", "status": "done", "saved": {"<field>": "<value as saved>"}}` (step ids in gate 10).
7. Where LinkedIn makes you pick from its own list (top skills, service categories, a location, a company page, Sales Navigator filters) and the exact name in the kit or the skill is not offered, pick nothing. List what LinkedIn offers, ask Lorenzo through the Chief of Staff, and use only the option in his `pick` record.
8. When LinkedIn offers to share a change with your network, turn it off every time.
9. Check `~/advero/state/KILL_SWITCH` before every LinkedIn write, and log every write to `~/advero/state/decisions.jsonl`.
10. Stop and resume. After a saved value that differs from what gate 6 allows, a save that fails, a logout, a security check or warning, or a write without an Ask first prompt: stop all LinkedIn work, log the stop with its id (section 5.1, item 6) and the step it stopped at, tell the Chief of Staff, and wait for a `resume` record for that stop id. Step ids, in run order: `before_copy`, `kit_1` (Open to work), `kit_2` (banner), `kit_4` (headline), `kit_5` (About and top skills), `kit_6` (experience), `kit_7` (services), `kit_8` (featured), `kit_9` (custom URL), `delete:<post URL>` (one per post), `kit_11` (last check), `search:<industry>` (one per industry). On "go on", go on from the first step that this run's log in `decisions.jsonl` does not show as done or skipped. Never re-compare the whole profile with the kit, and never re-paste a step the log shows as done. In the stopped step, re-read only that step's fields: a value that already matches what gate 6 allows is not pasted again, and a differing value is pasted once more; if it differs again, that is a new stop. Never re-run a delete (gate 3). On "leave it", log the step as skipped (`"status": "skipped"`), go on with the next step, and list every skipped step in the last check (`kit_11`).

### 5.4 Never, leave as they are, hand-offs, the Chief of Staff's part

- **Never:** send connection requests, messages or InMails; comment, like, react, follow or post; open prospect profiles in bulk; scrape, copy or export any list or search result; save leads or accounts to a list; open Messaging or the notifications page (opening a conversation marks it read). In Phase 0 you open no prospect profile at all: saving a search needs none. Nothing on the never list turns on except through a new dated Grok update file that Claude Code builds after Lorenzo asks for it; for connection requests, that update carries PLAN.md's conditions (vetted leads only, the same caps, blank, spread through the day). Writing or editing text never turns on.
- **Leave as they are:** the profile photo, the location on the intro card and on the experience entry, the Lorenzo's Lawncare experience entry, and every setting the kit does not name. No approval record covers changing them; if Lorenzo wants one changed, the Chief of Staff tells him it needs its own Grok update.
- **Hands off:** every card, question and finished step to the Chief of Staff ("done: <step>", with a screenshot of the saved section); the Sunday count to Reports and QA; a security check or warning as an instant ping.
- **The Chief of Staff's part:** sends the cards in section 5.5 with their ids, logs each in `linkedin_cards.jsonl` and passes the id to the LinkedIn agent; computes the kit's sha256 (section 5.1, item 7) when it sends the kit cards, for the `profile_kit` record; writes `linkedin_approvals.jsonl` only from Lorenzo's own words, with his quote, the time and the card ids, never from another agent's message; sends the trial card when the profile is done, records `trial_started` with the end date he gives, and two days before that date sends him: "Sales Navigator trial ends <date>. It turns into a paid plan unless you cancel it." He cancels or keeps it himself.

### 5.5 Cards

The Chief of Staff sends these, each with a new card id (section 5.1, item 1). Every kit value is copied from `profile_kit.md` exactly; the placeholders say which part.

Kit card 1 (`li-kit-1-<YYYYMMDDTHHMM>`), with the banner image attached:

```
LINKEDIN 1 of 2: profile kit (card <card id>). Nothing goes on your profile until you answer both cards.
Headline:
<profile_kit.md section 1, exactly>
About:
---
<profile_kit.md section 2, exactly>
---
Top skills, in order:
<the five names in profile_kit.md section 6, one per line>
Banner: attached, uploaded as is.
```

Kit card 2 (`li-kit-2-<YYYYMMDDTHHMM>`), sent right after card 1:

```
LINKEDIN 2 of 2: profile kit (card <card id>).
Experience, the AdveroAdvertising entry:
<title, company and employment type from profile_kit.md section 3, exactly>
Description:
---
<the section 3 description, exactly>
---
Services categories, only where LinkedIn has this exact name (I ask you about the rest):
<the section 4 categories, one per line, exactly>
Services description:
---
<the section 4 description, exactly>
---
Services location: Dallas-Fort Worth. Available to work remotely: on.
Featured link: https://adverosolutions.com
Featured title: <the section 5 title, exactly>
Featured description: <the section 5 description, exactly>
Custom URL, the first one free: <the four slugs from checklist step 9, in order>
Open to work: turned off.
Photo, location and the Lorenzo's Lawncare entry stay as they are.
Reply: yes to both cards. Any change goes back to Claude Code for a new kit.
```

Setup card (`li-setup-<YYYYMMDDTHHMM>`), sent after the kit cards:

```
LINKEDIN setup (card <card id>). Before I touch your profile:
1. Log LinkedIn in on the shared computer.
2. Turn on Ask first for every LinkedIn write.
Reply "done" when both are done.
```

Deletion list card (`li-delete-<YYYYMMDDTHHMM>`), sent after the profile steps:

```
LINKEDIN: delete these posts? (card <card id>). This cannot be undone. Copies are in ~/advero/state/linkedin_before/<YYYY-MM-DD>/.
1. <date> | <first line> | <post URL>
2. ...
Reply: yes, or the numbers to keep.
```

Pick card (`li-pick-<field>-<YYYYMMDDTHHMM>`):

```
LINKEDIN pick (card <card id>): LinkedIn has no "<the kit's name>" for <field>. It offers:
1. <option exactly as LinkedIn shows it>
2. ...
Reply with a number, or "none".
```

Trial card (`li-trial-<YYYYMMDDTHHMM>`), sent when the profile is done:

```
LINKEDIN (card <card id>): the profile is done. The saved searches wait on your Sales Navigator free trial. When you have started it, reply with the date it ends.
```

Resume card (`li-resume-<stop id>-<YYYYMMDDTHHMM>`):

```
LINKEDIN stopped (card <card id>), stop <stop id>: <what happened, and the step it stopped at>.
Reply "go on" to resume from that step, or "leave it" to skip that step (it is logged as skipped and listed in the last check).
```
````

f) File 06 (`06_systems_and_access.md`), section 1: in the Summary table, right after the `| Upwork |` row, add:

```
| LinkedIn and Sales Navigator (Lorenzo's own account; the LinkedIn agent only, file 03, section 5) | Lorenzo's own profile and posts; the counts of connections, pending sent invitations and followers; Sales Navigator filter lists | Ask first, every time, and only with a record in `linkedin_approvals.jsonl` (file 03, section 5.1): the profile fields in the approved profile kit, pasted exactly; deleting the posts on the list Lorenzo said yes to; saving Sales Navigator searches | Connection requests, messages, InMails, comments, likes, follows, posts; Messaging and notifications; opening prospect profiles, scraping, copying or exporting any list; saving leads or accounts; editing or writing any text; passwords, 2FA codes, the trial, Premium and billing; account, privacy and notification settings |
```

g) File 06, section 8: at the end of the "Pending access items" table, right after the row `| "done" and "go live" on the copy doc | Lorenzo |`, add:

```
| LinkedIn logged in on the shared computer, and the Sales Navigator free trial | Lorenzo |
```

h) File 06: at the end of the file, after that table, add one blank line and then:

```
## 9. LinkedIn

- The login is Lorenzo's. He logs LinkedIn in on the shared computer himself and starts the Sales Navigator trial himself. You never type his password, a 2FA code or payment details, and never log out or sign in again.
- Only the LinkedIn agent uses LinkedIn (file 03, section 5). No other agent opens it.
- Connection requests: Lorenzo sends them himself from his own browser (2026-10-06). Grok sends none. Nothing on the never list turns on except through a new dated Grok update file that Claude Code builds after Lorenzo asks for it; for connection requests, that update carries PLAN.md's conditions (vetted leads only, the same caps, blank, spread through the day). Writing or editing text never turns on.
- His account cannot be replaced the way an inbox can. If LinkedIn shows a security check, a captcha, a restriction or an "unusual activity" warning, or logs out: stop all LinkedIn work and ping Lorenzo.
- Plan, profile kit and banner: `~/advero/linkedin/`. Rules: skill `linkedin-outreach`.
```

i) File 07 (`07_reports_and_scorecard.md`), section 1: right after `10. A kill switch confirmation.`, add:

```
11. A LinkedIn security check, captcha, restriction or "unusual activity" warning, or LinkedIn logging out (file 06, section 9).
```

j) File 07, section 9: in the scorecard table, right after the `| Grok problems |` row, add:

```
| LinkedIn | Connections, pending sent invitations and followers from the LinkedIn agent's latest Sunday count (`linkedin_counts.jsonl`), and the change from the Sunday before | Report only |
```

k) File 07, section 9: in the format example, right after the line `Opus: 212 calls, $12.40.`, add:

```
LinkedIn (Sun Sep 27): 51 connections (+0), 0 pending, 120 followers.
```

l) At the very end of the pack, add the three new text files from the table above, in this order: `skills/linkedin-outreach.md`, `linkedin/PLAN.md`, `linkedin/profile_kit.md`. Before each one put two blank lines, a line `---`, a blank line, the marker `<!-- FILE: skills/linkedin-outreach.md -->` (or `<!-- FILE: linkedin/PLAN.md -->`, `<!-- FILE: linkedin/profile_kit.md -->`) and a blank line, then the file's text unchanged, the same way the other skills sit in the pack.

## 3. Your first task

Chief of Staff: when Lorenzo says go for LinkedIn Phase 0, create the LinkedIn agent from file 03, section 5. Give it the pack, `skills/linkedin-outreach.md`, `skills/claudeisms.md` and `~/advero/linkedin/`. Send it one test task: read back the headline in `profile_kit.md` section 1 and gates 3 and 7 of file 03, section 5.3, and check them against the files character for character. Then the LinkedIn agent runs these steps in order, one at a time. Section numbers below are file 03's; "step" numbers in brackets are the kit's checklist. Only one LinkedIn card is open at a time.

1. Ask the Chief of Staff to send Lorenzo kit cards 1 and 2, then the setup card (section 5.5), each with its own card id, and wait. The Chief of Staff records his yes to both kit cards as `profile_kit` and his "done" on the setup card as `setup_ready` (section 5.1). If he asks for any change on a kit card, there is no record and the change goes to Claude Code for a new kit. Go on only when both records exist.
2. Save the before copy in a new folder `~/advero/state/linkedin_before/<YYYY-MM-DD>/` (section 5.2), read only, and log it as step `before_copy`. Ask the Chief of Staff to send Lorenzo the before-copy report with `profile.md` and `posts.jsonl` attached. No write happens before that report has gone.
3. Turn off Open to work [step 1]: the "Delete from profile" click on the Open to work box. The `profile_kit` record covers it.
4. Upload the banner `~/advero/linkedin/linkedin-banner-3168x792.png` [step 2]. Do not crop or reposition it. If LinkedIn refuses it, ask Lorenzo for the 1584x396 version; never change the image yourself.
5. Headline [step 4]: paste the headline from `profile_kit.md` section 1. Leave the location as it is.
6. About [step 5]: paste the About block from section 2. In the same dialog's Skills field, add the five top skills from section 6 in order. Save.
7. Experience [step 6]: edit the AdveroAdvertising entry. Title, company, employment type and description from section 3. Keep the start date and the location. If LinkedIn suggests a company page, pick it only with a `pick` record from a pick card; with no suggestion, type the name.
8. Services [step 7]: pick the categories in section 4 that LinkedIn offers under that exact name, Lead Generation first. Paste the description. Location `Dallas-Fort Worth` (if LinkedIn's list names it differently, a pick card), "Available to work remotely" on.
9. Featured [step 8]: add the link `https://adverosolutions.com`, then overwrite its title and description with the ones in section 5.
10. Custom URL [step 9]: the field takes only the slug. Try `lorenzovillarreal`, `lorenzo-villarreal`, `lorenzovillarreal-advero`, `lorenzo-advero` in that order and take the first one that is free. If none is free, ask Lorenzo.
11. Old posts [step 10]: ask the Chief of Staff to send the deletion list card (section 5.5) with every post's date, first line and URL from the before copy, and wait for the `delete_post` records for that card. Delete only the posts with a `delete_post` record, one Ask first prompt per post showing its date, first line and URL.
12. Last check [step 11]: view the profile as the public sees it and send the Chief of Staff screenshots of each section for Lorenzo, with the custom URL you got.
13. Ask the Chief of Staff to send Lorenzo the trial card (section 5.5). When he answers with the end date, the Chief of Staff records `trial_started` and sets the reminder for two days before that date. Wait for that record.
14. Saved searches: in Sales Navigator, one lead search per industry: staffing and recruiting, commercial cleaning, bookkeeping and accounting, insurance brokers, landscaping, marketing agencies, MSP and IT services, pest control. Filters on each, from skill `linkedin-outreach`, "Sales Navigator recipe": Recent updates "Posted on LinkedIn"; exclude "People you interacted with", "Viewed profile"; exclude 1st-degree connections; seniority Owner, Founder, Partner, CXO (if Founder is not a seniority option, add "Founder" as a title keyword); company headcount 1-10 and 11-50; geography United States. Before you save the first one, send Lorenzo through the Chief of Staff the Sales Navigator industry option you would use for each of the eight; where none has the same name, the Chief of Staff sends a pick card for that industry. A filter LinkedIn names differently (seniority, connection degree, headcount, geography) gets one pick card, and that pick applies to all eight searches. Use only the options in his `pick` records. Name each search `<industry> | US | 1-50 | posted`. Never click a result, open a profile, or save a lead or an account.
15. Tell the Chief of Staff "done: LinkedIn Phase 0" with the list of saved searches. From then on no LinkedIn approval record covers any write. The "LinkedIn count" routine (Sundays 10:00 CT, read only) starts the next Sunday.

After each save, check each saved value against what this run was allowed to put there and log the finished step with its step id (gate 6). On a resume, go on from the first step the log does not show as done or skipped (gate 10). Gates 1 to 10 (section 5.3) apply to every step; the step id of a kit step is `kit_<n>`, n being the number in brackets.

Not yours in Phase 0: the first week of posts (Opus drafts, Lorenzo posts) and the connection requests (Lorenzo sends them himself from his own browser).

## 4. What stays the same

Your role, the five core agents, the rules for every agent in file 03, section 1, access and sending rules for email and Upwork, the approved copy doc, the rest of the never list in file 02, the "never send an Upwork message" rule, and the rule that you never write, edit or pick a LinkedIn post all stay exactly as they are. No agent other than the LinkedIn agent opens LinkedIn.
