#!/usr/bin/env python3
"""Flag STALLED leads for Appointment Setter (Revenue Operations).

Definition v2 (COO decision 2026-10-21 11:09 CT, reversible):
STALLED = a lead/client who ENGAGED, then went quiet 7+ days on EVERY channel.
Engagement signals:
  - a non-opt-out human reply (handled.jsonl label not ooo/auto/machine and not
    unsubscribe/negative_*; or Instantly lt_interest_status > 0),
  - a case file / offered times / sent reply / booking for the lead (cases/*.json,
    offered_times.jsonl, sent_log.jsonl),
  - an Upwork conversation (room in upwork_threads.json, except Blocked/Excluded contract),
  - LinkedIn accept + message (tracker: accepted set AND reply or video_sent set).
Not stalled:
  - opt-outs/unsubscribes and cold no's (handled unsubscribe/negative_*, Instantly status -2,
    lt_interest_status < 0, cases named optout/unsubscribe/notfit/annoyed): they go to the
    Reactivation cooldown via the CRM sync.
  - OOO/auto-replies are not engagement.
  - Instantly reply with no handled.jsonl record and no interest status = "unclassified reply":
    not flagged, counted (needs a human classification first).
Silence: last touch (ours or theirs) on every engaged/touched channel is 7+ days old (CT).
Exclusions: CRM Reactivation tab (cache state/stalled/crm_reactivation_tab.csv, fail closed if
missing or >36h), Lead Pool Reactivation mirror, do_not_reload.csv, already in queue.csv.
client_lost (fix 2026-10-23, COO ask after the Adrilani Shaw re-flag): skip any engaged lead whose
client record says Lost: client file Summary "Status: Lost..." or latest Log "Stage: Lost" (matched via
INDEX.csv on email, domain, company, Upwork client, LinkedIn URL or name; fallback <domain>.md /
<key>.md), Upwork thread stage "Lost", or a queue.csv row with status=lost.
September routing (Lorenzo 2026-10-23 11:00 CT via COO: "Tiffany needs to be moved to a nurture sequence
sep leads are now updated and have had no follow ups we are prioritizing October and newer"):
  - First-email date per would-be-flagged email lead: earliest outbound email (ue_type 1 campaign / 3 manual)
    from Instantly GET /emails?lead=<email> (read-only). Fallbacks from the leads/list records: a
    timestamp_last_contact before 2026-10-01 proves pre-October; all records created on/after 2026-10-01
    proves October+. Otherwise the date is unknown (reported in first_email_unknown, still flagged).
  - First emailed before 2026-10-01 (September 2026): NOT a stalled hold card. Real runs write the queue row
    with status=nurture (local status only; nothing moved in Instantly/GHL/sheets), counted as
    excluded.routed_nurture_sep.
  - Existing queue rows with status=nurture (or lost) are never re-flagged or rewritten (already_nurture).
  - Flagged rows are ordered: first emailed October 2026+ newest-first, then unknown-date email leads, then
    leads with no email channel (Upwork/LinkedIn only). Queue appends follow that order.

Also computes the "sequence complete, no reply" POOL (count only): Instantly leads whose every
delivered record is status 3 (all steps complete), last step 7+ days ago (--complete-grace-days,
default 7), never replied (OOO/auto only counts as never replied), no other engagement.
Written to state/stalled/sequence_complete_pool_latest.json on real runs. No per-lead files.

Modes: (default) real run; --dry-run (no writes except run log; add --no-runlog for zero writes); --pool-only (count only, prints
JSON, writes nothing; used by pull_instantly_northstar.py via pool_count()).
Read-only on Instantly (GET campaigns, POST leads/list list endpoint only).
"""
from __future__ import annotations

import argparse, csv, fcntl, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")  # DST-aware CT (was fixed -05:00 before 2026-11-04)
ST = Path("/home/box/advero/state")
BASE = "https://api.instantly.ai/api/v2"
QUEUE = ST / "stalled/queue.csv"
QLOCK = ST / "stalled/.lock"
CRM_REACT = ST / "stalled/crm_reactivation_tab.csv"
CRM_REACT_META = ST / "stalled/crm_reactivation_tab.meta.json"
LP_REACT = ST / "reactivation/reactivation_queue.csv"
DNR = ST / "reactivation/do_not_reload.csv"
CLIENTS = ST / "clients"
INDEX = CLIENTS / "INDEX.csv"
CLOCK = CLIENTS / ".lock"
RUNLOG = ST / "reports/stalled_flag.log"
QHDR = ["key", "name", "company", "email", "domain", "channels_touched", "last_touch_email_ct",
        "last_touch_upwork_ct", "last_touch_linkedin_ct", "client_file", "flagged_at", "status"]
IHDR = ["key", "company", "domain", "emails", "upwork_client", "linkedin_url", "file", "last_bot", "last_updated_ct"]
BOT = "revenue-operations"
AUTO_LABELS = {"ooo", "machine"}
FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "msn.com",
            "live.com", "comcast.net", "att.net", "me.com", "protonmail.com", "ymail.com",
            "sbcglobal.net", "verizon.net", "mail.com", "gmx.com", "bellsouth.net", "cox.net"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
STALE_DAYS = 7
API_CALLS = 0


def now_ct():
    return datetime.now(CT)


def fmt_ct(dt):
    return dt.astimezone(CT).strftime("%Y-%m-%d %H:%M CT") if dt else ""


def parse_ts(s):
    if not s:
        return None
    t = str(s).strip().replace("Z", "+00:00")
    if t.endswith(" CT"):
        t = t[:-3]
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=CT)


def dom(d):
    d = (d or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0]
    return d[4:] if d.startswith("www.") else d


def edom(e):
    return e.split("@", 1)[1].lower() if "@" in (e or "") else ""


def norm(s):
    s = re.sub(r"\(.*?\)", " ", (s or "").lower())
    s = re.sub(r"\b(llc|inc|corp|co|ltd|the|company)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def is_auto(label):
    lab = (label or "").strip().lower()
    return lab in AUTO_LABELS or lab.startswith("auto_reply") or lab.startswith("ooo")


# ---------------- Instantly (read-only) ----------------
def load_key():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lbs", "/home/box/advero/bin/_load_box_secrets.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.apply()
    k = os.environ.get("INSTANTLY_API_KEY")
    if not k:
        raise RuntimeError("INSTANTLY_API_KEY is not set")
    return k


def api(path, key, body=None):
    global API_CALLS
    hdr = {"Authorization": f"Bearer {key}", "Accept": "application/json",
           "User-Agent": "Mozilla/5.0 (compatible; AdveroBot/1.0)"}
    data = None
    if body is not None:
        hdr["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    for attempt in range(4):
        API_CALLS += 1
        req = urllib.request.Request(BASE + path, data=data, headers=hdr, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1)); continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < 3:
                time.sleep(5 * (attempt + 1)); continue
            raise


def instantly_leads(key, include_test=False):
    """Contacted leads across all non-draft, non-test campaigns (FILTER_VAL_CONTACTED)."""
    camps, after = [], None
    while True:
        q = "/campaigns?limit=100" + (f"&starting_after={after}" if after else "")
        d = api(q, key)
        camps += d.get("items", [])
        after = d.get("next_starting_after")
        if not after or not d.get("items"):
            break
    out, per_camp = [], {}
    for c in camps:
        name = c.get("name", "")
        if c.get("status") == 0 or (not include_test and name.lower().startswith("test only")):
            continue
        n, after = 0, None
        while True:
            body = {"campaign": c["id"], "limit": 100, "filter": "FILTER_VAL_CONTACTED"}
            if after:
                body["starting_after"] = after
            d = api("/leads/list", key, body)
            items = d.get("items", [])
            for it in items:
                it.pop("payload", None)
                it["_campaign_name"] = name
            out += items; n += len(items)
            after = d.get("next_starting_after")
            if not after or not items:
                break
            time.sleep(0.3)
        per_camp[name] = n
    return out, per_camp, camps



# ---------------- local sources ----------------
OPTOUT_LABEL_PREFIXES = ("unsubscribe", "negative_", "opt_out", "optout")
CASE_OPTOUT = re.compile(r"optout|opt_out|unsubscribe|notfit|annoyed", re.I)
CASE_IGNORE = re.compile(r"ooo|autoreply|auto_reply|leftcompany|left_company|challengeresponse|challenge|verification|unmonitored|seed|probe|test|maker_school|ai_agents|_opus_|_err|_in\.json|_out\.json", re.I)
OWN_EMAILS = {"[EMAIL]"}
CLOSED_UPWORK = ("blocked", "excluded contract")


def read_jsonl(p):
    rows = []
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def is_optout(label):
    lab = (label or "").strip().lower()
    return lab.startswith(OPTOUT_LABEL_PREFIXES)


def bump(d, e, dt):
    if dt and (e not in d or dt > d[e]):
        d[e] = dt


def local_email_signals():
    """Returns dict of sets/maps from handled, sent_log, offered_times, cases."""
    s = dict(engaged=set(), optout=set(), auto=set(), last={})
    for o in read_jsonl(ST / "handled.jsonl"):
        src = (o.get("source") or "")
        lab = o.get("label")
        e = (o.get("lead") or "").strip().lower()
        if "@" not in e or e.endswith("@example.com") or e in OWN_EMAILS:
            continue
        if (o.get("status") or "").startswith("ignored"):
            continue
        dt = parse_ts(o.get("timestamp_email")) or parse_ts(o.get("at_ct"))
        if is_optout(lab) or src == "reactivation_move":
            s["optout"].add(e)
        elif is_auto(lab):
            s["auto"].add(e)
        else:
            s["engaged"].add(e)
        bump(s["last"], e, dt)
    auto_only = s["auto"] - s["engaged"]
    for name, tf in (("sent_log.jsonl", "at"), ("offered_times.jsonl", "offered_at")):
        for o in read_jsonl(ST / name):
            e = (o.get("lead") or "").strip().lower()
            if "@" in e and e not in OWN_EMAILS:
                s["engaged"].add(e); bump(s["last"], e, parse_ts(o.get(tf)))
    for f in sorted((ST / "cases").glob("*.json")):
        if CASE_IGNORE.search(f.name):
            continue
        try:
            txt = f.read_text(errors="ignore")
        except OSError:
            continue
        try:
            obj = json.loads(txt)
        except json.JSONDecodeError:
            obj = {}
        leads = set()
        if isinstance(obj, dict):
            for k in ("lead", "lead_email", "email"):
                v = obj.get(k)
                if isinstance(v, str) and "@" in v:
                    leads.add(v.strip().lower())
            ctx = obj.get("context") if isinstance(obj.get("context"), dict) else {}
            for k in ("lead", "lead_email", "email", "from"):
                v = ctx.get(k)
                if isinstance(v, str) and "@" in v:
                    leads.add(v.strip().lower())
        if CASE_OPTOUT.search(f.name):
            # opt-out batch files list many emails; take them all as opt-outs
            s["optout"] |= {m.lower() for m in EMAIL_RE.findall(txt)} | leads
        else:
            # leads whose only handled replies are auto_reply_* stay not engaged (2026-11-04)
            s["engaged"] |= {x for x in leads if x not in auto_only}
    s["engaged"] -= OWN_EMAILS
    return s


def upwork_entities(gaps):
    p = ST / "upwork_threads.json"
    ents = []
    try:
        d = json.loads(p.read_text())
    except Exception as ex:
        gaps.append(f"upwork_threads.json unreadable: {ex}"); return ents, "unreachable"
    today = now_ct().date().isoformat()
    for rid, t in (d.get("threads") or {}).items():
        stage = (t.get("stage") or "").lower()
        client = t.get("client") or ""
        name, _, company = client.partition(",")
        cands = [parse_ts(t.get(k)) for k in ("last_client_msg_ct", "last_message_ct", "last_lorenzo_send_ct",
                                              "silence_started_ct", "meeting_start_ct")]
        cands = [c for c in cands if c]
        src = "fields"
        if not cands:
            # fall back to dates written in the note (only past dates)
            ds = [x for x in re.findall(r"20\d\d-\d\d-\d\d", t.get("note") or "") if x <= today]
            cands = [datetime.fromisoformat(x + "T12:00:00").replace(tzinfo=CT) for x in ds]
            src = "note_dates"
        company = company.strip()
        if company and name.strip() and company.split()[0].lower() == name.strip().split()[0].lower():
            company = ""  # Upwork display name like "Adrilani S", not a company
        ents.append(dict(name=name.strip(), company=company, client=client, room=rid, stage=t.get("stage") or "",
                         closed=any(stage.startswith(c) for c in CLOSED_UPWORK), lost=stage.startswith("lost"),
                         last=max(cands) if cands else None, last_src=src))
    return ents, "ok"


def linkedin_entities(gaps):
    ents = {}
    tr = ST / "linkedin_tracker.csv"
    if not tr.exists():
        gaps.append("linkedin_tracker.csv missing"); return [], "unreachable"
    with tr.open(newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            url = (r.get("profile_url") or "").strip()
            rd = (r.get("request_date") or "").strip()
            if not url or not rd:
                continue
            dates = []
            for c in ("request_date", "accepted", "video_sent", "reply", "next_followup"):
                for x in re.findall(r"20\d\d-\d\d-\d\d", r.get(c) or ""):
                    if c != "next_followup":
                        dates.append(datetime.fromisoformat(x + "T12:00:00").replace(tzinfo=CT))
            engaged = bool((r.get("accepted") or "").strip()) and bool((r.get("reply") or "").strip() or (r.get("video_sent") or "").strip())
            ents[url] = dict(name=(r.get("person") or "").strip(), company=(r.get("company") or "").strip(),
                             domain=dom(r.get("company_url")), url=url, engaged=engaged,
                             last=max([d for d in dates if d], default=None))
    # Audit fix 2026-10-22: the Setter writes to state/linkedin/; old root path kept as fallback.
    log = ST / "linkedin" / "linkedin_connect_log.jsonl"
    if not log.exists():
        log = ST / "linkedin_connect_log.jsonl"
    if log.exists():
        for o in read_jsonl(log):
            url = (o.get("profile_url") or "").strip()
            dt = parse_ts(o.get("sent_at") or o.get("at_ct") or o.get("date"))
            if url in ents and dt and (not ents[url]["last"] or dt > ents[url]["last"]):
                ents[url]["last"] = dt
    else:
        gaps.append("linkedin_connect_log.jsonl not present (no LinkedIn sends logged yet)")
    if not any(e["engaged"] for e in ents.values()):
        gaps.append("no LinkedIn accept+message recorded in linkedin_tracker.csv")
    return list(ents.values()), "ok"
def reactivation_sets(args, gaps):
    emails, domains, names, companies = set(), set(), set(), set()
    status = "ok"
    if not CRM_REACT.exists():
        status = "missing"
    else:
        try:
            meta = json.loads(CRM_REACT_META.read_text())
            age = now_ct() - parse_ts(meta["fetched_at"])
            if age > timedelta(hours=36):
                status = f"stale ({age.total_seconds()/3600:.0f}h)"
        except Exception:
            status = "meta_unreadable"
    if status != "ok":
        gaps.append(f"CRM Reactivation tab cache {status}")
        if not args.allow_stale_reactivation:
            raise SystemExit(json.dumps({"error": f"CRM Reactivation cache {status}; refresh "
                                         f"{CRM_REACT} from the sheet first (fail closed, nothing written)"}))
    rows = []
    if CRM_REACT.exists():
        with CRM_REACT.open(newline="", encoding="utf-8-sig") as fh:
            rows += [("crm", r) for r in csv.DictReader(fh)]
    if LP_REACT.exists():
        with LP_REACT.open(newline="", encoding="utf-8-sig") as fh:
            rows += [("lead_pool", r) for r in csv.DictReader(fh)]
    else:
        gaps.append("Lead Pool reactivation mirror missing")
    for src, r in rows:
        handle = (r.get("Email/Handle") or r.get("email") or "").strip()
        for e in EMAIL_RE.findall(handle):
            emails.add(e.lower())
            d = edom(e)
            if d and d not in FREEMAIL:
                domains.add(d)
        nm = norm(r.get("Name") or "")
        if handle.lower().startswith("upwork:"):
            names.add(norm(handle.split(":", 1)[1]))
        if nm and len(nm.split()) >= 2:
            names.add(nm)
        co = norm(r.get("Company") or r.get("company") or "")
        if co:
            companies.add(co)
    dnr = set()
    if DNR.exists():
        with DNR.open(newline="", encoding="utf-8-sig") as fh:
            dnr = {(r.get("email") or "").strip().lower() for r in csv.DictReader(fh)} - {""}
    else:
        gaps.append("do_not_reload.csv missing")
    return dict(emails=emails, domains=domains, names=names, companies=companies), dnr, status


def queue_seen():
    keys, emails = set(), set()
    if QUEUE.exists():
        with QUEUE.open(newline="") as fh:
            for r in csv.DictReader(fh):
                keys.add((r.get("key") or "").strip().lower())
                for e in (r.get("email") or "").split(";"):
                    if e.strip():
                        emails.add(e.strip().lower())
    return keys, emails


def load_index():
    rows = []
    if INDEX.exists():
        with INDEX.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    return rows


def index_match(rows, emails, domain, company, upwork_client=""):
    for r in rows:
        if upwork_client and norm(r.get("upwork_client")) and norm(r.get("upwork_client")) == norm(upwork_client):
            return r
        rem = {e.strip().lower() for e in (r.get("emails") or "").replace(",", ";").split(";") if e.strip()}
        if (domain and dom(r.get("domain")) == domain) or (rem & set(emails)) or \
           (company and norm(r.get("company")) == norm(company) and norm(company)):
            return r
    return None


LOST_SUMMARY_RE = re.compile(r"\bstatus:\s*\**\s*lost\b", re.I)
STAGE_RE = re.compile(r"\bstage:\s*([a-z][a-z ]*)", re.I)
_LOST_CACHE = {}


def client_file_lost(path):
    """True if a client file says Lost: Summary 'Status: Lost' or the latest Log 'Stage: X' is Lost."""
    path = Path(path)
    if path in _LOST_CACHE:
        return _LOST_CACHE[path]
    lost = False
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        text = ""
    sec, summary, log = "", [], []
    for line in text.split("\n"):
        if line.startswith("## "):
            sec = line[3:].strip().lower(); continue
        if sec == "summary" or sec == "":
            summary.append(line)
        elif sec == "log":
            log.append(line)
    if any(LOST_SUMMARY_RE.search(l) for l in summary):
        lost = True
    else:
        stages = [m.group(1).strip().lower() for l in log for m in [STAGE_RE.search(l)] if m]
        if stages and stages[-1].startswith("lost"):
            lost = True
    _LOST_CACHE[path] = lost
    return lost


def client_rows_for(rows, en):
    """All INDEX rows that match the entity on any channel identifier."""
    ems = {e.lower() for e in en["emails"]}
    names = {norm(n) for n in en["names"] if len(norm(n).split()) >= 2}
    cos = {norm(c) for c in en["companies"]} - {""}
    upc = norm(en.get("upwork_client", ""))
    li = (en.get("linkedin_url") or "").strip().rstrip("/").lower()
    out = []
    for r in rows:
        rem = {e.strip().lower() for e in (r.get("emails") or "").replace(",", ";").split(";") if e.strip()}
        rupc = norm(r.get("upwork_client"))
        rup_names = {norm(x) for x in (r.get("upwork_client") or "").split(",") if len(norm(x).split()) >= 2}
        rli = (r.get("linkedin_url") or "").strip().rstrip("/").lower()
        if (rem & ems) or (en["domain"] and dom(r.get("domain")) == en["domain"]) or \
           (upc and rupc and upc == rupc) or (rup_names & names) or (li and rli and li == rli) or \
           (norm(r.get("company")) and norm(r.get("company")) in cos) or \
           ((r.get("key") or "").strip().lower() == en["key"].lower()):
            out.append(r)
    return out


def is_client_lost(idx_rows, en, q_lost_keys, q_lost_emails):
    if en.get("upwork_lost"):
        return "upwork_stage_lost"
    if en["key"].lower() in q_lost_keys or {e.lower() for e in en["emails"]} & q_lost_emails:
        return "queue_status_lost"
    files = []
    for r in client_rows_for(idx_rows, en):
        if (r.get("key") or "").strip().lower() in q_lost_keys:
            return "queue_status_lost"
        if (r.get("file") or "").strip():
            files.append(CLIENTS / r["file"].strip())
    if en["domain"]:
        files.append(CLIENTS / f"{en['domain']}.md")
    files.append(CLIENTS / f"{slug(en['key'])}.md")
    for f in files:
        if f.exists() and client_file_lost(f):
            return "client_file_lost"
    return ""


def queue_lost(status="lost"):
    keys, emails = set(), set()
    if QUEUE.exists():
        with QUEUE.open(newline="") as fh:
            for r in csv.DictReader(fh):
                if (r.get("status") or "").strip().lower() == status:
                    keys.add((r.get("key") or "").strip().lower())
                    emails |= {e.strip().lower() for e in (r.get("email") or "").split(";") if e.strip()}
    return keys, emails



OCT_START = datetime(2026, 10, 1, tzinfo=CT)


def first_email_info(en, key):
    """(first outbound email datetime, source) for an email lead; (None, reason) if unknown."""
    firsts = []
    for e in sorted(en["emails"]):
        try:
            d = api("/emails?" + urllib.parse.urlencode({"lead": e, "limit": 100, "sort_order": "asc"}), key)
        except Exception:
            continue
        for it in d.get("items") or []:
            if it.get("ue_type") in (1, 3) and (it.get("lead") or "").strip().lower() == e:
                t = parse_ts(it.get("timestamp_email") or it.get("timestamp_created"))
                if t: firsts.append(t)
    if firsts:
        return min(firsts), "instantly_emails"
    recs = en["records"]
    lc = [parse_ts(r.get("timestamp_last_contact")) for r in recs]
    lc = [x for x in lc if x]
    if lc and min(lc) < OCT_START:
        return min(lc), "instantly_last_contact_bound"  # first email <= this date
    cr = [parse_ts(r.get("timestamp_created")) for r in recs]
    if recs and all(cr) and min(cr) >= OCT_START:
        return min(lc) if lc else min(cr), "instantly_created_bound"  # created Oct+, so first email Oct+
    return None, "unknown"


# ---------------- core ----------------
def new_ent(k, domain=""):
    return dict(key=k, emails=set(), domain=domain, names=set(), companies=set(), records=[],
                last={"email": None, "upwork": None, "linkedin": None}, channels=set(),
                engaged=set(), optout=False, unclassified=False, any_reply=False, linkedin_url="",
                all_complete=None, step_last=None)


def build(key, gaps, sources):
    sig = local_email_signals()
    leads, per_camp, camps = instantly_leads(key)
    sources["instantly"] = "ok"
    sender_domains = set()
    for l in leads:
        f = ((l.get("status_summary") or {}).get("lastStep") or {}).get("from") or ""
        if edom(f):
            sender_domains.add(edom(f))
    ents, by_email = {}, {}

    def kfor(e, d):
        d = d or edom(e)
        return d if d and d not in FREEMAIL else e

    def ent_for_email(e, d=""):
        if e in by_email:
            return by_email[e]
        d = d or edom(e)
        if d in FREEMAIL:
            d = ""
        k = kfor(e, d)
        en = ents.setdefault(k, new_ent(k, d))
        en["emails"].add(e); by_email[e] = en
        return en

    cnt = dict(instantly_contacted_records=len(leads), own_or_test=0)
    for l in leads:
        e = (l.get("email") or "").strip().lower()
        if not e or edom(e) in sender_domains or e.endswith("@example.com") or e in OWN_EMAILS:
            cnt["own_or_test"] += 1; continue
        d = dom(l.get("company_domain") or l.get("website")) or edom(e)
        en = ent_for_email(e, d)
        en["records"].append(l)
        nm = " ".join(x for x in [(l.get("first_name") or "").strip(), (l.get("last_name") or "").strip()] if x)
        if nm: en["names"].add(nm)
        if (l.get("company_name") or "").strip(): en["companies"].add(l["company_name"].strip())
    # local-only email leads (handled/cases/etc. not in Instantly contacted list)
    for e in sig["engaged"] | sig["optout"] | sig["auto"]:
        if edom(e) in sender_domains:
            continue
        ent_for_email(e)

    for en in ents.values():
        delivered = [r for r in en["records"] if r.get("status") not in (-1, -3)]
        ts = []
        for r in delivered:
            for f in ("timestamp_last_contact", "timestamp_last_reply", "timestamp_last_touch"):
                if parse_ts(r.get(f)): ts.append(parse_ts(r.get(f)))
        steps = [parse_ts(r.get("timestamp_last_contact")) for r in delivered]
        steps = [x for x in steps if x]
        en["step_last"] = max(steps) if steps else None
        en["all_complete"] = bool(delivered) and all(r.get("status") == 3 for r in delivered)
        for e in en["emails"]:
            if e in sig["last"]: ts.append(sig["last"][e])
            if e in sig["engaged"]: en["engaged"].add("email_reply_or_case")
            if e in sig["optout"]: en["optout"] = True
            if e in sig["engaged"] | sig["optout"] | sig["auto"]: en["any_reply"] = True
        for r in delivered + [r for r in en["records"] if r not in delivered]:
            e = r["email"].lower()
            if r.get("status") == -2: en["optout"] = True; en["any_reply"] = True
            isv = r.get("lt_interest_status")
            if isinstance(isv, (int, float)) and isv > 0: en["engaged"].add("instantly_interest"); en["any_reply"] = True
            if isinstance(isv, (int, float)) and isv < 0 and isv != -4: en["optout"] = True; en["any_reply"] = True
            if (r.get("email_reply_count") or 0) > 0:
                en["any_reply"] = True
                if e not in sig["engaged"] | sig["optout"] | sig["auto"] and not (isinstance(isv, (int, float)) and isv != 0):
                    en["unclassified"] = True
        if delivered or en["engaged"] or en["optout"]:
            en["channels"].add("email")
        en["last"]["email"] = max(ts) if ts else None

    rep_domains = {d for en in ents.values() if en["engaged"] or en["optout"] for d in [en["domain"]] if d}

    def find(name, company, domain=""):
        for en in ents.values():
            if domain and en["domain"] == domain: return en
            if company and norm(company) and norm(company) in {norm(c) for c in en["companies"]}: return en
            if name and len(norm(name).split()) >= 2 and norm(name) in {norm(n) for n in en["names"]}: return en
        return None

    up, sources["upwork"] = upwork_entities(gaps)
    for u in up:
        en = find(u["name"], u["company"])
        if not en:
            k = slug("-".join(x for x in [u["name"], u["company"]] if x)) or u["room"]
            en = ents.setdefault(k, new_ent(k))
        en["channels"].add("upwork"); en["upwork_client"] = u["client"]
        if u["name"]: en["names"].add(u["name"])
        if u["company"]: en["companies"].add(u["company"])
        if u.get("lost"):
            en["upwork_lost"] = True
        if u["closed"]:
            en["upwork_closed"] = True
        else:
            en["engaged"].add("upwork_conversation")
        if u["last"] and (not en["last"]["upwork"] or u["last"] > en["last"]["upwork"]):
            en["last"]["upwork"] = u["last"]
        en["upwork_last_src"] = u["last_src"]
    li, sources["linkedin"] = linkedin_entities(gaps)
    for x in li:
        en = find(x["name"], x["company"], x["domain"])
        if not en:
            k = x["domain"] or slug("-".join(y for y in [x["name"], x["company"]] if y))
            en = ents.setdefault(k, new_ent(k, x["domain"]))
        en["channels"].add("linkedin"); en["linkedin_url"] = x["url"]
        if x["name"]: en["names"].add(x["name"])
        if x["company"]: en["companies"].add(x["company"])
        if x["engaged"]: en["engaged"].add("linkedin_accept_message")
        if x["last"] and (not en["last"]["linkedin"] or x["last"] > en["last"]["linkedin"]):
            en["last"]["linkedin"] = x["last"]
    return ents, cnt, rep_domains


def compute_pool(ents, rep_domains, now, grace_days):
    cut = now - timedelta(days=grace_days)
    n = 0
    for en in ents.values():
        if not en["records"] or not en["all_complete"]:
            continue
        if en["engaged"] or en["optout"] or en["unclassified"] or en["channels"] - {"email"}:
            continue
        # "never replied": real (non-auto) replies disqualify; auto/OOO-only still counts as never replied
        if any((r.get("email_reply_count") or 0) > 0 for r in en["records"]) and not all(
                e in local_email_signals_cache["auto"] for e in en["emails"] if e in local_email_signals_cache["all"]):
            continue
        if en["domain"] and en["domain"] in rep_domains:
            continue
        if en["step_last"] and en["step_last"] <= cut:
            n += 1
    return n


local_email_signals_cache = {"auto": set(), "all": set()}


def pool_count(grace_days=7.0, key=None):
    """Count-only entry point for pull_instantly_northstar.py. Writes nothing."""
    gaps, sources = [], {}
    key = key or load_key()
    s = local_email_signals()
    local_email_signals_cache["auto"] = s["auto"] - s["engaged"] - s["optout"]
    local_email_signals_cache["all"] = s["auto"] | s["engaged"] | s["optout"]
    ents, cnt, rep = build(key, gaps, sources)
    return dict(count=compute_pool(ents, rep, now_ct(), grace_days), grace_days=grace_days,
                api_calls=API_CALLS, as_of=now_ct().isoformat(timespec="seconds"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute and print; write nothing but the run log")
    ap.add_argument("--pool-only", action="store_true", help="print the sequence-complete pool count only; write nothing")
    ap.add_argument("--allow-stale-reactivation", action="store_true",
                    help="proceed even if the CRM Reactivation cache is missing/old (not for the routine)")
    ap.add_argument("--complete-grace-days", type=float, default=7.0,
                    help="days after the last Instantly step before a lead joins the no-reply pool (default 7)")
    ap.add_argument("--silence-days", type=float, default=float(STALE_DAYS),
                    help="days of silence on every channel before an engaged lead is stalled (default 7)")
    ap.add_argument("--list", action="store_true", help="include flagged rows in the summary output")
    ap.add_argument("--no-runlog", action="store_true", help="with --dry-run: do not append to reports/stalled_flag.log (zero writes)")
    args = ap.parse_args()
    t0 = time.time(); now = now_ct()
    if (ST / "KILL_SWITCH").exists():
        print(json.dumps({"stopped": "KILL_SWITCH present", "flagged": 0})); return 0
    if args.pool_only:
        try:
            print(json.dumps(pool_count(args.complete_grace_days))); return 0
        except Exception as ex:
            print(json.dumps({"error": f"{ex}", "api_calls": API_CALLS})); return 2
    gaps, sources = [], {}
    react, dnr, sources["crm_reactivation_cache"] = reactivation_sets(args, gaps)
    s = local_email_signals()
    local_email_signals_cache["auto"] = s["auto"] - s["engaged"] - s["optout"]
    local_email_signals_cache["all"] = s["auto"] | s["engaged"] | s["optout"]
    try:
        key = load_key()
        ents, cnt, rep_domains = build(key, gaps, sources)
    except Exception as ex:
        print(json.dumps({"error": f"source read failed (Instantly or local): {type(ex).__name__}: {ex}", "flagged": 0, "api_calls": API_CALLS}))
        _runlog({"ts": now.isoformat(timespec="seconds"), "dry_run": args.dry_run, "error": f"{type(ex).__name__}: {ex}"}, args)
        return 2
    cut = now - timedelta(days=args.silence_days)
    excl = dict(not_engaged=0, opt_out_or_no=0, unclassified_reply=0, upwork_closed_only=0, not_quiet_7d=0,
                unknown_last_touch=0, reactivation=0, do_not_reload=0, already_in_queue=0, client_lost=0,
                already_nurture=0, routed_nurture_sep=0)
    idx_rows = load_index(); q_lost_keys, q_lost_emails = queue_lost(); lost_keys = []
    q_nur_keys, q_nur_emails = queue_lost("nurture")
    qkeys, qemails = queue_seen()
    qfiles = set()
    if QUEUE.exists():
        with QUEUE.open(newline="") as fh:
            qfiles = {(r.get("client_file") or "").strip() for r in csv.DictReader(fh)} - {""}
    cands = []
    for en in ents.values():
        if not en["channels"]:
            continue
        if en["optout"]:
            excl["opt_out_or_no"] += 1; continue
        if not en["engaged"]:
            if en.get("upwork_closed"): excl["upwork_closed_only"] += 1
            elif en["unclassified"]: excl["unclassified_reply"] += 1
            else: excl["not_engaged"] += 1
            continue
        why_lost = is_client_lost(idx_rows, en, q_lost_keys, q_lost_emails)
        if why_lost:
            excl["client_lost"] += 1; lost_keys.append(f"{en['key']} ({why_lost})"); continue
        if en["key"].lower() in q_nur_keys or {e.lower() for e in en["emails"]} & q_nur_emails or \
           any((r.get("key") or "").strip().lower() in q_nur_keys for r in client_rows_for(idx_rows, en)):
            excl["already_nurture"] += 1; continue
        touched = {c: en["last"][c] for c in en["channels"] if not (c == "upwork" and en.get("upwork_closed") and "upwork_conversation" not in en["engaged"])}
        if any(v is None for v in touched.values()):
            excl["unknown_last_touch"] += 1; continue
        if not all(v <= cut for v in touched.values()):
            excl["not_quiet_7d"] += 1; continue
        ems = en["emails"]
        if ems & react["emails"] or (en["domain"] and en["domain"] in react["domains"]) or \
           {norm(n) for n in en["names"]} & react["names"] or {norm(c) for c in en["companies"]} & react["companies"]:
            excl["reactivation"] += 1; continue
        if ems & dnr:
            excl["do_not_reload"] += 1; continue
        if en["key"].lower() in qkeys or ems & qemails:
            excl["already_in_queue"] += 1; continue
        en["touched"] = touched
        cands.append(en)
    pool = compute_pool(ents, rep_domains, now, args.complete_grace_days)
    by_ch = {"email": 0, "upwork": 0, "linkedin": 0}
    flagged_at = fmt_ct(now); out_rows = []
    for en in sorted(cands, key=lambda x: x["key"]):
        for c in en["touched"]: by_ch[c] += 1
        company = sorted(en["companies"])[0] if en["companies"] else ""
        m = index_match(idx_rows, list(en["emails"]), en["domain"], company, en.get("upwork_client", ""))
        cfile = (m.get("file") if m else "") or (f"{en['domain']}.md" if en["domain"] else f"{slug(en['key'])}.md")
        if (m and (m.get("key") or "").lower() in qkeys) or f"~/advero/state/clients/{cfile}" in qfiles:
            excl["already_in_queue"] += 1
            for c in en["touched"]: by_ch[c] -= 1
            continue
        out_rows.append(dict(key=(m.get("key") if m and m.get("key") else en["key"]), _upc=en.get("upwork_client", ""), name="; ".join(sorted(en["names"])), company=company,
                             email=";".join(sorted(en["emails"])), domain=en["domain"],
                             channels_touched=";".join(sorted(en["touched"])),
                             last_touch_email_ct=fmt_ct(en["touched"].get("email")),
                             last_touch_upwork_ct=fmt_ct(en["touched"].get("upwork")),
                             last_touch_linkedin_ct=fmt_ct(en["touched"].get("linkedin")),
                             client_file=f"~/advero/state/clients/{cfile}", flagged_at=flagged_at, status="new",
                             _why=f"engaged ({', '.join(sorted(en['engaged']))}) then {int(args.silence_days)}+ days quiet on every channel",
                             _li=en["linkedin_url"], _new_index=m is None, _en=en))
    flag_rows, nurture_rows, unknown_dates = [], [], []
    for r in out_rows:
        en = r.pop("_en")
        if "email" in en["touched"] and en["emails"]:
            fdt, fsrc = first_email_info(en, key)
        else:
            fdt, fsrc = None, "no_email_channel"
        r["_first_email"] = fdt; r["_first_src"] = fsrc
        r["first_email_ct"] = fmt_ct(fdt) if fdt else ""
        if fdt and fdt < OCT_START:
            r["status"] = "nurture"
            r["_why"] += (f"; first emailed {fmt_ct(fdt)} (pre-October), routed to nurture per Lorenzo 2026-10-23 "
                          f"11:00 CT (prioritizing October and newer); no hold card")
            nurture_rows.append(r); excl["routed_nurture_sep"] += 1
        else:
            if fsrc == "unknown": unknown_dates.append(r["key"])
            flag_rows.append(r)
    grp = lambda r: 0 if r["_first_email"] else (1 if r["_first_src"] == "unknown" else 2)
    flag_rows.sort(key=lambda r: (grp(r), -(r["_first_email"].timestamp() if r["_first_email"] else 0), r["key"]))
    by_ch = {"email": 0, "upwork": 0, "linkedin": 0}
    for r in flag_rows:
        for c in r["channels_touched"].split(";"):
            if c: by_ch[c] += 1
    out_rows = flag_rows + nurture_rows
    written = 0
    if not args.dry_run:
        if out_rows:
            written = write_outputs(out_rows, now)
        pf = QUEUE.parent / "sequence_complete_pool_latest.json"
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(json.dumps({"date_ct": now.date().isoformat(), "as_of": now.isoformat(timespec="seconds"),
                                  "count": pool, "grace_days": args.complete_grace_days,
                                  "definition": "all Instantly steps complete, last step >= grace days ago, never replied (OOO/auto only = never replied), no other engagement; count only"}, indent=1))
    summary = dict(ts=now.isoformat(timespec="seconds"), dry_run=args.dry_run, definition="v2 engaged-then-quiet",
                   flagged=len(flag_rows), written=written, by_channel=by_ch, excluded=excl, client_lost_keys=lost_keys,
                   flagged_oct_or_newer=sum(1 for r in flag_rows if r["_first_email"]),
                   flagged_first_email_unknown=unknown_dates,
                   flagged_no_email_channel=sum(1 for r in flag_rows if r["_first_src"] == "no_email_channel"),
                   routed_nurture_sep_keys=[r["key"] for r in nurture_rows],
                   sequence_complete_pool=pool, pool_grace_days=args.complete_grace_days, counts=cnt,
                   entities_considered=len(ents), sources=sources, data_gaps=gaps,
                   api_calls=API_CALLS, runtime_s=round(time.time() - t0, 1))
    if args.list:
        summary["rows"] = [{k: v for k, v in r.items() if not k.startswith("_")} | {"why": r["_why"], "first_email_source": r["_first_src"]} for r in out_rows]
    print(json.dumps(summary, indent=1))
    _runlog({k: v for k, v in summary.items() if k != "rows"}, args)
    return 0


def _runlog(obj, args):
    if getattr(args, "no_runlog", False) and getattr(args, "dry_run", False):
        return
    try:
        with RUNLOG.open("a") as fh:
            fh.write(json.dumps(obj) + "\n")
    except OSError:
        pass


def write_outputs(rows, now):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    # 1. queue (flock, re-check dedup inside lock)
    with open(QLOCK, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        new = not QUEUE.exists() or QUEUE.stat().st_size == 0
        qkeys, qemails = queue_seen()
        fresh = [r for r in rows if r["key"].lower() not in qkeys and not (set(r["email"].split(";")) - {""}) & qemails]
        with QUEUE.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=QHDR, extrasaction="ignore")
            if new:
                w.writeheader()
            for r in fresh:
                w.writerow(r)
    # 2. client files + INDEX (flock clients/.lock)
    stamp = now.strftime("%Y-%m-%d %H:%M CT")
    created_files, created_idx = [], []
    with open(CLOCK, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        idx = load_index()
        for r in fresh:
            path = Path(r["client_file"].replace("~", "/home/box", 1))
            touches = "; ".join(f"last {c} touch {r['last_touch_' + c + '_ct']}" for c in
                                r["channels_touched"].split(";") if r.get("last_touch_" + c + "_ct"))
            if r.get("status") == "nurture":
                line = (f"- {stamp} | {BOT} | stalled-flag | routed to nurture (status=nurture in state/stalled/queue.csv, "
                        f"no hold card): channels {r['channels_touched'].replace(';', ', ')}; {touches}; {r['_why']}")
            else:
                line = (f"- {stamp} | {BOT} | stalled-flag | flagged stalled: channels {r['channels_touched'].replace(';', ', ')}"
                        f"; {touches}; {r['_why']}; queued in state/stalled/queue.csv for Appointment Setter")
            if not path.exists():
                created_files.append(str(path))
            append_log(path, r, line)
            m = index_match(idx, [e for e in r["email"].split(";") if e], r["domain"], r["company"], r.get("_upc", ""))
            if m is None:
                created_idx.append(r["key"])
                idx.append(dict(key=r["key"], company=r["company"], domain=r["domain"], emails=r["email"],
                                upwork_client=r.get("_upc", ""), linkedin_url=r["_li"], file=path.name, last_bot=BOT,
                                last_updated_ct=stamp))
            else:
                have = {e.strip().lower() for e in (m.get("emails") or "").split(";") if e.strip()}
                add = [e for e in r["email"].split(";") if e and e not in have]
                if add:
                    m["emails"] = ";".join([x for x in (m.get("emails") or "").split(";") if x] + add)
                m["last_bot"] = BOT; m["last_updated_ct"] = stamp
                if not m.get("file"):
                    m["file"] = path.name
        tmp = INDEX.with_suffix(".csv.tmp")
        with tmp.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=IHDR, extrasaction="ignore")
            w.writeheader(); w.writerows(idx)
        os.replace(tmp, INDEX)
    man = QUEUE.parent / f"manifest_{now.strftime('%Y%m%d_%H%M')}.json"
    man.write_text(json.dumps({"flagged_at": stamp, "queued_keys": [r["key"] for r in fresh if r.get("status") != "nurture"],
                               "nurture_keys": [r["key"] for r in fresh if r.get("status") == "nurture"],
                               "created_client_files": created_files, "created_index_keys": created_idx}, indent=0))
    return len(fresh)


def append_log(path, r, line):
    if not path.exists():
        contacts = "\n".join(f"- {e}" for e in r["email"].split(";") if e) or ""
        names = r["name"] or ""
        body = (f"# {r['company'] or names or r['key']}\n\n## Summary\n"
                f"{names + ', ' if names else ''}{r['company'] or ''}. Status: stalled (flagged {r['flagged_at']}), "
                f"engaged then quiet on every channel.\n\n## Contacts\n{contacts}\n\n## Channels touched\n"
                + "\n".join(f"- {c}" for c in r["channels_touched"].split(";")) +
                "\n\n## What we know\n\n## Decisions by Lorenzo\n\n## Log\n" + line + "\n")
        path.write_text(body)
        return
    text = path.read_text()
    lines = text.split("\n")
    try:
        i = next(n for n, l in enumerate(lines) if l.strip().lower() == "## log")
    except StopIteration:
        path.write_text(text.rstrip("\n") + "\n\n## Log\n" + line + "\n"); return
    j = i + 1
    while j < len(lines) and not lines[j].startswith("## "):
        j += 1
    k = j
    while k > i + 1 and not lines[k - 1].strip():
        k -= 1
    lines.insert(k, line)
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
