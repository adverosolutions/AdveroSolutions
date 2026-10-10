---
name: feedback-estimates-and-stopping
description: Give realistic time estimates and cap review loops; park optional polish instead of opening more rounds
metadata:
  node_type: memory
  type: feedback
  originSessionId: 3dc944a4-c8ec-45c0-9c77-dfcacd50c4da
  modified: 2026-09-24T02:14:54.794Z
---

On 2026-09-23 Lorenzo pointed out that an overnight build I estimated at 1 to 1.5 hours ran about 12 hours. Most review rounds found real bugs, but several late rounds (Upwork price-wording U5 to U9) were optional polish that kept the session going.

**Why:** he plans his day around the estimate and wants a clear stopping point; an open-ended loop of optional reviewer suggestions costs him time and tokens.

Later the same day he added: "make sure we're not overtesting anything and spending unnecessary usage. A lot of this is just about getting a system that I can rely on up and running now, and then we can rigorously test later." So default to one normal `reviewer` pass per piece, reviewer-max only for changes that can put unapproved text in front of a real lead or write live systems, a second round only for a defect of that kind, and park work that is not on the go-live path. Local test runs are cheap (no model usage); max-effort agents are the expensive part.

**How to apply:** estimate with review rounds included (each worker plus reviewer-max round is roughly 45 to 60 minutes), say when an estimate is blown, and treat reviewer "optional / non-blocking" items as report entries, not new rounds, unless they are safety issues. Related: [[feedback-max-parallel-agents]].
