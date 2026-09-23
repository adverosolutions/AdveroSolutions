#!/usr/bin/env python3
"""Instantly (API v2) setup + daily lead push for the 2026 three-niche campaigns.

  python3 instantly_push.py --check                 # key + inboxes + campaigns
  python3 instantly_push.py --setup                 # cap every inbox at 25/day, create the 6 campaigns
  python3 instantly_push.py --push output/daily/day_<id>.csv   # upload that day's leads
  python3 instantly_push.py --activate              # start all 6 campaigns

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


def push(tok, day_csv):
    ids = json.loads((ROOT / "instantly_campaigns.json").read_text())
    master = {}
    for r in csv.DictReader(open(ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv", encoding="utf-8-sig")):
        master[r.get("lead_id") or r.get("email")] = r
    rows = list(csv.DictReader(open(day_csv, encoding="utf-8-sig")))
    by_niche = {n: [k for k, c in CAMPAIGNS.items() if c["niche"] == n] for n in {c["niche"] for c in CAMPAIGNS.values()}}
    counter, assigned = {}, {}
    for r in rows:  # round-robin within each niche, in send order
        n = r["campaign"]; i = counter.get(n, 0); assigned[r["lead_id"]] = by_niche[n][i % len(by_niche[n])]; counter[n] = i + 1
    sent, skipped, per = 0, [], {}
    for r in rows:
        m = master.get(r["lead_id"])
        if not m or not m.get("email"): skipped.append(r["lead_id"]); continue
        spec = r.get("specialty") or "your clients'"
        ck = assigned[r["lead_id"]]; per[ck] = per.get(ck, 0) + 1
        body = {"campaign": ids[ck], "email": m["email"], "first_name": r.get("first_name") or m.get("first_name", ""),
                "last_name": m.get("last_name", ""), "company_name": clean_company(r.get("company_name") or m.get("company_name", "")),
                "personalization": r["personalization"], "skip_if_in_workspace": True,
                "custom_variables": {"personalization": r["personalization"], "specialty": spec, "lead_id": r["lead_id"], "mv_result": m.get("mv_result", "")}}
        call("POST", "leads", body, tok); sent += 1
        if sent % 50 == 0: print(f"  {sent}/{len(rows)}"); time.sleep(1)
    print(f"pushed {sent} leads; skipped {len(skipped)} with no email {skipped[:5]}")
    for ck, n in per.items(): print(f"  {CAMPAIGNS[ck]['name']}: {n}")


def activate(tok):
    ids = json.loads((ROOT / "instantly_campaigns.json").read_text())
    for ck, cid in ids.items():
        call("POST", f"campaigns/{cid}/activate", {}, tok); print(f"activated {CAMPAIGNS[ck]['name']} {cid}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true"); p.add_argument("--setup", action="store_true")
    p.add_argument("--push"); p.add_argument("--activate", action="store_true")
    a = p.parse_args(); tok = key()
    if a.check: check(tok)
    if a.setup: setup(tok)
    if a.push: push(tok, a.push)
    if a.activate: activate(tok)
    if not any([a.check, a.setup, a.push, a.activate]): p.print_help()
