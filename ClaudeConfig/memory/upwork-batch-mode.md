---
name: upwork-batch-mode
description: "How Lorenzo runs a batch of Upwork jobs at once — per-job folders under Coding/upwork-pipeline/jobs, subagents write files only, main session compiles and verifies, builds loaded by name via ./job"
metadata: 
  node_type: memory
  type: project
  originSessionId: db551e75-45d4-461e-8eba-556c8fab2d9a
  modified: 2026-09-07T17:57:45.027Z
---

Established 2026-09-07. Lorenzo pastes several job posts in one message and
wants them all built at once, then loads each build by name only when he is
ready to record that Loom. Nothing goes on the clipboard until he asks.

**Layout:** `Coding/upwork-pipeline/jobs/<job-slug>/` holds `jd.txt`, `spec.json`,
the compiled `.n8n.json` / `.excalidraw` / `.mmd.md`, `assessment.md`, `beats.md`,
`proposal.md` (placeholders `[N] [LOOMURL] [START] [DRAFT]`). Shared subagent
brief lives at `jobs/_AGENT_BRIEF.md`. Helper: `Coding/upwork-pipeline/job <partial-name> [n8n|flow|mermaid]`
puts that job's file on the clipboard and prints its notes; `job list` lists them.

**Division of labour (his explicit ask):** subagents spawned on a cheaper model
write files only (never compile, never pbcopy, never commit); the main session
compiles serially with `--no-copy` and verifies every spec, JSON, proposal and
beat sheet itself before hand-off. Verification on the first batch caught real
problems: error-trigger nodes importing as Calendly, Ollama nodes as OpenAI,
broken `https://www.loom[LOOMURL]` placeholders, a double "the video" sentence,
and a beat sheet promising a demo the proposal didn't. Always run that pass.

**Why:** his context budget is the constraint, and the batch lets him record
Looms back to back. After a batch he deletes the job folders he did not apply
to ("we'll do a new batch"); the vault archetypes promoted from them stay.

**How to apply:** on a multi-post paste, split by title, write jd.txt per job,
spawn one agent per job with `model: "opus"` pointing at the brief, compile
serially, verify, then report a one-table summary. Load by name on request.
He skips a job when boosted connects are too high, so don't finalize copy
until he has recorded. See [[upwork-proposal-copy]], [[upwork-workflow-generator]].

**Updated 2026-09-09.** Saved-jobs flow: he hearts jobs in Upwork, the Upwork connector
lists them, one Opus subagent per job writes spec/assessment/beats ONLY. Proposals are
written by the main session, never a subagent ("that is going to hurt the process more
than help it"). `jobs/_ORDER.txt` + `job list` give newest-first apply order; `job
<name>` prints the Upwork url first because he closes tabs. Test opener "i went ahead
and built your system, i finished a similar build for a company just a week ago" is
being A/B logged. Full process now lives in the `upwork` skill v3.

**Standing trigger from 2026-09-09:** he hearts the jobs for the next batch in Upwork and
says the batch is saved; we pull them via the Upwork connector and run the process above.
Operational copy at `Coding/upwork-pipeline/PROCESS.md`, proposal templates in
`Coding/upwork-pipeline/templates/`, subagent brief at `jobs/_AGENT_BRIEF.md`.

**Updated 2026-09-22 (quality overhaul).** Subagents now write `dossier.md` first,
then spec/assessment/beats; the main session runs `python3 -m upwork_gen batch`
(compile + copy + `verify_job` table), then one client's-eye reviewer subagent per
job (`jobs/_REVIEWER_BRIEF.md`, both scores >= 8), and after recording
`python3 -m upwork_gen.finalize`. See [[upwork-quality-overhaul-2026-09]].
