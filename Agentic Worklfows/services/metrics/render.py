"""The DAILY UPDATE block, in the format the Daily Metrics tracker already uses.

The tracker's "Daily Update" tab builds this block out of spreadsheet formulas
(execution/build_daily_metrics_tracker.py, ``build_update``). This module
renders the same block in Python from measured numbers so the job can stage it
for Lorenzo and hand it to the Skool post without a round trip through the
sheet's recalculation.

Two deliberate differences from the sheet's version:

* **No em dash in the header.** The sheet writes "DAILY UPDATE - " with an em
  dash; the copy rules for anything a prospect or client can read forbid em
  dashes, and a Skool post is exactly that. The separator is " | ", which the
  header already uses between the date, the day count and the streak.
* **An unmeasured number prints "n/a", never 0.** The sheet can only show 0
  for an empty cell. A post that claims 0 replies on a day nothing was read is
  a lie that compounds; "n/a" says the truth.

Section order and wording are otherwise identical, including the rule that
every section prints every day even at zero, so the post has the same shape
each time and stays easy to skim.
"""
from datetime import date
from typing import Any, Dict, List, Optional

# Upwork sells Connects at $0.15 (the tracker's Dashboard!J2 default).
CONNECT_RATE = 0.15

SIGNATURE = "Lorenzo"

# Copy rules for anything a prospect or client could read.
FORBIDDEN_SUBSTRINGS = ("—", "!")
FORBIDDEN_WORDS = ("ai ", " ai", "a.i.", "automation", "automated", "automate",
                   "bot ", "chatgpt", "claude", "llm")


def fmt_int(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return "{:,.0f}".format(float(value))


def fmt_money(value: Optional[float], cents: bool = False) -> str:
    if value is None:
        return "n/a"
    return ("${:,.2f}" if cents else "${:,.0f}").format(float(value))


def fmt_pct(value: Optional[float]) -> str:
    """A 0-1 ratio as a percentage. None -> "n/a"."""
    if value is None:
        return "n/a"
    return "{:.1f}%".format(float(value) * 100.0)


def growth(total: Optional[float], prior: Optional[float]) -> str:
    """The sheet's " (+0.0%)" suffix: all-time growth contributed today."""
    if total is None or prior in (None, 0):
        return ""
    try:
        delta = (float(total) - float(prior)) / float(prior)
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    if abs(delta) < 0.00005:
        return ""   # the day added nothing to the all-time figure; "(+0.0%)" is noise
    return " ({:+.1f}%)".format(delta * 100.0)


def copy_violations(text: str) -> List[str]:
    """Copy-rule breaches in text a prospect or client could read."""
    out = []
    lowered = text.lower()
    if "—" in text:
        out.append("em dash")
    if "!" in text:
        out.append("exclamation mark")
    for word in FORBIDDEN_WORDS:
        if word in lowered:
            out.append("mentions %r" % word.strip())
    return out


def _get(values: Dict[str, Any], name: str) -> Optional[float]:
    value = values.get(name)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_daily_update(
    day: date,
    today: Dict[str, Any],
    totals: Optional[Dict[str, Any]] = None,
    prior_totals: Optional[Dict[str, Any]] = None,
    day_number: Optional[int] = None,
    streak: Optional[int] = None,
    note: Optional[str] = None,
    connect_rate: float = CONNECT_RATE,
    signature: Optional[str] = SIGNATURE,
    totals_are_partial: bool = False,
) -> str:
    """The DAILY UPDATE block as one string.

    ``today`` / ``totals`` / ``prior_totals`` are keyed by the tracker's own
    metric names ("Upwork Proposals", "Cold Emails Sent", ...). A missing or
    None value renders "n/a".

    ``totals_are_partial`` relabels every all-time figure "logged to date".
    The totals are summed from the rows present in the Daily Log, and the last
    logged day is 2026-08-12: a post that says "300 sent, 300 total" on a week
    that really sent 1,800 is not a rounding error, it is a claim about
    Lorenzo's whole history made in public under his name."""
    totals = totals or {}
    prior_totals = prior_totals or {}
    total_word = "logged to date" if totals_are_partial else "total"
    alltime_word = "logged to date" if totals_are_partial else "all-time"

    def T(name):
        return _get(today, name)

    def A(name):
        return _get(totals, name)

    def P(name):
        return _get(prior_totals, name)

    def G(name):
        return growth(A(name), P(name))

    spend_today = None
    if T("Connects Spent") is not None:
        spend_today = T("Connects Spent") * connect_rate
    spend_all = None
    if A("Connects Spent") is not None:
        spend_all = A("Connects Spent") * connect_rate

    # "%-d" is glibc/BSD only; build the day number by hand so the block
    # renders identically wherever the job runs.
    header = "\U0001F4CA DAILY UPDATE  |  %s %d, %d" % (day.strftime("%a, %b"), day.day, day.year)
    if day_number is not None:
        header += "  |  Day %s" % fmt_int(day_number)
    if streak is not None:
        header += "  |  \U0001F525 %s day streak" % fmt_int(streak)

    lines = [header, ""]

    lines.append("⚡ UPWORK")
    lines.append("   • %s proposals sent  →  %s %s%s"
                 % (fmt_int(T("Upwork Proposals")), fmt_int(A("Upwork Proposals")),
                    total_word, G("Upwork Proposals")))
    lines.append("   • %s connects (%s)  →  %s %s"
                 % (fmt_int(T("Connects Spent")), fmt_money(spend_today, cents=True),
                    fmt_money(spend_all, cents=True), alltime_word))
    lines.append("   • View rate %s  ·  Reply rate %s"
                 % (fmt_pct(T("Upwork View Rate")), fmt_pct(T("Upwork Reply Rate"))))
    lines.append("")

    lines.append("\U0001F4E7 EMAIL")
    lines.append("   • %s sent  →  %s %s%s"
                 % (fmt_int(T("Cold Emails Sent")), fmt_int(A("Cold Emails Sent")),
                    total_word, G("Cold Emails Sent")))
    lines.append("   • Open %s  ·  Reply %s"
                 % (fmt_pct(T("Email View Rate")), fmt_pct(T("Email Reply Rate"))))
    lines.append("")

    lines.append("\U0001F4AC DMs")
    lines.append("   • %s sent  →  %s %s%s"
                 % (fmt_int(T("DMs Sent")), fmt_int(A("DMs Sent")), total_word, G("DMs Sent")))
    lines.append("   • View %s  ·  Reply %s"
                 % (fmt_pct(T("DM View Rate")), fmt_pct(T("DM Reply Rate"))))
    lines.append("")

    lines.append("\U0001F310 COMMUNITY")
    lines.append("   • %s posts  →  %s %s%s"
                 % (fmt_int(T("Community Posts")), fmt_int(A("Community Posts")),
                    total_word, G("Community Posts")))
    lines.append("   • %s new communities  →  %s %s"
                 % (fmt_int(T("New Communities Joined")), fmt_int(A("New Communities Joined")),
                    total_word))
    lines.append("")

    lines.append("\U0001F4DE PIPELINE")
    lines.append("   • %s booked  ·  %s held  →  %s booked %s"
                 % (fmt_int(T("Calls Booked")), fmt_int(T("Calls Held")),
                    fmt_int(A("Calls Booked")), alltime_word))
    lines.append("   • %s closed  →  %s clients %s"
                 % (fmt_int(T("Closes")), fmt_int(A("Closes")), alltime_word))
    lines.append("")

    lines.append("\U0001F4B0 REVENUE")
    lines.append("   • %s collected  →  %s %s%s"
                 % (fmt_money(T("Cash Collected")), fmt_money(A("Cash Collected")),
                    alltime_word, G("Cash Collected")))
    lines.append("   • %s MRR  ·  %s active clients"
                 % (fmt_money(T("Total MRR")), fmt_int(T("Active Clients"))))

    if note:
        lines.append("")
        lines.append("\U0001F4DD %s" % note.strip())
    if signature:
        lines.append("")
        lines.append(signature)
    return "\n".join(lines)
