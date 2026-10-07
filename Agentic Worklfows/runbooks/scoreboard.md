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

Live URL: https://claude.ai/artifact/7i5vMdwy4aHPf9xrKG6nDr (private to Lorenzo).

The page writes only to its own `db` store, which is readable only by the owner and editors (rule: root `read: admin`, `write: owner`):

- `linkedinRows/<id>`: the LinkedIn tracker rows. They are written only when Lorenzo acts in the tracker, never on load.

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

`tests/ui.test.js` renders the page in jsdom. It loads jsdom from `JSDOM_PATH`, or from `~/.hermes/hermes-agent/node_modules` on Lorenzo's laptop. If neither is available it skips with a reason; if `JSDOM_PATH` is set but cannot load, it fails.

Publish from a Claude Code session with the Artifact tool:

- `file_path`: `Coding/scoreboard/scoreboard.html`
- `files`: `{"scoreboard-data.js": "Coding/scoreboard/scoreboard-data.js"}`
- The `capabilities` manifest is `mcp` (the four servers and their tools, as listed in `CONFIG.tools`), plus `db` and `user`.
- Republishing the same page keeps its link. Omit `capabilities` on a redeploy unless the tool list changed.
- To preview the UI without data, open the page with `#sample`. It then needs `tests/sample-model.js` next to it, which is never published.

A connector name or tool name that changes upstream shows up as a red chip in the top bar. The chip's text gives the fix (reconnect, add, or turn the connector on in the page's Permissions menu). Fix names in `CONFIG` in `scoreboard-data.js` and republish.

## LinkedIn tracker (channel 3)

LinkedIn has no API, and Lorenzo does every LinkedIn action by hand. The `linkedin-outreach` skill says the tracker lives in this dashboard, so the page keeps the rows itself, in db collection `linkedinRows` (one doc per person, id = the `/in/<handle>` slug). Fields, stages, reply types and follow-up timing come from that skill ("Follow-up timing", "Tracker fields and stages", "Weekly numbers"). If the skill changes, update `AdveroData.linkedin` (`FIELDS`, `STAGES`, `REPLY_TYPES`, `EVENTS`, `applyEvent`) and its tests together.

- **Daily use:** in Detail → LinkedIn tracker, pick an event in a row's "Log…" menu (DM sent A/B, FU1-FU3, Reply…, Answer sent, Meeting booked…). The page sets the stage, the dates and the next touch due per the skill. The row then shows in Follow-ups when the touch is due.
- **Bulk:** use "Paste rows" with a TSV or CSV that has a header row. The skill's field names and Sales Navigator style headers are accepted. Re-pasting someone already in the tracker updates their row and never resets their stage or dates. If a row changes after you paste (in another tab, or by a Refresh), the import leaves it as it is and says so. Row actions are locked while an import runs.
- **Claude** reads or writes the rows with the ArtifactData tool on this artifact's URL (collection `linkedinRows`). The rows are shared, durable data: pin writes with `if_version`. Every row Claude writes must carry `updatedAt` as a number in ms, because the page pages through rows by that field and a row without it can be skipped past the first 1,000.
- GHL cards tagged `linkedin` are also attributed to LinkedIn.

## Known limits

- Engine follow-up state (E1-E10 cadence, nurture, Upwork T-plan touch index) lives in the engine store, which is local JSON or a Modal Dict that the page cannot reach. The page shows GHL tasks, Upwork rooms and Instantly lead state instead.
- The Upwork build type per proposal (prototype, n8n, chart) lives in `proposals.csv` on the laptop. It is not joined yet.
- GHL has no Upwork pipeline yet (`ids.json` `ghl.pipelines.upwork` is null). Upwork deals show on the board only if they are added to the Sales pipeline.
