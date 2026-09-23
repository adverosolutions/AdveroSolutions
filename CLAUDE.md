# AdveroSolutions — Agent Instructions

> Canonical source: `Agentic Worklfows/Claude.md`. This root file ensures Claude Code auto-loads the instructions.

## 3-Layer Architecture

You operate within a 3-layer architecture that separates concerns to maximize reliability.

| Layer | Role | Location |
|-------|------|----------|
| **Directive** | What to do — SOPs in Markdown | `Agentic Worklfows/directives/` |
| **Orchestration** | Decision-making — that's you | — |
| **Execution** | Deterministic Python scripts | `Agentic Worklfows/execution/` |

**Why:** LLMs are probabilistic; business logic must be deterministic. Push complexity into scripts; you focus on routing and decisions.

## Operating Principles

1. **Check for tools first.** Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.
2. **Self-anneal when things break.** Read error → fix script → test → update directive with what you learned. If it uses paid tokens/credits, check with the user first.
3. **Update directives as you learn.** Directives are living documents. Don't create or overwrite directives without asking unless explicitly told to.

## Directory Structure

```
Agentic Worklfows/
├── directives/
│   ├── USER/          # User-triggered SOPs
│   └── AUTOMATED/     # Cloud/webhook-triggered SOPs
├── execution/         # Python scripts (deterministic tools)
├── Claude.md          # Full agent instructions
├── MASTER_SOP.md      # Business processes & email templates
├── INDEX.md           # System control center
└── QUICK_START.md     # Setup guide
```

- `.tmp/` — Intermediate files. Never commit. Always regenerable.
- `.env` — API keys and environment variables. **Never commit.**
- `credentials.json`, `token.json` — Google OAuth. **Never commit.**

## Key Directives (USER/)

| Directive | Purpose |
|-----------|---------|
| `add_leads.md` | Import new leads into CRM |
| `start_cold_campaign.md` | Launch 3-email outreach sequence |
| `discover_leads.md` | Find new HVAC/Roofing businesses and add them to the pipeline |
| `discover_and_enrich_leads.md` | Self-hosted owner identity + verified email pipeline (AnyMail Finder replacement) |
| `enrich_and_personalize_leads.md` | Enrich leads with research & personalization |
| `mass_scrape_leads.md` | Bulk scrape leads from Google Maps |
| `batch_personalize_leads.md` | Batch personalize CRM leads |
| `separate_contacted_leads.md` | Separate contacted leads for campaign management |
| `generate_deep_multiline_icebreaker.md` | Short "Hey {name}, ..." opener from site research; personalization only, no pitch |
| `generate_linkedin_content.md` | LinkedIn posts across 5 content pillars into the content calendar sheet |
| `prevent_anymail_data_corruption.md` | Guard against row misalignment when round-tripping CSVs through AnyMailFinder |

AUTOMATED/: `sync_instantly_leads.md` (daily Instantly → CRM status sync, the only live webhook), `generate_visual_breakdown.md`, `monitor_social_leads.md`.

## Cloud Webhooks (Modal)

Webhook slug → directive mapping lives in `execution/webhooks.json`. The live app is `execution/modal_lead_sync.py`; deploy with `python3 -m modal deploy execution/modal_lead_sync.py` (manual run: `python3 -m modal run execution/modal_lead_sync.py::run_sync_now`).

## Business Context

- **Company:** AdveroSolutions — AI-powered lead gen & automation for contractors (HVAC, Plumbing, Electrical, Roofing)
- **Founder:** Lorenzo Villarreal
- **CRM:** Google Sheets (`AdveroSolutions_CRM`)
- **Email platform:** Instantly (~2,000/day)
- **Verticals:** HVAC, Plumbing, Electrical use SOP-002; Roofing uses SOP-002R (different copy, 4 emails, prototype-first funnel)
- **Sales model:** One-call close. No proposals, no "let me follow up with pricing."

## Conventions

- Deliverables go to cloud services (Google Sheets, Slides, etc.), not local files.
- All intermediate/temp files go in `.tmp/`.
- When running execution scripts, use `python3` (macOS).
- The full Master SOP with all email templates, call scripts, and objection handling is in `Agentic Worklfows/MASTER_SOP.md`.

## Revenue Automation Build (started 2026-09-21)

**Instantly API contract:** `Agentic Worklfows/config/instantly_api_contract.md` holds the request schemas verified against developer.instantly.ai on 2026-09-21 (reply, interest status, blocklist, subsequence create and move, webhooks, account pause, campaign patch, rate limits). It is authoritative over any guess in code comments. Note in particular: recipient safety on the reply endpoint is enforced **twice**, because the published REST reference and the Instantly tool schema disagree about whether a `to` field exists. `shared/instantly.py` requires `to=<lead email>` (it raises without one) **and** `cadence.thread_recipient_ok` re-reads the email in live and refuses unless `from_address_email` is the lead. Do not remove either half; one live-send rehearsal settles which is load-bearing. Interest status takes `lead_email` + `interest_value` and answers 202; subsequence move takes one lead as `id` (no `ids` array).

Plan: `Agentic Worklfows/REVENUE_AUTOMATION_BLUEPRINT.md` (build IDs M#/S#/F#/O#, briefs A1–A12). Live ids: `Agentic Worklfows/config/ids.json`. Offer sheet: `Agentic Worklfows/config/offers.md`. Agents: `.claude/agents/{sales,marketing,fulfillment,ops}.md`.

**Controlled-environment rule (Lorenzo, 2026-09-21):** nothing touches live Instantly, GHL, Upwork, Gmail, Calendar or Modal until it is tested and Lorenzo approves the push.
- `MODE=shadow` (default) proposes, logs and notifies Lorenzo only. `MODE=live` plus `ALLOW_LIVE_WRITES=1` is the only combination that sends, books, pauses or moves anything.
- `.claude/hooks/guard_live_writes.sh` is registered only in the repo-root `.claude/settings.json`, so it does **not** run in sessions launched from `Coding/` or any other folder, and where it does run it only matches command text (re-review 2026-09-22, SAF-1 and SAF-3). Since 864ebe9 it also blocks writes to `config/approved_templates.json` and the approve/revoke modes of `jobs/approve_templates.py` (rule d), but it still is not installed for other folders until Lorenzo applies `Agentic Worklfows/changesets/claude_guard/` from his own terminal. Do not rely on it. The real protection is the code-level `shared.settings.guard_write` and, for templates, the git-tracked registry (Lorenzo reviews `git diff -- config/approved_templates.json`); never set the live flags or approve templates yourself.
- Every live change is a change-set under `Agentic Worklfows/changesets/` with an apply script: `--dry-run` diffs against live, live apply backs up the current object first.
- No Instantly webhooks yet: the reply engine's shadow poller reads replies with GET calls instead.
- Tests run on the recorded fixtures in `services/reply_engine/tests/fixtures/` with mocked transports; local Python is 3.9, so no `X | Y` unions or `match`.

Layout: `shared/` (API clients, store, notify, job log, LLM, slot rules), `services/reply_engine/` (S1–S5, S8), `jobs/` (O1–O8), `changesets/`, `runbooks/`, `products/` (F2 kits).

Rules the engine enforces: an engine email (first reply, counter-proposal, booking confirmation, cadence touch, show-rate or no-show message) auto-sends only when its text is exactly a template Lorenzo approved with `jobs/approve_templates.py` and unchanged since, the template kill switch is off and every send check passes; anything else is an approval card (replies) or held (cadence, show-rate, no-show) (rule of 2026-09-22, see `Agentic Worklfows/runbooks/template_approvals.md`); slots 12:00-18:00 CT Mon-Fri, ≥4 h out, ≤5 business days, never double-offered; replies go through Instantly's reply endpoint from the original inbox/thread; sends only 07:00-19:00 CT; pricing and proof only from `config/offers.md`.

Do not touch: the Upwork application flow and Demo Library loop; live campaign `email_list`; anything without a dry-run first.

Runtime models: Haiku for classification (escalate < 0.8 confidence to Sonnet), Sonnet for drafts and research lines, Opus 5 weekly for retro/proposals and the 20-draft/50-classification audit. Build models: Opus 5 for sales/marketing design, Sonnet for fulfillment/ops scripts. (Fable was the original pick; Lorenzo's weekly Fable allowance ran out on 2026-09-21, so Opus 5 is the heavy model everywhere. shared/llm.py MODEL_POLICY is the single place to change it back.)

Definition of done for any brief: pytest green, dry-run/replay shadow log, runbook in `runbooks/`, Job_Log rows, evidence in the report.
