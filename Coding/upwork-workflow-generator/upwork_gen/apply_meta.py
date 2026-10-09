"""Apply-time columns of proposals.csv: job_created_utc, age_hours_at_apply,
connects and boosted.

Best effort only: data that is missing or unreadable leaves the column blank,
and meta_for() never raises, so finalize logs the row either way.

Sources, first one found wins:
  job_created_utc  --posted <ISO UTC time>; a `created_utc: <ISO time>` line in
                   jd.txt (find_jobs action=search `created_date`); a
                   "Posted YYYY-MM-DD" date in jd.txt (date only; "Posted about
                   ..." is an estimate and is skipped).
  age_hours_at_apply  hours from job_created_utc to now, one decimal, only when
                   job_created_utc has a time of day.
  connects         --connects N; "Connects to apply: N" (or a `connects: N`
                   line) in jd.txt.
  boosted          --boosted yes|no (sync_outcomes.py --fill-boosted fills it
                   later from Upwork when it is left blank).
"""

from __future__ import annotations

import datetime
import os
import re
import sys
from typing import Dict, Optional, Tuple

META_FIELDS = ("job_created_utc", "age_hours_at_apply", "connects", "boosted")

_CREATED_LINE = re.compile(r"^\s*(?:created_utc|posted_utc)\s*:\s*(\S+)\s*$", re.I | re.M)
_POSTED_DATE = re.compile(r"\bPosted (\d{4}-\d{2}-\d{2})\b")
_CONNECTS = re.compile(r"\bConnects to apply:\s*(\d+)", re.I)
_CONNECTS_LINE = re.compile(r"^\s*connects\s*:\s*(\d+)\s*$", re.I | re.M)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_AGE_HOURS = 24 * 365


def parse_utc(text: Optional[str]) -> Optional[datetime.datetime]:
    """An aware UTC datetime for an ISO time ("2026-09-28T11:04:11.561Z",
    "2026-09-28T11:04Z", "2026-09-28 06:04:11-05:00"; no offset = UTC), or None
    for anything else, a bare date included."""
    text = (text or "").strip()
    if not text or _DATE.match(text):
        return None
    value = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    # Python 3.9's fromisoformat takes exactly 3 or 6 fraction digits and a +HH:MM offset.
    value = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], value)
    value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value)
    try:
        parsed = datetime.datetime.fromisoformat(value.replace(" ", "T", 1))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def format_utc(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_date(text: str) -> bool:
    try:
        datetime.datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def job_created(jd_text: str, posted: Optional[str] = None
                ) -> Tuple[str, Optional[datetime.datetime]]:
    """(job_created_utc value, its datetime when it has a time of day)."""
    for i, source in enumerate(([posted] if posted else []) + _CREATED_LINE.findall(jd_text or "")):
        moment = parse_utc(source)
        if moment is not None:
            return format_utc(moment), moment
        if _DATE.match(source.strip()) and _valid_date(source.strip()):
            return source.strip(), None
        if posted and i == 0:
            try:
                print("apply: --posted %r not parsed, falling back to jd.txt" % posted, file=sys.stderr)
            except Exception:
                pass
    match = _POSTED_DATE.search(jd_text or "")
    if match and _valid_date(match.group(1)):
        return match.group(1), None
    return "", None


def age_hours(created: Optional[datetime.datetime], now: datetime.datetime) -> str:
    """Hours from `created` to `now` (a naive `now` is local time), or "" when
    there is no creation time or the gap is negative or implausibly large."""
    if created is None:
        return ""
    now_utc = now.astimezone(datetime.timezone.utc)
    hours = (now_utc - created).total_seconds() / 3600.0
    if hours < 0 or hours > _MAX_AGE_HOURS:
        return ""
    return "{:.1f}".format(hours)


def connects_cost(jd_text: str, override: Optional[int] = None) -> str:
    if override is not None:
        return str(override) if override >= 0 else ""
    match = _CONNECTS.search(jd_text or "") or _CONNECTS_LINE.search(jd_text or "")
    return match.group(1) if match else ""


def normalize_boosted(value: Optional[str]) -> str:
    value = (value or "").strip().lower()
    if value in ("yes", "y", "true"):
        return "yes"
    if value in ("no", "n", "false"):
        return "no"
    return ""


def meta_for(job_dir: str, now: datetime.datetime, posted: Optional[str] = None,
             connects: Optional[int] = None, boosted: Optional[str] = None) -> Dict[str, str]:
    """The four apply-time columns for the job in `job_dir`; blank where the
    data is missing. Never raises."""
    meta = {key: "" for key in META_FIELDS}
    try:
        path = os.path.join(job_dir, "jd.txt")
        jd_text = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                jd_text = fh.read()
        created, moment = job_created(jd_text, posted)
        meta["job_created_utc"] = created
        meta["age_hours_at_apply"] = age_hours(moment, now)
        meta["connects"] = connects_cost(jd_text, connects)
        meta["boosted"] = normalize_boosted(boosted)
    except Exception:  # noqa: BLE001 - a blank column is always acceptable
        pass
    return meta


def describe(meta: Dict[str, str]) -> str:
    """One line for finalize's output: each column's value, or "blank"."""
    return ", ".join("{} {}".format(key, meta.get(key) or "blank") for key in META_FIELDS)
