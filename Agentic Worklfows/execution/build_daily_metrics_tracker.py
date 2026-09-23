#!/usr/bin/env python3
"""
Build Daily Metrics Tracker
===========================

Creates (or rebuilds) the "Advero — Daily Metrics" Google Spreadsheet:

    Daily Log   — one row per day, you type raw numbers into it. That's the only manual work.
    Dashboard   — today vs yesterday, 7d/30d rolling averages, week-over-week,
                  running totals, sparklines, derived conversion rates.
    Weekly      — week-by-week totals with color scales so compounding is visible at a glance.

Usage:
    python3 build_daily_metrics_tracker.py                 # create new
    python3 build_daily_metrics_tracker.py --id <sheet_id> # rebuild existing in place
"""

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_sheets_client import get_sheets_client  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS = os.path.join(BASE_DIR, "credentials.json")
SHARE_WITH = "adveroadvertising@gmail.com"
TITLE = "Advero — Daily Metrics"

DAYS = 400          # pre-filled date rows in Daily Log
WEEKS = 104         # pre-filled week rows in Weekly

# --- theme -------------------------------------------------------------------
INK = {"red": 0.09, "green": 0.09, "blue": 0.12}
PAPER = {"red": 1.0, "green": 1.0, "blue": 1.0}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
MUTED = {"red": 0.45, "green": 0.47, "blue": 0.53}
GREEN = {"red": 0.05, "green": 0.55, "blue": 0.35}
RED = {"red": 0.80, "green": 0.20, "blue": 0.22}
GREEN_BG = {"red": 0.88, "green": 0.96, "blue": 0.91}
RED_BG = {"red": 0.99, "green": 0.91, "blue": 0.91}
SCALE_LO = {"red": 1.0, "green": 1.0, "blue": 1.0}
SCALE_HI = {"red": 0.71, "green": 0.76, "blue": 0.98}

SECTIONS = [
    ("OUTREACH", {"red": 0.31, "green": 0.27, "blue": 0.90}),
    ("PIPELINE", {"red": 0.02, "green": 0.59, "blue": 0.41}),
    ("REVENUE", {"red": 0.85, "green": 0.47, "blue": 0.02}),
]

# name, section, kind, number format
#   flow  = a daily count that accumulates (sums into a running total)
#   stock = a level you restate each day (latest value wins, never summed)
#   rate  = a percentage you copy straight off a platform dashboard. Rates are
#           never summed; windows show a volume-weighted average so a 100% day
#           on 1 send cannot outweigh a 10% day on 200 sends.
METRICS = [
    ("Upwork Proposals",      "OUTREACH", "flow",  "int"),
    ("Connects Spent",        "OUTREACH", "flow",  "int"),
    ("Upwork View Rate",      "OUTREACH", "rate",  "pct"),
    ("Upwork Reply Rate",     "OUTREACH", "rate",  "pct"),
    ("Cold Emails Sent",      "OUTREACH", "flow",  "int"),
    ("Email View Rate",       "OUTREACH", "rate",  "pct"),
    ("Email Reply Rate",      "OUTREACH", "rate",  "pct"),
    ("DMs Sent",              "OUTREACH", "flow",  "int"),
    ("DM View Rate",          "OUTREACH", "rate",  "pct"),
    ("DM Reply Rate",         "OUTREACH", "rate",  "pct"),
    ("Community Posts",       "OUTREACH", "flow",  "int"),
    ("New Communities Joined", "OUTREACH", "flow", "int"),
    ("Upwork Hires",          "PIPELINE", "flow",  "int"),
    ("Replies",               "PIPELINE", "flow",  "int"),
    ("Positive Replies",      "PIPELINE", "flow",  "int"),
    ("Calls Booked",          "PIPELINE", "flow",  "int"),
    ("Calls Held",            "PIPELINE", "flow",  "int"),
    ("Proposals Sent",        "PIPELINE", "flow",  "int"),
    ("Closes",                "PIPELINE", "flow",  "int"),
    ("Cash Collected",        "REVENUE",  "flow",  "money"),
    ("New MRR",               "REVENUE",  "flow",  "money"),
    ("Total MRR",             "REVENUE",  "stock", "money"),
    ("Active Clients",        "REVENUE",  "stock", "int"),
]

# label, numerator metric, denominator metric
RATES = [
    ("Reply Rate",            "Replies",          "Cold Emails Sent"),
    ("Positive Reply Rate",   "Positive Replies", "Replies"),
    ("Outreach → Call Booked", "Calls Booked",    "Total Outreach"),
    ("Show Rate",             "Calls Held",       "Calls Booked"),
    ("Close Rate",            "Closes",           "Calls Held"),
]

# Upwork sells Connects at $0.15 each. Editable in the Dashboard's "Connect $" cell
# (J2) — every dollar figure below recalculates from it.
CONNECT_RATE = 0.15
RATE_CELL = f"'{'Dashboard'}'!$J$2"

# Upwork proposal analytics, mirroring Upwork's own panel.
# (label, numerator, denominator, fmt) — "spend" means connects x rate.
# denominator None = show the numerator on its own.
UPWORK_PANEL = [
    ("Applied",                 "Upwork Proposals", None,               "int"),
    ("Connects Spent",          "Connects Spent",   None,               "int"),
    ("Connects Spent ($)",      "spend",            None,               "money2"),
    ("View Rate",               "wavg:Upwork View Rate",  None,             "pct"),
    ("Reply Rate",              "wavg:Upwork Reply Rate", None,             "pct"),
    ("Replies",                 "replies",          None,               "num"),
    ("Conversion Rate",         "Upwork Hires",     "Upwork Proposals", "pct"),
    ("Cost / Reply",            "spend",            "replies",          "money2"),
    ("Connects / Reply",        "Connects Spent",   "replies",          "num"),
    ("Client Acquisition Cost", "spend",            "Upwork Hires",     "money2"),
]


VOLUME_FOR = {          # a rate's denominator volume, for weighted averaging
    "Upwork View Rate":  "Upwork Proposals",
    "Upwork Reply Rate": "Upwork Proposals",
    "Email View Rate":   "Cold Emails Sent",
    "Email Reply Rate":  "Cold Emails Sent",
    "DM View Rate":      "DMs Sent",
    "DM Reply Rate":     "DMs Sent",
}

LOG, DASH, PROG = "Daily Log", "Dashboard", "Daily Progress"
UPDATE = "Daily Update"
WEEK = "Weekly"   # retired — Daily Progress covers it; still deleted on rebuild

INT_FMT = {"type": "NUMBER", "pattern": "#,##0"}
MONEY_FMT = {"type": "CURRENCY", "pattern": '"$"#,##0'}
PCT_FMT = {"type": "PERCENT", "pattern": "+0.0%;-0.0%;0.0%"}
RATE_FMT = {"type": "PERCENT", "pattern": "0.0%"}
DATE_FMT = {"type": "DATE", "pattern": "ddd, mmm d"}


def col(n):
    """1 -> A"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# Daily Log column layout
DATE_COL = 1
FIRST_METRIC_COL = 2
METRIC_COL = {m[0]: FIRST_METRIC_COL + i for i, m in enumerate(METRICS)}
LAST_METRIC_COL = FIRST_METRIC_COL + len(METRICS) - 1
NOTES_COL = LAST_METRIC_COL + 1
LOGGED_COL = NOTES_COL + 1          # hidden helper
LOG_COLS = LOGGED_COL


def build_daily_log(start):
    header = ["Date"] + [m[0] for m in METRICS] + ["Notes", "Logged"]
    rows = [header]
    for i in range(DAYS):
        d = start + timedelta(days=i)
        r = i + 2
        row = [d.strftime("%Y-%m-%d")] + [""] * len(METRICS) + [""]
        row.append(
            f"=IF(COUNT({col(FIRST_METRIC_COL)}{r}:{col(LAST_METRIC_COL)}{r})>0,1,0)"
        )
        rows.append(row)
    return rows


def build_dashboard():
    """Returns (rows, meta) where meta records row indices for formatting."""
    L = f"'{LOG}'!"
    A = f"{L}$A$2:$A${DAYS + 1}"
    asof = "$B$2"

    rows = []
    meta = {"section_rows": [], "metric_rows": [], "rate_rows": [], "spark_rows": [],
            "econ_rows": []}

    rows.append(["DAILY METRICS", "", "", "", "", "", "", "", "", "", ""])          # 1
    rows.append(["As of", "=TODAY()", "", "Days logged",
                 f"=SUMIFS({L}${col(LOGGED_COL)}$2:${col(LOGGED_COL)}${DAYS + 1},{A},\"<=\"&{asof})",
                 "", "Current streak",
                 f'=IFERROR(MATCH(0,ARRAYFORMULA(IFERROR(VLOOKUP({asof}-SEQUENCE({DAYS},1,0),'
                 f"{L}$A$2:${col(LOGGED_COL)}${DAYS + 1},{LOGGED_COL},FALSE),0)),0)-1,{DAYS})",
                 "Connect $", CONNECT_RATE, "", ""])                                # 2
    rows.append([""] * 11)                                                          # 3
    rows.append(["Metric", "Today", "Yesterday", "Δ D/D", "7d avg", "30d avg",
                 "Last 7d", "Prior 7d", "Δ W/W", "All time", "All-time trend"])     # 4
    header_row = 4

    r = 5
    for section, _color in SECTIONS:
        rows.append([section] + [""] * 10)
        meta["section_rows"].append(r)
        r += 1
        for name, sec, kind, fmt in METRICS:
            if sec != section:
                continue
            c = col(METRIC_COL[name])
            V = f"{L}${c}$2:${c}${DAYS + 1}"
            if kind == "flow":
                today = f'=SUMIFS({V},{A},"="&{asof})'
                yday = f'=SUMIFS({V},{A},"="&{asof}-1)'
                avg7 = f'=SUMIFS({V},{A},">"&{asof}-7,{A},"<="&{asof})/7'
                avg30 = f'=SUMIFS({V},{A},">"&{asof}-30,{A},"<="&{asof})/30'
                last7 = f'=SUMIFS({V},{A},">"&{asof}-7,{A},"<="&{asof})'
                prior7 = f'=SUMIFS({V},{A},">"&{asof}-14,{A},"<="&{asof}-7)'
                alltime = f'=SUMIFS({V},{A},"<="&{asof})'
            elif kind == "rate":
                # weighted by volume: SUMPRODUCT(rate*volume)/SUM(volume)
                vc2 = col(METRIC_COL[VOLUME_FOR[name]])
                W = f"{L}${vc2}$2:${vc2}${DAYS + 1}"

                def wavg(lo, hi):
                    if lo is None:
                        cond = f'({A}<={asof})'
                    elif hi:
                        cond = f'(({A}>{asof}-{lo})*({A}<={asof}-{hi}))'
                    else:
                        cond = f'(({A}>{asof}-{lo})*({A}<={asof}))'
                    return (f'IFERROR(SUMPRODUCT({cond}*N({V})*N({W}))/'
                            f'SUMPRODUCT({cond}*N({W})),"")')

                today = f'=IFERROR(SUMIFS({V},{A},"="&{asof}),"")'
                yday = f'=IFERROR(SUMIFS({V},{A},"="&{asof}-1),"")'
                avg7 = f'={wavg(7, 0)}'
                avg30 = f'={wavg(30, 0)}'
                last7 = f'={wavg(7, 0)}'
                prior7 = f'={wavg(14, 7)}'
                alltime = f'={wavg(None, None)}'
            else:  # stock — carry the latest reported value forward
                today = f'=IFERROR(LOOKUP(2,1/(({A}<={asof})*({V}<>"")),{V}),0)'
                yday = f'=IFERROR(LOOKUP(2,1/(({A}<={asof}-1)*({V}<>"")),{V}),0)'
                avg7 = f'=IFERROR(AVERAGEIFS({V},{A},">"&{asof}-7,{A},"<="&{asof}),0)'
                avg30 = f'=IFERROR(AVERAGEIFS({V},{A},">"&{asof}-30,{A},"<="&{asof}),0)'
                last7 = today
                prior7 = f'=IFERROR(LOOKUP(2,1/(({A}<={asof}-7)*({V}<>"")),{V}),0)'
                alltime = today
            dd = f'=IF(N($C{r})=0,"",($B{r}-$C{r})/$C{r})'
            ww = f'=IF(N($H{r})=0,"",($G{r}-$H{r})/$H{r})'
            spark = (
                f'=IFERROR(SPARKLINE(FILTER({V},{A}<={asof}),'
                '{"charttype","column";"empty","zero";"color","#4F46E5"}),"")'
            )
            rows.append([name, today, yday, dd, avg7, avg30,
                         last7, prior7, ww, alltime, spark])
            meta["metric_rows"].append((r, fmt))
            meta["spark_rows"].append(r)
            r += 1
        rows.append([""] * 11)
        r += 1

    rows.append(["CONVERSION RATES"] + [""] * 10)
    meta["section_rows"].append(r)
    rate_section_row = r
    r += 1
    rows.append(["Rate", "Last 7d", "Prior 7d", "Δ W/W", "Last 30d", "All time",
                 "", "", "", "", ""])
    meta["rate_header"] = r
    r += 1

    outreach_cols = [col(METRIC_COL[m[0]]) for m in METRICS if m[1] == "OUTREACH"]

    def sum_expr(metric, lo, hi):
        if metric == "Total Outreach":
            parts = [
                f'SUMIFS({L}${c}$2:${c}${DAYS + 1},{A},">"&{asof}-{lo},{A},"<="&{asof}-{hi})'
                if hi else
                f'SUMIFS({L}${c}$2:${c}${DAYS + 1},{A},">"&{asof}-{lo},{A},"<="&{asof})'
                for c in outreach_cols
            ]
            return "(" + "+".join(parts) + ")"
        c = col(METRIC_COL[metric])
        V = f"{L}${c}$2:${c}${DAYS + 1}"
        if lo is None:
            return f'SUMIFS({V},{A},"<="&{asof})'
        if hi:
            return f'SUMIFS({V},{A},">"&{asof}-{lo},{A},"<="&{asof}-{hi})'
        return f'SUMIFS({V},{A},">"&{asof}-{lo},{A},"<="&{asof})'

    def all_expr(metric):
        if metric == "Total Outreach":
            parts = [f'SUMIFS({L}${c}$2:${c}${DAYS + 1},{A},"<="&{asof})'
                     for c in outreach_cols]
            return "(" + "+".join(parts) + ")"
        return sum_expr(metric, None, None)

    for label, num, den in RATES:
        rows.append([
            label,
            f'=IFERROR({sum_expr(num, 7, 0)}/{sum_expr(den, 7, 0)},"")',
            f'=IFERROR({sum_expr(num, 14, 7)}/{sum_expr(den, 14, 7)},"")',
            f'=IF(N($C{r})=0,"",($B{r}-$C{r})/$C{r})',
            f'=IFERROR({sum_expr(num, 30, 0)}/{sum_expr(den, 30, 0)},"")',
            f'=IFERROR({all_expr(num)}/{all_expr(den)},"")',
            "", "", "", "", "",
        ])
        meta["rate_rows"].append(r)
        r += 1

    # ---- Upwork panel: mirrors Upwork's own proposal analytics ----
    rows.append([""] * 11)
    r += 1
    rows.append(["UPWORK"] + [""] * 10)
    meta["section_rows"].append(r)
    r += 1
    rows.append(["", "Last 7d", "Prior 7d", "Δ W/W", "Last 30d", "All time",
                 "", "", "", "", ""])
    meta["econ_header"] = r
    r += 1

    conn = col(METRIC_COL["Connects Spent"])
    CV = f"{L}${conn}$2:${conn}${DAYS + 1}"

    def window(expr_col, lo, hi):
        """SUMIFS over a trailing window, or all time when lo is None."""
        V2 = f"{L}${expr_col}$2:${expr_col}${DAYS + 1}"
        if lo is None:
            return f'SUMIFS({V2},{A},"<="&{asof})'
        if hi:
            return f'SUMIFS({V2},{A},">"&{asof}-{lo},{A},"<="&{asof}-{hi})'
        return f'SUMIFS({V2},{A},">"&{asof}-{lo},{A},"<="&{asof})'

    def cond_for(lo, hi):
        if lo is None:
            return f'({A}<={asof})'
        if hi:
            return f'(({A}>{asof}-{lo})*({A}<={asof}-{hi}))'
        return f'(({A}>{asof}-{lo})*({A}<={asof}))'

    def term(what, lo, hi):
        if what == "spend":
            return f'({window(conn, lo, hi)}*{RATE_CELL})'
        if what == "replies":
            # no raw reply count is logged — derive it from rate x proposals
            rr = col(METRIC_COL["Upwork Reply Rate"])
            ap = col(METRIC_COL["Upwork Proposals"])
            c = cond_for(lo, hi)
            return (f'SUMPRODUCT({c}*N({L}${rr}$2:${rr}${DAYS + 1})'
                    f'*N({L}${ap}$2:${ap}${DAYS + 1}))')
        if what.startswith("wavg:"):
            m = what[5:]
            rc = col(METRIC_COL[m])
            vc2 = col(METRIC_COL[VOLUME_FOR[m]])
            c = cond_for(lo, hi)
            return (f'IFERROR(SUMPRODUCT({c}*N({L}${rc}$2:${rc}${DAYS + 1})'
                    f'*N({L}${vc2}$2:${vc2}${DAYS + 1}))/'
                    f'SUMPRODUCT({c}*N({L}${vc2}$2:${vc2}${DAYS + 1})),"")')
        return window(col(METRIC_COL[what]), lo, hi)

    for label, num, den, fmt in UPWORK_PANEL:
        def cell(lo, hi):
            if den is None:
                return f'={term(num, lo, hi)}'
            return f'=IFERROR({term(num, lo, hi)}/{term(den, lo, hi)},"")'
        rows.append([label, cell(7, 0), cell(14, 7),
                     f'=IF(N($C{r})=0,"",($B{r}-$C{r})/$C{r})',
                     cell(30, 0), cell(None, None), "", "", "", "", ""])
        meta["econ_rows"].append((r, fmt))
        r += 1

    meta["header_row"] = header_row
    meta["rate_section_row"] = rate_section_row
    meta["last_row"] = r - 1
    return rows, meta


def prog_groups():
    """Column groups on Daily Progress, in display order.

    Derived groups sit immediately after the metric they are derived from, so
    related numbers stay side by side instead of being exiled to the far right.
    Each entry: (name, section, kind, fmt, source_metric, is_derived)
    """
    groups = []
    for name, sec, kind, fmt in METRICS:
        groups.append((name, sec, kind, fmt, name, False))
        if name == "Connects Spent":
            groups.append(("Connects $", sec, "flow", "money", name, True))
    return groups


def build_progress(start):
    """Every single day since day one: value, day-over-day %, running total.

    Rows align 1:1 with Daily Log rows, so this uses direct cell refs rather
    than SUMIFS — 400 rows x 50 lookup formulas would crawl otherwise.
    """
    L = f"'{LOG}'!"
    groups = prog_groups()
    top = ["Date"]
    sub = [""]
    for name, _sec, kind, _fmt, _src, _derived in groups:
        top += [name, "", "", ""]        # must match the 4 sub-columns below
        # Totals lead, and the delta is that total's day-over-day growth:
        # (total today - total yesterday) / total yesterday. A running total only
        # ever grows, so this is never negative; it just gets smaller as the base
        # gets bigger — 7->15 is +114%, but 500->510 is +2%. The raw daily number
        # rides along at the end for context, deliberately without its own delta.
        head = {"flow": "Total", "stock": "Current", "rate": "Rate"}[kind]
        sub += [head, "Δ vs Yesterday", "7d Momentum", "Today"]
    rows = [top, sub]

    for i in range(DAYS):
        r = i + 3                      # progress row (2 header rows)
        lr = i + 2                     # matching Daily Log row
        d = start + timedelta(days=i)
        row = [d.strftime("%Y-%m-%d")]
        # hide a row only if it is BOTH in the future AND empty — anything the
        # user actually typed shows up, whatever the date
        guard = (f'IF(AND($A{r}>TODAY(),COUNT({L}${col(FIRST_METRIC_COL)}{lr}:'
                 f'${col(LAST_METRIC_COL)}{lr})=0),"",')
        for gi, (name, _sec, kind, _fmt, src, derived) in enumerate(groups):
            lc = col(METRIC_COL[src])
            tc = col(2 + 4 * gi)                   # this group's Total column
            mult = f"*{RATE_CELL}" if derived else ""
            if kind == "flow":
                row.append(f'={guard}SUM({L}${lc}$2:${lc}{lr}){mult})')
            elif kind == "rate":    # that day's rate, as logged — never summed
                row.append(f'={guard}{L}${lc}{lr})')
            else:   # stock: latest reported value, not a sum
                row.append(
                    f'={guard}IFERROR(LOOKUP(2,1/({L}${lc}$2:${lc}{lr}<>""),'
                    f'{L}${lc}$2:${lc}{lr}),""))'
                )
            row.append("" if i == 0 else
                       f'={guard}IF(N({tc}{r - 1})=0,"",'
                       f'({tc}{r}-{tc}{r - 1})/{tc}{r - 1}))')
            # rolling 7-day momentum: last 7 days vs the 7 before them. Derived
            # from the Total column (T_r - T_r-7), so it costs no extra SUMIFS.
            # Unlike the cumulative %, this does not decay as the total grows.
            if kind == "flow" and i >= 8:
                row.append(
                    f'={guard}IFERROR(IF(({tc}{r - 1}-{tc}{r - 8})=0,"",'
                    f'(({tc}{r}-{tc}{r - 7})/({tc}{r - 1}-{tc}{r - 8}))-1),""))'
                )
            else:
                row.append("")
            row.append(f'={guard}{L}${lc}{lr}{mult})')
        rows.append(row)
    return rows



def build_update():
    """A copy-paste accountability post, generated from the selected day's row.

    Lines that would report nothing (a channel you did not touch) collapse to ""
    and are dropped from the joined block, so the post never pads itself with
    zeros you did not earn.
    """
    L = f"'{LOG}'!"
    A = f"{L}$A$2:$A${DAYS + 1}"
    d = "$B$1"

    def V(m):
        c = col(METRIC_COL[m])
        return f"{L}${c}$2:${c}${DAYS + 1}"

    def today(m):
        return f'SUMIFS({V(m)},{A},"="&{d})'

    def total(m):
        return f'SUMIFS({V(m)},{A},"<="&{d})'

    def growth(m):
        prev = f'SUMIFS({V(m)},{A},"<="&{d}-1)'
        return (f'IF({prev}=0,"",TEXT(({total(m)}-{prev})/{prev},'
                f'" (+0.0%)"))')

    def n(expr, pat="#,##0"):
        return f'TEXT({expr},"{pat}")'

    def pct(m):
        return f'TEXT({today(m)},"0.0%")'

    lc = col(LOGGED_COL)
    streak = (f'IFERROR(MATCH(0,ARRAYFORMULA(IFERROR(VLOOKUP({d}-SEQUENCE({DAYS},1,0),'
              f'{L}$A$2:${lc}${DAYS + 1},{LOGGED_COL},FALSE),0)),0)-1,{DAYS})')
    days_logged = (f'SUMIFS({L}${lc}$2:${lc}${DAYS + 1},{A},"<="&{d})')

    spend_today = f'({today("Connects Spent")}*{RATE_CELL})'
    spend_total = f'({total("Connects Spent")}*{RATE_CELL})'

    lines = [
        # header
        f'="📊 DAILY UPDATE — "&TEXT({d},"ddd, mmm d, yyyy")&'
        f'"  |  Day "&{n(days_logged)}&'
        f'"  |  🔥 "&{n(streak)}&" day streak"',
        '=""',
        # Every section always prints, even at zero. A post whose shape changes
        # day to day is harder to read and easier to quietly skip.
        '="⚡ UPWORK"',
        f'="   • "&{n(today("Upwork Proposals"))}&" proposals sent  →  "&'
        f'{n(total("Upwork Proposals"))}&" total"&{growth("Upwork Proposals")}',
        f'="   • "&{n(today("Connects Spent"))}&" connects ("&'
        f'TEXT({spend_today},"$#,##0.00")&")  →  "&'
        f'TEXT({spend_total},"$#,##0.00")&" all-time"',
        f'="   • View rate "&{pct("Upwork View Rate")}&"  ·  Reply rate "&'
        f'{pct("Upwork Reply Rate")}',
        '=""',
        '="📧 EMAIL"',
        f'="   • "&{n(today("Cold Emails Sent"))}&" sent  →  "&'
        f'{n(total("Cold Emails Sent"))}&" total"&{growth("Cold Emails Sent")}',
        f'="   • Open "&{pct("Email View Rate")}&"  ·  Reply "&'
        f'{pct("Email Reply Rate")}',
        '=""',
        '="💬 DMs"',
        f'="   • "&{n(today("DMs Sent"))}&" sent  →  "&'
        f'{n(total("DMs Sent"))}&" total"&{growth("DMs Sent")}',
        f'="   • View "&{pct("DM View Rate")}&"  ·  Reply "&{pct("DM Reply Rate")}',
        '=""',
        '="🌐 COMMUNITY"',
        f'="   • "&{n(today("Community Posts"))}&" posts  →  "&'
        f'{n(total("Community Posts"))}&" total"&{growth("Community Posts")}',
        f'="   • "&{n(today("New Communities Joined"))}&" new communities  →  "&'
        f'{n(total("New Communities Joined"))}&" total"',
        '=""',
        '="📞 PIPELINE"',
        f'="   • "&{n(today("Calls Booked"))}&" booked  ·  "&'
        f'{n(today("Calls Held"))}&" held  →  "&{n(total("Calls Booked"))}&'
        f'" booked all-time"',
        f'="   • "&{n(today("Closes"))}&" closed  →  "&{n(total("Closes"))}&'
        f'" clients all-time"',
        '=""',
        '="💰 REVENUE"',
        f'="   • "&TEXT({today("Cash Collected")},"$#,##0")&" collected  →  "&'
        f'TEXT({total("Cash Collected")},"$#,##0")&" all-time"&'
        f'{growth("Cash Collected")}',
        f'="   • "&TEXT({today("Total MRR")},"$#,##0")&" MRR  ·  "&'
        f'{n(today("Active Clients"))}&" active clients"',
        # the only optional line: an empty note would just print a lonely icon
        '=""',
        f'=IF(INDEX({L}${col(NOTES_COL)}$2:${col(NOTES_COL)}${DAYS + 1},'
        f'MATCH({d},{A},0))="","","📝 "&INDEX({L}${col(NOTES_COL)}$2:${col(NOTES_COL)}${DAYS + 1},'
        f'MATCH({d},{A},0)))',
    ]

    rows = [["Update for:", "=TODAY()", "", "← change this date to regenerate"],
            ["Copy the block below (or grab the whole post from the boxed cell"
             " at the bottom)", "", "", ""],
            [""]]
    for ln in lines:
        rows.append([ln])
    first, last = 4, 4 + len(lines) - 1
    rows.append([""])
    rows.append([f'=TEXTJOIN(CHAR(10),FALSE,A{first}:A{last})'])
    return rows, first, last, last + 2


def build_weekly(start):
    L = f"'{LOG}'!"
    A = f"{L}$A$2:$A${DAYS + 1}"
    rows = [["Week Starting"] + [m[0] for m in METRICS] + ["Days Logged"]]
    monday = start - timedelta(days=start.weekday())
    for i in range(WEEKS):
        w = monday + timedelta(weeks=i)
        r = i + 2
        row = [w.strftime("%Y-%m-%d")]
        for name, _sec, kind, _fmt in METRICS:
            c = col(METRIC_COL[name])
            V = f"{L}${c}$2:${c}${DAYS + 1}"
            if kind == "flow":
                row.append(
                    f'=IF($A{r}>TODAY(),"",SUMIFS({V},{A},">="&$A{r},{A},"<"&$A{r}+7))'
                )
            else:
                row.append(
                    f'=IF($A{r}>TODAY(),"",IFERROR(LOOKUP(2,1/(({A}>=$A{r})*({A}<$A{r}+7)*'
                    f'({V}<>"")),{V}),""))'
                )
        lc = col(LOGGED_COL)
        row.append(
            f'=IF($A{r}>TODAY(),"",SUMIFS({L}${lc}$2:${lc}${DAYS + 1},'
            f'{A},">="&$A{r},{A},"<"&$A{r}+7))'
        )
        rows.append(row)
    return rows


# --- formatting helpers ------------------------------------------------------
def rng(sid, r1, c1, r2, c2):
    return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
            "startColumnIndex": c1, "endColumnIndex": c2}


def fmt_req(sid, r1, c1, r2, c2, cell, fields):
    return {"repeatCell": {"range": rng(sid, r1, c1, r2, c2),
                           "cell": {"userEnteredFormat": cell},
                           "fields": fields}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="existing spreadsheet id to rebuild")
    ap.add_argument("--start", help="first date in the log, YYYY-MM-DD "
                                    "(default: today). Set earlier to backfill history.")
    args = ap.parse_args()

    client = get_sheets_client(CREDENTIALS)
    start = date.fromisoformat(args.start) if args.start else date.today()

    saved = {}          # date string -> typed row, carried across the rebuild
    if args.id:
        ss = client.open_by_key(args.id)
        try:
            old = ss.worksheet(LOG).get(
                f"A1:{col(NOTES_COL)}{DAYS + 1}",
                value_render_option="UNFORMATTED_VALUE")
            old_hdr = [str(h) for h in old[0]][1:]   # metric names, minus Date
            epoch = date(1899, 12, 30)              # Sheets date serial origin
            for r in old[1:]:
                if len(r) > 1 and any(str(v).strip() for v in r[1:]):
                    key = r[0]
                    if isinstance(key, (int, float)):
                        key = (epoch + timedelta(days=int(key))).strftime("%Y-%m-%d")
                    # key by COLUMN NAME, so inserting/reordering metrics is safe
                    # only real input columns — never the "Logged" helper, whose
                    # formula would otherwise be overwritten with a stale literal
                    keep = {m[0] for m in METRICS} | {"Notes"}
                    vals = {
                        old_hdr[i]: v for i, v in enumerate(r[1:])
                        if i < len(old_hdr) and str(v).strip() != ""
                        and old_hdr[i] in keep
                    }
                    if vals:
                        saved[str(key)] = vals
            if saved:
                print(f"  preserving {len(saved)} logged day(s)")
        except Exception as e:                       # first build, or no log tab
            print(f"  no prior log to preserve ({e})")
        # a spreadsheet must always keep >=1 sheet, so park one before deleting
        ss.add_worksheet("_tmp", rows=1, cols=1)
        for ws in ss.worksheets():
            if ws.title in (LOG, DASH, WEEK, PROG, UPDATE):
                ss.del_worksheet(ws)
    else:
        ss = client.create(TITLE)
        ss.share(SHARE_WITH, perm_type="user", role="writer", notify=False)

    log_ws = ss.add_worksheet(LOG, rows=DAYS + 1, cols=LOG_COLS)
    dash_ws = ss.add_worksheet(DASH, rows=80, cols=12, index=0)
    upd_ws = ss.add_worksheet(UPDATE, rows=40, cols=6, index=0)
    prog_ws = ss.add_worksheet(PROG, rows=DAYS + 2, cols=4 * len(prog_groups()) + 1, index=1)

    for ws in ss.worksheets():
        if ws.title in ("Sheet1", "_tmp"):
            ss.del_worksheet(ws)

    dash_rows, meta = build_dashboard()
    log_rows = build_daily_log(start)
    restored = 0
    hdr = log_rows[0]
    for row in log_rows[1:]:
        vals = saved.get(row[0])
        if vals:
            for name, v in vals.items():
                if name in hdr:
                    row[hdr.index(name)] = v
            restored += 1
    if restored:
        print(f"  restored {restored} logged day(s)")

    # keyword args: gspread swapped the positional order between v5 and v6
    log_ws.update(range_name="A1", values=log_rows,
                  value_input_option="USER_ENTERED")
    dash_ws.update(range_name="A1", values=dash_rows,
                   value_input_option="USER_ENTERED")
    prog_ws.update(range_name="A1", values=build_progress(start),
                   value_input_option="USER_ENTERED")
    upd_rows, u_first, u_last, u_full = build_update()
    upd_ws.update(range_name="A1", values=upd_rows,
                  value_input_option="USER_ENTERED")

    lid, did, pid, uid = log_ws.id, dash_ws.id, prog_ws.id, upd_ws.id
    reqs = []

    # ---------------- Daily Log ----------------
    reqs += [
        {"updateSheetProperties": {
            "properties": {"sheetId": lid,
                           "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
        fmt_req(lid, 0, 0, 1, LOG_COLS,
                {"backgroundColor": INK,
                 "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                 "wrapStrategy": "WRAP",
                 "verticalAlignment": "MIDDLE",
                 "horizontalAlignment": "CENTER"},
                "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,"
                "verticalAlignment,horizontalAlignment)"),
        fmt_req(lid, 1, 0, DAYS + 1, 1,
                {"numberFormat": DATE_FMT, "textFormat": {"bold": True}},
                "userEnteredFormat(numberFormat,textFormat)"),
        {"updateDimensionProperties": {
            "range": {"sheetId": lid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 48}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": lid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 110}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": lid, "dimension": "COLUMNS",
                      "startIndex": FIRST_METRIC_COL - 1, "endIndex": LAST_METRIC_COL},
            "properties": {"pixelSize": 92}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": lid, "dimension": "COLUMNS",
                      "startIndex": NOTES_COL - 1, "endIndex": NOTES_COL},
            "properties": {"pixelSize": 320}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": lid, "dimension": "COLUMNS",
                      "startIndex": LOGGED_COL - 1, "endIndex": LOGGED_COL},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
    ]
    for name, _sec, _kind, fmt in METRICS:
        c = METRIC_COL[name] - 1
        reqs.append(fmt_req(lid, 1, c, DAYS + 1, c + 1,
                            {"numberFormat": MONEY_FMT if fmt == "money" else INT_FMT,
                             "horizontalAlignment": "CENTER"},
                            "userEnteredFormat(numberFormat,horizontalAlignment)"))
    # section color band on the header
    for section, color in SECTIONS:
        cols = [METRIC_COL[m[0]] for m in METRICS if m[1] == section]
        reqs.append(fmt_req(lid, 0, min(cols) - 1, 1, max(cols),
                            {"backgroundColor": color},
                            "userEnteredFormat.backgroundColor"))
    # highlight today's row + zebra striping
    reqs += [
        {"addConditionalFormatRule": {"rule": {
            "ranges": [rng(lid, 1, 0, DAYS + 1, LOG_COLS)],
            "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA",
                              "values": [{"userEnteredValue": "=$A2=TODAY()"}]},
                "format": {"backgroundColor": {"red": 1.0, "green": 0.97, "blue": 0.85},
                           "textFormat": {"bold": True}}}}, "index": 0}},
        {"addConditionalFormatRule": {"rule": {
            "ranges": [rng(lid, 1, 0, DAYS + 1, LOG_COLS)],
            "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA",
                              "values": [{"userEnteredValue": "=WEEKDAY($A2,2)>5"}]},
                "format": {"backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.97}}}},
            "index": 1}},
    ]

    # ---------------- Dashboard ----------------
    hr = meta["header_row"]
    last = meta["last_row"]
    reqs += [
        {"updateSheetProperties": {
            "properties": {"sheetId": did,
                           "gridProperties": {"frozenRowCount": hr, "frozenColumnCount": 1,
                                              "hideGridlines": True}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount,"
                      "gridProperties.hideGridlines"}},
        fmt_req(did, 0, 0, 1, 11,
                {"backgroundColor": INK,
                 "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": WHITE},
                 "horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE",
                 "padding": {"left": 14}},
                "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,"
                "verticalAlignment,padding)"),
        {"updateDimensionProperties": {
            "range": {"sheetId": did, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 54}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": did, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 32}, "fields": "pixelSize"}},
        # as-of / streak strip
        fmt_req(did, 1, 0, 2, 11,
                {"backgroundColor": {"red": 0.95, "green": 0.96, "blue": 0.99},
                 "textFormat": {"bold": True, "fontSize": 11},
                 "verticalAlignment": "MIDDLE"},
                "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)"),
        fmt_req(did, 1, 1, 2, 2, {"numberFormat": DATE_FMT},
                "userEnteredFormat.numberFormat"),
        # metric table header
        fmt_req(did, hr - 1, 0, hr, 11,
                {"backgroundColor": INK,
                 "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                 "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                 "wrapStrategy": "WRAP"},
                "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,"
                "verticalAlignment,wrapStrategy)"),
        {"updateDimensionProperties": {
            "range": {"sheetId": did, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 190}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": did, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 10},
            "properties": {"pixelSize": 95}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": did, "dimension": "COLUMNS", "startIndex": 10, "endIndex": 11},
            "properties": {"pixelSize": 170}, "fields": "pixelSize"}},
    ]
    for r in meta["section_rows"]:
        color = dict(SECTIONS[0][1])
        for name, c in SECTIONS:
            if dash_rows[r - 1][0].startswith(name):
                color = c
        if dash_rows[r - 1][0] == "CONVERSION RATES":
            color = {"red": 0.36, "green": 0.20, "blue": 0.70}
        reqs.append(fmt_req(did, r - 1, 0, r, 11,
                            {"backgroundColor": color,
                             "textFormat": {"bold": True, "fontSize": 10,
                                            "foregroundColor": WHITE},
                             "verticalAlignment": "MIDDLE"},
                            "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)"))
    for r, fmt in meta["metric_rows"]:
        nf = {"money": MONEY_FMT, "pct": RATE_FMT}.get(fmt, INT_FMT)
        reqs += [
            fmt_req(did, r - 1, 0, r, 1,
                    {"textFormat": {"bold": True}, "verticalAlignment": "MIDDLE"},
                    "userEnteredFormat(textFormat,verticalAlignment)"),
            fmt_req(did, r - 1, 1, r, 3,
                    {"numberFormat": nf, "horizontalAlignment": "CENTER",
                     "textFormat": {"bold": True, "fontSize": 11}},
                    "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)"),
            fmt_req(did, r - 1, 4, r, 8,
                    {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.0"}
                     if fmt == "int" else nf,
                     "horizontalAlignment": "CENTER",
                     "textFormat": {"foregroundColor": MUTED}},
                    "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)"),
            fmt_req(did, r - 1, 9, r, 10,
                    {"numberFormat": nf, "horizontalAlignment": "CENTER"},
                    "userEnteredFormat(numberFormat,horizontalAlignment)"),
        ]
    for r in meta["rate_rows"]:
        reqs += [
            fmt_req(did, r - 1, 0, r, 1, {"textFormat": {"bold": True}},
                    "userEnteredFormat.textFormat"),
            fmt_req(did, r - 1, 1, r, 3, {"numberFormat": RATE_FMT,
                                          "horizontalAlignment": "CENTER",
                                          "textFormat": {"bold": True}},
                    "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)"),
            fmt_req(did, r - 1, 4, r, 6, {"numberFormat": RATE_FMT,
                                          "horizontalAlignment": "CENTER"},
                    "userEnteredFormat(numberFormat,horizontalAlignment)"),
        ]
    ECON_FMT = {"money2": {"type": "CURRENCY", "pattern": '"$"#,##0.00'},
                "pct": RATE_FMT,
                "int": INT_FMT,
                "num": {"type": "NUMBER", "pattern": "#,##0.0"}}
    for r, fmt in meta["econ_rows"]:
        nf = ECON_FMT[fmt]
        reqs += [
            fmt_req(did, r - 1, 0, r, 1, {"textFormat": {"bold": True}},
                    "userEnteredFormat.textFormat"),
            fmt_req(did, r - 1, 1, r, 3,
                    {"numberFormat": nf, "horizontalAlignment": "CENTER",
                     "textFormat": {"bold": True}},
                    "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)"),
            fmt_req(did, r - 1, 4, r, 6,
                    {"numberFormat": nf, "horizontalAlignment": "CENTER"},
                    "userEnteredFormat(numberFormat,horizontalAlignment)"),
        ]
    reqs += [
        fmt_req(did, meta["econ_header"] - 1, 0, meta["econ_header"], 6,
                {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.88},
                 "textFormat": {"bold": True, "fontSize": 10},
                 "horizontalAlignment": "CENTER"},
                "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"),
        # the editable Connect $ rate cell — outlined so it reads as an input
        fmt_req(did, 1, 9, 2, 10,
                {"numberFormat": {"type": "CURRENCY", "pattern": '"$"0.00'},
                 "horizontalAlignment": "CENTER",
                 "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                 "textFormat": {"bold": True},
                 "borders": {s: {"style": "SOLID_MEDIUM",
                                 "color": {"red": 0.85, "green": 0.47, "blue": 0.02}}
                             for s in ("top", "bottom", "left", "right")}},
                "userEnteredFormat(numberFormat,horizontalAlignment,backgroundColor,"
                "textFormat,borders)"),
    ]
    reqs.append(fmt_req(did, meta["rate_header"] - 1, 0, meta["rate_header"], 6,
                        {"backgroundColor": {"red": 0.93, "green": 0.92, "blue": 0.98},
                         "textFormat": {"bold": True, "fontSize": 10},
                         "horizontalAlignment": "CENTER"},
                        "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"))
    # delta columns: D (idx 3) and I (idx 8) on metric rows, D on rate rows
    delta_ranges = [rng(did, hr, 3, last, 4), rng(did, hr, 8, last, 9)]
    reqs += [
        fmt_req(did, hr, 3, last, 4, {"numberFormat": PCT_FMT,
                                      "horizontalAlignment": "CENTER"},
                "userEnteredFormat(numberFormat,horizontalAlignment)"),
        fmt_req(did, hr, 8, last, 9, {"numberFormat": PCT_FMT,
                                      "horizontalAlignment": "CENTER"},
                "userEnteredFormat(numberFormat,horizontalAlignment)"),
        {"addConditionalFormatRule": {"rule": {
            "ranges": delta_ranges,
            "booleanRule": {"condition": {"type": "NUMBER_GREATER",
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": GREEN_BG,
                                       "textFormat": {"bold": True,
                                                      "foregroundColor": GREEN}}}},
            "index": 0}},
        {"addConditionalFormatRule": {"rule": {
            "ranges": delta_ranges,
            "booleanRule": {"condition": {"type": "NUMBER_LESS",
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": RED_BG,
                                       "textFormat": {"bold": True,
                                                      "foregroundColor": RED}}}},
            "index": 1}},
    ]
    for r, _f in meta["metric_rows"]:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": did, "dimension": "ROWS",
                      "startIndex": r - 1, "endIndex": r},
            "properties": {"pixelSize": 30}, "fields": "pixelSize"}})

    # ---------------- Daily Progress ----------------
    pcols = 4 * len(prog_groups()) + 1
    reqs += [
        {"updateSheetProperties": {
            "properties": {"sheetId": pid,
                           "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 1}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
        fmt_req(pid, 0, 0, 2, pcols,
                {"textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
                 "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                 "wrapStrategy": "WRAP", "backgroundColor": INK},
                "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,"
                "wrapStrategy,backgroundColor)"),
        fmt_req(pid, 2, 0, DAYS + 2, 1,
                {"numberFormat": DATE_FMT, "textFormat": {"bold": True},
                 "horizontalAlignment": "LEFT"},
                "userEnteredFormat(numberFormat,textFormat,horizontalAlignment)"),
        {"updateDimensionProperties": {
            "range": {"sheetId": pid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 115}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": pid, "dimension": "COLUMNS", "startIndex": 1,
                      "endIndex": pcols},
            "properties": {"pixelSize": 78}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": pid, "dimension": "ROWS", "startIndex": 0, "endIndex": 2},
            "properties": {"pixelSize": 34}, "fields": "pixelSize"}},
        # today's row stands out while scrolling history
        {"addConditionalFormatRule": {"rule": {
            "ranges": [rng(pid, 2, 0, DAYS + 2, pcols)],
            "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA",
                              "values": [{"userEnteredValue": "=$A3=TODAY()"}]},
                "format": {"backgroundColor": {"red": 1.0, "green": 0.97, "blue": 0.85},
                           "textFormat": {"bold": True}}}}, "index": 0}},
    ]
    groups = prog_groups()
    for idx, (name, sec, kind, fmt, _src, _der) in enumerate(groups):
        v = 1 + 4 * idx          # 0-based: Total col
        color = dict(next(c for n, c in SECTIONS if n == sec))
        nf = {"money": MONEY_FMT, "pct": RATE_FMT}.get(fmt, INT_FMT)
        if name == "Connects $":        # connect spend is small — cents matter
            nf = {"type": "CURRENCY", "pattern": '"$"#,##0.00'}
        reqs += [
            # metric name banner spans its three sub-columns
            {"mergeCells": {"range": rng(pid, 0, v, 1, v + 4), "mergeType": "MERGE_ALL"}},
            fmt_req(pid, 0, v, 1, v + 4, {"backgroundColor": color},
                    "userEnteredFormat.backgroundColor"),
            fmt_req(pid, 2, v, DAYS + 2, v + 1,
                    {"numberFormat": nf, "horizontalAlignment": "CENTER",
                     "textFormat": {"bold": True}},
                    "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)"),
            fmt_req(pid, 2, v + 1, DAYS + 2, v + 3,
                    {"numberFormat": PCT_FMT, "horizontalAlignment": "CENTER"},
                    "userEnteredFormat(numberFormat,horizontalAlignment)"),
            fmt_req(pid, 2, v + 3, DAYS + 2, v + 4,
                    {"numberFormat": nf, "horizontalAlignment": "CENTER",
                     "textFormat": {"foregroundColor": MUTED}},
                    "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)"),
            # the running total darkens as it grows — the compounding cue
            {"addConditionalFormatRule": {"rule": {
                "ranges": [rng(pid, 2, v, DAYS + 2, v + 1)],
                "gradientRule": {"minpoint": {"color": SCALE_LO, "type": "MIN"},
                                 "maxpoint": {"color": SCALE_HI, "type": "MAX"}}},
                "index": 0}},
        ]
    delta_p = [rng(pid, 2, 2 + 4 * i, DAYS + 2, 4 + 4 * i)
               for i in range(len(groups))]
    reqs += [
        {"addConditionalFormatRule": {"rule": {
            "ranges": delta_p,
            "booleanRule": {"condition": {"type": "NUMBER_GREATER",
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {"bold": True,
                                                      "foregroundColor": GREEN}}}},
            "index": 0}},
        {"addConditionalFormatRule": {"rule": {
            "ranges": delta_p,
            "booleanRule": {"condition": {"type": "NUMBER_LESS",
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {"foregroundColor": RED}}}},
            "index": 1}},
    ]

    # ---------------- Daily Update ----------------
    reqs += [
        {"updateSheetProperties": {
            "properties": {"sheetId": uid, "gridProperties": {"hideGridlines": True}},
            "fields": "gridProperties.hideGridlines"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": uid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 620}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": uid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 130}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": uid, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
            "properties": {"pixelSize": 260}, "fields": "pixelSize"}},
        # the date picker
        fmt_req(uid, 0, 0, 1, 2,
                {"textFormat": {"bold": True, "fontSize": 11},
                 "backgroundColor": {"red": 0.95, "green": 0.96, "blue": 0.99},
                 "verticalAlignment": "MIDDLE"},
                "userEnteredFormat(textFormat,backgroundColor,verticalAlignment)"),
        fmt_req(uid, 0, 1, 1, 2,
                {"numberFormat": DATE_FMT, "horizontalAlignment": "CENTER",
                 "backgroundColor": WHITE,
                 "borders": {b: {"style": "SOLID_MEDIUM",
                                 "color": {"red": 0.31, "green": 0.27, "blue": 0.90}}
                             for b in ("top", "bottom", "left", "right")}},
                "userEnteredFormat(numberFormat,horizontalAlignment,backgroundColor,borders)"),
        fmt_req(uid, 1, 0, 2, 4,
                {"textFormat": {"italic": True, "fontSize": 9,
                                "foregroundColor": MUTED}},
                "userEnteredFormat.textFormat"),
        fmt_req(uid, 0, 3, 1, 4,
                {"textFormat": {"italic": True, "fontSize": 9,
                                "foregroundColor": MUTED}},
                "userEnteredFormat.textFormat"),
        # the post body — monospace so it pastes cleanly into Discord/Slack
        fmt_req(uid, u_first - 1, 0, u_last, 1,
                {"textFormat": {"fontFamily": "Roboto Mono", "fontSize": 10},
                 "wrapStrategy": "CLIP"},
                "userEnteredFormat(textFormat,wrapStrategy)"),
        # the one-cell version, boxed
        fmt_req(uid, u_full - 1, 0, u_full, 1,
                {"textFormat": {"fontFamily": "Roboto Mono", "fontSize": 9},
                 "wrapStrategy": "WRAP", "verticalAlignment": "TOP",
                 "backgroundColor": {"red": 0.97, "green": 0.97, "blue": 0.99},
                 "borders": {b: {"style": "SOLID",
                                 "color": {"red": 0.31, "green": 0.27, "blue": 0.90}}
                             for b in ("top", "bottom", "left", "right")}},
                "userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,"
                "backgroundColor,borders)"),
        {"updateDimensionProperties": {
            "range": {"sheetId": uid, "dimension": "ROWS",
                      "startIndex": u_full - 1, "endIndex": u_full},
            "properties": {"pixelSize": 300}, "fields": "pixelSize"}},
    ]

    # ---------------- lock the computed tabs ----------------
    # Dashboard and Daily Progress are pure formulas. Typing into them destroys
    # a formula silently and permanently, so warn on every edit attempt.
    for sid, name in ((did, DASH), (pid, PROG), (uid, UPDATE)):
        reqs.append({"addProtectedRange": {"protectedRange": {
            "range": {"sheetId": sid},
            "description": f"{name} is calculated — enter data in '{LOG}' instead.",
            "warningOnly": True}}})

    ss.batch_update({"requests": reqs})

    print("\n✓ Built:", ss.title)
    print("  URL:", ss.url)
    print("  Shared with:", SHARE_WITH)
    print("  Sheet ID:", ss.id)


if __name__ == "__main__":
    main()
