"""The suppression list. Built read-only from the live workspace, fail-closed.

What goes in, and where it is read from (all GET / read-shaped POST):

  every lead already in the workspace   POST /leads/list, no filter, walked to
                                        the end (4,918 rows on 2026-09-21)
  every bounce                          the same pull, ``status == -1``
  every unsubscribe                     the same pull, ``status == -2``
  every blocklist entry                 GET /block-lists-entries
  every hostile reply                   GET /emails?email_type=received, matched
                                        against HOSTILE_MARKERS
  every current client domain           config/icp/suppression_manual.json
  every domain already contacted        company_domain + the email's domain from
                                        the workspace pull

**Do not swap the workspace pull for a filtered one.** Measured 2026-09-21:
``leads/list`` silently IGNORES a filter it does not recognise. A body with
``filter: "TOTAL_NONSENSE_XYZ"`` returned all 4,918 leads, byte-identical to no
filter at all. So a typo in a filter name does not raise, it changes what the
call means, and a bounce-only pull that quietly became an everything pull would
look like it worked. Statuses are read off the full pull instead, where a wrong
value can only ever suppress too much.

Fail-closed: if any source cannot be read, or a cursor walk comes back
truncated, ``SuppressionList.complete`` is False and the pipeline refuses to
stage. A partial suppression list is worse than none, because it reads as a
complete one.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from shared.paths import CONFIG_DIR, tmp_dir

from services.list_factory import models

logger = logging.getLogger("list_factory.suppression")

# Instantly lead status values seen live: 1 active, 3 completed, -1 bounced.
# -2 (unsubscribed) and -3 (skipped) are documented and handled although the
# workspace had none on 2026-09-21.
STATUS_BOUNCED = -1
STATUS_UNSUBSCRIBED = -2
STATUS_SKIPPED = -3

# Re-derived read-only against all 115 received replies on 2026-09-22 and
# recorded in ``fixtures/received_emails_recorded.json`` so the claim is
# checkable offline. The OLD list fired on 16 rows from 15 distinct senders,
# and one of them was a FALSE POSITIVE: info@theaugustacpa.com, subject
# "Automatic reply: Stefanie, question", whose standard CPA footer reads
# "please do not email documents containing sensitive ... information". The
# bare marker "do not email" matched it, and the firm plus its whole domain
# were suppressed permanently - in the bookkeeping niche, where that footer is
# industry boilerplate. The marker is now anchored on the sender's own intent
# ("do not email me/us"), auto-replies are skipped by subject, and quoted text
# is stripped before matching. That leaves 15 rows from 14 senders, every one a
# genuine opt-out. ``test_the_recorded_replies_produce_exactly_the_opt_outs``
# pins it.
#
# Matching is WHOLE-PHRASE (icp.keyword_hit), never a bare substring. The old
# `marker in blob` made "was spam filtered" hit "as spam" and any reply quoting
# our own unsubscribe footer hit "unsubscribe", suppressing a warm prospect and
# every colleague at their domain with nothing downstream reporting it.
#
# A bare "spam" is deliberately NOT in this list. "your email landed in my spam
# folder" is a reply from someone who read it, and suppressing them would throw
# away a lead and a deliverability signal at the same time. Only the phrases
# that mean they are reporting us are here.
HOSTILE_MARKERS = (
    "unsubscribe", "unsubscribed", "unsubscribe me",
    "remove me", "remove us from", "remove my email", "take me off", "take us off",
    "stop emailing", "stop contacting", "do not contact", "don't contact",
    "do not email me", "don't email me", "do not email us", "don't email us",
    "not interested and", "leave me alone", "harassment",
    "this is spam", "marked as spam", "marking this as spam", "mark this as spam",
    "reported as spam", "report as spam", "flagged as spam",
    "report you", "reporting you",
    "cease and desist", "legal action", "fuck", "piss off",
    "how did you get my", "gdpr", "can-spam", "ccpa",
)

# A subject that starts with one of these is an out-of-office, not an opt-out.
# Instantly's own ue_type is 2 on EVERY received row in this workspace (checked
# read-only on all 115), so it cannot be used to tell them apart.
AUTO_REPLY_SUBJECT_PREFIXES = (
    "automatic reply", "auto reply", "auto-reply", "auto:", "autoreply",
    "out of office", "out-of-office", "ooo:", "away from my mail",
    "automatische antwort", "respuesta automatica", "réponse automatique",
    "undeliverable", "delivery status notification", "mail delivery",
)

# Where the reply ends and our own quoted email begins. Everything from here
# down is OUR words, including our unsubscribe footer.
_QUOTE_MARKERS = (
    re.compile(r"^\s*_{5,}\s*$", re.M),
    re.compile(r"^\s*-{5,}\s*$", re.M),
    re.compile(r"-+\s*original message\s*-+", re.I),
    re.compile(r"\bon\b[^\n]{0,200}?\bwrote:", re.I),
    re.compile(r"^\s*from:\s*\S+[^\n]*$", re.I | re.M),
    re.compile(r"^\s*sent from my \w+", re.I | re.M),
)

# A list older than this is refused like an incomplete one. built_utc used to
# be stored and never read: a 40-week-old file passed the fail-closed check
# exactly like a fresh one, and every address that unsubscribed, bounced or
# replied hostile in between got mailed again.
DEFAULT_MAX_AGE_HOURS = 24.0

MAX_LEAD_PAGES = 200   # 4,918 leads at limit=100 is 50 pages; 200 is headroom
MAX_EMAIL_PAGES = 30   # GET /emails is capped at 20 requests/minute
MAX_BLOCKLIST_PAGES = 50


class SuppressionError(Exception):
    pass


class SuppressionList(object):
    """Emails and domains a lead must not match, plus why."""

    def __init__(self):
        self.emails = set()      # type: Set[str]
        self.domains = set()     # type: Set[str]
        self.reasons = {}        # type: Dict[str, str]
        self.sources = {}        # type: Dict[str, Any]
        self.errors = []         # type: List[str]
        self.skipped_sources = []  # type: List[str]
        self.complete = False
        self.built_utc = ""

    # ---------------------------------------------------------------- build
    def add_email(self, email: Any, reason: str) -> bool:
        value = models.clean_text(email).lower()
        if not value or "@" not in value:
            return False
        if value not in self.emails:
            self.emails.add(value)
            self.reasons.setdefault("email:%s" % value, reason)
        return True

    def add_domain(self, domain: Any, reason: str) -> bool:
        value = models.domain_of(domain)
        if not value:
            return False
        if value not in self.domains:
            self.domains.add(value)
            self.reasons.setdefault("domain:%s" % value, reason)
        return True

    # --------------------------------------------------------------- lookup
    def check_domain(self, lead: Dict[str, Any]) -> Optional[str]:
        """The domain-level half of ``check``: free, and knowable the moment a
        row is sourced.

        Running the whole suppression check only after verification meant the
        run paid for a Perplexity look-up and 2.6 MillionVerifier checks on
        leads it already knew were suppressed by domain. In the recorded
        rehearsal that was 9 of 37 verified leads, all of them "domain already
        contacted or uploaded".
        """
        domain = lead.get("domain") or models.domain_of(lead.get("website"))
        if domain and domain in self.domains:
            return self.reasons.get("domain:%s" % domain, "domain suppressed")
        return None

    def check(self, lead: Dict[str, Any]) -> Optional[str]:
        """The reason this lead is suppressed, or None.

        Every address the lead could be mailed at is checked, not only the one
        that verified: a company whose ``first@`` bounced is not made fresh by
        our guessing ``first.last@`` instead.
        """
        by_domain = self.check_domain(lead)
        if by_domain:
            return by_domain
        checked = [lead.get("email")] + list(lead.get("email_candidates") or [])
        for email in checked:
            value = models.clean_text(email).lower()
            if not value:
                continue
            if value in self.emails:
                return self.reasons.get("email:%s" % value, "email suppressed")
            candidate_domain = models.domain_of(value)
            if candidate_domain and candidate_domain in self.domains:
                return self.reasons.get("domain:%s" % candidate_domain, "domain suppressed")
        return None

    def age_hours(self, now: Optional[datetime] = None) -> Optional[float]:
        """How old this list is, or None when it does not say."""
        stamp = (self.built_utc or "").strip()
        if not stamp:
            return None
        try:
            built = datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return round((now - built).total_seconds() / 3600.0, 2)

    def require_complete(self, max_age_hours: Optional[float] = None, now: Optional[datetime] = None) -> None:
        if not self.complete:
            raise SuppressionError(
                "suppression list is incomplete (%s); refusing to stage leads. A partial "
                "suppression list reads exactly like a complete one and is how a client, an "
                "unsubscribe or a hostile reply gets mailed again."
                % ("; ".join(self.errors) or "unknown reason")
            )
        if max_age_hours is None:
            return
        age = self.age_hours(now)
        if age is None:
            raise SuppressionError(
                "suppression list carries no built_utc, so its age cannot be checked; refusing to "
                "stage. A stale list reads exactly like a fresh one."
            )
        if age > float(max_age_hours):
            raise SuppressionError(
                "suppression list is %.1f hours old (limit %.1f, built %s); refusing to stage. "
                "Every address that unsubscribed, bounced or replied hostile since then is missing "
                "from it. Rebuild with --refresh-suppression, or pass --allow-stale-suppression if "
                "you really mean it." % (age, float(max_age_hours), self.built_utc)
            )

    def summary(self) -> Dict[str, Any]:
        return {
            "emails": len(self.emails),
            "domains": len(self.domains),
            "complete": self.complete,
            "errors": list(self.errors),
            "skipped_sources": list(self.skipped_sources),
            "sources": dict(self.sources),
            "built_utc": self.built_utc,
            "age_hours": self.age_hours(),
        }

    # --------------------------------------------------------- serialisation
    def to_dict(self) -> Dict[str, Any]:
        return {
            "emails": sorted(self.emails),
            "domains": sorted(self.domains),
            "reasons": self.reasons,
            "sources": self.sources,
            "errors": self.errors,
            "skipped_sources": self.skipped_sources,
            "complete": self.complete,
            "built_utc": self.built_utc,
        }

    @classmethod
    def from_dict(cls, blob: Dict[str, Any]) -> "SuppressionList":
        out = cls()
        out.emails = set(blob.get("emails") or [])
        out.domains = set(blob.get("domains") or [])
        out.reasons = blob.get("reasons") or {}
        out.sources = blob.get("sources") or {}
        out.errors = list(blob.get("errors") or [])
        out.skipped_sources = list(blob.get("skipped_sources") or [])
        out.complete = bool(blob.get("complete"))
        out.built_utc = blob.get("built_utc") or ""
        return out


# ------------------------------------------------------------------ builder
def manual_path() -> str:
    override = os.environ.get("LIST_FACTORY_ICP_DIR")
    base = override or os.path.join(str(CONFIG_DIR), "icp")
    return os.path.join(base, "suppression_manual.json")


def load_manual(path: Optional[str] = None) -> Dict[str, Any]:
    path = path or manual_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, IOError, ValueError) as exc:
        raise SuppressionError("could not read %s (%s)" % (path, exc))


def is_auto_reply(subject: Any) -> bool:
    """An out-of-office is not an opt-out."""
    low = models.clean_text(subject).lower().lstrip()
    for prefix in ("re:", "fw:", "fwd:"):
        while low.startswith(prefix):
            low = low[len(prefix):].lstrip()
    return any(low.startswith(prefix) for prefix in AUTO_REPLY_SUBJECT_PREFIXES)


def strip_quoted(text: Any) -> str:
    """Drop our own quoted email from the bottom of a reply.

    Without this, a warm reply that quotes the original including our
    unsubscribe footer reads as an opt-out, and the sender plus their whole
    domain are excluded from every future run.
    """
    raw = text if isinstance(text, str) else ("" if text is None else str(text))
    if not raw:
        return ""
    cut = len(raw)
    for pattern in _QUOTE_MARKERS:
        match = pattern.search(raw)
        if match is not None and match.start() < cut:
            cut = match.start()
    visible = raw[:cut]
    return "\n".join(line for line in visible.splitlines() if not line.lstrip().startswith(">"))


def _normalize(text: Any) -> str:
    """Lowercase, straighten curly apostrophes, collapse whitespace.

    "don't" arrives as "don’t" from Outlook, and an escaped literal
    apostrophe in the marker then never matches.
    """
    blob = models.clean_text(text).lower()
    return blob.replace("’", "'").replace("‘", "'").replace("ʼ", "'")


def hostile_markers_in(text: Any, subject: Any = "") -> List[str]:
    """Every marker that fires, so a false positive is visible in the output."""
    from services.list_factory.icp import keyword_hit

    if is_auto_reply(subject):
        return []
    blob = _normalize("%s\n%s" % (models.clean_text(subject), strip_quoted(text)))
    if not blob:
        return []
    return [marker for marker in HOSTILE_MARKERS if keyword_hit(blob, marker)]


def is_hostile(text: Any, subject: Any = "") -> bool:
    return bool(hostile_markers_in(text, subject=subject))


def build(client, manual: Optional[Dict[str, Any]] = None, read_emails: bool = True) -> SuppressionList:
    """Read-only build against the live workspace.

    ``client`` is a ``shared.instantly.Instantly``. Nothing here writes.
    """
    supp = SuppressionList()
    supp.built_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # 1 + 2 + 3 + 7: every lead in the workspace, its status, and its domain.
    try:
        walk = client.iterate("leads/list", body={"limit": 100}, max_pages=MAX_LEAD_PAGES)
        leads = list(walk)
        if walk.truncated:
            supp.errors.append("leads/list walk truncated at %d pages: the workspace pull is partial" % MAX_LEAD_PAGES)
        counts = {"in_workspace": 0, "bounced": 0, "unsubscribed": 0, "skipped": 0, "domains": 0}
        for lead in leads:
            email = lead.get("email") or ""
            status = lead.get("status")
            if status == STATUS_BOUNCED:
                reason = "bounced in Instantly"
                counts["bounced"] += 1
            elif status == STATUS_UNSUBSCRIBED:
                reason = "unsubscribed in Instantly"
                counts["unsubscribed"] += 1
            elif status == STATUS_SKIPPED:
                reason = "skipped in Instantly"
                counts["skipped"] += 1
            else:
                reason = "already in the workspace"
            if supp.add_email(email, reason):
                counts["in_workspace"] += 1
            # Domain-level suppression: one company, one outreach. A second
            # contact at a domain we have already mailed is a second cold email
            # to the same business, which is what stop_for_company exists for.
            domain = lead.get("company_domain") or models.domain_of(email)
            if supp.add_domain(domain, "domain already contacted or uploaded"):
                counts["domains"] += 1
        supp.sources["workspace_leads"] = dict(counts, rows=len(leads), truncated=bool(walk.truncated))
    except Exception as exc:  # noqa: BLE001 - any failure makes the list partial
        supp.errors.append("workspace leads pull failed: %s" % exc)

    # 4: the blocklist (unsubscribes Lorenzo or Instantly added by hand).
    try:
        walk = client.iterate("block-lists-entries", params={"limit": 100}, max_pages=MAX_BLOCKLIST_PAGES)
        entries = list(walk)
        if walk.truncated:
            supp.errors.append("block-lists-entries walk truncated")
        added = 0
        for entry in entries:
            value = entry.get("bl_value")
            if entry.get("is_domain"):
                added += 1 if supp.add_domain(value, "on the Instantly blocklist (domain)") else 0
            else:
                added += 1 if supp.add_email(value, "on the Instantly blocklist") else 0
        supp.sources["blocklist"] = {"rows": len(entries), "added": added}
    except Exception as exc:  # noqa: BLE001
        supp.errors.append("blocklist pull failed: %s" % exc)

    # 5: hostile replies. Instantly has no "hostile" flag, so the text decides.
    if read_emails:
        try:
            walk = client.iterate("emails", params={"email_type": "received", "limit": 100}, max_pages=MAX_EMAIL_PAGES)
            rows = list(walk)
            if walk.truncated:
                supp.errors.append("emails walk truncated at %d pages" % MAX_EMAIL_PAGES)
            hostile = 0
            hits = []  # type: List[Dict[str, Any]]
            senders = set()
            for row in rows:
                body = row.get("body")
                text = body if isinstance(body, str) else (body or {}).get("text") or ""
                blob = "%s\n%s" % (models.clean_text(row.get("content_preview")), text)
                markers = hostile_markers_in(blob, subject=row.get("subject"))
                if not markers:
                    continue
                hostile += 1
                sender = row.get("from_address_email")
                senders.add(models.clean_text(sender).lower())
                # Every hit is logged with the marker that fired, so a false
                # positive is visible without opening the cache file.
                hits.append({"from": sender, "subject": models.clean_text(row.get("subject"))[:80],
                             "markers": markers})
                supp.add_email(sender, "hostile or opt-out reply")
                supp.add_domain(models.domain_of(sender), "hostile or opt-out reply from this domain")
            supp.sources["hostile_replies"] = {
                "rows": len(rows), "hostile": hostile, "senders": len(senders), "hits": hits[:40],
            }
        except Exception as exc:  # noqa: BLE001
            supp.errors.append("received-email pull failed: %s" % exc)
    else:
        # A mandatory source that was SKIPPED leaves the list incomplete. It
        # used to leave complete=True, so --skip-hostile-scan silently turned
        # off the fail-closed guarantee and the hostile-free list was then
        # cached and reused by later runs that never passed the flag.
        supp.sources["hostile_replies"] = {"skipped": True}
        supp.skipped_sources.append("hostile_replies")
        supp.errors.append(
            "the received-email scan was skipped, so hostile replies and opt-outs that are not "
            "already in the workspace pull are NOT in this list"
        )

    # 6: clients, our own domains, free mailbox providers.
    try:
        blob = manual if manual is not None else load_manual()
        added = 0
        for domain in blob.get("client_domains") or []:
            added += 1 if supp.add_domain(domain, "client or our own sending domain") else 0
        for domain in blob.get("manual_domains") or []:
            added += 1 if supp.add_domain(domain, "manually suppressed domain") else 0
        for email in blob.get("manual_emails") or []:
            added += 1 if supp.add_email(email, "manually suppressed address") else 0
        supp.sources["manual"] = {"added": added}
    except SuppressionError as exc:
        supp.errors.append(str(exc))

    supp.complete = not supp.errors
    if not supp.complete:
        logger.error("suppression list is incomplete: %s", "; ".join(supp.errors))
    return supp


# ------------------------------------------------------------------- cache
def cache_path(day: Optional[str] = None) -> str:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    directory = os.path.join(str(tmp_dir()), "list_factory", "suppression")
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        pass
    return os.path.join(directory, "%s.json" % day)


def load_cached(path: Optional[str] = None) -> Optional[SuppressionList]:
    path = path or cache_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return SuppressionList.from_dict(json.load(fh))
    except (OSError, IOError, ValueError):
        return None


def save_cache(supp: SuppressionList, path: Optional[str] = None) -> str:
    path = path or cache_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(supp.to_dict(), fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def get(client, refresh: bool = False, manual: Optional[Dict[str, Any]] = None,
        read_emails: bool = True) -> SuppressionList:
    """Today's list, cached. A cached list that was incomplete is never reused."""
    if not refresh:
        cached = load_cached()
        if cached is not None and cached.complete:
            cached.sources["from_cache"] = True
            return cached
    supp = build(client, manual=manual, read_emails=read_emails)
    if supp.complete and not supp.skipped_sources:
        # Never cache a list built with a source switched off: a later run that
        # did NOT pass --skip-hostile-scan would silently reuse it.
        try:
            save_cache(supp)
        except (OSError, IOError) as exc:
            logger.warning("could not cache the suppression list: %s", exc)
    return supp


def apply(leads: List[Dict[str, Any]], supp: SuppressionList,
          max_age_hours: Optional[float] = None, domain_only: bool = False) -> Dict[str, Any]:
    """Reject every lead the list matches. Mandatory before staging.

    ``domain_only`` runs the free half early, right after sourcing, so the run
    does not pay to discover an owner and verify an address for a company whose
    domain is already in a campaign.
    """
    supp.require_complete(max_age_hours=max_age_hours)
    summary = {"checked": 0, "suppressed": 0, "passed": 0, "domain_only": bool(domain_only),
               "list_emails": len(supp.emails), "list_domains": len(supp.domains),
               "list_built_utc": supp.built_utc}  # type: Dict[str, Any]
    by_reason = {}  # type: Dict[str, int]
    check = supp.check_domain if domain_only else supp.check
    for lead in leads:
        summary["checked"] += 1
        reason = check(lead)
        if reason:
            models.reject(lead, models.REJECT_SUPPRESSED, reason)
            summary["suppressed"] += 1
            by_reason[reason] = by_reason.get(reason, 0) + 1
            continue
        if not domain_only:
            models.advance(lead, models.SUPPRESSED_CHECK)
        summary["passed"] += 1
    summary["by_reason"] = dict(sorted(by_reason.items(), key=lambda kv: -kv[1])[:10])
    return summary
