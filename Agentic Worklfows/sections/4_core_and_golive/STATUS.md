# Section 4 status

**2026-09-23 (split day):** the core engine, template gate (CT3) and approval pages are committed and tested (clean checkout: 11,635 passed, 2 path-only failures, see README). The one Google Doc was uploaded and verified (379 blocks). Its tooling is now in `tools/template_doc/` (the self-test passes from there). Nothing is approved, deployed or live. The apply path from the doc to the system is not built.

## Lorenzo's doc edits so far (export 2026-09-23 18:15Z)
Export saved in `tools/template_doc/exports/2026-09-23T1815Z.txt`. Diff against `manifest.json`: 2 blocks changed, 2 deleted, 0 unknown; the other 375 match the upload (whitespace and quote cosmetics only). All four are section 1's cadence emails, handed to the section 1 chat on 2026-09-23. Nothing here is approved yet; his "done" on the doc is what approves.
- `cadence.d1`: new body "The time slots from yesterday got filled. Here are 2 more, let me know if they work: {slots}." The `{booking_url}` line is gone.
- `cadence.d2`: note to Claude on the subject line: the research line must tie back into the offer; the email is essentially "here's why I think this call is important". New body ends "...how this would run for {company}.Think this would really benefit {company name} let me know when a good time is to get a call on the books." `{slots}` and `{booking_url}` are gone. `{company name}` is not a real placeholder; section 1 confirms the wording with him.
- `cadence.d1/no_slots` and `cadence.d2/no_slots`: deleted.

## Done
- **Suite green in worktrees (2026-09-23).** `build_schedules.py --check` now normalises the checkout root, so it passes from any checkout and still fails on real staleness or a third root; write mode is byte-identical. The Apify niche filter files (`Coding/lead-scrape-2026/niches/*.json`, filter settings only) are now in git. The doc tooling has pytest tests (`tools/template_doc/tests`, in `pytest.ini`). Worktree full suite: 11,650 passed, 0 failed.

## Next
1. Build the apply path (in progress, in review): `tools/template_doc/route_doc.py` (who owns each edit), `changesets/instantly_copy/` (doc edits to a dry-runnable Instantly PATCH), `tools/template_doc/record_doc_approvals.py` (approvals after "done").
2. Small items (in review): resume-page POST leak, `GATE_RULES_VERSION` pin test, top-level `requirements.txt` pins. The two cadence.py items (company in public pushes, uncapped Resume reminder) were handed to section 1.

## Parked polish (reviewed, optional)
- `build_schedules.py`: a committed file already holding `<BASE_DIR>` would pass `--check`; the main-folder path is hard-coded (fine while the repo stays on the Desktop); writing from a worktree gives no warning that worktree paths went into the files.
- `tools/template_doc/tests/conftest.py` puts the tool folder first on sys.path (`build` is a generic name); appending would be safer.

## Waiting on Lorenzo
The go-live items in README step 4 (all his own actions). "done" on the doc and "go live" are his words to give.
