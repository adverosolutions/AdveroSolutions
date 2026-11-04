---
name: grokbot-orchestrator
description: "Grok Bot is Lorenzo's day-to-day operator (decided 2026-09-25): event-driven, executes and retries sends, Opus 5.5 decides everything, Claude Code only builds; manual is the grok-operator skill"
metadata:
  node_type: memory
  type: project
  originSessionId: 588685e4-5751-44eb-958d-e840fd9ed461
  modified: 2026-09-25T17:12:26.067Z
---

Current pointer, 2026-11-04: Grok Bot supplies the current operating rules; the repository maintains the record. Read `ClaudeConfig/PROCESS_AUTHORITY.md` first. The dated notes below are historical where they differ.

2026-09-25 decisions (Lorenzo, replacing the 2026-09-24 design and vetoing my "engine sends approved templates itself" proposal):
- Grok Bot (SpaceX/xAI's persistent-agent product, NOT the Grok API) is his one contact and the operator for replies, quiet-lead follow-up, booked calls, no-shows and nurture. Grok executes the sends, verifies them, and handles failed sends (retry, then report).
- Every decision runs through a model: Claude Opus 5.5 (`claude-opus-5-5`) via a `decide` tool. He sees the engine as "no brain" (record, templates, timers only). All MODEL_POLICY roles move to Opus 5.5.
- Grok never writes or chooses customer-facing text. Only approved-template text goes out without Lorenzo seeing it; he wants everything fully autonomous from those templates.
- No polling. Grok is triggered by webhooks: Instantly `reply_received`, GHL, Zoom; the engine timer wakes Grok only when a touch is due. Periodic checks are a usage waste in his view.
- Grok is logged into everything, read-only (credential scopes), with writes through an MCP/API connector.
- Claude's job is infrastructure that makes money, not day-to-day ops.
- He wants every process as a custom skill so Grok can load them; skills library built 2026-09-25 in ~/.claude/skills.

UPDATE 2026-09-25 later (supersedes the connector plan): Grok IS the engine. It reads GHL stages and Instantly, sends approved copy from its knowledge base (the one Google Doc + skills) itself, and hands every judgement call to Opus 5.5 via ask_opus.py (Lorenzo: lean on Opus as much as possible to save Grok tokens). Lorenzo called the engine/connector build a waste; the grok-core, grok-transport and reply-examples builds were stopped unmerged (branches section/reply-examples at 330f7d8 stay pushed). Don't propose engine-side decide/send builds again.

Onboarding pack for the Chief of Staff Bot: `Agentic Worklfows/agents/grokbot/onboarding/` (GROK_ONBOARDING_PACK.md single upload, ask_opus.py, rebuilt by build_pack.py; merged 2026-09-25). The operating manual is the `grok-operator` skill (~/.claude/skills/grok-operator/SKILL.md).

**Why:** he sees Claude as slow and costly for daily ops, and Grok as better at UI and at spinning up agents.

**How to apply:**
- Don't re-propose engine-side auto-send or polling.
- The earlier connector proposal was canceled by the later September 25 decision. Do not build it from this historical note. For current operations, read `ClaudeConfig/PROCESS_AUTHORITY.md` and the November 4 Grok source snapshot.
- The no-live-changes rule still holds ([[no-live-changes-until-tested]]).
- Unconfirmed until tested in his account: Grok routine webhook URLs and custom MCP.
