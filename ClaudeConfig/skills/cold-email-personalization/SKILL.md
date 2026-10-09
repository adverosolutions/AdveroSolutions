---
name: cold-email-personalization
description: The per-lead opener that fills {{personalization}} at the top of Lorenzo's cold emails. Covers his philosophy (one specific thing you saw, plain praise, no pitch, the bar test), the locked template mode for recruiting, cleaning and bookkeeping ("Hey {first_name}, saw that you do {x}. That's exciting, {y}, ..."), X and Y rules with real examples, what is safe to assert blind per niche, the guessability test, the med-spa angle library, and the QA gate. Use for "personalize leads", "write the icebreaker", "personalization line", "opener", "cold read", or checking a batch of lines.
---

# Cold email personalization

The line proves someone looked at the business for 30 seconds. It is not insight, not a
pitch, not a problem statement. The email body carries the offer.

Lorenzo's wider voice rules are in `lorenzo-voice`; the kicker-line ban is in `claudeisms`.
The campaigns the line goes into are in `cold-campaigns`.

## Who does what (decided 2026-09-25)

- **Claude Opus 5.5** decides every line: what X and Y are for each lead, and whether a
  line passes. Scripts and cheap models may fetch pages and extract facts.
- **Grok Bot** never writes, edits, paraphrases or picks a personalization line. If a line
  fails at send time, it reports; it does not rewrite.
- **Lorenzo** approves the template and reads samples. His literal copy is used verbatim.

## The philosophy (Lorenzo, September 2026)

1. **One concrete anchor** that proves you looked: a named niche, a founding year, a named
   client type. Never a generic compliment.
2. **Plain praise** of that anchor: "congrats on", "love that", "big fan of that",
   "awesome work". Nothing analysed, implied, guessed or labelled.
3. **No closer or ask** beyond the template's own words.
4. **No sender-side beats.** Never invent Lorenzo's life ("my gf says...", "common topic at
   our HQ").
5. **The bar test:** write it exactly as you'd say it out loud to a stranger who just told
   you what they do. Name at the start ("Hey Robert,") or not at all.
6. Peer register, contractions fine, no em dashes, no exclamation marks.

Rejected along the way, never bring back: aphorism closers ("that kind of staying power is
not an accident"), templated constructions ("is about as X as it gets", "rarer than it
should be"), reciting a list of client types, the name tacked onto the end, verdicts ("that
takes nerve"), labels plus stock reactions ("that's a wide range. Bet it stays
interesting."), and consequence guesses ("those guys must show up with a shoebox of closing
statements"). On that last one he said the first part "isn't supposed to pitch, create an
issue, or state an issue. It's just to confirm that we did a little bit of research."

He approved these (v5, 2026-09-07):
- "Hey Robert, saw the firm goes back to 1937, congrats on almost ninety years."
- "Hey Basit, saw you guys do taxes for flippers and syndicators, big fan of that."
- "Hey Zineb, saw you guys take on office and medical accounts, awesome work."

## Locked form: template mode (2026-09-07, current)

After nine freeform rounds Lorenzo said "we might have gone too far... no human being would
ever say that" and fixed one sentence for everyone. No model writes sentences any more;
only two slots vary.

```
Hey {first_name}, saw that you do {x}. That's exciting, {y}, wondering if I can run something by you.
```

No first name: `Hey, saw that you do {x}. That's exciting, {y}, wondering if I can run something by you.`

### X: what this company specifically does

- 3-10 word noun phrase that reads naturally after "saw that you do".
- Order of preference: (1) the named niche or client type from their site; (2) the specific
  services in the company description; (3) the niche plus their city.
- Must contain the niche word: recruiting/search/staffing/placements/hiring;
  cleaning/janitorial; tax/accounting/bookkeeping/CPA/payroll.
- Lowercase except proper nouns. No period. No "you", "your", "we", "our", no company name.
- Never invent a client type, place or service that is not in the lead's data.
- No marketing words: solutions, premier, state of the art, unparalleled, full service,
  tailored, comprehensive.

Examples: "recruiting for commercial HVAC and electrical companies", "executive search and
job transition consulting", "taxes for real estate investors and flippers", "CPA and tax work
for Long Island business owners", "commercial cleaning for medical facilities and retail
spaces", "janitorial work for banks up in North Idaho".

### Y: a friendly exaggeration

- Starts with "you must", 4-12 words, built on one detail from X or their city/state.
  Obviously not literal, so it can't be wrong. Warm and a little funny.
- Reference line: "you must have half of Long Island on speed dial".
- Shapes to rotate: "have half of <place> on speed dial", "know every <client type> in
  <place> by name", "be able to <core task> in your sleep", "have a desk at half your
  clients' offices by now", "know every <building type> on the <area> by now".
- Never a problem, pain, advice, pitch or judgement. Banned: busy, handful, grind, nightmare,
  headache, stress, tough, hard, crazy. No questions. No invented places or client types.
- No single shape on more than a third of a batch.

Examples: "you must know every flipper in the five boroughs by name", "you must be able to
close a month's books in your sleep", "you must know every clinic manager in town by name",
"you must have one of the deepest rolodexes in the business".

### {{specialty}} (recruiting outbound only)

1-4 words for the niche they recruit, reading naturally before "roles" ("commercial HVAC and
electrical", "agtech and foodtech", "executive"). Blank when unknown. The upload falls back
to "your clients'", which 2,507 live recruiting leads carry: that is filler, not data.

## Two tiers

- **Tier 2, researched:** a non-guessable fact from the site (named niche, founding year,
  guarantee wording, non-default credential like CIMS, GBAC, Enrolled Agent, QuickBooks
  ProAdvisor), kept as a named anchor. Plain "CPA" or "licensed and insured" is not
  distinctive.
- **Tier 1, cold read:** assert only a trait at least 80% of the niche shares, anchored to
  the business type, never the website (a quarter to a third of sites are dead).
- **Off-niche companies are skipped**, never cold-read.

Safe to assert blind (random sample, 2026-09-02):
- Recruiting: they specialise in an industry or role (5/5). Nothing else.
- Bookkeeping: small-business focus, personal-relationship positioning, client portal,
  individual tax too. Do not assume CPA (3/5).
- Cleaning: they serve offices (6/6) and medical/healthcare (5/6). Eco/green, free quote,
  years in business and custom plans are coin flips.

## The guessability test (all niches)

Before using a fact, ask: could someone guess this about a random company in the niche and
be right, without researching this one? If yes, it cannot be the anchor, however true. A
good fact can also be diluted in writing: keep the named thing (publication, credential,
device), do not turn it into an adjective.

## Location

Use `company_city` / `company_state`. The lead's `state` and `city` are the contact's
LinkedIn location and differ from the company's for 16-34% of leads. Never name a city
from `state`.

## QA gate (every line, before it ships)

- Template intact; X and Y grounded in the lead's own data; place names match city/state.
- No em dashes, no "!", no AI, automation or tool words, no price, no pitch, no call to
  action, no "+" shorthand on numbers ("20+ years"), no fabricated percentages.
- Banned words match on word boundaries ("air ducts" and "Bottom Line Bookkeeping" are fine).
- No guessing words (must be, bet, probably, gotta be, no wonder) outside the fixed "you must".
- No niche clash, no foreign company (skip Seoul, Lagos, Ontario and similar when state is blank).
- Batch variety: no reaction shape on more than about 30% of lines.
- A person reads every Y before send. Flagged lines get one rewrite pass, two at most, then
  are hand-fixed or skipped.
- Always spot-check against real domain facts, not only structure. Batches of 10 or more
  show repetition problems that 4-5 lead tests miss.

Known failure seen at volume: the filler model copied examples across leads ("Treasure
Coast" on a California cleaner, one X reused across four firms).

## Med-spa angle library (July 2026, separate offer)

For med-spa leads, the output is `Hey {first_name}, {clause}`, the clause taken verbatim
from Lorenzo's reference templates, first matching angle wins, facts extracted from up to
three site pages. His rule: "i dont want your own invention use the templates". A claim may
only fire when it is checkable: the neurotoxin and laser review claims need a displayed
rating of 4.5+, the filler angle needs a before/after gallery, review count needs 150+,
"around since" needs 8+ years. Commodity brands never count as distinctive (HydraFacial,
Botox, Dysport, Xeomin, Jeuveau, Juvederm, Restylane, Belotero, Latisse, DiamondGlow,
SkinPen, microneedling, chemical peel, dermaplaning). Two leads hitting the same angle get
identical text; that is accepted. Three of his templates, verbatim:
- "noticed you guys run {specific_tech_brand} — not every spa around here has that."
- "saw you guys are right in {neighborhood} — good spot."
- "been checking out a few med spas in the area and {spa_name} kept coming up — good
  reviews, clean site, the whole thing." (fallback)

His originals carry em dashes, which the September 2026 rules ban. Ask Lorenzo for the
wording before reusing them; do not swap the punctuation yourself.
The med-spa offer is patient reactivation from the spa's own dormant list, not ads.

## Legacy (do not use for new work)

The 2025 contractor icebreaker rules ("25 years building a trusted HVAC brand... speaks to
serious pride in the craft, figured I'd reach out", start with action verbs, "says a lot
about", "stood out to me") and the Haiku/GPT-4o "operational fact pain" batch generator
predate every rule above and fail the bar test.

## Gaps

- Which model fills X and Y at volume under the Opus 5.5 decision is not settled; the daily
  run was built on Haiku fill plus a Sonnet rewrite.
- The list factory's personalization stage writes a freeform line (opens "Hey <first
  name>,", 30-240 characters) that Lorenzo has not reviewed; template mode is the only form
  he approved.

## Sources (for maintainers)

- memory `personalization-philosophy-2026.md` (2026-09-02 to 09-07): philosophy, corrections, template mode
- `Coding/lead-scrape-2026/personalize/prompts.json` (2026-09-07 22:06): template, X/Y rules and examples; `DAILY_RUN.md` for the daily pipeline
- memory `cold-read-research-2026.md` (2026-09-02): safe traits, location mismatch
- memory `personalization-line-generator.md` (2026-06-29 to 07-06): guessability test, QA pass
- memory `deep-multiline-icebreaker-tool.md` (2026-07-25/26) and `Agentic Worklfows/execution/deep_multiline_icebreaker.py` `ANGLES`: med-spa library
- memory `medspa-offer.md` (2026-07-25)
- `Agentic Worklfows/runbooks/list_factory.md` (2026-09-22): copy rules on the line
- `Agentic Worklfows/directives/USER/generate_deep_multiline_icebreaker.md`, `enrich_and_personalize_leads.md`, `batch_personalize_leads.md`: legacy rules
- `Agentic Worklfows/config/offers.md` rule 8: no AI, no em dashes, no "!"
