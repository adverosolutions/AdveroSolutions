#!/usr/bin/env python3
"""Builds the five n8n workflows for the Bid and Follow-Up Automation System.

Run:  python3 build_workflows.py
Out:  n8n/*.json  sheets/*.csv
"""
import csv, json, os, uuid, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "n8n")
SHEETS = os.path.join(HERE, "sheets")
os.makedirs(OUT, exist_ok=True); os.makedirs(SHEETS, exist_ok=True)

BID_COLUMNS = ["bid_id","customer_name","first_name","phone","email","project","bid_amount",
               "date_sent","status","touch_index","next_touch_at","last_touch","last_touch_channel",
               "last_reply","last_reply_text","thread_id","opt_out","notes"]

CONFIG = [
    ("sheet_id",        "PASTE_GOOGLE_SHEET_ID_HERE"),
    ("business_name",   "Lawson Construction"),
    ("owner_name",      "Jennifer"),
    ("owner_phone",     "(555) 555-0100"),
    ("from_email",      "bids@yourbusiness.com"),
    ("team_email",      "jennifer@yourbusiness.com"),
    ("team_phone",      "+15555550100"),
    ("twilio_from",     "+15555550199"),
    ("timezone",        "America/Chicago"),
    ("no_response_grace_days", "3"),
]

# ---------------------------------------------------------------- helpers
def nid(): return str(uuid.uuid4())

def node(name, type_, version, params, pos, **extra):
    n = {"parameters": params, "id": nid(), "name": name, "type": type_,
         "typeVersion": version, "position": list(pos)}
    n.update(extra); return n

def sticky(text, pos, w=420, h=160, color=4):
    return node("Note " + str(uuid.uuid4())[:6], "n8n-nodes-base.stickyNote", 1,
                {"content": text, "width": w, "height": h, "color": color}, pos)

def config_node(pos):
    return node("Config", "n8n-nodes-base.set", 3.4, {
        "assignments": {"assignments": [
            {"id": nid(), "name": k, "value": v, "type": "string"} for k, v in CONFIG] + [
            {"id": nid(), "name": "lane", "value": "={{ $prevNode.name }}", "type": "string"}]},
        "includeOtherFields": True, "options": {}}, pos)

def sheet_ref(tab):
    return {"documentId": {"__rl": True, "mode": "id", "value": "={{ $('Config').first().json.sheet_id }}"},
            "sheetName": {"__rl": True, "mode": "name", "value": tab}}

def sheets_read(name, tab, pos, once=True):
    return node(name, "n8n-nodes-base.googleSheets", 4.5, {**sheet_ref(tab), "options": {}}, pos,
                executeOnce=once, alwaysOutputData=True)

def sheets_append(name, tab, pos):
    return node(name, "n8n-nodes-base.googleSheets", 4.5, {
        "operation": "append", **sheet_ref(tab),
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [],
                    "schema": [schema_col(c) for c in BID_COLUMNS]},
        "options": {"cellFormat": "RAW"}}, pos)

def schema_col(c, match=False):
    return {"id": c, "displayName": c, "required": False, "defaultMatch": match, "display": True,
            "type": "string", "canBeUsedToMatch": True, "removed": False}

def sheets_update(name, tab, fields, pos):
    """Update by row_number. `fields` = list of column names taken from $json."""
    value = {"row_number": "={{ $json.row_number }}"}
    value.update({f: "={{ $json.%s }}" % f for f in fields})
    schema = [schema_col("row_number", True)] + [schema_col(c) for c in BID_COLUMNS]
    return node(name, "n8n-nodes-base.googleSheets", 4.5, {
        "operation": "update", **sheet_ref(tab),
        "columns": {"mappingMode": "defineBelow", "value": value, "matchingColumns": ["row_number"], "schema": schema},
        "options": {"cellFormat": "RAW"}}, pos)

def gmail_send(name, to, subject, body, pos):
    return node(name, "n8n-nodes-base.gmail", 2.1, {
        "sendTo": to, "subject": subject, "emailType": "text", "message": body,
        "options": {"appendAttribution": False}}, pos)

def twilio_sms(name, to, body, pos):
    return node(name, "n8n-nodes-base.twilio", 1, {
        "resource": "sms", "operation": "send", "from": "={{ $('Config').first().json.twilio_from }}",
        "to": to, "toWhatsapp": False, "message": body, "options": {}}, pos)

def code(name, js, pos, each=False):
    p = {"jsCode": js}
    if each: p["mode"] = "runOnceForEachItem"
    return node(name, "n8n-nodes-base.code", 2, p, pos)

def if_node(name, left, right, pos, op="equals", typ="string"):
    return node(name, "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [{"id": nid(), "leftValue": left, "rightValue": right,
                                       "operator": {"type": typ, "operation": op}}],
                       "combinator": "and"}, "options": {}}, pos)

def switch_node(name, lanes, pos):
    """lanes = [(outputKey, [trigger node names]), ...] routed on $json.lane."""
    values = []
    for key, triggers in lanes:
        values.append({"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                      "conditions": [{"id": nid(), "leftValue": "={{ $json.lane }}", "rightValue": t,
                                                      "operator": {"type": "string", "operation": "equals"}} for t in triggers],
                                      "combinator": "or"},
                       "renameOutput": True, "outputKey": key})
    return node(name, "n8n-nodes-base.switch", 3.2, {"rules": {"values": values}, "options": {}}, pos)

def wire(conns, src, dst, out_index=0):
    conns.setdefault(src, {"main": []})
    while len(conns[src]["main"]) <= out_index: conns[src]["main"].append([])
    conns[src]["main"][out_index].append({"node": dst, "type": "main", "index": 0})

def workflow(name, nodes, conns):
    return {"name": name, "nodes": nodes, "connections": conns, "active": False,
            "settings": {"executionOrder": "v1", "timezone": "America/Chicago"}, "pinData": {}}

def save(fname, wf):
    path = os.path.join(OUT, fname)
    with open(path, "w") as f: json.dump(wf, f, indent=2)
    return path

# shared JS snippets ------------------------------------------------------
JS_DATE_HELPERS = r"""
const ACTIVE = ['Sent', 'Following Up'];
function parseDate(v) {
  if (v === undefined || v === null || v === '') return null;
  if (typeof v === 'number') return DateTime.fromMillis(Math.round((v - 25569) * 86400000), { zone: 'utc' }).setZone(ZONE);
  const s = String(v).trim();
  let d = DateTime.fromISO(s, { zone: ZONE });
  for (const f of ['M/d/yyyy', 'M/d/yyyy H:mm:ss', 'M/d/yyyy H:mm', 'yyyy-MM-dd H:mm:ss', 'yyyy-MM-dd H:mm']) {
    if (d.isValid) break;
    d = DateTime.fromFormat(s, f, { zone: ZONE });
  }
  if (!d.isValid) { const js = new Date(s); d = isNaN(js.getTime()) ? null : DateTime.fromJSDate(js).setZone(ZONE); }
  return d && d.isValid ? d : null;
}
function digits(s) { return String(s || '').replace(/\D/g, ''); }
function e164(s) { const d = digits(s); if (d.length === 10) return '+1' + d; if (d.length === 11 && d[0] === '1') return '+' + d; return d ? '+' + d : ''; }
function money(v) { if (v === undefined || v === null || v === '') return ''; const n = Number(String(v).replace(/[^0-9.]/g, '')); return isNaN(n) ? String(v) : '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 }); }
"""

# ======================================================================
# 01  BID INTAKE
# ======================================================================
def lane_intake(nodes, conns, Y):
    nodes.append(sticky("## 1. Bid intake\nA new bid from the website form hits this webhook (POST). It is normalized, given a bid_id, and logged in the **Bids** tab with status **Sent**. The scheduler picks it up from there.\n\nWebhook URL: `https://YOUR-N8N/webhook/new-bid`\n\nYou can also add a row by hand in the sheet with status Sent and a date_sent. The scheduler handles it the same way.", (-460, -260), 560, 220))
    nodes.append(sticky("## Optional: start from the form's notification email\nIf the form cannot call a webhook, enable this Gmail trigger and it will parse the notification email instead. Adjust the subject filter in the trigger and the field names in **Parse Notification Email** to match the form.", (-460, 260), 560, 160, 5))

    nodes.append(node("New Bid (Website Form)", "n8n-nodes-base.webhook", 2.1,
        {"httpMethod": "POST", "path": "new-bid", "responseMode": "responseNode", "options": {}},
        (0, 0), webhookId=nid()))
    nodes.append(node("Form Notification Email", "n8n-nodes-base.gmailTrigger", 1.2,
        {"pollTimes": {"item": [{"mode": "everyMinute"}]}, "simple": False,
         "filters": {"q": "subject:(new bid OR new estimate OR estimate request)"}, "options": {}},
        (0, 460), disabled=True))
    nodes.append(code("Parse Notification Email", r"""
// Turns a plain-text form notification ("Name: Jane Doe" lines) into a form-style payload.
const m = $input.first().json;
const text = String(m.text || m.snippet || '');
const body = {};
for (const line of text.split(/\r?\n/)) {
  const mm = line.match(/^\s*([A-Za-z][A-Za-z0-9 _-]{1,40})\s*[:=]\s*(.+)$/);
  if (mm) body[mm[1].trim().toLowerCase().replace(/\s+/g, '_')] = mm[2].trim();
}
return [{ json: { body } }];
""", (240, 460)))
    nodes.append(code("Normalize Bid", JS_DATE_HELPERS + r"""
const cfg = $('Config').first().json;
const ZONE = cfg.timezone || 'America/Chicago';
const j = $input.first().json;
const src = (j.body && typeof j.body === 'object' && Object.keys(j.body).length) ? j.body : j;
const norm = k => String(k).toLowerCase().replace(/[^a-z0-9]/g, '');
const pick = (...keys) => {
  for (const k of keys) {
    const hit = Object.keys(src).find(x => norm(x) === k);
    if (hit && src[hit] !== null && src[hit] !== undefined && String(src[hit]).trim() !== '') return String(src[hit]).trim();
  }
  return '';
};
const name = pick('customername', 'fullname', 'name', 'contactname', 'customer') || [pick('firstname', 'first'), pick('lastname', 'last')].join(' ').trim();
const first = pick('firstname', 'first') || name.split(/\s+/)[0] || '';
const now = DateTime.now().setZone(ZONE);
const bid_id = 'BID-' + now.toFormat('yyyyLLdd') + '-' + Math.random().toString(36).slice(2, 6).toUpperCase();
return [{ json: {
  bid_id,
  customer_name: name,
  first_name: first,
  phone: e164(pick('phone', 'phonenumber', 'tel', 'telephone', 'mobile', 'cell', 'cellphone')),
  email: pick('email', 'emailaddress', 'customeremail').toLowerCase(),
  project: pick('project', 'projecttype', 'service', 'jobtype', 'job', 'scope', 'description', 'message'),
  bid_amount: pick('bidamount', 'amount', 'estimate', 'estimateamount', 'total', 'price', 'quote'),
  date_sent: (parseDate(pick('datesent', 'date', 'sentdate')) || now).toISO(),
  status: 'Sent',
  touch_index: 0,
  next_touch_at: '',
  last_touch: '',
  last_touch_channel: '',
  last_reply: '',
  last_reply_text: '',
  thread_id: '',
  opt_out: '',
  notes: pick('notes', 'comments'),
}}];
""", (480, 0)))
    nodes.append(sheets_append("Log Bid in Tracker", "Bids", (720, 0)))
    nodes.append(node("Respond OK", "n8n-nodes-base.respondToWebhook", 1.1,
        {"respondWith": "json", "responseBody": "={{ JSON.stringify({ ok: true, bid_id: $('Normalize Bid').first().json.bid_id }) }}", "options": {}},
        (960, 0)))
    wire(conns, "New Bid (Website Form)", "Config")
    wire(conns, "Form Notification Email", "Parse Notification Email")
    wire(conns, "Parse Notification Email", "Config")
    wire(conns, "Normalize Bid", "Log Bid in Tracker")
    wire(conns, "Log Bid in Tracker", "Respond OK")

# ======================================================================
# 02  FOLLOW-UP SCHEDULER
# ======================================================================
def lane_scheduler(nodes, conns, Y):
    nodes.append(sticky("## 2. Follow-up scheduler\nRuns every hour, 9am to 5pm Central, Monday to Friday. For every bid with status **Sent** or **Following Up** it checks whether the next touch is due, sends it (email via Gmail, text via Twilio), and moves the bid forward.\n\nThe cadence lives in the **Templates** tab (day + channel + copy). Change days or wording there. Nothing here needs editing.\n\nStopping a bid: any reply, a STOP, or setting the status to Booked / Declined / anything other than Sent or Following Up.", (-460, -300), 620, 260))
    nodes.append(sticky("## Why one touch per bid per run\nIf a bid was entered late and several touches are already overdue, it still gets at most one touch per hour and never two on the same day. The next touch is always at least the next business morning.", (1200, -300), 460, 160, 5))

    nodes.append(node("Every hour, business hours CT", "n8n-nodes-base.scheduleTrigger", 1.2,
        {"rule": {"interval": [{"field": "cronExpression", "expression": "0 9-17 * * 1-5"}]}}, (0, 0)))
    nodes.append(sheets_read("Read Bids (scheduler)", "Bids", (480, 0)))
    nodes.append(sheets_read("Read Templates (scheduler)", "Templates", (720, 0)))
    nodes.append(code("Build Due Touches", JS_DATE_HELPERS + r"""
const cfg = $('Config').first().json;
const ZONE = cfg.timezone || 'America/Chicago';
const GRACE_DAYS = Number(cfg.no_response_grace_days || 3);
const now = DateTime.now().setZone(ZONE);

const templates = $('__READ_TEMPLATES__').all().map(i => i.json)
  .filter(t => t.step !== undefined && String(t.step).trim() !== '' && String(t.enabled === undefined ? 'TRUE' : t.enabled).toUpperCase() !== 'FALSE')
  .map(t => ({ ...t, step: Number(t.step), day: Number(t.day), channel: String(t.channel || '').trim().toLowerCase() }))
  .sort((a, b) => a.day - b.day || a.step - b.step);

function dueFor(sentAt, day) { return sentAt.startOf('day').plus({ days: day }).set({ hour: 9, minute: 0, second: 0, millisecond: 0 }); }
function render(text, vars) { return String(text || '').replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, k) => (vars[k] === undefined ? '' : vars[k])); }

const out = [];
for (const item of $('__READ_BIDS__').all()) {
  const r = item.json;
  if (!r || r.row_number === undefined) continue;
  const status = String(r.status || '').trim();
  if (!ACTIVE.includes(status)) continue;
  if (String(r.opt_out || '').toUpperCase() === 'TRUE') continue;
  const sentAt = parseDate(r.date_sent);
  if (!sentAt) continue;
  const idx = Number(r.touch_index || 0);
  const lastTouch = parseDate(r.last_touch);
  const base = {
    row_number: r.row_number, bid_id: r.bid_id || '', customer_name: r.customer_name || '',
    email: String(r.email || '').trim(), phone: r.phone || '', project: r.project || '', bid_amount: r.bid_amount || '',
    thread_id: r.thread_id || '', status, touch_index: idx, next_touch_at: r.next_touch_at || '',
    last_touch: r.last_touch || '', last_touch_channel: r.last_touch_channel || '',
  };

  // Sequence finished: after the grace period with no reply, close it out.
  if (idx >= templates.length) {
    const anchor = lastTouch || sentAt;
    if (now.diff(anchor, 'days').days >= GRACE_DAYS) out.push({ json: { ...base, action: 'no_response', status: 'No Response', next_touch_at: '' } });
    continue;
  }

  const step = templates[idx];
  const stored = parseDate(r.next_touch_at);
  const due = stored || dueFor(sentAt, step.day);
  if (due > now) continue;

  const nextStep = templates[idx + 1];
  let nextAt = '';
  if (nextStep) {
    const scheduled = dueFor(sentAt, nextStep.day);
    const floor = now.plus({ days: 1 }).set({ hour: 9, minute: 0, second: 0, millisecond: 0 });
    nextAt = (scheduled > floor ? scheduled : floor).toISO();
  }
  const after = { ...base, status: 'Following Up', touch_index: idx + 1, next_touch_at: nextAt, last_touch: now.toISO(), last_touch_channel: step.channel };

  const hasTarget = step.channel === 'sms' ? digits(r.phone).length >= 10 : base.email.includes('@');
  if (!hasTarget) { out.push({ json: { ...after, action: 'skip', last_touch: base.last_touch, last_touch_channel: base.last_touch_channel } }); continue; }

  const vars = {
    first_name: (r.first_name || base.customer_name.split(/\s+/)[0] || 'there'),
    customer_name: base.customer_name, project: base.project || 'project', bid_amount: money(base.bid_amount),
    business_name: cfg.business_name || '', owner_name: cfg.owner_name || '', owner_phone: cfg.owner_phone || '',
  };
  out.push({ json: { ...after, action: 'send', channel: step.channel, step: step.step,
    subject: render(step.subject, vars), body: render(step.body, vars),
    to_email: base.email, to_phone: e164(r.phone) } });
}
return out;
""", (960, 0)))
    nodes.append(if_node("Send something?", "={{ $json.action }}", "send", (1200, 0)))
    nodes.append(if_node("Email or text?", "={{ $json.channel }}", "email", (1440, -120)))
    nodes.append(gmail_send("Send Follow-Up Email", "={{ $json.to_email }}", "={{ $json.subject }}", "={{ $json.body }}", (1680, -240)))
    nodes.append(twilio_sms("Send Follow-Up Text", "={{ $json.to_phone }}", "={{ $json.body }}", (1680, 0)))
    nodes.append(code("After Email", r"""
const base = $('Build Due Touches').item.json;
return { json: { ...base, thread_id: $json.threadId || base.thread_id || '' } };
""", (1920, -240), each=True))
    nodes.append(code("After Text", r"""
const base = $('Build Due Touches').item.json;
return { json: { ...base } };
""", (1920, 0), each=True))
    nodes.append(sheets_update("Update Bid Row", "Bids",
        ["status", "touch_index", "next_touch_at", "last_touch", "last_touch_channel", "thread_id"], (2200, 0)))

    wire(conns, "Every hour, business hours CT", "Config")
    wire(conns, "Read Bids (scheduler)", "Read Templates (scheduler)")
    wire(conns, "Read Templates (scheduler)", "Build Due Touches")
    wire(conns, "Build Due Touches", "Send something?")
    wire(conns, "Send something?", "Email or text?", 0)
    wire(conns, "Send something?", "Update Bid Row", 1)
    wire(conns, "Email or text?", "Send Follow-Up Email", 0)
    wire(conns, "Email or text?", "Send Follow-Up Text", 1)
    wire(conns, "Send Follow-Up Email", "After Email")
    wire(conns, "Send Follow-Up Text", "After Text")
    wire(conns, "After Email", "Update Bid Row")
    wire(conns, "After Text", "Update Bid Row")

# ======================================================================
# 03  INBOUND TEXT (Twilio webhook)
# ======================================================================
def lane_inbound_sms(nodes, conns, Y):
    nodes.append(sticky("## 3. Customer texts back\nTwilio posts every inbound text here. Point the Twilio number's **Messaging > A message comes in** webhook at:\n`https://YOUR-N8N/webhook/twilio-inbound` (HTTP POST)\n\nThe bid is matched by phone number, marked **Replied** (or **Opted Out** on STOP), all remaining touches stop, and the team is alerted by text and email.\n\nTwilio also enforces STOP on its side, so the number is blocked even if this workflow is paused.", (-460, -300), 620, 240))

    nodes.append(node("Twilio Inbound SMS", "n8n-nodes-base.webhook", 2.1,
        {"httpMethod": "POST", "path": "twilio-inbound", "responseMode": "responseNode", "options": {}},
        (0, 0), webhookId=nid()))
    nodes.append(node("Respond to Twilio", "n8n-nodes-base.respondToWebhook", 1.1,
        {"respondWith": "text", "responseBody": "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
         "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/xml"}]}}}, (240, 0)))
    nodes.append(sheets_read("Read Bids (text reply)", "Bids", (720, 0)))
    nodes.append(code("Match Reply to Bid", JS_DATE_HELPERS + r"""
const cfg = $('Config').first().json;
const ZONE = cfg.timezone || 'America/Chicago';
const hook = $('Twilio Inbound SMS').first().json;
const p = hook.body || {};
const from = String(p.From || '');
const text = String(p.Body || '').trim();
const isStop = /^\s*(stop|stopall|unsubscribe|cancel|end|quit)\b/i.test(text);
const key = digits(from).slice(-10);
const rows = $('__READ_BIDS__').all().map(i => i.json).filter(r => r && r.row_number !== undefined && key && digits(r.phone).slice(-10) === key);
const row = rows.filter(r => ACTIVE.includes(String(r.status || '').trim())).pop() || rows.pop() || null;
const now = DateTime.now().setZone(ZONE);

const name = row ? (row.customer_name || from) : from;
const bid = row ? `${row.project || 'bid'}${row.bid_amount ? ' (' + money(row.bid_amount) + ')' : ''}` : 'no bid on file for this number';
const wasActive = row ? ACTIVE.includes(String(row.status || '').trim()) : false;
const status = row ? (isStop ? 'Opted Out' : (wasActive ? 'Replied' : String(row.status).trim())) : '';

let alert_sms, alert_subject, alert_body;
if (isStop) {
  alert_sms = `${name} replied STOP. All follow-ups stopped for ${bid}.`;
  alert_subject = `Opt-out: ${name} (${bid})`;
  alert_body = `${name} (${from}) replied STOP.\n\nBid: ${bid}\n\nTexting and emailing for this bid has been stopped and the tracker is marked Opted Out.`;
} else {
  const snippet = text.length > 200 ? text.slice(0, 197) + '...' : text;
  alert_sms = `Reply from ${name} on ${bid}: "${snippet}" - text them back at ${from}`;
  alert_subject = `Reply from ${name}: ${bid}`;
  alert_body = `${name} (${from}) just replied by text.\n\nBid: ${bid}\n\nMessage:\n${text}\n\nFollow-ups for this bid are paused. Reply to them directly at ${from}.` + (row ? `\n\nTracker row: ${row.row_number}${row.bid_id ? ' / ' + row.bid_id : ''}` : '');
}
return [{ json: {
  matched: !!row, is_stop: isStop,
  row_number: row ? row.row_number : '',
  status,
  opt_out: isStop ? 'TRUE' : (row ? (row.opt_out || '') : ''),
  next_touch_at: '',
  last_reply: now.toISO(),
  last_reply_text: text,
  from, alert_sms, alert_subject, alert_body,
}}];
""", (960, 0)))
    nodes.append(if_node("Bid found?", "={{ $json.matched }}", "true", (1200, 0), op="true", typ="boolean"))
    # boolean IF: leftValue boolean, operation "true", no rightValue
    nodes[-1]["parameters"]["conditions"]["conditions"][0].pop("rightValue")
    nodes.append(sheets_update("Mark Replied / Opted Out", "Bids",
        ["status", "opt_out", "next_touch_at", "last_reply", "last_reply_text"], (1440, -120)))
    nodes.append(twilio_sms("Text the Team (text reply)", "={{ $('Config').first().json.team_phone }}", "={{ $('Match Reply to Bid').item.json.alert_sms }}", (1680, 0)))
    nodes.append(gmail_send("Email the Team (text reply)", "={{ $('Config').first().json.team_email }}",
        "={{ $('Match Reply to Bid').item.json.alert_subject }}", "={{ $('Match Reply to Bid').item.json.alert_body }}", (1920, 0)))

    wire(conns, "Twilio Inbound SMS", "Respond to Twilio")
    wire(conns, "Respond to Twilio", "Config")
    wire(conns, "Read Bids (text reply)", "Match Reply to Bid")
    wire(conns, "Match Reply to Bid", "Bid found?")
    wire(conns, "Bid found?", "Mark Replied / Opted Out", 0)
    wire(conns, "Bid found?", "Text the Team (text reply)", 1)
    wire(conns, "Mark Replied / Opted Out", "Text the Team (text reply)")
    wire(conns, "Text the Team (text reply)", "Email the Team (text reply)")

# ======================================================================
# 04  INBOUND EMAIL REPLY
# ======================================================================
def lane_inbound_email(nodes, conns, Y):
    nodes.append(sticky("## 4. Customer emails back\nWatches the sending inbox every minute. A new email is matched to a bid by Gmail thread first, then by the sender's address. Matches are marked **Replied**, remaining touches stop, and the team is alerted by text and email. Unrelated inbox mail is ignored.", (-460, -260), 620, 180))

    nodes.append(node("Reply Lands in Inbox", "n8n-nodes-base.gmailTrigger", 1.2,
        {"pollTimes": {"item": [{"mode": "everyMinute"}]}, "simple": False, "filters": {}, "options": {}}, (0, 0)))
    nodes.append(sheets_read("Read Bids (email reply)", "Bids", (480, 0)))
    nodes.append(code("Match Email to Bid", JS_DATE_HELPERS + r"""
const cfg = $('Config').first().json;
const ZONE = cfg.timezone || 'America/Chicago';
const out = [];
for (const m of $('Reply Lands in Inbox').all().map(i => i.json)) {
const fromAddr = ((m.from && m.from.value && m.from.value[0] && m.from.value[0].address)
  || (String(m.From || m.from || '').match(/[\w.+-]+@[\w.-]+/) || [''])[0]).toLowerCase();
const self = String(cfg.from_email || '').toLowerCase();
if (!fromAddr || fromAddr === self || /no-?reply|mailer-daemon|postmaster|notifications?@|calendar-notification/.test(fromAddr)) continue;

const threadId = String(m.threadId || '');
const rows = $('__READ_BIDS__').all().map(i => i.json).filter(r => r && r.row_number !== undefined);
const pick = list => list.filter(r => ACTIVE.includes(String(r.status || '').trim())).pop() || list.pop() || null;
const row = pick(rows.filter(r => threadId && String(r.thread_id || '') === threadId))
  || pick(rows.filter(r => String(r.email || '').trim().toLowerCase() === fromAddr));
if (!row) continue;

const raw = String(m.text || m.snippet || '');
const text = raw.split(/\r?\n\s*(On .{5,120} wrote:|From: |-----Original Message-----)/)[0].trim().slice(0, 1500);
const now = DateTime.now().setZone(ZONE);
const name = row.customer_name || fromAddr;
const bid = `${row.project || 'bid'}${row.bid_amount ? ' (' + money(row.bid_amount) + ')' : ''}`;
const wasActive = ACTIVE.includes(String(row.status || '').trim());
const snippet = text.length > 200 ? text.slice(0, 197) + '...' : text;
out.push({ json: {
  row_number: row.row_number,
  status: wasActive ? 'Replied' : String(row.status).trim(),
  next_touch_at: '',
  last_reply: now.toISO(),
  last_reply_text: text,
  alert_sms: `Email reply from ${name} on ${bid}: "${snippet}" - reply from ${self}`,
  alert_subject: `Reply from ${name}: ${bid}`,
  alert_body: `${name} (${fromAddr}) just replied by email.\n\nBid: ${bid}\nSubject: ${m.subject || ''}\n\nMessage:\n${text}\n\nFollow-ups for this bid are paused. Reply to them from the ${self} inbox.\n\nTracker row: ${row.row_number}${row.bid_id ? ' / ' + row.bid_id : ''}`,
}});
}
return out;
""", (720, 0)))
    nodes.append(sheets_update("Mark Replied", "Bids", ["status", "next_touch_at", "last_reply", "last_reply_text"], (960, 0)))
    nodes.append(twilio_sms("Text the Team (email reply)", "={{ $('Config').first().json.team_phone }}", "={{ $('Match Email to Bid').item.json.alert_sms }}", (1200, 0)))
    nodes.append(gmail_send("Email the Team (email reply)", "={{ $('Config').first().json.team_email }}",
        "={{ $('Match Email to Bid').item.json.alert_subject }}", "={{ $('Match Email to Bid').item.json.alert_body }}", (1440, 0)))

    wire(conns, "Reply Lands in Inbox", "Config")
    wire(conns, "Read Bids (email reply)", "Match Email to Bid")
    wire(conns, "Match Email to Bid", "Mark Replied")
    wire(conns, "Mark Replied", "Text the Team (email reply)")
    wire(conns, "Text the Team (email reply)", "Email the Team (email reply)")

# ======================================================================
# 05  DAILY SUMMARY
# ======================================================================
def lane_daily_summary(nodes, conns, Y):
    nodes.append(sticky("## 5. Daily summary\nEvery morning at 8am Central: which bids are still in follow-up, what goes out today, and every reply from the last 24 hours. Sent to the team email in the Config node.", (-460, -220), 560, 140))
    nodes.append(node("Every day 8am CT", "n8n-nodes-base.scheduleTrigger", 1.2,
        {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}}, (0, 0)))
    nodes.append(sheets_read("Read Bids (summary)", "Bids", (480, 0)))
    nodes.append(sheets_read("Read Templates (summary)", "Templates", (720, 0)))
    nodes.append(code("Build Summary", JS_DATE_HELPERS + r"""
const cfg = $('Config').first().json;
const ZONE = cfg.timezone || 'America/Chicago';
const now = DateTime.now().setZone(ZONE);
const dayAgo = now.minus({ hours: 24 });
const rows = $('__READ_BIDS__').all().map(i => i.json).filter(r => r && r.row_number !== undefined && String(r.status || '').trim() !== '');
const templates = $('__READ_TEMPLATES__').all().map(i => i.json)
  .filter(t => t.step !== undefined && String(t.step).trim() !== '' && String(t.enabled === undefined ? 'TRUE' : t.enabled).toUpperCase() !== 'FALSE')
  .map(t => ({ day: Number(t.day), channel: String(t.channel || '').trim().toLowerCase() })).sort((a, b) => a.day - b.day);
function nextTouch(r) {
  const idx = Number(r.touch_index || 0);
  if (idx >= templates.length) return 'sequence complete, closing out soon';
  const sent = parseDate(r.date_sent);
  const stored = parseDate(r.next_touch_at);
  const due = stored || (sent ? sent.startOf('day').plus({ days: templates[idx].day }).set({ hour: 9 }) : now);
  return (due <= now ? 'today' : fmt(due)) + ' (' + templates[idx].channel + ')';
}

const counts = {};
for (const r of rows) { const s = String(r.status).trim(); counts[s] = (counts[s] || 0) + 1; }
const active = rows.filter(r => ACTIVE.includes(String(r.status).trim()));
const replies = rows.filter(r => { const d = parseDate(r.last_reply); return d && d >= dayAgo; });
const fmt = d => d ? d.toFormat('ccc M/d h:mm a') : '';
const line = r => `- ${r.customer_name || '(no name)'} | ${r.project || 'bid'} | ${money(r.bid_amount)}`;

const lines = [];
lines.push(`Bid follow-up summary for ${now.toFormat('cccc, LLLL d')}`, '');
lines.push(`Totals: ` + Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(' | '), '');
lines.push(`REPLIES IN THE LAST 24 HOURS (${replies.length})`);
if (!replies.length) lines.push('- none');
for (const r of replies) lines.push(line(r) + ` | ${fmt(parseDate(r.last_reply))}` + (r.last_reply_text ? `\n    "${String(r.last_reply_text).slice(0, 160)}"` : ''));
lines.push('', `STILL IN FOLLOW-UP (${active.length})`);
if (!active.length) lines.push('- none');
for (const r of active.sort((a, b) => (parseDate(a.next_touch_at) || now).toMillis() - (parseDate(b.next_touch_at) || now).toMillis())) {
  const sent = parseDate(r.date_sent);
  lines.push(line(r) + ` | sent ${sent ? sent.toFormat('M/d') : '?'} | touches so far ${Number(r.touch_index || 0)} | next ${nextTouch(r)}`);
}
lines.push('', 'Open the tracker to mark any bid Booked or Declined. That stops its follow-ups immediately.');
return [{ json: { subject: `Bid follow-up: ${replies.length} repl${replies.length === 1 ? 'y' : 'ies'}, ${active.length} in progress`, body: lines.join('\n') } }];
""", (960, 0)))
    nodes.append(gmail_send("Email Daily Summary", "={{ $('Config').first().json.team_email }}", "={{ $json.subject }}", "={{ $json.body }}", (1200, 0)))
    wire(conns, "Every day 8am CT", "Config")
    wire(conns, "Read Bids (summary)", "Read Templates (summary)")
    wire(conns, "Read Templates (summary)", "Build Summary")
    wire(conns, "Build Summary", "Email Daily Summary")

# ======================================================================
# Sheets seeds
# ======================================================================
TEMPLATES = [
  (1, 1, "email", "Your {{project}} estimate from {{business_name}}",
   "Hi {{first_name}},\n\nThanks again for having us out. Your estimate for the {{project}} came to {{bid_amount}}.\n\nIf anything in it needs a second look, or you'd like me to walk you through it, just reply here or call me at {{owner_phone}}.\n\n{{owner_name}}\n{{business_name}}"),
  (2, 2, "sms", "",
   "Hi {{first_name}}, {{owner_name}} with {{business_name}}. Just making sure the {{project}} estimate reached you. Any questions? Reply STOP to opt out."),
  (3, 3, "email", "Quick question on the {{project}}",
   "Hi {{first_name}},\n\nWanted to check in on the {{project}} estimate. If anything needs adjusting, whether that's scope, timing, or budget, tell me and I'll rework it.\n\nIf you're ready to go, reply here and we'll get you on the schedule.\n\n{{owner_name}}\n{{business_name}}"),
  (4, 5, "sms", "",
   "Hi {{first_name}}, our schedule for the next few weeks is filling up. If you'd like to lock in a start date for the {{project}}, just reply here. - {{owner_name}}"),
  (5, 7, "email", "Still thinking it over?",
   "Hi {{first_name}},\n\nIt's been a week since I sent over the {{project}} estimate, so I wanted to reach out one more time. Totally understand if you're comparing bids or the timing isn't right.\n\nIf it helps, I'm glad to answer anything about materials, timeline, or the price. Just reply and let me know where things stand.\n\n{{owner_name}}\n{{business_name}}"),
  (6, 9, "sms", "",
   "Hi {{first_name}}, {{owner_name}} here. Did you decide on the {{project}}? A quick yes, no, or not yet is all I need. Thanks!"),
  (7, 12, "sms", "",
   "Hi {{first_name}}, last text from me on the {{project}} estimate. If you'd like to move forward or have it updated, reply anytime. - {{owner_name}}, {{business_name}}"),
  (8, 14, "email", "Closing the file on your {{project}} estimate",
   "Hi {{first_name}},\n\nI'll assume the timing didn't work out on the {{project}} and close out the estimate on my end. If anything changes, the price of {{bid_amount}} stays good for 30 days from today. Just reply to this email.\n\nThanks for considering {{business_name}}.\n\n{{owner_name}}"),
]

def write_sheets():
    with open(os.path.join(SHEETS, "Bids.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(BID_COLUMNS)
    with open(os.path.join(SHEETS, "Templates.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["step", "day", "channel", "subject", "body", "enabled"])
        for step, day, ch, subj, body in TEMPLATES: w.writerow([step, day, ch, subj, body, "TRUE"])

# ======================================================================
# Validate
# ======================================================================
def validate(wf):
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names in " + wf["name"]
    for src, outs in wf["connections"].items():
        assert src in names, f"{wf['name']}: connection from unknown node {src}"
        for branch in outs["main"]:
            for c in branch: assert c["node"] in names, f"{wf['name']}: connection to unknown node {c['node']}"
    # every Code node must be valid JS (wrapped as an async fn body, as n8n runs it)
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.code":
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as t:
                t.write("const DateTime={}, $=()=>({first(){},all(){return []},item:{}}), $input={first(){},all(){return []}}, $json={};\n(async () => {\n" + n["parameters"]["jsCode"] + "\n})();")
            r = subprocess.run(["node", "--check", t.name], capture_output=True, text=True)
            os.unlink(t.name)
            assert r.returncode == 0, f"{wf['name']} / {n['name']}: JS syntax error\n{r.stderr}"
    # $('Name') references must point to real nodes in the same workflow
    import re
    for n in wf["nodes"]:
        for ref in re.findall(r"\$\('([^']+)'\)", json.dumps(n["parameters"])):
            assert ref in names, f"{wf['name']} / {n['name']}: references missing node '{ref}'"

LANES = [  # (lane builder, switch output key, trigger node names, y offset, lane-specific node refs)
    (lane_intake,        "intake",     ["New Bid (Website Form)", "Parse Notification Email"], 0,    "Normalize Bid",     {}),
    (lane_scheduler,     "scheduler",  ["Every hour, business hours CT"],                       500,  "Read Bids (scheduler)",  {"__READ_BIDS__": "Read Bids (scheduler)", "__READ_TEMPLATES__": "Read Templates (scheduler)"}),
    (lane_inbound_sms,   "text_reply", ["Respond to Twilio"],                                    1000, "Read Bids (text reply)", {"__READ_BIDS__": "Read Bids (text reply)"}),
    (lane_inbound_email, "email_reply",["Reply Lands in Inbox"],                                 1500, "Read Bids (email reply)",{"__READ_BIDS__": "Read Bids (email reply)"}),
    (lane_daily_summary, "summary",    ["Every day 8am CT"],                                     2000, "Read Bids (summary)",    {"__READ_BIDS__": "Read Bids (summary)", "__READ_TEMPLATES__": "Read Templates (summary)"}),
]
X_LANE = 1120   # lane nodes start here; triggers at x=0, Config and Switch in between

def build_all():
    nodes, conns = [], {}
    nodes.append(sticky("# Bid and Follow-Up Automation System\nOne workflow, five lanes. Every trigger on the left runs through the single **Config** node (edit your details there once) and the **Which lane?** switch sends it to the right lane.\n\nThe Google Sheet is the source of truth: **Bids** is the tracker, **Templates** holds the copy and cadence. Edit those in the sheet, not here.\n\nStop any customer's follow-ups by setting their status to anything other than Sent / Following Up.", (0, -420), 1000, 240, 6))
    nodes.append(config_node((560, 1000)))
    nodes.append(switch_node("Which lane?", [(key, trig) for _, key, trig, _, _, _ in LANES], (820, 1000)))
    wire(conns, "Config", "Which lane?")
    for i, (builder, key, triggers, y, first_node, refs) in enumerate(LANES):
        lane_nodes, lane_conns = [], {}
        builder(lane_nodes, lane_conns, y)
        for n in lane_nodes:
            is_trigger_side = n["name"] in triggers or n["type"].endswith(("webhook", "gmailTrigger", "scheduleTrigger")) or n["name"] in ("Parse Notification Email", "Respond to Twilio")
            n["position"][1] += y
            if n["type"] == "n8n-nodes-base.stickyNote":
                n["position"][0] += X_LANE + 460
            elif not is_trigger_side:
                n["position"][0] += X_LANE
            if n["type"] == "n8n-nodes-base.code":
                for k, v in refs.items(): n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(k, v)
        nodes.extend(lane_nodes)
        for src, outs in lane_conns.items():
            for oi, branch in enumerate(outs["main"]):
                for c in branch: wire(conns, src, c["node"], oi)
        wire(conns, "Which lane?", first_node, i)
    return workflow("Bid Follow-Up System", nodes, conns)

if __name__ == "__main__":
    write_sheets()
    import glob
    for old in glob.glob(os.path.join(OUT, "0*-*.json")): os.remove(old)
    wf = build_all(); validate(wf); save("bid-follow-up-system.json", wf)
    print(f"ok  bid-follow-up-system.json  {len(wf['nodes'])} nodes, {sum(len(b) for o in wf['connections'].values() for b in o['main'])} connections")
