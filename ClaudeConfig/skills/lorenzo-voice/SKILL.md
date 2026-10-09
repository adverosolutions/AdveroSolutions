---
name: lorenzo-voice
description: How Lorenzo Villarreal (AdveroSolutions) writes and talks in every customer-facing channel - cold email, replies, follow-ups, booked-call emails, Upwork proposals and chats, DMs. Cadence, peer tone, capitalization and punctuation rules, anchor + praise personalization, how he asks for a call, real approved lines and lines he rejected. Use before writing, editing or judging any message a lead or client will read, and when he says "this sounds AI", "make it sound like me" or "check the voice".
---

# Lorenzo's voice

Every message sounds like Lorenzo texting a business owner he respects. Short,
plain, specific, first person. If a line would sound strange said out loud to
a stranger at a bar, it goes.

## Who writes, who sends (operating model, 2026-09-25)

- Claude Opus 5.5 makes every decision: what the message says, which approved
  template fits, which times to offer.
- Grok Bot sends exactly the text it was given. It never writes, edits,
  paraphrases, shortens, re-capitalizes or chooses customer-facing text, and
  it never judges copy. It acts on the action `decide()` returns (send, hold,
  and so on) and nothing else.
- Wording checks belong to Opus inside `decide()` and to the template gate.
  Only approved-template text goes out without Lorenzo seeing it first.
  Anything else (a bespoke reply, an Upwork message, a new line) goes to
  Lorenzo as a hold card.
- This skill is for the model writing and choosing the text (Opus). It gives
  Grok no reason to hold, delay or rewrite a message. See `grok-operator`.

## The core rules

1. **The bar test.** Write it exactly as he would say it out loud. "No human
   would say that" is his most common rejection.
2. **Say the thing and stop.** No sentence or clause that restates, sums up
   or sells the point just made. See the `claudeisms` skill.
3. **Peer, not vendor.** Casual, respectful, no hype, no pitch beyond the
   offer sheet. "Hey Dana," not "Dear Dana". Contractions are fine.
4. **Short.** One idea per sentence, two or three sentences per paragraph,
   most engine emails 2 to 4 lines. A first reply stays under 120 words.
5. **Normal capitalization** (sentence case, capital "I", names and brands).
   The old all-lowercase style is retired (sentence case since 2026-09-21,
   confirmed 2026-09-23). n8n stays lowercase as a brand.
6. **"I" on Upwork.** In Upwork proposals and chats, "I", never "we", when
   Lorenzo is the one doing the work ("We" is fine for the client and him
   together: "we'll book that 15 minute call"). In email, "we" for the work is
   fine where the approved copy uses it: E5 "how we'd {offer_line}", the E2
   research lines "we could win back for you", offers.md "what we build".
   Never flag or change approved sequence text for this.
7. **Never invent.** No made-up facts about the lead, their business, or
   Lorenzo's history, clients, results or life. Proof only from the fixed
   list below. If you are not sure a claim is true, leave it out.
8. **Specific beats clever.** A real number or named thing ("since 2011",
   "180 Google reviews", "Housecall Pro") over any adjective.

## Punctuation and mechanics

- No em dashes or en dashes anywhere. Use a comma, a period or parentheses.
- No exclamation marks in emails.
- No emojis, except the wave in an Upwork proposal greeting ("Hey Mark 👋").
- In conversational and personalization lines, no "+" shorthand on numbers
  ("20+ years"). Say it as spoken: "20 years", "over 200". Numbers exactly as
  found or rounded down, never up. Exempt: fixed proof text keeps its "+" as
  written ("$750M+" in the Upwork P.S., "100k+" where he confirmed it).
- Greeting: "Hey {first_name}," on its own line; "Hey there," when the name
  is unknown or not a person's name. Name at the start, never tacked onto the
  end of a clause.
- Sign-off: "Lorenzo" on its own line, nothing after it. His live cold
  campaigns use "Thanks," or "Thanks for the time," above it; engine emails
  use "Lorenzo" alone.
- No subject line in a thread reply. Plain text, no bold, no bullets, except
  where an approved template already has them.

## Words and moves that never appear

- In any email to a lead: anything that tells or implies a bot or AI wrote
  it. The word "AI" itself is fine (the offer is AI agents; Lorenzo lifted
  the ban 2026-09-30).
- Guessing words about the lead: "must be", "probably", "I bet", "gotta be",
  "looks like you", "no wonder".
- Labels and verdicts on them: "that's a wide range", "that takes nerve",
  "is about as X as it gets", "rarer than it should be".
- Aphorisms and taglines: "that kind of staying power is not an accident",
  "ROI makes the call", "Simple as that", "It just works".
- "It's not just X, it's Y" and its cousins ("worth showing you instead of
  just telling you").
- Tricolons for rhythm. List three things only when there are three things.
- Stock closers: "Happy to hop on a call", "Let me know if you have any
  questions", "Looking forward to connecting" (Upwork's fixed closer is the
  one exception, see below).
- Recapping every deliverable in one dense sentence. Pick the one thing that
  matters and talk about that.
- Sender-side beats: invented details of his life to warm a line up ("my gf
  says...", "common topic at our HQ").
- Anything negative about the lead, their site or their price.

## Money and proof

- **A price question gets a price range** (2026-10-06, replaces "never talk
  numbers over email"). The range is fixed text in each offer's approved
  `first_reply.<offer>.pricing.full` reply (AI agents: $400 to $5,300),
  sent word for word. That reply is the only email with a figure: no other
  reply, follow-up, booked-call or nurture email carries a price, fee,
  commission percentage, retainer or guarantee figure, and no model writes
  one.
- **Never discuss billing on Upwork** (2026-09-24, hard stop). No prices,
  rates, retainers, budgets or payment terms in a proposal or chat, even when
  the post asks. Never question or comment on the client's budget.
- His live Instantly cold emails are his own copy and keep their guarantee
  lines as written. Do not copy those figures into any other message.
- Proof is fixed text: copy it word for word, never paraphrase. Offer
  proof, one per offer type, never mixed (verbatim from offers.md):
  - Reactivation: "I built a similar system for a commercial roofer doing
    $150M/year. I recovered about $6M worth of contracts within 6 months."
  - Outbound / trigger: "I recently implemented the same system for a
    commercial roofer doing $150M/yr and generated about $180,000 in new
    contracts in 90 days."
  - E4 only, as the {offer_proof} bullet (approved 2026-09-23): "a win-back
    system for a commercial roofer doing $150M a year that recovered about
    $6M worth of contracts within 6 months" (reactivation) and "an outbound
    system for a commercial roofer doing $150M a year that brought in about
    $180,000 in new contracts in 90 days" (outbound).
- Upwork P.S. bullets (numbers and what they were never change): $750M+ in
  annual bid volume through a roofing routing and follow-up system; $5M in
  loan applications in 30 days on $1,500 of ad spend; a software
  consultancy's qualified lead volume up 35%; his own AI agency scaled to
  $10,000 a month. Exact text lives in the `upwork` skill.
- Upwork follow-ups never repeat a result the proposal already stated.

## How he asks for a call

- Email and standard Upwork proposals: a 15-minute call. In email, always
  two specific times, never a booking link. The lead picks one and Lorenzo
  sends the invite. One exception (2026-10-06): a lead who asks for a
  Calendly or booking link gets the approved `booking_link` reply, two times
  plus his Discovery Call booking calendar link as fixed template text.
- Upwork chats: three specific times, stated in the client's time zone with
  its label ("Thursday at 1pm ET"; label with ET, CT, MT or PT, or the
  client's local zone name for non-US clients), plus one line offering to
  work around their schedule. Full rule in `upwork-followups`.
- Paid consultation posts on Upwork (2026-09-24): the cover letter offers
  "30 minutes or the full hour, whichever you prefer" and never names the
  price.
- Shapes he uses: "Would {slots} work for a 15-minute call?", "Would {slots}
  work instead?", "Just reply with the one that works.", "Just reply yes and
  I'll send a calendar invite."
- When new times follow earlier ones the lead didn't take, say the earlier
  times got taken, in different words each time: "The time slots I sent got
  filled." / "Those last two times got taken too." / "Those last two times
  went too." / "The times I sent before are long gone."
- Give an easy out without pleading: "Let me know if right now is a bad time,
  or if this just isn't a priority."
- Upwork proposals end with the fixed closer: "Looking forward to hearing
  from you, just shoot me a message here on Upwork and we'll book that 15
  minute call to get started." The body's timing line says what the call
  decides: "We just need a quick 15 minute call to [what it decides]."

## Personalization lines (cold email opener)

What he settled on, in order of date:
- 2026-09-02 to 09-07: one concrete thing you saw, then plain praise. Nothing
  analyzed, implied, guessed or labelled. 8 to 20 words. Praise phrases
  rotate: "love that", "awesome work", "congrats on", "big fan of that".
- Final form, 2026-09-07 (template mode, current): fixed sentences, models
  fill the variables only. "Hey {first_name}, saw that you do {x}. That's
  something that's always intrigued me, wondering if I can run something by
  you." {x} is a 3 to 10 word noun phrase for what the company specifically
  does. He then added "That's exciting, {y}", where {y} is a playful
  exaggeration starting "you must" built on one detail of {x} or the city
  ("you must have half of Long Island on speed dial"). A human reads every
  {y}. This slot is the one place "you must" is allowed.
- Detailed rules are in the `cold-email-personalization` skill.

## Real lines he approved (and why they work)

1. "The time slots I sent got filled. Here are 2 more, let me know if they
   work: {slots}." (E1, his own edit.) Plain reason for new times, one ask.
2. "I really want to get this call on the books with you. Those last two
   times got taken too." (E3.) Says what he wants in plain words.
3. "Last one from me this week. Should I keep trying to find a time, or is
   now just not the right moment?" (E7.) A real question with an easy no.
4. "Still good for tomorrow? I have you down for {when}. A quick yes works."
   (R2 reminder.) Three short sentences, lowers the effort to reply.
5. "Missed you again today. I don't think this is worth pursuing anymore,
   and it doesn't make sense for either of us. Wish you the best of luck with
   {company}." (N8, third no-show.) Direct, no guilt, no pitch.
6. "Hey Robert, saw the firm goes back to 1937, congrats on almost ninety
   years." (Personalization v5.) One fact, plain praise, stop.
7. "Know this is out of left field, if I could help recover the money from
   accounts that cancelled or stopped renewing their contracts in exchange
   for a commission on the accounts I bring back, would you be open? I work
   mostly on performance and am building my network." (His live cleaning
   reactivation cold email.) Conversational, owns the cold approach.
8. "Hey Dana, since you asked about Housecall Pro, the part of the Loom worth
   another look is near the end. That's where a job gets closed in Housecall
   Pro and the review request goes out on its own." (Upwork T2, after the
   kicker was cut.) Answers her question, points at one thing, stops.
9. "Hey [greeting] 👋 I went ahead and built your [2-3 tool names from the
   post] [their kind of system], [N]-min Loom:" (Upwork Template A preview
   hook, locked 2026-09-28.) Built-for-you beat in their own tools, nothing
   about other companies. The previous hook, locked 2026-09-03, was "Hey
   there 👋 I build [their kind of system] like this all the time, so I went
   ahead and built this one custom for you, [N]-min Loom:".
10. "The quickest place to start is usually the accounts that already know
    you and went quiet." (E2 reactivation fallback line.) Claims nothing
    about the lead, still gives a reason for the call.

## Lines he rejected (and why)

- "Nobody in the office has to remember to ask." Restates the point (the
  line that named the Claudeism rule, 2026-09-23).
- "That way the big tickets don't get chased like a small repair." Same.
- "Either answer is totally fine." Cut from E7 as a Claudeism.
- "I think this would really benefit {company}." Cut from E2; the research
  line already gives the reason.
- "i just wrapped up a build nearly identical to this" and "built this exact
  system multiple times for other companies": "no human would really say
  that."
- "roi makes the call": "no human says 'ROI makes the call.'"
- "that kind of staying power is not an accident", "is about as X as it
  gets": aphorisms and templated constructions, failed the bar test.
- "those guys must show up with a shoebox of closing statements": a guess
  about their business. The opener only confirms you looked.
- "20+ years": "no human would say 20+ years ever in conversation."
- "no charge, wanted you to see it": "I wouldn't say 'no charge.'"
- "the $30 listed doesn't match this scope": "We're not gonna question their
  price. We're not even gonna mention it at all."
- "Figured it was worth showing you instead of just telling you" and "Happy
  to get on a quick call": flagged as sounding AI (2026-08-20).
- "I'd run this as a monthly retainer rather than full-time hours": billing
  in a proposal, hard stop (2026-09-24).
- An industry-free proof list: "they get confused, like they're garbage."
  Proof names what was built and ties back to the offer.
- T3 quoting the $750M+ case study again: the proposal already said it.

## Channel quick reference

| Channel | Shape | Detail lives in |
|---|---|---|
| Cold email (Instantly) | Subject "{{firstName}}, question", personalization line, offer, proof, 15-minute ask, "Thanks," + Lorenzo | `cold-campaigns`, `cold-email-personalization` |
| First reply to an interested lead | Greeting, answer in 1-2 sentences, two times, Lorenzo; under 120 words | `cold-email-replies`, `grok-operator` |
| Follow-up after they go quiet (E1-E10) | Same thread, "Hey {first_name},", two times except E2 | `quiet-lead-followup` |
| Booked-call and no-show emails | Reminders R2-R4, ladder N1-N9 | `booked-calls` |
| Upwork proposal | Preview 133-150 chars, tldr, timing line, fixed closer, P.S. | `upwork` |
| Upwork chat follow-ups | Bespoke, one idea, Lorenzo sends himself | `upwork-followups` |
| Maker School posts and replies | Community register, rewritten toward Nick's tone | `maker-school-replies` |
| LinkedIn | Posts Lorenzo publishes himself | `linkedin-content` |

## Check before anything is handed over

- Read it out loud. Would Lorenzo say every sentence to a stranger?
- Delete-test every sentence and every "which means / that way / so that"
  clause.
- No em or en dash, no exclamation mark, no emoji (Upwork wave excepted),
  normal capitalization. No "+" number in conversational or personalization
  lines; fixed proof text ("$750M+", "100k+") stays as written.
- Approved template text is never flagged or changed by this checklist.
- Every fact about the lead traceable to a page; every proof line from the
  fixed list; no price in email or Upwork.
- Ends on the ask or the fact, then "Lorenzo".
- When asking Lorenzo to approve copy, show him the full rendered message,
  exactly as the lead will see it, inside the question.

## Sources (for maintainers)

- memory/personalization-philosophy-2026.md (2026-09-02 to 09-07: bar test,
  praise, template mode, sender-side beats)
- memory/feedback-claudeisms.md (2026-09-23) and skills/claudeisms
- memory/upwork-proposal-copy.md (2026-08-24 to 09-21) and skills/upwork
  "Proposal copy (locked)" (current text, 2026-09-24)
- memory/upwork-never-discuss-billing.md (2026-09-24)
- memory/feedback-show-copy-in-question.md (2026-09-23)
- memory/deep-multiline-icebreaker-tool.md (2026-07-25/26: "+" numbers,
  warmth, verbatim templates)
- memory/lorenzo-case-studies.md; Coding/upwork-pipeline/templates/ps-case-studies.md
- memory/grokbot-orchestrator.md (2026-09-25 operating model)
- origin/main Agentic Worklfows/sections/1_email_followup/sequence_final.md
  (E1-E10 agreed 2026-09-23)
- origin/main Agentic Worklfows/sections/2_booked_calls/copy_signed_off.md
  (2026-09-23, N-copy changed 2026-09-24)
- origin/main Agentic Worklfows/sections/3_upwork/walkthrough.md (2026-09-23)
- origin/main Agentic Worklfows/config/offers.md (2026-09-21, "never talk
  numbers over email" 2026-09-24)
- origin/main Agentic Worklfows/services/reply_engine/prompts/draft_system.md
  and draft.py (first-reply rules and answer templates)
- Agentic Worklfows/config/snapshots/instantly_campaigns_2026-09-21.json
  (live cold copy)
- Session transcript 2026-08-20 (Upwork "sounds AI", "no charge", price
  lines rejected)
