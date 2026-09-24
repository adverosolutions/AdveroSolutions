One-doc template editing (2026-09-23). Owned by section 5 (see sections/README.md).
Google Doc: 1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U ("Advero emails: edit here (every email, one doc)")
Drive folder: 1yww1rrk0blgKnD98CkIY95XPEsaDZQ9c (older doc versions there are renamed OLD).
manifest.json = the text of every tagged block as uploaded (379 blocks; baseline for diffs).
Read back: Drive download_file_content(fileId, exportMimeType=text/plain) -> base64 JSON saved to a file -> decode to a .txt
Diff:      python3 diff_doc.py <export.txt> --manifest manifest.json
Route:     python3 route_doc.py <export.txt> [--json out.json] [--md out.md]   (which section and file owns each changed/deleted/new block, plus flags)
Self-test: python3 selftest.py   (paths are relative to this folder; works in any checkout or worktree)
drive_export.txt = Drive's own export right after upload (diffs empty against manifest).
The Drive connector cannot edit a doc's text in place (update_file changes title and folder only),
so a rebuilt doc is a NEW doc: build.py -> create_file (HTML -> Google Doc) -> rename the old one OLD.
When Lorenzo says "done", everything in the doc counts as approved; "go live" is a separate yes.
Copied from .tmp/template_doc/ on 2026-09-23 so it is in git; the .tmp copy is no longer the source.

Builds and uploads (from 2026-09-23, record_doc_approvals.py):
Build:     python3 build.py   -> builds/<fingerprint>/advero_all_emails.html + manifest.json (never the top-level files).
           The fingerprint hashes every block and every line outside the blocks; the doc shows it as
           "Doc build: <fingerprint> (tag: X-BUILD)" at the end of the top section.
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
