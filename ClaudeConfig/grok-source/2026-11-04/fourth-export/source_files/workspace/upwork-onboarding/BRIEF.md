# Upwork demo/proposal pipeline: working brief (Grok Bot onboarding)

Compiled 2026-10-20, 9:15 PM CDT, read-only. Nothing was modified on the Mac, no queue/registry command was run, and nothing was submitted.
Canonical root (Mac): `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline` (PIPELINE).
Tool root (Mac): `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator`.
Snapshot: `/workspace/upwork-onboarding/handbook/upwork-master-handbook/` (box). verify_package.py: PASS, 269 files.

## 0. Session state and hard boundaries
- All 6 jobs in the 2026-10-20 batch are **recorded**. Proposals are finalized. **Queue clearing and Upwork saved-job removal are PAUSED by Lorenzo.** Don't archive anything or unsave jobs until he tells you to.
- Lorenzo records the Looms and submits every application himself. No live account writes, no sending, no publishing. The only Upwork connector use is reading saved jobs (`find_saved_jobs` list, org_uid `2081884703335585732`, limit ≤10, offset pagination; use `job.id`/`job.url`, not the saved-record id).
- The five rejected jobs from 2026-10-19 stay archived. Don't revive them. Don't start a batch without an explicit request.
- Only main touches the queue, builds, review receipts, finalization, and Git. Workers edit only their assigned `deck-spec.json` and private evidence.
- Commit or push only when Lorenzo asks. Before any push, `git rev-list --max-parents=0 HEAD` must equal `fe95263e92f15c9b2f8dc20a8806c00343c1ef32`. Never push --all, --mirror, --tags, or archive/*.
- Standing directives live in `PIPELINE/DIRECTIVES.md` (U-001..U-013). Log a new standing instruction or correction there in the same turn and update the affected rules (U-013).

## 1. Locked proposal, approved facts, P.S. bullets (verbatim, UPWORK_PROCESS.md §6 to §8)

## 6. Proposal (locked format)

```
Hey there 👋 I do [X] builds all the time, so here's your [system] finished and connected, [N]-min video: https://www.loom.com/share/[LOOMURL]

The video walks through what your [thing] will look like once it's [set up and live], [input] going in and [output] coming out: [the 4 to 6 things shown, in order].

The build is done; the video is just a more visual way to show it running end to end.

[Middle paragraph: answers the post's questions in one to four plain sentences, ends with "I can start this week."]

The next step is a quick 15 minute call. Just reply here or send me a message on Upwork, I'll send over three times, and we'll get everything started.

Lorenzo

P.S. A few other things I've done:

-> [bullet]
-> [bullet]
-> [bullet]
-> [bullet]
```

**Format**
- Preview: 133 to 150 characters, counted from the start through `https://www.loom`. Check it with:
  ```bash
  python3 -c "import sys; sys.path.insert(0,'/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator'); from upwork_gen.verify_job import preview_length; print(preview_length(open('<job>/proposal.md').read()))"
  ```
  To hit the range, trim or lengthen the opener's [X] and [system] wording.
- Required keyword goes inline before the greeting: `SyncReady. Hey there 👋 ...`, `TRACKER. Hey there 👋 ...`.
- "The video walks through" appears exactly once.
- Sentence case, no em dashes.
- No Claudeisms: no sentence or clause that restates, sums up or sells the point just made. Say it and stop.
- "[set up and live]" fits the job. Real variants: "fixed and live", "cleaned up and live", "built and live", "connected and live", "reviewed and running".
- A company name the post states can go in the opener ("here's El Amigo's lead system", "here's RestoreNow's lead intake") and in the walkthrough line ("what TrustInSoft's Zoho setup will look like", "what El Amigo's marketing will look like").

**Never**
- Never discuss billing: no rates, prices, fees, retainers or budget. When the post asks, write "we can cover that on the call".
- Never invent facts about Lorenzo, past clients, counts (e.g. A2P approvals), past campaign stats, years of experience, certifications, or specific past debugging stories. When a post asks for one, leave it out and tell Lorenzo so he can supply it.

**P.S. bullets**
The bullet text comes from `templates/ps-case-studies.md`. `verify_job` reads that file and fails a P.S. missing a case study's number. Facts are fixed: every number and what it was stays word for word.
- R: `-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.`
- A: `-> Scaled my own AI agency to $10,000 a month on the same kind of system.`
- C: `-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.`
- L: `-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.`

Order, as practised:
- Trades and contractors: R, A, C, L.
- Lender, finance, insurance, real estate, ads: L, R, A, C.
- GHL or AI builds, for non-agency clients and for agencies: A, R, C, L.
- Outbound, cold email, B2B: C, A, R, L.
- When two rules fit, the client's own business wins: a GHL build for a roofer or HVAC company is R first, for an insurance agency L first.

Agency tail: keep "on the same kind of system" only when the build is what his agency itself runs on (cold email and outbound, lead generation and follow-up, AI agents). For anything else (a CRM or e-commerce sync, a bakery's boards, a dental account build), end the bullet at "Scaled my own AI agency to $10,000 a month." Roofing, consultancy and lender tails stay as written unless they read off for the job; shorten rather than invent.

No-video (text-only) proposals: no locked format yet; ask Lorenzo for the shape. Finalize needs a Loom, so log nothing until he decides.

## 7. Confirmed facts about Lorenzo (use only these)

- Runs AdveroSolutions.
- Sets up GoHighLevel accounts all the time.
- Sends 100k+ cold emails a month on Instantly, with an agent researching each message, and Apify and MillionVerifier for list building and checking.
- His cold email setup: mailboxes and lookalike domains provisioned through a mailbox provider (Zapmail, about $3 to $4 per mailbox, pre-warmed when speed matters; never put the price in proposal copy), everything configured in Instantly, one unibox, Instantly's API wired to Claude.
- Works daily in n8n, Make and Claude Code, with MCP tools on live APIs.
- Has Claude and Grok agents deployed in his own agency and for numerous client companies.
- Has built AI agents on a client's existing database for numerous companies. "Just finished a similar build last week" is approved for those.
- Has built bots in Hermes AI and Muse, and in every major bot platform. He recommends Hermes over Muse for now.
- Built the intake system for a PI law firm.
- Has consulted for very large companies.
- Has experience working with dental practices. Not a GHL dental build, PMS integration or offline conversions.
- Has set up flows like these for other bakeries.
- Has worked with outdoor living / construction companies, like the Texas GHL consult client.
- Has built systems for several other lenders.
- Deploys systems daily.
- Runs his own business on a Claude setup: skills, connectors, a morning brief.
- Is based in DFW (Dallas-Fort Worth), Central Time, US-based. Mention it for Texas or DFW clients and for time-zone questions.
- The four P.S. case studies in section 6.
- His website is adverosolutions.com, hosted on Vercel. It isn't a GoHighLevel site.
- Not confirmed, so never claim:
  - any certification
  - JobTread, AppFolio, PadSplit, NextTech or Aesthetix, WhatConverts or CallRail builds
  - a number of A2P approvals
  - HubSpot builds specifically (ask him)


## 8. Screening questions ("Describe your recent experience…" and the like)

- Answer in his voice: short, plain, first person, no em dashes, no Claudeisms.
- Use only section 7 facts plus what the build shows.
- Price, rate or fee questions: "we can cover that on the call", or leave the pricing to him.
- Links: Upwork can flag links that lead to contact details or a booking page. Prefer "My work samples are on my Upwork profile, and the video in my proposal shows your build."
- Compliance questions such as SMS to people who haven't opted in: the answer is no, with the compliant route (register A2P 10DLC, text only people who consented, gather opt-in by email or a landing page).
- After the answers, list anything he must confirm, e.g. "the HubSpot yes is only true if you've built HubSpot automations".


Pricing in a post always gets "we can cover that on the call". A warm lead or referral must be flagged to Lorenzo first (§9).

## 2. Finalizer (after Lorenzo provides the real Loom URL and runtime)
```sh
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator
/usr/bin/python3 -m upwork_gen.finalize ../upwork-pipeline/jobs/<slug> --loom <actual-Loom-share-URL> --runtime <minutes> --start "this week" --no-copy && cat ../upwork-pipeline/jobs/<slug>/proposal.md
```
- Flags (from finalize.py argparse): job_dir, `--loom` (req), `--runtime` int (req), `--start` (req), `--draft`, `--name <First>` (only when jd.txt has `client first name:`), `--variant` (default do-x-all-the-time), `--replace-loom`, `--relog`, `--no-log`, `--no-copy`, `--posted`, `--connects`, `--boosted yes|no`.
- **Always pass `--no-copy`. Never pbcopy. Never hand-edit proposals.csv.** If the runtime is unclear, use 2. "50/fifth/115 minute call" means the 15-minute call. "too many video" means two minutes.
- Preview must be 133 to 150 chars counted through `https://www.loom`. Check: `python3 -c "import sys; sys.path.insert(0,'<tool root>'); from upwork_gen.verify_job import preview_length; print(preview_length(open('<job>/proposal.md').read()))"`. Count it with the name in place of "there" when `--name` will be used.
- The finalizer refuses (exit 2) when: the preview is out of range; [LOOMURL]/[START]/[greeting] would remain; more than one "Lorenzo" sign-off; a different Loom is already present (use `--replace-loom` only for a real new recording); proposal.md is missing; the URL isn't a Loom; jd.txt has no `url:` line; the CSV row isn't editable. It reads legacy `spec.json` before `deck-spec.json`, so never leave a stale spec.json.
- After finalizing, show the WHOLE proposal in a code block plus the job link, and do the same after any edit. A manual edit doesn't update the CSV row, so say so.

## 3. Recording-queue CLI
Wrapper `PIPELINE/recording-queue` runs `/usr/bin/python3 templates/sales-deck/queue_engine.py "$@"`. Default store is `~/Desktop/AdveroSolutions/Coding/upwork-pipeline/.local/recording-queue`, with an fcntl lock on mutations. `--root` is only for isolated tests, e.g. `/private/tmp/<unique>`.
Subcommands: `register <manifest>`, `build [ids...]` (no ids builds all), `review <id> --verdict approve|reject --page-hash <sha256> --notes <evidence>`, `status [--json]` (**read-only**), `recorded <id> [--loom URL]`, `reopen <id>`, `archive <id>`, `restore <id>`, `serve [--port 8769]` (foreground), `start [--port 8769]` (idempotent, doesn't open a browser).
Statuses: queued, needs_build, built_pending_review, review_rejected, reviewed_ready, recorded, failed.
Manifest format: `{"jobs":[{"id":"slug-<jobid>","title":"...","spec":"slug-<jobid>/deck-spec.json","jobUrl":"https://www.upwork.com/jobs/~02<jobid>"}]}`.
HTTP server (queue_server.py) is GET-only on 127.0.0.1. It serves `/`, `/health`, `/queue.json`, and `/jobs/<id>/page.html|recording-script.txt`. POST/PUT/DELETE are refused. The board sorts by descending numeric Upwork job ID.
Artifacts are in `.local/recording-queue/public/jobs/<id>/`. Never hand-edit the registry or index. Never run `build.py batch --out` into the shared store.
**Live state (GET http://127.0.0.1:8769/queue.json from the Mac, 9:11 PM CDT 2026-10-20): reachable, HTTP 200. Counts: recorded 6, all others 0.** Jobs, newest first:
1. fintech-web-mobile-ai-2112576497428457570 (Full-Stack AI Developer, Fintech Mobile & Web App + AI Automation)
2. personalized-news-intelligence-2112556179744982477
3. med-spa-ghl-migration-2112537540421545478
4. aged-care-ai-operations-2112536224921411609
5. openai-n8n-production-agents-2112525389850618800
6. ghl-landing-calendar-funnel-2112504919683362216
Batch manifests: `jobs/2026-10-20-queue.json` and `jobs/2026-10-20-final-job-queue.json`. Both are untracked in git.

## 4. Demo templates and how a new demo is generated
- Compiler: `templates/sales-deck/build.py`, which needs only Python 3.9+ stdlib. Schemas: `schema.py`, `native_schema.py`, `gmail_schema.py`, `funnel_schema.py`, `intelligence_schema.py`, `product_schema.py`. Runtime: `runtime/*.js|css`. Catalog: `platforms.json`. Lock: `template-lock.json`.
- Protected outer files (never edit during daily work): `runtime/base.css`, `runtime/components.css`, `runtime/shell.html`, `assets/inter-variable.woff2`.
- Native seeds: `templates/sales-deck/native-templates/{ghl,n8n,zapier,claude}.json`. These are invented samples (Avery Morgan, Maya Chen, Northstar), so never copy their names into a real job. Legacy financial/skool/make examples are technical fixtures only.
- Flow: (1) Main does intake into `jobs/<slug>-<jobid>/jd.txt` (`url:` line, title, metadata, optional `client first name:`, blank line, verbatim post). (2) Main writes the manifest and registers it before specs exist. (3) Pick the exact product and surface from `master-handoff/02-UI-REFERENCE-GUIDE.md`, the `visual-reference/` catalog, and the native-templates review. The outcome is either: accepted template, candidate with a readiness gap, `requires_adapter`, or genuine custom. (4) A Sol Medium content worker writes `deck-spec.json` plus `scene-map.md` and `evidence.md` per CONTENT_BRIEF. (5) Main runs `recording-queue build <id>`. (6) Mechanical checks, then one Astra High review per REVIEW_BRIEF. (7) Main records `review --verdict approve --page-hash <sha>`. (8) Main drafts `proposal.md` from §6. (9) Lorenzo records. (10) Main runs `recorded <id> --loom`, then the finalizer.
- Isolated test build (allowed): `python3 $DECK/build.py validate <spec>` and `python3 $DECK/build.py build <spec> --out /tmp/<x>`. Don't run `build.py lock` to bypass drift.
- Maintenance tests (Mac): `/usr/bin/python3 -m pytest -q -p no:cacheprovider tests/test_build.py tests/test_queue.py tests/test_queue_server.py tests/test_native.py`; `node tests/runtime.cjs`; `node tests/native_browser.cjs`.
- Story: personalized opening (0 to 10s) → mechanism (10 to 35s) → useful result (35 to 90s) → exception → directional goals + blue 15-minute CTA. 2 to 3 demo stops. Default route is 2 minutes.
- Opening caption, exact: "I've already put this workflow together for you. Let me walk you through how it works." It goes on the front page once.
- Intro recipient fallback: verified first name → business name → "your team". A review-derived name needs ≥2 separate reviews, with `source: client_reviews` and `reviewCount` recorded privately. Never imply ownership.

## 5. Acceptance and review essentials (SALES_ACCEPTANCE, REVIEW_BRIEF, Master §8)
1. Correct problem and the exact tool/surface. 2. Every stop adds a new buyer fact, with no duplicate canvas, inspector, or result. 3. Every promised output is visible on Quick, Standard, and Detailed. 4. Causality: no acknowledgement presented as a booking, no invented pipeline movement. 5. Identity, value, owner, time, IDs, and totals stay consistent (no $0.00). 6. The result is readable without raw JSON. 7. Narration gives concrete pointing cues. 8. Job-specific directional goals (no invented uplift) and the blue CTA asking for a reply and a 15-minute call. 9. Replay (settles in ~5s), Show result, navigation, notes, Present/Escape, keyboard, and reduced motion all work. No auto-advance, scroll hijack, or stale timers. 10. Native geometry matches current saved references. 11. Exact hashes are bound to the review. 12. Unmet evidence is reported, never approved.
- Read-aloud gate (U-011): every heading, caption, metric, and CTA must work as plain spoken English. Rejected example: "Agree the product. Test one journey."
- Viewports: desktop at 1440 and 1280 px, plus a 390 px containment check. No network requests. Private evidence must stay out of the page.
- The reviewer returns APPROVE/REJECT per dimension with the page SHA-256 from `build-report.json` and distinguishes source checks from browser checks. Any changed spec, template, page, or script needs a new review.

## 6. Platform and native-reference rules
- Identify product + surface + edition + theme first. Claude Skills, Projects, and Code are distinct surfaces. Grok and Grok Bot are distinct. "Orca" means onorca.dev. Never use GHL chrome as a fallback. Narration stays outside the software frame. No fake JSON downloads or imports.
- Supported adapters (PLATFORMS.md): ghl, n8n, make, claude-code, codex, workbench. The 20 Oct extension added workbench/architecture, n8n typed AI (ai_agent, openai_chat_model via ai_languageModel, http_request_tool via ai_tool), gmail (unsent draft only), ghl/funnel (Neo booking), ghl appointment_status, workbench/product (fintech), and workbench/intelligence. Native candidates: ghl (builder/conversations/pipeline), n8n (editor/node), zapier (editor/test), claude (skills/chat). Reference-only, no adapter: airtable, clay, clickup, cold-email, grok, hermes, hubspot, notion, pipedrive, voice-agent (and zapier in the legacy catalog).
- Saved references under `templates/sales-deck/native-templates/references/current-2026/`:
  - `README.md`, `manifest.json`
  - `ghl/`: README.md, live-capture-provenance.json, official-research-contact-form.png, official-research-contact-form-mobile.png, official-research-live.png, official-research-selected-slot.png
  - `gmail/`: gmail-official-3.webp, gmail-reply-2026.png, sources.json
  - `n8n/`: CURRENT-N8N-COMPARISON.md, n8n-ai-logs-2026-08.png, n8n-ai-memory-2026-07.png, n8n-native-trace-2026-05.png, sources.json
  - Parent `native-templates/references/` also holds claude-project-current.png, claude-project-wide-current.png, claude-skill-detail-current.png, claude-skills-current.png, ghl-card-config-3/6.png, ghl-pipeline-3/4.png, and icon-*.svg. The larger library (29 product plans, 43 curated images) is at `templates/sales-deck/visual-reference/` (catalog.json, references.json, index.html board).

## 7. Model policy (OPERATING_POLICY.md, U-008)
- "Sol Medium" means **GPT-6.1 Sol at medium reasoning effort** (`gpt-6.1-sol`). It's the default for the coordinator and content workers. Sol High is for a bounded hard repair.
- "Astra High" means **GPT-6 Astra at high effort** (`gpt-6-astra`). It does one independent final review.
- Both are OpenAI models selected inside the **Codex app/CLI** on Lorenzo's Mac. Workers are dispatched as generic Codex agents with `fork_turns: none`. Batch chats use `create_thread`, `list_projects`, and `wait_threads`. Speed is Standard by default, Fast only when time-sensitive (2.5× usage). Capacity is 4 agents including main.
- **From this Linux box they aren't usable.** The box has no `codex` binary, and Grok Bot can't pick OpenAI models. `codex` and `claude` CLIs exist on the Mac (`~/.nvm/versions/node/v24.13.1/bin/`), but running them would mean launching paid model sessions under Lorenzo's account, which needs his explicit authorization. Implication: when Grok Bot authors, a separate independent reviewer has to be arranged. A self-review can't be reported as an independent Astra approval (Master §7).
- Don't change global model or agent settings, and don't edit the shared Claude skills.

## 8. Discrepancies (snapshot vs canonical, and internal)
- **Snapshot vs canonical: none in content.** SHA-256 is identical for AGENTS.md, DIRECTIVES.md (=05-DIRECTIVES.md), UPWORK_PROCESS.md, recording-queue, master-handoff 00/01/02/03/NEW_MODEL_PROMPT/VERIFICATION, all six sales-deck docs, sales-deck AGENTS/README/IMPLEMENTATION_SPEC, queue_engine.py, queue_server.py, build.py, and ps-case-studies.md. The zip is the same size as `.local/upwork-master-handbook.zip`.
- The canonical working tree is **dirty** relative to HEAD 6dad2ce (manifest: sourceWorkingTreeHadChanges=true). There are uncommitted edits to AGENTS.md, the master, the sales-deck docs, build.py, the runtime, template-lock.json, finalize.py, and proposals.csv. DIRECTIVES.md and the two batch manifests are untracked.
- master-handoff/ has no 04-LOCKED-PROPOSAL or 05-DIRECTIVES. Those are generated at export (04 = UPWORK_PROCESS §6 onward, verified verbatim; 05 = DIRECTIVES.md). It does contain README.md and build_handbook.py, which aren't in the zip.
- AGENTS.md, UPWORK_PROCESS, BATCH_RUNBOOK, and CONTENT_BRIEF list adapters as "GHL, n8n, Make, Claude Code/Codex, workbench", and PLATFORMS.md lists zapier as reference-only. The Master and native-templates/README, however, describe native Zapier and Claude-app candidates. The Master acknowledges the gap: the candidates are newer.
- PLATFORMS.md's 19 Oct banner says "No replacement native template is accepted yet". The current-2026 README says the six 20 Oct generations were independently approved (`.local/batch-2026-10-20-qa/astra-review.md`). Each statement is scoped to its own date.
- Finalizer interpreter: UPWORK_PROCESS uses `python3`, OPERATIONS uses `/usr/bin/python3`. Use /usr/bin/python3 on the Mac. finalize.py's `--start` help example says "today", but policy is "this week".
- native-templates/README says to run `build.py lock` for local review, while OPERATIONS forbids running lock to bypass drift. Treat lock as maintenance-only.
- UPWORK_PROCESS §5 says to take a name only from the post. The top note, CONTENT_BRIEF, and U-006 supersede that with the two-review rule.
- ps-case-studies.md lists bullets in R,L,C,A order with a simpler "vertical first" rule. Use the more specific ordering rules in UPWORK_PROCESS §6.
- Older, superseded sources still exist: the `~/.claude/skills/upwork/SKILL.md` skill, PROCESS.md, proposal-template-a/b, UPWORK_PROCESS §3 to 4. Don't use them.

## 9. Not read or not found
- Everything the handoff pointed to was found. Nothing referenced is missing (spot-checked on the Mac: runtime/shell.html, extension-contract.md, SALES-REVIEW-2026-10-19.md, visual-reference/README.md, template-lock.json, both batch manifests, jobs/_examples/finished-*.html, astra-review.md, copy-review.md, intelligence-redesign-qa/, verify_job.py, the claude upwork skill, .local/upwork-master-handbook/00-MASTER.md, UPWORK_MASTER.html).
- Not read in full, because it wasn't requested, though it's referenced: 02-UI-REFERENCE-GUIDE.md (59 KB, read per job), 03-TEST-THE-NEXT-MODEL.md, 04 (verified identical to §6+), sources/voice/lorenzo-voice.md and claudeisms.md (**read these before drafting copy**), extension-contract.md, native-templates/SALES-REVIEW-2026-10-19.md, visual-reference/README.md, CLAUDE.md, finalize.py beyond argparse, queue_engine.py beyond the CLI and statuses, and the job folders.

## Addendum, 2026-10-20 10:20 PM CT: rules from the previously skipped files

Sources read: `~/.agents/skills/lorenzo-voice` and `claudeisms` (bundled as handbook `sources/voice/`), repo `CLAUDE.md`, `master-handoff/02-UI-REFERENCE-GUIDE.md` (header and selected entries), `templates/sales-deck/visual-reference/README.md`, `extension-contract.md`, `native-templates/SALES-REVIEW-2026-10-19.md`.

Voice (lorenzo-voice, claudeisms)
- Bar test: would Lorenzo say it out loud to a peer at a bar? Say it and stop. Peer tone, sentence case, "I" on Upwork.
- No em or en dashes anywhere. No exclamation marks in email. Emoji only the Upwork greeting wave. No "+" shorthand except inside fixed proof numbers.
- Never invent facts, clients, numbers or confirmations. Never discuss billing, rates or budget on Upwork (verify_job fails billing words).
- Delete test for Claudeisms/Grokisms: if a phrase can be deleted with no loss, delete it. Avoid the skill's rejected-lines list (hype openers, "I hope this finds you well", "seamless", "leverage", throat-clearing recaps).
- Precedence: the locked proposal in `UPWORK_PROCESS.md` section 6 wins over the voice skill's older Upwork shape (Template A hook, fixed "Looking forward to hearing from you" closer).
- Conflict, not edited: the voice skill's 2026-09-25 operating note says Grok Bot only sends text it was given and never writes customer-facing text. U-014 (2026-10-20) makes Demo Builder the author, reviewer and approver. Treat U-014 as current for demos; shared skills are not modified per standing rule.

Repository rules (CLAUDE.md)
- For Upwork work read `DIRECTIVES.md` and `master-handoff/00-MASTER.md` first.
- Controlled environment: nothing touches live Instantly, GHL, Upwork, Gmail, Calendar or Modal without Lorenzo's approval. Do not touch the Upwork application flow or the Demo Library loop.
- Python 3.9 (`/usr/bin/python3`). Git pushes follow the repo push rules; no commits unless asked.

UI reference readiness (02 guide, visual-reference README)
- 29 products, `productionReady: false`. Keep four states separate: saved image, technical catalog, implemented screen, accepted generation. A saved image or catalog entry is never approval.
- Read only the job's product entry and images; match the exact product and surface; no generic GHL chrome.

Native candidates (SALES-REVIEW-2026-10-19)
- GHL, n8n, Zapier (editor/test), Claude app (skills/project/chat): desktop sales candidates, bounded review, native production parity withheld. Findings S1 to S3 closed; S4 is the n8n mobile whole-flow limitation.
- Reference gaps: GHL account settings, n8n execution chrome, Zapier editor/test panels, Claude Contents and populated chat. Zapier Paths/Next Gen not implemented; no Cowork/Code substitution for the Claude app.
- extension-contract: `ai_agent`/`chat_model` unavailable only in the legacy canvas; the typed n8n AI surface (ai_agent, openai_chat_model, http_request_tool) is supported per PLATFORMS 20 October extension.

Docs sync done 10:16 to 10:18 PM CT: see `DIRECTIVES.md` last history entry; backups in `.local/backups/20261020-sync-all/`.
