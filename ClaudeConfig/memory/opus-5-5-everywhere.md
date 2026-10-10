---
name: opus-5-5-everywhere
description: "Every runtime model call in Lorenzo's code runs on claude-opus-5-5 (decided 2026-09-25); no Haiku/Sonnet tiers for cost"
metadata:
  type: feedback
---

On 2026-09-25 Lorenzo said "everything needs to be on Opus 5.5". That covers:
- the engine's MODEL_POLICY (branch section/opus-policy)
- every standalone script: icebreakers, LinkedIn, Skool tone, personalization, Coding/ tools (branch section/opus-scripts)

**Why:** he wants every decision and every draft made by the strongest model. Cost tiers (Haiku for research, Sonnet for drafts) are not wanted.

**How to apply:**
- New code defaults to `claude-opus-5-5`.
- Opus 5.5 rejects disabled thinking and `budget_tokens`. Use `output_config` effort "low" plus max_tokens headroom for short calls.
- Older memories that name Haiku or Sonnet tiers (e.g. [[personalization-line-generator]]) are stale on the model choice.
- Claude Code agent tiers in `.claude/agents` are build-time settings. They are not covered by this rule.
