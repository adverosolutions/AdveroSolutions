"""Pure calendar-slot rules and reply-time parsing (America/Chicago).

Rules (Blueprint S2/S3, offers.md rule 2): offered slots are 12:00-18:00 CT,
Mon-Fri, at least 4 hours out, within the next 5 business days, never a slot
already offered to someone else. Replies only go out 07:00-19:00 CT.

All functions take ``now`` explicitly (no wall-clock reads) so they are
deterministic in tests.
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Set, Tuple, Union

import pytz

logger = logging.getLogger("shared.slots")

TZ = pytz.timezone("America/Chicago")
EASTERN = pytz.timezone("America/New_York")
MOUNTAIN = pytz.timezone("America/Denver")
PACIFIC = pytz.timezone("America/Los_Angeles")

SEND_WINDOW = (7, 19)
SLOT_WINDOW = (12, 18)
MIN_LEAD_HOURS = 4
MAX_BUSINESS_DAYS = 5
SLOT_MINUTES = 15

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "weds": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# alias -> tz. "CTS" appears in a real reply and means Central; "Estern" is a
# real typo for Eastern.
TZ_ALIASES = {
    "eastern": EASTERN, "estern": EASTERN, "easter": EASTERN, "est": EASTERN, "edt": EASTERN, "et": EASTERN,
    "new york": EASTERN, "ny": EASTERN,
    "central": TZ, "cst": TZ, "cdt": TZ, "ct": TZ, "cts": TZ, "chicago": TZ,
    "mountain": MOUNTAIN, "mst": MOUNTAIN, "mdt": MOUNTAIN, "mt": MOUNTAIN, "denver": MOUNTAIN,
    "pacific": PACIFIC, "pst": PACIFIC, "pdt": PACIFIC, "pt": PACIFIC,
}

_TZ_RE = re.compile(
    r"\b(eastern|estern|easter|est|edt|et|new york|central|cst|cdt|cts|ct|chicago|mountain|mst|mdt|mt|pacific|pst|pdt|pt)\b"
    r"(?:\s*(?:time|standard time|daylight time))?",
    re.I,
)
_DAY_RE = re.compile(
    r"\b(?:(this|next|coming)\s+)?(monday|mon|tuesday|tues|tue|wednesday|weds|wed|thursday|thurs|thur|thu|friday|fri|saturday|sat|sunday|sun|tomorrow|today)\b",
    re.I,
)
_AMPM_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\b", re.I)
_COLON_RE = re.compile(r"(?<![\d.\-/])\b(\d{1,2}):(\d{2})\b(?![\d.\-/])")
_CUE_RE = re.compile(r"\b(?:at|around|about|@|how'?s|say|maybe)\s+(\d{1,2})\b(?![:\d]|\s*(?:am|pm|a\.m|p\.m|%|k\b|\d))", re.I)
_OCLOCK_RE = re.compile(r"\b(\d{1,2})\s*o'?clock\b", re.I)
# A bare number after a cue word is only a clock time when nothing turns it into
# a quantity. "We have about 4 crews right now. Thursday?" used to parse as
# Thursday 16:00 and "I am at 3 locations on Thursday" as 15:00. am/pm, ":mm"
# and o'clock are handled by their own patterns before the cue is consulted, so
# the only evidence left here is the word that follows the number: a noun makes
# it a count, a time word or the end of the clause leaves it a time.
_CUE_FOLLOWERS = set("""
oclock o'clock ish sharp on or and to if then instead that this next tomorrow today
your my our his her their works work working sounds sound good fine great ok okay
perfect possible would could should will can is are was am be for up so but either
both please thanks thank yes yeah sure central eastern mountain pacific chicago
""".split()) | set(TZ_ALIASES.keys()) | set(
    "monday mon tuesday tues tue wednesday weds wed thursday thurs thur thu "
    "friday fri saturday sat sunday sun".split())
_CUE_NEXT_WORD_RE = re.compile(r"\s*([A-Za-z][A-Za-z'\.]*)")


def _cue_is_a_time(text: str, match) -> bool:
    """False when the word after a cue number makes it a quantity, not a clock."""
    tail = text[match.end():]
    nxt = _CUE_NEXT_WORD_RE.match(tail)
    if not nxt:
        return True              # end of clause or punctuation: "how's 3?" is a time
    return nxt.group(1).lower().strip(".") in _CUE_FOLLOWERS
_NOON_RE = re.compile(r"\bnoon\b", re.I)
_RANGE_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*(?:-|–|—|to|until|till|through)\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?",
    re.I,
)
_QUOTE_HEADER_RE = re.compile(
    r"^(>"
    r"|(?:-{2,}\s*)?On .{3,200}?wrote\s*(?::|-{2,})"   # "On ... wrote:" and Zoho's "---- On ... wrote ----"
    r"|-{2,}\s*Original Message"
    r"|From:\s|Sent from my|_{5,}|Get Outlook for)",
    re.I,
)
# Gmail (and Zoho) wrap a long attribution over two or three lines:
#   On Wed, Sep 16, 2026 at 6:42 AM Lorenzo Villarreal <
#   lorenzovillarreal@proadvero.com> wrote:
# Neither line matches the single-line form, so the quote has to be detected
# by joining the line that starts with "On" with the next one or two.
_ON_START_RE = re.compile(r"^\s*(?:-{2,}\s*)?On\b", re.I)
_WROTE_END_RE = re.compile(r"wrote\s*(?::|-{2,})", re.I)
# Phone numbers must never be read as times: "contact Barbara at 1-800-311-6441"
# otherwise parses as "at 1" -> 13:00.
_PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]\d{3}[\s.\-]\d{4}\b")


# ------------------------------------------------------------ tz helpers
def ensure_aware(dt: datetime, tz=TZ) -> datetime:
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt


def to_tz(dt: datetime, tz=TZ) -> datetime:
    return ensure_aware(dt, tz).astimezone(tz)


def parse_iso(value: Union[str, datetime, int, float], tz=TZ) -> datetime:
    """ISO 8601 string (Z or offset or naive-in-tz), epoch seconds/ms, or datetime."""
    if isinstance(value, datetime):
        return ensure_aware(value, tz)
    if isinstance(value, (int, float)):
        seconds = float(value) / (1000.0 if value > 1e11 else 1.0)
        return datetime.fromtimestamp(seconds, pytz.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python 3.9's fromisoformat accepts exactly 3 or 6 fractional digits, so
    # normalise any run of them to 6 (pad short ones, trim long ones). Without
    # this a 4- or 5-digit fraction raises ValueError and the slot is silently
    # dropped by candidate_slots.
    text = re.sub(
        r"(\d{2}:\d{2}:\d{2})\.(\d+)",
        lambda m: "%s.%s" % (m.group(1), (m.group(2) + "000000")[:6]),
        text,
        count=1,
    )
    dt = datetime.fromisoformat(text)
    return ensure_aware(dt, tz)


def _shift_days(dt: datetime, days: int, tz=None) -> datetime:
    """Same wall-clock time N days later, DST-safe (re-localise, do not add to UTC).

    ``parse_iso`` returns a FIXED-offset ``datetime.timezone``, which has no
    ``localize`` and no idea that CDT ends on 2026-11-01: re-attaching it kept
    -05:00 across the change, so ``business_days_ahead(parse_iso(...), 5)``
    answered an hour early. Anything without ``localize`` is normalised into a
    real zone (``tz``, default America/Chicago) before the shift, so the wall
    clock is preserved and the offset follows the calendar.
    """
    if not hasattr(dt.tzinfo, "localize"):
        dt = to_tz(dt, tz or TZ)
    zone = dt.tzinfo
    naive = dt.replace(tzinfo=None) + timedelta(days=days)
    if hasattr(zone, "localize"):
        return zone.localize(naive)
    return naive.replace(tzinfo=zone)


def _key(dt: datetime) -> int:
    return int(ensure_aware(dt).timestamp())


# --------------------------------------------------------- business days
def business_days_ahead(now: datetime, n: int) -> datetime:
    """The datetime n business days (Mon-Fri) after ``now`` at the same wall
    clock time. n=0 returns ``now``."""
    now = ensure_aware(now)
    d = now
    count = 0
    while count < n:
        d = _shift_days(d, 1)
        if d.weekday() < 5:
            count += 1
    return d


def is_business_day(d: Union[date, datetime]) -> bool:
    return d.weekday() < 5


# ------------------------------------------------------------ candidates
def candidate_slots(
    free_slots: Iterable[Union[str, datetime]],
    now: datetime,
    already_offered: Optional[Iterable[Union[str, datetime]]] = None,
    tz=TZ,
    window: Tuple[int, int] = SLOT_WINDOW,
    min_lead_hours: int = MIN_LEAD_HOURS,
    max_business_days: int = MAX_BUSINESS_DAYS,
    slot_minutes: int = SLOT_MINUTES,
) -> List[datetime]:
    """Filter calendar free slots down to offerable ones, sorted, in ``tz``."""
    now_tz = to_tz(ensure_aware(now, tz), tz)
    earliest = now_tz + timedelta(hours=min_lead_hours)  # absolute instant; offset arithmetic is fine here
    last_date = business_days_ahead(now_tz, max_business_days).date()
    offered = set()  # type: Set[int]
    unreadable = 0
    for item in already_offered or ():
        try:
            offered.add(_key(parse_iso(item, tz)))
        except (ValueError, TypeError) as exc:
            # A stored reservation we cannot read means we cannot prove the slot
            # is free. Never swallow it: an unparsed entry is how the same slot
            # gets offered to a second lead.
            unreadable += 1
            logger.warning("already_offered entry is unreadable (%r): %s", item, exc)
            continue
    if unreadable:
        logger.warning(
            "%d of %d already_offered entries could not be parsed; double-offer protection is incomplete",
            unreadable, unreadable + len(offered),
        )
    win_start = window[0] * 60
    win_end = window[1] * 60

    seen = set()  # type: Set[int]
    out = []  # type: List[datetime]
    for raw in free_slots:
        try:
            dt = to_tz(parse_iso(raw, tz), tz)
        except (ValueError, TypeError) as exc:
            logger.warning("free slot is unreadable and was skipped (%r): %s", raw, exc)
            continue
        if dt.weekday() >= 5:
            continue
        minute_of_day = dt.hour * 60 + dt.minute
        if minute_of_day < win_start or minute_of_day + slot_minutes > win_end:
            continue
        if dt < earliest:
            continue
        if dt.date() > last_date:
            continue
        k = _key(dt)
        if k in offered or k in seen:
            continue
        seen.add(k)
        out.append(dt)
    out.sort(key=_key)
    return out


def pick_two(cands: List[datetime], spread: bool = True) -> List[datetime]:
    """Two slots, on different days when possible, else different hours."""
    if not cands:
        return []
    first = cands[0]
    if len(cands) == 1:
        return [first]
    second = None
    if spread:
        for c in cands[1:]:
            if c.date() != first.date():
                second = c
                break
    if second is None:
        for c in cands[1:]:
            if c.hour != first.hour or c.date() != first.date():
                second = c
                break
    if second is None:
        second = cands[1]
    return [first, second]


def _tz_label(dt: datetime, tz) -> str:
    zone = getattr(tz, "zone", "")
    if zone == "America/Chicago":
        return "CT"
    if zone == "America/New_York":
        return "ET"
    if zone == "America/Denver":
        return "MT"
    if zone == "America/Los_Angeles":
        return "PT"
    return dt.strftime("%Z")


def format_slot(dt: datetime, tz=TZ) -> str:
    """'Thu 3:30pm'. The am/pm is not optional: without it 17:00 reads as
    'Thu 5:00' and a prospect answering "7:00 is past my last slot" means 7am,
    and every counter-proposal in the thread is ambiguous."""
    dt = to_tz(dt, tz)
    hour = dt.hour % 12 or 12
    return "%s %d:%02d%s" % (dt.strftime("%a"), hour, dt.minute, "am" if dt.hour < 12 else "pm")


def format_slots(two: List[datetime], tz=TZ) -> str:
    """'Tue 2:00 or Thu 3:30 CT'."""
    if not two:
        return ""
    label = _tz_label(to_tz(two[0], tz), tz)
    if len(two) == 1:
        return "%s %s" % (format_slot(two[0], tz), label)
    return "%s or %s %s" % (format_slot(two[0], tz), format_slot(two[1], tz), label)


def _zone_of(zone) -> object:
    """A pytz zone for ``zone``: a tzinfo is used as is, a zone name is
    loaded, and None or a name pytz does not know is Central."""
    if zone is None:
        return TZ
    if isinstance(zone, str):
        try:
            return pytz.timezone(zone)
        except Exception:  # noqa: BLE001 - an unknown name reads as Central, the calendar's zone
            return TZ
    return zone


def format_asked_time(dt: datetime, zone=None, dated: bool = False) -> str:
    """The time a lead proposed, written back in the zone the lead wrote it
    in, with that zone's label: 'Thu 11:00am ET'. ``zone`` is a pytz zone or
    a zone name; None (the lead named no zone) or an unknown name is Central,
    labelled 'CT'. ``dated`` adds the month and day ('Tue Sep 29 2:00pm PT')
    for a counter-proposal that crosses a week.

    format_slot drops the zone on purpose (the call time is always Central),
    but a refused time converted to Central and printed bare reads back to
    the lead as a different time: "Thursday 11am ET" came back as
    "Thu 10:00am"."""
    tz = _zone_of(zone)
    local = to_tz(dt, tz)
    text = format_slot(local, tz)
    if dated:
        text = "%s %s %d %s" % (local.strftime("%a"), local.strftime("%b"), local.day, text.split(" ", 1)[1])
    return "%s %s" % (text, _tz_label(local, tz))


def is_offerable(
    dt: Union[str, datetime],
    now: datetime,
    already_offered: Optional[Iterable[Union[str, datetime]]] = None,
    tz=TZ,
    window: Tuple[int, int] = SLOT_WINDOW,
    min_lead_hours: int = MIN_LEAD_HOURS,
    max_business_days: int = MAX_BUSINESS_DAYS,
    slot_minutes: int = SLOT_MINUTES,
) -> bool:
    """True when this one time satisfies every rule candidate_slots enforces.

    A lead-proposed time (parse_proposed_time) must be checked with this before
    it is booked: 11:30 on a Wednesday parses fine but breaks the no-mornings
    rule, and nothing else in the library ties the parser to SLOT_WINDOW.
    """
    return bool(
        candidate_slots(
            [dt], now, already_offered, tz=tz, window=window,
            min_lead_hours=min_lead_hours, max_business_days=max_business_days,
            slot_minutes=slot_minutes,
        )
    )


def within_send_window(now: datetime, tz=TZ, window: Tuple[int, int] = SEND_WINDOW) -> bool:
    """07:00 <= CT hour < 19:00. Hour only: this says nothing about the weekday,
    so anything that auto-sends must use is_send_time() instead."""
    ct = to_tz(ensure_aware(now, tz), tz)
    return window[0] <= ct.hour < window[1]


def is_send_time(now: datetime, tz=TZ, window: Tuple[int, int] = SEND_WINDOW) -> bool:
    """The full send gate for anything that goes out without Lorenzo in the
    loop: a business day AND inside the send window (Blueprint S2 'skip
    weekends'). within_send_window() alone answers True on a Saturday."""
    ct = to_tz(ensure_aware(now, tz), tz)
    return is_business_day(ct) and within_send_window(ct, tz, window)


# --------------------------------------------------------------- parsing
def _quote_starts_at(lines: List[str], i: int) -> bool:
    """True when the quoted history begins at line ``i``."""
    line = lines[i].strip()
    if not line:
        return False
    if _QUOTE_HEADER_RE.match(line):
        return True
    # Wrapped attribution: join this "On ..." line with the next one or two and
    # look for the trailing "wrote:".
    if _ON_START_RE.match(line):
        joined = line
        for j in range(i + 1, min(i + 3, len(lines))):
            joined = joined + " " + lines[j].strip()
            if _WROTE_END_RE.search(joined):
                return True
            if len(joined) > 400:
                break
    return False


def strip_quoted(text: str) -> str:
    """Keep only the lead's own words: cut at quote markers / reply headers.

    Returns "" when nothing survives above the quote. It must NOT fall back to
    the raw text: a bottom-posted reply would then be parsed as if Lorenzo's
    own offered times were the lead's proposal.
    """
    raw_lines = (text or "").splitlines()
    kept = []  # type: List[str]
    for i in range(len(raw_lines)):
        if _quote_starts_at(raw_lines, i):
            break
        kept.append(raw_lines[i])
    top = "\n".join(kept).strip()
    # Single-line replies where the quote follows on the same line
    for marker in (" On ", "-----Original Message-----", "________________"):
        idx = top.find(marker)
        if idx > 20 and re.search(r"wrote:|Original Message|_{5,}", top[idx:]):
            top = top[:idx]
    return top.strip()


def strip_phone_numbers(text: str) -> str:
    """Blank out phone-shaped runs so they cannot be read as times."""
    return _PHONE_RE.sub(" ", text or "")


def detect_tz(text: str):
    """pytz timezone named in the text, or None."""
    m = _TZ_RE.search(text or "")
    if not m:
        return None
    return TZ_ALIASES.get(m.group(1).lower())


def _hour_from_bare(hour: int) -> int:
    """Business-hours heuristic for a bare hour with no am/pm: 1-6 -> pm, 7-11 -> am."""
    if 1 <= hour <= 6:
        return hour + 12
    return hour


def _parse_time(text: str) -> Optional[Tuple[int, int]]:
    m = _AMPM_RE.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if hour > 12 or minute > 59:
            return None
        if m.group(3).lower() == "p" and hour != 12:
            hour += 12
        if m.group(3).lower() == "a" and hour == 12:
            hour = 0
        return hour, minute
    if _NOON_RE.search(text):
        return 12, 0
    m = _COLON_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour <= 23 and minute <= 59:
            if hour <= 12:
                hour = _hour_from_bare(hour)
            return hour, minute
    m = _OCLOCK_RE.search(text)
    if m is None:
        for cue in _CUE_RE.finditer(text):
            if _cue_is_a_time(text, cue):
                m = cue
                break
    if m:
        hour = int(m.group(1))
        if 1 <= hour <= 12:
            return _hour_from_bare(hour), 0
    return None


def _parse_day(text: str, now_local: datetime, time_hm: Tuple[int, int]) -> Optional[date]:
    m = _DAY_RE.search(text)
    if not m:
        return None
    word = m.group(2).lower()
    today = now_local.date()
    if word == "today":
        return today
    if word == "tomorrow":
        return today + timedelta(days=1)
    weekday = WEEKDAYS[word]
    delta = (weekday - today.weekday()) % 7
    target = today + timedelta(days=delta)
    modifier = (m.group(1) or "").lower()
    if modifier in ("next", "coming"):
        # "next Tuesday" said on a Monday is the Tuesday of the following week,
        # not tomorrow. Applies for every delta, not only when delta == 0.
        return target + timedelta(days=7)
    if delta == 0:
        # same weekday as today: only "today" if the time is still ahead of us
        if (time_hm[0], time_hm[1]) <= (now_local.hour, now_local.minute):
            target = target + timedelta(days=7)
    return target


def parse_availability_window(text: str, default_tz=TZ) -> Optional[Tuple[int, int, object]]:
    """'3pm-6pm Eastern time' -> (15, 18, <America/New_York>). None if no range."""
    top = strip_phone_numbers(strip_quoted(text))
    m = _RANGE_RE.search(top)
    if not m:
        return None
    if not (m.group(3) or m.group(6)):
        # bare "3-6" is too ambiguous (phone numbers, dates) unless a tz follows closely
        tail = top[m.end(): m.end() + 24]
        if not _TZ_RE.search(tail):
            return None
    start_h = int(m.group(1))
    end_h = int(m.group(4))
    start_ap = (m.group(3) or "").lower().replace(".", "")
    end_ap = (m.group(6) or "").lower().replace(".", "")
    if not start_ap and end_ap:
        start_ap = end_ap if start_h <= end_h else ("am" if end_ap == "pm" else "pm")
    if not end_ap and start_ap:
        end_ap = start_ap if end_h > start_h else ("pm" if start_ap == "am" else "am")
    if start_ap.startswith("p") and start_h != 12:
        start_h += 12
    if end_ap.startswith("p") and end_h != 12:
        end_h += 12
    if not start_ap and not end_ap:
        start_h, end_h = _hour_from_bare(start_h), _hour_from_bare(end_h)
    if start_h > 23 or end_h > 24 or start_h >= end_h:
        return None
    tz = detect_tz(top) or default_tz
    return start_h, end_h, tz


def parse_proposed_time(text: str, now: datetime, tz=TZ) -> Optional[datetime]:
    """A single concrete proposed time from a reply, converted to ``tz`` (CT).

    Handles "Thursday 4pm Eastern time", "Monday at 2 CTS", "this Wednesday
    around 11:30 am", "Friday. Afternoon. How's 2pm EST?". Returns None for
    availability ranges ("every day 3pm-6pm") and for text with no day+time.
    """
    top = strip_phone_numbers(strip_quoted(text))
    if not top:
        return None
    if parse_availability_window(top, tz) is not None:
        return None
    lead_tz = detect_tz(top) or tz
    now_local = to_tz(ensure_aware(now, tz), lead_tz)
    hm = _parse_time(top)
    if hm is None:
        return None
    day = _parse_day(top, now_local, hm)
    if day is None:
        return None
    naive = datetime(day.year, day.month, day.day, hm[0], hm[1])
    try:
        local = lead_tz.localize(naive, is_dst=None)
    except pytz.exceptions.AmbiguousTimeError:
        local = lead_tz.localize(naive, is_dst=False)
    except pytz.exceptions.NonExistentTimeError:
        local = lead_tz.localize(naive + timedelta(hours=1), is_dst=True)
    return local.astimezone(tz)
