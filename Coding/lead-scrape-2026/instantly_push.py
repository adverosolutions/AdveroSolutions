#!/usr/bin/env python3
"""Instantly (API v2) setup + daily lead push for the 2026 three-niche campaigns.

  python3 instantly_push.py --check                 # key + inboxes + campaigns
  python3 instantly_push.py --setup                 # cap every inbox at 25/day, create the 6 campaigns
  python3 instantly_push.py --push output/daily/day_<id>.csv   # upload that day's leads
  python3 instantly_push.py --activate              # start all 6 campaigns
  python3 instantly_push.py --push a.csv b.csv --offer ai_agents [--dry-run] [--ids-file f.json] [--limit-per-campaign N] [--allow-active]
      # AI-agents campaigns (ids in instantly_campaigns_ai_agents.json), slot1/slot2 set; never activates;
      # GETs the six campaigns first and refuses (exit 2) to add to an active one unless --allow-active;
      # a live run writes logs/push_ai_<ts>.json before the first add (pre_existing leads per campaign),
      # then the rollback list (instantly_ids = leads this push created), and reads one lead per campaign back
  --setup is refused with --offer or --dry-run, --activate with --dry-run (both write live).

Key: INSTANTLY_API_KEY in this folder's .env (falls back to Agentic Worklfows/.env).
Campaign ids are saved to instantly_campaigns.json after --setup.
"""
import argparse, csv, json, re, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.instantly.ai/api/v2"
PER_INBOX_DAILY = 25
SUBJECT = "{{firstName}}, question"
SCHEDULE = {"schedules": [{"name": "Business hours", "timing": {"from": "08:00", "to": "17:00"},
                           "days": {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": False},
                           "timezone": "America/Chicago"}]}

# ---- copy (Lorenzo's, typos fixed: personaliztion, "outreach outreach", ill -> I'll, dictation fragment removed) ----
REACTIVATION_RECRUITING = """{{personalization}}

I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

TLDR: I'd recover lost revenue by building email and text sequences that would go out to any dormant or near miss candidate accounts. 

I'm so certain this would work for you that I won't charge you a single cent up front, only a percentage of placement fees from accounts I bring back, $0 if nothing closes. I truly believe I can benefit {{companyName}}.

Would you be open to a quick 15 minute call about this? If so just say yes and I'll shoot a calendar invite over.

Thanks,
Lorenzo"""

OUTBOUND_RECRUITING = """{{personalization}}

I build outbound systems for recruiting agencies. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

Here's what this would look like for {{companyName}}: I watch for {{specialty}} roles sitting open on job boards, run outreach to the hiring managers under your name, and put the intro calls straight on your calendar.

I'm so confident this works that I guarantee at least $40,000 in new placement fees from those calls within 180 days, or I return your money and throw in a $200 gift card to your favorite steakhouse.

Open to a quick 15 minute call? Just say yes and I'll send a calendar invite.

Thanks,
Lorenzo"""

REACTIVATION_CLEANING = """{{personalization}}

Know this is out of left field, if I could help recover the money from accounts that cancelled or stopped renewing their contracts in exchange for a commission on the accounts I bring back, would you be open? I work mostly on performance and am building my network.

About me: I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months. Would cost you nothing upfront.

Let me know.

Thanks,
Lorenzo"""

TRIGGER_CLEANING = """{{personalization}}

I build outbound acquisition systems. I recently implemented the same system for a commercial roofing company doing around $150M/yr and was able to generate around $180,000 in 90 days. 

I do this by watching for triggers (new leases, office expansions, property management changes, new construction) and run outreach under {{companyName}}'s name. All the walkthroughs would land straight on your calendar.

I'm so confident that I guarantee at least $24,000 a year in new cleaning contracts signed within 90 days, or I give your money back and throw in a $200 gift card to your favorite steakhouse. 

If this interests you, let's hop on a short 15 minute call. Just reply Yes and I can shoot you over a calendar invite. 

Thanks,
Lorenzo"""

REACTIVATION_BOOKKEEPING = """{{personalization}}

I build client reactivation systems. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

TLDR: I'd recover lost revenue by building email sequences that would go out to any lost inquiries and former clients, timed to tax season, quarterly estimates, and year-end cleanup. Booked straight onto your calendar.

I'm so certain this would work for you that I won't charge you a single cent up front, only a percentage of first-year fees from clients I bring back, $0 if nothing closes. I truly believe I can benefit {{companyName}}.
Would you be open to a quick 15 minute call about this? If so just say yes and I'll shoot a calendar invite over.

Thanks,
Lorenzo"""

TRIGGER_BOOKKEEPING = """{{personalization}}

I build outbound acquisition systems. I recently implemented the same system for a commercial roofing company doing around $150M/yr and was able to generate around $180,000 in 90 days. 

I do this by watching for triggers (new business formations, companies posting part time bookkeeper or admin roles, second location openings) and run outreach under {{companyName}}'s name. All the discovery calls land straight on your calendar.

I'm so confident that I guarantee at least $15,000 in new annual client fees signed within 90 days, or I give your money back and throw in a $200 gift card to your favorite steakhouse. 

If this interests you, let's hop on a short 15 minute call. Just reply Yes and I can shoot you over a calendar invite. 

Thanks,
Lorenzo"""

FOLLOWUPS = {
 "recruiting_reactivation": "Hey {{firstName}},\n\nChecking in, in case the first one got buried. Quick version:\n- I want to build a reactivation system for {{companyName}}. Goal is to bring back the accounts that went quiet on you, with email and text sequences that run on their own.\n- I did this for a commercial roofer doing $150M/yr and recovered about $6M in contracts in 6 months.\n- Nothing up front. I only take a percentage of placement fees on accounts I bring back, $0 if nothing closes.\n\nWorth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\n\nThanks for the time,\nLorenzo",
 "recruiting_outbound": "Hey {{firstName}},\n\nChecking in, in case the first one got buried. Quick version:\n- I want to build an outbound system for {{companyName}}. Goal is to find {{specialty}} roles sitting open on job boards, reach the hiring managers under your name, and put the intro calls on your calendar.\n- I did this for a commercial roofer doing $150M/yr and generated about $180K in new contracts in 90 days.\n- If you don't see $40K in new placement fees within 180 days, I return your money and throw in a $200 gift card to your favorite steakhouse.\n\nWorth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\n\nThanks for the time,\nLorenzo",
 "cleaning_reactivation": "Hey {{firstName}},\n\nChecking in, in case the first one got buried. Quick version:\n- I want to build a reactivation system for {{companyName}}. Goal is to bring back the accounts that cancelled or stopped renewing, without you chasing anyone.\n- I did this for a commercial roofer doing $150M/yr and recovered about $6M in contracts in 6 months.\n- Nothing up front. I only take a commission on the accounts I bring back.\n\nWorth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\n\nThanks for the time,\nLorenzo",
 "cleaning_trigger": "Hey {{firstName}},\n\nChecking in, in case the first one got buried. Quick version:\n- I want to build an outbound system for {{companyName}}. Goal is to catch businesses signing new leases or expanding, reach them under your name, and land the walkthroughs on your calendar.\n- I did this for a commercial roofer doing $150M/yr and generated about $180K in new contracts in 90 days.\n- If you don't have at least $24K a year in new cleaning contracts signed within 90 days, I give your money back and throw in a $200 gift card to your favorite steakhouse.\n\nWorth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\n\nThanks for the time,\nLorenzo",
 "bookkeeping_reactivation": "Hey {{firstName}},\n\nChecking in, in case the first one got buried. Quick version:\n- I want to build a reactivation system for {{companyName}}. Goal is to bring back lost inquiries and former clients with sequences timed to tax season, quarterly estimates, and year-end cleanup.\n- I did this for a commercial roofer doing $150M/yr and recovered about $6M in contracts in 6 months.\n- Nothing up front. I only take a percentage of first-year fees on clients I bring back, $0 if nothing closes.\n\nWorth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\n\nThanks for the time,\nLorenzo",
 "bookkeeping_trigger": "Hey {{firstName}},\n\nChecking in, in case the first one got buried. Quick version:\n- I want to build an outbound system for {{companyName}}. Goal is to catch new business formations and second locations opening, reach them under your name, and land the discovery calls on your calendar.\n- I did this for a commercial roofer doing $150M/yr and generated about $180K in new contracts in 90 days.\n- If you don't have at least $15K in new annual client fees signed within 90 days, I give your money back and throw in a $200 gift card to your favorite steakhouse.\n\nWorth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\n\nThanks for the time,\nLorenzo"
}
FOLLOWUP_DELAY_DAYS = 3

# six campaigns, one body each; a niche's leads are split round-robin across its campaigns
CAMPAIGNS = {
    "recruiting_reactivation": {"niche": "recruiting", "name": "2026 Recruiting - Client Reactivation", "body": REACTIVATION_RECRUITING},
    "recruiting_outbound": {"niche": "recruiting", "name": "2026 Recruiting - Outbound (specialty roles)", "body": OUTBOUND_RECRUITING},
    "cleaning_reactivation": {"niche": "cleaning", "name": "2026 Cleaning - Client Reactivation", "body": REACTIVATION_CLEANING},
    "cleaning_trigger": {"niche": "cleaning", "name": "2026 Cleaning - Trigger Outbound", "body": TRIGGER_CLEANING},
    "bookkeeping_reactivation": {"niche": "bookkeeping", "name": "2026 Bookkeeping - Client Reactivation", "body": REACTIVATION_BOOKKEEPING},
    "bookkeeping_trigger": {"niche": "bookkeeping", "name": "2026 Bookkeeping - Trigger Outbound", "body": TRIGGER_BOOKKEEPING},
}


def key():
    for env in (ROOT / ".env", ROOT.parent.parent / "Agentic Worklfows" / ".env"):
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("INSTANTLY_API_KEY=") and line.split("=", 1)[1].strip():
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("INSTANTLY_API_KEY missing")


def call(method, path, body=None, tok=None):
    req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


def accounts(tok):
    out, after = [], None
    while True:
        d = call("GET", f"accounts?limit=100" + (f"&starting_after={after}" if after else ""), tok=tok)
        out += d.get("items", []); after = d.get("next_starting_after")
        if not after: break
    return out


def check(tok):
    acc = accounts(tok)
    print(f"inboxes: {len(acc)}")
    for a in acc:
        print(f"  {a.get('email'):40s} status={a.get('status')} warmup={a.get('warmup_status')} daily_limit={a.get('daily_limit')}")
    camps = call("GET", "campaigns?limit=100", tok=tok).get("items", [])
    print(f"campaigns: {len(camps)}")
    for c in camps: print(f"  {c.get('id')} | {c.get('name')} | status={c.get('status')}")
    return acc, camps


def setup(tok):
    acc = accounts(tok)
    emails = [a["email"] for a in acc]
    if not emails: sys.exit("no inboxes on the workspace")
    for e in emails:
        call("PATCH", f"accounts/{e}", {"daily_limit": PER_INBOX_DAILY}, tok)
    print(f"capped {len(emails)} inboxes at {PER_INBOX_DAILY}/day")
    per_campaign = (len(emails) * PER_INBOX_DAILY) // len(CAMPAIGNS)
    ids = {}
    for ckey, cfg in CAMPAIGNS.items():
        body = {
            "name": cfg["name"],
            "campaign_schedule": SCHEDULE,
            "sequences": [{"steps": [{"type": "email", "delay": 0, "variants": [{"subject": SUBJECT, "body": cfg["body"]}]}]}],
            "email_list": emails,
            "daily_limit": per_campaign,
            "email_gap": 10,
            "text_only": True,
            "stop_on_reply": True,
            "link_tracking": False,
            "open_tracking": False,
            "insert_unsubscribe_header": True,
            "prioritize_new_leads": False,
        }
        r = call("POST", "campaigns", body, tok)
        ids[ckey] = r["id"]
        print(f"created {cfg['name']} -> {r['id']} (daily cap {per_campaign})")
    (ROOT / "instantly_campaigns.json").write_text(json.dumps(ids, indent=1))


SUFFIX = re.compile(r"[,.]?\s*\b(l\.?l\.?c\.?|inc\.?|incorporated|p\.?l\.?l\.?c\.?|p\.?c\.?|l\.?l\.?p\.?|corp\.?|corporation|ltd\.?|co\.?|company|cpa'?s?|cpas|pa)\b\.?\s*$", re.I)
ACR = {"Cpa": "CPA", "Cpas": "CPAs", "Hvac": "HVAC", "It": "IT", "Hr": "HR", "Usa": "USA", "Nyc": "NYC", "Ai": "AI"}


def clean_company(n):
    """'Posses & Chasan Cpa's Pllc' -> 'Posses & Chasan'; legal suffixes off, acronyms upper, no dangling '&'."""
    raw = (n or "").strip(); n = raw
    for _ in range(3):
        n2 = SUFFIX.sub("", n).strip(" ,.-")
        if re.search(r"(&|\band)$", n2): break          # keep "X & Company" / "X & Co" intact
        n = n2
    n = re.sub(r"\bco\.?$", "Company", n, flags=re.I)
    return " ".join(ACR.get(w, w) for w in n.split()) or raw


ALLOWED_ESP = {"google", "other", "zoho"}  # Lorenzo 2026-09-29: no Microsoft-hosted leads (deliverability); free Yahoo mailboxes stay out too


def push(tok, day_csv):
    ids = json.loads((ROOT / "instantly_campaigns.json").read_text())
    master = {}
    for r in csv.DictReader(open(ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv", encoding="utf-8-sig")):
        master[r.get("lead_id") or r.get("email")] = r
    rows = list(csv.DictReader(open(day_csv, encoding="utf-8-sig")))
    by_niche = {n: [k for k, c in CAMPAIGNS.items() if c["niche"] == n] for n in {c["niche"] for c in CAMPAIGNS.values()}}
    counter, assigned = {}, {}
    no_camp = sorted({r["campaign"] for r in rows if r["campaign"] not in by_niche})
    if no_camp: print(f"  no Instantly campaign yet for {no_camp}: those rows stay on the sheet only")
    rows = [r for r in rows if r["campaign"] in by_niche]
    for r in rows:  # round-robin within each niche, in send order
        n = r["campaign"]; i = counter.get(n, 0); assigned[r["lead_id"]] = by_niche[n][i % len(by_niche[n])]; counter[n] = i + 1
    sent, skipped, per = 0, [], {}
    from personalize.esp import esp_of, prime, save as esp_save
    prime([master.get(r["lead_id"], {}).get("email", "") for r in rows])
    esp_skipped = {}
    for r in rows:
        m = master.get(r["lead_id"])
        if not m or not m.get("email"): skipped.append(r["lead_id"]); continue
        e = esp_of(m["email"])
        if e not in ALLOWED_ESP: esp_skipped[e] = esp_skipped.get(e, 0) + 1; continue
        spec = r.get("specialty") or "your clients'"
        ck = assigned[r["lead_id"]]; per[ck] = per.get(ck, 0) + 1
        body = {"campaign": ids[ck], "email": m["email"], "first_name": r.get("first_name") or m.get("first_name", ""),
                "last_name": m.get("last_name", ""), "company_name": clean_company(r.get("company_name") or m.get("company_name", "")),
                "personalization": r["personalization"], "skip_if_in_workspace": True,
                "custom_variables": {"personalization": r["personalization"], "specialty": spec, "lead_id": r["lead_id"], "mv_result": m.get("mv_result", "")}}
        call("POST", "leads", body, tok); sent += 1
        if sent % 50 == 0: print(f"  {sent}/{len(rows)}"); time.sleep(1)
    esp_save()
    print(f"pushed {sent} leads; skipped {len(skipped)} with no email {skipped[:5]}; skipped by mailbox provider {esp_skipped} (allowed: {sorted(ALLOWED_ESP)})")
    for ck, n in per.items(): print(f"  {CAMPAIGNS[ck]['name']}: {n}")


# ---- AI-agents offer (six campaigns created by the ai_agents change-set; ids in their OWN file) ----
AI_NICHE_TO_KEY = {"bookkeeping": "bookkeeping_ai", "insurance_broker": "insurance_broker_ai",
                   "landscaping": "landscaping_ai", "marketing_agency": "marketing_agency_ai",
                   "msp": "msp_ai", "pest_control": "pest_control_ai"}
BULK_ADD_MAX = 1000          # POST leads/add takes 1-1000 leads per call
BULK_PAUSE_S = 2.0


def _bump(d, k):
    d[k] = d.get(k, 0) + 1


def _write_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, default=str))


CAMPAIGN_STATUS = {0: "draft", 1: "ACTIVE", 2: "paused", 3: "completed", 4: "running subsequences",
                   -99: "suspended", -1: "accounts unhealthy", -2: "bounce protect"}


def _campaign_statuses(api, ids):
    """{campaign key: status int, or None when it could not be read}. GETs only."""
    out = {}
    for ck, cid in ids.items():
        if cid.startswith("<missing:"):
            out[ck] = None
            continue
        try:
            out[ck] = (api("GET", f"campaigns/{cid}") or {}).get("status")
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported, then the caller decides
            print(f"  {ck}: GET campaigns/{cid} failed: {str(exc)[:200]}")
            out[ck] = None
    return out


def _utc_ts(s):
    """An Instantly ISO timestamp ('2026-09-30T12:00:00.123Z') as an aware UTC datetime, or None."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def created_by_this_push(found, sent, pre_existing_ids, started_at):
    """Split the campaign's leads whose email this push sent into
    ({email: id} created by this push, {email: {id, reason}} that were not).
    A lead counts as created only if its id was not in the campaign before the
    first add and, when it carries timestamp_created, that is >= started_at."""
    start = _utc_ts(started_at)
    created, not_created = {}, {}
    for l in found:
        em = (l.get("email") or "").strip().lower()
        if em not in sent or not l.get("id"):
            continue
        if l["id"] in pre_existing_ids:
            not_created[em] = {"id": l["id"], "reason": "in the campaign before this push"}
            continue
        if l.get("timestamp_created") is not None:
            ts = _utc_ts(l["timestamp_created"])
            if ts is None or start is None or ts < start:
                not_created[em] = {"id": l["id"], "reason": "timestamp_created %s before the push start %s"
                                   % (l["timestamp_created"], started_at)}
                continue
        created[em] = l["id"]
    return created, not_created


def _verify_push(api, ids, record):
    """After a live push: read each campaign's leads, record the Instantly id of
    every lead this push created there (the rollback list: not in `pre_existing`,
    created at or after the push start) and print one pushed lead's custom
    variables per campaign. Reads only."""
    import slots_daily as sd
    print("verification (reads only):")
    for ck, camp in record["campaigns"].items():
        sent = {l["email"].strip().lower() for l in camp["sent"]}
        if not sent:
            continue
        try:
            found = sd.list_campaign_leads(api, [ids[ck]]).get(ids[ck], [])
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - the push record already exists
            camp["verify_error"] = str(exc)[:300]
            print(f"  {ck}: leads/list failed ({exc}); resolve ids by hand before any rollback")
            continue
        pre_ids = {p["id"] for p in camp.get("pre_existing", [])}
        camp["instantly_ids"], camp["not_created_by_this_push"] = created_by_this_push(
            found, sent, pre_ids, record["push_started_at"])
        print(f"  {ck}: {len(camp['instantly_ids'])} of {len(sent)} sent emails created in the campaign by this push"
              f"; {len(camp['not_created_by_this_push'])} sent email(s) were already there (not in the rollback list)")
        if not camp["instantly_ids"]:
            continue
        email, lid = sorted(camp["instantly_ids"].items())[0]
        try:
            got = api("GET", f"leads/{lid}") or {}
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            print(f"    GET leads/{lid} failed: {exc}")
            continue
        cv = sd._vars_view(got)
        camp["verified_lead"] = {"id": lid, "email": email, "variables": cv}
        print(f"    {email} ({lid}): {json.dumps(cv)}")
        missing = [k for k in ("personalization", "lead_id", "slot1", "slot2", "slot_date") if not cv.get(k)]
        if missing:
            print(f"    !! MISSING on the read-back: {missing}")


def push_ai_agents(tok, day_csvs, dry_run=False, ids_file=None, call_fn=None, now=None, free_fn=None,
                   master_path=None, esp=None, sleep=time.sleep, limit_per_campaign=None, record_dir=None,
                   allow_active=False):
    """Push day files into the six AI-agents campaigns with {{slot1}}/{{slot2}} set.
    Never writes instantly_campaigns.json and never activates anything.
    limit_per_campaign keeps only the first N leads per campaign (a rehearsal).
    GETs the six campaigns first; a live push into an ACTIVE campaign (status 1),
    or one whose status cannot be read, exits 2 unless allow_active.
    A live push writes logs/push_ai_<ts>.json before the first add (start time,
    each campaign's pre_existing leads), then every email/lead_id sent per
    campaign, Instantly's returned counts, and the Instantly ids this push created."""
    import slots_daily as sd
    call_fn = call_fn or call
    try:
        ids = sd.load_ai_ids(ids_file)
    except SystemExit as exc:
        if not dry_run:
            raise
        print(f"  WARNING (dry-run only): {exc}; using placeholder ids")
        ids = {k: f"<missing:{k}>" for k in sd.AI_CAMPAIGN_KEYS}
    master = {}
    for r in csv.DictReader(open(master_path or ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv", encoding="utf-8-sig")):
        master[r.get("lead_id") or r.get("email")] = r

    skipped, per_file, kept, seen_ids, seen_emails = {}, {}, [], set(), set()
    for path in day_csvs:
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        per_file[str(path)] = len(rows)
        for r in rows:
            ck = AI_NICHE_TO_KEY.get((r.get("campaign") or "").strip())
            if not ck: _bump(skipped, f"other niche ({r.get('campaign')})"); continue
            if not (r.get("personalization") or "").strip(): _bump(skipped, "empty personalization"); continue
            if (r.get("tier") or "").strip().lower() == "skip": _bump(skipped, "skip tier"); continue
            m = master.get(r.get("lead_id"))
            if not m or not m.get("email"): _bump(skipped, "no email in master"); continue
            em = m["email"].strip().lower()
            if r["lead_id"] in seen_ids or em in seen_emails: _bump(skipped, "duplicate"); continue
            seen_ids.add(r["lead_id"]); seen_emails.add(em)
            kept.append((ck, r, m))

    if esp is None:
        from personalize.esp import esp_of, prime, save as esp_save
        prime([m["email"] for _, _, m in kept])
    else:
        esp_of, esp_save = esp, (lambda: None)
    allowed = []
    for ck, r, m in kept:
        e = esp_of(m["email"])
        if e not in ALLOWED_ESP: _bump(skipped, f"esp {e}"); continue
        allowed.append((ck, r, m))
    esp_save()

    now = now or sd.datetime.now(sd.TZ)
    send_day = sd.next_send_day(now)
    free = (free_fn or sd.ghl_free_slots)(now)
    try:
        day1, day2, source = sd.compute_slots(send_day, free, now)  # once per run
    except sd.SlotError as exc:
        raise SystemExit(f"ERROR: {exc}")

    leads = {}
    for ck, r, m in allowed:
        cv = {"personalization": r["personalization"], "specialty": r.get("specialty") or "your clients'",
              "lead_id": r["lead_id"], "mv_result": m.get("mv_result", "")}
        cv.update(sd.slot_vars_for(m["email"], send_day, day1, day2))
        leads.setdefault(ck, []).append({
            "email": m["email"], "first_name": r.get("first_name") or m.get("first_name", ""),
            "last_name": m.get("last_name", ""),
            "company_name": clean_company(r.get("company_name") or m.get("company_name", "")),
            "personalization": r["personalization"], "custom_variables": cv})
    if limit_per_campaign is not None:
        for ck in list(leads):
            over = len(leads[ck]) - limit_per_campaign
            if over > 0:
                leads[ck] = leads[ck][:limit_per_campaign]
                skipped[f"over --limit-per-campaign {limit_per_campaign}"] = (
                    skipped.get(f"over --limit-per-campaign {limit_per_campaign}", 0) + over)

    print("rows per file:")
    for f, n in per_file.items(): print(f"  {Path(f).name}: {n}")
    print(f"total rows {sum(per_file.values())}; to push {sum(len(v) for v in leads.values())}")
    print("per campaign:")
    for ck in sd.AI_CAMPAIGN_KEYS: print(f"  {ck:20s} {len(leads.get(ck, []))}  ({ids[ck]})")
    print("skipped by reason:")
    shown = dict.fromkeys(("skip tier", "empty personalization", "no email in master", "duplicate"), 0)
    shown.update(skipped)
    for k, n in sorted(shown.items(), key=lambda x: -x[1]): print(f"  {k}: {n}")
    if source != "ghl":
        sd.print_fallback_banner(source)
    print(f"send day {send_day} ({send_day.strftime('%A')}), slot source: {source}")
    print(f"  slot1 options: {[sd.fmt_slot(x) for x in day1]}")
    print(f"  slot2 options: {[sd.fmt_slot(x, zone=True) for x in day2]}")
    summary = {"per_file": per_file, "per_campaign": {k: len(v) for k, v in leads.items()}, "skipped": skipped,
               "source": source, "send_day": send_day.isoformat(), "leads": leads, "ids": ids, "results": []}

    # The no-MODE-gate decision assumes the campaigns are drafts: check before any add (GETs only).
    statuses = _campaign_statuses(lambda m, p, b=None: call_fn(m, p, b, tok), ids)
    summary["campaign_status"] = statuses
    print("campaign status (GET campaigns/{id}):")
    for ck in sd.AI_CAMPAIGN_KEYS:
        st = statuses.get(ck)
        label = "unreadable" if st is None else f"{st} {CAMPAIGN_STATUS.get(st, '?')}"
        print(f"  {ck:20s} {label}{'   <- receives leads' if leads.get(ck) else ''}")
    active = [ck for ck in sd.AI_CAMPAIGN_KEYS if leads.get(ck) and statuses.get(ck) == 1]
    unknown = [ck for ck in sd.AI_CAMPAIGN_KEYS if leads.get(ck) and statuses.get(ck) is None]
    if active or unknown:
        why = (f"ACTIVE campaign(s) {active} would start mailing the new leads" if active else "") + \
              ("; " if active and unknown else "") + \
              (f"status of {unknown} could not be read (draft not confirmed)" if unknown else "")
        if allow_active:
            print(f"  WARNING: {why}; going ahead because --allow-active was passed")
        elif dry_run:
            print(f"  WARNING: {why}. A live push would be refused (exit 2) without --allow-active.")
        else:
            print(f"refused: {why}. The push has no MODE gate only because it adds to drafts; "
                  f"pass --allow-active to push anyway. Nothing written.")
            raise SystemExit(2)

    if dry_run:
        samples = [(ck, l) for ck, ls in leads.items() for l in ls][:2]
        for ck, l in samples:
            print(f"sample body ({ck}):")
            print(json.dumps({"campaign_id": ids[ck], "skip_if_in_workspace": True, "leads": [l]}, indent=1))
        print("dry-run: nothing written")
        return summary

    stamp = sd.datetime.now(sd.TZ).strftime("%Y%m%dT%H%M%S")
    record_path, n = Path(record_dir or ROOT / "logs") / f"push_ai_{stamp}.json", 1
    while record_path.exists():
        n += 1
        record_path = record_path.with_name(f"push_ai_{stamp}_{n}.json")
    from datetime import timezone
    started = sd.datetime.now(timezone.utc)
    started = started.replace(microsecond=started.microsecond // 1000 * 1000)  # Instantly stamps milliseconds
    record = {"kind": "push_ai", "ts": sd.datetime.now(sd.TZ).isoformat(), "files": [str(f) for f in day_csvs],
              "push_started_at": started.isoformat().replace("+00:00", "Z"),
              "send_day": send_day.isoformat(), "source": source, "limit_per_campaign": limit_per_campaign,
              "allow_active": allow_active, "campaign_status": statuses,
              "campaigns": {ck: {"campaign_id": ids[ck], "pre_existing": [], "sent": [], "results": []}
                            for ck in sd.AI_CAMPAIGN_KEYS if leads.get(ck)}}
    # every lead already in a target campaign, read before the first add: a rollback
    # deletes only ids that are NOT in this list, even after a crash mid-push
    api = lambda m, p, b=None: call_fn(m, p, b, tok)  # noqa: E731
    for ck, camp in record["campaigns"].items():
        try:
            found = sd.list_campaign_leads(api, [ids[ck]]).get(ids[ck], [])
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - no safe rollback without this list
            print(f"refused: listing {ck}'s existing leads failed ({str(exc)[:200]}); nothing written")
            raise SystemExit(1)
        camp["pre_existing"] = [{"id": l.get("id"), "email": (l.get("email") or "").strip().lower()}
                                for l in found if l.get("id")]
        print(f"  {ck}: {len(camp['pre_existing'])} lead(s) already in the campaign (saved as pre_existing)")
    _write_record(record_path, record)
    summary["record"] = str(record_path)
    print(f"push record (written before the first add): {record_path}")
    for ck in sd.AI_CAMPAIGN_KEYS:
        ls = leads.get(ck, [])
        for i in range(0, len(ls), BULK_ADD_MAX):
            chunk = ls[i:i + BULK_ADD_MAX]
            # recorded before the call, so a crash mid-push still leaves the rollback list
            record["campaigns"][ck]["sent"].extend(
                {"email": l["email"], "lead_id": l["custom_variables"]["lead_id"]} for l in chunk)
            _write_record(record_path, record)
            res = call_fn("POST", "leads/add", {"campaign_id": ids[ck], "leads": chunk, "skip_if_in_workspace": True}, tok) or {}
            counts = {k: res.get(k) for k in (
                "total_sent", "leads_uploaded", "skipped_count", "duplicated_leads", "in_blocklist",
                "invalid_email_count", "duplicate_email_count", "remaining_in_plan")}
            summary["results"].append({"campaign": ck, **counts})
            record["campaigns"][ck]["results"].append({"batch": i // BULK_ADD_MAX + 1, **counts,
                                                       "response": res})
            _write_record(record_path, record)
            print(f"  {ck} batch {i // BULK_ADD_MAX + 1}: sent {res.get('total_sent')}, uploaded {res.get('leads_uploaded')}, "
                  f"skipped (in workspace) {res.get('skipped_count')}, already in campaign {res.get('duplicated_leads')}, "
                  f"blocklist {res.get('in_blocklist')}, invalid {res.get('invalid_email_count')}, "
                  f"dup in payload {res.get('duplicate_email_count')}")
            sleep(BULK_PAUSE_S)
    print(f"push record: {record_path}")
    _verify_push(api, ids, record)
    _write_record(record_path, record)
    print("campaigns NOT activated (Lorenzo turns them on by hand)")
    return summary


def activate(tok):
    ids = json.loads((ROOT / "instantly_campaigns.json").read_text())
    for ck, cid in ids.items():
        call("POST", f"campaigns/{cid}/activate", {}, tok); print(f"activated {CAMPAIGNS[ck]['name']} {cid}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true"); p.add_argument("--setup", action="store_true")
    p.add_argument("--push", nargs="+"); p.add_argument("--activate", action="store_true")
    p.add_argument("--offer", choices=["ai_agents"], help="ai_agents: push into the six AI-agents campaigns (ids from --ids-file)")
    p.add_argument("--dry-run", action="store_true", help="with --offer ai_agents: print what would be pushed, write nothing")
    p.add_argument("--ids-file", help="with --offer ai_agents: campaign ids JSON (default instantly_campaigns_ai_agents.json)")
    p.add_argument("--limit-per-campaign", type=int, metavar="N",
                   help="with --offer ai_agents: push at most N leads per campaign (N=1 is the first live rehearsal)")
    p.add_argument("--allow-active", action="store_true",
                   help="with --offer ai_agents: push even if a target campaign is active (status 1) or its status is unreadable")
    a = p.parse_args(argv)
    # every refusal happens here, before key() or any call: --setup and --activate are live writes on the OLD campaigns
    if a.setup and (a.offer or a.dry_run): p.error("--setup cannot be combined with --offer or --dry-run (it writes live)")
    if a.activate and a.dry_run: p.error("--activate cannot be combined with --dry-run (it writes live)")
    if a.offer == "ai_agents" and a.activate: p.error("--activate is never allowed with --offer ai_agents")
    if a.offer != "ai_agents" and (a.dry_run or a.ids_file or a.limit_per_campaign is not None or a.allow_active):
        p.error("--dry-run/--ids-file/--limit-per-campaign/--allow-active only work with --offer ai_agents")
    if a.limit_per_campaign is not None and a.limit_per_campaign < 1: p.error("--limit-per-campaign must be >= 1")
    if a.offer == "ai_agents" and not a.push: p.error("--offer ai_agents needs --push <day csv> [...]")
    if a.push and a.offer != "ai_agents" and len(a.push) != 1: p.error("--push takes one file unless --offer ai_agents")
    tok = key()
    if a.check: check(tok)
    if a.setup: setup(tok)
    if a.push and a.offer == "ai_agents":
        push_ai_agents(tok, a.push, dry_run=a.dry_run, ids_file=a.ids_file, limit_per_campaign=a.limit_per_campaign,
                       allow_active=a.allow_active)
    elif a.push: push(tok, a.push[0])
    if a.activate: activate(tok)
    if not any([a.check, a.setup, a.push, a.activate]): p.print_help()


if __name__ == "__main__":
    main()
