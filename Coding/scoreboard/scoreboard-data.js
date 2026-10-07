/* Advero Scoreboard: data layer.
 * Reads Instantly, Upwork, GoHighLevel and Google Calendar through the Artifact
 * `mcp` capability and turns them into the model the page renders.
 * Read-only towards every connector. The only writes go to the page's own db:
 * `settings/costs` (saveCosts) and `upworkRooms/<proposalId>` (room cache).
 * Plain ES2020, no dependencies. Browser: globalThis.AdveroData. Node: module.exports.
 */
(function (root) {
  "use strict";

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

  const SOURCE_KEYS = ["instantly", "upwork", "ghl", "calendar"];
  const DAY_MS = 86400000;
  const HOUR_MS = 3600000;
  const MAX_IN_FLIGHT = 4;
  const CACHE = { staleTime: 300000, gcTime: 86400000 };
  const EPS = 1e-12;
  const GHL_REASON = "Scoreboard read";
  const ROOM_RECHECK_MS = 12 * HOUR_MS;
  const ROOM_RECHECK_MAX_AGE_MS = 30 * DAY_MS;
  const COLUMN_CAP = 25;

  const CAMPAIGN_STATUS = { "0": "Draft", "1": "Active", "2": "Paused", "3": "Completed",
    "4": "Running subsequences", "-1": "Accounts unhealthy", "-2": "Bounce protect", "-99": "Suspended" };

  // ------------------------------------------------------------------ small utils

  const arr = v => (Array.isArray(v) ? v : []);
  const str = v => (typeof v === "string" ? v : v == null ? "" : String(v));
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);

  function num(v) {
    if (typeof v === "number") return Number.isFinite(v) ? v : 0;
    if (typeof v === "string" && v.trim() !== "") {
      const n = Number(v.replace(/[$,\s]/g, ""));
      return Number.isFinite(n) ? n : 0;
    }
    if (isObj(v) && "rawValue" in v) return num(v.rawValue);
    return 0;
  }

  /** Any timestamp shape (ms number, seconds number, numeric string, ISO, {rawValue}) to epoch ms, or null. */
  function toMs(v) {
    if (v == null || v === "") return null;
    if (typeof v === "number") return Number.isFinite(v) ? (Math.abs(v) < 1e11 ? v * 1000 : v) : null;
    if (v instanceof Date) { const t = v.getTime(); return Number.isFinite(t) ? t : null; }
    if (isObj(v)) return "rawValue" in v ? toMs(v.rawValue) : null;
    const s = String(v).trim();
    if (/^-?\d+(\.\d+)?$/.test(s)) return toMs(Number(s));
    const t = Date.parse(s);
    return Number.isFinite(t) ? t : null;
  }

  /** Strip Upwork's <untrusted_participant_content> wrapper. The result is still untrusted text. */
  function unwrap(v) {
    return str(v).replace(/<\/?untrusted_participant_content>/g, "").trim();
  }

  /** Collapse every run of whitespace (newlines included) to one space and cut so the result,
   *  ellipsis included, is at most `n` characters. */
  function clip(s, n) {
    const t = str(s).replace(/\s+/g, " ").trim();
    return t.length > n ? t.slice(0, Math.max(0, n - 1)).trimEnd() + "…" : t;
  }

  /** Resolve with the promise's value, or with `fallback` once `ms` pass. Never rejects: a rejection also gives `fallback`. */
  function withTimeout(p, ms, fallback) {
    return new Promise(resolve => {
      let done = false;
      const timer = setTimeout(() => { if (!done) { done = true; resolve(fallback); } }, ms);
      Promise.resolve(p).then(
        v => { if (!done) { done = true; clearTimeout(timer); resolve(v); } },
        () => { if (!done) { done = true; clearTimeout(timer); resolve(fallback); } });
    });
  }
  const TIMED_OUT = { __timedOut: true };
  const DB_TIMEOUT_MS = 3000;

  /** Only https links leave the data layer. */
  function safeUrl(u) {
    const s = str(u).trim();
    return /^https:\/\/[^\s"'<>]+$/i.test(s) ? s : null;
  }

  const round2 = n => Math.round(n * 100) / 100;
  const lower = s => str(s).trim().toLowerCase();
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  const _intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const _usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const _usd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtInt = n => _intFmt.format(num(n));
  const fmtUsd = (n, cents) => (cents ? _usd2 : _usd0).format(num(n));
  const fmtPct = (f, digits) => `${(f * 100).toFixed(digits == null ? 1 : digits)}%`;

  // ------------------------------------------------------------------ dates (America/Chicago)

  const _fmtCache = {};
  function dayFormatter(tz) {
    const k = "d|" + tz;
    return _fmtCache[k] || (_fmtCache[k] = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }));
  }
  function partsFormatter(tz) {
    const k = "p|" + tz;
    return _fmtCache[k] || (_fmtCache[k] = new Intl.DateTimeFormat("en-US", {
      timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  /** YYYY-MM-DD of an instant, in the time zone (default Central). */
  function ymd(ms, tz) {
    return dayFormatter(tz || CONFIG.timeZone).format(new Date(ms));
  }

  /** Pure calendar arithmetic on a YYYY-MM-DD string. */
  function addDays(day, n) {
    const [y, m, d] = day.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
  }

  /** Wall-clock offset (ms) of the zone at an instant: wall time read as UTC minus the instant. */
  function tzOffsetMs(ms, tz) {
    const p = {};
    for (const part of partsFormatter(tz).formatToParts(new Date(ms))) p[part.type] = part.value;
    const wall = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second);
    return wall - Math.floor(ms / 1000) * 1000;
  }

  /** Epoch ms of local midnight that starts `day` in the zone. DST-safe. */
  function startOfDayMs(day, tz) {
    tz = tz || CONFIG.timeZone;
    const [y, m, d] = day.split("-").map(Number);
    const guess = Date.UTC(y, m - 1, d);
    const first = guess - tzOffsetMs(guess, tz);
    return guess - tzOffsetMs(first, tz);
  }

  /** Last ms of `day` in the zone. */
  function endOfDayMs(day, tz) {
    return startOfDayMs(addDays(day, 1), tz) - 1;
  }

  function dateList(start, end) {
    const out = [];
    for (let d = start; d <= end && out.length < 400; d = addDays(d, 1)) out.push(d);
    return out;
  }

  function normDays(n) {
    return n === 7 || n === 90 ? n : 30;
  }

  /** The range: last `days` calendar days ending today (Central), inclusive, and the `days` before it. */
  function rangeFor(nowMs, days, tz) {
    tz = tz || CONFIG.timeZone;
    days = normDays(days);
    const end = ymd(nowMs, tz);
    const start = addDays(end, -(days - 1));
    const prevEnd = addDays(start, -1);
    const prevStart = addDays(start, -days);
    return {
      days, start, end, prevStart, prevEnd, label: `Last ${days} days`,
      startMs: startOfDayMs(start, tz), endMs: endOfDayMs(end, tz),
      prevStartMs: startOfDayMs(prevStart, tz), prevEndMs: endOfDayMs(prevEnd, tz),
      todayStartMs: startOfDayMs(end, tz), todayEndMs: endOfDayMs(end, tz)
    };
  }

  const inRange = (ms, R) => ms != null && ms >= R.startMs && ms <= R.endMs;
  const inPrev = (ms, R) => ms != null && ms >= R.prevStartMs && ms <= R.prevEndMs;

  function toNowMs(now) {
    const t = toMs(now);
    return t == null ? Date.now() : t;
  }

  // ------------------------------------------------------------------ errors

  const KNOWN_CODES = new Set(["needs_reauth", "server_not_connected", "selection_required", "server_not_found",
    "server_unavailable", "not_in_manifest", "blocked_by_policy", "approval_required", "tool_error", "bad_request",
    "cancelled", "rate_limited", "upstream_error", "not_granted", "capability_disabled", "capability_removed",
    "transform_error", "consent_required", "user_changed"]);
  const UNAVAILABLE_CODES = new Set(["not_granted", "capability_disabled", "capability_removed", "user_changed"]);

  /** Fix copy for an error code (spec "Calling tools"). */
  function fixFor(code, server, message) {
    switch (code) {
      case "needs_reauth":
        return `Reconnect ${server} in claude.ai Settings → Connectors.`;
      case "server_not_connected":
      case "server_not_found":
        return `Add the ${server} connector in claude.ai Settings → Connectors.`;
      case "selection_required":
        return `Choose which ${server} connector this page should use when claude.ai asks.`;
      case "not_in_manifest":
      case "consent_required":
        return `${server} is switched off for this page. Turn it on in the page's Permissions menu.`;
      case "blocked_by_policy":
      case "approval_required":
        return `Your organization's policy blocks ${server} on this page.`;
      case "tool_error":
        return `${server} returned an error: ${clipExact(str(message), 160)}`;
      default:
        return `${server} didn't answer. Press Refresh in a minute.`;
    }
  }

  function clipExact(s, n) {
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  /** Normalize anything thrown into a source error: { code, server, message, fix, state, retryable, result }. */
  function toSourceError(e, server) {
    if (e && e.__sourceError) return e;
    const rawCode = e && typeof e.code === "string" ? e.code : "upstream_error";
    const code = KNOWN_CODES.has(rawCode) ? rawCode : "upstream_error";
    const message = str(e && e.message != null ? e.message : e);
    const out = {
      __sourceError: true,
      code, server,
      message: clipExact(message, 300),
      fix: UNAVAILABLE_CODES.has(code) ? "" : fixFor(code, server, message),
      state: UNAVAILABLE_CODES.has(code) ? "unavailable" : "error",
      retryable: !!(e && e.retryable === true),
      result: e ? e.result : undefined,
      rawMessage: message
    };
    return out;
  }

  /** The contract's error object. */
  function publicError(se) {
    return { code: se.code, server: se.server, message: se.message, fix: se.fix };
  }

  function isNotFound(se) {
    if (!se || se.code !== "tool_error") return false;
    let blob = str(se.rawMessage);
    try { blob += " " + JSON.stringify(se.result === undefined ? null : se.result); } catch (_) { /* ignore */ }
    return /NOT_FOUND/.test(blob);
  }

  // ------------------------------------------------------------------ calling tools

  function makeLimiter(max) {
    let active = 0;
    const queue = [];
    const next = () => {
      if (active >= max || !queue.length) return;
      active++;
      const job = queue.shift();
      Promise.resolve().then(job.fn).then(job.resolve, job.reject).finally(() => { active--; next(); });
    };
    return fn => new Promise((resolve, reject) => { queue.push({ fn, resolve, reject }); next(); });
  }

  function readPayload(res) {
    if (!res || typeof res !== "object") return res;
    let p = res.payload;
    if (p === undefined && res.structuredContent !== undefined) p = res.structuredContent;
    if (p === undefined && Array.isArray(res.content)) {
      const t = res.content.find(b => b && b.type === "text");
      if (t) p = t.text;
    }
    if (typeof p === "string") {
      try { p = JSON.parse(p); } catch (_) { /* keep the string */ }
    }
    return p;
  }

  const defaultSleep = ms => new Promise(r => setTimeout(r, ms));

  /**
   * The one helper every tool call goes through: per-source concurrency (4), cache options,
   * one retry for retryable errors, payload parsing, storedAt tracking and error mapping.
   */
  function makeCaller(opts) {
    const server = CONFIG.servers[opts.serverKey] || opts.serverKey;
    const limit = makeLimiter(MAX_IN_FLIGHT);
    const sleep = typeof opts.sleep === "function" ? opts.sleep : defaultSleep;
    const random = typeof opts.random === "function" ? opts.random : Math.random;
    const meta = { oldestCached: null, calls: 0, aborted: false };
    const options = { cache: { staleTime: CACHE.staleTime, gcTime: CACHE.gcTime, refresh: !!opts.refresh } };
    const abortedError = () => Object.assign(sourceError(server, "cancelled", "Stopped: another call for this source failed."), { aborted: true });

    // Once the source's main chain failed (meta.aborted), queued and later calls stop instead of paging on.
    const attempt = (tool, input) => limit(() => {
      if (meta.aborted) throw abortedError();
      meta.calls++;
      return opts.mcp.callTool(server, tool, input, options);
    });

    async function call(tool, input) {
      if (meta.aborted) throw abortedError();
      let res;
      try {
        res = await attempt(tool, input);
      } catch (e) {
        if (e && e.aborted) throw e;
        if (!(e && e.retryable === true)) throw toSourceError(e, server);
        const after = e.retryAfterMs;
        const wait = typeof after === "number" && Number.isFinite(after) && after >= 0
          ? Math.min(after, 60000) : 1500 + Math.floor(random() * 1500);
        await sleep(wait);
        if (meta.aborted) throw abortedError();
        try {
          res = await attempt(tool, input);
        } catch (e2) {
          throw toSourceError(e2, server);
        }
      }
      const st = res && res.cache && typeof res.cache.storedAt === "number" ? res.cache.storedAt : null;
      if (st != null && (meta.oldestCached == null || st < meta.oldestCached)) meta.oldestCached = st;
      return readPayload(res);
    }

    const abort = () => { meta.aborted = true; };

    /** Run a source's main call chains together. The first chain to fail aborts the others, and its error is the one thrown. */
    const main = (chains) => Promise.all(chains.map(p => Promise.resolve(p).catch(e => { abort(); throw e; })));

    return { call, meta, server, abort, main };
  }

  function sourceError(server, code, message) {
    return toSourceError({ code, message }, server);
  }

  // ------------------------------------------------------------------ source 1: Instantly

  function listOf(p, keys) {
    if (Array.isArray(p)) return p;
    if (!isObj(p)) return [];
    for (const k of keys) if (Array.isArray(p[k])) return p[k];
    return [];
  }

  function overviewOf(p) {
    if (Array.isArray(p)) return isObj(p[0]) ? p[0] : {};
    if (isObj(p) && isObj(p.result) && !Array.isArray(p.result)) return p.result;
    return isObj(p) ? p : {};
  }

  async function fetchInstantly(caller, R) {
    const T = CONFIG.tools.instantly;
    const cur = { start_date: R.start, end_date: R.end };
    const prev = { start_date: R.prevStart, end_date: R.prevEnd };
    const warnings = [];

    const unreadP = caller.call(T.unread, {}).then(p => ({ ok: true, p }), e => ({ ok: false, e }));

    async function campaigns() {
      const items = [];
      let after = null;
      for (let page = 0; page < 5; page++) {
        const input = { limit: 100 };
        if (after) input.starting_after = after;
        const p = await caller.call(T.campaigns, input);
        items.push(...listOf(p, ["items", "data"]));
        after = isObj(p) ? p.next_starting_after : null;
        if (!after) break;
      }
      return items;
    }

    const [overview, overviewPrev, daily, analytics, camps, interested, booked] = await caller.main([
      caller.call(T.overview, cur),
      caller.call(T.overview, prev),
      caller.call(T.daily, cur),
      caller.call(T.campaignAnalytics, cur),
      campaigns(),
      caller.call(T.leads, { filter: "FILTER_LEAD_INTERESTED", limit: 100 }),
      caller.call(T.leads, { filter: "FILTER_LEAD_MEETING_BOOKED", limit: 100 })
    ]);

    const u = await unreadP;
    let unread = null;
    if (u.ok) {
      unread = typeof u.p === "number" ? u.p : num(isObj(u.p) ? u.p.count : 0);
    } else {
      warnings.push(`Unread reply count didn't load (${u.e.code}).`);
    }

    return {
      data: {
        overview: overviewOf(overview),
        overviewPrev: overviewOf(overviewPrev),
        daily: listOf(daily, ["result", "items", "data"]),
        campaignAnalytics: listOf(analytics, ["result", "items", "data"]),
        campaigns: camps,
        leadsInterested: listOf(interested, ["items", "data"]),
        leadsBooked: listOf(booked, ["items", "data"]),
        unread
      },
      warnings
    };
  }

  const RULES = {
    cold_reply: { dir: "up", green: 0.01, alert: 0.01, target: "≥ 1.0%" },
    cold_positive: { dir: "up", green: 0.007, alert: 0.005, target: "≥ 0.7%" },
    cold_bounce: { dir: "down", green: 0.01, alert: 0.02, target: "≤ 1.0%" },
    cold_p2b: { dir: "up", green: 0.5, alert: 0.4, target: "≥ 50%" },
    upwork_reply: { dir: "up", green: 0.15, alert: 0.08, target: "≥ 15%" },
    show_rate: { dir: "up", green: 0.9, alert: 0.8, target: "≥ 90%" }
  };

  function rateState(value, rule) {
    if (value == null || !Number.isFinite(value)) return "no_data";
    if (!rule) return "info";
    if (rule.dir === "down") {
      if (value <= rule.green + EPS) return "green";
      if (value > rule.alert + EPS) return "alert";
      return "watch";
    }
    if (value >= rule.green - EPS) return "green";
    if (value < rule.alert - EPS) return "alert";
    return "watch";
  }

  function makeRate(key, label, n, d, pn, pd, rule) {
    const value = d > 0 ? n / d : null;
    const prev = pd != null && pd > 0 && pn != null ? pn / pd : null;
    return { key, label, value, prev, format: "pct", target: rule ? rule.target : null,
      state: value == null ? "no_data" : rateState(value, rule) };
  }

  const COLD_FUNNEL = [
    ["sent", "Emails sent"], ["leads", "New leads reached"], ["replies", "Human replies"],
    ["positive", "Positive replies"], ["booked", "Calls booked"], ["won", "Closed"]
  ];
  const COLD_RATES = [
    ["reply_rate", "Reply rate", "cold_reply"], ["positive_rate", "Positive rate", "cold_positive"],
    ["bounce_rate", "Bounce rate", "cold_bounce"], ["positive_to_booked", "Positive → booked", "cold_p2b"]
  ];

  function coldNumbers(o) {
    if (!isObj(o)) return null;
    return {
      sent: num(o.emails_sent_count),
      leads: num(o.new_leads_contacted_count),
      replies: num(o.reply_count_unique),
      positive: num(o.total_opportunities),
      booked: num(o.total_meeting_booked) + num(o.total_meeting_completed) + num(o.total_closed),
      won: num(o.total_closed),
      bounced: num(o.bounced_count)
    };
  }

  function coldRates(c, p) {
    const pv = (k) => (p ? p[k] : null);
    return [
      makeRate("reply_rate", "Reply rate", c.replies, c.leads, pv("replies"), pv("leads"), RULES.cold_reply),
      makeRate("positive_rate", "Positive rate", c.positive, c.leads, pv("positive"), pv("leads"), RULES.cold_positive),
      makeRate("bounce_rate", "Bounce rate", c.bounced, c.sent, pv("bounced"), pv("sent"), RULES.cold_bounce),
      makeRate("positive_to_booked", "Positive → booked", c.booked, c.positive, pv("booked"), pv("positive"), RULES.cold_p2b)
    ];
  }

  function leadName(l) {
    const name = [str(l.first_name).trim(), str(l.last_name).trim()].filter(Boolean).join(" ");
    const parts = [name, str(l.company_name).trim()].filter(Boolean);
    return parts.length ? parts.join(" · ") : str(l.email);
  }

  function isUnanswered(l) {
    return (toMs(l.timestamp_last_reply) || 0) > (toMs(l.timestamp_last_contact) || 0);
  }

  function deriveInstantly(d, R) {
    const cur = coldNumbers(d.overview) || coldNumbers({});
    const prev = coldNumbers(d.overviewPrev);
    const funnel = COLD_FUNNEL.map(([key, label]) => ({ key, label, value: cur[key], prev: prev ? prev[key] : null }));
    const rates = coldRates(cur, prev);

    // daily series, zero-filled across the range
    const byDate = {};
    for (const row of arr(d.daily)) {
      if (!isObj(row)) continue;
      const day = str(row.date).slice(0, 10);
      if (!byDate[day]) byDate[day] = { a: 0, b: 0, c: 0 };
      byDate[day].a += num(row.sent);
      byDate[day].b += num(row.replies);
      byDate[day].c += num(row.unique_opportunities);
    }
    const dates = dateList(R.start, R.end);
    const points = dates.map(date => ({ date, a: byDate[date] ? byDate[date].a : 0, b: byDate[date] ? byDate[date].b : 0, c: byDate[date] ? byDate[date].c : 0 }));

    // campaigns: join analytics rows with the list by id
    const list = arr(d.campaigns).filter(isObj);
    const analytics = {};
    for (const a of arr(d.campaignAnalytics)) if (isObj(a) && a.campaign_id != null) analytics[str(a.campaign_id)] = a;
    const seen = new Set();
    const campaigns = [];
    const pushRow = (id, c, a) => {
      const statusRaw = c && c.status != null ? c.status : a ? a.campaign_status : null;
      const status = statusRaw == null || statusRaw === "" ? null : Number(statusRaw);
      const sent = a ? num(a.emails_sent_count) : 0;
      campaigns.push({
        id,
        name: str((c && c.name) || (a && a.campaign_name) || id),
        status,
        statusLabel: status == null ? "Unknown" : CAMPAIGN_STATUS[String(status)] || `Status ${status}`,
        sent,
        newLeads: a ? num(a.new_leads_contacted_count) : 0,
        replies: a ? num(a.reply_count_unique) : 0,
        positive: a ? num(a.total_opportunities) : 0,
        bounceRate: sent > 0 ? num(a.bounced_count) / sent : null,
        dailyLimit: c && c.daily_limit != null ? num(c.daily_limit) : null,
        url: safeUrl(CONFIG.links.instantlyCampaign(encodeURIComponent(id)))
      });
    };
    for (const c of list) {
      const id = str(c.id);
      if (!id || seen.has(id)) continue;
      seen.add(id);
      pushRow(id, c, analytics[id]);
    }
    for (const id of Object.keys(analytics)) if (!seen.has(id)) { seen.add(id); pushRow(id, null, analytics[id]); }
    campaigns.sort((x, y) => (y.status === 1) - (x.status === 1) || y.sent - x.sent || x.name.localeCompare(y.name));

    const counts = { total: campaigns.length, active: 0, paused: 0, drafts: 0 };
    for (const c of campaigns) {
      if (c.status === 1) counts.active++;
      else if (c.status === 2) counts.paused++;
      else if (c.status === 0) counts.drafts++;
    }
    const lastTwo = points.slice(-2);
    const sending = counts.active > 0 && lastTwo.some(p => p.a > 0);

    // interested / booked leads
    const campaignName = {};
    for (const c of campaigns) campaignName[c.id] = c.name;
    const leads = [];
    const leadKeys = new Set();
    for (const l of arr(d.leadsInterested).concat(arr(d.leadsBooked))) {
      if (!isObj(l)) continue;
      const k = lower(l.email) || str(l.id);
      if (!k || leadKeys.has(k)) continue;
      leadKeys.add(k);
      leads.push(l);
    }
    const unanswered = leads.filter(isUnanswered).map(l => ({
      id: str(l.id || l.email), email: str(l.email), title: leadName(l),
      campaign: campaignName[str(l.campaign)] || "Instantly",
      lastReplyMs: toMs(l.timestamp_last_reply)
    }));
    const leadEmails = new Set(leads.map(l => lower(l.email)).filter(Boolean));

    const o = isObj(d.overview) ? d.overview : {};
    const extras = [
      { label: "Active campaigns", value: `${counts.active} of ${counts.total}` },
      { label: "Unread in Unibox", value: d.unread == null ? "—" : fmtInt(d.unread) },
      { label: "Auto-replies (not counted)", value: fmtInt(o.reply_count_automatic_unique) },
      { label: "Unsubscribed", value: fmtInt(o.unsubscribed_count) },
      { label: "Interested", value: fmtInt(o.total_interested) },
      { label: "Opportunity value", value: fmtUsd(o.total_opportunity_value) }
    ];

    return { funnel, rates, points, campaigns, counts, sending, unanswered, leadEmails, unread: d.unread, extras, booked: cur.booked };
  }

  // ------------------------------------------------------------------ source 2: Upwork

  const UPWORK_STATUSES = [
    { status: "Accepted", max: 12, stopEarly: true },
    { status: "Archived", max: 12, stopEarly: true },
    { status: "Offered", max: 3, stopEarly: false },
    { status: "Hired", max: 3, stopEarly: false },
    { status: "Declined", max: 3, stopEarly: false },
    { status: "Withdrawn", max: 3, stopEarly: false }
  ];

  const statusRank = b => (b === "Hired" ? 2 : b === "Offered" ? 1 : 0);

  function normProposal(node, bucket) {
    const n = isObj(node) ? node : {};
    const job = isObj(n.marketplaceJobPosting) ? n.marketplaceJobPosting : {};
    const st = isObj(n.status) ? n.status : {};
    const created = n.auditDetails && n.auditDetails.createdDateTime;
    let url = str(job.url).trim();
    if (url && url.startsWith("/")) url = "https://www.upwork.com" + url;
    return {
      id: str(n.id),
      bucket,
      createdAt: toMs(isObj(created) ? created.rawValue : created),
      title: unwrap(job.content && job.content.title) || "Untitled job",
      url: safeUrl(url),
      statusLabel: unwrap(st.status_label || st.status || bucket),
      reason: unwrap(st.reason && st.reason.reason) || null,
      boosted: n.boosted === true,
      connectsBid: n.terms && n.terms.connectsBid != null ? num(n.terms.connectsBid) : null
    };
  }

  let _roomShapeLogged = false;
  function extractRoomId(p) {
    if (!_roomShapeLogged && typeof console !== "undefined" && console.debug) {
      _roomShapeLogged = true;
      try {
        const shape = isObj(p) ? Object.keys(p).map(k => (isObj(p[k]) ? `${k}{${Object.keys(p[k]).join(",")}}` : k)).join(",") : typeof p;
        console.debug("[AdveroData] get_room payload shape:", shape);
      } catch (_) { /* ignore */ }
    }
    if (!isObj(p)) return null;
    const cands = [p.id, p.roomId, p.room && p.room.id, p.room && p.room.roomId,
      p.data && p.data.room && p.data.room.id, p.data && p.data.roomId, p.data && p.data.id];
    for (const c of cands) if ((typeof c === "string" && c) || typeof c === "number") return String(c);
    return null;
  }

  // In-memory room cache, used when there is no db (or it can't be read). Survives reloads of the model, not the page.
  // It follows the same rules as the db cache, including the 12 h re-check of a null: within one page session that
  // costs at most one extra get_room call per young unanswered proposal every 12 h, which is acceptable (review item e).
  const _memRooms = new Map();

  async function canWriteDb(db, user) {
    if (!db) return false;
    try {
      const v = user && typeof user.can === "function" ? await user.can("data.write") : null;
      return v !== false;
    } catch (_) {
      return true;
    }
  }

  /** Decide whether a cached entry answers the question, per the cache rules. */
  function roomCacheVerdict(entry, createdAt, nowMs) {
    if (!entry) return { use: false };
    if (typeof entry.roomId === "string" && entry.roomId) return { use: true, roomId: entry.roomId };
    if (entry.roomId === null) {
      const checkedAt = num(entry.checkedAt);
      const young = createdAt != null && nowMs - createdAt < ROOM_RECHECK_MAX_AGE_MS;
      if (nowMs - checkedAt > ROOM_RECHECK_MS && young) return { use: false };
      return { use: true, roomId: null };
    }
    return { use: false };
  }

  /** Read the cached room docs that can matter for these proposals: a doc is written after its proposal was
   *  created, so `checkedAt >=` the oldest createdAt covers them all; newest first, so a full window drops the oldest. */
  async function readRoomCache(db, proposals, timeoutMs) {
    const times = proposals.map(p => p.createdAt).filter(t => typeof t === "number" && Number.isFinite(t));
    if (!times.length) return new Map();
    const oldest = Math.min(...times);
    let q;
    try {
      q = db.collection("upworkRooms").where("checkedAt", ">=", oldest).orderBy("checkedAt", "desc").limit(1000);
    } catch (_) {
      return null;
    }
    const res = await withTimeout(Promise.resolve().then(() => q.get()).then(snap => ({ snap })), timeoutMs, null);
    if (!res) return null;
    const map = new Map();
    for (const doc of arr(res.snap && res.snap.docs)) {
      if (!doc || doc.exists === false) continue;
      const body = typeof doc.data === "function" ? doc.data() : null;
      if (isObj(body)) map.set(str(doc.id), { roomId: body.roomId === undefined ? undefined : body.roomId, checkedAt: body.checkedAt });
    }
    return map;
  }

  async function checkRooms(proposals, caller, env) {
    const { db, user, nowMs } = env;
    const timeoutMs = typeof env.dbTimeoutMs === "number" ? env.dbTimeoutMs : DB_TIMEOUT_MS;
    // Load-scoped: one rejected (or stalled) write stops every later room-cache write in this load.
    const writeState = isObj(env.roomWrites) ? env.roomWrites : { disabled: false };
    const T = CONFIG.tools.upwork;
    const out = new Map();
    const dbMap = db && proposals.length ? await readRoomCache(db, proposals, timeoutMs) : null;
    const writable = dbMap && !writeState.disabled ? await withTimeout(canWriteDb(db, user), timeoutMs, false) : false;
    const writes = [];
    let failed = 0;

    await Promise.all(proposals.map(async (pr) => {
      const fromDb = dbMap ? dbMap.get(pr.id) : undefined;
      const cached = fromDb || _memRooms.get(pr.id);
      const v = roomCacheVerdict(cached, pr.createdAt, nowMs);
      if (v.use) { out.set(pr.id, v.roomId ? true : false); return; }
      let roomId;
      try {
        const p = await caller.call(T.proposals, { action: "get_room", org_uid: CONFIG.upworkOrg, params: { proposal_id: pr.id } });
        roomId = extractRoomId(p);
        if (roomId == null) {
          let blob = "";
          try { blob = JSON.stringify(p); } catch (_) { /* ignore */ }
          if (!/NOT_FOUND/.test(blob)) { failed++; out.set(pr.id, null); return; }
        }
      } catch (e) {
        if (isNotFound(e)) roomId = null;
        else { failed++; out.set(pr.id, null); return; }
      }
      out.set(pr.id, roomId ? true : false);
      const entry = { roomId: roomId || null, checkedAt: nowMs };
      _memRooms.set(pr.id, entry);
      if (!dbMap) return;
      if (fromDb && fromDb.roomId === null && entry.roomId === null) {
        // A re-checked null that is still null: only checkedAt changed.
        if (num(fromDb.checkedAt) !== entry.checkedAt) writes.push({ id: pr.id, patch: { checkedAt: entry.checkedAt }, entry });
      } else if (!fromDb || fromDb.roomId !== entry.roomId || num(fromDb.checkedAt) !== entry.checkedAt) {
        writes.push({ id: pr.id, entry });
      }
    }));

    // One write at a time, so the first rejection really is the last write of this load.
    let writeFailed = false;
    if (writable) {
      for (const w of writes) {
        if (writeState.disabled) break;
        const ref = db.collection("upworkRooms").doc(w.id);
        const ok = await withTimeout(Promise.resolve().then(() => (w.patch && typeof ref.update === "function"
          ? ref.update(w.patch) : ref.set(w.entry))).then(() => true), timeoutMs, false);
        if (!ok) { writeState.disabled = true; writeFailed = true; }
      }
    }

    const warnings = [];
    if (failed) warnings.push(`Couldn't check ${plural(failed, "proposal", "proposals")} for a client reply.`);
    if (writeFailed) warnings.push("Couldn't save the proposal-room cache.");
    return { replied: out, warnings };
  }

  async function fetchUpwork(caller, R, env) {
    const T = CONFIG.tools.upwork;
    const org = CONFIG.upworkOrg;
    const warnings = [];

    async function pageProposals(cfg) {
      const nodes = [];
      let cursor = null;
      for (let page = 0; page < cfg.max; page++) {
        const params = { status: cfg.status, limit: 10, sort_field: "CREATEDDATETIME", sort_order: "DESC" };
        if (cursor) params.cursor = cursor;
        const p = await caller.call(T.proposals, { action: "list", org_uid: org, params });
        const vp = isObj(p) && isObj(p.data) && isObj(p.data.vendorProposals) ? p.data.vendorProposals : {};
        const batch = arr(vp.edges).map(e => normProposal(e && e.node, cfg.status)).filter(x => x.id);
        nodes.push(...batch);
        if (cfg.stopEarly && batch.length) {
          const times = batch.map(b => b.createdAt).filter(t => t != null);
          if (times.length && Math.min(...times) < R.prevStartMs) break;
        }
        const hasMore = isObj(p) && p.hasMore === true;
        cursor = isObj(p) ? p.next_cursor : null;
        if (!hasMore || !cursor) break;
      }
      return nodes;
    }

    async function rooms() {
      const all = [];
      let cursor = null;
      for (let page = 0; page < 3; page++) {
        const params = { room_type: "INTERVIEW", limit: 100 };
        if (cursor) params.cursor = cursor;
        const p = await caller.call(T.messages, { action: "list_rooms", org_uid: org, params });
        all.push(...listOf(isObj(p) && isObj(p.data) ? p.data : p, ["rooms"]));
        cursor = isObj(p) ? p.next_cursor : null;
        if (!(isObj(p) && p.hasMore === true) || !cursor) break;
      }
      return all.filter(isObj);
    }

    async function connects() {
      let balance = null;
      const tx = [];
      let cursor = null;
      for (let page = 0; page < 10; page++) {
        const params = { limit: 10 };
        if (cursor) params.cursor = cursor;
        const p = await caller.call(T.financials, { action: "connects_balance", org_uid: org, params });
        if (!isObj(p)) break;
        if (balance == null && isObj(p.balance) && p.balance.connectsBalance != null) balance = num(p.balance.connectsBalance);
        const batch = arr(p.usage_history && p.usage_history.transactions).filter(isObj).map(t => ({
          amount: num(isObj(t.amount) ? t.amount.rawValue : t.amount),
          createdAt: toMs(t.createdDateTime)
        }));
        tx.push(...batch);
        const times = batch.map(t => t.createdAt).filter(t => t != null);
        if (times.length && Math.min(...times) < R.startMs) break;
        cursor = p.next_cursor;
        if (p.hasMore !== true || !cursor) break;
      }
      return { balance, transactions: tx };
    }

    const summaryP = caller.call(T.financials, { action: "summary", org_uid: org, params: { from_date: R.start, to_date: R.end } })
      .then(p => ({ ok: true, p }), e => ({ ok: false, e }));

    const [lists, roomList, conn] = await caller.main([
      caller.main(UPWORK_STATUSES.map(pageProposals)),
      rooms(),
      connects()
    ]);

    // dedupe by id, keeping the most advanced status (Hired > Offered > the rest; ties keep the first seen),
    // then keep the range + previous range
    const byId = new Map();
    for (const list of lists) for (const pr of list) {
      const have = byId.get(pr.id);
      if (!have || statusRank(pr.bucket) > statusRank(have.bucket)) byId.set(pr.id, pr);
    }
    const proposals = [];
    for (const pr of byId.values()) {
      if (pr.createdAt != null && pr.createdAt >= R.prevStartMs && pr.createdAt <= R.endMs) proposals.push(pr);
    }

    const rc = await checkRooms(proposals, caller, { db: env.db, user: env.user, nowMs: env.nowMs, R,
      dbTimeoutMs: env.dbTimeoutMs, roomWrites: env.roomWrites });
    for (const pr of proposals) pr.replied = rc.replied.has(pr.id) ? rc.replied.get(pr.id) : null;
    warnings.push(...rc.warnings);

    const s = await summaryP;
    let summary = null;
    if (s.ok && isObj(s.p)) summary = s.p;
    else warnings.push(`Upwork billing summary didn't load (${s.ok ? "empty" : s.e.code}).`);

    return { data: { proposals, rooms: roomList, connects: conn, summary }, warnings };
  }

  function deriveUpwork(d, R, nowMs) {
    const all = arr(d.proposals);
    const cur = all.filter(p => inRange(p.createdAt, R));
    const prev = all.filter(p => inPrev(p.createdAt, R));
    const isOffer = p => p.bucket === "Offered" || p.bucket === "Hired";
    const count = (list) => ({
      proposals: list.length,
      replies: list.filter(p => p.replied === true).length,
      offers: list.filter(isOffer).length,
      hired: list.filter(p => p.bucket === "Hired").length
    });
    const c = count(cur), pv = count(prev);
    const funnel = [
      { key: "proposals", label: "Proposals sent", value: c.proposals, prev: pv.proposals },
      { key: "replies", label: "Client replied", value: c.replies, prev: pv.replies },
      { key: "offers", label: "Offers", value: c.offers, prev: pv.offers },
      { key: "hired", label: "Hired", value: c.hired, prev: pv.hired }
    ];
    const rates = [
      makeRate("reply_rate", "Client reply rate", c.replies, c.proposals, pv.replies, pv.proposals, RULES.upwork_reply),
      makeRate("hire_rate", "Hire rate", c.hired, c.proposals, pv.hired, pv.proposals, null)
    ];

    const days = {};
    for (const p of cur) {
      const day = ymd(p.createdAt);
      if (!days[day]) days[day] = { a: 0, b: 0 };
      days[day].a++;
      if (p.replied === true) days[day].b++;
    }
    const points = dateList(R.start, R.end).map(date => ({ date, a: days[date] ? days[date].a : 0, b: days[date] ? days[date].b : 0 }));

    const conn = isObj(d.connects) ? d.connects : { balance: null, transactions: [] };
    let connectsSpent = 0;
    for (const t of arr(conn.transactions)) if (t.amount < 0 && inRange(t.createdAt, R)) connectsSpent += -t.amount;
    const spendUsd = round2(connectsSpent * CONFIG.upworkConnectUsd);
    const boosted = cur.filter(p => p.boosted).length;
    const boostedShare = cur.length ? boosted / cur.length : null;
    const billedUsd = isObj(d.summary) && isObj(d.summary.totals) ? num(d.summary.totals.billed) : null;

    const proposals = cur.slice().sort((a, b) => b.createdAt - a.createdAt).map(p => ({
      id: p.id, title: p.title, url: p.url, createdAt: p.createdAt, statusLabel: p.statusLabel,
      reason: p.reason, boosted: p.boosted, connectsBid: p.connectsBid, replied: p.replied === undefined ? null : p.replied
    }));

    const extras = [
      { label: "Connects balance", value: conn.balance == null ? "—" : fmtInt(conn.balance) },
      { label: "Connects spent", value: `${fmtInt(connectsSpent)} (${fmtUsd(spendUsd, true)})` },
      { label: "Boosted proposals", value: boostedShare == null ? "—" : `${fmtPct(boostedShare, 0)} (${boosted} of ${cur.length})` },
      { label: "Billed in range", value: billedUsd == null ? "—" : fmtUsd(billedUsd, true) }
    ];

    // follow-ups from INTERVIEW rooms
    const replyNow = [];
    const due = [];
    const touchDays = CONFIG.upworkTouchDays;
    for (const r of arr(d.rooms)) {
      const id = str(r.id);
      if (!id) continue;
      const last = toMs(r.lastActivity);
      const name = unwrap(r.roomName) || "Upwork client";
      const url = safeUrl(CONFIG.links.upworkRoom(encodeURIComponent(id)));
      if (r.awaiting_reply_from === "you") {
        replyNow.push({ id: `upwork_reply:${id}`, group: "reply_now", kind: "upwork_reply", title: name,
          detail: clip(unwrap(r.latestStory && r.latestStory.message), 140), source: "upwork",
          ageMs: last == null ? null : Math.max(0, nowMs - last), dueAt: null, overdue: false, url });
        continue;
      }
      if (r.awaiting_reply_from === "them" && r.contractStatus !== "ENDED" && r.last_message_from_self === true && last != null) {
        const daysSince = Math.floor((nowMs - last) / DAY_MS);
        if (daysSince >= 2 && daysSince <= 30) {
          const planDay = touchDays.filter(t => t <= daysSince).pop() || touchDays[0];
          due.push({ id: `upwork_nudge:${id}`, group: "due", kind: "upwork_nudge", title: name,
            detail: `No reply for ${daysSince} days. Touch due (plan days ${touchDays.join(", ")}).`, source: "upwork",
            ageMs: nowMs - last, dueAt: last + planDay * DAY_MS, overdue: false, url });
        }
      }
    }

    return { funnel, rates, points, proposals, extras, connectsSpent, spendUsd, connectsBalance: conn.balance,
      boostedShare, billedUsd, replyNow, due, counts: c };
  }

  // ------------------------------------------------------------------ source 3: GoHighLevel

  function ghlData(p, server) {
    if (isObj(p) && p.success === false) {
      throw sourceError(server, "tool_error", `GHL answered ${str(p.status) || "with an error"}${p.data && p.data.message ? ": " + str(p.data.message) : ""}`);
    }
    if (isObj(p) && isObj(p.data)) return p.data;
    return isObj(p) ? p : {};
  }

  async function fetchGhl(caller) {
    const op = CONFIG.tools.ghl.exec;
    const base = { locationId: CONFIG.ghlLocation, reason: GHL_REASON };

    async function pipelines() {
      const p = await caller.call(op, Object.assign({ operationId: "get-pipelines" }, base, { params: {} }));
      return arr(ghlData(p, caller.server).pipelines).filter(isObj);
    }

    async function opportunities() {
      const all = [];
      const seen = new Set();
      let startAfter = null, startAfterId = null;
      for (let page = 0; page < 10; page++) {
        const query = { limit: 100, getTasks: true, getNotes: true };
        if (startAfter != null) query.startAfter = startAfter;
        if (startAfterId != null) query.startAfterId = startAfterId;
        const p = await caller.call(op, Object.assign({ operationId: "search-opportunity" }, base, { params: { query } }));
        const data = ghlData(p, caller.server);
        const opps = arr(data.opportunities).filter(isObj);
        for (const o of opps) {
          const id = str(o.id);
          if (id && !seen.has(id)) { seen.add(id); all.push(o); }
        }
        const meta = isObj(data.meta) ? data.meta : {};
        startAfter = meta.startAfter != null ? meta.startAfter : null;
        startAfterId = meta.startAfterId != null ? meta.startAfterId : null;
        if (opps.length !== 100 || (startAfter == null && startAfterId == null)) break;
      }
      return all;
    }

    const [pls, opps] = await caller.main([pipelines(), opportunities()]);
    return { data: { pipelines: pls, opportunities: opps }, warnings: [] };
  }

  /** Channel attribution for an opportunity: first match wins. */
  function attributeSource(o) {
    const contact = isObj(o.contact) ? o.contact : {};
    const tags = arr(contact.tags).map(lower);
    const source = lower(o.source);
    const name = lower(o.name);
    if (tags.includes("cold-email") || source.startsWith("instantly") || name.includes("(cold email)")) return "cold_email";
    if (tags.includes("upwork") || source.includes("upwork") || name.includes("upwork")) return "upwork";
    if (tags.includes("linkedin") || source.includes("linkedin") || name.includes("linkedin")) return "linkedin";
    return "other";
  }

  function stageRule(name) {
    const n = lower(name).replace(/\s+/g, " ");
    if (/new (reply|lead)/.test(n)) return { kind: "new", warn: 1, crit: 3 };
    if (/call booked/.test(n)) return { kind: "booked", warn: 7, crit: null };
    if (/proposal sent/.test(n)) return { kind: "proposal", warn: 7, crit: 14 };
    return null;
  }

  function staleLevelFor(stageName, status, elapsedMs) {
    if (status !== "open") return "none";
    const rule = stageRule(stageName);
    if (!rule || elapsedMs == null) return "none";
    if (rule.crit != null && elapsedMs > rule.crit * DAY_MS) return "critical";
    if (rule.warn != null && elapsedMs > rule.warn * DAY_MS) return "warning";
    return "none";
  }

  function sortedStages(p) {
    return arr(p && p.stages).filter(isObj).slice().sort((a, b) => num(a.position) - num(b.position));
  }

  function deriveGhl(d, R, nowMs) {
    const pipelines = arr(d.pipelines);
    const opps = arr(d.opportunities);
    const sales = pipelines.find(p => str(p.id) === CONFIG.ghlSalesPipelineId);
    const callsP = pipelines.find(p => str(p.id) === CONFIG.ghlCallsPipelineId);
    const salesStages = sortedStages(sales);
    const stageById = {};
    for (const s of salesStages) stageById[str(s.id)] = s;
    // "Call Booked or later" for Upwork callsBooked: stage Call Booked, Proposal Sent or Won, or status won.
    // Lost, Follow Up Later and any other stage never count.
    const callBookedOrLater = (stageName, status) => {
      if (status === "won") return true;
      const n = lower(stageName).replace(/\s+/g, " ").trim();
      return /call booked|proposal sent/.test(n) || /^won\b/.test(n);
    };

    // Call attribution maps (B2). Sales cards count whatever their source; cards in any other pipeline (for example
    // the Call Booked Pipeline) count only when their source is not "other", so they never block the Instantly fallback.
    const attrib = { salesEmail: new Map(), salesDomain: new Map(), otherEmail: new Map(), otherDomain: new Map() };
    const tasks = [];
    const cards = [];
    const totals = { open: 0, openValue: 0, wonInRange: 0, wonValueInRange: 0, lostInRange: 0 };
    const upworkCardContacts = new Set();

    for (const o of opps) {
      const contact = isObj(o.contact) ? o.contact : {};
      const source = attributeSource(o);
      const email = lower(contact.email);
      const isSales = str(o.pipelineId) === CONFIG.ghlSalesPipelineId;
      if (email && (isSales || source !== "other")) {
        const em = isSales ? attrib.salesEmail : attrib.otherEmail;
        const dm = isSales ? attrib.salesDomain : attrib.otherDomain;
        if (!em.has(email)) em.set(email, source);
        const dom = email.split("@")[1];
        if (dom && !dm.has(dom)) dm.set(dom, source);
      }
      const status = lower(o.status) || "open";
      const stageChange = toMs(o.lastStageChangeAt) != null ? toMs(o.lastStageChangeAt) : toMs(o.createdAt);
      const title = str(contact.name).trim() || str(o.name).trim() || "Unnamed";
      const contactId = str(o.contactId || contact.id);
      const url = contactId ? safeUrl(CONFIG.links.ghlContact(encodeURIComponent(contactId))) : null;

      for (const t of arr(o.tasks)) {
        if (!isObj(t) || t.completed === true) continue;
        tasks.push({ id: str(t.id), title: str(t.title).trim() || "Task", dueAt: toMs(t.dueDate), oppTitle: title, source, url });
      }

      if (!isSales) continue;
      const value = num(o.monetaryValue);
      if (status === "open") { totals.open++; totals.openValue += value; }
      const statusChange = toMs(o.lastStatusChangeAt);
      if (status === "won" && inRange(statusChange, R)) { totals.wonInRange++; totals.wonValueInRange += value; }
      if (status === "lost" && inRange(statusChange, R)) totals.lostInRange++;

      const stage = stageById[str(o.pipelineStageId)];
      if (source === "upwork" && callBookedOrLater(stage ? stage.name : "", status) && inRange(stageChange, R)) {
        upworkCardContacts.add(email || `card:${str(o.id)}`);
      }

      const elapsed = stageChange == null ? null : Math.max(0, nowMs - stageChange);
      const openTasks = arr(o.tasks).filter(t => isObj(t) && t.completed !== true);
      const dues = openTasks.map(t => toMs(t.dueDate)).filter(t => t != null);
      const notes = arr(isObj(o.notes) ? o.notes.notes : o.notes).filter(isObj)
        .map(n => ({ text: n.bodyText, date: toMs(n.dateAdded) }))
        .sort((a, b) => (b.date || 0) - (a.date || 0));
      const newest = notes[0];
      cards.push({
        id: str(o.id), title, company: str(contact.companyName).trim(), email: str(contact.email).trim(), contactId, url,
        source, value, status, stageId: str(o.pipelineStageId),
        daysInStage: elapsed == null ? 0 : Math.floor(elapsed / DAY_MS),
        staleLevel: staleLevelFor(stage ? stage.name : "", status, elapsed),
        lastNote: newest ? { text: clip(newest.text, 280), date: newest.date } : null,
        openTasks: openTasks.length,
        nextTaskDue: dues.length ? Math.min(...dues) : null,
        _stageName: stage ? str(stage.name) : "",
        _stageChange: stageChange
      });
    }
    totals.openValue = round2(totals.openValue);
    totals.wonValueInRange = round2(totals.wonValueInRange);

    // board: one column per Sales stage with every card in it (open, won, lost, abandoned). count and value cover all
    // of them; the column shows at most COLUMN_CAP cards, open first, then longest in stage, and hiddenCount the rest.
    const stages = salesStages.map(s => {
      const col = cards.filter(c => c.stageId === str(s.id))
        .sort((a, b) => (b.status === "open") - (a.status === "open") || b.daysInStage - a.daysInStage || a.title.localeCompare(b.title));
      const shown = col.slice(0, COLUMN_CAP);
      return { id: str(s.id), name: str(s.name), count: col.length, value: round2(col.reduce((t, c) => t + c.value, 0)),
        cards: shown.map(publicCard), hiddenCount: col.length - shown.length };
    });

    // Call Booked pipeline: counts per stage and the show rate, over stage changes in the range
    const callStages = sortedStages(callsP);
    const callStageName = {};
    for (const s of callStages) callStageName[str(s.id)] = str(s.name);
    const tally = (pred) => {
      const out = {};
      for (const s of callStages) out[str(s.name)] = 0;
      for (const o of opps) {
        if (str(o.pipelineId) !== CONFIG.ghlCallsPipelineId) continue;
        const name = callStageName[str(o.pipelineStageId)];
        const t = toMs(o.lastStageChangeAt) != null ? toMs(o.lastStageChangeAt) : toMs(o.createdAt);
        if (name != null && pred(t)) out[name]++;
      }
      return out;
    };
    const curT = tally(t => inRange(t, R));
    const prevT = tally(t => inPrev(t, R));
    const findCount = (t, re) => Object.keys(t).filter(k => re.test(k)).reduce((s, k) => s + t[k], 0);
    const showed = findCount(curT, /^showed$/i), noShow = findCount(curT, /^no[\s-]?show$/i);
    const pShowed = findCount(prevT, /^showed$/i), pNoShow = findCount(prevT, /^no[\s-]?show$/i);
    const showRate = makeRate("show_rate", "Show rate", showed, showed + noShow, pShowed, pShowed + pNoShow, RULES.show_rate);

    const openCards = cards.filter(c => c.status === "open");
    return {
      pipeline: {
        name: "Sales", url: CONFIG.links.ghlOpportunities, stages, totals,
        calls: { stages: callStages.map(s => ({ name: str(s.name), count: curT[str(s.name)] || 0 })), showRate }
      },
      openCards, tasks, attrib, upworkCardContacts
    };
  }

  function publicCard(c) {
    return { id: c.id, title: c.title, company: c.company, email: c.email, contactId: c.contactId, url: c.url,
      source: c.source, value: c.value, status: c.status, stageId: c.stageId, daysInStage: c.daysInStage,
      staleLevel: c.staleLevel, lastNote: c.lastNote, openTasks: c.openTasks, nextTaskDue: c.nextTaskDue };
  }

  // ------------------------------------------------------------------ source 4: Google Calendar

  /** Copy only the fields the scoreboard uses. `description` is never read (it holds Zoom passcodes). */
  function pickEvent(ev) {
    if (!isObj(ev)) return null;
    const start = isObj(ev.start) ? ev.start.dateTime : null;
    const end = isObj(ev.end) ? ev.end.dateTime : null;
    return {
      id: str(ev.id), summary: str(ev.summary), status: str(ev.status),
      start: start == null ? null : str(start), end: end == null ? null : str(end),
      attendees: arr(ev.attendees).filter(isObj).map(a => ({ email: str(a.email), self: a.self === true, organizer: a.organizer === true })),
      location: str(ev.location), htmlLink: str(ev.htmlLink)
    };
  }

  async function fetchCalendar(caller, R, env) {
    const tool = CONFIG.tools.calendar.events;
    const nowMs = env.nowMs;
    async function list(startTime, endTime) {
      const out = [];
      let token = null;
      for (let page = 0; page < 4; page++) { // first page + at most 3 nextPageToken follows
        const input = { calendarId: CONFIG.calendarId, startTime, endTime, orderBy: "startTime", pageSize: 250 };
        if (token) input.pageToken = token;
        const p = await caller.call(tool, input);
        for (const ev of listOf(p, ["events", "items"])) { const e = pickEvent(ev); if (e) out.push(e); }
        token = isObj(p) ? p.nextPageToken : null;
        if (!token) break;
      }
      return out;
    }
    const nowIso = new Date(nowMs).toISOString();
    const [past, upcoming] = await caller.main([
      list(new Date(R.startMs).toISOString(), nowIso),
      list(nowIso, new Date(nowMs + 14 * DAY_MS).toISOString())
    ]);
    return { data: { past, upcoming }, warnings: [] };
  }

  const SELF = () => new Set(CONFIG.selfEmails.map(lower));

  function externalAttendees(ev) {
    const self = SELF();
    return arr(ev.attendees).filter(a => a.email && a.self !== true && !self.has(lower(a.email)));
  }

  function isSalesCall(ev) {
    if (!ev || ev.status === "cancelled") return false;
    if (!externalAttendees(ev).length) return false;
    const kw = /zoom|discovery|call|meeting/i;
    return kw.test(str(ev.summary)) || kw.test(str(ev.location)) || str(ev.location).toLowerCase().includes("zoom.us");
  }

  function zoomJoinUrl(location) {
    const s = str(location).trim();
    return /^https:\/\/([a-z0-9-]+\.)*zoom\.us(\/[^\s]*)?$/i.test(s) ? s : null;
  }

  // Shared mailbox domains never attribute by domain alone (only an exact email match counts).
  const FREEMAIL = new Set(["gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "zoho.com", "yandex.com", "mail.com"]);

  /** Call source, first match wins: Sales cards (email, then domain), cards in other pipelines whose source is not
   *  "other" (email, then domain), Instantly interested/booked leads (email, then domain), else unattributed. */
  function attributeCall(email, G, I) {
    const e = lower(email);
    const d0 = e.split("@")[1] || "";
    const dom = FREEMAIL.has(d0) ? "" : d0;
    const A = G && G.attrib;
    if (A) {
      for (const [em, dm] of [[A.salesEmail, A.salesDomain], [A.otherEmail, A.otherDomain]]) {
        if (em && em.has(e)) return em.get(e);
        if (dom && dm && dm.has(dom)) return dm.get(dom);
      }
    }
    if (I) {
      if (I.leadEmails.has(e)) return "cold_email";
      if (dom) for (const le of I.leadEmails) if (le.split("@")[1] === dom) return "cold_email";
    }
    return "unattributed";
  }

  function deriveCalendar(d, R, nowMs, G, I) {
    const byId = new Map();
    for (const ev of arr(d.past).concat(arr(d.upcoming))) if (ev && ev.id && !byId.has(ev.id)) byId.set(ev.id, ev);
    const calls = [];
    for (const ev of byId.values()) {
      if (!isSalesCall(ev)) continue;
      const start = toMs(ev.start);
      if (start == null) continue;
      const who = externalAttendees(ev)[0].email;
      calls.push({ id: ev.id, start, end: toMs(ev.end), title: ev.summary || "Call", who,
        joinUrl: zoomJoinUrl(ev.location), url: safeUrl(ev.htmlLink), source: attributeCall(who, G, I) });
    }
    const upcoming = calls.filter(c => c.start >= nowMs && c.start <= nowMs + 14 * DAY_MS).sort((a, b) => a.start - b.start);
    const pastInRange = calls.filter(c => c.start < nowMs && c.start >= R.startMs).sort((a, b) => b.start - a.start);
    const bySource = { cold_email: 0, upwork: 0, linkedin: 0, other: 0, unattributed: 0 };
    const upworkContacts = new Set();
    for (const c of pastInRange) {
      bySource[c.source in bySource ? c.source : "other"]++;
      if (c.source === "upwork") upworkContacts.add(lower(c.who));
    }
    return { upcoming, pastInRange, bySource, upworkContacts };
  }

  // ------------------------------------------------------------------ follow-ups

  /** Time in stage for stale details: whole hours under 48 h ("30 hours"), whole days after that. Under 48 h a
   *  day count would read "1 day" for a card that broke a "> 1 day" rule. */
  function stalePeriod(elapsedMs, fallbackDays) {
    if (elapsedMs == null) return plural(fallbackDays, "day", "days");
    if (elapsedMs < 48 * HOUR_MS) return plural(Math.floor(elapsedMs / HOUR_MS), "hour", "hours");
    return plural(Math.floor(elapsedMs / DAY_MS), "day", "days");
  }

  function deriveFollowups(I, U, G, C, nowMs, R, L) {
    const reply_now = [], due = [], upcoming = [];
    if (U) { reply_now.push(...U.replyNow); due.push(...U.due); }
    if (L) { reply_now.push(...L.replyNow); due.push(...L.due); upcoming.push(...L.upcoming); }
    if (I) {
      for (const l of I.unanswered) {
        reply_now.push({ id: `email_reply:${l.id}`, group: "reply_now", kind: "email_reply", title: l.title, detail: l.campaign,
          source: "cold_email", ageMs: l.lastReplyMs == null ? null : Math.max(0, nowMs - l.lastReplyMs), dueAt: null, overdue: false,
          url: CONFIG.links.instantlyUnibox });
      }
      if (I.unread != null && I.unread > 0) {
        reply_now.push({ id: "unibox", group: "reply_now", kind: "unibox",
          title: `${I.unread} unread ${I.unread === 1 ? "reply" : "replies"} in Instantly`, detail: "", source: "cold_email",
          ageMs: null, dueAt: null, overdue: false, url: CONFIG.links.instantlyUnibox });
      }
    }
    if (G) {
      for (const c of G.openCards) {
        const rule = stageRule(c._stageName);
        const elapsed = c._stageChange == null ? null : Math.max(0, nowMs - c._stageChange);
        if (rule && rule.kind === "new") {
          // A new lead is listed once, in reply_now; its stale level goes into the detail instead of a stale_deal item.
          // How long it has waited shows only in the side age text (ageMs), not in the detail.
          let detail = c.company ? `New lead · ${c.company}` : "New lead";
          if (c.staleLevel !== "none") detail += ` · ${c.staleLevel === "critical" ? "Stale" : "Getting stale"}`;
          reply_now.push({ id: `new_lead:${c.id}`, group: "reply_now", kind: "new_lead", title: c.title,
            detail, source: c.source, ageMs: elapsed, dueAt: null, overdue: false, url: c.url });
          continue;
        }
        if (c.staleLevel !== "none") {
          let detail = `In ${c._stageName} for ${stalePeriod(elapsed, c.daysInStage)}.`;
          if (rule && rule.kind === "booked") detail += " The call has likely happened; update the stage.";
          due.push({ id: `stale_deal:${c.id}`, group: "due", kind: "stale_deal", title: c.title, detail, source: c.source,
            ageMs: c._stageChange == null ? null : Math.max(0, nowMs - c._stageChange),
            dueAt: c._stageChange == null || !rule ? null : c._stageChange + rule.warn * DAY_MS,
            overdue: c.staleLevel === "critical", url: c.url });
        }
      }
      const weekEnd = endOfDayMs(addDays(R.end, 7));
      for (const t of G.tasks) {
        if (t.dueAt == null) continue;
        const base = { title: t.title, detail: `For ${t.oppTitle}`, source: t.source, ageMs: null, dueAt: t.dueAt, url: t.url };
        if (t.dueAt <= R.todayEndMs) {
          due.push(Object.assign({ id: `ghl_task:${t.id}`, group: "due", kind: "ghl_task", overdue: t.dueAt < R.todayStartMs }, base));
        } else if (t.dueAt <= weekEnd) {
          upcoming.push(Object.assign({ id: `ghl_task:${t.id}`, group: "upcoming", kind: "ghl_task", overdue: false }, base));
        }
      }
    }
    if (C) {
      for (const c of C.upcoming) {
        if (c.start - nowMs > DAY_MS) continue;
        due.push({ id: `call_prep:${c.id}`, group: "due", kind: "call_prep", title: c.title, detail: `With ${c.who}`,
          source: c.source, ageMs: null, dueAt: c.start, overdue: false, url: c.url });
      }
    }
    const byAgeDesc = (a, b) => (b.ageMs == null ? -Infinity : b.ageMs) - (a.ageMs == null ? -Infinity : a.ageMs);
    const byDueAsc = (a, b) => (a.dueAt == null ? Infinity : a.dueAt) - (b.dueAt == null ? Infinity : b.dueAt);
    reply_now.sort((a, b) => { const x = byAgeDesc(a, b); return Number.isNaN(x) ? 0 : x; });
    due.sort((a, b) => { const x = byDueAsc(a, b); return Number.isNaN(x) ? 0 : x; });
    upcoming.sort((a, b) => { const x = byDueAsc(a, b); return Number.isNaN(x) ? 0 : x; });
    return { reply_now, due, upcoming };
  }

  // ------------------------------------------------------------------ LinkedIn tracker (piece 2)
  // Field names, stages, events and timing follow ~/.claude/skills/linkedin-outreach/SKILL.md ("Follow-up timing",
  // "Tracker fields and stages", "Weekly numbers"). Rows live in the page's own db, collection `linkedinRows`.

  const LI_COLLECTION = "linkedinRows";
  const LI_SERVER = "LinkedIn";
  const LI_PAGE = 1000;          // the store's largest page (db.d.ts: limit 1-1000)
  const LI_MAX_PAGES = 20;       // safety cap on paging; past it the read counts as truncated
  const LI_WRITE_TIMEOUT_MS = 5000;
  const LI_PENDING_WARN = 550;
  const LI_READ_FIX = "Your LinkedIn rows could not be read. Press Refresh.";
  const LI_NO_DB = "Editing needs the claude.ai viewer";
  const LI_TOO_MANY = "Too many LinkedIn rows to edit safely here. Tell Claude.";
  const LI_DENIED = "Saving isn't allowed for this view.";
  // db.d.ts: a write below the viewer's level rejects invalid_argument; the other two are kept as access codes too.
  const LI_ACCESS_CODES = new Set(["invalid_argument", "permission_denied", "not_writer"]);

  const LI_STAGES = ["Connect sent", "Accepted", "DM sent", "Follow-up 1", "Follow-up 2", "Follow-up 3", "No reply",
    "Voice note sent", "Reply", "Positive reply", "Meeting booked", "Closed won", "Closed lost", "Withdrawn"];
  // The skill's reply types (it wins over the spec summary's list).
  const LI_REPLY_TYPES = ["positive", "price", "more_info", "what_is_this", "not_now", "not_interested", "referral", "other"];
  // The skill's tracker fields, in its order (21: the spec summary's 19 plus reply_date and reply_answered_date).
  const LI_FIELDS = ["name", "first_name", "profile_url", "company", "role", "what_they_do", "industry", "country",
    "connect_sent_date", "accepted_date", "dm_date", "loom_variant", "last_touch_date", "next_touch_due", "stage",
    "reply_type", "reply_date", "reply_answered_date", "meeting_booked", "outcome", "slots_offered"];
  const LI_DATE_FIELDS = ["connect_sent_date", "accepted_date", "dm_date", "last_touch_date", "next_touch_due", "reply_date", "reply_answered_date"];
  const LI_EVENTS = [
    { type: "connect_sent", label: "Connect sent", needs: null },
    { type: "accepted", label: "Accepted", needs: null },
    { type: "dm_sent", label: "DM sent", needs: "variant" },
    { type: "fu1_sent", label: "FU1 sent", needs: null },
    { type: "fu2_sent", label: "FU2 sent", needs: null },
    { type: "fu3_sent", label: "FU3 sent", needs: null },
    { type: "no_reply", label: "Mark no reply", needs: null },
    { type: "voice_note_sent", label: "Voice note sent", needs: null },
    { type: "reply", label: "Reply…", needs: "replyType" },
    // The skill's "Answer sent" rows: Lorenzo answered the lead's latest reply. Optional `date` = the date a not_now lead gave.
    { type: "answer_sent", label: "Answer sent", needs: null },
    { type: "meeting_booked", label: "Meeting booked…", needs: "datetime" },
    { type: "closed_won", label: "Closed won", needs: null },
    { type: "closed_lost", label: "Closed lost", needs: null },
    { type: "withdrawn", label: "Withdrawn", needs: null }
  ];
  // The channel funnel. conv false: that step is not a subset of the step above it in the same cohort (Accepted and
  // Looms sent count people dated in range whatever month their request went out; calls are dated by the meeting),
  // so the UI shows no "% of previous step" for it. Replies, Positive and Closed won are subsets of the step above.
  const LI_FUNNEL = [["requests", "Requests sent", true], ["accepted", "Accepted", false], ["looms", "Looms sent", false],
    ["replies", "Replies", true], ["positive", "Positive", true], ["booked", "Calls booked", false], ["won", "Closed won", true]];
  const LI_ACTIVE = new Set(["Connect sent", "Accepted", "DM sent", "Follow-up 1", "Follow-up 2", "Follow-up 3"]);
  const LI_REPLIED = new Set(["Reply", "Positive reply"]);
  RULES.li_accept = { dir: "up", green: 0.3, alert: 0.15, target: "≥ 30%" };

  function isYmd(s) {
    if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    return addDays(s, 0) === s;
  }

  /** 0 = Sunday ... 6 = Saturday, for a YYYY-MM-DD calendar day. */
  function weekdayOf(day) {
    const [y, m, d] = day.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  }

  function addBusinessDays(day, n) {
    let d = day;
    for (let left = n; left > 0;) {
      d = addDays(d, 1);
      const w = weekdayOf(d);
      if (w !== 0 && w !== 6) left--;
    }
    return d;
  }

  /** Monday of the Monday-to-Sunday week that holds `day`. */
  function mondayOf(day) {
    return addDays(day, -((weekdayOf(day) + 6) % 7));
  }

  /** The Central calendar day of `meeting_booked` (an ISO datetime, a datetime-local value or a plain date), or "". */
  function meetingDay(v) {
    const s = str(v).trim();
    if (!s) return "";
    if (isYmd(s)) return s;
    if (/(Z|[+-]\d{2}:?\d{2})$/i.test(s)) {
      const t = toMs(s);
      return t == null ? "" : ymd(t);
    }
    if (/^\d{4}-\d{2}-\d{2}[T ]/.test(s) && isYmd(s.slice(0, 10))) return s.slice(0, 10);
    const t = toMs(s);
    return t == null ? "" : ymd(t);
  }

  function randomId() {
    let s = "";
    try {
      const c = typeof globalThis !== "undefined" ? globalThis.crypto : null;
      if (c && typeof c.getRandomValues === "function") {
        const b = new Uint8Array(9);
        c.getRandomValues(b);
        for (const x of b) s += (x % 36).toString(36);
      }
    } catch (_) { s = ""; }
    while (s.length < 12) s += Math.floor(Math.random() * 36).toString(36);
    return "r_" + s.slice(0, 12);
  }

  function slugify(s) {
    let t = str(s);
    try { t = decodeURIComponent(t); } catch (_) { /* keep raw */ }
    return t.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "").slice(0, 150);
  }

  /** The /in/<handle> part as an id: lowercase ASCII letters, digits, _ and - stay; other ASCII runs become "-";
   *  every non-ASCII character keeps its percent-encoded UTF-8 bytes with "~" for "%" (db path segments can't hold
   *  "%"), so two handles that differ only in non-ASCII characters never share an id. */
  function handleSlug(h) {
    let t = str(h);
    try { t = decodeURIComponent(t); } catch (_) { /* keep raw */ }
    let out = "";
    for (const ch of t.toLowerCase()) {
      if (ch.charCodeAt(0) > 127) {
        let enc;
        try { enc = encodeURIComponent(ch); } catch (_) { enc = "%" + ch.codePointAt(0).toString(16); }
        out += enc.toLowerCase().replace(/%/g, "~");
      } else out += /[a-z0-9_-]/.test(ch) ? ch : "-";
    }
    return out.replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "").slice(0, 150);
  }

  /** Stable doc id: an existing `id`, else the slug of the profile URL's /in/<handle> (lowercase, no query string or
   *  trailing slash), else a slug of any other URL ("u_..."), else a random id ("r_..."). */
  function liRowId(row) {
    const r = isObj(row) ? row : {};
    if (typeof r.id === "string" && r.id.trim()) return r.id.trim();
    const url = str(r.profile_url).trim().split(/[?#]/)[0].replace(/\/+$/, "");
    if (url) {
      const m = /\/in\/([^/]+)/i.exec(url);
      if (m) {
        const slug = handleSlug(m[1]);
        if (slug) return slug;
      }
      const rest = slugify(url.replace(/^[a-z]+:\/\//i, "").replace(/^www\./i, ""));
      if (rest) return "u_" + rest;
    }
    return randomId();
  }

  /** A stored or edited row with every field present as a string, plus updatedAt (ms|null) and id. Lenient: never throws. */
  function liNormRow(row, id) {
    const r = isObj(row) ? row : {};
    const out = {};
    for (const f of LI_FIELDS) out[f] = str(r[f]).trim();
    const v = out.loom_variant.toUpperCase();
    out.loom_variant = v === "A" || v === "B" ? v : "";
    out.updatedAt = typeof r.updatedAt === "number" && Number.isFinite(r.updatedAt) ? r.updatedAt : null;
    out.id = id != null && str(id) ? str(id) : liRowId(r);
    return out;
  }

  /** What goes into the db doc: the skill's fields and updatedAt, nothing else. */
  function liBody(row, nowMs) {
    const n = liNormRow(row, "x");
    const body = {};
    for (const f of LI_FIELDS) body[f] = n[f];
    body.updatedAt = nowMs;
    return body;
  }

  const liSameFields = (a, b) => LI_FIELDS.every(f => str(a[f]).trim() === str(b[f]).trim());

  /**
   * Apply one event from the skill's table. Pure: returns a new row, never touches the input.
   * event = { type, variant?, replyType?, datetime?, date?, now? }; `now` (ms) stamps updatedAt (default Date.now()).
   */
  function liApplyEvent(row, event, todayYmd) {
    const ev = isObj(event) ? event : {};
    if (!isYmd(todayYmd)) throw new TypeError(`todayYmd must be YYYY-MM-DD, got "${str(todayYmd)}"`);
    const t = todayYmd;
    const r = liNormRow(row, isObj(row) && row.id ? row.id : undefined);
    switch (ev.type) {
      case "connect_sent":
        r.stage = "Connect sent"; r.connect_sent_date = t; r.next_touch_due = addDays(t, 21); break;
      case "withdrawn":
        r.stage = "Withdrawn"; r.next_touch_due = ""; break;
      case "accepted":
        // The skill: "next block, or blank until Looms start". The page can't know the block, so blank.
        r.stage = "Accepted"; r.accepted_date = t; r.next_touch_due = ""; break;
      case "dm_sent": {
        const v = str(ev.variant).trim().toUpperCase();
        if (v !== "A" && v !== "B") throw new Error("DM sent needs the Loom variant, A or B.");
        r.stage = "DM sent"; r.dm_date = t; r.last_touch_date = t; r.loom_variant = v; r.next_touch_due = addDays(t, 2); break;
      }
      case "fu1_sent":
        r.stage = "Follow-up 1"; r.last_touch_date = t; r.next_touch_due = addDays(t, 4); break;
      case "fu2_sent":
        r.stage = "Follow-up 2"; r.last_touch_date = t; r.next_touch_due = addDays(t, 7); break;
      case "fu3_sent":
        r.stage = "Follow-up 3"; r.last_touch_date = t; r.next_touch_due = addDays(t, 7); break;
      case "no_reply":
        // The voice note date counts 60 days from FU3 (last_touch_date), not from the No reply check.
        r.stage = "No reply"; r.next_touch_due = addDays(isYmd(r.last_touch_date) ? r.last_touch_date : t, 60); break;
      case "voice_note_sent":
        r.stage = "Voice note sent"; r.last_touch_date = t; r.next_touch_due = ""; break;
      case "reply": {
        const type = str(ev.replyType).trim().toLowerCase();
        if (!LI_REPLY_TYPES.includes(type)) throw new Error(`Reply needs a reply type (${LI_REPLY_TYPES.join(", ")}).`);
        r.stage = type === "positive" ? "Positive reply" : "Reply";
        r.reply_type = type; r.reply_date = t;
        r.reply_answered_date = ""; // a new reply is unanswered until Lorenzo answers it
        r.next_touch_due = ""; break;
      }
      case "answer_sent": {
        if (!r.reply_type) throw new Error("Answer sent needs a reply to answer: log the reply first.");
        r.reply_answered_date = t; r.last_touch_date = t;
        if (r.reply_type === "positive") {
          r.stage = "Positive reply"; r.next_touch_due = addBusinessDays(t, 2); // quiet check
        } else {
          r.stage = "Reply";
          r.next_touch_due = r.reply_type === "not_now" && isYmd(str(ev.date).trim()) ? str(ev.date).trim() : "";
        }
        break;
      }
      case "meeting_booked": {
        const dt = str(ev.datetime).trim();
        if (!dt) throw new Error("Meeting booked needs the call date and time.");
        r.stage = "Meeting booked"; r.meeting_booked = dt; r.next_touch_due = ""; break;
      }
      case "closed_won":
        r.stage = "Closed won"; r.outcome = "Closed won"; r.next_touch_due = ""; break;
      case "closed_lost":
        r.stage = "Closed lost"; r.outcome = "Closed lost"; r.next_touch_due = ""; break;
      default:
        throw new Error(`Unknown LinkedIn event "${str(ev.type)}".`);
    }
    // not_interested: next_touch_due stays blank and is never set again (until a new reply changes the type).
    if (r.reply_type === "not_interested") r.next_touch_due = "";
    r.updatedAt = typeof ev.now === "number" && Number.isFinite(ev.now) ? ev.now : Date.now();
    return r;
  }

  /** Merge by doc id: non-empty incoming fields overwrite, empty ones never blank existing data. Fields parsePaste
   *  filled in by default (listed in `incoming._defaulted`) never overwrite a row that already has a stage. */
  function liMerge(existing, incoming) {
    const ex = isObj(existing) ? existing : null;
    const inc = isObj(incoming) ? incoming : {};
    const out = liNormRow(ex || {}, ex && ex.id ? ex.id : (inc.id ? inc.id : undefined));
    const defaulted = new Set(arr(inc._defaulted));
    const keepDefaults = !!ex && str(ex.stage).trim() !== "";
    for (const f of LI_FIELDS) {
      const v = str(inc[f]).trim();
      if (!v) continue;
      if (defaulted.has(f) && keepDefaults) continue;
      out[f] = f === "loom_variant" ? (v.toUpperCase() === "A" || v.toUpperCase() === "B" ? v.toUpperCase() : out[f]) : v;
    }
    const times = [ex && ex.updatedAt, inc.updatedAt].filter(x => typeof x === "number" && Number.isFinite(x));
    out.updatedAt = times.length ? Math.max(...times) : null;
    return out;
  }

  // ---- paste parsing

  /** Split delimited text into records, honoring double-quoted fields (delimiters, newlines and "" inside quotes). */
  function splitDelimited(text, delim) {
    const records = [];
    let cells = [], cell = "", inQ = false, fieldStart = true, line = 1, recLine = 1;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQ) {
        if (c === '"') {
          if (text[i + 1] === '"') { cell += '"'; i++; } else inQ = false;
        } else {
          if (c === "\n") line++;
          cell += c;
        }
        continue;
      }
      if (c === '"' && fieldStart) { inQ = true; fieldStart = false; continue; }
      if (c === delim) { cells.push(cell); cell = ""; fieldStart = true; continue; }
      if (c === "\n") {
        cells.push(cell); records.push({ line: recLine, cells });
        cells = []; cell = ""; fieldStart = true; line++; recLine = line;
        continue;
      }
      cell += c; fieldStart = false;
    }
    if (cell !== "" || cells.length) { cells.push(cell); records.push({ line: recLine, cells }); }
    return records;
  }

  const normHeader = h => str(h).replace(/^﻿/, "").toLowerCase().replace(/[_\-.]+/g, " ").replace(/\s+/g, " ").trim();
  const LI_HEADER = (() => {
    const m = {};
    for (const f of LI_FIELDS) m[normHeader(f)] = f;
    Object.assign(m, {
      "full name": "name", "last name": "_last", "linkedin url": "profile_url", "profile url": "profile_url", "url": "profile_url",
      "company name": "company", "title": "role", "job title": "role", "location": "country"
    });
    return m;
  })();

  const squash = s => str(s).toLowerCase().replace(/[\s\-_]+/g, "");
  const LI_STAGE_BY_KEY = new Map(LI_STAGES.map(s => [squash(s), s]));

  /** A pasted date to YYYY-MM-DD: YYYY-MM-DD, YYYY/MM/DD, M/D/YYYY, or an ISO datetime (its Central day). null if invalid. */
  function pasteDate(v) {
    const s = str(v).trim();
    let m;
    const mk = (y, mo, d) => { const out = `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`; return isYmd(out) ? out : null; };
    if ((m = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/.exec(s))) return mk(m[1], +m[2], +m[3]);
    if ((m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s))) return mk(m[3], +m[1], +m[2]);
    if (/^\d{4}-\d{2}-\d{2}T/.test(s)) { const d = meetingDay(s); return d || null; }
    return null;
  }

  /**
   * Parse rows pasted from a sheet: TSV or CSV with a header row. Returns { rows, errors: [{ line, message }] }.
   * Each row carries `id` (rowId) and `_defaulted` (the fields filled in here, not pasted). Pure apart from the
   * random id of a row with no URL.
   */
  function liParsePaste(text, todayYmd) {
    const rows = [], errors = [];
    if (!isYmd(todayYmd)) throw new TypeError(`todayYmd must be YYYY-MM-DD, got "${str(todayYmd)}"`);
    const src = str(text).replace(/\r\n?/g, "\n");
    const firstLine = src.split("\n").find(l => l.trim() !== "") || "";
    const delim = firstLine.includes("\t") ? "\t" : ",";
    const records = splitDelimited(src, delim).filter(r => r.cells.some(c => c.trim() !== ""));
    if (!records.length) return { rows, errors };

    const head = records[0];
    const cols = head.cells.map(h => LI_HEADER[normHeader(h)] || null);
    if (!cols.some(c => c === "name" || c === "first_name" || c === "_last" || c === "profile_url")) {
      errors.push({ line: head.line, message: "The first line must be a header row with a name or profile URL column." });
      return { rows, errors };
    }

    const byId = new Map();
    for (const rec of records.slice(1)) {
      const raw = {};
      cols.forEach((f, i) => {
        if (!f) return;
        const v = str(rec.cells[i]).trim();
        if (v && !raw[f]) raw[f] = v;
      });
      const row = {};
      for (const f of LI_FIELDS) row[f] = raw[f] || "";
      if (!row.name && (raw.first_name || raw._last)) row.name = [raw.first_name, raw._last].filter(Boolean).join(" ");

      let url = row.profile_url;
      if (url && /^(www\.)?linkedin\.com\//i.test(url)) url = "https://" + url;
      if (/^http:\/\/(www\.)?linkedin\.com\//i.test(url)) url = "https://" + url.slice(7);
      row.profile_url = url;

      const fail = message => errors.push({ line: rec.line, message });
      if (!row.name && !row.profile_url) { fail("No name or profile URL."); continue; }

      let bad = false;
      for (const f of LI_DATE_FIELDS) {
        if (!row[f]) continue;
        const d = pasteDate(row[f]);
        if (!d) { fail(`"${row[f]}" in ${f} is not a date (use YYYY-MM-DD).`); bad = true; break; }
        row[f] = d;
      }
      if (bad) continue;
      if (row.stage) {
        const s = LI_STAGE_BY_KEY.get(squash(row.stage));
        if (!s) { fail(`Unknown stage "${row.stage}".`); continue; }
        row.stage = s;
      }
      if (row.reply_type) {
        const t = str(row.reply_type).toLowerCase().replace(/[\s-]+/g, "_");
        if (!LI_REPLY_TYPES.includes(t)) { fail(`Unknown reply type "${row.reply_type}".`); continue; }
        row.reply_type = t;
      }
      if (row.loom_variant) {
        const v = row.loom_variant.replace(/^variant\s*/i, "").toUpperCase();
        if (v !== "A" && v !== "B") { fail(`Loom variant must be A or B, not "${row.loom_variant}".`); continue; }
        row.loom_variant = v;
      }
      if (row.outcome) {
        const o = row.outcome.toLowerCase().replace(/^closed\s*/, "");
        if (o !== "won" && o !== "lost") { fail(`Outcome must be Closed won or Closed lost, not "${row.outcome}".`); continue; }
        row.outcome = o === "won" ? "Closed won" : "Closed lost";
      }

      row.id = liRowId(row);
      const prior = byId.get(row.id);
      if (prior) {
        // The same person twice in one paste: merged here first, before any defaults, so the later line's real
        // values fill and override the earlier line's and a default never stands in for a pasted value.
        for (const f of LI_FIELDS) if (row[f]) prior[f] = row[f];
      } else {
        rows.push(row);
        byId.set(row.id, row);
      }
    }
    // Defaults, once per person: no stage means Connect sent, sent today when blank, withdraw check by the
    // Connect sent rule. `_defaulted` lists them, so a merge never lets them overwrite a saved row's data.
    for (const row of rows) {
      const defaulted = [];
      if (!row.stage) { row.stage = "Connect sent"; defaulted.push("stage"); }
      if (row.stage === "Connect sent") {
        if (!row.connect_sent_date) { row.connect_sent_date = todayYmd; defaulted.push("connect_sent_date"); }
        if (!row.next_touch_due) { row.next_touch_due = addDays(row.connect_sent_date, 21); defaulted.push("next_touch_due"); }
      }
      row._defaulted = defaulted;
    }
    return { rows, errors };
  }

  // ---- writes (only on an explicit viewer action; never on load)

  function liReject(code, message) {
    return Object.assign(new Error(message), { code });
  }

  /** Run a db call, rejecting after `ms` with code "timeout" (the message names `totalMs`, default `ms`). */
  function writeWithTimeout(fn, ms, totalMs) {
    return new Promise((resolve, reject) => {
      let done = false;
      const timer = setTimeout(() => {
        if (!done) { done = true; reject(liReject("timeout", `The save took longer than ${Math.round((totalMs || ms) / 1000)} s.`)); }
      }, ms);
      Promise.resolve().then(fn).then(
        v => { if (!done) { done = true; clearTimeout(timer); resolve(v); } },
        e => { if (!done) { done = true; clearTimeout(timer); reject(e); } });
    });
  }

  const liTimeout = opts => (isObj(opts) && typeof opts.timeoutMs === "number" && opts.timeoutMs >= 0 ? opts.timeoutMs : LI_WRITE_TIMEOUT_MS);
  const liNow = opts => (isObj(opts) && typeof opts.now === "number" ? opts.now : Date.now());

  // The rows this page read (or wrote since): a `set` may replace only these. Any other id is read first.
  function liLoadedRows(opts) {
    if (isObj(opts) && Array.isArray(opts.existing)) return opts.existing;
    return _last && isObj(_last.raw.linkedin) && isObj(_last.raw.linkedin.data) ? arr(_last.raw.linkedin.data.rows) : [];
  }

  // After a write rejects with an access code while the platform said nothing about this viewer's write level
  // (user.can("data.write") resolved null), the tracker is read-only for the rest of the visit (db.d.ts).
  function liNoteFailure(e) {
    const code = str(e && e.code);
    const d = _last && isObj(_last.raw.linkedin) && isObj(_last.raw.linkedin.data) ? _last.raw.linkedin.data : null;
    if (LI_ACCESS_CODES.has(code) && d && d.canWrite === null) _liDenied = true;
  }

  /**
   * Write one row to linkedinRows/<rowId>. Resolves with the saved row (id, updatedAt); rejects on failure or after
   * 5 s. A doc this page never read is never replaced: its id is read first, and when it exists the row is merged
   * into it (or, with opts.ifExists "refuse", the save rejects with code "exists").
   */
  async function liSave(db, row, opts) {
    if (!db) throw liReject("unavailable", LI_NO_DB + ".");
    const id = liRowId(row);
    const total = liTimeout(opts);
    const deadline = Date.now() + total;
    const loadedIds = isObj(opts) && opts._loadedIds instanceof Set ? opts._loadedIds
      : new Set(liLoadedRows(opts).filter(isObj).map(r => liRowId(r)));
    const loaded = loadedIds.has(id);
    let body;
    try {
      const ref = db.collection(LI_COLLECTION).doc(id);
      let toWrite = row;
      if (!loaded) {
        const snap = await writeWithTimeout(() => ref.get(), total);
        const stored = snap && snap.exists !== false && typeof snap.data === "function" ? snap.data() : null;
        if (isObj(stored)) {
          if (isObj(opts) && opts.ifExists === "refuse") throw liReject("exists", "Another row already has this profile URL.");
          toWrite = Object.assign(liMerge(liNormRow(stored, id), row), { id });
        }
      }
      body = liBody(toWrite, liNow(opts));
      const left = deadline - Date.now();
      if (left <= 0) throw liReject("timeout", `The save took longer than ${Math.round(total / 1000)} s.`);
      await writeWithTimeout(() => ref.set(body), left, total);
    } catch (e) {
      liNoteFailure(e);
      throw e;
    }
    return Object.assign({}, body, { id });
  }

  const liStamp = r => (isObj(r) && typeof r.updatedAt === "number" && Number.isFinite(r.updatedAt) ? r.updatedAt : null);
  // r carries a newer updatedAt than the basis row b (a basis row without one is older than any stamp)
  const liNewer = (r, b) => { const t = liStamp(r); if (t === null) return false; const bt = liStamp(b); return bt === null || t > bt; };

  // The rows the page holds right now (the last load, plus every rebuild({linkedinRows}) since), or null before a read.
  let _liCurKey = null, _liCurMap = null;
  function liCurrentRows() {
    const d = _last && isObj(_last.raw.linkedin) && isObj(_last.raw.linkedin.data) ? _last.raw.linkedin.data : null;
    if (!d || !Array.isArray(d.rows)) return null;
    if (_liCurKey !== d.rows) { _liCurKey = d.rows; _liCurMap = new Map(d.rows.filter(isObj).map(r => [liRowId(r), r])); }
    return _liCurMap;
  }

  /**
   * True when row `id` changed after the basis the import was prepared from: the page now holds a newer version of
   * it (or holds it although the basis did not, or no longer holds a basis row), or the stored doc is newer than the
   * basis row or is gone. A row the basis did not have is not read here: liSave reads it and merges into it.
   */
  async function liChangedSince(db, id, base, opts) {
    const cur = liCurrentRows();
    const was = base.get(id);
    if (cur) {
      const now = cur.get(id);
      if (was && !now) return true;
      if (now && (!was || liNewer(now, was))) return true;
    }
    if (!was) return false;
    const snap = await writeWithTimeout(() => db.collection(LI_COLLECTION).doc(id).get(), liTimeout(opts));
    const stored = snap && snap.exists !== false && typeof snap.data === "function" ? snap.data() : null;
    return !isObj(stored) || liNewer(stored, was);
  }

  /**
   * Write rows one at a time, only those that differ from the last loaded rows (or `opts.existing`, the rows the
   * import was prepared from), and stop at the first failure. A row changed since that basis (liChangedSince) is
   * never overwritten: it is skipped and listed in `conflicts`. Never rejects. Resolves
   * { written, failed, skipped, conflicts: [id], saved: [row], error: null|{ id, code, message } }: `skipped` counts
   * the unchanged rows and the conflicts; `failed` counts the changed rows not written (the one that failed and
   * every one after it).
   */
  async function liSaveMany(db, rows, opts) {
    const list = arr(rows).filter(isObj);
    const baseRows = liLoadedRows(opts);
    const base = new Map(baseRows.filter(isObj).map(r => [liRowId(r), r]));
    const changed = [];
    let skipped = 0;
    for (const r of list) {
      const id = liRowId(r);
      const have = base.get(id);
      if (have && liSameFields(have, r)) { skipped++; continue; }
      changed.push(Object.assign({}, r, { id }));
    }
    const out = { written: 0, failed: 0, skipped, conflicts: [], saved: [], error: null };
    const one = Object.assign({}, isObj(opts) ? opts : {}, { _loadedIds: new Set(base.keys()) });
    for (let i = 0; i < changed.length; i++) {
      try {
        if (await liChangedSince(db, changed[i].id, base, opts)) {
          out.skipped++;
          out.conflicts.push(changed[i].id);
          continue;
        }
        out.saved.push(await liSave(db, changed[i], one));
        out.written++;
      } catch (e) {
        out.failed = changed.length - i;
        out.error = { id: changed[i].id, code: str(e && e.code) || "error", message: str(e && e.message != null ? e.message : e) };
        break;
      }
    }
    return out;
  }

  /** Delete linkedinRows/<id>. Rejects on failure or after 5 s. */
  async function liRemove(db, id, opts) {
    if (!db) throw liReject("unavailable", LI_NO_DB + ".");
    const docId = str(id).trim();
    if (!docId) throw liReject("invalid_argument", "No row id to delete.");
    try {
      await writeWithTimeout(() => db.collection(LI_COLLECTION).doc(docId).delete(), liTimeout(opts));
    } catch (e) {
      liNoteFailure(e);
      throw e;
    }
  }

  // ---- read (once per load, in parallel with the connectors)

  function liUnavailable() {
    return { state: "unavailable", data: null, error: null, storedAt: null, warnings: [LI_NO_DB], refreshing: false };
  }

  function liReadError(code, message) {
    return { state: "error", data: null, error: { code, server: LI_SERVER, message: clipExact(str(message), 300), fix: LI_READ_FIX },
      storedAt: null, warnings: [], refreshing: false };
  }

  /** user.can("data.write"): true, false, or null when the platform says nothing (no user, null, or a throw). */
  async function liWriteLevel(user) {
    try {
      const v = user && typeof user.can === "function" ? await user.can("data.write") : null;
      return v === true ? true : v === false ? false : null;
    } catch (_) {
      return null;
    }
  }

  /**
   * Read every doc in linkedinRows, a page of 1000 at a time: ordered by updatedAt, each later page starting at the
   * last page's final updatedAt (>=), deduped by id. Each page races the db timeout. Stops at a short page; at 20
   * pages, at a full page that adds nothing new, or at a full page ending in a doc without a numeric updatedAt the
   * read is `truncated` (more docs may exist). A store without orderBy gets one page. Rejects on a failed page.
   */
  async function liReadAll(db, timeoutMs) {
    const col = db.collection(LI_COLLECTION);
    const byId = new Map();
    const take = docs => {
      let added = 0;
      for (const doc of docs) {
        if (!doc || doc.exists === false) continue;
        const id = str(doc.id);
        if (!id || byId.has(id)) continue;
        const body = typeof doc.data === "function" ? doc.data() : null;
        if (isObj(body)) { byId.set(id, liNormRow(body, id)); added++; }
      }
      return added;
    };
    const page = async q => {
      const r = await withTimeout(Promise.resolve().then(() => q.get()).then(snap => ({ snap }), err => ({ err })), timeoutMs, TIMED_OUT);
      if (r === TIMED_OUT) throw liReject("timeout", `The LinkedIn rows read took longer than ${Math.round(timeoutMs / 1000)} s.`);
      if ("err" in r) throw r.err;
      return arr(r.snap && r.snap.docs);
    };
    if (typeof col.orderBy !== "function") {
      const docs = await page(col.limit(LI_PAGE));
      take(docs);
      return { rows: [...byId.values()], truncated: docs.length >= LI_PAGE };
    }
    let cursor = null;
    for (let n = 0; n < LI_MAX_PAGES; n++) {
      let q = col.orderBy("updatedAt");
      if (cursor !== null) q = q.where("updatedAt", ">=", cursor);
      const docs = await page(q.limit(LI_PAGE));
      const added = take(docs);
      if (docs.length < LI_PAGE) return { rows: [...byId.values()], truncated: false };
      const lastDoc = docs[docs.length - 1];
      const lastBody = lastDoc && typeof lastDoc.data === "function" ? lastDoc.data() : null;
      const next = isObj(lastBody) ? lastBody.updatedAt : undefined;
      if (added === 0 || typeof next !== "number" || !Number.isFinite(next)) break;
      cursor = next;
    }
    return { rows: [...byId.values()], truncated: true };
  }

  /** Read the whole collection (paged) and the viewer's write level, each raced against the db timeout. Never rejects. */
  function readLinkedin(db, user, timeoutMs) {
    if (!db) return Promise.resolve(liUnavailable());
    const read = Promise.resolve().then(() => liReadAll(db, timeoutMs)).then(res => ({ res }), err => ({ err }));
    const can = withTimeout(liWriteLevel(user), timeoutMs, false);
    return Promise.all([read, can]).then(([r, level]) => {
      if (r.err) {
        const code = r.err && typeof r.err.code === "string" ? r.err.code : "unavailable";
        if (UNAVAILABLE_CODES.has(code)) return liUnavailable();
        return liReadError(code, r.err && r.err.message != null ? r.err.message : r.err);
      }
      const { rows, truncated } = r.res;
      const warnings = truncated ? [`Only the first ${fmtInt(rows.length)} LinkedIn rows loaded.`] : [];
      const data = { rows, editable: level !== false && !truncated, canWrite: level, truncated, lockReason: truncated ? LI_TOO_MANY : null };
      return { state: "ok", data, error: null, storedAt: Date.now(), warnings, refreshing: false };
    });
  }

  // ---- derive

  const liTitle = r => [r.name || r.first_name || r.profile_url || "LinkedIn lead", r.company].filter(Boolean).join(" · ");
  const liAnswered = r => r.reply_answered_date !== "" && (r.reply_date === "" || r.reply_answered_date >= r.reply_date);
  const liAccepted = r => r.accepted_date !== "" || (r.stage !== "" && r.stage !== "Connect sent" && r.stage !== "Withdrawn");
  const liIsClosed = (r, outcome) => r.outcome === outcome || r.stage === outcome;

  function liDueDetail(r) {
    switch (r.stage) {
      case "Connect sent": return "Pending 21 days. Withdraw the request.";
      case "Accepted": return "Loom DM due";
      case "DM sent": return "FU1 due";
      case "Follow-up 1": return "FU2 due";
      case "Follow-up 2": return "FU3 due";
      case "Follow-up 3": return "No reply 7 days after FU3. Mark No reply.";
      case "No reply": return "Voice note window open";
      case "Positive reply": return "No answer 2 business days after the two times. Decide the next step.";
      case "Reply": return "The date they gave to check back. Decide the next step.";
      default: return "Touch due";
    }
  }

  function liSortRows(rows) {
    return rows.slice().sort((a, b) => {
      const x = a.next_touch_due, y = b.next_touch_due;
      if (x !== y) { if (!x) return 1; if (!y) return -1; return x < y ? -1 : 1; }
      return liTitle(a).localeCompare(liTitle(b)) || a.id.localeCompare(b.id);
    });
  }

  function deriveLinkedin(d, R, nowMs) {
    const rows = liSortRows(arr(d && d.rows).filter(isObj).map(r => liNormRow(r, r.id)));
    const today = R.end;
    const aged = addDays(today, -14); // the acceptance rule counts only requests sent 14 or more days ago

    const cohort = (inWin) => {
      const looms = rows.filter(r => inWin(r.dm_date));
      const byV = v => looms.filter(r => r.loom_variant === v);
      const replied = list => list.filter(r => r.reply_type !== "").length;
      const positive = list => list.filter(r => r.reply_type === "positive").length;
      const booked = rows.filter(r => inWin(meetingDay(r.meeting_booked)));
      const sentAged = rows.filter(r => inWin(r.connect_sent_date) && r.connect_sent_date <= aged);
      return {
        requests: rows.filter(r => inWin(r.connect_sent_date)).length,
        accepted: rows.filter(r => inWin(r.accepted_date)).length,
        looms: looms.length, replies: replied(looms), positive: positive(looms),
        booked: booked.length, won: booked.filter(r => liIsClosed(r, "Closed won")).length,
        loomsA: byV("A").length, loomsB: byV("B").length,
        repliesA: replied(byV("A")), repliesB: replied(byV("B")),
        positiveA: positive(byV("A")), positiveB: positive(byV("B")),
        agedSent: sentAged.length, agedAccepted: sentAged.filter(liAccepted).length
      };
    };
    const win = (a, b) => day => !!day && day >= a && day <= b;
    const c = cohort(win(R.start, R.end));
    const p = cohort(win(R.prevStart, R.prevEnd));

    const funnel = LI_FUNNEL.map(([key, label, conv]) => ({ key, label, value: c[key], prev: p[key], conv }));
    const rates = [
      makeRate("acceptance", "Acceptance", c.agedAccepted, c.agedSent, p.agedAccepted, p.agedSent, RULES.li_accept),
      makeRate("reply_rate_a", "Reply rate, variant A", c.repliesA, c.loomsA, p.repliesA, p.loomsA, null),
      makeRate("reply_rate_b", "Reply rate, variant B", c.repliesB, c.loomsB, p.repliesB, p.loomsB, null),
      makeRate("positive_rate", "Positive rate", c.positive, c.looms, p.positive, p.looms, null)
    ];

    const pending = rows.filter(r => r.stage === "Connect sent").length;
    const nearLimit = pending >= LI_PENDING_WARN;
    const extras = [
      { label: "Pending requests", value: nearLimit ? `${fmtInt(pending)} (near the 600 limit)` : fmtInt(pending) },
      { label: "Looms sent, variant A", value: fmtInt(c.loomsA) },
      { label: "Looms sent, variant B", value: fmtInt(c.loomsB) }
    ];

    // weekly numbers: this week, Monday to Sunday in Central
    const weekStart = mondayOf(today), weekEnd = addDays(weekStart, 6);
    const inWeek = win(weekStart, weekEnd);
    const w = cohort(inWeek);
    const allAged = rows.filter(r => r.connect_sent_date !== "" && r.connect_sent_date <= aged);
    const closedIn = outcome => rows.filter(r => liIsClosed(r, outcome) &&
      inWeek(r.updatedAt != null ? ymd(r.updatedAt) : meetingDay(r.meeting_booked))).length;
    const info = (key, label, n, dd) => makeRate(key, label, n, dd, null, null, null);
    const weekly = {
      weekStart, weekEnd,
      requestsSent: w.requests,
      pending, nearLimit,
      acceptance: makeRate("acceptance", "Acceptance", allAged.filter(liAccepted).length, allAged.length, null, null, RULES.li_accept),
      looms: { A: w.loomsA, B: w.loomsB },
      replyRate: { A: info("reply_rate_a", "Reply rate, variant A", w.repliesA, w.loomsA), B: info("reply_rate_b", "Reply rate, variant B", w.repliesB, w.loomsB) },
      positiveRate: { A: info("positive_rate_a", "Positive rate, variant A", w.positiveA, w.loomsA), B: info("positive_rate_b", "Positive rate, variant B", w.positiveB, w.loomsB) },
      callsBooked: w.booked,
      closedWon: closedIn("Closed won"),
      closedLost: closedIn("Closed lost")
    };

    // follow-ups
    const replyNow = [], due = [], upcoming = [], noReplyDue = [];
    const weekAhead = addDays(today, 7);
    for (const r of rows) {
      const url = safeUrl(r.profile_url);
      const title = liTitle(r);
      if (LI_REPLIED.has(r.stage) && !liAnswered(r)) {
        const t = r.reply_type ? r.reply_type.replace(/_/g, " ") : "";
        const since = isYmd(r.reply_date) ? startOfDayMs(r.reply_date) : r.updatedAt;
        replyNow.push({ id: `linkedin_reply:${r.id}`, group: "reply_now", kind: "linkedin_reply", title,
          detail: t ? `Replied (${t}). Answer on LinkedIn.` : "Replied. Answer on LinkedIn.", source: "linkedin",
          ageMs: since == null ? null : Math.max(0, nowMs - since), dueAt: null, overdue: false, url });
        continue;
      }
      const day = r.next_touch_due;
      if (!isYmd(day)) continue;
      const base = { title, detail: liDueDetail(r), source: "linkedin", ageMs: null, dueAt: startOfDayMs(day), url };
      if (day <= today) {
        due.push(Object.assign({ id: `linkedin_touch:${r.id}`, group: "due", kind: "linkedin_touch", overdue: day < today }, base));
        if (r.stage === "Follow-up 3") noReplyDue.push(r.id);
      } else if (day <= weekAhead) {
        upcoming.push(Object.assign({ id: `linkedin_touch:${r.id}`, group: "upcoming", kind: "linkedin_touch", overdue: false }, base));
      }
    }

    return { rows, editable: d && d.editable === true, lockReason: d && typeof d.lockReason === "string" && d.lockReason ? d.lockReason : null,
      pending, nearLimit, weekly, noReplyDue, funnel, rates, extras, callsBooked: c.booked, replyNow, due, upcoming };
  }

  // ------------------------------------------------------------------ model

  function emptySource(state) {
    return { state: state || "loading", data: null, error: null, storedAt: null, warnings: [], refreshing: false };
  }

  function deriveError(k, e) {
    const server = CONFIG.servers[k] || k;
    if (typeof console !== "undefined" && console.error) console.error(`[AdveroData] could not read the ${server} data`, e);
    return { code: "upstream_error", server, message: clipExact(str(e && e.message != null ? e.message : e), 300),
      fix: `Something in the ${server} data could not be read. Press Refresh; if it repeats, tell Claude.` };
  }

  function normCosts(c) {
    const v = x => { const n = typeof x === "number" ? x : Number(x); return Number.isFinite(n) && n > 0 ? n : 0; };
    const o = isObj(c) ? c : {};
    return { upwork: v(o.upwork), cold_email: v(o.cold_email), linkedin: v(o.linkedin) };
  }

  function channelStatus(s) {
    if (s.state === "loading") return "loading";
    if (s.state === "error") return "error";
    if (s.state === "unavailable") return "not_connected";
    return null;
  }

  function costPerCall(usd, calls) {
    return usd != null && usd > 0 && calls != null && calls > 0 ? round2(usd / calls) : null;
  }

  function monthlySpend(monthly, days) {
    return monthly > 0 ? round2(monthly * days / 30) : null;
  }

  function buildModel(raw, ctx) {
    raw = raw || {};
    ctx = ctx || {};
    const nowMs = toNowMs(ctx.now);
    const R = rangeFor(nowMs, ctx.rangeDays);
    const src = k => (isObj(raw[k]) ? raw[k] : emptySource("loading"));
    const ok = k => src(k).state === "ok" && isObj(src(k).data);
    const costsIn = isObj(raw.costs) ? raw.costs : {};
    const costs = normCosts(costsIn);

    // Each source's derive step is isolated: a throw becomes that source's error and never breaks the model.
    const deriveErrors = {};
    const derive = (k, fn) => {
      if (!ok(k)) return null;
      try {
        return fn(src(k).data);
      } catch (e) {
        deriveErrors[k] = deriveError(k, e);
        return null;
      }
    };
    const I = derive("instantly", d => deriveInstantly(d, R));
    const U = derive("upwork", d => deriveUpwork(d, R, nowMs));
    const G = derive("ghl", d => deriveGhl(d, R, nowMs));
    const C = derive("calendar", d => deriveCalendar(d, R, nowMs, G, I));
    const L = derive("linkedin", d => deriveLinkedin(d, R, nowMs));
    const followups = deriveFollowups(I, U, G, C, nowMs, R, L);

    const sources = {};
    for (const k of SOURCE_KEYS.concat(["linkedin"])) {
      const s = src(k);
      let state = ["loading", "ok", "error", "unavailable"].includes(s.state) ? s.state : "loading";
      let error = state === "error" && isObj(s.error)
        ? { code: str(s.error.code), server: str(s.error.server), message: str(s.error.message), fix: str(s.error.fix) } : null;
      if (deriveErrors[k]) { state = "error"; error = deriveErrors[k]; }
      sources[k] = {
        state,
        storedAt: typeof s.storedAt === "number" ? s.storedAt : null,
        error,
        warnings: arr(s.warnings).map(str),
        refreshing: s.refreshing === true
      };
    }

    const calls = C ? { upcoming: C.upcoming, pastInRange: C.pastInRange, bySource: C.bySource }
      : { upcoming: [], pastInRange: [], bySource: { cold_email: 0, upwork: 0, linkedin: 0, other: 0, unattributed: 0 } };

    // channel 1: cold email
    const coldStatus = channelStatus(sources.instantly) || (I ? (I.sending ? "live" : "paused") : "error");
    let coldText;
    if (I) {
      coldText = I.sending ? `Sending: ${I.counts.active} active of ${plural(I.counts.total, "campaign", "campaigns")}`
        : `Not sending: ${I.counts.active} active of ${plural(I.counts.total, "campaign", "campaigns")}`;
    } else coldText = statusTextFor(sources.instantly, "Instantly");
    const coldSpendUsd = monthlySpend(costs.cold_email, R.days);
    const coldCalls = I ? I.booked : null;
    const cold = {
      key: "cold_email", name: "Cold email", status: coldStatus, statusText: coldText,
      funnel: I ? I.funnel : COLD_FUNNEL.map(([key, label]) => ({ key, label, value: null, prev: null })),
      rates: I ? I.rates : COLD_RATES.map(([key, label, rule]) => emptyRate(key, label, RULES[rule])),
      series: { aLabel: "Sent", bLabel: "Human replies", cLabel: "Positive", points: I ? I.points : [] },
      spend: { usd: coldSpendUsd, note: coldSpendUsd == null ? "No monthly cost entered. Add it under Costs."
        : `${fmtUsd(costs.cold_email, true)}/mo scaled to ${R.days} days` },
      callsBooked: coldCalls, costPerCall: costPerCall(coldSpendUsd, coldCalls),
      extras: I ? I.extras : []
    };

    // channel 2: Upwork
    const upMonthly = monthlySpend(costs.upwork, R.days);
    let upUsd = null;
    if (upMonthly != null || U) upUsd = round2((upMonthly || 0) + (U ? U.spendUsd : 0));
    const monthlyNote = `${fmtUsd(costs.upwork, true)}/mo scaled to ${R.days} days`;
    const connectsNote = U ? `${plural(U.connectsSpent, "Connect", "Connects")} at ${fmtUsd(CONFIG.upworkConnectUsd, true)} (${fmtUsd(U.spendUsd, true)})` : "";
    let upNote;
    if (upMonthly != null) upNote = U ? `${monthlyNote} + ${connectsNote}` : monthlyNote;
    else upNote = U ? `${connectsNote}. No monthly cost entered. Add it under Costs.` : "No monthly cost entered. Add it under Costs.";
    // Each contact once across calendar calls in range attributed upwork and upwork Sales cards in Call Booked or later
    // whose stage changed in range, matched on attendee email = card email.
    let upCalls = null;
    if (C || G) {
      const contacts = new Set(C ? C.upworkContacts : []);
      if (G) for (const k of G.upworkCardContacts) contacts.add(k);
      upCalls = contacts.size;
    }
    const upwork = {
      key: "upwork", name: "Upwork",
      status: channelStatus(sources.upwork) || (U ? "live" : "error"),
      statusText: U ? `${plural(U.counts.proposals, "proposal", "proposals")} sent in the last ${R.days} days` : statusTextFor(sources.upwork, "Upwork"),
      funnel: U ? U.funnel : [["proposals", "Proposals sent"], ["replies", "Client replied"], ["offers", "Offers"], ["hired", "Hired"]]
        .map(([key, label]) => ({ key, label, value: null, prev: null })),
      rates: U ? U.rates : [emptyRate("reply_rate", "Client reply rate", RULES.upwork_reply), emptyRate("hire_rate", "Hire rate", null)],
      series: { aLabel: "Proposals", bLabel: "Client replied", cLabel: null, points: U ? U.points : [] },
      spend: { usd: upUsd, note: upNote },
      callsBooked: upCalls, costPerCall: costPerCall(upUsd, upCalls),
      extras: U ? U.extras : []
    };

    // channel 3: LinkedIn, computed from the tracker rows in the page's db
    const liUsd = monthlySpend(costs.linkedin, R.days);
    const liHasRows = !!L && L.rows.length > 0;
    let liStatus, liText;
    if (liHasRows) {
      liStatus = "live";
      liText = `${plural(L.rows.length, "person", "people")} in the tracker · ${fmtInt(L.pending)} pending`;
    } else if (sources.linkedin.state === "loading") {
      liStatus = "loading"; liText = "Loading LinkedIn rows…";
    } else if (sources.linkedin.state === "error") {
      liStatus = "error"; liText = sources.linkedin.error ? sources.linkedin.error.fix : LI_READ_FIX;
    } else if (sources.linkedin.state === "unavailable") {
      liStatus = "not_connected"; liText = "LinkedIn rows load when this page is open in claude.ai.";
    } else {
      liStatus = "not_connected"; liText = "No LinkedIn rows yet. Add or paste them in the LinkedIn tracker below.";
    }
    const liCalls = liHasRows ? L.callsBooked : (L ? 0 : null);
    const linkedin = {
      key: "linkedin", name: "LinkedIn", status: liStatus, statusText: liText,
      funnel: liHasRows ? L.funnel : LI_FUNNEL.map(([key, label, conv]) => ({ key, label, value: null, prev: null, conv })),
      rates: liHasRows ? L.rates : [emptyRate("acceptance", "Acceptance", RULES.li_accept), emptyRate("reply_rate_a", "Reply rate, variant A", null),
        emptyRate("reply_rate_b", "Reply rate, variant B", null), emptyRate("positive_rate", "Positive rate", null)],
      series: null,
      spend: { usd: liUsd, note: liUsd == null ? "No monthly cost entered. Add it under Costs." : `${fmtUsd(costs.linkedin, true)}/mo scaled to ${R.days} days` },
      callsBooked: liCalls, costPerCall: costPerCall(liUsd, liCalls), extras: liHasRows ? L.extras : []
    };

    // pipeline
    const pipeline = G ? G.pipeline : {
      name: "Sales", url: CONFIG.links.ghlOpportunities, stages: [],
      totals: { open: 0, openValue: 0, wonInRange: 0, wonValueInRange: 0, lostInRange: 0 },
      calls: { stages: [], showRate: emptyRate("show_rate", "Show rate", RULES.show_rate) }
    };

    // today
    const next7 = calls.upcoming.filter(c => c.start <= nowMs + 7 * DAY_MS);
    // Upwork ok but its billing summary missing: the part is unknown (null, not 0) and the sum covers the known parts.
    const upworkBilled = U ? (U.billedUsd != null ? U.billedUsd : null) : 0;
    const ghlWon = pipeline.totals.wonValueInRange;
    if (U && upworkBilled == null && !sources.upwork.warnings.some(w => /billing summary/.test(w))) {
      sources.upwork.warnings.push("Upwork billing summary didn't load, so Revenue in range leaves Upwork billed out.");
    }
    const alerts = buildAlerts(I, U, G, followups, L);
    const liModel = L ? { rows: L.rows, editable: L.editable === true && sources.linkedin.state === "ok" && !_liDenied, pending: L.pending,
      noReplyDue: L.noReplyDue, weekly: L.weekly, lockReason: _liDenied ? LI_DENIED : L.lockReason }
      : Object.assign({ rows: [], editable: false, pending: 0, noReplyDue: [] },
        { weekly: deriveLinkedin({ rows: [] }, R, nowMs).weekly, lockReason: null });

    return {
      generatedAt: nowMs,
      range: { days: R.days, start: R.start, end: R.end, prevStart: R.prevStart, prevEnd: R.prevEnd, label: R.label },
      sources,
      today: {
        waitingOnYou: followups.reply_now.length,
        callsNext7d: { count: next7.length, next: next7[0] || null },
        openPipeline: { count: pipeline.totals.open, value: pipeline.totals.openValue },
        revenue: { value: round2((upworkBilled == null ? 0 : upworkBilled) + ghlWon), upworkBilled, ghlWon },
        coldEmailSending: I ? I.sending : null,
        alerts
      },
      channels: [cold, upwork, linkedin],
      campaigns: I ? I.campaigns : [],
      proposals: U ? U.proposals : [],
      pipeline,
      calls,
      followups,
      costs: { upwork: costs.upwork, cold_email: costs.cold_email, linkedin: costs.linkedin, editable: costsIn.editable === true },
      linkedin: liModel
    };
  }

  function emptyRate(key, label, rule) {
    return { key, label, value: null, prev: null, format: "pct", target: rule ? rule.target : null, state: "no_data" };
  }

  function statusTextFor(s, name) {
    if (s.state === "loading") return `Loading ${name}…`;
    if (s.state === "error") return s.error ? s.error.fix : `${name} didn't answer.`;
    return `${name} isn't connected to this page.`;
  }

  function buildAlerts(I, U, G, followups, L) {
    const alerts = [];
    if (I && !I.sending) {
      alerts.push({ id: "cold_not_sending", severity: "critical", source: "cold_email",
        text: `Cold email is not sending: ${I.counts.paused} paused, ${plural(I.counts.drafts, "draft", "drafts")}, ${I.counts.active} active.` });
    }
    if (I) {
      const bounce = I.rates.find(r => r.key === "bounce_rate");
      if (bounce && bounce.state === "alert") {
        alerts.push({ id: "cold_bounce", severity: "critical", source: "cold_email",
          text: `Bounce rate is ${fmtPct(bounce.value)} (alert above 2.0%).` });
      }
      const reply = I.rates.find(r => r.key === "reply_rate");
      if (reply && reply.state === "alert") {
        alerts.push({ id: "cold_reply_rate", severity: "warning", source: "cold_email",
          text: `Cold email reply rate is ${fmtPct(reply.value)} (target ${reply.target}).` });
      }
    }
    if (U) {
      const reply = U.rates.find(r => r.key === "reply_rate");
      if (reply && reply.state === "alert") {
        alerts.push({ id: "upwork_reply_rate", severity: "warning", source: "upwork",
          text: `Upwork client reply rate is ${fmtPct(reply.value)} (target ${reply.target}).` });
      }
    }
    if (L && L.nearLimit) {
      alerts.push({ id: "linkedin_pending", severity: "warning", source: "linkedin",
        text: `${fmtInt(L.pending)} LinkedIn requests are pending, near the 600 limit. Withdraw the ones older than 3 weeks.` });
    }
    if (G) {
      const stale = G.openCards.filter(c => c.staleLevel === "critical").length;
      if (stale > 0) alerts.push({ id: "stale_deals", severity: "warning", source: "ghl",
        text: stale === 1 ? "1 deal is stale" : `${stale} deals are stale` });
    }
    const overdue = followups.due.filter(i => i.kind === "ghl_task" && i.overdue).length;
    if (overdue > 0) alerts.push({ id: "overdue_tasks", severity: "warning", source: "ghl",
      text: overdue === 1 ? "1 task is overdue" : `${overdue} tasks are overdue` });
    const rank = { critical: 0, warning: 1 };
    return alerts.map((a, i) => [a, i]).sort((x, y) => rank[x[0].severity] - rank[y[0].severity] || x[1] - y[1]).map(x => x[0]);
  }

  // ------------------------------------------------------------------ costs (db)

  async function loadCosts(db) {
    if (!db) return normCosts(null);
    try {
      const snap = await db.doc("settings/costs").get();
      return normCosts(snap && snap.exists ? snap.data() : null);
    } catch (_) {
      return normCosts(null);
    }
  }

  async function saveCosts(db, costs) {
    const clean = normCosts(costs);
    if (!db) return normCosts(null);
    await db.doc("settings/costs").set(clean);
    return clean;
  }

  // ------------------------------------------------------------------ load

  const FETCHERS = { instantly: fetchInstantly, upwork: fetchUpwork, ghl: fetchGhl, calendar: fetchCalendar };

  // The latest load's state: its rangeDays, ctx and raw input (per-source { state, data, ... } plus costs).
  // A later load in the same range seeds from it, so a source never drops back to "loading", and rebuild()
  // re-derives the model from it without calling any connector.
  let _last = null;
  // Set when a LinkedIn write was refused for access after user.can("data.write") said nothing (null): from then on
  // the tracker is read-only for this visit.
  let _liDenied = false;

  const defaultCosts = () => Object.assign(normCosts(null), { editable: false });
  const sameCosts = (a, b) => isObj(a) && isObj(b) && a.upwork === b.upwork && a.cold_email === b.cold_email &&
    a.linkedin === b.linkedin && a.editable === b.editable;

  /**
   * Fetch the four sources in parallel and call onUpdate(model) right away (seeded or loading), after each source
   * settles, and again if the cost settings arrive later. Never waits on db before starting the fetches; the costs
   * read races a ~3 s timeout. With no mcp it resolves at once.
   */
  async function load(ctx, onUpdate) {
    ctx = Object.assign({}, ctx || {});
    ctx.rangeDays = normDays(ctx.rangeDays);
    const nowMs = toNowMs(ctx.now);
    ctx.now = new Date(nowMs);
    const R = rangeFor(nowMs, ctx.rangeDays);
    const timeoutMs = typeof ctx.dbTimeoutMs === "number" && ctx.dbTimeoutMs >= 0 ? ctx.dbTimeoutMs : DB_TIMEOUT_MS;
    const prev = _last;
    const sameRange = !!prev && prev.rangeDays === ctx.rangeDays;
    const hasMcp = !!(ctx.mcp && typeof ctx.mcp.callTool === "function");

    const raw = { costs: prev && isObj(prev.raw.costs) ? Object.assign({}, prev.raw.costs) : defaultCosts() };
    for (const k of SOURCE_KEYS) {
      const p = sameRange && isObj(prev.raw[k]) ? prev.raw[k] : null;
      if (!hasMcp) raw[k] = emptySource("unavailable");
      // Same range: keep the last settled result (with its data) and mark it refreshing until the new one settles.
      else if (p && p.state !== "loading") raw[k] = Object.assign({}, p, { refreshing: true });
      else raw[k] = emptySource("loading");
    }
    // LinkedIn rows come from the page's db, not a connector, and don't depend on the range: any earlier settled
    // result is kept (refreshing) while this load re-reads them.
    const prevLi = prev && isObj(prev.raw.linkedin) ? prev.raw.linkedin : null;
    if (!ctx.db) raw.linkedin = liUnavailable();
    else if (prevLi && prevLi.state !== "loading" && prevLi.state !== "unavailable") raw.linkedin = Object.assign({}, prevLi, { refreshing: true });
    else raw.linkedin = emptySource("loading");
    const st = { rangeDays: ctx.rangeDays, ctx, raw, costsPatched: false, liPatched: false };
    _last = st;

    let last = null;
    const emit = () => {
      let m;
      try {
        m = buildModel(raw, ctx);
      } catch (e) {
        if (typeof console !== "undefined") console.error("[AdveroData] buildModel threw", e);
        return last;
      }
      last = m;
      if (typeof onUpdate === "function") {
        try { onUpdate(m); } catch (e) { if (typeof console !== "undefined") console.error("[AdveroData] onUpdate threw", e); }
      }
      return m;
    };

    // Costs: read in the background. Until they arrive the model uses the last known costs (defaults on a first load).
    const costsRead = (async () => {
      const c = await loadCosts(ctx.db);
      const editable = await canWriteDb(ctx.db, ctx.user);
      return Object.assign(c, { editable });
    })().catch(() => null);
    const costsApplied = costsRead.then(c => {
      if (!c) return;
      // A rebuild({costs}) during this load is newer than this read: keep its numbers, take only `editable`.
      const next = st.costsPatched ? Object.assign({}, raw.costs, { editable: c.editable === true })
        : Object.assign(normCosts(c), { editable: c.editable === true });
      const changed = !sameCosts(next, raw.costs);
      raw.costs = next;
      if (changed) emit();
    });

    // LinkedIn rows: one read of the collection, started now and raced against the db timeout. It never delays a
    // connector source; its result is one more progressive update.
    const liApplied = ctx.db ? readLinkedin(ctx.db, ctx.user, timeoutMs).then(res => {
      // A rebuild({linkedinRows}) during this load is newer than this read: keep its rows, take the rest.
      if (st.liPatched && res.state === "ok" && isObj(raw.linkedin) && isObj(raw.linkedin.data)) {
        res = Object.assign({}, res, { data: Object.assign({}, res.data, { rows: raw.linkedin.data.rows }) });
      }
      raw.linkedin = res;
      emit();
    }).catch(e => { if (typeof console !== "undefined") console.error("[AdveroData] LinkedIn rows read failed", e); }) : Promise.resolve();

    emit();
    if (!hasMcp) return last;

    const env = { db: ctx.db || null, user: ctx.user || null, nowMs, dbTimeoutMs: timeoutMs, roomWrites: { disabled: false } };
    const runSource = async (k) => {
      const caller = makeCaller({ mcp: ctx.mcp, serverKey: k, refresh: ctx.refresh, sleep: ctx.sleep, random: ctx.random });
      try {
        const out = await FETCHERS[k](caller, R, env);
        return { state: "ok", data: out.data, error: null,
          storedAt: caller.meta.oldestCached != null ? caller.meta.oldestCached : Date.now(), warnings: out.warnings || [], refreshing: false };
      } catch (e) {
        caller.abort();
        const se = toSourceError(e, caller.server);
        return { state: se.state, data: null, error: se.state === "error" ? publicError(se) : null, storedAt: null, warnings: [], refreshing: false };
      }
    };

    await Promise.all(SOURCE_KEYS.map(k => runSource(k).then(res => { raw[k] = res; emit(); })));
    await withTimeout(costsApplied, timeoutMs, null);
    // The rows read pages itself, each page raced against the db timeout, so it always settles.
    await withTimeout(liApplied, timeoutMs * (LI_MAX_PAGES + 1), null);
    return last;
  }

  /**
   * Rebuild the model synchronously from the latest load's raw data, with `patch.costs` merged into the cost
   * settings (they also stick for later emits of that load). Never calls a connector. `patch.now` optionally
   * moves the clock; by default the latest load's `now` is kept. Before any load it returns a loading model.
   */
  function rebuild(patch) {
    patch = isObj(patch) ? patch : {};
    const liRows = Array.isArray(patch.linkedinRows) ? patch.linkedinRows.filter(isObj).map(r => liNormRow(r, r.id)) : null;
    if (!_last) {
      const raw0 = { costs: Object.assign(defaultCosts(), normCosts(patch.costs)) };
      if (liRows) raw0.linkedin = { state: "ok", data: { rows: liRows, editable: false, canWrite: false, truncated: false, lockReason: null },
        error: null, storedAt: null, warnings: [], refreshing: false };
      return buildModel(raw0, { rangeDays: 30, now: patch.now != null ? patch.now : Date.now() });
    }
    if (liRows) {
      // The rows the UI just saved (or the full list after a delete) replace the cached ones.
      const cur = isObj(_last.raw.linkedin) ? _last.raw.linkedin : emptySource("loading");
      _last.raw.linkedin = Object.assign({}, cur, {
        state: "ok", error: null,
        data: Object.assign({ editable: false, canWrite: false, truncated: false, lockReason: null }, isObj(cur.data) ? cur.data : {},
          { rows: liRows, editable: isObj(cur.data) && cur.data.editable === true }),
        warnings: cur.state === "error" ? [] : arr(cur.warnings),
        storedAt: typeof cur.storedAt === "number" ? cur.storedAt : Date.now()
      });
      _last.liPatched = true;
    }
    if (isObj(patch.costs)) {
      const cur = isObj(_last.raw.costs) ? _last.raw.costs : defaultCosts();
      const merged = Object.assign({}, cur, patch.costs);
      _last.raw.costs = Object.assign(normCosts(merged), { editable: typeof merged.editable === "boolean" ? merged.editable : cur.editable === true });
      _last.costsPatched = true;
    }
    const ctx = Object.assign({}, _last.ctx);
    if (patch.now != null) ctx.now = new Date(toNowMs(patch.now));
    return buildModel(_last.raw, ctx);
  }

  const _internals = {
    ymd, addDays, startOfDayMs, endOfDayMs, rangeFor, dateList, toMs, num, unwrap, clip, safeUrl,
    fixFor, toSourceError, publicError, isNotFound, rateState, RULES, makeRate, makeLimiter, makeCaller, readPayload,
    fetchInstantly, fetchUpwork, fetchGhl, fetchCalendar, checkRooms, roomCacheVerdict, extractRoomId, normProposal,
    deriveInstantly, deriveUpwork, deriveGhl, deriveCalendar, deriveFollowups, attributeSource, staleLevelFor,
    isSalesCall, pickEvent, zoomJoinUrl, attributeCall, FREEMAIL, buildAlerts, normCosts, withTimeout, stalePeriod,
    COLUMN_CAP, isYmd, weekdayOf, addBusinessDays, mondayOf, meetingDay, splitDelimited, pasteDate, readLinkedin,
    deriveLinkedin, liNormRow, LI_WRITE_TIMEOUT_MS, LI_PENDING_WARN, LI_PAGE, LI_MAX_PAGES, LI_TOO_MANY, LI_DENIED,
    resetMemory: () => { _memRooms.clear(); _roomShapeLogged = false; _last = null; _liDenied = false; _liCurKey = null; _liCurMap = null; },
    memRooms: _memRooms
  };

  const linkedin = {
    STAGES: LI_STAGES.slice(), REPLY_TYPES: LI_REPLY_TYPES.slice(), FIELDS: LI_FIELDS.slice(),
    EVENTS: LI_EVENTS.map(e => Object.assign({}, e)),
    rowId: liRowId, applyEvent: liApplyEvent, parsePaste: liParsePaste, merge: liMerge,
    save: liSave, saveMany: liSaveMany, remove: liRemove
  };

  const AdveroData = { CONFIG, load, rebuild, buildModel, loadCosts, saveCosts, linkedin, _internals };
  if (typeof module !== "undefined" && module.exports) module.exports = AdveroData; else root.AdveroData = AdveroData;
})(typeof globalThis !== "undefined" ? globalThis : this);
