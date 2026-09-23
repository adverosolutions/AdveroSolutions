#!/usr/bin/env python3
"""Proof that the preflight passed on THIS code, recently (D1 round 3, defect 5).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/preflight_stamp.py check      # exit 0 only for a fresh stamp on this code
    python3 changesets/deploy/preflight_stamp.py show

There is no command that writes a stamp. Only ``install_schedules.sh
--preflight`` writes one, as its last step, after checks 1 to 5 have passed
(``set -e`` stops it at the first failure), through
``_write_after_preflight``.

``install_schedules.sh --preflight`` writes .tmp/deploy/preflight_ok.json when
all five automated checks pass: the time, the deploy tiers, and a SHA-256 of
every file the Modal image mounts (modal_app.LOCAL_DIRS with its IGNORE
patterns, plus the image requirements). The live flip needs it BEFORE the
live secret exists:

* ``modal_secret.py --mode live --create`` refuses without a stamp no older
  than MAX_AGE_MINUTES whose fingerprint matches the code on disk now;
* ``install_schedules.sh --deploy live`` checks the same stamp before it asks
  anything, and runs no preflight of its own: between the live secret and the
  ``modal deploy`` nothing slow or fallible runs.

A stamp from other code (anything edited since the preflight) or an older one
is refused: run the preflight again. Reads files, writes only the stamp.
Python 3.9.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common

STAMP_NAME = "preflight_ok.json"
MAX_AGE_MINUTES = 60


def stamp_path() -> str:
    return os.path.join(common.deploy_tmp(), STAMP_NAME)


def _ignored(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def fingerprint() -> Dict[str, Any]:
    """SHA-256 over every file the image mounts, in a stable order."""
    from services.reply_engine import modal_app

    digest = hashlib.sha256()
    count = 0
    sources = sorted(modal_app.LOCAL_DIRS.items())
    extra = [str(modal_app.REQUIREMENTS)]
    for local, remote in sources:
        if not os.path.isdir(local):
            continue
        for root, dirs, files in os.walk(local):
            dirs[:] = sorted(d for d in dirs if not _ignored(d, modal_app.IGNORE))
            for name in sorted(files):
                if _ignored(name, modal_app.IGNORE):
                    continue
                path = os.path.join(root, name)
                rel = remote + "/" + os.path.relpath(path, local).replace(os.sep, "/")
                digest.update(rel.encode("utf-8") + b"\0")
                with open(path, "rb") as fh:
                    digest.update(hashlib.sha256(fh.read()).digest())
                count += 1
    for path in extra:
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                digest.update(b"requirements\0" + hashlib.sha256(fh.read()).digest())
    return {"sha256": digest.hexdigest(), "files": count, "deploy_tiers": list(modal_app.DEPLOY_TIERS)}


def _write_after_preflight(now: Optional[datetime] = None, path: Optional[str] = None) -> Dict[str, Any]:
    """Write the stamp. Called ONLY by install_schedules.sh's preflight, after
    checks 1 to 5 passed; not a command, and nothing else calls it."""
    record = dict(fingerprint(), ts_utc=(now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat(),
                  written_by="install_schedules.sh --preflight, after checks 1-5")
    with open(path or stamp_path(), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
    return record


def read(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        with open(path or stamp_path(), "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def problems(now: Optional[datetime] = None, path: Optional[str] = None,
             max_age_minutes: int = MAX_AGE_MINUTES) -> List[str]:
    """Why the stamp does not cover a live flip now (empty: it does)."""
    from changesets.deploy.watch_report import parse_ts

    rec = read(path)
    if rec is None:
        return ["no preflight stamp (.tmp/deploy/%s): run bash changesets/schedules/install_schedules.sh "
                "--preflight first" % STAMP_NAME]
    now = now or datetime.now(timezone.utc)
    out = []  # type: List[str]
    at = parse_ts(rec.get("ts_utc"))
    if at is None or now - at > timedelta(minutes=max_age_minutes) or at - now > timedelta(minutes=5):
        out.append("the preflight stamp is from %s, not within the last %d minutes: run the preflight again"
                   % (rec.get("ts_utc"), max_age_minutes))
    current = fingerprint()
    if rec.get("sha256") != current["sha256"]:
        out.append("the code the image would carry changed since the preflight (%d files now): run the "
                   "preflight again" % current["files"])
    if list(rec.get("deploy_tiers") or []) != current["deploy_tiers"]:
        out.append("the preflight ran for DEPLOY_TIERS=%s, this deploy is %s"
                   % (",".join(rec.get("deploy_tiers") or []), ",".join(current["deploy_tiers"])))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("check", "show"),
                        help="check or show the stamp; only install_schedules.sh --preflight writes one")
    args = parser.parse_args(argv)
    if args.action == "show":
        print(json.dumps(read() or {}, indent=2, sort_keys=True))
        return 0
    found = problems()
    if found:
        print("REFUSED: the live flip needs a passing preflight on this code first:")
        for line in found:
            print("  - " + line)
        return 1
    print("preflight stamp OK: %s" % (read() or {}).get("ts_utc"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
