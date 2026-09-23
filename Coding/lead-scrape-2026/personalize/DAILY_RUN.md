# Daily personalization run (4 a.m.)

Personalizes the next ~300 leads in send order for the three campaigns
(recruiting, bookkeeping, cleaning) and writes them live into the Google Sheet
`1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw`, tab `Leads`.
All model work runs as in-session subagents (on-plan). Code does everything else.
Working dir: `Coding/lead-scrape-2026`. Run from there.

## Sequence

1. **Pick + fetch** (code):
   `python3 personalize/daily_pick.py --n 300 --only-clean`
   → prints a batch dir `personalize/batches/<id>/` with `leads.json` and one
   `<lead_id>.txt` per Tier-2 candidate (home + about page text, trimmed).
   Off-niche rows are marked `skipped` in the sheet; picked rows `queued`.
   (Drop `--only-clean` once clean rows are exhausted.)
   Then: `python3 personalize/refetch_thin.py <batch_dir>` to retry thin/JS-only
   pages and demote the unrecoverable ones to Tier 1.

2. **Extract** (Haiku subagents, ~25 leads each, run in parallel, background):
   For each chunk of ~25 Tier-2 candidates, spawn an Agent with model `haiku`
   and the EXTRACTION PROMPT below, pointing it at the batch dir and its list
   of lead_ids. Each agent writes `extract_<k>.json`. When all finish, merge:
   `python3 -c "import json,glob,sys;b=sys.argv[1];out=[];[out.extend(json.load(open(f))) for f in sorted(glob.glob(b+'/extract_*.json'))];json.dump(out,open(b+'/extract.json','w'),indent=1);print(len(out))" <batch_dir>`

3. **Select** (code): `python3 personalize/daily_select.py <batch_dir>`
   → `select.json` with tier 2 / 1 / skip and the anchor per lead.

4. **Fill X** (template mode; Haiku subagents, 50 leads each, parallel, background):
   `python3 personalize/daily_fill.py <batch_dir>` → `fill_chunk_<k>.json`.
   For each chunk spawn an Agent (model `haiku`) with the FILL PROMPT below. Each
   writes `x_<k>.json`. Then `python3 personalize/daily_fill.py <batch_dir> --merge`
   → `x.json` + `lines.json` (the fixed template from prompts.json with X filled).

5. **Apply** (code): `python3 personalize/daily_apply.py <batch_dir>`
   → QA gate (banned phrases, fact-labelling, stock reactions, grounding) plus a
   batch variety cap (no reaction marker on more than ~30% of lines). Sheet
   updated (done / flagged / skipped), send file `output/daily/day_<id>.csv`.

5b. **Rewrite loop** (code + one sonnet subagent), while anything is flagged:
   `python3 personalize/daily_rewrite.py <batch_dir>` → `rewrite_needed.json`
   (lead, facts, previous line, why it failed). Spawn ONE Agent (model `sonnet`)
   with the REWRITE PROMPT → `lines_rewrite_1.json`. Then
   `python3 personalize/daily_rewrite.py <batch_dir> --merge` and re-run step 5.
   Two loops max; hand-fix whatever is left.

6. **Review** (Fable): read EVERY Y (they are short; ~400 fit in two prints).
   Hand-fix anything off in `x_rewrite_9.json` (merged last). Lead_ids the gate
   flagged but that read fine go in `approved.json` (`{"lead_ids": [...]}`) so
   the gate stops holding them. Leads outside the US that the state check missed
   (blank state) → set `skipped: foreign company` by hand and drop from the day file. Then report:
   counts by tier, flagged reasons, subagent token totals from the task
   notifications, path of the day file.

7. **Push to Instantly** (code): `python3 instantly_push.py --push output/daily/day_<id>.csv`.
   Six campaigns (ids in `instantly_campaigns.json`): recruiting x3, bookkeeping x2,
   cleaning x1; a niche's leads split round-robin across its campaigns; company
   names cleaned at upload; `{{specialty}}` falls back to "your clients'".

## EXTRACTION PROMPT (model: haiku)

You are extracting facts for cold-email personalization. Work ONLY from the
text files given; do not browse or guess. For each lead_id in your list, read
`<batch_dir>/<lead_id>.txt` (it contains [HOME url] and maybe [ABOUT url]
sections). Return a JSON array to `<batch_dir>/extract_<k>.json`, one object per
lead_id, keys exactly:
{"lead_id":"", "is_in_niche": true|false|null, "what_it_is":"", "founded_year":null,
 "years_claim":"", "named_niche":"", "guarantee":"", "credential":"",
 "about_voice_quote":"", "service_traits":[], "source_url":"", "evidence_quote":""}
- is_in_niche: is this actually a <campaign> business (recruiting/staffing firm;
  commercial cleaning/janitorial; bookkeeping/tax/CPA)? false if clearly not.
- named_niche: a SPECIFIC specialization they state (industries, roles, client
  types). Never generic ("small business", "commercial").
- guarantee: exact wording of any guarantee. credential: NON-default ones only
  (CIMS, GBAC, Enrolled Agent, QuickBooks ProAdvisor, NAPS...). Plain "CPA" or
  "licensed and insured" is NOT distinctive: leave blank.
- about_voice_quote: a short verbatim phrase (4-14 words) that shows a
  distinctive personality or origin story, if one exists. Else blank.
- founded_year: only if stated. years_claim: e.g. "over 20 years" if stated.
- source_url: the [HOME]/[ABOUT] url the facts came from. evidence_quote: <=15
  words verbatim supporting the best fact. Blank/null whenever unconfirmed.
Fabrication is the one unforgivable error.

## FILL PROMPT (model: haiku)

Read `personalize/prompts.json` (`template`, `x_rules`, `x_examples`) and
`<batch_dir>/fill_chunk_<k>.json`. For each lead write X and Y. X: a 3 to 10 word noun
phrase for what that company specifically does, so that "saw that you do <X>" reads
naturally. Y: per `y_rules` and `y_examples`, a playful exaggeration starting with
"you must", built on one detail from X or the city/state, rotating shapes. Use ONLY the data in that lead's record (named_niche, what_it_is,
service_traits, headline, company_description, city, state), in the priority order
`x_rules` gives. Plain spoken words, no marketing copy, no pronouns, no company name,
no trailing period, and X must name the niche (recruiting / cleaning / tax or
bookkeeping). Return `<batch_dir>/x_<k>.json`: [{"lead_id":"", "x":"", "y":""}]. No commentary.

## REWRITE PROMPT (model: sonnet)

Read `personalize/prompts.json` and `<batch_dir>/rewrite_needed.json`. Each entry
has the lead, its facts, `previous_x` and `rejected_because`. Write a NEW X for
each that fixes that reason and follows `x_rules`. Return
`<batch_dir>/x_rewrite_1.json`: [{"lead_id":"", "x":""}], then run
`daily_fill.py <batch_dir> --merge` and `daily_apply.py` again.
