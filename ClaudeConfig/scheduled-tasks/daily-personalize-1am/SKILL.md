---
name: daily-personalize-1am
description: Personalize the next 360 clean leads for the recruiting / cleaning / bookkeeping campaigns, QA them, write to the Google Sheet, and push to Instantly.
---

You are running Lorenzo Villarreal's daily cold-email personalization batch. Work from `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026` and follow `personalize/DAILY_RUN.md` exactly. Use in-session subagents (on-plan), Haiku for extraction and fill, Sonnet for rewrites. Do not use any paid API keys for model calls.

Sequence:
1. `python3 personalize/daily_pick.py --n 360 --only-clean` then `python3 personalize/refetch_thin.py <batch_dir>`. If fewer than 360 clean rows remain, drop `--only-clean` and say so in the report.
2. Extraction: Haiku agents, ~25 leads each, EXTRACTION PROMPT from DAILY_RUN.md, merge to extract.json. Review every `is_in_niche: false`; dead or unreadable pages become null, not false.
3. `python3 personalize/daily_select.py <batch_dir>`
4. `python3 personalize/daily_fill.py <batch_dir>` then Haiku agents (50 leads each) with the FILL PROMPT (template mode: x, y, specialty per `personalize/prompts.json`), then `daily_fill.py <batch_dir> --merge`.
5. `python3 personalize/daily_apply.py <batch_dir>`. While anything is flagged: `daily_rewrite.py <batch_dir>` -> one Sonnet agent per ~50 with the REWRITE PROMPT -> `daily_fill.py --merge` -> apply again. Two loops max.
6. Read EVERY Y yourself. Hand-fix anything flat, vague, ungrammatical, off-niche, or that names a place or client type not in the lead's data, in `x_rewrite_9.json`; put gate false-positives in `approved.json`; mark non-US companies `skipped: foreign company`. Re-merge and re-apply until `flagged=0`.
7. Push to Instantly: `python3 instantly_push.py --push output/daily/day_<id>.csv`. If the key is invalid, stop and say so.
8. Report: done / flagged / skipped counts by campaign, the day file path, subagent token totals, and anything you had to hand-fix. Never send email yourself; Instantly sends.

Bar for the lines: the fixed template is "Hey {first_name}, saw that you do {x}. That's exciting, {y}, wondering if I can run something by you." X is a true 3-10 word noun phrase from the lead's own data. Y starts with "you must", is a playful exaggeration built on one detail from X or the lead's city, never a problem or advice, never copied from an example onto a lead it doesn't fit. Reference Y: "you must have half of Long Island on speed dial".