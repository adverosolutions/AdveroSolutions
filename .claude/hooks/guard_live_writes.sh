#!/bin/bash
# PreToolUse live-write guard: thin FAIL-CLOSED wrapper around guard_live_writes.py.
#
# Registered at user level (~/.claude/settings.json) by
# "Agentic Worklfows/changesets/claude_guard/apply_claude_guard.py"; see
# "Agentic Worklfows/runbooks/live_write_guard.md".
#
# Claude Code treats a hook that exits non-zero (other than 2) without valid
# JSON as "no decision" and lets the call through. So every failure here
# (python3 missing, the guard erroring, output that is not a decision) is
# turned into exit 2, which blocks. Valid output is either nothing (no
# decision) or one line of decision JSON, passed through with exit 0.
# Runs from any working directory; uses only bash builtins and python3.

src="${BASH_SOURCE[0]}"
case "$src" in
  */*) dir="${src%/*}" ;;
  *)   dir="." ;;
esac
guard="$dir/guard_live_writes.py"

fail() {
  printf 'LIVE-WRITE GUARD BLOCKED THIS CALL (fail-closed): %s. Nothing ran. Fix the guard (python3 %s --self-test) rather than working around it.\n' "$1" "$guard" >&2
  exit 2
}

[ -f "$guard" ] || fail "guard script missing at $guard"
command -v python3 >/dev/null 2>&1 || fail "python3 not found on PATH"

out="$(python3 "$guard")"
rc=$?
[ "$rc" -eq 0 ] || fail "guard exited with status $rc"

case "$out" in
  "")
    exit 0 ;;
  *$'\n'*)
    fail "guard printed more than one line" ;;
  '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "'*'"}}' | \
  '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "'*'"}}')
    printf '%s\n' "$out"
    exit 0 ;;
  *)
    fail "guard output is not a decision" ;;
esac
