"""The Daily Metrics tracker: read the Daily Log, merge a day's row, write it.

The Google service account has **zero Drive quota**, so it cannot create a
spreadsheet (403 storageQuotaExceeded). This module never creates anything: it
opens the tracker Lorenzo already owns
("AdveroSolutions - Daily Metrics", id in DAILY_METRICS_SHEET_ID or the default
below), which is shared with the service account as Editor.

The Daily Log is 400 pre-filled date rows, one per day, starting 2026-08-03 in
row 2. Writing a day is therefore **not** an append: it is an update of the one
row whose date column matches, found by reading column A unformatted (the
displayed value "Tue, Sep 22" carries no year and cannot be matched safely).

The write itself is a live write and goes through ``settings.guard_write``: in
shadow it is a would_do record and the sheet is untouched.
"""
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from shared import settings
from shared.paths import BASE_DIR, ROOT_DIR

logger = logging.getLogger("services.metrics.sheet")

# "AdveroSolutions - Daily Metrics" (verified read-only 2026-09-22: 4 logged
# days, last 2026-08-12, tabs Daily Update / Daily Progress / Dashboard / Daily Log).
DEFAULT_SHEET_ID = "1GuJBW_FSZJsJZ9gmN37EmTGo65DH695BtwhFkBXWDj0"
SHEET_ID_ENV = "DAILY_METRICS_SHEET_ID"
LOG_TAB = "Daily Log"
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

DATE_COL = 1          # column A
FIRST_METRIC_COL = 2  # column B
# Google Sheets' serial-date epoch.
SHEET_EPOCH = date(1899, 12, 30)

# Fallback copy of the tracker's schema. execution/build_daily_metrics_tracker.py
# owns it; ``metric_schema()`` imports that module so there is one source of
# truth, and jobs/tests/test_metrics_sheet.py fails if these drift apart.
FALLBACK_METRICS = [
    ("Upwork Proposals", "flow"), ("Connects Spent", "flow"),
    ("Upwork View Rate", "rate"), ("Upwork Reply Rate", "rate"),
    ("Cold Emails Sent", "flow"), ("Email View Rate", "rate"),
    ("Email Reply Rate", "rate"), ("DMs Sent", "flow"),
    ("DM View Rate", "rate"), ("DM Reply Rate", "rate"),
    ("Community Posts", "flow"), ("New Communities Joined", "flow"),
    ("Upwork Hires", "flow"), ("Replies", "flow"), ("Positive Replies", "flow"),
    ("Calls Booked", "flow"), ("Calls Held", "flow"), ("Proposals Sent", "flow"),
    ("Closes", "flow"), ("Cash Collected", "flow"), ("New MRR", "flow"),
    ("Total MRR", "stock"), ("Active Clients", "stock"),
]

# Metrics the job measures itself. Anything here that comes back None renders
# "n/a" and is left out of the sheet write, because a 0 in the tracker is
# indistinguishable from a real zero day.
MEASURED_METRICS = (
    "Cold Emails Sent", "Email Reply Rate", "Replies", "Positive Replies",
    "Calls Booked", "Calls Held", "Proposals Sent", "Closes",
    "Upwork Proposals", "Connects Spent", "Upwork View Rate",
    "Upwork Reply Rate", "Upwork Hires",
)

# Columns where a measured **zero** must never overwrite a value Lorenzo typed.
#
# The engine books nothing in shadow, so its "calls booked today" is 0 every
# evening. On a day Lorenzo had typed 2 booked calls and 3 positives, the run
# wrote 0 over both and the post read "0 booked - 2 held - 0 booked all-time".
# A measured zero here is weaker evidence than a human's number: the pipeline
# columns are the ones he fills in by hand, and there is no way to tell "the
# engine saw nothing" from "nothing happened". A non-zero measurement still
# wins, and an empty cell still takes the zero.
NO_ZERO_OVER_MANUAL = ("Calls Booked", "Calls Held", "Positive Replies",
                       "Proposals Sent", "Closes")


def metric_schema() -> List[Tuple[str, str]]:
    """[(name, kind)] in column order, from the tracker builder when it imports."""
    try:
        import importlib
        import sys

        exec_dir = str(BASE_DIR / "execution")
        if exec_dir not in sys.path:
            sys.path.insert(0, exec_dir)
        module = importlib.import_module("build_daily_metrics_tracker")
        return [(m[0], m[2]) for m in module.METRICS]
    except Exception as exc:  # noqa: BLE001 - never let the schema import kill a run
        logger.warning("could not import build_daily_metrics_tracker (%s); using the local schema copy", exc)
        return list(FALLBACK_METRICS)


def sheet_id() -> str:
    return os.environ.get(SHEET_ID_ENV) or DEFAULT_SHEET_ID


def service_account_info() -> Optional[Dict[str, Any]]:
    """A usable service account, or None.

    GOOGLE_CREDENTIALS_JSON in this repo's .env is still the placeholder
    ``{"type": "service_account", "paste_your_json_here": "..."}``. It parses as
    JSON, so a credentials loader that only checks "did json.loads work" picks
    it and then fails deep inside google.auth with MalformedError. Every
    candidate is validated for ``client_email`` + ``private_key`` before it is
    accepted, and an invalid one falls through to the next."""
    candidates = []
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if raw:
        try:
            candidates.append(json.loads(raw))
        except ValueError:
            if os.path.isfile(raw):
                try:
                    with open(raw, "r", encoding="utf-8") as fh:
                        candidates.append(json.load(fh))
                except (OSError, ValueError):
                    pass
    for path in (BASE_DIR / "credentials.json", ROOT_DIR / "credentials.json"):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    candidates.append(json.load(fh))
            except (OSError, ValueError):
                continue
    for info in candidates:
        if isinstance(info, dict) and info.get("client_email") and info.get("private_key"):
            return info
    return None


# --------------------------------------------------------------- sheet i/o
class GspreadSheet(object):
    """The one worksheet this module touches. Tests inject a fake instead."""

    def __init__(self, spreadsheet_id: Optional[str] = None, tab: str = LOG_TAB):
        self.spreadsheet_id = spreadsheet_id or sheet_id()
        self.tab = tab
        self._ws = None

    def _worksheet(self):
        if self._ws is None:
            import gspread  # local import: only needed for a real read
            from google.oauth2.service_account import Credentials

            info = service_account_info()
            if not info:
                raise RuntimeError(
                    "no usable Google service account (GOOGLE_CREDENTIALS_JSON is a placeholder "
                    "and credentials.json is missing or not a service account)")
            client = gspread.authorize(Credentials.from_service_account_info(info, scopes=list(SCOPES)))
            self._ws = client.open_by_key(self.spreadsheet_id).worksheet(self.tab)
        return self._ws

    def get_all_values(self) -> List[List[Any]]:
        return self._worksheet().get_all_values(value_render_option="UNFORMATTED_VALUE")

    def update(self, range_name: str, values: List[List[Any]]) -> Any:
        # gspread 5.12: keyword arguments only. The positional order changed in
        # v6 and silently writes to the wrong range.
        return self._worksheet().update(range_name=range_name, values=values,
                                        value_input_option="USER_ENTERED")


def col_letter(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def serial_to_date(value: Any) -> Optional[date]:
    try:
        return SHEET_EPOCH + timedelta(days=int(value))
    except (TypeError, ValueError):
        return None


class DailyLog(object):
    """A read-only snapshot of the Daily Log tab."""

    def __init__(self, header: List[Any], rows: List[List[Any]]):
        self.header = [str(h).strip() for h in header]
        self.rows = rows
        self.col_of = dict((name, i + 1) for i, name in enumerate(self.header) if name)
        self.row_of = {}  # type: Dict[date, int]
        self.values_by_date = {}  # type: Dict[date, Dict[str, Any]]
        self.unparsed_dates = 0
        self.non_empty_rows = 0
        for offset, row in enumerate(rows):
            if any(str(cell).strip() for cell in (row or [])):
                self.non_empty_rows += 1
            day = serial_to_date(row[0] if row else None)
            if day is None:
                if any(str(cell).strip() for cell in (row or [])):
                    self.unparsed_dates += 1
                continue
            number = offset + 2  # header is row 1
            self.row_of[day] = number
            record = {}
            for name, col in self.col_of.items():
                if col == DATE_COL:
                    continue
                value = row[col - 1] if len(row) >= col else ""
                record[name] = value
            self.values_by_date[day] = record

    # -- days ------------------------------------------------------------
    def is_logged(self, day: date) -> bool:
        record = self.values_by_date.get(day) or {}
        logged = record.get("Logged")
        if logged not in (None, ""):
            try:
                return float(logged) > 0
            except (TypeError, ValueError):
                pass
        names = [n for n, _k in FALLBACK_METRICS]
        return any(str(record.get(n, "")).strip() != "" for n in names)

    def logged_days(self) -> List[date]:
        return sorted(d for d in self.values_by_date if self.is_logged(d))

    def row_for(self, day: date) -> Optional[int]:
        return self.row_of.get(day)

    def existing(self, day: date) -> Dict[str, Any]:
        return dict(self.values_by_date.get(day) or {})


def read_daily_log(io: Optional[Any] = None) -> DailyLog:
    """The Daily Log tab, or an exception the job degrades on.

    An unreadable **date column** raises rather than returning an empty log. If
    column A ever comes back as display text instead of serial numbers (a
    gspread upgrade dropping ``value_render_option``, or a hand-retyped
    column), every row parses to None: the log then looks identical to a first
    run, and the job publishes "Day 1, 1 day streak" with n/a all-time totals
    under Lorenzo's name on day five, with nothing in the notes saying so."""
    io = io if io is not None else GspreadSheet()
    values = io.get_all_values()
    if not values:
        raise RuntimeError("Daily Log is empty")
    log = DailyLog(values[0], values[1:])
    if log.non_empty_rows and not log.values_by_date:
        raise RuntimeError(
            "Daily Log has %d non-empty row(s) but no readable date in column A "
            "(expected Google Sheets serial numbers; got %r). Refusing to read it as "
            "an empty log." % (log.non_empty_rows, (values[1] or [None])[0]))
    return log


# ------------------------------------------------------------ pure helpers
def streak_and_day(logged_days: List[date], day: date) -> Dict[str, Any]:
    """Day number, streak and the gap, counting today as logged.

    The last logged day is 2026-08-12 and the streak is zero, so the honest
    answer today is "day 5, streak 1", **not** a backfilled 41-day streak.
    Nothing here writes a row for a missed day: a gap stays a gap."""
    logged = sorted(set(d for d in logged_days if d <= day))
    previous = [d for d in logged if d < day]
    last = previous[-1] if previous else None
    streak = 1
    cursor = day - timedelta(days=1)
    known = set(logged)
    while cursor in known:
        streak += 1
        cursor -= timedelta(days=1)
    day_number = len(set(logged) | set([day]))
    gap_days = (day - last).days - 1 if last else None
    return {
        "day_number": day_number,
        "streak": streak,
        "last_logged": last,
        "gap_days": gap_days,
        "restarted": bool(gap_days),
    }


def _float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def all_time_totals(log: DailyLog, upto: date, schema: Optional[List[Tuple[str, str]]] = None,
                    today: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Flow metrics summed, stock metrics latest-wins, through ``upto``.

    ``today`` is merged in before the sum so the block's "all time" figures
    include the day being posted, the way the sheet's own formulas do."""
    schema = schema or metric_schema()
    today = today or {}
    totals = {}  # type: Dict[str, Any]
    for name, kind in schema:
        if kind == "rate":
            continue
        values = []
        for day in sorted(log.values_by_date):
            if day > upto:
                break
            raw = today.get(name) if day == upto and today.get(name) is not None else \
                log.values_by_date[day].get(name)
            value = _float(raw)
            if value is not None:
                values.append(value)
        if not values:
            totals[name] = None
        elif kind == "stock":
            totals[name] = values[-1]
        else:
            totals[name] = sum(values)
    return totals


def carry_forward(log: DailyLog, upto: date, name: str) -> Optional[float]:
    """The last value a stock metric was restated at, on or before ``upto``."""
    latest = None
    for day in sorted(log.values_by_date):
        if day > upto:
            break
        value = _float(log.values_by_date[day].get(name))
        if value is not None:
            latest = value
    return latest


def merge_row(
    log: Optional[DailyLog],
    day: date,
    measured: Dict[str, Any],
    schema: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """The values to write, and the values to render.

    * a measured number wins over whatever is in the cell (we are the source of
      truth for the metrics we read);
    * an unmeasured cell keeps what Lorenzo typed;
    * a manual flow metric with an empty cell renders 0 (a blank flow cell in
      this tracker has always meant "none today") but is **not written**, so we
      never turn his blank into our data;
    * a stock metric with an empty cell carries the last restated value forward
      for the render only.

    Returns {"write": {...}, "render": {...}, "kept": [...]}: ``write`` is what
    goes in the row, ``render`` is what the DAILY UPDATE block prints, ``kept``
    names the cells where a measured zero was refused in favour of what Lorenzo
    typed (see NO_ZERO_OVER_MANUAL)."""
    schema = schema or metric_schema()
    existing = log.existing(day) if log is not None else {}
    write = {}  # type: Dict[str, Any]
    render = {}  # type: Dict[str, Any]
    kept = []  # type: List[str]
    for name, kind in schema:
        measured_value = measured.get(name)
        cell = _float(existing.get(name))
        if measured_value is not None:
            if (name in NO_ZERO_OVER_MANUAL and _float(measured_value) == 0.0
                    and cell not in (None, 0.0)):
                kept.append(name)
                render[name] = cell
                continue
            write[name] = measured_value
            render[name] = measured_value
            continue
        if cell is not None:
            render[name] = cell
            continue
        if name in MEASURED_METRICS:
            render[name] = None            # honest "n/a": we tried and failed
        elif kind == "stock":
            render[name] = carry_forward(log, day, name) if log is not None else None
        elif kind == "rate":
            render[name] = None
        else:
            render[name] = 0.0             # manual flow, nothing logged: none today
    return {"write": write, "render": render, "kept": kept}


def row_values(write: Dict[str, Any], existing: Dict[str, Any],
               schema: Optional[List[Tuple[str, str]]] = None,
               note: Optional[str] = None) -> List[Any]:
    """One B..(Notes) row: measured values, existing values kept, blanks blank.

    The hidden "Logged" column holds a formula and is never in the range."""
    schema = schema or metric_schema()
    out = []
    for name, _kind in schema:
        if name in write and write[name] is not None:
            out.append(write[name])
        else:
            value = existing.get(name)
            out.append("" if value in (None,) else value)
    out.append(note if note is not None else (existing.get("Notes") or ""))
    return out


def row_range(row: int, schema: Optional[List[Tuple[str, str]]] = None) -> str:
    schema = schema or metric_schema()
    last = FIRST_METRIC_COL + len(schema)  # +len covers the Notes column
    return "%s%d:%s%d" % (col_letter(FIRST_METRIC_COL), row, col_letter(last), row)


# ------------------------------------------------------------------- write
def write_day(
    day: date,
    write: Dict[str, Any],
    existing: Dict[str, Any],
    row: Optional[int],
    io: Optional[Any] = None,
    schema: Optional[List[Tuple[str, str]]] = None,
    note: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update the tracker row for ``day``. Guarded: shadow records, never writes."""
    schema = schema or metric_schema()
    spreadsheet_id = spreadsheet_id or sheet_id()
    if row is None:
        return {"ok": False, "reason": "no_row_for_date",
                "detail": "%s is outside the Daily Log's pre-filled date rows" % day.isoformat()}
    values = row_values(write, existing, schema, note=note)
    rng = row_range(row, schema)
    payload = {
        "sheet_id": spreadsheet_id,
        "tab": LOG_TAB,
        "date": day.isoformat(),
        "row": row,
        "range": rng,
        "values": values,
        "measured": dict((k, v) for k, v in write.items() if v is not None),
    }
    guard = settings.guard_write("google_sheets", "daily_metrics_row", payload)
    if guard.get("shadow"):
        return {"ok": True, "shadow": True, "guard": guard, "range": rng, "row": row, "values": values}
    io = io if io is not None else GspreadSheet(spreadsheet_id)
    try:
        result = io.update(rng, [values])
    except Exception as exc:  # noqa: BLE001 - reported, never raised into the job
        logger.error("Daily Log write failed (%s): %s", rng, exc)
        return {"ok": False, "shadow": False, "reason": "write_failed", "error": str(exc)[:300],
                "range": rng, "row": row}
    return {"ok": True, "shadow": False, "result": result, "range": rng, "row": row, "values": values}
