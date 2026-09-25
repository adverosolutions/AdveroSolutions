"""Cost ledger, the per-contact hard stop, and source attribution.

Blueprint Section 6 KPI: cost per verified lead green at <= $0.02, alert at
> $0.04. The run's hard stop is its own cap, $0.07 since 2026-09-25 (see
shared/thresholds.py LIST_FACTORY_MAX_COST_PER_CONTACT_USD). This module is the thing that makes that number real: one row per run
with per-stage counts and dollar cost, and a stop that fires at a stage
boundary rather than after the money is gone.

Unit costs below are the measured ones, each with its provenance. Change them
here and nowhere else.
"""
import csv
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from shared import llm
from shared import thresholds as TH
from shared.paths import tmp_dir

logger = logging.getLogger("list_factory.ledger")

# --------------------------------------------------------------- unit costs
# Provenance for every number:
#   apify_*        Coding/lead-scrape-2026/runner.py (billed per lead ACTUALLY
#                  returned, plus a per-run start fee; both measured Aug 2026)
#   perplexity     execution/discover_owner.py docstring, sonar, ~$0.005/lookup
#   millionverifier execution/verify_emails_bulk.py docstring, $0.0006/check at
#                  the $30/mo 50k tier. The Blueprint quotes a wider
#                  $0.0015-0.004 band for other tiers; PRICES below is what
#                  Lorenzo's account actually pays.
#   leadmagic      Blueprint M5 range $0.002-0.005; midpoint. NO ACCOUNT EXISTS,
#                  so this only ever prices the stub's would-have-cost.
PRICES = {
    "apify_run_start": 0.02,
    "apify_per_lead": 0.002,
    "gmaps_per_business": 0.0,
    "perplexity_per_owner_lookup": 0.005,
    "millionverifier_per_check": 0.0006,
    "paid_finder_per_find": 0.0035,
}

# Blueprint Section 6 KPI "cost per verified lead": green <= $0.02, alert
# > $0.04. The hard stop is the run cap, $0.07 since 2026-09-25 (Lorenzo: Opus
# 5.5 everywhere, worst-case thinking priced; lower it after the first real
# run). Bound to shared/thresholds.py, the one home of every Section 6 number.
DEFAULT_MAX_COST_PER_CONTACT = TH.LIST_FACTORY_MAX_COST_PER_CONTACT_USD
ALERT_COST_PER_CONTACT = TH.LIST_FACTORY_ALERT_COST_PER_CONTACT_USD

# The run's OBSERVED deliverable and confirmed rates replace the plan's only
# once this many leads have been through verification (since the last
# re-test, see ``restart_rate_sample``). The first version switched after the
# first 20-check batch, about 7 leads, and at the plan's 0.375 confirmed per
# lead an all-catch-all first batch is common enough that about 7% of healthy
# pulls halted as "unbounded" (reviewer Monte Carlo on the recorded
# MillionVerifier outcomes, re-review 2). With 30 leads, a healthy list shows
# zero confirmed by chance with probability (1 - 0.375)^30 = 7.5e-7 at the plan
# rate, and 0.12% even at a pessimistic 0.2 confirmed per lead.
MIN_OBSERVED_SAMPLE_LEADS = 30

# Rates the projection falls back on before the run has observed any of its
# own. They mirror pipeline.DEFAULT_RATES; the pipeline passes its own copy in,
# and these exist so a Ledger used on its own still projects a number instead
# of None. Returning None was the bug: the hard stop could not speak until
# verification had already run, which is after 80% of a Google Maps run's money
# is spent.
DEFAULT_PROJECTION_RATES = {"verify_rate": 0.50, "checks_per_lead": 2.6, "catch_all_share": 0.25}

# Stages the ledger tracks, in pipeline order. "catch_all" is a COUNT-only
# stage: a catch-all domain accepts every local part at SMTP time, so for an
# address we guessed there is no evidence the mailbox exists. Counting those as
# "verified" put roughly 30% unconfirmed guesses into the denominator of the
# cost-per-verified KPI and of the 3,300 target.
STAGES = ["source", "icp", "owner", "patterns", "verify", "catch_all", "finder",
          "suppression", "personalize", "stage"]

LEDGER_HEADER = [
    "ts_utc", "run_id", "niche", "mode", "source", "verifier", "dry_run",
    "sourced", "icp_pass", "icp_reject", "owner_found", "candidates",
    "verified", "catch_all", "verify_errors", "finder_miss", "suppressed",
    "personalized", "staged", "target",
    "cost_source", "cost_icp", "cost_owner", "cost_verify", "cost_finder",
    "cost_personalize", "cost_total", "cost_per_verified", "cost_per_deliverable",
    "verdict",
]


class BudgetExceeded(Exception):
    """Raised at a stage boundary when the projection breaks the cap."""

    def __init__(self, message: str, snapshot: Dict[str, Any]):
        Exception.__init__(self, message)
        self.snapshot = snapshot


def ledger_path() -> str:
    override = os.environ.get("LIST_FACTORY_LEDGER_PATH")
    if override:
        return override
    return os.path.join(str(tmp_dir()), "list_factory", "cost_ledger.csv")


class Ledger(object):
    """Per-stage counts and dollars for one run.

    LLM spend is not estimated twice: ``shared.llm`` already writes every call
    (real or faked) to ``.tmp/llm_ledger.csv`` with the model's own price, so
    an LLM stage is measured by the delta of that file across the stage. The
    ``estimate_llm`` fallback exists only for the case where the ledger file
    cannot be read.
    """

    def __init__(self, run_id: str, niche: str, max_cost_per_contact: float = DEFAULT_MAX_COST_PER_CONTACT,
                 source: str = "", verifier: str = "", dry_run: bool = False, target: int = 0,
                 rates: Optional[Dict[str, float]] = None):
        self.run_id = run_id
        self.niche = niche
        # Which source and which verifier produced these numbers, and whether
        # this was a rehearsal. Without them a free ``--verify replay`` row in
        # cost_ledger.csv is indistinguishable from a real paid run, and
        # "correct DEFAULT_RATES from the ledger's observed rates" cannot be
        # done at all: you cannot tell which rows were paid.
        self.source = source
        self.verifier = verifier
        self.dry_run = bool(dry_run)
        self.target = int(target or 0)
        self.rates = dict(DEFAULT_PROJECTION_RATES)
        self.rates.update(rates or {})
        self.max_cost_per_contact = float(max_cost_per_contact)
        self.counts = dict((stage, 0) for stage in STAGES)  # type: Dict[str, int]
        self.costs = dict((stage, 0.0) for stage in STAGES)  # type: Dict[str, float]
        self.detail = {}  # type: Dict[str, Any]
        self.events = []  # type: List[Dict[str, Any]]
        self.halted = False
        self.halt_reason = ""

    # ------------------------------------------------------------- recording
    def count(self, stage: str, n: int = 1) -> None:
        self.counts[stage] = self.counts.get(stage, 0) + int(n)

    def spend(self, stage: str, amount: float, what: str = "", units: int = 0) -> float:
        amount = round(float(amount), 6)
        self.costs[stage] = round(self.costs.get(stage, 0.0) + amount, 6)
        if amount or units:
            self.events.append({
                "stage": stage, "what": what, "units": units, "usd": amount,
                "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            })
        return amount

    def spend_units(self, stage: str, price_key: str, units: int) -> float:
        """Charge ``units`` of a priced third-party call."""
        return self.spend(stage, PRICES[price_key] * int(units), price_key, int(units))

    def note(self, key: str, value: Any) -> None:
        self.detail[key] = value

    # ------------------------------------------------------------- llm delta
    @staticmethod
    def _llm_ledger_total() -> float:
        path = llm.ledger_path()
        total = 0.0
        try:
            with open(str(path), "r", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    try:
                        total += float(row.get("est_cost_usd") or 0.0)
                    except (TypeError, ValueError):
                        continue
        except (OSError, IOError):
            return 0.0
        return round(total, 6)

    def llm_stage(self, stage: str):
        """Context manager charging a stage with whatever shared.llm billed.

            with ledger.llm_stage("icp"):
                ... complete(...) ...
        """
        return _LLMStage(self, stage)

    def estimate_llm(self, stage: str, model: str, in_tokens: int, out_tokens: int) -> float:
        return self.spend(stage, llm.estimate_cost(model, in_tokens, out_tokens), "llm:%s" % model, 1)

    # ------------------------------------------------------------ projection
    def total(self) -> float:
        return round(sum(self.costs.values()), 6)

    def verified_count(self) -> int:
        """CONFIRMED mailboxes only. A catch-all is counted, and reported,
        separately: MillionVerifier explicitly could not confirm it."""
        return int(self.counts.get("verify", 0))

    def catch_all_count(self) -> int:
        return int(self.counts.get("catch_all", 0))

    def deliverable_count(self) -> int:
        """Confirmed plus catch-all: what actually gets staged and mailed."""
        return self.verified_count() + self.catch_all_count()

    def catch_all_share(self) -> Optional[float]:
        deliverable = self.deliverable_count()
        if deliverable <= 0:
            return None
        return round(float(self.catch_all_count()) / deliverable, 4)

    def cost_per_verified(self) -> Optional[float]:
        verified = self.verified_count()
        if verified <= 0:
            return None
        return round(self.total() / verified, 6)

    def cost_per_deliverable(self) -> Optional[float]:
        """The softer number: every address that will be mailed, catch-alls
        included. Reported beside cost_per_verified so the gap is visible."""
        deliverable = self.deliverable_count()
        if deliverable <= 0:
            return None
        return round(self.total() / deliverable, 6)

    def rate_sample(self) -> Dict[str, int]:
        """Leads attempted, confirmed and catch-all since the rate sample began
        (the start of the run, or the last ``restart_rate_sample``)."""
        base = self.detail.get("rate_sample_from") or {}
        return {
            "attempted": int(self.detail.get("verify_attempted") or 0) - int(base.get("attempted") or 0),
            "confirmed": self.verified_count() - int(base.get("confirmed") or 0),
            "catch_all": self.catch_all_count() - int(base.get("catch_all") or 0),
        }

    def restart_rate_sample(self, reason: str) -> None:
        """Start a fresh observed-rate sample from here. Until it reaches
        ``MIN_OBSERVED_SAMPLE_LEADS`` the projection runs on the plan's rates,
        so a resume re-tests verification instead of re-halting on the rate it
        saved."""
        self.detail["rate_sample_from"] = {
            "attempted": int(self.detail.get("verify_attempted") or 0),
            "confirmed": self.verified_count(),
            "catch_all": self.catch_all_count(),
            "reason": reason,
        }

    def observed_verify_rate(self, min_sample: Optional[int] = None) -> Optional[float]:
        """Deliverable (confirmed plus catch-all) per lead attempted, or None
        below the minimum sample."""
        sample = self.rate_sample()
        need = MIN_OBSERVED_SAMPLE_LEADS if min_sample is None else min_sample
        if sample["attempted"] <= 0 or sample["attempted"] < need:
            return None
        return float(sample["confirmed"] + sample["catch_all"]) / sample["attempted"]

    def observed_confirmed_rate(self, min_sample: Optional[int] = None) -> Optional[float]:
        """CONFIRMED mailboxes per lead attempted: the rate that feeds the
        cost-per-verified denominator. Catch-alls are left out here exactly as
        they are left out of ``cost_per_verified``. None below the minimum
        sample, so the plan's rate stands in."""
        sample = self.rate_sample()
        need = MIN_OBSERVED_SAMPLE_LEADS if min_sample is None else min_sample
        if sample["attempted"] <= 0 or sample["attempted"] < need:
            return None
        return float(sample["confirmed"]) / sample["attempted"]

    def planned_confirmed_rate(self, rates: Optional[Dict[str, float]] = None) -> float:
        """The plan's verify_rate with the catch-all share taken out."""
        merged = dict(self.rates)
        merged.update(rates or {})
        verify_rate = max(0.0, min(1.0, float(merged.get("verify_rate", 0.5))))
        catch_all = max(0.0, min(1.0, float(merged.get("catch_all_share", 0.0))))
        return verify_rate * (1.0 - catch_all)

    def projected_from(self, future_usd: float, expected_new_confirmed: float) -> Optional[float]:
        """(spent + still to spend) / (confirmed so far + confirmed still to come).

        The single formula behind every projection: the stage-boundary check,
        the in-loop check and the gate before the source fetch. The denominator
        is CONFIRMED mailboxes, the same one ``cost_per_verified`` and the
        preflight use, so a run cannot be "inside the cap" by one yardstick and
        over it by the next. The old projection divided by deliverables
        (catch-alls included) and ignored suppression at the source boundary,
        so it read $0.0161 on a run the preflight had priced at $0.0222.
        """
        expected_total = self.verified_count() + max(0.0, float(expected_new_confirmed or 0.0))
        if expected_total <= 0:
            return None
        return round((self.total() + max(0.0, float(future_usd or 0.0))) / expected_total, 6)

    def project_cost_per_verified(
        self,
        remaining_candidates: int = 0,
        verify_rate: Optional[float] = None,
        rates: Optional[Dict[str, float]] = None,
        extra_future_usd: float = 0.0,
    ) -> Optional[float]:
        """Cost per CONFIRMED contact if the run finishes as it has been going.

        ``remaining_candidates`` are leads still to be verified; ``verify_rate``
        is the share of them expected to become CONFIRMED mailboxes. When the
        caller does not give one, the run's own observed confirmed rate is used,
        and before anything has been verified the plan's verify_rate with the
        catch-all share removed. The plan fallback matters: the version before
        it returned None until verification had already happened, which made
        the hard stop a post-mortem verdict instead of a control.

        The future leg charges ``checks_per_lead`` verifications per remaining
        candidate (2.6 measured, not 1), plus ``extra_future_usd`` for the owner
        look-ups and personalization the caller knows are still to come.

        The pipeline itself projects from the run state
        (``pipeline.project_run``); this helper stays for a Ledger used alone.
        """
        merged = dict(self.rates)
        merged.update(rates or {})
        if verify_rate is None:
            observed = self.observed_confirmed_rate()
            verify_rate = observed if observed is not None else self.planned_confirmed_rate(rates)
        verify_rate = max(0.0, min(1.0, float(verify_rate)))
        remaining = max(0, int(remaining_candidates))
        expected_new = int(round(remaining * verify_rate))
        checks_per_lead = max(0.0, float(merged.get("checks_per_lead", 2.6)))
        future = (
            PRICES["millionverifier_per_check"] * remaining * checks_per_lead
            + max(0.0, float(extra_future_usd or 0.0))
        )
        return self.projected_from(future, expected_new)

    def _halt(self, projected: float, where: str, detail: str) -> None:
        self.halted = True
        self.halt_reason = (
            "projected $%.4f per verified contact exceeds the $%.4f cap at %s "
            "(spent $%.4f, %d verified, %s)"
            % (projected, self.max_cost_per_contact, where or "stage boundary",
               self.total(), self.verified_count(), detail)
        )
        raise BudgetExceeded(self.halt_reason, self.snapshot(projected=projected))

    def unbounded(self, future_usd: float = 0.0, expected_new_confirmed: float = 0.0) -> bool:
        """No confirmed contact so far or still to come, but money spent or
        still to spend: the cost per confirmed contact is unbounded.

        ``projected_from`` has no number for this case and returns None, and
        the check used to read None as "inside the cap". A run whose every
        address came back catch-all, on top of a $5 verification bill, went
        through with status ok (MKT-1 re-review).
        """
        expected_total = self.verified_count() + max(0.0, float(expected_new_confirmed or 0.0))
        money = self.total() + max(0.0, float(future_usd or 0.0))
        return expected_total <= 0 and money > 0

    def check_projection(self, future_usd: float, expected_new_confirmed: float,
                         where: str = "", detail: str = "") -> Optional[float]:
        """Hard stop on an explicit projection. Returns the projected figure."""
        projected = self.projected_from(future_usd, expected_new_confirmed)
        self.detail["last_projection"] = {
            "where": where, "projected_cost_per_verified": projected,
            "future_usd": round(float(future_usd or 0.0), 6),
            "expected_new_confirmed": round(float(expected_new_confirmed or 0.0), 2),
        }
        if projected is None and self.unbounded(future_usd, expected_new_confirmed):
            self.detail["last_projection"]["unbounded"] = True
            self.halted = True
            sample = self.rate_sample()
            self.halt_reason = (
                "no confirmed contact so far and none expected from what is left, with $%.4f spent "
                "and $%.4f still to spend at %s: the cost per verified contact is unbounded, over "
                "any cap (%d lead(s) verified in the current sample, %d confirmed, %d catch-all; %s). "
                "A raised cap does not change this. If leads are still waiting for verification, a "
                "--resume re-tests on a fresh sample of %d leads before judging again; if none are "
                "left, this list produced no confirmed mailbox"
                % (self.total(), max(0.0, float(future_usd or 0.0)), where or "stage boundary",
                   sample["attempted"], sample["confirmed"], sample["catch_all"],
                   detail or "0 confirmed", MIN_OBSERVED_SAMPLE_LEADS)
            )
            raise BudgetExceeded(self.halt_reason, self.snapshot())
        if projected is None or projected <= self.max_cost_per_contact:
            return projected
        self._halt(projected, where, detail or "$%.4f still to spend for %.0f more confirmed"
                   % (float(future_usd or 0.0), float(expected_new_confirmed or 0.0)))
        return projected

    def check_budget(
        self,
        remaining_candidates: int = 0,
        verify_rate: Optional[float] = None,
        where: str = "",
        rates: Optional[Dict[str, float]] = None,
        extra_future_usd: float = 0.0,
    ) -> None:
        """Hard stop. Raises BudgetExceeded as soon as the projection breaks.

        A projection is available from the first boundary now, because an
        unobserved verify rate falls back to the plan's. The only case that
        still cannot produce a number is "nothing verified and nothing left to
        verify", which is a finished run, not a running one.
        """
        projected = self.project_cost_per_verified(
            remaining_candidates, verify_rate, rates=rates, extra_future_usd=extra_future_usd,
        )
        if projected is None:
            return
        if projected <= self.max_cost_per_contact:
            return
        self._halt(projected, where, "%d candidates left" % remaining_candidates)

    # --------------------------------------------------------------- output
    def snapshot(self, projected: Optional[float] = None) -> Dict[str, Any]:
        cpv = self.cost_per_verified()
        return {
            "run_id": self.run_id,
            "niche": self.niche,
            "source": self.source,
            "verifier": self.verifier,
            "dry_run": self.dry_run,
            "target": self.target,
            "rates": dict(self.rates),
            "counts": dict(self.counts),
            "costs": dict(self.costs),
            "detail": dict(self.detail),
            "total_usd": self.total(),
            "cost_per_verified": cpv,
            "cost_per_deliverable": self.cost_per_deliverable(),
            "catch_all_share": self.catch_all_share(),
            "projected_cost_per_verified": projected,
            "max_cost_per_contact": self.max_cost_per_contact,
            "verdict": self.verdict(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "events": list(self.events),
        }

    def verdict(self) -> str:
        cpv = self.cost_per_verified()
        if self.halted:
            return "halted_over_budget"
        if cpv is None:
            # Mid-run this is normal (the source is paid before anything is
            # verified). A FINISHED run in this state with money spent is over
            # the cap: pipeline.run_pipeline reports it as over_cap.
            return "no_verified_contacts"
        if cpv > ALERT_COST_PER_CONTACT:
            return "alert"
        if cpv > self.max_cost_per_contact:
            return "over_cap"
        return "green"

    def row(self, mode: str) -> Dict[str, Any]:
        cpv = self.cost_per_verified()
        return {
            "ts_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "run_id": self.run_id,
            "niche": self.niche,
            "mode": mode,
            "source": self.source,
            "verifier": self.verifier,
            "dry_run": "yes" if self.dry_run else "no",
            "sourced": self.counts.get("source", 0),
            "icp_pass": self.counts.get("icp", 0),
            "icp_reject": int(self.detail.get("icp_rejected") or 0),
            "owner_found": self.counts.get("owner", 0),
            "candidates": self.counts.get("patterns", 0),
            "verified": self.counts.get("verify", 0),
            "catch_all": self.counts.get("catch_all", 0),
            "verify_errors": int(self.detail.get("verify_errors") or 0),
            "finder_miss": self.counts.get("finder", 0),
            "suppressed": int(self.detail.get("suppressed") or 0),
            "personalized": self.counts.get("personalize", 0),
            "staged": self.counts.get("stage", 0),
            "target": self.target,
            "cost_source": self.costs.get("source", 0.0),
            "cost_icp": self.costs.get("icp", 0.0),
            "cost_owner": self.costs.get("owner", 0.0),
            "cost_verify": self.costs.get("verify", 0.0),
            "cost_finder": self.costs.get("finder", 0.0),
            "cost_personalize": self.costs.get("personalize", 0.0),
            "cost_total": self.total(),
            "cost_per_verified": "" if cpv is None else cpv,
            "cost_per_deliverable": "" if self.cost_per_deliverable() is None else self.cost_per_deliverable(),
            "verdict": self.verdict(),
        }

    @staticmethod
    def _rotate_if_header_changed(path: str) -> None:
        """Move an old-schema ledger aside rather than appending into it.

        DictWriter writes the new field order under the old header, which makes
        every column after the first new one wrong, silently. The pre-2026-09-22
        file has no source/verifier/dry_run columns (that is the very gap that
        made a free rehearsal indistinguishable from a paid run), so it is
        preserved beside the new one instead of being corrupted.
        """
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                header = next(csv.reader(fh), [])
        except (OSError, IOError, StopIteration):
            return
        if header == LEDGER_HEADER:
            return
        for n in range(1, 100):
            archive = "%s.v%d.csv" % (path[:-4] if path.endswith(".csv") else path, n)
            if not os.path.exists(archive):
                os.rename(path, archive)
                logger.warning("cost ledger schema changed; previous rows preserved at %s", archive)
                return

    def append_csv(self, mode: str, path: Optional[str] = None) -> str:
        path = path or ledger_path()
        row = self.row(mode)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._rotate_if_header_changed(path)
            new_file = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, "a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=LEDGER_HEADER)
                if new_file:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as exc:  # noqa: BLE001 - the ledger must never break a run
            logger.warning("cost ledger append failed (%s): %s", path, exc)
        return path

    def table(self) -> str:
        lines = ["stage         count        usd"]
        for stage in STAGES:
            lines.append("  %-11s %6d  %9.4f" % (stage, self.counts.get(stage, 0), self.costs.get(stage, 0.0)))
        cpv = self.cost_per_verified()
        cpd = self.cost_per_deliverable()
        share = self.catch_all_share()
        lines.append("  %-11s %6s  %9.4f" % ("TOTAL", "", self.total()))
        lines.append("  cost per verified contact: %s (cap $%.4f) -> %s"
                     % ("n/a" if cpv is None else "$%.5f" % cpv, self.max_cost_per_contact, self.verdict()))
        lines.append("  cost per deliverable (catch-alls included): %s%s"
                     % ("n/a" if cpd is None else "$%.5f" % cpd,
                        "" if share is None else "  catch-all share %.1f%%" % (100.0 * share)))
        return "\n".join(lines)


class _LLMStage(object):
    def __init__(self, ledger: Ledger, stage: str):
        self.ledger = ledger
        self.stage = stage
        self.before = 0.0

    def __enter__(self):
        self.before = Ledger._llm_ledger_total()
        return self

    def __exit__(self, exc_type, exc, tb):
        after = Ledger._llm_ledger_total()
        delta = round(after - self.before, 6)
        if delta > 0:
            self.ledger.spend(self.stage, delta, "llm", 0)
        return False


# ------------------------------------------------------------- attribution
def source_attribution(
    leads_reader: Callable[[], List[Dict[str, Any]]],
    source_key: str = "advero_source",
) -> Dict[str, Any]:
    """Replies per 1,000 sends by source, from live Instantly leads.

    ``leads_reader`` returns the workspace's leads (the caller passes a
    read-only pull). Every lead the factory stages carries its source in the
    custom variable ``advero_source``, so the join happens inside Instantly's
    own payload and needs no second system.

    A lead uploaded before the factory existed has no source; those are
    reported under ``unattributed`` rather than dropped, because pretending the
    denominator is only the attributed part is how a source looks better than
    it is.

    ``replies`` is Instantly's own ``email_reply_count``, which counts EVERY
    reply including auto-responders and out-of-office. It is not the "real
    reply rate" of Blueprint Section 6: on 2026-09-21 this reports 37.0 replies
    per 1,000 sends against a measured real rate of about 12. Use it to compare
    sources against each other, never as the headline reply number.
    """
    rows = leads_reader() or []
    by_source = {}  # type: Dict[str, Dict[str, int]]
    for lead in rows:
        payload = lead.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        source = (payload.get(source_key) or "").strip() or "unattributed"
        bucket = by_source.setdefault(source, {"leads": 0, "sends": 0, "replies": 0, "bounced": 0})
        bucket["leads"] += 1
        # A contacted lead is one send of step 1 at minimum; email_reply_count
        # is Instantly's own counter and is the only reply number that does not
        # need the emails endpoint (20 requests/minute) to compute.
        if lead.get("timestamp_last_contact"):
            bucket["sends"] += 1
        bucket["replies"] += int(lead.get("email_reply_count") or 0)
        if lead.get("status") == -1:
            bucket["bounced"] += 1
    out = []
    for source in sorted(by_source):
        bucket = by_source[source]
        sends = bucket["sends"]
        out.append({
            "source": source,
            "leads": bucket["leads"],
            "sends": sends,
            "replies": bucket["replies"],
            "bounced": bucket["bounced"],
            "replies_per_1k_sends": round(1000.0 * bucket["replies"] / sends, 2) if sends else None,
            "bounce_rate_pct": round(100.0 * bucket["bounced"] / sends, 2) if sends else None,
        })
    return {"by_source": out, "sources": len(out), "total_leads": len(rows)}
