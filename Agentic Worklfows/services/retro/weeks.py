"""Week windows for the retro, in America/Chicago. Pure; the clock is injected.

The retro runs Friday 16:00 CT, so "this week" is never a finished week. The
naive comparison (Mon-to-now against the whole previous Mon-Sun) reads as a
collapse every single Friday, because the current week is missing two and a
half days. Both windows therefore run Monday 00:00 CT through the SAME weekday
as the run, and the packet says out loud that the last day is partial.

Instantly's analytics endpoints are per calendar date, not per timestamp, so a
window is expressed as an inclusive list of ``YYYY-MM-DD`` strings and the run
day is counted whole. That biases the current week low by the sending hours
still left in the day (07:00-19:00 CT, so up to three hours at a 16:00 run).
``Window.partial_last_day`` carries that caveat into the rendered packet
instead of leaving it for the reader to work out.

Two things this module is careful about, because every other retro number
is built on them:

1. **Timestamps are converted to CT before their date is taken.** Instantly
   returns UTC (``2026-09-21T19:01:33.148Z``) and the Job_Log writes UTC, so
   slicing ``value[:10]`` attributes a Friday 20:30 CT positive to Saturday,
   which with three positives a week is a 33% error on the headline row and
   can drop the event out of both windows. ``contains_date`` converts first.
2. **Day arithmetic is redone in local wall-clock time, not by adding
   timedeltas to a localized datetime.** ``TZ.localize(x) - timedelta(days=7)``
   keeps the old UTC offset, so across the 2026-11-01 DST change last week's
   start came back an hour late and ``contains`` was off by an hour.
   ``shift_days`` rebuilds and re-localizes instead.
"""
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional

import pytz

from shared.settings import TZ

WEEK_DAYS = 7


class Window(object):
    """An inclusive range of calendar dates in CT."""

    def __init__(self, start, end, label, partial_last_day=False, cutoff=None):
        # type: (datetime, datetime, str, bool, Optional[datetime]) -> None
        self.start = start          # CT-aware, 00:00 on the first day
        self.end = end              # CT-aware, 00:00 on the LAST day (inclusive)
        self.label = label
        self.partial_last_day = partial_last_day
        self.cutoff = cutoff        # CT-aware instant the window really stops at

    @property
    def start_date(self):
        # type: () -> str
        return self.start.strftime("%Y-%m-%d")

    @property
    def end_date(self):
        # type: () -> str
        return self.end.strftime("%Y-%m-%d")

    def dates(self):
        # type: () -> List[str]
        out = []
        day = self.start
        while day.date() <= self.end.date():
            out.append(day.strftime("%Y-%m-%d"))
            day = day + timedelta(days=1)
        return out

    def contains_date(self, value):
        # type: (Optional[str]) -> bool
        """True when ``value`` falls on one of the window's CT calendar days.

        ``value`` is either a plain ``YYYY-MM-DD`` (Instantly's daily analytics
        rows, which are already per calendar date) or a full ISO timestamp
        (lead interest changes, GHL ``lastStageChangeAt``, Job_Log ``ts_utc``, Gmail
        message dates), which is in UTC and is converted to CT first. Taking
        ``value[:10]`` off a UTC timestamp put every event after 19:00 CT on
        the wrong day.
        """
        date = ct_date(value)
        if not date:
            return False
        return date in set(self.dates())

    def contains(self, moment):
        # type: (Optional[datetime]) -> bool
        """True when an aware datetime falls inside the window (CT)."""
        if moment is None:
            return False
        if moment.tzinfo is None:
            moment = TZ.localize(moment)
        local = moment.astimezone(TZ)
        stop = self.cutoff if self.cutoff is not None else shift_days(self.end, 1)
        return self.start <= local < stop

    def describe(self):
        # type: () -> str
        text = "%s to %s" % (
            self.start.strftime("%a %Y-%m-%d"), self.end.strftime("%a %Y-%m-%d"),
        )
        if self.partial_last_day and self.cutoff is not None:
            text += " (last day partial, counted through %s CT)" % self.cutoff.strftime("%H:%M")
        return text

    def __repr__(self):
        return "Window(%s..%s, %r)" % (self.start_date, self.end_date, self.label)

    def as_dict(self):
        return {
            "label": self.label,
            "start": self.start_date,
            "end": self.end_date,
            "partial_last_day": self.partial_last_day,
            "describe": self.describe(),
        }


def _ct(moment):
    # type: (datetime) -> datetime
    if moment.tzinfo is None:
        return TZ.localize(moment)
    return moment.astimezone(TZ)


def _midnight(moment):
    # type: (datetime) -> datetime
    local = _ct(moment)
    return TZ.localize(datetime(local.year, local.month, local.day))


def shift_days(moment, days):
    # type: (datetime, int) -> datetime
    """``moment`` plus ``days`` calendar days, in CT wall-clock time.

    Arithmetic on a pytz-localized datetime keeps the offset the datetime was
    localized with, so ``TZ.localize(2026-11-02 00:00) - 7 days`` came back as
    ``2026-10-26T00:00-06:00`` when 2026-10-26 was still CDT (-05:00): one hour
    late, and ``Window.contains`` said an event at 00:30 CT was outside last
    week. Rebuilding the naive wall clock and re-localizing gives the offset
    that date really had.
    """
    local = _ct(moment)
    naive = local.replace(tzinfo=None) + timedelta(days=days)
    return TZ.localize(naive)


def ct_date(value):
    # type: (Any) -> Optional[str]
    """The America/Chicago calendar date of a date string or ISO timestamp.

    A bare ``YYYY-MM-DD`` is returned as-is: Instantly's daily analytics rows
    are already per calendar date and have no clock to convert. Anything with a
    time in it is parsed, treated as UTC when it carries no offset (Instantly,
    GHL and the Job_Log all write UTC), and converted to CT before the date is
    taken. Something unparseable falls back to the first ten characters, which
    is the old behaviour, rather than silently dropping the row.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        return text
    moment = parse_utc(text)
    if moment is None:
        return text[:10]
    return moment.astimezone(TZ).strftime("%Y-%m-%d")


def parse_utc(value):
    # type: (Any) -> Optional[datetime]
    """An aware datetime from an ISO-8601 string, assuming UTC when it has no
    offset. Returns None when it cannot be parsed."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    # "2026-09-21T19:01:33.148148148Z": fromisoformat takes 3 or 6 fractional
    # digits on Python 3.9 and nothing else.
    match = re.match(r"^(.*\.\d{1,6})\d*([+-]\d\d:?\d\d)?$", text)
    if match:
        text = match.group(1) + (match.group(2) or "")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        try:
            moment = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = pytz.utc.localize(moment)
    return moment


def week_start(now):
    # type: (datetime) -> datetime
    """Monday 00:00 CT of the week that contains ``now``."""
    local = _midnight(now)
    return shift_days(local, -local.weekday())


def is_end_of_day(now):
    # type: (datetime) -> bool
    """True when the run is late enough that the day is effectively complete
    (after the 19:00 CT send window closes)."""
    return _ct(now).hour >= 19


def windows(now, weeks_back=0):
    # type: (datetime, int) -> tuple
    """(this_week, last_week) for a run at ``now``.

    ``weeks_back`` shifts both windows back whole weeks, so a retro can be
    regenerated for an earlier Friday without touching the clock.
    """
    anchor = shift_days(_ct(now), -WEEK_DAYS * weeks_back)
    this_start = week_start(anchor)
    this_end = _midnight(anchor)
    partial = not is_end_of_day(anchor)
    this_window = Window(
        this_start, this_end, "this week",
        partial_last_day=partial,
        cutoff=anchor if partial else shift_days(this_end, 1),
    )
    last_end = shift_days(this_end, -WEEK_DAYS)
    last_window = Window(
        shift_days(this_start, -WEEK_DAYS),
        last_end,
        "last week",
        partial_last_day=partial,
        cutoff=shift_days(anchor, -WEEK_DAYS) if partial else shift_days(last_end, 1),
    )
    return this_window, last_window


def week_key(window):
    # type: (Window) -> str
    """Stable key for a week, used for the store claim and the output filename."""
    return window.start_date
