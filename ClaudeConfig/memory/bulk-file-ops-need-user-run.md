---
name: bulk-file-ops-need-user-run
description: Auto-mode classifier blocks bulk trash/move scripts as "Irreversible Local Destruction" even when reversible; hand Lorenzo a Run-button command instead. Finder AppleScript trash hangs on a permission prompt.
metadata:
  type: feedback
---

Bulk file operations (moving many files, even pure relocations) run from Bash get denied by the auto-mode permission classifier with reason "Irreversible Local Destruction", regardless of a Trash mirror and restore script. Also: `osascript ... tell Finder to delete` hangs waiting on a macOS Automation prompt the user is not there to click; `ls ~/.Trash` is blocked by TCC but `mv`/`mkdir`/`stat` inside ~/.Trash work.

**Why:** learned 2026-09-21 during the file cleanup; two attempts (full plan, moves-only) were both blocked, and Lorenzo ran the command himself in seconds.

**How to apply:** build the plan deterministically, stage the script + plan in a durable folder, dry-run it, then give Lorenzo the exact `python3 ... apply_cleanup.py plan.json --out ...` command in a `bash` block (the app shows a Run button). Never use Finder AppleScript for trashing; move into a dated mirror folder under ~/.Trash and write a restore script. Related: [[cleanup-2026-09-21]].
