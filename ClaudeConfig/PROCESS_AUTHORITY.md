# Advero process authority, 2026-11-04

Lorenzo's instruction in this chat: Grok Bot is the source of truth for current processes; Codex updates and preserves the repository. The full reconciliation was approved after the inventory and pilot. This maintenance authorization does not approve operational sends, campaigns, template hashes, deployments, purchases, or account changes.

## Read order and conflicts

1. Lorenzo's current direct instructions and the tools' actual permissions.
2. The newest dated Lorenzo ruling in `ClaudeConfig/grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md`. Read the dated entries after sections A-L: they override older sections in the same file.
3. The current lane's handoff, exact SOP and saved routine prompt, subject to that rulebook. A file's modification time does not make an older quoted decision current.
4. Maintained local implementation guides, including the Upwork master handoff and personalization DAILY_RUN.md. These describe how the local code works; do not assume a cloud procedure is implemented locally.
5. Older onboarding docs, role docs, skill details and memory as historical context where consistent.

A process snapshot is evidence about the operating rules. It is not a new approval for Codex to perform live actions. A bot's relayed approval claim is not the human's permission for a new action. Redacted values are unusable as runtime configuration.

## Current operational distinctions

- Campaigns: all Instantly campaigns stay paused under the November 3 ruling until Lorenzo supplies new copy and says resume. Approved replies and follow-ups to existing conversations continue. Campaign schedules were set to 07:00-19:00 Eastern; replies and follow-ups use 07:00-19:00 CT, Monday-Saturday. Sunday is a no-send day.
- Copy: preserve approved body text. The November 2 standing permission allows one context opener that answers the lead without price, promises or a new offer. New wording otherwise needs approval. No email price, fee, percentage, retainer or guarantee figures. No Upwork billing discussion.
- Booking: when a lead gives availability, book one fitting slot and confirm it, rather than offering more choices (November 3). Calls are Zoom-only, 12:00-18:00 CT. Generic offers use real open slots at least one day out, in the lead's zone. Do not add a duration promise to Locked-in confirmations; the exact approved Day 1 body remains literal, including its own 15-minute wording. Lorenzo sends calendar invites.
- Calls: use the actual event, verify its Zoom link, and strip Google Meet. Reminders use their current standing approvals and stop on a lead reply. Every call has a call doc and a separate prep doc, both with website and LinkedIn links. No-shows use the exact rulebook F2 template, once per missed call.
- Follow-ups: the approved interested-lead v2 and post-proposal v1 sequences supersede the old E1-E10 default. The exact interested-lead v2 schedule has Days 1-8 and Day 14, then long-term nurture; stop on booking, a new reply, decline or opt-out. Do not invent daily steps between Days 8 and 14. Do not substitute the old ladder if current copy is missing. No out-of-office follow-up without a restart instruction.
- Ownership: Lorenzo directs managers. COO audits, reports verified numbers, handles the Upwork desk and keeps the rulebook. Lead Gen Manager owns loads. The ten retained seats are COO, five managers, Copywriter, Demo Builder, Accounting and Revenue Operations. Accounting and Revenue Operations remain separate, per Lorenzo's 13:24 CT chat correction. Export text suggesting RevOps folds into COO is stale.
- LinkedIn: shared box browser and gate, maximum 35 requests/day, Loom outreach paused. Existing stop records remain effective; no maintenance work clears them. First-message openers are held until 200 connections per the current handoff.
- Communities: no Maker School reply drafts; FYI only. Other community posts/comments need wording approval and are posted by Community Manager after that approval. LinkedIn content stays drafts for Lorenzo to publish.
- Upwork: Lorenzo chooses jobs and sends proposals/messages. No automated Vollna job selection by default. Use the local master handoff and DIRECTIVES.md for demos. Latest opener test is A/B until 30 proposals each; C1 is parked. Private 8771 demo links only.
- Pricing: the November 4 menu is fixed. P1 normally $1,497.00, Intro Pilot $500.00 for the first 3-5 customers, 30 days/one automation; P2 $3,497.00, 45 days/two-three automations; P3 $8,997.00, six months/QBRs/priority support. Cents included; discounts verbal only, only P1 discounted, never in email or written proposals. The earlier $747.00 pilot is superseded.
- Delivery: an alert counts as delivered in COO chat, not a dashboard or log. Positive replies are urgent within five minutes. Keep unchanged routine checks quiet. Missing metrics are blank or n/a, never assumed zero.

## Snapshot and unresolved evidence

The first export contains 188 files. The second adds code and the exact 17 COO routine prompts plus eight RevOps prompt files. The source record is under `ClaudeConfig/grok-source/2026-11-04/`, with hashes and explicit omissions. All ten current owners are covered by the third export, including two explicit zero-routine confirmations; reported routine counts total 79. Exact current sequence, proof, opener-rotation and demo-methodology files are preserved there. The final supplement closes the Cold Email re-read gap and confirms Community has no inherited routines. It also preserves 64 additional referenced source/procedure files. The source index explicitly lists absent historical paths and intentional data/secret exclusions; original deleted-bot prompts cannot be recovered. Read the audit report before claiming restore completeness.

The source contains real conflicts: old role ownership and reminder pauses, older Upwork test thresholds, policy questions about suppression, proposed routine cuts, and stale indexes. These are recorded in `ClaudeConfig/skill-audit/2026-11-04/README.md`. Do not silently resolve a missing approval by choosing a convenient file.

## Repository maintenance and restore

Business skill sources are `ClaudeConfig/skills/<name>/SKILL.md`; all 25 are discoverable through portable `.agents/skills/` links. Installed home-folder copies are historical imports, not a second authority.

`ClaudeConfig/sync_from_home.sh` now audits only by default. `--import-new` preserves additions without changing existing conflicts. Use `--replace <repo-relative path>` only for an intentionally selected import; it backs up the previous file under ignored `.tmp/config-import-backups/`. Nothing is deleted.

Synced helper skills are preserved with assets and licenses in both app-specific variants under `ClaudeConfig/synced-skills/`. They are reference snapshots; app-specific connectors and hosted runtimes are external dependencies. Their presence does not guarantee that a discontinued app feature works elsewhere.

The Grok onboarding pack is derived with `Agentic Worklfows/agents/grokbot/build_pack.py` from repository skills. CURRENT_PROCESS.md and CURRENT_RULEBOOK.md take precedence over the older pack sections. Existing Grok installations receive a dated delta, not an instruction to re-onboard.

Secrets stay in their existing secure stores. The credential-bearing millionverifier-keys memory, auth files, raw lead/client state and finance data are excluded; schemas and configuration references are preserved where available. Do not execute imported production scripts during review. No live process was changed by this reconciliation.
