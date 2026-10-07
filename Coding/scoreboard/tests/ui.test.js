// UI tests for the LinkedIn tracker in scoreboard.html, run in jsdom with the real data layer, a fake mcp (every
// connector call fails after a delay, which is enough for connector-only updates) and an in-memory db.
// jsdom is not a project dependency: set JSDOM_PATH, or these tests use the copy at ~/.hermes/hermes-agent and
// skip when that isn't there. A JSDOM_PATH that doesn't load fails the run. Run: node --test Coding/scoreboard/tests/*.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");

const JSDOM_DEFAULT = path.join(os.homedir(), ".hermes/hermes-agent/node_modules/jsdom");
let JSDOM = null;
if (process.env.JSDOM_PATH) {
  try { JSDOM = require(process.env.JSDOM_PATH).JSDOM; } catch (e) { JSDOM = null; }
  if (typeof JSDOM !== "function") throw new Error("JSDOM_PATH is set but jsdom did not load from " + process.env.JSDOM_PATH);
} else {
  try { JSDOM = require(JSDOM_DEFAULT).JSDOM; } catch (_) { JSDOM = null; }
}
const SKIP_WHY = "jsdom not found at " + JSDOM_DEFAULT + "; set JSDOM_PATH to a jsdom install to run the UI tests";
const uiTest = JSDOM ? test : (name, fn) => test(name, { skip: SKIP_WHY }, fn);

const DIR = path.join(__dirname, "..");
const PAGE = fs.readFileSync(path.join(DIR, "scoreboard.html"), "utf8");
const DATAJS = fs.readFileSync(path.join(DIR, "scoreboard-data.js"), "utf8");
const SAMPLEJS = fs.readFileSync(path.join(__dirname, "sample-model.js"), "utf8");
const clone = v => JSON.parse(JSON.stringify(v));
const wait = ms => new Promise(r => setTimeout(r, ms));
const text = el => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");

function fakeDb(rows, opts) {
  opts = opts || {};
  const cols = new Map();
  const col = n => { if (!cols.has(n)) cols.set(n, new Map()); return cols.get(n); };
  const db = { writes: [], deletes: [] };
  const ref = (c, id) => ({
    get: async () => { const v = col(c).get(id); return { id, exists: !!v, data: () => v && clone(v) }; },
    set: async body => {
      if (opts.setDelay) await wait(opts.setDelay);
      if (c === "linkedinRows" && opts.failCode) throw { code: opts.failCode, message: "refused" };
      db.writes.push([c, id]); col(c).set(id, clone(body));
    },
    update: async patch => { col(c).set(id, Object.assign({}, col(c).get(id), patch)); },
    delete: async () => { if (opts.deleteDelay) await wait(opts.deleteDelay); db.deletes.push([c, id]); col(c).delete(id); }
  });
  const query = c => {
    const q = { where: () => q, orderBy: () => q, limit: () => q,
      get: async () => ({ docs: [...col(c).entries()].map(([id, v]) => ({ id, exists: true, data: () => clone(v) })) }), doc: id => ref(c, id) };
    return q;
  };
  db.collection = c => query(c);
  db.doc = p => { const [c, id] = p.split("/"); return ref(c, id); };
  db.rows = () => col("linkedinRows");
  for (const [id, body] of Object.entries(rows || {})) col("linkedinRows").set(id, clone(body));
  return db;
}

function fakeMcp(delays) {
  return {
    async callTool(server) {
      await wait((delays && delays[server]) || 20);
      throw { code: "tool_error", message: server + " test error" };
    }
  };
}

function makePage(opts) {
  opts = opts || {};
  const errors = [];
  const html = PAGE.replace('<script src="scoreboard-data.js"></script>', "<script>" + DATAJS + "</script>");
  const dom = new JSDOM("<!doctype html><html><head></head><body>" + html + "</body></html>", {
    url: "https://example.org/scoreboard.html" + (opts.hash || ""),
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
      window.console.error = (...a) => errors.push(a.map(String).join(" "));
      window.localStorage.setItem("advero-scoreboard-tab", "linkedin");
      window.localStorage.setItem("advero-scoreboard-li-filter", "all");
      const origAppend = window.Node.prototype.appendChild;
      window.Node.prototype.appendChild = function (c) {
        if (c && c.tagName === "SCRIPT" && /sample-model\.js$/.test(c.getAttribute("src") || "")) {
          const r = origAppend.call(this, window.document.createComment("sample"));
          setTimeout(() => { window.eval(SAMPLEJS); if (c.onload) c.onload(); }, 0);
          return r;
        }
        return origAppend.call(this, c);
      };
      if (opts.caps) window.claude = { use: name => Promise.resolve(opts.caps[name] || null) };
      if (window.HTMLDialogElement && !window.HTMLDialogElement.prototype.showModal) {
        window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
        window.HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
      }
    }
  });
  const w = dom.window, d = w.document;
  return {
    w, d, errors,
    close: () => w.close(),
    q: s => d.querySelector(s),
    row: id => { const x = d.querySelector('[data-li-row="' + id + '"]'); return x && x.closest("tr"); },
    ctl: (id, role) => d.querySelector('[data-li-row="' + id + '"][data-li-role="' + role + '"]'),
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input", { bubbles: true })); },
    change: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("change", { bubbles: true })); },
    key: (el, k) => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }))
  };
}

const base = { name: "", first_name: "", profile_url: "", company: "", role: "", what_they_do: "", industry: "", country: "",
  connect_sent_date: "", accepted_date: "", dm_date: "", loom_variant: "", last_touch_date: "", next_touch_due: "", stage: "",
  reply_type: "", reply_date: "", reply_answered_date: "", meeting_booked: "", outcome: "", slots_offered: "", updatedAt: 1 };
const seed = () => ({
  "test-old-handle": Object.assign({}, base, { name: "Test Old Handle", first_name: "Test", profile_url: "https://www.linkedin.com/in/test-old-handle",
    company: "Test Handle Co", stage: "DM sent", dm_date: "2026-10-01", loom_variant: "A", last_touch_date: "2026-10-01", next_touch_due: "2026-10-03" }),
  "test-other": Object.assign({}, base, { name: "Test Other", profile_url: "https://www.linkedin.com/in/test-other", stage: "Accepted", accepted_date: "2026-10-01" }),
  "r_testnourl001": Object.assign({}, base, { name: "Test No Url", stage: "Follow-up 1", last_touch_date: "2026-10-01", next_touch_due: "2026-10-05" }),
  "test-replied": Object.assign({}, base, { name: "Test Replied", profile_url: "https://www.linkedin.com/in/test-replied", stage: "Reply",
    reply_type: "price", reply_date: "2026-10-05" })
});
const caps = (db, can, delays) => ({ mcp: fakeMcp(delays), db, user: { can: async () => (can === undefined ? true : can) } });

uiTest("typing in Add person survives connector-only updates: focus, caret and value stay", async () => {
  const db = fakeDb(seed());
  const p = makePage({ caps: caps(db, true, { Upwork: 700, GHL: 350 }) });
  try {
    await wait(120);
    assert.ok(p.q("#li-add"), "the tracker is editable before the slow connectors answer");
    p.q("#li-add").click();
    await wait(10);
    const nm = p.q("#lf-name");
    nm.focus();
    p.type(nm, "Test Jan");
    nm.setSelectionRange(5, 8);
    let moves = 0, last = p.d.activeElement;
    for (let i = 0; i < 9; i++) { await wait(100); if (p.d.activeElement !== last) { moves++; last = p.d.activeElement; } }
    const chips = [...p.d.querySelectorAll("#chips .chip")];
    assert.deepEqual(chips.slice(0, 4).map(c => c.classList.contains("is-error")), [true, true, true, true], "every connector settled (failed)");
    assert.ok(!chips.some(c => c.classList.contains("is-loading") || c.classList.contains("is-refreshing")), "nothing is still loading");
    assert.equal(moves, 0, "focus never moved while the connectors loaded");
    assert.equal(p.d.activeElement, nm, "the same input element, not a rebuilt copy");
    assert.deepEqual([nm.value, nm.selectionStart, nm.selectionEnd], ["Test Jan", 5, 8]);
    p.type(nm, "Test Jane");
    assert.equal(p.q("#lf-name").value, "Test Jane", "later keystrokes land in the input");

    // a LinkedIn update (Refresh re-reads the rows) does rebuild the tracker: the fallback puts focus,
    // value and selection back
    p.q("#refresh-btn").click();
    const co = p.q("#lf-company");
    co.focus();
    p.type(co, "Test Co Name");
    co.setSelectionRange(2, 4);
    await wait(900);
    const co2 = p.q("#lf-company");
    assert.equal(p.d.activeElement, co2);
    assert.deepEqual([co2.value, co2.selectionStart, co2.selectionEnd, p.q("#lf-name").value], ["Test Co Name", 2, 4, "Test Jane"]);
  } finally { p.close(); }
});

uiTest("the doc id follows an edited or added profile URL; a later paste of it updates the row", async () => {
  const db = fakeDb(seed());
  const p = makePage({ caps: caps(db) });
  try {
    await wait(150);
    const formField = (n, v) => p.type(p.q("form.li-card [name=" + n + "]"), v);

    // edit the URL of a saved row: saved under the new slug, old doc removed
    p.ctl("test-old-handle", "edit").click(); await wait(5);
    formField("profile_url", "https://www.linkedin.com/in/test-new-handle/");
    p.q("#lf-submit").click(); await wait(40);
    assert.deepEqual([...db.rows().keys()].sort(), ["r_testnourl001", "test-new-handle", "test-other", "test-replied"]);
    assert.deepEqual(db.deletes, [["linkedinRows", "test-old-handle"]]);
    assert.equal(db.rows().get("test-new-handle").dm_date, "2026-10-01");
    assert.ok(p.row("test-new-handle") && !p.row("test-old-handle"));

    // add a URL to a row that had none
    p.ctl("r_testnourl001", "edit").click(); await wait(5);
    formField("profile_url", "https://www.linkedin.com/in/test-no-url-now");
    p.q("#lf-submit").click(); await wait(40);
    assert.ok(db.rows().has("test-no-url-now") && !db.rows().has("r_testnourl001"));

    // moving onto another row's URL is refused, and nothing is written
    const writes = db.writes.length;
    p.ctl("test-other", "edit").click(); await wait(5);
    formField("profile_url", "https://www.linkedin.com/in/TEST-NEW-HANDLE");
    p.q("#lf-submit").click(); await wait(40);
    assert.equal(text(p.q("#lf-status")), "Another row already has this profile URL.");
    assert.equal(db.writes.length, writes);
    p.q("form.li-card .btn--glass").click(); await wait(5);

    // a later paste of the new URLs: both match their rows ("Will update"), none is new
    p.q("#li-paste-btn").click(); await wait(5);
    p.type(p.q("#li-paste-text"), "Full Name\tLinkedIn URL\tCompany Name\nTest Old Handle\thttps://www.linkedin.com/in/test-new-handle\tTest Renamed Co\n" +
      "Test No Url\thttps://www.linkedin.com/in/test-no-url-now\tTest No Url Co");
    await wait(260);
    assert.deepEqual([...p.d.querySelectorAll("#li-paste-preview .li-sum .tag")].map(text), ["0 new rows", "2 will update"]);
    assert.deepEqual([...p.d.querySelectorAll("#li-paste-preview tbody tr td:first-child")].map(text), ["Will update", "Will update"]);
    p.q("#li-import").click(); await wait(60);
    assert.equal(db.rows().size, 4);
    assert.deepEqual([db.rows().get("test-new-handle").company, db.rows().get("test-new-handle").stage], ["Test Renamed Co", "DM sent"]);
    assert.deepEqual(p.errors, []);
  } finally { p.close(); }
});

uiTest("Log… applies only on Apply or Enter; Answer sent is offered only with a reply; reply type waits for Save", async () => {
  const db = fakeDb(seed());
  const p = makePage({ caps: caps(db) });
  try {
    await wait(150);
    const log = id => p.ctl(id, "log");
    const options = id => [...log(id).options].map(o => o.value);
    assert.ok(!options("test-other").includes("answer_sent"), "no reply yet: no Answer sent");
    assert.ok(options("test-replied").includes("answer_sent"));

    // arrowing through the menu (change events) writes nothing
    for (const v of ["accepted", "fu1_sent", "closed_lost", "withdrawn"]) p.change(log("test-other"), v);
    await wait(30);
    assert.equal(db.writes.filter(x => x[0] === "linkedinRows").length, 0);
    assert.equal(db.rows().get("test-other").stage, "Accepted");
    p.ctl("test-other", "apply").click(); await wait(40);
    assert.equal(db.rows().get("test-other").stage, "Withdrawn");

    // Enter on the menu applies too
    p.change(log("test-replied"), "fu2_sent");
    p.key(log("test-replied"), "Enter"); await wait(40);
    assert.equal(db.rows().get("test-replied").stage, "Follow-up 2");

    // Reply…: Apply opens the reply type; picking one alone writes nothing, Save logs it
    p.change(log("test-old-handle"), "reply");
    p.ctl("test-old-handle", "apply").click(); await wait(10);
    const pick = p.ctl("test-old-handle", "pick");
    assert.equal(pick.tagName, "SELECT");
    p.change(pick, "positive"); p.change(p.ctl("test-old-handle", "pick"), "not_interested"); await wait(20);
    assert.equal(db.rows().get("test-old-handle").stage, "DM sent");
    p.ctl("test-old-handle", "save").click(); await wait(40);
    assert.deepEqual([db.rows().get("test-old-handle").stage, db.rows().get("test-old-handle").reply_type], ["Reply", "not_interested"]);

    // DM sent… still asks for the variant after Apply
    p.change(log("test-other"), "dm_sent");
    p.ctl("test-other", "apply").click(); await wait(10);
    assert.ok(p.ctl("test-other", "pick") && p.ctl("test-other", "pick-b"));
    assert.deepEqual(p.errors, []);
  } finally { p.close(); }
});

uiTest("a save refused for access after can() returned null turns the tracker read-only", async () => {
  const db = fakeDb(seed(), { failCode: "invalid_argument" });
  const p = makePage({ caps: caps(db, null) });
  try {
    await wait(150);
    p.change(p.ctl("test-other", "log"), "fu1_sent");
    p.ctl("test-other", "apply").click(); await wait(40);
    const panel = p.q("#tabpanel-linkedin");
    assert.equal(text(panel.querySelector(".fix")), "Saving isn't allowed for this view.");
    assert.equal(panel.querySelectorAll("[data-li-role=log]").length, 0);
    assert.ok(!p.q("#li-add"));
  } finally { p.close(); }

  // can() said yes: the same failure is a failed save, and the tracker stays editable
  const p2 = makePage({ caps: caps(fakeDb(seed(), { failCode: "invalid_argument" }), true) });
  try {
    await wait(150);
    p2.change(p2.ctl("test-other", "log"), "fu1_sent");
    p2.ctl("test-other", "apply").click(); await wait(40);
    assert.equal(text(p2.q('[data-li-msg="test-other"]')), "Couldn't save. Try again.");
    assert.ok(p2.q("#li-add"));
  } finally { p2.close(); }
});

uiTest("LinkedIn funnel shows no '% of' line for conv:false steps; footer copy", async () => {
  const p = makePage({ hash: "#sample" });
  try {
    await wait(150);
    const li = p.d.querySelectorAll("#channels-grid .channel")[2];
    const convs = [...li.querySelectorAll(".funnel .step")].map(s => text(s.querySelector(".step__conv")));
    assert.deepEqual(convs, ["", "", "", "33% of Looms sent", "67% of Replies", "", "0% of Calls booked"]);
    assert.equal(li.querySelectorAll(".funnel .meter").length, 3);
    const cold = p.d.querySelectorAll("#channels-grid .channel")[0];
    assert.ok(cold.querySelectorAll(".funnel .step__conv").length > 0, "other channels keep their % lines");
    assert.ok(text(p.q(".foot__base")).endsWith("Connector data is read-only. LinkedIn rows are saved in this page."));
    assert.ok(!/Read-only\./.test(text(p.q(".foot__base"))));
  } finally { p.close(); }
});

// Imports and single-row writes never overlap: Import waits for a row save or delete in flight, and every row write
// control waits for an import. Rows changed elsewhere and re-read during an import are never reverted by it.
const pasteRows = (p, lines) => p.type(p.q("#li-paste-text"), "Full Name\tLinkedIn URL\tCompany Name\n" + lines.join("\n"));
const newLines = n => Array.from({ length: n }, (_, i) => "Test New" + i + "\thttps://www.linkedin.com/in/test-new" + i + "\tTest New Co");
const tableIds = p => [...p.d.querySelectorAll("#tabpanel-linkedin [data-li-role=log]")].map(x => x.dataset.liRow).sort();
const stageOf = p => id => { const tr = p.row(id); return tr ? text(tr.children[2]) : null; };
const newDocs = db => [...db.rows().keys()].filter(k => /^test-new/.test(k));

uiTest("Import waits for a row Log in flight, then runs normally; row controls wait for the import", async () => {
  const db = fakeDb(seed(), { setDelay: 60 });
  const p = makePage({ caps: caps(db) });
  try {
    await wait(150);
    p.q("#li-paste-btn").click(); await wait(5);
    pasteRows(p, newLines(4).concat(["Test Old Handle\thttps://www.linkedin.com/in/test-old-handle\tTest Pasted Co"]));
    await wait(260);
    assert.ok(!p.q("#li-import").disabled && !p.q("#li-import-wait"));

    // FU1 on test-old-handle is saving: Import is off, with the reason, and a click (even forced) starts nothing
    p.change(p.ctl("test-old-handle", "log"), "fu1_sent");
    p.ctl("test-old-handle", "apply").click();
    await wait(5);
    assert.ok(p.q("#li-import").disabled);
    assert.equal(text(p.q("#li-import-wait")), "Saving a row… Import when it finishes");
    p.q("#li-import").click();
    p.q("#li-import").disabled = false; p.q("#li-import").click();
    await wait(20);
    assert.deepEqual([newDocs(db), p.q("#li-importing")], [[], null], "no import started during the save");

    // the save settles: Import is offered again, and the preview has the logged row as its basis
    await wait(80);
    assert.equal(db.rows().get("test-old-handle").stage, "Follow-up 1");
    assert.ok(!p.q("#li-import").disabled && !p.q("#li-import-wait"));
    p.q("#li-import").click();
    await wait(5);
    assert.equal(text(p.q("#li-importing")), "Importing… Rows can be changed again when it finishes.");
    assert.ok(p.q("#li-add").disabled && p.q("#li-import").disabled);
    for (const role of ["log", "apply", "edit", "delete"]) assert.ok(p.ctl("test-other", role).disabled, role + " waits for the import");
    // a Log or Delete tried now writes nothing
    p.change(p.ctl("test-other", "log"), "withdrawn"); p.ctl("test-other", "apply").click();
    p.ctl("test-replied", "delete").click();

    await wait(900);
    assert.ok(!p.q("#li-importing") && !p.q("#li-add").disabled && !p.ctl("test-other", "log").disabled);
    assert.equal(text(p.q("#li-paste-preview [role=status]")), "Imported 5");
    const r = db.rows().get("test-old-handle");
    assert.deepEqual([r.stage, r.company], ["Follow-up 1", "Test Pasted Co"], "the import merged onto the logged row");
    assert.equal(stageOf(p)("test-old-handle"), "Follow-up 1", "the table agrees with the db");
    assert.equal(db.rows().get("test-other").stage, "Accepted");
    assert.ok(db.rows().has("test-replied") && !p.q('[data-li-role=confirm][data-li-row="test-replied"]'));
    assert.deepEqual(tableIds(p), [...db.rows().keys()].sort());
    assert.equal(db.rows().size, 8);

    // a later edit of another field keeps the logged stage
    p.ctl("test-old-handle", "edit").click(); await wait(5);
    p.type(p.q("form.li-card [name=company]"), "Test Handle Co Renamed");
    p.q("#lf-submit").click(); await wait(150);
    const r2 = db.rows().get("test-old-handle");
    assert.deepEqual([r2.stage, r2.next_touch_due, r2.company], ["Follow-up 1", r.next_touch_due, "Test Handle Co Renamed"]);
    assert.deepEqual(p.errors, []);
  } finally { p.close(); }
});

uiTest("Import waits for a Delete in flight; the deleted row stays deleted", async () => {
  const db = fakeDb(seed(), { setDelay: 30, deleteDelay: 60 });
  const p = makePage({ caps: caps(db) });
  try {
    await wait(150);
    p.q("#li-paste-btn").click(); await wait(5);
    pasteRows(p, newLines(2).concat(["Test Other\thttps://www.linkedin.com/in/test-other\tTest Pasted Co"]));
    await wait(260);
    p.ctl("test-other", "delete").click(); await wait(2);
    p.ctl("test-other", "confirm").click(); await wait(5);
    assert.ok(p.q("#li-import").disabled);
    assert.equal(text(p.q("#li-import-wait")), "Saving a row… Import when it finishes");
    p.q("#li-import").disabled = false; p.q("#li-import").click();
    await wait(90);
    assert.deepEqual(newDocs(db), [], "the forced click started nothing");
    assert.ok(!db.rows().has("test-other"));
    // the preview now counts Test Other as a new row; importing it adds it back on purpose
    assert.equal(text(p.q("#li-import")), "Import 3 rows");
    p.q("#li-import").click();
    await wait(400);
    assert.equal(text(p.q("#li-paste-preview [role=status]")), "Imported 3");
    assert.deepEqual(tableIds(p), [...db.rows().keys()].sort());
    assert.deepEqual([db.rows().get("test-other").company, db.rows().get("test-other").stage], ["Test Pasted Co", "Connect sent"]);
    assert.deepEqual(p.errors, []);
  } finally { p.close(); }
});

uiTest("rows another tab changed or deleted, re-read by Refresh during an import, are not reverted by it", async () => {
  const db = fakeDb(seed(), { setDelay: 60 });
  const p = makePage({ caps: caps(db) });
  try {
    await wait(150);
    p.q("#li-paste-btn").click(); await wait(5);
    pasteRows(p, newLines(5).concat(["Test Other\thttps://www.linkedin.com/in/test-other\tTest Pasted Co"]));
    await wait(260);
    p.q("#li-import").click(); await wait(20);
    // another tab: logs a reply on test-replied (not pasted), saves test-other again (pasted), deletes r_testnourl001
    const later = (id, extra) => db.rows().set(id, Object.assign(clone(db.rows().get(id)), extra, { updatedAt: Date.now() }));
    later("test-replied", { stage: "Positive reply", reply_type: "positive" });
    later("test-other", { stage: "DM sent", loom_variant: "B" });
    db.rows().delete("r_testnourl001");
    p.q("#refresh-btn").click();
    await wait(900);
    assert.ok(!p.q("#li-importing"));
    assert.equal(text(p.q("#li-paste-preview [role=status]")), "Imported 5. 1 row changed after you pasted and was left as is.");
    assert.equal(stageOf(p)("test-replied"), "Positive reply", "the re-read row is not put back to its pre-import version");
    assert.deepEqual([db.rows().get("test-other").stage, db.rows().get("test-other").company], ["DM sent", ""]);
    assert.equal(stageOf(p)("test-other"), "DM sent");
    assert.ok(!p.row("r_testnourl001") && !db.rows().has("r_testnourl001"), "a row deleted elsewhere doesn't come back");
    assert.deepEqual(tableIds(p), [...db.rows().keys()].sort());
    assert.deepEqual(p.errors, []);
  } finally { p.close(); }
});

uiTest("Add person onto a doc another tab saved is refused; Edit onto one says the URL is taken; neither logs an error", async () => {
  const db = fakeDb(seed());
  const p = makePage({ caps: caps(db) });
  try {
    await wait(150);
    const stored = Object.assign({}, base, { name: "Test Elsewhere", profile_url: "https://www.linkedin.com/in/test-elsewhere", stage: "DM sent",
      dm_date: "2026-10-02", loom_variant: "B", last_touch_date: "2026-10-02", next_touch_due: "2026-10-04", updatedAt: 9 });
    db.rows().set("test-elsewhere", clone(stored));
    const writes = db.writes.length;

    p.q("#li-add").click(); await wait(5);
    p.type(p.q("form.li-card [name=name]"), "Test Elsewhere");
    p.type(p.q("form.li-card [name=profile_url]"), "https://www.linkedin.com/in/test-elsewhere");
    p.q("#lf-submit").click(); await wait(60);
    assert.equal(text(p.q("#lf-status")), "This person is already in the tracker. Press Refresh to see them.");
    assert.deepEqual(db.rows().get("test-elsewhere"), stored, "the stored stage and dates are untouched");
    assert.equal(db.writes.length, writes);
    assert.ok(!p.row("test-elsewhere"));
    p.q("form.li-card .btn--glass").click(); await wait(5);

    // Edit moving a row onto that URL: refused too
    p.ctl("test-other", "edit").click(); await wait(5);
    p.type(p.q("form.li-card [name=profile_url]"), "https://www.linkedin.com/in/test-elsewhere");
    p.q("#lf-submit").click(); await wait(60);
    assert.equal(text(p.q("#lf-status")), "Another row already has this profile URL.");
    assert.deepEqual(db.rows().get("test-elsewhere"), stored);
    assert.ok(db.rows().has("test-other"));
    assert.deepEqual(p.errors, [], "a refused duplicate is not an error");

    // Edit of a loaded row keeps merge semantics: only the edited field changes
    p.q("form.li-card .btn--glass").click(); await wait(5);
    p.ctl("test-other", "edit").click(); await wait(5);
    p.type(p.q("form.li-card [name=company]"), "Test Other Co");
    p.q("#lf-submit").click(); await wait(60);
    const o = db.rows().get("test-other");
    assert.deepEqual([o.company, o.stage, o.accepted_date], ["Test Other Co", "Accepted", "2026-10-01"]);
  } finally { p.close(); }
});
