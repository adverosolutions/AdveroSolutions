Current process pointer, 2026-11-04: read `ClaudeConfig/PROCESS_AUTHORITY.md` and the maintained repo skills first for operational rules. The installed home-folder skill copies are no longer the maintained source. Availability comes from the actual toolset in the session; the old unavailable-feature list below is a historical snapshot. Do not run the recovered installer as part of process maintenance.

# Lorenzo's global rules for Codex

Source of truth: `ClaudeConfig/codex/AGENTS.md` in the AdveroSolutions repo, installed by `ClaudeConfig/codex/setup_codex.sh`. Project rules come from each repo's `CLAUDE.md` / `Claude.md`, which Codex reads as fallback project docs. The live-write safety rules in `~/Desktop/AdveroSolutions/CLAUDE.md` apply in full.

## Delegation (main session only)
If you are running as a subagent, ignore this entire section and follow only your own agent instructions.

- Follow Lorenzo's current instructions for whether to delegate, and use the agents available in the session. Handle questions, small edits and work finishable in a few steps directly.
- When delegating, give each task a clear goal, files in scope and acceptance criteria. Pass only the context it needs. Run independent tasks in parallel and dependent tasks in order.
- Review implementation against the original requirements and resolve defects before accepting it. Use an independent review agent when delegation is available and authorized; otherwise do a separate self-review and report that it was not independent.
- Only the main session delegates. Subagents never start other agents or workflows.
- Never start a workflow unless Lorenzo asks for one.

## Writing (every session and every agent)
No Claudeisms in any copy you write for me or my clients (emails, Upwork proposals and messages, LinkedIn, DMs, and prompts that generate copy): never add a sentence or tacked-on clause that restates, sums up or sells the point you just made ("Nobody in the office has to remember to ask.", "No more chasing leads.", "That's the whole point.", "...which means you never lose a lead"). Say the thing and stop. Test: delete the line; if the reader loses no fact, question or next step, it goes. Details in the `claudeisms` skill. If a job looks too big for a handful of agents (codebase-wide audit, large migration, many-file refactor), suggest a workflow and wait for my go-ahead, recommending a small test slice first.

## Running Claude-written skills in Codex
The skills in `~/.agents/skills/` are symlinks to `~/.claude/skills/`, shared with Claude Code. They are written for Claude Code. Do not edit them to fit Codex; translate as you read:
- "Claude", "Claude Code" or "you" in a skill means you. "Claude Opus 5.5", "Opus" or "Sonnet" called through the API, `claude -p`, and "Claude" labels inside build JSON are real model names and real text. Keep them exactly as written.
- Agent tool, Task tool, subagent, "send to scout/worker/reviewer": treat Claude role names as descriptions of the task (research, implementation or review). Follow the current delegation instructions and use available Codex agents; these names do not require custom agent files or prescribe Codex model or effort settings.
- A reviewer step with no subagent available: do a self-review pass against the stated acceptance criteria before finishing, and say it was a self-review.
- AskUserQuestion: ask in chat with numbered options, mark the one you recommend, and show the full text of any copy being approved.
- Artifact, "publish a page", claude.ai artifact links: write a local HTML file (in the repo's `.tmp/` or the job folder the skill names) and give the path. Do not open it in a browser unless asked.
- `mcp__<id>__<tool>` tool names: use the tool with the same name on the matching server or plugin (Instantly, Upwork, ClickUp, HighLevel, skool, or the Gmail, Google Calendar and Google Drive plugins). If no server offers that tool, say so and stop; do not fall back to raw API calls that write to live systems.
- Skill tool, `/<skill>` or "invoke the X skill": read that skill with `$<skill>`.
- Scheduled tasks, `/loop`, `/schedule`, Claude in Chrome, the built-in browser pane, computer use, Claude Docs, hooks in `.claude/settings.json`: not available to these skills in Codex. Say so and tell Lorenzo what he needs to run himself.
- Tests: run pytest with `/usr/bin/python3` (3.9, has pytest). `python3` on PATH is Homebrew 3.14 without pytest. In `Agentic Worklfows/` use the test command from its CLAUDE.md.
- Scripts that call the Anthropic API (for example `shared/llm.py` and the lead-scrape personalizer) keep using `ANTHROPIC_API_KEY` and Claude models. Do not switch them to OpenAI.
- Memory: Claude's auto-memory in `~/.claude/projects/*/memory/` is not loaded by Codex. Read a memory file only when a skill or Lorenzo points to it.
