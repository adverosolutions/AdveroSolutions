---
name: workspace-layout
description: "~/Personal, ~/Business, ~/Clients/<client> workspaces set up 2026-09-22; which Desktop folders stay put and why; user-level agent roster and delegation rules"
metadata:
  node_type: memory
  type: project
  originSessionId: e084910d-b060-42c8-b289-0cd3b23ef151
  modified: 2026-09-22T18:17:24.407Z
---

On 2026-09-22 Lorenzo set up three Claude Code workspaces in his home folder, each with its own CLAUDE.md: `~/Personal` (health, home, finances, Lorenzo's Lawncare), `~/Business` (AdveroSolutions context, AdveroAdvertising brand files, Content & Reference), and `~/Clients/<client>` (Aysha, Best Work Construction, Start Financial Solutions LLC; each with .env, .gitignore, .claude/skills, active/). There is deliberately no CLAUDE.md in ~ itself.

Desktop folders left in place because code depends on their paths: `~/Desktop/AdveroSolutions` (the repo; runbooks, scripts and this memory dir are keyed to that path), `~/Desktop/Projects` (Demo Library at `Projects/library`, on the do-not-touch Upwork loop), `~/Desktop/GHL-Imports` (written by `upwork-pipeline/job`). Screenshots and the empty Work folder stay by his choice. Move log and `undo.sh`: `~/Desktop/AdveroSolutions/.tmp/desktop_filing_2026-09-22/`.

User-level agents in ~/.claude/agents: scout (low), worker (medium), worker-heavy (high), reviewer (xhigh), reviewer-max (max, high-stakes only), all claude-opus-5-5. The orchestration rules are the "Delegation (main session only)" section of ~/.claude/CLAUDE.md, written verbatim from his spec. The worker-heavy and reviewer-max descriptions contain ": ", which strict YAML rejects; Claude Code 2.1.280 retries frontmatter parsing with values auto-quoted, so they load. Leave them verbatim unless he asks.

**Why:** later sessions should look for files in the new locations, and should not try to move the path-bound folders.
**How to apply:** `~/Desktop/Aysha Delivery`, `~/Desktop/Clients & Ventures` and `~/Desktop/Content & Reference` no longer exist; see [[cleanup-2026-09-21]] (its restore.sh would recreate some of those old Desktop paths).
