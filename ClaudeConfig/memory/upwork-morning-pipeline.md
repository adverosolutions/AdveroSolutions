---
name: upwork-morning-pipeline
description: RETIRED — the Upwork discovery/scoring/monitoring half was removed 2026-08-17; the system now only generates creatives and proposal copy
metadata: 
  node_type: memory
  type: project
  originSessionId: b4d10cb0-4b89-4132-a193-8c07de7ccd4c
  modified: 2026-08-17T18:23:57.784Z
---

**Retired 2026-08-17.** `/upwork-morning` and `/upwork-pulse` were moved to
`~/.claude/skills-archive/`. Do not re-arm the pulse cron, do not propose
job monitoring, ranking or push notifications.

**Why:** Lorenzo asked Nick Saraev in Maker School how to structure his day.
Nick, Maximilian Lesek and Tre Heart all said the same thing — stop being
always-on, batch applications into two short blocks, mitigate context switching.
Max noted he goes back a couple of hours into the feed and still wins those
jobs. The pulse existed to keep Lorenzo reactive, which was the exact problem.
He also decided the AI adds nothing to finding and vetting jobs; he does that
himself now.

**What replaced it:** two manual blocks a day at **8:00 AM and 4:00 PM Central**,
chosen from a posting heat map (71 jobs, 4 days, `upwork-pipeline/postings.csv`,
visual at `posting-heatmap.html`). That pair minimises staleness: average job is
5.2h old when seen, 85% under 8h. Postings plateau 06:00–16:00 CT, peak 10:00–12:00.

**What the system still does:** `/upwork` only — builds the workflow/diagram/
mockup and writes the proposal copy. See [[upwork-proposal-copy]] and
[[upwork-proposal-assessment]].

**Logging:** `upwork-pipeline/proposals.csv` is now the evidence base, one row
per proposal handed over. The old `applications.csv` (renamed
`applications-scoring-log-ARCHIVED.csv`) held 137 scored jobs and exactly one
recorded submission, so no question about timing or copy could be answered from
it. Real numbers as of 2026-08-17: **25 applications sent, 2 views, 0 replies.**

Related: [[upwork-workflow-generator]], [[maker-school-digest]]
