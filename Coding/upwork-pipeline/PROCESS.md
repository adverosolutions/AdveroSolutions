# Upwork batch process (pointer, v4 2026-09-22)

The full process lives in the `upwork` skill: `~/.claude/skills/upwork/SKILL.md`
(copy in `upwork-workflow-generator/skill/SKILL.md`). It wins over this page.
This is only the order of operations.

Tool root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator`
Pipeline root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline` (this folder)

1. Lorenzo hearts jobs in Upwork and says the batch is saved.
2. Main session pulls them with the Upwork connector, writes `jobs/<slug>/jd.txt`
   per job (with a `client first name: <Name>` line in the metadata paragraph
   whenever it knows the name) and writes `jobs/_ORDER.txt` (newest post first
   by Upwork job id).
3. PAUSED (Lorenzo, 2026-09-22): skip this step until he turns it back on
   (no Chrome step, no grades, nothing dropped; go straight to step 4). Kept
   for when it returns:
   Client intel, per job, before any subagent, in Lorenzo's Chrome with Claude
   in Chrome (the built-in browser is blocked by Cloudflare; a Cloudflare
   "Just a moment..." page clears in about 5 seconds; an interactive challenge
   means stop and ask Lorenzo, never click it).
   Install once per snippet version with the scripts from
   `cd <pipeline root> && python3 client_intel.py --install-js` (add a file
   input, `file_upload` `client_intel/snippet.js` into it, store it in
   localStorage). Then on each job page run the one line from
   `cd <pipeline root> && python3 client_intel.py --loader`; it returns the
   object (`not_installed` / `stale_install` means install again).
   Write the object to `jobs/<slug>/client_raw.json` with a heredoc and run
   `cd <pipeline root> && python3 client_intel.py jobs/<slug> jobs/<slug>/client_raw.json`.
   It writes `client.json` and the `client first name:` / `client grade:`
   lines in jd.txt. If the page fails, carry on without it. C and D jobs are
   dropped before any subagent is spawned; the batch does not wait on
   Lorenzo. Their grades still go to him in the batch table (name, grade,
   reasons, dropped yes/no) so he can reinstate one by name.
4. One Opus subagent per job with `jobs/_AGENT_BRIEF.md`: `dossier.md` first,
   then `spec.json`, `assessment.md`, `beats.md`. Folders from an older run are
   rebuilt from `jd.txt`, never patched. The one exception is the revise round
   in step 8: a subagent whose prompt carries the reviewer's fixes opens this
   run's files and applies only those fixes.
5. Main session drafts every `proposal.md` from `templates/` (sentence case,
   greeting from the dossier's first name).
6. GoHighLevel jobs: `ghl_prereqs` dry run, then `--apply` (the first apply on a
   new account or token waits for Lorenzo). See `jobs/_GHL_BUILDER_BRIEF.md`.
7. `cd <tool root> && python3 -m upwork_gen batch <job dirs>` compiles, copies into each folder
   and runs `verify_job`.
8. Reviewer gate: one reviewer per job with `jobs/_REVIEWER_BRIEF.md`. PASS
   needs 8 or more on both scores; one revise round (a spec subagent applies
   only the reviewer's fixes, then re-batch; a GHL revise that adds a tag, field,
   custom value or pipeline reruns ghl_prereqs (dry run, then --apply) before
   re-batching), a second REVISE goes to Lorenzo.
9. He loads one at a time with `./job <partial>` (n8n or Make, warms n8n),
   `./job <partial> flow` (chart) or `./job <partial> ghl` (import files to
   `~/Desktop/GHL-Imports/`, imported with the Backup & Audit extension).
10. After he records: `cd <tool root> && python3 -m upwork_gen.finalize <job dir> --loom ...`
   fills the proposal and logs the row in `proposals.csv`.
11. Weekly: outcome sync per SKILL.md "After he records" and `OUTCOMES.md`.

Props by post type: n8n canvas (default), Make blueprint (client names Make),
GoHighLevel import JSON (GHL posts), Excalidraw chart (audits,
setup/infrastructure, methods, Zapier).
