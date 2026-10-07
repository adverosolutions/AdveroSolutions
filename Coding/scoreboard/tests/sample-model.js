/* SYNTHETIC sample model for a local UI preview of scoreboard.html (open it with #sample).
   Every person, company, id and link here is invented; links point at example.com, and the LinkedIn rows
   use https://www.linkedin.com/in/test-... handles only.
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
          { key: "reply_rate", label: "Reply rate", value: 21 / 4210, prev: 17 / 5120, format: "pct", target: "≥ 1.0%", state: "alert", basis: "replies ÷ emails sent" },
          { key: "positive_rate", label: "Positive reply rate", value: 9 / 4210, prev: 9 / 5120, format: "pct", target: "≥ 0.7%", state: "alert", basis: "positive replies ÷ emails sent" },
          { key: "bounce_rate", label: "Bounce rate", value: 0.014, prev: 0.009, format: "pct", target: "≤ 1.0%", state: "watch", basis: "bounces ÷ emails sent" },
          { key: "positive_to_booked", label: "Positive → booked", value: 4 / 9, prev: 3 / 9, format: "pct", target: "≥ 50%", state: "watch", basis: "calls booked ÷ positive replies" }
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
          { key: "reply_rate", label: "Client reply rate", value: 2 / 33, prev: 5 / 41, format: "pct", target: "≥ 15%", state: "alert", basis: "proposals the client answered ÷ proposals sent" },
          { key: "hire_rate", label: "Hire rate", value: 1 / 33, prev: 0, format: "pct", target: null, state: "info", basis: "hires ÷ proposals sent" }
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
        showRate: { key: "show_rate", label: "Show rate", value: 5 / 6, prev: 0.75, format: "pct", target: "≥ 90%", state: "watch", basis: "showed ÷ (showed + no-show)" }
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

  /* LinkedIn (channel 3): rows the page keeps in its own db. Invented people; profile URLs are test handles only. */
  function addDays(k, n) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(k);
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]) + n * DAY);
    return d.toISOString().slice(0, 10);
  }
  var T = ymd(now);
  var dowT = new Date(T + "T12:00:00Z").getUTCDay();          // 0 = Sunday
  var weekStart = addDays(T, -((dowT + 6) % 7));               // Monday
  var weekEnd = addDays(weekStart, 6);
  function liUrl(handle) { return "https://www.linkedin.com/in/test-" + handle; }
  function liRow(o) {
    return Object.assign({
      name: "", first_name: "", profile_url: "", company: "", role: "", what_they_do: "", industry: "", country: "",
      connect_sent_date: "", accepted_date: "", dm_date: "", loom_variant: "", last_touch_date: "", next_touch_due: "",
      stage: "", reply_type: "", reply_date: "", reply_answered_date: "", meeting_booked: "", outcome: "", slots_offered: "", updatedAt: now - DAY
    }, o, { id: o.id || (/\/in\/([^/]+)/.exec(o.profile_url || "") || [])[1] || "" });
  }
  var liRows = [
    liRow({ name: "Avery Testwell", first_name: "Avery", profile_url: liUrl("avery-testwell"), company: "Testwell Cleaning Example", role: "Owner",
      what_they_do: "commercial office cleaning", industry: "Facilities Services", country: "United States, Texas",
      connect_sent_date: addDays(T, -12), accepted_date: addDays(T, -9), dm_date: addDays(T, -4), loom_variant: "A",
      last_touch_date: addDays(T, -4), next_touch_due: addDays(T, -2), stage: "DM sent" }),
    liRow({ name: "Quinn Fakename", first_name: "Quinn", profile_url: liUrl("quinn-fakename"), company: "Fakename Staffing Example", role: "Founder",
      industry: "Staffing and Recruiting", country: "United States, Ohio",
      connect_sent_date: addDays(T, -22), next_touch_due: addDays(T, -1), stage: "Connect sent" }),
    liRow({ name: "Sam Notreal", first_name: "Sam", profile_url: liUrl("sam-notreal"), company: "Notreal Books Example", role: "Managing Partner",
      industry: "Accounting", country: "United States, Florida",
      connect_sent_date: addDays(T, -40), accepted_date: addDays(T, -36), dm_date: addDays(T, -28), loom_variant: "B",
      last_touch_date: addDays(T, -8), next_touch_due: addDays(T, -1), stage: "Follow-up 3" }),
    liRow({ name: "Jordan Samplely", first_name: "Jordan", profile_url: liUrl("jordan-samplely"), company: "Samplely Janitorial Example", role: "Operations Director",
      industry: "Facilities Services", country: "United States, Illinois",
      connect_sent_date: addDays(T, -16), accepted_date: addDays(T, -13), dm_date: addDays(T, -6), loom_variant: "B",
      last_touch_date: addDays(T, -4), next_touch_due: T, stage: "Follow-up 1" }),
    liRow({ name: "Taylor Mockridge", first_name: "Taylor", profile_url: liUrl("taylor-mockridge"), company: "Mockridge Recruiting Example", role: "CEO",
      industry: "Staffing and Recruiting", country: "United States, Georgia",
      connect_sent_date: addDays(T, -2), next_touch_due: addDays(T, 19), stage: "Connect sent" }),
    liRow({ name: "Drew Dummyson", first_name: "Drew", profile_url: liUrl("drew-dummyson"), company: "Dummyson Tax Example", role: "Owner",
      industry: "Accounting", country: "United States, Arizona",
      connect_sent_date: addDays(T, -5), accepted_date: addDays(T, -1), stage: "Accepted" }),
    liRow({ name: "Riley Example", first_name: "Riley", profile_url: liUrl("riley-example"), company: "Example Facility Care", role: "Owner",
      industry: "Facilities Services", country: "United States, Colorado",
      connect_sent_date: addDays(T, -14), accepted_date: addDays(T, -11), dm_date: addDays(T, -5), loom_variant: "A",
      last_touch_date: addDays(T, -5), stage: "Positive reply", reply_type: "positive", reply_date: addDays(T, -1) }),
    liRow({ name: "Casey Placeholder", first_name: "Casey", profile_url: liUrl("casey-placeholder"), company: "Placeholder Bookkeeping Co", role: "Founder",
      industry: "Accounting", country: "Canada, Ontario",
      connect_sent_date: addDays(T, -15), accepted_date: addDays(T, -12), dm_date: addDays(T, -7), loom_variant: "B",
      last_touch_date: addDays(T, -3), stage: "Reply", reply_type: "more_info", reply_date: addDays(T, -2) }),
    liRow({ name: "Morgan Testcase", first_name: "Morgan", profile_url: liUrl("morgan-testcase"), company: "Testcase Talent Example", role: "Managing Director",
      industry: "Staffing and Recruiting", country: "United States, Texas",
      connect_sent_date: addDays(T, -20), accepted_date: addDays(T, -18), dm_date: addDays(T, -10), loom_variant: "A",
      last_touch_date: addDays(T, -6), stage: "Meeting booked", reply_type: "positive", reply_date: addDays(T, -7), reply_answered_date: addDays(T, -6),
      meeting_booked: iso(now + 2 * DAY), slots_offered: "Thu 1:00 PM CT, Fri 3:30 PM CT" })
  ];
  liRows.sort(function (a, b) {
    var x = a.next_touch_due, y = b.next_touch_due;
    if (!x || !y) return (x ? 0 : 1) - (y ? 0 : 1);
    return x < y ? -1 : x > y ? 1 : 0;
  });
  var info = function (key, label, value, basis) { return { key: key, label: label, value: value, prev: null, format: "pct", target: null, state: value == null ? "no_data" : "info", basis: basis }; };
  model.sources.linkedin = ok(0);
  model.linkedin = {
    rows: liRows,
    editable: true,
    pending: 2,
    noReplyDue: ["test-sam-notreal"],
    weekly: {
      weekStart: weekStart, weekEnd: weekEnd, requestsSent: 14, pending: 2, nearLimit: false,
      acceptance: { key: "acceptance", label: "Acceptance", value: 0.27, prev: null, format: "pct", target: "≥ 30%", state: "watch", basis: "accepted ÷ requests sent 14+ days ago" },
      looms: { A: 4, B: 3 },
      replyRate: { A: info("reply_a", "Reply rate A", 0.25, "replies ÷ Looms sent"), B: info("reply_b", "Reply rate B", 1 / 3, "replies ÷ Looms sent") },
      positiveRate: { A: info("positive_a", "Positive rate A", 0.25, "positive replies ÷ Looms sent"), B: info("positive_b", "Positive rate B", 0, "positive replies ÷ Looms sent") },
      callsBooked: 1, closedWon: 0, closedLost: 0
    }
  };
  model.channels[2] = {
    key: "linkedin", name: "LinkedIn", status: "live", statusText: "9 people in the tracker",
    funnel: [
      { key: "requests", label: "Requests sent", value: 42, prev: 18 },
      { key: "accepted", label: "Accepted", value: 13, prev: 5, conv: false },
      { key: "looms", label: "Looms sent", value: 9, prev: 4, conv: false },
      { key: "replies", label: "Replies", value: 3, prev: 1 },
      { key: "positive", label: "Positive", value: 2, prev: 0 },
      { key: "booked", label: "Calls booked", value: 1, prev: 0, conv: false },
      { key: "won", label: "Closed won", value: 0, prev: 0 }
    ],
    rates: [
      { key: "acceptance", label: "Acceptance", value: 0.27, prev: 0.22, format: "pct", target: "≥ 30% (alert under 15%)", state: "watch", basis: "accepted ÷ requests sent 14+ days ago" },
      info("reply_a", "Reply rate, variant A", 2 / 5, "replies ÷ Looms sent"),
      info("reply_b", "Reply rate, variant B", 1 / 4, "replies ÷ Looms sent"),
      info("positive", "Positive rate", 2 / 9, "positive replies ÷ Looms sent")
    ],
    series: null,
    spend: { usd: 99, note: "From your monthly LinkedIn cost of $99." },
    callsBooked: 1, costPerCall: 99,
    extras: [{ label: "Pending requests", value: "2" }, { label: "Looms sent, variant A", value: "5" }, { label: "Looms sent, variant B", value: "4" }]
  };
  model.costs.linkedin = 99;
  model.followups.reply_now.push(
    { id: "li-r-riley", group: "reply_now", kind: "linkedin_reply", title: "Riley Example · Example Facility Care", detail: "Replied (positive). Answer on LinkedIn.", source: "linkedin", ageMs: null, dueAt: null, overdue: false, url: liUrl("riley-example") },
    { id: "li-r-casey", group: "reply_now", kind: "linkedin_reply", title: "Casey Placeholder · Placeholder Bookkeeping Co", detail: "Replied (more_info). Answer on LinkedIn.", source: "linkedin", ageMs: null, dueAt: null, overdue: false, url: liUrl("casey-placeholder") });
  model.followups.due.push(
    { id: "li-t-avery", group: "due", kind: "linkedin_touch", title: "Avery Testwell · Testwell Cleaning Example", detail: "FU1 due", source: "linkedin", ageMs: null, dueAt: addDays(T, -2), overdue: true, url: liUrl("avery-testwell") },
    { id: "li-t-quinn", group: "due", kind: "linkedin_touch", title: "Quinn Fakename · Fakename Staffing Example", detail: "Pending 21 days. Withdraw the request.", source: "linkedin", ageMs: null, dueAt: addDays(T, -1), overdue: true, url: liUrl("quinn-fakename") },
    { id: "li-t-sam", group: "due", kind: "linkedin_touch", title: "Sam Notreal · Notreal Books Example", detail: "No reply 7 days after FU3. Mark No reply.", source: "linkedin", ageMs: null, dueAt: addDays(T, -1), overdue: true, url: liUrl("sam-notreal") },
    { id: "li-t-jordan", group: "due", kind: "linkedin_touch", title: "Jordan Samplely · Samplely Janitorial Example", detail: "FU2 due", source: "linkedin", ageMs: null, dueAt: T, overdue: false, url: liUrl("jordan-samplely") });
  model.today.waitingOnYou = model.followups.reply_now.length;

  /* Variant 2: GHL needs reconnect, Upwork still loading, Calendar live with upcoming calls. */
  var v2 = clone(model);
  v2.sources.ghl = { state: "error", refreshing: false, storedAt: null, warnings: [],
    error: { code: "needs_reauth", server: "GHL", message: "Unauthorized", fix: "Reconnect GHL in claude.ai Settings → Connectors." } };
  v2.sources.upwork = { state: "loading", refreshing: false, storedAt: null, error: null, warnings: [] };
  v2.sources.calendar = ok(1);
  v2.pipeline = { name: "Sales", url: ex("ghl/opportunities"), stages: [], totals: { open: 0, openValue: 0, wonInRange: 0, wonValueInRange: 0, lostInRange: 0 },
    calls: { stages: [], showRate: { key: "show_rate", label: "Show rate", value: null, prev: null, format: "pct", target: "≥ 90%", state: "no_data", basis: "showed ÷ (showed + no-show)" } } };
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
  v3.sources = { instantly: off, upwork: off, ghl: off, calendar: off,
    linkedin: { state: "unavailable", refreshing: false, storedAt: null, error: null, warnings: ["Editing needs the claude.ai viewer"] } };
  v3.linkedin = { rows: [], editable: false, pending: 0, noReplyDue: [], weekly: null };
  v3.today = { waitingOnYou: 0, callsNext7d: { count: 0, next: null }, openPipeline: { count: 0, value: 0 }, revenue: { value: 0, upworkBilled: 0, ghlWon: 0 }, coldEmailSending: null, alerts: [] };
  v3.channels = [
    { key: "cold_email", name: "Cold email", status: "not_connected", statusText: "", funnel: model.channels[0].funnel.map(function (f) { return { key: f.key, label: f.label, value: null, prev: null }; }),
      rates: [], series: null, spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: [] },
    { key: "upwork", name: "Upwork", status: "not_connected", statusText: "", funnel: model.channels[1].funnel.map(function (f) { return { key: f.key, label: f.label, value: null, prev: null }; }),
      rates: [], series: null, spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: [] },
    { key: "linkedin", name: "LinkedIn", status: "not_connected",
      statusText: "No LinkedIn rows yet. Add or paste them in the LinkedIn tracker below.",
      funnel: model.channels[2].funnel.map(function (f) { return { key: f.key, label: f.label, value: null, prev: null }; }),
      rates: [], series: null, spend: { usd: null, note: "" }, callsBooked: null, costPerCall: null, extras: [] }
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

  /* Variant 5: the LinkedIn rows could not be read from the db. */
  var v5 = clone(model);
  v5.sources.linkedin = { state: "error", refreshing: false, storedAt: null, warnings: [],
    error: { code: "db_error", server: "db", message: "read failed", fix: "Your LinkedIn rows could not be read. Press Refresh." } };
  v5.linkedin = { rows: [], editable: false, pending: 0, noReplyDue: [], weekly: null };
  v5.channels[2] = { key: "linkedin", name: "LinkedIn", status: "error", statusText: "",
    funnel: model.channels[2].funnel.map(function (f) { return { key: f.key, label: f.label, value: null, prev: null }; }),
    rates: [], series: null, spend: { usd: 99, note: "" }, callsBooked: null, costPerCall: null, extras: [] };
  v5.followups.reply_now = v5.followups.reply_now.filter(function (x) { return x.source !== "linkedin"; });
  v5.followups.due = v5.followups.due.filter(function (x) { return x.source !== "linkedin"; });
  v5.today.waitingOnYou = v5.followups.reply_now.length;

  window.__SAMPLE_MODEL__ = model;
  window.__SAMPLE_VARIANTS__ = [
    { name: "Calendar needs reconnect", model: model },
    { name: "GHL needs reconnect, Upwork loading", model: v2 },
    { name: "No connectors", model: v3 },
    { name: "Refreshing Instantly and GHL", model: v4 },
    { name: "LinkedIn rows not read", model: v5 }
  ];
})();
