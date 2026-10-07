# Advero Scoreboard: build spec (2026-10-06)

Lorenzo's daily marketing + sales dashboard and his single source of truth.
It replaces clicking around GoHighLevel. It is a private claude.ai Artifact page
that reads his own connectors live through the Artifact `mcp` capability: no server,
no API keys in the page. It is read-only towards every connector. The only writes
go to the page's own `db` store: cost settings and a small Upwork proposal-room cache.

## Files (all in `Coding/scoreboard/`)

| File | Owner | Published? |
|---|---|---|
| `scoreboard.html` | UI worker | yes: the page itself, with all CSS inline |
| `scoreboard-data.js` | data worker | yes: a supporting file loaded with `<script src="scoreboard-data.js"></script>` |
| `tests/data.test.js` + `tests/fixtures/*.json` | data worker | no |
| `tests/sample-model.js` | UI worker | no. A synthetic model, used only for a local preview of the UI |
| `SPEC.md` | orchestrator | no |

Neither worker edits the other's files. The **model contract** below is the only interface between the two layers.

## Platform rules (both workers)

- Runtime contract 0.2.72. The type definitions are at
  `/private/tmp/claude-501/bundled-skills/2.1.292/5b82e8604205e6b20c8db8bb6187a521/artifact-capabilities/0.2.72/`
  (`claude.d.ts`, `mcp.d.ts`, `db.d.ts`, `user.d.ts`, `permissions.d.ts`). Read the ones you use; they are authoritative.
- Reach capabilities with `await window.claude.use("mcp" | "db" | "user")`. Each resolves to `null` when unavailable, so design for absence. Never read `window.claude.mcp` etc.
- The page must render fully without data: loading skeletons, then per-section states.
- The page is written WITHOUT `<!doctype>`, `<html>`, `<head>` or `<body>` (the publisher wraps it). Put `<title>Advero Scoreboard</title>` first, then `<link>` for fonts, then `<style>`, then the markup, then the scripts.
- CSP: external scripts only from cdnjs/jsdelivr/unpkg. Stylesheets only from Google Fonts. No fetch to other hosts. No `alert`/`confirm`/`prompt`. No `window.print`. Links out use real `<a href target="_blank" rel="noopener">`.
- **Every string that comes from a connector is untrusted.** Render it with `textContent` or an escaping helper, never `innerHTML`. Upwork wraps names and messages as `<untrusted_participant_content>\n...\n</untrusted_participant_content>`: strip that wrapper (data layer) and still render as text. GHL note `body` is HTML; use `bodyText` only.
- Python is not involved. Plain ES2020 JavaScript, no build step, no frameworks.

## Connectors (CONFIG in `scoreboard-data.js`, one place to fix names)

```js
const CONFIG = {
  servers: { instantly: "Instantly", upwork: "Upwork", ghl: "GHL", calendar: "Google Calendar" }, // display names; orchestrator confirms at publish
  tools: {
    instantly: { overview: "analytics_campaign_overview", daily: "get_daily_campaign_analytics",
                 campaignAnalytics: "get_campaign_analytics", campaigns: "list_campaigns",
                 leads: "list_leads", unread: "count_unread_emails" },
    upwork:    { proposals: "upwork__list_freelancer_proposals", messages: "upwork__get_messages",
                 financials: "upwork__get_freelancer_financials" },
    ghl:       { exec: "execute_operation" },
    calendar:  { events: "list_events" }
  },
  upworkOrg: "2081884703335585732",
  ghlLocation: "ebyNANPagaK7ycf1pfge",
  ghlSalesPipelineId: "GCBkIzFpung73cIDVPzn",
  ghlCallsPipelineId: "vNB4nHSeDZlu6URPbtmP",      // "Call Booked Pipeline": Call Booked / Cancelled / Showed / No Show
  calendarId: "lorenzovillarreal@adverosolutions.com",
  selfEmails: ["lorenzovillarreal@adverosolutions.com"],
  timeZone: "America/Chicago",
  upworkConnectUsd: 0.15,
  upworkTouchDays: [2, 4, 7, 11, 16, 23, 30],
  links: {
    upworkRoom: id => `https://www.upwork.com/ab/messages/rooms/${id}`,
    ghlContact: id => `https://app.gohighlevel.com/v2/location/ebyNANPagaK7ycf1pfge/contacts/detail/${id}`,
    ghlOpportunities: "https://app.gohighlevel.com/v2/location/ebyNANPagaK7ycf1pfge/opportunities/list",
    instantlyCampaign: id => `https://app.instantly.ai/app/campaign/${id}/analytics`,
    instantlyUnibox: "https://app.instantly.ai/app/unibox"
  }
};
```

## Data layer (`scoreboard-data.js`)

### Shape and API

```js
(function (root) {
  // ...
  const AdveroData = { CONFIG, load, buildModel, loadCosts, saveCosts, _internals /* pure helpers for tests */ };
  if (typeof module !== "undefined" && module.exports) module.exports = AdveroData; else root.AdveroData = AdveroData;
})(typeof globalThis !== "undefined" ? globalThis : this);
```

- `load(ctx, onUpdate) -> Promise<Model>`
  - `ctx = { rangeDays: 7|30|90, refresh: boolean, now: Date, mcp, db, user }`. The UI resolves `mcp`, `db` and `user` with `claude.use` and passes them in, so tests can pass fakes.
  - Fetch the four sources **in parallel**, each one fully isolated: one source failing never blocks or blanks another.
  - After each source settles, call `onUpdate(buildModel(raw, ctx))` (progressive render). Resolve with the final model.
  - `mcp === null`: resolve at once with every source in state `unavailable`.
- `buildModel(raw, ctx) -> Model` is pure (no I/O, `now` comes from `ctx`). `raw` holds per-source `{ state, data, error, storedAt }` plus `costs`.
- `loadCosts(db) -> Promise<{upwork, cold_email, linkedin}>` reads db doc `settings/costs` (numbers are monthly USD; missing means 0). `saveCosts(db, costs)` writes it. Both are no-ops returning defaults when `db` is null.

### Calling tools

- `callTool(server, tool, input, { cache: { staleTime: 300000, gcTime: 86400000, refresh: ctx.refresh } })`, then read `res.payload`. If `payload` is a string, `JSON.parse` it inside try/catch.
- Retry once only for `retryable: true` errors: wait `retryAfterMs`, or 1.5 to 3 s random when it is absent. Never loop.
- Concurrency: at most 4 in-flight calls per source.
- Record `storedAt` per source as the oldest `res.cache?.storedAt` seen, or the fetch time when no call was cached.
- Map each error to a source state. The model carries `error: { code, server, message, fix }`, where `fix` is the copy below with `{server}` filled in:
  - `needs_reauth` → "Reconnect {server} in claude.ai Settings → Connectors."
  - `server_not_connected` / `server_not_found` → "Add the {server} connector in claude.ai Settings → Connectors."
  - `selection_required` → "Choose which {server} connector this page should use when claude.ai asks."
  - `not_in_manifest` → "{server} is switched off for this page. Turn it on in the page's Permissions menu."
  - `blocked_by_policy` / `approval_required` → "Your organization's policy blocks {server} on this page."
  - `server_unavailable` / `upstream_error` / `rate_limited` / unknown → "{server} didn't answer. Press Refresh in a minute."
  - `tool_error` → "{server} returned an error: {message}" (message truncated to 160 characters)
  - `not_granted` / `capability_disabled` / `capability_removed` → state `unavailable`
- A source whose main call fails gets state `error`. A source where only a secondary call failed (for example the Instantly unread count) stays `ok` and adds a `warnings[]` entry.

### Dates

All day math uses `CONFIG.timeZone` (Central). The range is the last `rangeDays` calendar days ending today, inclusive: `start` = today − (rangeDays − 1). The previous range is the `rangeDays` days before `start`. Format dates as `YYYY-MM-DD` with `Intl.DateTimeFormat("en-CA", { timeZone })`. Write a tested helper for this.

### Source 1: Instantly (server `Instantly`)

Calls:
1. `analytics_campaign_overview {start_date, end_date}` for the range and again for the previous range. The payload is an object with these fields:
   `emails_sent_count, new_leads_contacted_count, contacted_count, reply_count_unique, reply_count_automatic_unique, bounced_count, unsubscribed_count, total_opportunities, total_opportunity_value, total_interested, total_meeting_booked, total_meeting_completed, total_closed`.
   - `reply_count_unique` already EXCLUDES auto-replies; Instantly reports those separately.
2. `get_daily_campaign_analytics {start_date, end_date}` → `{ result: [{ date, sent, new_leads_contacted, replies, unique_replies, replies_automatic, opportunities, unique_opportunities }] }`. Days with no sends are missing; fill them with 0.
3. `get_campaign_analytics {start_date, end_date}` (no ids; the `ids` param is broken) → `{ result: [{ campaign_id, campaign_name, campaign_status, leads_count, emails_sent_count, new_leads_contacted_count, reply_count_unique, reply_count_automatic_unique, bounced_count, total_opportunities }] }`. Accept a bare array too.
4. `list_campaigns {limit: 100}` → `{ items: [{ id, name, status, daily_limit, email_list[] }], next_starting_after }`. Page while `next_starting_after` is set, at most 5 pages.
   - Status labels: 0 Draft, 1 Active, 2 Paused, 3 Completed, 4 Running subsequences, -1 Accounts unhealthy, -2 Bounce protect, -99 Suspended.
5. `list_leads {filter: "FILTER_LEAD_INTERESTED", limit: 100}` and `list_leads {filter: "FILTER_LEAD_MEETING_BOOKED", limit: 100}` → `{ items: [{ id, email, first_name, last_name, company_name, campaign, lt_interest_status, timestamp_last_reply, timestamp_last_contact, timestamp_last_interest_change }] }`. One page each is enough.
6. `count_unread_emails {}` → `{ count }`. This call is secondary.

Derived:
- Funnel, in this order. Each step has a `prev` value from the previous range:

  | key | label | value |
  |---|---|---|
  | `sent` | Emails sent | `emails_sent_count` |
  | `leads` | New leads reached | `new_leads_contacted_count` |
  | `replies` | Human replies | `reply_count_unique` |
  | `positive` | Positive replies | `total_opportunities` |
  | `booked` | Calls booked | `total_meeting_booked + total_meeting_completed + total_closed` |
  | `won` | Closed | `total_closed` |

- Rates, with these thresholds:

  | key | label | formula | green | alert | in between |
  |---|---|---|---|---|---|
  | `reply_rate` | Reply rate | replies / leads | ≥ 1.0% | < 1.0% | n/a |
  | `positive_rate` | Positive rate | positive / leads | ≥ 0.7% | < 0.5% | watch |
  | `bounce_rate` | Bounce rate | `bounced_count / emails_sent_count` | ≤ 1.0% | > 2.0% | watch |
  | `positive_to_booked` | Positive → booked | booked / positive | ≥ 50% | < 40% | watch |

  - A denominator of 0 gives state `no_data`.
- `sending`: true when any campaign has status 1 AND the daily series shows `sent > 0` on either of the last 2 days.
- Daily series points: `{ date, a: sent, b: replies, c: unique_opportunities }`.
- Campaign rows: join the analytics rows with the campaigns list by id. Include campaigns with no sends in the range. Sort active first, then by sent descending.
- Interested leads, unanswered: `timestamp_last_reply > timestamp_last_contact` (absent counts as 0). These become follow-up items.

### Source 2: Upwork (server `Upwork`)

Every input carries `org_uid: CONFIG.upworkOrg`.

1. Proposals: `upwork__list_freelancer_proposals {action: "list", org_uid, params: {status, limit: 10, sort_field: "CREATEDDATETIME", sort_order: "DESC", cursor?}}`.
   - The payload is `{ data: { vendorProposals: { edges: [{ node }], totalCount } }, hasMore, next_cursor }`.
   - Each `node` has these fields: `id, boosted, auditDetails.createdDateTime.rawValue` (an ms string), `marketplaceJobPosting { id, content.title, url }`, `status { status, status_label, reason?.reason }`, `terms.connectsBid?` (only when boosted).
   - Pages can come back EMPTY while `hasMore` is true. Upstream merges active and archived records and the tool filters them, so keep paging.
   - Statuses and page caps:

     | status | max pages | when to stop early |
     |---|---|---|
     | `Accepted` (= submitted, active) | 12 | the oldest created on a page is before the previous-range start |
     | `Archived` (job closed) | 12 | same rule |
     | `Offered` | 3 | none |
     | `Hired` | 3 | none |
     | `Declined` | 3 | none |
     | `Withdrawn` | 3 | none |

   - Dedupe by `node.id`.
   - Keep proposals created in the range (and in the previous range, for `prev`).
2. Proposal → client reply. On a proposal only the client can open the room, so a proposal that has a room means the client replied.
   - For each proposal created in the range (and the previous range), call `upwork__list_freelancer_proposals {action: "get_room", org_uid, params: {proposal_id}}`.
   - The tool REJECTS with `tool_error` when there is no room; the error's message or result contains `NOT_FOUND`. Treat that as `roomId: null`, not as a source error.
   - On success, read the room id from the payload: look for `id` / `roomId` / `room.id` / `data.room.id`. Be defensive and log the payload shape once with `console.debug`.
   - Cache in db collection `upworkRooms`, doc id = proposal id: `{ roomId: string|null, checkedAt: ms }`.
     - A found room is permanent; never re-check it.
     - Re-check a `null` only when `checkedAt` is older than 12 h and the proposal is under 30 days old.
     - Write a doc only when its value changed, and only when `user?.can("data.write") !== false`.
     - Without db, call every time and keep the results in memory.
3. Rooms: `upwork__get_messages {action: "list_rooms", org_uid, params: {room_type: "INTERVIEW", limit: 100, cursor?}}`.
   - The payload is `{ data: { rooms: [...] }, hasMore, next_cursor }`. Page up to 3 times.
   - Room fields: `id, roomName` (wrapped), `lastActivity` (an ms string), `awaiting_reply_from` ("you" | "them" | absent), `last_message_from_self, contractId?, contractStatus?` ("ENDED" etc.), `latestStory { createdDateTime, message }` (wrapped), `numUnread`.
4. Connects: `upwork__get_freelancer_financials {action: "connects_balance", org_uid, params: {limit: 10, cursor?}}`.
   - The payload is `{ balance: { connectsBalance }, usage_history: { transactions: [{ amount.rawValue ("-53"), createdDateTime, jobPost.jobTitle, reason, transactionType }] }, hasMore, next_cursor }`.
   - Page until the oldest transaction is before the range start, at most 10 pages.
   - Connects spent in the range = −sum of the negative `amount.rawValue` of transactions in the range.
5. Revenue: `upwork__get_freelancer_financials {action: "summary", org_uid, params: {from_date, to_date}}` → `{ totals: { billed, earned }, by_client: [{ client, billed, jobs:[{ job, billed }] }] }`. This call is secondary.

Derived:
- Funnel:

  | key | label | value |
  |---|---|---|
  | `proposals` | Proposals sent | proposals created in range |
  | `replies` | Client replied | of those, the ones with a room |
  | `offers` | Offers | proposals in range with status Offered or Hired |
  | `hired` | Hired | status Hired |

- Rates:

  | key | label | formula | green | alert | in between |
  |---|---|---|---|---|---|
  | `reply_rate` | Client reply rate | replies / proposals | ≥ 15% | < 8% | watch |
  | `hire_rate` | Hire rate | hired / proposals | no threshold | no threshold | `no_data` when 0 proposals, else `info` |

- Extras:
  - `connectsBalance`, `connectsSpent`, `spendUsd = connectsSpent × CONFIG.upworkConnectUsd`, `boostedShare` (boosted / proposals), `billedUsd` (summary totals.billed).
- Daily series: points `{ date, a: proposals that day, b: those that got a room }`.
- Proposal rows (range, newest first): `{ id, title, url, createdAt, statusLabel, reason, boosted, connectsBid, replied: boolean|null }`.
  - `null` means the room check failed or was skipped.

### Source 3: GoHighLevel (server `GHL`)

Every call is `execute_operation {operationId, locationId: CONFIG.ghlLocation, params: {query: {...}}, reason: "Scoreboard read"}`. The payload is `{ success, status, data }`.

1. `get-pipelines` (no query) → `data.pipelines[{ id, name, stages[{ id, name, position }] }]`.
2. `search-opportunity` with query `{ limit: 100, getTasks: true, getNotes: true, startAfter?, startAfterId? }`.
   - Page with `data.meta.startAfter` / `data.meta.startAfterId` while `opportunities.length === 100`, at most 10 pages.
   - Do NOT send `location_id` in the query; the connector injects it, and sending it again fails with 422.
   - `data.opportunities[]` fields: `id, name, monetaryValue, pipelineId, pipelineStageId, status (open|won|lost|abandoned), source, createdAt, lastStageChangeAt, lastStatusChangeAt, contactId, contact { name, companyName, email, tags[] }, notes { notes[{ bodyText, dateAdded }] }, tasks[{ id, title, body, dueDate, completed }]`.

Derived:
- Board: for the Sales pipeline (`ghlSalesPipelineId`), one column per stage in `position` order.
  - Each card: `{ id, title: contact.name || name, company, email, contactId, url: links.ghlContact(contactId), source, value: monetaryValue, status, stageId, daysInStage, staleLevel, lastNote { text (first 280 chars of the newest note's bodyText), date } | null, openTasks, nextTaskDue }`.
  - `daysInStage` = whole days since `lastStageChangeAt` (fallback `createdAt`).
- Source attribution, first match wins:
  - tag `cold-email`, `source` starting with "Instantly", or a name containing "(Cold Email)" → `cold_email`
  - tag `upwork`, source or name containing "Upwork" → `upwork`
  - tag `linkedin`, source or name containing "LinkedIn" → `linkedin`
  - else → `other`
- `staleLevel` applies to open cards only:

  | stage | warning when | critical when |
  |---|---|---|
  | New Reply/Lead | > 1 day | > 3 days |
  | Call Booked | > 7 days (the call has likely happened; update the stage) | none |
  | Proposal Sent | > 7 days | > 14 days |
  | any other stage | never | never |

  - Otherwise `none`.
- Calls pipeline (`ghlCallsPipelineId`): counts per stage name, plus `showRate = Showed / (Showed + No Show)` over opportunities whose `lastStageChangeAt` falls in the range.
  - Thresholds: green ≥ 90%, alert < 80%, in between watch. `no_data` when the denominator is 0.
- Totals:
  - `open` count and value (Sales pipeline, status open)
  - `wonInRange` (status won, `lastStatusChangeAt` in range): count and value
  - `lostInRange` count
- Tasks: every open (not completed) task on any opportunity becomes a follow-up candidate.

### Source 4: Google Calendar (server `Google Calendar`)

1. `list_events {calendarId: CONFIG.calendarId, startTime: rangeStartISO, endTime: nowISO, orderBy: "startTime", pageSize: 250}` (past calls in range).
2. `list_events {calendarId: CONFIG.calendarId, startTime: nowISO, endTime: now+14d ISO, orderBy: "startTime", pageSize: 250}` (upcoming).

- The payload is `{ events: [{ id, summary, status, start.dateTime, end.dateTime, attendees[{ email, self?, organizer? }], location, htmlLink }], nextPageToken }`. Follow `nextPageToken` at most 3 times.
- A sales call is an event that meets all three conditions:
  - `status !== "cancelled"`
  - it has at least one attendee whose email is not in `CONFIG.selfEmails`
  - `summary` or `location` matches `/zoom|discovery|call|meeting/i`, or `location` contains `zoom.us`
- Never read or render `description` (it holds Zoom passcodes).
- Call fields: `{ id, start, end, title: summary, who: first external attendee email, joinUrl: location if it is an https zoom.us URL else null, url: htmlLink, source }`.
- `source` attribution matches the attendee email, or its domain, against GHL contact emails and Instantly interested/booked lead emails:
  - GHL card source first
  - then any Instantly lead → `cold_email`
  - else `unattributed`

### Follow-ups (derived across sources)

Each item is `{ id, group: "reply_now"|"due"|"upcoming", kind, title, detail, source, ageMs|null, dueAt|null, overdue, url|null }`. Sort `reply_now` by `ageMs` descending, and `due` and `upcoming` by `dueAt` ascending.

**`reply_now`:**
- `upwork_reply`: INTERVIEW rooms with `awaiting_reply_from === "you"`.
  - title: client name (unwrapped)
  - detail: first 140 characters of the latest message
  - age: now − lastActivity
- `email_reply`: Instantly interested or meeting-booked leads that are unanswered.
  - title: "First Last · Company"
  - detail: campaign name
  - age: now − timestamp_last_reply
  - url: unibox
- `unibox`: one item when unread > 0: "N unread replies in Instantly".
- `new_lead`: open Sales opportunities in stage "New Reply/Lead".

**`due`:**
- `ghl_task`: open tasks with dueDate ≤ end of today (Central). `overdue` = dueDate < start of today.
- `upwork_nudge`: rooms where all of the following hold:
  - `awaiting_reply_from === "them"`
  - `contractStatus !== "ENDED"`
  - `last_message_from_self === true`
  - 2 ≤ days since lastActivity ≤ 30
  - Title: client name. Detail: "No reply for N days. Touch due (plan days 2, 4, 7, 11, 16, 23, 30)."
- `call_prep`: sales calls starting within the next 24 h.
- `stale_deal`: open cards with `staleLevel !== "none"`. Detail names the rule, for example "In Proposal Sent for 9 days."

**`upcoming`:**
- `ghl_task`: tasks due in the next 7 days.

### Model contract (what the UI renders; produce exactly this)

```js
/** @typedef {{state:"loading"|"ok"|"error"|"unavailable", storedAt:number|null, error:null|{code:string,server:string,message:string,fix:string}, warnings:string[]}} SourceStatus */
/** @typedef {{key:string,label:string,value:number|null,prev:number|null}} FunnelStep */
// FunnelStep.conv?: boolean (default true). false = the UI shows no "% of <previous step>" line or meter for that step (LinkedIn Accepted, Looms sent, Calls booked); any shown % is capped at 100%.
/** @typedef {{key:string,label:string,value:number|null,prev:number|null,format:"pct"|"num"|"usd",target:string|null,state:"green"|"watch"|"alert"|"no_data"|"info"}} Rate */
const Model = {
  generatedAt: 0,                                 // ms
  range: { days: 30, start: "YYYY-MM-DD", end: "YYYY-MM-DD", prevStart: "", prevEnd: "", label: "Last 30 days" },
  sources: { instantly: SourceStatus, upwork: SourceStatus, ghl: SourceStatus, calendar: SourceStatus },
  today: {
    waitingOnYou: 0,                              // count of reply_now items
    callsNext7d: { count: 0, next: null },        // next: Call | null
    openPipeline: { count: 0, value: 0 },
    revenue: { value: 0, upworkBilled: 0, ghlWon: 0 },
    coldEmailSending: true | false | null,        // null = unknown (Instantly not loaded)
    alerts: [{ id: "", severity: "critical"|"warning", text: "", source: "" }]
  },
  channels: [                                     // always 3, in this order: cold_email, upwork, linkedin
    { key: "cold_email", name: "Cold email",
      status: "live"|"paused"|"not_connected"|"loading"|"error",
      statusText: "",                             // e.g. "Not sending: 0 active of 13 campaigns"
      funnel: [FunnelStep], rates: [Rate],
      series: { aLabel: "Sent", bLabel: "Human replies", cLabel: "Positive", points: [{ date: "", a: 0, b: 0, c: 0 }] },
      spend: { usd: null|0, note: "" },           // cost settings scaled to the range; null when no cost entered
      callsBooked: 0, costPerCall: null|0,
      extras: [{ label: "", value: "" }]          // small key/value facts, preformatted strings
    },
    { key: "upwork", name: "Upwork", /* same shape; series has aLabel "Proposals", bLabel "Client replied", cLabel null and c omitted */ },
    { key: "linkedin", name: "LinkedIn", status: "not_connected",
      statusText: "Picked as channel 3 on Oct 6. These rows fill in once outreach starts and its data source is connected.",
      funnel: [ /* requests, accepted, replies, positive, booked: all value null */ ], rates: [], series: null,
      spend: { usd: null|0, note: "" }, callsBooked: null, costPerCall: null, extras: [] }
  ],
  campaigns: [{ id, name, status, statusLabel, sent, newLeads, replies, positive, bounceRate, dailyLimit, url }],
  proposals: [{ id, title, url, createdAt, statusLabel, reason, boosted, connectsBid, replied }],
  pipeline: {
    name: "Sales", url: CONFIG.links.ghlOpportunities,
    stages: [{ id, name, count, value, cards: [Card] }],
    totals: { open: 0, openValue: 0, wonInRange: 0, wonValueInRange: 0, lostInRange: 0 },
    calls: { stages: [{ name, count }], showRate: Rate }
  },
  calls: { upcoming: [Call], pastInRange: [Call], bySource: { cold_email: 0, upwork: 0, linkedin: 0, other: 0, unattributed: 0 } },
  followups: { reply_now: [Item], due: [Item], upcoming: [Item] },
  costs: { upwork: 0, cold_email: 0, linkedin: 0, editable: true|false }   // monthly USD from db; editable = db available and writable
};
```

Cost per call: `spend.usd = monthly × rangeDays / 30`. For Upwork, add `spendUsd` from connects. Each channel's `callsBooked` is:
- `cold_email`: funnel `booked`
- `upwork`: `calls.bySource.upwork`, plus GHL cards with source upwork that are in Call Booked or later
- `linkedin`: `calls.bySource.linkedin`

`costPerCall = spend.usd / callsBooked` when both are > 0, else null.

Alerts:
- critical "Cold email is not sending" when `coldEmailSending === false`. Text it as "Cold email is not sending: N paused, M drafts, 0 active."
- critical when the bounce rate is in alert.
- warning when the cold email reply rate or the Upwork client reply rate is in alert.
- warning "N deals are stale" when any card has `staleLevel === "critical"`.
- warning "N tasks are overdue".

### Tests (`node --test Coding/scoreboard/tests/*.test.js`)

Use `node:test` + `node:assert`, with no dependencies. Fixtures are SYNTHETIC: invented names (e.g. "Test Lead"), example.com emails, and the same field shapes as above. **Never copy real names, emails or companies into fixtures.**

Cover:
- the range math (including a DST boundary)
- every funnel and rate formula, with threshold states
- daily series zero-fill
- the campaign join and labels
- unanswered-lead detection
- Upwork paging with empty pages, dedupe, the range filter, room-cache rules (permanent found, 12 h recheck) and reply rate
- connects spent in range
- stale rules, source attribution, tasks into due/overdue/upcoming
- the calendar call filter (description never read, cancelled excluded, self-only excluded)
- error-code → fix copy
- a failing source leaving the others `ok` in `load` (fake mcp)
- cost per call
- alerts

## UI (`scoreboard.html`)

**Look: Lorenzo's "Spatial" style, the one he likes best.** Copy its tokens and recipes from:
- `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Brand/tokens/brand.css` (tokens)
- `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Website/assets/site.css`:
  - sky body background + `.sky-haze`: lines 84-102
  - `.glass`, `.pill`, `.tag`: 135-145
  - buttons: 148-160
  - stat tiles: 229-234
  - `.ui-tile` mini bars: 340-349
- `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/jobs/_examples/pilots/impact-hero.html`:
  - self-contained single-file example: sky, haze, panel at 49-55, rows at 64-67, ring at 112-114

Read those files. Use Figtree (Google Fonts) and the brand blue/mint/amber.

- Add one critical token that fits the palette: a desaturated rose, around `#d9534f` softened, for alerts.
- **Single light theme, deliberately.** The brand has no dark theme: put `color-scheme: light` on `:root`, set every color explicitly from tokens, and give `body` its sky background.
- Use the `.sky-haze` drift and honor `prefers-reduced-motion`.
- This is a UI scanned daily: summary before detail. State is encoded in form (pills, stripes, chips), not only in numbers.
- Semantic colors (mint good, amber watch, rose alert, grey no data) are separate from the blue accent.

Layout, top to bottom (one scrolling page, max width about 1280px, 16px minimum side gutter, everything stacks at about 400px wide, no horizontal page scroll):

1. **Top bar** (sticky glass, `top: env(safe-area-inset-top, 0px)`):
   - the Advero wordmark: text "Advero" plus a small blue rounded-square mark drawn in CSS (no external images)
   - "Scoreboard"
   - range pills 7d / 30d / 90d (default 30d; remembered in localStorage inside try/catch)
   - a Refresh button with a spinning state
   - a Costs button that opens the settings drawer
   - on wide screens, anchor links: Today · Channels · Pipeline · Follow-ups · Calls · Detail
   - a source status row of four small chips (Instantly / Upwork / GHL / Calendar), each with a dot and "Live · 3 min ago" / "Loading" / the short error ("Reconnect needed"). A tap on an errored chip shows its `fix` text.
2. **Today** (`#today`, the hero; one glass panel):
   - the alerts as a stacked list of severity-striped rows at the top (critical first)
   - then 4 stat tiles:
     - Waiting on you (count; links to #followups)
     - Calls next 7 days (count + "Next: Tue 2:00 PM · who")
     - Open pipeline (count · $value)
     - Revenue in range ($, with an "Upwork billed $X · GHL won $Y" foot)
   - the cold-email sending state as a pill next to the panel title
3. **Channels** (`#channels`): three glass panels side by side (stacked when narrow), in model order.
   - Each panel has:
     - header: name + status pill
     - the funnel as a stepped list. Each step shows the label, the big number, a delta vs prev (▲/▼ with "vs prev N days"), and the conversion from the previous step as a % plus a thin meter whose fill = that conversion (to scale, 0-100%).
     - the rates as rows with a state pill and the target text
     - a daily chart (inline SVG): bars for `a`, with `b` (and `c`) drawn as dots/markers on their own baseline row above, never on a shared dual axis. It needs a faint grid, the endpoint emphasized, date ticks for the first, middle and last day, and labels colored from tokens.
     - spend / calls booked / cost per call
     - extras as small key/value rows
   - LinkedIn renders as a calm, dashed "ghost" glass panel showing the funnel labels with "—" and the statusText. It must not look broken.
4. **Pipeline** (`#pipeline`): a glass panel titled "Sales pipeline" with totals chips (Open N · $X, Won in range, Lost in range) and an "Open in GHL" link.
   - Below that, the board: one column per stage, inside its own `overflow-x: auto` container (the only horizontal scroller).
   - Column header: stage name + count + $ value.
   - Card:
     - name, company
     - source tag (Cold email = blue tag, Upwork = mint tag, LinkedIn = indigo-ish tag, Other = grey)
     - "N days in stage"
     - a stale stripe (amber warning / rose critical) on the card's left edge
     - next task due
     - the last note in a `<details>` ("Last note · Sep 28")
     - the whole card links to the GHL contact
   - Show empty columns as a quiet "No deals" line.
   - Under the board, a compact row for the Call Booked pipeline: counts per stage plus the show-rate pill.
5. **Follow-ups** (`#followups`) and **Calls** (`#calls`): two glass panels side by side (stacked when narrow).
   - Follow-ups: three groups with headers and counts ("Reply now", "Due", "Coming up").
     - Each item: a kind tag (Upwork / Email / GHL task / Deal / Call), title, detail, age or due text ("waiting 2 days", "due today", "overdue 3 days" in rose), and an "Open" link.
     - An empty group says so plainly ("Nothing waiting on you.").
   - Calls:
     - upcoming calls (day, time in Central, who, source tag, Join link if any, Calendar link)
     - then "Held in range: N" by source
     - the show-rate pill
6. **Detail** (`#detail`): two tabs in one glass panel, "Campaigns" and "Upwork proposals", with tables in `overflow-x: auto` wrappers and tabular numbers.
   - Campaign rows show status pills.
   - Proposal rows show a "Replied" mint tag or "No reply" grey or "—".
   - Titles link out.
7. **Footer**: a quiet line per source with freshness (from `storedAt`) and "Read-only. Data comes live from your connectors."

Settings drawer (Costs): a glass sheet.
- Three number inputs, monthly USD: "Upwork (membership and anything beyond Connects)", "Cold email (Instantly, inboxes, domains, lead data)", "LinkedIn (Sales Navigator, tools)".
- A note: "Connects are counted automatically at $0.15 each."
- Save writes via `AdveroData.saveCosts` and re-renders. Show "Saved" inline.
- When `costs.editable` is false, the inputs are disabled with the reason ("Costs need the claude.ai viewer").

States:
- Before the first update, every panel shows a visible skeleton (shimmer that respects reduced motion).
- A source in `error` greys only its own sections and shows its `fix` text in each affected panel (for example the Upwork channel panel, the proposals tab, the Upwork follow-ups).
- When ALL sources are `unavailable` (no mcp), show one page-level banner: "Live data loads when this page is open in claude.ai." Panels then show designed empty states, not skeletons forever.

Boot:
```js
const data = window.AdveroData;
const [mcp, db, user] = await Promise.all(["mcp","db","user"].map(n => window.claude?.use ? window.claude.use(n).catch(() => null) : Promise.resolve(null)));
```
- Load costs, then call `data.load({ rangeDays, refresh: false, now: new Date(), mcp, db, user }, render)`.
- Range change and Refresh call `load` again (Refresh with `refresh: true`).
- Re-render the relative times every 60 s without refetching.
- Never block the first paint on `claude.use`.

Charts follow the `dataviz` skill (load it with the Skill tool if available):
- one scale per chart
- labels only for values the chart reaches
- a faint grid
- an explicit fill on every shape
- room in the viewBox for the outer labels
- `aria-label` summaries

For a local preview only, `tests/sample-model.js` defines a synthetic `window.__SAMPLE_MODEL__`. The page uses it ONLY when the URL hash is `#sample`. That file is never published and must hold no real data.

Accessibility: visible focus rings, buttons are `<button>`, tabs use `role="tablist"`, and color is never the only signal (pills carry words).

## Acceptance

- Data: `node --test Coding/scoreboard/tests/*.test.js` passes. No real names, emails or companies are in fixtures.
- UI: renders the sample model with no console errors. No horizontal page scroll at 400px. Every connector string is rendered as text.
- The two layers meet only through the model contract above.

## Fix round 1 contract changes (2026-10-06, after review)

- `SourceStatus` gains `refreshing: boolean`. A same-range Refresh keeps every source that was `ok`, with its last data, in state `ok` and `refreshing: true` until its new data settles. A source never goes from `ok` back to `loading` during a refresh. A range change is a new view, so sources without cached data for that range may show `loading`.
- `AdveroData.rebuild(patch) -> Model` rebuilds the model synchronously from the last raw data, with `patch.costs` (and, in piece 2, LinkedIn rows) applied. It never calls a connector. Saving costs uses it instead of reloading.
- Pipeline columns:
  - Each column holds every card in that stage: open, won, lost and abandoned. The Lost stage shows lost cards.
  - Each column shows at most 25 cards, open ones first, then by days in stage descending. A new `hiddenCount` field gives how many more are in GHL.
  - Column `count` and `value` cover all of that stage's cards. The totals stay as specified.
- Upwork `callsBooked` counts each contact once across two sets:
  - calendar calls in range attributed `upwork`
  - Sales cards with source `upwork` in Call Booked or later whose stage changed in range

  The two sets are matched on the attendee email against the card email.
- A card listed as `new_lead` is not listed again as `stale_deal`. Its stale level shows in the `new_lead` detail instead.

---

# Piece 2: LinkedIn tracker (channel 3)

LinkedIn has no API. Lorenzo does every action on LinkedIn by hand, and the `linkedin-outreach` skill (`~/.claude/skills/linkedin-outreach/SKILL.md`, sections "Follow-up timing", "Tracker fields and stages" and "Weekly numbers") says the tracker lives in **his own dashboard**, which is this page. So the page holds the LinkedIn rows in its own `db`, lets him add, paste and update them, and computes the channel from them. Field names, stages and timing come from that skill. Read those three sections; they win over this summary if the two disagree.

## Storage

- db collection `linkedinRows`, one doc per person. The doc id is a stable slug of `profile_url` (lowercased, `https://www.linkedin.com/in/<handle>` → `<handle>`), or a random id when there is no URL.
- Fields, exactly as in the skill: `name, first_name, profile_url, company, role, what_they_do, industry, country, connect_sent_date, accepted_date, dm_date, loom_variant ("A"|"B"|""), last_touch_date, next_touch_due, stage, reply_type, meeting_booked, outcome, slots_offered`, plus `updatedAt` (ms).
  - Dates are `YYYY-MM-DD` strings in Central.
  - `meeting_booked` is an ISO datetime string or "".
- Stages: Connect sent, Accepted, DM sent, Follow-up 1, Follow-up 2, Follow-up 3, No reply, Voice note sent, Reply, Positive reply, Meeting booked, Closed won, Closed lost, Withdrawn.
- `reply_type`: positive, question, price, not_now, not_interested, wrong_person, other.
- The whole db is private to the owner. The orchestrator publishes with `db: { rules: [{ path: "", read: "admin", write: "owner" }] }`.

## Data layer (`scoreboard-data.js`, pure and tested)

- `linkedinApplyEvent(row, event, todayYmd) -> row`. Implements the skill's event table exactly:

  | event | stage | sets | `next_touch_due` |
  |---|---|---|---|
  | `connect_sent` | Connect sent | `connect_sent_date` | +21 days |
  | `withdrawn` | Withdrawn | n/a | "" |
  | `accepted` | Accepted | `accepted_date` | "" (next block) |
  | `dm_sent {variant}` | DM sent | `dm_date`, `last_touch_date`, `loom_variant` | +2 days |
  | `fu1_sent` | Follow-up 1 | `last_touch_date` | +4 days |
  | `fu2_sent` | Follow-up 2 | `last_touch_date` | +7 days |
  | `fu3_sent` | Follow-up 3 | `last_touch_date` | +7 days |
  | `no_reply` | No reply | n/a | FU3 date (`last_touch_date`) + 60 days |
  | `voice_note_sent` | Voice note sent | `last_touch_date` | "" |
  | `reply {type}` | Positive reply if type is positive, else Reply | `reply_type` | "" |
  | `meeting_booked {datetime}` | Meeting booked | `meeting_booked` | "" |
  | `closed_won` / `closed_lost` | Closed won / Closed lost | `outcome` | "" |

  Every event also sets `updatedAt`.
- `linkedinParsePaste(text) -> { rows, errors }`:
  - Accepts TSV or CSV with a header row; detect the delimiter, and handle quoted CSV fields.
  - Headers map case-insensitively to the field names. Accept these aliases:
    - "Full Name" → name
    - "First Name" + "Last Name" → name and first_name
    - "LinkedIn URL", "Profile URL", "URL" → profile_url
    - "Company Name" → company
    - "Title", "Job Title" → role
    - "Location" → country
  - Unknown columns are ignored.
  - Rows without a name or URL go to `errors`.
  - A pasted row with no stage defaults to stage "Connect sent", with `connect_sent_date` set to today when blank.
- `linkedinMerge(existing, incoming)`: merges by doc id. Non-empty incoming fields overwrite; empty ones never blank existing data.
- Loading:
  - Read the whole `linkedinRows` collection once per load.
  - db null or unreadable: state `unavailable` with a reason.
  - The LinkedIn source has its own `SourceStatus` key `linkedin` in `model.sources`.
- Model additions:
  - `model.linkedin = { rows: [Row], editable: bool, pending: n, weekly: {...}, noReplyDue: [rowId] }`
  - `channels[2]` is computed instead of the placeholder:
    - status `live` when rows exist
    - otherwise `not_connected`, with statusText "No LinkedIn rows yet. Add or paste them in the LinkedIn tracker below."
    - **funnel** (range):

      | label | counts |
      |---|---|
      | Requests sent | `connect_sent_date` in range |
      | Accepted | `accepted_date` in range |
      | Looms sent | `dm_date` in range |
      | Replies | rows with `dm_date` in range and `reply_type` set (cohort) |
      | Positive | `reply_type` positive, same cohort |
      | Calls booked | `meeting_booked` date in range |
      | Closed won | `outcome` Closed won among rows with `meeting_booked` in range |

    - **rates**:

      | rate | formula | state |
      |---|---|---|
      | Acceptance | accepted / sent, counting only requests sent 14 or more days ago | alert < 15%, green ≥ 30%, watch between (Jonatan's figures) |
      | Reply rate, variant A | replies / Looms for that variant | `info` |
      | Reply rate, variant B | replies / Looms for that variant | `info` |
      | Positive rate | positive / Looms | `info` |

    - `callsBooked` = the Calls booked count.
    - `spend` from costs as for the other channels.
    - extras:
      - Pending requests N. Add "near the 600 limit" when N ≥ 550, which also raises a warning alert.
      - Looms sent per variant.
- Follow-ups:
  - `reply_now`, kind `linkedin_reply`: rows at stage Reply or Positive reply. Title "name · company", detail "Replied (reply_type). Answer on LinkedIn.", url `profile_url`.
  - `due`, kind `linkedin_touch`: rows with `next_touch_due` ≤ today. The detail names what is due from the stage:

    | stage | detail |
    |---|---|
    | Connect sent | "Pending 21 days. Withdraw the request." |
    | DM sent | "FU1 due" |
    | Follow-up 1 | "FU2 due" |
    | Follow-up 2 | "FU3 due" |
    | Follow-up 3 | "No reply 7 days after FU3. Mark No reply." (also listed in `noReplyDue`) |
    | No reply | "Voice note window open" |

    `overdue` = `next_touch_due` < today.
  - `upcoming`: `next_touch_due` within the next 7 days.
- Weekly numbers (this week, Monday to Sunday in Central): every row of the skill's "Weekly numbers" table. Requests sent, pending, acceptance rate (14-day rule), Looms per variant, reply rate per variant, positive rate per variant, calls booked, closed (won/lost).
- Writes: `saveLinkedinRow(db, row)` and `saveLinkedinRows(db, rows)` (batched, one write per doc, only changed docs) and `deleteLinkedinRow(db, id)`. Writes happen only on an explicit viewer action, never on load.
- Tests:
  - every event row of the table
  - paste parsing (TSV, quoted CSV, aliases, errors)
  - merge not blanking fields
  - the funnel cohort math
  - the acceptance 14-day rule
  - the pending ≥ 550 warning
  - the due/overdue/upcoming grouping
  - weekly numbers across a week boundary

  Fixtures use invented people and example.com URLs only.

## UI (`scoreboard.html`)

- The LinkedIn channel panel renders like the others when rows exist, and keeps the ghost look when there are none.
- Detail gets a third tab, **LinkedIn tracker**:
  - **Toolbar**: "Add person" (opens a form with every field; dates as date inputs, stage and reply_type as selects) and "Paste rows" (a textarea plus a preview table of what will be added or updated and of the errors, then "Import N rows"). Filters by stage group: Active (Connect sent through Follow-up 3), Replied, Booked/Closed, All.
  - **Table**:
    - columns: name, company, stage pill, next touch due (rose when overdue), variant, last touch, reply type
    - sort: next touch due ascending, blanks last
    - the name links to `profile_url`
    - each row has a **"Log…"** select that applies one event via `linkedinApplyEvent` and saves:
      - Connect sent, Accepted, DM sent A, DM sent B, FU1 sent, FU2 sent, FU3 sent, Mark no reply, Voice note sent
      - Reply…, which asks for the reply type in an inline select
      - Meeting booked…, which asks for the datetime in an inline input
      - Closed won, Closed lost, Withdrawn
    - each row also has an "Edit" button (the same form) and "Delete", with an in-page confirm step (no `confirm()`).
  - A **Weekly numbers** card above the table shows the skill's weekly table.
- `model.linkedin.editable` false → hide the write controls and say why ("Editing needs the claude.ai viewer").
- After any save, re-run `buildModel` from the updated rows without refetching the other connectors, so the update shows at once.
- Same security rules: every row field renders as text, and `profile_url` must start with `https://` before it goes into an href.

## Piece 2: exact interface (both workers build to this)

Data layer exports, added to `AdveroData`:

```js
AdveroData.linkedin = {
  STAGES,         // the 14 stage strings in skill order
  REPLY_TYPES,    // positive, question, price, not_now, not_interested, wrong_person, other
  FIELDS,         // the 19 field names in skill order
  EVENTS,         // [{type, label, needs: null|"variant"|"replyType"|"datetime"}] in menu order:
                  // connect_sent "Connect sent", accepted "Accepted", dm_sent "DM sent" (variant), fu1_sent "FU1 sent",
                  // fu2_sent "FU2 sent", fu3_sent "FU3 sent", no_reply "Mark no reply", voice_note_sent "Voice note sent",
                  // reply "Reply…" (replyType), meeting_booked "Meeting booked…" (datetime), closed_won "Closed won",
                  // closed_lost "Closed lost", withdrawn "Withdrawn"
  rowId(row) -> string,
  applyEvent(row, { type, variant?, replyType?, datetime? }, todayYmd) -> newRow,   // pure
  parsePaste(text, todayYmd) -> { rows, errors: [{ line, message }] },             // pure
  merge(existing, incoming) -> row,                                                // pure
  save(db, row) -> Promise<row>,            // set linkedinRows/<rowId>; rejects on failure (UI shows it)
  saveMany(db, rows) -> Promise<{ written, failed }>,   // one write per changed doc, sequential, stops on first failure
  remove(db, id) -> Promise<void>
};
AdveroData.rebuild({ costs?, linkedinRows? }) -> Model   // linkedinRows replaces the cached rows; no connector calls
```

- `load()` reads `linkedinRows` from the db (a single `get` of the collection, raced against the 3 s db timeout) in parallel with the connectors. Its result is `model.sources.linkedin`:
  - `ok`: rows read
  - `unavailable`: db null, with `error: null` and a warning "Editing needs the claude.ai viewer"
  - `error`: read failed or timed out, with fix "Your LinkedIn rows could not be read. Press Refresh."
- `model.linkedin = { rows, editable, pending, noReplyDue: [id], weekly }`.
  - `rows`: sorted by `next_touch_due` ascending, blanks last.
  - `editable`: db present and `user.can("data.write") !== false`.
  - `weekly = { weekStart, weekEnd, requestsSent, pending, nearLimit, acceptance: Rate, looms: { A, B }, replyRate: { A: Rate, B: Rate }, positiveRate: { A: Rate, B: Rate }, callsBooked, closedWon, closedLost }`.
- `today.waitingOnYou` also counts LinkedIn `reply_now` items.
- The "Waiting on you" tile's sources gain `linkedin`.
- The top bar shows a fifth source chip, "LinkedIn", whose freshness reads "Saved rows".

---

# Accuracy fixes (2026-10-07)

Lorenzo reported wrong reply rates. A live diagnosis found the causes below. Where the spec above disagrees with this section, this section wins.

## Cold email: rates follow his metric definitions

The source is `~/.claude/skills/daily-reports-and-metrics/SKILL.md`, rule 6 and the KPI table: **real reply rate = unique_replies / emails sent**. Auto-replies are a separate bucket; never add or subtract them.

| Rate | Formula (range) | Thresholds |
|---|---|---|
| `reply_rate` "Reply rate" | `reply_count_unique / emails_sent_count` | green ≥ 1.0%, alert < 1.0% |
| `positive_rate` "Positive reply rate" | `total_opportunities / emails_sent_count` | green ≥ 0.7%, alert < 0.5%, watch between |
| `bounce_rate` | unchanged: `bounced_count / emails_sent_count` | unchanged |
| `positive_to_booked` | unchanged | unchanged |

`prev` uses the same formulas on the previous range. Funnel steps are unchanged. The step conversion lines stay, because they are step-to-step and labelled as such.

## Every rate says what it divides by

`Rate` gains `basis: string`, a short plain phrase that the UI shows next to the target (for example "Target ≥ 1.0% · replies ÷ emails sent"):

| Rate | `basis` |
|---|---|
| Cold email reply rate | "replies ÷ emails sent" |
| Positive reply rate | "positive replies ÷ emails sent" |
| Bounce rate | "bounces ÷ emails sent" |
| Positive → booked | "calls booked ÷ positive replies" |
| Upwork client reply rate | "proposals the client answered ÷ proposals sent" |
| Hire rate | "hires ÷ proposals sent" |
| Show rate | "showed ÷ (showed + no-show)" |
| LinkedIn acceptance | "accepted ÷ requests sent 14+ days ago" |
| LinkedIn reply rate | "replies ÷ Looms sent" |
| LinkedIn positive rate | "positive replies ÷ Looms sent" |

## Upwork: client replied

Observed live on 2026-10-07:

1. When a client answers a proposal, Upwork moves it to status **`Activated`** (status_label "Invitation accepted"). Proposals that were later hired are `Hired`, and some answered proposals later become `Archived`. The proposal fetch must also page **`Activated`** (max 3 pages, dedupe like the others).
   - Status precedence for dedupe: Hired > Offered > Activated > Accepted / Archived / Declined / Withdrawn.
2. `get_room` returns the room at **`payload.data.proposalRoom`**: `{ id: "room_…", createdAtDateTime: "2026-10-02T16:08:25+0000", roomType: "INTERVIEW", topic, roomName, … }`. Parse `data.proposalRoom.id`, and keep the old defensive paths as fallbacks. A missing room is still the NOT_FOUND tool_error.
3. A proposal counts as **client replied** when any of these holds:
   - its status is Activated, Offered or Hired (no `get_room` call needed for these)
   - `get_room` returns a room
   - the room cache holds a roomId

   Only Accepted, Archived, Declined and Withdrawn proposals need a `get_room` check.
4. **Cache reset.** Every cache doc written before this fix has `roomId: null` because of the parse bug. Docs now carry `v: 2`. Ignore any cached doc without `v: 2`, which makes it re-check. Write `v: 2` on every new write.
5. `replied` on proposal rows and the funnel `replies` step use rule 3. The reply rate is `replies / proposals` in range, so proposals sent in the range are the denominator.

## Tests

Use synthetic fixtures that mirror the observed shapes. Cover:
- an Activated proposal counts as replied with no `get_room` call
- `data.proposalRoom.id` parsing
- a cached null without `v:2` gets re-checked
- the new cold email rate formulas and their states at the threshold edges
- `basis` present on every rate

## Upwork paging caps (added mid-round, 2026-10-07; revised after review)

Observed live on 2026-10-07:
- Upwork pages one merged stream of all his proposals, newest first, 10 upstream records a page. The connector removes records of other statuses after fetching (`filtered_note`).
  - `status=Withdrawn` and `status=Archived` returned the same `next_cursor` on page 1. Withdrawn got 0 of 10 records and Archived got 4 of 10.
  - Pages can therefore be empty, or nearly empty, while `hasMore` is true.
- Some statuses are filtered upstream and end cleanly. `Activated` returned its 3 records with `hasMore: false`.
- `totalCount` is not reliable: the connector says so in `count_note`.

Rules, the same for all seven statuses:
1. **Cap** = 12, 20 or 40 pages for a 7, 30 or 90-day range. Every status walks the same stream, so each needs the same depth.
2. **Stop early** as soon as a page holds a proposal created before `prevStart`. The order is CREATEDDATETIME DESC, so nothing after that page can fall in either range.
3. **Capped** means the cap was reached with `hasMore` true. Missed proposals can fall in range only when the **last page fetched held at least one proposal of that status**. They were all on or after `prevStart`, or rule 2 would have stopped the paging.
   - An empty last page is the filtered tail, and so is a status that saw nothing at all. In that case: no cutoff, no warning, no nulls.
4. **When capped with a non-empty last page:**
   - **Accepted / Archived** (the denominator): cutoff = the oldest createdAt seen. Add "Upwork proposals before <date> did not load; counts for that period may be low." Null every value whose range starts before the cutoff.
   - **Activated, Offered, Hired, Declined, Withdrawn:** add only "Some <status> proposals may not have loaded." Never null a value.
