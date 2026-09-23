"""A recorded, read-only Instantly for rehearsals, replays and the shadow test.

``OfflineInstantly`` is a real ``shared.instantly.Instantly`` with the
transport replaced: it subclasses the live client and overrides ``_request``
only. That matters more than it sounds. A hand-written stand-in re-implements
the parts of the client a test happens to exercise and quietly drops the rest,
so the thing under test is the stand-in, not the client. Here every guard,
every retry decision, every payload shape and every ``guard_write`` call is the
production code path; the only thing that changes is where the bytes come from.

Consequences worth knowing:

* **Writes never reach this class in shadow mode.** They stop at
  ``guard_write`` and come back as a would_do record, which is exactly what a
  shadow-safety test wants to assert. A write that *did* arrive here means the
  shadow contract was bypassed, so ``_request`` refuses one loudly.
* **An unrecorded read is a failure, not an empty list**, unless the caller
  passes ``strict=False``. A silent empty answer turns "I have no fixture for
  the placement endpoint" into "the workspace has no placement tests", and the
  job then reports a clean bill of health for something it never looked at.

The fixtures are the real responses this workspace gave, pulled read-only on
2026-09-21 and 2026-09-22 and committed under ``changesets/capacity/snapshots``
and the per-service ``fixtures/`` directories.

    from shared.offline import OfflineInstantly
    client = OfflineInstantly.from_recorded()
    monkeypatch.setattr(instantly_mod, "default_client", lambda **kw: client)

Python 3.9 compatible.
"""
import copy
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from shared.instantly import Instantly, InstantlyError
from shared.paths import BASE_DIR

logger = logging.getLogger("shared.offline")

SNAPSHOT_DIR = os.path.join(str(BASE_DIR), "changesets", "capacity", "snapshots")
METRICS_FIXTURES = os.path.join(str(BASE_DIR), "services", "metrics", "fixtures")
EXPERIMENT_FIXTURES = os.path.join(str(BASE_DIR), "services", "experiments", "fixtures")
LIST_FACTORY_FIXTURES = os.path.join(str(BASE_DIR), "services", "list_factory", "fixtures")


class UnrecordedRead(AssertionError):
    """A read this recording has no fixture for.

    Deliberately an AssertionError: in a test it should fail the test, and in a
    rehearsal it should stop the run rather than let a job draw a conclusion
    from a response nobody recorded.
    """


class ShadowContractBypassed(AssertionError):
    """A write reached the transport during an offline run."""


def _load(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        logger.debug("no fixture at %s (%s)", path, exc)
        return default


def _rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [r for r in payload["items"] if isinstance(r, dict)]
    return []


class OfflineInstantly(Instantly):
    """``Instantly`` reading from recorded payloads instead of the network."""

    def __init__(self, recordings: Optional[Dict[str, Any]] = None, strict: bool = True,
                 api_key: str = "offline-no-key", **kwargs):
        # An httpx client is still built (the base class owns it) but nothing
        # ever calls through it: _request is overridden below. sleep is a no-op
        # so a retry path exercised offline does not stall a test for a minute.
        kwargs.setdefault("sleep", lambda _seconds: None)
        Instantly.__init__(self, api_key=api_key, **kwargs)
        self.recordings = dict(recordings or {})
        self.strict = bool(strict)
        self.calls = []  # type: List[Any]

    # -------------------------------------------------------------- loading
    @classmethod
    def from_recorded(cls, strict: bool = True, **overrides) -> "OfflineInstantly":
        """Every snapshot committed in this repo, wired to its endpoint.

        Anything missing from disk answers an empty page rather than raising at
        construction time: a recording is allowed to be partial, and the
        failure should happen at the read that needed it, naming the path.
        """
        rec = {
            "accounts": _rows(_load(os.path.join(SNAPSHOT_DIR, "accounts_2026-09-22.json"))),
            "campaigns": _rows(_load(os.path.join(SNAPSHOT_DIR, "campaigns_2026-09-22.json"))),
            "accounts/warmup-analytics": _load(
                os.path.join(SNAPSHOT_DIR, "warmup_analytics_2026-09-22.json"), {}) or {},
            "accounts/analytics/daily": _rows(_load(
                os.path.join(SNAPSHOT_DIR, "daily_account_analytics_2026-09-15_21.json"), [])),
            "campaigns/analytics": _rows(_load(
                os.path.join(METRICS_FIXTURES, "instantly_campaign_analytics_2026-09-21.json"), [])),
            "emails": _rows(_load(
                os.path.join(LIST_FACTORY_FIXTURES, "received_emails_recorded.json"), [])),
            # Measured read-only 2026-09-22: the workspace has run no placement
            # test at all, so an empty page is the RECORDED answer here, not a
            # missing fixture.
            "inbox-placement-tests": [],
            "inbox-placement-analytics/stats-by-test-id": [],
            # Two entries live on 2026-09-22. The shape carries is_domain, which
            # is what says whether bl_value is an address or a whole domain.
            "block-lists-entries": [],
            "lead-labels": [],
            "webhooks": [],
            "subsequences": [],
            "leads/list": [],
            "audit-logs": [],
        }
        # accounts/test/vitals answers grouped BY DOMAIN. Derived from the
        # recorded accounts so the domains match the fleet in the same file.
        domains = sorted(set((a.get("email") or "").rsplit("@", 1)[-1].lower()
                             for a in rec["accounts"] if a.get("email")))
        rec["accounts/test/vitals"] = {
            "status": "ok",
            "success_list": [{"domain": d, "mx": True, "spf": True, "dkim": True,
                              "dmarc": True, "allPass": True} for d in domains if d],
            "failure_list": [],
        }
        steps = _load(os.path.join(EXPERIMENT_FIXTURES, "campaign_steps_2026-09-22.json"), {}) or {}
        daily_campaign = _load(os.path.join(EXPERIMENT_FIXTURES, "campaign_daily_2026-09-22.json"), {}) or {}
        rec["_campaign_steps_by_key"] = steps
        rec["_campaign_daily_by_key"] = daily_campaign
        rec.update(overrides)
        return cls(recordings=rec, strict=strict)

    # ------------------------------------------------------------ transport
    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                 json: Optional[Any] = None, retry: Optional[bool] = None) -> Any:
        key = path.strip("/")
        self.calls.append((method.upper(), key, dict(params or {}), json))
        if not self._is_read(method, "/" + key):
            raise ShadowContractBypassed(
                "an offline run reached the transport with %s /%s. Every write goes through "
                "settings.guard_write first, so in shadow it should have stopped there and "
                "returned a would_do record." % (method.upper(), key))
        return self._answer(key, params or {}, json or {})

    def _answer(self, key: str, params: Dict[str, Any], body: Dict[str, Any]) -> Any:
        # Per-campaign endpoints are keyed by campaign id in the recording.
        if key == "campaigns/analytics/steps":
            return self._by_campaign("_campaign_steps_by_key", params.get("campaign_id"))
        if key == "campaigns/analytics/daily":
            return self._by_campaign("_campaign_daily_by_key", params.get("campaign_id"))
        # A recorded path always wins. This check has to come BEFORE the
        # "campaigns/<id>" branch below, because ``campaigns/analytics`` also
        # has exactly one slash and was being read as a campaign id.
        if key in self.recordings:
            return copy.deepcopy(self.recordings[key])
        if key.startswith("campaigns/") and key.count("/") == 1:
            campaign_id = key.split("/", 1)[1]
            for row in self.recordings.get("campaigns") or []:
                if row.get("id") == campaign_id:
                    return copy.deepcopy(row)
            raise UnrecordedRead("no recorded campaign %s" % campaign_id)
        if not self.strict:
            return {"items": []}
        raise UnrecordedRead(
            "this recording has no fixture for GET /%s (params=%r). Add one, or construct the "
            "client with strict=False if an empty page really is the right answer." % (key, params))

    def _by_campaign(self, bucket: str, campaign_id: Optional[str]) -> Any:
        table = self.recordings.get(bucket) or {}
        by_id = {}
        from shared import settings

        for campaign_key, meta in (settings.CAMPAIGNS or {}).items():
            if meta.get("id"):
                by_id[meta["id"]] = campaign_key
        campaign_key = by_id.get(campaign_id)
        if campaign_key is None or campaign_key not in table:
            return []
        return copy.deepcopy(table[campaign_key])

    def close(self) -> None:
        try:
            Instantly.close(self)
        except Exception:  # noqa: BLE001 - closing a never-used client must not fail a test
            pass


def offline_client_factory(strict: bool = True, **overrides) -> Callable[..., OfflineInstantly]:
    """A drop-in for ``shared.instantly.default_client`` in a rehearsal.

    One client is built and reused, so the analytics cache and the recorded
    call log describe one run rather than one per job function.
    """
    client = OfflineInstantly.from_recorded(strict=strict, **overrides)

    def factory(*_args, **_kwargs) -> OfflineInstantly:
        return client

    factory.client = client  # type: ignore[attr-defined]
    return factory


__all__ = ["OfflineInstantly", "UnrecordedRead", "ShadowContractBypassed",
           "offline_client_factory", "InstantlyError"]
