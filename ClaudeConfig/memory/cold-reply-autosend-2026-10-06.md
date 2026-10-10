---
name: cold-reply-autosend-2026-10-06
description: "2026-10-06 decisions: Grok auto-sends common cold-email replies (interested, price/tell me more, send info/Calendly) from approved templates; price RANGE allowed in email; auto-blocklist; E1 veto dropped; Upwork stays hand-sent with band from private assessment"
metadata:
  type: project
---

Lorenzo, 2026-10-06 (follow-up process chat, branch section/followup-autosend in .worktrees/followups):
- Cold email can be fully automated; Upwork replies cannot (drafts only, he sends).
- Grok auto-sends, from approved templates, with no card: interested with no time (two times), price / "tell me more" / how it works, send info / Calendly link ask (no link, two times). A fitting named time already auto-books with "Locked in".
- Clear unsubscribe / hostile replies are blocklisted the same day without asking him; a buying signal in the same reply still goes to him.
- Still a card: referrals, neutral questions, mixed yes-and-no, competitor/contract talk, other languages, confidence under 0.8.
- Price questions in email get a RANGE (overrides "we never talk numbers over email", 2026-09-24). He gave ranges twice in Sep (Sopio booked on "20% to 30%"). AI agents band: $400 to $5,300 (2026-10-06).
- A lead asking for a Calendly/booking link gets two times AND his GHL calendar link (Discovery Call widget in ids.json); the only link besides Zoom.
- Approved AI agents first replies (2026-10-06): interested = "Glad to hear it." straight to two times; tell me more = "Glad you asked. Quick overview: ... If you like it, I build them. If not, the plan is yours to keep."; send info; price with the range. Exact text in the new doc build.
- E1 veto heads-up is dropped; E1 sends at 10:00 CT like the rest.
- Upwork first reply after interest: price range default $500 to $3,500 (Lorenzo 2026-10-06: "you can go above never below 500"). Low end near the client's budget or slightly under, never below $500; top is $3,500 or the assessment's higher standard price. Supersedes the earlier "band from assessment only, else NEEDS_YOU".
- Upwork drafts keep banning exclamation marks (2026-10-06), even though his own typed Upwork messages use them.

**Why:** he doesn't want approval cards for the common replies; 75% of real replies (Sep 15-30) need no email at all, the rest are a handful of types.

**How to apply:** templates still need his approval (full rendered text in the question) before anything sends; nothing live until "go live". Related: [[cold-email-template-autosend]], [[grokbot-orchestrator]], [[upwork-followup-pipeline]], [[no-live-changes-until-tested]].

Later 2026-10-06:
- Auto-send set narrowed to an allow list: the five ai_agents first replies (base text only), E1-E10, and the basic "Locked in". Show-rate, no-show, already-booked, counters and every variant are hold cards (booked-call reminders paused since Oct 5).
- Booking order: Grok books a fitting named time in GHL right away (no Ask first for that one action), then sends "Locked in" only once the appointment exists. The slot stays reserved for that lead until then.
- Call times in emails stay Central only ("Thu 2:00pm or Fri 3:00pm CT"), even though the approval samples showed the lead's local time.
- Zoom IS connected on the GHL Discovery Call calendar (verified read-only 2026-10-06). Calendar opens 11:00, but replies offer 12-6 CT.
- New approval doc build df0ec92ac7a26ada passed review; upload waits for the Grok gate to pass review so the wording matches.
- Upwork framework drafts (commits fe93b14, 2fa3578, 29b5ad6) failed review 3 times (last at max effort) on regex gate gaps; Lorenzo ACCEPTED them as is (2026-10-06): he reads every draft, the card flags any price the client named. Known gaps: a draft can agree to the client's number in unusual wording ("...$3,500, so your budget works", "That's fine with me"), the agreement check misses statements like "I have $1,000 for this", some rate words slip past the band mask, and unusual assessment wording can raise the top. Fallback plan if a bad draft shows up: a second Opus read of the price line, not more regex.
- 2026-10-08: a lead already in E1-E10 who asks "how much?"/"tell me more" still gets the approved first-reply template automatically (not strict first contact). A lead who has or had a call never gets an automatic first reply or booking.
- 2026-10-08 Orca: Claude was missing from Orca's agent menu because Orca restarted (17:47) while Claude Code was mid auto-update (17:43-17:49, npm package under nvm). Fix = quit and reopen Orca once claude --version works. Orca's daemon keeps sessions alive across an Orca restart.
