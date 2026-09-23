"""Where raw businesses come from, and the gate that stops them costing money.

Three sources, one interface:

    FixtureSource   a recorded JSON/CSV file. Free, deterministic, offline.
    ApifySource     Coding/lead-scrape-2026/runner.py, sharded by US state
                    because the actor has no offset and identical filters
                    return byte-identical leads (measured: 100% overlap on a
                    repeat run, 0% overlap across states).
    MapsSource      execution/google_maps_scraper.py, sharded by metro.

Both live sources are PAID or rate-limited and neither runs unless
``ALLOW_PAID_CALLS=1``. Without it they raise ``PaidCallBlocked`` carrying the
dollar figure the run would have spent, which the ledger records as a
would-have-cost instead of a cost.
"""
import csv
import json
import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from services.list_factory import models
from services.list_factory.ledger import PRICES

logger = logging.getLogger("list_factory.sources")

# Sharding axis for the Apify actor, copied from runner.SHARD_WEIGHTS so the
# factory and the standalone runner agree about supply per state.
SHARD_WEIGHTS = {
    "california, us": 200, "texas, us": 180, "new york, us": 170,
    "florida, us": 160, "illinois, us": 120, "pennsylvania, us": 110,
    "michigan, us": 100, "north carolina, us": 100, "virginia, us": 90,
    "ohio, us": 90, "massachusetts, us": 90, "georgia, us": 90,
}

TRUTHY = ("1", "true", "yes", "on", "y", "t")


class PaidCallBlocked(Exception):
    """A paid third-party call was attempted without ALLOW_PAID_CALLS=1."""

    def __init__(self, service: str, units: int, usd: float, detail: str = ""):
        Exception.__init__(self, "%s blocked: %d units, would have cost $%.4f. %s" % (service, units, usd, detail))
        self.service = service
        self.units = units
        self.usd = round(usd, 6)
        self.detail = detail


def paid_calls_allowed() -> bool:
    """Runtime gate, read live so a test can flip it."""
    return os.environ.get("ALLOW_PAID_CALLS", "").strip().lower() in TRUTHY


def require_paid(service: str, units: int, usd: float, detail: str = "") -> None:
    if not paid_calls_allowed():
        raise PaidCallBlocked(service, units, usd, detail)


def plan_shards(target: int, fill_rate: float, weights: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """Per-state fetch quotas for ``target`` usable contacts.

    ``fill_rate`` is the measured share of returned rows that carry what we
    need, so the run over-fetches by 1/fill_rate. Identical to
    ``runner.plan_shards`` on purpose.
    """
    weights = weights or SHARD_WEIGHTS
    fill_rate = max(0.01, float(fill_rate))
    total = int(round(target / fill_rate))
    denom = sum(weights.values()) or 1
    return dict((state, max(1, int(round(total * w / float(denom))))) for state, w in weights.items())


# ------------------------------------------------------------------ sources
class SourceError(Exception):
    """The source could not deliver. Not the same as 'it returned few rows'."""


# Apify bills per lead ACTUALLY returned, so a run whose shards half failed is
# billed for what came back, not for what was planned. Above this share of
# failed shards the source raises instead of quietly returning a short list
# that every downstream stage then reports as "ok".
MAX_FAILED_SHARD_SHARE = 0.25


class Source(object):
    name = "source"

    def __init__(self):
        # What the last fetch actually incurred, as opposed to what was
        # planned. None when the source has not run.
        self.last_run_cost = None  # type: Optional[float]

    def estimate_cost(self, target: int, fill_rate: float) -> float:
        raise NotImplementedError

    def fetch(self, niche: str, target: int, fill_rate: float) -> List[Dict[str, Any]]:
        raise NotImplementedError


class FixtureSource(Source):
    """A recorded file. Free. This is what the Sunday rehearsal and every test
    run against."""

    name = "fixture"

    def __init__(self, path: str):
        Source.__init__(self)
        self.path = path

    def estimate_cost(self, target: int, fill_rate: float) -> float:
        return 0.0

    def fetch(self, niche: str, target: int, fill_rate: float) -> List[Dict[str, Any]]:
        rows = load_records(self.path)
        if target and target > 0:
            rows = rows[: max(target, 0)] if len(rows) > target else rows
        shard = os.path.basename(self.path)
        self.last_run_cost = 0.0
        return [models.new_lead(row, source="fixture:%s" % shard, shard=shard) for row in rows]


class ApifySource(Source):
    """code_crafter/leads-finder through the sharded runner. PAID."""

    name = "apify"

    def __init__(self, run_shard: Optional[Callable[..., Dict[str, Any]]] = None, weights: Optional[Dict[str, int]] = None):
        Source.__init__(self)
        self._run_shard = run_shard
        self.weights = weights or SHARD_WEIGHTS

    def estimate_cost(self, target: int, fill_rate: float) -> float:
        shards = plan_shards(target, fill_rate, self.weights)
        return round(len(shards) * PRICES["apify_run_start"] + sum(shards.values()) * PRICES["apify_per_lead"], 4)

    def cost_for(self, shards_started: int, rows_returned: int) -> float:
        """What Apify actually bills: a start fee per shard, plus per lead
        RETURNED. Charging the plan instead billed the ledger for rows a failed
        shard never delivered."""
        return round(shards_started * PRICES["apify_run_start"]
                     + rows_returned * PRICES["apify_per_lead"], 6)

    def fetch(self, niche: str, target: int, fill_rate: float) -> List[Dict[str, Any]]:
        shards = plan_shards(target, fill_rate, self.weights)
        usd = self.estimate_cost(target, fill_rate)
        require_paid(
            "apify:code_crafter/leads-finder", sum(shards.values()), usd,
            "%d state shards. Cancelled runs still bill, so do not start one to 'see what happens'." % len(shards),
        )
        runner = self._run_shard or _import_runner_run_shard()
        filters = _load_niche_filters(niche)
        token = _apify_token()
        out = []  # type: List[Dict[str, Any]]
        failed = []  # type: List[str]
        started = 0
        for state, quota in sorted(shards.items()):
            started += 1
            result = runner(niche, state, quota, filters, token)
            if result.get("error"):
                logger.warning("apify shard %s/%s failed: %s", niche, state, result["error"])
                failed.append("%s: %s" % (state, result["error"]))
                continue
            for row in result.get("leads") or []:
                out.append(models.new_lead(row, source="apify:leads-finder", shard=state))
        rows = models.dedupe(out)
        self.last_run_cost = self.cost_for(started, len(out))
        if shards and float(len(failed)) / len(shards) > MAX_FAILED_SHARD_SHARE:
            # Swallowing shard failures returned a short list that every later
            # stage happily processed and the job reported as ok. A Sunday run
            # that quietly produced nothing is the failure Blueprint Section 6
            # ("every campaign has >= 5 days of uncontacted leads") exists to
            # catch, and Lorenzo would find out on Thursday.
            raise SourceError(
                "%d of %d Apify shards failed (%s); refusing to return a short list that reads "
                "like a complete one. Shards already started were billed."
                % (len(failed), len(shards), "; ".join(failed[:4]))
            )
        return rows


class MapsSource(Source):
    """execution/google_maps_scraper.py, sharded by metro. No per-call fee, but
    it drives a real browser against Google and is gated all the same: an
    unattended Sunday run that trips Google's bot detection costs the scraper,
    which is not a line item but is still a cost."""

    name = "gmaps"

    def __init__(self, metros: Optional[List[str]] = None, search: Optional[Callable[..., List[Dict[str, Any]]]] = None):
        Source.__init__(self)
        self.metros = metros or []
        self._search = search

    def estimate_cost(self, target: int, fill_rate: float) -> float:
        return round(target * PRICES["gmaps_per_business"], 4)

    def fetch(self, niche: str, target: int, fill_rate: float) -> List[Dict[str, Any]]:
        require_paid("google_maps_scraper", target, self.estimate_cost(target, fill_rate),
                     "Playwright against live Google Maps.")
        search = self._search or _import_maps_search()
        query = _load_niche_query(niche)
        per_metro = max(1, int(round(target / float(max(1, len(self.metros))))))
        out = []  # type: List[Dict[str, Any]]
        for metro in self.metros:
            for row in search(query, metro, per_metro) or []:
                out.append(models.new_lead(row, source="gmaps", shard=metro))
        self.last_run_cost = 0.0
        return models.dedupe(out)


def build(name: str, fixture: Optional[str] = None, metros: Optional[List[str]] = None) -> Source:
    if name == "fixture":
        if not fixture:
            raise ValueError("source=fixture needs --fixture <path>")
        return FixtureSource(fixture)
    if name == "apify":
        return ApifySource()
    if name == "gmaps":
        return MapsSource(metros=metros)
    raise ValueError("unknown source %r (fixture, apify, gmaps)" % name)


# ------------------------------------------------------------------ loading
def load_records(path: str) -> List[Dict[str, Any]]:
    """JSON array, JSONL or CSV -> list of dicts."""
    if not os.path.exists(path):
        raise IOError("source file not found: %s" % path)
    if path.endswith(".csv"):
        with open(path, "r", encoding="utf-8") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _lead_scrape_root() -> str:
    from shared.paths import ROOT_DIR

    return os.path.join(str(ROOT_DIR), "Coding", "lead-scrape-2026")


def _load_niche_filters(niche: str) -> Dict[str, Any]:
    path = os.path.join(_lead_scrape_root(), "niches", "%s.json" % niche)
    with open(path, "r", encoding="utf-8") as fh:
        return (json.load(fh) or {}).get("filters") or {}


def niche_fill_rate(niche: str, default: float = 0.5) -> float:
    """The measured share of returned rows that carry an email, from the niche
    config the scraper already uses."""
    try:
        path = os.path.join(_lead_scrape_root(), "niches", "%s.json" % niche)
        with open(path, "r", encoding="utf-8") as fh:
            return float((json.load(fh) or {}).get("fill_rate") or default)
    except (OSError, IOError, ValueError, TypeError):
        return default


def _load_niche_query(niche: str) -> str:
    queries = {
        "cleaning": "commercial cleaning company",
        "bookkeeping": "bookkeeping and tax service",
        "recruiting": "recruiting agency",
    }
    return queries.get(niche, niche)


def _apify_token() -> str:
    token = os.environ.get("APIFY_API_TOKEN") or os.environ.get("APIFY_TOKEN")
    if not token:
        raise PaidCallBlocked("apify", 0, 0.0, "no APIFY_API_TOKEN in the environment")
    return token


def _import_runner_run_shard() -> Callable[..., Dict[str, Any]]:
    import sys

    root = _lead_scrape_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    import runner  # type: ignore  # noqa: E402

    return runner.run_shard


def _import_maps_search() -> Callable[..., List[Dict[str, Any]]]:
    """Wrap the async Playwright scraper in a blocking call."""
    import asyncio
    import sys

    from shared.paths import BASE_DIR

    execution = os.path.join(str(BASE_DIR), "execution")
    if execution not in sys.path:
        sys.path.insert(0, execution)
    from google_maps_scraper import GoogleMapsScraper  # type: ignore  # noqa: E402

    def search(query: str, location: str, limit: int) -> List[Dict[str, Any]]:
        async def _run():
            scraper = GoogleMapsScraper()
            await scraper.start()
            try:
                return await scraper.search(query, location)
            finally:
                await scraper.stop()

        rows = asyncio.get_event_loop().run_until_complete(_run())
        return list(rows or [])[:limit]

    return search


def iter_chunks(items: Iterable[Any], size: int) -> Iterable[List[Any]]:
    chunk = []  # type: List[Any]
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
