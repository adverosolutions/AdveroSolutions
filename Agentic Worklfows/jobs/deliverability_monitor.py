"""Five-level deliverability monitor (Blueprint M1; jobs O1 daily, O6 Friday audit).

    cd "Agentic Worklfows"
    python3 jobs/deliverability_monitor.py --dry-run                 # read-only, prints the card
    python3 jobs/deliverability_monitor.py --dry-run --level 1 3     # only those levels
    python3 jobs/deliverability_monitor.py --now                     # same + the ntfy card + change-set
    python3 jobs/deliverability_monitor.py --dry-run --as-of 2026-09-22T07:00:00-05:00 --json

Reads are live and always safe. Every *action* the monitor decides on is a
**proposal**: it is written to ``changesets/inbox_actions/<date>.json`` and
applied, if Lorenzo approves the diff, by
``changesets/inbox_actions/apply_inbox_actions.py --apply``. This job never
pauses an account and never patches a campaign, in shadow or in live. That is
deliberate: a monitor that both decides and executes is one bad threshold away
from pausing the whole sending fleet at 07:00 on a Monday.

Levels (M1)
  1  warm-up health per inbox + domain vitals (SPF/DKIM/DMARC/MX)   daily 07:00
  2  inbox placement seed tests                                     Monday  -> jobs/inbox_placement.py
  3  reply rate and bounce per inbox and per domain                 Friday
  4  auto-responder canary                                          Saturday -> jobs/autoresponder_canary.py
  5  positive-behaviour baseline campaign                           always on
  +  sudden-drop alert (7-day reply rate < 50% of the 4-week average), daily with level 1;
     DOMAIN-ONLY for now (owner decision R13): every inbox row abstains with the reason

Levels 2 and 4 live in their own jobs because each one owns a live write the
monitor must not make (a seed test costs credits; a canary sends mail). This
job *reads* what they recorded and folds it into the one card.

Every number comes from ``shared/thresholds.py``. There are no literals here.
"""
import argparse
import json
import logging
import os
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from shared import analytics  # noqa: E402
from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.settings import TZ  # noqa: E402

logger = logging.getLogger("jobs.deliverability_monitor")

JOB = "deliverability_monitor"
CHANGESET_DIR = BASE_DIR / "changesets" / "inbox_actions"

# Instantly account.status values (observed live 2026-09-22).
ACCOUNT_STATUS_ACTIVE = 1
ACCOUNT_STATUS_PAUSED = 2

ROLE_SENDING = "sending"       # in at least one campaign email_list
ROLE_INSURANCE = "insurance"   # warming, not in any email_list
ROLE_PAUSED = "paused"


# =========================================================================
# Reading the workspace
# =========================================================================

def chunked(seq: Sequence[Any], size: int) -> List[List[Any]]:
    """[1..n] -> list of lists of at most ``size``. size <= 0 means one chunk."""
    items = list(seq)
    if size <= 0:
        return [items] if items else []
    return [items[i:i + size] for i in range(0, len(items), size)]


def load_accounts(client: Any) -> List[Dict[str, Any]]:
    """Every account in the workspace, paged. 45 today (12 sending, 33 warming)."""
    walk = client.iterate("accounts", params={"limit": 100})
    rows = list(walk)
    if getattr(walk, "truncated", False):
        # A partial account list would make the monitor report on a subset and
        # silently call the rest healthy.
        raise RuntimeError("accounts walk truncated; refusing to report on a partial inbox list")
    if not rows:
        # An empty answer is never a real state for this workspace, and the
        # monitor used to render it as "0 inboxes, 0 proposals / No action
        # proposed", Job_Log status ok, default-priority push: a clean bill of
        # health for a fleet it could not read. An org-id change, a permissions
        # narrowing or a response-shape change all land here.
        raise RuntimeError(
            "GET /accounts returned zero accounts. This workspace has 45. An empty inbox list is an "
            "unreadable workspace, not a healthy one, so the run stops rather than reporting every "
            "inbox as fine.")
    return rows


def load_campaign_email_lists(client: Any, campaigns: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """{campaign_key: {'id', 'name', 'email_list', 'status'}} read from live."""
    campaigns = campaigns if campaigns is not None else settings.CAMPAIGNS
    out = OrderedDict()  # type: Dict[str, Dict[str, Any]]
    for key in sorted(campaigns):
        cfg = campaigns[key]
        camp = client.get_campaign(cfg["id"])
        out[key] = {
            "key": key,
            "id": cfg["id"],
            "name": camp.get("name") or cfg.get("name"),
            "status": camp.get("status"),
            "email_list": list(camp.get("email_list") or []),
            "daily_limit": camp.get("daily_limit"),
        }
    return out


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    # Python 3.9's fromisoformat rejects anything but 3 or 6 fractional digits.
    if "." in text:
        head, _, tail = text.partition(".")
        digits = ""
        rest = ""
        for i, ch in enumerate(tail):
            if ch.isdigit():
                digits += ch
            else:
                rest = tail[i:]
                break
        if digits:
            digits = (digits + "000000")[:6]
            text = "%s.%s%s" % (head, digits, rest)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_inbox_index(accounts: List[Dict[str, Any]],
                      campaign_lists: Dict[str, Dict[str, Any]],
                      now: datetime) -> List[Dict[str, Any]]:
    """One row per inbox with its role, domain, age and campaign membership."""
    membership = {}  # type: Dict[str, List[str]]
    for key, camp in campaign_lists.items():
        for email in camp.get("email_list") or []:
            membership.setdefault(email.strip().lower(), []).append(key)
    out = []
    for acc in accounts:
        email = (acc.get("email") or "").strip().lower()
        if not email:
            continue
        in_campaigns = sorted(membership.get(email, []))
        status = acc.get("status")
        if status == ACCOUNT_STATUS_PAUSED:
            role = ROLE_PAUSED
        elif in_campaigns:
            role = ROLE_SENDING
        else:
            role = ROLE_INSURANCE
        warmup_start = _parse_ts(acc.get("timestamp_warmup_start"))
        created = _parse_ts(acc.get("timestamp_created"))
        age_days = None
        if warmup_start is not None:
            age_days = (now - warmup_start).total_seconds() / 86400.0
        elif created is not None:
            age_days = (now - created).total_seconds() / 86400.0
        out.append({
            "email": email,
            "domain": TH.domain_of(email),
            "role": role,
            "status": status,
            "warmup_status": acc.get("warmup_status"),
            "daily_limit": acc.get("daily_limit"),
            "reported_warmup_score": acc.get("stat_warmup_score"),
            "warmup_start": acc.get("timestamp_warmup_start"),
            "created": acc.get("timestamp_created"),
            "warmup_age_days": round(age_days, 2) if age_days is not None else None,
            "in_campaigns": in_campaigns,
        })
    out.sort(key=lambda r: (r["role"] != ROLE_SENDING, r["domain"], r["email"]))
    return out


# =========================================================================
# Level 1 - warm-up health and domain vitals
# =========================================================================

def _read_post(client: Any, path: str, body: Dict[str, Any],
               method_name: Optional[str] = None, arg: Any = None) -> Any:
    """A POST that only reads, issued so a transient 5xx is retried like a GET.

    ``shared.instantly.READ_POST_PATHS`` lists the POSTs the client will retry,
    and ``accounts/test/vitals`` and the placement stats endpoint are not on it:
    both are reads, but the client cannot know that, so one 503 on vitals used
    to take the whole 07:00 run down with it. ``_request(..., retry=True)``
    says so explicitly at the call site. Falls back to ``_post`` for any client
    (a stub, a recorded transport) that does not expose ``_request``.
    """
    if method_name and hasattr(client, method_name):
        return getattr(client, method_name)(arg)
    if hasattr(client, "_request"):
        return client._request("POST", path, json=body, retry=True)
    return client._post(path, body)


def fetch_warmup(client: Any, emails: Sequence[str],
                 sleep: Callable[[float], None] = time.sleep) -> Dict[str, Dict[str, Any]]:
    """POST /accounts/warmup-analytics in chunks of at most 100 emails (M1 L1)."""
    out = {}  # type: Dict[str, Dict[str, Any]]
    batches = chunked(emails, TH.WARMUP_ANALYTICS_MAX_EMAILS_PER_CALL)
    for i, batch in enumerate(batches):
        data = client.warmup_analytics(list(batch)) or {}
        for email, agg in (data.get("aggregate_data") or {}).items():
            out[email.strip().lower()] = dict(agg)
        if i + 1 < len(batches):
            sleep(TH.API_CHUNK_SLEEP_SECONDS)
    return out


def fetch_vitals(client: Any, emails: Sequence[str],
                 sleep: Callable[[float], None] = time.sleep) -> Dict[str, Dict[str, Any]]:
    """POST /accounts/test/vitals. The answer is grouped BY DOMAIN, not by
    account: three inboxes on one domain produce one row. Returns
    {domain: {'mx','spf','dkim','dmarc','allPass','passed'}}."""
    out = {}  # type: Dict[str, Dict[str, Any]]
    batches = chunked(emails, TH.VITALS_MAX_ACCOUNTS_PER_CALL)
    for i, batch in enumerate(batches):
        data = _read_post(client, "accounts/test/vitals", {"accounts": list(batch)},
                          method_name="test_vitals", arg=list(batch))
        data = data or {}
        for bucket, passed in (("success_list", True), ("failure_list", False)):
            for row in data.get(bucket) or []:
                domain = (row.get("domain") or "").strip().lower()
                if not domain:
                    continue
                record = {k: bool(row.get(k)) for k in TH.VITALS_REQUIRED_RECORDS}
                record["allPass"] = bool(row.get("allPass"))
                record["passed"] = passed and record["allPass"]
                record["missing"] = [k for k in TH.VITALS_REQUIRED_RECORDS if not record.get(k)]
                out[domain] = record
        if i + 1 < len(batches):
            sleep(TH.API_CHUNK_SLEEP_SECONDS)
    return out


# Most actionable first. ``level1`` can attach more than one verdict to an
# inbox; this decides which one leads the row.
VERDICT_PRIORITY = ("health_emergency", "health_fail", "dns_fail", "unknown_health",
                    "unknown_vitals", "too_young")


def _primary_verdict(verdicts: Sequence[str]) -> str:
    for candidate in VERDICT_PRIORITY:
        if candidate in verdicts:
            return candidate
    return "ok"


def level1(inboxes: List[Dict[str, Any]], warmup: Dict[str, Dict[str, Any]],
           vitals: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Health per inbox + DNS per domain. Returns rows and findings.

    An inbox younger than WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT is reported but
    never failed: Instantly reports health 100 from the first hour, so an
    "unhealthy" verdict on a day-old inbox is noise, and the 33 inboxes that
    started warming on 2026-09-20 are the insurance this monitor exists to
    protect.
    """
    rows = []
    findings = []
    for inbox in inboxes:
        agg = warmup.get(inbox["email"]) or {}
        health = agg.get("health_score")
        if health is None:
            health = inbox.get("reported_warmup_score")
        vit = vitals.get(inbox["domain"]) or {}
        age = inbox.get("warmup_age_days")
        too_young = age is not None and age < TH.WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT
        row = {
            "email": inbox["email"],
            "domain": inbox["domain"],
            "role": inbox["role"],
            "health": health,
            "warmup_sent": agg.get("sent"),
            "warmup_landed_inbox": agg.get("landed_inbox"),
            "warmup_received": agg.get("received"),
            "warmup_age_days": age,
            "vitals": vit or None,
            "verdict": "ok",
            "verdicts": [],
            "reason": "",
        }
        # Verdicts ACCUMULATE. An inbox on a DKIM-less domain whose warm-up
        # health is also 94% used to report only the health number, because the
        # health branch overwrote both fields; the operator then chased the
        # inbox instead of the missing DNS record.
        verdicts = []  # type: List[str]
        reasons = []  # type: List[str]
        if not vit:
            verdicts.append("unknown_vitals")
            reasons.append("no vitals answer for %s" % inbox["domain"])
        elif vit.get("missing"):
            verdicts.append("dns_fail")
            reasons.append("missing DNS: %s" % ", ".join(vit["missing"]))
        if health is None:
            verdicts.append("unknown_health")
            reasons.append("no warm-up score")
        elif health < TH.WARMUP_HEALTH_EMERGENCY_PCT and not too_young:
            verdicts.append("health_emergency")
            reasons.append("warm-up health %.0f%% is below the never-send floor of %.0f%%"
                           % (health, TH.WARMUP_HEALTH_EMERGENCY_PCT))
        elif health < TH.WARMUP_HEALTH_MIN_PCT and not too_young:
            verdicts.append("health_fail")
            reasons.append("warm-up health %.0f%% is below %.0f%%" % (health, TH.WARMUP_HEALTH_MIN_PCT))
        elif health < TH.WARMUP_HEALTH_MIN_PCT and too_young:
            verdicts.append("too_young")
            reasons.append("warm-up health %.0f%% but only %.1f days of warm-up; no verdict before %d days"
                           % (health, age or 0.0, TH.WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT))
        if verdicts:
            row["verdicts"] = verdicts
            # The primary verdict is the most actionable one, so a DNS fault is
            # never hidden behind "too_young" and an emergency is never hidden
            # behind a DNS note.
            row["verdict"] = _primary_verdict(verdicts)
            row["reason"] = "; ".join(reasons)
        rows.append(row)
        if [v for v in verdicts if v != "too_young"]:
            findings.append(row)
    # A DNS fault is a domain fault: one finding per domain, not per inbox.
    domain_faults = OrderedDict()
    for domain in sorted(set(r["domain"] for r in rows)):
        vit = vitals.get(domain)
        if vit and vit.get("missing"):
            domain_faults[domain] = vit["missing"]
    return {"level": 1, "rows": rows, "findings": findings, "domain_dns_faults": domain_faults,
            "checked": len(rows), "vitals_domains": len(vitals)}


# =========================================================================
# Level 3 - reply rate and bounce (and the data the sudden-drop check reuses)
# =========================================================================

def real_replies(replies: Any, replies_automatic: Any) -> int:
    """Replies from a human, per GET /accounts/analytics/daily.

    **`replies` and `replies_automatic` are DISJOINT counters on this
    workspace, not nested.** Measured read-only 2026-09-22 over Sept 15-21:
    lorenzo@myadvero.com reports replies=0, replies_automatic=2, and
    lorenzo@proadvero.com reports replies=1, replies_automatic=3. Subtracting
    (which is what "excluding replies_automatic" reads like, and what M1 L3
    says in words) yields -2 real replies, which is impossible. Summed the
    other way the numbers land exactly on the measured workspace figures:
    22 replies / 1,800 sent = 1.2% real reply rate and 22 automatic = 1.2%,
    which is what Lorenzo measured by hand.

    So `replies` is ALREADY the real count. The subtraction is kept behind a
    constant rather than deleted, because a workspace or an API version that
    nests them would otherwise overcount replies and keep a dead inbox alive.
    """
    r = int(replies or 0)
    a = int(replies_automatic or 0)
    if getattr(TH, "REPLIES_INCLUDE_AUTOMATIC", False):
        return max(0, r - a)
    return max(0, r)


def window_dates(now: datetime, days: int, include_today: bool = False) -> List[str]:
    """The ``days`` complete CT days ending yesterday (or today).

    Level 1 runs at 07:00, when today has almost no sends; counting today would
    drag every rate toward zero and propose pausing the whole fleet every
    morning. The windows therefore end on the last complete day.
    """
    ct = now.astimezone(TZ)
    last = ct.date() if include_today else (ct - timedelta(days=1)).date()
    return [(last - timedelta(days=i)).isoformat() for i in range(days)][::-1]


def fetch_daily(client: Any, emails: Sequence[str], start_date: str, end_date: str,
                sleep: Callable[[float], None] = time.sleep) -> List[Dict[str, Any]]:
    """GET /accounts/analytics/daily, chunked over emails.

    This workspace answers HTTP 413 without an emails filter and the failure
    mode is a whole missing report, so the monitor never relies on the
    endpoint's own capacity: it asks for DAILY_ANALYTICS_CHUNK_EMAILS inboxes
    at a time and stitches the rows together.

    The chunking itself lives in ``shared.analytics`` now, because the inbox
    inventory, the daily metrics and the retro packet all read the same
    endpoint and each had its own copy of this loop.
    """
    return analytics.account_daily(
        client, emails, start_date, end_date,
        chunk=TH.DAILY_ANALYTICS_CHUNK_EMAILS,
        sleep=sleep, sleep_seconds=TH.API_CHUNK_SLEEP_SECONDS,
        # RAISE, not DEGRADE: a monitor that quietly reports a partial fleet is
        # a monitor that says "all clear" about inboxes it never read. The
        # caller catches and says so on the card.
        on_error=analytics.RAISE,
    ).rows


def aggregate_window(rows: List[Dict[str, Any]], dates: Sequence[str]) -> Dict[str, Counter]:
    """{inbox: Counter(sent, replies, replies_total, replies_automatic, bounced, days)}.

    ``replies`` is the PER-LEAD count, ``unique_replies`` (falling back to
    ``replies`` only on a row that lacks it), read through
    ``shared.analytics.real_replies``: the one definition the capacity
    inventory, the retro and DECISIONS J1 use. The monitor used to sum total
    ``replies``, so a lead who wrote back three times counted three times and
    the two 07:00 cards disagreed: on the recorded week lorenzov@theadvero.com
    (3 replies from 1 lead in 150 sends) passed here at 2.00% while the
    inventory flagged it at 0.67% (MKT-4). ``replies_total`` keeps the raw
    counter for display only.
    """
    wanted = set(dates)
    out = {}  # type: Dict[str, Counter]
    for row in rows:
        date = row.get("date")
        if date not in wanted:
            continue
        email = (row.get("email_account") or "").strip().lower()
        if not email:
            continue
        acc = out.setdefault(email, Counter())
        acc["sent"] += int(row.get("sent") or 0)
        acc["replies"] += analytics.real_replies(row, unique=True)
        acc["replies_total"] += int(row.get("replies") or 0)
        acc["replies_automatic"] += int(row.get("replies_automatic") or 0)
        acc["bounced"] += int(row.get("bounced") or 0)
        acc["days"] += 1
    return out


# The two level 3 rules, and the volume floor each one needs. They are judged
# INDEPENDENTLY: gating bounce behind the reply rule's 100-send floor made
# BOUNCE_RATE_MIN_SENT dead code and threw away an 80-send inbox bouncing at 10%.
RULE_REPLY = "reply_rate"
RULE_BOUNCE = "bounce_rate"
RULE_MIN_SENT = {RULE_REPLY: TH.REPLY_RATE_MIN_SENT, RULE_BOUNCE: TH.BOUNCE_RATE_MIN_SENT}


def _window_verdict(sent: int, real: int, bounced: int) -> Dict[str, Any]:
    reply_pct = TH.rate_pct(real, sent)
    bounce_pct = TH.rate_pct(bounced, sent)
    fails = []
    if sent >= TH.REPLY_RATE_MIN_SENT and reply_pct < TH.REPLY_RATE_MIN_PCT:
        fails.append(RULE_REPLY)
    if sent >= TH.BOUNCE_RATE_MIN_SENT and bounce_pct > TH.BOUNCE_RATE_MAX_PCT:
        fails.append(RULE_BOUNCE)
    return {"sent": sent, "real_replies": real, "bounced": bounced,
            "reply_pct": round(reply_pct, 3), "bounce_pct": round(bounce_pct, 3),
            "fails": fails,
            "judgeable": sent >= TH.REPLY_RATE_MIN_SENT,
            "judgeable_reply": sent >= TH.REPLY_RATE_MIN_SENT,
            "judgeable_bounce": sent >= TH.BOUNCE_RATE_MIN_SENT}


def level3(inboxes: List[Dict[str, Any]], rows: List[Dict[str, Any]], now: datetime,
           rules: Sequence[str] = (RULE_REPLY, RULE_BOUNCE)) -> Dict[str, Any]:
    """Per-inbox and per-domain reply / bounce audit over every window in
    REPLY_RATE_WINDOWS_DAYS.

    Two corrections to the original shape, both of which let a dead inbox pass:

    * **Each rule picks its own window.** The reply rule needs 100 sends, the
      bounce rule 50. Choosing one window for both made the bounce floor
      unreachable.
    * **Any judgeable window that fails, fails the inbox.** M1 L3 reads
      ">= 100 sent in 7 d or 14 d and < 1% real replies", which means either
      window failing is a failure. Judging only on the longest window let an
      inbox with 7 replies in the older week and zero in the recent one pass at
      2.00% on 14 days while its 7-day rate was 0.00%.

    ``rules`` narrows the audit. The daily run passes ``(RULE_BOUNCE,)`` so
    Section 6's Monday bounce audit is not six days late, and Friday passes
    both.
    """
    rules = tuple(rules)
    windows = {}  # type: Dict[int, Dict[str, Counter]]
    for days in TH.REPLY_RATE_WINDOWS_DAYS:
        windows[days] = aggregate_window(rows, window_dates(now, days))
    ordered_days = sorted(TH.REPLY_RATE_WINDOWS_DAYS)

    per_inbox = []
    for inbox in inboxes:
        if inbox["role"] == ROLE_INSURANCE:
            continue  # an inbox that has never sent a campaign email has no reply rate
        email = inbox["email"]
        by_window = OrderedDict()
        for days in ordered_days:
            acc = windows[days].get(email) or Counter()
            sent = int(acc["sent"])
            by_window[days] = _window_verdict(
                sent, real_replies(acc["replies"], acc["replies_automatic"]), int(acc["bounced"]))

        fails = []
        failed_on = OrderedDict()  # {rule: days that produced the failure}
        judged_on_rule = OrderedDict()  # {rule: longest judgeable window for it}
        for rule in (RULE_REPLY, RULE_BOUNCE):
            floor = RULE_MIN_SENT[rule]
            judgeable_days = [d for d in ordered_days if by_window[d]["sent"] >= floor]
            if judgeable_days:
                judged_on_rule[rule] = judgeable_days[-1]
            if rule not in rules:
                continue
            hit = [d for d in judgeable_days if rule in by_window[d]["fails"]]
            if hit:
                fails.append(rule)
                # Report the window that produced the verdict, shortest first:
                # "0.00% over 7 days" is the sharper statement.
                failed_on[rule] = hit[0]

        # The row's headline numbers come from the longest window with enough
        # volume for ANY rule, so an 80-send inbox still prints its 10% bounce
        # instead of "sent -, bounce -".
        any_judgeable = [d for d in ordered_days
                         if by_window[d]["sent"] >= min(RULE_MIN_SENT.values())]
        headline_days = any_judgeable[-1] if any_judgeable else None
        headline = by_window[headline_days] if headline_days else None
        thin = bool(headline and headline["sent"] < TH.REPLY_RATE_THIN_EVIDENCE_SENT)
        per_inbox.append({
            "email": email, "domain": inbox["domain"], "role": inbox["role"],
            "in_campaigns": inbox["in_campaigns"],
            "windows": {str(k): v for k, v in by_window.items()},
            # judged_on_days stays the reply rule's window, which is what the
            # reason line has always quoted.
            "judged_on_days": judged_on_rule.get(RULE_REPLY),
            "judged_on_days_bounce": judged_on_rule.get(RULE_BOUNCE),
            "failed_on_days": dict(failed_on),
            "headline_days": headline_days,
            "fails": fails,
            "rules_applied": list(rules),
            "thin_evidence": thin,
            "reply_pct": headline["reply_pct"] if headline else None,
            "bounce_pct": headline["bounce_pct"] if headline else None,
            "sent": headline["sent"] if headline else 0,
            "real_replies": headline["real_replies"] if headline else 0,
        })

    per_domain = OrderedDict()
    for row in per_inbox:
        d = per_domain.setdefault(row["domain"], {
            "domain": row["domain"], "inboxes": 0, "failing": 0, "sent": 0,
            "real_replies": 0, "bounced": 0, "emails": [], "failing_emails": [],
            "thin_failing_emails": []})
        d["inboxes"] += 1
        d["sent"] += row["sent"]
        d["real_replies"] += row["real_replies"]
        longest = row["headline_days"]
        if longest:
            d["bounced"] += row["windows"][str(longest)]["bounced"]
        d["emails"].append(row["email"])
        if row["fails"]:
            d["failing"] += 1
            d["failing_emails"].append(row["email"])
            if row["thin_evidence"]:
                d["thin_failing_emails"].append(row["email"])
    for d in per_domain.values():
        d["reply_pct"] = round(TH.rate_pct(d["real_replies"], d["sent"]), 3)
        d["bounce_pct"] = round(TH.rate_pct(d["bounced"], d["sent"]), 3)
        d["retire"] = bool(
            d["inboxes"] >= TH.DOMAIN_MIN_INBOXES_FOR_RETIRE
            and d["failing"] >= d["inboxes"] * TH.DOMAIN_RETIRE_FAIL_RATIO)
        # Retirement is permanent and Eric's rule is never to heal a domain, so
        # it may not be proposed at full severity off the same thin evidence
        # level 3 demotes for a single inbox. At 150 sends per inbox and a
        # 1.22% fleet rate, three individually healthy inboxes on one domain all
        # read under 1% about 9% of the time.
        d["thin_evidence"] = bool(d["thin_failing_emails"])
        d["retire_thin"] = bool(d["retire"] and d["thin_evidence"]
                                and TH.DOMAIN_RETIRE_REQUIRES_THICK_EVIDENCE)
    return {"level": 3, "per_inbox": per_inbox, "per_domain": list(per_domain.values()),
            "windows_days": list(TH.REPLY_RATE_WINDOWS_DAYS),
            "rules_applied": list(rules),
            "failing": [r for r in per_inbox if r["fails"]]}


# =========================================================================
# Sudden-drop alert
# =========================================================================

def _per_inbox_off_reason(r_sent: int, b_pct: float) -> str:
    """Why the per-inbox check abstains (owner decision R13), with the numbers."""
    week = TH.PER_INBOX_DAILY_LIMIT * TH.SENDING_DAYS_PER_WEEK
    needed_pct = 100.0 * TH.SUDDEN_DROP_MIN_EXPECTED_REPLIES / float(max(1, week))
    return ("per-inbox sudden drop is OFF, domain-only for now (owner decision R13): one inbox sends "
            "at most %d a week, and expecting %.0f replies from that needs a baseline of %.1f%% or "
            "more; this inbox's baseline is %.2f%% on %d recent sends. The domain check still runs."
            % (week, TH.SUDDEN_DROP_MIN_EXPECTED_REPLIES, needed_pct, b_pct, r_sent))


def sudden_drop(inboxes: List[Dict[str, Any]], rows: List[Dict[str, Any]], now: datetime,
                per_inbox: Optional[bool] = None) -> Dict[str, Any]:
    """7-day real reply rate below SUDDEN_DROP_RATIO of the 4-week average.

    Domain-only by default (``TH.SUDDEN_DROP_PER_INBOX_ENABLED``, owner decision
    R13): every inbox row is still computed and reported, but it ABSTAINS with
    the reason, so the card never implies an armed per-inbox alert that the
    volume makes impossible to trip. ``per_inbox=True`` runs the old per-inbox
    logic (kept for the redesign and pinned by tests).

    The 4-week window INCLUDES the recent 7 days, which is what "its 4-week
    average" says and which makes the test conservative: a collapse drags its
    own baseline down, so the drop has to be larger before this fires. For a
    check whose proposed action is "pause immediately", erring toward silence
    is the right direction.
    """
    if per_inbox is None:
        per_inbox = bool(getattr(TH, "SUDDEN_DROP_PER_INBOX_ENABLED", False))
    recent_dates = window_dates(now, TH.SUDDEN_DROP_RECENT_DAYS)
    base_dates = window_dates(now, TH.SUDDEN_DROP_BASELINE_DAYS)
    recent = aggregate_window(rows, recent_dates)
    base = aggregate_window(rows, base_dates)

    def _scan(keyfn, label):
        out = []
        groups = OrderedDict()
        for inbox in inboxes:
            if inbox["role"] == ROLE_INSURANCE:
                continue
            groups.setdefault(keyfn(inbox), []).append(inbox["email"])
        for name, emails in groups.items():
            r = Counter()
            b = Counter()
            for e in emails:
                r.update(recent.get(e) or Counter())
                b.update(base.get(e) or Counter())
            r_sent, b_sent = int(r["sent"]), int(b["sent"])
            r_real = real_replies(r["replies"], r["replies_automatic"])
            b_real = real_replies(b["replies"], b["replies_automatic"])
            r_pct, b_pct = TH.rate_pct(r_real, r_sent), TH.rate_pct(b_real, b_sent)
            expected = (b_pct / 100.0) * r_sent
            row = {"scope": label, "name": name, "recent_sent": r_sent, "recent_pct": round(r_pct, 3),
                   "baseline_sent": b_sent, "baseline_pct": round(b_pct, 3),
                   "baseline_extra_sent": b_sent - r_sent,
                   "expected_replies": round(expected, 2),
                   "ratio": round(r_pct / b_pct, 3) if b_pct else None,
                   "thin_evidence": r_sent < TH.SUDDEN_DROP_THIN_EVIDENCE_SENT,
                   "dropped": False, "abstained": True, "reason": ""}
            if label == "inbox" and not per_inbox:
                row["disabled"] = True
                row["reason"] = _per_inbox_off_reason(r_sent, b_pct)
            elif b_sent and b_sent == r_sent:
                # Every send in the 4-week window is also in the 7-day window, so
                # the baseline IS the recent period and the ratio is 1.0 by
                # construction. Without this branch the check reports "within
                # range" and reads as a passed health check, when in fact it
                # cannot fire at all. True today: the active inboxes only began
                # sending 2026-09-15.
                row["reason"] = ("the %d-day baseline holds no sends outside the last %d days "
                                 "(%d = %d), so this check cannot fire yet"
                                 % (TH.SUDDEN_DROP_BASELINE_DAYS, TH.SUDDEN_DROP_RECENT_DAYS,
                                    b_sent, r_sent))
            elif b_sent < TH.SUDDEN_DROP_MIN_BASELINE_SENT:
                row["reason"] = ("baseline has only %d sends in %d days (need %d); no verdict"
                                 % (b_sent, TH.SUDDEN_DROP_BASELINE_DAYS, TH.SUDDEN_DROP_MIN_BASELINE_SENT))
            elif b_pct < TH.SUDDEN_DROP_MIN_BASELINE_RATE_PCT:
                row["reason"] = ("baseline reply rate %.2f%% is under the %.2f%% floor; halving it is noise"
                                 % (b_pct, TH.SUDDEN_DROP_MIN_BASELINE_RATE_PCT))
            elif r_sent < TH.SUDDEN_DROP_MIN_RECENT_SENT:
                row["reason"] = ("only %d sends in the last %d days (need %d); no verdict"
                                 % (r_sent, TH.SUDDEN_DROP_RECENT_DAYS, TH.SUDDEN_DROP_MIN_RECENT_SENT))
            elif expected < TH.SUDDEN_DROP_MIN_EXPECTED_REPLIES:
                # Volume is not the same thing as signal. At a 1.22% baseline,
                # 50 sends expects 0.6 replies, so zero replies is the modal
                # outcome and always reads as a 100% drop. This check proposes
                # an immediate pause, so it abstains until the recent window
                # expects enough replies for "none arrived" to mean something.
                row["reason"] = ("the last %d days expect only %.1f replies at the %.2f%% baseline "
                                 "(need %.0f); zero replies here is an ordinary quiet week, not a drop"
                                 % (TH.SUDDEN_DROP_RECENT_DAYS, expected, b_pct,
                                    TH.SUDDEN_DROP_MIN_EXPECTED_REPLIES))
            elif r_pct < b_pct * TH.SUDDEN_DROP_RATIO:
                row["dropped"] = True
                row["abstained"] = False
                row["reason"] = ("7-day reply rate %.2f%% is below %.0f%% of the %d-day average %.2f%% "
                                 "(%d sends in the recent window, %.1f replies expected)"
                                 % (r_pct, TH.SUDDEN_DROP_RATIO * 100, TH.SUDDEN_DROP_BASELINE_DAYS,
                                    b_pct, r_sent, expected))
            else:
                row["abstained"] = False
                row["reason"] = "within range"
            out.append(row)
        return out

    inbox_rows = _scan(lambda i: i["email"], "inbox")
    domain_rows = _scan(lambda i: i["domain"], "domain")
    dropped = [r for r in inbox_rows + domain_rows if r["dropped"]]
    # The rows that COULD have fired: a switched-off scope is not evidence of
    # anything, so it never makes the check look usable.
    armed = domain_rows + (inbox_rows if per_inbox else [])
    every = inbox_rows + domain_rows
    abstained = [r for r in armed if r["abstained"]]
    return {"check": "sudden_drop", "inboxes": inbox_rows, "domains": domain_rows,
            "dropped": dropped, "abstained": abstained,
            "per_inbox_enabled": bool(per_inbox),
            "per_inbox_off_reason": (None if per_inbox else
                                     (inbox_rows[0]["reason"] if inbox_rows
                                      else _per_inbox_off_reason(0, 0.0))),
            # The whole check is meaningless, not merely quiet, when nothing
            # could have fired. The card says so rather than printing "0 flagged".
            "usable": bool(armed) and len(abstained) < len(armed),
            "recent_days": TH.SUDDEN_DROP_RECENT_DAYS,
            "baseline_days": TH.SUDDEN_DROP_BASELINE_DAYS}


def fetch_recent_bounces(client: Any, now: datetime,
                         campaigns: Optional[Dict[str, Any]] = None,
                         hours: Optional[int] = None) -> Dict[str, Any]:
    """Bounced leads from the last ``hours``, attributed to the inbox that sent.

    POST /leads/list with FILTER_VAL_BOUNCED per campaign. The sending inbox is
    in ``status_summary.lastStep.from`` (verified live 2026-09-22).
    """
    campaigns = campaigns if campaigns is not None else settings.CAMPAIGNS
    hours = TH.BOUNCE_LOOKBACK_HOURS if hours is None else hours
    cutoff = now - timedelta(hours=hours)
    per_inbox = Counter()
    recent = []
    total = 0
    for key in sorted(campaigns):
        cid = campaigns[key]["id"]
        walk = client.iterate("leads/list", body={"filter": TH.BOUNCED_LEADS_FILTER,
                                                  "campaign": cid, "limit": 100})
        for lead in walk:
            total += 1
            ts = _parse_ts(lead.get("timestamp_last_contact"))
            summary = lead.get("status_summary") or {}
            sender = ((summary.get("lastStep") or {}).get("from") or "").strip().lower()
            if ts is not None and ts >= cutoff:
                per_inbox[sender] += 1
                recent.append({"email": lead.get("email"), "campaign": key,
                               "sent_from": sender, "at": lead.get("timestamp_last_contact")})
    return {"hours": hours, "total_bounced_all_time": total, "recent": recent,
            "per_inbox": dict(per_inbox)}


def scan_bounce_signatures(client: Any, max_pages: Optional[int] = None) -> Dict[str, Any]:
    """Look for 550 / "reported as spam" in what the mailboxes received.

    Instantly does not surface delivery-status notifications in the Unibox
    (115 received messages on 2026-09-22, zero NDRs), so this usually finds
    nothing. It still runs, because when a provider DOES route a rejection
    into the mailbox that text is the fastest signal that a domain is being
    blocked rather than merely ignored. A miss is reported as a miss, never as
    a clean bill of health.
    """
    max_pages = TH.CANARY_HARVEST_MAX_PAGES if max_pages is None else max_pages
    hits = []
    scanned = 0
    walk = client.iterate("emails", params={"email_type": "received", "limit": 100},
                          max_pages=max_pages)
    for row in walk:
        scanned += 1
        blob = " ".join([
            str(row.get("subject") or ""), str(row.get("content_preview") or ""),
            str(row.get("from_address_email") or ""),
        ]).lower()
        for sig in TH.BOUNCE_SIGNATURES:
            if sig in blob:
                hits.append({"eaccount": row.get("eaccount"), "from": row.get("from_address_email"),
                             "subject": row.get("subject"), "signature": sig})
                break
    partial = bool(getattr(walk, "truncated", False))
    note = ""
    if not hits:
        note = ("no delivery-status notifications are visible through GET /emails on this "
                "workspace; an empty result is not evidence of clean delivery")
    if partial:
        # This scan tolerates a partial read where the canary harvest refuses
        # one, because a miss here is already reported as a miss. It must still
        # say so: "no NDRs found" over the newest N messages is a much weaker
        # statement than "no NDRs found".
        note = ("scanned the newest %d received message(s) only (the walk stopped at max_pages=%d "
                "with the cursor still open). %s" % (scanned, max_pages, note)).strip()
    return {"scanned": scanned, "hits": hits, "partial": partial, "max_pages": max_pages,
            "note": note}


# =========================================================================
# Level 5 - positive-behaviour baseline campaign
# =========================================================================

def load_level5_spec(directory: Path = CHANGESET_DIR) -> Optional[Dict[str, Any]]:
    """The baseline-campaign spec, if Lorenzo has created the campaign and
    written its id into the change-set folder. The monitor never creates it."""
    path = Path(directory) / TH.LEVEL5_SPEC_FILENAME
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("level 5 spec at %s is unreadable: %s", path, exc)
        return None


def level5(client: Any, inboxes: List[Dict[str, Any]], spec: Optional[Dict[str, Any]],
           now: datetime) -> Dict[str, Any]:
    """Per-inbox reply rate on the always-on partner/peer campaign.

    An inbox whose baseline rate falls below LEVEL5_DROP_RATIO of the campaign
    median takes a level 3 action (M1 L5). Without a live campaign id this
    reports ``not_configured`` and proposes nothing; the spec file is the
    handoff point, and runbooks/deliverability.md says how to create it.
    """
    if not spec or not spec.get("campaign_id"):
        return {"level": 5, "configured": False,
                "note": ("no %s with a live campaign_id in %s; level 5 is a spec only"
                         % (TH.LEVEL5_SPEC_FILENAME, CHANGESET_DIR)),
                "rows": [], "failing": []}
    start = spec.get("start_date") or window_dates(now, TH.SUDDEN_DROP_BASELINE_DAYS)[0]
    end = window_dates(now, 1)[0]
    emails = [i["email"] for i in inboxes if i["role"] != ROLE_INSURANCE]
    rows_raw = fetch_daily(client, emails, start, end)
    # The baseline campaign's own rows are the only ones that count, and the
    # daily endpoint is per account, not per account+campaign: when the spec
    # names inboxes, trust it; otherwise fall back to every sending inbox.
    agg = aggregate_window(rows_raw, [r.get("date") for r in rows_raw])
    rates = []
    rows = []
    for email in emails:
        acc = agg.get(email) or Counter()
        sent = int(acc["sent"])
        real = real_replies(acc["replies"], acc["replies_automatic"])
        pct = TH.rate_pct(real, sent)
        rows.append({"email": email, "sent": sent, "real_replies": real, "reply_pct": round(pct, 3),
                     "judgeable": sent >= TH.LEVEL5_MIN_SENT})
        if sent >= TH.LEVEL5_MIN_SENT:
            rates.append(pct)
    median = 0.0
    if rates:
        ordered = sorted(rates)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
    failing = []
    for row in rows:
        row["median_pct"] = round(median, 3)
        row["fails"] = bool(row["judgeable"] and median and row["reply_pct"] < median * TH.LEVEL5_DROP_RATIO)
        if row["fails"]:
            failing.append(row)
    return {"level": 5, "configured": True, "campaign_id": spec.get("campaign_id"),
            "median_pct": round(median, 3), "rows": rows, "failing": failing,
            # The daily analytics endpoint is per account, not per account and
            # campaign, so this rate is the inbox's whole cold-outreach traffic
            # and NOT the baseline campaign's. Carried on the result so the
            # proposal wording and the card cannot quietly call it a baseline.
            "mixed_traffic": True,
            "note": ("measured on every campaign's traffic: GET /accounts/analytics/daily cannot be "
                     "filtered to campaign %s" % spec.get("campaign_id"))}


# =========================================================================
# Proposals and the change-set
# =========================================================================

def eligible_insurance(inboxes: List[Dict[str, Any]], warmup: Dict[str, Dict[str, Any]],
                       vitals: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insurance inboxes that could be swapped into a campaign email_list today.

    M2: warm-up runs 21 days. An inbox that started warming on 2026-09-20 is
    not insurance on 2026-09-22, it is a liability, and promoting it would burn
    the capacity the Oct 11 plan depends on.
    """
    out = []
    for inbox in inboxes:
        if inbox["role"] != ROLE_INSURANCE:
            continue
        age = inbox.get("warmup_age_days")
        health = (warmup.get(inbox["email"]) or {}).get("health_score", inbox.get("reported_warmup_score"))
        vit = vitals.get(inbox["domain"]) or {}
        reasons = []
        if age is None or age < TH.WARMUP_DAYS_BEFORE_PROMOTION:
            reasons.append("warming %s of %d days" % (
                "?" if age is None else ("%.1f" % age), TH.WARMUP_DAYS_BEFORE_PROMOTION))
        if health is None or health < TH.WARMUP_HEALTH_MIN_PCT:
            reasons.append("health %s" % ("?" if health is None else ("%.0f%%" % health)))
        if vit.get("missing"):
            reasons.append("DNS missing %s" % ",".join(vit["missing"]))
        if not reasons:
            out.append(inbox)
    out.sort(key=lambda i: (-(i.get("warmup_age_days") or 0), i["email"]))
    return out


def _proposal_id(kind: str, target: str) -> str:
    return "%s:%s" % (kind, target)


# Which proposals describe the same decision about the same object. Deduping on
# the proposal id (kind:target) let level 1 and level 3 condemn one inbox twice,
# under two different kinds, and hand each copy a different insurance inbox: two
# spares burned on one failure, and the second proposal dead on arrival because
# applying the first made its expected_before stale.
PROPOSAL_FAMILY = {
    "pause_inbox": "inbox_removal",
    "remove_from_email_list": "inbox_removal",
    "pause_domain": "domain_removal",
    "retire_domain": "domain_removal",
    "fix_dns": "dns",
    "stop_using_domain": "registrar",
}
# Within a family, the most COMPLETE action wins, whatever its severity: pausing
# an inbox already carries the email_list patch that removing it would make, so
# the pause supersedes the removal and the removal's reason is folded in.
KIND_COMPLETENESS = {"pause_inbox": 0, "remove_from_email_list": 1,
                     "pause_domain": 0, "retire_domain": 1}


class _InsuranceAllocator(object):
    """Hands out insurance inboxes, once each, respecting M2's per-domain cap.

    Two rules the old closure did not have:

    * **Only an inbox that is actually in a campaign gets a replacement.** A
      failing inbox that is in no email_list has nothing to swap, so claiming a
      spare for it produced a proposal with zero actions while a real sending
      inbox was reported as having "NO replacement available".
    * **M2's three-inboxes-per-domain cap is enforced.** A swap that puts a
      fourth inbox from one domain into a campaign trades one deliverability
      problem for another, and MAX_INBOXES_PER_DOMAIN existed but was never read.
    """

    def __init__(self, insurance: List[Dict[str, Any]], campaign_lists: Dict[str, Dict[str, Any]]):
        self._pool = list(insurance)
        self._claimed = set()  # type: set
        # {campaign_key: {domain: count}} of what is in each list right now,
        # updated as this run hands out replacements.
        self._per_campaign_domains = {}  # type: Dict[str, Counter]
        for key, camp in (campaign_lists or {}).items():
            counter = Counter()
            for email in camp.get("email_list") or []:
                counter[TH.domain_of(email)] += 1
            self._per_campaign_domains[key] = counter

    def claim(self, failing_email: str, in_campaigns: Sequence[str]) -> Optional[str]:
        campaigns = list(in_campaigns or [])
        if not campaigns:
            return None  # nothing to swap it into
        failing_domain = TH.domain_of(failing_email)
        for cand in self._pool:
            if cand["email"] in self._claimed:
                continue
            domain = cand["domain"]
            if not self._fits(domain, failing_domain, campaigns):
                continue
            self._claimed.add(cand["email"])
            for key in campaigns:
                counter = self._per_campaign_domains.setdefault(key, Counter())
                counter[domain] += 1
                if failing_domain:
                    counter[failing_domain] = max(0, counter[failing_domain] - 1)
            return cand["email"]
        return None

    def _fits(self, domain: str, failing_domain: str, campaigns: Sequence[str]) -> bool:
        for key in campaigns:
            counter = self._per_campaign_domains.get(key) or Counter()
            present = counter.get(domain, 0)
            if domain == failing_domain:
                present -= 1  # the failing inbox is leaving this list
            if present + 1 > TH.MAX_INBOXES_PER_DOMAIN:
                return False
        return True

    @property
    def claimed(self) -> List[str]:
        return sorted(self._claimed)


def build_proposals(l1: Dict[str, Any], l3: Optional[Dict[str, Any]], l5: Optional[Dict[str, Any]],
                    drop: Optional[Dict[str, Any]], inboxes: List[Dict[str, Any]],
                    campaign_lists: Dict[str, Dict[str, Any]],
                    insurance: List[Dict[str, Any]],
                    placement: Optional[Dict[str, Any]] = None,
                    canary: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Turn findings into concrete, reviewable actions.

    Every proposal names the exact API call the apply script would make, the
    evidence behind it, and - when it removes sending capacity - what replaces
    it. A pause with no replacement is still proposed, flagged
    ``replacement: null``, because hiding a capacity problem is worse than
    reporting one Lorenzo has to decide about.

    Order of operations matters and is the fix for two defects: findings are
    collected first, **deduplicated per target**, and only then handed an
    insurance inbox and an action list. Allocating during collection burned one
    spare per finding rather than one per inbox, and rebuilding the actions
    after the merge is the only way the surviving proposal's ``expected_before``
    can be right.
    """
    by_email = {i["email"]: i for i in inboxes}
    allocator = _InsuranceAllocator(insurance, campaign_lists)
    raw = []  # type: List[Dict[str, Any]]

    def _add(kind, target, severity, level, reason, spec, evidence, **extra):
        row = {"id": _proposal_id(kind, target), "kind": kind, "target": target,
               "severity": severity, "level": level, "reason": reason,
               "evidence": evidence, "_spec": spec}
        row.update(extra)
        raw.append(row)
        return row

    # ---- Level 1: health and DNS -----------------------------------------
    for domain, missing in (l1.get("domain_dns_faults") or {}).items():
        affected = sorted(i["email"] for i in inboxes if i["domain"] == domain and i["role"] != ROLE_PAUSED)
        _add("fix_dns", domain, "critical", 1,
             "%s is missing %s; every inbox on it is affected and pausing one inbox fixes nothing"
             % (domain, ", ".join(missing)),
             ("manual", [{"system": "dns", "op": "add_records", "domain": domain, "records": missing}]),
             {"missing": missing, "inboxes": affected}, manual=True)

    for row in l1.get("findings") or []:
        verdicts = row.get("verdicts") or [row.get("verdict")]
        if "health_emergency" in verdicts or "health_fail" in verdicts:
            email = row["email"]
            sev = "critical" if "health_emergency" in verdicts else "high"
            _add("pause_inbox", email, sev, 1, row["reason"], ("pause_inbox", email),
                 {"health": row["health"], "warmup_age_days": row["warmup_age_days"],
                  "warmup_sent": row["warmup_sent"], "warmup_landed_inbox": row["warmup_landed_inbox"],
                  "verdicts": verdicts})

    # ---- Level 3: reply rate and bounce ----------------------------------
    if l3:
        retired_domains = set(d["domain"] for d in l3.get("per_domain") or [] if d.get("retire"))
        for domain in sorted(retired_domains):
            d = [x for x in l3["per_domain"] if x["domain"] == domain][0]
            affected = sorted(set(
                key for e in d["failing_emails"] for key in (by_email.get(e, {}).get("in_campaigns") or [])))
            thin = bool(d.get("retire_thin"))
            severity = TH.demote("high") if thin else "high"
            reason = ("every one of the %d sending inboxes on %s fails the level 3 audit (%d replies on "
                      "%d sends, %.2f%%; bounce %.2f%%); M1 L3 and Eric's rule are to retire the domain "
                      "and never try to heal it"
                      % (d["inboxes"], domain, d["real_replies"], d["sent"], d["reply_pct"],
                         d["bounce_pct"]))
            note = None
            if thin:
                note = ("thin evidence: %s under %d sends, which is where a single reply moves an "
                        "inbox across the 1%% line. Three healthy inboxes on one domain read under 1%% "
                        "about one Friday in ten at today's volume, so this is demoted until the "
                        "sample is real." % (", ".join(d.get("thin_failing_emails") or []),
                                             TH.REPLY_RATE_THIN_EVIDENCE_SENT))
            # One patch per campaign removing ALL of the domain's inboxes at once. Emitting one
            # action per inbox would make the second action's expected_before stale the moment
            # the first one applied, and the apply script would refuse the rest of its own
            # change-set.
            _add("retire_domain", domain, severity, 3, reason,
                 ("remove_many", list(d["failing_emails"]), affected),
                 {k: d[k] for k in ("inboxes", "failing", "sent", "real_replies", "reply_pct",
                                    "bounce_pct")},
                 thin_evidence=thin, note=note)
            # The registrar step is its own proposal. Bundled into the one above
            # it was permanently unapplyable: the apply script marks any manual
            # op blocked, and a proposal that mixes blocked and executable
            # actions is refused whole, so the single most important protective
            # action in M1 L3 could only ever be done by hand in the UI.
            _add("stop_using_domain", domain, severity, 3,
                 "stop sending from %s for good once the email_list patches above are applied; "
                 "Eric's rule is never to heal a retired domain" % domain,
                 ("manual", [{"system": "manual", "op": "stop_using_domain", "domain": domain}]),
                 {"domain": domain, "follows": _proposal_id("retire_domain", domain)}, manual=True)
        for row in l3.get("failing") or []:
            email = row["email"]
            if row["domain"] in retired_domains:
                continue  # the domain proposal already covers it
            reasons = []
            failed_on = row.get("failed_on_days") or {}
            if RULE_REPLY in row["fails"]:
                days = failed_on.get(RULE_REPLY) or row.get("judged_on_days")
                window = row["windows"].get(str(days)) or {}
                reasons.append("%.2f%% real replies on %d sends in %s days (floor %.1f%% at %d sends)"
                               % (window.get("reply_pct", row["reply_pct"] or 0.0),
                                  window.get("sent", row["sent"]), days,
                                  TH.REPLY_RATE_MIN_PCT, TH.REPLY_RATE_MIN_SENT))
            if RULE_BOUNCE in row["fails"]:
                days = failed_on.get(RULE_BOUNCE) or row.get("judged_on_days_bounce")
                window = row["windows"].get(str(days)) or {}
                reasons.append("%.2f%% bounce on %d sends in %s days (ceiling %.1f%%)"
                               % (window.get("bounce_pct", row["bounce_pct"] or 0.0),
                                  window.get("sent", row["sent"]), days, TH.BOUNCE_RATE_MAX_PCT))
            severity = "medium" if row["thin_evidence"] else "high"
            note = None
            if row["thin_evidence"]:
                note = ("thin evidence: %d sends is under the %d this monitor wants before it trusts a "
                        "rate. One more reply moves this inbox across the line."
                        % (row["sent"], TH.REPLY_RATE_THIN_EVIDENCE_SENT))
            _add("remove_from_email_list", email, severity, 3, "; ".join(reasons),
                 ("remove_inbox", email),
                 {"windows": row["windows"], "judged_on_days": row["judged_on_days"],
                  "failed_on_days": failed_on},
                 thin_evidence=row["thin_evidence"], note=note)

    # ---- Level 5: baseline campaign --------------------------------------
    for row in (l5 or {}).get("failing") or []:
        _add("remove_from_email_list", row["email"], TH.LEVEL5_MAX_SEVERITY, 5,
             "all-campaign reply rate %.2f%% is below %.0f%% of the fleet median %.2f%% (M1 L5 -> level "
             "3 action); level 5 cannot isolate the baseline campaign yet"
             % (row["reply_pct"], TH.LEVEL5_DROP_RATIO * 100, row["median_pct"]),
             ("remove_inbox", row["email"]), row,
             thin_evidence=True,
             note=("GET /accounts/analytics/daily is per account, not per campaign, so this number is "
                   "the inbox's whole cold-outreach traffic and not the partner/peer baseline. It is "
                   "computed on %d sends against level 3's %d, so it is capped at %s and never "
                   "outranks a level 3 verdict on the same inbox."
                   % (row.get("sent", 0), TH.REPLY_RATE_THIN_EVIDENCE_SENT, TH.LEVEL5_MAX_SEVERITY)))

    # ---- Sudden drop ------------------------------------------------------
    for row in (drop or {}).get("dropped") or []:
        thin = bool(row.get("thin_evidence"))
        severity = TH.demote("critical") if thin else "critical"
        note = None
        if thin:
            note = ("thin evidence: the drop is computed on %d recent sends, under the %d level 3 "
                    "needs before it trusts a rate, so this is demoted from critical."
                    % (row.get("recent_sent", 0), TH.SUDDEN_DROP_THIN_EVIDENCE_SENT))
        if row["scope"] == "inbox":
            _add("pause_inbox", row["name"], severity, 1, row["reason"],
                 ("pause_inbox", row["name"]), row,
                 trigger="sudden_drop", thin_evidence=thin, note=note)
        else:
            emails = sorted(i["email"] for i in inboxes
                            if i["domain"] == row["name"] and i["role"] == ROLE_SENDING)
            # Pausing alone is NOT the action. Instantly keeps a paused inbox in
            # email_list, so a bare pause_account silently drops each campaign's
            # capacity instead of moving it: three paused inboxes left in six
            # lists is 75 sends/day of 300 gone with nothing swapped in. The
            # email_list patches ride along, exactly as every other pause
            # proposal's do.
            _add("pause_domain", row["name"], severity, 1, row["reason"],
                 ("pause_many", emails), row,
                 trigger="sudden_drop", thin_evidence=thin, note=note)

    # ---- Levels 2 and 4 fold in whatever their own jobs recorded ----------
    for row in (placement or {}).get("failing") or []:
        _add("pause_inbox", row["email"], "high", 2,
             "inbox placement %.1f%% on %s seeds is below %.0f%% (M1 L2); re-test in %d h%s"
             % (row.get("inbox_pct") or 0.0, row.get("esp"), TH.PLACEMENT_INBOX_MIN_PCT,
                TH.PLACEMENT_RETEST_HOURS, _evidence_age_suffix(placement)),
             ("pause_inbox", row["email"]), row,
             retest_after_hours=TH.PLACEMENT_RETEST_HOURS)
    for row in (canary or {}).get("failing") or []:
        _add("pause_inbox", row["email"], "high", 4,
             "auto-responder canary %.0f%% is below the %.0f%% kill line (M1 L4)%s"
             % (row.get("response_pct") or 0.0, TH.CANARY_RESPONSE_KILL_PCT,
                _evidence_age_suffix(canary)),
             ("pause_inbox", row["email"]), row)

    merged = _dedupe(raw)
    return _materialise(merged, by_email, campaign_lists, allocator)


def _evidence_age_suffix(sidecar: Optional[Dict[str, Any]]) -> str:
    """', measured N days ago (<as_of>)' for a sidecar-sourced verdict.

    A level 2 or level 4 verdict read off a sidecar carries no date in its
    reason line, so a months-old kill re-proposed every morning read exactly
    like today's evidence.
    """
    if not sidecar:
        return ""
    age = sidecar.get("age_days")
    as_of = sidecar.get("as_of")
    if age is None:
        return "" if not as_of else ", measured %s" % as_of
    return ", measured %.1f day(s) ago (%s)" % (age, as_of or "no timestamp")


def _dedupe(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One proposal per (family, target).

    Two levels can condemn the same inbox under different kinds. The most
    complete action survives, it inherits the most severe severity of the set,
    and every safety-relevant field is **merged forward**, not dropped: a louder
    level used to strip the quieter one's ``thin_evidence`` flag and its note,
    so Lorenzo read a high-severity removal with no sign that one reply either
    way decided it.
    """
    groups = OrderedDict()  # type: Dict[Any, List[Dict[str, Any]]]
    for p in proposals:
        key = (PROPOSAL_FAMILY.get(p["kind"], p["kind"]), p["target"])
        groups.setdefault(key, []).append(p)

    out = []
    for key, members in groups.items():
        members = sorted(members, key=lambda p: (KIND_COMPLETENESS.get(p["kind"], 9),
                                                 TH.severity_rank(p["severity"]), p["level"]))
        winner = dict(members[0])
        losers = members[1:]
        winner["also"] = [{"level": p["level"], "reason": p["reason"], "severity": p["severity"],
                           "kind": p["kind"]} for p in losers]
        # Severity is the loudest of the set: a medium pause must not quieten a
        # high removal just because pausing is the more complete action.
        for p in losers:
            if TH.severity_rank(p["severity"]) < TH.severity_rank(winner["severity"]):
                winner["severity"] = p["severity"]
        # Safety fields survive the merge.
        if any(p.get("thin_evidence") for p in members):
            winner["thin_evidence"] = True
        notes = [p["note"] for p in members if p.get("note")]
        if notes:
            winner["note"] = notes[0] if len(notes) == 1 else " | ".join(notes)
        winner["notes"] = notes
        levels = sorted(set(p["level"] for p in members))
        winner["levels"] = levels
        triggers = sorted(set(p["trigger"] for p in members if p.get("trigger")))
        if triggers:
            winner["trigger"] = triggers[0]
        out.append(winner)

    order = {s: i for i, s in enumerate(TH.SEVERITY_ORDER)}
    out.sort(key=lambda p: (order.get(p["severity"], 9), p["level"], p["target"]))
    return out


def _materialise(proposals: List[Dict[str, Any]], by_email: Dict[str, Dict[str, Any]],
                 campaign_lists: Dict[str, Dict[str, Any]],
                 allocator: "_InsuranceAllocator") -> List[Dict[str, Any]]:
    """Give each surviving proposal its replacement inbox and its action list.

    Run after ``_dedupe`` so one condemned inbox consumes one spare, and so the
    ``expected_before`` in every patch is computed once, for the one proposal
    that will actually be applied.
    """
    out = []
    for p in proposals:
        p = dict(p)
        spec = p.pop("_spec", None) or ("manual", [])
        kind = spec[0]
        if kind in ("pause_inbox", "remove_inbox"):
            email = spec[1]
            inbox = by_email.get(email, {})
            in_campaigns = list(inbox.get("in_campaigns") or [])
            replacement = allocator.claim(email, in_campaigns)
            p["replacement"] = replacement
            p["in_campaigns"] = in_campaigns
            p["removes_inboxes"] = [email] if in_campaigns else []
            p["actions"] = (_pause_actions(email, inbox, campaign_lists, replacement)
                            if kind == "pause_inbox"
                            else _remove_actions(email, inbox, campaign_lists, replacement))
        elif kind in ("pause_many", "remove_many"):
            emails = list(spec[1])
            campaign_keys = list(spec[2]) if len(spec) > 2 else sorted(set(
                key for e in emails for key in (by_email.get(e, {}).get("in_campaigns") or [])))
            adds = []
            for e in emails:
                inbox = by_email.get(e, {})
                claimed = allocator.claim(e, list(inbox.get("in_campaigns") or []))
                if claimed:
                    adds.append(claimed)
            actions = []
            if kind == "pause_many":
                actions.extend({"system": "instantly", "op": "pause_account", "email": e}
                               for e in emails)
            actions.extend(_remove_many_actions(emails, campaign_keys, campaign_lists, adds))
            p["actions"] = actions
            p["replacement"] = ", ".join(adds) if adds else None
            p["in_campaigns"] = campaign_keys
            p["removes_inboxes"] = [e for e in emails
                                    if by_email.get(e, {}).get("in_campaigns")]
        else:  # manual
            p["actions"] = list(spec[1])
            p.setdefault("replacement", None)
            p.setdefault("in_campaigns", [])
            p["removes_inboxes"] = []
        out.append(p)
    return out


def _pause_actions(email: str, inbox: Dict[str, Any], campaign_lists: Dict[str, Dict[str, Any]],
                   replacement: Optional[str]) -> List[Dict[str, Any]]:
    """POST /accounts/{email}/pause plus the email_list swap in every campaign
    that uses it. Pausing alone is not enough: Instantly keeps a paused inbox in
    the list, so the campaign's capacity silently drops instead of moving."""
    actions = [{"system": "instantly", "op": "pause_account", "email": email}]
    actions.extend(_remove_actions(email, inbox, campaign_lists, replacement))
    return actions


def _remove_actions(email: str, inbox: Dict[str, Any], campaign_lists: Dict[str, Dict[str, Any]],
                    replacement: Optional[str]) -> List[Dict[str, Any]]:
    """PATCH /campaigns/{id} with the new email_list, one action per campaign.

    The apply script re-reads email_list live and recomputes; the list stored
    here is the expected before/after, which is exactly the diff Lorenzo
    approves.
    """
    actions = []
    for key in inbox.get("in_campaigns") or []:
        camp = campaign_lists.get(key)
        if not camp:
            continue
        before = list(camp["email_list"])
        after = [e for e in before if e.lower() != email.lower()]
        if replacement and replacement not in after:
            after.append(replacement)
            after.sort()
        actions.append({"system": "instantly", "op": "patch_campaign_email_list",
                        "campaign_key": key, "campaign_id": camp["id"],
                        "remove": email, "add": replacement,
                        "expected_before": before, "expected_after": after})
    return actions


def _remove_many_actions(emails: Sequence[str], campaign_keys: Sequence[str],
                         campaign_lists: Dict[str, Dict[str, Any]],
                         adds: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """One PATCH per campaign that drops every one of ``emails`` in a single call."""
    drop = set(e.lower() for e in emails)
    adds = list(adds or [])
    actions = []
    for key in sorted(set(campaign_keys)):
        camp = campaign_lists.get(key)
        if not camp:
            continue
        before = list(camp["email_list"])
        after = [e for e in before if e.lower() not in drop]
        for add in adds:
            if add not in after:
                after.append(add)
        after = sorted(after)
        if after == sorted(before):
            continue
        actions.append({"system": "instantly", "op": "patch_campaign_email_list",
                        "campaign_key": key, "campaign_id": camp["id"],
                        "remove": sorted(e for e in before if e.lower() in drop),
                        "add": adds[0] if len(adds) == 1 else (adds or None),
                        "expected_before": before, "expected_after": after})
    return actions



def build_changeset(proposals: List[Dict[str, Any]], now: datetime, report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "_about": ("Proposed inbox actions from the five-level deliverability monitor (Blueprint M1). "
                   "Nothing here has been applied. Review, then run "
                   "changesets/inbox_actions/apply_inbox_actions.py --dry-run."),
        "generated_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "generated_by": JOB,
        "mode": settings.get_mode(),
        "levels_run": report.get("levels_run"),
        # Which levels actually produced data this run. A level that abstained
        # or blew up on a 413 is NOT in here, and write_changeset refuses to
        # withdraw a proposal whose level it could not re-evaluate.
        "levels_evaluated": report.get("levels_evaluated"),
        "thresholds": {
            "warmup_health_min_pct": TH.WARMUP_HEALTH_MIN_PCT,
            "reply_rate_min_pct": TH.REPLY_RATE_MIN_PCT,
            "reply_rate_min_sent": TH.REPLY_RATE_MIN_SENT,
            "bounce_rate_max_pct": TH.BOUNCE_RATE_MAX_PCT,
            "placement_inbox_min_pct": TH.PLACEMENT_INBOX_MIN_PCT,
            "canary_kill_pct": TH.CANARY_RESPONSE_KILL_PCT,
            "sudden_drop_ratio": TH.SUDDEN_DROP_RATIO,
        },
        "capacity": report.get("capacity"),
        "proposals": proposals,
    }


def _action_key(action: Dict[str, Any]) -> Any:
    """Identity of one action, so two writers' lists can be unioned."""
    op = action.get("op")
    if op == "patch_campaign_email_list":
        return (op, action.get("campaign_id") or action.get("campaign_key"))
    return (op, action.get("email") or action.get("domain") or action.get("target"))


def _merge_actions(prior: List[Dict[str, Any]], current: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Union two writers' action lists, the current writer's version winning on
    a collision. The prior writer's extra actions are kept: a pause-only list
    from the canary must never delete the email_list patches the monitor
    attached to the same proposal id."""
    out = OrderedDict()  # type: Dict[Any, Dict[str, Any]]
    for action in prior:
        out[_action_key(action)] = action
    for action in current:
        out[_action_key(action)] = action
    return list(out.values())


def write_changeset(changeset: Dict[str, Any], now: datetime,
                    directory: Path = CHANGESET_DIR) -> Optional[Path]:
    """changesets/inbox_actions/<YYYY-MM-DD>.json, merged by proposal id.

    Three jobs (the monitor, the placement test, the canary) write into the
    same day's file. Merging on ``id`` keeps ``first_seen`` from the first run
    that saw a problem, so a proposal that has been sitting unapplied for three
    days says so instead of looking new every morning.

    Three merge rules, each of which cost a real defect:

    * **Actions are unioned, not replaced.** The canary and the placement job
      emit ``pause_inbox:<email>`` with a single ``pause_account`` op; the
      monitor's version of the same id carries the ``email_list`` patches too.
      The later writer used to win outright, so applying the merged proposal
      paused an inbox and left it in every campaign's list, which is exactly the
      silent capacity drop the rest of this file guards against.
    * **Top-level context a previous writer supplied is kept.** A canary write
      used to blank the monitor's ``capacity`` and ``thresholds`` blocks and
      flip ``generated_by`` on the file, while the file still held the monitor's
      proposals.
    * **Only levels that were actually evaluated may be withdrawn.** A second
      run that did not evaluate level 3 (a 413 on the analytics endpoint, or a
      ``--level 1`` rerun) used to mark the morning's ``retire_domain`` proposal
      ``withdrawn``, and the apply script then skipped it.
    """
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("could not create %s: %s", directory, exc)
        return None
    path = directory / ("%s.json" % now.astimezone(TZ).date().isoformat())
    existing = {}  # type: Dict[str, Any]
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, ValueError) as exc:
            logger.warning("existing change-set %s unreadable (%s); it will be replaced", path, exc)
            existing = {}
    seen = {p.get("id"): p for p in (existing.get("proposals") or [])}
    merged = []
    stamp = changeset["generated_at"]
    writer = changeset.get("generated_by") or JOB
    evaluated = changeset.get("levels_evaluated")
    evaluated = set(evaluated) if evaluated is not None else None
    for p in changeset.get("proposals") or []:
        prior = seen.pop(p.get("id"), None)
        p = dict(p)
        if prior:
            p["actions"] = _merge_actions(prior.get("actions") or [], p.get("actions") or [])
            for field in ("thin_evidence", "note", "replacement"):
                if p.get(field) in (None, False, "") and prior.get(field) not in (None, False, ""):
                    p[field] = prior[field]
        p["first_seen"] = (prior or {}).get("first_seen") or stamp
        p["last_seen"] = stamp
        p["status"] = (prior or {}).get("status") or "proposed"
        p["generated_by"] = writer
        p.setdefault("level", (prior or {}).get("level"))
        merged.append(p)
    # A proposal from an earlier run today that this run no longer makes is
    # kept and marked: the inbox may have recovered, and deleting the row would
    # erase the only record that it was ever condemned.
    #
    # **Only this writer's own proposals, and only for levels this run actually
    # evaluated, may be withdrawn.** Three jobs share one day's file (the
    # monitor, the placement test, the canary). Without the ownership check the
    # monitor's 07:00 run withdrew the placement job's create_placement_test
    # proposal thirty seconds after it was written. Without the level check, a
    # 12:00 rerun that could not read the analytics endpoint withdrew the
    # morning's level 3 verdicts, which are the most consequential proposals the
    # system makes, leaving nothing but a note.
    for leftover in seen.values():
        leftover = dict(leftover)
        owner = leftover.get("generated_by")
        # A merged proposal carries every level that contributed to it, and ALL
        # of them must have been re-evaluated before it may be withdrawn.
        levels = leftover.get("levels") or ([leftover["level"]] if leftover.get("level") else [])
        level = leftover.get("level")
        level_was_evaluated = evaluated is None or not levels or set(levels).issubset(evaluated)
        if leftover.get("status") == "proposed" and owner == writer and level_was_evaluated:
            leftover["status"] = "withdrawn"
            leftover["withdrawn_at"] = stamp
        elif leftover.get("status") == "proposed" and owner == writer:
            leftover["kept_because"] = (
                "level(s) %s were not all evaluated by the %s run at %s, so this proposal was "
                "neither confirmed nor withdrawn"
                % (", ".join(str(x) for x in (levels or [level])), writer, stamp))
        merged.append(leftover)
    out = dict(existing) if existing else {}
    out.update(changeset)
    # Context blocks a previous writer supplied survive a writer that has none.
    for field in ("capacity", "thresholds", "levels_run", "levels_evaluated"):
        if out.get(field) in (None, [], {}) and (existing or {}).get(field):
            out[field] = existing[field]
    out["proposals"] = merged
    writers = sorted(set([writer] + list((existing or {}).get("written_by") or [])))
    out["written_by"] = writers
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=False, default=str)
            fh.write("\n")
        os.replace(str(tmp), str(path))
    except OSError as exc:
        logger.warning("could not write %s: %s", path, exc)
        return None
    return path


# =========================================================================
# The card
# =========================================================================

def _capacity_cost_line(proposals: List[Dict[str, Any]], caps: Dict[str, Any]) -> str:
    """The one number the per-proposal lines never add up for Lorenzo: what
    applying all of them costs the fleet. Four removals each printing "25
    sends/day" is 100 of 300, and that decides whether any of them can be
    applied today."""
    removed = set()
    replaced = 0
    for p in proposals:
        for email in p.get("removes_inboxes") or []:
            removed.add(email)
        if p.get("replacement") and p.get("removes_inboxes"):
            replaced += len(p["removes_inboxes"])
    if not removed:
        return ""
    total = int(caps.get("daily_capacity") or 0)
    cost = TH.PER_INBOX_DAILY_LIMIT * len(removed)
    left = max(0, total - cost + TH.PER_INBOX_DAILY_LIMIT * replaced)
    share = (float(left) / total * 100.0) if total else 0.0
    return ("Applying all of these removes %d of %d sending inbox(es): %d of %d sends/day, leaving "
            "%.0f%% of today's capacity."
            % (len(removed), caps.get("sending", 0), cost, total, share))


def render_card(report: Dict[str, Any], width: int = 78) -> str:
    """One card. Lorenzo reads this on a phone, so it leads with the count of
    things that need a decision and never buries a critical row under a table."""
    lines = []
    ct = report.get("as_of_ct") or report.get("as_of")
    caps = report.get("capacity") or {}
    props = report.get("proposals") or []
    crit = [p for p in props if p["severity"] in ("critical", "high")]
    head = "Deliverability %s - %d inbox%s, %d proposal%s" % (
        ct, caps.get("total", 0), "" if caps.get("total") == 1 else "es",
        len(props), "" if len(props) == 1 else "s")
    lines.append(head)
    lines.append("=" * min(width, len(head)))
    # No reserve count and no reserve ratio (Lorenzo, 2026-09-22: health
    # alerts only; how many spare inboxes to hold is his call). Whether a
    # removal has a replacement is still said per proposal below.
    # The inboxes in no campaign are named so the line adds up to the header,
    # but never totalled: that total is a reserve count.
    rest = int(caps.get("total") or 0) - int(caps.get("sending") or 0) - int(caps.get("paused") or 0)
    lines.append("sending %s (%s/day)  paused %s%s" % (
        caps.get("sending", 0), caps.get("daily_capacity", 0), caps.get("paused", 0),
        "  the rest warming or idle (not in any campaign)" if rest > 0 else ""))
    lines.append("levels run: %s" % ", ".join(str(x) for x in report.get("levels_run") or []))
    lines.append("")

    if not props:
        lines.append("No action proposed. Every check either passed or abstained for lack of data.")
    else:
        lines.append("PROPOSALS (nothing applied; review changesets/inbox_actions/%s.json)" %
                     (report.get("changeset_date") or ""))
        for p in props:
            lines.append("- [%s] L%s %s %s%s" % (
                p["severity"].upper(), p["level"], p["kind"], p["target"],
                "  THIN EVIDENCE" if p.get("thin_evidence") else ""))
            lines.append("    %s" % p["reason"])
            if p.get("note"):
                lines.append("    %s" % p["note"])
            removed = p.get("removes_inboxes") or []
            if p.get("in_campaigns"):
                # Instantly's 25/day is a PER-INBOX cap shared across campaigns,
                # not 25 per campaign, and a domain-scope proposal removes one
                # inbox's worth of capacity per inbox. The old line read
                # "removes 25 sends/day from 6 campaign(s)" for a three-inbox
                # domain, understating the cost by 3x and inviting a reading of
                # 150/day.
                cost = TH.PER_INBOX_DAILY_LIMIT * max(1, len(removed)) if removed else 0
                if p.get("replacement"):
                    lines.append("    replace with %s; it is in %d campaign(s)"
                                 % (p["replacement"], len(set(p["in_campaigns"]))))
                elif p["kind"] in ("pause_inbox", "remove_from_email_list", "pause_domain",
                                   "retire_domain") and cost:
                    lines.append("    NO replacement available: removes %d inbox(es), %d sends/day "
                                 "total; %s in %d campaign(s)"
                                 % (len(removed), cost,
                                    "they are" if len(removed) != 1 else "it is",
                                    len(set(p["in_campaigns"]))))
            for extra in p.get("also") or []:
                lines.append("    also L%s %s: %s" % (extra["level"], extra.get("kind", ""),
                                                      extra["reason"]))
        cost_line = _capacity_cost_line(props, caps)
        if cost_line:
            lines.append("")
            lines.append(cost_line)
    lines.append("")

    l1 = report.get("level1")
    if l1:
        ok = l1["checked"] - len(l1["findings"])
        lines.append("L1 warm-up + vitals: %d/%d ok, %d domain(s) checked, %d DNS fault(s)" % (
            ok, l1["checked"], l1["vitals_domains"], len(l1.get("domain_dns_faults") or {})))
    l3 = report.get("level3")
    if l3:
        rules = l3.get("rules_applied") or []
        scope = "reply+bounce" if len(rules) > 1 else (rules[0] if rules else "no rule")
        lines.append("L3 %s audit (%s-day windows): %d failing of %d sending inboxes%s" % (
            scope, "/".join(str(d) for d in l3["windows_days"]), len(l3["failing"]),
            len(l3["per_inbox"]),
            "" if len(rules) > 1 else "  [daily bounce pass; the reply audit runs Friday]"))
        for d in sorted(l3["per_domain"], key=lambda x: x["reply_pct"]):
            lines.append("    %-18s %5.2f%% reply  %5.2f%% bounce %-8s %d/%d inboxes failing%s" % (
                d["domain"], d["reply_pct"], d["bounce_pct"], _bounce_flag(d["bounce_pct"]),
                d["failing"], d["inboxes"],
                ("  RETIRE (thin)" if d.get("retire_thin") else "  RETIRE") if d.get("retire") else ""))
    drop = report.get("sudden_drop")
    if drop:
        domain_only = drop.get("per_inbox_enabled") is False
        if not drop.get("usable"):
            lines.append("Sudden drop: NOT EVALUATED, every %sscope abstained"
                         % ("domain " if domain_only else ""))
            if drop.get("abstained"):
                lines.append("    %s" % drop["abstained"][0]["reason"])
        elif domain_only:
            lines.append("Sudden drop (domain-only): %d of %d domains flagged (%d abstained)" % (
                len([r for r in drop["dropped"] if r["scope"] == "domain"]),
                len(drop.get("domains") or []), len(drop.get("abstained") or [])))
            for row in drop.get("abstained") or []:
                lines.append("    abstained %s %s: %s" % (row["scope"], row["name"], row["reason"]))
        else:
            lines.append("Sudden drop: %d of %d inboxes and %d domains flagged (%d abstained)" % (
                len([r for r in drop["dropped"] if r["scope"] == "inbox"]),
                len(drop["inboxes"]), len([r for r in drop["dropped"] if r["scope"] == "domain"]),
                len(drop.get("abstained") or [])))
            for row in drop.get("abstained") or []:
                lines.append("    abstained %s %s: %s" % (row["scope"], row["name"], row["reason"]))
        if domain_only:
            lines.append("    per-inbox: OFF, every inbox abstains. %s"
                         % (drop.get("per_inbox_off_reason") or ""))
    bounces = report.get("bounces")
    if bounces:
        sig = report.get("bounce_signatures") or {}
        lines.append("Bounces last %dh: %d (all-time in campaigns: %d); NDR text hits: %d%s" % (
            bounces["hours"], len(bounces.get("recent") or []), bounces.get("total_bounced_all_time", 0),
            len(sig.get("hits") or []),
            "  [scanned the newest %d message(s) only]" % sig.get("scanned", 0)
            if sig.get("partial") else ""))
    l5 = report.get("level5")
    if l5:
        lines.append("L5 baseline campaign: %s" % ("configured, median %.2f%%, %d failing%s" % (
            l5["median_pct"], len(l5["failing"]),
            " (measured on all-campaign traffic)" if l5.get("mixed_traffic") else "")
            if l5.get("configured") else "not configured"))
    l2 = report.get("level2")
    if l2 is not None:
        lines.append("L2 placement: %s%s" % (l2.get("summary") or "no test results available",
                                             _sidecar_age_suffix(l2)))
    l4 = report.get("level4")
    if l4 is not None:
        lines.append("L4 canary: %s%s" % (l4.get("summary") or "no canary round scored",
                                          _sidecar_age_suffix(l4)))
    lines.append("Scheduled: daily %02d:00 CT (M1 L1 + vitals + sudden drop); levels %s today." % (
        TH.LEVEL1_HOUR_CT, ", ".join(str(x) for x in report.get("levels_run") or [])))
    for note in report.get("notes") or []:
        lines.append("note: %s" % note)
    return "\n".join(lines)


def _bounce_flag(bounce_pct: Optional[float]) -> str:
    """'green', 'AT LINE' or '' for a domain's bounce rate. Section 6 calls
    under BOUNCE_RATE_GREEN_PCT green; at the ceiling is one bounce from a
    removal and deserves to be visible on a phone."""
    if bounce_pct is None:
        return ""
    if bounce_pct > TH.BOUNCE_RATE_MAX_PCT:
        return "OVER"
    if _at_the_line(bounce_pct):
        return "AT LINE"
    if bounce_pct < TH.BOUNCE_RATE_GREEN_PCT:
        return "green"
    return ""


def _at_the_line(bounce_pct: Optional[float]) -> bool:
    """Within an epsilon of BOUNCE_RATE_MAX_PCT without crossing it. Three
    sending inboxes sat at exactly 2.00% on 2026-09-22 and the card gave no
    at-a-glance signal that one more bounce condemns them."""
    if bounce_pct is None:
        return False
    return (TH.BOUNCE_RATE_MAX_PCT - TH.BOUNCE_RATE_AT_LINE_EPSILON_PCT
            <= bounce_pct <= TH.BOUNCE_RATE_MAX_PCT)


def _sidecar_age_suffix(sidecar: Dict[str, Any]) -> str:
    age = (sidecar or {}).get("age_days")
    if age is None:
        return ""
    if sidecar.get("stale"):
        return "  [%.1f day(s) old: STALE, its failing rows were dropped]" % age
    return "  [%.1f day(s) old]" % age


# =========================================================================
# Orchestration
# =========================================================================

def _capacity(inboxes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What is sending today. Health alerts only (Lorenzo, 2026-09-22): no
    insurance count, no promotable count and no reserve ratio, because how
    many spare inboxes to hold, and when to buy more, is his decision."""
    sending = [i for i in inboxes if i["role"] == ROLE_SENDING]
    paused = [i for i in inboxes if i["role"] == ROLE_PAUSED]
    daily = sum(int(i.get("daily_limit") or TH.PER_INBOX_DAILY_LIMIT) for i in sending)
    return {"total": len(inboxes), "sending": len(sending), "paused": len(paused),
            "daily_capacity": daily,
            "domains": sorted(set(i["domain"] for i in inboxes))}


def run_monitor(now: datetime, client: Any = None, levels: Optional[Sequence[int]] = None,
                dry_run: bool = True, notify_fn: Callable = notify, log_fn: Callable = log_run,
                write: Optional[bool] = None, send_card: Optional[bool] = None,
                changeset_dir: Path = CHANGESET_DIR,
                campaigns: Optional[Dict[str, Any]] = None,
                sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """One pass. Reads only; every action is a proposal in the change-set."""
    ct = now.astimezone(TZ)
    if levels is None:
        levels = TH.LEVELS_BY_WEEKDAY.get(ct.weekday(), (1,))
    levels = sorted(set(int(x) for x in levels))
    notes = []  # type: List[str]
    if client is None:
        from shared.instantly import default_client
        client = default_client()

    accounts = load_accounts(client)
    campaign_lists = load_campaign_email_lists(client, campaigns)
    inboxes = build_inbox_index(accounts, campaign_lists, now)
    all_emails = [i["email"] for i in inboxes]
    sending_emails = [i["email"] for i in inboxes if i["role"] != ROLE_INSURANCE]

    warmup = fetch_warmup(client, all_emails, sleep=sleep)
    vitals = fetch_vitals(client, all_emails, sleep=sleep)
    l1 = level1(inboxes, warmup, vitals)
    insurance = eligible_insurance(inboxes, warmup, vitals)

    # One 28-day pull serves level 3 (7/14-day windows) and the sudden-drop
    # baseline. Two pulls would double the 413 risk for no new information.
    # Always pulled: levels 3 and 5 need it, and so does the sudden-drop check,
    # which runs every day alongside level 1 whatever else is scheduled.
    daily_rows = []  # type: List[Dict[str, Any]]
    if sending_emails:
        base_dates = window_dates(now, TH.SUDDEN_DROP_BASELINE_DAYS)
        try:
            daily_rows = fetch_daily(client, sending_emails, base_dates[0], base_dates[-1], sleep=sleep)
        except Exception as exc:  # noqa: BLE001 - a 413 must degrade, not kill the run
            notes.append("accounts/analytics/daily failed (%s): levels 3 and 5 and the sudden-drop "
                         "check were NOT evaluated this run" % str(exc)[:160])
            logger.warning("daily analytics failed: %s", exc)
            daily_rows = None

    # Levels that actually produced data. A level that could not be evaluated
    # must never withdraw yesterday's (or this morning's) verdict for it.
    levels_evaluated = set()  # type: set
    if l1:
        levels_evaluated.add(1)

    l3 = None
    if daily_rows is not None:
        if 3 in levels:
            l3 = level3(inboxes, daily_rows, now)
            levels_evaluated.add(3)
        elif TH.BOUNCE_CHECK_EVERY_DAY:
            # Section 6 gives the Monday run a bounce audit and the Friday run
            # the reply-rate audit, but bounce was only ever evaluated inside
            # the Friday pass. A domain that starts bouncing at 5% on a Saturday
            # sent six more days of mail before anything noticed, and bounce is
            # the fastest way to lose a domain. The 28-day pull is already in
            # hand every morning, so the bounce half runs daily.
            l3 = level3(inboxes, daily_rows, now, rules=(RULE_BOUNCE,))
            notes.append("bounce is audited every day (M1 L3 / Section 6 Monday row); the reply-rate "
                         "half of level 3 runs on its own day")
    drop = sudden_drop(inboxes, daily_rows, now) if daily_rows is not None else None
    l5 = None
    if 5 in levels:
        spec = load_level5_spec(changeset_dir)
        if spec and spec.get("campaign_id"):
            l5 = level5(client, inboxes, spec, now)
            levels_evaluated.add(5)
        else:
            l5 = {"level": 5, "configured": False, "rows": [], "failing": [],
                  "note": "no %s with a live campaign_id in %s; level 5 is a spec only"
                          % (TH.LEVEL5_SPEC_FILENAME, changeset_dir)}
            notes.append(l5["note"])

    bounces = None
    bounce_sig = None
    if drop and drop.get("dropped"):
        try:
            bounces = fetch_recent_bounces(client, now, campaigns)
            bounce_sig = scan_bounce_signatures(client)
        except Exception as exc:  # noqa: BLE001
            notes.append("bounce pull failed (%s)" % str(exc)[:160])

    # Levels 2 and 4 are read from whatever their own jobs last recorded, and
    # **aged**. Without the age check one stale failing row re-proposed a
    # high-severity pause every morning indefinitely, and the card printed a
    # months-old summary with no date on it. M1 L2's rule is a 48-hour re-test,
    # not a standing verdict.
    placement = _age_sidecar(_read_sidecar(changeset_dir, "last_placement.json"), now,
                             TH.PLACEMENT_RETEST_HOURS / 24.0, "placement")
    canary = _age_sidecar(_read_sidecar(changeset_dir, "last_canary.json"), now,
                          float(TH.CANARY_RESULT_MAX_AGE_DAYS), "canary")
    for sidecar in (placement, canary):
        if sidecar and sidecar.get("stale_note"):
            notes.append(sidecar["stale_note"])
    if placement and placement.get("stats_failed"):
        attempt = placement.get("last_attempt") or {}
        notes.append("the placement job's last stats read failed (%s, %s); %s, and level 2 is NOT counted "
                     "as evaluated, so no earlier level 2 proposal is withdrawn"
                     % (attempt.get("error") or "unknown error", attempt.get("as_of") or "unknown time",
                        "its previous verdict is kept" if attempt.get("kept_previous_verdict")
                        else "there is no previous verdict to keep"))
    level2 = None
    level4 = None
    if 2 in levels or placement:
        level2 = placement or {"summary": "no placement results recorded; run jobs/inbox_placement.py",
                               "failing": []}
        # A sidecar that records a FAILED stats read is not evidence that
        # level 2 passed: counting it as evaluated let the merge withdraw a
        # level 2 pause proposed earlier the same day (MKT-7c).
        if placement and not placement.get("stale") and not placement.get("stats_failed"):
            levels_evaluated.add(2)
    if 4 in levels or canary:
        level4 = canary or {"summary": "no canary round recorded; run jobs/autoresponder_canary.py",
                            "failing": []}
        if canary and not canary.get("stale"):
            levels_evaluated.add(4)

    proposals = build_proposals(l1, l3, l5, drop, inboxes, campaign_lists, insurance,
                                placement=level2, canary=level4)
    capacity = _capacity(inboxes)

    report = {
        "job": JOB, "as_of": now.isoformat(), "as_of_ct": ct.strftime("%a %Y-%m-%d %H:%M CT"),
        "mode": settings.get_mode(), "dry_run": bool(dry_run), "levels_run": levels,
        "levels_evaluated": sorted(levels_evaluated),
        "capacity": capacity, "inboxes": inboxes, "level1": l1, "level2": level2,
        "level3": l3, "level4": level4, "level5": l5, "sudden_drop": drop,
        "bounces": bounces, "bounce_signatures": bounce_sig,
        "proposals": proposals, "notes": notes,
        "changeset_date": ct.date().isoformat(),
    }

    if write is None:
        write = not dry_run
    path = None
    if write and proposals:
        path = write_changeset(build_changeset(proposals, now, report), now, changeset_dir)
    report["changeset_path"] = str(path) if path else None
    report["card"] = render_card(report)

    severities = set(p["severity"] for p in proposals)
    # "partial" WINS over "proposals". It used to be the other way round, so a
    # run whose analytics read failed but which still proposed something from
    # level 1 logged "proposals" and exited 0, and the missing levels were
    # invisible in the Job_Log (MKT-9). main() exits non-zero on partial, the
    # same contract as the capacity inventory.
    partial = bool(notes and any("failed" in n for n in notes))
    status = "ok"
    if proposals:
        status = "proposals"
    if partial:
        status = "partial"
    report["partial"] = partial
    report["status"] = status
    if dry_run:
        status = "dry_run_" + status
    log_fn(JOB, status, {
        "as_of": now.isoformat(), "levels": levels, "capacity": capacity, "partial": partial,
        "levels_evaluated": sorted(levels_evaluated),
        "proposals": [{"id": p["id"], "severity": p["severity"], "level": p["level"]} for p in proposals],
        "notes": notes, "changeset": report["changeset_path"],
    })

    if send_card is None:
        send_card = not dry_run
    report["notified"] = None
    if send_card:
        loud = TH.severities_at_or_above(TH.NOTIFY_HIGH_PRIORITY_AT)
        # A partial run is pushed loud too: "0 proposals" at default priority
        # after a failed read looks exactly like a quiet morning (MKT-9).
        priority = "high" if (partial or severities.intersection(loud)) else "default"
        report["notified"] = notify_fn(
            "Deliverability: %s%d proposal%s" % ("PARTIAL, " if partial else "", len(proposals),
                                                 "" if len(proposals) == 1 else "s"),
            report["card"], priority=priority, tags=["mailbox"])
    return report


def _age_sidecar(sidecar: Optional[Dict[str, Any]], now: datetime, max_age_days: float,
                 label: str) -> Optional[Dict[str, Any]]:
    """Stamp a level 2 / level 4 sidecar with its age and drop stale verdicts.

    ``_read_sidecar`` returns whatever is on disk whatever its ``as_of``, and
    ``build_proposals`` used to iterate ``failing`` unconditionally. A single
    failing row from a test run months earlier therefore re-proposed a
    high-severity pause every morning, with no date anywhere in the reason for
    Lorenzo to notice. Level 2's rule is a 48-hour re-test and the canary's is a
    weekly round; past that the evidence is history and the failing rows go.
    """
    if not sidecar:
        return None
    out = dict(sidecar)
    as_of = _parse_ts(sidecar.get("as_of"))
    if as_of is None:
        out["age_days"] = None
        out["stale"] = True
        out["stale_note"] = ("the %s sidecar carries no readable as_of, so its %d failing row(s) are "
                             "not treated as today's evidence"
                             % (label, len(sidecar.get("failing") or [])))
        out["failing"] = []
        return out
    age_days = (now - as_of).total_seconds() / 86400.0
    out["age_days"] = round(age_days, 2)
    out["stale"] = age_days > max_age_days
    if out["stale"]:
        dropped = len(sidecar.get("failing") or [])
        out["failing"] = []
        if dropped:
            out["stale_note"] = ("the %s result is %.1f days old (limit %.1f), so its %d failing "
                                 "row(s) were dropped rather than re-proposed; re-run the %s job"
                                 % (label, age_days, max_age_days, dropped, label))
            retest = sidecar.get("retest") or {}
            if retest:
                # The pause leaves the card at 48 h; the re-test staged with it
                # must not leave silently too.
                out["stale_note"] += (
                    ". A re-test of %s was staged (%s, not before %s%s): until it runs and is scored, "
                    "those inboxes are UNVERIFIED, not healthy"
                    % (", ".join(retest.get("inboxes") or []), retest.get("proposal_id"),
                       retest.get("not_before"), ", BLOCKED: no seeds" if retest.get("blocked") else ""))
        out["summary"] = "%s  [%.1f day(s) old, stale]" % (sidecar.get("summary") or "", age_days)
    return out


def _read_sidecar(directory: Path, name: str) -> Optional[Dict[str, Any]]:
    path = Path(directory) / name
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("sidecar %s unreadable: %s", path, exc)
        return None


def write_sidecar(directory: Path, name: str, data: Dict[str, Any]) -> Optional[Path]:
    """How jobs/inbox_placement.py and jobs/autoresponder_canary.py hand their
    results to the daily card without importing each other."""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
            fh.write("\n")
        os.replace(str(tmp), str(path))
        return path
    except OSError as exc:
        logger.warning("could not write sidecar %s: %s", name, exc)
        return None


def _parse_as_of(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = _parse_ts(value)
    if parsed is None:
        raise SystemExit("--as-of must be an ISO timestamp, got %r" % value)
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="deliverability_monitor",
        description="Five-level deliverability monitor (M1 / O1). Reads live, proposes, never applies.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="read-only: print the card and a scratch Job_Log row, write no change-set, send no push")
    g.add_argument("--now", action="store_true",
                   help="same reads, plus the change-set file and the ntfy card")
    p.add_argument("--level", nargs="+", type=int, choices=[1, 2, 3, 4, 5],
                   help="force specific levels (default: whatever today's weekday runs)")
    p.add_argument("--all-levels", action="store_true", help="run every level regardless of weekday")
    p.add_argument("--as-of", help="ISO timestamp used as 'now' (replay)")
    p.add_argument("--json", action="store_true", help="print the whole report as JSON")
    p.add_argument("--full", action="store_true", help="print the per-inbox tables under the card")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        from shared.job_log import use_scratch_logs

        use_scratch_logs("deliverability_monitor_dryrun")

    levels = args.level
    if args.all_levels:
        levels = [1, 2, 3, 4, 5]
    now = _parse_as_of(args.as_of)
    # A scheduled 07:00 job that dies must say so. Without this the run
    # propagated the exception, wrote zero Job_Log rows and sent zero
    # notifications, and a monitor that has stopped running is indistinguishable
    # from a quiet morning: Lorenzo simply stops receiving cards, which is
    # precisely the failure this job exists to prevent for the inboxes.
    # jobs/campaign_verdicts.py is the house pattern.
    try:
        report = run_monitor(now, levels=levels, dry_run=bool(args.dry_run))
    except Exception as exc:  # noqa: BLE001
        logger.exception("deliverability monitor failed")
        log_run(JOB, "failed", {"as_of": now.isoformat(), "levels": levels,
                                "dry_run": bool(args.dry_run), "error": str(exc)[:400]})
        notify("Deliverability monitor FAILED",
               "%s\n\nThe 07:00 deliverability run did not complete, so no inbox was checked today. "
               "Re-run:\n  python3 jobs/deliverability_monitor.py --dry-run --full" % str(exc)[:400],
               priority="high", tags=["rotating_light"])
        return 1
    rc = 1 if report.get("partial") else 0
    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return rc
    print(report["card"])
    if args.full:
        print("")
        print(_render_tables(report))
    if report.get("changeset_path"):
        print("\nchange-set: %s" % report["changeset_path"])
    return rc


def _render_tables(report: Dict[str, Any]) -> str:
    lines = ["PER-INBOX (%s)" % report["as_of_ct"],
             "%-38s %-10s %6s %6s %8s %8s %7s" %
             ("inbox", "role", "health", "sent", "reply%", "bounce%", "verdict")]
    l3rows = {r["email"]: r for r in ((report.get("level3") or {}).get("per_inbox") or [])}
    for row in (report.get("level1") or {}).get("rows") or []:
        a = l3rows.get(row["email"]) or {}
        lines.append("%-38s %-10s %6s %6s %8s %8s %7s" % (
            row["email"], row["role"],
            "-" if row["health"] is None else "%.0f" % row["health"],
            a.get("sent", "-"),
            "-" if a.get("reply_pct") is None else "%.2f" % a["reply_pct"],
            "-" if a.get("bounce_pct") is None else "%.2f" % a["bounce_pct"],
            "FAIL" if a.get("fails") or row["verdict"] not in ("ok", "too_young") else row["verdict"]))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
