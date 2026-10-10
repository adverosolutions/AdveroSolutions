# Codex setup (same skills, rules and tools as Claude Code)

This folder makes OpenAI Codex on Lorenzo's Mac work from the same setup as Claude Code. The skills are not copied: `~/.agents/skills/<name>` is a symlink to `~/.claude/skills/<name>`, so an edit to a skill reaches both. The rules are ported, the subagent roster is rebuilt as Codex agents, and the MCP servers point at each vendor's official endpoint.

| File | Installed as |
|---|---|
| `AGENTS.md` | `~/.codex/AGENTS.md` (global rules plus how to read Claude-written skills) |
| `agents/*.toml` | `~/.codex/agents/*.toml` (scout, worker, worker-heavy, worker-max, reviewer, reviewer-max) |
| `config.toml` | two marked blocks inside `~/.codex/config.toml`; the ChatGPT app's own settings are left alone |
| `setup_codex.sh` | installs all of the above; `--dry-run` prints the changes without making them |

## Steps

1. **Codex is already installed** through the ChatGPT desktop app, and that app is signed in. Its CLI is bundled at `/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex`, but it is not on your PATH. To use `codex` in Terminal, pick one:
   - Link the bundled CLI, which updates with the app:
     `ln -s "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex" ~/.local/bin/codex`
   - Or install the standalone CLI (official, [OpenAI Codex CLI docs](https://learn.chatgpt.com/docs/codex/cli)): `curl -fsSL https://chatgpt.com/codex/install.sh | sh`, or `npm install -g @openai/codex`, or `brew install --cask codex`.
2. **Sign in.** The terminal CLI shares `~/.codex/auth.json` with the app, so you are probably signed in already. If `codex` asks, choose Sign in with ChatGPT, or run `codex login`.
3. **Run the setup** from the repo: `ClaudeConfig/codex/setup_codex.sh --dry-run`, check the output, then run `ClaudeConfig/codex/setup_codex.sh`. Every replaced file gets a `.bak.<timestamp>` copy next to it. The app's imported skill copies are moved to `~/.agents/skills.imported-backup.<timestamp>/`, never deleted. Run it again after you edit anything in this folder; a second run with nothing new changes nothing.
4. **Restart Codex** (quit and reopen the ChatGPT app, or open a new `codex` session) so it loads the new config, agents and skills.
5. **Log in to the remote MCP servers**, once each (a browser window opens for each):
   ```
   codex mcp login instantly
   codex mcp login upwork
   codex mcp login clickup
   codex mcp login gohighlevel
   ```
   `codex mcp list` shows each server's status. Skool needs no login; it reads `~/.config/skool-mcp/config.json` like it does for Claude.
6. **Gmail, Google Calendar and Google Drive** come from OpenAI's own plugins, not from MCP config: run `/plugins` in Codex (or open the Plugins tab in the ChatGPT app), install Gmail, Google Calendar and Google Drive, and approve the Google sign-in.
7. **Environment variables.** None are required. Only if the Instantly OAuth login fails: add `export INSTANTLY_API_KEY=...` to `~/.zshrc` and switch to the commented API-key lines in the `[mcp_servers.instantly]` block of `config.toml`, then re-run the setup. Scripts that already use `ANTHROPIC_API_KEY` (for example `Agentic Worklfows/shared/llm.py` and the lead-scrape personalizer) keep calling Claude models through your existing `.env`; Codex does not change that.
8. **Start working:** `cd ~/Desktop/AdveroSolutions && codex`. You can also open the folder in the ChatGPT app's Codex tab.
9. **Call a skill** with `$` plus its name, for example `$upwork` or `$cold-email-replies`, or pick one from `/skills`. Ask for a subagent by name ("send this to worker-heavy", "have reviewer check it") or let `AGENTS.md` steer the delegation.

## MCP servers

| Server | Endpoint | Auth | Source |
|---|---|---|---|
| `skool` | local: `node Coding/skool-mcp/dist/index.js` | its own config file | `Coding/.mcp.json` |
| `instantly` | `https://mcp.instantly.ai/` | OAuth (`codex mcp login`); API-key fallback commented in the config | [Instantly MCP docs](https://developer.instantly.ai/mcp/authentication), server OAuth metadata |
| `upwork` | `https://mcp.upwork.com/mcp` | OAuth | [upwork.com/ai/mcp](https://www.upwork.com/ai/mcp) |
| `clickup` | `https://mcp.clickup.com/mcp` | OAuth only | [ClickUp developer docs](https://developer.clickup.com/docs/connect-an-ai-assistant-to-clickups-mcp-server) |
| `gohighlevel` | `https://services.leadconnectorhq.com/mcp/openai/v2/codex` | OAuth | [HighLevel MCP docs](https://marketplace.gohighlevel.com/docs/other/mcp) |
| Gmail, Calendar, Drive | OpenAI plugins | Google sign-in in the plugin | [Codex plugins](https://learn.chatgpt.com/docs/plugins) |

## Permissions

Claude Code runs in bypass-permissions mode. The Codex default here is one step tighter: `sandbox_mode = "workspace-write"` with network on and `approval_policy = "on-request"`. Commands, Python tools and their API calls run without asking inside the repo. Codex asks before writing outside `~/Desktop/AdveroSolutions`, or before writes the sandbox blocks (git metadata can be one of them). For one unsandboxed session, run `codex --sandbox danger-full-access --ask-for-approval never`. To tighten, set `network_access = false` or `sandbox_mode = "read-only"` in `config.toml` and re-run the setup. The live-write rules in the repo's `CLAUDE.md` (`MODE=shadow` by default, never set the live flags or approve templates, no pushes of `--all`/`--mirror`/`--tags`/`archive/*`) apply to Codex unchanged, and `shared.settings.guard_write` still enforces them in code.

## What does not carry over

- **Claude's live-write hook** (`.claude/hooks/guard_live_writes.sh`) is not registered with Codex by this setup. The code-level `guard_write` still holds.
- **Scheduled tasks**, `/loop`, Claude in Chrome, the built-in browser pane, computer use, Claude Docs and claude.ai Artifacts are not available to these skills. Skills that publish a page write a local HTML file instead.
- **Claude's auto-memory** (`~/.claude/projects/*/memory/`) is not loaded.
- **Tool names differ** on the Gmail, Calendar and Drive plugins, so skills that name a Claude connector tool get the nearest plugin tool.
- **Skill list budget:** Codex caps the initial skill list at 2% of the model's context window (8,000 characters if the window is unknown) and shortens descriptions first. The 25 descriptions total about 12,600 characters, so some may be shortened when many plugin skills are also installed. `$<name>` still loads the full skill.
- **Effort levels** must be supported by the chosen model. `worker-max` and `reviewer-max` use `max`, which the current GPT models in Codex support.
- **The ChatGPT app's "import from Claude Code" sync** is still on. It made the copies that the setup moves aside, and it may copy files again. Re-run `setup_codex.sh --dry-run` after an app update to check.
- **Tests** still run with `/usr/bin/python3` (3.9 with pytest). Homebrew `python3` (3.14) has no pytest.
