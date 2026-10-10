# AdveroSolutions — Agent Instructions

> Canonical source: `Agentic Worklfows/Claude.md` (Claude's copy). This root file ensures Codex auto-loads the instructions.

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
├── AGENTS.md          # Full agent instructions
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
| `generate_linkedin_content.md` | RETIRED 2026-10-06; LinkedIn posts now come from the `linkedin-content` skill |
| `linkedin_outreach.md` | LinkedIn outreach: Sales Navigator list, blank connection requests, Loom DMs, FU1-FU3, voice notes; Lorenzo sends everything, Codex drafts (skill `linkedin-outreach`) |
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

Plan: `Agentic Worklfows/REVENUE_AUTOMATION_BLUEPRINT.md` (build IDs M#/S#/F#/O#, briefs A1–A12). Live ids: `Agentic Worklfows/config/ids.json`. Offer sheet: `Agentic Worklfows/config/offers.md`. Agents: `.claude/agents/{sales,marketing,fulfillment,ops}.md` (Codex copies: `.codex/agents/*.toml`).

**Controlled-environment rule (Lorenzo, 2026-09-21):** nothing touches live Instantly, GHL, Upwork, Gmail, Calendar or Modal until it is tested and Lorenzo approves the push.
- `MODE=shadow` (default) proposes, logs and notifies Lorenzo only. `MODE=live` plus `ALLOW_LIVE_WRITES=1` is the only combination that sends, books, pauses or moves anything.
- The Claude Code live-write guard hook (`.claude/hooks/guard_live_writes.sh`) was removed on 2026-10-10 at Lorenzo's request so agents run without stopping for approval. The protection is the code-level `shared.settings.guard_write` and, for templates, the git-tracked registry (Lorenzo reviews `git diff -- config/approved_templates.json`); never set the live flags or approve templates yourself.
- Every live change is a change-set under `Agentic Worklfows/changesets/` with an apply script: `--dry-run` diffs against live, live apply backs up the current object first.
- No Instantly webhooks yet: the reply engine's shadow poller reads replies with GET calls instead.
- Tests run on the recorded fixtures in `services/reply_engine/tests/fixtures/` with mocked transports; local Python is 3.9, so no `X | Y` unions or `match`.

Layout: `shared/` (API clients, store, notify, job log, LLM, slot rules), `services/reply_engine/` (S1–S5, S8), `jobs/` (O1–O8), `changesets/`, `runbooks/`, `products/` (F2 kits).

Rules the engine enforces: an engine email (first reply, counter-proposal, booking confirmation, cadence touch, show-rate or no-show message) auto-sends only when its text is exactly a template Lorenzo approved with `jobs/approve_templates.py` and unchanged since, the template kill switch is off and every send check passes; anything else is an approval card (replies) or held (cadence, show-rate, no-show) (rule of 2026-09-22, see `Agentic Worklfows/runbooks/template_approvals.md`); slots 12:00-18:00 CT Mon-Fri, ≥4 h out, ≤5 business days, never double-offered; replies go through Instantly's reply endpoint from the original inbox/thread; sends only 07:00-19:00 CT; pricing and proof only from `config/offers.md`.

Do not touch: the Upwork application flow and Demo Library loop; live campaign `email_list`; anything without a dry-run first.

Runtime models: as of 2026-09-25 (Lorenzo), every runtime role uses Opus 5.5 (`claude-opus-5-5`): classification, escalation (< 0.8 confidence still escalates), drafts, research lines, the weekly retro and proposals, and the 20-draft/50-classification audit. Nothing runtime is on Haiku or Sonnet. Thinking cannot be disabled on Opus 5.5, so shared/llm.py sends effort `low` per role with a thinking headroom on max_tokens. Build models: Opus 5 for sales/marketing design, Sonnet for fulfillment/ops scripts. (Fable was the original pick; Lorenzo's weekly Fable allowance ran out on 2026-09-21.) shared/llm.py MODEL_POLICY is the single place to change a runtime model.

Definition of done for any brief: pytest green, dry-run/replay shadow log, runbook in `runbooks/`, Job_Log rows, evidence in the report.

## Working in sections (from 2026-09-23)

The revenue build is split into 4 sections, each run in its own chat at the same time: (1) email follow-up after an interested lead goes quiet, plus the 90-day nurture; (2) booked calls: confirmation, reminders, no-show recovery; (3) Upwork follow-ups; (4) core engine, the one Google Doc, cold campaigns, go-live. `Agentic Worklfows/sections/README.md` has the rules, who owns which files, and the kickoff message for each chat; each section's folder has its handoff `README.md` and a `STATUS.md` to keep current.
- Each chat works in its own git worktree under `.worktrees/` on branch `section/<name>`, never in the main folder.
- **Push every change to GitHub** (Lorenzo, 2026-09-23; replaces the earlier "no push"): commit by path, push the section branch, then rebase on `origin/main`, run the full suite and push to `main`. Pushing deploys nothing; every live-write rule above still applies. Before every push, `git rev-list --max-parents=0 HEAD` must print only `fe95263e92f15c9b2f8dc20a8806c00343c1ef32`; never push `--all`, `--mirror`, `--tags` or an `archive/*` ref (old history holds live credentials).
- Test command (from `Agentic Worklfows/`): `PYTHONPATH=tools/netguard python3 -c "import netguard, pytest, sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider']))"`.

## Context Codex should read

Claude Code keeps its working knowledge outside the repo; these copies are in the repo for Codex:
- `ClaudeConfig/memory/MEMORY.md`: index of Claude's project memory (decisions, rules, project state). Read the files it links before acting on a topic it covers.
- `ClaudeConfig/skills/<name>/SKILL.md`: the skills (cold campaigns, personalization, lead sourcing, replies, Upwork, etc.).
- `ClaudeConfig/global-CLAUDE.md`: Lorenzo's global rules (delegation, no Claudeisms in copy).
- Cold-email lead pipeline: `Coding/lead-scrape-2026/` (`personalize/DAILY_RUN.md` for the run, `personalize/tools/` for the per-batch tools, `instantly_push.py` for pushes). API keys are in that folder's `.env`; never print them.

Refresh the copies with `ClaudeConfig/sync_from_home.sh`, then commit and push.
