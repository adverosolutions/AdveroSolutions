---
name: upwork-quality-overhaul-2026-09
description: "Why Upwork props read generic (hollow params, cloned charts, no client detail) and the 2026-09-22 overhaul decisions: quality in what the client SEES, then speed"
metadata:
  node_type: memory
  type: project
  originSessionId: db551e75-45d4-461e-8eba-556c8fab2d9a
  modified: 2026-09-22T23:03:47.337Z
---

Trigger: 2026-09-21 client Mark Firth replied "you pasted the wrong loom, that's a
generic loom". Lorenzo: "the market is always correct"; optimize only quality
(builds worth thousands, unmistakably for that client) then speed.

Evidence found 2026-09-22: 28 of 31 specs had no node params, so compiled nodes were
placeholder defaults (example.com URLs, prompt = label, Slack with no channel);
Mark's chart matched an older client's chart on 9 of 14 steps; no beat 1 ever named
the client. The two wins (Treasure Labs chart echoing every line of the post;
Jennifer shown a real live system) were the most specific props.

**Why:** generic props lose to specific ones; the proposal CSV had no outcome data
to show it, so an outcome sync from the Upwork connector was added.

**How to apply:** dossier.md per job first; spec from the dossier; client's-eye
reviewer gate (both scores >= 8); `verify_job` lint. Decisions: keep the proposal
copy template and four P.S. bullets as is; Zapier skipped (chart); GHL fully
automated incl. pipelines via a Private Integration token.

Scope correction (Lorenzo, 2026-09-22 evening): specificity lives in what the client
sees (node titles, section labels, overview sticky, chart, beats, every requirement
answered in their words and order). He rarely opens a node, so do not trade speed
for field-level polish; n8n and Make "weren't broken". Params only on the core AI
step and the call to a tool the client named. Field-level lint WARNs never send a
build back. Don't overbuild the checker.

Client intel (added 2026-09-22): the Upwork connector returns only review scores, no
text or names. The job page in his Chrome (Claude in Chrome, Cloudflare wait clears
itself in ~5 s; built-in browser is blocked) shows the full review history;
freelancers name the client (Cal.com client = "Jordan", 7 mentions). Used for the
greeting name and an A-D client grade so C/D clients are skipped before building.
The page tool truncates strings over ~1,000 chars and arrays over ~100 items, so the
page snippet must parse in-page and return a compact object.

Client intel PAUSED (Lorenzo, 2026-09-22 late): after two review failures on name
extraction (regex picked 'Talk', 'Brightpath', 'Min'), he chose to skip it entirely until
he revisits it. Docs carry a PAUSED note; code restored to the reviewed pre-max state
(49 tests). A stopped max round's partial work (script returns name candidates with
evidence sentences, main session picks the name) is saved in
.tmp/upwork-overhaul-baselines/ci_max_partial_stopped/ if he wants it back.

Final state (2026-09-22 night): every piece reviewed and APPROVED - n8n/Make compilers,
speed tools (verify_job, batch, finalize, outcome sync), docs, GHL compiler (one tag per
step; a gate's explicit negate always wins; negation never read inside quoted tag names),
ghl_prereqs after 4 max rounds (5xx on a create = 'possibly created'; spec GHL names must
be plain ASCII). Rollback copies in .tmp/upwork-overhaul-baselines/*.pre_*; the overhaul
files are committed as ONE commit 1bdb998 on local branch `upwork-overhaul` (56 files,
parent revenue-automation 19081ab; rewritten overnight 2026-09-23 with his approval to
drop a GHL storage-link token from history, replacing 8781607; built with a temp
GIT_INDEX_FILE so his working copy stayed on revenue-automation). Not committed: job
folders, out/, runs.csv, heatmap, PROFILE/RUBRIC. Merging to main is his call.
Overnight 2026-09-23 also: GHL compiler locked to his saved reference export
(reference/ghl_export_reference_all_types.json); ghl_prereqs hardened (8-endpoint
allowlist, no redirects, HTTPS/host pin, named User-Agent, token never echoed); live
read-only dry run passed with his narrow 8-scope key (contacts -> 401).

The five 2026-09-22 jobs were scrapped, not rebuilt; the goal became a flawless
system for the next day's batch. Plan: `~/.claude/plans/swift-splashing-peacock.md`.
See [[upwork-ghl-demo-disadvantage]], [[upwork-batch-mode]], [[upwork-proposal-copy]].
