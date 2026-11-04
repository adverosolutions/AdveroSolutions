#!/usr/bin/env python3
"""Instantly north-star card — morning handoff on yesterday closed.

Lorenzo lock 2026-09-29:
- Card-only (no lean sheet columns).
- Contacts/positive = Email-1 ÷ positives (not total sent).
- Positives = Instantly total_interested when > 0; else classifier distinct
  (handled.jsonl positive_*). Prefer classifier when Instantly dated interested
  is 0/unreliable.
- Morning default = yesterday closed (--final). Mid-day --so-far on ask only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")  # DST-aware (2026-11-04)
BASE = "https://api.instantly.ai/api/v2"
HANDLED = Path("/home/box/advero/state/handled.jsonl")
POS_PREFIX = "positive_"

SHORT = {
    "2026 Cleaning - Client Reactivation": "cleaning reactivation",
    "2026 Cleaning - Trigger Outbound": "cleaning trigger",
    "2026 Bookkeeping - Client Reactivation": "bookkeeping reactivation",
    "2026 Bookkeeping - Trigger Outbound": "bookkeeping trigger",
    "2026 Recruiting - Client Reactivation": "recruiting reactivation",
    "2026 Recruiting - Outbound (specialty roles)": "recruiting outbound",
}


def load_key() -> str:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lbs", "/home/box/advero/bin/_load_box_secrets.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.apply()
    key = os.environ.get("INSTANTLY_API_KEY")
    if not key:
        sys.exit("INSTANTLY_API_KEY is not set")
    return key


def get(path: str, key: str):
    req = urllib.request.Request(
        BASE + path,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; AdveroBot/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def pct(n: int, d: int, places: int = 2) -> str:
    if d <= 0:
        return "n/a"
    return f"{(n / d) * 100:.{places}f}%"


def contacts_per_positive(email1: int, positives: int):
    """Email-1 ÷ positives. n/a if no positives."""
    if not positives:
        return "n/a"
    if email1 <= 0:
        return "n/a"
    return str(int(round(email1 / positives)))


def short_name(name: str) -> str:
    return SHORT.get(name or "", (name or "unknown").replace("2026 ", "").lower())


def classifier_positives(start: date, end: date) -> set[str]:
    """Distinct leads with positive_* labels in [start, end] CT (by at_ct date)."""
    leads: set[str] = set()
    if not HANDLED.exists():
        return leads
    for line in HANDLED.read_text().splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        lab = (o.get("label") or "").strip()
        if not lab.startswith(POS_PREFIX):
            continue
        day_s = (o.get("at_ct") or "")[:10]
        if not day_s:
            continue
        try:
            d = date.fromisoformat(day_s)
        except ValueError:
            continue
        if d < start or d > end:
            continue
        lead = (o.get("lead") or o.get("from") or "").lower().strip()
        if lead:
            leads.add(lead)
    return leads


def resolve_positives(instantly_interested: int, start: date, end: date) -> tuple[int, str]:
    """Return (count, source). Classifier when Instantly interested is 0/unreliable."""
    clf = classifier_positives(start, end)
    if instantly_interested and instantly_interested > 0:
        # Instantly path available; still prefer classifier if it has data and
        # Instantly looks empty-window unreliable relative to known replies.
        # Locked rule: use classifier when Instantly dated interested unreliable.
        # Treat 0 as unreliable; non-zero Instantly accepted unless classifier
        # finds more distinct positives in-window (Instantly undercount).
        if len(clf) > instantly_interested:
            return len(clf), "classifier"
        return int(instantly_interested), "instantly_interested"
    if clf:
        return len(clf), "classifier"
    return 0, "none"


def build_card(
    day: date,
    phase: str,
    ov: dict,
    ov7: dict,
    camps: list,
    pos_day: int,
    pos_7d: int,
    pos_src_day: str,
    pos_src_7d: str,
    pool=None,
) -> str:
    sent = int(ov.get("emails_sent_count") or 0)
    uniq = int(ov.get("reply_count_unique") or 0)
    email1 = int(ov.get("new_leads_contacted_count") or 0)
    follow = max(sent - email1, 0)
    bounced = int(ov.get("bounced_count") or 0)

    sent7 = int(ov7.get("emails_sent_count") or 0)
    uniq7 = int(ov7.get("reply_count_unique") or 0)
    email1_7 = int(ov7.get("new_leads_contacted_count") or 0)

    best = None
    for c in camps:
        s = int(c.get("emails_sent_count") or 0)
        if s <= 0:
            continue
        r = int(c.get("reply_count_unique") or 0)
        rate = r / s
        row = (rate, short_name(c.get("campaign_name")), r, s)
        if best is None or row > best:
            best = row

    day_label = f"{day.strftime('%a')} {day.strftime('%b')} {day.day}"

    lines = [
        f"Instantly north-star — {day_label} ({phase})",
        f"Reply {pct(uniq, sent)} ({uniq}/{sent}) · 7d {pct(uniq7, sent7)}",
        f"Contacts/positive {contacts_per_positive(email1, pos_day)} today · {contacts_per_positive(email1_7, pos_7d)} on 7d ({pos_7d} positives)",
        f"Email-1 ~{email1} of {sent} sent ({follow} follow-ups)",
    ]
    if best:
        rate, name, r, s = best
        rate_s = (
            f"{rate * 100:.1f}%"
            if abs(rate * 100 - round(rate * 100, 1)) < 1e-9
            else f"{rate * 100:.2f}%"
        )
        lines.append(f"Best today: {name} {rate_s} ({r}/{s})")
    else:
        lines.append("Best today: n/a")

    # Sequence complete, no reply pool (COO 2026-10-21): count only, as of pull time,
    # same logic as flag_stalled_leads.py (all steps complete + 7d grace, never replied).
    if pool is not None:
        lines.append(f"Sequence complete, no reply {pool} (pool)")
    else:
        lines.append("Sequence complete, no reply n/a (pool unavailable)")

    bounce_rate = (bounced / sent) if sent else 0.0
    if sent and bounce_rate >= 0.03:
        lines.append(f"Bounce {bounce_rate * 100:.1f}% — Deliverability watch")
    elif sent and bounce_rate > 0 and bounced >= 5:
        lines.append(f"Bounce {bounce_rate * 100:.1f}% — Deliverability watch")

    if phase == "so far":
        lines.append("UNFINISHED — replies lag; do not use for kill/rotate")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Instantly north-star morning card (yesterday closed by default)."
    )
    ap.add_argument("--date", help="CT day YYYY-MM-DD")
    ap.add_argument(
        "--final",
        action="store_true",
        help="Closed CT day (default when not --so-far). Default date = yesterday CT.",
    )
    ap.add_argument(
        "--so-far",
        action="store_true",
        dest="so_far",
        help="Mid-day same-day pull on ask only. Never for kill/rotate.",
    )
    ap.add_argument(
        "--unfinished",
        action="store_true",
        help="Alias for --so-far",
    )
    ap.add_argument("--write", action="store_true", help="Write card + json under state/reports/")
    ap.add_argument("--no-pool", action="store_true", help="Skip the sequence-complete pool count (saves ~60 read calls)")
    args = ap.parse_args()

    if args.so_far and args.final:
        sys.exit("use either --final or --so-far, not both")

    today = datetime.now(CT).date()
    so_far = args.so_far or args.unfinished

    if so_far:
        day = date.fromisoformat(args.date) if args.date else today
        phase = "so far"
    else:
        day = date.fromisoformat(args.date) if args.date else (today - timedelta(days=1))
        phase = "final"
        if day >= today:
            print(
                "# warn: closed card on today/future is wrong; use --so-far for same-day or omit --date for yesterday",
                file=sys.stderr,
            )

    day7 = day - timedelta(days=6)

    key = load_key()
    q_day = f"start_date={day.isoformat()}&end_date={day.isoformat()}&expand_crm_events=true"
    q_7d = f"start_date={day7.isoformat()}&end_date={day.isoformat()}&expand_crm_events=true"
    ov = get(f"/campaigns/analytics/overview?{q_day}", key)
    ov7 = get(f"/campaigns/analytics/overview?{q_7d}", key)
    camps = get(f"/campaigns/analytics?{q_day}", key)

    pos_day, src_day = resolve_positives(int(ov.get("total_interested") or 0), day, day)
    pos_7d, src_7d = resolve_positives(int(ov7.get("total_interested") or 0), day7, day)

    pool, pool_info = None, {"skipped": True}
    if not args.no_pool:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import flag_stalled_leads as fsl  # count-only; writes nothing

            pool_info = fsl.pool_count(grace_days=7.0, key=key)
            pool = pool_info["count"]
        except Exception as ex:  # card still goes out without the pool line value
            pool_info = {"error": f"{type(ex).__name__}: {ex}"}
            print(f"# warn: pool count failed: {ex}", file=sys.stderr)

    card = build_card(day, phase, ov, ov7, camps, pos_day, pos_7d, src_day, src_7d, pool if not args.no_pool else None)
    if args.no_pool:
        card = "\n".join(l for l in card.split("\n") if not l.startswith("Sequence complete"))
    print(card)

    if args.write:
        out_dir = Path("/home/box/advero/state/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"instantly_northstar_{day.isoformat()}"
        suffix = "_so_far" if phase == "so far" else ""
        path_txt = out_dir / f"{stem}{suffix}.txt"
        path_txt.write_text(card + "\n")
        email1 = int(ov.get("new_leads_contacted_count") or 0)
        email1_7 = int(ov7.get("new_leads_contacted_count") or 0)
        payload = {
            "date": day.isoformat(),
            "phase": phase,
            "judgment_ok": phase == "final",
            "pulled_at_ct": datetime.now(CT).isoformat(timespec="seconds"),
            "contacts_per_positive": {
                "formula": "email1 / positives",
                "day": {
                    "email1": email1,
                    "positives": pos_day,
                    "source": src_day,
                    "ratio": contacts_per_positive(email1, pos_day),
                },
                "d7": {
                    "email1": email1_7,
                    "positives": pos_7d,
                    "source": src_7d,
                    "ratio": contacts_per_positive(email1_7, pos_7d),
                },
            },
            "overview": ov,
            "overview_7d": {
                k: ov7.get(k)
                for k in (
                    "emails_sent_count",
                    "reply_count_unique",
                    "new_leads_contacted_count",
                    "total_interested",
                    "bounced_count",
                )
            },
            "sequence_complete_pool": pool_info,
            "card": card,
            "handoff": "morning_report_yesterday_closed",
            "note": "Card-only. No lean columns. COO owns morning routine.",
        }
        (out_dir / f"{stem}{suffix}.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\n# wrote {path_txt}", file=sys.stderr)


if __name__ == "__main__":
    main()
