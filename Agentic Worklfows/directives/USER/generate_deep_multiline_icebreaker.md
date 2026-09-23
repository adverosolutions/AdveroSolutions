# Generate Deep Multiline Icebreaker

**Purpose:** Generate a short, human "Hey {name}, ..." opener from a lead's website, picked from a fixed angle library based on which real signal was found. PERSONALIZATION ONLY, no offer/pitch
**When to use:** For leads that already have a website_url and email, when you want a research-backed personalization that still reads like a real person wrote it
**Frequency:** As needed, batch by CSV

---

## Architecture (as of 2026-07-25, current)

This is a **template/angle-library system**, not freeform LLM generation —
matching the proven pattern already used in the med-spa `relevance_line` tool
(see [[personalization-line-generator]] in memory): pick the highest-priority
angle whose required signal(s) are present, fill it in deterministically. No
LLM call ever writes the actual output sentence anymore; Claude Haiku is only
used for (a) summarizing scraped pages and (b) structured signal extraction
("is X clearly stated, yes/no/value" — never creative writing).

**Output shape:** `"Hey {first_name}, {clause}"` — greeting always
deterministic (built from the CSV's `first_name` column, never model-written).

### Angle library (`ANGLES` in `deep_multiline_icebreaker.py`)

Adapted from 15 reference templates Lorenzo supplied (2026-07-25), tried in
priority order, first match wins:

| # | Angle | Fires on | Notes |
|---|-------|----------|-------|
| 1-3 | `primary_treatment_neurotoxin/filler/laser` | site clearly leans into one treatment type | |
| 4 | `specific_tech_brand` | a named device (CoolSculpting, Emsculpt, Morpheus8, HydraFacial, Tixel, etc.) | |
| 5 | `weight_loss_program` | semaglutide/weight-loss program present | |
| 6 | `google_review_count` | a specific review count is known | **not reliably scrapeable** — see limitations |
| 7 | `year_founded` | founding year stated | |
| 8 | `ownership_type` | RN-owned/NP-owned/physician-led stated | |
| 9 | `location_count` | 2+ locations explicitly stated | |
| 10 | `neighborhood` | a specific named area (not just city) | |
| 11 | `membership_program` | membership program mentioned | pitch clause ("which is basically what I do") dropped — out of scope |
| — | ~~SocialPlatform/ContentType~~ | **not implemented** | this tool never visits social platforms; needs a real scraper, not built |
| 12 | `active_promo` | a current promo/special found | |
| 13 | `founder_named` | owner named specifically on the site | |
| 14 | `fallback` | always available (needs only a company name) | Lorenzo's own framing: "works generically for ~80% of prospects" |

**Each angle uses Lorenzo's EXACT wording, verbatim — one template per
angle, no invented variants.** ("i dont want your own invention use the
templates", 2026-07-25.) An earlier version of this tool added 2-3 rotated
wording variants per angle to avoid duplicate text within a batch; Lorenzo
explicitly rejected that and asked for his literal templates only.

**Known, accepted tradeoff:** if multiple leads in one batch match the same
angle (e.g. several neurotoxin-heavy spas, which is common), they get
**byte-identical output text**. This was demonstrated live and confirmed
acceptable — 3 of 7 leads in a test batch got the exact same neurotoxin-angle
sentence. If this becomes a real problem at volume, the fix is re-adding
variants, but only if/when Lorenzo asks for it again.

### Signal extraction (`extract_signals()`)

One Haiku call per lead over the aggregated page abstracts, filling a strict
JSON schema (`SIGNAL_SCHEMA`). Every field defaults to null/false unless
**clearly and explicitly stated** in the research — never inferred or
guessed, same anti-fabrication discipline as everywhere else in this tool.
`google_review_count`, `year_founded`, and `location_count` can also be
passed through directly from optional CSV columns of the same name (e.g. if
sourcing leads from a CRM export that already researched them — your
`Med Spa Research Doc` sheet's `reviewCount`/`founding_year` columns are
exactly this kind of pre-verified source) and are trusted as-is when present,
without needing scrape confirmation.

### Review-claim verification (`reviews_confirmed_good`)

Templates 1 and 3 assert "solid reviews on the Botox side specifically" /
"reviews are pretty stacked". Rather than drop that clause or fire it
unconditionally, both angles now ALSO require `reviews_confirmed_good` — an
explicit displayed star rating of `REVIEWS_CONFIRMED_MIN_RATING` (4.5) or
higher, extracted via `review_rating` in `SIGNAL_SCHEMA`. A raw review COUNT
is deliberately NOT sufficient on its own (500 reviews could be 2-star) —
only an actual rating counts as confirming sentiment. If no rating is
confirmed, these two angles simply don't fire and selection falls through to
the next matching angle — the template wording itself is never altered.

Like `google_review_count`, star-rating widgets are usually JS-rendered and
rarely present in raw scraped HTML, so `review_rating` also has an optional
CSV passthrough column (same mechanism) for CRM-sourced leads that already
have a confirmed rating.

### Distinctiveness / "does this actually apply" checks (2026-07-26)

Lorenzo asked directly: "do these actually make sense and apply to the
particular company... do all of them pass a logical analysis?" A real audit
of a live batch found three angles that could fire while making a claim that
isn't actually true for that company (this is the SAME underlying discipline
as the "guessability test" in [[personalization-line-generator]] — flagged as
an open question earlier in this build and now effectively answered: yes,
apply it here too):

- **`specific_tech_brand` (template 4)**: "not every spa around here has
  that" was firing on HydraFacial and Juvederm — two of the most common
  products in the entire med-spa industry, where that claim is very likely
  FALSE. Fixed with `COMMODITY_TECH_BRANDS`, a blocklist (HydraFacial, Botox,
  Dysport, Xeomin, Juvederm, Restylane, Belotero, microneedling, chemical
  peels, etc.) applied both in the extraction prompt instruction AND as a
  mechanical post-extraction filter (defense in depth, same pattern as
  everywhere else in this tool) — genuinely distinctive capital equipment
  (Emsculpt, Morpheus8, Tixel, CoolSculpting) still fires normally.
- **`google_review_count` (template 6)**: "is no joke" was allowed to fire on
  any count ≥ 1 — a spa with 3 reviews would trigger that claim, which is
  absurd. Raised the schema minimum to 150 (matches the threshold already
  validated in [[personalization-line-generator]]).
- **`year_founded` (template 7)**: "good run in this space" had no minimum
  age — could fire on a business founded 8 months ago. Added a derived
  `long_established` signal (founded `LONG_ESTABLISHED_MIN_YEARS` = 8+ years
  ago) that the angle now also requires.
- **`primary_treatment_filler` (template 2)**: "noticed a few of the
  before/afters" was never actually checking that a before/after gallery
  exists. Added `has_before_after_gallery` as a required signal.

Live-verified: re-running the same 10-lead batch after these fixes changed
CRAVE's fired angle from HydraFacial (now correctly filtered) to a genuinely
distinctive device found on their site ("Medisurface RF"), and changed Miss
Botox Fort Worth from JUVÉDERM (filtered) to falling through to
`ownership_type` instead.

### Content still carried over verbatim despite flagged concerns

Per "use the templates" (literal), these ship exactly as Lorenzo wrote them:
- **Template 6** uses `{ReviewCount}+` — the literal "+" shorthand Lorenzo
  himself flagged as unnatural earlier in the same session ("no human would
  say 20+ years ever in conversation"). Also not reliably scrapeable — see
  limitations.
- **Template 11** ends "...which is basically what I do" — pitch language,
  in tension with the earlier "personalization only, no pitch" scope
  decision from correction #1.
- **Template 12** (SocialPlatform/ContentType) is the one exception NOT
  restored — this isn't a wording choice, the tool has no social-media
  scraper at all and can't fire this angle regardless of template wording.

---

## What This Does

1. Scrapes the lead's homepage, extracts internal links
2. Picks up to 3 internal sub-pages (About/Services-style pages prioritized)
3. Scrapes each sub-page, summarizes it with Claude Haiku (cheap)
4. Extracts structured signals from the aggregated research via Haiku
   (`extract_signals()`)
5. Selects the highest-priority matching angle and fills it in deterministically
   (`select_and_fill_angle()`) — rotating wording variants to avoid duplicate
   text within a batch
6. Prepends `"Hey {first_name}, "` and writes results to CSV (and optionally
   a Google Sheet)

Because the always-available `fallback` angle requires nothing but a company
name, **this pipeline now succeeds for essentially every lead with any
scrapeable content** — a meaningful reliability improvement over the earlier
freeform-generation version, which could fail validation and skip a lead
even when research succeeded.

This is distinct from `icebreaker_generator.py` (single-line Haiku opener for
contractor outreach, which uses admiring language like "shows serious grit"
by design) and the med-spa `relevance_line` tool in
[[personalization-line-generator]] (which this tool's angle-library
architecture is directly modeled on).

---

## Required Tools

- `execution/deep_multiline_icebreaker.py` — main script (no new dependencies or API keys needed; reuses `ANTHROPIC_API_KEY`)

---

## Input Format

CSV with columns: `first_name, last_name, email, website_url, company_name, location`

Optional passthrough columns (used directly when present, skipping extraction
for that field): `google_review_count`, `year_founded`, `location_count`.

```
python3 execution/deep_multiline_icebreaker.py --input leads.csv --output results.csv
```

### Test Mode
```
python3 execution/deep_multiline_icebreaker.py --input leads.csv --limit 5
```

### Flags
- `--pages N` — max internal sub-pages researched per lead (default 3)
- `--sleep N` — seconds between leads (default 1.5)
- `--limit N` — only process first N leads (test mode)
- `--sheet-id ID` — also append results to a Google Sheet (optional; falls back to `ICEBREAKER_SHEET_ID` env var if set)
- `--sheet-tab NAME` — worksheet tab to append to (default `Deep Icebreakers`; created automatically if missing)
- `--credentials PATH` — service account JSON path (optional; falls back to `GOOGLE_CREDENTIALS_JSON` env var, then `credentials.json` in the project root)

CSV output is always written, even when `--sheet-id` is set — the sheet
append is additive, not a replacement, so a sheet-write failure never loses
results. If the target tab is empty, a header row is added automatically;
otherwise rows are appended below existing content.

---

## Output

CSV with: `first_name, last_name, email, website_url, company_name, location, pages_researched, angle, personalization`

The `angle` column records which template fired (e.g. `specific_tech_brand`,
`year_founded`, `fallback`) — useful for spot-checking angle distribution
across a batch and for A/B analysis later, same convention as
`personalization_type` in [[personalization-line-generator]].

A lead is skipped only if: no `website_url`, homepage fails to scrape, or no
sub-page yields summarizable content. Generation itself essentially never
fails now (the `fallback` angle always matches), so `skipped_generation_failed`
in the run summary should stay near zero — if it isn't, something's wrong.

The `personalization` column is meant to be prepended to whatever offer/pitch
copy the actual outreach uses — see [[medspa-offer]] in memory for the current
confirmed offer content, kept separately since it isn't this tool's job.

---

## Costs

- Haiku summarization: ~3 calls/lead (1 per researched page)
- Haiku signal extraction: 1 call/lead
- No Sonnet 5 calls anymore (removed with the freeform-generation architecture)
- Rough order of magnitude: a fraction of a cent per lead, all-in

---

## Known Limitations / Not Built

- **No lead-sourcing step.** The original n8n template also scraped Apollo
  via an Apify actor to find leads. That was intentionally NOT ported —
  this script only researches+writes icebreakers for leads you already have
  (with `website_url` populated). If you want automated lead sourcing added
  later, that needs your own Apify token and Apollo search-URL list.
- **The Apify API key embedded in the original course JSON file was live,
  not a placeholder** — do not reuse it; it should be treated as a leaked/
  compromised credential from the course author.
- Single-page sites with no internal links fall back to summarizing the
  homepage itself (not in the original workflow, added for robustness).
- **`google_review_count` is not reliably obtainable from scraping.** This
  tool only reads the spa's own website, which rarely displays an exact
  Google review count. That angle mostly relies on the optional CSV
  passthrough column from a CRM export that already has it.
- **SocialPlatform/ContentType angle not implemented at all** — would need a
  real Instagram/TikTok scraper, out of scope for this tool.

---

## Learnings & Updates

*This section updated as system learns from errors*

- **2026-07-25: rebuilt from freeform LLM generation to a template/angle
  library.** The tool went through 7 rounds of prompt-tuning iteration on a
  freeform-generation approach (too long → too analytical/praise-heavy → too
  neutral → forced "love that" repetition → "20+" number-shorthand issue)
  before Lorenzo supplied 15 concrete reference templates and the whole
  approach was replaced with deterministic angle selection. If tuning this
  tool again, prefer adjusting/adding angle templates over reintroducing
  freeform LLM sentence-writing — the template approach is cheaper, more
  reliable (near-100% success via the fallback angle), and immune to the
  repetition/over-editorializing failure modes that took many rounds to fix
  in the freeform version.
- **2026-07-25, same day: first pass at the rebuild added 2-3 wording
  variants per angle (my own addition, not requested) to solve duplicate
  text within a batch. Lorenzo rejected this outright** ("i dont want your
  own invention use the templates") **and reverted to his exact 15 templates,
  one wording each, accepting duplicate text as the tradeoff.** Lesson: when
  a user hands over concrete finished copy (not a rough direction), treat it
  as final content to reproduce exactly, not a style reference to riff on —
  even when riffing solves a real problem (duplicate text) that the literal
  version reintroduces. If a real problem resurfaces from using literal
  templates, raise it explicitly and let Lorenzo choose the fix rather than
  silently improvising a solution again.
- **2026-07-26: added real review-rating verification instead of asserting
  or dropping the unverifiable review clause in templates 1/3.** Lorenzo's
  rule: "as long as the actual sentence is factual to the company then its
  fine if it doesnt apply its bad" — i.e. a template must never fire when
  its claim can't actually be confirmed true for that lead. Given the choice
  between dropping the clause, asserting it anyway, or building real
  verification, he chose real verification. Net effect: this is a genuinely
  different kind of correction than the others in this file — not a wording
  or tone preference, but a hard requirement that a fired sentence be
  checkably true, enforced by making the SIGNAL more precise (a real
  displayed rating) rather than by rewriting the copy.
