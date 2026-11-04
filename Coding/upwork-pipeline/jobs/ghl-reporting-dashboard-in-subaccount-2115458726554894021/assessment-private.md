# Private assessment: GoHighLevel Reporting Specialist (~022115458726554894021)
Worker N=3, saved-jobs batch 2026-10-28, legacy sales-deck template. U1 opener A. Boost 70.
Open check 11:08 CT: find_jobs get, workFlowState ACTIVE, can_apply true, 0 hired.

## Scene map (2-minute Standard route)
| Stop | Purpose | New fact | Visible evidence | Seconds |
| --- | --- | --- | --- | --- |
| Cover | Frame the ask | Report lives inside each sub-account | Title, anchors, 4 preview steps | 10 |
| 1 morning-refresh (workbench architecture) | How data gets there | Daily sync, per-sub-account storage, shown in GHL menu | 5-node path, context states | 25 |
| 2 email-table (ghl outcome) | Their #1 named requirement | One row per campaign with all 6-7 stats | 4 campaign rows, 3 totals, date filter note | 30 |
| 3 marketing-summary (ghl outcome) | Rest of required reporting | Meta Ads, organic, GA, pipeline same period | 6 tiles, period/visibility fields | 25 |
| 4 next-client (workbench record) | Replication without dev | Snapshot + form setup, checked, isolated | Setup guide fields, 4 events | 20 |
| Close | Goals + CTA | 3 directional metrics, 15-min call | Metrics, blue CTA | 10 |

## Choices
- Dashboard shown on the GHL outcome surface (GHL nav, "Dashboard" chrome) because the client strictly wants it viewed inside GHL. Behind-the-scenes sync and the team setup checklist are on workbench (custom project workspace), never a vendor screen. No n8n/Make: post names neither, and the catalog has no schedule trigger.
- Email table uses outcome fields rows (one label/value row per campaign); totals as metric tiles.
- Personalization omitted: "Darren" appears in one review only (needs two).
- Sample data: Larkfield Physio (sample client), Northgate Fitness Studio (second sample sub-account), Priya (sample agency team member). All figures invented, labelled illustrative.

## Risks / unknowns
- GHL API coverage of per-campaign email stats (recipients, delivered, unsubscribes) unverified; flagged as pilot confirmation.
- Custom menu link iframe + sub-account context for data isolation is the planned approach; secure identity check (e.g. marketplace app SSO) to confirm in pilot.
- Meta Ads layout to mirror client's screenshots, not yet provided.
- Budget $500 fixed vs large scope; client spend $280.80.
