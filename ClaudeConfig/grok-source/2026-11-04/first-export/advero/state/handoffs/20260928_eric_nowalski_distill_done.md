# Eric Nowoslawski — Claude distill complete

**Date:** 2026-09-28 23:08 CDT  
**Channel:** https://www.youtube.com/@ericnowoslawski  
**Transport:** Claude Code CLI (`claude -p --model opus`), Max subscription  
**ANTHROPIC_API_KEY:** unset (subscription only)

## Counts

| Metric | Value |
|--------|-------|
| Videos distilled | **51** / 51 |
| Batches | **11** (size 5; last batch size 1) |
| Playbook `.md` files | **11** |
| Companion `.sources.json` | **11** |
| Status ok | **11** |
| Skipped | 0 |
| Failures | **0** |
| Wall time (sum of Claude calls) | ~14 min |
| Total playbook bytes | 167,534 (~164 KB) |

## Playbook files

- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_01_of_11.md` (19,440 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_02_of_11.md` (18,645 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_03_of_11.md` (15,242 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_04_of_11.md` (16,361 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_05_of_11.md` (12,758 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_06_of_11.md` (16,496 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_07_of_11.md` (15,165 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_08_of_11.md` (13,954 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_09_of_11.md` (20,205 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_10_of_11.md` (13,293 B)
- `~/advero/knowledge/eric-nowalski/playbooks/playbook_batch_11_of_11.md` (5,975 B)

### Themes (H1 from each batch)

- `playbook_batch_01_of_11.md` — Playbook batch: Agent-run cold email ops (Grok Bot + Clay CLI), cheap layered data, and 5-level deliverability
- `playbook_batch_02_of_11.md` — Playbook batch: AI-orchestrated list building, signal selection, and agentic campaign ops (post-Apollo stack)
- `playbook_batch_03_of_11.md` — Playbook batch: Claude Code + Clay pipelines for TAM-first, signal-driven, self-optimizing outbound
- `playbook_batch_04_of_11.md` — Playbook batch: Claude Code/Codex as the outbound engine (skills, sub-agent personalization, DIY scrapers, email finding, job-description signals)
- `playbook_batch_05_of_11.md` — Playbook batch: Colleague-style subject lines, signal mining on positive replies, AI research chains, and 3 north-star metrics
- `playbook_batch_06_of_11.md` — Playbook batch: Offer-first optimization, data-backed benchmarks, 2-email follow-ups, and the "Creative Ideas" + Clay/Claude supply chain
- `playbook_batch_07_of_11.md` — Playbook batch: List-building source selection (Sales Nav, look-alikes, Google Maps, custom scrapes, agents) + Claude Code as a campaign-testing engine
- `playbook_batch_08_of_11.md` — Playbook batch: AI lead magnets, signal-based lists, and cheap AI list scoring (2026)
- `playbook_batch_09_of_11.md` — Playbook batch: First principles, research-driven "alpha" copy, and Cursor-automated list/infra ops
- `playbook_batch_10_of_11.md` — Playbook batch: Cursor as the GTM build layer (Maps scrapes, Python + OpenRouter enrichment, campaign ops) + Clay operating rules
- `playbook_batch_11_of_11.md` — Playbook batch: Disposable-inbox deliverability ops (end-2025 SOP)

## Failures

_None. All 11 batches returned rc=0 with substantial markdown (>5KB each)._

## Quality notes

- Structure follows requested sections: frameworks, copy formulas, offer angles, list-building, deliverability, metrics, tools, caveats; plus source-video footer.
- Items tagged with `[video_id]` for traceability back to transcripts.
- Batch 11 is a single deliverability video (`V5k2uY9T-Eg`) — shorter but complete.
- Content is tactical (templates, signal tiers, Clay/Claude workflows, Instantly-adjacent infra) suitable for Advero Copywriter reuse.
- Spot-check: batches 01 (Grokbot/agency systems), 06 (response rates / 500k campaign / Claude+Clay), 11 (deliverability update) all readable and non-empty.
- Not a single unified mega-playbook — 11 thematic batches. Optional later step: Claude merge into one master playbook (separate go/no-go).

## Paths

- Playbooks: `~/advero/knowledge/eric-nowalski/playbooks/`
- Runner: `~/advero/knowledge/eric-nowalski/scripts/04_distill_claude.py` (shell wrapper `.sh`)
- Summary JSON: `~/advero/knowledge/eric-nowalski/logs/distill_summary.json`
- This handoff: `~/advero/state/handoffs/20260928_eric_nowalski_distill_done.md`

## Not done (by design)

- Whisper install
- Master consolidated playbook
- Pushing content into Instantly / GHL / Copy Doc
