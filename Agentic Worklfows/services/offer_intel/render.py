"""What Lorenzo reads: CSVs for the "Offer Intel" Google Sheet, the weekly
digest, and the hand-check sheet for the first sample.

All of it is written under .tmp/offer_intel/out/ (member names and post text
stay off git). The push line carries counts and pattern names only, never a
member's name, because the ntfy topic may be public.
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.offer_intel import extract as ex
from services.offer_intel import rollup

PATTERN_COLUMNS = ("rank", "pattern", "industry", "mechanism", "winners", "winners_90d", "wins", "wins_30d",
                   "wins_prev_30d", "trend", "median_setup_usd", "median_monthly_usd", "median_deal_usd",
                   "cold_email_share", "with_numbers", "crowded", "fit", "complete", "last_win_at", "post_urls")
WINNER_COLUMNS = ("author_id", "author_name", "wins", "patterns", "channels", "first_win_at", "last_win_at",
                  "post_urls")


def _cell(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(v) for v in value)
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: List[Dict[str, Any]], columns: tuple) -> str:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict((k, _cell(row.get(k))) for k in columns))
    return str(path)


def _usd(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return "${:,.0f}".format(value)


def _md(text: Any) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def _n(count: int, word: str) -> str:
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def digest(rows: List[Dict[str, Any]], ranked: List[Dict[str, Any]], picks: List[Dict[str, Any]],
           unmatched: Dict[str, Dict[str, int]], as_of: datetime, new_since: Optional[datetime] = None,
           analyzed_count: int = 0, top: int = 10) -> str:
    fresh = [r for r in rows if new_since and (rollup.parse_time(r.get("posted_at")) or as_of) >= new_since]
    cold = [r for r in rows if r.get("channel") == "cold_email"]
    lines = [
        "# Offer Intel: Maker School wins, as of %s" % as_of.strftime("%Y-%m-%d"),
        "",
        "Market research only. Other members' numbers never go in an email or a proof line; "
        "config/offers.md stays the only proof.",
        "",
        "- Posts analyzed: %d. Business wins: %d (cold email: %d). Different winners: %d."
        % (analyzed_count, len(rows), len(cold), len(set(r["author_id"] for r in rows))),
        "- Wins that state no industry or offer (usually a screenshot): %d." % rollup.unstated(rows),
    ]
    if new_since:
        lines.append("- New wins since %s: %d." % (new_since.strftime("%Y-%m-%d"), len(fresh)))
    lines += ["", "## Top patterns (ranked by different winners in the last 90 days)", "",
              "| # | Pattern | Winners 90d | Winners | Wins 30d | Trend | Median setup | Median monthly | "
              "Cold email | Flags |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for item in ranked[:top]:
        flags = [f for f in ("crowded" if item["crowded"] else "", ("fit: " + item["fit"]) if item["fit"] else "")
                 if f]
        lines.append("| %d | %s | %d | %d | %d | %s | %s | %s | %d%% | %s |" % (
            item["rank"], _md(item["pattern"]), item["winners_90d"], item["winners"], item["wins_30d"],
            item["trend"], _usd(item["median_setup_usd"]), _usd(item["median_monthly_usd"]),
            int(round(100 * item["cold_email_share"])), ", ".join(flags) or "-"))
    if not ranked:
        lines.append("| - | no wins yet | | | | | | | | |")

    lines += ["", "## 3 to test", ""]
    if not picks:
        lines.append("Nothing clears the bar yet (both industry and mechanism stated, not crowded).")
    for n, item in enumerate(picks, 1):
        weak = " Only one member so far, so this is an anecdote, not a pattern." if item.get("weak") else ""
        lines.append("%d. **%s**: %s (%d in 90 days), trend %s, median setup %s, monthly %s.%s"
                     % (n, _md(item["pattern"]), _n(item["winners"], "different winner"), item["winners_90d"],
                        item["trend"], _usd(item["median_setup_usd"]), _usd(item["median_monthly_usd"]), weak))
        for url in item["post_urls"][:3]:
            lines.append("   - %s" % url)

    risers = [p for p in ranked if p["trend"] in ("rising", "new") and p["complete"]][:5]
    lines += ["", "## Rising", ""]
    lines += ["- %s: %s in the last 30 days vs %d before" % (_md(p["pattern"]), _n(p["wins_30d"], "win"),
                                                              p["wins_prev_30d"])
              for p in risers] or ["- none"]

    lines += ["", "## Unmatched (add keywords to config/offer_intel/taxonomy.json if these repeat)", ""]
    for kind in ("industries", "mechanisms"):
        items = sorted(unmatched.get(kind, {}).items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        lines.append("- %s: %s" % (kind, ", ".join("%s (%d)" % (_md(k), v) for k, v in items) or "none"))
    return "\n".join(lines) + "\n"


def review_sheet(raws: List[Dict[str, Any]], analyzed: List[Dict[str, Any]]) -> str:
    """The hand check: each post next to what the models took from it. Mark a
    field wrong if its quote does not say what the value says."""
    by_id = dict((r["post_id"], r) for r in raws)
    lines = ["# Offer Intel hand check", "",
             "For each post: is the win call right, and does each value match its quote? "
             "Target before the full run: no invented facts, 90%+ of fields right.", ""]
    for n, result in enumerate(analyzed, 1):
        raw = by_id.get(result["post_id"]) or {}
        verdict = result.get("gate") or {}
        lines += ["---", "", "## %d. %s" % (n, _md(raw.get("title")) or result["post_id"]),
                  "", "%s  (%s)" % (raw.get("url") or "(no url)", raw.get("created_at") or "")]
        lines += ["", "**Post:**", "", "> " + (raw.get("content") or "").replace("\n", "\n> ")]
        for reply in raw.get("author_replies") or []:
            lines += ["", "**Author reply:**", "", "> " + (reply.get("content") or "").replace("\n", "\n> ")]
        lines += ["", "**Gate:** win=%s, type=%s, channel=%s, confidence=%.2f%s. %s" % (
            verdict.get("is_win"), verdict.get("win_type"), verdict.get("channel"), verdict.get("confidence", 0),
            " (escalated)" if verdict.get("escalated") else "", _md(verdict.get("reason")))]
        found = result.get("extract")
        if found:
            lines += ["", "| Field | Value | Quote | Right? |", "|---|---|---|---|"]
            for field in ex.ALL_FIELDS:
                item = (found.get("fields") or {}).get(field)
                if item:
                    lines.append("| %s | %s | %s | |" % (field, _md(_cell(item["value"])), _md(item["quote"])))
            if found.get("dropped"):
                lines += ["", "Dropped by the quote check: %s" % ", ".join(
                    "%s (%s)" % kv for kv in sorted(found["dropped"].items()))]
        lines.append("")
    return "\n".join(lines) + "\n"


def push_line(rows: List[Dict[str, Any]], ranked: List[Dict[str, Any]], analyzed_count: int) -> str:
    top = ", ".join(p["pattern"] for p in ranked[:3]) or "none yet"
    return "%d posts analyzed, %d wins, %d different winners. Top: %s" % (
        analyzed_count, len(rows), len(set(r["author_id"] for r in rows)), top)
