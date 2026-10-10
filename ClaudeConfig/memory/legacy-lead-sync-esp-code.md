---
name: legacy-lead-sync-esp-code
description: "Old Instantly->CRM sync (advero-lead-sync) IS deployed on Modal workspace adverosolutions; esp_code is the email provider, not delivery; fix + CRM correction change-set on branch fix/lead-sync-esp-code (2026-09-25)"
metadata:
  node_type: memory
  type: project
  originSessionId: c54c9ca9-3aad-4bec-887d-a1355927be29
  modified: 2026-09-26T02:47:30.600Z
---

`advero-lead-sync` is deployed in Modal workspace/profile `adverosolutions` (v1, 2026-03-04, cron `0 9 * * *` = 09:00 UTC), even though repo runbooks (MASTER_BUILD_REPORT, REREVIEW_2026-09-22, DECISIONS_FOR_LORENZO) call it not deployed. The default Modal profile on the Mac is `adverosolutionsbackup`, so `modal app list` without `MODAL_PROFILE=adverosolutions` hides it.

Instantly lead `esp_code` = recipient email provider (1 Google, 2 Microsoft, 3 Zoho, 999 Other, 1000 Not Found), never a delivery status. Lead `status` 3 = Completed (not replied); `lt_interest_status` 0 = Out of Office. Bounce signal is `status == -1` / FILTER_VAL_BOUNCED.

2026-09-25: sync fixed and `changesets/crm_stage_correction/` built (commits 987586d, 43164c5 on `fix/lead-sync-esp-code`, rebased on origin/main 1a488fa). Merged to main and pushed 2026-10-09 ([[sync-2026-10-09]]); still not deployed, not applied (runbook `runbooks/lead_sync_esp_code_fix.md`, steps need Lorenzo's terminal). Parked reviewer items: per-tab re-read before each batch_update, restore skipping never-sent tabs and checking Last Updated, get_campaigns repeated-cursor guard, rule-order tests.

**Why:** the old sync marked Zoho leads "Closed - Lost" (terminal) and Microsoft leads "Contacted" pre-send in HVAC/Roofing tabs.
**How to apply:** stop or redeploy the old app before any CRM correction apply, or it re-breaks rows next morning. See [[no-live-changes-until-tested]], [[instantly-2026-campaigns]].
