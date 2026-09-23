#!/bin/bash
# Reinstall the /upwork skill if ~/.claude gets cleaned out.
set -e
DEST="$HOME/.claude/skills/upwork"
mkdir -p "$DEST"
cp "$(dirname "$0")/SKILL.md" "$DEST/SKILL.md"
echo "Installed /upwork skill to $DEST/SKILL.md"
