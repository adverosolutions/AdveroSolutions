# Spintax RANDOM fix apply log — Instantly live campaigns

**When:** 2026-10-02 ~07:58 CT
**Root cause:** Instantly needs `{{RANDOM | a | b}}`, not `{a|b}`. Diagnosis: `20261002_spintax_diagnosis.md`.
**Backup dir:** `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/`
**Converter:** classic `(?<!{){([^{}]+\|[^{}]+)}(?!})` → `{{RANDOM | opts}}` with spaces around `|`; merge tags and existing RANDOM left alone.
**PATCH payload:** full `sequences` + full `email_list` (API replaces both whole).
**Stopped early:** False. **Restores:** none.
**Preview API:** none used; Instantly UI preview still recommended.

| Campaign | ID | Spins converted | PATCH ok? | Leftover classic | {{RANDOM}} after | email_list | Backup | Error |
|---|---|---|---|---|---|---|---|---|
| 2026 Cleaning - Client Reactivation | `8086b41e-b546-4b36-9fa0-2d01f5cc119a` | 18 | **ok** | 0 | 18 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/8086b41e-b546-4b36-9fa0-2d01f5cc119a.json` |  |
| 2026 Cleaning - Trigger Outbound | `f347604e-48c7-4813-831c-dc7b9d4b50ae` | 18 | **ok** | 0 | 18 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/f347604e-48c7-4813-831c-dc7b9d4b50ae.json` |  |
| 2026 Bookkeeping - Client Reactivation | `f00c5e28-fdc4-4d84-a7e6-dfba9695f35d` | 12 | **ok** | 0 | 12 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/f00c5e28-fdc4-4d84-a7e6-dfba9695f35d.json` |  |
| 2026 Bookkeeping - Trigger Outbound | `87ebb167-9b64-4b6f-b658-88f3d1af9980` | 13 | **ok** | 0 | 13 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/87ebb167-9b64-4b6f-b658-88f3d1af9980.json` |  |
| 2026 Recruiting - Client Reactivation | `1d4d5bb3-40a7-4333-bf34-b269d2cc9955` | 12 | **ok** | 0 | 12 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/1d4d5bb3-40a7-4333-bf34-b269d2cc9955.json` |  |
| 2026 Recruiting - Outbound (specialty roles) | `cd2e251c-3b5a-40d2-a3dc-d07c4004a48c` | 12 | **ok** | 0 | 12 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/cd2e251c-3b5a-40d2-a3dc-d07c4004a48c.json` |  |
| 2026 Bookkeeping & tax - AI Agents | `e8867dbb-4f94-40ee-81c0-c11d7a256e2d` | 9 | **ok** | 0 | 9 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/e8867dbb-4f94-40ee-81c0-c11d7a256e2d.json` |  |
| 2026 Service - AI Agents | `d81f1d53-23d6-48a6-aea3-80c21192e17e` | 11 | **ok** | 0 | 11 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/d81f1d53-23d6-48a6-aea3-80c21192e17e.json` |  |
| 2026 MSP - AI Agents | `9b82c9ce-b772-440a-b4a0-b984fe6a7a3f` | 9 | **ok** | 0 | 9 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/9b82c9ce-b772-440a-b4a0-b984fe6a7a3f.json` |  |
| 2026 Insurance brokers - AI Agents | `8a50b4e8-48e7-4db2-aa8f-b2e75187a8be` | 9 | **ok** | 0 | 9 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/8a50b4e8-48e7-4db2-aa8f-b2e75187a8be.json` |  |
| 2026 Landscaping - AI Agents | `891bf2b5-9351-4cde-a5c4-13dd1d8ffce8` | 9 | **ok** | 0 | 9 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/891bf2b5-9351-4cde-a5c4-13dd1d8ffce8.json` |  |
| 2026 Recruiting - AI Agents | `59b20790-12bb-446d-bcd6-e3b6f9a61953` | 12 | **ok** | 0 | 12 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/59b20790-12bb-446d-bcd6-e3b6f9a61953.json` |  |
| 2026 Marketing agencies - AI Agents | `4eedb228-53c7-42ff-baf5-5b40c8646bd8` | 9 | **ok** | 0 | 9 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/4eedb228-53c7-42ff-baf5-5b40c8646bd8.json` |  |
| 2026 Pest control - AI Agents | `21f5568a-d82e-4280-8437-04b0f8d6df37` | 9 | **ok** | 0 | 9 | 12→12 | `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/21f5568a-d82e-4280-8437-04b0f8d6df37.json` |  |

## Totals
- Campaigns fixed: 14/14
- Total spins converted: 162
- Cold six: all ok
- AI Agents (8): Bookkeeping & tax, Service, MSP, Insurance brokers, Landscaping, Recruiting, Marketing agencies, Pest control — all ok

## Notes
- Subjects and A/B variant structure unchanged.
- Merge tags `{{firstName}}` / `{{companyName}}` / `{{personalization}}` / `{{specialty}}` counts unchanged before→after.
- Campaign pause/activate status not changed by this PATCH.
- Workspace artifacts: `/workspace/instantly_spintax_fix/{id}_{before,after,payload}.json`
