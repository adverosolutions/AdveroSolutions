#!/usr/bin/env python3
"""Reply intake rules (Lorenzo via COO, 2026-11-02 4:05 PM CT, after the Marco miss).

1. POSITIVE labels: interested, reschedule, no-show/apology, asking for times or
   availability, time accepted/picked, booking, questions. Positive = URGENT alert
   to COO (priority:true) so Lorenzo sees it in COO chat within 5 min; write alert_ts.
2. A human reply NEVER gets booking.times_refresh or any automated template.
   times_refresh is only for the no-pick-after-1-business-day automation (no inbound).
   Human replies go to a hold card + alert instead.
3. check_alerts(): every positive row in handled.jsonl must have alert_ts.

Usage:
  reply_rules.py classify LABEL [BODY]     -> {"positive": bool, ...}
  reply_rules.py guard TEMPLATE human|automation  -> exit 1 if blocked
  reply_rules.py check-alerts [--since ISO] -> rows missing alert_ts (exit 1 if any)
Internal only. Never sends anything.
"""
import json, re, sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
HANDLED = Path.home() / "advero/state/handled.jsonl"
# Date this rule began; rows before it are reported as legacy, not flagged.
RULE_START = datetime(2026, 11, 2, 0, 0, tzinfo=CT)

NEGATIVE = re.compile(r"unsub|opt_out|not_interested|negative|hostile|wrong_person|"
                      r"business_closed|ooo|out_of_office|auto_reply|bounce|machine|stop", re.I)
POSITIVE = re.compile(r"positive|interest|reschedul|no_?show|apolog|time|availab|"
                      r"book|meeting|call_request|question|pricing|send_info|later", re.I)
BODY_POSITIVE = re.compile(r"\b(reschedul\w*|apolog\w*|sorry|missed|no[- ]show|"
                           r"availability|available|what times?|other times?|"
                           r"afternoon|morning|next week|interested|call me|let'?s talk)\b|\?", re.I)
AUTOMATED_TEMPLATES = re.compile(r"times_refresh|^booking\.|^nurture\.|^post_proposal\.|^followup\.", re.I)


def is_positive(label, body=""):
    label = label or ""
    if NEGATIVE.search(label):
        return False
    if POSITIVE.search(label):
        return True
    return bool(body and BODY_POSITIVE.search(body))


def template_allowed(template, source):
    """source: 'human' (lead wrote it) or 'automation' (no inbound). Human -> no templates."""
    if source == "human" and AUTOMATED_TEMPLATES.search(template or ""):
        return False
    return True


def _ts(r):
    for k in ("at_ct", "timestamp_email"):
        v = r.get(k)
        if v:
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return d if d.tzinfo else d.replace(tzinfo=CT)
            except ValueError:
                pass
    return None


def check_alerts(since=RULE_START, path=HANDLED):
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    # latest row per email_id wins (later rows may add alert_ts)
    alerted = {r.get("email_id") for r in rows if r.get("alert_ts")}
    missing, legacy, seen = [], 0, set()
    for r in rows:
        eid = r.get("email_id")
        if eid in seen or not is_positive(r.get("label"), r.get("body_stripped", "")):
            continue
        seen.add(eid)
        if eid in alerted:
            continue
        t = _ts(r)
        if t and t < since:
            legacy += 1
            continue
        missing.append({"email_id": eid, "lead": r.get("lead"), "label": r.get("label"),
                        "at_ct": r.get("at_ct"), "action": r.get("action")})
    return {"missing_alert_ts": missing, "count": len(missing), "legacy_pre_rule": legacy,
            "flag_coo_priority": bool(missing)}


def main(a):
    if a[:1] == ["classify"] and len(a) >= 2:
        p = is_positive(a[1], a[2] if len(a) > 2 else "")
        print(json.dumps({"label": a[1], "positive": p,
                          "route": "URGENT alert to COO (priority:true) + hold card" if p else "normal"}))
        return 0
    if a[:1] == ["guard"] and len(a) == 3:
        ok = template_allowed(a[1], a[2])
        print(json.dumps({"template": a[1], "source": a[2], "allowed": ok,
                          "instead": None if ok else "hold card + URGENT alert to COO"}))
        return 0 if ok else 1
    if a[:1] == ["check-alerts"]:
        since = RULE_START
        if "--since" in a:
            since = datetime.fromisoformat(a[a.index("--since") + 1])
        r = check_alerts(since)
        print(json.dumps(r, indent=2))
        return 1 if r["count"] else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
