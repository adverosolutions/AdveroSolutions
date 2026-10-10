---
name: python3-is-3-14-no-pytest
description: "As of 2026-10-09 `python3` resolves to Homebrew 3.14 with no pytest; run test suites with /usr/bin/python3 (3.9.6, pytest 7.4.3)"
metadata:
  node_type: memory
  type: reference
  originSessionId: c353b499-27d8-4e43-bf3d-8ccacf86af32
  modified: 2026-10-09T22:53:16.731Z
---

Found 2026-10-09: `python3` on PATH is `/opt/homebrew/bin/python3` (Python 3.14), which has no pytest, so the repo test command in CLAUDE.md fails with "No module named pytest". `/usr/bin/python3` is 3.9.6 with pytest 7.4.3 and runs everything (full Agentic Worklfows suite: 12,534 passed in ~5.5 min). Also no `timeout` binary on this Mac.

**How to apply:** swap `python3` for `/usr/bin/python3` in the test command, e.g. from `Agentic Worklfows/`: `PYTHONPATH=tools/netguard /usr/bin/python3 -c "import netguard, pytest, sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider']))"`. Related: [[feedback-push-every-change]].
