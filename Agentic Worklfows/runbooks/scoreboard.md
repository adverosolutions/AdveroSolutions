# Runbook: Advero Scoreboard (marketing + sales dashboard)

Lorenzo's daily dashboard and the source of truth for marketing and sales, built 2026-10-06. It is a private claude.ai Artifact page in the Spatial look. It reads four claude.ai connectors live, with Lorenzo's own credentials, through the Artifact `mcp` capability. There is no server and no scheduled job, and the page holds no API keys.

Code lives in `Coding/scoreboard/`. `SPEC.md` is the full contract: every call, formula, threshold and model field.

| File | What it is |
| --- | --- |
| `scoreboard.html` | The page (Spatial UI, all CSS inline) |
| `scoreboard-data.js` | The data layer: connector calls, metric math and the model the page renders |
| `tests/` | `node --test` suite on synthetic fixtures, plus `sample-model.js` for a local preview |

## What it reads

| Connector | Calls (all reads) | Feeds |
| --- | --- | --- |
| Instantly | campaign overview (range and previous range), daily analytics, per-campaign analytics, campaign list, interested and meeting-booked leads, unread count | Cold email funnel, rates, daily chart, campaign table, unanswered replies |
| Upwork | proposals (all statuses, paged), `get_room` per proposal in range, interview rooms, connects usage, earnings summary | Upwork funnel (proposals → client replied → offers → hired), reply rate, connects spend, revenue, rooms waiting on you, nudges due |
| GHL | `get-pipelines`, `search-opportunity` with tasks and notes (location `ebyNANPagaK7ycf1pfge`) | Sales board, days in stage, stale flags, tasks, show rate from the Call Booked pipeline, won revenue |
| Google Calendar | `list_events` on `lorenzovillarreal@adverosolutions.com`, range and next 14 days | Calls held and upcoming. Event descriptions are never read, because they hold Zoom passcodes |

The page writes only to its own `db` store:

- `settings/costs`: monthly spend per channel, entered in the Costs drawer.
- `upworkRooms/<proposalId>`: a cache of which proposals got a client room. A found room is kept for good. A missing room is re-checked after 12 hours while the proposal is under 30 days old.

It never writes to Instantly, Upwork, GHL or Calendar, so the live-write guard rules are not involved.

## Metric rules worth knowing

- Human replies are Instantly's `reply_count_unique`. Instantly counts auto-replies separately (`reply_count_automatic_unique`).
- An Upwork "client replied" means the proposal has a room. Only the client can open a room on a proposal, so this is the true reply rate. It replaces the blank `viewed/replied` columns in `proposals.csv`.
- Connects are costed at $0.15 each (`CONFIG.upworkConnectUsd`). Cost per booked call is (monthly cost × days / 30, plus Connects) ÷ calls booked.
- Thresholds come from the KPI table in the `daily-reports-and-metrics` skill:

  | Metric | Green | Alert |
  | --- | --- | --- |
  | Bounce | ≤1% | >2% |
  | Real reply rate | ≥1% | <1% |
  | Positive rate | ≥0.7% | <0.5% |
  | Positive → booked | ≥50% | <40% |
  | Upwork reply rate | ≥15% | <8% |
  | Show rate | ≥90% | <80% |

- Stale deals:

  | Stage | Amber | Rose |
  | --- | --- | --- |
  | New Reply/Lead | over 1 day | over 3 days |
  | Call Booked | over 7 days | — |
  | Proposal Sent | over 7 days | over 14 days |

- Upwork nudges follow the T-plan days (2, 4, 7, 11, 16, 23, 30). One shows when your message is the latest in the room and it has had no reply for 2 to 30 days.

## Change, test, publish

```bash
cd /Users/lorenzovillarreal/orca/workspaces/AdveroSolutions/madtom   # or any checkout
node --test Coding/scoreboard/tests/*.test.js
```

Publish from a Claude Code session with the Artifact tool:

- `file_path`: `Coding/scoreboard/scoreboard.html`
- `files`: `{"scoreboard-data.js": "Coding/scoreboard/scoreboard-data.js"}`
- The `capabilities` manifest is `mcp` (the four servers and their tools, as listed in `CONFIG.tools`), plus `db` and `user`.
- Republishing the same page keeps its link. Omit `capabilities` on a redeploy unless the tool list changed.
- To preview the UI without data, open the page with `#sample`. It then needs `tests/sample-model.js` next to it, which is never published.

A connector name or tool name that changes upstream shows up as a red chip in the top bar. The chip's text gives the fix (reconnect, add, or turn the connector on in the page's Permissions menu). Fix names in `CONFIG` in `scoreboard-data.js` and republish.

## Adding LinkedIn (channel 3)

The LinkedIn column is a placeholder until outreach starts. Once a data source exists (an outreach tool with a claude.ai connector, or GHL opportunities tagged `linkedin`):

1. Add a fetcher in `scoreboard-data.js` that fills the `linkedin` channel funnel. The steps are requests, accepted, replies, positive and booked.
2. Add the connector to the manifest and republish.

GHL cards tagged `linkedin` are already attributed to LinkedIn.

## Known limits

- Engine follow-up state (E1-E10 cadence, nurture, Upwork T-plan touch index) lives in the engine store, which is local JSON or a Modal Dict that the page cannot reach. The page shows GHL tasks, Upwork rooms and Instantly lead state instead.
- The Upwork build type per proposal (prototype, n8n, chart) lives in `proposals.csv` on the laptop. It is not joined yet.
- GHL has no Upwork pipeline yet (`ids.json` `ghl.pipelines.upwork` is null). Upwork deals show on the board only if they are added to the Sales pipeline.
