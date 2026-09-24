"""The template gate (CT3): may this engine email go out without a per-email Approve?

Rule (2026-09-22): an engine email (first reply, counter-proposal, booking
confirmation, cadence touch, show-rate or no-show message) is sent
automatically only when its text is exactly a template Lorenzo approved with
jobs/approve_templates.py and unchanged since, the template kill switch is off,
and every send check passes. Anything else goes to Lorenzo as an approval card
(replies) or is held (cadence, show-rate, no-show).

This module only answers that question and keeps the FYI counters. It sends
nothing itself except one urgent parity alert a day, through the ordinary
notify path (which records it and sends nothing in shadow). Every existing
send check still runs in the send paths; the gate is one more check in front.
An allowed verdict is not permission to send on its own: the day-6 approval,
the D1 veto window, opt-out, lead hold, send window and recipient checks stay
in the send paths.

Gate order (the first failure wins; any exception is ``registry_error``):

1. kill switch            template_approvals.kill_switch_on()
2. parity                 the catalogue digest equals config/template_catalogue_hashes.json
                          (a catalogue that cannot be built yet because an
                          engine module is still importing is registry_error,
                          with no parity alert)
3. template render        a Draft's model is "template" (not_template_render),
                          and a template id is present (no_template)
4. ids                    every id (main plus parts) exists in the kind's
                          catalogue (unknown_id), is approvable (not_approvable)
                          and its status is approved (unapproved /
                          changed_since_approval)
5. stamp                  the hash stamped at render time equals the current
                          hash, main and parts (stale_render)
6. classification         first replies AND booking emails: a positive label
                          (POSITIVE_LABELS), confidence >= classify.CONFIDENCE_FLOOR,
                          method not "fallback"; no classification is refused
7. requested override     ``requested`` is None (requested_override)
8. copy gate              the kind's copy rules pass on the body, and the
                          subject passes the same banned-word, figure, "!"
                          and link checks (copy_gate); a researched day 2
                          touch also runs cadence.copy_problems on its body
                          here, whatever touch.problems says
9. conforms               the text is the template with only its placeholders
                          filled, each with a value of its type (nonconforming);
                          a researched day 2 touch is checked as below

How a placeholder is checked (step 9)
-------------------------------------
Every captured value must be unchanged by NFKC normalisation, and the whole
body and subject may carry no control, format, zero-width, separator or
blank-rendering characters. Then, per placeholder type:

- names (first_name, referral_name, referral_first_name): letters with
  hyphen, apostrophe and spaces, a period only after an initial, at most 3
  words and 40 characters, and no mix of scripts: Latin letters with a
  letter from any other script, or Cyrillic with Greek ("Jordan" with a
  Cyrillic "о" or an Armenian "օ" is refused; "José" and "Müller" are
  Latin and pass). referral_first_name is the first
  word of referral_name and never an article or a role word ("The",
  "Manager").
- free text (company, specialty, original_subject): at most 80 characters and
  10 words; letters, digits, space and & . , ' ( ) / + # - only; no link,
  e-mail address, phone number, money figure or percentage, no "!" and no
  "?", and no period followed by a capitalised word unless the period ends an
  initial or an abbreviation. A company is stricter: at most 8 words, no run
  of 5 or more digits, nothing after Inc., LLC., Ltd., Corp., LLP., PLLC. or
  PC. but another of those, and no period followed by any word (whatever its
  case) unless the period ends an initial or an abbreviation, and the same
  no-mixed-scripts rule as names. Look-alike letters are not refused in
  specialty or original_subject.
- times and slots: the value must be exactly what the engine's own formatter
  (shared.slots.format_slot / format_slots / format_asked_time,
  booking._dated_slot(s), show_rate.fmt_when / fmt_time_only) writes for
  some time. The formatter is
  called to check; nothing here restates its format. The lead's own time
  (the bracketed part of {when_ct}, and {lead_local_time}) may be in any zone
  the formatters can be handed: every pytz common zone and every US/* and
  Canada/* alias (_lead_zones). {lead_local_time} must be the lead's time for
  the {slot} in the same text, in winter or summer time.
- links: https only, with the host spelled out (no user info, no port):
  booking_url is a configured booking link or a GHL booking-widget link
  (GHL_BOOKING_LINKS: that host, that path and one calendar id, with
  nothing after it) whose calendar id is one of ours (ghl.calendars.*.id in
  config/ids.json, or the id in a configured booking link), zoom_link (the
  call's join link) is on zoom.us or a subdomain of it, or on exactly
  meet.google.com when it is the appointment's own call link bound by
  appointment_bindings() (never a Meet link on its own), loom_url is a
  configured Loom link.

``bindings`` ({placeholder: value}) pins a placeholder to the value the caller
knows (the lead's first name, the offered slots, the link): the captured
value must equal it exactly AND pass its type's check above. A binding only
narrows the check; a bound link that is not a configured or allowed link is
refused like an unbound one. The one kind of binding that is its own check is
a time value appointment_bindings() computed for an appointment with the
engine's own formatters: equal to it, the value is accepted even for a lead
zone outside the list (a legacy name such as America/Indianapolis).

The ``confirmed_time`` variant of a first reply ("{slot} CT works on my end. I
will send the invite over, and if anything shifts, you can grab a different
time here: {booking_url}") never auto-sends: the gate cannot know the
invite was actually booked, so a body that matches only that variant is
nonconforming.

The researched day 2 line (E2)
------------------------------
Day 2 auto-sends with a per-lead line in {research_line} only when its parts
are exactly [template_approvals.RESEARCH_RULES_ID] ("cadence.d2.research_rules",
the rules Lorenzo approved, checked by steps 4 and 5 like any part) on
cadence.d2 (RESEARCH_RULES_MAINS). The per-lead line with no rules
(cadence.d2.research_line) stays not approvable, and the fallback parts
(cadence.d2.research_fallback.*) are checked as before. For a researched
touch, after step 8 (touch_verdict only; everywhere else the rules part is
refused as unknown_id or nonconforming):

- touch.meta is a dict with a non-empty "research_line" (research_line_missing)
  and a dict "research_evidence" (research_evidence_missing);
- the bindings carry RESEARCH_CONTEXT_KEYS (company, website_domain,
  offer_branch, niche), each non-empty text, offer_branch "reactivation" or
  "outbound" (research_context_missing);
- the body matches the approved cadence.d2 text or one of its variants with
  every placeholder checked as above and {research_line} a bounded capture:
  one line (no line break at all, so never a blank line), at most
  RESEARCH_LINE_MAX_CHARS characters, no "{" or "}", no leading or trailing
  space, NFKC-stable, no control or format characters (nonconforming);
- the captured line equals normalise(touch.meta["research_line"])
  (research_line_mismatch);
- the rules module imports and is complete (research_rules_unavailable), and
  its rules still hash to the catalogue entry just checked
  (changed_since_approval);
- research_rules.validate(line, evidence, context) is called HERE, at verdict
  time, on a copy of the evidence; a stored verdict is never read. An
  exception, or anything but a verdict, is research_rules_error;
  verdict.rules_sha must equal research_rules_sha() of the module now
  (research_rules_sha_mismatch); verdict.ok must be True
  (research_rules_failed, with the validator's reasons in the detail); and
  verdict.line must equal the captured line (research_line_mismatch).

``Verdict.to_record()`` carries ids, statuses and the reason, never any text.
The FYI queue and the held counters carry ids, statuses and counts only.

Engine modules that are edited alongside this one (draft, cadence, classify,
models, booking, show_rate) are imported inside the functions that need them,
by name.
"""
import copy as copy_mod
import hashlib
import itertools
import json
import logging
import os
import platform
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from shared.paths import BASE_DIR, IDS_PATH

from services.reply_engine import template_approvals as ta

logger = logging.getLogger("reply_engine.template_gate")

REASONS = ("ok", "kill_switch", "parity_failed", "no_template", "not_template_render", "unknown_id",
           "unapproved", "changed_since_approval", "not_approvable", "stale_render", "classification",
           "requested_override", "copy_gate", "nonconforming", "registry_error",
           # the researched day 2 line (see "The researched day 2 line" above)
           "research_line_missing", "research_evidence_missing", "research_context_missing",
           "research_line_mismatch", "research_rules_unavailable", "research_rules_error",
           "research_rules_failed", "research_rules_sha_mismatch")

FYI_KEY = "autosend_fyi:pending"
HELD_KEY_PREFIX = "autosend_fyi:held:"
FYI_LEASE_PREFIX = "autosend_fyi:lease:"
FYI_MINUTES = 30
FYI_CAP = 500

PARITY_REFERENCE_PATH = BASE_DIR / "config" / "template_catalogue_hashes.json"
PARITY_REFERENCE_NAME = "template_catalogue_hashes.json"
PARITY_ALERT_PREFIX = "template_parity_alert:"
PARITY_OK = "ok"
PARITY_MISMATCH = "mismatch"
PARITY_MISSING = "reference_missing"
PARITY_ERROR = "error"
PARITY_NOT_READY = "not_ready"
PARITY_ALERT_MAX_IDS = 20
# After a failed push this process waits this long before trying again (the
# day's claim is released, so another container may try sooner).
PARITY_ALERT_RETRY_MINUTES = 15

DRAFT_KINDS = ("first_reply", "booking")
APPOINTMENT_KINDS = ("show_rate", "no_show")
CLASSIFIED_KINDS = ("first_reply", "booking")
# The catalogue kind each gated message kind must resolve to, and the kind its
# parts (spliced lines) must have. A first-reply id passed as "booking" would
# get the booking copy rules, so a kind mismatch is refused as unknown_id.
MAIN_KIND = {"first_reply": "first_reply", "booking": "booking", "cadence": "cadence",
             "show_rate": "show_rate", "no_show": "no_show"}
PART_KIND = {"cadence": "cadence_fragment"}
# Part id prefix -> the placeholder its text fills in the day template.
PART_PLACEHOLDERS = (
    ("cadence.d2.research_fallback.", "research_line"),
    ("cadence.d2.research_line", "research_line"),
    (ta.RESEARCH_RULES_ID, "research_line"),
    ("cadence.d4.case_study.", "case_study"),
    ("cadence.d5.free_work.", "free_work"),
)
PART_FILLED = tuple(sorted(set(ph for _, ph in PART_PLACEHOLDERS)))
LADDER_PREFIXES = ("cadence.", "show_rate.", "no_show.")
# Ladder ids that are unextractable on purpose (never approvable), so the
# deploy preflight does not count them as a failed extraction. An entry that
# carries "unextractable_by_design" is skipped too: cadence.d2.research_rules
# while its module is not there yet (a rules module that is there but broken
# IS counted).
UNEXTRACTABLE_BY_DESIGN = ("cadence.d2.research_line",)
# The researched day 2 line: the rules part may only be given to these main
# ids, of these gated kinds, and fills this placeholder with a capture.
RESEARCH_RULES_MAINS = ("cadence.d2",)
RESEARCH_RULES_KINDS = ("cadence",)
RESEARCH_PLACEHOLDER = "research_line"
RESEARCH_LINE_MAX_CHARS = 300
# The context research_rules.validate gets, read from the bindings.
RESEARCH_CONTEXT_KEYS = ("company", "website_domain", "offer_branch", "niche")
RESEARCH_OFFER_BRANCHES = ("reactivation", "outbound")
# Variants that never auto-send even when approved (see the module docstring).
NEVER_AUTO_VARIANTS = ("confirmed_time",)
SUBJECT_VARIANT = "subject"
SUBJECT_PREFIX = "Subject: "

MAX_BODY_CHARS = 6000
MAX_SUBJECT_CHARS = 300

# The version of this module's rules: the gate order and every check below
# (the value checks for names, free text, times and links, and the
# conformance match). A rule change alone moves nothing else: the catalogue,
# its hashes and the approvals stay the same. A live D1 whose full check was
# refused is checked again only once something that check depended on has
# changed (cadence._d1_gate_fingerprint, which carries this number and
# catalogue_digest_cached()), so bump it with any change to a rule: every
# such D1 is then checked afresh once after the deploy. Without the bump it
# stays held until the lead's data or the template changes, or Lorenzo taps
# Resume on its stop (runbooks/template_approvals.md, "Cadence holds, stalls
# and resume"). tests/test_gate_rules_version.py pins this module's source
# per version, so a change to this file without a bump fails the suite.
GATE_RULES_VERSION = 2

# Placeholder types.
NAME_PLACEHOLDERS = ("first_name", "referral_name", "referral_first_name")
TEXT_PLACEHOLDERS = ("company", "specialty", "original_subject")
TIME_VALUE_PLACEHOLDERS = tuple(ta.TIME_PLACEHOLDERS)
URL_PLACEHOLDERS = ("booking_url", "zoom_link", "loom_url")
NAME_MAX_CHARS = 40
NAME_MAX_WORDS = 3
TEXT_MAX_CHARS = 80
TEXT_MAX_WORDS = 10
COMPANY_MAX_WORDS = 8
TIME_MAX_CHARS = 60
URL_MAX_CHARS = 300
ZOOM_HOST_SUFFIXES = ("zoom.us",)
# Google Meet join links (the Discovery Call calendar's widget bookings), by
# exact host: https, no user info, no port, no subdomain (_LINK_RE and
# _link_parts already refuse everything but a plain https host). Accepted
# ONLY as the appointment's own call link, bound by appointment_bindings()
# (_EngineLink): a Meet link the text produced on its own is refused.
MEET_HOSTS = ("meet.google.com",)
# GHL booking-widget links, the one host and path the code and config use for
# booking and rescheduling (config/ids.json ghl.calendars.discovery_call.
# booking_url, cadence.DEFAULT_BOOKING_URL, changesets/ghl_workflows/*.md):
# (host, path prefix). The link must be the prefix plus one calendar id
# segment and nothing after it (no query, no fragment), as all of those are.
GHL_BOOKING_LINKS = (("api.leadconnectorhq.com", "/widget/booking/"),)
# The calendar id in such a link must be one of ours: an id under
# ghl.calendars.<name>.id in config/ids.json (read only), or the id of a
# configured booking link. Anyone can make a GHL calendar, so a link to a
# stranger's calendar on the same host is refused.
CALENDAR_IDS_PATH = IDS_PATH
# Corporate-form suffixes end a company name: after "Inc." only another one of
# these may follow ("Acme Inc. Reply with your password" is a sentence).
CORPORATE_SUFFIXES = frozenset("inc llc ltd corp llp pllc pc".split())
# A name may use the letters of one of these scripts only, and a name or a
# company that has Latin letters may have no letter from any other script
# (Armenian "\u0585" or Cherokee "\u13fc" in a Latin word). Latin letters with
# diacritics are Latin ("Jos\u00e9", "M\u00fcller").
LOOKALIKE_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")
LATIN_SCRIPT = "LATIN"
# Lead zones: every pytz common zone plus the pytz names under these prefixes.
LEAD_ZONE_ALIAS_PREFIXES = ("US/", "Canada/")
# An undated lead-zone time is checked in FIXED_NOW's week (winter) and this
# many weeks later (summer), so both the standard and the daylight label pass.
SUMMER_WEEK_OFFSET = 26
# Per-instant tables of every zone's rendering kept at once.
ZONE_OUTPUTS_MAX = 512
# referral_first_name is spliced in as "looping {referral_first_name} in":
# an article or a role word there is a sentence about nobody.
ROLE_WORDS = frozenset("""
a an the our my your their his her its this that these those
manager managers owner owners boss ceo coo cfo cto founder cofounder president director directors
team office someone somebody anyone whoever person people staff admin administrator department
partner partners them him it they hr accounts accounting billing sales support reception receptionist
""".split())
# A word before ". X" that is an abbreviation, not the end of a sentence.
# "Mr. Rooter", "Ms. Molly Maid", "Ft. Worth", "Assoc.", "Svcs.", "Mfg.", "Ctr." are common in trade names.
ABBREVIATIONS = frozenset("co inc ltd corp llc llp pc pllc bros st mt dr jr sr no dept assn intl "
                          "mr mrs ms ft pt assoc svcs mfg ctr".split())

# Characters that render blank or reflow a line without being "\n".
_BLANK_CHARS = frozenset("\u2800\u3164\u115f\u1160\uffa0\u180e")

# Regex classes the pattern uses per placeholder type, so the engine only
# considers splits of a plausible shape. Each captured value is then checked
# in full by the validator; the class is a narrowing, never the check.
_NAME_CLASS = r"(?:[^\W\d_]|[ .'\u2019-]){1,%d}?" % NAME_MAX_CHARS
_TEXT_CLASS = r"(?:[^\W_]|[ &.,'\u2019()/+#-]){1,%d}?" % TEXT_MAX_CHARS
# + and - for the numeric zone labels pytz writes ("-03", "+0530").
_TIME_CLASS = r"(?:[^\W_]|[ :,()+-]){1,%d}?" % TIME_MAX_CHARS
_URL_CLASS = r"[!#-;=?-~]{1,%d}?" % URL_MAX_CHARS   # printable ASCII except space, < and >
# A researched day 2 line: one line, no braces. _research_capture_ok checks it in full.
_RESEARCH_CLASS = r"[^{}\n]{1,%d}?" % RESEARCH_LINE_MAX_CHARS

_NAME_WORD_RE = re.compile(r"(?:[^\W\d_]\.)+|[^\W\d_]+(?:['\u2019-][^\W\d_]+)*")
_TEXT_CHARS_RE = re.compile(r"(?:[^\W_]|[ &.,'\u2019()/+#-])+")
_URLISH_RE = re.compile(r"https?:|www\.|://|[^\W_][\w-]*\.[^\W\d_]{2,}(?![^\W\d_])", re.I)
_PHONEISH_RE = re.compile(r"\d{3}\s*[-.)]?\s*\d{3,4}")
_MONEY_WORD_RE = re.compile(r"\b(?:usd|dollars?|euros?|percent|bucks)\b", re.I)
_THOUSANDS_RE = re.compile(r"\d,\d{3}")
_DIGIT_RUN_RE = re.compile(r"\d{5,}")
# A word, a period, space and the next word. The next word is looked at, not
# consumed, so "J. Acme. Reply" is checked at both periods.
_SENTENCE_BREAK_RE = re.compile(r"([^\W_]+)\.\s+(?=([^\W_]+))")
# A link, split strictly: https, a host of dot-separated labels (letters,
# digits, hyphens; no user info, no port), then nothing, or a path, query or
# fragment of RFC 3986 characters (no backslash, no space, no quotes).
_HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_LINK_RE = re.compile(r"https://(%s(?:\.%s)+)([/?#][A-Za-z0-9._~!$&'()*+,;=:@%%/?#-]*)?"
                      % (_HOST_LABEL, _HOST_LABEL))
_GHL_ID_SEGMENT_RE = re.compile(r"[A-Za-z0-9_-]+/?")
_CLOCK_RE = re.compile(r"(\d{1,2}):(\d{2})")
_NUMBER_RE = re.compile(r"\d+")
_SUBJECT_LINK_RE = re.compile(r"https?:|www\.|://|@|[^\W_][\w-]*\.[^\W\d_]{2,}(?![^\W\d_])", re.I)


@dataclass
class Verdict:
    allowed: bool
    reason: str
    template_id: Optional[str]
    ids: List[str] = field(default_factory=list)
    statuses: Dict[str, str] = field(default_factory=dict)
    detail: str = ""

    def to_record(self) -> Dict[str, Any]:
        """ids, statuses and the reason only. ``detail`` is left out: a copy
        problem can quote a figure from the body, and the record is stored."""
        return {"allowed": bool(self.allowed), "reason": self.reason, "template_id": self.template_id,
                "ids": list(self.ids), "statuses": dict(self.statuses)}


class _Fail(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        Exception.__init__(self, reason)
        self.reason = reason
        self.detail = detail


# ------------------------------------------------------------ the index
_INDEX_CACHE = {"key": None, "index": None}  # type: Dict[str, Any]
_PARITY_CACHE = {"key": None, "result": None}  # type: Dict[str, Any]
# The CT day this process last sent (or saw claimed) the parity alert, so a
# failing parity does not cost one store claim per verdict.
_ALERT_SEEN = {"day": None, "retry_after": None}  # type: Dict[str, Any]
# (placeholder, value, the {slot} beside it for lead_local_time) -> verdict
_VALUE_CACHE = {}  # type: Dict[Tuple[str, str, Optional[str]], bool]
_VALUE_CACHE_MAX = 4096
# (kind, UTC timestamp) -> every rendering of that instant over the lead zones
_ZONE_OUTPUTS = {}  # type: Dict[Tuple[str, float], frozenset]
# The lead zones, built once per process (they depend on pytz only).
_ZONES = {"list": None}  # type: Dict[str, Any]
# The GHL calendar ids from CALENDAR_IDS_PATH, keyed on the file's path, size
# and mtime, so an edited ids.json is read again.
_CALENDAR_IDS = {"key": None, "ids": frozenset()}  # type: Dict[str, Any]
# (index, catalogue_digest of it): the digest of the catalogue this process
# built, beside the index object it was computed from. One tuple, replaced
# whole, so a reader never pairs one index with another's digest.
_DIGEST_CACHE = {"pair": None}  # type: Dict[str, Any]


def clear_cache() -> None:
    # Keys first: a reader that races this sees a miss, never an old value.
    _INDEX_CACHE["key"] = None
    _INDEX_CACHE["index"] = None
    _DIGEST_CACHE["pair"] = None
    _PARITY_CACHE["key"] = None
    _PARITY_CACHE["result"] = None
    _ALERT_SEEN["day"] = None
    _ALERT_SEEN["retry_after"] = None
    _VALUE_CACHE.clear()
    _ZONE_OUTPUTS.clear()
    _CALENDAR_IDS["key"] = None
    _CALENDAR_IDS["ids"] = frozenset()


def _index(key: Optional[Tuple[Any, ...]] = None) -> Dict[str, Dict[str, Any]]:
    """The catalogue index, cached per process on template_approvals'
    content key. One deep copy per rebuild, none on the hot path. Callers
    must not mutate it. Raises ta.CatalogueNotReady while an engine module
    is still importing (the catalogue is never built half-imported)."""
    key = key if key is not None else ta._source_key()
    if _INDEX_CACHE["index"] is not None and _INDEX_CACHE["key"] == key:
        return _INDEX_CACHE["index"]
    index = ta.catalogue_index()
    if ta._source_key() == key:
        # Value before key: a reader that sees the new key sees the new index.
        _INDEX_CACHE["index"] = index
        _INDEX_CACHE["key"] = key
    _warm_lead_zones()
    return index


def _warm_lead_zones() -> None:
    """Build the lead-zone list with the catalogue: loading every zone from
    pytz is a one-time cost of some 40 ms a process, paid here once instead of
    inside the first value check that needs it. The engine modules are all
    imported by now (the catalogue was just built). A failure is left to that
    value check, which then fails closed."""
    if _ZONES["list"] is not None:
        return
    try:
        _lead_zones()
    except Exception as exc:  # noqa: BLE001 - the value check retries and fails closed
        logger.warning("lead zone warm-up failed: %s", type(exc).__name__)


def _hash_of(index: Dict[str, Dict[str, Any]], template_id: Optional[str]) -> Optional[str]:
    if not template_id:
        return None
    entry = index.get(template_id)
    return entry.get("sha256") if entry else None


def current_hash(template_id: str) -> Optional[str]:
    """The catalogue sha256 of ``template_id`` now; None when unknown or
    unextractable (or when the catalogue cannot be built)."""
    try:
        return _hash_of(_index(), template_id)
    except Exception as exc:  # noqa: BLE001 - a hash we cannot compute is no hash
        logger.warning("current_hash(%s) failed: %s", template_id, type(exc).__name__)
        return None


def _set(obj: Any, name: str, value: Any) -> None:
    try:
        setattr(obj, name, value)
    except Exception as exc:  # noqa: BLE001 - an unstamped object fails the gate later
        logger.warning("could not stamp %s on %s: %s", name, type(obj).__name__, type(exc).__name__)


def stamp(obj: Any, template_id: Optional[str], parts: Sequence[str] = ()) -> None:
    """Record on a Draft or Touch which template it was rendered from and the
    hashes at render time. Called by the pipeline, the tick and the scheduler,
    never by builder code (builders return ids only). Never raises: an object
    that cannot be stamped fails the gate as stale_render or no_template."""
    try:
        index = _index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("stamp: catalogue unavailable (%s)", type(exc).__name__)
        index = {}
    parts = [p for p in (parts or ()) if p]
    _set(obj, "template_id", template_id or None)
    _set(obj, "template_hash", _hash_of(index, template_id))
    if parts or hasattr(obj, "template_parts"):
        _set(obj, "template_parts", dict((p, _hash_of(index, p)) for p in parts))


# --------------------------------------------------------------- digest
def catalogue_digest(index: Optional[Dict[str, Dict[str, Any]]] = None) -> Tuple[str, Dict[str, str]]:
    """(digest, id -> sha256) over every approvable id. The digest is the
    sha256 of the sorted ``id=sha`` lines joined by newlines. The single
    source for it: template_parity.py and parity_status both call this."""
    idx = index if index is not None else _index()
    ids = dict((tid, e["sha256"]) for tid, e in idx.items() if e.get("approvable") and e.get("sha256"))
    lines = sorted("%s=%s" % (tid, sha) for tid, sha in ids.items())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(), ids


def catalogue_digest_cached() -> str:
    """catalogue_digest() of the catalogue this process builds now, computed
    once per catalogue build: the digest is kept beside the index object it
    came from (_DIGEST_CACHE), so while the catalogue is unchanged a call
    costs only the catalogue cache lookup every verdict already makes
    (_index()). Raises when the catalogue cannot be built."""
    index = _index()
    pair = _DIGEST_CACHE["pair"]
    if pair is None or pair[0] is not index:
        pair = (index, catalogue_digest(index)[0])
        _DIGEST_CACHE["pair"] = pair
    return pair[1]


def _versions() -> Dict[str, str]:
    out = {"python": platform.python_version()}
    try:
        import pytz

        out["pytz"] = str(pytz.__version__)
    except Exception:  # noqa: BLE001
        out["pytz"] = "unknown"
    try:
        import pydantic

        out["pydantic"] = str(pydantic.VERSION)
    except Exception:  # noqa: BLE001
        out["pydantic"] = "unknown"
    return out


def reference_record(index: Optional[Dict[str, Dict[str, Any]]] = None,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    """What config/template_catalogue_hashes.json holds: the versions it was
    built with, when, the digest and the id -> sha256 map. Ids and hashes
    only, never template text."""
    digest, ids = catalogue_digest(index)
    rec = _versions()
    rec["generated_at"] = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    rec["digest"] = digest
    rec["ids"] = dict(sorted(ids.items()))
    return rec


def ladder_ids(index: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """Every approvable cadence, show_rate and no_show id (fragments included)."""
    idx = index if index is not None else _index()
    return sorted(tid for tid, e in idx.items() if e.get("approvable") and tid.startswith(LADDER_PREFIXES))


def unextractable_ladder_ids(index: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """Ladder ids the catalogue could not render (an extractor failed), other
    than the ones that are unextractable by design. A touch that uses one is
    held until the code is fixed."""
    idx = index if index is not None else _index()
    return sorted(tid for tid, e in idx.items()
                  if tid.startswith(LADDER_PREFIXES) and not e.get("extractable") and tid not in UNEXTRACTABLE_BY_DESIGN
                  and not e.get("unextractable_by_design"))


# --------------------------------------------------------------- parity
def _parity(key: Optional[Tuple[Any, ...]] = None) -> Dict[str, Any]:
    path = Path(PARITY_REFERENCE_PATH)
    try:
        if not path.exists():
            return {"status": PARITY_MISSING, "ids": []}
        raw = path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        return {"status": PARITY_ERROR, "ids": [], "detail": type(exc).__name__}
    try:
        key = key if key is not None else ta._source_key()
        cache_key = (key, str(path), hashlib.sha256(raw).hexdigest())
        if _PARITY_CACHE["key"] == cache_key and _PARITY_CACHE["result"] is not None:
            return dict(_PARITY_CACHE["result"])
        ref = json.loads(raw.decode("utf-8"))
        ref_digest = ref.get("digest") if isinstance(ref, dict) else None
        ref_ids = ref.get("ids") if isinstance(ref, dict) else None
        if not isinstance(ref_digest, str) or not isinstance(ref_ids, dict):
            result = {"status": PARITY_ERROR, "ids": [], "detail": "reference has no digest or ids"}
        else:
            digest, current = catalogue_digest(_index(key))
            if digest == ref_digest:
                result = {"status": PARITY_OK, "ids": []}
            else:
                differing = sorted(tid for tid in set(ref_ids) | set(current) if ref_ids.get(tid) != current.get(tid))
                result = {"status": PARITY_MISMATCH, "ids": differing}
        _PARITY_CACHE["result"] = dict(result)
        _PARITY_CACHE["key"] = cache_key
        return result
    except ta.CatalogueNotReady:
        return {"status": PARITY_NOT_READY, "ids": []}
    except Exception as exc:  # noqa: BLE001
        return {"status": PARITY_ERROR, "ids": [], "detail": type(exc).__name__}


def parity_status() -> Dict[str, Any]:
    """{"status": ok|mismatch|reference_missing|error|not_ready, "ids": [...]}:
    whether the catalogue this process builds hashes to the reference written
    at deploy time (config/template_catalogue_hashes.json). Cached per process
    on the catalogue's content key plus the reference file's content.
    not_ready: an engine module is still importing, so the catalogue was not
    built (no alert for it)."""
    return _parity()


def _ct_date(now: Optional[datetime] = None) -> str:
    from shared import slots as slot_rules

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(slot_rules.TZ).date().isoformat()


def _push_went_out(result: Any) -> bool:
    """notify() never raises; it reports. A test capture or a shadow record is
    the notify path doing its job, so it counts as delivered."""
    if not isinstance(result, dict):
        return False
    return bool(result.get("sent") or result.get("shadow") or result.get("test"))


def alert_parity_failure(status: Dict[str, Any], store: Any = None, now: Optional[datetime] = None) -> bool:
    """One urgent push a day saying template auto-send is off because of
    parity. Ids and counts only. The day is claimed with set_if_absent before
    the push (so two containers do not both send) and the claim is released
    when the push fails, so a later verdict tries again. True when this call
    delivered it (or, in shadow, recorded it). Never raises."""
    claimed = None
    try:
        if (status or {}).get("status") in (PARITY_OK, PARITY_NOT_READY):
            return False
        if store is None:
            from shared import store as store_mod

            store = store_mod.get_store()
        key = PARITY_ALERT_PREFIX + _ct_date(now)
        if not store.set_if_absent(key, {"status": status.get("status"), "count": len(status.get("ids") or [])}):
            return False
        claimed = key
        from shared import notify

        ids = list(status.get("ids") or [])
        shown = ids[:PARITY_ALERT_MAX_IDS]
        lines = ["Template auto-send is OFF: every engine email becomes a card or a hold.",
                 "Parity status: %s. Differing ids: %d." % (status.get("status"), len(ids))]
        if shown:
            lines.append("Ids: %s%s" % (", ".join(shown), " (+%d more)" % (len(ids) - len(shown))
                                         if len(ids) > len(shown) else ""))
        lines.append("Fix: run the deploy preflight (template_parity.py --write, then --check) and redeploy.")
        result = notify.notify("Template parity %s: auto-send off" % status.get("status"), "\n".join(lines),
                               priority="urgent", tags=["warning", "reply-engine"])
        if not _push_went_out(result):
            store.delete(claimed)
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - the alert is about a failure, it must not become one
        logger.warning("template parity alert failed: %s", type(exc).__name__)
        if claimed is not None:
            try:
                store.delete(claimed)
            except Exception:  # noqa: BLE001
                logger.warning("could not release the parity alert claim %s", claimed)
        return False


def _parity_ok_or_alert(key: Optional[Tuple[Any, ...]] = None) -> Dict[str, Any]:
    ps = _parity(key)
    if ps.get("status") not in (PARITY_OK, PARITY_NOT_READY):
        try:
            day = _ct_date()
        except Exception:  # noqa: BLE001
            day = None
        now = datetime.now(timezone.utc)
        retry_after = _ALERT_SEEN["retry_after"]
        if (day is None or _ALERT_SEEN["day"] != day) and (retry_after is None or now >= retry_after):
            if alert_parity_failure(ps):
                _ALERT_SEEN["day"] = day
                _ALERT_SEEN["retry_after"] = None
            else:
                _ALERT_SEEN["retry_after"] = now + timedelta(minutes=PARITY_ALERT_RETRY_MINUTES)
    return ps


def auto_send_enabled() -> bool:
    """Kill switch off and parity ok. Any error is False."""
    try:
        if ta.kill_switch_on():
            return False
        return _parity_ok_or_alert().get("status") == PARITY_OK
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_send_enabled failed closed: %s", type(exc).__name__)
        return False


def health_summary() -> Dict[str, Any]:
    """For /health: parity, kill switch, approved counts. No ids beyond
    counts, no text. Never raises."""
    out = {}  # type: Dict[str, Any]
    try:
        out["kill_switch"] = bool(ta.kill_switch_on())
    except Exception:  # noqa: BLE001
        out["kill_switch"] = True
    try:
        ps = parity_status()
        out["parity"] = ps.get("status")
        out["parity_differing"] = len(ps.get("ids") or [])
    except Exception:  # noqa: BLE001
        out["parity"] = PARITY_ERROR
        out["parity_differing"] = 0
    try:
        index = _index()
        approvals = ta.load_approvals()
        approvable = [tid for tid, e in index.items() if e.get("approvable")]
        approved = [tid for tid in approvable
                    if ta.status(tid, entries=index, approvals=approvals) == ta.STATUS_APPROVED]
        ladders = set(ladder_ids(index))
        out["approvable_count"] = len(approvable)
        out["approved_count"] = len(approved)
        out["ladder_unapproved_count"] = len(ladders - set(approved))
    except Exception as exc:  # noqa: BLE001
        out["approvable_count"] = None
        out["approved_count"] = None
        out["ladder_unapproved_count"] = None
        out["error"] = type(exc).__name__
    out["auto_send_enabled"] = (not out["kill_switch"]) and out.get("parity") == PARITY_OK
    return out


# ------------------------------------------------------- value checks
def _nfkc_stable(value: str) -> bool:
    return unicodedata.normalize("NFKC", value) == value


def _clean_chars(text: str, allow_newline: bool) -> bool:
    """No control, format, private, unassigned, separator (other than a plain
    space) or blank-rendering characters. "\\n" only where allowed."""
    for ch in text:
        if ch == "\n" and allow_newline:
            continue
        if ch == " ":
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("C", "Z") or ch in _BLANK_CHARS:
            return False
    return True


def _mixed_script(value: str) -> bool:
    """True when the value mixes scripts: Latin letters with a letter from any
    other script (a Cyrillic, Greek, Armenian or Cherokee look-alike in a
    Latin word), or letters from more than one of LOOKALIKE_SCRIPTS. The
    script is the first word of the letter's Unicode name ("LATIN SMALL
    LETTER E WITH ACUTE"); a letter with no name counts as its own script, so
    it never passes beside Latin letters."""
    seen = set()  # type: set
    for ch in value:
        if ch.isalpha():
            seen.add(unicodedata.name(ch, "?").split(" ", 1)[0])
    if LATIN_SCRIPT in seen and len(seen) > 1:
        return True
    return len(seen & set(LOOKALIKE_SCRIPTS)) > 1


def _name_ok(value: str, max_words: int = NAME_MAX_WORDS) -> bool:
    if not value or len(value) > NAME_MAX_CHARS or value != value.strip() or "  " in value:
        return False
    words = value.split(" ")
    if len(words) > max_words:
        return False
    if _mixed_script(value):
        return False
    return all(_NAME_WORD_RE.fullmatch(w) for w in words)


def _free_text_ok(value: str, company: bool = False) -> bool:
    """Short free text (company, specialty, original_subject). ``company``
    adds the stricter company rules (see the module docstring)."""
    if not value or len(value) > TEXT_MAX_CHARS or value != value.strip() or "  " in value:
        return False
    if len(value.split(" ")) > (COMPANY_MAX_WORDS if company else TEXT_MAX_WORDS):
        return False
    if not _TEXT_CHARS_RE.fullmatch(value):
        return False
    if _URLISH_RE.search(value) or _MONEY_WORD_RE.search(value) or _THOUSANDS_RE.search(value):
        return False
    if sum(ch.isdigit() for ch in value) >= 7 or _PHONEISH_RE.search(value):
        return False
    if company and (_DIGIT_RUN_RE.search(value) or _mixed_script(value)):
        return False
    for m in _SENTENCE_BREAK_RE.finditer(value):
        word, nxt = m.group(1), m.group(2)
        lower = word.lower()
        if company and lower in CORPORATE_SUFFIXES:
            if nxt.lower() in CORPORATE_SUFFIXES:
                continue          # "Co. Ltd", "Inc. LLC"
            return False          # "Acme Inc. Reply with ..."
        if len(word) == 1 or lower in ABBREVIATIONS:
            continue              # an initial ("J. R.") or an abbreviation ("Co.", "St.")
        if company or nxt[:1].isupper():
            return False          # a second sentence ("Acme. reply ...")
    return True


def _configured_booking_urls() -> List[str]:
    out = []  # type: List[str]
    try:
        from shared import settings

        out.append(getattr(settings, "BOOKING_URL", None))
    except Exception:  # noqa: BLE001
        pass
    try:
        from services.reply_engine import cadence

        out.append(getattr(cadence, "DEFAULT_BOOKING_URL", None))
    except Exception:  # noqa: BLE001
        pass
    return [u for u in out if isinstance(u, str) and u]


def _configured_loom_urls() -> List[str]:
    return [v for k, v in os.environ.items() if k.startswith("LOOM_URL_") and v]


def _link_parts(value: str) -> Optional[Tuple[str, str]]:
    """(host lower-cased, everything after the host) of an https link, or
    None when the value is not one by the strict grammar (_LINK_RE), is too
    long, or ends in punctuation that would read as the end of the
    sentence."""
    if not value or len(value) > URL_MAX_CHARS or value[-1] in ".,;:)!?":
        return None
    m = _LINK_RE.fullmatch(value)
    if m is None:
        return None
    return m.group(1).lower(), m.group(2) or ""


def _ghl_calendar_id(host: str, rest: str) -> Optional[str]:
    """The calendar id of a GHL_BOOKING_LINKS link (its host, its path prefix
    and one id segment, nothing else), or None when it is not one."""
    for ghl_host, prefix in GHL_BOOKING_LINKS:
        if host == ghl_host and rest.startswith(prefix) and _GHL_ID_SEGMENT_RE.fullmatch(rest[len(prefix):]):
            return rest[len(prefix):].rstrip("/")
    return None


def _ids_json_calendar_ids() -> frozenset:
    """Every ghl.calendars.<name>.id in CALENDAR_IDS_PATH. Read only; cached
    on the file's size and mtime. A file that cannot be read gives no ids (so
    only a configured booking link passes), with a warning."""
    path = Path(CALENDAR_IDS_PATH)
    try:
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime_ns)
    except OSError as exc:
        logger.warning("GHL calendar ids: cannot read %s (%s)", path.name, type(exc).__name__)
        return frozenset()
    if _CALENDAR_IDS["key"] == key:
        return _CALENDAR_IDS["ids"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        calendars = ((data.get("ghl") or {}).get("calendars") or {}) if isinstance(data, dict) else {}
        ids = frozenset(c["id"] for c in calendars.values()
                        if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"])
    except Exception as exc:  # noqa: BLE001 - no ids is the narrower check
        logger.warning("GHL calendar ids: cannot parse %s (%s)", path.name, type(exc).__name__)
        return frozenset()
    _CALENDAR_IDS["ids"] = ids
    _CALENDAR_IDS["key"] = key
    return ids


def _ghl_booking_link(host: str, rest: str) -> bool:
    """A GHL booking-widget link (see _ghl_calendar_id) whose calendar id is
    one of ours: in config/ids.json, or the id of a configured booking link."""
    cal = _ghl_calendar_id(host, rest)
    if not cal:
        return False
    if cal in _ids_json_calendar_ids():
        return True
    for url in _configured_booking_urls():
        parts = _link_parts(url)
        if parts is not None and _ghl_calendar_id(*parts) == cal:
            return True
    return False


def _url_ok(name: str, value: str, engine_link: bool = False) -> bool:
    """The full link check, bound or not: a binding (already equal) only
    narrows it. ``engine_link``: the value equals the appointment's own call
    link, bound by appointment_bindings(); only then may a zoom_link be on
    meet.google.com."""
    parts = _link_parts(value)
    if parts is None:
        return False
    host, rest = parts
    if name == "booking_url":
        return value in _configured_booking_urls() or _ghl_booking_link(host, rest)
    if name == "loom_url":
        return value in _configured_loom_urls()
    if name == "zoom_link":
        # {zoom_link} is the call's join link: Zoom, or Google Meet (widget
        # bookings). Meet is its exact host only, never a subdomain.
        return (any(host == s or host.endswith("." + s) for s in ZOOM_HOST_SUFFIXES)
                or (engine_link and host in MEET_HOSTS))
    return False


# ---- times: the engine's own formatters decide
def _reference_week(weeks_later: int = 0) -> List[date]:
    """Seven consecutive days from FIXED_NOW (or ``weeks_later`` weeks on): an
    undated format shows the weekday only."""
    start = date(*ta.FIXED_NOW[:3]) + timedelta(weeks=weeks_later)
    return [start + timedelta(days=i) for i in range(7)]


def _both_seasons() -> List[date]:
    """The winter reference week and the summer one: a lead zone's label can
    differ between them (EST and EDT)."""
    return _reference_week() + _reference_week(SUMMER_WEEK_OFFSET)


def _clocks(value: str) -> List[Tuple[int, int]]:
    out = []  # type: List[Tuple[int, int]]
    for h, m in _CLOCK_RE.findall(value):
        h, m = int(h), int(m)
        if m > 59 or h > 23:
            continue
        for hour in sorted({h % 12, h % 12 + 12} if h <= 12 else {h}):
            if (hour, m) not in out:
                out.append((hour, m))
    return out


def _dates(value: str, dated: bool) -> List[date]:
    if not dated:
        return _reference_week()
    clock_spans = [m.span() for m in _CLOCK_RE.finditer(value)]
    days = set()
    for m in _NUMBER_RE.finditer(value):
        if any(a <= m.start() < b for a, b in clock_spans):
            continue
        n = int(m.group(0))
        if 1 <= n <= 31:
            days.add(n)
    # Last year to five years on, plus FIXED_NOW's year always: the catalogue
    # (and its tests) render at FIXED_NOW, whatever the real clock says.
    this_year = datetime.now(timezone.utc).year
    years = sorted(set(range(this_year - 1, this_year + 6)) | {ta.FIXED_NOW[0]})
    out = []  # type: List[date]
    for year in years:
        for month in range(1, 13):
            for day in days:
                try:
                    d = date(year, month, day)
                except ValueError:
                    continue
                # strftime is what the formatters write; a date whose month or
                # weekday name is not in the value cannot have produced it
                if d.strftime("%b") in value and d.strftime("%a") in value:
                    out.append(d)
    return out


def _instants(value: str, dated: bool, tz: Any = None, days: Optional[List[date]] = None) -> List[datetime]:
    """Candidate times for a value: the dates it names (``dated``) or the
    reference days, at each clock time it shows. Candidates only: a value is
    accepted when a formatter renders one of them to exactly the value."""
    from shared import slots as slot_rules

    zone = tz or slot_rules.TZ
    out = []  # type: List[datetime]
    for d in (days if days is not None else _dates(value, dated)):
        for hour, minute in _clocks(value):
            out.append(zone.localize(datetime(d.year, d.month, d.day, hour, minute)))
    return out


def _lead_zones() -> List[Any]:
    """Every zone the engine's time formatters can be handed for a lead, one
    per zone name, built once per process: for every pytz common zone name and
    every US/* and Canada/* name, the zone pytz loads for it (what
    booking._their_time uses) and the zone show_rate.lead_tz_of answers for it
    (which maps some names to one of slots.TZ_ALIASES' zones first); plus the
    TZ_ALIASES zones and template_approvals.VALUE_FORMAT_ZONES."""
    got = _ZONES["list"]
    if got is not None:
        return got
    import pytz
    from shared import slots as slot_rules
    from services.reply_engine import show_rate

    names = set(pytz.common_timezones)
    names.update(n for n in pytz.all_timezones if n.startswith(LEAD_ZONE_ALIAS_PREFIXES))
    names.update(ta.VALUE_FORMAT_ZONES)
    zones = {}  # type: Dict[str, Any]
    for z in slot_rules.TZ_ALIASES.values():
        zones.setdefault(z.zone, z)
    skipped = []  # type: List[str]
    for n in sorted(names):
        try:
            loaded = (pytz.timezone(n), show_rate.lead_tz_of({"lead_tz": n}))
        except Exception as exc:  # noqa: BLE001 - one bad zone name must not refuse every time
            skipped.append("%s (%s)" % (n, type(exc).__name__))
            continue
        for z in loaded:
            zone_name = getattr(z, "zone", None) if z is not None else None
            if zone_name:
                zones.setdefault(zone_name, z)
    if skipped:
        # Once per build, and the list is built once per process. A lead in a
        # skipped zone is refused (its time matches no zone), never let through.
        logger.warning("lead zones: skipped %d zone name(s) that failed to load: %s",
                       len(skipped), ", ".join(skipped))
    got = [zones[n] for n in sorted(zones)]
    _ZONES["list"] = got
    return got


def _zone_outputs(kind: str, dt: datetime) -> frozenset:
    """Every rendering of instant ``dt`` over the lead zones, cached per
    instant: "when_ct" is show_rate.fmt_when(dt, zone) (and with no zone),
    "lead_local_time" is format_slots([dt], tz=zone) without its weekday, as
    the catalogue defines it (template_approvals._booking_entries) and
    booking._their_time writes it."""
    key = (kind, dt.timestamp())
    got = _ZONE_OUTPUTS.get(key)
    if got is not None:
        return got
    from shared import slots as slot_rules
    from services.reply_engine import show_rate

    zones = _lead_zones()
    if kind == "when_ct":
        got = frozenset([show_rate.fmt_when(dt, None)] + [show_rate.fmt_when(dt, z) for z in zones])
    elif kind == "lead_local_time":
        got = frozenset(slot_rules.format_slots([dt], tz=z).split(" ", 1)[-1] for z in zones)
    else:
        raise ValueError("no zone table for %s" % kind)
    if len(_ZONE_OUTPUTS) >= ZONE_OUTPUTS_MAX:
        _ZONE_OUTPUTS.clear()
    _ZONE_OUTPUTS[key] = got
    return got


def _when_ok(value: str) -> bool:
    """show_rate.fmt_when(dt, zone) == value for a date and time the value
    names and a lead zone (or none)."""
    from services.reply_engine import show_rate

    for dt in _instants(value, True):
        base = show_rate.fmt_when(dt, None)
        if value == base:
            return True
        # Narrowing only: the lead's time is added to the zone-less rendering,
        # so an instant whose rendering does not start the value is skipped
        # without building its zone table. Acceptance is the membership test.
        if value.startswith(base) and value in _zone_outputs("when_ct", dt):
            return True
    return False


def _lead_local_ok(value: str, slot: Optional[str]) -> bool:
    """{lead_local_time} is the lead's own time for the {slot} beside it: the
    rendering, in some lead zone, of an instant whose Central rendering is
    ``slot``, in the winter or the summer reference week. With no slot beside
    it, the time cannot be checked, so it is refused."""
    from shared import slots as slot_rules

    if not isinstance(slot, str) or not slot or len(slot) > TIME_MAX_CHARS:
        return False
    for dt in _instants(slot, False, days=_both_seasons()):
        if slot_rules.format_slot(dt) == slot and value in _zone_outputs("lead_local_time", dt):
            return True
    return False


def _single(value: str, render: Callable[[datetime], str], dated: bool) -> bool:
    return any(render(dt) == value for dt in _instants(value, dated))


def _pair(value: str, piece: Callable[[datetime], str], whole: Callable[[List[datetime]], str], dated: bool) -> bool:
    """value == whole([a]) or whole([a, b]) for times a, b whose single
    rendering (piece) appears in value."""
    seen = {}  # type: Dict[str, datetime]
    for dt in _instants(value, dated):
        p = piece(dt)
        if p and p in value and p not in seen:
            seen[p] = dt
    dts = list(seen.values())
    for a in dts:
        if whole([a]) == value:
            return True
    for a, b in itertools.permutations(dts, 2):
        if whole([a, b]) == value:
            return True
    return False


def _time_ok(name: str, value: str, slot: Optional[str] = None) -> bool:
    """``slot``: the {slot} value in the same text, which {lead_local_time}
    must be the lead's time for."""
    from shared import slots as slot_rules

    if not value or len(value) > TIME_MAX_CHARS:
        return False
    if name == "asked_time":
        return _asked_time_ok(value)
    if name == "slot":
        return _single(value, slot_rules.format_slot, False)
    if name in ("slots", "alt_slots"):
        if _pair(value, slot_rules.format_slot, slot_rules.format_slots, False):
            return True
        if name == "alt_slots":
            from services.reply_engine import booking

            return _pair(value, booking._dated_slot, booking._dated_slots, True)
        return False
    if name in ("slot1", "slot2"):
        return _single(value, lambda dt: slot_rules.format_slots([dt]), False)
    if name == "lead_local_time":
        return _lead_local_ok(value, slot)
    if name == "when_ct":
        return _when_ok(value)
    if name == "time_ct":
        from services.reply_engine import show_rate

        return _single(value, show_rate.fmt_time_only, False)
    return False


def _asked_time_ok(value: str) -> bool:
    """{asked_time} is the lead's proposed time written back in the zone the
    lead named, with that zone's label (slots.format_asked_time): 'Thu
    11:00am ET', or the dated form 'Tue Jan 15 2:00pm PT'; CT when the lead
    named Central or no zone. Only the zones slots.TZ_ALIASES answers, so a
    value with no zone ('Thu 11:00am') or another label ('EST') is refused."""
    from shared import slots as slot_rules

    zones = dict((z.zone, z) for z in slot_rules.TZ_ALIASES.values())
    for name in sorted(zones):
        zone = zones[name]
        for dated in (False, True):
            if any(slot_rules.format_asked_time(dt, zone, dated=dated) == value
                   for dt in _instants(value, dated, tz=zone)):
                return True
    return False


class _EngineTime(str):
    """A time value appointment_bindings() computed with the engine's own
    formatter for one appointment. Bound to its placeholder, equality with it
    is the whole check."""
    __slots__ = ()


class _EngineLink(str):
    """The appointment's own call link, as appointment_bindings() read it.
    Bound to {zoom_link}, it still has to pass the link grammar, and only it
    may be a meet.google.com link."""
    __slots__ = ()


def appointment_bindings(appointment: Dict[str, Any], start: datetime) -> Dict[str, str]:
    """{"when_ct", "time_ct"}: what show_rate.render and no_show.render write
    for this appointment at ``start``, computed by their own formatters
    (show_rate.fmt_when with show_rate.lead_tz_of(appointment), and
    show_rate.fmt_time_only). Pass them in ``bindings`` to
    appointment_touch_verdict (merged with any others): the text must then
    carry exactly these values, for any lead zone the formatter accepts,
    including one outside _lead_zones(). Plus "zoom_link", the appointment's
    own call link (show_rate.call_link_of) when it has one: the only way a
    meet.google.com link passes. {} when they cannot be computed (the
    unbound checks still apply); never raises."""
    try:
        from services.reply_engine import show_rate

        lead_tz = show_rate.lead_tz_of(appointment or {})
        out = {"when_ct": _EngineTime(show_rate.fmt_when(start, lead_tz)),
               "time_ct": _EngineTime(show_rate.fmt_time_only(start))}  # type: Dict[str, str]
        link = show_rate.call_link_of(appointment or {})
        if link:
            out["zoom_link"] = _EngineLink(link)
        return out
    except Exception as exc:  # noqa: BLE001 - no binding is the unbound check, never a wider one
        logger.warning("appointment_bindings failed: %s", type(exc).__name__)
        return {}


def _value_ok(name: str, value: str, captured: Dict[str, str], bindings: Dict[str, str]) -> bool:
    """One captured placeholder value, checked for its type. A binding only
    narrows: the value must equal it AND pass the type check, except a time
    value appointment_bindings() computed (see the module docstring)."""
    if not isinstance(value, str) or not _nfkc_stable(value) or not _clean_chars(value, allow_newline=False):
        return False
    bound = name in bindings
    if bound and value != bindings[name]:
        return False
    if name in NAME_PLACEHOLDERS:
        if name == "referral_first_name":
            if not _name_ok(value, max_words=1) or value.lower().rstrip(".") in ROLE_WORDS:
                return False
            ref = captured.get("referral_name", bindings.get("referral_name"))
            return ref is None or value == ref.split(" ", 1)[0]
        if not _name_ok(value):
            return False
        if name == "referral_name" and value.split(" ", 1)[0].lower().rstrip(".") in ROLE_WORDS:
            return False
        return True
    if name in TEXT_PLACEHOLDERS:
        return _free_text_ok(value, company=(name == "company"))
    if name in TIME_VALUE_PLACEHOLDERS:
        if bound and isinstance(bindings[name], _EngineTime):
            return True           # equal to the formatter's own output for this appointment
        slot = captured.get("slot") if name == "lead_local_time" else None
        ck = (name, value, slot)
        if ck not in _VALUE_CACHE:
            if len(_VALUE_CACHE) >= _VALUE_CACHE_MAX:
                _VALUE_CACHE.clear()
            _VALUE_CACHE[ck] = bool(_time_ok(name, value, slot=slot))
        return _VALUE_CACHE[ck]
    if name in URL_PLACEHOLDERS:
        return _url_ok(name, value, engine_link=bound and isinstance(bindings[name], _EngineLink))
    return False  # a placeholder this module has no type for never conforms


# ------------------------------------------------------------ conformance
def _part_placeholder(part_id: str) -> Optional[str]:
    for prefix, ph in PART_PLACEHOLDERS:
        if part_id == prefix or part_id.startswith(prefix):
            return ph
    return None


def _class_for(name: str) -> str:
    if name in NAME_PLACEHOLDERS:
        return _NAME_CLASS
    if name in TEXT_PLACEHOLDERS:
        return _TEXT_CLASS
    if name in TIME_VALUE_PLACEHOLDERS:
        return _TIME_CLASS
    if name in URL_PLACEHOLDERS:
        return _URL_CLASS
    return r"(?!)"


def _research_capture_ok(value: Any) -> bool:
    """The shape of a researched day 2 line as captured from the body: text,
    1 to RESEARCH_LINE_MAX_CHARS characters, one line, no braces, no leading
    or trailing space, NFKC-stable, no control, format or blank-rendering
    characters. What it says is research_rules.validate's to judge."""
    if not isinstance(value, str) or not value or len(value) > RESEARCH_LINE_MAX_CHARS:
        return False
    if "\n" in value or "{" in value or "}" in value or value != value.strip():
        return False
    return _nfkc_stable(value) and _clean_chars(value, allow_newline=False)


_PATTERN_CACHE = {}  # type: Dict[Any, Any]


def _pattern(text: str, fallbacks: Optional[Dict[str, set]] = None,
             captures: frozenset = frozenset()) -> "re.Pattern":
    """The template text as an anchored regex: literals escaped, each
    placeholder a bounded run of the characters its type can hold (or one of
    its approved fallback wordings), a repeated placeholder the same value as
    its first use. A placeholder in ``captures`` (the researched day 2 line)
    is _RESEARCH_CLASS and never takes a fallback wording."""
    names = set(m.group(1) for m in ta._PLACEHOLDER_RE.finditer(text))
    fb = dict((n, tuple(sorted(v, key=lambda x: (-len(x), x)))) for n, v in (fallbacks or {}).items()
              if n in names and v and n not in captures)
    captures = frozenset(c for c in captures if c in names)
    ck = (text, tuple(sorted(fb.items())), tuple(sorted(captures)))
    cached = _PATTERN_CACHE.get(ck)
    if cached is not None:
        return cached
    out = []  # type: List[str]
    seen = set()  # type: set
    pos = 0
    for m in ta._PLACEHOLDER_RE.finditer(text):
        out.append(re.escape(text[pos:m.start()]))
        name = m.group(1)
        if name in seen:
            out.append("(?P=%s)" % name)
        else:
            seen.add(name)
            alts = "".join(re.escape(v) + "|" for v in fb.get(name, ()))
            out.append("(?P<%s>%s%s)" % (name, alts, _RESEARCH_CLASS if name in captures else _class_for(name)))
        pos = m.end()
    out.append(re.escape(text[pos:]))
    pat = re.compile("".join(out))
    if len(_PATTERN_CACHE) > 2048:
        _PATTERN_CACHE.clear()
    _PATTERN_CACHE[ck] = pat
    return pat


def _loose_pattern(text: str) -> "re.Pattern":
    """Any single line per placeholder: only used between two catalogue texts
    (below), never on a body."""
    out = []  # type: List[str]
    seen = set()  # type: set
    pos = 0
    for m in ta._PLACEHOLDER_RE.finditer(text):
        out.append(re.escape(text[pos:m.start()]))
        name = m.group(1)
        out.append("(?P=%s)" % name if name in seen else "(?P<%s>[^\\n]+?)" % name)
        seen.add(name)
        pos = m.end()
    out.append(re.escape(text[pos:]))
    return re.compile("".join(out))


_FALLBACK_CACHE = {}  # type: Dict[Tuple[Any, ...], Dict[str, set]]


def _fallback_values(entry: Dict[str, Any], texts: List[str], filled: frozenset = frozenset()) -> Dict[str, set]:
    """The literal wording each placeholder takes in the entry's own variants
    ("there" for {first_name}, "your business" for {company}), found by lining
    each catalogue text up against the others. Lorenzo approved these words
    as part of the variant, so a body may use them in that placeholder's
    place even when the variant it came from differs elsewhere (no first name
    AND no free slot). ``filled`` (the spliced-line placeholders a part is
    given for) is part of the cache key: it changes ``texts``."""
    ck = (entry.get("id"), entry.get("sha256"), filled)
    cached = _FALLBACK_CACHE.get(ck)
    if cached is not None:
        return cached
    out = {}  # type: Dict[str, set]
    norm = [ta.normalise(t) for t in texts]
    for a in norm:
        pat = _loose_pattern(a)
        for b in norm:
            if a is b:
                continue
            m = pat.fullmatch(b)
            if m is None:
                continue
            for name, value in m.groupdict().items():
                if value is not None and "{" not in value and "}" not in value:
                    out.setdefault(name, set()).add(value)
    if len(_FALLBACK_CACHE) > 1024:
        _FALLBACK_CACHE.clear()
    _FALLBACK_CACHE[ck] = out
    return out


def _match_values(template_text: str, text: str, bindings: Dict[str, str],
                  fallbacks: Optional[Dict[str, set]] = None,
                  captures: frozenset = frozenset()) -> Optional[Dict[str, str]]:
    """The placeholder values of ``text`` read against ``template_text``, or
    None when it does not match or a value fails its check. A placeholder in
    ``captures`` (the researched day 2 line) must pass _research_capture_ok
    and equal its binding when it has one; the caller checks the rest."""
    fb = dict((n, v) for n, v in (fallbacks or {}).items() if n not in captures)
    m = _pattern(ta.normalise(template_text), fb, captures).fullmatch(ta.normalise(text))
    if m is None:
        return None
    captured = dict((k, v) for k, v in m.groupdict().items() if v is not None)
    for name, value in captured.items():
        if name in captures:
            if not _research_capture_ok(value) or (name in bindings and value != bindings[name]):
                return None
            continue
        if name not in bindings and value in fb.get(name, ()):
            # Approved variant wording for this placeholder. The referral's
            # first name only when the referral name is a fallback too.
            if name != "referral_first_name" or captured.get("referral_name") in (None,) + tuple(
                    fb.get("referral_name", ())):
                continue
        if not _value_ok(name, value, captured, bindings):
            return None
    return captured


def _matches(template_text: str, text: str, bindings: Dict[str, str],
             fallbacks: Optional[Dict[str, set]] = None) -> bool:
    return _match_values(template_text, text, bindings, fallbacks) is not None


def _split_subject(text: str) -> Tuple[Optional[str], str]:
    """A show-rate / no-show catalogue text is "Subject: X\\n\\nbody"."""
    if text.startswith(SUBJECT_PREFIX):
        head, sep, rest = text.partition("\n\n")
        if sep and "\n" not in head:
            return head[len(SUBJECT_PREFIX):], rest
    return None, text


def _subject_patterns(entry: Dict[str, Any]) -> List[str]:
    """Each line of the 'subject' variant is "<label>: <subject template>"."""
    out = []  # type: List[str]
    for v in entry.get("variants") or []:
        if v.get("name") != SUBJECT_VARIANT:
            continue
        for line in (v.get("text") or "").split("\n"):
            if ": " in line:
                out.append(line.split(": ", 1)[1])
    return out


def _family_texts(index: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    """(text, placeholder) for every part the catalogue knows, longest first,
    so a variant rendered with an example part in place can take any part."""
    out = []  # type: List[Tuple[str, str]]
    for tid, e in index.items():
        ph = _part_placeholder(tid)
        # the research rules are prose, never a line spliced into a body
        if ph and e.get("kind") != ta.RESEARCH_RULES_KIND and e.get("extractable") and e.get("text"):
            out.append((e["text"], ph))
    return sorted(out, key=lambda t: len(t[0]), reverse=True)


def _candidate_texts(index: Dict[str, Dict[str, Any]], entry: Dict[str, Any], filled: frozenset) -> List[str]:
    """The texts a body may be: the entry's text and every variant but
    value_formats, subject and the never-auto ones. Where a variant shows an
    example spliced line in place and a part is given for that placeholder
    (``filled``), the example is put back as the placeholder, so the variant
    takes the given part."""
    families = _family_texts(index) if filled else []
    out = [entry["text"]]
    for v in entry.get("variants") or []:
        if v.get("name") in (ta.VALUE_FORMATS_VARIANT, SUBJECT_VARIANT) or v.get("name") in NEVER_AUTO_VARIANTS:
            continue
        text = v.get("text") or ""
        for example, ph in families:
            if ph in filled:
                text = text.replace(example, "{%s}" % ph)
        out.append(text)
    return out


def fallback_wordings(index: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, List[str]]:
    """Placeholder -> every fixed wording an approvable entry's own variants
    put in its place, over the whole catalogue, computed as a conformance
    check does (with and without the spliced lines given as parts). These
    are what the check accepts in an unbound placeholder without its type
    check; a bound placeholder must still equal its binding."""
    idx = index if index is not None else _index()
    out = {}  # type: Dict[str, set]
    for tid in sorted(idx):
        e = idx[tid]
        if not (e.get("approvable") and e.get("extractable") and e.get("text")):
            continue
        if e.get("kind") == ta.RESEARCH_RULES_KIND:
            continue              # rules prose, not an email
        spliced = frozenset(ph for ph in PART_FILLED if "{%s}" % ph in e["text"])
        for filled in ((frozenset(), spliced) if spliced else (frozenset(),)):
            texts = _candidate_texts(idx, e, filled) + _subject_patterns(e)
            for ph, values in _fallback_values(e, texts, filled).items():
                out.setdefault(ph, set()).update(values)
    return dict((ph, sorted(values)) for ph, values in sorted(out.items()))


def _conforms(index: Dict[str, Dict[str, Any]], template_id: str, body: str, subject: Optional[str],
              parts: Sequence[str], bindings: Optional[Dict[str, str]] = None,
              research_lines: Optional[List[str]] = None) -> bool:
    """``research_lines``: only touch_verdict's research check passes a list.
    With the research rules part among ``parts`` and a list, {research_line}
    is captured (_RESEARCH_CLASS) and every captured line of a matching text
    is appended to the list for the caller to check; without a list, a body
    with that part never conforms."""
    bindings = dict(bindings or {})
    entry = index.get(template_id)
    if not entry or not entry.get("extractable") or not entry.get("text"):
        return False
    if len(body) > MAX_BODY_CHARS or not _nfkc_stable(body) or not _clean_chars(body, allow_newline=True):
        return False
    if subject is not None and (len(subject) > MAX_SUBJECT_CHARS or not _nfkc_stable(subject)
                                or not _clean_chars(subject, allow_newline=False)):
        return False
    fills = {}  # type: Dict[str, str]
    captures = frozenset()  # type: frozenset
    for pid in parts or ():
        pe = index.get(pid)
        ph = _part_placeholder(pid)
        if pid == ta.RESEARCH_RULES_ID:
            # the researched line: captured, checked by the caller
            if (research_lines is None or template_id not in RESEARCH_RULES_MAINS or not pe
                    or not pe.get("approvable") or ph is None or ph in fills or ph in captures):
                return False
            captures = frozenset([ph])
            continue
        if not pe or not pe.get("extractable") or not pe.get("text") or ph is None or ph in fills or ph in captures:
            return False
        fills[ph] = pe["text"]
    filled = frozenset(fills) | captures
    candidates = _candidate_texts(index, entry, filled)
    subject_patterns = _subject_patterns(entry)
    fallbacks = _fallback_values(entry, candidates + subject_patterns, filled)
    subject_needed = subject is not None
    matched = False
    for cand in candidates:
        for ph, fill_text in fills.items():
            cand = cand.replace("{%s}" % ph, fill_text)
        # a spliced line nobody supplied (the LLM research line) never conforms
        if any("{%s}" % ph in cand for ph in PART_FILLED if ph not in captures):
            continue
        # a researched touch carries its line: a text without the slot is not it
        if any("{%s}" % ph not in cand for ph in captures):
            continue
        cand_subject, cand_body = _split_subject(cand)
        if cand_subject is not None:
            if subject is not None:
                got = _match_values(cand, "%s%s\n\n%s" % (SUBJECT_PREFIX, subject, body), bindings, fallbacks,
                                    captures)
            else:
                got = _match_values(cand_body, body, bindings, fallbacks, captures)
        else:
            got = _match_values(cand, body, bindings, fallbacks, captures)
            if got is not None and subject_needed and not any(
                    _matches(p, subject, bindings, fallbacks) for p in subject_patterns):
                got = None
        if got is None:
            continue
        if not captures:
            return True
        research_lines.extend(got[ph] for ph in sorted(captures))
        matched = True
    return matched


def conforms(template_id: str, body: str, subject: Optional[str] = None, parts: Sequence[str] = (),
             bindings: Optional[Dict[str, str]] = None) -> bool:
    """True when ``body`` (and ``subject`` when given) is the template's text,
    or one of its variants other than confirmed_time, with only its
    placeholders filled, each by a value of its type (and equal to its
    binding when one is given). Parts are substituted into their placeholder
    first. Any error is False."""
    try:
        return _conforms(_index(), template_id, body or "", subject, list(parts or ()), bindings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("conforms(%s) failed closed: %s", template_id, type(exc).__name__)
        return False


# ------------------------------------------------------------- the checks
def _fail_unless_kill_switch_off_and_parity(key: Tuple[Any, ...]) -> None:
    if ta.kill_switch_on():
        raise _Fail("kill_switch", "template auto-send is switched off")
    ps = _parity_ok_or_alert(key)
    if ps.get("status") == PARITY_NOT_READY:
        raise _Fail("registry_error", "the catalogue is not built while an engine module is still importing")
    if ps.get("status") != PARITY_OK:
        raise _Fail("parity_failed", "parity=%s" % ps.get("status"))


def _check_ids(index: Dict[str, Dict[str, Any]], kind: Optional[str], template_id: str, parts: Sequence[str],
               statuses: Dict[str, str]) -> None:
    approvals = ta.load_approvals()
    ids = [template_id] + list(parts)
    for tid in ids:
        statuses[tid] = ta.status(tid, entries=index, approvals=approvals)
    for n, tid in enumerate(ids):
        entry = index.get(tid)
        if entry is None:
            raise _Fail("unknown_id", "%s is not in the catalogue" % tid)
        if not entry.get("approvable"):
            raise _Fail("not_approvable", "%s cannot be approved" % tid)
        if kind is not None:
            if n == 0:
                want = MAIN_KIND.get(kind)
            elif tid == ta.RESEARCH_RULES_ID:
                # the research rules are a part of cadence.d2 only
                want = (ta.RESEARCH_RULES_KIND if kind in RESEARCH_RULES_KINDS and template_id in RESEARCH_RULES_MAINS
                        else None)
            else:
                want = PART_KIND.get(kind)
            if want is None or entry.get("kind") != want:
                raise _Fail("unknown_id", "%s is not a %s template" % (tid, "main" if n == 0 else "part"))
        st = statuses[tid]
        if st != ta.STATUS_APPROVED:
            raise _Fail(st if st in REASONS else "unapproved", "%s is %s" % (tid, st))


def _check_stamp(index: Dict[str, Dict[str, Any]], template_id: str, stamped: Optional[str],
                 stamped_parts: Dict[str, Optional[str]]) -> None:
    if not stamped or stamped != _hash_of(index, template_id):
        raise _Fail("stale_render", "%s was rendered from other text" % template_id)
    for pid, h in stamped_parts.items():
        if not h or h != _hash_of(index, pid):
            raise _Fail("stale_render", "%s was rendered from other text" % pid)


def _check_classification(classification: Any) -> None:
    from services.reply_engine import classify, models

    if classification is None:
        raise _Fail("classification", "no classification")
    label = getattr(classification, "label", None)
    if label not in models.POSITIVE_LABELS:
        raise _Fail("classification", "label %s" % label)
    confidence = getattr(classification, "confidence", None)
    if confidence is None or float(confidence) < float(classify.CONFIDENCE_FLOOR):
        raise _Fail("classification", "confidence %s below %s" % (confidence, classify.CONFIDENCE_FLOOR))
    if getattr(classification, "method", None) == "fallback":
        raise _Fail("classification", "fallback classifier")


_SUBJECT_PROBLEMS_IGNORED = ("must end with the signature line", "missing booking link", "too long", "empty body")


def _subject_problems(subject: Optional[str], campaign_key: Optional[str], allow_terms: Any) -> List[str]:
    """The body's copy rules on the subject line: banned words, figures and
    "!" through draft.validate_draft, plus no link or address at all."""
    if subject is None:
        return []
    from services.reply_engine import draft as draft_mod

    raw = draft_mod.validate_draft(subject, campaign_key=campaign_key,
                                   allow_terms=[a for a in (allow_terms or []) if a] or None)
    out = ["subject: %s" % p for p in raw if not str(p).startswith(_SUBJECT_PROBLEMS_IGNORED)]
    if _SUBJECT_LINK_RE.search(subject):
        out.append("subject: a link or address")
    return out


def _parts_of(obj: Any) -> Dict[str, Optional[str]]:
    raw = getattr(obj, "template_parts", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _verdict(run: Callable[[Dict[str, Any]], None]) -> Verdict:
    """Run the checks. ``run`` fills st["template_id"], st["ids"] and
    st["statuses"] as it reads them, INSIDE the try, so a raising attribute
    is registry_error like any other exception."""
    st = {"template_id": None, "ids": [], "statuses": {}}  # type: Dict[str, Any]
    try:
        run(st)
        return Verdict(True, "ok", st["template_id"], list(st["ids"]), dict(st["statuses"]))
    except _Fail as f:
        return Verdict(False, f.reason, st["template_id"], list(st["ids"]), dict(st["statuses"]), f.detail)
    except Exception as exc:  # noqa: BLE001 - any doubt fails closed
        logger.warning("template gate failed closed for %s: %s: %s", st["template_id"], type(exc).__name__, exc)
        return Verdict(False, "registry_error", st["template_id"], list(st["ids"]), dict(st["statuses"]),
                       type(exc).__name__)


def _read_ids(st: Dict[str, Any], obj: Any) -> Tuple[Optional[str], Dict[str, Optional[str]], List[str]]:
    if obj is None:
        raise ValueError("nothing to judge")
    template_id = getattr(obj, "template_id", None)
    stamped_parts = _parts_of(obj)
    parts = list(stamped_parts)
    st["template_id"] = template_id
    st["ids"] = ([template_id] if template_id else []) + parts
    return template_id, stamped_parts, parts


def ids_verdict(template_id: Optional[str], parts: Sequence[str] = ()) -> Verdict:
    """Kill switch, parity and statuses only: the pre-check before anything is
    rendered (the draft polish decision, cadence D1's veto ping)."""
    def run(st: Dict[str, Any]) -> None:
        clean = [p for p in (parts or ()) if p]
        st["template_id"] = template_id
        st["ids"] = ([template_id] if template_id else []) + clean
        key = ta._source_key()
        _fail_unless_kill_switch_off_and_parity(key)
        if not template_id:
            raise _Fail("no_template", "no template id")
        _check_ids(_index(key), None, template_id, clean, st["statuses"])
    return _verdict(run)


def draft_verdict(draft: Any, *, kind: str, campaign_key: Optional[str] = None, allow_terms: Any = None,
                  classification: Any = None, requested: Any = None,
                  bindings: Optional[Dict[str, str]] = None) -> Verdict:
    """The verdict for a first reply or a booking card (kind "first_reply" or
    "booking"), in the gate order above."""
    def run(st: Dict[str, Any]) -> None:
        if kind not in DRAFT_KINDS:
            raise ValueError("draft_verdict kind must be one of %s" % (DRAFT_KINDS,))
        template_id, stamped_parts, parts = _read_ids(st, draft)
        model = getattr(draft, "model", None)
        stamped = getattr(draft, "template_hash", None)
        body = getattr(draft, "body_text", None) or ""
        subject = getattr(draft, "subject", None)
        problems = list(getattr(draft, "problems", None) or [])
        link = getattr(draft, "booking_link", None)
        key = ta._source_key()
        _fail_unless_kill_switch_off_and_parity(key)
        index = _index(key)
        if model != "template":
            raise _Fail("not_template_render", "the body is not the template render (model %s)" % model)
        if not template_id:
            raise _Fail("no_template", "no template id")
        _check_ids(index, kind, template_id, parts, st["statuses"])
        _check_stamp(index, template_id, stamped, stamped_parts)
        if kind in CLASSIFIED_KINDS:
            _check_classification(classification)
        if requested is not None:
            raise _Fail("requested_override", "the lead asked for a time the slot rules refuse")
        if not problems:
            from services.reply_engine import draft as draft_mod

            # A booking confirmation carries the booking link as a field but not
            # in its body; conformance (step 9) already fixes where a link goes.
            problems = list(draft_mod.validate_draft(body, booking_link=link if kind == "first_reply" else None,
                                                     campaign_key=campaign_key,
                                                     allow_terms=list(allow_terms) if allow_terms else None))
        problems += _subject_problems(subject, campaign_key, allow_terms)
        if problems:
            raise _Fail("copy_gate", "; ".join(str(p) for p in problems))
        if not _conforms(index, template_id, body, subject, parts, bindings):
            raise _Fail("nonconforming", "the text is not an auto-sendable form of the approved template with "
                                         "valid placeholder values")
    return _verdict(run)


# ------------------------------------------------ the researched day 2 line
def research_rules_sha(module: Any = None) -> str:
    """The rules_sha a research_rules.ResearchVerdict must carry: what the
    rules module reports for its own rules NOW. Raises when it cannot say.

    Contract for services/reply_engine/research_rules.py (section 1):

    - with a callable ``rules_sha()``, that is the answer: a non-empty str,
      and validate() must put exactly it in ResearchVerdict.rules_sha;
    - without one, the answer is
      ``template_approvals.research_rules_sha(RULES_TEXT, RULES_VERSION)``:
      sha256 hex of normalise(RULES_TEXT.rstrip("\\n") + "\\n\\nRULES_VERSION: " +
      str(RULES_VERSION)), which is also the catalogue hash of
      cadence.d2.research_rules that Lorenzo approves.

    ``module`` defaults to the module imported by name now."""
    mod = module
    if mod is None:
        mod, why, _absent = ta.load_research_rules()
        if mod is None:
            raise RuntimeError(why or ta.RESEARCH_RULES_ABSENT)
    fn = getattr(mod, "rules_sha", None)
    if fn is not None:
        if not callable(fn):
            raise TypeError("research_rules.rules_sha is not callable")
        got = fn()
    else:
        text, version, why = ta.research_rules_parts(mod)
        if why:
            raise RuntimeError(why)
        got = ta.research_rules_sha(text, version)
    if not isinstance(got, str) or not got:
        raise ValueError("research_rules.rules_sha() gave no sha")
    return got


def _research_context(bindings: Optional[Dict[str, str]]) -> Dict[str, str]:
    """RESEARCH_CONTEXT_KEYS from the bindings, each non-empty text;
    offer_branch one of RESEARCH_OFFER_BRANCHES."""
    b = bindings or {}
    missing = [k for k in RESEARCH_CONTEXT_KEYS if not isinstance(b.get(k), str) or not b[k].strip()]
    if missing:
        raise _Fail("research_context_missing", "no %s in the bindings" % ", ".join(missing))
    context = dict((k, str(b[k])) for k in RESEARCH_CONTEXT_KEYS)
    if context["offer_branch"] not in RESEARCH_OFFER_BRANCHES:
        raise _Fail("research_context_missing", "offer_branch is not one of %s" % ", ".join(RESEARCH_OFFER_BRANCHES))
    return context


def _check_research(index: Dict[str, Dict[str, Any]], template_id: str, touch: Any, body: str,
                    subject: Optional[str], parts: Sequence[str], bindings: Optional[Dict[str, str]]) -> None:
    """Step 9 for a researched day 2 touch (see the module docstring). The
    ids and the stamp of the rules part were checked by steps 4 and 5."""
    meta = getattr(touch, "meta", None)
    if not isinstance(meta, dict):
        raise _Fail("research_line_missing", "the touch carries no meta")
    line = meta.get("research_line")
    if not isinstance(line, str) or not ta.normalise(line):
        raise _Fail("research_line_missing", "touch.meta has no research_line")
    evidence = meta.get("research_evidence")
    if not isinstance(evidence, dict):
        raise _Fail("research_evidence_missing", "touch.meta has no research_evidence dict")
    context = _research_context(bindings)
    captured = []  # type: List[str]
    if not _conforms(index, template_id, body, subject, parts, bindings, research_lines=captured):
        raise _Fail("nonconforming", "the text is not the approved day 2 template with valid placeholder values "
                                     "and one research line of at most %d characters" % RESEARCH_LINE_MAX_CHARS)
    want = ta.normalise(line)
    if want not in captured:
        raise _Fail("research_line_mismatch", "the line in the body is not touch.meta's research_line")
    mod, why, _absent = ta.load_research_rules()
    if mod is None:
        raise _Fail("research_rules_unavailable", why or ta.RESEARCH_RULES_ABSENT)
    text, version, why = ta.research_rules_parts(mod)
    if why:
        raise _Fail("research_rules_unavailable", why)
    if ta.research_rules_sha(text, version) != _hash_of(index, ta.RESEARCH_RULES_ID):
        raise _Fail("changed_since_approval", "%s changed after the catalogue was read" % ta.RESEARCH_RULES_ID)
    try:
        expected = research_rules_sha(mod)
    except Exception as exc:  # noqa: BLE001 - no expected sha, no send
        raise _Fail("research_rules_unavailable", "the rules sha could not be computed (%s)" % type(exc).__name__)
    try:
        evidence_copy = copy_mod.deepcopy(evidence)
    except Exception as exc:  # noqa: BLE001
        raise _Fail("research_evidence_missing", "research_evidence cannot be copied (%s)" % type(exc).__name__)
    try:
        result = mod.validate(want, evidence_copy, dict(context))
    except Exception as exc:  # noqa: BLE001 - a validator that raised has passed nothing
        logger.warning("research_rules.validate raised for %s: %s", template_id, type(exc).__name__)
        raise _Fail("research_rules_error", "validate raised %s: %s" % (type(exc).__name__, exc))
    try:
        ok, vline = getattr(result, "ok"), getattr(result, "line")
        reasons, vsha = getattr(result, "reasons"), getattr(result, "rules_sha")
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_rules.validate gave no verdict for %s: %s", template_id, type(result).__name__)
        raise _Fail("research_rules_error", "validate returned %s, not a ResearchVerdict (%s)"
                    % (type(result).__name__, type(exc).__name__))
    if not isinstance(vsha, str) or vsha != expected:
        raise _Fail("research_rules_sha_mismatch", "the verdict was reached under other rules than the module's own")
    if ok is not True:
        try:
            why_not = "; ".join(str(r) for r in reasons) if isinstance(reasons, (list, tuple)) else str(reasons)
        except Exception:  # noqa: BLE001
            why_not = ""
        raise _Fail("research_rules_failed", why_not or "no reasons given")
    if not isinstance(vline, str) or ta.normalise(vline) != want:
        raise _Fail("research_line_mismatch", "the validator judged another line than the one in the body")


def _research_copy_problems(touch: Any, body: str) -> List[str]:
    """cadence.copy_problems on the body itself, for a researched touch: the
    line is the lead's own, so its copy check is not taken on trust from
    touch.problems."""
    from services.reply_engine import cadence

    return list(cadence.copy_problems(body, allow=[a for a in (getattr(touch, "allow_terms", None) or []) if a],
                                      campaign_key=getattr(touch, "campaign_key", None)))


def touch_verdict(touch: Any, bindings: Optional[Dict[str, str]] = None) -> Verdict:
    """The verdict for a cadence.Touch: the tick's copy gate already ran, the
    gate re-asserts touch.problems is empty and checks the subject. A
    researched day 2 touch (parts [cadence.d2.research_rules]) also gets the
    copy gate run here on its body and the research checks at step 9."""
    def run(st: Dict[str, Any]) -> None:
        template_id, stamped_parts, parts = _read_ids(st, touch)
        stamped = getattr(touch, "template_hash", None)
        body = getattr(touch, "body_text", None) or ""
        subject = getattr(touch, "subject", None)
        key = ta._source_key()
        _fail_unless_kill_switch_off_and_parity(key)
        index = _index(key)
        if not template_id:
            raise _Fail("no_template", "no template id")
        _check_ids(index, "cadence", template_id, parts, st["statuses"])
        _check_stamp(index, template_id, stamped, stamped_parts)
        researched = ta.RESEARCH_RULES_ID in parts
        problems = list(getattr(touch, "problems", None) or [])
        if researched:
            problems += [p for p in _research_copy_problems(touch, body) if p not in problems]
        problems += _subject_problems(subject, getattr(touch, "campaign_key", None),
                                      getattr(touch, "allow_terms", None))
        if problems:
            raise _Fail("copy_gate", "; ".join(str(p) for p in problems))
        if researched:
            _check_research(index, template_id, touch, body, subject, parts, bindings)
            return
        if not _conforms(index, template_id, body, subject, parts, bindings):
            raise _Fail("nonconforming", "the text is not the approved template with valid placeholder values")
    return _verdict(run)


def appointment_touch_verdict(touch: Any, *, kind: str, allow_terms: Any = None,
                              campaign_key: Optional[str] = None,
                              bindings: Optional[Dict[str, str]] = None) -> Verdict:
    """The verdict for a show_rate.Touch (kind "show_rate" or "no_show").
    Copy gate: cadence.shared_problems, minus "unsigned" for an SMS, plus
    the subject check. Not copy_problems: the outbound pre-reads say
    "guarantee". ``allow_terms`` and ``campaign_key`` default to touch.meta's."""
    def run(st: Dict[str, Any]) -> None:
        if kind not in APPOINTMENT_KINDS:
            raise ValueError("appointment_touch_verdict kind must be one of %s" % (APPOINTMENT_KINDS,))
        template_id, stamped_parts, parts = _read_ids(st, touch)
        stamped = getattr(touch, "template_hash", None)
        meta = getattr(touch, "meta", None) or {}
        allow = allow_terms if allow_terms is not None else meta.get("allow_terms")
        ckey = campaign_key if campaign_key is not None else meta.get("campaign_key")
        body = getattr(touch, "body", None) or ""
        subject = getattr(touch, "subject", None)
        channel = getattr(touch, "channel", None)
        key = ta._source_key()
        _fail_unless_kill_switch_off_and_parity(key)
        index = _index(key)
        if not template_id:
            raise _Fail("no_template", "no template id")
        _check_ids(index, kind, template_id, parts, st["statuses"])
        _check_stamp(index, template_id, stamped, stamped_parts)
        from services.reply_engine import cadence

        problems = list(cadence.shared_problems(body, allow=[a for a in (allow or []) if a], campaign_key=ckey))
        if channel == "sms":
            problems = [p for p in problems if p != "unsigned"]
        problems += _subject_problems(subject, ckey, allow)
        if problems:
            raise _Fail("copy_gate", "; ".join(str(p) for p in problems))
        if channel == "sms":
            from services.reply_engine import show_rate

            # render() cuts an SMS at SMS_MAX_LEN. A cut inside the last
            # placeholder would leave a shorter value, so a body at the limit
            # is treated as cut.
            if len(body) >= int(show_rate.SMS_MAX_LEN):
                raise _Fail("nonconforming", "the SMS is at the length limit and may have been cut")
        if not _conforms(index, template_id, body, subject, parts, bindings):
            raise _Fail("nonconforming", "the text is not the approved template with valid placeholder values")
    return _verdict(run)


def resolve_combo_id(kind: str, template_key: str, niche: str, offer: str, repeat: bool = False) -> Optional[str]:
    """The show_rate / no_show catalogue id that covers (niche, offer), from
    the entries' ``applies_to``. ``repeat`` picks the second-no-show copy.
    None when no entry (or more than one) covers it."""
    try:
        if kind not in APPOINTMENT_KINDS or not template_key:
            return None
        base = "%s.%s%s" % (kind, template_key, ".repeat" if repeat else "")
        niche = (niche or "").strip().lower()
        offer = (offer or "").strip().lower()
        index = _index()
        combo = [niche, offer]
        found = []  # type: List[str]
        for tid in (base, "%s.%s" % (base, niche), "%s.%s" % (base, offer), "%s.%s_%s" % (base, niche, offer)):
            e = index.get(tid)
            if e is None or e.get("kind") != kind:
                continue
            if combo in [list(c) for c in (e.get("applies_to") or [])] and tid not in found:
                found.append(tid)
        return found[0] if len(found) == 1 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve_combo_id(%s, %s) failed: %s", kind, template_key, type(exc).__name__)
        return None


# ------------------------------------------------------------------- FYI
def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _cap(entries: List[Any]) -> List[Any]:
    if len(entries) > FYI_CAP:
        logger.warning("template auto-send FYI queue over %d entries; the oldest %d dropped",
                       FYI_CAP, len(entries) - FYI_CAP)
        return entries[-FYI_CAP:]
    return entries


def record_auto_send(store: Any, *, kind: str, template_id: Optional[str], approval_id: Optional[str], status: str,
                     send_after: Any = None, now: Any) -> None:
    """Queue one line for the next FYI push: ids and status only, no text."""
    entry = {"kind": kind, "template_id": template_id, "approval_id": approval_id, "status": status,
             "send_after": _iso(send_after), "at": _iso(now)}

    def add(current: Any) -> List[Any]:
        items = list(current) if isinstance(current, list) else []
        items.append(entry)
        return _cap(items)
    store.mutate(FYI_KEY, add, default=[])


def _held_key(kind: str, template_id: Optional[str]) -> str:
    return HELD_KEY_PREFIX + (template_id or "%s:(no template)" % kind)


def note_held(store: Any, *, kind: str, template_id: Optional[str], reason: str, now: Any) -> None:
    """Count one held message for the FYI (per template id). ``reason`` and
    ``now`` are logged; only the count is stored."""
    store.mutate(_held_key(kind, template_id), lambda cur: (int(cur) if isinstance(cur, int) else 0) + 1, default=0)
    logger.info("template gate held %s %s: %s at %s", kind, template_id, reason, _iso(now))


def drain_fyi(store: Any) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Take everything pending: (auto-send entries, held count per template
    id). Each read-and-clear happens under the store's lock, so an entry
    recorded meanwhile lands in the next drain."""
    box = {}  # type: Dict[str, Any]

    def take(current: Any) -> List[Any]:
        box["entries"] = list(current) if isinstance(current, list) else []
        return []
    store.mutate(FYI_KEY, take, default=[])
    held = {}  # type: Dict[str, int]
    for key in list(store.keys(HELD_KEY_PREFIX)):
        got = {}  # type: Dict[str, Any]

        def zero(current: Any, got=got) -> int:
            got["n"] = current
            return 0
        store.mutate(key, zero, default=0)
        n = got.get("n")
        if isinstance(n, int) and n > 0:
            held[key[len(HELD_KEY_PREFIX):]] = n
    return box.get("entries", []), held


def restore_fyi(store: Any, entries: List[Dict[str, Any]], held: Dict[str, int]) -> None:
    """Put a drained batch back (the push failed): entries ahead of anything
    recorded since, capped at FYI_CAP; held counts added back."""
    back = list(entries or [])

    def put(current: Any) -> List[Any]:
        return _cap(back + (list(current) if isinstance(current, list) else []))
    if back:
        store.mutate(FYI_KEY, put, default=[])
    for tid, n in (held or {}).items():
        if isinstance(n, int) and n > 0:
            store.mutate(HELD_KEY_PREFIX + tid, lambda cur, n=n: (int(cur) if isinstance(cur, int) else 0) + n,
                         default=0)
