One-doc template editing (2026-09-23). Owned by section 4 (see sections/README.md).
Google Doc: 1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U ("Advero emails: edit here (every email, one doc)")
Drive folder: 1yww1rrk0blgKnD98CkIY95XPEsaDZQ9c (older doc versions there are renamed OLD).
manifest.json = the text of every tagged block as uploaded (379 blocks; baseline for diffs).
Read back: Drive download_file_content(fileId, exportMimeType=text/plain) -> base64 JSON saved to a file -> decode to a .txt
           For "done" also exportMimeType=text/html -> a .html: record_doc_approvals.py --write needs it as --html
           (it refuses strikethrough, highlights and colours the build did not set, which the .txt drops; grey only
           where the build made it grey). Suggestions are in neither export: reading the doc's comments and
           suggestions (--checked-comments) is the control for them.
Diff:      python3 diff_doc.py <export.txt> --manifest manifest.json
Route:     python3 route_doc.py <export.txt> [--json out.json] [--md out.md]   (which section and file owns each changed/deleted/new block, plus flags)
Self-test: python3 selftest.py   (paths are relative to this folder; works in any checkout or worktree)
drive_export.txt = Drive's own export right after upload (diffs empty against manifest).
The Drive connector cannot edit a doc's text in place (update_file changes title and folder only),
so a rebuilt doc is a NEW doc: build.py -> create_file (HTML -> Google Doc) -> rename the old one OLD.
When Lorenzo says "done", everything in the doc counts as approved; "go live" is a separate yes.
Copied from .tmp/template_doc/ on 2026-09-23 so it is in git; the .tmp copy is no longer the source.

Builds and uploads (from 2026-09-23, record_doc_approvals.py):
Build:     python3 build.py --export <export.md>   -> builds/<fingerprint>/advero_all_emails.html + manifest.json
           (never the top-level files). For the current code, make the export first:
             python3 fresh_manifest.py <tmp dir>      (renders the catalogue to <tmp dir>/templates_export_fresh.md
                                                       and test-builds it there)
             python3 build.py --export <tmp dir>/templates_export_fresh.md
           Without --export, build.py reads templates_export_final.md: the export the doc in Drive was built from
           (the old cadence.d ids), kept so that doc can still be diffed.
           The layout follows the catalogue (services/reply_engine/template_approvals.py): every approvable id, in the
           catalogue's order, by section; each follow-up email with its spliced lines under it. No id or count is
           written in the code, so ids the catalogue adds or drops need no change here; the one count check is that
           the doc holds every approvable id exactly once (build.py stops otherwise). A catalogue entry that is not
           approvable (cadence.e2.research_line, written by AI for each lead) shows only as a read-only note on its
           email; "done" never approves it.
           The fingerprint hashes every block and every line outside the blocks; the doc shows it as
           "Doc build: <fingerprint> (tag: X-BUILD)" at the end of the top section.
           Versions are shown as notes quoting the main-text lines they replace or leave out (doc_rules.py). The
           build reads every template back out of the doc's text (doc_areas.DocReader) and writes nothing unless
           every part comes back exactly.
           builds/ is committed, not ignored: record_doc_approvals.py needs builds/<fingerprint>/manifest.json of
           the doc Lorenzo said "done" on, in whichever checkout runs it.
           The doc's words on sending are doc_rules.py (DONE_SENTENCE, SENDING_SENTENCE, HELD_INTRO and the section
           notes), Grok's allow list of 2026-10-06 (agents/grokbot/onboarding/ask_opus.py): only the main text of the
           five AI agents first replies, of E1 to E10 with their lines, and of the Locked in confirmation (after the
           GHL booking exists at exactly that time) send on their own after "done" and "go live"; every version under
           any template, every booking.counter.*, slot_already_taken, already_booked, show-rate, no-show, nurture and
           the older offers' first replies ("Not approved yet") are drafts. The legacy engine's own first-reply path
           stays locked (approval.py).
Upload and promote (only when a new doc goes to Lorenzo):
  1. create_file the build's HTML as a new Google Doc; rename the old doc OLD.
  2. Add {"doc_id", "title", "fingerprint", "build": "builds/<fingerprint>/", "uploaded_at"} to uploads.json.
  3. Export the new doc as text right away and check it: python3 diff_doc.py <export.txt> --manifest builds/<fingerprint>/manifest.json
     must print nothing changed, and record_doc_approvals.py <export.txt> (dry run) must list no area changes.
  4. Promote: copy builds/<fingerprint>/advero_all_emails.html and manifest.json over the top-level files, save the
     export as drive_export.txt, run selftest.py, and commit builds/<fingerprint>/, uploads.json and the promoted files.
  The top-level manifest.json / advero_all_emails.html are the build of the doc in Drive; the other tools default to them.
  The doc in Drive today (1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U) predates fingerprints: it can be diffed and
  routed, but record_doc_approvals.py --write refuses it until a fingerprinted build is uploaded.
Approve:   after Lorenzo says "done": runbooks/template_approvals.md, "From the Google Doc".
