---
name: feedback-grok-delta-updates
description: "Grok Bot is already onboarded; every new skill or context change ships as a small dated update file Lorenzo pastes to Grok, never a re-onboarding"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 34d1e12c-1d0d-43da-b2eb-53bdb2ac3a8e
  modified: 2026-09-28T15:01:53.899Z
---

Grok Bot is onboarded and has all its agents (2026-09-28). Whenever we build or change a skill, or add context Grok needs, write a small dated update file in `Agentic Worklfows/agents/grokbot/updates/YYYY-MM-DD_<topic>.md` with: what changed (short), the exact edits to Grok's copies in `~/advero/` (ask_opus.py, skills/<name>.md) as find/replace or insert-after blocks, and what stays the same. Lorenzo pastes it to Grok himself.

**Why:** he doesn't want to redo onboarding or re-upload the whole GROK_ONBOARDING_PACK.md for every change.

**How to apply:** still rebuild the pack with build_pack.py (the drift test in tests/test_pack.py fails otherwise), but hand Lorenzo only the update file. Diff the pack copies between the last update and now (`git diff <old> <new> -- "Agentic Worklfows/agents/grokbot/onboarding"`) to make sure the update covers every change. First one: `2026-09-28_upwork-call-times-reports-pricing.md`. Related: [[grokbot-orchestrator]], [[feedback-claudeisms]].
