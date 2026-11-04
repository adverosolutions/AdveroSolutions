---
name: cold-email-personalization
description: "The per-lead opener that fills {{personalization}} at the top of Lorenzo's cold emails. Covers his philosophy (one specific thing you saw, plain praise, no pitch, the bar test), the locked template mode for recruiting, cleaning and bookkeeping (\"Hey {first_name}, I know that you do {x}. Congrats on {specific}. Was wondering if I can run something by you.\"), X and congrats-on-a-specific rules with real examples, what is safe to assert blind per niche, the guessability test, the batch review rules (banned vague verbs, X/Y fixes, skip/restore, 2-per-company cap), the step-by-step batch pipeline (pick, extract, fill, review, push to Instantly), the med-spa angle library, and the QA gate. Use for \"personalize leads\", \"write the icebreaker\", \"personalization line\", \"opener\", \"cold read\", \"enrich and personalize the leads\", \"run a batch\", or checking a batch of lines."
---

# Cold email personalization

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- The November 1 Codex implementation and its DAILY_RUN.md remain the local execution reference. Keep fact extraction and copy review in the current Codex session; do not restore older Anthropic or Claude CLI calls for this pipeline.
- The latest Grok rulebook records approved niche fallbacks for future loads: pest and cleaning text on November 1, PPC text on November 2 at 10:36 CT. Copy those exact strings and their needs_review status from the rulebook; do not edit loaded leads or campaign templates while updating local records.
- The October 10 I know / Congrats template is retained. The old blanket claim below that only marketing-agency fallbacks are approved is superseded by those later dated niche approvals; deterministic pipeline gates still apply until their configuration is explicitly updated.
- All campaigns remain paused pending Lorenzo’s new copy and resume. A personalized row, a passed QA gate or an archived approval is not a new instruction to upload or send.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)
- [feedback-opener-certain-language.md](../../memory/feedback-opener-certain-language.md)
- [feedback-cold-read-not-skip.md](../../memory/feedback-cold-read-not-skip.md)


The line proves someone looked at the business for 30 seconds. It is not insight, not a
pitch, not a problem statement. The email body carries the offer.

Lorenzo's wider voice rules are in `lorenzo-voice`; the kicker-line ban is in `claudeisms`.
The campaigns the line goes into are in `cold-campaigns`.

## Implementation status (updated 2026-11-01)

The current batch implementation now supports the approved achievement template and
cold-read alternative. `personalize/prompts.json` and `daily_fill.py` carry `specific`,
mode and evidence; `research.py` retains the homepage and up to four same-site proof
pages, with fetch diagnostics. The old Y renderer and auto-approval loop are retired.

Writing, fact selection and copy review use **OpenAI/Codex** in the current session,
per Lorenzo on 2026-11-01. Do not call Anthropic, Claude or Opus for this pipeline,
including through the CLI. This overrides older model assignments here and in
`lorenzo-voice` for personalization. Scripts fetch, stage, render and verify data;
they make no model API calls or require a separate model API subscription.

Local verification: 112 tests pass across personalization, upload and slots. A 12-lead
real-site validation produced six researched candidates, three approved cold reads,
two holds and one foreign-company skip. The historical-company cap prevented repeat
uploads of existing firms. No lines were human-approved or sent. See
`Coding/lead-scrape-2026/personalize/VALIDATION.md` for evidence and examples.
This was a Codex self-review, not an independent review.

Read `personalize/DAILY_RUN.md` before running a batch. Review now runs locally by
default; `daily_apply.py --write-sheet` is the explicit live apply option and refuses
unresolved QA or missing human review. Matching quotes and numbers do not prove a
claim's meaning: check attribution, identity, priority and voice by reading the source.
Only the existing marketing-agency fallback variants are approved; other niches with
no usable achievement are held for wording review rather than assigned invented copy.
Changing a reviewed record invalidates its review digest. Old `approved.json` files
cannot waive template or factual failures.

## Who does what (updated 2026-11-01)

- **OpenAI/Codex** selects the facts, writes each line and performs copy QA in the current
  session. Scripts fetch pages and perform deterministic validation. No Claude/Opus calls.
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

## Current form (Lorenzo, 2026-10-10)

```
Hey {first_name}, I know that you do {x}. Congrats on {specific}. Was wondering if I can run something by you.
```

No first name: `Hey, I know that you do {x}. Congrats on {specific}. Was wondering if I can run something by you.`

How he got here, all on 2026-10-10 reading PPC-agency samples:
- "I know that you do", never "saw that you do": "that's just really weak... we just want to say we know."
- "That's exciting" is gone: "just sounds really AI... I wouldn't say that's exciting."
- No filler reaction between sentences ("Very cool", "Love that"): the sentence stands on its own.
- The "you must..." exaggeration (Y) is retired: four fixed shapes repeated across thousands of emails, cheesy to an owner ("rank a website in your sleep"), and a guess right after a confident "I know".
- "Congrats on {specific}" replaced it. A real result from their own site "really crushes"; a cold read is the fallback, and he wants specifics on nearly every lead ("this should be a non-issue").

Approved example shapes:
- "Hey Caden, I know that you do Google Ads and Meta ads management. Congrats on managing over $6 million a month in ad spend. Was wondering if I can run something by you."
- "Hey James, I know that you do paid ads and SEO for restoration companies. Congrats on generating over $30 million for your clients in 2024. Was wondering if I can run something by you."
- "Hey Brian, I know that you do SEO and PPC. Congrats on 25 years in business. Was wondering if I can run something by you."

### X: what this company specifically does

- 3-10 word noun phrase that reads naturally after "I know that you do", read off their own site.
- Order of preference: (1) their service plus a client type the site names; (2) their specific
  mix of services; (3) a plain service line. Starts with the service, never a client type.
- Must contain the niche word: recruiting/search/staffing/placements/hiring;
  cleaning/janitorial; tax/accounting/bookkeeping/CPA/payroll; pest/termite/wildlife/mosquito/
  rodent/extermination; PPC/paid search/Google Ads/ads/advertising/SEO/marketing.
- Lowercase except proper nouns, brands and acronyms. No period, dashes, "&", numbers, "you",
  "your", "we", "our", company name, or city/state/region names. No "AI" or "automation".
- Never invent a client type, place or service that is not on the lead's own site.
- No marketing words: solutions, premier, state of the art, unparalleled, full service,
  tailored, comprehensive, innovative, leading, best, strategic, growth, trusted, quality.

Examples: "SEO and PPC for law firms", "Amazon advertising for consumer brands", "recruiting for
commercial HVAC and electrical companies", "taxes for real estate investors and flippers",
"commercial cleaning for medical facilities and retail spaces".

### {specific}: one achievement from their own site

Take the first rung that exists, completing "Congrats on <phrase>." (3-14 plain spoken words):
1. A client result with a number: "helping a client grow Amazon sales 1,902% year over year".
2. A total with a number: ad spend managed, revenue or leads generated, clients served, square
   feet cleaned, homes treated.
3. A named award or ranking: Inc. 5000, Clutch, Best of <city>, Angi Super Service Award.
4. Named press, a book, a podcast or a talk: "being featured in Associated Press and Business Insider".
5. A review rating with 25 or more reviews: "the 4.9 rating across 120 Google reviews".
6. A partner badge or non-default credential, named exactly: Google Premier Partner, QualityPro,
   CIMS, GBAC STAR, Enrolled Agent.
7. Years in business from a stated founding year: "22 years in business".
8. Another concrete company milestone with a number or name: team size, a new office.
Fallback when the site is dead or shows nothing true: a cold read, never a generic congrats and
never a skip (Lorenzo, 2026-10-10). A cold read is a compliment true of nearly everyone in the niche
that still reads as aimed at them. His content-creator example: "Fantastic work on the content. I can
tell that you really lean into being real and original." The line becomes "Hey {first_name}, I know
that you do {x}. {cold read} Was wondering if I can run something by you." Rotate a few variants
and never give two people at the same company the same one. PPC agency set used 2026-10-10:
- "Fantastic work on the campaigns. I can tell you really care about the leads and not just the clicks."
- "Great work on the campaigns. I can tell you're big on tracking what actually turns into revenue."
- "Fantastic work on the accounts. I can tell you stay on top of them instead of setting and forgetting."
- "Great work with your clients. I can tell you're upfront with them about the numbers."
- Amazon agencies (x names Amazon): "Fantastic work on the Amazon accounts. I can tell you care about
  profit and not just sales." / "Great work with your brands on Amazon. I can tell you really dig into
  the numbers."
Match the cold read to x: a shop that runs no ads or marketing (web design, hosting, branding) only
gets the "accounts" or "clients" lines; ecommerce agencies never get the "leads" line.
Also use a cold read instead of a specific that can't be stated truly (a pooled stat, a client's own
number); don't drop the lead.

Guardrails: exact numbers and names from the text, said the way people say them ("$6 million",
"over 500 clients", never "$6M" or "500+"); keep a stated year as stated ("in 2024", never
"last year"); never name a client company; never a result about an ethnic, religious or
demographic group; skip vague claims ("award-winning" with no award named); every phrase keeps
a verbatim evidence quote and source URL, and the quote must be on the page.

How to find specifics at volume: the home page top and an about page are not enough (a third
of sites). Fetch the full home page plus up to four proof pages (case studies, results,
portfolio, testimonials, reviews, awards, press, about), then extract with the ladder above.
On a 60-site PPC test that took specifics from 37% to 88%.

### Retired: Y, the "you must" exaggeration (2026-09-07 to 2026-10-10)

Do not use for new lines. It read "That's exciting, you must have half of Long Island on speed
dial" in four shapes (speed dial, by name, in your sleep, desk at half your clients' offices).
The Y rules below under batch review are kept only for reading old batches.

### Batch review rules (learned at volume, 2026-09-28 to 09-30)

Fill models break the same ways every batch. A person reads every line and hand-fixes these:

**X fixes**
- City or state inside X gets replaced: "tax prep for Chattanooga businesses" becomes "tax
  prep for local businesses". Do not move the place into the current achievement sentence.
- "small business" (singular) becomes "small businesses". Brand names keep their caps
  (QuickBooks, Xero, Gusto).
- X starts with the service, never a bare list of client types.

**Y fixes (retired template only)**
- Every sleep line reads "you must be able to <task> in your sleep". "You must file returns
  in your sleep" (missing "be able to") gets fixed.
- The sleep task is one concrete, singular job. Banned vague verbs: file taxes, prepare
  taxes, manage, organize books, balance books, reconcile accounts, process payroll, plan
  taxes, minimize taxes, handle anything. Plural nouns read wrong ("reconcile accounts");
  use the singular ("reconcile a bank account").
- Good bookkeeping/tax tasks: reconcile a bank account, file a business return, file a tax
  return, prep a tax return, run payroll, do a bookkeeping catch-up, build a tax plan, set up
  a chart of accounts, settle an IRS notice, set up QuickBooks, set up an LLC, run an audit,
  build a cash flow forecast, file an S-corp return.
- Good recruiting tasks: "place a <specific role from X>" (place a CFO, place a travel
  nurse). Broken nouns ("place a sourcing") get fixed.
- "by now" only on the desk line; "by name" lines end "by name" and use a noun that is in X.
- Speed dial and by-name lines use the company city (state only when the city is blank).
  No regions, counties or nicknames that are not in the data (Long Island, Treasure Coast).
- No competitor nouns as the client type (PR firms, recruiters).
- Shapes stay at or under about a third of the batch each. The fill model leans on speed
  dial, so swap the extras to sleep or desk.

**Skip or restore**
- Skip foreign firms the state filter missed: Canada, UK, Australia, New Zealand, India,
  Korea, Ukraine, Poland, Netherlands, Dubai, Honduras and similar.
- Skip off-niche rows: general business consulting, wealth management, software, job boards,
  nanny agencies, business brokers, telecom filings, medical billing, audit training.
- Restore rows the extract wrongly marked off-niche when they are the niche: staffing
  agencies (recruiting), payroll services, forensic or trust accounting, fractional CFO firms
  (bookkeeping).
- No more than 2 contacts per company (same company name and city) across everything already
  pushed. Later batches repeat firms 3-4 times; check a kept row's achievement or cold read against the line its
  colleague already got so two people at one firm do not get the same line.

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

- Template intact. For researched lines, X and the specific are grounded in the lead's own site,
  and the specific's quote is on its source page. For cold reads, follow the fallback rules
  and label them as fallback internally; never attach fabricated evidence.
- No em dashes, no "!", no AI, automation or tool words, no price, no pitch, no additional call to
  action beyond the template's fixed ask, no "+" shorthand on numbers ("20+ years"), no fabricated percentages.
- Banned words match on word boundaries ("air ducts" and "Bottom Line Bookkeeping" are fine).
- No guessing words (must, must be, bet, probably, gotta be, no wonder).
- No niche clash, no foreign company (skip Seoul, Lagos, Ontario and similar when state is blank).
- Two people at one company never get the identical line: the second contact gets the next rung's fact when one exists.
- A person reads every line before send. Flagged lines get one rewrite pass, two at most, then
  are hand-fixed or skipped.
- Always spot-check against real domain facts, not only structure. Batches of 10 or more
  show repetition problems that 4-5 lead tests miss.

Known failure seen at volume: the filler model copied examples across leads ("Treasure
Coast" on a California cleaner, one X reused across four firms).

## Running a batch

Code lives in `Coding/lead-scrape-2026/`. Follow `personalize/DAILY_RUN.md` for local
research, Codex extraction/fill, evidence-aware review, manual corrections and exports.
The exact record schemas are in `personalize/tools/prompts/extract_mixed.txt` and
`fill_mixed.txt`. New writer records use `mode`, `x`, `specific`, `achievement_kind`,
`x_evidence`, `specific_evidence`, `cold_read` and `specialty`; never Y.

`tools/review.py`, `final_view.py`, `autofix.py` and `applyfix.py` are local-only.
`approve_rest.py` is now a compatibility alias for local review, never automatic approval.
Every factual or template failure must be corrected or held. Human review of the full
line and evidence is recorded in `human_review.json` using the current record digest;
never grant yourself this human review. Only reviewed rows reach `reviewed.csv`.

`daily_pick.py` marks the live Sheet; `daily_apply.py --write-sheet` writes the live Sheet
and exports the day CSV; Instantly upload is separate. Follow repository live-write
authorization rules. A code/skill edit does not approve an upload. Never activate or pause
a campaign or touch a live campaign's `email_list`.

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

- Cleaning, bookkeeping and recruiting do not yet have approved cold-read wording in the
  current config. Research an achievement first; hold unresolved fallback wording for Lorenzo.
- The list factory's separate freeform stage is not the approved template pipeline. Do not
  infer that updating this pipeline changes unrelated generators or runtime services.
- Scheduling and unattended model generation are outside this batch implementation. Codex
  supplies the model work in-session; live operations still require their normal authorization.

## Sources (for maintainers)

- memory `lead-scrape-2026-niches.md` (2026-09-28 to 09-30): batch review rules, tools, cap
- memory `personalization-philosophy-2026.md` (2026-09-02 to 09-07): philosophy, corrections, template mode
- `Coding/lead-scrape-2026/personalize/prompts.json`, `daily_fill.py`, `daily_pick.py`,
  `tools/prompts/fill_*.txt`, and saved September CSVs: implementation status inspected
  2026-11-01, then migrated to the current template. `DAILY_RUN.md` and `VALIDATION.md`
  document the current procedure and verification.
- memory `cold-read-research-2026.md` (2026-09-02): safe traits, location mismatch
- memory `personalization-line-generator.md` (2026-06-29 to 07-06): guessability test, QA pass
- memory `deep-multiline-icebreaker-tool.md` (2026-07-25/26) and `Agentic Worklfows/execution/deep_multiline_icebreaker.py` `ANGLES`: med-spa library
- memory `medspa-offer.md` (2026-07-25)
- `Agentic Worklfows/runbooks/list_factory.md` (2026-09-22): copy rules on the line
- `Agentic Worklfows/directives/USER/generate_deep_multiline_icebreaker.md`, `enrich_and_personalize_leads.md`, `batch_personalize_leads.md`: legacy rules
- `Agentic Worklfows/config/offers.md` rule 8: no AI, no em dashes, no "!"
