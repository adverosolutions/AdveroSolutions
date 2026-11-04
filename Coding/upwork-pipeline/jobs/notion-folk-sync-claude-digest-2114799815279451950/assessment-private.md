# Private assessment (not for the client)
- Open check 2026-10-26 3:15 PM CT: ACTIVE, can_apply true, 0 hired.
- Personalization (U-006): "Felix" appears as the client contact in 3 separate reviews (2026-09-21 "working with Felix", 2026-07-27 "you or Felix", 2026-06-21 "Felix was a great client"). source client_reviews, reviewCount 3. Not called owner. Business name "Sila Capital" appears in reviews only; not used in deck copy (UPWORK_PROCESS s5: no companies from review history).
- Post is a VA role, part-time. Budget exists; never mentioned.
- FLAGS for Lorenzo: post prefers Russian speaker (never claim), needs US Eastern hours through at least 2 PM ET (Lorenzo is Central; hours/week must come from him), screening asks education (only Lorenzo can answer), asks hours per week.
- No Notion or Folk adapter exists. Notion and Folk are not depicted natively; deck uses Claude Code transcript (post names Claude; Lorenzo works daily in Claude Code) plus the custom workbench ("Custom project workspace").
- Apps Script is shown only as a file Claude Code writes (sample), not a live deployment.

## Scene map (2-minute Standard)
1. Cover (~10s): Notion projects and Folk contacts kept in step, with a Monday stale-deal note.
2. claude-code workflow (~35s): purpose: show how the sync is built. New fact: Claude Code reads the Notion project fields and Folk fields, writes sync.gs (Apps Script), runs a dry run on 3 sample projects, flags one mismatch. Evidence: transcript stages + project context.
3. workbench record (~30s): purpose: show one synced record. New fact: Notion project row on left (source), Folk contact fields on right after sync, with events. Evidence: field values match.
4. workbench outcome (~35s): purpose: result. New fact: Monday digest with stale deals listed; sync run summary. Evidence: stages, metrics (illustrative counts), proof.
5. Close (~15s): three directional metrics + 15-min call.
