# Skills and process reconciliation, 2026-11-04

Current state: reconciliation and offline verification are complete. All 25 business-skill entrypoints use Grok Bot's current dated rules, and the source archive is saved. Lorenzo approved the full workflow after the initial inventory and pilot.

## What was preserved

- 25 maintained business skills, with portable `.agents/skills/` discovery links and a source catalog in `SKILL_CATALOG.md`.
- 369 sanitized source files across four Grok exports, each checked against its manifest hash. The owners reported 79 routine records across eight owners; Copywriter and Demo Builder confirmed zero routines. The final supplement re-read Cold Email routines 8-16 and confirmed Community Manager has no inherited routines on its bot.
- Current interested-lead and post-proposal copy, approved-proof boundaries, the Upwork opener rotation and demo methodology.
- Six previously missing project-memory records, plus both app-specific variants of 14 unique synced helper skills with their support files and licenses.
- Codex setup records that existed only in an older worktree, saved as historical setup evidence without running the installer.
- Existing local Upwork process directives and handbook text. Existing implementation/source work is separately preserved in GitHub branch `codex/preserved-source-2026-11-04`, commit `515bd8e260305313abd8bfbc0483d7ea859dd28f` (441 source paths). This is an unreviewed WIP snapshot, not a runtime release. See `preserved-source.tsv` for included and excluded paths.

## Source precedence and actual corrections

`ClaudeConfig/PROCESS_AUTHORITY.md` records the read order: current direct Lorenzo instructions, newest dated Lorenzo decisions in Grok's rulebook, current lane evidence, local implementation guides, then older consistent detail. Skill headers explicitly override conflicting older sections. Prior text remains dated evidence rather than being silently destroyed.

Corrections include: all cold campaigns paused until new copy/resume; replies/follow-ups continue; campaign schedules Eastern versus reply window Central; one fitting booking when availability is supplied; Zoom-only confirmations with no added duration promise; current reminder/no-show policy; current sequence schedules rather than the old E1-E10 default; no email pricing; the fixed November 4 offer menu; ownership after consolidation; current LinkedIn caps/stops; Maker School reply-draft stop; the current Upwork A/B milestone; and exact approved proof boundaries.

The sync tool now audits only by default. Missing files require `--import-new`; existing conflicts retain the repo version unless an exact path is selected with `--replace`. A replacement is backed up, and an invalid replacement fails before any import. No repository file is deleted. The pack builder and parity checks now read repo skills, include all 25 skills, and place current authority and rulebook text before historical onboarding.

## Verification and review

This was a self-review, not an independent agent review. The review checked each dated override against its source and corrected three issues found during review: Sales Nav ownership belongs to Lead Gen Manager; the exact interested-lead schedule is Days 1-8 then Day 14; a literal approved Day 1 duration phrase is preserved while Locked-in confirmations receive no added duration promise.

- 21 onboarding-pack checks passed before the full run.
- 4 repeatable non-destructive-sync behavior tests passed.
- 25 skill frontmatter records passed YAML/name/description checks with the system Ruby YAML parser. The bundled Python validator could not load because PyYAML is absent; no package was installed.
- All 25 discovery links and current-source references resolve. All 369 exported source hashes match.
- 54 archived Python files were parsed without importing or running them: 53 parsed, and the exported historical ask_opus.py has one syntax error caused by a [SECRET] redaction at line 885. The raw source remains unchanged and hashed; it is not runnable as exported. Shell wrappers were checked with `bash -n`. No imported production script was executed.
- Initial full engine suite: 9,967 passed, 2 failed in 472.53 seconds. One failed because its temporary file could not be written under the worktree's restricted permissions; one performance test recorded 0.058290292 seconds against 0.058. Both passed on a targeted rerun with the required write access (2 passed in 1.14 seconds). The final full rerun passed: 9,969 tests in 312.64 seconds, with zero blocked egress attempts and zero credential-file opens. No test threshold or production send rule was changed. Netguard recorded zero blocked egress attempts and zero credential-file opens.

## Explicit limits and exclusions

- These are source and procedure records, not a complete copy of live customer state or a tested deployment. Secrets, auth files, raw lead/client records and transaction data remain in their existing systems. The credential-bearing `millionverifier-keys.md` memory was excluded before reading it.
- Grok's final reference scan covered 608 paths and recorded 117 intentional exclusions plus 25 unresolved references: 12 absent historical files and 13 filename patterns. Its full list is `ClaudeConfig/grok-source/2026-11-04/fourth-export/INDEX.md`. Original prompts from already-deleted bots are unavailable; current rebuilt prompts are preserved with that status. No missing text was invented.
- Archived code retains redactions and external runtime/configuration dependencies. It was not enabled or deployed. App-specific helper skills retain their hosted-tool dependencies. The old recovered installer remains historical and unexecuted.
- 414 preexisting paths were excluded from the separate source snapshot as generated QA/archive/old-backup material or separate submodule work. The two dirty Git submodules remain untouched and are identified in the inventory. Generated QA assets are regenerable; no user files were removed.
- Installed home-folder copies intentionally differ from the maintained repo skills. `local-config-final.tsv` records these conflicts so a future import cannot silently overwrite the current rules.
- The source snapshot stops at Grok's 13:52 CT final supplement. Lorenzo then asked Codex to stop interacting with Grok Bot; that instruction was honored. Later Grok changes are outside this snapshot.

The dated Grok delta is `Agentic Worklfows/agents/grokbot/updates/2026-11-04_repository-process-reconciliation.md`. No live routines, campaigns, templates, permissions, accounts, billing or client messages were changed by this task.
