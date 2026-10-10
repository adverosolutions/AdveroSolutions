---
name: personalization-philosophy-2026
description: Lorenzo's cold-email {{personalization}} opener philosophy (Sept 2026) — anchor + opinion, no closer, no sender-side beats, peer voice; plus the two-tier cold-read/researched design used for recruiting, cleaning, bookkeeping
metadata:
  type: feedback
---

Derived from six lines Lorenzo shared from a YouTuber campaign (2026-09-02) and his
explicit corrections. He said: don't copy them, extract the philosophy.

**The line = 1-2 sentences, 15-30 words, sits in {{personalization}} as the opener.**
1. Beat one: a CONCRETE ANCHOR that proves you looked (a number, a named thing, a named
   trait of their style). Never a generic compliment.
2. Beat two: PLAIN PRAISE of the anchor ("congrats on", "love that", "awesome work"),
   not analysis, not a consequence, not a label (see corrections below).
3. NO closer/ask ("can I run something by you" was wrong) — the email body carries it.
4. NO sender-side beats ("my gf says…", "common topic at our HQ") — Lorenzo excluded
   these explicitly on 2026-09-02, so never invent his life to make a line warmer.
5. Peer register: "man", "respect", "love that", contractions off is fine; no em dashes.

**VOICE CORRECTION (2026-09-06, Lorenzo, after seeing the first 10 production lines):**
"They don't sound human… no human would say those things at a bar." Rejected: aphorism
closers ("that kind of staying power is not an accident"), templated constructions ("is
about as X as it gets", "rarer than it should be"), reciting six client types, and the
first name tacked onto the END of a clause ("…gets Basit"). The governing rule is now
THE BAR TEST: write it exactly as you'd say it out loud to a stranger who just told you
what they do. Name goes at the START ("Hey Robert,") or not at all. 10-24 words,
contractions fine.

**VOICE CORRECTIONS 2-4 (2026-09-06/07), the one that stuck:** v2 verdicts ("that takes
nerve"), v3 labels + stock reactions ("that's a wide range. Bet it stays interesting."),
and v4 consequence guesses ("those guys must show up with a shoebox of closing
statements") were ALL rejected. On v4 Lorenzo said: "these aren't personalization lines
anymore… the first part isn't supposed to pitch, create an issue, or state an issue.
It's just to confirm that we did a little bit of research on the prospect." So the
line is exactly his YouTuber examples' shape: ONE SPECIFIC THING YOU SAW + PLAIN
PRAISE ("Huge work on the $72K." "Congrats on 35K." "Love your channel."). Nothing
analyzed, implied, guessed or labelled. 8-20 words. v5 examples: "Hey Robert, saw the
firm goes back to 1937, congrats on almost ninety years." / "Hey Basit, saw you guys
do taxes for flippers and syndicators, big fan of that." / "Hey Zineb, saw you guys
take on office and medical accounts, awesome work." Praise phrase rotates (love that /
awesome / congrats on / big fan / cool that you stuck with it), none on more than
~a third of a batch (variety cap in daily_apply.py flags excess for daily_rewrite.py).
Gate bans guessing words (must be, bet, probably, gotta be, no wonder), labels
("that's a <adj> <noun>"), verdicts and stock lines. Brief: personalize/prompts.json
(v1-v4 kept as prompts_vN.json). Lesson: every time I "improved" the reaction I was
editorializing; the reaction is praise, full stop.

**TIE-IN BEAT (2026-09-07, Lorenzo):** after fact + praise, a THIRD beat ties Lorenzo in
with something in common ("That's how I try to run my own shop too."). Two hard rules he
gave: (1) casual, like a text; (2) NICHE-CONSISTENT: in each campaign he is a specialist
who ONLY works with that niche, so the tie-in never mentions another vertical or "I work
with X as well" (to a recruiter, never "I've worked with HVAC companies"). Tie-ins come
from a fixed per-niche library in prompts.json `tiein_library` (one-lane / values /
years / pay-for-results / generic), never freeform, so nothing false about him ships.
Gate bans cross-niche phrases and requires a first-person beat. Lines are now 20-36 words.

**FINAL FORM, TEMPLATE MODE (2026-09-07):** after nine freeform iterations Lorenzo
called it ("we might have gone too far… no human being would ever say that") and
templatized: ONE fixed sentence for everybody, two variables. His template:
"Hey {first_name}, saw that you do {x}. That's something that's always intrigued me,
wondering if I can run something by you." Only X varies: a 3-10 word noun phrase
for what the company specifically does (named niche > services in the scrape's
company_description > niche + city for cold reads). No sentences are written by
models anymore; Haiku only fills X (50 leads/call), the gate judges X alone
(niche word present, no marketing words, no pronouns, no company name), and
prompts.json `_mode: template`. Lesson: when the user keeps rejecting voice,
stop iterating on voice and remove the degrees of freedom.
Then Lorenzo added a third slot: "That's exciting, {y}" where Y = a playful
exaggeration starting "you must", built on one detail from X or the city ("you must
have half of Long Island on speed dial"). First 400-run lessons (2026-09-07): Haiku
fill copied examples across leads (Treasure Coast on a California cleaner, X reused
across 4 firms) and produced ungrammatical shapes; the gate now checks grounding of X
and Y against the lead's own data, place names vs city/state, niche clashes, and
foreign companies. Sonnet rewrite pass fixed 204 → 27; a human read of every Y is
still required and cheap. Foreign leads (London, Seoul, Lagos, Managua, Ontario,
Israel) slip through when company_state is blank.

**Two-tier design (cold reading):**
- Tier 1 cold-read = assert a trait the research showed is near-universal in the niche
  (see [[cold-read-research-2026]]), then praise the CHOICE. Anchors the business type,
  never the website (a quarter of sites are dead). e.g. "Hey Terri, office and medical
  accounts, the medical ones must be a handful with all the protocols."
- Tier 2 researched = a non-guessable fact from the site/search (founding year, named
  niche, guarantee, credential, about-page voice), preserved as a NAMED anchor.
- Off-niche companies get "skipped", never a cold read.

**Why:** cold reading makes lines feel researched at scale; the guessability bar
([[personalization-line-generator]]) still applies to Tier 2.
**How to apply:** samples live in the Leads sheet as `SAMPLE v2`; review file
`research/PERSONALIZATION_REVIEW.csv`. Build per-niche briefs from the lines he approves.
