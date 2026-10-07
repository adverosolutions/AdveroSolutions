# LinkedIn Outreach

**Purpose:** Run the LinkedIn channel: Sales Navigator list, blank connection requests, a personal Loom DM to each new connection, follow-ups FU1 to FU3, a voice note months later
**When to use:** Every working day once Looms start; week 1 is profile, connection requests and posting only
**Frequency:** Daily block, Sunday accepted-connections update, weekly numbers

**IMPORTANT:** Lorenzo does every prospect-facing action on LinkedIn himself (connection requests, Looms, DMs, voice notes). Grok Bot's LinkedIn agent does only the Phase 0 setup (profile from the approved kit, deleting the old posts after his yes, Sales Navigator saved searches) and weekly counts, with Ask first on every write. Nothing on Grok's never list turns on except through a new dated Grok update file that Claude Code builds after Lorenzo asks for it; for connection requests, that update carries PLAN.md's conditions (vetted leads only, the same caps, blank, spread through the day). Writing or editing text never turns on. Claude only drafts and never acts on LinkedIn. His personal account can't be replaced like an email inbox.

---

## What This Does

Follows Jonatan's (Maker School) Loom playbook, chosen by Lorenzo on 2026-10-06, with broad positioning: service businesses that close new business on a call, a walkthrough or a quote.

1. Grok's LinkedIn agent saves the Sales Navigator searches (one per starting industry). Lorenzo works the lists, vets each lead and sends blank connection requests from his own browser.
2. Each block he opens 10 new connections, checks fit and types their rows into his own dashboard.
3. Claude fills the Loom script and DM for each row from the copy file.
4. Lorenzo records and sends the Looms, then the follow-ups Claude lists as due, then the day's connection requests.
5. Positive replies get two specific call times; Lorenzo sends the invite.

---

## Where Everything Lives

| What | Where |
|------|-------|
| The operating manual (setup weeks, Sales Navigator recipe, limits, daily block, follow-up timing, tracker fields and stages, drafting rules, weekly numbers, don'ts) | `~/.claude/skills/linkedin-outreach/SKILL.md` |
| Every message text (connection request, Loom scripts A and B, DMs, FU1 to FU3, voice note, reply templates) | `Agentic Worklfows/linkedin/outreach_copy.md` |
| Plan (phases, who does what, gates) | `Agentic Worklfows/linkedin/PLAN.md` |
| Profile (headline, About, banner, services, checklist) | `Agentic Worklfows/linkedin/profile_kit.md` |
| Grok's LinkedIn agent | `Agentic Worklfows/agents/grokbot/onboarding/03_team.md` section 5; update file `agents/grokbot/updates/2026-10-06_linkedin-foundation.md` |
| Posts | `linkedin-content` skill |
| Voice rules | `lorenzo-voice` and `claudeisms` skills |
| Call times | `Coding/lead-scrape-2026/slots_daily.py` dry-run (read-only GHL free slots), or Lorenzo's calendar |

---

## Required Tools

None. No execution script and no tracker: Lorenzo is building his own dashboard. The skill defines the fields and stages it should hold.

---

## Input Format

```
"Write the Loom DMs" + 10 pasted rows (first name, role, company, what_they_do, variant)
"LinkedIn follow-ups due" + pasted rows or an export
"LinkedIn reply" + the reply and the lead's row
"LinkedIn numbers this week" + an export
```

---

## Rules That Never Bend

- Never more than 50 connection requests in one day (Jonatan's experience, not LinkedIn policy).
- No note on connection requests.
- Template text only: fill placeholders, never write new sentences per lead.
- Two specific times for a 15-minute call, never a booking link.
- No price figures by message.
- No invented proof.

---

## Learnings

- 2026-10-06: Channel set up. Lorenzo had 51 connections; Looms start at about 200. Sales Navigator not bought yet.
