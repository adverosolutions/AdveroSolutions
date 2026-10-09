#!/bin/sh
# Copy the live Claude Code config on this Mac into the repo, then commit and push it.
# Live copies stay in ~/.claude; this folder is the backup on GitHub.
set -e
cd "$(dirname "$0")"
rsync -a --delete --exclude 'synced/' --exclude '.*' ~/.claude/skills/ skills/
rsync -a --delete ~/.claude/agents/ agents/
rsync -a --delete --exclude '.*' ~/.claude/scheduled-tasks/ scheduled-tasks/
cp ~/.claude/CLAUDE.md global-CLAUDE.md
git status --short .
