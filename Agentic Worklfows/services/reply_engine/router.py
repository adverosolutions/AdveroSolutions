"""Route a classified reply into GHL and Instantly through the guarded
clients. In shadow every write returns a would_do record and no HTTP request
is made; the returned Action list is what the shadow log and the replay
summary are built from.

Mapping (config/ids.json stages):
  positive_*          -> contact upsert (tags cold-email, instantly-positive-reply, niche, campaign key),
                         opportunity New Reply/Lead, Instantly interest 1; referral adds task "Ask for intro"
  neutral_question    -> contact upsert + New Reply/Lead (no interest change)
  negative_notnow     -> Follow Up Later + dated task, Instantly -1
  negative_notfit     -> Lost (reason in note), Instantly -1
  negative_hostile / unsubscribe -> Lost + Instantly blocklist + tag dnd, Instantly -1
  wrong_person        -> Lost + note (named contact queued for the list factory), Instantly -2
  ooo                 -> Instantly 0, cadence resume date; no GHL
  auto_reply_unmonitored -> recorded for the deliverability monitor (M1 level 4); no GHL, no Instantly

A stale reply rewrites nothing (stale_reason, _route_stale): one the lead sent
before their opt-out, or, unless it is an opt-out itself, one sent before a
newer human reply of theirs already on the row (sent_before_a_newer_reply).
The sticky opt-out marker's rules are next_opt_out_marker.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from shared import settings, slots

from services.reply_engine.classify import REFERRAL_RE, core_text, explicit_removal, has_positive_cue
from services.reply_engine.models import (
    BLOCKLIST_LABELS,
    INTEREST_FOR_LABEL,
    POSITIVE_LABELS,
    RECEIVED_AT_EMAIL,
    RECEIVED_AT_PROCESSING,
    STAGE_FOR_LABEL,
    Action,
    Classification,
    LeadState,
    ReplyEvent,
    entry_email_time,
    iso_utc,
    opt_out_marker,
    opt_out_received_at,
    parse_time,
    reply_received_at,
)

logger = logging.getLogger("reply_engine.router")

# A lead in one of these has been decided: booked, removed, lost, wrong
# person, not now, or a withheld blocklist waiting on a human. An auto-reply
# that lands after the human reply that decided it (an out-of-office fired by
# the lead's own "remove me") must not overwrite that with "ooo" or
# "auto_reply": the cadence's stop_reason reads the status, so a blocklisted
# or lost lead read as a mere pause, and the Instantly interest the decision
# set (-1, -2, 2) was reset to 0. Mirrors cadence's BOOKED / UNSUBSCRIBE /
# HOSTILE / NOT_NOW status sets (router does not import cadence; a test
# pins the two together).
FINAL_STATUSES = (
    "booked", "call_booked", "meeting_booked", "meeting_completed", "won", "closed",
    "unsubscribe", "unsubscribed", "blocklisted",
    "negative_hostile", "hostile", "lost", "negative_notfit", "wrong_person",
    "negative_notnow", "not_now", "follow_up_later",
    "needs_review",
)


# The part of FINAL_STATUSES that is the lead saying no: removed, hostile,
# lost / not a fit, wrong person, not now, or a withheld blocklist waiting on
# a human. The booked statuses are left out (a booking confirmation card must
# still go out). No approved reply may be sent to a lead whose row carries
# one of these, and no card answers a reply with one of these labels
# (approval.lead_reply_hold; app holds the lead's open cards when one lands).
BOOKED_FINAL_STATUSES = ("booked", "call_booked", "meeting_booked", "meeting_completed", "won", "closed")
OPT_OUT_STATUSES = tuple(s for s in FINAL_STATUSES if s not in BOOKED_FINAL_STATUSES)
OPT_OUT_LABELS = ("unsubscribe", "negative_hostile", "wrong_person", "negative_notfit", "negative_notnow")


def has_final_status(state: LeadState) -> bool:
    return str(getattr(state, "status", "") or "").strip().lower() in FINAL_STATUSES


# Labels a machine writes (an out-of-office, an unmonitored mailbox), never the
# lead: cadence.AUTO_REPLY_STATUSES, which router does not import (a test pins
# the two together).
MACHINE_LABELS = ("ooo", "auto_reply", "auto_reply_unmonitored")


def _norm_label(label: Any) -> str:
    return str(label or "").strip().lower()


# ------------------------------------------ replies processed out of order
# The poller retries a reply whose processing raised, and skips one a killed
# run still holds, so a reply the lead sent earlier can be processed after a
# newer one. Such a reply is stale (stale_reason): it is recorded and
# rewrites nothing (app._record_stale_reply, _route_stale).
#   STALE_OPT_OUT      sent before the lead's opt-out (the sticky marker),
#                      whatever its label, an opt-out's included;
#   STALE_OLDER_REPLY  not an opt-out, and sent before a newer human reply of
#                      the lead's already on the row. An opt-out sent before a
#                      newer reply is not stale: it still takes effect and
#                      sets the marker (next_opt_out_marker).
STALE_OPT_OUT = "opt_out"
STALE_OLDER_REPLY = "older_than_newest_reply"
STALE_REASONS = (STALE_OPT_OUT, STALE_OLDER_REPLY)


def after_opt_out(marker: Any, received_at: datetime, source: Optional[str] = RECEIVED_AT_EMAIL) -> bool:
    """True only when a reply sent at ``received_at`` is PROVABLY later than
    the opt-out ``marker`` records: the email's own time (not a processing
    stand-in), strictly after the marker's received_at. An unreadable marker
    time proves nothing."""
    if str(source or RECEIVED_AT_EMAIL) != RECEIVED_AT_EMAIL:
        return False
    opted = opt_out_received_at(marker)
    return opted is not None and slots.ensure_aware(received_at) > opted


def stale_reason(state: Any, label: Any, received_at: datetime, source: Optional[str] = RECEIVED_AT_EMAIL,
                 email_id: Optional[str] = None) -> Optional[str]:
    """Why this reply is stale, or None when it is not:

    * ``opt_out`` (STALE_OPT_OUT): the row carries an opt-out marker
      (LeadState.opt_out) and this reply is not provably later than it (sent
      before it, at the same moment, or with only a processing time),
      whatever its label, an opt-out's included (the marker keeps the later
      one);
    * ``older_than_newest_reply`` (STALE_OLDER_REPLY): this reply is not an
      opt-out, it carries the email's own time, and a human reply the lead
      sent strictly later (by that email's own time) is already on the row
      (sent_before_a_newer_reply). A reply with only a processing time cannot
      be shown to be older, so it is processed as a new one.

    A stale reply is recorded and rewrites nothing: no status,
    classification, booking or cadence change, no draft, no card, no card of
    the lead's superseded (app._record_stale_reply, _route_stale). An opt-out
    is never stale for a newer reply: it takes effect and sets the marker
    (next_opt_out_marker), and app holds the lead's open cards for it.
    ``email_id`` is the reply's own id: an entry for the same email (a retry)
    is never "newer"."""
    marker = opt_out_marker(state)
    if marker is not None and not after_opt_out(marker, received_at, source):
        return STALE_OPT_OUT
    if (str(source or RECEIVED_AT_EMAIL) == RECEIVED_AT_EMAIL
            and sent_before_a_newer_reply(state, label, received_at, email_id=email_id)):
        return STALE_OLDER_REPLY
    return None


def newer_replies(state: Any, received_at: datetime, email_id: Optional[str] = None,
                  include_opt_outs: bool = True) -> List[Dict[str, Any]]:
    """The inbound history entries of human replies (not a machine's) the
    lead SENT strictly after ``received_at``, by each email's own time, oldest
    first. ``state`` is a LeadState or a stored row. The entry for
    ``email_id`` (the reply being processed) is skipped, and so are the
    opt-outs unless ``include_opt_outs``. An entry with no received_at
    (written before it existed) or only a processing time cannot show that
    its reply is newer, so it never counts."""
    history = state.get("history") if isinstance(state, dict) else getattr(state, "history", None)
    received = slots.ensure_aware(received_at)
    out = []  # type: List[Any]
    for entry in list(history or []):
        if not isinstance(entry, dict) or entry.get("event") != "inbound":
            continue
        if email_id is not None and str(entry.get("email_id")) == str(email_id):
            continue
        label = _norm_label(entry.get("label"))
        if label in MACHINE_LABELS or (not include_opt_outs and label in OPT_OUT_LABELS):
            continue
        sent = entry_email_time(entry)
        if sent is not None and sent > received:
            out.append((sent, len(out), entry))
    return [entry for _sent, _i, entry in sorted(out, key=lambda item: (item[0], item[1]))]


def sent_before_a_newer_reply(state: Any, label: Any, received_at: datetime,
                              email_id: Optional[str] = None) -> bool:
    """True when this reply is not an opt-out and a human reply the lead sent
    strictly later (newer_replies: by the email's own time, a machine's reply
    never counts) is already on the row's history. Such a reply is stale
    (stale_reason: STALE_OLDER_REPLY, when its own time is the email's). An
    opt-out always takes effect, whatever came after it."""
    if _norm_label(label) in OPT_OUT_LABELS:
        return False
    return bool(newer_replies(state, received_at, email_id=email_id))


def next_opt_out_marker(current: Any, label: Any, email_id: Optional[str], received_at: datetime,
                        source: Optional[str], now: datetime) -> Optional[Dict[str, Any]]:
    """The lead's opt-out marker once this reply is processed:

    * an opt-out label (OPT_OUT_LABELS) sets it to this reply, unless the
      current marker records a later one;
    * a human reply (not a machine's, not an opt-out) PROVABLY sent after the
      marker (after_opt_out) clears it;
    * anything else leaves it as it is. An older reply never clears it,
      whatever order the replies are processed in.

    Applied under the row's lock to the marker as stored (app._inbound_stop_hook),
    never to a copy read earlier."""
    norm = _norm_label(label)
    if not norm:
        return current
    received = slots.ensure_aware(received_at)
    if norm in OPT_OUT_LABELS:
        opted = opt_out_received_at(current)
        if current and opted is not None:
            if opted > received:
                return current
            if opted == received and str(current.get("email_id")) == str(email_id):
                return current  # the same reply again: keep when it was set
        marker = {"label": norm, "email_id": None if email_id is None else str(email_id),
                  "received_at": iso_utc(received), "set_at": slots.to_tz(slots.ensure_aware(now)).isoformat()}
        if str(source or RECEIVED_AT_EMAIL) == RECEIVED_AT_PROCESSING:
            marker["received_at_source"] = RECEIVED_AT_PROCESSING
        return marker
    if not current or norm in MACHINE_LABELS:
        return current
    return None if after_opt_out(current, received, source) else current


def implied_opt_out(history: Any) -> Optional[Dict[str, Any]]:
    """The opt-out the inbound history implies by the time each reply was
    sent: the latest opt-out entry that carries a received_at, when no human
    non-opt-out reply was provably sent after it. None otherwise.

    Under sequential processing next_opt_out_marker never leaves the marker
    absent while this is not None. It puts back a marker that a concurrent
    first write of the row dropped (two pipelines that both read no row: the
    three-way merge then lets the later writer's empty field win), because
    the history is combined across writers and never loses an entry."""
    entries = [e for e in (history or []) if isinstance(e, dict) and e.get("event") == "inbound"]
    latest = None  # type: Optional[Dict[str, Any]]
    latest_at = None  # type: Optional[datetime]
    for entry in entries:
        if _norm_label(entry.get("label")) not in OPT_OUT_LABELS:
            continue
        at = parse_time(entry.get("received_at"))
        if at is not None and (latest_at is None or at >= latest_at):
            latest, latest_at = entry, at
    if latest is None:
        return None
    for entry in entries:
        norm = _norm_label(entry.get("label"))
        if norm in OPT_OUT_LABELS or norm in MACHINE_LABELS:
            continue
        sent = entry_email_time(entry)
        if sent is not None and sent > latest_at:
            return None
    marker = {"label": _norm_label(latest.get("label")), "email_id": latest.get("email_id"),
              "received_at": iso_utc(latest_at), "set_at": latest.get("at")}
    if str(latest.get("received_at_source") or RECEIVED_AT_EMAIL) == RECEIVED_AT_PROCESSING:
        marker["received_at_source"] = RECEIVED_AT_PROCESSING
    return marker


TAG_COLD = "cold-email"
TAG_POSITIVE = "instantly-positive-reply"
TAG_DND = "dnd"
AUTO_RESPONDERS_KEY = "auto_responders"
LIST_FACTORY_QUEUE_KEY = "list_factory_queue"


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# "Please email the following to get to the right place  Daryl Ayers: dayers@..."
_NAMED_ADDRESS_RE = re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){0,2})\s*[:\-]\s*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")


def handover_contacts(body: str, sender_email: str) -> List[Dict[str, Any]]:
    """Named contacts an auto-responder hands the conversation over to.

    Two of the 44 recorded replies are auto-responders whose whole content is a
    hand-off ("our email has changed ... Daryl Ayers: dayers@ayerspartners.com",
    "I have moved to a limited capacity role, please reach out to Gary or
    Dustin"). router.route() returned after recording {at, campaign_id, email,
    subject}, so the only place that contact ever existed - the reply body - was
    discarded: no list-factory row, no wrong_person, nothing the deliverability
    monitor could recover. offers.md rule 7 says a named new contact is queued
    for the list factory.
    """
    text = body or ""
    sender = (sender_email or "").strip().lower()
    sender_domain = sender.split("@")[-1] if "@" in sender else ""
    out = []  # type: List[Dict[str, Any]]
    seen = set()  # type: set
    for m in _NAMED_ADDRESS_RE.finditer(text):
        address = m.group(2).strip().lower()
        if address == sender or address in seen:
            continue
        seen.add(address)
        out.append({"name": m.group(1).strip(), "email": address})
    for m in _EMAIL_RE.finditer(text):
        address = m.group(0).strip().lower()
        if address == sender or address in seen:
            continue
        seen.add(address)
        out.append({"name": None, "email": address})
    if not out:
        # No address in the body, but a name may still be there ("reach out to
        # Gary or Dustin"): queue the name so the list factory can find them.
        ref = REFERRAL_RE.search(text)
        if ref:
            out.append({"name": ref.group(1).strip(), "email": None,
                        "note": "named in an auto-responder with no address; find the address before any outreach"})
    if sender_domain:
        for row in out:
            row["same_domain"] = bool(row.get("email") and row["email"].endswith("@" + sender_domain))
    return out


def _action(system: str, action: str, payload: Dict[str, Any], result: Any, note: str = "") -> Action:
    if isinstance(result, dict) and result.get("shadow") is True:
        kind = "would_do"
    elif result is None:
        kind = "skipped"
    else:
        kind = "done"
    res = result if isinstance(result, dict) else ({"raw": result} if result is not None else None)
    return Action(system=system, action=action, payload=payload, result=res, kind=kind, note=note)


def _call(system: str, action: str, payload: Dict[str, Any], fn, note: str = ""):
    """One guarded write, plus its Action record.

    shared.ghl now raises when a live write has no token (so a booking can never
    be reported as real with nothing behind it). One failed CRM write must not
    abort the whole reply: the claim for this email id is already persisted, so
    an exception escaping route() would lose the lead's words entirely. The
    failure becomes a 'failed' Action that the shadow log, the replay summary
    and the Job_Log row all carry.
    """
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - a CRM outage must not lose a reply
        logger.error("%s.%s failed for this reply: %s", system, action, exc)
        return Action(system=system, action=action, payload=payload, result={"error": str(exc)}, kind="failed",
                      note=("%s; " % note if note else "") + "client error: %s" % str(exc)[:200]), None
    return _action(system, action, payload, result, note=note), result


def _id_from(result: Any, *paths) -> Optional[str]:
    """Pull an id out of a live GHL response; None for shadow records."""
    if not isinstance(result, dict) or result.get("shadow"):
        return None
    for path in paths:
        cur = result  # type: Any
        for part in path:
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
                break
        if cur:
            return str(cur)
    return None


def _due_iso(d: datetime, hour: int = 10) -> str:
    naive = datetime(d.year, d.month, d.day, hour, 0)
    return slots.TZ.localize(naive).isoformat()


def _contact_name(event: ReplyEvent) -> str:
    parts = [p for p in (event.first_name, event.last_name) if p]
    return " ".join(parts) if parts else event.lead_email


def opportunity_name(event: ReplyEvent) -> str:
    company = event.company or event.lead_email.split("@")[-1].split(".")[0].title()
    return "%s - %s (Cold Email)" % (company, _contact_name(event))


def tags_for(event: ReplyEvent, classification: Classification) -> List[str]:
    tags = [TAG_COLD]
    if event.niche:
        tags.append(event.niche)
    if event.campaign_key:
        tags.append(event.campaign_key)
    if classification.label in POSITIVE_LABELS:
        tags.append(TAG_POSITIVE)
    if classification.label in BLOCKLIST_LABELS:
        tags.append(TAG_DND)
    if classification.label == "wrong_person":
        tags.append("wrong-person")
    return tags


def _status_kept(state: LeadState, label: str) -> Action:
    return Action(system="store", action="status_kept", payload={"status": state.status, "label": label},
                  kind="skipped",
                  note="an auto-reply after the lead's own reply does not reopen a decided lead (%s)" % state.status)


def _route_stale(event: ReplyEvent, classification: Classification, state: LeadState, ghl, instantly,
                 now: datetime, store, stale: str) -> List[Action]:
    """A stale reply (stale_reason): one sent before the lead's opt-out, or
    one that is not an opt-out, sent before a newer human reply of theirs
    already on the row.

    Nothing on ``state`` moves: status, classification, cadence and
    last_inbound_at stay what the opt-out or the newer reply made them, and
    no CRM stage or Instantly interest is rewritten from older words. Two
    things still happen, each on a scratch copy of the row: a removal request
    (BLOCKLIST_LABELS) is applied, because a lead who asked to be removed is
    removed whatever else they wrote, and an auto-responder's hand-off to a
    named contact is queued for the list factory (offers.md rule 7). The CRM
    ids a live write returned are kept; nothing else of the copy is."""
    label = classification.label
    received, _source = reply_received_at(event, now)
    if stale == STALE_OLDER_REPLY:
        note = "sent before a newer reply of the lead's: their status, classification and cadence are kept"
    else:
        note = "sent before the lead's opt-out: their status, classification and cadence are kept"
    actions = [Action(system="store", action="stale_reply",
                      payload={"label": label, "stale": stale, "received_at": iso_utc(received),
                               "status": state.status},
                      kind="skipped", note=note)]  # type: List[Action]
    if label in BLOCKLIST_LABELS or label == "auto_reply_unmonitored":
        scratch = state.model_copy(deep=True)
        actions += route(event, classification, scratch, ghl, instantly, now=now, store=store, stale=None)
        state.ghl_contact_id = state.ghl_contact_id or scratch.ghl_contact_id
        state.ghl_opportunity_id = state.ghl_opportunity_id or scratch.ghl_opportunity_id
    return actions


_DECIDE = object()


def route(
    event: ReplyEvent,
    classification: Classification,
    state: LeadState,
    ghl,
    instantly,
    now: Optional[datetime] = None,
    store=None,
    stale: Any = _DECIDE,
) -> List[Action]:
    """``stale``: stale_reason's verdict for this reply (None: not stale).
    Left out, route() decides it from ``state`` itself, so no caller can let
    a stale reply (sent before the lead's opt-out, or before a newer human
    reply of theirs already on the row) rewrite the row; a stale reply goes
    to _route_stale."""
    now = slots.ensure_aware(now) if now is not None else event.received_at
    label = classification.label
    ex = classification.extracted
    actions = []  # type: List[Action]
    received, source = reply_received_at(event, now)
    if stale is _DECIDE:
        stale = stale_reason(state, label, received, source, email_id=event.email_id)
    if stale:
        return _route_stale(event, classification, state, ghl, instantly, now, store, stale)
    state.classification = classification
    state.last_inbound_at = event.received_at.isoformat()

    # ---- auto responders: no GHL, no drafts
    if label == "auto_reply_unmonitored":
        body = core_text(event.text)[:1500]
        handovers = handover_contacts(body, event.lead_email)
        record = {"email": event.lead_email, "campaign_id": event.campaign_id, "at": event.received_at.isoformat(),
                  "subject": event.subject, "body": body, "handover_contacts": handovers}
        if store is not None:
            try:
                store.append(AUTO_RESPONDERS_KEY, record)
            except Exception as exc:  # noqa: BLE001
                logger.warning("store append failed: %s", exc)
            # offers.md rule 7: a named new contact is queued for the list
            # factory, never emailed from this thread.
            for contact in handovers:
                queued = {"email": event.lead_email, "company": event.company, "named_contact": contact.get("name"),
                          "named_email": contact.get("email"), "campaign_id": event.campaign_id,
                          "at": event.received_at.isoformat(), "source": "auto_responder_handover"}
                try:
                    store.append(LIST_FACTORY_QUEUE_KEY, queued)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("store append failed: %s", exc)
        actions.append(Action(system="store", action="record_auto_responder", payload=record, kind="done",
                              note="feeds deliverability monitor M1 level 4"))
        if handovers:
            actions.append(Action(system="store", action="queue_list_factory",
                                  payload={"handover_contacts": handovers, "from": event.lead_email}, kind="done",
                                  note="auto-responder handed the conversation to a named contact"))
        if has_final_status(state):
            actions.append(_status_kept(state, label))
            return actions
        state.status = "auto_reply"
        return actions

    if label == "ooo" and has_final_status(state):
        # Recorded (the history entry carries the label), nothing else moves:
        # no status, no cadence pause, no Instantly interest reset.
        actions.append(_status_kept(state, label))
        return actions

    if label == "ooo":
        resume = ex.return_date or (event.received_at + timedelta(days=7)).date().isoformat()
        state.cadence = dict(state.cadence, paused=True, resume_at=resume, reason="ooo")
        state.status = "ooo"
        if instantly is not None:
            act, res = _call("instantly", "update_interest_status", {"lead_email": event.lead_email, "interest_value": 0},
                             lambda: instantly.update_interest_status(event.lead_email, event.campaign_id, 0),
                             note="ooo; resume %s" % resume)
        else:
            act = _action("instantly", "update_interest_status", {"lead_email": event.lead_email, "interest_value": 0}, None,
                          note="ooo; resume %s" % resume)
        actions.append(act)
        return actions

    # ---- GHL contact
    contact_id = state.ghl_contact_id
    if contact_id is None and ghl is not None and getattr(ghl, "has_token", False):
        try:
            found = ghl.search_contacts(event.lead_email)
            if isinstance(found, dict) and found.get("contacts"):
                contact_id = str(found["contacts"][0].get("id") or "") or None
                if contact_id:
                    state.ghl_contact_id = contact_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("GHL search_contacts failed: %s", exc)
    if ghl is not None:
        act, upsert = _call("ghl", "upsert_contact", {"email": event.lead_email, "tags": tags_for(event, classification)},
                            lambda: ghl.upsert_contact(event.lead_email, first_name=event.first_name, last_name=event.last_name,
                                                       company=event.company, phone=ex.phone,
                                                       tags=tags_for(event, classification)))
    else:
        upsert = None
        act = _action("ghl", "upsert_contact", {"email": event.lead_email, "tags": tags_for(event, classification)}, None)
    actions.append(act)
    live_id = _id_from(upsert, ("contact", "id"), ("id",))
    if live_id:
        contact_id = live_id
        state.ghl_contact_id = live_id
    if contact_id is None:
        contact_id = "shadow:%s" % event.lead_email  # placeholder so dependent would_do records show intent

    # ---- opportunity / stage
    stage_key = STAGE_FOR_LABEL.get(label)
    if stage_key and ghl is not None:
        stage_id = settings.GHL_STAGES.get(stage_key)
        status = "lost" if stage_key == "lost" else "open"
        if state.ghl_opportunity_id:
            act, res = _call("ghl", "update_opportunity_stage", {"opportunity_id": state.ghl_opportunity_id, "stage": stage_key},
                             lambda: ghl.update_opportunity_stage(state.ghl_opportunity_id, stage_id, status=status))
            actions.append(act)
        else:
            act, res = _call("ghl", "upsert_opportunity",
                             {"contact_id": contact_id, "stage": stage_key, "name": opportunity_name(event), "status": status},
                             lambda: ghl.upsert_opportunity(contact_id, settings.GHL_SALES_PIPELINE_ID, stage_id, opportunity_name(event), status=status))
            actions.append(act)
            opp_id = _id_from(res, ("opportunity", "id"), ("id",))
            if opp_id:
                state.ghl_opportunity_id = opp_id

    # ---- note with the lead's own words
    if ghl is not None:
        note = "Instantly reply on %s (%s)\nLabel: %s (%.2f, %s)\nReason: %s\n\n%s" % (
            event.received_at.isoformat(), event.campaign_key or event.campaign_id, label, classification.confidence,
            classification.method, classification.reason, core_text(event.text)[:1500])
        if label == "wrong_person" and ex.referral_name:
            note += "\n\nNamed contact: %s (queued for the list factory; do not email from this thread)" % ex.referral_name
        if label == "negative_notfit":
            note += "\n\nLost reason: not a fit"
        act, res = _call("ghl", "create_note", {"contact_id": contact_id, "chars": len(note)},
                         lambda: ghl.create_note(contact_id, note))
        actions.append(act)

    # ---- label specific
    if label == "negative_notnow":
        follow_up = ex.follow_up_date or (event.received_at + timedelta(days=30)).date().isoformat()
        due = _due_iso(datetime.strptime(follow_up, "%Y-%m-%d"))
        if ghl is not None:
            act, res = _call("ghl", "create_task", {"contact_id": contact_id, "due": due, "title": "Follow up"},
                             lambda: ghl.create_task(contact_id, "Follow up: %s" % (event.company or event.lead_email), due,
                                                     body="Said not now on %s. Re-touch with two slots and the booking link."
                                                          % event.received_at.date().isoformat()))
            actions.append(act)
        state.cadence = dict(state.cadence, mode="follow_up_later", follow_up_at=follow_up, paused=True, armed=False)
        state.status = "follow_up_later"
    elif label == "positive_referral":
        who = ex.referral_name or "the right contact"
        due = _due_iso(slots.business_days_ahead(now, 1))
        if ghl is not None:
            act, res = _call("ghl", "create_task", {"contact_id": contact_id, "due": due, "title": "Ask for intro to %s" % who},
                             lambda: ghl.create_task(contact_id, "Ask for intro to %s" % who, due,
                                                     body="Referral from %s (%s)" % (_contact_name(event), event.lead_email)))
            actions.append(act)
        state.status = "positive_awaiting_draft"
    elif label == "wrong_person":
        record = {"email": event.lead_email, "company": event.company, "named_contact": ex.referral_name, "campaign_id": event.campaign_id,
                  "at": event.received_at.isoformat()}
        if store is not None:
            try:
                store.append(LIST_FACTORY_QUEUE_KEY, record)
            except Exception as exc:  # noqa: BLE001
                logger.warning("store append failed: %s", exc)
        actions.append(Action(system="store", action="queue_list_factory", payload=record, kind="done"))
        state.status = "wrong_person"
    elif label in POSITIVE_LABELS:
        state.status = "positive_awaiting_draft"
    elif label == "neutral_question":
        state.status = "question_awaiting_draft"
    elif label == "negative_notfit":
        state.status = "lost"
    elif label in BLOCKLIST_LABELS:
        state.status = "blocklisted"

    # ---- Instantly interest + blocklist
    interest = INTEREST_FOR_LABEL.get(label)
    if interest is not None and instantly is not None:
        act, res = _call("instantly", "update_interest_status", {"lead_email": event.lead_email, "interest_value": interest},
                         lambda: instantly.update_interest_status(event.lead_email, event.campaign_id, interest))
        actions.append(act)
    if label in BLOCKLIST_LABELS and instantly is not None:
        # An Instantly blocklist entry is workspace-wide and the lead cannot
        # undo it, so it is the one write worth a second look. classify() now
        # refuses to produce a hostile/unsubscribe label for a reply that
        # carries a buying signal and no opt-out in the lead's own words; this
        # is the same check one layer down, in case such a label ever arrives
        # from a model, a replay or a hand override.
        core = core_text(event.text)
        if not (ex.remove_request or explicit_removal(core)) and has_positive_cue(core):
            logger.warning("withholding the blocklist for %s: buying signal and no removal request", event.lead_email)
            actions.append(Action(system="instantly", action="blocklist_withheld",
                                  payload={"bl_value": event.lead_email, "label": label}, kind="skipped",
                                  note="buying signal present and no removal request in the lead's words; needs a human"))
            state.status = "needs_review"
        else:
            act, res = _call("instantly", "blocklist_create", {"bl_value": event.lead_email},
                             lambda: instantly.blocklist_create(event.lead_email), note="same-day blocklist + DND tag")
            actions.append(act)
            state.cadence = dict(state.cadence, paused=True, stopped=True, reason=label)

    return actions
