# Lorenzo's global rules for Codex

Ported from `~/.claude/CLAUDE.md` (source of truth: `ClaudeConfig/codex/AGENTS.md` in the AdveroSolutions repo, installed by `ClaudeConfig/codex/setup_codex.sh`). Project rules come from each repo's `CLAUDE.md` / `Claude.md`, which Codex reads as fallback project docs. The live-write safety rules in `~/Desktop/AdveroSolutions/CLAUDE.md` apply in full.

## Delegation (main session only)
If you are running as a subagent, ignore this entire section and follow only your own agent instructions.

### Roles
The roster is defined as Codex custom agents in `~/.codex/agents/*.toml`. Spawn them by name.
- Main session = orchestrator. Plans, splits work, briefs agents, reads reports, decides. On multi-step builds it does not do the implementation itself.
- `scout` (low effort, read-only sandbox): read-only context gathering. Use it instead of reading many files yourself or using the built-in `explorer` agent.
- `worker` (medium): default for small, clearly scoped implementation pieces.
- `worker-heavy` (high): multi-file or tricky pieces, debugging, and fixing anything the reviewer rejected.
- `reviewer` (xhigh): reviews every implementation result before it's accepted.
- `reviewer-max` (max): replaces reviewer ONLY for high-stakes changes (infrastructure, deployments, auth/security, payments, migrations, client production systems, data deletion, anything hard to undo).
- `worker-max` (max): only when Lorenzo approves max effort for a piece that failed review twice.

### When to act directly (no agents)
Questions, explanations, small or single-file edits, config tweaks, and anything finishable in a few steps. Don't spin up agents for these.

### Build loop (multi-step builds)
1. If context is missing, send scout first.
2. Plan and split the work into pieces, each with a clear spec: goal, files in scope, acceptance criteria.
3. Send each piece to worker (small, clear) or worker-heavy (multi-file, tricky). Run independent pieces in parallel; keep dependent pieces in order.
4. Send each result plus the ORIGINAL spec to reviewer, or reviewer-max if high-stakes.
5. On REJECT, send the defect list to worker-heavy (even if a worker did the original), then review again.
6. Accept a piece only on APPROVE.

If subagents are unavailable in the current session, do the pieces yourself in order, then run a separate review pass against each piece's acceptance criteria before you call it done, and say in your report that the review was not independent.

### Lanes (who backs off)
- Scouts read, workers build, reviewers judge. No agent does another's job.
- Only the main session delegates. Subagents never start other agents or workflows.
- The main session does not approve work itself. Every implementation result goes through reviewer or reviewer-max.
- Pass each agent only the context its piece needs.

### Escalation and limits
- If a piece fails review twice after worker-heavy, stop and tell me what's failing. I decide whether to switch effort to max. Never use max effort on your own except through reviewer-max for high-stakes changes.
- Workflows/ultracode: never start one unless I type "ultracode" or ask for a workflow. In Codex this also means: don't switch to `ultra` reasoning effort on your own.

## Writing (every session and every agent)
No Claudeisms in any copy you write for me or my clients (emails, Upwork proposals and messages, LinkedIn, DMs, and prompts that generate copy): never add a sentence or tacked-on clause that restates, sums up or sells the point you just made ("Nobody in the office has to remember to ask.", "No more chasing leads.", "That's the whole point.", "...which means you never lose a lead"). Say the thing and stop. Test: delete the line; if the reader loses no fact, question or next step, it goes. Details in the `claudeisms` skill. If a job looks too big for a handful of agents (codebase-wide audit, large migration, many-file refactor), suggest a workflow and wait for my go-ahead, recommending a small test slice first.

## Running Claude-written skills in Codex
The skills in `~/.agents/skills/` are symlinks to `~/.claude/skills/`, shared with Claude Code. They are written for Claude Code. Do not edit them to fit Codex; translate as you read:
- "Claude", "Claude Code" or "you" in a skill means you. "Claude Opus 5.5", "Opus" or "Sonnet" called through the API, `claude -p`, and "Claude" labels inside build JSON are real model names and real text. Keep them exactly as written.
- Agent tool, Task tool, subagent, "send to scout/worker/reviewer": spawn the Codex custom agent with that name from `~/.codex/agents/`. Built-in names such as `general-purpose`, `Explore` or `Plan` map to Codex's `default` or `explorer` agents.
- A reviewer step with no subagent available: do a self-review pass against the stated acceptance criteria before finishing, and say it was a self-review.
- AskUserQuestion: ask in chat with numbered options, mark the one you recommend, and show the full text of any copy being approved.
- Artifact, "publish a page", claude.ai artifact links: write a local HTML file (in the repo's `.tmp/` or the job folder the skill names) and give the path. Do not open it in a browser unless asked.
- `mcp__<id>__<tool>` tool names: use the tool with the same name on the matching server or plugin (Instantly, Upwork, ClickUp, HighLevel, skool, or the Gmail, Google Calendar and Google Drive plugins). If no server offers that tool, say so and stop; do not fall back to raw API calls that write to live systems.
- Skill tool, `/<skill>` or "invoke the X skill": read that skill with `$<skill>`.
- Scheduled tasks, `/loop`, `/schedule`, Claude in Chrome, the built-in browser pane, computer use, Claude Docs, hooks in `.claude/settings.json`: not available to these skills in Codex. Say so and tell Lorenzo what he needs to run himself.
- Tests: run pytest with `/usr/bin/python3` (3.9, has pytest). `python3` on PATH is Homebrew 3.14 without pytest. In `Agentic Worklfows/` use the test command from its CLAUDE.md.
- Scripts that call the Anthropic API (for example `shared/llm.py` and the lead-scrape personalizer) keep using `ANTHROPIC_API_KEY` and Claude models. Do not switch them to OpenAI.
- Memory: Claude's auto-memory in `~/.claude/projects/*/memory/` is not loaded by Codex. Read a memory file only when a skill or Lorenzo points to it.
