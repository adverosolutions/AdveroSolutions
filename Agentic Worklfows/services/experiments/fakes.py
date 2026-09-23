"""A fixture-backed stand-in for ``shared.instantly.Instantly``.

The fixtures in ``services/experiments/fixtures/`` are the real responses this
workspace gave on 2026-09-22, pulled read-only. Tests run against them so the
verdict rules are exercised on real shapes (string, zero-based step and
variant indices; a totals row with ``step: null``; `reply_count_unique` that
already excludes automatic replies) without touching the API.

``FakeInstantly`` answers only the reads ``services.experiments`` makes. It
has no write methods at all, which is the point: a test that reaches for one
fails loudly instead of silently shadow-logging.
"""
import copy
import json
import os
from typing import Any, Dict, List, Optional

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

OVERVIEW_FIXTURE = "campaign_overview_2026-09-22.json"
STEPS_FIXTURE = "campaign_steps_2026-09-22.json"
LEADS_FIXTURE = "replied_leads_2026-09-22.json"
DAILY_FIXTURE = "campaign_daily_2026-09-22.json"
CAMPAIGNS_FIXTURE = "campaigns_2026-09-22.json"


def load_fixture(name: str) -> Any:
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


class _Walk(list):
    """What ``Instantly.iterate`` returns: an iterable that also reports
    whether the cursor ran out or the page cap stopped it."""

    def __init__(self, rows, truncated=False):
        list.__init__(self, rows)
        self.truncated = truncated
        self.complete = not truncated
        self.pages = 1


class FakeInstantly(object):
    def __init__(
        self,
        overview: Optional[List[Dict[str, Any]]] = None,
        steps: Optional[Dict[str, Any]] = None,
        leads: Optional[Dict[str, Any]] = None,
        daily: Optional[Dict[str, Any]] = None,
        campaigns: Optional[Dict[str, Any]] = None,
        truncate_leads: bool = False,
    ):
        self.overview = copy.deepcopy(overview if overview is not None else load_fixture(OVERVIEW_FIXTURE))
        self.steps = copy.deepcopy(steps if steps is not None else load_fixture(STEPS_FIXTURE))
        self.leads = copy.deepcopy(leads if leads is not None else load_fixture(LEADS_FIXTURE))
        self.daily = copy.deepcopy(daily if daily is not None else load_fixture(DAILY_FIXTURE))
        self.campaigns = copy.deepcopy(campaigns if campaigns is not None else load_fixture(CAMPAIGNS_FIXTURE))
        self.truncate_leads = truncate_leads
        self.calls = []  # type: List[Any]
        self.closed = False
        self._by_id = {}
        for key, campaign in self.campaigns.items():
            self._by_id[campaign.get("id")] = key

    # ---------------------------------------------------------------- reads
    def campaign_analytics(self, ids=None, start_date=None, end_date=None):
        self.calls.append(("campaign_analytics", ids))
        return copy.deepcopy(self.overview)

    def _get(self, path, params=None):
        self.calls.append(("GET", path, dict(params or {})))
        if path.strip("/") == "campaigns/analytics/steps":
            key = self._key(params.get("campaign_id"))
            return copy.deepcopy(self.steps.get(key) or [])
        raise AssertionError("FakeInstantly has no fixture for GET %s %r" % (path, params))

    def iterate(self, path, params=None, body=None, max_pages=200):
        self.calls.append(("iterate", path, dict(body or {})))
        if path.strip("/") != "leads/list":
            raise AssertionError("FakeInstantly only iterates leads/list, not %s" % path)
        key = self._key((body or {}).get("campaign"))
        rows = copy.deepcopy(self.leads.get(key) or [])
        if self.truncate_leads:
            return _Walk(rows[:1], truncated=True)
        return _Walk(rows)

    def get_campaign(self, id):
        self.calls.append(("get_campaign", id))
        key = self._key(id)
        if key is None:
            raise AssertionError("FakeInstantly has no campaign fixture for %r" % id)
        return copy.deepcopy(self.campaigns[key])

    def daily_campaign_analytics(self, campaign_id, start_date, end_date):
        self.calls.append(("daily", campaign_id, start_date, end_date))
        key = self._key(campaign_id)
        return copy.deepcopy(self.daily.get(key) or [])

    def close(self):
        self.closed = True

    # ------------------------------------------------------------- internals
    def _key(self, campaign_id):
        return self._by_id.get(campaign_id)
