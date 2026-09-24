"""Build the one doc again from the CURRENT code, into a folder of your choice.

record_doc_approvals.py compares Lorenzo's doc against this fresh build, not
against the committed manifest.json: an id can only be approved from the doc
when the doc still shows exactly what the code sends today.

Steps (read-only apart from the output folder):
1. Render the review markdown in-process with the engine's own catalogue
   (services/reply_engine/template_approvals.render_catalogue_markdown, the
   same function jobs/approve_templates.py --export uses; it writes no
   Job_Log row). The approvals status lines in it are read from a file that
   does not exist, so the export never depends on the registry.
2. Run build.py on it (a subprocess, --export/--out-dir) so the HTML and
   manifest are made by the same code that made the doc.
3. Check that every approvable id's hash in the manifest is the hash of the
   catalogue entries the export was rendered from, and that the manifest's
   fingerprint is the fingerprint of its own blocks and lines.

    python3 fresh_manifest.py OUT_DIR
"""
import hashlib
import io
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT = os.path.dirname(os.path.dirname(HERE))  # tools/template_doc -> Agentic Worklfows
BUILD = os.path.join(HERE, "build.py")
EXPORT_NAME = "templates_export_fresh.md"
NO_APPROVALS_NAME = "no_approvals_file.json"

for _p in (HERE, CODE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doc_areas  # noqa: E402


class FreshBuildError(RuntimeError):
    """The doc could not be rebuilt from the current code (fail closed)."""


def build_fresh(out_dir: str, python: Optional[str] = None) -> Dict[str, Any]:
    """Export and build into out_dir. Returns {"manifest", "export_path",
    "export_sha256", "html_path", "manifest_path", "hashes"} where hashes maps
    every approvable id to the catalogue sha256 the export was rendered from,
    plus "fingerprint"."""
    from services.reply_engine import template_approvals as ta

    out_dir = os.path.abspath(out_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    no_file = os.path.join(out_dir, NO_APPROVALS_NAME)
    if os.path.exists(no_file):
        raise FreshBuildError("%s must not exist (it stands for an empty registry)" % no_file)
    try:
        entries = ta.catalogue()
        md = ta.render_catalogue_markdown(entries, path=no_file)
    except Exception as exc:  # noqa: BLE001 - any failure refuses the whole run
        raise FreshBuildError("could not render the template catalogue: %s" % exc)
    hashes = dict((e["id"], e["sha256"]) for e in entries if e.get("approvable"))
    export_path = os.path.join(out_dir, EXPORT_NAME)
    with io.open(export_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(export_path, "rb") as fh:
        export_sha = hashlib.sha256(fh.read()).hexdigest()

    proc = subprocess.run([python or sys.executable, BUILD, "--export", export_path, "--out-dir", out_dir],
                          cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    if proc.returncode != 0:
        raise FreshBuildError("build.py failed (exit %d):\n%s" % (proc.returncode, proc.stdout[-3000:]))
    manifest_path = os.path.join(out_dir, "manifest.json")
    try:
        with io.open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise FreshBuildError("build.py wrote no readable manifest: %s" % exc)
    if manifest.get("export_sha256") != export_sha:
        raise FreshBuildError("the fresh manifest was not built from the fresh export")

    problems = []
    seen = set()
    for b in manifest.get("blocks", []):
        tid = b.get("template_id")
        if not tid:
            continue
        seen.add(tid)
        if tid not in hashes:
            problems.append("%s: in the manifest but not an approvable catalogue id" % b.get("tag"))
        elif b.get("sha256") != hashes[tid]:
            problems.append("%s: manifest hash differs from the catalogue it was rendered from" % b.get("tag"))
    missing = sorted(set(hashes) - seen)
    if missing:
        problems.append("approvable ids with no block in the fresh doc: %s" % ", ".join(missing))
    fp = manifest.get("fingerprint")
    if not fp or doc_areas.fingerprint(manifest.get("blocks", []), manifest.get("visible", [])) != fp:
        problems.append("the fresh manifest's fingerprint does not match its blocks and lines")
    if problems:
        raise FreshBuildError("the fresh build does not match the catalogue: " + "; ".join(problems[:10]))
    return {"manifest": manifest, "export_path": export_path, "export_sha256": export_sha, "fingerprint": fp,
            "html_path": os.path.join(out_dir, "advero_all_emails.html"), "manifest_path": manifest_path,
            "hashes": hashes}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: fresh_manifest.py OUT_DIR")
    res = build_fresh(sys.argv[1])
    print("wrote %s and %s (%d approvable ids)" % (res["html_path"], res["manifest_path"], len(res["hashes"])))
