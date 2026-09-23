"""Scheduled jobs Lorenzo turned off (config/turned_off_jobs.json).

He runs these by hand now. Their code stays in git, but nothing schedules
them, so a reader that expects their output must say "turned off", never
"missing" or "failed":

    from shared import turned_off
    turned_off.is_off("campaign_verdicts")          # True
    turned_off.label("upwork_rooms_am")             # 'turned off since 2026-09-22 (...)'

Never raises: a missing or unreadable file means nothing is turned off.
Standard library only. Python 3.9.
"""
import json
import logging
from typing import Any, Dict, List

from shared.paths import CONFIG_DIR

logger = logging.getLogger("shared.turned_off")

PATH = CONFIG_DIR / "turned_off_jobs.json"
UPWORK_ROOMS_JOBS = ("upwork_rooms_am", "upwork_rooms_pm")


def load(path=None) -> Dict[str, Dict[str, Any]]:
    """{schedule name: record} for every turned-off job."""
    try:
        with open(str(path or PATH), "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except IOError:
        return {}
    except ValueError as exc:
        logger.warning("config/turned_off_jobs.json is not valid JSON (%s); treating nothing as turned off", exc)
        return {}
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return {}
    return dict((str(k), v if isinstance(v, dict) else {}) for k, v in jobs.items())


def names(path=None) -> List[str]:
    return sorted(load(path))


def is_off(name: str, path=None) -> bool:
    return str(name) in load(path)


def label(name: str, path=None) -> str:
    """One line for a report: 'turned off since <date> (<why>; by hand: <cmd>)'."""
    rec = load(path).get(str(name))
    if rec is None:
        return ""
    parts = [p for p in (rec.get("why"), ("by hand: %s" % rec["by_hand"]) if rec.get("by_hand") else None) if p]
    return "turned off since %s%s" % (rec.get("turned_off_on") or "?", (" (%s)" % "; ".join(parts)) if parts else "")


def upwork_rooms_off(path=None) -> bool:
    """Both scheduled Upwork rooms digests are turned off."""
    jobs = load(path)
    return all(n in jobs for n in UPWORK_ROOMS_JOBS)
