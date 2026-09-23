"""Approve cold-email templates once, so emails of that type can send without a per-email Approve.

    python3 jobs/approve_templates.py --list
    python3 jobs/approve_templates.py --show cadence.d1
    python3 jobs/approve_templates.py --export .tmp/templates_for_approval.md
    python3 jobs/approve_templates.py --approve cadence.d1 cadence.d3
    python3 jobs/approve_templates.py --approve-all-shown .tmp/templates_for_approval.md
    python3 jobs/approve_templates.py --revoke cadence.d1

--approve, --approve-all-shown and --revoke write config/approved_templates.json.
They need an interactive terminal: you type APPROVE to confirm, or pass --yes,
and --yes is refused when stdin is not a TTY (Claude's Bash tool, a pipe, cron).

Approved templates send automatically (CT3): an engine email whose text is
exactly an approved template goes out without a per-email Approve, as long as
the kill switch is off and every send check passes. Revoke an id, or set the
kill switch (runbooks/template_approvals.md), to stop them.

Every approve / revoke run writes one Job_Log row (job "approve_templates")
with the ids and hashes only, never the template text.
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

if __package__ in (None, ""):  # run as a script: make "shared"/"services" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.job_log import log_run  # noqa: E402

from services.reply_engine import template_approvals as ta  # noqa: E402

JOB = "approve_templates"
EXIT_OK = 0
EXIT_REFUSED = 1
CONFIRM_WORD = "APPROVE"
AUTO_SEND_WARNING = ("WARNING: once CT3 phase 2 is deployed, these auto-send with no card "
                     "while the kill switch is off.")


def confirm_from_tty(word: str, prompt: str) -> bool:
    """The typed word from the terminal (mirrors changesets/claude_guard).
    Refuses when stdin is not a TTY and reads the answer from /dev/tty."""
    if not sys.stdin.isatty():
        print("REFUSED: this needs an interactive terminal (stdin is not a TTY). Run it from your own terminal.")
        return False
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write("%s [type %s] " % (prompt, word))
            tty.flush()
            answer = tty.readline().strip()
    except OSError:
        print("REFUSED: no terminal (/dev/tty) to read the answer from.")
        return False
    return answer == word


def _stdin_isatty() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _gate(yes: bool, isatty: Callable[[], bool], confirm: Callable[[str, str], bool], prompt: str) -> bool:
    if not isatty():
        if yes:
            print("REFUSED: --yes is only accepted from an interactive terminal (stdin is not a TTY).")
        else:
            print("REFUSED: this needs an interactive terminal (stdin is not a TTY). Run it from your own terminal.")
        return False
    if yes:
        return True
    if not confirm(CONFIRM_WORD, prompt):
        print("Not confirmed. Nothing was written.")
        return False
    return True


def _short(h: Optional[str]) -> str:
    return (h or "")[:12]


def cmd_list(path) -> int:
    entries = ta.catalogue()
    index = ta.catalogue_index(entries)
    approvals = ta.load_approvals(path)
    print("kill switch: %s" % ("ON (auto-send off)" if ta.kill_switch_on(path) else "off"))
    width = max(len(e["id"]) for e in entries)
    kwidth = max(len(e["kind"]) for e in entries)
    for e in entries:
        st = ta.status(e["id"], entries=index, approvals=approvals)
        flag = "" if e.get("approvable") else ("  (not extractable)" if not e.get("extractable") else "  (reference)")
        print("%-*s  %-*s  %s%s" % (width, e["id"], kwidth, e["kind"], st, flag))
    print("%d templates" % len(entries))
    return EXIT_OK


def cmd_show(template_id: str, path) -> int:
    index = ta.catalogue_index()
    e = index.get(template_id)
    if e is None:
        print("unknown id: %s" % template_id)
        return EXIT_REFUSED
    print("id:        %s" % e["id"])
    print("kind:      %s" % e["kind"])
    print("status:    %s" % ta.status(template_id, entries=index, path=path))
    print("variables: %s" % (", ".join("{%s}" % v for v in e["variables"]) or "none"))
    print("source:    %s" % e["source"])
    print("sent from: %s" % e.get("hook", ""))
    if e.get("notes"):
        print("notes:     %s" % e["notes"])
    if not e.get("extractable"):
        print("not extractable: %s" % e.get("explanation", ""))
        return EXIT_OK
    print("sha256:    %s" % e["sha256"])
    if not e.get("approvable"):
        print("reference piece: not approved on its own")
    print("")
    print(e["review_text"].rstrip("\n"))
    return EXIT_OK


def cmd_export(out_path: str, path) -> int:
    md = ta.render_catalogue_markdown(path=path)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    n = len(ta.parse_exported(md))
    print("wrote %s (%d approvable templates)" % (p, n))
    return EXIT_OK


def _approve(ids: List[str], path, yes: bool, isatty, confirm, approved_by: str,
             expected=None, source_note: str = "", action: str = "approve", log_fn=log_run) -> int:
    entries = ta.catalogue_index()
    approvals = ta.load_approvals(path)
    base = {"action": action, "requested": list(ids), "approved_by": approved_by}
    try:
        plan = ta.plan_approve(ids, entries, approvals, expected=expected)
    except ta.ApprovalError as exc:
        print("REFUSED: %s" % exc)
        print("Nothing was written.")
        log_fn(JOB, "refused", dict(base, reason=str(exc)))
        return EXIT_REFUSED
    todo = [p for p in plan if p["before"] != ta.STATUS_APPROVED]
    for p in plan:
        if p["before"] == ta.STATUS_APPROVED:
            print("already approved, unchanged: %s" % p["id"])
        else:
            print("will approve: %s (sha256 %s, was %s)" % (p["id"], _short(p["sha256"]), p["before"]))
    hashes = dict((p["id"], p["sha256"]) for p in todo)
    if not todo:
        print("Nothing to change.")
        log_fn(JOB, "ok", dict(base, approved={}, unchanged=[p["id"] for p in plan]))
        return EXIT_OK
    print(ta.WIRED_NOTE)
    if isatty():
        print(AUTO_SEND_WARNING)
    if not _gate(yes, isatty, confirm, "Approve %d template(s)%s?" % (len(todo), source_note)):
        log_fn(JOB, "refused", dict(base, reason="not confirmed or no interactive terminal", would_approve=hashes))
        return EXIT_REFUSED
    new = ta.apply_approve(plan, approvals, approved_by)
    written = ta.save_approvals(new, path)
    for p in todo:
        print("approved: %s (sha256 %s, was %s)" % (p["id"], _short(p["sha256"]), p["before"]))
    print("wrote %s" % written)
    print(ta.WIRED_NOTE)
    log_fn(JOB, "ok", dict(base, approved=hashes, previous=dict((p["id"], p["before"]) for p in todo)))
    return EXIT_OK


def cmd_approve_all_shown(md_path: str, path, yes, isatty, confirm, approved_by, log_fn=log_run) -> int:
    try:
        md = Path(md_path).read_text(encoding="utf-8")
    except OSError as exc:
        print("REFUSED: cannot read %s: %s" % (md_path, exc))
        log_fn(JOB, "refused", {"action": "approve_all_shown", "file": md_path, "reason": "unreadable"})
        return EXIT_REFUSED
    # Every marker must carry its text block, the hash of the text shown must
    # equal the marker hash, and both must equal the current catalogue hash.
    # One problem refuses the whole file: Lorenzo approves what he read or nothing.
    shown, problems = ta.verify_exported(md)
    if problems:
        print("REFUSED: %s cannot be approved as shown:" % md_path)
        for p in problems:
            print("  - %s" % p)
        print("Re-export with --export, review the new file, and approve that one. Nothing was written.")
        log_fn(JOB, "refused", {"action": "approve_all_shown", "file": md_path, "problems": problems})
        return EXIT_REFUSED
    return _approve(sorted(shown), path, yes, isatty, confirm, approved_by, expected=shown,
                    source_note=" exactly as shown in %s" % md_path, action="approve_all_shown", log_fn=log_fn)


def cmd_revoke(ids: List[str], path, yes, isatty, confirm, log_fn=log_run) -> int:
    approvals = ta.load_approvals(path)
    base = {"action": "revoke", "requested": list(ids)}
    try:
        plan = ta.plan_revoke(ids, approvals)
    except ta.ApprovalError as exc:
        print("REFUSED: %s" % exc)
        print("Nothing was written.")
        log_fn(JOB, "refused", dict(base, reason=str(exc)))
        return EXIT_REFUSED
    revoked = dict((tid, (approvals["approvals"].get(tid) or {}).get("sha256")) for tid in plan)
    for tid in plan:
        print("will revoke: %s" % tid)
    print(ta.WIRED_NOTE)
    if not _gate(yes, isatty, confirm, "Revoke %d approval(s)?" % len(plan)):
        log_fn(JOB, "refused", dict(base, reason="not confirmed or no interactive terminal"))
        return EXIT_REFUSED
    written = ta.save_approvals(ta.apply_revoke(plan, approvals), path)
    for tid in plan:
        print("revoked: %s" % tid)
    print("wrote %s" % written)
    log_fn(JOB, "ok", dict(base, revoked=revoked))
    return EXIT_OK


def main(argv: Optional[List[str]] = None, confirm: Callable[[str, str], bool] = confirm_from_tty,
         isatty: Callable[[], bool] = _stdin_isatty, log_fn: Callable[..., Any] = log_run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="id, kind and status of every template")
    mode.add_argument("--show", metavar="ID", help="one template's text and status")
    mode.add_argument("--export", metavar="PATH", help="write the review document (markdown)")
    mode.add_argument("--approve", metavar="ID", nargs="+", help="approve these templates as they are now")
    mode.add_argument("--approve-all-shown", metavar="PATH",
                      help="approve exactly the templates in an exported file, refused if any changed since")
    mode.add_argument("--revoke", metavar="ID", nargs="+", help="remove these approvals")
    parser.add_argument("--yes", action="store_true", help="skip typing APPROVE (interactive terminal only)")
    parser.add_argument("--by", default="Lorenzo", help="approved_by on new records (default: Lorenzo)")
    parser.add_argument("--approvals-file", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = args.approvals_file or None
    try:
        if args.list:
            return cmd_list(path)
        if args.show:
            return cmd_show(args.show, path)
        if args.export:
            return cmd_export(args.export, path)
        if args.approve:
            return _approve(args.approve, path, args.yes, isatty, confirm, args.by, log_fn=log_fn)
        if args.approve_all_shown:
            return cmd_approve_all_shown(args.approve_all_shown, path, args.yes, isatty, confirm, args.by,
                                         log_fn=log_fn)
        if args.revoke:
            return cmd_revoke(args.revoke, path, args.yes, isatty, confirm, log_fn=log_fn)
    except ValueError as exc:  # unreadable approvals file
        print("REFUSED: %s" % exc)
        action = ("approve" if args.approve else "approve_all_shown" if args.approve_all_shown
                  else "revoke" if args.revoke else None)
        if action:
            log_fn(JOB, "refused", {"action": action, "reason": "approvals file unreadable: %s" % exc})
        return EXIT_REFUSED
    return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
