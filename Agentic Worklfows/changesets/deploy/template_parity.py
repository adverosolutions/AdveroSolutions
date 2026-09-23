#!/usr/bin/env python3
"""Template catalogue parity: the hashes the deployed app compares against (CT3).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/template_parity.py --write              # refresh config/template_catalogue_hashes.json
    python3 changesets/deploy/template_parity.py --check              # exit 1 and list the ids that differ
    python3 changesets/deploy/template_parity.py --report-unapproved  # ladder ids not approved at their current text

--report-unapproved prints three header lines, parsed by install_schedules.sh
step 8, then the ids:

    UNAPPROVED LADDER IDS: <n>      approvable ladder ids not approved at their current text
    UNEXTRACTABLE LADDER IDS: <m>   ladder ids the catalogue could not render (an extractor failed)
    KILL SWITCH: on|off             as this laptop sees it (AUTO_SEND_TEMPLATES and the approvals file)

It exits 0 whatever the counts, and 2 when the approvals file cannot be read.

Each --write rewrites config/template_catalogue_hashes.json. The first one
creates it as a new, untracked file; once it is committed, every preflight
leaves it changed in git when the catalogue changed (and its generated_at
line changes every time).

The reference file holds the catalogue digest and the id -> sha256 map of every
approvable template, plus the python, pytz and pydantic versions it was built
with. On Modal (Python 3.11) services/reply_engine/template_gate.parity_status
rebuilds the catalogue and compares its digest with this file, which reaches
the container through the config/ mount. Any difference, a missing file or an
error turns template auto-send off everywhere (every email becomes a card or a
hold) and sends one urgent alert a day.

``install_schedules.sh --preflight`` runs --write, then --check (step 7), then
--report-unapproved (step 8). Lorenzo runs it, not an agent.

Ids and hashes only: nothing here prints or writes template text. This script
never writes config/approved_templates.json; approvals only come from
jobs/approve_templates.py in Lorenzo's own terminal. Python 3.9.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from changesets.deploy import common  # noqa: F401 - puts the repo root on sys.path
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common  # noqa: F401

from services.reply_engine import template_approvals as ta  # noqa: E402
from services.reply_engine import template_gate as gate  # noqa: E402

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_REFUSED = 2
UNAPPROVED_HEADER = "UNAPPROVED LADDER IDS: %d"
UNEXTRACTABLE_HEADER = "UNEXTRACTABLE LADDER IDS: %d"
KILL_SWITCH_HEADER = "KILL SWITCH: %s"


class Refused(Exception):
    pass


def _in_temp_dir(p: Path) -> bool:
    try:
        p.resolve().relative_to(Path(tempfile.gettempdir()).resolve())
        return True
    except ValueError:
        return False


def _reference_path(path: Optional[str]) -> Path:
    """The reference file. The hidden --reference flag (tests) may only name
    a file called template_catalogue_hashes.json, or a file inside the
    system temp directory; and never the approvals registry."""
    p = Path(path) if path else Path(gate.PARITY_REFERENCE_PATH)
    approvals = Path(ta.APPROVALS_PATH)
    if p.name == approvals.name or p.resolve() == approvals.resolve():
        raise Refused("refusing to use %s as the parity reference: that is the approvals registry" % p)
    if path and p.name != gate.PARITY_REFERENCE_NAME and not _in_temp_dir(p):
        raise Refused("refusing to use %s as the parity reference: only a file named %s, or one in a temp "
                      "directory" % (p, gate.PARITY_REFERENCE_NAME))
    return p


def write_reference(path: Optional[str] = None) -> Dict[str, Any]:
    """Build the catalogue and write the reference atomically. Returns it."""
    p = _reference_path(path)
    rec = gate.reference_record()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rec, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".%s." % p.name, suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(p))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return rec


def compare(path: Optional[str] = None) -> Dict[str, Any]:
    """{"ok", "digest", "reference_digest", "ids" (differing), "reference"}."""
    p = _reference_path(path)
    digest, current = gate.catalogue_digest()
    if not p.exists():
        return {"ok": False, "missing": True, "digest": digest, "reference_digest": None, "ids": sorted(current),
                "reference": None}
    ref = json.loads(p.read_text(encoding="utf-8"))
    ref_ids = ref.get("ids") if isinstance(ref, dict) else None
    ref_digest = ref.get("digest") if isinstance(ref, dict) else None
    if not isinstance(ref_ids, dict) or not isinstance(ref_digest, str):
        raise Refused("%s has no digest or ids; run --write" % p)
    differing = sorted(tid for tid in set(ref_ids) | set(current) if ref_ids.get(tid) != current.get(tid))
    return {"ok": digest == ref_digest and not differing, "missing": False, "digest": digest,
            "reference_digest": ref_digest, "ids": differing, "reference": ref}


def unapproved_ladder_ids(approvals_path: Optional[str] = None) -> List[str]:
    index = ta.catalogue_index()
    approvals = ta.load_approvals(approvals_path)
    return [tid for tid in gate.ladder_ids(index)
            if ta.status(tid, entries=index, approvals=approvals) != ta.STATUS_APPROVED]


def unextractable_ladder_ids() -> List[str]:
    return gate.unextractable_ladder_ids(ta.catalogue_index())


def cmd_write(path: Optional[str]) -> int:
    rec = write_reference(path)
    print("wrote %s: %d ids, digest %s (python %s, pytz %s, pydantic %s)"
          % (_reference_path(path), len(rec["ids"]), rec["digest"][:16], rec["python"], rec["pytz"], rec["pydantic"]))
    return EXIT_OK


def cmd_check(path: Optional[str]) -> int:
    res = compare(path)
    if res["missing"]:
        print("MISMATCH: no reference file at %s; run --write" % _reference_path(path))
        return EXIT_MISMATCH
    if res["ok"]:
        print("OK: %d ids, digest %s" % (len(res["reference"]["ids"]), res["digest"][:16]))
        return EXIT_OK
    ref = res["reference"] or {}
    print("MISMATCH: %d id(s) differ (digest now %s, reference %s built with python %s)"
          % (len(res["ids"]), res["digest"][:16], (res["reference_digest"] or "")[:16], ref.get("python")))
    for tid in res["ids"]:
        print("  %s" % tid)
    return EXIT_MISMATCH


def cmd_report_unapproved(approvals_path: Optional[str]) -> int:
    ids = unapproved_ladder_ids(approvals_path)
    broken = unextractable_ladder_ids()
    kill = ta.kill_switch_on(approvals_path)
    # The three header lines are parsed by install_schedules.sh (step 8).
    print(UNAPPROVED_HEADER % len(ids))
    print(UNEXTRACTABLE_HEADER % len(broken))
    print(KILL_SWITCH_HEADER % ("on" if kill else "off"))
    if ids:
        print("Not approved at their current text:")
        for tid in ids:
            print("  %s" % tid)
        print("Messages that use these are held until approved: python3 jobs/approve_templates.py --export "
              ".tmp/templates_for_approval.md, review, then --approve-all-shown from your own terminal.")
    if broken:
        print("Could not be rendered (a code problem; approving cannot fix it):")
        for tid in broken:
            print("  %s" % tid)
    if kill:
        print("The kill switch is on: every cadence, show-rate and no-show message is held, approved or not.")
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the reference hashes file")
    mode.add_argument("--check", action="store_true",
                      help="compare the catalogue with the reference; exit 1 on a difference")
    mode.add_argument("--report-unapproved", action="store_true",
                      help="list ladder ids (cadence, show_rate, no_show) not approved at their current text")
    parser.add_argument("--reference", help=argparse.SUPPRESS)       # tests: a tmp reference path
    parser.add_argument("--approvals-file", help=argparse.SUPPRESS)  # tests: a tmp approvals path (read only)
    args = parser.parse_args(argv)
    try:
        if args.write:
            return cmd_write(args.reference)
        if args.check:
            return cmd_check(args.reference)
        return cmd_report_unapproved(args.approvals_file)
    except Refused as exc:
        print("REFUSED: %s" % exc)
        return EXIT_REFUSED
    except ValueError as exc:  # an unreadable approvals or reference file
        print("REFUSED: %s" % exc)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
