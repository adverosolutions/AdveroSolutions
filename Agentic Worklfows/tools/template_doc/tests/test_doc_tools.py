"""The one-doc tooling stays working: its own self-test passes, and the first
real export of Lorenzo's edits (2026-09-23 18:15Z) diffs to exactly what he
changed."""
import io
import os
import subprocess
import sys

import diff_doc
from parse_doc import parse_with_info

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(TOOL_DIR, "manifest.json")
UPLOAD_EXPORT = os.path.join(TOOL_DIR, "drive_export.txt")
FIRST_EDITS = os.path.join(TOOL_DIR, "exports", "2026-09-23T1815Z.txt")


def _diff(export_path):
    with io.open(export_path, encoding="utf-8") as fh:
        info = parse_with_info(fh.read())
    return diff_doc.diff(info, diff_doc.load_manifest(MANIFEST))


def test_selftest_passes():
    proc = subprocess.run([sys.executable, os.path.join(TOOL_DIR, "selftest.py")],
                          cwd=TOOL_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert "all checks passed" in proc.stdout


def test_the_upload_export_diffs_clean():
    assert diff_doc.is_clean(_diff(UPLOAD_EXPORT))


def test_lorenzos_first_edits_are_exactly_the_two_cadence_emails():
    report = _diff(FIRST_EDITS)
    assert sorted(c["tag"] for c in report["changed"]) == ["cadence.d1", "cadence.d2"]
    assert sorted(report["missing"]) == ["cadence.d1/no_slots", "cadence.d2/no_slots"]
    assert report["unknown"] == []
