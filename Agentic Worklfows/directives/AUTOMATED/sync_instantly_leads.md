# Sync Instantly Leads (AUTOMATED)

**Trigger:** Daily at 9:00 AM CT + on-demand
**Frequency:** Once per day (automated), or manual trigger
**System:** Automated via scheduled webhook / CLI

---

## Purpose

Pull all lead statuses from Instantly across every active campaign and reconcile with the Master CRM (Google Sheet). Ensures `current_stage`, `stage_updated_at`, and `last_reply_at` are always accurate and up-to-date.

This is the **single source of truth sync** — it catches anything missed by real-time reply webhooks or sequence tracking.

---

## Process

### 1. Load CRM Data (Batch)

- Call `bulk_get_all_leads()` on Google Sheets CRM
- Index all leads by email for O(1) lookup
- This avoids N+1 API calls to Google Sheets

### 2. Pull Leads from Instantly

- Get all campaigns via `get_campaigns()`
- For each campaign, paginate through all leads via `list_leads(campaign_id)`
- Collect email, lead_status, interest_value, replied flag, timestamps

### 3. Cross-Reference and Update

For each Instantly lead:

1. **Find in CRM** by email
   - If not in CRM → skip (lead was added outside our system)
2. **Map the Instantly lead to a CRM stage** with `determine_crm_stage()` in `execution/instantly_lead_sync.py`. It reads the lead's `status`, `lt_interest_status` (interest), `email_reply_count` and its contact timestamps, and takes the first rule that matches:

| # | When | CRM Stage |
|---|---|---|
| 1 | Lead unsubscribed (`status` -2) | Closed - Lost |
| 2 | Interest is Interested (1) | Replied - Positive |
| 2 | Interest is Meeting Booked (2) or Meeting Completed (3) | Meeting Scheduled |
| 2 | Interest is Won (4) | Closed - Won |
| 2 | Interest is Not Interested (-1), Wrong Person (-2) or Lost (-3) | Closed - Lost |
| 2 | Interest is No Show (-4) | No-Show |
| 3 | The lead replied and interest is anything other than Out of Office (0), including unset or a custom value | Replied - Neutral |
| 4 | Lead bounced (`status` -1) | Closed - Lost |
| 5 | Lead is Active, Paused or Completed (`status` 1, 2, 3) and an email step actually went out (`timestamp_last_contact`, `last_step_timestamp_executed` or `status_summary.lastStep.timestamp_executed` is set) | Contacted |
| 6 | Anything else (no email sent yet, or Skipped `status` -3) | no change |

   An Out of Office auto-reply (interest 0) is not a reply: that lead lands on rule 4 or 5. `status` 3 means Completed (the sequence finished), not replied.

   `esp_code` is **not used**. It is the recipient's email provider (0 In Queue, 1 Google, 2 Microsoft, 3 Zoho, 8 AirMail, 9 Yahoo, 10 Yandex, 12 Web.de, 13 Libero.it, 999 Other, 1000 Not Found), not a delivery status, so it says nothing about whether an email was sent, delivered or bounced.

3. **Check update rules:**
   - NEVER downgrade stages (Booked → Contacted = blocked)
   - NEVER overwrite terminal stages (Closed Won, Closed Lost)
   - Only update if proposed stage is higher priority AND is a valid transition per SOP-001
4. **Update CRM** if rules pass:
   - Update `current_stage` and `stage_updated_at`
   - If lead replied: update `last_reply_at`

### 4. Generate Summary

Print and log:
- Total leads in Instantly
- Matched in CRM
- Stages updated
- Reply timestamps updated
- Skipped (terminal / no change / would downgrade)
- Not in CRM
- Errors

---

## Tools Required

- `execution/instantly_lead_sync.py` — Main sync engine
- `execution/instantly_api.py` — Instantly API wrapper (uses `list_leads()`)
- `execution/google_sheets_crm.py` — CRM operations

---

## Usage

### Automated (daily)
Triggered via webhook at 9:00 AM CT. No inputs needed.

### Manual (CLI)
```bash
# Full sync — preview changes first
python execution/instantly_lead_sync.py --dry-run

# Full sync — live
python execution/instantly_lead_sync.py

# Single campaign only
python execution/instantly_lead_sync.py --campaign "HVAC Austin Q1"
```

---

## Edge Cases

- **Lead in Instantly but not in CRM**: Skip. Log count for visibility.
- **Lead in CRM but not in Instantly**: No action. Lead may have been added manually or through a different channel.
- **Instantly API rate limit**: Script uses pagination with reasonable page sizes (100). If rate limited, the request library will raise an error — retry on next scheduled run.
- **Google Sheets quota**: Bulk read in one call. Updates are individual (Google Sheets API allows ~60 writes/min). For large batches, this is acceptable for daily sync.
- **Duplicate emails across campaigns**: Process each campaign independently. The latest/highest-priority status wins due to the "never downgrade" rule.

---

## Error Handling

- If Instantly API fails: Log error, exit with non-zero code, alert
- If CRM connection fails: Log error, exit — do not partial-sync
- If individual lead update fails: Log, continue to next lead, include in error count
- If campaign fetch fails: Log, skip campaign, continue with remaining

---

## Learnings

_(Updated as the system runs and self-anneals)_

- **2026-09-25: `esp_code` is the recipient's email provider, not a delivery status.** Per the Instantly API v2 docs (https://developer.instantly.ai/api-reference/lead/list-leads.md, get-lead.md, move-leads-to-a-campaign-or-list.md): 0 In Queue, 1 Google, 2 Microsoft, 3 Zoho, 8 AirMail, 9 Yahoo, 10 Yandex, 12 Web.de, 13 Libero.it, 999 Other, 1000 Not Found. An MX check that day agreed for 24 of 25 sampled leads per group. The old code read 3 as "bounced" and 2 as "delivered", so Zoho-hosted leads were closed as "Closed - Lost" (a terminal stage the sync never leaves), Microsoft-hosted active leads were marked "Contacted" before any email went out, and Google-hosted and other leads were never marked "Contacted". The mapping no longer reads `esp_code`; contact is judged from the contact timestamps.
- **2026-09-25: lead `status` 3 is Completed, not replied.** The documented values are 1 Active, 2 Paused, 3 Completed, -1 Bounced, -2 Unsubscribed, -3 Skipped. The old code sent every Completed lead to "Replied - Neutral" even with 0 replies.
- **2026-09-25: `lt_interest_status` 0 is Out of Office, not neutral.** The documented values are 0 Out of Office, 1 Interested, 2 Meeting Booked, 3 Meeting Completed, 4 Won, -1 Not Interested, -2 Wrong Person, -3 Lost, -4 No Show (also in `config/instantly_api_contract.md`). An auto-reply no longer counts as a reply.
- **2026-09-25: `POST /leads/list` takes `campaign`, not `campaign_id`.** `list_leads()` sent `campaign_id`, which is not a documented field, so the per-campaign pulls may have returned leads from the whole workspace. It now sends `campaign` (the Python parameter is still `campaign_id`).
- **2026-09-25: the campaigns list is now paginated.** `get_campaigns()` made one GET and kept only the first page; it now asks for `limit=100` pages and follows `next_starting_after` until the cursor is absent or a page is empty.
