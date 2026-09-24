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
