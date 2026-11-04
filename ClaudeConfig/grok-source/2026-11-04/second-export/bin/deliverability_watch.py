#!/usr/bin/env python3
"""Read-only Instantly deliverability watch for AdveroSolutions.

GET requests only. Never changes campaigns, inboxes, warmup, settings,
webhooks, leads or billing. Never creates or runs inbox placement tests
(those cost credits); it only reads results of tests that already exist.

Prints one JSON summary to stdout.
Exit 0 = no alerts, 2 = ALERT (hard threshold crossed), 1 = pull error.
Soft signals (zero replies at >300 sent) are listed under "soft_alerts"
and do not change the exit code.

Usage:
  ~/advero/bin/deliverability_watch.py [--snapshot PATH] [--no-placement] [--no-state]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
BASE = "https://api.instantly.ai/api/v2"
STATE = Path("/home/box/advero/state/deliverability_watch_state.json")
REPORTS = Path("/home/box/advero/state/reports")
OLD12_DOMAINS = {"adveromedia.com", "myadvero.com", "proadvero.com", "theadvero.com"}

# Thresholds
BOUNCE_TODAY_PCT = 2.0
BOUNCE_TODAY_MIN_SENT = 50
BOUNCE_7D_PCT = 3.0
WARMUP_MIN = 90
WARMUP_DROP = 5
INBOX_BOUNCES_TODAY = 3
ZERO_REPLY_MIN_SENT = 300

ACCOUNT_STATUS = {1: "active", 2: "paused", -1: "connection_error",
                  -2: "soft_bounce_error", -3: "sending_error"}
WARMUP_STATUS = {0: "paused", 1: "active", -1: "banned",
                 -2: "spam_folder_unknown", -3: "permanent_suspension"}
CAMPAIGN_STATUS = {0: "draft", 1: "active", 2: "paused", 3: "completed",
                   4: "running_subsequences", -99: "account_suspended",
                   -1: "accounts_unhealthy", -2: "bounce_protect"}


def load_key() -> str:
    spec = importlib.util.spec_from_file_location(
        "lbs", "/home/box/advero/bin/_load_box_secrets.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.apply()
    k = os.environ.get("INSTANTLY_API_KEY")
    if not k:
        raise SystemExit("INSTANTLY_API_KEY is not set")
    return k


KEY = None


def get(path: str, params=None):
    """GET only. No other HTTP method exists in this script."""
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, method="GET", headers={
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; AdveroBot/1.0)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(f"GET {path} -> HTTP {e.code}: {e.read().decode()[:200]}")


def paged(path: str, params=None, cap=20):
    params = dict(params or {})
    params.setdefault("limit", 100)
    out = []
    for _ in range(cap):
        d = get(path, params)
        items = d.get("items", []) if isinstance(d, dict) else (d or [])
        out += items
        nxt = d.get("next_starting_after") if isinstance(d, dict) else None
        if not nxt or not items:
            break
        params["starting_after"] = nxt
    return out


def pct(n, d):
    return round(100.0 * n / d, 2) if d else None


def main() -> int:
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", help="also write the JSON summary here")
    ap.add_argument("--no-placement", action="store_true",
                    help="skip reading past inbox placement test results")
    ap.add_argument("--no-state", action="store_true",
                    help="do not update the state file (dry run)")
    a = ap.parse_args()
    KEY = load_key()

    now = datetime.now(CT)
    today = now.date()
    d7 = today - timedelta(days=6)
    alerts, soft, notes = [], [], []

    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text())
        except Exception:
            prev = {}

    # ---------- campaigns ----------
    camps = paged("/campaigns")
    an_today = get("/campaigns/analytics", {"start_date": str(today), "end_date": str(today)}) or []
    an_7d = get("/campaigns/analytics", {"start_date": str(d7), "end_date": str(today)}) or []
    t_by = {x["campaign_id"]: x for x in an_today}
    w_by = {x["campaign_id"]: x for x in an_7d}
    prev_camp = prev.get("campaign_status", {})

    campaigns_out = []
    watched_inboxes = set()
    for c in camps:
        cid, name, st = c["id"], c["name"], c.get("status")
        is_launch = name.startswith("Launch ")
        t, w = t_by.get(cid, {}), w_by.get(cid, {})
        sent_t, b_t = t.get("emails_sent_count", 0), t.get("bounced_count", 0)
        sent_w, b_w = w.get("emails_sent_count", 0), w.get("bounced_count", 0)
        rel = st in (1, 4) or is_launch or sent_w > 0 or (st is not None and st < 0)
        if not rel:
            continue
        if st in (1, 4):
            watched_inboxes.update(c.get("email_list") or [])
        row = {
            "id": cid, "name": name, "status": CAMPAIGN_STATUS.get(st, st),
            "inboxes": len(c.get("email_list") or []), "daily_limit": c.get("daily_limit"),
            "today": {"sent": sent_t, "bounced": b_t, "bounce_rate_pct": pct(b_t, sent_t),
                      "replies_unique": t.get("reply_count_unique", 0),
                      "reply_rate_pct": pct(t.get("reply_count_unique", 0), sent_t),
                      "auto_replies": t.get("reply_count_automatic_unique", 0),
                      "unsubscribed": t.get("unsubscribed_count", 0),
                      "opportunities": t.get("total_opportunities", 0)},
            "7d": {"sent": sent_w, "bounced": b_w, "bounce_rate_pct": pct(b_w, sent_w),
                   "replies_unique": w.get("reply_count_unique", 0),
                   "reply_rate_pct": pct(w.get("reply_count_unique", 0), sent_w),
                   "unsubscribed": w.get("unsubscribed_count", 0)},
        }
        campaigns_out.append(row)
        if sent_t >= BOUNCE_TODAY_MIN_SENT and pct(b_t, sent_t) > BOUNCE_TODAY_PCT:
            alerts.append(f"BOUNCE_TODAY {name}: {b_t}/{sent_t} = {pct(b_t, sent_t)}% (>2% at 50+ sent)")
        if sent_w and pct(b_w, sent_w) > BOUNCE_7D_PCT:
            alerts.append(f"BOUNCE_7D {name}: {b_w}/{sent_w} = {pct(b_w, sent_w)}% (>3%)")
        if sent_t > ZERO_REPLY_MIN_SENT and t.get("reply_count_unique", 0) == 0:
            soft.append(f"ZERO_REPLIES_TODAY {name}: 0 replies at {sent_t} sent")
        if st is not None and st < 0:
            alerts.append(f"CAMPAIGN_ERROR {name}: status {CAMPAIGN_STATUS.get(st, st)}")
        was = prev_camp.get(cid)
        if was in ("active", "running_subsequences") and st not in (1, 4, 3):
            alerts.append(f"CAMPAIGN_STOPPED {name}: was {was}, now {CAMPAIGN_STATUS.get(st, st)}")
        elif is_launch and name.endswith("| Live") and st not in (1, 4, 3):
            alerts.append(f"CAMPAIGN_NOT_ACTIVE {name}: status {CAMPAIGN_STATUS.get(st, st)}")

    # ---------- inboxes ----------
    accts = paged("/accounts")
    prev_w = prev.get("warmup_score", {})
    daily = {}
    emails_all = [x["email"] for x in accts]
    for i in range(0, len(emails_all), 10):
        batch = emails_all[i:i + 10]
        try:
            rows = get("/accounts/analytics/daily", {"start_date": str(today), "end_date": str(today), "emails": batch}) or []
        except RuntimeError as e:
            notes.append(f"per-inbox analytics batch failed: {e}")
            continue
        for r in rows:
            if r.get("date") == str(today):
                daily[r["email_account"]] = r

    inbox_out = []
    for x in accts:
        em = x["email"]
        st, ws, sc = x.get("status"), x.get("warmup_status"), x.get("stat_warmup_score")
        d = daily.get(em, {})
        errs = {k: v for k, v in x.items() if ("error" in k.lower() or "status_message" in k.lower()) and v}
        row = {"email": em, "status": ACCOUNT_STATUS.get(st, st),
               "warmup": WARMUP_STATUS.get(ws, ws), "warmup_health": sc,
               "daily_limit": x.get("daily_limit"), "sent_today": d.get("sent", 0),
               "bounced_today": d.get("bounced", 0), "replies_today": d.get("unique_replies", 0),
               "in_active_campaign": em in watched_inboxes,
               "old12": em.split("@")[1] in OLD12_DOMAINS}
        if errs:
            row["errors"] = errs
        inbox_out.append(row)
        if st != 1:
            alerts.append(f"INBOX_STATUS {em}: {ACCOUNT_STATUS.get(st, st)}")
        if errs:
            # Instantly keeps old error text on the account after it recovers.
            # Alert only if the error timestamp is recent (<72h) or unparseable;
            # older errors on an active account go to notes.
            import re
            m = re.search(r"Timestamp: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})Z", json.dumps(errs))
            err_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if m else None
            stale = bool(err_ts and st == 1 and (datetime.now(timezone.utc) - err_ts) > timedelta(hours=72))
            row["error_stale"] = stale
            if err_ts:
                row["error_time_ct"] = err_ts.astimezone(CT).isoformat(timespec="minutes")
            msg = json.dumps(errs)[:160]
            if stale:
                notes.append(f"STALE_INBOX_ERROR {em} (status active, error from {row['error_time_ct']}, sent today {d.get('sent', 0)}): {msg}")
            else:
                alerts.append(f"INBOX_ERROR {em}: {msg}")
        if ws not in (1,) and em in watched_inboxes:
            alerts.append(f"WARMUP_STATUS {em}: {WARMUP_STATUS.get(ws, ws)}")
        if isinstance(sc, (int, float)):
            if sc < WARMUP_MIN:
                alerts.append(f"WARMUP_LOW {em}: {sc} (<90)")
            p = prev_w.get(em)
            if isinstance(p, (int, float)) and p - sc >= WARMUP_DROP:
                alerts.append(f"WARMUP_DROP {em}: {p} -> {sc}")
        if row["bounced_today"] >= INBOX_BOUNCES_TODAY:
            alerts.append(f"INBOX_BOUNCES {em}: {row['bounced_today']} bounces today")

    # ---------- placement (read existing results only) ----------
    placement = {"free_signals": "Instantly exposes warmup health score per inbox (stat_warmup_score) and account status for free. Real inbox placement needs paid placement tests; this script never creates or runs one.",
                 "tests": []}
    if not a.no_placement:
        try:
            for tst in paged("/inbox-placement-tests"):
                res = paged("/inbox-placement-analytics", {"test_id": tst["id"]})
                n = len(res); spam = sum(1 for r in res if r.get("is_spam"))
                by_esp = {}
                for r in res:
                    k = {1: "google", 2: "microsoft"}.get(r.get("recipient_esp"), str(r.get("recipient_esp")))
                    e = by_esp.setdefault(k, {"inbox": 0, "spam": 0})
                    e["spam" if r.get("is_spam") else "inbox"] += 1
                senders = sorted({r.get("sender_email") for r in res})
                placement["tests"].append({"name": tst.get("name"), "id": tst["id"],
                    "created_utc": tst.get("timestamp_created"), "results": n,
                    "spam": spam, "inbox_pct": pct(n - spam, n), "by_recipient_esp": by_esp,
                    "senders": len(senders),
                    "senders_old12_only": all(s and s.split("@")[1] in OLD12_DOMAINS for s in senders)})
        except RuntimeError as e:
            notes.append(f"placement read failed: {e}")

    # ---------- baseline compare ----------
    baseline = None
    cands = sorted(REPORTS.glob("deliverability_20??-??-??.json"))
    if cands:
        try:
            b = json.loads(cands[-1].read_text())
            est = b.get("estate", {})
            baseline = {"file": cands[-1].name, "pulled_at": b.get("pulled_at_ct"),
                        "inbox_count": est.get("inbox_count"), "accounts_active": est.get("accounts_active"),
                        "warmup_health_100": est.get("warmup_health_100"),
                        "campaigns_by_status": est.get("campaigns_by_status")}
        except Exception as e:
            notes.append(f"baseline read failed: {e}")

    tot_sent = sum(c["today"]["sent"] for c in campaigns_out)
    tot_b = sum(c["today"]["bounced"] for c in campaigns_out)
    tot_r = sum(c["today"]["replies_unique"] for c in campaigns_out)
    act = [i for i in inbox_out if i["in_active_campaign"]]
    scores = [i["warmup_health"] for i in inbox_out if isinstance(i["warmup_health"], (int, float))]
    summary = {
        "generated_at_ct": now.isoformat(timespec="seconds"),
        "date_ct": str(today), "window_7d": [str(d7), str(today)],
        "read_only": True,
        "headline": {
            "campaigns_watched": len(campaigns_out),
            "campaigns_active": sum(1 for c in campaigns_out if c["status"] in ("active", "running_subsequences")),
            "sent_today": tot_sent, "bounced_today": tot_b, "bounce_rate_today_pct": pct(tot_b, tot_sent),
            "replies_unique_today": tot_r, "reply_rate_today_pct": pct(tot_r, tot_sent),
            "inboxes_total": len(inbox_out),
            "inboxes_active": sum(1 for i in inbox_out if i["status"] == "active"),
            "inboxes_in_active_campaigns": len(act),
            "warmup_health_min": min(scores) if scores else None,
            "inboxes_with_bounce_today": sum(1 for i in inbox_out if i["bounced_today"]),
            "max_inbox_bounces_today": max((i["bounced_today"] for i in inbox_out), default=0),
        },
        "alerts": alerts, "soft_alerts": soft, "notes": notes,
        "campaigns": campaigns_out,
        "inboxes": sorted(inbox_out, key=lambda i: (-i["bounced_today"], not i["in_active_campaign"], i["email"])),
        "placement": placement, "baseline": baseline,
        "thresholds": {"bounce_today_pct": BOUNCE_TODAY_PCT, "bounce_today_min_sent": BOUNCE_TODAY_MIN_SENT,
                       "bounce_7d_pct": BOUNCE_7D_PCT, "warmup_min": WARMUP_MIN, "warmup_drop": WARMUP_DROP,
                       "inbox_bounces_today": INBOX_BOUNCES_TODAY, "zero_reply_min_sent": ZERO_REPLY_MIN_SENT},
        "previous_run_ct": prev.get("last_run_ct"),
    }
    out = json.dumps(summary, indent=1)
    print(out)
    if a.snapshot:
        Path(a.snapshot).expanduser().write_text(out + "\n")
    if not a.no_state:
        STATE.write_text(json.dumps({
            "last_run_ct": summary["generated_at_ct"],
            "warmup_score": {i["email"]: i["warmup_health"] for i in inbox_out},
            "campaign_status": {c["id"]: c["status"] for c in campaigns_out},
            "last_alerts": alerts}, indent=1) + "\n")
    if alerts:
        print("ALERT:\n" + "\n".join("- " + x for x in alerts), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # pull error
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
