/* SYNTHETIC sample model for a local UI preview of scoreboard.html (open it with #sample).
   Every person, company, id and link here is invented; links point at example.com.
   Never published, never holds real data.
   Defines window.__SAMPLE_MODEL__ and window.__SAMPLE_VARIANTS__ (Refresh cycles the variants in sample mode). */
(function () {
  "use strict";
  var now = Date.now();
  var MIN = 60000, HOUR = 3600000, DAY = 86400000;
  var TZ = "America/Chicago";
  var ymdFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
  function ymd(ms) { return ymdFmt.format(new Date(ms)); }
  function iso(ms) { return new Date(ms).toISOString(); }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function ex(path) { return "https://example.com/" + path; }

  var days = 30;
  var start = now - (days - 1) * DAY;

  /* daily series: weekday sends, sparse replies */
  var coldPoints = [], upPoints = [];
  for (var i = 0; i < days; i++) {
    var t = start + i * DAY;
    var dow = new Date(t).getUTCDay();
    var weekend = dow === 0 || dow === 6;
    var sent = weekend ? 0 : 140 + ((i * 37) % 60) + (i > 20 ? 40 : 0);
    coldPoints.push({ date: ymd(t), a: sent, b: weekend ? 0 : (i % 3 === 0 ? 2 : i % 4 === 0 ? 1 : 0), c: i % 7 === 2 ? 1 : 0 });
    upPoints.push({ date: ymd(t), a: weekend ? 0 : (i % 2 === 0 ? 3 : 2), b: i % 5 === 1 ? 1 : 0 });
  }
  coldPoints[days - 1].a = 212; coldPoints[days - 1].b = 3; coldPoints[days - 1].c = 1;

  var ok = function (agoMin, warnings, refreshing) { return { state: "ok", refreshing: !!refreshing, storedAt: now - agoMin * MIN, error: null, warnings: warnings || [] }; };

  var callNext = {
    id: "evt-sample-1", start: iso(now + 26 * HOUR), end: iso(now + 26 * HOUR + 15 * MIN),
    title: "Discovery call: Sample Cleaning Co", who: "owner@example.com",
    joinUrl: "https://example.zoom.us/j/000000000", url: ex("calendar/evt-sample-1"), source: "cold_email"
  };

  function card(o) {
    return Object.assign({
      id: "", title: "", company: "", email: "", contactId: "", url: null, source: "other", value: 0, status: "open",
      stageId: "", daysInStage: 0, staleLevel: "none", lastNote: null, openTasks: 0, nextTaskDue: null
    }, o);
  }

  var stages = [
    { id: "st-new", name: "New Reply/Lead", cards: [
      card({ id: "op-1", title: "Maximiliana Featherstonehaugh-Abernathy", company: "Northern Lights Commercial Cleaning and Janitorial Services of Greater Minneapolis LLC",
        email: "max@example.com", contactId: "c-1", url: ex("ghl/contacts/c-1"), source: "cold_email", value: 1500, stageId: "st-new",
        daysInStage: 5, staleLevel: "critical", openTasks: 1, nextTaskDue: iso(now - 2 * DAY),
        lastNote: { text: "Replied asking whether the reactivation offer works for a list that is mostly commercial accounts. Wants to know about the guarantee before booking.", date: iso(now - 5 * DAY) } }),
      card({ id: "op-2", title: "Test Lead Two", company: "Brightside Books Example", email: "two@example.com", contactId: "c-2", url: ex("ghl/contacts/c-2"),
        source: "upwork", value: 0, stageId: "st-new", daysInStage: 2, staleLevel: "warning" })
    ] },
    { id: "st-booked", name: "Call Booked", cards: [
      card({ id: "op-3", title: "Sample Cleaning Co", company: "Sample Cleaning Co", email: "owner@example.com", contactId: "c-3", url: ex("ghl/contacts/c-3"),
        source: "cold_email", value: 2400, stageId: "st-booked", daysInStage: 1, openTasks: 2, nextTaskDue: iso(now + 3 * HOUR),
        lastNote: { text: "Booked for tomorrow. Has about 900 past customers in the CRM.", date: iso(now - 1 * DAY) } })
    ] },
    { id: "st-prop", name: "Proposal Sent", cards: [
      card({ id: "op-4", title: "Ada Example", company: "Example Recruiting Partners", email: "ada@example.com", contactId: "c-4", url: ex("ghl/contacts/c-4"),
        source: "linkedin", value: 3000, stageId: "st-prop", daysInStage: 9, staleLevel: "warning", openTasks: 1, nextTaskDue: iso(now + 4 * DAY) }),
      card({ id: "op-5", title: "Ledger Example LLC", company: "", email: "books@example.com", contactId: "c-5", url: ex("ghl/contacts/c-5"),
        source: "other", value: 1200, stageId: "st-prop", daysInStage: 16, staleLevel: "critical",
        lastNote: { text: "Sent the one-page scope. Said they would review it with a partner.", date: iso(now - 16 * DAY) } })
    ] },
    { id: "st-won", name: "Won", cards: [
      card({ id: "op-6", title: "Sample Bookkeeping Group", company: "Sample Bookkeeping Group", email: "won@example.com", contactId: "c-6", url: ex("ghl/contacts/c-6"),
        source: "upwork", value: 1000, status: "won", stageId: "st-won", daysInStage: 4 })
    ] },
    { id: "st-lost", name: "Lost", hiddenCount: 6, cards: [
      card({ id: "op-7", title: "Example Staffing Partners", company: "Example Staffing Partners", email: "lost1@example.com", contactId: "c-7", url: ex("ghl/contacts/c-7"),
        source: "cold_email", value: 1500, status: "lost", stageId: "st-lost", daysInStage: 3,
        lastNote: { text: "Went with an in-house hire.", date: iso(now - 3 * DAY) } }),
      card({ id: "op-8", title: "Sample Janitorial Example", company: "", email: "lost2@example.com", contactId: "c-8", url: ex("ghl/contacts/c-8"),
        source: "linkedin", value: 0, status: "lost", stageId: "st-lost", daysInStage: 12 })
    ] }
  ];
  stages.forEach(function (s) {
    s.hiddenCount = s.hiddenCount || 0;
    s.count = s.cards.length + s.hiddenCount;
    s.value = s.cards.reduce(function (a, c) { return a + (c.value || 0); }, 0) + (s.hiddenCount ? 4200 : 0);
  });

  var model = {
    generatedAt: now,
    range: { days: days, start: ymd(start), end: ymd(now), prevStart: ymd(start - days * DAY), prevEnd: ymd(start - DAY), label: "Last 30 days" },
    sources: {
      instantly: ok(3, ["The unread reply count did not load, so the unibox item may be missing."]),
      upwork: ok(4),
      ghl: ok(2),
      calendar: { state: "error", refreshing: false, storedAt: null, warnings: [],
        error: { code: "needs_reauth", server: "Google Calendar", message: "Token expired", fix: "Reconnect Google Calendar in claude.ai Settings → Connectors." } }
    },
    today: {
      waitingOnYou: 4,
      callsNext7d: { count: 0, next: null },
      openPipeline: { count: 5, value: 8100 },
      revenue: { value: 1850, upworkBilled: 850, ghlWon: 1000 },
      coldEmailSending: false,
      alerts: [
        { id: "a-bounce", severity: "warning", text: "Upwork client reply rate is 6.1%, under the 8% alert line.", source: "upwork" },
        { id: "a-send", severity: "critical", text: "Cold email is not sending: 3 paused, 2 drafts, 0 active.", source: "instantly" },
        { id: "a-stale", severity: "warning", text: "2 deals are stale", source: "ghl" },
        { id: "a-tasks", severity: "warning", text: "1 task is overdue", source: "ghl" }
      ]
    },
    channels: [
      { key: "cold_email", name: "Cold email", status: "paused", statusText: "Not sending: 0 active of 5 campaigns",
        funnel: [
          { key: "sent", label: "Emails sent", value: 4210, prev: 5120 },
          { key: "leads", label: "New leads reached", value: 1830, prev: 2210 },
          { key: "replies", label: "Human replies", value: 21, prev: 17 },
          { key: "positive", label: "Positive replies", value: 9, prev: 9 },
          { key: "booked", label: "Calls booked", value: 4, prev: 3 },
          { key: "won", label: "Closed", value: 1, prev: 0 }
        ],
        rates: [
          { key: "reply_rate", label: "Reply rate", value: 21 / 1830, prev: 17 / 2210, format: "pct", target: "≥ 1.0%", state: "alert" },
          { key: "positive_rate", label: "Positive rate", value: 9 / 1830, prev: 9 / 2210, format: "pct", target: "≥ 0.7%", state: "alert" },
          { key: "bounce_rate", label: "Bounce rate", value: 0.014, prev: 0.009, format: "pct", target: "≤ 1.0%", state: "watch" },
          { key: "positive_to_booked", label: "Positive → booked", value: 4 / 9, prev: 3 / 9, format: "pct", target: "≥ 50%", state: "watch" }
        ],
        series: { aLabel: "Sent", bLabel: "Human replies", cLabel: "Positive", points: coldPoints },
        spend: { usd: 410, note: "From your monthly cold email cost of $410." },
        callsBooked: 4, costPerCall: 102.5,
        extras: [{ label: "Unread in unibox", value: "Unknown" }, { label: "Auto-replies (excluded)", value: "38" }, { label: "Bounced", value: "59" }]
      },
      { key: "upwork", name: "Upwork", status: "live", statusText: "33 proposals in range",
        funnel: [
          { key: "proposals", label: "Proposals sent", value: 33, prev: 41 },
          { key: "replies", label: "Client replied", value: 2, prev: 5 },
          { key: "offers", label: "Offers", value: 1, prev: 1 },
          { key: "hired", label: "Hired", value: 1, prev: 0 }
        ],
        rates: [
          { key: "reply_rate", label: "Client reply rate", value: 2 / 33, prev: 5 / 41, format: "pct", target: "≥ 15%", state: "alert" },
          { key: "hire_rate", label: "Hire rate", value: 1 / 33, prev: 0, format: "pct", target: null, state: "info" }
        ],
        series: { aLabel: "Proposals", bLabel: "Client replied", cLabel: null, points: upPoints },
        spend: { usd: 87.2, note: "Membership $20 plus 448 Connects at $0.15." },
        callsBooked: 1, costPerCall: 87.2,
        extras: [{ label: "Connects balance", value: "212" }, { label: "Connects spent", value: "448" }, { label: "Boosted", value: "24%" }, { label: "Billed in range", value: "$850" }]
      },
      { key: "linkedin", name: "LinkedIn", status: "not_connected",
        statusText: "Picked as channel 3 on Oct 6. These rows fill in once outreach starts and its data source is connected.",
        funnel: [
          { key: "requests", label: "Requests", value: null, prev: null },
          { key: "accepted", label: "Accepted", value: null, prev: null },
          { key: "replies", label: "Replies", value: null, prev: null },
          { key: "positive", label: "Positive", value: null, prev: null },
          { key: "booked", label: "Booked", value: null, prev: null }
        ],
        rates: [], series: null, spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: []
      }
    ],
    campaigns: [
      { id: "cmp-1", name: "Cleaning reactivation (sample)", status: 2, statusLabel: "Paused", sent: 1820, newLeads: 790, replies: 9, positive: 4, bounceRate: 0.012, dailyLimit: 150, url: ex("instantly/cmp-1") },
      { id: "cmp-2", name: "Bookkeeping outbound with a deliberately long campaign name that has to wrap in the table cell", status: 2, statusLabel: "Paused", sent: 1410, newLeads: 640, replies: 7, positive: 3, bounceRate: 0.019, dailyLimit: 150, url: ex("instantly/cmp-2") },
      { id: "cmp-3", name: "Recruiting outbound (sample)", status: -2, statusLabel: "Bounce protect", sent: 980, newLeads: 400, replies: 5, positive: 2, bounceRate: 0.031, dailyLimit: 100, url: ex("instantly/cmp-3") },
      { id: "cmp-4", name: "Draft A", status: 0, statusLabel: "Draft", sent: 0, newLeads: 0, replies: 0, positive: 0, bounceRate: null, dailyLimit: 50, url: ex("instantly/cmp-4") },
      { id: "cmp-5", name: "Draft B", status: 0, statusLabel: "Draft", sent: 0, newLeads: 0, replies: 0, positive: 0, bounceRate: null, dailyLimit: 50, url: ex("instantly/cmp-5") }
    ],
    proposals: [
      { id: "p-1", title: "Build an AI intake agent for a sample dental office", url: ex("upwork/jobs/p-1"), createdAt: now - 1 * DAY, statusLabel: "Submitted", reason: null, boosted: true, connectsBid: 24, replied: true },
      { id: "p-2", title: "GoHighLevel workflow for an example roofing company with missed-call text back, review requests and a reactivation sequence", url: ex("upwork/jobs/p-2"), createdAt: now - 3 * DAY, statusLabel: "Submitted", reason: null, boosted: false, connectsBid: null, replied: false },
      { id: "p-3", title: "n8n lead routing (sample)", url: ex("upwork/jobs/p-3"), createdAt: now - 6 * DAY, statusLabel: "Hired", reason: null, boosted: true, connectsBid: 16, replied: true },
      { id: "p-4", title: "Make.com CRM sync (sample)", url: ex("upwork/jobs/p-4"), createdAt: now - 12 * DAY, statusLabel: "Archived", reason: "Job closed", boosted: false, connectsBid: null, replied: null }
    ],
    pipeline: {
      name: "Sales", url: ex("ghl/opportunities"),
      stages: stages,
      totals: { open: 5, openValue: 8100, wonInRange: 1, wonValueInRange: 1000, lostInRange: 2 },
      calls: {
        stages: [{ name: "Call Booked", count: 1 }, { name: "Cancelled", count: 1 }, { name: "Showed", count: 5 }, { name: "No Show", count: 1 }],
        showRate: { key: "show_rate", label: "Show rate", value: 5 / 6, prev: 0.75, format: "pct", target: "≥ 90%", state: "watch" }
      }
    },
    calls: { upcoming: [], pastInRange: [], bySource: { cold_email: 0, upwork: 0, linkedin: 0, other: 0, unattributed: 0 } },
    followups: {
      reply_now: [
        { id: "f-1", group: "reply_now", kind: "upwork_reply", title: "Bartholomew Q. Example-Longname of Very Long Company Name Holdings", detail: "Thanks for the walkthrough. Could you do a version that also sends a text when a booking is cancelled? We have three locations.", source: "upwork", ageMs: 2 * DAY + 3 * HOUR, dueAt: null, overdue: false, url: ex("upwork/rooms/r-1") },
        { id: "f-2", group: "reply_now", kind: "email_reply", title: "Test Lead · Example Cleaning", detail: "Cleaning reactivation (sample)", source: "cold_email", ageMs: 20 * HOUR, dueAt: null, overdue: false, url: ex("instantly/unibox") },
        { id: "f-3", group: "reply_now", kind: "new_lead", title: "Maximiliana Featherstonehaugh-Abernathy", detail: "New lead · Stale", source: "cold_email", ageMs: 5 * DAY, dueAt: null, overdue: false, url: ex("ghl/contacts/c-1") },
        { id: "f-4", group: "reply_now", kind: "new_lead", title: "Test Lead Two", detail: "New lead", source: "upwork", ageMs: 40 * MIN, dueAt: null, overdue: false, url: ex("ghl/contacts/c-2") }
      ],
      due: [
        { id: "f-5", group: "due", kind: "ghl_task", title: "Send the guarantee one-pager", detail: "Maximiliana Featherstonehaugh-Abernathy", source: "cold_email", ageMs: null, dueAt: now - 2 * DAY, overdue: true, url: ex("ghl/contacts/c-1") },
        { id: "f-6", group: "due", kind: "upwork_nudge", title: "Sample Client", detail: "No reply for 4 days. Touch due (plan days 2, 4, 7, 11, 16, 23, 30).", source: "upwork", ageMs: null, dueAt: now - 1 * HOUR, overdue: false, url: ex("upwork/rooms/r-2") },
        { id: "f-7", group: "due", kind: "stale_deal", title: "Ledger Example LLC", detail: "In Proposal Sent for 16 days.", source: "other", ageMs: null, dueAt: now, overdue: false, url: ex("ghl/contacts/c-5") },
        { id: "f-8", group: "due", kind: "ghl_task", title: "Prep notes for Sample Cleaning Co", detail: "Sample Cleaning Co", source: "cold_email", ageMs: null, dueAt: now + 3 * HOUR, overdue: false, url: ex("ghl/contacts/c-3") }
      ],
      upcoming: []
    },
    costs: { upwork: 20, cold_email: 410, linkedin: 0, editable: true }
  };

  /* Variant 2: GHL needs reconnect, Upwork still loading, Calendar live with upcoming calls. */
  var v2 = clone(model);
  v2.sources.ghl = { state: "error", refreshing: false, storedAt: null, warnings: [],
    error: { code: "needs_reauth", server: "GHL", message: "Unauthorized", fix: "Reconnect GHL in claude.ai Settings → Connectors." } };
  v2.sources.upwork = { state: "loading", refreshing: false, storedAt: null, error: null, warnings: [] };
  v2.sources.calendar = ok(1);
  v2.pipeline = { name: "Sales", url: ex("ghl/opportunities"), stages: [], totals: { open: 0, openValue: 0, wonInRange: 0, wonValueInRange: 0, lostInRange: 0 },
    calls: { stages: [], showRate: { key: "show_rate", label: "Show rate", value: null, prev: null, format: "pct", target: "≥ 90%", state: "no_data" } } };
  v2.today.openPipeline = { count: 0, value: 0 };
  v2.today.revenue = { value: 0, upworkBilled: 0, ghlWon: 0 };
  v2.today.coldEmailSending = true;
  v2.today.alerts = [];
  v2.today.waitingOnYou = 1;
  v2.today.callsNext7d = { count: 2, next: callNext };
  v2.channels[0].status = "live";
  v2.channels[0].statusText = "Sending: 2 active of 5 campaigns";
  v2.channels[1] = { key: "upwork", name: "Upwork", status: "loading", statusText: "", funnel: [], rates: [], series: null,
    spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: [] };
  v2.proposals = [];
  v2.followups = {
    reply_now: [model.followups.reply_now[1]],
    due: [{ id: "f-9", group: "due", kind: "call_prep", title: "Discovery call: Sample Cleaning Co", detail: "owner@example.com", source: "cold_email", ageMs: null, dueAt: now + 26 * HOUR - 4 * HOUR, overdue: false, url: ex("calendar/evt-sample-1") }],
    upcoming: []
  };
  v2.calls = {
    upcoming: [
      callNext,
      { id: "evt-sample-2", start: iso(now + 3 * DAY + 2 * HOUR), end: iso(now + 3 * DAY + 2 * HOUR + 15 * MIN),
        title: "Intro call with a deliberately long event title that has to wrap on a phone screen", who: "someone.with.a.long.address@subdomain.example.com",
        joinUrl: null, url: ex("calendar/evt-sample-2"), source: "unattributed" }
    ],
    pastInRange: [{ id: "evt-p1" }, { id: "evt-p2" }, { id: "evt-p3" }],
    bySource: { cold_email: 2, upwork: 1, linkedin: 0, other: 0, unattributed: 0 }
  };

  /* Variant 3: no connectors (the page-level banner). */
  var off = { state: "unavailable", refreshing: false, storedAt: null, error: null, warnings: [] };
  var v3 = clone(model);
  v3.sources = { instantly: off, upwork: off, ghl: off, calendar: off };
  v3.today = { waitingOnYou: 0, callsNext7d: { count: 0, next: null }, openPipeline: { count: 0, value: 0 }, revenue: { value: 0, upworkBilled: 0, ghlWon: 0 }, coldEmailSending: null, alerts: [] };
  v3.channels = [
    { key: "cold_email", name: "Cold email", status: "not_connected", statusText: "", funnel: model.channels[0].funnel.map(function (f) { return { key: f.key, label: f.label, value: null, prev: null }; }),
      rates: [], series: null, spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: [] },
    { key: "upwork", name: "Upwork", status: "not_connected", statusText: "", funnel: model.channels[1].funnel.map(function (f) { return { key: f.key, label: f.label, value: null, prev: null }; }),
      rates: [], series: null, spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: [] },
    clone(model.channels[2])
  ];
  v3.campaigns = []; v3.proposals = []; v3.pipeline = null;
  v3.calls = { upcoming: [], pastInRange: [], bySource: { cold_email: 0, upwork: 0, linkedin: 0, other: 0, unattributed: 0 } };
  v3.followups = { reply_now: [], due: [], upcoming: [] };
  v3.costs = { upwork: 0, cold_email: 0, linkedin: 0, editable: false };

  /* Variant 4: same-range Refresh in flight. Instantly and GHL keep their data, marked refreshing; Calendar live. */
  var v4 = clone(model);
  v4.sources.instantly = ok(9, [], true);
  v4.sources.ghl = ok(8, [], true);
  v4.sources.calendar = ok(1);
  v4.calls = clone(v2.calls);
  v4.today.callsNext7d = { count: 2, next: callNext };

  window.__SAMPLE_MODEL__ = model;
  window.__SAMPLE_VARIANTS__ = [
    { name: "Calendar needs reconnect", model: model },
    { name: "GHL needs reconnect, Upwork loading", model: v2 },
    { name: "No connectors", model: v3 },
    { name: "Refreshing Instantly and GHL", model: v4 }
  ];
})();
