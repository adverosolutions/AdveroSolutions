---
name: feedback-working-first-test-later
description: "Get a reliable system running first, rigorous testing later; keep tests lean and review rounds few to save usage"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 322d6581-8a8c-4a27-9d28-1062d27050ff
  modified: 2026-09-24T02:14:36.238Z
---

Lorenzo (2026-09-23, section 2 build): don't overtest or spend usage on it. The goal is a system he can rely on up and running now; rigorous testing comes later.

**Why:** usage limits are tight (he was about to hit them and move to cloud); repeated review/fix rounds and exhaustive test matrices burned usage without changing whether the thing works.

**How to apply:** tests cover the main paths only (one per path), no edge-case matrices; one review per piece, a fix round only for real blockers, park non-blocking findings in STATUS; reviewer-max only where the global rules require it (recipient safety, live sends). Local pytest runs are cheap (time, not tokens) and still run once before each push to main. Also: defer review of code nothing calls yet until the piece that uses it, and merge small related pieces so there are fewer review rounds (he said it again in the section 1 chat the same day). Related: [[feedback-estimates-and-stopping]], [[feedback-max-parallel-agents]].
