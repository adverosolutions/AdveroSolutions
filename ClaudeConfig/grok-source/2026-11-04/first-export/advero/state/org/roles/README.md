# Bot running docs (standing rule, Lorenzo 2026-10-21)
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Every bot keeps ONE running doc here: ~/advero/state/org/roles/<bot-slug>.md
Update it whenever a process, decision, schedule, or ongoing work item changes (at least at the end of any work session).
Sections:
1. Position: title, reports to, one-line mandate
2. What I do: responsibilities, routines (name, schedule CT, what each does)
3. Processes: step-by-step how I do each recurring job, tools/sources used
4. Rules and limits: Lorenzo's standing rules that apply to me (approvals, never-do list)
5. Decisions log: dated, what Lorenzo decided and why
6. Ongoing work: open items, waiting-on, next steps
7. Files and state: key paths, sheets (ids), logs
8. Handoff notes: what a replacement bot would need to pick this up cold
Keep it current; overwrite stale lines, keep the decisions log append-only.

## Cross-referencing (2026-10-21)
- All role docs live in this one folder and every bot can read all of them. INDEX.md lists them.
- Add a "Shared context" section to your doc: which teammates' docs you depend on and why.
- Before acting on a lead or client, follow ~/advero/state/clients/README.md (check, then log back).
- Before changing a process that hands work to or from another bot, read that bot's doc first.

## Org v3 (approved 2026-10-21)
- 20 bots in 5 branches plus Accounting and Revenue Operations; INDEX.md lists each bot, its manager, agent id and doc.
- Every doc's section 1 also names: single job, reports to, delegates to, room (with room id). Add a dated "Org v3 changes" note when your seat changes, and keep leak checks and handoff files in your doc.
- Hierarchy: Lorenzo to COO only; COO to managers, Accounting and Revenue Operations only; managers to their own bots. Bots in different branches never message each other; cross-branch handoffs are the documented files in ../ORG_STRUCTURE.md s3 rule 6.
- LinkedIn: only the named LinkedIn bots (LinkedIn Outreach Manager, LinkedIn Setter, Sales Nav Bot) open it, one at a time while holding ~/advero/bin/linkedin_gate (li-227).

