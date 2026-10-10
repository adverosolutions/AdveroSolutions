#!/bin/sh
# Install Lorenzo's Claude Code setup into Codex (ChatGPT app / Codex CLI) on this Mac.
#
#   ClaudeConfig/codex/setup_codex.sh            make the changes
#   ClaudeConfig/codex/setup_codex.sh --dry-run  print what would change, change nothing
#
# What it does (safe to re-run; a run with nothing to do changes nothing):
#   1. ~/.agents/skills/<name> -> ~/.claude/skills/<name> symlinks, one per Claude skill (skips
#      `synced`). A real folder or other entry already at one of those names (the ChatGPT app's
#      imported copies) is MOVED, never deleted, to ~/.agents/skills.imported-backup.<timestamp>/,
#      as is any dangling symlink in ~/.agents/skills. The first time it moves anything it also
#      copies ~/.claude/skills into that backup folder as claude-skills-snapshot/.
#   2. ~/.codex/agents/<name>.toml from ClaudeConfig/codex/agents/ (changed files are backed up
#      to <file>.bak.<timestamp> first).
#   3. ~/.codex/AGENTS.md from ClaudeConfig/codex/AGENTS.md (backed up first).
#   4. Two managed blocks in ~/.codex/config.toml from ClaudeConfig/codex/config.toml (backed up
#      first). Nothing outside the blocks is edited; keys or tables the app already sets outside
#      them are skipped and reported.
# Never touches ~/.codex/hooks.json, hooks.json.bak, auth.json or any other file.

set -eu

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

HERE=$(cd "$(dirname "$0")" && pwd)
TS=$(date +%Y%m%d-%H%M%S)
CLAUDE_SKILLS="$HOME/.claude/skills"
AGENT_SKILLS="$HOME/.agents/skills"
SKILL_BACKUP="$HOME/.agents/skills.imported-backup.$TS"
CODEX_HOME_DIR="$HOME/.codex"

CHANGES=0
NOTES=""
say() { printf '%s\n' "$*"; }
act() {
  # act "description" command args...   (prints; runs unless --dry-run)
  desc=$1; shift
  if [ "$DRY_RUN" -eq 1 ]; then say "  would: $desc"; else say "  $desc"; "$@"; fi
  CHANGES=$((CHANGES + 1))
}
note() { NOTES="$NOTES
  - $*"; }

[ "$DRY_RUN" -eq 1 ] && say "DRY RUN: nothing will be changed."

# Python with tomllib (3.11+) for the config.toml step. /usr/bin/python3 is 3.9, so look for Homebrew's.
PY=""
for cand in python3 /opt/homebrew/bin/python3 python3.14 python3.13 python3.12 python3.11; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import tomllib' >/dev/null 2>&1; then
    PY=$(command -v "$cand"); break
  fi
done

# ---------------------------------------------------------------- 1. skills
say ""
say "1. Skills: $AGENT_SKILLS -> $CLAUDE_SKILLS"
if [ ! -d "$CLAUDE_SKILLS" ]; then
  say "  $CLAUDE_SKILLS not found; skipping skills."
else
  [ -d "$AGENT_SKILLS" ] || act "mkdir -p $AGENT_SKILLS" mkdir -p "$AGENT_SKILLS"
  BACKUP_MADE=0
  ensure_backup() {
    if [ "$BACKUP_MADE" -eq 0 ]; then
      act "create $SKILL_BACKUP" mkdir -p "$SKILL_BACKUP"
      act "snapshot $CLAUDE_SKILLS to $SKILL_BACKUP/claude-skills-snapshot" cp -Rp "$CLAUDE_SKILLS" "$SKILL_BACKUP/claude-skills-snapshot"
      BACKUP_MADE=1
    fi
  }
  # Dangling symlinks (e.g. the old ego-browser link) are moved out of the way.
  for entry in "$AGENT_SKILLS"/* "$AGENT_SKILLS"/.[!.]*; do
    [ -L "$entry" ] || continue
    [ -e "$entry" ] && continue
    ensure_backup
    act "move dangling link $(basename "$entry") -> backup" mv "$entry" "$SKILL_BACKUP/"
  done
  linked=0; already=0
  for src in "$CLAUDE_SKILLS"/*; do
    [ -d "$src" ] || continue
    name=$(basename "$src")
    dst="$AGENT_SKILLS/$name"
    if [ "$name" = "synced" ]; then
      if [ -e "$dst" ] || [ -L "$dst" ]; then
        ensure_backup
        act "move imported $name -> backup (not a skill; not linked)" mv "$dst" "$SKILL_BACKUP/"
      fi
      continue
    fi
    if [ ! -f "$src/SKILL.md" ]; then
      note "skill folder without SKILL.md, not linked: $src"
      continue
    fi
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
      already=$((already + 1)); continue
    fi
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      ensure_backup
      act "move existing $name -> backup" mv "$dst" "$SKILL_BACKUP/"
    fi
    act "link $name" ln -s "$src" "$dst"
    linked=$((linked + 1))
  done
  say "  skills already linked: $already, newly linked: $linked"
  if [ "$BACKUP_MADE" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then note "imported skill copies would move to $SKILL_BACKUP"
    else note "imported skill copies moved to $SKILL_BACKUP"; fi
  fi
fi

# ---------------------------------------------------------------- helper: install one file
# install_file SRC DST   copies SRC to DST unless identical; backs DST up first.
install_file() {
  src=$1; dst=$2
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
    say "  unchanged: $dst"; return 0
  fi
  if [ -e "$dst" ]; then
    act "back up $dst -> $dst.bak.$TS" cp -p "$dst" "$dst.bak.$TS"
    [ "$DRY_RUN" -eq 1 ] || note "backup: $dst.bak.$TS"
  fi
  act "install $dst" cp "$src" "$dst"
}

# ---------------------------------------------------------------- 2. agents
say ""
say "2. Subagents: $CODEX_HOME_DIR/agents/"
[ -d "$CODEX_HOME_DIR/agents" ] || act "mkdir -p $CODEX_HOME_DIR/agents" mkdir -p "$CODEX_HOME_DIR/agents"
for f in "$HERE"/agents/*.toml; do
  install_file "$f" "$CODEX_HOME_DIR/agents/$(basename "$f")"
done

# ---------------------------------------------------------------- 3. AGENTS.md
say ""
say "3. Global instructions: $CODEX_HOME_DIR/AGENTS.md"
install_file "$HERE/AGENTS.md" "$CODEX_HOME_DIR/AGENTS.md"

# ---------------------------------------------------------------- 4. config.toml
say ""
say "4. Config: managed blocks in $CODEX_HOME_DIR/config.toml"
if [ -z "$PY" ]; then
  say "  no python3 with tomllib (3.11+) found; config.toml NOT changed."
  note "config.toml not updated: install Homebrew python3 and re-run"
else
  CFG_TMP=$(mktemp "${TMPDIR:-/tmp}/setup_codex.XXXXXX")
  set +e
  "$PY" - "$HERE/config.toml" "$CODEX_HOME_DIR/config.toml" "$DRY_RUN" "$TS" >"$CFG_TMP" 2>&1 <<'PYEOF'
import difflib, os, re, sys, tomllib

template_path, target, dry_run, ts = sys.argv[1], sys.argv[2], sys.argv[3] == "1", sys.argv[4]
TAG = "advero-codex managed block"
B_TOP = f"# >>> {TAG} (top): edit ClaudeConfig/codex/config.toml and re-run setup_codex.sh, not this block >>>"
E_TOP = f"# <<< {TAG} (top) <<<"
B_BOT = f"# >>> {TAG} (tables): edit ClaudeConfig/codex/config.toml and re-run setup_codex.sh, not this block >>>"
E_BOT = f"# <<< {TAG} (tables) <<<"
MARKER = "# ---- TABLES"

tpl = open(template_path, encoding="utf-8").read()
idx = tpl.find("\n" + MARKER)
if idx < 0:
    sys.exit("template has no TABLES marker")
top_tpl = tpl[: idx + 1]
bot_tpl = tpl[idx + 1 :].split("\n", 1)[1]  # drop the marker line

existing = open(target, encoding="utf-8").read() if os.path.exists(target) else ""

# Strip our previous blocks (exactly what we add below).
top_re = re.compile(re.escape(B_TOP) + r"\n.*?" + re.escape(E_TOP) + r"\n\n?", re.S)
bot_re = re.compile(r"\n?" + re.escape(B_BOT) + r"\n.*?" + re.escape(E_BOT) + r"\n", re.S)
base = bot_re.sub("", top_re.sub("", existing, count=1), count=1)
try:
    base_doc = tomllib.loads(base)
except tomllib.TOMLDecodeError as e:
    sys.exit(f"existing config.toml does not parse, not touching it: {e}")

notes = []

# Top-level keys: skip any the file already sets outside the block.
top_lines = []
for line in top_tpl.splitlines():
    m = re.match(r"^([A-Za-z0-9_-]+)\s*=", line)
    if m and m.group(1) in base_doc:
        top_lines.append(f"# skipped: {m.group(1)} is already set outside this block")
        notes.append(f"config.toml: '{m.group(1)}' already set by the app outside the block; kept the app's value ({base_doc[m.group(1)]!r})")
        continue
    top_lines.append(line)
top_body = "\n".join(top_lines).strip("\n")

# Tables: one paragraph per table; drop a table the file already defines.
def has_table(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True

paras = [p for p in re.split(r"\n\s*\n", bot_tpl.strip("\n"))]
kept = []
first_real = None
for p in paras:
    headers = re.findall(r"^\[([^\]]+)\]\s*$", p, re.M)
    if len(headers) > 1:
        sys.exit("template paragraph with more than one table header: " + headers[0])
    code = [l for l in p.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if code and first_real is None:
        first_real = code[0]
    if headers:
        name = headers[0].strip().strip('"')
        if has_table(base_doc, name):
            notes.append(f"config.toml: [{name}] already defined outside the block; kept the app's version")
            kept.append(f"# skipped: [{name}] is already defined outside this block")
            continue
    kept.append(p)
if first_real is not None and not first_real.startswith("["):
    sys.exit("template tables section must start with a [table] header")
bot_body = "\n\n".join(kept)

top_block = f"{B_TOP}\n{top_body}\n{E_TOP}\n\n"
if base and not base.endswith("\n"):
    base += "\n"
    notes.append("config.toml: added a final newline to the existing file")
bot_block = f"\n{B_BOT}\n{bot_body}\n{E_BOT}\n"
new = top_block + base + bot_block

# Checks: parses; stripping the blocks gives the base back byte for byte; base values unchanged.
new_doc = tomllib.loads(new)
assert bot_re.sub("", top_re.sub("", new, count=1), count=1) == base, "block round-trip failed"
def same(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and all(k in b and same(v, b[k]) for k, v in a.items())
    return a == b
assert same(base_doc, new_doc), "a pre-existing value changed"

for n in notes:
    print("NOTE " + n)
if new == existing:
    print("  unchanged: " + target)
    sys.exit(0)
if dry_run:
    print("  would update " + target + ":")
    for l in difflib.unified_diff(existing.splitlines(), new.splitlines(), "config.toml (now)", "config.toml (after)", lineterm="", n=1):
        print("    " + l)
    print("CHANGED")
    sys.exit(0)
if os.path.exists(target):
    bak = f"{target}.bak.{ts}"
    with open(bak, "w", encoding="utf-8") as f:
        f.write(existing)
    os.chmod(bak, 0o600)
    print(f"  back up {target} -> {bak}")
    print(f"NOTE backup: {bak}")
tmp = target + ".tmp-setup"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(new)
os.chmod(tmp, 0o600)
os.replace(tmp, target)
tomllib.loads(open(target, encoding="utf-8").read())
print("  installed managed blocks in " + target)
print("CHANGED")
PYEOF
  rc=$?
  set -e
  CFG_OUT=$(cat "$CFG_TMP"); rm -f "$CFG_TMP"
  printf '%s\n' "$CFG_OUT" | grep -v -e '^NOTE ' -e '^CHANGED$' || true
  if [ $rc -ne 0 ]; then
    say "  config.toml step failed (exit $rc); file left as it was."
    note "config.toml NOT updated, see message above"
  fi
  printf '%s\n' "$CFG_OUT" | grep -q '^CHANGED$' && CHANGES=$((CHANGES + 1))
  NOTE_LINES=$(printf '%s\n' "$CFG_OUT" | sed -n 's/^NOTE //p')
  while IFS= read -r l; do
    [ -n "$l" ] && note "$l"
  done <<EOF_NOTES
$NOTE_LINES
EOF_NOTES
fi

# ---------------------------------------------------------------- summary
say ""
if [ "$CHANGES" -eq 0 ]; then
  say "Done: nothing to change, everything already in place."
elif [ "$DRY_RUN" -eq 1 ]; then
  say "Dry run: $CHANGES change(s) would be made. Run again without --dry-run to apply."
else
  say "Done: $CHANGES change(s) made."
fi
[ -n "$NOTES" ] && say "Notes:$NOTES"
cat <<'EOF'

Next steps (details in ClaudeConfig/codex/README.md):
  - Quit and reopen the ChatGPT app, or start a new `codex` session, so it reloads config, agents and skills.
  - Log in to each remote MCP server once:
      codex mcp login instantly
      codex mcp login upwork
      codex mcp login clickup
      codex mcp login gohighlevel
  - In Codex, run /plugins and install Gmail, Google Calendar and Google Drive.
  - Start work: cd ~/Desktop/AdveroSolutions && codex     (call a skill with $upwork)
EOF
