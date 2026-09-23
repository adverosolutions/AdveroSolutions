#!/usr/bin/env python3
"""Change-set: install the Claude Code live-write guard at USER level (R1(a), SAF-1, SAF-3).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/claude_guard/apply_claude_guard.py                # dry-run (the default): unified diffs
    python3 changesets/claude_guard/apply_claude_guard.py --apply        # Lorenzo's terminal only; asks for APPLY
    python3 changesets/claude_guard/apply_claude_guard.py --rollback 20260922T180000Z   # asks for APPLY

It changes three files and nothing else:

1. ``~/.claude/settings.json``: adds a PreToolUse hook (matcher
   ``Bash|Read|Grep|Write|Edit|MultiEdit|NotebookEdit|mcp__.*``, timeout 15 s) that
   runs the repo's ``.claude/hooks/guard_live_writes.sh`` by ABSOLUTE path, so
   it runs whichever folder Claude Code starts in, and a SessionStart hook
   (``startup|resume|clear|compact``) that runs ``guard_session_check.sh``.
   Both commands refuse on their own when the script file is missing: a missing
   PreToolUse script exits 2 (blocks every call) instead of 127 (lets it
   through). Every other key is kept as it is. Already installed means no
   change (idempotent); an older guard entry is replaced, never duplicated.
2. Repo-root ``.claude/settings.local.json``: removes ONLY the pre-approvals
   ``Bash(curl:*)`` and ``Bash(python3:*)``.
3. Repo-root ``.claude/settings.json``: removes the old project-level
   PreToolUse guard entry so the guard does not run twice from the repo root.
   The Stop hook stays.

``--apply`` needs an interactive terminal and the typed word APPLY (read from
/dev/tty, so it cannot be piped). It first checks the hook scripts exist and
that ``guard_live_writes.py --self-test`` passes, backs every file up to
``<repo>/.tmp/claude_guard_backup/<UTC timestamp>/`` (with a manifest), then
writes each changed file atomically (temp file + rename, mode kept).
``--rollback <timestamp>`` restores that backup the same way (a file that did
not exist before the apply is removed again).

The live-write guard itself denies Claude running this script without
--dry-run (rule j). ``--home`` and ``--repo`` exist for the tests only.
Exit codes: 0 ok, 1 invalid input (unreadable JSON, bad timestamp), 2 refused.
Python 3.9, stdlib only.
"""
import argparse
import copy
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # .../AdveroSolutions

PRE_MATCHER = "Bash|Read|Grep|Write|Edit|MultiEdit|NotebookEdit|mcp__.*"
SESSION_MATCHER = "startup|resume|clear|compact"
PRE_TIMEOUT = 15
SESSION_TIMEOUT = 30
GUARD_MARKER = "guard_live_writes.sh"
SESSION_MARKER = "guard_session_check.sh"
REMOVE_PERMISSIONS = ("Bash(curl:*)", "Bash(python3:*)")
BACKUP_SUBDIR = os.path.join(".tmp", "claude_guard_backup")
TS_RE = re.compile(r"^\d{8}T\d{6}Z$")
CONFIRM_WORD = "APPLY"

# backup name -> which file
USER_SETTINGS = "user_settings.json"
REPO_SETTINGS = "repo_settings.json"
REPO_LOCAL = "repo_settings.local.json"


class Invalid(Exception):
    pass


def hook_paths(repo: str) -> Tuple[str, str]:
    hooks = os.path.join(repo, ".claude", "hooks")
    return os.path.join(hooks, GUARD_MARKER), os.path.join(hooks, SESSION_MARKER)


def _safe_path(p: str) -> str:
    if any(ch in p for ch in "'\"$`\\\n"):
        raise Invalid("the repo path %r contains a quote, $, backtick, backslash or newline; "
                      "the hook command cannot quote it safely" % p)
    return p


def guard_command(guard_sh: str) -> str:
    g = _safe_path(guard_sh)
    return ("bash -c '[ -f \"%s\" ] && exec bash \"%s\" || "
            "{ echo \"live-write guard missing: %s\" >&2; exit 2; }'" % (g, g, g))


def session_command(check_sh: str) -> str:
    c = _safe_path(check_sh)
    return ("bash -c '[ -f \"%s\" ] && exec bash \"%s\" || "
            "echo \"LIVE-WRITE GUARD WARNING: session check script missing: %s\"'" % (c, c, c))


def desired_entries(repo: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    guard_sh, check_sh = hook_paths(repo)
    pre = {"matcher": PRE_MATCHER,
           "hooks": [{"type": "command", "command": guard_command(guard_sh), "timeout": PRE_TIMEOUT}]}
    ses = {"matcher": SESSION_MATCHER,
           "hooks": [{"type": "command", "command": session_command(check_sh), "timeout": SESSION_TIMEOUT}]}
    return pre, ses


# ------------------------------------------------------------ file helpers
def read_json(path: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """(raw text or None when missing, parsed object or None when missing)."""
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    if not raw.strip():
        return raw, {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise Invalid("%s is not valid JSON (%s); fix it by hand first" % (path, exc))
    if not isinstance(data, dict):
        raise Invalid("%s does not hold a JSON object" % path)
    return raw, data


def dump_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def atomic_write(path: str, text: str, mode: Optional[int] = None) -> None:
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    if mode is None and os.path.exists(path):
        mode = os.stat(path).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix=".%s." % os.path.basename(path), suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode if mode is not None else 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ------------------------------------------------------------ the three transforms
def _hook_commands(entry: Any) -> List[str]:
    if not isinstance(entry, dict):
        return []
    return [h.get("command", "") for h in entry.get("hooks", []) if isinstance(h, dict)
            and isinstance(h.get("command", ""), str)]


def _install(entries: List[Any], marker: str, wanted: Dict[str, Any]) -> List[Any]:
    """entries with exactly one guard entry equal to `wanted`, others kept in order."""
    ours = [e for e in entries if any(marker in c for c in _hook_commands(e))]
    if len(ours) == 1 and ours[0] == wanted:
        return entries  # already installed as wanted
    out = []
    for e in entries:
        if not any(marker in c for c in _hook_commands(e)):
            out.append(e)
            continue
        keep = [h for h in e.get("hooks", []) if not (isinstance(h, dict) and marker in str(h.get("command", "")))]
        if keep:
            e2 = dict(e)
            e2["hooks"] = keep
            out.append(e2)
    out.append(wanted)
    return out


def transform_user(data: Optional[Dict[str, Any]], repo: str) -> Dict[str, Any]:
    new = copy.deepcopy(data) if data is not None else {}
    pre, ses = desired_entries(repo)
    hooks = new.get("hooks")
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, dict):
        raise Invalid("~/.claude/settings.json has a 'hooks' value that is not an object")
    hooks = dict(hooks)
    for event, marker, wanted in (("PreToolUse", GUARD_MARKER, pre), ("SessionStart", SESSION_MARKER, ses)):
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            raise Invalid("~/.claude/settings.json hooks.%s is not a list" % event)
        hooks[event] = _install(list(entries), marker, wanted)
    new["hooks"] = hooks
    if new.get("disableAllHooks") is True:
        raise Invalid("~/.claude/settings.json sets disableAllHooks: true; remove it by hand first "
                      "(the guard would never run)")
    return new


def transform_local(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    new = copy.deepcopy(data)
    perms = new.get("permissions")
    if isinstance(perms, dict) and isinstance(perms.get("allow"), list):
        perms["allow"] = [p for p in perms["allow"] if p not in REMOVE_PERMISSIONS]
    return new


def transform_project(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    new = copy.deepcopy(data)
    hooks = new.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get("PreToolUse"), list):
        return new
    kept = []
    for e in hooks["PreToolUse"]:
        if any(GUARD_MARKER in c for c in _hook_commands(e)):
            rest = [h for h in e.get("hooks", [])
                    if not (isinstance(h, dict) and GUARD_MARKER in str(h.get("command", "")))]
            if rest:
                e2 = dict(e)
                e2["hooks"] = rest
                kept.append(e2)
            continue
        kept.append(e)
    if kept:
        hooks["PreToolUse"] = kept
    else:
        del hooks["PreToolUse"]
    return new


# ------------------------------------------------------------ plan
class Change(object):
    def __init__(self, key: str, path: str, old_raw: Optional[str], new_text: Optional[str]):
        self.key = key
        self.path = path
        self.old_raw = old_raw
        self.new_text = new_text

    @property
    def changed(self) -> bool:
        if self.new_text is None:
            return False
        if self.old_raw is None:
            return True
        try:
            return json.loads(self.old_raw or "{}") != json.loads(self.new_text)
        except ValueError:
            return True

    def diff(self) -> str:
        if not self.changed:
            return "no change: %s\n" % self.path
        old = (self.old_raw or "").splitlines(keepends=True)
        new = (self.new_text or "").splitlines(keepends=True)
        fromfile = ("a" + self.path) if self.old_raw is not None else "/dev/null"
        return "".join(difflib.unified_diff(old, new, fromfile, "b" + self.path, n=3))


def build_plan(home: str, repo: str) -> List[Change]:
    user_path = os.path.join(home, ".claude", "settings.json")
    local_path = os.path.join(repo, ".claude", "settings.local.json")
    proj_path = os.path.join(repo, ".claude", "settings.json")
    plan = []
    raw, data = read_json(user_path)
    plan.append(Change(USER_SETTINGS, user_path, raw, dump_json(transform_user(data, repo))))
    raw, data = read_json(local_path)
    new = transform_local(data)
    plan.append(Change(REPO_LOCAL, local_path, raw, dump_json(new) if new is not None else None))
    raw, data = read_json(proj_path)
    new = transform_project(data)
    plan.append(Change(REPO_SETTINGS, proj_path, raw, dump_json(new) if new is not None else None))
    return plan


# ------------------------------------------------------------ confirmation
def confirm_from_tty(word: str, prompt: str) -> bool:
    """The typed word from the terminal. Refuses when stdin is not a TTY
    (Claude's Bash tool, a pipe, cron) and reads the answer from /dev/tty."""
    if not sys.stdin.isatty():
        print("REFUSED: --apply / --rollback need an interactive terminal (stdin is not a TTY). "
              "Run this from your own terminal.")
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


# ------------------------------------------------------------ apply / rollback
def _self_test_ok(repo: str) -> Tuple[bool, str]:
    guard_py = os.path.join(repo, ".claude", "hooks", "guard_live_writes.py")
    try:
        proc = subprocess.run([sys.executable, guard_py, "--self-test"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    lines = proc.stdout.decode("utf-8", "replace").strip().splitlines()
    return proc.returncode == 0, (lines[-1] if lines else "no output")


def backup(plan: List[Change], repo: str, ts: str) -> str:
    folder = os.path.join(repo, BACKUP_SUBDIR, ts)
    if os.path.exists(folder):
        raise Invalid("backup folder %s already exists" % folder)
    os.makedirs(folder, mode=0o700)
    manifest = {"created": ts, "files": {}}
    for ch in plan:
        entry = {"path": ch.path, "existed": ch.old_raw is not None}
        if ch.old_raw is not None:
            dest = os.path.join(folder, ch.key)
            shutil.copy2(ch.path, dest)
            os.chmod(dest, 0o600)
            entry["mode"] = os.stat(ch.path).st_mode & 0o777
        manifest["files"][ch.key] = entry
    atomic_write(os.path.join(folder, "manifest.json"), dump_json(manifest), 0o600)
    return folder


def do_apply(plan: List[Change], repo: str, confirm: Callable[[str, str], bool], now: Callable[[], datetime]) -> int:
    changed = [ch for ch in plan if ch.changed]
    if not changed:
        print("Nothing to apply: the guard is already installed and the pre-approvals are gone.")
        return EXIT_OK
    guard_sh, check_sh = hook_paths(repo)
    for p in (guard_sh, check_sh, os.path.join(os.path.dirname(guard_sh), "guard_live_writes.py")):
        if not os.path.isfile(p):
            print("REFUSED: %s is missing; installing a hook that points at nothing would block every call." % p)
            return EXIT_REFUSED
    ok, line = _self_test_ok(repo)
    if not ok:
        print("REFUSED: guard self-test failed (%s)." % line)
        return EXIT_REFUSED
    if not confirm(CONFIRM_WORD, "Write %d file(s) shown above?" % len(changed)):
        print("Not applied.")
        return EXIT_REFUSED
    ts = now().strftime("%Y%m%dT%H%M%SZ")
    folder = backup(plan, repo, ts)
    print("Backed up to %s" % folder)
    for ch in changed:
        atomic_write(ch.path, ch.new_text)
        print("wrote %s" % ch.path)
    print("Done. Roll back with: python3 changesets/claude_guard/apply_claude_guard.py --rollback %s" % ts)
    print("Now open a FRESH Claude Code session from Coding/ and check that no 'LIVE-WRITE GUARD WARNING' appears.")
    return EXIT_OK


def rollback_plan(repo: str, ts: str) -> List[Tuple[str, str, Optional[str], Optional[str], Optional[int]]]:
    """[(key, path, current_raw, restored_raw or None=delete, mode)]"""
    if not TS_RE.match(ts or ""):
        raise Invalid("--rollback takes a timestamp like 20260922T180000Z")
    folder = os.path.join(repo, BACKUP_SUBDIR, ts)
    man_path = os.path.join(folder, "manifest.json")
    if not os.path.isfile(man_path):
        raise Invalid("no backup at %s" % folder)
    with open(man_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    out = []
    for key, entry in sorted(manifest.get("files", {}).items()):
        if key not in (USER_SETTINGS, REPO_SETTINGS, REPO_LOCAL):
            raise Invalid("unexpected entry %r in the manifest" % key)
        path = entry["path"]
        current = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                current = fh.read()
        if entry.get("existed"):
            with open(os.path.join(folder, key), "r", encoding="utf-8") as fh:
                restored = fh.read()
        else:
            restored = None
        out.append((key, path, current, restored, entry.get("mode")))
    return out


def do_rollback(repo: str, ts: str, confirm: Callable[[str, str], bool]) -> int:
    steps = rollback_plan(repo, ts)
    todo = [s for s in steps if s[2] != s[3]]
    for key, path, current, restored, mode in steps:
        if current == restored:
            print("no change: %s" % path)
        elif restored is None:
            print("would remove %s (it did not exist before the apply)" % path)
        else:
            sys.stdout.write("".join(difflib.unified_diff((current or "").splitlines(keepends=True),
                                                          restored.splitlines(keepends=True),
                                                          "a" + path, "b" + path, n=3)))
    if not todo:
        print("Nothing to roll back.")
        return EXIT_OK
    if not confirm(CONFIRM_WORD, "Restore %d file(s) from %s?" % (len(todo), ts)):
        print("Not rolled back.")
        return EXIT_REFUSED
    for key, path, current, restored, mode in todo:
        if restored is None:
            if os.path.exists(path):
                os.unlink(path)
            print("removed %s" % path)
        else:
            atomic_write(path, restored, mode)
            print("restored %s" % path)
    return EXIT_OK


# ------------------------------------------------------------ main
def main(argv: Optional[List[str]] = None, confirm: Callable[[str, str], bool] = confirm_from_tty,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the diffs (the default)")
    mode.add_argument("--apply", action="store_true", help="back up, then write (interactive terminal, APPLY)")
    mode.add_argument("--rollback", metavar="TIMESTAMP", help="restore a backup (interactive terminal, APPLY)")
    parser.add_argument("--home", help=argparse.SUPPRESS)
    parser.add_argument("--repo", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    home = os.path.abspath(args.home or os.path.expanduser("~"))
    repo = os.path.abspath(args.repo or DEFAULT_REPO)
    try:
        if args.rollback:
            return do_rollback(repo, args.rollback, confirm)
        plan = build_plan(home, repo)
        print("claude_guard change-set (%s)\n" % ("APPLY" if args.apply else "dry-run"))
        for ch in plan:
            sys.stdout.write(ch.diff())
            sys.stdout.write("\n")
        if not args.apply:
            n = sum(1 for ch in plan if ch.changed)
            print("dry-run: %d file(s) would change. Nothing was written." % n)
            if n:
                print("To apply, run from your own terminal: "
                      "python3 changesets/claude_guard/apply_claude_guard.py --apply")
            return EXIT_OK
        return do_apply(plan, repo, confirm, now)
    except Invalid as exc:
        print("INVALID: %s" % exc)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
