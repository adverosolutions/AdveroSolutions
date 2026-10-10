---
name: sections-split-2026-09-23
description: Revenue build split into 4 parallel chats (email follow-up+nurture, booked calls+no-show, Upwork, core/doc/go-live); handoffs in Agentic Worklfows/sections/, worktrees + section/* branches
metadata:
  type: project
---

On 2026-09-23 Lorenzo split the revenue automation build into exactly 4 chats run side by side (4 is the most he can keep in one window):
1. Email follow-up after an interested lead goes quiet (E1-E10 rewrite in `sections/1_email_followup/sequence_final.md`) plus the 90-day nurture (`nurture.enroll`).
2. Booked calls: confirmation (keep as is), pre-call reminder cadence (research first), no-show recovery.
3. Upwork follow-ups.
4. Core engine, template gate, the one Google Doc and its apply path, the 6 Instantly cold campaigns, go-live; owns `shared/` and all shared files; back-office jobs parked here.

Rules, file ownership and kickoff prompts: `Agentic Worklfows/sections/README.md`; each section keeps a `STATUS.md`. Each chat works in a worktree at `.worktrees/<n>` on `section/<name>`, pushes its branch, rebases and pushes to `main` after each reviewed piece. Doc tooling moved into git at `Agentic Worklfows/tools/template_doc/`, test guard at `tools/netguard/`.

**Why:** the single-chat build ran ~18 hours; Lorenzo wants parallel, pushed work so nothing is lost when usage runs out. **How to apply:** when resuming revenue-build work, find which section it belongs to and follow that section's README and STATUS; don't cross into another section's files except via a `shared:` commit. Related: [[feedback-push-every-change]], [[cold-email-template-autosend]], [[upwork-followup-pipeline]].
