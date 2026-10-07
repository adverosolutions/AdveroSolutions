"use strict";
// Tests for scoreboard-data.js. Run from the repo root: node --test Coding/scoreboard/tests/
// All fixtures are synthetic (invented people and companies, example.com addresses).
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

const D = require(path.join(__dirname, "..", "scoreboard-data.js"));
const X = D._internals;
const CONFIG = D.CONFIG;

// Keep real addresses out of the test run: point the self/calendar settings at synthetic ones.
CONFIG.selfEmails = ["me@self.example.com"];
CONFIG.calendarId = "me@self.example.com";

const fx = name => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name + ".json"), "utf8"));
const clone = v => JSON.parse(JSON.stringify(v));
const NOW = Date.parse("2026-10-06T17:00:00Z"); // 12:00 CDT
const H = 3600000, DAY = 86400000;
const R30 = X.rangeFor(NOW, 30);
const SALES = CONFIG.ghlSalesPipelineId;

const ok = data => ({ state: "ok", data, error: null, storedAt: NOW, warnings: [] });

// ------------------------------------------------------------------ fake MCP

function mcpError(code, message, extra) {
  return Object.assign({ code, message: message || code }, extra || {});
}
const notFound = () => mcpError("tool_error", "Upwork: room NOT_FOUND", { result: { isError: true, content: [{ type: "text", text: "NOT_FOUND" }] } });

/** Routes every call to the synthetic fixtures. `overrides(server, tool, input)` may return a response or throw first. */
function fixtureRouter(overrides) {
  const I = fx("instantly"), U = fx("upwork"), G = fx("ghl"), C = fx("calendar");
  const cursorIndex = pages => { const m = { "": 0 }; pages.forEach((p, i) => { if (p.next_cursor) m[p.next_cursor] = i + 1; }); return m; };
  return (server, tool, input) => {
    if (overrides) {
      const o = overrides(server, tool, input);
      if (o !== undefined) return o;
    }
    if (server === "Instantly") {
      switch (tool) {
        case "analytics_campaign_overview": return { payload: input.start_date === R30.start ? I.overview : I.overviewPrev };
        case "get_daily_campaign_analytics": return { payload: I.daily };
        case "get_campaign_analytics": return { payload: I.campaignAnalytics };
        case "list_campaigns": return { payload: input.starting_after ? I.campaignsPage2 : I.campaignsPage1 };
        case "list_leads": return { payload: input.filter === "FILTER_LEAD_INTERESTED" ? I.leadsInterested : I.leadsBooked };
        case "count_unread_emails": return { payload: JSON.stringify(I.unread) }; // string payloads are parsed
      }
    }
    if (server === "Upwork") {
      if (tool === "upwork__list_freelancer_proposals" && input.action === "list") {
        const pages = U.proposals[input.params.status];
        const idx = cursorIndex(pages)[input.params.cursor || ""];
        if (idx == null || !pages[idx]) throw mcpError("tool_error", "unexpected cursor " + input.params.cursor);
        return { payload: pages[idx] };
      }
      if (tool === "upwork__list_freelancer_proposals" && input.action === "get_room") {
        const r = U.rooms[input.params.proposal_id];
        if (r === "NOT_FOUND" || r === undefined) throw notFound();
        return { payload: r };
      }
      if (tool === "upwork__get_messages") {
        return { payload: U.roomsPages[cursorIndex(U.roomsPages)[input.params.cursor || ""]] };
      }
      if (tool === "upwork__get_freelancer_financials" && input.action === "connects_balance") {
        const idx = cursorIndex(U.connectsPages)[input.params.cursor || ""];
        if (idx == null || !U.connectsPages[idx]) throw mcpError("tool_error", "unexpected connects cursor");
        return { payload: U.connectsPages[idx] };
      }
      if (tool === "upwork__get_freelancer_financials" && input.action === "summary") return { payload: U.summary };
    }
    if (server === "GHL" && tool === "execute_operation") {
      if (input.operationId === "get-pipelines") return { payload: G.pipelines };
      if (input.operationId === "search-opportunity") return { payload: G.opportunities };
    }
    if (server === "Google Calendar" && tool === "list_events") {
      if (input.startTime === new Date(R30.startMs).toISOString()) return { payload: input.pageToken === "past-2" ? C.pastPage2 : C.pastPage1 };
      return { payload: C.upcoming };
    }
    throw mcpError("tool_error", `no route for ${server}/${tool}`);
  };
}

function fakeMcp(route, opts) {
  opts = opts || {};
  const calls = [];
  const inflight = {}, maxInflight = {};
  return {
    calls, maxInflight,
    async callTool(server, tool, input, options) {
      calls.push({ server, tool, input: clone(input), options });
      inflight[server] = (inflight[server] || 0) + 1;
      maxInflight[server] = Math.max(maxInflight[server] || 0, inflight[server]);
      try {
        const delay = typeof opts.delay === "function" ? opts.delay(server, tool) : opts.delay || 0;
        await new Promise(r => setTimeout(r, delay));
        const res = route(server, tool, input, calls);
        return res && typeof res === "object" ? clone(res) : res;
      } finally {
        inflight[server]--;
      }
    }
  };
}

const callsTo = (mcp, server, tool) => mcp.calls.filter(c => c.server === server && (!tool || c.tool === tool));
const noSleep = () => Promise.resolve();

/**
 * In-memory stand-in for the db capability, following db.d.ts: without orderBy, results come back by document id
 * ascending; orderBy sorts on one field (missing last); limit cuts the ordered result. `opts.failSet` rejects writes.
 */
function fakeDb(initial, opts) {
  opts = opts || {};
  const docs = new Map(Object.entries(initial || {}));
  const writes = [];
  const queries = [];
  const docRef = p => ({
    id: p.split("/").pop(), path: p,
    async get() { const b = docs.get(p); return { id: p.split("/").pop(), exists: b !== undefined, data: () => (b === undefined ? undefined : clone(b)) }; },
    async set(body) {
      writes.push({ path: p, body: clone(body), op: "set" });
      if (opts.failSet) throw { code: "invalid_argument", message: "write rejected" };
      docs.set(p, clone(body));
    },
    async update(body) {
      writes.push({ path: p, body: clone(body), op: "update" });
      if (opts.failSet) throw { code: "invalid_argument", message: "write rejected" };
      if (!docs.has(p)) throw { code: "invalid_argument", message: "update needs an existing document" };
      docs.set(p, Object.assign(clone(docs.get(p)), clone(body)));
    }
  });
  const query = (coll, q) => ({
    where: (f, op, v) => query(coll, Object.assign({}, q, { filters: q.filters.concat([[f, op, v]]) })),
    orderBy: (f, dir) => query(coll, Object.assign({}, q, { order: [f, dir || "asc"] })),
    limit: n => query(coll, Object.assign({}, q, { lim: n })),
    async get() {
      queries.push({ coll, filters: q.filters, order: q.order, lim: q.lim });
      let out = [];
      for (const [p, b] of docs) {
        const parts = p.split("/");
        if (parts.length !== 2 || parts[0] !== coll) continue;
        if (!q.filters.every(([f, op, v]) => (op === ">=" ? b[f] >= v : true))) continue;
        out.push({ id: parts[1], body: b });
      }
      out.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      if (q.order) {
        const [f, dir] = q.order;
        const sign = dir === "desc" ? -1 : 1;
        out.sort((a, b) => {
          const x = a.body[f], y = b.body[f];
          if (x === undefined || y === undefined) return (x === undefined) - (y === undefined);
          return x < y ? -sign : x > y ? sign : 0;
        });
      }
      if (q.lim) out = out.slice(0, q.lim);
      const snaps = out.map(d => ({ id: d.id, exists: true, data: () => clone(d.body) }));
      return { docs: snaps, size: snaps.length, empty: !snaps.length };
    },
    doc: id => docRef(`${coll}/${id}`)
  });
  return { docs, writes, queries, doc: docRef, collection: name => query(name, { filters: [], order: null, lim: null }) };
}

/** A db whose every call hangs forever. */
function stalledDb() {
  const never = () => new Promise(() => {});
  const ref = { get: never, set: never, update: never };
  const q = { where: () => q, orderBy: () => q, limit: () => q, get: never, doc: () => ref };
  return { doc: () => ref, collection: () => q };
}

// Build the raw model input from fixtures through the real fetchers.
async function fetchAll(route, env) {
  const mcp = fakeMcp(route || fixtureRouter());
  const raw = {};
  for (const k of ["instantly", "upwork", "ghl", "calendar"]) {
    const caller = X.makeCaller({ mcp, serverKey: k, sleep: noSleep });
    const fn = { instantly: X.fetchInstantly, upwork: X.fetchUpwork, ghl: X.fetchGhl, calendar: X.fetchCalendar }[k];
    const out = await fn(caller, R30, Object.assign({ db: null, user: null, nowMs: NOW }, env || {}));
    raw[k] = Object.assign(ok(out.data), { warnings: out.warnings });
  }
  return { raw, mcp };
}

const CTX = { rangeDays: 30, now: new Date(NOW) };

test.beforeEach(() => X.resetMemory());

// ------------------------------------------------------------------ dates

test("range math: last N days ending today in Central, previous range before it", () => {
  const r = X.rangeFor(NOW, 30);
  assert.deepEqual([r.start, r.end, r.prevStart, r.prevEnd], ["2026-09-07", "2026-10-06", "2026-08-08", "2026-09-06"]);
  assert.equal(r.label, "Last 30 days");
  assert.equal(r.startMs, Date.parse("2026-09-07T05:00:00Z"));
  assert.equal(r.endMs, Date.parse("2026-10-07T04:59:59.999Z"));
  const r7 = X.rangeFor(NOW, 7);
  assert.deepEqual([r7.start, r7.prevStart, r7.prevEnd], ["2026-09-30", "2026-09-23", "2026-09-29"]);
  const r90 = X.rangeFor(NOW, 90);
  assert.equal(r90.start, "2026-07-09");
  assert.equal(X.dateList(r90.start, r90.end).length, 90);
  assert.equal(X.rangeFor(NOW, 45).days, 30, "unknown range falls back to 30");
  // 03:00 UTC is still the previous evening in Central
  assert.equal(X.ymd(Date.parse("2026-10-07T03:00:00Z")), "2026-10-06");
  assert.equal(X.ymd(Date.parse("2026-10-07T05:00:00Z")), "2026-10-07");
});

test("range math across DST boundaries", () => {
  // Fall back: Sun 2026-11-01 is a 25-hour day in Central.
  assert.equal(X.startOfDayMs("2026-11-01"), Date.parse("2026-11-01T05:00:00Z"));
  assert.equal(X.startOfDayMs("2026-11-02"), Date.parse("2026-11-02T06:00:00Z"));
  assert.equal(X.endOfDayMs("2026-11-01") - X.startOfDayMs("2026-11-01") + 1, 25 * H);
  // Spring forward: Sun 2026-03-08 is a 23-hour day.
  assert.equal(X.startOfDayMs("2026-03-08"), Date.parse("2026-03-08T06:00:00Z"));
  assert.equal(X.startOfDayMs("2026-03-09"), Date.parse("2026-03-09T05:00:00Z"));
  assert.equal(X.endOfDayMs("2026-03-08") - X.startOfDayMs("2026-03-08") + 1, 23 * H);
  // A 7-day range whose start is in CDT and end is in CST.
  const r = X.rangeFor(Date.parse("2026-11-03T04:30:00Z"), 7); // Mon 2026-11-02 22:30 CST
  assert.deepEqual([r.start, r.end, r.prevStart, r.prevEnd], ["2026-10-27", "2026-11-02", "2026-10-20", "2026-10-26"]);
  assert.equal(r.startMs, Date.parse("2026-10-27T05:00:00Z"));
  assert.equal(r.endMs, Date.parse("2026-11-03T05:59:59.999Z"));
  assert.equal(X.dateList(r.start, r.end).length, 7);
  assert.equal(X.addDays("2026-03-07", 2), "2026-03-09");
});

// ------------------------------------------------------------------ Instantly

test("Instantly funnel, rates and threshold states", async () => {
  const { raw } = await fetchAll();
  const m = D.buildModel(raw, CTX);
  const cold = m.channels[0];
  assert.equal(cold.key, "cold_email");
  assert.deepEqual(cold.funnel.map(f => [f.key, f.value, f.prev]), [
    ["sent", 5000, 4000], ["leads", 2000, 1600], ["replies", 30, 12], ["positive", 12, 6], ["booked", 6, 2], ["won", 1, 0]
  ]);
  const r = Object.fromEntries(cold.rates.map(x => [x.key, x]));
  assert.deepEqual(Object.keys(r), ["reply_rate", "positive_rate", "bounce_rate", "positive_to_booked"]);
  assert.equal(r.reply_rate.value, 0.015); assert.equal(r.reply_rate.state, "green"); assert.equal(r.reply_rate.target, "≥ 1.0%");
  assert.equal(r.reply_rate.prev, 12 / 1600);
  assert.equal(r.positive_rate.value, 0.006); assert.equal(r.positive_rate.state, "watch");
  assert.equal(r.bounce_rate.value, 0.008); assert.equal(r.bounce_rate.state, "green"); assert.equal(r.bounce_rate.prev, 0.025);
  assert.equal(r.positive_to_booked.value, 0.5); assert.equal(r.positive_to_booked.state, "green");
  for (const x of cold.rates) assert.equal(x.format, "pct");
  assert.equal(cold.status, "live");
  assert.equal(cold.statusText, "Sending: 1 active of 5 campaigns");
  assert.equal(m.today.coldEmailSending, true);
});

test("rate thresholds at the edges, including no_data", () => {
  const S = (v, k) => X.rateState(v, X.RULES[k]);
  // reply rate: no watch band
  assert.equal(S(0.01, "cold_reply"), "green"); assert.equal(S(0.0099, "cold_reply"), "alert");
  // positive rate
  assert.equal(S(7 / 1000, "cold_positive"), "green"); assert.equal(S(0.006, "cold_positive"), "watch");
  assert.equal(S(0.005, "cold_positive"), "watch"); assert.equal(S(0.0049, "cold_positive"), "alert");
  // bounce: lower is better
  assert.equal(S(0.01, "cold_bounce"), "green"); assert.equal(S(0.015, "cold_bounce"), "watch");
  assert.equal(S(0.02, "cold_bounce"), "watch"); assert.equal(S(0.0201, "cold_bounce"), "alert");
  // positive to booked
  assert.equal(S(0.5, "cold_p2b"), "green"); assert.equal(S(0.45, "cold_p2b"), "watch"); assert.equal(S(0.39, "cold_p2b"), "alert");
  // upwork reply
  assert.equal(S(0.15, "upwork_reply"), "green"); assert.equal(S(0.1, "upwork_reply"), "watch"); assert.equal(S(0.079, "upwork_reply"), "alert");
  // show rate
  assert.equal(S(0.9, "show_rate"), "green"); assert.equal(S(0.85, "show_rate"), "watch"); assert.equal(S(0.79, "show_rate"), "alert");
  // zero denominator
  const z = X.makeRate("reply_rate", "Reply rate", 0, 0, 0, 0, X.RULES.cold_reply);
  assert.equal(z.value, null); assert.equal(z.prev, null); assert.equal(z.state, "no_data");
  // no threshold
  assert.equal(X.makeRate("hire_rate", "Hire rate", 1, 4, 0, 0, null).state, "info");
  assert.equal(X.makeRate("hire_rate", "Hire rate", 0, 0, 0, 0, null).state, "no_data");
});

test("daily series is zero-filled across the range", async () => {
  const { raw } = await fetchAll();
  const s = D.buildModel(raw, CTX).channels[0].series;
  assert.deepEqual([s.aLabel, s.bLabel, s.cLabel], ["Sent", "Human replies", "Positive"]);
  assert.equal(s.points.length, 30);
  assert.equal(s.points[0].date, "2026-09-07");
  assert.equal(s.points[29].date, "2026-10-06");
  assert.deepEqual(s.points[0], { date: "2026-09-07", a: 100, b: 1, c: 0 });
  assert.deepEqual(s.points.find(p => p.date === "2026-10-05"), { date: "2026-10-05", a: 250, b: 2, c: 1 });
  assert.deepEqual(s.points.find(p => p.date === "2026-09-20"), { date: "2026-09-20", a: 0, b: 0, c: 0 });
  assert.deepEqual(s.points[29], { date: "2026-10-06", a: 0, b: 0, c: 0 });
});

test("sending is false without sends on the last 2 days, even with an active campaign", async () => {
  const { raw } = await fetchAll();
  raw.instantly.data.daily = raw.instantly.data.daily.filter(r => r.date !== "2026-10-05");
  const m = D.buildModel(raw, CTX);
  assert.equal(m.today.coldEmailSending, false);
  assert.equal(m.channels[0].status, "paused");
  assert.equal(m.channels[0].statusText, "Not sending: 1 active of 5 campaigns");
});

test("campaign join, labels and sort order", async () => {
  const { raw, mcp } = await fetchAll();
  assert.equal(callsTo(mcp, "Instantly", "list_campaigns").length, 2, "follows next_starting_after");
  assert.equal(callsTo(mcp, "Instantly", "list_campaigns")[1].input.starting_after, "camp-a");
  const c = D.buildModel(raw, CTX).campaigns;
  assert.deepEqual(c.map(x => x.id), ["camp-a", "camp-b", "camp-c", "camp-d", "camp-gone"]);
  const a = c[0];
  assert.deepEqual(a, { id: "camp-a", name: "Test Campaign A", status: 1, statusLabel: "Active", sent: 3000, newLeads: 1200,
    replies: 20, positive: 8, bounceRate: 0.01, dailyLimit: 200, url: "https://app.instantly.ai/app/campaign/camp-a/analytics" });
  assert.deepEqual(c.map(x => x.statusLabel), ["Active", "Paused", "Draft", "Bounce protect", "Completed"]);
  const draft = c.find(x => x.id === "camp-c");
  assert.equal(draft.sent, 0); assert.equal(draft.bounceRate, null);
  assert.equal(c.find(x => x.id === "camp-gone").dailyLimit, null);
});

test("unanswered interested/booked leads become email_reply items; unread becomes one unibox item", async () => {
  const { raw } = await fetchAll();
  const m = D.buildModel(raw, CTX);
  const email = m.followups.reply_now.filter(i => i.kind === "email_reply");
  assert.deepEqual(email.map(i => i.id), ["email_reply:lead-1", "email_reply:lead-3"]);
  assert.equal(email[0].title, "Test Lead · Alpha Test Co");
  assert.equal(email[0].detail, "Test Campaign A");
  assert.equal(email[0].ageMs, 20 * H);
  assert.equal(email[0].url, CONFIG.links.instantlyUnibox);
  assert.equal(email[1].title, "No Contact", "absent timestamp_last_contact counts as 0");
  assert.equal(email[1].detail, "Instantly", "unknown campaign id falls back");
  const unibox = m.followups.reply_now.filter(i => i.kind === "unibox");
  assert.equal(unibox.length, 1);
  assert.equal(unibox[0].title, "3 unread replies in Instantly");
  raw.instantly.data.unread = 0;
  assert.equal(D.buildModel(raw, CTX).followups.reply_now.filter(i => i.kind === "unibox").length, 0);
});

// ------------------------------------------------------------------ Upwork

test("Upwork proposal paging: empty pages, early stop, page caps, dedupe, range filter", async () => {
  const { raw, mcp } = await fetchAll();
  const list = callsTo(mcp, "Upwork", "upwork__list_freelancer_proposals").filter(c => c.input.action === "list");
  const by = s => list.filter(c => c.input.params.status === s);
  assert.equal(by("Accepted").length, 3, "keeps paging through an empty page, stops once a page reaches before prevStart");
  assert.equal(by("Accepted")[1].input.params.cursor, "acc-2");
  assert.equal(by("Archived").length, 1);
  for (const c of list) {
    assert.equal(c.input.org_uid, CONFIG.upworkOrg);
    assert.equal(c.input.params.limit, 10);
    assert.equal(c.input.params.sort_field, "CREATEDDATETIME");
    assert.equal(c.input.params.sort_order, "DESC");
  }
  assert.ok(!("cursor" in by("Accepted")[0].input.params));
  const ids = raw.upwork.data.proposals.map(p => p.id).sort();
  assert.deepEqual(ids, ["p1", "p2", "p3", "p4", "p6", "p7", "p8"], "p2 deduped; p5 and p9 outside both ranges");

  // caps: a status that pages forever with empty pages
  const endless = fakeMcp((server, tool, input) => {
    if (input.action === "list") return { payload: { data: { vendorProposals: { edges: [] } }, hasMore: true, next_cursor: "c" + Math.random() } };
    if (tool === "upwork__get_messages") return { payload: { data: { rooms: [] }, hasMore: true, next_cursor: "r" + Math.random() } };
    if (input.action === "connects_balance") return { payload: { balance: { connectsBalance: 1 }, usage_history: { transactions: [] }, hasMore: true, next_cursor: "k" + Math.random() } };
    return { payload: { totals: { billed: 0 } } };
  });
  await X.fetchUpwork(X.makeCaller({ mcp: endless, serverKey: "upwork", sleep: noSleep }), R30, { db: null, user: null, nowMs: NOW });
  const el = callsTo(endless, "Upwork", "upwork__list_freelancer_proposals");
  const count = s => el.filter(c => c.input.params.status === s).length;
  assert.deepEqual(["Accepted", "Archived", "Offered", "Hired", "Declined", "Withdrawn"].map(count), [12, 12, 3, 3, 3, 3]);
  assert.equal(callsTo(endless, "Upwork", "upwork__get_messages").length, 3);
  assert.equal(callsTo(endless, "Upwork", "upwork__get_freelancer_financials").filter(c => c.input.action === "connects_balance").length, 10);
});

test("Upwork funnel, reply rate, series, proposal rows and extras", async () => {
  const { raw, mcp } = await fetchAll();
  const rooms = callsTo(mcp, "Upwork", "upwork__list_freelancer_proposals").filter(c => c.input.action === "get_room");
  assert.deepEqual(rooms.map(c => c.input.params.proposal_id).sort(), ["p1", "p2", "p3", "p4", "p6", "p7", "p8"]);
  const m = D.buildModel(raw, CTX);
  const up = m.channels[1];
  assert.equal(up.key, "upwork");
  assert.deepEqual(up.funnel.map(f => [f.key, f.value, f.prev]), [["proposals", 6, 1], ["replies", 4, 0], ["offers", 2, 0], ["hired", 1, 0]]);
  assert.equal(up.rates[0].key, "reply_rate"); assert.equal(up.rates[0].value, 4 / 6); assert.equal(up.rates[0].state, "green");
  assert.equal(up.rates[0].prev, 0);
  assert.equal(up.rates[1].key, "hire_rate"); assert.equal(up.rates[1].state, "info"); assert.equal(up.rates[1].target, null);
  assert.equal(up.series.cLabel, null);
  assert.equal(up.series.points.length, 30);
  assert.ok(up.series.points.every(p => !("c" in p)));
  const day = X.ymd(NOW - DAY);
  assert.deepEqual(up.series.points.find(p => p.date === day), { date: day, a: 1, b: 1 });
  assert.deepEqual(m.proposals.map(p => [p.id, p.replied]), [["p1", true], ["p2", false], ["p7", true], ["p6", false], ["p8", true], ["p3", true]]);
  const p1 = m.proposals[0];
  assert.deepEqual(Object.keys(p1), ["id", "title", "url", "createdAt", "statusLabel", "reason", "boosted", "connectsBid", "replied"]);
  assert.equal(p1.boosted, true); assert.equal(p1.connectsBid, 30); assert.equal(p1.createdAt, NOW - DAY);
  assert.equal(m.proposals.find(p => p.id === "p6").reason, "Job was closed");
  assert.deepEqual(up.extras, [
    { label: "Connects balance", value: "140" },
    { label: "Connects spent", value: "46 ($6.90)" },
    { label: "Boosted proposals", value: "17% (1 of 6)" },
    { label: "Billed in range", value: "$1,200.00" }
  ]);
  assert.equal(m.today.revenue.upworkBilled, 1200);
});

test("Upwork reply rate alert and watch", () => {
  const mk = (n, replied) => ({ id: "x" + n, bucket: "Accepted", createdAt: NOW - n * H, title: "t", url: null, statusLabel: "s", reason: null, boosted: false, connectsBid: null, replied });
  const props = Array.from({ length: 20 }, (_, i) => mk(i + 1, i < 1));
  const u = X.deriveUpwork({ proposals: props, rooms: [], connects: { balance: 0, transactions: [] }, summary: null }, R30, NOW);
  assert.equal(u.rates[0].value, 0.05); assert.equal(u.rates[0].state, "alert");
  const u2 = X.deriveUpwork({ proposals: props.map((p, i) => Object.assign({}, p, { replied: i < 2 })), rooms: [], connects: null, summary: null }, R30, NOW);
  assert.equal(u2.rates[0].state, "watch");
  const empty = X.deriveUpwork({ proposals: [], rooms: [], connects: null, summary: null }, R30, NOW);
  assert.equal(empty.rates[0].state, "no_data"); assert.equal(empty.rates[1].state, "no_data");
});

test("connects spent counts only negative transactions inside the range", async () => {
  const { raw, mcp } = await fetchAll();
  const conn = callsTo(mcp, "Upwork", "upwork__get_freelancer_financials").filter(c => c.input.action === "connects_balance");
  assert.equal(conn.length, 2, "stops after the page whose oldest transaction is before the range start");
  const u = X.deriveUpwork(raw.upwork.data, R30, NOW);
  assert.equal(u.connectsSpent, 46);
  assert.equal(u.spendUsd, 6.9);
  assert.equal(u.connectsBalance, 140);
});

test("room cache: found is permanent, null rechecks after 12 h only for proposals under 30 days", async () => {
  const day5 = NOW - 5 * DAY, day40 = NOW - 40 * DAY;
  const db = fakeDb({
    "upworkRooms/a": { roomId: "room-a", checkedAt: NOW - 39 * DAY },          // found long ago: never re-check
    "upworkRooms/b": { roomId: null, checkedAt: NOW - 13 * H },                 // stale null, young proposal: re-check
    "upworkRooms/c": { roomId: null, checkedAt: NOW - 2 * H },                  // fresh null: trust it
    "upworkRooms/d": { roomId: null, checkedAt: NOW - 13 * H }                  // stale null, old proposal: trust it
  });
  const mcp = fakeMcp((s, t, input) => {
    const id = input.params.proposal_id;
    if (id === "b") return { payload: { room: { id: "room-b" } } };
    if (id === "e") throw notFound();
    if (id === "f") throw mcpError("tool_error", "permission denied");
    throw mcpError("tool_error", "unexpected call for " + id);
  });
  const caller = X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep });
  const props = [{ id: "a", createdAt: day40 }, { id: "b", createdAt: day5 }, { id: "c", createdAt: day5 }, { id: "d", createdAt: day40 },
    { id: "e", createdAt: day5 }, { id: "f", createdAt: day5 }];
  const user = { can: async () => true };
  const res = await X.checkRooms(props, caller, { db, user, nowMs: NOW, R: R30 });
  assert.deepEqual(mcp.calls.map(c => c.input.params.proposal_id).sort(), ["b", "e", "f"]);
  assert.deepEqual(["a", "b", "c", "d", "e", "f"].map(id => res.replied.get(id)), [true, true, false, false, false, null]);
  assert.deepEqual(db.writes.map(w => w.path).sort(), ["upworkRooms/b", "upworkRooms/e"], "writes only real check results; failed check is not written");
  assert.deepEqual(db.writes.find(w => w.path === "upworkRooms/b").body, { roomId: "room-b", checkedAt: NOW });
  assert.deepEqual(db.writes.find(w => w.path === "upworkRooms/e").body, { roomId: null, checkedAt: NOW });
  assert.equal(res.warnings.length, 1);
  assert.match(res.warnings[0], /1 proposal/);
  assert.deepEqual(X.roomCacheVerdict({ roomId: null, checkedAt: NOW - 11 * H }, day5, NOW), { use: true, roomId: null });
  assert.deepEqual(X.roomCacheVerdict({ roomId: null, checkedAt: NOW - 13 * H }, day5, NOW), { use: false });
});

test("room cache: no writes when the viewer cannot write; memory cache without db", async () => {
  const db = fakeDb({});
  const route = (s, t, input) => { if (input.params.proposal_id === "x") return { payload: { room: { id: "room-x" } } }; throw notFound(); };
  let mcp = fakeMcp(route);
  const props = [{ id: "x", createdAt: NOW - DAY }, { id: "y", createdAt: NOW - DAY }];
  await X.checkRooms(props, X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), { db, user: { can: async () => false }, nowMs: NOW, R: R30 });
  assert.equal(db.writes.length, 0, "user.can('data.write') === false blocks writes");
  assert.equal(mcp.calls.length, 2);

  X.resetMemory();
  mcp = fakeMcp(route);
  const env = { db: null, user: null, nowMs: NOW, R: R30 };
  const r1 = await X.checkRooms(props, X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), env);
  assert.equal(mcp.calls.length, 2);
  assert.deepEqual([r1.replied.get("x"), r1.replied.get("y")], [true, false]);
  // same session, 1 h later: both answered from memory
  const r2 = await X.checkRooms(props, X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), Object.assign({}, env, { nowMs: NOW + H }));
  assert.equal(mcp.calls.length, 2);
  assert.deepEqual([r2.replied.get("x"), r2.replied.get("y")], [true, false]);
  // 13 h later: only the null is re-checked
  await X.checkRooms(props, X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), Object.assign({}, env, { nowMs: NOW + 13 * H }));
  assert.deepEqual(mcp.calls.slice(2).map(c => c.input.params.proposal_id), ["y"]);
});

test("Upwork rooms: reply_now and nudges, wrapper stripped", async () => {
  const { raw } = await fetchAll();
  const m = D.buildModel(raw, CTX);
  const reply = m.followups.reply_now.filter(i => i.kind === "upwork_reply");
  assert.equal(reply.length, 1);
  assert.equal(reply[0].title, "Client Alpha Test");
  assert.ok(!reply[0].detail.includes("untrusted"));
  assert.ok(reply[0].detail.startsWith("Hi there, this is a synthetic"));
  assert.ok(reply[0].detail.length <= 140);
  assert.equal(reply[0].ageMs, 2 * H);
  assert.equal(reply[0].url, "https://www.upwork.com/ab/messages/rooms/r1");
  const nudges = m.followups.due.filter(i => i.kind === "upwork_nudge");
  assert.deepEqual(nudges.map(n => n.id), ["upwork_nudge:r2"], "1 day, ENDED, 40 days and not-from-self rooms are excluded");
  assert.equal(nudges[0].title, "Client Beta Test");
  assert.equal(nudges[0].detail, "No reply for 5 days. Touch due (plan days 2, 4, 7, 11, 16, 23, 30).");
  assert.equal(X.unwrap("<untrusted_participant_content>\nName\n</untrusted_participant_content>"), "Name");
});

// ------------------------------------------------------------------ GHL

test("GHL calls: no location_id in the query, paging cap of 10", async () => {
  const { mcp } = await fetchAll();
  const g = callsTo(mcp, "GHL", "execute_operation");
  for (const c of g) {
    assert.equal(c.input.locationId, CONFIG.ghlLocation);
    assert.equal(c.input.reason, "Scoreboard read");
    if (c.input.params.query) assert.ok(!("location_id" in c.input.params.query));
  }
  const search = g.find(c => c.input.operationId === "search-opportunity");
  assert.deepEqual(search.input.params.query, { limit: 100, getTasks: true, getNotes: true });

  let n = 0;
  const full = fakeMcp((s, t, input) => {
    if (input.operationId === "get-pipelines") return { payload: { success: true, status: 200, data: { pipelines: [] } } };
    const opps = Array.from({ length: 100 }, () => ({ id: "g" + (n++) }));
    return { payload: { success: true, status: 200, data: { opportunities: opps, meta: { startAfter: n, startAfterId: "g" + (n - 1) } } } };
  });
  const out = await X.fetchGhl(X.makeCaller({ mcp: full, serverKey: "ghl", sleep: noSleep }), R30, {});
  const pages = callsTo(full, "GHL").filter(c => c.input.operationId === "search-opportunity");
  assert.equal(pages.length, 10);
  assert.equal(pages[1].input.params.query.startAfterId, "g99");
  assert.equal(out.data.opportunities.length, 1000);
});

test("GHL board, stale rules, totals, source attribution and the calls pipeline", async () => {
  const { raw } = await fetchAll();
  const m = D.buildModel(raw, CTX);
  const p = m.pipeline;
  assert.equal(p.name, "Sales");
  assert.deepEqual(p.stages.map(s => [s.name, s.count, s.value, s.hiddenCount]),
    [["New Reply/Lead", 2, 1500, 0], ["Call Booked", 1, 2000, 0], ["Proposal Sent", 3, 4700, 0], ["Won", 1, 2500, 0]]);
  assert.deepEqual(Object.keys(p.stages[0]), ["id", "name", "count", "value", "cards", "hiddenCount"]);
  const cards = Object.fromEntries(p.stages.flatMap(s => s.cards).map(c => [c.id, c]));
  assert.deepEqual(Object.keys(cards.o1), ["id", "title", "company", "email", "contactId", "url", "source", "value", "status", "stageId",
    "daysInStage", "staleLevel", "lastNote", "openTasks", "nextTaskDue"]);
  assert.deepEqual(["o1", "o2", "o3", "o4", "o5", "o6"].map(id => cards[id].staleLevel), ["warning", "critical", "warning", "critical", "none", "none"]);
  assert.deepEqual(["o1", "o2", "o3", "o4", "o5", "o6"].map(id => cards[id].source), ["cold_email", "cold_email", "upwork", "linkedin", "other", "upwork"]);
  assert.equal(cards.o1.daysInStage, 2);
  assert.equal(cards.o2.title, "Foxtrot opportunity", "falls back to the opportunity name");
  assert.equal(cards.o1.url, "https://app.gohighlevel.com/v2/location/ebyNANPagaK7ycf1pfge/contacts/detail/c-o1");
  assert.equal(cards.o1.openTasks, 1);
  assert.equal(cards.o3.nextTaskDue, NOW + 5 * H);
  assert.ok(cards.o1.lastNote.text.startsWith("Newest note."), "newest note first");
  assert.ok(cards.o1.lastNote.text.length <= 280);
  assert.ok(!cards.o1.lastNote.text.includes("<"), "bodyText only, never HTML body");
  assert.equal(cards.o1.lastNote.date, NOW - DAY);
  assert.equal(p.stages[0].cards[0].id, "o2", "oldest in stage first");
  assert.equal(cards.o7.status, "lost", "lost deals show in their stage's column");
  assert.deepEqual(p.stages[2].cards.map(c => c.id), ["o4", "o5", "o7"], "open first, then longest in stage");
  assert.equal(cards.o7.staleLevel, "none");
  assert.deepEqual(p.totals, { open: 5, openValue: 7300, wonInRange: 1, wonValueInRange: 2500, lostInRange: 1 });
  assert.deepEqual(p.calls.stages, [{ name: "Call Booked", count: 1 }, { name: "Cancelled", count: 0 }, { name: "Showed", count: 1 }, { name: "No Show", count: 1 }]);
  assert.equal(p.calls.showRate.value, 0.5); assert.equal(p.calls.showRate.state, "alert"); assert.equal(p.calls.showRate.prev, 1);
  assert.deepEqual(m.today.openPipeline, { count: 5, value: 7300 });
  assert.deepEqual(m.today.revenue, { value: 3700, upworkBilled: 1200, ghlWon: 2500 });

  // stale thresholds in isolation
  assert.equal(X.staleLevelFor("New Reply/Lead", "open", 1 * DAY), "none");
  assert.equal(X.staleLevelFor("New Reply/Lead", "open", 1 * DAY + 1), "warning");
  assert.equal(X.staleLevelFor("New Reply/Lead", "open", 3 * DAY + 1), "critical");
  assert.equal(X.staleLevelFor("Call Booked", "open", 30 * DAY), "warning");
  assert.equal(X.staleLevelFor("Proposal Sent", "open", 14 * DAY), "warning");
  assert.equal(X.staleLevelFor("Proposal Sent", "open", 14 * DAY + 1), "critical");
  assert.equal(X.staleLevelFor("Proposal Sent", "won", 30 * DAY), "none");
  assert.equal(X.staleLevelFor("Negotiation", "open", 300 * DAY), "none");

  // attribution order
  const A = o => X.attributeSource(o);
  assert.equal(A({ contact: { tags: ["Cold-Email"] }, source: "Upwork" }), "cold_email");
  assert.equal(A({ source: "Instantly reply" }), "cold_email");
  assert.equal(A({ name: "Test Lead (Cold Email)" }), "cold_email");
  assert.equal(A({ contact: { tags: ["upwork"] }, source: "LinkedIn" }), "upwork");
  assert.equal(A({ name: "Some job via Upwork" }), "upwork");
  assert.equal(A({ source: "linkedin dm" }), "linkedin");
  assert.equal(A({ source: "Referral" }), "other");
});

test("tasks become due, overdue and upcoming items; new leads and stale deals", async () => {
  const { raw } = await fetchAll();
  const f = D.buildModel(raw, CTX).followups;
  const tasks = f.due.filter(i => i.kind === "ghl_task");
  assert.deepEqual(tasks.map(t => [t.id, t.overdue]), [["ghl_task:t1", true], ["ghl_task:t3", false]]);
  assert.equal(tasks[0].title, "Send the recap");
  assert.equal(tasks[0].detail, "For Test Lead");
  assert.deepEqual(f.upcoming.map(t => t.id), ["ghl_task:t4"], "t5 (10 days out) and completed t2 are excluded");
  assert.equal(f.upcoming[0].group, "upcoming");
  const newLeads = f.reply_now.filter(i => i.kind === "new_lead");
  assert.deepEqual(newLeads.map(i => i.id), ["new_lead:o2", "new_lead:o1"]);
  // K2: a stale new lead is listed once, as new_lead, with its stale level in the detail
  // the wait shows only in the side age text (ageMs), never twice
  assert.equal(newLeads[0].detail, "New lead · Foxtrot Test Inc · Stale");
  assert.equal(newLeads[1].detail, "New lead · Alpha Test Co · Getting stale");
  assert.ok(newLeads.every(i => !/waiting/.test(i.detail) && typeof i.ageMs === "number"));
  const stale = f.due.filter(i => i.kind === "stale_deal");
  assert.deepEqual(stale.map(i => i.id), ["stale_deal:o4", "stale_deal:o3"], "o1 and o2 are new leads, not listed again");
  assert.equal(stale[0].detail, "In Proposal Sent for 15 days.");
  assert.equal(stale[1].detail, "In Call Booked for 8 days. The call has likely happened; update the stage.");
  // ordering contracts
  const ages = f.reply_now.map(i => i.ageMs);
  assert.deepEqual(f.reply_now.map(i => i.kind), ["new_lead", "new_lead", "email_reply", "email_reply", "upwork_reply", "unibox"]);
  assert.equal(ages[ages.length - 1], null);
  const dues = f.due.map(i => i.dueAt);
  assert.deepEqual(dues, dues.slice().sort((a, b) => a - b));
  for (const group of ["reply_now", "due", "upcoming"]) for (const i of f[group]) {
    assert.deepEqual(Object.keys(i).sort(), ["ageMs", "detail", "dueAt", "group", "id", "kind", "overdue", "source", "title", "url"]);
    assert.equal(i.group, group);
  }
});

// ------------------------------------------------------------------ Calendar

test("calendar call filter: cancelled, self-only, no keyword and all-day events excluded; description never read", async () => {
  let touched = 0;
  const withTrap = ev => { const e = clone(ev); Object.defineProperty(e, "description", { enumerable: true, get() { touched++; return "secret"; } }); return e; };
  const C = fx("calendar");
  const mcp = { callTool: async (server, tool, input) => {
    let page = input.startTime === new Date(R30.startMs).toISOString() ? (input.pageToken ? C.pastPage2 : C.pastPage1) : C.upcoming;
    return { payload: { events: page.events.map(withTrap), nextPageToken: page.nextPageToken } };
  } };
  const out = await X.fetchCalendar(X.makeCaller({ mcp, serverKey: "calendar", sleep: noSleep }), R30, { nowMs: NOW });
  const { raw } = await fetchAll();
  raw.calendar = ok(out.data);
  const m = D.buildModel(raw, CTX);
  assert.equal(touched, 0, "description was read");
  assert.ok(!JSON.stringify(m).includes("Passcode"));
  assert.deepEqual(m.calls.pastInRange.map(c => c.id), ["e1", "e5", "e6"]);
  assert.deepEqual(m.calls.upcoming.map(c => c.id), ["u1", "u2", "u3"]);
  const e1 = m.calls.pastInRange[0];
  assert.deepEqual(Object.keys(e1), ["id", "start", "end", "title", "who", "joinUrl", "url", "source"]);
  assert.equal(e1.who, "test.lead@alpha.example.com");
  assert.equal(e1.joinUrl, "https://us02web.zoom.us/j/1234567890");
  assert.equal(e1.source, "cold_email", "GHL contact email");
  assert.equal(m.calls.pastInRange[1].source, "cold_email", "Instantly lead domain");
  assert.equal(m.calls.pastInRange[2].source, "unattributed");
  assert.deepEqual(m.calls.upcoming.map(c => [c.source, c.joinUrl]), [["upwork", null], ["linkedin", "https://zoom.us/j/999"], ["unattributed", null]]);
  assert.deepEqual(m.calls.bySource, { cold_email: 2, upwork: 0, linkedin: 0, other: 0, unattributed: 1 });
  assert.equal(m.today.callsNext7d.count, 2);
  assert.equal(m.today.callsNext7d.next.id, "u1");
  const prep = m.followups.due.filter(i => i.kind === "call_prep");
  assert.deepEqual(prep.map(i => i.id), ["call_prep:u1"]);
  // past calls: list_events paged with nextPageToken
  assert.equal(X.isSalesCall({ status: "confirmed", summary: "Chat", location: "https://acme.zoom.us/j/1", attendees: [{ email: "a@b.example.com" }] }), true);
  assert.equal(X.isSalesCall({ status: "confirmed", summary: "Discovery call", attendees: [{ email: "Me@Self.example.com" }] }), false);
  assert.equal(X.zoomJoinUrl("http://zoom.us/j/1"), null);
  // shared mailbox domains (gmail.com etc.) only match on the exact address
  assert.ok(X.FREEMAIL.has("gmail.com"));
  X.FREEMAIL.add("mailbox.example.com");
  try {
    const G = { attrib: { salesEmail: new Map([["pat@mailbox.example.com", "upwork"]]), salesDomain: new Map([["mailbox.example.com", "upwork"]]),
      otherEmail: new Map(), otherDomain: new Map() } };
    assert.equal(X.attributeCall("someone.else@mailbox.example.com", G, null), "unattributed");
    assert.equal(X.attributeCall("Pat@mailbox.example.com", G, null), "upwork");
  } finally {
    X.FREEMAIL.delete("mailbox.example.com");
  }
});

test("calendar paging follows nextPageToken at most 3 times", async () => {
  const mcp = fakeMcp(() => ({ payload: { events: [], nextPageToken: "more" } }));
  await X.fetchCalendar(X.makeCaller({ mcp, serverKey: "calendar", sleep: noSleep }), R30, { nowMs: NOW });
  assert.equal(mcp.calls.length, 8, "4 requests for past + 4 for upcoming");
  const first = mcp.calls[0].input;
  assert.equal(first.calendarId, CONFIG.calendarId); assert.equal(first.orderBy, "startTime"); assert.equal(first.pageSize, 250);
});

// ------------------------------------------------------------------ errors and calling

test("error code → fix copy", () => {
  const f = code => X.toSourceError({ code, message: "boom" }, "Upwork");
  assert.equal(f("needs_reauth").fix, "Reconnect Upwork in claude.ai Settings → Connectors.");
  assert.equal(f("server_not_connected").fix, "Add the Upwork connector in claude.ai Settings → Connectors.");
  assert.equal(f("server_not_found").fix, "Add the Upwork connector in claude.ai Settings → Connectors.");
  assert.equal(f("selection_required").fix, "Choose which Upwork connector this page should use when claude.ai asks.");
  assert.equal(f("not_in_manifest").fix, "Upwork is switched off for this page. Turn it on in the page's Permissions menu.");
  assert.equal(f("blocked_by_policy").fix, "Your organization's policy blocks Upwork on this page.");
  assert.equal(f("approval_required").fix, "Your organization's policy blocks Upwork on this page.");
  for (const c of ["server_unavailable", "upstream_error", "rate_limited"]) assert.equal(f(c).fix, "Upwork didn't answer. Press Refresh in a minute.");
  const unknown = f("brand_new_code");
  assert.equal(unknown.code, "upstream_error"); assert.equal(unknown.fix, "Upwork didn't answer. Press Refresh in a minute.");
  assert.equal(f("tool_error").fix, "Upwork returned an error: boom");
  const long = X.toSourceError({ code: "tool_error", message: "x".repeat(400) }, "GHL");
  assert.equal(long.fix.length, "GHL returned an error: ".length + 160);
  for (const c of ["not_granted", "capability_disabled", "capability_removed"]) {
    assert.equal(f(c).state, "unavailable");
  }
  assert.equal(f("needs_reauth").state, "error");
  assert.deepEqual(Object.keys(X.publicError(f("needs_reauth"))), ["code", "server", "message", "fix"]);
});

test("callTool helper: cache options, one retry for retryable errors, never loops, storedAt", async () => {
  // retry once, honoring retryAfterMs
  let n = 0;
  const slept = [];
  const mcp1 = { callTool: async (s, t, i, o) => { n++; if (n === 1) throw mcpError("server_unavailable", "x", { retryable: true, retryAfterMs: 1234 }); return { payload: { ok: 1 }, cache: { storedAt: 111 } }; } };
  const c1 = X.makeCaller({ mcp: mcp1, serverKey: "instantly", refresh: true, sleep: ms => { slept.push(ms); return Promise.resolve(); } });
  assert.deepEqual(await c1.call("t", {}), { ok: 1 });
  assert.equal(n, 2); assert.deepEqual(slept, [1234]); assert.equal(c1.meta.oldestCached, 111);
  // random 1.5-3 s when retryAfterMs is absent; second failure is final
  let m = 0;
  const slept2 = [];
  const mcp2 = { callTool: async () => { m++; throw mcpError("server_unavailable", "x", { retryable: true }); } };
  const c2 = X.makeCaller({ mcp: mcp2, serverKey: "ghl", sleep: ms => { slept2.push(ms); return Promise.resolve(); }, random: () => 0.5 });
  await assert.rejects(c2.call("t", {}), e => e.code === "server_unavailable" && e.fix === "GHL didn't answer. Press Refresh in a minute.");
  assert.equal(m, 2); assert.deepEqual(slept2, [2250]);
  // non-retryable: exactly one call
  let k = 0;
  const c3 = X.makeCaller({ mcp: { callTool: async () => { k++; throw mcpError("needs_reauth"); } }, serverKey: "upwork", sleep: noSleep });
  await assert.rejects(c3.call("t", {}), e => e.code === "needs_reauth");
  assert.equal(k, 1);
  // options passed through
  const seen = [];
  const c4 = X.makeCaller({ mcp: { callTool: async (s, t, i, o) => { seen.push([s, o]); return { payload: "not json" }; } }, serverKey: "calendar", refresh: false });
  assert.equal(await c4.call("t", {}), "not json");
  assert.deepEqual(seen[0], ["Google Calendar", { cache: { staleTime: 300000, gcTime: 86400000, refresh: false } }]);
});

test("at most 4 in-flight calls per source", async () => {
  const mcp = fakeMcp(fixtureRouter(), { delay: 3 });
  await D.load({ rangeDays: 30, refresh: false, now: new Date(NOW), mcp, db: null, user: null, sleep: noSleep }, () => {});
  for (const s of ["Instantly", "Upwork", "GHL", "Google Calendar"]) assert.ok(mcp.maxInflight[s] <= 4, `${s}: ${mcp.maxInflight[s]}`);
  assert.equal(mcp.maxInflight.Instantly, 4);
  assert.ok(callsTo(mcp, "Upwork").length > 4);
});

// ------------------------------------------------------------------ load

test("load: one failing source leaves the other three ok, with progressive onUpdate", async () => {
  const route = fixtureRouter((server) => { if (server === "GHL") throw mcpError("needs_reauth", "token expired", { server: "GHL" }); });
  const order = { "Google Calendar": 1, GHL: 4, Instantly: 6, Upwork: 2 };
  const mcp = fakeMcp(route, { delay: s => order[s] });
  const updates = [];
  const db = fakeDb({ "settings/costs": { upwork: 30, cold_email: 300, linkedin: 0 } });
  const final = await D.load({ rangeDays: 30, refresh: true, now: new Date(NOW), mcp, db, user: { can: async () => true }, sleep: noSleep }, m => updates.push(m));
  // first emit right away (all loading, default costs), then the costs read, then one per settled source
  assert.equal(updates.length, 6);
  const settled = updates.map(u => Object.values(u.sources).filter(s => s.state !== "loading").length);
  assert.deepEqual(settled, [0, 0, 1, 2, 3, 4]);
  assert.deepEqual(updates[0].costs, { upwork: 0, cold_email: 0, linkedin: 0, editable: false });
  assert.deepEqual(updates[1].costs, { upwork: 30, cold_email: 300, linkedin: 0, editable: true });
  assert.ok(updates.every(u => Object.values(u.sources).every(s => s.refreshing === false)), "a first load has nothing to refresh");
  assert.strictEqual(final, updates[5]);
  assert.deepEqual(Object.fromEntries(Object.entries(final.sources).map(([k, s]) => [k, s.state])),
    { instantly: "ok", upwork: "ok", ghl: "error", calendar: "ok" });
  assert.deepEqual(final.sources.ghl.error, { code: "needs_reauth", server: "GHL", message: "token expired", fix: "Reconnect GHL in claude.ai Settings → Connectors." });
  assert.equal(final.channels[0].status, "live");
  assert.equal(final.channels[1].status, "live");
  assert.deepEqual(final.pipeline.stages, []);
  assert.equal(final.pipeline.calls.showRate.state, "no_data");
  assert.ok(final.followups.reply_now.some(i => i.kind === "upwork_reply"), "Upwork follow-ups survive the GHL failure");
  assert.ok(typeof final.sources.instantly.storedAt === "number");
  assert.equal(final.sources.ghl.storedAt, null);
  assert.deepEqual(final.costs, { upwork: 30, cold_email: 300, linkedin: 0, editable: true });
  assert.ok(mcp.calls.every(c => c.options.cache.refresh === true));
  // contract shape
  assert.deepEqual(Object.keys(final), ["generatedAt", "range", "sources", "today", "channels", "campaigns", "proposals", "pipeline", "calls", "followups", "costs"]);
  assert.deepEqual(final.channels.map(c => c.key), ["cold_email", "upwork", "linkedin"]);
  assert.equal(final.generatedAt, NOW);
  assert.deepEqual(final.range, { days: 30, start: "2026-09-07", end: "2026-10-06", prevStart: "2026-08-08", prevEnd: "2026-09-06", label: "Last 30 days" });
  // room cache was written to db
  assert.ok(db.writes.some(w => w.path === "upworkRooms/p1"));
});

test("load: unavailable lifecycle code, secondary-call warnings, GHL success:false", async () => {
  const route = fixtureRouter((server, tool, input) => {
    if (server === "Google Calendar") throw mcpError("not_granted");
    if (tool === "count_unread_emails") throw mcpError("server_unavailable", "down");
    if (input && input.action === "summary") throw mcpError("tool_error", "nope");
    if (server === "GHL" && input.operationId === "search-opportunity") return { payload: { success: false, status: 422, data: { message: "bad query" } } };
  });
  const m = await D.load({ rangeDays: 30, now: new Date(NOW), mcp: fakeMcp(route), db: null, user: null, sleep: noSleep });
  assert.equal(m.sources.calendar.state, "unavailable");
  assert.equal(m.sources.calendar.error, null);
  assert.equal(m.sources.instantly.state, "ok");
  assert.equal(m.sources.instantly.warnings.length, 1);
  assert.equal(m.channels[0].extras.find(e => e.label === "Unread in Unibox").value, "—");
  assert.equal(m.sources.upwork.state, "ok");
  assert.ok(m.sources.upwork.warnings.some(w => /billing summary/.test(w)));
  assert.equal(m.channels[1].extras.find(e => e.label === "Billed in range").value, "—");
  assert.equal(m.sources.ghl.state, "error");
  assert.equal(m.sources.ghl.error.code, "tool_error");
  assert.match(m.sources.ghl.error.fix, /^GHL returned an error: GHL answered 422/);
  assert.equal(m.costs.editable, false);
});

test("load: no mcp resolves at once with every source unavailable", async () => {
  const updates = [];
  const m = await D.load({ rangeDays: 7, refresh: false, now: new Date(NOW), mcp: null, db: null, user: null }, u => updates.push(u));
  assert.equal(updates.length, 1);
  assert.deepEqual(Object.values(m.sources).map(s => s.state), ["unavailable", "unavailable", "unavailable", "unavailable"]);
  assert.equal(m.today.coldEmailSending, null);
  assert.deepEqual(m.channels.map(c => c.status), ["not_connected", "not_connected", "not_connected"]);
  assert.equal(m.channels[0].funnel.length, 6);
  assert.ok(m.channels[0].funnel.every(f => f.value === null));
  assert.equal(m.channels[2].series, null);
  assert.equal(m.range.label, "Last 7 days");
  assert.deepEqual(m.costs, { upwork: 0, cold_email: 0, linkedin: 0, editable: false });
});

// ------------------------------------------------------------------ costs, cost per call, alerts

test("loadCosts / saveCosts", async () => {
  assert.deepEqual(await D.loadCosts(null), { upwork: 0, cold_email: 0, linkedin: 0 });
  assert.deepEqual(await D.saveCosts(null, { upwork: 5 }), { upwork: 0, cold_email: 0, linkedin: 0 });
  const db = fakeDb({ "settings/costs": { upwork: "49", cold_email: -3 } });
  assert.deepEqual(await D.loadCosts(db), { upwork: 49, cold_email: 0, linkedin: 0 });
  assert.deepEqual(await D.saveCosts(db, { upwork: 10, cold_email: 250.5, linkedin: "x" }), { upwork: 10, cold_email: 250.5, linkedin: 0 });
  assert.deepEqual(db.writes[0], { path: "settings/costs", body: { upwork: 10, cold_email: 250.5, linkedin: 0 }, op: "set" });
});

test("cost per call per channel", async () => {
  const { raw } = await fetchAll();
  raw.costs = { upwork: 30, cold_email: 300, linkedin: 0, editable: true };
  const m = D.buildModel(raw, CTX);
  const [cold, up, li] = m.channels;
  assert.equal(cold.spend.usd, 300); assert.equal(cold.callsBooked, 6); assert.equal(cold.costPerCall, 50);
  assert.equal(up.spend.usd, 36.9); assert.equal(up.callsBooked, 2, "calendar upwork calls (0) + upwork cards in Call Booked or later (2)");
  assert.equal(up.costPerCall, 18.45);
  assert.match(up.spend.note, /46 Connects/);
  assert.equal(li.spend.usd, null); assert.equal(li.callsBooked, 0); assert.equal(li.costPerCall, null);
  assert.equal(li.statusText, "Picked as channel 3 on Oct 6. These rows fill in once outreach starts and its data source is connected.");
  assert.deepEqual(li.funnel.map(f => f.key), ["requests", "accepted", "replies", "positive", "booked"]);
  // 7-day range scales monthly cost by 7/30
  const m7 = D.buildModel(Object.assign({}, raw, { costs: { cold_email: 300, linkedin: 90 } }), { rangeDays: 7, now: new Date(NOW) });
  assert.equal(m7.channels[0].spend.usd, 70);
  assert.equal(m7.channels[2].spend.usd, 21);
  // no cost entered
  const m0 = D.buildModel(Object.assign({}, raw, { costs: null }), CTX);
  assert.equal(m0.channels[0].spend.usd, null); assert.equal(m0.channels[0].costPerCall, null);
  assert.equal(m0.channels[1].spend.usd, 6.9, "connects are counted even with no monthly cost");
});

test("alerts", async () => {
  const { raw } = await fetchAll();
  let m = D.buildModel(raw, CTX);
  assert.deepEqual(m.today.alerts.map(a => [a.id, a.severity, a.text]), [
    ["stale_deals", "warning", "2 deals are stale"],
    ["overdue_tasks", "warning", "1 task is overdue"]
  ]);
  // paused cold email, high bounce, low reply rates
  const r2 = clone(raw);
  r2.instantly.data.daily = [];
  r2.instantly.data.overview.bounced_count = 150;     // 3% → alert
  r2.instantly.data.overview.reply_count_unique = 10; // 0.5% → alert
  r2.upwork.data.proposals.forEach(p => { p.replied = false; });
  r2.instantly.data.leadsInterested = []; r2.instantly.data.leadsBooked = [];
  m = D.buildModel(r2, CTX);
  const ids = m.today.alerts.map(a => a.id);
  assert.deepEqual(ids, ["cold_not_sending", "cold_bounce", "cold_reply_rate", "upwork_reply_rate", "stale_deals", "overdue_tasks"]);
  assert.equal(m.today.alerts[0].text, "Cold email is not sending: 1 paused, 1 draft, 1 active.");
  assert.equal(m.today.alerts[0].severity, "critical");
  assert.equal(m.today.alerts[1].text, "Bounce rate is 3.0% (alert above 2.0%).");
  assert.ok(m.today.alerts.every(a => typeof a.source === "string" && a.source));
  assert.equal(m.today.waitingOnYou, m.followups.reply_now.length);
});

test("buildModel is pure and renders a full skeleton from empty input", () => {
  const m = D.buildModel({}, CTX);
  assert.deepEqual(Object.values(m.sources).map(s => s.state), ["loading", "loading", "loading", "loading"]);
  assert.deepEqual(m.channels.map(c => c.status), ["loading", "loading", "not_connected"]);
  assert.deepEqual(m.followups, { reply_now: [], due: [], upcoming: [] });
  assert.deepEqual(m.calls.bySource, { cold_email: 0, upwork: 0, linkedin: 0, other: 0, unattributed: 0 });
  assert.equal(m.channels[1].callsBooked, null);
  assert.deepEqual(m, D.buildModel({}, CTX));
});

// ------------------------------------------------------------------ fix round 1

const KEYS = ["instantly", "upwork", "ghl", "calendar"];
const statesOf = m => KEYS.map(k => m.sources[k].state);
const node = (id, ms) => ({ id, auditDetails: { createdDateTime: { rawValue: String(ms) } },
  marketplaceJobPosting: { content: { title: "Job " + id } }, status: { status: "x" } });
const page = nodes => ({ data: { vendorProposals: { edges: nodes.map(n => ({ node: n })) } }, hasMore: false, next_cursor: null });

test("B1: room cache read filters on the oldest proposal's createdAt, newest checkedAt first, so a full window drops the oldest", async () => {
  const initial = {};
  // 1100 found-room docs; id order runs oldest to newest, so an unordered (id-ascending) read would keep the oldest 1000
  for (let i = 0; i < 1100; i++) {
    const id = "a" + String(i).padStart(4, "0");
    initial["upworkRooms/" + id] = { roomId: "room-" + id, checkedAt: NOW - 24 * DAY + i * 60000 };
  }
  const db = fakeDb(initial);
  const mcp = fakeMcp((s, t, input) => ({ payload: { room: { id: "room-" + input.params.proposal_id } } }));
  const props = [{ id: "a0000", createdAt: NOW - 25 * DAY }, { id: "a1099", createdAt: NOW - DAY }, { id: "a1050", createdAt: NOW - 2 * DAY }];
  const res = await X.checkRooms(props, X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), { db, user: { can: async () => true }, nowMs: NOW, R: R30 });
  assert.deepEqual(db.queries, [{ coll: "upworkRooms", filters: [["checkedAt", ">=", NOW - 25 * DAY]], order: ["checkedAt", "desc"], lim: 1000 }]);
  assert.deepEqual(mcp.calls.map(c => c.input.params.proposal_id), ["a0000"], "the newest docs come from the cache; only the dropped oldest is re-checked");
  assert.deepEqual(props.map(p => res.replied.get(p.id)), [true, true, true]);
  // no proposals: no query at all
  const db2 = fakeDb({});
  await X.checkRooms([], X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), { db: db2, user: null, nowMs: NOW, R: R30 });
  assert.equal(db2.queries.length, 0);
});

test("B2: call attribution: Sales cards, then non-'other' cards in other pipelines, then Instantly leads, then unattributed", () => {
  const CALLS = CONFIG.ghlCallsPipelineId;
  const opp = (id, pipelineId, email, extra) => Object.assign({ id, name: "Opp " + id, status: "open", pipelineId, pipelineStageId: "x",
    contact: { name: "Name " + id, email, tags: [] } }, extra || {});
  const G = X.deriveGhl({ pipelines: [], opportunities: [
    opp("k1", CALLS, "lead@inst.example.com"),                                         // Call Booked Pipeline, source other
    opp("k2", CALLS, "a@dom.example.com"),                                             // other-source domain
    opp("k3", CALLS, "up@callp.example.com", { contact: { email: "up@callp.example.com", tags: ["upwork"] } }),
    opp("k4", CALLS, "x@shared.example.com", { source: "Upwork" }),
    opp("s1", SALES, "y@shared.example.com", { source: "LinkedIn DM" }),
    opp("s2", SALES, "plain@sales.example.com", { source: "Referral" })                // Sales card, source other: still counts
  ] }, R30, NOW);
  const I = { leadEmails: new Set(["lead@inst.example.com", "b@dom.example.com", "up@callp.example.com"]) };
  const A = e => X.attributeCall(e, G, I);
  assert.equal(A("lead@inst.example.com"), "cold_email", "an 'other' card in the calls pipeline does not block the Instantly match");
  assert.equal(A("c@dom.example.com"), "cold_email", "same for the domain map");
  assert.equal(A("up@callp.example.com"), "upwork", "a non-'other' card in another pipeline beats Instantly");
  assert.equal(A("x@shared.example.com"), "linkedin", "a Sales card's domain beats another pipeline's exact email");
  assert.equal(A("plain@sales.example.com"), "other", "Sales cards count whatever their source");
  assert.equal(A("nobody@nowhere.example.com"), "unattributed");
  assert.equal(X.attributeCall("lead@inst.example.com", G, null), "unattributed");
});

test("K1: Upwork callsBooked counts each contact once across calendar calls and GHL cards", async () => {
  const { raw } = await fetchAll();
  const ev = (id, email, ago) => ({ id, summary: "Discovery call", status: "confirmed", start: new Date(NOW - ago).toISOString(),
    end: new Date(NOW - ago + H / 2).toISOString(), attendees: [{ email: "me@self.example.com", self: true, organizer: false }, { email, self: false, organizer: false }],
    location: "", htmlLink: "https://calendar.example.com/" + id });
  raw.calendar.data.past.push(
    ev("k1", "client@golf.example.com", 2 * DAY),     // o3's contact (Sales, upwork, Call Booked, changed in range)
    ev("k2", "Client@Golf.example.com", 1 * DAY),     // same contact again
    ev("k3", "juliet@juliet.example.com", 3 * DAY),   // o6's contact (Won, upwork)
    ev("k4", "someone@golf.example.com", 4 * DAY));   // new contact, attributed upwork by domain
  const m = D.buildModel(raw, CTX);
  assert.equal(m.calls.bySource.upwork, 4);
  assert.equal(m.channels[1].callsBooked, 3, "client@golf, juliet, someone@golf: each once");
  // without the calendar, the cards alone
  const m2 = D.buildModel(Object.assign({}, raw, { calendar: { state: "error", data: null } }), CTX);
  assert.equal(m2.channels[1].callsBooked, 2);
});

test("Upwork callsBooked: Call Booked, Proposal Sent, Won or status won count; Lost and Follow Up Later do not", async () => {
  const { raw } = await fetchAll();
  const sales = raw.ghl.data.pipelines.find(p => p.id === D.CONFIG.ghlSalesPipelineId);
  sales.stages.push({ id: "s-lost", name: "Lost", position: 4 }, { id: "s-ful", name: "Follow Up Later", position: 5 });
  const o3 = raw.ghl.data.opportunities.find(o => o.id === "o3");
  const card = (id, stageId, status, email) => Object.assign(JSON.parse(JSON.stringify(o3)), {
    id, pipelineStageId: stageId, status, tasks: [], lastStageChangeAt: new Date(NOW - 2 * DAY).toISOString(),
    lastStatusChangeAt: new Date(NOW - 2 * DAY).toISOString(),
    contact: Object.assign({}, o3.contact, { email }) });
  const base = D.buildModel(raw, CTX).channels[1].callsBooked;
  raw.ghl.data.opportunities.push(
    card("x1", "s-lost", "lost", "lost1@x.example.com"),
    card("x2", "s-lost", "open", "lost2@x.example.com"),
    card("x3", "s-ful", "open", "later@x.example.com"),
    card("x4", "s-prop", "open", "prop@x.example.com"),
    card("x5", "s-new", "won", "wonstatus@x.example.com"));
  const m = D.buildModel(raw, CTX);
  assert.equal(m.channels[1].callsBooked, base + 2, "only the Proposal Sent card and the status-won card are added");
});

test("revenue: Upwork ok but billing summary failed is null, not 0; the sum covers the known parts", async () => {
  const { raw } = await fetchAll(fixtureRouter((server, tool, input) => {
    if (input && input.action === "summary") throw mcpError("tool_error", "nope");
  }));
  const m = D.buildModel(raw, CTX);
  assert.equal(m.sources.upwork.state, "ok");
  assert.deepEqual(m.today.revenue, { value: 2500, upworkBilled: null, ghlWon: 2500 });
  assert.ok(m.sources.upwork.warnings.some(w => /billing summary/.test(w)));
  // summary present but without totals: still unknown, and a warning says so
  const { raw: raw2 } = await fetchAll(fixtureRouter((server, tool, input) => {
    if (input && input.action === "summary") return { payload: { by_client: [] } };
  }));
  const m2 = D.buildModel(raw2, CTX);
  assert.equal(m2.today.revenue.upworkBilled, null);
  assert.equal(m2.today.revenue.value, 2500);
  assert.equal(m2.sources.upwork.warnings.filter(w => /billing summary/.test(w)).length, 1);
  // Upwork not ok at all: unchanged (0, the tile shows the part as "—" from the source state)
  const m3 = D.buildModel(Object.assign({}, raw, { upwork: { state: "error", data: null } }), CTX);
  assert.equal(m3.today.revenue.upworkBilled, 0);
  assert.equal(m3.today.revenue.value, 2500);
});

test("d: stale details say hours under 48 h, whole days after", async () => {
  assert.equal(X.stalePeriod(30 * H), "30 hours");
  assert.equal(X.stalePeriod(48 * H - 1), "47 hours");
  assert.equal(X.stalePeriod(48 * H), "2 days");
  assert.equal(X.stalePeriod(15 * DAY + 5 * H), "15 days");
  const { raw } = await fetchAll();
  raw.ghl.data.opportunities.find(o => o.id === "o1").lastStageChangeAt = new Date(NOW - 30 * H).toISOString();
  const item = D.buildModel(raw, CTX).followups.reply_now.find(i => i.id === "new_lead:o1");
  assert.equal(item.detail, "New lead · Alpha Test Co · Getting stale");
  assert.equal(item.ageMs, 30 * H);
  assert.ok(!/\b1 day\b/.test(JSON.stringify(D.buildModel(raw, CTX).followups)));
});

test("c: clip keeps the result, ellipsis included, within the limit and turns newlines into single spaces", () => {
  assert.equal(X.clip("a\n\n b \t c", 280), "a b c");
  assert.equal(X.clip("x".repeat(140), 140), "x".repeat(140));
  assert.equal(X.clip("x".repeat(141), 140), "x".repeat(139) + "…");
  const c = X.clip("word\n".repeat(100), 280);
  assert.ok(c.length <= 280 && c.endsWith("…") && !c.includes("\n"));
});

test("pipeline columns: every status, at most 25 cards (open first, then longest in stage), hiddenCount, count and value over all", () => {
  const opps = [];
  for (let i = 0; i < 27; i++) opps.push({ id: "op" + i, name: "Open " + i, status: "open", monetaryValue: 100, pipelineId: SALES, pipelineStageId: "s-prop",
    lastStageChangeAt: new Date(NOW - (i + 1) * DAY).toISOString(), contact: { name: "Open " + i } });
  for (const st of ["lost", "abandoned", "won"]) opps.push({ id: "x-" + st, name: st, status: st, monetaryValue: 100, pipelineId: SALES, pipelineStageId: "s-prop",
    lastStageChangeAt: new Date(NOW - 90 * DAY).toISOString(), lastStatusChangeAt: new Date(NOW - DAY).toISOString(), contact: { name: st } });
  opps.push({ id: "lost-1", name: "Lost one", status: "lost", monetaryValue: 50, pipelineId: SALES, pipelineStageId: "s-lost", contact: { name: "Lost one" } });
  const pipelines = [{ id: SALES, name: "Sales", stages: [{ id: "s-prop", name: "Proposal Sent", position: 0 }, { id: "s-lost", name: "Lost", position: 1 }] }];
  const g = X.deriveGhl({ pipelines, opportunities: opps }, R30, NOW).pipeline;
  const col = g.stages[0];
  assert.equal(col.count, 30); assert.equal(col.value, 3000);
  assert.equal(col.cards.length, X.COLUMN_CAP); assert.equal(col.hiddenCount, 5);
  assert.ok(col.cards.every(c => c.status === "open"), "open cards first");
  assert.deepEqual(col.cards.slice(0, 2).map(c => c.id), ["op26", "op25"], "then longest in stage");
  assert.deepEqual(g.stages[1].cards.map(c => [c.id, c.status]), [["lost-1", "lost"]], "the Lost stage shows lost cards");
  assert.equal(g.stages[1].hiddenCount, 0);
  assert.deepEqual(g.totals, { open: 27, openValue: 2700, wonInRange: 1, wonValueInRange: 100, lostInRange: 1 });
});

test("refresh: same-range sources stay ok with refreshing:true until they settle, never loading; a range change starts fresh", async () => {
  await D.load({ rangeDays: 30, refresh: false, now: new Date(NOW), mcp: fakeMcp(fixtureRouter()), db: null, user: null, sleep: noSleep });
  const route = fixtureRouter(server => { if (server === "GHL") throw mcpError("server_unavailable", "down"); });
  const mcp = fakeMcp(route, { delay: s => ({ "Google Calendar": 20, GHL: 1, Instantly: 6, Upwork: 10 })[s] });
  const updates = [];
  const final = await D.load({ rangeDays: 30, refresh: true, now: new Date(NOW + 60000), mcp, db: null, user: null, sleep: noSleep }, m => updates.push(m));
  for (const u of updates) assert.ok(statesOf(u).every(s => s !== "loading"), "never loading after ok in the same range");
  assert.deepEqual(statesOf(updates[0]), ["ok", "ok", "ok", "ok"]);
  assert.ok(KEYS.every(k => updates[0].sources[k].refreshing === true));
  assert.equal(updates[0].pipeline.stages.length, 4, "the last data is kept while refreshing");
  const firstErr = updates.find(u => u.sources.ghl.state === "error");
  assert.equal(firstErr.sources.ghl.refreshing, false);
  assert.equal(firstErr.sources.calendar.refreshing, true, "calendar is still refreshing on its old data");
  assert.equal(firstErr.sources.calendar.state, "ok");
  assert.deepEqual(statesOf(final), ["ok", "ok", "error", "ok"]);
  assert.ok(KEYS.every(k => final.sources[k].refreshing === false));
  assert.deepEqual(final.pipeline.stages, [], "the failed refresh replaces GHL's data with its error");

  // the next same-range refresh shows the error while refreshing, not loading
  const u3 = [];
  await D.load({ rangeDays: 30, refresh: true, now: new Date(NOW), mcp: fakeMcp(fixtureRouter()), db: null, user: null, sleep: noSleep }, m => u3.push(m));
  assert.deepEqual([u3[0].sources.ghl.state, u3[0].sources.ghl.refreshing], ["error", true]);
  assert.deepEqual(statesOf(u3[u3.length - 1]), ["ok", "ok", "ok", "ok"]);

  // a range change is a new view
  const u7 = [];
  await D.load({ rangeDays: 7, refresh: false, now: new Date(NOW), mcp: fakeMcp(fixtureRouter()), db: null, user: null, sleep: noSleep }, m => u7.push(m));
  assert.deepEqual(statesOf(u7[0]), ["loading", "loading", "loading", "loading"]);
  assert.ok(KEYS.every(k => u7[0].sources[k].refreshing === false));
});

test("rebuild: synchronous, from the last raw data, costs merged, no connector calls", async () => {
  const before = D.rebuild({ costs: { upwork: 10 } });
  assert.deepEqual(statesOf(before), ["loading", "loading", "loading", "loading"], "before any load: a loading model");
  assert.equal(before.costs.upwork, 10);

  const mcp = fakeMcp(fixtureRouter());
  const db = fakeDb({ "settings/costs": { upwork: 30, cold_email: 300, linkedin: 0 } });
  const final = await D.load({ rangeDays: 30, refresh: false, now: new Date(NOW), mcp, db, user: { can: async () => true }, sleep: noSleep });
  const n = mcp.calls.length, w = db.writes.length;
  const m = D.rebuild({ costs: { cold_email: 600 } });
  assert.ok(!(m instanceof Promise));
  assert.equal(mcp.calls.length, n); assert.equal(db.writes.length, w);
  assert.deepEqual(m.costs, { upwork: 30, cold_email: 600, linkedin: 0, editable: true });
  assert.equal(m.channels[0].spend.usd, 600); assert.equal(m.channels[0].costPerCall, 100);
  const strip = x => Object.assign({}, x, { costs: null, channels: x.channels.map(c => Object.assign({}, c, { spend: null, costPerCall: null })) });
  assert.deepEqual(strip(m), strip(final), "only the cost-driven fields change");
  assert.equal(D.rebuild().costs.cold_email, 600, "the patch sticks");

  // a rebuild during a load sticks for that load's later emits; the costs read still supplies `editable`
  X.resetMemory();
  let patched = false;
  const db2 = fakeDb({ "settings/costs": { upwork: 30, cold_email: 300, linkedin: 0 } });
  const fin2 = await D.load({ rangeDays: 30, now: new Date(NOW), mcp: fakeMcp(fixtureRouter(), { delay: 2 }), db: db2, user: { can: async () => true }, sleep: noSleep },
    () => { if (!patched) { patched = true; D.rebuild({ costs: { linkedin: 90 } }); } });
  assert.deepEqual(fin2.costs, { upwork: 0, cold_email: 0, linkedin: 90, editable: true });
});

test("a: a stalled db never blocks the sources; costs race a timeout and arrive later; no mcp resolves at once", async () => {
  const updates = [];
  const final = await D.load({ rangeDays: 30, now: new Date(NOW), mcp: fakeMcp(fixtureRouter()), db: stalledDb(),
    user: { can: () => new Promise(() => {}) }, sleep: noSleep, dbTimeoutMs: 30 }, m => updates.push(m));
  assert.deepEqual(statesOf(final), ["ok", "ok", "ok", "ok"]);
  assert.deepEqual(final.costs, { upwork: 0, cold_email: 0, linkedin: 0, editable: false });
  assert.deepEqual(updates.map(u => statesOf(u).filter(s => s !== "loading").length), [0, 1, 2, 3, 4]);
  assert.equal(final.channels[1].funnel[1].value, 4, "room checks ran without the cache");

  // slow costs: load resolves on defaults, then one more update carries the real costs
  const slow = fakeDb({ "settings/costs": { upwork: 30, cold_email: 300, linkedin: 0 } });
  const docOf = slow.doc;
  slow.doc = p => { const r = docOf(p); const g = r.get; r.get = () => new Promise(res => setTimeout(() => res(g()), 80)); return r; };
  X.resetMemory();
  const u2 = [];
  const f2 = await D.load({ rangeDays: 30, now: new Date(NOW), mcp: fakeMcp(fixtureRouter()), db: slow, user: { can: async () => true }, sleep: noSleep, dbTimeoutMs: 20 }, m => u2.push(m));
  assert.equal(f2.costs.cold_email, 0);
  const n = u2.length;
  await new Promise(r => setTimeout(r, 120));
  assert.equal(u2.length, n + 1);
  assert.deepEqual(u2[n].costs, { upwork: 30, cold_email: 300, linkedin: 0, editable: true });

  // no mcp: resolves at once even with a stalled db
  X.resetMemory();
  const t0 = Date.now();
  const m0 = await D.load({ rangeDays: 30, now: new Date(NOW), mcp: null, db: stalledDb(), user: null, dbTimeoutMs: 5000 });
  assert.ok(Date.now() - t0 < 100);
  assert.deepEqual(statesOf(m0), ["unavailable", "unavailable", "unavailable", "unavailable"]);
});

test("f: once a main call fails, the source's other chains stop paging", async () => {
  let search = 0;
  const ghl = { callTool: async (s, t, input) => {
    if (input.operationId === "get-pipelines") throw mcpError("needs_reauth", "expired");
    search++;
    await new Promise(r => setTimeout(r, 5));
    return { payload: { success: true, data: { opportunities: Array.from({ length: 100 }, (_, i) => ({ id: `g${search}-${i}` })), meta: { startAfter: search, startAfterId: "g" } } } };
  } };
  const settle = () => new Promise(r => setTimeout(r, 60)); // let any chain that kept paging show itself
  await assert.rejects(X.fetchGhl(X.makeCaller({ mcp: ghl, serverKey: "ghl", sleep: noSleep }), R30, {}), e => e.code === "needs_reauth");
  await settle();
  assert.equal(search, 1, "the in-flight page finishes, no further pages");

  const up = fakeMcp((s, tool, input) => {
    if (tool === "upwork__get_messages") throw mcpError("server_unavailable", "down");
    if (input.action === "list") return { payload: { data: { vendorProposals: { edges: [] } }, hasMore: true, next_cursor: "c" + Math.random() } };
    if (input.action === "connects_balance") return { payload: { balance: { connectsBalance: 1 }, usage_history: { transactions: [] }, hasMore: true, next_cursor: "k" + Math.random() } };
    return { payload: { totals: { billed: 0 } } };
  }, { delay: 3 });
  await assert.rejects(X.fetchUpwork(X.makeCaller({ mcp: up, serverKey: "upwork", sleep: noSleep }), R30, { db: null, user: null, nowMs: NOW }),
    e => e.code === "server_unavailable");
  await settle();
  const lists = callsTo(up, "Upwork", "upwork__list_freelancer_proposals").length;
  assert.ok(lists < 12, `proposal paging stopped early (${lists} calls; 36 without the abort)`);
});

test("g: after a rejected room-cache write, no more writes in that load", async () => {
  const db = fakeDb({}, { failSet: true });
  const mcp = fakeMcp(() => { throw notFound(); });
  const props = ["w1", "w2", "w3", "w4", "w5"].map(id => ({ id, createdAt: NOW - DAY }));
  const roomWrites = { disabled: false };
  const env = { db, user: { can: async () => true }, nowMs: NOW, R: R30, roomWrites };
  const res = await X.checkRooms(props, X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), env);
  assert.equal(db.writes.length, 1);
  assert.ok(res.warnings.includes("Couldn't save the proposal-room cache."));
  assert.equal(roomWrites.disabled, true);
  X.resetMemory();
  await X.checkRooms([{ id: "w6", createdAt: NOW - DAY }], X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), env);
  assert.equal(db.writes.length, 1, "the same load writes nothing more");
});

test("h: dedupe keeps the most advanced status", async () => {
  const pages = { Accepted: [node("q1", NOW - DAY), node("q3", NOW - DAY)], Archived: [node("q2", NOW - 2 * DAY)], Offered: [node("q2", NOW - 2 * DAY)],
    Hired: [node("q1", NOW - DAY)], Declined: [], Withdrawn: [node("q3", NOW - DAY)] };
  const mcp = fakeMcp((s, tool, input) => {
    if (input.action === "list") return { payload: page(pages[input.params.status]) };
    if (input.action === "get_room") throw notFound();
    if (tool === "upwork__get_messages") return { payload: { data: { rooms: [] } } };
    if (input.action === "connects_balance") return { payload: { balance: { connectsBalance: 0 }, usage_history: { transactions: [] } } };
    return { payload: { totals: { billed: 0 } } };
  });
  const out = await X.fetchUpwork(X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }), R30, { db: null, user: null, nowMs: NOW });
  const by = Object.fromEntries(out.data.proposals.map(p => [p.id, p.bucket]));
  assert.deepEqual(by, { q1: "Hired", q2: "Offered", q3: "Accepted" });
  const u = X.deriveUpwork(out.data, R30, NOW);
  assert.deepEqual(u.funnel.map(f => f.value), [3, 0, 2, 1]);
});

test("i: a throw while deriving one source becomes that source's error and never rejects load", async () => {
  const badRow = () => ({ get date() { throw new Error("bad row"); } });
  const quiet = console.error;
  console.error = () => {};
  try {
    const { raw } = await fetchAll();
    raw.instantly.data.daily = [badRow()];
    const m = D.buildModel(raw, CTX);
    assert.deepEqual(statesOf(m), ["error", "ok", "ok", "ok"]);
    assert.deepEqual(m.sources.instantly.error, { code: "upstream_error", server: "Instantly", message: "bad row",
      fix: "Something in the Instantly data could not be read. Press Refresh; if it repeats, tell Claude." });
    assert.equal(m.channels[0].status, "error");
    assert.equal(m.channels[0].statusText, m.sources.instantly.error.fix);
    assert.ok(m.followups.reply_now.some(i => i.kind === "upwork_reply"));

    const inner = fakeMcp(fixtureRouter());
    const mcp = { callTool: (s, t, i, o) => (t === "get_daily_campaign_analytics" ? Promise.resolve({ payload: { result: [badRow()] } }) : inner.callTool(s, t, i, o)) };
    const final = await D.load({ rangeDays: 30, now: new Date(NOW), mcp, db: null, user: null, sleep: noSleep });
    assert.deepEqual(statesOf(final), ["error", "ok", "ok", "ok"]);
    assert.equal(final.sources.instantly.error.code, "upstream_error");
  } finally {
    console.error = quiet;
  }
});

test("j: Upwork nudge window is 2 to 30 days inclusive", () => {
  const room = (id, ago) => ({ id, roomName: "Client " + id, lastActivity: String(NOW - ago), awaiting_reply_from: "them", last_message_from_self: true });
  const u = X.deriveUpwork({ proposals: [], rooms: [room("a", 2 * DAY), room("b", 2 * DAY - 1), room("c", 30 * DAY), room("d", 31 * DAY)], connects: null, summary: null }, R30, NOW);
  assert.deepEqual(u.due.map(i => [i.id, i.detail.slice(0, 20)]), [["upwork_nudge:a", "No reply for 2 days."], ["upwork_nudge:c", "No reply for 30 days"]]);
});

test("j: a stale null re-checked to null again writes only the new checkedAt", async () => {
  const db = fakeDb({ "upworkRooms/n1": { roomId: null, checkedAt: NOW - 13 * H } });
  const mcp = fakeMcp(() => { throw notFound(); });
  const res = await X.checkRooms([{ id: "n1", createdAt: NOW - 3 * DAY }], X.makeCaller({ mcp, serverKey: "upwork", sleep: noSleep }),
    { db, user: { can: async () => true }, nowMs: NOW, R: R30 });
  assert.equal(mcp.calls.length, 1);
  assert.equal(res.replied.get("n1"), false);
  assert.deepEqual(db.writes, [{ path: "upworkRooms/n1", body: { checkedAt: NOW }, op: "update" }]);
  assert.deepEqual(db.docs.get("upworkRooms/n1"), { roomId: null, checkedAt: NOW });
});
