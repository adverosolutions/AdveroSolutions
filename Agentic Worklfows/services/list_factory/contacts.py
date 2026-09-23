"""Owner -> email candidates -> verified address.

    owner discovery   execution/discover_owner.py (Perplexity sonar, PAID)
    pattern guessing  execution/generate_email_patterns.py (free)
    verification      execution/verify_emails_bulk.py (MillionVerifier, PAID)
    paid finder       STUB. LeadMagic and Prospeo accounts do not exist.

Order matters and is the whole cost story: guess the four cheap patterns and
verify them before paying a finder, because four verifications at $0.0006 cost
less than half of one find. Every paid step is injectable and gated behind
``ALLOW_PAID_CALLS=1``.
"""
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional

from shared.paths import BASE_DIR

from services.list_factory import models
from services.list_factory.ledger import PRICES
from services.list_factory.sources import PaidCallBlocked, require_paid

logger = logging.getLogger("list_factory.contacts")

# The four patterns Blueprint M5 names, in SMB likelihood order. Deliberately
# NOT the full 15-pattern list in generate_email_patterns: each extra pattern
# is another verification charge on the same lead, and patterns 5-15 have a hit
# rate low enough that they cost more than the finder they were meant to avoid.
PATTERNS = ("first", "first.last", "flast", "firstlast")
MAX_CANDIDATES = len(PATTERNS)

# MillionVerifier results we will mail. 'catch_all' is accepted but flagged
# AND counted separately: the domain accepts every local part at SMTP time, so
# for an address WE guessed there is no evidence the mailbox exists. About a
# quarter of real checks come back this way, and counting them as "verified"
# told Lorenzo he had 3,300 confirmed contacts when ~800 were unconfirmed
# guesses.
ACCEPT_STATUSES = ("valid",)
ACCEPT_CATCH_ALL = True

# Two different things that both used to read as "the mailbox does not exist".
#
# ERROR_STATUSES is a TRANSPORT or QUOTA failure:
# execution/verify_emails_bulk.verify_emails returns status 'error' with
# raw=None whenever the HTTP call fails, MILLIONVERIFIER_API_KEY is missing, or
# the account is out of credits. Falling through to the next pattern on that
# burned all four patterns for every lead (148 billed checks instead of 44),
# rejected the whole week's list TERMINALLY, and still exited 0 with no alert.
# These leads are held, not rejected, and the stage fails above a small rate.
ERROR_STATUSES = ("error", "")
# UNKNOWN is MillionVerifier's own per-address "could not determine". It is a
# real answer at a steady background rate (the recorded distribution has it),
# so it is not evidence of an outage: try the next pattern, and if every
# pattern comes back unknown or invalid the lead is a genuine miss. Never
# accepted: an unconfirmed guess is not a contact.
UNKNOWN_STATUSES = ("unknown", "risky", "disposable")

# Fail the verify stage once this share of checks came back undecided. One
# flaky check is noise; one in twenty is an outage or an empty credit balance,
# and every further check is money spent to reject a good lead.
DEFAULT_MAX_VERIFY_ERROR_RATE = 0.05
MIN_CHECKS_BEFORE_ERROR_STOP = 10


class VerifyStageError(Exception):
    """The verifier is not answering. The stage stops; the leads stay pending."""


class Verifier(object):
    """MillionVerifier, or anything with the same ``verify(emails) -> rows``."""

    name = "millionverifier"

    def __init__(self, verify_fn: Optional[Callable[[List[str]], List[Dict[str, Any]]]] = None):
        self._verify_fn = verify_fn

    def cost(self, n: int) -> float:
        return round(n * PRICES["millionverifier_per_check"], 6)

    def verify(self, emails: List[str]) -> List[Dict[str, Any]]:
        if not emails:
            return []
        if self._verify_fn is not None:
            return self._verify_fn(emails)
        require_paid("millionverifier", len(emails), self.cost(len(emails)),
                     "each check is billed whether the address exists or not")
        return _import_verify_emails()(emails)


class ReplayVerifier(Verifier):
    """Offline stand-in for MillionVerifier, drawn from recorded outcomes.

    ``fixtures/mv_recorded_rates.json`` holds the real result distribution of
    7,026 recorded checks (role addresses excluded), split by whether the local
    part contains a dot, because ``first.last@`` behaves very differently from
    ``first@``. An address is mapped to an outcome by hashing it, so the same
    address always gets the same answer and a rehearsal is reproducible.

    **These rates are an upper bound, not a prediction.** The recorded
    addresses arrived from the Apify actor already flagged
    ``email_status: validated``; a freshly guessed pattern verifies less often.
    ``ok_multiplier`` scales the deliverable share down so a rehearsal can be
    stressed against a pessimistic assumption; the surplus becomes ``invalid``.
    Nothing here spends money, and ``verify_source`` on the lead says
    ``replay`` so a staged CSV can never be mistaken for a paid one.
    """

    name = "replay"

    def __init__(self, rates_path: Optional[str] = None, ok_multiplier: float = 1.0):
        Verifier.__init__(self)
        self.ok_multiplier = max(0.0, min(1.0, float(ok_multiplier)))
        self.rates_path = rates_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "fixtures", "mv_recorded_rates.json"
        )
        self._buckets = self._load()
        self.calls = []  # type: List[str]

    def _load(self) -> Dict[str, List[Any]]:
        import json

        with open(self.rates_path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        out = {}
        for bucket, counts in (blob.get("buckets") or {}).items():
            total = sum(counts.values()) or 1
            ladder = []
            running = 0.0
            deliverable = ("ok", "catch_all")
            shifted = 0.0
            for result, count in sorted(counts.items()):
                share = float(count) / total
                if result in deliverable:
                    kept = share * self.ok_multiplier
                    shifted += share - kept
                    share = kept
                running += share
                ladder.append((running, result))
            if shifted > 0:
                ladder.append((running + shifted, "invalid"))
            out[bucket] = ladder
        return out

    def verify(self, emails: List[str]) -> List[Dict[str, Any]]:
        import hashlib

        rows = []
        for email in emails:
            self.calls.append(email)
            local = email.split("@")[0]
            bucket = "dotted" if "." in local else "plain"
            ladder = self._buckets.get(bucket) or self._buckets.get("plain") or [(1.0, "invalid")]
            draw = int(hashlib.sha256(email.encode("utf-8")).hexdigest()[:8], 16) / float(0xFFFFFFFF)
            result = ladder[-1][1]
            for edge, outcome in ladder:
                if draw <= edge:
                    result = outcome
                    break
            status = {"ok": "valid", "catch_all": "catch_all"}.get(result, result)
            rows.append({
                "email": email, "status": status,
                "is_deliverable": status in ("valid", "catch_all"),
                "is_catch_all": status == "catch_all",
                "is_role": False, "is_disposable": False, "is_free": False,
                "raw": {"replay": True, "result": result},
            })
        return rows


class PaidFinder(object):
    """Last-resort email finder. No account exists, so this never finds anything.

    It is not a no-op though: it records what a real run would have spent, so
    the ledger can answer "would a finder have paid for itself" the day Lorenzo
    signs up for one.
    """

    name = "leadmagic"
    enabled = False

    def cost(self, n: int) -> float:
        return round(n * PRICES["paid_finder_per_find"], 6)

    def find(self, lead: Dict[str, Any]) -> Optional[str]:
        raise PaidCallBlocked(
            "paid_finder:%s" % self.name, 1, self.cost(1),
            "no LeadMagic or Prospeo account exists (config/ids.json dead_or_missing)",
        )


class OwnerFinder(object):
    """Perplexity sonar via execution/discover_owner.py. PAID, ~$0.005 a look-up."""

    name = "perplexity"

    def __init__(self, discover_fn: Optional[Callable[..., Optional[Dict[str, str]]]] = None):
        self._discover_fn = discover_fn

    def cost(self, n: int) -> float:
        return round(n * PRICES["perplexity_per_owner_lookup"], 6)

    def discover(self, lead: Dict[str, Any], industry: str) -> Optional[Dict[str, str]]:
        fn = self._discover_fn
        if fn is None:
            require_paid("perplexity:discover_owner", 1, self.cost(1), lead.get("company_name") or "")
            fn = _import_discover_owner()
        return fn(
            company_name=lead.get("company_name") or "",
            city=lead.get("city") or "",
            state=lead.get("state") or "",
            industry=industry,
            website=lead.get("website") or "",
        )


# ------------------------------------------------------------------- stages
def resolve_owners(
    leads: List[Dict[str, Any]],
    industry: str,
    finder: Optional[OwnerFinder] = None,
    on_lookup: Optional[Callable[[int], None]] = None,
) -> Dict[str, int]:
    """Fill first/last name. A source row that already carries a name is free;
    only the rest cost a look-up.

    A lead with no domain is rejected before the look-up, not after: there is
    nothing to build an address on, so the $0.005 would buy a name we cannot
    use.
    """
    summary = {"from_source": 0, "looked_up": 0, "found": 0, "missing": 0, "no_domain": 0, "blocked": 0}
    finder = finder or OwnerFinder()
    for lead in leads:
        if not lead.get("domain"):
            models.reject(lead, models.REJECT_NO_DOMAIN, "no website to derive a domain from")
            summary["no_domain"] += 1
            continue
        if lead.get("first_name"):
            lead["owner_source"] = lead.get("owner_source") or "source_row"
            models.advance(lead, models.OWNER, "source")
            summary["from_source"] += 1
            continue
        try:
            found = finder.discover(lead, industry)
            summary["looked_up"] += 1
            if on_lookup is not None:
                on_lookup(1)
        except PaidCallBlocked as exc:
            # Not a failure of the lead: the run is simply not allowed to pay.
            # models.hold, NOT models.reject. reject() is terminal and
            # RunState.pending() filters a rejected lead out for good, so the
            # runbook's own "rehearse first, then open the gate and resume"
            # sequence returned an empty list and no explanation. A held lead
            # is released at the start of the next pass and picked up here.
            lead["owner_blocked"] = str(exc)
            models.hold(lead, models.HOLD_GATE, "owner look-up blocked: %s" % exc.service)
            summary["blocked"] += 1
            continue
        if not found or not found.get("first_name"):
            models.reject(lead, models.REJECT_NO_OWNER, "no owner found")
            summary["missing"] += 1
            continue
        lead["first_name"] = models.clean_text(found.get("first_name"))
        lead["last_name"] = models.clean_text(found.get("last_name"))
        lead["title"] = models.clean_text(found.get("title")) or lead.get("title") or ""
        lead["owner_confidence"] = found.get("confidence") or ""
        lead["owner_source"] = "perplexity"
        if found.get("research"):
            lead["research"] = models.clean_text(found.get("research"))
        models.advance(lead, models.OWNER, "lookup")
        summary["found"] += 1
    return summary


def candidates_for(first_name: str, last_name: str, domain: str) -> List[str]:
    """The four Blueprint patterns, in order, deduped.

    Built on ``execution.generate_email_patterns`` so the normalisation rules
    (lowercase, strip non-letters) stay in one place; this only picks which of
    its patterns we are willing to pay to verify.
    """
    gen = _import_generate_patterns()
    normalize = gen.normalize_name
    first = normalize(first_name)
    last = normalize(last_name)
    if not domain or not first:
        return []
    out = ["%s@%s" % (first, domain)]
    if last:
        out.append("%s.%s@%s" % (first, last, domain))
        out.append("%s%s@%s" % (first[0], last, domain))
        out.append("%s%s@%s" % (first, last, domain))
    seen = set()
    unique = []
    for email in out:
        if email not in seen:
            seen.add(email)
            unique.append(email)
    return unique[:MAX_CANDIDATES]


def generate_candidates(leads: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"with_candidates": 0, "none": 0, "candidates": 0}
    for lead in leads:
        cands = candidates_for(lead.get("first_name") or "", lead.get("last_name") or "", lead.get("domain") or "")
        lead["email_candidates"] = cands
        if not cands:
            models.reject(lead, models.REJECT_NO_CANDIDATES, "could not build an address from the name")
            summary["none"] += 1
            continue
        summary["with_candidates"] += 1
        summary["candidates"] += len(cands)
        models.advance(lead, models.PATTERNS)
    return summary


def verify_leads(
    leads: List[Dict[str, Any]],
    verifier: Optional[Verifier] = None,
    paid_finder: Optional[PaidFinder] = None,
    on_checks: Optional[Callable[[int], None]] = None,
    on_finder: Optional[Callable[[int], None]] = None,
    on_result: Optional[Callable[[str], None]] = None,
    accept_catch_all: bool = ACCEPT_CATCH_ALL,
    max_error_rate: float = DEFAULT_MAX_VERIFY_ERROR_RATE,
) -> Dict[str, int]:
    """Verify each lead's candidates in order and stop at the first hit.

    Stopping at the first hit is the cost rule: verifying all four patterns for
    every lead would roughly triple the verification line for no extra
    contacts, because we only ever mail one address per company.

    Three outcomes, kept apart on purpose:

    * a confirmed mailbox, or an accepted catch-all (counted separately)
    * a real miss: every pattern came back invalid -> rejected, terminal
    * **undecided**: the verifier errored, is out of credits or answered
      "unknown". The lead is HELD, not rejected, further patterns for it are
      not billed, and the stage fails outright once the error rate crosses
      ``max_error_rate`` so a resume with a healthy verifier picks the whole
      list up. Treating an outage as "this mailbox does not exist" billed 4
      checks per lead, destroyed the week's list terminally, and exited 0.

    ``on_result`` is called once per lead with its outcome, as it happens, so
    the ledger's verified count moves with the money instead of being assigned
    after the loop returns. A crash mid-stage used to persist 100% of the spend
    and 0% of the count, and the resumed run then divided the whole bill by the
    handful of contacts it bought afterwards and falsely halted.
    """
    summary = {
        "verified": 0, "catch_all": 0, "checks": 0, "unverifiable": 0,
        "errors": 0, "undecided": 0, "unknown": 0, "blocked": 0,
        "finder_attempted": 0, "finder_found": 0, "finder_blocked": 0,
    }
    verifier = verifier or Verifier()
    paid_finder = paid_finder or PaidFinder()

    def record(outcome: str) -> None:
        if on_result is not None:
            on_result(outcome)

    for lead in leads:
        hit = None
        for email in lead.get("email_candidates") or []:
            try:
                rows = verifier.verify([email])
            except PaidCallBlocked as exc:
                lead["verify_blocked"] = str(exc)
                models.hold(lead, models.HOLD_GATE, "verification blocked: %s" % exc.service)
                summary["blocked"] += 1
                hit = "blocked"
                break
            summary["checks"] += 1
            if on_checks is not None:
                on_checks(1)
            row = (rows or [{}])[0]
            status = (row.get("status") or "").lower()
            if status in ERROR_STATUSES or (status != "" and row.get("raw", "") is None):
                # No verdict at all. Stop burning patterns on this lead.
                summary["errors"] += 1
                summary["undecided"] += 1
                lead["verify_error"] = status or "no response"
                models.hold(lead, models.HOLD_VERIFY_ERROR,
                            "verifier returned %r" % (status or "no response"))
                hit = "undecided"
                if (summary["checks"] >= MIN_CHECKS_BEFORE_ERROR_STOP
                        and float(summary["errors"]) / summary["checks"] > max_error_rate):
                    record("undecided")
                    raise VerifyStageError(
                        "%d of %d verification checks failed outright (%.0f%% > %.0f%% allowed). "
                        "The verifier is erroring or out of credits; the leads are held, not rejected, "
                        "so a resume picks them up."
                        % (summary["errors"], summary["checks"],
                           100.0 * summary["errors"] / summary["checks"], 100.0 * max_error_rate)
                    )
                break
            if status in UNKNOWN_STATUSES:
                summary["unknown"] += 1
                continue
            if status in ACCEPT_STATUSES or (accept_catch_all and status == "catch_all"):
                if row.get("is_role"):
                    # info@/sales@ verify fine and are not a decision maker.
                    continue
                hit = email
                lead["email"] = email
                lead["verify_status"] = status
                lead["verify_catch_all"] = bool(row.get("is_catch_all") or status == "catch_all")
                lead["verify_source"] = verifier.name
                if lead["verify_catch_all"]:
                    summary["catch_all"] += 1
                break
        if hit == "blocked":
            record("blocked")
            continue
        if hit == "undecided":
            record("undecided")
            continue
        if hit:
            summary["verified"] += 1
            models.advance(lead, models.VERIFIED)
            models.advance(lead, models.FINDER, "not_needed")
            record("catch_all" if lead.get("verify_catch_all") else "valid")
            continue
        # Miss. This is where a paid finder would earn its keep.
        summary["finder_attempted"] += 1
        if on_finder is not None:
            on_finder(1)
        try:
            found = paid_finder.find(lead)
        except PaidCallBlocked as exc:
            found = None
            lead["finder_blocked"] = str(exc)
            summary["finder_blocked"] += 1
        if found:
            lead["email"] = found
            lead["verify_status"] = "valid"
            lead["verify_source"] = paid_finder.name
            summary["finder_found"] += 1
            summary["verified"] += 1
            models.advance(lead, models.VERIFIED)
            models.advance(lead, models.FINDER, "found")
            record("valid")
            continue
        models.reject(lead, models.REJECT_UNVERIFIABLE, "no pattern verified and no finder available")
        summary["unverifiable"] += 1
        record("miss")
    return summary


def credits_available(check_credits: Optional[Callable[[], Optional[int]]] = None) -> Optional[int]:
    """Remaining MillionVerifier credits, or None when they cannot be read.

    Read-only and free. The run calls it before the verify stage so an empty
    balance stops the stage instead of turning every lead into an 'error' that
    used to read as "this mailbox does not exist".
    """
    fn = check_credits
    if fn is None:
        _execution_dir()
        try:
            from verify_emails_bulk import check_credits as fn  # type: ignore  # noqa: F811
        except ImportError as exc:  # pragma: no cover - only when the file moves
            logger.warning("could not import check_credits (%s)", exc)
            return None
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a credits probe must never break a run
        logger.warning("MillionVerifier credit check failed: %s", exc)
        return None


# ------------------------------------------------------------------ imports
def _execution_dir() -> str:
    path = os.path.join(str(BASE_DIR), "execution")
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def _import_generate_patterns():
    _execution_dir()
    import generate_email_patterns  # type: ignore

    return generate_email_patterns


def _import_discover_owner():
    _execution_dir()
    from discover_owner import discover_owner_and_research  # type: ignore

    return discover_owner_and_research


def _import_verify_emails():
    _execution_dir()
    from verify_emails_bulk import verify_emails  # type: ignore

    return verify_emails
