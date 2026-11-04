# Team running docs index (all readable by every bot; shared box filesystem)
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Org v3, APPROVED 2026-10-21 (Lorenzo 12:07 CT). Chart, agent ids and room ids: ../ORG_STRUCTURE.md. Rollout of routine changes: ../ROLLOUT_20261021.md.

| Bot | Branch | Reports to | Agent id | Doc |
|---|---|---|---|---|
| COO / Chief of Staff | Ops | Lorenzo | 732ca015-c7c3-412e-92f7-f9b2de73d050 | coo.md |
| Upwork Coordinator (mgr) | Upwork | COO |  | upwork-coordinator.md |
| Demo Builder (Demo Build Manager duty) | Upwork | Upwork Coordinator |  | demo-builder.md |
| Cold Email Manager (mgr) | Cold Email | COO | 027f41ab-4ca3-4daa-afb1-708ab41d36a3 | cold-email-manager.md |
| Deliverability Specialist | Cold Email | Cold Email Manager |  | deliverability-specialist.md |
| Appointment Setter | Cold Email | Cold Email Manager | bd8d5b35-c4bc-43bd-bebc-dffeb32b1838 | appointment-setter.md |
| ~~Copywriter (PARKED)~~ REMOVED 2026-10-30 | Cold Email | Cold Email Manager |  | copywriter.md |
| Lead Gen Manager (mgr, was Lead Generation Specialist) | Lead Gen | COO | 9704b4a8-4a3f-4af8-9db0-65997f6745f9 | lead-generation-specialist.md |
| QuickEnrich Bot | Lead Gen | Lead Gen Manager | 32720104-f197-4e05-a13e-c224bfba9e7f | quickenrich-bot.md |
| Maps Bot | Lead Gen | Lead Gen Manager | 51582e73-37a0-403c-9a32-ca9ed612c4b6 | maps-bot.md |
| Vollna Bot | Lead Gen | Lead Gen Manager | 181ceaab-0c45-4e5e-8306-30a1030822d9 | vollna-bot.md |
| Sales Nav Bot (named LinkedIn bot, li-227) | Lead Gen | Lead Gen Manager | 01fd0c69-89cd-4b0b-9d7a-5f515f534de5 | sales-nav-bot.md |
| LinkedIn Outreach Manager (mgr, delegator, named LinkedIn bot) | LinkedIn | COO | 77efa803-a8b3-4c01-93e4-f94897abdd35 | linkedin-outreach-manager.md |
| LinkedIn Setter (named LinkedIn bot, li-227) | LinkedIn | LinkedIn Outreach Manager | 17766568-c28d-4b58-afba-c695b215c8f2 | linkedin-setter.md |
| LinkedIn Content Manager (weekly) | LinkedIn | LinkedIn Outreach Manager |  | linkedin-content-manager.md |
| Community Manager (mgr) | Community | COO |  | community-manager.md |
| Community Engagement Bot | Community | Community Manager | b19d90a5-088a-4b71-8ad8-08e8d82730fa | community-engagement-bot.md |
| Community Content Bot | Community | Community Manager | f3b4967d-2135-410b-b3a0-6f3fbf58e8fb | community-content-bot.md |
| Accounting | Cross-branch | COO |  | accounting.md |
| Revenue Operations | Cross-branch | COO |  | revenue-operations.md |
| ~~Committee: Simplicity~~ REMOVED 2026-10-30 | Cross-branch (Committee) | COO | 3167ba18-4cef-41e1-93f6-8968c19eddce | committee.md |
| ~~Committee: Revenue Impact~~ REMOVED 2026-10-30 | Cross-branch (Committee) | COO | b11348fc-9e60-4523-ad52-1c2640d8d609 | committee.md |
| ~~Committee: Risk and Reversibility~~ REMOVED 2026-10-30 | Cross-branch (Committee) | COO | ee37f7a8-6939-4ee8-879d-c0f420adbcc7 | committee.md |
| ~~Committee: Time Cost~~ REMOVED 2026-10-30 | Cross-branch (Committee) | COO | 8a8b471f-41f6-4073-a318-017a63352c74 | committee.md |
| ~~Committee: Compounding~~ REMOVED 2026-10-30 | Cross-branch (Committee) | COO | f5372601-4c96-4e49-9ea4-494a86c0a8bd | committee.md |
| Cold Email Split Test Bot (DRAFT) | Cold Email | Cold Email Manager | 75a2e8de-59d0-4978-9210-92b89f2c6f5c | split-test-bots.md |
| ~~LinkedIn Split Test Bot (DRAFT)~~ REMOVED 2026-10-30 | LinkedIn | LinkedIn Outreach Manager | 0caa3496-04d1-4ccc-98d1-9f1b4eb5d531 | split-test-bots.md |
| ~~Upwork Split Test Bot (DRAFT)~~ REMOVED 2026-10-30 | Upwork | Upwork Coordinator | e5547dce-42e7-4a4a-be1e-93350ef0d71a | split-test-bots.md |
| ~~Community Split Test Bot (DRAFT)~~ REMOVED 2026-10-30 | Community | Community Manager | daaaaa93-0e01-43a4-8cbb-3008bdd113f0 | split-test-bots.md |

Rooms: Upwork team 7f9c1b53-30ee-430e-8830-6caf3740782e; Cold Email team 67666b1b-7a52-4505-83fc-c44421a655c7; Lead Gen team 37c5a01a-616f-4ac9-807a-d1d35be4ae25; LinkedIn team 8e5c3d92-7d4b-47e8-9197-7665a468ef40; Community team d5214bab-7fb7-49ca-b6c6-5f9dda230744; Committee team e66b0ee4-23ce-4eed-895d-ed38cf2077e7 (LIVE, five Committee seats, on demand; COO not a member). Split Test Bots are not yet in their branch rooms (add refused; Lorenzo deciding).
LinkedIn: only the three named LinkedIn bots open it, one at a time via ~/advero/bin/linkedin_gate (li-227).
Shared client/lead context: ~/advero/state/clients/ (see README there).
RETIRED 2026-10-30 (seats removed): procedures for the Committee and Split Test Bots (significance p < 0.05, minimum samples, data sources, cadence): ../BOT_PROCEDURES.md. Draft bots stay idle until Lorenzo says go.
