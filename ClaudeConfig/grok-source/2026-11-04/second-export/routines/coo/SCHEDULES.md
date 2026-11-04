# COO routines: schedules (read 2026-11-04 1:40 PM CT, read-only get)
All times America/Chicago. Flexible = server picks a start inside the window (firesAt).

| Routine | Folder | Status | Schedule | Timing | firesAt |
|---|---|---|---|---|---|
| Instantly reply webhook | instantly-reply-webhook | enabled | webhook trigger | n/a | n/a |
| LinkedIn and Community watchdog | linkedin-and-community-watchdog | enabled | 0 8,17 * * 1-5 | flexible ±15 | 49 7,16 * * 1-5 |
| Morning roll-up to Lorenzo | morning-roll-up-to-lorenzo | enabled | 0 12 * * 1-5 | flexible ±15 | 50 11 * * 1-5 |
| Hourly follow-up leak sweep | hourly-follow-up-leak-sweep | enabled | 0 8-18 * * 1-6 | flexible ±15 | 6 8-18 * * 1-6 |
| Evening login check | evening-login-check | enabled | 0 18 * * 1-6 | flexible ±15 | 15 18 * * 1-6 |
| Community batch | daily-post-reminder | enabled | 0 11 * * 1-6 | flexible ±15 | 54 10 * * 1-6 |
| Upwork-first morning agenda 7:30 | morning-sales-first-agenda-8-and-10 | enabled | 30 7 * * 1-6 | flexible ±15 | 20 7 * * 1-6 |
| Upwork KPI noon check | upwork-kpi-noon-check | enabled | 0 12 * * 1-6 | flexible ±15 | 11 12 * * 1-6 |
| Interested-lead sequence runner | interested-lead-sequence-runner | enabled | */15 7-18 * * 1-6 | flexible ±7 | 6,21,36,51 7-18 * * 1-6 |
| Post-proposal sequence runner | post-proposal-sequence-runner | enabled | 5,35 7-18 * * 1-6 | flexible ±15 | 8,38 7-18 * * 1-6 |
| COO evening list | coo-evening-list | enabled | 30 18 * * * | flexible ±15 | 31 18 * * * |
| Mission Control refresh | mission-control-refresh | enabled | 15 8-18 * * 1-6 | flexible ±15 | 23 8-18 * * 1-6 |
| Growth dashboards refresh | growth-dashboards-refresh | enabled | 0 7,12,17 * * 1-6 | flexible ±15 | 11 7,12,17 * * 1-6 |
| Cancel GHL reminder 11/12 | cancel-ghl-reminder-11-12 | enabled | 0 10 12 11 * | exact | one-off |
| 90-day lead re-hit reminder | 90-day-lead-re-hit-reminder | enabled | 0 9 31 1 * | exact | one-off |
| Overnight lead loader 11/2 | overnight-lead-loader-11-2 | enabled, EXPIRED one-off | 0 0-6 2 11 * | flexible ±15 | 15 0-6 2 11 * |
| Bum energy drinks reminder | bum-energy-drinks-reminder | paused, EXPIRED one-off | 0 7 2 11 * | exact | one-off |

Webhook URL/key for the Instantly webhook live in the app, not exported.
Usage-saving cuts (frequency, Mission Control) are PROPOSED, NOT APPROVED.
