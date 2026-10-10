---
name: upwork-proposal-copy
description: "History and reasons behind Lorenzo's Upwork proposal templates (preview line, tldr body, timing line, closer); current locked text lives in the upwork skill, sentence case since 2026-09-21"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b4d10cb0-4b89-4132-a193-8c07de7ccd4c
  modified: 2026-09-03T20:36:56.544Z
---

**Current text lives in `~/.claude/skills/upwork/SKILL.md`, which wins over this file.** Since 2026-09-21 (Mark job, his ask "proper caps") proposals are sentence case, not lowercase, and the closer is "Looking forward to hearing from you. Just shoot me a message here on Upwork and we'll book that 15 minute call to get started." 2026-09-22: he chose to keep this template and the four P.S. bullets as is during the quality overhaul ([[upwork-quality-overhaul-2026-09]]). The templates below are the lowercase originals, kept for the reasoning.

Two canonical templates, picked by whether there's an actual build to show or it's an
audit/roadmap/methodology walkthrough. Both locked after live iteration until he said
"this is exactly what I was looking to write" / "absolutely fantastic" — treat these as
ground truth, don't re-derive from first principles per job.

## Template A — a real build exists (n8n/Make export, working canvas)

```
hey there 👋 i build systems like this all the time, so i went ahead and built
this one custom for you, [N]-min loom: https://www.loom.com/share/...

tldr: [one or two short lines — what the system does, no mechanics. end with
"the video walks through how."]

i can start [when], working demo by [when] (assuming we speak soon). estimated
timeline is [X] from kickoff to tested and handed off.

looking forward to hearing from you, just shoot me a message here on upwork to get started.

Lorenzo
```

## Template B — audit / roadmap / methodology walkthrough, nothing built

Locked 2026-08-26. Use when the Loom is Lorenzo talking through a thought-process
chart (see [[upwork-workflow-generator]] "process flowchart" note) rather than a
build on a canvas — audits, roadmaps, "how I'd approach this" methodology videos.

```
hey there 👋 i run this exact [audit / roadmap / X] for [their kind of business]
all the time, [N]-min walkthrough of what this would look like for you:
https://www.loom.com/share/...

[one paragraph: walk through the stages of the methodology and name the
metric-driven or evidence-driven differentiator — what makes it not a gut call.]

i can start [when], [audit/roadmap] delivered by [when]. estimated timeline is
[X] from kickoff to [deliverable] in hand.

looking forward to hearing from you, just shoot me a message here on upwork to get started.

Lorenzo
```

Corrected 2026-08-26 away from two earlier, worse openers for this case:
- "here is a [N]-minute video on [what it covers]" — flat, no credibility signal.
- Any tagline like "roi makes the call" / "metrics make the decisions" tacked onto
  the end of the preview line — he killed this explicitly: "no human says 'ROI
  makes the call.'" Don't invent a punchy abstract-noun-as-subject tagline. If you
  want a closing beat on the hook, it should sound like something a person would
  actually say, not a slogan.
The fix in both cases was the same move: replace the flat/awkward tail with a
credibility clause — "I do this all the time" — establishing a repeated, proven
pattern, exactly parallel to what Template A's hook already does with "a build
nearly identical to this."

Refined again 2026-08-26 after he'd already submitted one: the tail "walkthrough
of how i do it" became "walkthrough of what this would look like for you." Same
two-beat shape as Template A — credibility first ("i run this exact audit for
creators all the time"), then custom-for-them second ("what this would look like
for you"). Name their kind of business in the credibility half (creators, real
estate, agencies) rather than a generic "businesses." Don't drop the custom half
in favour of pure credibility — he flagged it needed to "look like it's for them."

## Shared rules across both templates

1. **Preview line — use the full ~150 characters, don't leave slack.** Corrected
   2026-08-24 after a version that only used 69 of 150 chars ("wasted" characters,
   his words). Default hook when a build exists, corrected 2026-09-03: "i build
   systems like this all the time, so i went ahead and built this one custom for
   you." Two beats — I do this constantly, and this one is yours. He retired the
   earlier "i just wrapped up a build nearly identical to this, then built this
   exact flow custom for your setup" and "built this exact system multiple times
   for other companies" wording: "no human would really say that." Keep the hook
   plain-spoken; the credibility beat is "all the time," not a claim about other
   companies. Runtime stays in the preview line — say "[N]-min loom" for a client
   who reads as Upwork-savvy/technical, "[N]-min video"/"[N]-minute walkthrough"
   when the client seems less familiar with the tool name itself (his call per job,
   flagged 2026-08-24: "I don't know if they're very familiar, right? You want to
   be careful"). `https://www.loom` is the last thing before the link spills past
   the cutoff — always compute the count, target close to 150 without going over.
2. **Body is a "tldr:" line, not a paragraph.** Locked 2026-09-03 after he adopted
   it on the invoice-tracking proposal: "tldr: [what the system does in one or two
   short lines]. the video walks through how." Deliberately brief — his words: "we
   don't want to give away too much information because the emphasis is on them
   watching the video." Say what it does, not how it works; the mechanics live in
   the Loom. No em dashes, no "it's not just X, it's Y," no tricolons, no
   abstract-noun taglines (see Template B correction above). Applies to Template
   B too when the video carries the methodology.
3. **Timing line.** Template A: "i can start [when], working demo by [when]
   (assuming we speak soon). estimated timeline is [X]." Template B: "i can start
   [when], [deliverable] delivered by [when]. estimated timeline is [X] from
   kickoff to [deliverable] in hand." Always start date + draft/delivery date.
   Then, when the timeline is more than a few days, the rush seed verbatim: "i can
   always get it done faster, i just have to move a few things around in my
   schedule." Locked 2026-09-09; it leaves room to upcharge when they want it
   quicker. Do
   NOT add a specific dollar estimate unless Lorenzo gives you the number himself —
   he cut a $250-350 estimate out of a draft even though the job explicitly asked
   for "estimated cost," so default to timeline only, cost only on request.
4. **Sign-off closer — SUPERSEDES the old "avoid stock closers, ask a direct
   question" rule for the closer specifically.** Always: "looking forward to
   hearing from you, just shoot me a message here on upwork to get started." Then a
   line break and "Lorenzo". The old rule (ask a concrete question instead of a
   stock closer) is dead for this slot.
5. **Sentence case** (proper capitalization) since 2026-09-21; was all lowercase before.
6. **Wave emoji (👋) specifically** in the greeting. Use the client's first name
   when the post shows one ("hey duaan 👋"), otherwise "hey there 👋" — he started
   doing this himself 2026-09-03. Recompute the preview length when the name is
   longer than "there", and double-check the spelling against the post; a
   misspelled name in the first three words undoes the whole line.
7. **First person singular**, "I" never "we".
8. **Never invent facts about the client's business or about Lorenzo's own
   history.** Ask before asserting anything unverified about either side. This
   includes claims like "I've done this in [X] industry before" — verify with him
   directly rather than assuming from memory or refusing outright once he's
   confirmed it's true.
9. **Say only what the video actually shows** — match the body's claim to whether
   it's a canvas walkthrough or a methodology/thought-process explainer.
10. **No deliverable exists** (ongoing ops role, nothing to hand over, not even an
    audit/roadmap): swap the delivery date for the actual next step, e.g. "worth a
    quick 5-minute call to go through your current setup."
11. **Never answer a post's screening-question list point by point.** Locked
    2026-08-27 after I drafted seven numbered answers for an "AI Systems Architect"
    post and he cut them: "that truly is just a waste of time... considering that
    the AI wrote them." Replace the whole block with his four case-study bullets,
    placed at the BOTTOM as a P.S. after the "Lorenzo" sign-off (exact text and
    placement in [[lorenzo-case-studies]]). Keep the body short; the P.S. carries
    the proof. Don't invent additional results beyond those four. Yes/no
    eligibility questions Upwork itself asks at submit time are separate and still
    need his real answers.

**Framing:** custom-for-them / proven-pattern is the core differentiator over
people batching one asset — both templates' hooks state it directly ("built this
exact flow custom for your setup" / "i do this exactly like this all the time")
rather than a softer "here's a gift" phrasing. For the audit template's body,
frame around money and growth (inefficiency, overspend, ROI, dollar impact) rather
than engineer language like "efficiency" or "step count" — but never as an
abstract-noun tagline in the preview line itself.

**Why:** view rate is driven almost entirely by that first line plus the visible
link, so wasting preview budget is a real cost, not a style nicety. Every rule
above was an explicit live correction on a real proposal, not a hypothetical —
when in doubt, the version he last said was "fantastic" wins over an earlier draft.

Related: [[upwork-proposal-assessment]], [[upwork-workflow-generator]]

**Required keyword (2026-09-29):** when a post asks you to start with a word (PROVENANCE, Deluge), put it inline on the first line, e.g. "Deluge. Hey there 👋 ...", never on its own line. A line break pushes the Loom link out of the preview. It still counts toward the 133-150.

**LOCKED opener for the next 100 proposals (2026-09-29):** "Hey [greeting] 👋 I do [X] builds all the time, so here's your [their system] finished, [N]-min video: https://www.loom.com/share/[LOOMURL]". The "just finished a similar build last week" line is dropped; Lorenzo: "it just doesn't sound very true, so people don't buy it." finalize now logs opener_variant `do-x-all-the-time` by default, so after 100 rows `sync_outcomes.py --report` compares it. The full rule is in the upwork skill under "LOCKED OPENER".
**Opener wording he called perfect (2026-09-30):** end the opener with "so here's your [system] finished and connected". The body adds "The build is done; the video is just a more visual way to show it running end to end." That's how he pitches every Loom: a full build, shown visually.
