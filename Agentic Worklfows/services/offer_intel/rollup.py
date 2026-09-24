"""Wins -> patterns, ranked by how many DIFFERENT members won with them.

A pattern is one industry x mechanism pair. One member posting 12 wins about
the same niche counts as one winner, so a single prolific poster cannot make a
niche look validated. Windows are measured back from ``as_of``.
"""
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

from services.offer_intel import extract as ex
from services.offer_intel import taxonomy
from services.offer_intel.skool_read import parse_time

WIN_COLUMNS = ("post_id", "posted_at", "url", "author_id", "author_name", "title", "win_type", "channel",
               "gate_confidence", "industry", "industry_label", "industry_text", "mechanism", "mechanism_label",
               "mechanism_text", "offer_one_line", "pricing_model", "setup_usd", "monthly_usd", "deal_usd",
               "emails_sent", "reply_rate_pct", "positive_replies", "calls_booked", "guarantee", "list_source",
               "tools", "copy_angle", "time_to_result", "experience", "buyer_role", "geo", "evidence_strength",
               "has_media", "fields_filled", "fields_dropped")

# Price medians read only one-client wins: month totals and call quotes are not one client's price.
CLOSED_WIN_TYPES = ("new_client", "first_client")


def win_rows(raws: List[Dict[str, Any]], analyzed: List[Dict[str, Any]],
             data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """One flat row per post the gate called a win, newest first."""
    data = data or taxonomy.load()
    by_id = dict((r["post_id"], r) for r in raws)
    rows = []
    for result in analyzed:
        verdict = result.get("gate") or {}
        raw = by_id.get(result.get("post_id"))
        if not verdict.get("is_win") or not raw:
            continue
        found = result.get("extract") or {}
        fields = found.get("fields") or {}
        norm = taxonomy.normalize(fields, data)
        row = {
            "post_id": raw["post_id"], "posted_at": raw.get("created_at"), "url": raw.get("url"),
            "author_id": raw.get("author_id"), "author_name": raw.get("author_name"), "title": raw.get("title"),
            "win_type": verdict.get("win_type"), "channel": verdict.get("channel"),
            "gate_confidence": verdict.get("confidence"),
            "industry": norm["industry"], "industry_label": taxonomy.label(norm["industry"], "industries", data),
            "industry_text": norm["industry_text"],
            "mechanism": norm["mechanism"], "mechanism_label": taxonomy.label(norm["mechanism"], "mechanisms", data),
            "mechanism_text": norm["mechanism_text"],
            "evidence_strength": found.get("evidence_strength") or ("screenshot_only" if raw.get("has_media")
                                                                    else "vague"),
            "has_media": bool(raw.get("has_media")),
            "fields_filled": found.get("filled", 0),
            "fields_dropped": len(found.get("dropped") or {}),
        }
        for field in ex.ALL_FIELDS:
            if field not in ("industry", "mechanism"):
                row[field] = ex.value(found, field)
        rows.append(row)
    rows.sort(key=lambda r: str(r.get("posted_at") or ""), reverse=True)
    return rows


def _within(row: Dict[str, Any], as_of: datetime, start_days: int, end_days: int) -> bool:
    """posted in (as_of - end_days, as_of - start_days]."""
    stamp = parse_time(row.get("posted_at"))
    if stamp is None:
        return False
    return as_of - timedelta(days=end_days) < stamp <= as_of - timedelta(days=start_days)


def _median(values: List[Any]) -> Optional[float]:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(median(nums), 2) if nums else None


def _trend(now_30: int, prev_30: int) -> str:
    if now_30 and not prev_30:
        return "new"
    if now_30 > prev_30:
        return "rising"
    if now_30 < prev_30:
        return "fading"
    return "steady"


def patterns(rows: List[Dict[str, Any]], as_of: datetime,
             data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = data or taxonomy.load()
    our_mech, our_ind = taxonomy.ours(data)
    crowd_min = int(data.get("crowded_min_winners_90d") or 5)
    groups = {}  # type: Dict[tuple, List[Dict[str, Any]]]
    for row in rows:
        if row["industry"] == taxonomy.UNKNOWN and row["mechanism"] == taxonomy.UNKNOWN:
            continue  # no offer stated at all (a screenshot win): counted by unstated(), not a pattern
        groups.setdefault((row["industry"], row["mechanism"]), []).append(row)

    out = []
    for (industry, mechanism), items in groups.items():
        recent_90 = [r for r in items if _within(r, as_of, 0, 90)]
        now_30 = sum(1 for r in items if _within(r, as_of, 0, 30))
        prev_30 = sum(1 for r in items if _within(r, as_of, 30, 60))
        winners_90 = len(set(r["author_id"] for r in recent_90))
        closed = [r for r in items if r.get("win_type") in CLOSED_WIN_TYPES]
        fit = [name for name, hit in (("mechanism", mechanism in our_mech), ("industry", industry in our_ind)) if hit]
        out.append({
            "industry": industry, "mechanism": mechanism,
            "pattern": "%s x %s" % (items[0]["industry_label"], items[0]["mechanism_label"]),
            "winners": len(set(r["author_id"] for r in items)),
            "winners_90d": winners_90,
            "wins": len(items),
            "wins_30d": now_30, "wins_prev_30d": prev_30, "trend": _trend(now_30, prev_30),
            "median_setup_usd": _median([r.get("setup_usd") for r in closed]),
            "median_monthly_usd": _median([r.get("monthly_usd") for r in closed]),
            "median_deal_usd": _median([r.get("deal_usd") for r in closed]),
            "cold_email_share": round(sum(1 for r in items if r.get("channel") == "cold_email") / float(len(items)), 2),
            "with_numbers": sum(1 for r in items if r.get("evidence_strength") == "numbers"),
            "crowded": winners_90 >= crowd_min,
            "fit": "+".join(fit),
            "complete": taxonomy.UNKNOWN not in (industry, mechanism) and taxonomy.OTHER not in (industry, mechanism),
            "last_win_at": max(str(r.get("posted_at") or "") for r in items),
            "post_urls": [r["url"] for r in items if r.get("url")][:5],
        })
    # Half-stated patterns ("Dental x (not stated)") rank below every fully stated one.
    out.sort(key=lambda p: (not p["complete"], -p["winners_90d"], -p["winners"], -p["wins_30d"], -p["wins"],
                            p["pattern"]))
    for rank, item in enumerate(out, 1):
        item["rank"] = rank
    return out


def unstated(rows: List[Dict[str, Any]]) -> int:
    """Wins that name neither an industry nor a mechanism."""
    return sum(1 for r in rows if r["industry"] == taxonomy.UNKNOWN and r["mechanism"] == taxonomy.UNKNOWN)


def candidates(ranked: List[Dict[str, Any]], count: int = 3) -> List[Dict[str, Any]]:
    """Patterns worth a test campaign: both sides known, not crowded, and two or
    more different winners (one winner is an anecdote). Falls back to single
    winners only when nothing clears that bar, and says so."""
    usable = [p for p in ranked if p["complete"] and not p["crowded"]]
    strong = [p for p in usable if p["winners"] >= 2]
    picked = strong[:count]
    if len(picked) < count:
        picked += [dict(p, weak=True) for p in usable if p["winners"] < 2][:count - len(picked)]
    return picked


def winners(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The per-person view: one row per member, most wins first."""
    people = {}  # type: Dict[str, Dict[str, Any]]
    for row in rows:
        person = people.setdefault(row["author_id"], {
            "author_id": row["author_id"], "author_name": row.get("author_name"), "wins": 0,
            "patterns": [], "channels": [], "first_win_at": row.get("posted_at"), "last_win_at": row.get("posted_at"),
            "post_urls": []})
        person["wins"] += 1
        pattern = "%s x %s" % (row["industry_label"], row["mechanism_label"])
        if pattern not in person["patterns"]:
            person["patterns"].append(pattern)
        if row.get("channel") and row["channel"] not in person["channels"]:
            person["channels"].append(row["channel"])
        stamp = str(row.get("posted_at") or "")
        person["first_win_at"] = min(str(person["first_win_at"] or stamp), stamp)
        person["last_win_at"] = max(str(person["last_win_at"] or ""), stamp)
        if row.get("url"):
            person["post_urls"].append(row["url"])
    return sorted(people.values(), key=lambda p: (-p["wins"], str(p.get("author_name") or "")))


def unmatched(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Stated industries / mechanisms that matched nothing: grow the lists from these."""
    out = {"industries": {}, "mechanisms": {}}  # type: Dict[str, Dict[str, int]]
    for row in rows:
        if row["industry"] == taxonomy.OTHER and row.get("industry_text"):
            key = row["industry_text"].strip().lower()
            out["industries"][key] = out["industries"].get(key, 0) + 1
        if row["mechanism"] == taxonomy.OTHER and row.get("mechanism_text"):
            key = row["mechanism_text"].strip().lower()
            out["mechanisms"][key] = out["mechanisms"].get(key, 0) + 1
    return out
