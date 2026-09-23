#!/bin/bash
# SessionStart check for the live-write guard. It cannot block (SessionStart
# hooks never do); its stdout goes into Claude's context, so a problem shows
# up as ONE line starting "LIVE-WRITE GUARD WARNING:". Silent when clean.
#
# Checks:
#   1. python3 exists and `guard_live_writes.py --self-test` passes;
#   2. no .claude/settings*.json from this project up to $HOME (and $HOME's
#      own ~/.claude) sets "disableAllHooks": true;
#   3. ~/.claude/settings.json registers guard_live_writes.sh.
# Always exits 0.

src="${BASH_SOURCE[0]}"
case "$src" in
  */*) dir="${src%/*}" ;;
  *)   dir="." ;;
esac
guard="$dir/guard_live_writes.py"
home="${HOME:-}"
problems=""
add() { if [ -z "$problems" ]; then problems="$1"; else problems="$problems; $1"; fi; }

if [ ! -f "$guard" ]; then
  add "guard script missing at $guard (every tool call will be blocked)"
elif ! command -v python3 >/dev/null 2>&1; then
  add "python3 not found (every tool call will be blocked)"
elif ! python3 "$guard" --self-test >/dev/null 2>&1; then
  add "self-test failed: run python3 \"$guard\" --self-test"
fi

scan() {
  local f
  for f in "$1"/.claude/settings*.json; do
    [ -f "$f" ] || continue
    if grep -Eq '"disableAllHooks"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null; then
      add "disableAllHooks is set in $f (the guard does not run)"
    fi
  done
}

start="${CLAUDE_PROJECT_DIR:-$PWD}"
d="$start"
seen_home=0
for _ in $(seq 1 64); do
  scan "$d"
  [ -n "$home" ] && [ "$d" = "$home" ] && { seen_home=1; break; }
  [ "$d" = "/" ] && break
  d="$(dirname "$d")"
done
[ "$seen_home" -eq 1 ] || { [ -n "$home" ] && scan "$home"; }

if [ -n "$home" ] && ! grep -q 'guard_live_writes.sh' "$home/.claude/settings.json" 2>/dev/null; then
  add "the guard is not registered in ~/.claude/settings.json (run changesets/claude_guard/apply_claude_guard.py)"
fi

if [ -n "$problems" ]; then
  printf 'LIVE-WRITE GUARD WARNING: %s. Do not run anything that could touch live systems until Lorenzo fixes this.\n' "$problems"
fi
exit 0
