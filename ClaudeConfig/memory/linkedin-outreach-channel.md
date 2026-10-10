---
name: linkedin-outreach-channel
description: "Channel 3 (2026-10-06): LinkedIn outreach picked over communities; Jonatan's Maker School Loom playbook doc is the reference; build waits on Lorenzo's go + 3 answers"
metadata:
  node_type: memory
  type: project
  originSessionId: 71989dd9-0694-4a26-b83f-8f2055b489dc
  modified: 2026-10-07T00:07:49.682Z
---

On 2026-10-06 Lorenzo weighed communities vs LinkedIn outreach as his third acquisition channel, next to cold email and Upwork. Claude recommended LinkedIn. Reasons: it reuses the offers, proof and GHL setup; his niches' buyers are on LinkedIn; it reaches the 1,154 parked Microsoft leads; it can be counted daily. Communities come later, once one niche has closed deals. Offer Intel data (223 Maker School wins over 90 days): LinkedIn had 5, and communities had no channel category (about 3 wins mention one).

Reference playbook: "Copy of Linkedin outreach post", Google Doc `1kMiei1lCW3rMdc7iX8H2Hpiry-gH7rO7Z5cozJQaTAA`. It is Lorenzo's copy of a doc by Jonatan (jonatan@zaguryai.com), a Maker School member. The method:
- Blank connection requests at about 30% accepted, 40 a day and never more than 50, withdraw pending requests after 3 weeks.
- Sales Navigator with the "Posted on LinkedIn" filter.
- Profile aimed at one ICP and one offer.
- About a 1-minute Loom per accepted connection, downloaded and embedded in the DM.
- Follow-ups at 48 h, 4 days and 7 days, then a voice-note reactivation.
- Results: 70+ positive replies and $10k from 3,000 requests and 700 Looms. US leads reply at about 10%, UK and Dubai higher.

**Decisions 2026-10-06 (Lorenzo):**
- Follow Jonatan's method, with Looms.
- Broad positioning (AI agents for service businesses, matching the website and banner), not one niche.
- He deletes his old posts himself.
- He is building his own custom dashboard and tracker, so Claude doesn't build one; the skill defines the fields and statuses.
- Opus drafts posts only from real material: no invented stats.

**Account on 2026-10-06:** 51 connections, no Premium or Sales Nav, messy headline, no About, default banner, "Open to work" on. Readable through Claude in Chrome. Banner to reuse: Brand/social/linkedin/linkedin-banner-1584x396.png.

**Built and reviewed 2026-10-06.**
- Commit cfaff7f is on branch `channel/linkedin-outreach`, worktree `Desktop/AdveroSolutions/.worktrees/linkedin`.
- The live-write guard blocks `git push` from Claude, so Lorenzo pushes it himself.
- The old `generate_linkedin_content.md` directive is RETIRED: its generator, profile JSON and swipe file invent numbers.
- Parked polish for the outreach skill's reply edge cases:
  - a second reply on the same day;
  - a not_now reply that already gives a date;
  - questions that go quiet;
  - clearing the due date once the invite is sent.

**Later decisions, 2026-10-06:**
- Headline: "Helping businesses get leads in, calls booked and more revenue with AI agents | Founder, Advero Solutions".
  - He wants the agents tied to front-end revenue.
  - He doesn't want them tied to one thing.
  - He dropped "service businesses" from the headline.
- Lorenzo sends connection requests himself for now; Grok takes over later, only on his written go.
- Grok's LinkedIn agent does the Phase 0 setup in the browser, with "Ask first" (plan: `Agentic Worklfows/linkedin/PLAN.md`).

**Build files:** `Agentic Worklfows/linkedin/` (profile_kit.md, outreach_copy.md, README), `directives/USER/linkedin_outreach.md`, and the skill `~/.claude/skills/linkedin-outreach/`. linkedin-content was updated for the broad positioning. Lorenzo sends everything himself; nothing on LinkedIn is automated.

**Why:** his choice of channel 3 and the source he trusts for how to run it.
**How to apply:** never send connection requests or DMs, or edit his profile, without his explicit yes for that action. See [[linkedin-content]], [[offer-intel]], [[deliverability-2026-09-25]].
