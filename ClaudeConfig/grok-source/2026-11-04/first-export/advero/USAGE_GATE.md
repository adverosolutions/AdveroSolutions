Canonical copy: state/usage_gate.md

# Usage gate (effective 2026-09-26)
Updated: 2026-09-25 18:03 CT
Owner: Chief of Staff (usage moderator)
Full retro: ~/advero/state/reports/usage_retro_2026-09-25.md

Read this before any non-trivial Advero work. Files 00-07 still win on product rules.

## Goal
Spend Grok on gathering facts and carrying out actions. Spend Claude Opus (routed automatically through the harness; no script or Claude Code call) on judgement and public drafts. Do not burn Grok on long reasoning, duplicate pulls, or browser click-tax when an API exists.

## Rules
1. **Judgement and public drafts → Opus first.** Classify replies, choose templates, ambiguous ops, Nick-tone Maker School reshape, Upwork drafts for Lorenzo: package facts; the judgement routes to Opus automatically through the harness; no script or Claude Code call is needed. Do only what that judgement says; if it says hold, or confidence is under 0.8, send Lorenzo a hold card. Do not write long Grok essays and "fix" with Opus later.
2. **One owner per task.** CoS assigns. Do not start a second agent or executor on the same lead, metric, or GHL/Instantly move unless CoS says so.
3. **API before browser.** Prefer `~/advero/bin/instantly` and `~/advero/bin/ghl`. Browser/computerUse only when the API cannot do the step.
4. **Cheap read first.** Check `~/advero/state/` (cases, decisions, handled, sent_log, reports, accountability_sheet) and existing logs. If the answer is already there, stop.
5. **One desktop at a time.** Only one computerUse on the shared box. Stagger; do not parallel-click.
6. **Maker School / communities:** Maker School posts are drafted or reshaped only when Lorenzo asks. Community Manager's routines that Lorenzo approved are allowed: the engagement digest (Mon-Sat 8:30 AM and 3:30 PM CT) and the 6 PM CT post draft plus engagement plan. Everything else stays on request only: no other feed scrapes, and nothing gets posted without Lorenzo's yes.
7. **Ask-first still on** for customer-facing sends until Lorenzo changes that.
8. **Empty / nothing-new exits.** If a scan finds nothing due, report once briefly (or stay quiet on a routine that says so) and stop. No retry loops.

## CoS enforcement
- CoS is usage moderator across the shared box.
- Before kicking Inbox / Calls / Reports / Upwork / Maker School on overlapping work, CoS checks this gate.
- Metrics / accountability sheet writes: CoS owns the numbers. Others may gather only if CoS asks; they do not re-pull and rewrite the same row.
- Midday or end-of-day usage ping only if something is blocked or Lorenzo asked.

## Standing routines (2026-09-25 18:03 CT)
- **Upwork check (15m)** (`reply-check-hourly`): Mon–Sat every 15 min 6:12am–10:57pm CT (12,27,42,57). Upwork messages only. Quiet if nothing new. Draft for Lorenzo; never send Upwork.
- **Instantly reply webhook** (`instantly-reply-webhook`): wakes on Instantly `reply_received` once the Instantly webhook points at this routine URL with the Authorization bearer key. Ask-first holds to Lorenzo's phone.
- Instantly is NOT on the hourly cron.

## Claude CLI lock
Not needed. Judgement calls route to Opus automatically through the harness: no `ask_opus.py`, no lock, no `claude -p` call.

## Smoke check (Opus path)
Not needed. Opus routing is automatic through the harness.
