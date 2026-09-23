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
2. **Map Instantly status to CRM stage** using this mapping:

| Instantly Status | CRM Stage | Notes |
|---|---|---|
| active | Contacted | In active campaign |
| paused | Contacted | Paused but was contacted |
| completed | Closed Lost | Sequence exhausted, no reply |
| bounced | Closed Lost | Bad email |
| unsubscribed | Closed Lost | Opted out |
| replied | Engaged | Any reply |
| interested | Engaged | Positive signal |
| not_interested | Closed Lost | Explicitly declined |
| wrong_person | Closed Lost | Wrong contact |
| meeting_booked | Booked | Scheduled via Instantly |
| meeting_completed | Discovery Done | Meeting happened |
| out_of_office | Contacted | Auto-reply |

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

- None yet — first deployment
