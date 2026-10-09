# Claude Code config backup

Backup of the Claude Code setup Lorenzo uses every day. The live copies are on his Mac in `~/.claude/`: skills, agents, scheduled-task prompts and the global `CLAUDE.md`. Claude Code reads those, not this folder.

- `skills/`: one folder per skill, copied from `~/.claude/skills/`.
- `agents/`: scout, worker, worker-heavy, reviewer and reviewer-max, copied from `~/.claude/agents/`.
- `scheduled-tasks/`: the prompt of each Claude desktop scheduled task. `daily-personalize-1am` and `upwork-followup-watch` are deleted from the scheduler (last runs 2026-10-02 and 2026-09-30); only their prompts are kept here.
- `global-CLAUDE.md`: `~/.claude/CLAUDE.md`.

To refresh: `ClaudeConfig/sync_from_home.sh`, then commit and push. To restore a skill on a new machine, copy `skills/<name>/` into `~/.claude/skills/`.

The Grok Bot copies of the skills are separate: `Agentic Worklfows/agents/grokbot/onboarding/skills/`, rebuilt by `build_pack.py`.
