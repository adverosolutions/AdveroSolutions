# Runbook: Instantly cold-email copy from the one Google Doc

Code and details: `changesets/instantly_copy/README.md`. All commands from `Agentic Worklfows/`.

1. **Export.** Read the doc back as Drive text/plain (`download_file_content`, file
   `1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U`, `exportMimeType=text/plain`). The connector
   answers base64 inside JSON: save that to a file, decode the base64 to bytes, and write them
   unchanged to `tools/template_doc/exports/<UTC stamp>.txt`. **Keep this file**: the dry-run and the
   apply verify the staged folder against it by sha256 and refuse if it is moved or changed.
2. **Route.** Run the doc router over the same export for the engine templates:
   `python3 tools/template_doc/route_doc.py tools/template_doc/exports/<stamp>.txt`.
   Only the `instantly.*` blocks come here. For every Instantly edit, note the router's `also_in`
   list: other copies of the edited sentence elsewhere in the doc (for example the step-2 line
   "Worth a quick 15 minute call? ..." in all six campaigns). This build propagates only whole
   shared blocks (the step-1 subjects), not sentences repeated inside different bodies.
3. **Build (offline).**
   `python3 changesets/instantly_copy/build_from_doc.py tools/template_doc/exports/<stamp>.txt`
   Exit 1 lists every problem and writes nothing: tell Lorenzo exactly which block and rule
   (dash or `--`, "!", `{first_name}`, a variable inside a spin, a note or a doc layout line inside
   an email, a variable the campaign lacks, a deleted step, a subject on step 2, a dollar figure or
   any new "N days/weeks/months/years" not in offers.md, two copies of a shared subject edited
   differently). Do not change his text;
   he fixes it in the doc and you export again. "No Instantly changes" means there is nothing to push;
   quote-only edits are listed and dropped. An edit to one step-1 subject is staged for all six
   campaigns (it is one shared sentence).
4. **Dry-run.**
   `python3 changesets/instantly_copy/apply_instantly_copy.py --staged changesets/instantly_copy/staged/<stamp>`
   It first verifies the staged folder (exit 1, no request, if it does not rebuild from the export),
   then GETs each edited campaign. A `REFUSED: live no longer matches ...` line means Instantly was
   edited after the doc was made: show Lorenzo the drift lines and make a fresh doc; never force it.
5. **Show Lorenzo.** Per campaign: the plain-text diff (live -> target), the warnings (curly quotes,
   `{{ firstName }}` with spaces, `[first_name]` brackets, removed `{{variables}}`, `v_disabled`
   variants), any "formatting-only change" label, every "NOT EDITED IN THIS CAMPAIGN'S BLOCK" note
   (a shared subject edited in one niche reaches the other niches' leads), the campaign names, and
   that only the edited variants change. Show him the router's `also_in` list from step 2 too, so he
   can decide whether the other copies of an edited sentence should change as well. Also tell him:
   - links, bold and other formatting typed in the doc are not carried over (the export is plain text);
   - a new step-1 subject reaches leads already mid-sequence too: their step 2 replies in the thread
     of the subject they got, so a subject change mid-campaign can look like a new conversation;
   - applying the Phase 0 change-set later overwrites these edits with Phase 0's copy.
   The dry-run copy is under `.tmp/changeset_dryruns/instantly_copy/`.
6. **Apply, only after he said "done" on the doc and then, separately, "go live".** He runs it from
   his own terminal, one campaign at a time:
   `MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_copy/apply_instantly_copy.py --staged DIR --apply --campaign <key>`
   It shows the diff, asks him to type the campaign key, re-reads live, and only then writes the
   backup and sends. Expect `PATCH landed and was verified` and a rollback point
   `changesets/backups/instantly_copy_<campaign_id>_<ts>.json`. A re-run on an applied campaign
   sends nothing. Check the campaign in the Instantly UI afterwards.
7. **Exit 3** (API error, or `PATCH ... NOT verified`): do not re-run blindly. The before-image is
   kept as the rollback point named in the output (outcome `landed_after_error`,
   `unchanged_at_reread`, `unknown_after_error` or `acknowledged_unverified`). Open the campaign in
   the Instantly UI and compare with the diff; re-run the dry-run: `live already equals the target`
   means it landed, a clean diff means it did not and the apply can be repeated, drift means stop and
   ask Lorenzo. Restore with step 9 if the result is wrong. After a retry there are TWO rollback
   points for the campaign; restore from the newest one whose `_rollback_point.outcome` is
   `landed_verified` (the other outcomes are `landed_after_error`, `unchanged_at_reread`,
   `unknown_after_error`, `acknowledged_unverified`).
8. **After an apply, the next doc** must be built from a fresh snapshot of the campaigns
   (`tools/template_doc/build.py` reads the 2026-09-21 snapshot today). Otherwise every re-edit of an
   applied campaign shows as drift, because live no longer equals the old baseline.
9. **Restore** (if the new copy must come off):
   `MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_copy/apply_instantly_copy.py --apply --restore changesets/backups/instantly_copy_<campaign_id>_<ts>.json --campaign <key>`

Exit codes: 0 ok, 1 invalid or drift, 2 live write refused, 3 API error / unverified.
