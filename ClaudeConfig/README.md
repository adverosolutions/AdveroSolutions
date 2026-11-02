# Claude Code config backup

Backup of the Claude Code setup Lorenzo uses every day. The live copies are on his Mac in `~/.claude/`: skills, agents, scheduled-task prompts and the global `CLAUDE.md`. Claude Code reads those, not this folder.

- `skills/`: one folder per skill, copied from `~/.claude/skills/`.
- `agents/`: scout, worker, worker-heavy, reviewer and reviewer-max, copied from `~/.claude/agents/`.
- `scheduled-tasks/`: the prompt of each Claude desktop scheduled task. `daily-personalize-1am` and `upwork-followup-watch` are deleted from the scheduler (last runs 2026-10-02 and 2026-09-30); only their prompts are kept here.
- `global-CLAUDE.md`: `~/.claude/CLAUDE.md`.
- `memory/`: Claude's project memory for this repo (`~/.claude/projects/-Users-lorenzovillarreal-Desktop-AdveroSolutions/memory/`). `MEMORY.md` is the index; each file is one fact (decisions, rules, project state). Codex reads this copy.

To refresh: `ClaudeConfig/sync_from_home.sh`, then commit and push. To restore a skill on a new machine, copy `skills/<name>/` into `~/.claude/skills/`.

The Grok Bot copies of the skills are separate: `Agentic Worklfows/agents/grokbot/onboarding/skills/`, rebuilt by `build_pack.py`.

## Codex / Orca clones

Codex discovers repo-scoped skills under `.agents/skills/`; `ClaudeConfig/skills/`
alone is an archive location, not an automatic discovery location. The repo now
tracks relative symlinks for `cold-email-personalization` and its referenced
`lorenzo-voice`, `claudeisms` and `cold-campaigns` skills. These point to this
folder, so they work in another checkout without any files under `~/.claude`.

In an existing clone, run `git pull --ff-only` from the repository root, then
start a new Codex session in that clone. Use `$cold-email-personalization` or
look in `/skills`. If the list has not refreshed, restart the Codex process in
Orca. This configures Codex discovery; Orca's own UI may maintain a separate list.
No installer, Claude login or Anthropic key is needed for these repo skill links.

When editing a linked skill, change the source under `ClaudeConfig/skills/`;
the link follows it automatically. `sync_from_home.sh` copies installed skills
into that source directory, so review its diff to preserve current Codex policies.
