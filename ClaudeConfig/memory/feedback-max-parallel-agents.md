---
name: feedback-max-parallel-agents
description: "Lorenzo wants as many agents running in parallel as possible, with work split into small disjoint pieces; no stalling questions while he's away"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 5a6eeb0b-0a8e-4f7a-80da-80780c7ba0d5
  modified: 2026-09-23T04:57:51.488Z
---

**Parallel agents.** Lorenzo repeatedly asked (2026-09-22) to deploy "as many agents as humanly possible", splitting work into smaller pieces, including splitting one file's fixes across agents by function, then merging. Two agents at a time felt too slow to him.

**Why:** speed. He was watching a long build and saw serial work as wasted time.

**How to apply:**
- Split each build into pieces with disjoint file sets and write a shared contract (field names, function signatures) first.
- Run the builders and reviewers in parallel, and send interface facts to the other agents mid-flight.
- When he is asleep or away, don't ask him questions (it stalls the build). Park anything that needs his decision and put it in a morning report.
- On the night of 2026-09-22 he pre-approved unlimited worker-max rounds for any piece that fails review twice after worker-heavy.

Related: [[no-live-changes-until-tested]].
