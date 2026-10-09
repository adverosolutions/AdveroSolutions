---
name: claudeisms
description: Lorenzo's rule against "Claudeisms" (in Grok, "Grokisms"), the sentence or tacked-on clause that restates, sums up or sells the point a message just made ("Nobody in the office has to remember to ask.", "No more chasing leads."). Applies to any model writing for Lorenzo: Claude, Grok Bot, Opus via API. Use whenever writing or editing copy for Lorenzo or his clients (cold emails, follow-ups, Upwork proposals and messages, LinkedIn, Maker School, DMs, and prompts that generate copy), and when he says "Claudeism" or "Grokism" or asks to check a draft for them.
---

# Claudeisms

A Claudeism is a line whose only job is to restate, sum up or sell what the
previous sentence already said. People texting a peer never write them. They
say the thing and stop.

## Who it applies to

Every model that writes anything Lorenzo or his clients will read: Claude in
Claude Code, Claude Opus 5.5 called through the API (the model that writes
and chooses customer-facing text), and Grok Bot. The name comes from Claude,
but the habit is the same in any model; in Grok it is a "Grokism" and gets
cut the same way.

Grok Bot never writes, edits or paraphrases customer-facing text; it sends
exactly the text it was given. So for Grok this rule covers what it does
write: its reports, hold cards and messages to Lorenzo. Grok never judges
the copy it sends: it acts on the action `decide()` returns and never holds,
delays or cuts a message over wording. Catching Claudeisms in customer-facing
text is Opus's job inside `decide()` and the template gate's job. See
`grok-operator`.

No Grok-specific tics are recorded yet. When Lorenzo flags one, add it under
"What they look like" with the date.

## The test

Delete the sentence (or the clause). If the reader loses no fact, no question
and no next step, it was a Claudeism. Leave it deleted. Do not rewrite it into
a different kicker.

## What they look like

- A kicker sentence after a point: "...the review request goes out on its own.
  ~~Nobody in the office has to remember to ask.~~"
- A "that way" or "which means" line that explains the benefit of what was just
  described: "...split them by type. ~~That way the big tickets don't get
  chased like a small repair.~~"
- A tacked-on benefit clause: "The text goes out in seconds~~, which means you
  never lose a lead~~."
- A tagline or fragment close: "No more chasing leads." "That's the whole
  point." "Simple as that." "It just works." "Fast. Simple. Done."

They show up most at the end of a paragraph, at the end of a message, and right
after a feature is described.

## What is fine

A sentence that adds something new: a fact, a detail of the client's project,
an answer to what they asked, a question, or a next step. A reason is fine when
it is new information the reader needs, not a restatement.

## How to apply

- When writing: end each point when the point is made.
- When checking a draft: run the test on every sentence and every "which
  means / that way / so that" clause, cut what fails, and show Lorenzo the cut
  lines so he can see what changed.
- When writing a prompt that generates copy: include the rule in the prompt,
  in plain words, with one or two examples. The runtime model does not see
  this skill.

## Sources (for maintainers)

- memory/feedback-claudeisms.md (rule set 2026-09-23, Upwork touch walkthrough)
- Agentic Worklfows/sections/3_upwork/walkthrough.md and
  sections/1_email_followup/sequence_final.md on origin/main (2026-09-23 cuts)
- memory/grokbot-orchestrator.md (2026-09-25: Grok sends, never writes)
- Lorenzo's request of 2026-09-25 naming "Claude and Grokisms"
