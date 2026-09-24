"""Template approval registry for the cold-email reply engine (CT1).

Lorenzo approves each prospect-facing template once. The approval records a
sha256 of the exact approved text; a later change to the wording (a prompt
file edit, a new sentence in draft.py, a new offers.md proof line, a changed
fallback such as "Hey there,") changes the hash and the template drops back
to "changed_since_approval" until he approves it again.

This module only answers questions. It sends nothing and changes no send path
itself: CT3's services/reply_engine/template_gate.py reads these approvals and
decides, per email, whether it may go out without a per-email Approve.

How the catalogue is built
--------------------------
Every template is rendered by the engine's OWN copy functions (draft.build_draft,
cadence.build_touch, booking.counter_proposal_text, show_rate.render,
no_show.render, ...) with sentinel values in place of the lead data, and the
sentinels are then swapped for placeholders like ``{first_name}`` and
``{slots}``. So the catalogue text is what the code would send, not a copy of
it that can drift.

Variants
--------
The same id can go out with different literal wording when data is missing
(no first name -> "Hey there,", no company -> "your business", no call link, no
free slots, no referral name), when the lead is in another timezone, when a
counter-proposal crosses a week (dated form), or with the fallback subject.
Each such case is rendered by the same functions and appended to the id's
``review_text`` under a "=== variant: ... ===" line. The id's sha256 is the
hash of that whole review text, which is also exactly what the exported review
document shows Lorenzo. So every literal a body sent under an approved id can
contain feeds that id's hash, and he sees every variant he is approving.

Times and slots are swapped for placeholders too ({slots}, {when_ct}, ...),
which would leave the formatter code (" or ", "CT", "am"/"pm", the date
format) outside every hash. So every id that carries a time or slot
placeholder (TIME_PLACEHOLDERS) also gets the "value_formats" variant: the
formatters' own output at fixed example times (value_formats_text). It is the
same block on every such id, so a change to how the engine writes times needs
all of them approved again.

A sentinel that survives the swap (the code transformed it, e.g. lower-cased
the company) marks the entry ``extractable: False`` rather than guessing, and
any extractor that raises becomes an unextractable entry: fail closed.

Nothing here mutates module attributes or os.environ. Two process-level
things happen during a build: a logging filter on the booking logger that
drops only the dummy-lead "booking refused" line (added and removed in
try/finally), and a per-process cache keyed on a content hash of the source
files.

Ids
---
    first_reply.<offer>.<branch>.full          composed first reply (what Lorenzo approves)
    first_reply.<offer>.greeting | .answer.<branch> | .slots   reference pieces (not approved alone)
    cadence.<d1..d30, d6_noinvite>             prompts/cadence_*.md plus build_touch variants
    cadence.<fragment>...                      text build_touch splices into d2/d4/d5
    cadence.d2.research_rules                  the rules a researched day 2 line must pass (not an email;
                                               see research_rules_review_text)
    booking.<...>                              confirmation, counter-proposals, already-booked
    show_rate.<template_key>[.<niche|offer|niche_offer>]
    no_show.<template_key>[...]
"""
import copy as copy_mod
import hashlib
import importlib
import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared.paths import BASE_DIR

logger = logging.getLogger("reply_engine.template_approvals")

APPROVALS_PATH = BASE_DIR / "config" / "approved_templates.json"
FILE_VERSION = 1
KILL_SWITCH_ENV = "AUTO_SEND_TEMPLATES"
# The only env values that leave auto-send on. Anything else that is set,
# including a typo or an empty string, is the kill switch.
KILL_SWITCH_ENABLE_VALUES = ("1", "on", "true", "yes")

STATUS_APPROVED = "approved"
STATUS_CHANGED = "changed_since_approval"
STATUS_UNAPPROVED = "unapproved"
STATUS_UNKNOWN = "unknown_id"

FIRST_REPLY_BRANCHES = ("pricing", "send_info", "mechanism", "other", "referral", "default")
NICHE_COMBOS = (
    ("cleaning", "reactivation"), ("cleaning", "outbound"),
    ("bookkeeping", "reactivation"), ("bookkeeping", "outbound"),
    ("recruiting", "reactivation"), ("recruiting", "outbound"),
    ("generic", "reactivation"), ("generic", "outbound"),
)

KIND_ORDER = (
    "first_reply",
    "cadence",
    "cadence_fragment",
    "research_rules",
    "booking",
    "show_rate",
    "no_show",
    "first_reply_piece",
)
KIND_TITLES = {
    "first_reply": "First reply to an interested lead (full body per offer and question type)",
    "cadence": "Daily follow-up cadence (prompts/cadence_*.md)",
    "cadence_fragment": "Cadence: lines spliced into day 2, day 4 and day 5",
    "research_rules": "Cadence day 2: the rules a researched line must pass (not an email)",
    "booking": "Booking: confirmation, counter-proposals, already booked",
    "show_rate": "Show-rate: confirmation, pre-read and reminders",
    "no_show": "No-show recovery",
    "first_reply_piece": "First reply: reference pieces (not approved on their own)",
}
HOOKS = {
    "first_reply": "services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved",
    "first_reply_piece": "services/reply_engine/draft.py:skeleton (not sent on its own)",
    "cadence": "services/reply_engine/cadence.py:build_touch -> tick_lead -> _send",
    "cadence_fragment": "services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send",
    "research_rules": "services/reply_engine/research_rules.py:validate <- template_gate.touch_verdict (cadence day 2, "
                      "run again at verdict time for every researched line)",
    "show_rate": "services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)",
    "no_show": "services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)",
}

WIRED_NOTE = "Approved templates send automatically (CT3). Revoke or set the kill switch to stop them."
# The CT1 name, kept for anything that still imports it.
NOT_YET_WIRED_NOTE = WIRED_NOTE

VARIANT_TITLES = {
    "missing_lead_data": "no first name, company or referral name on file",
    "no_slots": "no free slot to offer",
    "one_slot": "only one free slot",
    "confirmed_time": "the lead proposed a time that passes every slot rule",
    "proposed_time_refused": "the lead proposed a time the slot rules refuse",
    "lead_in_other_timezone": "the lead wrote in another timezone (example times)",
    "no_alternatives": "no free alternative time",
    "no_proposed_time": "the lead's time could not be read",
    "dated": "the refused time and the alternatives fall in different weeks (example dates)",
    "no_loom_url": "no Loom URL configured (the sentence is dropped)",
    "no_call_link": "no call link on file (the sentence says the link is on the calendar invite)",
    "no_call_link_or_loom": "no call link on file and no Loom URL configured",
    "no_booking_link": "no booking link configured",
    "subject": "subject line (thread subject, and the fallback when the thread has none)",
    "value_formats": "how times and slots are written",
}

# ------------------------------------------------------------- sentinels
# Lead data is replaced by sentinels, rendered by the engine's own functions,
# then swapped back for placeholders (longest sentinel first).
S_FIRST = "Zqxfirstname"
S_COMPANY = "Zqxcompany Holdings"
S_BOOKING = "https://zqx.invalid/book"
S_ZOOM = "https://zqx.invalid/zoom"
S_SLOTS_TEXT = "Zqxslotstext"
S_REFERRAL_FULL = "Zqxreferral Zqxlastname"
S_REFERRAL_FIRST = "Zqxreferral"
S_SPECIALTY = "Zqxspecialty"
S_RESEARCH = "Zqxresearchline"
S_SUBJECT = "Zqxsubjectline"
DUMMY_LEAD_EMAIL = "template-catalogue-render@example.invalid"
_SENTINEL_RE = re.compile(r"zqx", re.I)
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
VARIANT_HEADER = "=== variant: %s ==="

VARIABLE_NOTES = {
    "first_name": "lead first name (each template's missing_lead_data variant shows the fallback wording)",
    "company": "lead company name (fallback wording is shown in the missing_lead_data variant)",
    "booking_url": "Discovery Call booking link",
    "slots": "two offered times, e.g. 'Tue 2:00pm or Thu 3:30pm CT'",
    "slot": "one call time, weekday and clock time, e.g. 'Tue 2:00pm'",
    "slot1": "the held slot with its zone, e.g. 'Tue 2:00pm CT'",
    "slot2": "the alternative slot with its zone",
    "asked_time": "the time the lead proposed, in the zone they wrote it in, e.g. 'Sat 2:00pm CT' or 'Thu 11:00am ET'",
    "alt_slots": "counter-proposed times, e.g. 'Wed 2:00pm or Thu 3:00pm CT'",
    "lead_local_time": "the call time in the lead's zone, e.g. '3:00pm ET'",
    "zoom_link": "the call's join link: Zoom, or the appointment's own Google Meet link on widget bookings "
                 "(show-rate and no-show: the no_call_link variant shows the wording when none is on file)",
    "when_ct": "'Tue, Sep 23 at 2:00pm CT' (the lead's local time is added when known; see the timezone variant)",
    "time_ct": "'2:00pm CT'",
    "referral_name": "the person the lead referred us to, as written",
    "referral_first_name": "first word of referral_name",
    "specialty": "recruiting specialty from the lead record",
    "research_line": "one line about the business: the approved fallback (cadence.d2.research_fallback.*), or a "
                     "researched line that passes the approved rules (cadence.d2.research_rules) when the gate "
                     "checks it",
    "case_study": "the offer type's proof line (cadence.d4.case_study.*)",
    "free_work": "the niche and offer sample-of-work line (cadence.d5.free_work.*)",
    "loom_url": "Loom walkthrough URL",
    "original_subject": "the thread's own subject, reply prefixes stripped",
}


def _placeholders(text: str) -> List[str]:
    out = []  # type: List[str]
    for m in _PLACEHOLDER_RE.finditer(text or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _swap(text: str, mapping: Dict[str, str]) -> str:
    for raw in sorted(mapping, key=len, reverse=True):
        if raw:
            text = text.replace(raw, mapping[raw])
    return text


def _base_mapping() -> Dict[str, str]:
    return {
        S_REFERRAL_FULL: "{referral_name}",
        S_REFERRAL_FIRST: "{referral_first_name}",
        S_FIRST: "{first_name}",
        S_COMPANY: "{company}",
        S_BOOKING: "{booking_url}",
        S_ZOOM: "{zoom_link}",
        S_SLOTS_TEXT: "{slots}",
        S_SPECIALTY: "{specialty}",
        S_RESEARCH: "{research_line}",
        S_SUBJECT: "{original_subject}",
    }


def compose_review_text(text: str, variants: List[Dict[str, str]]) -> str:
    """The text an id's hash covers and the review document shows: the main
    template, then every variant under its own header line."""
    parts = [(text or "").rstrip("\n")]
    for v in variants:
        title = VARIANT_TITLES.get(v["name"], "")
        header = VARIANT_HEADER % (("%s (%s)" % (v["name"], title)) if title else v["name"])
        parts.append("%s\n%s" % (header, (v["text"] or "").rstrip("\n")))
    return "\n\n".join(parts)


def _clean_variants(text: str, variants: Optional[List[Tuple[str, str]]]) -> List[Dict[str, str]]:
    """Drop variants identical to the main text or to an earlier variant."""
    seen = {normalise(text)}
    out = []  # type: List[Dict[str, str]]
    for name, vtext in variants or []:
        key = normalise(vtext)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "text": vtext})
    return out


def _entry(tid: str, kind: str, text: str, source: str, approvable: bool = True, notes: str = "",
           hook: Optional[str] = None, variants: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
    text = text or ""
    vs = _clean_variants(text, variants)
    review = compose_review_text(text, vs)
    ok = not _SENTINEL_RE.search(review)
    entry = {
        "id": tid,
        "kind": kind,
        "text": text if ok else "",
        "variants": vs if ok else [],
        "review_text": review if ok else "",
        "variables": _placeholders(review) if ok else [],
        "source": source,
        "approvable": bool(approvable and ok),
        "extractable": ok,
        "hook": hook or HOOKS.get(kind, ""),
        "notes": notes,
    }
    if not ok:
        entry["explanation"] = ("a lead-data sentinel survived rendering, so the code transforms that value "
                                "and the template cannot be stated faithfully with placeholders")
    entry["sha256"] = text_hash(review) if ok else None
    return entry


def _unextractable(tid: str, kind: str, source: str, explanation: str, hook: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": tid, "kind": kind, "text": "", "variants": [], "review_text": "", "variables": [], "source": source,
        "approvable": False, "extractable": False, "explanation": explanation, "hook": hook or HOOKS.get(kind, ""),
        "notes": "", "sha256": None,
    }


def _guard(tid: str, kind: str, source: str, build: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Run one extractor; a failure becomes an unextractable entry, never a crash."""
    try:
        return build()
    except Exception as exc:  # noqa: BLE001 - the catalogue must still list everything it can
        logger.warning("template extraction failed for %s: %s", tid, exc)
        return [_unextractable(tid, kind, source, "extraction failed: %s: %s" % (type(exc).__name__, exc))]


# -------------------------------------------------------- fixed moments
def _tz():
    from shared import slots as slot_rules

    return slot_rules.TZ


def _ct(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return _tz().localize(datetime(y, mo, d, h, mi))


# A Monday morning far from any real booking; the engine computes the offered
# slots from it, and those exact strings are swapped for {slots}.
FIXED_NOW = (2030, 1, 7, 9, 0)
LEAD_TZ = "America/New_York"


def _all_day_busy() -> List[Tuple[str, str]]:
    start = _ct(*FIXED_NOW) - timedelta(days=1)
    return [(start.isoformat(), (start + timedelta(days=40)).isoformat())]


# ---------------------------------------------------------- first reply
def _first_reply_classification(branch: str, proposed_time: Optional[str] = None, referral: bool = True):
    from services.reply_engine.models import Classification, Extracted

    if branch == "referral":
        return Classification(label="positive_referral",
                              extracted=Extracted(referral_name=S_REFERRAL_FULL if referral else None,
                                                  proposed_time=proposed_time))
    if branch == "default":
        return Classification(label="positive_interested", extracted=Extracted(proposed_time=proposed_time))
    return Classification(label="positive_question",
                          extracted=Extracted(question_type=branch, proposed_time=proposed_time))


def _first_reply_event(offer: str, missing: bool = False):
    from services.reply_engine.models import ReplyEvent

    return ReplyEvent(email_id="catalogue", lead_email=DUMMY_LEAD_EMAIL, campaign_key=offer,
                      first_name=None if missing else S_FIRST, company=None if missing else S_COMPANY,
                      subject=S_SUBJECT, text="", received_at=_ct(*FIXED_NOW))


def _draft_text(d: Any, confirmed: Optional[datetime] = None, asked: Optional[datetime] = None) -> str:
    from shared import slots as slot_rules

    mapping = _base_mapping()
    offered = [slot_rules.parse_iso(s) for s in (d.offered_slots or [])]
    if confirmed is not None:
        mapping[slot_rules.format_slot(confirmed)] = "{slot}"
    elif len(offered) >= 2:
        mapping[slot_rules.format_slots(offered)] = "{slots}"
    if asked is not None:
        mapping[slot_rules.format_asked_time(asked)] = "{asked_time}"
    return _swap(d.body_text, mapping)


def _build_first_reply(offer: str, branch: str, proposed: Optional[datetime] = None, missing: bool = False,
                       no_slots: bool = False) -> Any:
    from services.reply_engine import draft

    cls = _first_reply_classification(branch, proposed.isoformat() if proposed is not None else None,
                                      referral=not missing)
    return draft.build_draft(_first_reply_event(offer, missing=missing), cls, now=_ct(*FIXED_NOW),
                             booking_link=S_BOOKING, use_llm=False, already_offered=[],
                             busy_blocks=_all_day_busy() if no_slots else [])


def _reply_subject_variant() -> str:
    from services.reply_engine import draft

    return _swap("Subject: %s\nSubject when the thread has none: %s"
                 % (draft.reply_subject(S_SUBJECT), draft.reply_subject(None)), _base_mapping())


def _first_reply_entries() -> List[Dict[str, Any]]:
    from services.reply_engine import draft

    out = []  # type: List[Dict[str, Any]]
    confirmed = _ct(2030, 1, 8, 15, 30)  # Tue, inside every slot rule relative to FIXED_NOW
    refused = _ct(2030, 1, 12, 14, 0)  # Saturday: refused, so the draft counters
    for offer in draft.PRICING:
        for branch in FIRST_REPLY_BRANCHES:
            tid = "first_reply.%s.%s.full" % (offer, branch)

            def build(offer=offer, branch=branch, tid=tid):
                main = _draft_text(_build_first_reply(offer, branch))
                variants = [
                    ("missing_lead_data", _draft_text(_build_first_reply(offer, branch, missing=True))),
                    ("no_slots", _draft_text(_build_first_reply(offer, branch, no_slots=True))),
                    ("confirmed_time", _draft_text(_build_first_reply(offer, branch, proposed=confirmed),
                                                   confirmed=confirmed)),
                ]
                d = _build_first_reply(offer, branch, proposed=refused)
                variants.append(("proposed_time_refused", _draft_text(d, asked=refused)))
                variants.append(("subject", _reply_subject_variant()))
                notes = ("The template body before any LLM polish (draft.build_draft with use_llm=False). "
                         "A polished body is different text and is not covered by this approval.")
                if branch == "other":
                    notes += " Also used for every neutral_question that is not pricing, send_info or mechanism."
                return [_entry(tid, "first_reply", main, "services/reply_engine/draft.py:build_draft (skeleton)",
                               notes=notes, variants=variants)]
            out.extend(_guard(tid, "first_reply", "services/reply_engine/draft.py:build_draft", build))
    return out


def _first_reply_pieces() -> List[Dict[str, Any]]:
    from shared import slots as slot_rules
    from services.reply_engine import draft

    kind = "first_reply_piece"
    out = []  # type: List[Dict[str, Any]]
    a, b = _ct(2030, 1, 8, 13, 47), _ct(2030, 1, 10, 16, 13)
    for offer in draft.PRICING:
        ev = _first_reply_event(offer)
        tid = "first_reply.%s.greeting" % offer
        out.extend(_guard(tid, kind, "services/reply_engine/draft.py:greeting", lambda tid=tid, ev=ev: [
            _entry(tid, kind, _swap(draft.greeting(ev), _base_mapping()), "services/reply_engine/draft.py:greeting",
                   approvable=False)]))
        for branch in FIRST_REPLY_BRANCHES:
            tid = "first_reply.%s.answer.%s" % (offer, branch)

            def build(tid=tid, ev=ev, branch=branch):
                text = draft.answer_paragraph(ev, _first_reply_classification(branch))
                return [_entry(tid, kind, _swap(text, _base_mapping()),
                               "services/reply_engine/draft.py:answer_paragraph", approvable=False)]
            out.extend(_guard(tid, kind, "services/reply_engine/draft.py:answer_paragraph", build))
        tid = "first_reply.%s.slots" % offer

        def build_slots(tid=tid):
            mapping = _base_mapping()
            mapping[slot_rules.format_slots([a, b])] = "{slots}"
            return [_entry(tid, kind, _swap(draft.slot_paragraph([a, b], S_BOOKING), mapping),
                           "services/reply_engine/draft.py:slot_paragraph", approvable=False)]
        out.extend(_guard(tid, kind, "services/reply_engine/draft.py:slot_paragraph", build_slots))
    return out


# -------------------------------------------------------------- cadence
def cadence_template_names() -> List[str]:
    """Every prompts/cadence_d*.md, as the name cadence.render() takes ('d1', 'd6_noinvite')."""
    from services.reply_engine import cadence

    names = [p.stem[len("cadence_"):] for p in Path(cadence.PROMPTS_DIR).glob("cadence_d*.md")]

    def order(name: str) -> Tuple[int, str]:
        m = re.match(r"d(\d+)(.*)$", name)
        return (int(m.group(1)), m.group(2)) if m else (10 ** 6, name)
    return sorted(names, key=order)


class _State(types.SimpleNamespace):
    pass


def _cadence_state(missing: bool = False, subject: Optional[str] = S_SUBJECT) -> Any:
    return _State(first_name=None if missing else S_FIRST, company=None if missing else S_COMPANY,
                  niche="cleaning", offer="reactivation", campaign_key="cleaning_reactivation", campaign_id=None,
                  phone=None, specialty=None, website=None, last_subject=subject, subject=None, thread_subject=None,
                  lead_email=DUMMY_LEAD_EMAIL, ghl_contact_id=None, cadence={})


def _cadence_subject_variant() -> str:
    from services.reply_engine import cadence

    return _swap("Subject: %s\nSubject when the thread has none: %s\nSubject when there is no first name either: %s"
                 % (cadence.subject_for(_cadence_state()), cadence.subject_for(_cadence_state(subject=None)),
                    cadence.subject_for(_cadence_state(missing=True, subject=None))), _base_mapping())


def _touch_text(touch: Any, two: List[datetime]) -> str:
    from shared import slots as slot_rules

    mapping = _base_mapping()
    from services.reply_engine import cadence

    mapping[cadence.DEFAULT_BOOKING_URL] = "{booking_url}"
    if two:
        mapping[slot_rules.format_slots(two)] = "{slots}"
        mapping[slot_rules.format_slots(two[:1])] = "{slot1}"
        if len(two) > 1:
            mapping[slot_rules.format_slots(two[1:2])] = "{slot2}"
    return _swap(touch.body_text, mapping)


def _cadence_entries() -> List[Dict[str, Any]]:
    from services.reply_engine import cadence

    out = []  # type: List[Dict[str, Any]]
    notes = {
        "d2": "{research_line} is cadence.d2.research_fallback.<offer>, the fixed fallback line, or a researched "
              "line that the approved rules (cadence.d2.research_rules) pass at send time. A line written per lead "
              "with no rules check (cadence.d2.research_line) is not covered by any approval, so a day 2 touch "
              "carrying one is always held, never sent.",
        "d4": "{case_study} is cadence.d4.case_study.<offer>; the variants show the reactivation line in place.",
        "d5": "{free_work} is cadence.d5.free_work.<niche>_<offer>; the variants show the cleaning line in place.",
        "d6": "Needs Lorenzo's one-tap OK on the calendar hold today (Touch.requires_approval).",
        "d7": "No slots.",
    }
    two = [_ct(2030, 1, 8, 13, 47), _ct(2030, 1, 10, 16, 13)]
    for name in cadence_template_names():
        tid = "cadence.%s" % name
        path = "services/reply_engine/prompts/cadence_%s.md" % name

        def build(tid=tid, name=name, path=path):
            text = cadence._load_template(name)
            m = re.match(r"d(\d+)(_noinvite)?$", name)
            variants = []  # type: List[Tuple[str, str]]
            if m:
                day = int(m.group(1))
                invite = not m.group(2)

                def touch(state, slots_):
                    return cadence.build_touch(state, day, [s.isoformat() for s in slots_], research_line=S_RESEARCH,
                                               invite_created=invite)
                if day == 6 and invite:
                    variants.append(("missing_lead_data", _touch_text(touch(_cadence_state(missing=True), two), two)))
                    variants.append(("one_slot", _touch_text(touch(_cadence_state(), two[:1]), two[:1])))
                else:
                    variants.append(("missing_lead_data", _touch_text(touch(_cadence_state(missing=True), two), two)))
                    variants.append(("no_slots", _touch_text(touch(_cadence_state(), []), [])))
            variants.append(("subject", _cadence_subject_variant()))
            return [_entry(tid, "cadence", text, path, notes=notes.get(name, ""), variants=variants)]
        out.extend(_guard(tid, "cadence", path, build))
    return out


def _cadence_fragments() -> List[Dict[str, Any]]:
    from services.reply_engine import cadence

    kind = "cadence_fragment"
    out = []  # type: List[Dict[str, Any]]
    for offer in ("reactivation", "outbound"):
        tid = "cadence.d4.case_study.%s" % offer
        out.extend(_guard(tid, kind, "services/reply_engine/cadence.py:case_study_line", lambda tid=tid, offer=offer: [
            _entry(tid, kind, cadence.case_study_line(offer),
                   "services/reply_engine/cadence.py:case_study_line (config/offers.md proof table)")]))
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        for offer in ("reactivation", "outbound"):
            variants = [("", None)]
            if niche == "recruiting" and offer == "outbound":
                variants.append(("_specialty", S_SPECIALTY))
            for suffix, specialty in variants:
                tid = "cadence.d5.free_work.%s_%s%s" % (niche, offer, suffix)

                def build(tid=tid, niche=niche, offer=offer, specialty=specialty):
                    text = cadence.free_work_line(niche, S_COMPANY, specialty, offer=offer)
                    return [_entry(tid, kind, _swap(text, _base_mapping()),
                                   "services/reply_engine/cadence.py:free_work_line",
                                   notes="'generic' is any niche the function does not name. Without a company "
                                         "the cadence passes its own fallback (see the cadence variants).")]
                out.extend(_guard(tid, kind, "services/reply_engine/cadence.py:free_work_line", build))
    for offer in ("reactivation", "outbound"):
        tid = "cadence.d2.research_fallback.%s" % offer
        out.extend(_guard(tid, kind, "services/reply_engine/cadence.py:fallback_research_line",
                          lambda tid=tid, offer=offer: [
                              _entry(tid, kind, _swap(cadence.fallback_research_line(S_COMPANY, offer), _base_mapping()),
                                     "services/reply_engine/cadence.py:fallback_research_line",
                                     notes="Used when the research model returns nothing usable.")]))
    out.append(_unextractable(
        "cadence.d2.research_line", kind, "services/reply_engine/cadence.py:generate_research_line",
        "Written per lead by the LLM (shared.llm role 'research') from the prompt in prompts/cadence_research.md, "
        "so there is no fixed text to hash. CT3: day 2 uses the fallback line by default; a touch carrying an "
        "LLM line is always held, never sent."))
    return out


# ------------------------------------------------ day 2 research rules
# Lorenzo approves the rules a researched day 2 line must pass, once, as the
# catalogue entry RESEARCH_RULES_ID. The rules live in section 1's module
# RESEARCH_RULES_MODULE (pure: no network, no model, no clock):
#
#     RULES_TEXT: str          what Lorenzo reads and approves
#     RULES_VERSION: int       bumped with any change to how validate() judges
#     validate(line, evidence, context) -> ResearchVerdict(ok, line, reasons, rules_sha)
#     rules_sha() -> str       optional; see template_gate.research_rules_sha
#
# The entry's review text is RULES_TEXT plus a "RULES_VERSION: N" line, and its
# sha256 is text_hash() of that like every entry, so a change to RULES_TEXT or
# RULES_VERSION drops the approval to changed_since_approval. Until the module
# is there (or while it is broken) the entry is unextractable and not
# approvable, so the approvable count and the parity digest do not move.
RESEARCH_RULES_MODULE = "services.reply_engine.research_rules"
RESEARCH_RULES_ID = "cadence.d2.research_rules"
RESEARCH_RULES_KIND = "research_rules"
RESEARCH_RULES_SOURCE = "services/reply_engine/research_rules.py:RULES_TEXT"
RESEARCH_RULES_VERSION_LINE = "RULES_VERSION: %d"
RESEARCH_RULES_ABSENT = "the research rules module is not there yet"


def load_research_rules() -> Tuple[Optional[Any], Optional[str], bool]:
    """(module, why_not, absent_by_design). Imported lazily, by name, every
    call (a module already imported comes straight from sys.modules). Never
    raises: a missing module is (None, RESEARCH_RULES_ABSENT, True); a module
    that fails to import is (None, why, False)."""
    try:
        return importlib.import_module(RESEARCH_RULES_MODULE), None, False
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", None) == RESEARCH_RULES_MODULE:
            return None, RESEARCH_RULES_ABSENT, True
        return None, "the research rules module could not be imported (%s: %s)" % (type(exc).__name__, exc), False
    except Exception as exc:  # noqa: BLE001 - a broken rules module is no rules, never a broken catalogue
        return None, "the research rules module could not be imported (%s: %s)" % (type(exc).__name__, exc), False


def research_rules_parts(module: Any) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """(RULES_TEXT, RULES_VERSION, why_not) of an imported rules module.
    why_not is None only when RULES_TEXT is non-empty text, RULES_VERSION an
    int (not a bool) and validate callable. Never raises."""
    try:
        text = getattr(module, "RULES_TEXT", None)
        version = getattr(module, "RULES_VERSION", None)
        if not isinstance(text, str) or not text.strip():
            return None, None, "the research rules module has no RULES_TEXT"
        if isinstance(version, bool) or not isinstance(version, int):
            return None, None, "the research rules module's RULES_VERSION is not an integer"
        if not callable(getattr(module, "validate", None)):
            return None, None, "the research rules module has no validate()"
        return text, version, None
    except Exception as exc:  # noqa: BLE001
        return None, None, "the research rules module could not be read (%s)" % type(exc).__name__


def research_rules_review_text(text: str, version: int) -> str:
    """What the RESEARCH_RULES_ID entry shows Lorenzo and hashes: RULES_TEXT,
    a blank line, then "RULES_VERSION: N"."""
    return "%s\n\n%s" % ((text or "").rstrip("\n"), RESEARCH_RULES_VERSION_LINE % int(version))


def research_rules_sha(text: str, version: int) -> str:
    """text_hash(research_rules_review_text(text, version)): the entry's
    sha256, and the rules_sha a module without rules_sha() must report."""
    return text_hash(research_rules_review_text(text, version))


def research_rules_fingerprint() -> str:
    """What the RESEARCH_RULES_ID entry depends on, for the catalogue cache
    key (_source_key): the rules text, version and whether validate is there,
    or why the module is not usable (its exception type only, so the key is
    the same on every call). Never raises."""
    mod, _why, absent = load_research_rules()
    if mod is None:
        return "absent" if absent else "broken"
    try:
        raw = json.dumps([repr(getattr(mod, "RULES_TEXT", None)), repr(getattr(mod, "RULES_VERSION", None)),
                          callable(getattr(mod, "validate", None))])
        return "module:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception as exc:  # noqa: BLE001
        return "unreadable:%s" % type(exc).__name__


def _research_rules_entries() -> List[Dict[str, Any]]:
    kind = RESEARCH_RULES_KIND
    notes = ("Not an email. Approving this approves the rules a researched day 2 line must pass: cadence.d2 then "
             "auto-sends with a per-lead line only when services/reply_engine/research_rules.py:validate passes it "
             "again at send time. A change to RULES_TEXT or RULES_VERSION needs approval again.")
    mod, why, absent = load_research_rules()
    if mod is None:
        entry = _unextractable(RESEARCH_RULES_ID, kind, RESEARCH_RULES_SOURCE, why or RESEARCH_RULES_ABSENT)
        if absent:
            entry["unextractable_by_design"] = True
        return [entry]
    text, version, why = research_rules_parts(mod)
    if why:
        return [_unextractable(RESEARCH_RULES_ID, kind, RESEARCH_RULES_SOURCE, why)]
    entry = _entry(RESEARCH_RULES_ID, kind, research_rules_review_text(text, version), RESEARCH_RULES_SOURCE,
                   notes=notes)
    # Rules prose, not a template: whatever braces it quotes are not placeholders.
    entry["variables"] = []
    return [entry]


# -------------------------------------------------------------- booking
def _booking_state(missing: bool = False) -> Any:
    return _cadence_state(missing=missing)


def _booking_entries() -> List[Dict[str, Any]]:
    from shared import slots as slot_rules
    from services.reply_engine import booking, cadence

    kind = "booking"
    hook_confirm = ("services/reply_engine/booking.py:_confirmation_draft <- book() / _already_booked_result; "
                    "sent as an approval card via app.py -> approval.py:send_approved")
    hook_counter = ("services/reply_engine/booking.py:counter_proposal_text <- app.py; "
                    "sent via approval.py:send_approved")
    out = []  # type: List[Dict[str, Any]]
    start = _ct(2030, 1, 8, 13, 47)

    def mapping_for(*pairs: Tuple[str, str]) -> Dict[str, str]:
        m = _base_mapping()
        m[cadence.DEFAULT_BOOKING_URL] = "{booking_url}"
        for raw, ph in pairs:
            m[raw] = ph
        return m

    subject = _cadence_subject_variant()

    def confirmation(zoom: bool):
        def build():
            def render(state, lead_tz):
                d, _ = booking._confirmation_draft(state, start, lead_tz, S_ZOOM if zoom else None, True)
                return d.body_text
            import pytz

            lead_local = slot_rules.format_slots([start], tz=pytz.timezone(LEAD_TZ)).split(" ", 1)[1]
            m = mapping_for((slot_rules.format_slot(start), "{slot}"), (lead_local, "{lead_local_time}"))
            main = _swap(render(_booking_state(), None), m)
            variants = [
                ("lead_in_other_timezone", _swap(render(_booking_state(), LEAD_TZ), m)),
                ("missing_lead_data", _swap(render(_booking_state(missing=True), None), m)),
                ("subject", subject),
            ]
            tid = "booking.confirmation.%s" % ("zoom_link" if zoom else "no_zoom_link")
            return [_entry(tid, kind, main, "services/reply_engine/booking.py:_confirmation_draft", hook=hook_confirm,
                           notes="Claims an invite: approval.py:claims_invite rules still apply.", variants=variants)]
        return build

    out.extend(_guard("booking.confirmation.zoom_link", kind, "booking.py:_confirmation_draft", confirmation(True)))
    out.extend(_guard("booking.confirmation.no_zoom_link", kind, "booking.py:_confirmation_draft", confirmation(False)))

    # Counter-proposals: a proposed time and two alternatives in the same ISO week (undated form).
    k1, k2 = _ct(2030, 1, 9, 14, 43), _ct(2030, 1, 10, 15, 17)
    n1, n2 = _ct(2030, 1, 15, 14, 43), _ct(2030, 1, 16, 15, 17)  # next ISO week: the dated form
    cases = (
        ("window_no_fit", booking.WINDOW_NO_FIT, _ct(2030, 1, 8, 13, 47)),
        ("outside_window_early", booking.OUTSIDE_WINDOW, _ct(2030, 1, 8, 9, 47)),
        ("outside_window_late", booking.OUTSIDE_WINDOW, _ct(2030, 1, 8, 19, 47)),
        ("weekend", booking.WEEKEND, _ct(2030, 1, 12, 13, 47)),
        ("too_soon", booking.TOO_SOON, _ct(2030, 1, 8, 13, 47)),
        ("beyond_horizon", booking.BEYOND_HORIZON, _ct(2030, 1, 11, 13, 47)),
        ("slot_taken", booking.SLOT_TAKEN, _ct(2030, 1, 8, 13, 47)),
    )
    for name, status_, proposed in cases:
        tid = "booking.counter.%s" % name

        def build(tid=tid, status_=status_, proposed=proposed):
            def render(state, prop, counters):
                match = booking.BookingMatch(slot=None, status=status_, proposed=prop, counter_slots=list(counters))
                body = booking.counter_proposal_text(match, state)
                if body is None:
                    raise ValueError("counter_proposal_text returned None for %s" % status_)
                return body
            m = mapping_for((slot_rules.format_slots([k1, k2]), "{alt_slots}"),
                            (slot_rules.format_asked_time(proposed), "{asked_time}"))
            main = _swap(render(_booking_state(), proposed, [k1, k2]), m)
            # The dated form keeps its example dates, so the date format itself is hashed.
            variants = [
                ("missing_lead_data", _swap(render(_booking_state(missing=True), proposed, [k1, k2]), m)),
                ("no_alternatives", _swap(render(_booking_state(), proposed, []), m)),
                ("no_proposed_time", _swap(render(_booking_state(), None, [k1, k2]), m)),
                ("dated", _swap(render(_booking_state(), proposed, [n1, n2]), mapping_for())),
                ("subject", subject),
            ]
            return [_entry(tid, kind, main, "services/reply_engine/booking.py:counter_proposal_text", hook=hook_counter,
                           variants=variants)]
        out.extend(_guard(tid, kind, "booking.py:counter_proposal_text", build))

    def taken():
        now_ct = _ct(*FIXED_NOW)
        free = [k1.isoformat(), k2.isoformat()]

        def render(state, free_slots):
            res = booking._unbookable_result(state, start, booking.SLOT_ALREADY_TAKEN, now_ct, free_slots=free_slots)
            return res.draft.body_text
        alts = slot_rules.format_slots(booking._counter(booking._candidates(now_ct, free), start))
        m = mapping_for((alts, "{alt_slots}"), (slot_rules.format_slot(start), "{slot}"))
        main = _swap(render(_booking_state(), free), m)
        variants = [
            ("missing_lead_data", _swap(render(_booking_state(missing=True), free), m)),
            ("no_alternatives", _swap(render(_booking_state(), []), m)),
            ("subject", subject),
        ]
        return [_entry("booking.slot_already_taken", kind, main, "services/reply_engine/booking.py:_unbookable_result",
                       hook="services/reply_engine/booking.py:_unbookable_result <- book(); the draft carries the "
                            "slot_already_taken problem, so it is always a card, never auto-sent",
                       notes="Sent when the calendar filled between the offer and the booking.", variants=variants)]
    out.extend(_guard("booking.slot_already_taken", kind, "booking.py:_unbookable_result", taken))

    try:
        from services.reply_engine import app as app_mod
    except Exception as exc:  # noqa: BLE001
        for variant in ("awaiting_approval", "invite_withheld", "invite_on_calendar"):
            out.append(_unextractable("booking.already_booked.%s" % variant, kind,
                                      "services/reply_engine/app.py:_already_booked_body",
                                      "app.py could not be imported here (%s)" % exc))
        return out
    variants_ab = (
        ("awaiting_approval", {"awaiting_approval": True}),
        ("invite_withheld", {"invite_released": False}),
        ("invite_on_calendar", {"invite_released": True}),
    )
    for variant, rec in variants_ab:
        tid = "booking.already_booked.%s" % variant

        def build_ab(tid=tid, rec=rec):
            def render(first, link):
                st = _State(first_name=first, cadence={"booking": dict(rec)})
                return app_mod._already_booked_body(st, start.isoformat(), link)
            m = mapping_for((slot_rules.format_slot(start), "{slot}"))
            main = _swap(render(S_FIRST, S_BOOKING), m)
            variants = [
                ("missing_lead_data", _swap(render(None, S_BOOKING), m)),
                ("no_booking_link", _swap(render(S_FIRST, None), m)),
                ("subject", _reply_subject_variant()),
            ]
            return [_entry(tid, kind, main, "services/reply_engine/app.py:_already_booked_body",
                           hook="services/reply_engine/app.py:_already_booked_body -> approval card",
                           notes="When the lead also asked a question, the answer paragraph is inserted after the "
                                 "greeting; that answer is the first reply's answer text.", variants=variants)]
        out.extend(_guard(tid, kind, "app.py:_already_booked_body", build_ab))
    return out


# ------------------------------------------------ show-rate and no-show
def _appointment(niche: str, offer: str, missing: bool = False, lead_tz: Optional[str] = None,
                 no_link: bool = False) -> Dict[str, Any]:
    """``missing``: no first name or company on file. ``no_link``: no call
    link on file (its own variant, no_call_link, like no_loom_url)."""
    appt = {"niche": niche, "offer": offer, "booking_url": S_BOOKING, "id": "catalogue"}
    if not missing:
        appt.update({"first_name": S_FIRST, "company": S_COMPANY})
    if not no_link:
        appt["zoom_link"] = S_ZOOM
    if lead_tz:
        appt["lead_tz"] = lead_tz
    return appt


def _group_by_combo(texts: Dict[Tuple[str, str], Any]) -> List[Tuple[str, Any, List[Tuple[str, str]]]]:
    """[(suffix, value, combos)]: one entry when the value never varies, else per
    niche, per offer or per (niche, offer), whichever is the coarsest exact split.
    Values are compared with ==, so pass the full (main, variants) tuple."""
    combos = list(texts)
    first = texts[combos[0]]
    if all(texts[c] == first for c in combos):
        return [("", first, combos)]
    niches = sorted(set(n for n, _ in combos), key=[n for n, _ in NICHE_COMBOS].index)
    offers = sorted(set(o for _, o in combos), key=("reactivation", "outbound").index)
    if all(all(texts[(n, o)] == texts[(n, offers[0])] for o in offers) for n in niches):
        return [(".%s" % n, texts[(n, offers[0])], [(n, o) for o in offers]) for n in niches]
    if all(all(texts[(n, o)] == texts[(niches[0], o)] for n in niches) for o in offers):
        return [(".%s" % o, texts[(niches[0], o)], [(n, o) for n in niches]) for o in offers]
    return [(".%s_%s" % c, texts[c], [c]) for c in combos]


def loom_sentence() -> Optional[str]:
    """The Loom sentence show_rate.loom_line() emits, with {loom_url}, read from
    its code constants so no environment variable has to be set to see it."""
    from services.reply_engine import show_rate

    found = [c for c in show_rate.loom_line.__code__.co_consts
             if isinstance(c, str) and c.count("%s") == 1 and " " in c and not c.startswith("LOOM_URL")]
    if len(found) != 1:
        return None
    return found[0].replace("%s", "{loom_url}")


SHOW_RATE_LEAD_FACING = ("confirm_email", "confirm_sms", "preread_email", "reminder_24h_sms",
                         "reminder_24h_email", "reminder_1h_sms", "reminder_15m_sms")
NO_SHOW_LEAD_FACING = ("ns_still_on_sms", "ns_still_on_email", "ns_reschedule_email", "ns_d1_other_channel",
                       "ns_d3_value_email", "ns_d7_yes_no_email", "ns_d14_breakup_email")
LOOM_ANCHOR = "If anything comes up before then"


def _with_subject(copy: Dict[str, Any]) -> str:
    subject = copy.get("subject")
    body = copy.get("body") or ""
    return ("Subject: %s\n\n%s" % (subject, body)) if subject else body


def _put_loom(text: str, niche: str, loom: str) -> str:
    """confirm_email with the Loom sentence in place as '{loom_url}' wording,
    whatever the environment holds; raises when it cannot be placed."""
    from services.reply_engine import show_rate

    real = show_rate.loom_line(niche)
    if real:
        if real not in text:
            raise ValueError("the configured Loom sentence is not where confirm_email puts it")
        return text.replace(real, loom, 1)
    if LOOM_ANCHOR not in text:
        raise ValueError("confirm_email no longer has the anchor the Loom line sits before")
    return text.replace(LOOM_ANCHOR, loom + "\n\n" + LOOM_ANCHOR, 1)


def _drop_loom(text: str, niche: str) -> str:
    from services.reply_engine import show_rate

    real = show_rate.loom_line(niche)
    return text.replace(real + "\n\n", "", 1) if real else text


def _show_rate_entries() -> List[Dict[str, Any]]:
    from services.reply_engine import show_rate

    kind = "show_rate"
    out = []  # type: List[Dict[str, Any]]
    start = _ct(2030, 1, 8, 13, 47)
    now = _ct(*FIXED_NOW)
    keys = [k for k, _, _ in show_rate.SEQUENCE if k in SHOW_RATE_LEAD_FACING]
    for key in keys:
        base = "show_rate.%s" % key

        def build(key=key, base=base):
            loom = loom_sentence() if key == "confirm_email" else None
            if key == "confirm_email" and not loom:
                raise ValueError("the Loom sentence could not be read from show_rate.loom_line")
            mapping = _base_mapping()
            mapping[show_rate.fmt_when(start, None)] = "{when_ct}"
            mapping[show_rate.fmt_time_only(start)] = "{time_ct}"
            texts = {}  # type: Dict[Tuple[str, str], Any]
            for niche, offer in NICHE_COMBOS:
                def render(**kw):
                    return _with_subject(show_rate.render(key, _appointment(niche, offer, **kw), start, now))
                main_raw = render()
                variants = [("missing_lead_data", _swap(render(missing=True), mapping)),
                            ("no_call_link", _swap(render(no_link=True), mapping))]
                if "{when_ct}" in _swap(main_raw, mapping):
                    # example times kept: the lead-zone format is part of what is approved
                    tz_map = dict(mapping)
                    tz_map.pop(show_rate.fmt_when(start, None))
                    tz_map.pop(show_rate.fmt_time_only(start))
                    variants.append(("lead_in_other_timezone", _swap(render(lead_tz=LEAD_TZ), tz_map)))
                main = _swap(main_raw, mapping)
                if key == "confirm_email":
                    main = _put_loom(main, niche, loom)
                    variants = [(n, _put_loom(t, niche, loom)) for n, t in variants]
                    variants.append(("no_loom_url", _swap(_drop_loom(main_raw, niche), mapping)))
                    # both optional links missing at once: its own wording, so
                    # it needs its own variant (no single one above shows it)
                    variants.append(("no_call_link_or_loom",
                                     _swap(_drop_loom(render(no_link=True), niche), mapping)))
                texts[(niche, offer)] = (main, tuple(variants))
            entries = []
            for suffix, (main, variants), combos in _group_by_combo(texts):
                notes = "Applies to: %s." % ", ".join("%s/%s" % c for c in combos)
                if key.endswith("_sms"):
                    notes += " SMS bodies are cut at %d characters." % show_rate.SMS_MAX_LEN
                entry = _entry(base + suffix, kind, main, "services/reply_engine/show_rate.py:render",
                               notes=notes, variants=list(variants))
                # Outside review_text, so it feeds no hash: which (niche, offer)
                # pairs this id covers, for template_gate.resolve_combo_id.
                entry["applies_to"] = [list(c) for c in combos]
                entries.append(entry)
            return entries
        out.extend(_guard(base, kind, "services/reply_engine/show_rate.py:render", build))
    return out


def _no_show_entries() -> List[Dict[str, Any]]:
    from services.reply_engine import no_show, show_rate

    kind = "no_show"
    out = []  # type: List[Dict[str, Any]]
    start = _ct(2030, 1, 8, 13, 47)
    keys = [k for k, _, _ in no_show.FULL_SEQUENCE if k in NO_SHOW_LEAD_FACING]
    runs = [(k, 1, "") for k in keys] + [("ns_reschedule_email", 2, ".repeat")]
    for key, count, tail in runs:
        base = "no_show.%s" % key

        def build(key=key, count=count, tail=tail, base=base):
            mapping = _base_mapping()
            mapping[show_rate.fmt_when(start, None)] = "{when_ct}"
            mapping[show_rate.fmt_time_only(start)] = "{time_ct}"
            texts = {}  # type: Dict[Tuple[str, str], Any]
            for niche, offer in NICHE_COMBOS:
                def render(slots_text=S_SLOTS_TEXT, **kw):
                    return _swap(_with_subject(no_show.render(key, _appointment(niche, offer, **kw), start,
                                                              slots_text, count)), mapping)
                texts[(niche, offer)] = (render(), (("missing_lead_data", render(missing=True)),
                                                    ("no_call_link", render(no_link=True)),
                                                    ("no_slots", render(slots_text=""))))
            entries = []
            for suffix, (main, variants), combos in _group_by_combo(texts):
                notes = "Applies to: %s." % ", ".join("%s/%s" % c for c in combos)
                if tail:
                    notes += " Second no-show for the same lead."
                entry = _entry(base + tail + suffix, kind, main, "services/reply_engine/no_show.py:render",
                               notes=notes, variants=list(variants))
                entry["applies_to"] = [list(c) for c in combos]  # outside review_text: no hash change
                entries.append(entry)
            return entries
        out.extend(_guard(base + tail, kind, "services/reply_engine/no_show.py:render", build))
    return out


# -------------------------------------------------------- value formats
# Placeholders whose value is a time or a slot the engine writes itself. The
# extractors swap each formatted time for its placeholder, so without the
# block below the formatter code would feed no hash at all.
TIME_PLACEHOLDERS = ("slots", "alt_slots", "slot1", "slot2", "slot", "asked_time", "lead_local_time",
                     "when_ct", "time_ct")
VALUE_FORMATS_VARIANT = "value_formats"
# Fixed example times, localized in America/Chicago by pytz (January 2030:
# standard time, far from any real booking). Neither the machine's timezone
# nor the date of the build can change the text rendered from them.
VALUE_FORMAT_TIMES = ((2030, 1, 7, 9, 45), (2030, 1, 8, 12, 5), (2030, 1, 10, 16, 30))
VALUE_FORMAT_NEXT_WEEK = ((2030, 1, 15, 12, 5), (2030, 1, 17, 16, 30))
# One lead zone per _tz_label branch: Central, Eastern, Mountain, Pacific,
# and a zone it has no short name for (its strftime("%Z") fallback).
# The zones slots.TZ_ALIASES answers for a lead's proposed time ({asked_time}).
ASKED_TIME_ZONES = ("America/Chicago", "America/New_York", "America/Denver", "America/Los_Angeles")
VALUE_FORMAT_ZONES = ("America/Chicago", "America/New_York", "America/Denver", "America/Los_Angeles",
                      "America/Phoenix")


def value_formats_text() -> str:
    """How the engine writes every time and slot placeholder, rendered by its
    own formatters at VALUE_FORMAT_TIMES:

    shared/slots.py      format_slots (two times, one time), format_slot,
                         _tz_label, parse_iso and to_tz (offered slots are
                         stored as ISO strings and parsed back)
    booking.py           _their_time ({lead_local_time}), _dated_slots and
                         _dated_slot (a counter-proposal that crosses a week)
    shared/slots.py      format_asked_time ({asked_time}, undated and dated,
                         in each zone a lead can name)
    show_rate.py         fmt_when with and without the lead's zone (the zone
                         read by lead_tz_of, as render does) and
                         fmt_time_only

    draft.py, cadence.py, no_show.py and app.py fill their time placeholders
    through these same functions. The text is the value_formats variant of
    every id that carries a TIME_PLACEHOLDERS placeholder, so a change to any
    of these formatters changes all of their hashes."""
    import pytz
    from shared import slots as slot_rules
    from services.reply_engine import booking, show_rate

    mon, tue, thu = [_ct(*t) for t in VALUE_FORMAT_TIMES]
    next_tue, next_thu = [_ct(*t) for t in VALUE_FORMAT_NEXT_WEEK]
    stored = [slot_rules.parse_iso(dt.isoformat()) for dt in (tue, thu)]
    zones = [(name, pytz.timezone(name)) for name in VALUE_FORMAT_ZONES]
    # the zones a lead can name when proposing a time (slots.TZ_ALIASES):
    # Phoenix is not one of them
    asked_zones = [(name, pytz.timezone(name)) for name in ASKED_TIME_ZONES]

    def each(items: Any) -> str:
        return " | ".join(items)

    def example(dt: datetime) -> str:
        return "%s %s %d %d:%02d" % (dt.strftime("%a"), dt.strftime("%b"), dt.day, dt.hour, dt.minute)

    lines = [
        "Example times: %s, %s and %s, 2030, Central (America/Chicago). This block is the same on every "
        "template that has a time or slot in it." % (example(mon), example(tue), example(thu)),
        "Two times, {slots} and {alt_slots}: %s" % slot_rules.format_slots(stored),
        "One time, {slots}, {alt_slots}, {slot1} and {slot2}: %s" % slot_rules.format_slots(stored[:1]),
        "A time without its zone, {slot}: %s"
        % each(slot_rules.format_slot(dt) for dt in (tue, thu, mon)),
        "A counter-proposal that crosses a week, {alt_slots}: %s" % booking._dated_slots([next_tue, next_thu]),
        "The time the lead proposed, in the zone they wrote it in, {asked_time}: %s"
        % each("%s = %s" % (name, slot_rules.format_asked_time(mon, tz)) for name, tz in asked_zones),
        "The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: %s"
        % each("%s = %s" % (name, slot_rules.format_asked_time(mon, tz, dated=True)) for name, tz in asked_zones),
        "The lead's own time after the call time, {lead_local_time}: %s"
        % each("%s = %s" % (name, booking._their_time(tue, name).strip() or "(nothing added)")
               for name, _ in zones),
        "The call time, {when_ct}: %s" % show_rate.fmt_when(tue),
        "The call time when the lead's timezone is known, {when_ct}: %s"
        % each("%s = %s" % (name, show_rate.fmt_when(tue, show_rate.lead_tz_of({"lead_tz": name})))
               for name, _ in zones),
        "The clock time only, {time_ct}: %s" % each(show_rate.fmt_time_only(dt) for dt in (tue, thu)),
        "Zone labels: %s"
        % each("%s = %s" % (name, slot_rules._tz_label(slot_rules.to_tz(tue, tz), tz)) for name, tz in zones),
    ]
    text = "\n".join(line.rstrip() for line in lines)
    if _SENTINEL_RE.search(text):
        raise ValueError("a lead-data sentinel reached the value formats")
    return text


def _add_value_formats(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Append the value_formats variant to every extractable entry whose text
    carries a time or slot placeholder, and hash it with the rest. ``variables``
    stays what the template itself carries. If the block cannot be rendered,
    those entries become unextractable: fail closed."""
    needs = set(e["id"] for e in entries if e.get("extractable") and set(e["variables"]) & set(TIME_PLACEHOLDERS))
    if not needs:
        return entries
    try:
        block = value_formats_text()
    except Exception as exc:  # noqa: BLE001 - every entry that needs the block fails closed instead
        logger.warning("value formats could not be rendered: %s", exc)
        why = ("how times and slots are written could not be rendered (%s: %s), so the template cannot be "
               "stated in full" % (type(exc).__name__, exc))
        return [_unextractable(e["id"], e["kind"], e["source"], why, hook=e.get("hook")) if e["id"] in needs else e
                for e in entries]
    for e in entries:
        if e["id"] in needs:
            e["variants"] = list(e["variants"]) + [{"name": VALUE_FORMATS_VARIANT, "text": block}]
            e["review_text"] = compose_review_text(e["text"], e["variants"])
            e["sha256"] = text_hash(e["review_text"])
    return entries


# ------------------------------------------------------------ catalogue
EXCLUDED = (
    {"what": "show_rate unconfirmed_task", "source": "services/reply_engine/show_rate.py:render",
     "why": "a GHL task for Lorenzo; the suggested text inside it is sent by hand from his phone"},
    {"what": "no_show ns_call_task and ns_d1_other_channel_task", "source": "services/reply_engine/no_show.py:render",
     "why": "tasks for Lorenzo with a voicemail script and a suggested text he sends by hand"},
    {"what": "cadence day 6 channel_note", "source": "services/reply_engine/cadence.py:build_touch",
     "why": "a manual second-channel suggestion shown to Lorenzo, not sent by the engine"},
    {"what": "booking 'NOT SENT - for Lorenzo' card", "source": "services/reply_engine/booking.py:_unbookable_result",
     "why": "a card for Lorenzo, never prospect-facing"},
    {"what": "GHL appointment title ('Lorenzo <> {company}: 15-min ... plan')",
     "source": "services/reply_engine/booking.py:book",
     "why": "the calendar event title GHL shows on the invite; it is not an email body, and the invite itself is "
            "released only after the confirmation email is approved and sent"},
    {"what": "bodies Lorenzo edits on a card", "source": "services/reply_engine/approval.py:edit",
     "why": "hand-written text with no template to hash; an edited body is never auto-sent and always goes "
            "through a card"},
    {"what": "proposals and verbal-commit drafts", "source": "services/reply_engine/proposal.py",
     "why": "LLM-assembled documents Lorenzo pastes and sends himself; nothing in proposal.py sends"},
    {"what": "LLM-polished first replies", "source": "services/reply_engine/draft.py:build_draft",
     "why": "free text per lead; only the unpolished template (first_reply.*.full) can be approved"},
)


class _DummyLeadLogFilter(logging.Filter):
    """Drops only the 'booking refused for <dummy address>' line the catalogue's
    own render of booking._unbookable_result produces."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return DUMMY_LEAD_EMAIL not in record.getMessage()
        except Exception:  # noqa: BLE001 - never lose a real record over a formatting error
            return True


_CACHE = {"key": None, "entries": None}  # type: Dict[str, Any]
_SOURCE_MODULES = ("services.reply_engine.draft", "services.reply_engine.cadence", "services.reply_engine.booking",
                   "services.reply_engine.show_rate", "services.reply_engine.no_show", "services.reply_engine.app",
                   "services.reply_engine.models", "shared.slots", "shared.settings", RESEARCH_RULES_MODULE, __name__)


def _module_file(name: str) -> Optional[str]:
    """A module's source file, whether or not it is imported yet (find_spec
    locates it without running it), so the key is the same before and after a
    build that imports it."""
    mod = sys.modules.get(name)
    f = getattr(mod, "__file__", None) if mod is not None else None
    if f:
        return f
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    return spec.origin if spec is not None and spec.has_location else None


def _file_digest(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def _source_key() -> Tuple[Any, ...]:
    """A sha256 of the CONTENT of every file the catalogue is rendered from:
    the copy modules, every prompt file, config/offers.md and config/ids.json.
    Content, not mtime and size, so a same-size edit whose mtime was put back
    still invalidates the cache. A different prompts directory does too. Plus
    research_rules_fingerprint(): the rules module's RULES_TEXT, RULES_VERSION
    and whether it imports, as loaded now (a module with no file of its own,
    or one that appears or goes away, changes the key too)."""
    from services.reply_engine import cadence, show_rate
    from shared import paths

    files = [_module_file(name) or name for name in _SOURCE_MODULES]
    for d in sorted({str(cadence.PROMPTS_DIR), str(show_rate.PROMPTS_DIR)}):
        files.extend(str(p) for p in sorted(Path(d).glob("*.md")))
    files.extend([str(paths.OFFERS_PATH), str(paths.IDS_PATH)])
    key = [str(cadence.PROMPTS_DIR), str(show_rate.PROMPTS_DIR)]  # type: List[Any]
    key.extend((f, _file_digest(f)) for f in files)
    key.append(("research_rules", research_rules_fingerprint()))
    return tuple(key)


def clear_cache() -> None:
    _CACHE["key"] = None
    _CACHE["entries"] = None


def _build_catalogue() -> List[Dict[str, Any]]:
    booking_logger = logging.getLogger("reply_engine.booking")
    flt = _DummyLeadLogFilter()
    booking_logger.addFilter(flt)
    try:
        out = []  # type: List[Dict[str, Any]]
        for build in (_first_reply_entries, _cadence_entries, _cadence_fragments, _booking_entries,
                      _show_rate_entries, _no_show_entries, _first_reply_pieces):
            out.extend(build())
        out.extend(_guard(RESEARCH_RULES_ID, RESEARCH_RULES_KIND, RESEARCH_RULES_SOURCE, _research_rules_entries))
        out = _add_value_formats(out)
    finally:
        booking_logger.removeFilter(flt)
    seen = set()  # type: set
    for e in out:
        if e["id"] in seen:
            raise ValueError("duplicate template id %s" % e["id"])
        seen.add(e["id"])
    return out


CATALOGUE_BUILD_ATTEMPTS = 3


class CatalogueNotReady(RuntimeError):
    """An engine module the catalogue renders from is still being imported.

    Building then would read a half-initialised module (app.py without
    _already_booked_body, say), drop those ids and look like a catalogue
    change, which turns template auto-send off everywhere. So the catalogue
    is not built at all; callers fail closed and try again later."""


def sources_importing() -> List[str]:
    """The source modules that are mid-import in this process right now."""
    busy = []  # type: List[str]
    for name in _SOURCE_MODULES:
        if name == __name__:
            continue
        mod = sys.modules.get(name)
        spec = getattr(mod, "__spec__", None) if mod is not None else None
        if spec is not None and getattr(spec, "_initializing", False):
            busy.append(name)
    return busy


def catalogue() -> List[Dict[str, Any]]:
    """Every prospect-facing template the engine can send.

    Built once per process and cached, keyed on a content hash of the source
    files, so an edit to a prompt file or a copy module rebuilds it. Returns a
    deep copy. Each entry: id, kind, text, variants, review_text, variables,
    source, sha256 (of review_text), approvable, extractable, hook, notes (and
    explanation when not extractable; show_rate and no_show entries also carry
    applies_to, the [niche, offer] pairs the id covers, outside the hash).

    The key is taken BEFORE the build and checked again after it. A source
    that changed during the build means the build may mix old and new text,
    so it is neither cached nor returned: the catalogue is built again. If the
    sources never hold still, this raises (is_approved then fails closed).
    While a source module is still importing it raises CatalogueNotReady
    instead of building.
    """
    for _ in range(CATALOGUE_BUILD_ATTEMPTS):
        key = _source_key()
        if _CACHE["entries"] is not None and _CACHE["key"] == key:
            return copy_mod.deepcopy(_CACHE["entries"])
        busy = sources_importing()
        if busy:
            raise CatalogueNotReady("not building the template catalogue while %s is still importing"
                                    % ", ".join(busy))
        entries = _build_catalogue()
        if _source_key() == key:
            # Entries before key: a reader that sees the new key sees them.
            _CACHE["entries"] = entries
            _CACHE["key"] = key
            return copy_mod.deepcopy(entries)
        logger.info("a template source file changed during the catalogue build; building it again")
    raise RuntimeError("the template source files kept changing during %d catalogue builds"
                       % CATALOGUE_BUILD_ATTEMPTS)


def catalogue_index(entries: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    return {e["id"]: e for e in (entries if entries is not None else catalogue())}


def fill(text: str, **values: Any) -> str:
    """Put values into a catalogue text's placeholders (unknown ones stay)."""
    return _PLACEHOLDER_RE.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text or "")


# ---------------------------------------------------------------- hashes
def normalise(text: str) -> str:
    """Line endings unified, trailing spaces per line dropped, runs of blank
    lines collapsed to one, ends stripped. Paragraph structure still counts."""
    lines = [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


# ------------------------------------------------------------- the file
def _path(path: Optional[Any] = None) -> Path:
    return Path(path) if path is not None else Path(APPROVALS_PATH)


def empty_approvals() -> Dict[str, Any]:
    return {"version": FILE_VERSION, "approvals": {}}


def load_approvals(path: Optional[Any] = None) -> Dict[str, Any]:
    """The approvals file; a missing file is an empty registry. A file that is
    not valid JSON or has the wrong shape raises ValueError (callers that gate
    a send treat that as 'not approved')."""
    p = _path(path)
    if not p.exists():
        return empty_approvals()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError("%s is not valid JSON: %s" % (p, exc))
    if not isinstance(data, dict) or not isinstance(data.get("approvals", {}), dict):
        raise ValueError("%s must be an object with an 'approvals' object" % p)
    data.setdefault("version", FILE_VERSION)
    data.setdefault("approvals", {})
    return data


def save_approvals(data: Dict[str, Any], path: Optional[Any] = None) -> Path:
    """Write atomically: a temp file in the same directory, fsync, os.replace."""
    if not isinstance(data, dict) or not isinstance(data.get("approvals"), dict):
        raise ValueError("approvals data must be an object with an 'approvals' object")
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".%s." % p.name, suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(p))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return p


def _preview(text: str, limit: int = 120) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


def _now_iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()


# --------------------------------------------------------------- status
def status(template_id: str, entries: Optional[Dict[str, Dict[str, Any]]] = None,
           approvals: Optional[Dict[str, Any]] = None, path: Optional[Any] = None) -> str:
    index = entries if entries is not None else catalogue_index()
    entry = index.get(template_id)
    if entry is None:
        return STATUS_UNKNOWN
    data = approvals if approvals is not None else load_approvals(path)
    rec = (data.get("approvals") or {}).get(template_id)
    if not rec:
        return STATUS_UNAPPROVED
    if not entry.get("extractable") or entry.get("sha256") is None:
        return STATUS_CHANGED
    return STATUS_APPROVED if rec.get("sha256") == entry["sha256"] else STATUS_CHANGED


def is_approved(template_id: str, path: Optional[Any] = None) -> bool:
    """True only when the template's current text (every variant included)
    hashes to the approved hash. Any error is False: fail closed."""
    try:
        index = catalogue_index()
        entry = index.get(template_id)
        if entry is None or not entry.get("approvable"):
            return False
        return status(template_id, entries=index, path=path) == STATUS_APPROVED
    except Exception as exc:  # noqa: BLE001
        logger.warning("is_approved(%s) failed closed: %s", template_id, exc)
        return False


def kill_switch_on(path: Optional[Any] = None) -> bool:
    """True when template auto-send is switched off.

    Env AUTO_SEND_TEMPLATES: unset leaves it to the file; set to 1/on/true/yes
    leaves auto-send on; ANY other value (0, off, a typo, empty) is the kill
    switch. File: "auto_send" absent or the JSON literal true leaves it on; any
    other value is the kill switch. An unreadable file is the kill switch too."""
    raw = os.environ.get(KILL_SWITCH_ENV)
    if raw is not None and raw.strip().lower() not in KILL_SWITCH_ENABLE_VALUES:
        return True
    try:
        data = load_approvals(path)
    except ValueError:
        return True
    return "auto_send" in data and data["auto_send"] is not True


def auto_send_allowed(template_id: str, path: Optional[Any] = None) -> bool:
    """Kill switch off AND the template approved and unchanged.

    NOT a send gate: it checks no parity, no render stamp, no classification,
    no copy rules and not whether the text sent is the template. The send
    paths ask services/reply_engine/template_gate.py (draft_verdict,
    touch_verdict, appointment_touch_verdict) and nothing else."""
    return (not kill_switch_on(path)) and is_approved(template_id, path=path)


# ------------------------------------------------------ approve / revoke
class ApprovalError(Exception):
    """An approve or revoke request that cannot be applied as asked."""


def plan_approve(ids: List[str], entries: Dict[str, Dict[str, Any]], approvals: Dict[str, Any],
                 expected: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """What approving ``ids`` would change. ``expected`` maps id -> hash the
    approver saw (an exported review file); a mismatch refuses everything."""
    problems = []  # type: List[str]
    changed = []  # type: List[str]
    plan = []  # type: List[Dict[str, Any]]
    for tid in ids:
        entry = entries.get(tid)
        if entry is None:
            problems.append("%s: unknown id" % tid)
            continue
        if not entry.get("extractable"):
            problems.append("%s: not extractable (%s)" % (tid, entry.get("explanation", "")))
            continue
        if not entry.get("approvable"):
            problems.append("%s: a reference piece, approve the full template instead" % tid)
            continue
        if expected is not None and expected.get(tid) != entry["sha256"]:
            changed.append(tid)
            continue
        before = status(tid, entries=entries, approvals=approvals)
        plan.append({"id": tid, "before": before, "sha256": entry["sha256"], "text": entry["text"]})
    if changed:
        raise ApprovalError("these templates changed since the review file was exported; re-export and review "
                            "again: %s" % ", ".join(changed))
    if problems:
        raise ApprovalError("; ".join(problems))
    return plan


def apply_approve(plan: List[Dict[str, Any]], approvals: Dict[str, Any], approved_by: str,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    data = json.loads(json.dumps(approvals))
    data.setdefault("version", FILE_VERSION)
    recs = data.setdefault("approvals", {})
    for item in plan:
        if item["before"] == STATUS_APPROVED:
            continue
        recs[item["id"]] = {"sha256": item["sha256"], "approved_at": _now_iso(now), "approved_by": approved_by,
                            "text_preview": _preview(item["text"])}
    return data


def approve(ids: List[str], approved_by: str, path: Optional[Any] = None, now: Optional[datetime] = None,
            expected: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Approve and save. Returns the plan (with each id's status before)."""
    entries = catalogue_index()
    approvals = load_approvals(path)
    plan = plan_approve(ids, entries, approvals, expected=expected)
    save_approvals(apply_approve(plan, approvals, approved_by, now=now), path)
    return plan


def plan_revoke(ids: List[str], approvals: Dict[str, Any]) -> List[str]:
    recs = approvals.get("approvals") or {}
    missing = [tid for tid in ids if tid not in recs]
    if missing:
        raise ApprovalError("no approval on record for: %s" % ", ".join(missing))
    return list(ids)


def apply_revoke(ids: List[str], approvals: Dict[str, Any]) -> Dict[str, Any]:
    data = json.loads(json.dumps(approvals))
    for tid in ids:
        (data.get("approvals") or {}).pop(tid, None)
    return data


def revoke(ids: List[str], path: Optional[Any] = None) -> List[str]:
    approvals = load_approvals(path)
    plan = plan_revoke(ids, approvals)
    save_approvals(apply_revoke(plan, approvals), path)
    return plan


# ------------------------------------------------------------- markdown
MARKER_RE = re.compile(r"^<!--\s*approve-template\s+id=(\S+)\s+sha256=([0-9a-f]{64})\s*-->\s*$")
FENCE_OPEN = "```text"
FENCE_CLOSE = "```"


def parse_exported_blocks(markdown: str) -> List[Dict[str, Any]]:
    """Every approve marker in an exported review file, in order, with the
    fenced text block that follows it: [{"id", "marker_sha256", "text"}].
    ``text`` is None when the marker is not followed (after blank lines) by a
    ```text block closed by a ``` line."""
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    out = []  # type: List[Dict[str, Any]]
    i = 0
    while i < len(lines):
        m = MARKER_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        text = None
        if j < len(lines) and lines[j].strip() == FENCE_OPEN:
            k = j + 1
            body = []  # type: List[str]
            while k < len(lines) and lines[k].strip() != FENCE_CLOSE:
                body.append(lines[k])
                k += 1
            if k < len(lines):
                text = "\n".join(body)
                j = k
        out.append({"id": m.group(1), "marker_sha256": m.group(2), "text": text})
        i = j + 1 if text is not None else i + 1
    return out


def parse_exported(markdown: str) -> Dict[str, str]:
    """id -> marker sha256 for every template marker in an exported review file."""
    return dict((b["id"], b["marker_sha256"]) for b in parse_exported_blocks(markdown))


def verify_exported(markdown: str, entries: Optional[Dict[str, Dict[str, Any]]] = None) -> Tuple[Dict[str, str], List[str]]:
    """(id -> hash, problems) for an exported review file. A block is only
    accepted when the hash of its shown text equals its marker hash AND the
    current catalogue hash. Any problem refuses the whole file."""
    index = entries if entries is not None else catalogue_index()
    blocks = parse_exported_blocks(markdown)
    problems = []  # type: List[str]
    shown = {}  # type: Dict[str, str]
    if not blocks:
        problems.append("the file has no approve-template markers (export it with --export)")
    for b in blocks:
        tid = b["id"]
        if tid in shown:
            problems.append("%s: appears more than once" % tid)
            continue
        if b["text"] is None:
            problems.append("%s: marker has no text block" % tid)
            continue
        h = text_hash(b["text"])
        if h != b["marker_sha256"]:
            problems.append("%s: the text shown does not match its marker hash (edited after export)" % tid)
            continue
        entry = index.get(tid)
        if entry is None:
            problems.append("%s: unknown id" % tid)
            continue
        if h != entry.get("sha256"):
            problems.append("%s: changed since the review file was exported" % tid)
            continue
        shown[tid] = h
    return shown, problems


def render_catalogue_markdown(entries: Optional[List[Dict[str, Any]]] = None, path: Optional[Any] = None,
                              now: Optional[datetime] = None) -> str:
    items = entries if entries is not None else catalogue()
    index = catalogue_index(items)
    try:
        approvals = load_approvals(path)
        file_note = ""
    except ValueError as exc:
        approvals = empty_approvals()
        file_note = "\n**Warning:** the approvals file could not be read (%s); every status below shows unapproved.\n" % exc
    by_kind = {}  # type: Dict[str, List[Dict[str, Any]]]
    for e in items:
        by_kind.setdefault(e["kind"], []).append(e)
    kinds = [k for k in KIND_ORDER if k in by_kind] + sorted(k for k in by_kind if k not in KIND_ORDER)

    lines = [
        "# Cold-email templates for approval",
        "",
        "Generated %s." % _now_iso(now),
        "",
        "Approving a template means every email of that type sends automatically, without a per-email "
        "Approve, for as long as its text stays exactly as shown here. The safety checks stay on for every "
        "send: the send window, the slot rules, the offers.md copy gate, the recipient check and the kill "
        "switch. If the wording changes in code or in a prompt file, the template drops back to "
        "\"changed_since_approval\" and goes back to a card until it is approved again.",
        "",
        "Each block shows the main template and then every variant the same email can go out as: missing "
        "lead data, no free slot, another timezone, the fallback subject. Approving an id approves all of the "
        "text in its block. Placeholders like `{first_name}` are filled per lead. Only templates with an "
        "approve marker can be approved; reference pieces and unextractable entries are listed for context.",
        "",
        "Every template with a time or slot in it ends with a value_formats block: how the engine writes "
        "those times, rendered by its own code at fixed example times. It is the same block each time, and "
        "it is part of what you approve, so a change to how times are written sends every one of those "
        "templates back for approval.",
        "",
        "To approve everything in this file exactly as shown, from your own terminal (refused if any text "
        "was edited in this file or changed in the code since export):",
        "",
        "    python3 jobs/approve_templates.py --approve-all-shown <this file>",
        "",
        "Kill switch: %s." % ("ON (auto-send off)" if kill_switch_on(path) else "off"),
        file_note,
        "## Counts",
        "",
    ]
    for kind in kinds:
        lines.append("- %s: %d" % (kind, len(by_kind[kind])))
    lines.append("- total: %d" % len(items))
    lines.append("- approvable: %d" % sum(1 for e in items if e.get("approvable")))
    lines.append("")
    for kind in kinds:
        lines += ["## %s" % KIND_TITLES.get(kind, kind), ""]
        for e in by_kind[kind]:
            st = status(e["id"], entries=index, approvals=approvals)
            lines += ["### `%s`" % e["id"], ""]
            lines.append("- status: %s" % st)
            lines.append("- variables: %s" % (", ".join("`{%s}`" % v for v in e["variables"]) or "none"))
            if e.get("variants"):
                lines.append("- variants: %s" % ", ".join(v["name"] for v in e["variants"]))
            lines.append("- source: `%s`" % e["source"])
            if e.get("hook"):
                lines.append("- sent from: `%s`" % e["hook"])
            if e.get("notes"):
                lines.append("- notes: %s" % e["notes"])
            if not e.get("extractable"):
                lines.append("- not extractable: %s" % e.get("explanation", ""))
            elif not e.get("approvable"):
                lines.append("- reference only, not approved on its own")
            else:
                lines.append("- sha256: `%s`" % e["sha256"])
            lines.append("")
            if e.get("extractable"):
                if e.get("approvable"):
                    lines += ["<!-- approve-template id=%s sha256=%s -->" % (e["id"], e["sha256"]), ""]
                lines += [FENCE_OPEN, e["review_text"].rstrip("\n"), FENCE_CLOSE, ""]
    lines += ["## Not in the catalogue", "",
              "These are not prospect-facing or are never auto-sent by the engine:", ""]
    for ex in EXCLUDED:
        lines.append("- %s (`%s`): %s" % (ex["what"], ex["source"], ex["why"]))
    lines.append("")
    placeholders = sorted(set(v for e in items for v in e["variables"]))
    lines += ["## Placeholders", "",
              "The examples here are a guide only. The exact time and slot formats are in each template's "
              "value_formats block, which is approved with it.", ""]
    for v in placeholders:
        lines.append("- `{%s}`: %s" % (v, VARIABLE_NOTES.get(v, "")))
    lines.append("")
    return "\n".join(lines)
