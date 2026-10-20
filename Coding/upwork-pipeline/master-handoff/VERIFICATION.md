# Handoff package verification — 20 October 2026

These are main-session checks of documentation and portability, not an independent
Astra audit of the new handbook and not a pass by another model. Existing exact
Astra template reviews are copied without expanding their approval scope.

Completed checks:

- All root handbook HTML links/images resolve to included local files or explicit
  external source URLs; the initial generated root pages had 92 local references.
- All 43 curated main UI images and eight supplemental assets with saved
  provenance exist and match the recorded hashes.
- The ZIP was extracted into a disposable directory. Its offline verifier passed.
- Using only the extracted compiler/font/specs, all four native fixtures rebuilt
  to exactly the reviewed standalone page SHA-256 identities.
- The start page, master, operations, UI guide, new-model test and locked-proposal
  HTML rendered at 1440px and 390px without whole-page horizontal overflow.
- The isolated browser reported no page errors or HTTP(S) asset requests.
  All four start-page result thumbnails loaded; the start page was inspected visually.
- Explicit exclusions were checked: no real job-folder tree, live `.local` queue
  tree, `.env`, credentials/token file or registry was included in the snapshot.
- The builder’s own manifest verifier checks every exported file’s SHA-256 and
  flags missing, changed and unexpected files. It does not certify factual
  correctness or native production readiness.
- The documentation was self-reviewed against the saved current operating policy,
  final whole-walkthrough review, schema/build behavior and locked proposal source.

No real saved jobs were fetched, no queue operation was run, no Loom was recorded,
no proposal was finalized/submitted, and no live app/account was changed by this
handbook export. The unknown next model has not yet been tested; use the supplied
small isolated assessment rather than assuming it can follow the instructions.

Rebuild with `build_handbook.py` after canonical changes and run the exported
`verify_package.py`. The manifest contains the source commit, working-tree state,
snapshot date, candidate page identities and full inventory. The Git source and
local ZIP complement each other; neither is automatic cloud sync of runtime state.
