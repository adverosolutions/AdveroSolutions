# APPLIED

Applied: 20260930T221320
Before snapshot: /Users/lorenzovillarreal/Desktop/AdveroSolutions/.tmp/ai_agents_2026_09_30/before_20260930T221320.json

| campaign | key | id | verify |
|---|---|---|---|
| 2026 Bookkeeping & tax - AI Agents | bookkeeping_ai | e8867dbb-4f94-40ee-81c0-c11d7a256e2d | FAIL: link_tracking None != sent False |
| 2026 Insurance brokers - AI Agents | insurance_broker_ai | 8a50b4e8-48e7-4db2-aa8f-b2e75187a8be | FAIL: link_tracking None != sent False |
| 2026 Landscaping - AI Agents | landscaping_ai | 891bf2b5-9351-4cde-a5c4-13dd1d8ffce8 | FAIL: link_tracking None != sent False |
| 2026 Marketing agencies - AI Agents | marketing_agency_ai | 4eedb228-53c7-42ff-baf5-5b40c8646bd8 | FAIL: link_tracking None != sent False |
| 2026 MSP - AI Agents | msp_ai | 9b82c9ce-b772-440a-b4a0-b984fe6a7a3f | FAIL: link_tracking None != sent False |
| 2026 Pest control - AI Agents | pest_control_ai | 21f5568a-d82e-4280-8437-04b0f8d6df37 | FAIL: link_tracking None != sent False |

Pre-existing campaign statuses unchanged: yes

## Manual read-back 2026-09-30 (main session, after the apply)
- The only verify failure was `link_tracking None != sent False`. Instantly omits `link_tracking` from GET on these campaigns; the field is absent rather than true.
- Link tracking is off in practice: `text_only` is true, so nothing is tracked, and the copy has no links.
- All six campaigns are status 0 (draft), 12 inboxes, daily_limit 50, 2 steps (2 variants + 1), delays 3/3, `open_tracking` false.
- Every subject and body equals the dry-run payload byte for byte.
- No pre-existing campaign changed status.
