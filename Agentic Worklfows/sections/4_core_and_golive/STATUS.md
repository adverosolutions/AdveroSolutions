# Section 4 status

**2026-09-23 (split day):** the core engine, template gate (CT3) and approval pages are committed and tested (clean checkout: 11,635 passed, 2 path-only failures, see README). The one Google Doc was uploaded and verified (379 blocks). Its tooling is now in `tools/template_doc/` (the self-test passes from there). Nothing is approved, deployed or live. The apply path from the doc to the system is not built.

## Lorenzo's doc edits so far (export 2026-09-23 18:15Z)
Export saved in `tools/template_doc/exports/2026-09-23T1815Z.txt`. Diff against `manifest.json`: 2 blocks changed, 2 deleted, 0 unknown; the other 375 match the upload (whitespace and quote cosmetics only). All four are section 1's cadence emails, handed to the section 1 chat on 2026-09-23. Nothing here is approved yet; his "done" on the doc is what approves.
- `cadence.d1`: new body "The time slots from yesterday got filled. Here are 2 more, let me know if they work: {slots}." The `{booking_url}` line is gone.
- `cadence.d2`: note to Claude on the subject line: the research line must tie back into the offer; the email is essentially "here's why I think this call is important". New body ends "...how this would run for {company}.Think this would really benefit {company name} let me know when a good time is to get a call on the books." `{slots}` and `{booking_url}` are gone. `{company name}` is not a real placeholder; section 1 confirms the wording with him.
- `cadence.d1/no_slots` and `cadence.d2/no_slots`: deleted.

## Done
- **Suite green in worktrees (2026-09-23).** `build_schedules.py --check` now normalises the checkout root, so it passes from any checkout and still fails on real staleness or a third root; write mode is byte-identical. The Apify niche filter files (`Coding/lead-scrape-2026/niches/*.json`, filter settings only) are now in git. The doc tooling has pytest tests (`tools/template_doc/tests`, in `pytest.ini`). Worktree full suite: 11,650 passed, 0 failed.
- **Routing report (2026-09-23).** `python3 tools/template_doc/route_doc.py <export.txt>` says, for every changed, deleted or new block, which section owns it and which file holds its text (with overrides where the manifest `source` is not where the text lives: `cadence.*/no_slots` in `cadence.py` `NO_SLOTS_BODIES`, case studies in `config/offers.md`, show-rate pre-read bodies in their prompt files). It flags invalid placeholders, wrong placeholder style, stray braces, and pulls out notes Lorenzo left for Claude. An export with no tags exits 2.
- **Small items (2026-09-23).** The resume page's POST gives the same neutral 403 for an unknown lead as for a bad link (no store key echoed). `GATE_RULES_VERSION` has a pin test (`services/reply_engine/tests/test_gate_rules_version.py`): any edit to `template_gate.py` needs a new digest recorded, and a rule change needs the version bumped. The top-level `requirements.txt` now pins the engine's anthropic 0.92.0, httpx 0.28.1, pydantic 2.12.5, and modal 1.2.6 (the installed version); `changesets/tests/test_requirements_agree.py` keeps shared pins equal.
- **The two cadence.py items** (company in public pushes, uncapped Resume reminder) were fixed by section 1 (5c02a40, on main); `runbooks/reply_engine_alerts.md` now describes both.

## Next
1. Build the rest of the apply path (in review): `changesets/instantly_copy/` (doc edits to a dry-runnable Instantly PATCH), `tools/template_doc/record_doc_approvals.py` (approvals after "done").

## Parked polish (reviewed, optional)
- `build_schedules.py`: a committed file already holding `<BASE_DIR>` would pass `--check`; the main-folder path is hard-coded (fine while the repo stays on the Desktop); writing from a worktree gives no warning that worktree paths went into the files.
- `tools/template_doc/tests/conftest.py` puts the tool folder first on sys.path (`build` is a generic name); appending would be safer.
- `route_doc.py`: the 8 `booking.counter.*` / `booking.slot_already_taken` blocks include draft.py's shared `BOOKING_LINE` ("Or if it's easier, grab a time here: ..."); they route to `booking.py`, but an edit to that one sentence belongs in `draft.py` (section 1) and changes the first replies too. A note on those tags would help. Also parked: a copy line starting "Note" is treated as a note for Claude; deleted entries omit the flag keys in JSON; a `--json`/`--md` write failure prints a traceback; `{{}}` counts as a valid Instantly tag.
- Pin test message (`test_gate_rules_version.py`): it prints the current version, so after a rule change someone could record the digest without bumping. Better: split the "file changed" and "version bumped" cases.
- `test_requirements_agree.py` reads only `==` pins: a top-level `pkg<x` for an engine package, or a pin with an environment marker, slips through.
- The booking-cancelled page (`app.py` ~:2794) still says "Unknown lead" with the key; not a leak (it sits behind a signed link built from that key), but a neutral page would be consistent.

## Waiting on Lorenzo
The go-live items in README step 4 (all his own actions). "done" on the doc and "go live" are his words to give.
- FYI (not ours to fix; `execution/` is off-limits): `execution/modal_mass_scraper.py` uses `modal.Mount`, which modal 1.2.6 (installed) no longer has, so it does not import. The live `modal_lead_sync.py` imports fine.
