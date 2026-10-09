"""CT3 piece A: the template gate. No network, no LLM, no live flags.

Every test runs against a tmp approvals file and a tmp parity reference
(template_fixtures.make_template_env); the real config/approved_templates.json
and config/template_catalogue_hashes.json are checked unchanged after each test.
Lead data is made up.
"""
import json
import types
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pytest
from pydantic import Field

from shared import notify, settings
from shared.paths import BASE_DIR
from shared.store import JsonFileStore

from changesets.deploy import template_parity as parity_cli
from services.reply_engine import booking, cadence, classify, draft, models, no_show, show_rate
from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate
from services.reply_engine.tests import template_fixtures as tf

REAL_APPROVALS = BASE_DIR / "config" / "approved_templates.json"
REAL_REFERENCE = BASE_DIR / "config" / "template_catalogue_hashes.json"
FIRST = "Jordan"
COMPANY = "Brightline Test Co"
LINK = "https://example.invalid/book"
ZOOM = "https://example.invalid/zoom"
NOW = ta._ct(2030, 1, 7, 9, 0)
START = ta._ct(2030, 1, 8, 13, 0)
TWO = [ta._ct(2030, 1, 8, 13, 0), ta._ct(2030, 1, 10, 15, 30)]


def _bytes(p):
    return p.read_bytes() if p.exists() else None


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    before = (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    alerts = []

    def fake_notify(title, message, priority="default", **kw):
        alerts.append({"title": title, "message": message, "priority": priority, "kw": kw})
        return {"sent": False, "test": True}
    monkeypatch.setattr(notify, "notify", fake_notify)
    # The made-up links count as configured: the booking link through the
    # real setting, the Zoom host through the gate's host list.
    monkeypatch.setattr(settings, "BOOKING_URL", LINK)
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us", "example.invalid"))
    e = tf.make_template_env(monkeypatch, tmp_path)
    e.alerts = alerts
    yield e
    gate.clear_cache()
    assert (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE)) == before, "a test wrote a real config file"


# ------------------------------------------------------------- builders
class GDraft(models.Draft):
    """models.Draft with the CT3 fields, whether or not models.py has them yet."""
    template_id: Optional[str] = None
    template_hash: Optional[str] = None
    template_parts: Dict[str, Optional[str]] = Field(default_factory=dict)


def _state(niche="cleaning", offer="reactivation", first=FIRST, company=COMPANY):
    return types.SimpleNamespace(first_name=first, company=company, niche=niche, offer=offer,
                                 campaign_key="%s_%s" % (niche, offer), campaign_id=None, phone=None, specialty=None,
                                 website=None, last_subject="Quick question", subject=None, thread_subject=None,
                                 lead_email="lead@example.invalid", ghl_contact_id=None, cadence={})


def _cls(label="positive_interested", confidence=0.95, method="llm", **extracted):
    return models.Classification(label=label, confidence=confidence, method=method,
                                 extracted=models.Extracted(**extracted))


def _first_reply(offer="cleaning_reactivation", cls=None, first=FIRST, company=COMPANY):
    cls = cls or _cls()
    ev = models.ReplyEvent(email_id="t1", lead_email="lead@example.invalid", campaign_key=offer, first_name=first,
                           company=company, subject="Quick question", text="", received_at=NOW)
    d = draft.build_draft(ev, cls, now=NOW, booking_link=LINK, use_llm=False, already_offered=[], busy_blocks=[])
    return GDraft(**d.model_dump())


def _offer():
    return sorted(draft.PRICING)[0]


def _fr_id(offer, branch="default"):
    return "first_reply.%s.%s.full" % (offer, branch)


def _approved_first_reply(env, branch="default", cls=None):
    offer = _offer()
    tid = _fr_id(offer, branch)
    env.approve_ids(tid)
    d = _first_reply(offer, cls=cls)
    gate.stamp(d, tid)
    return d, tid, offer


def _fr_verdict(d, offer, cls=None, requested=None):
    return gate.draft_verdict(d, kind="first_reply", campaign_key=offer, allow_terms=[COMPANY, FIRST],
                              classification=cls or _cls(), requested=requested)


def _touch(day=1, niche="cleaning", offer="reactivation", slots_=None, stamp_id=None, parts=()):
    slots_ = TWO if slots_ is None else slots_
    st = _state(niche, offer)
    line = cadence.fallback_research_line(COMPANY, offer) if day == 2 else None
    t = cadence.build_touch(st, day, [s.isoformat() for s in slots_], research_line=line)
    if stamp_id:
        gate.stamp(t, stamp_id, parts)
    return t


def _sr_touch(key="confirm_email", niche="cleaning", offer="reactivation", appt=None, kind="show_rate"):
    appt = appt or {"niche": niche, "offer": offer, "booking_url": LINK, "id": "a1", "first_name": FIRST,
                    "company": COMPANY, "zoom_link": ZOOM}
    copy = show_rate.render(key, appt, START, NOW)
    t = show_rate.Touch(key="a1:%s:%s" % (START.isoformat(), key), appointment_id="a1", contact_id=None,
                        when_iso=NOW.isoformat(), channel="sms" if key.endswith("_sms") else "email",
                        template_key=key, body=copy["body"], subject=copy.get("subject"))
    gate.stamp(t, gate.resolve_combo_id(kind, key, niche, offer))
    return t


def _mismatch_reference(env, drop=None):
    rec = json.loads(env.reference_path.read_text())
    tid = drop or sorted(rec["ids"])[0]
    rec["ids"][tid] = "0" * 64
    rec["digest"] = "f" * 64
    env.reference_path.write_text(json.dumps(rec))
    gate.clear_cache()
    return tid


# ---------------------------------------------------------------- reasons
def test_ok_first_reply_cadence_and_show_rate(env):
    d, tid, offer = _approved_first_reply(env)
    v = _fr_verdict(d, offer)
    assert (v.allowed, v.reason, v.template_id) == (True, "ok", tid)
    assert v.statuses == {tid: ta.STATUS_APPROVED}

    env.approve_ids("cadence.e4", "cadence.e4.offer_proof.reactivation")
    t = _touch(4, stamp_id="cadence.e4", parts=["cadence.e4.offer_proof.reactivation"])
    v = gate.touch_verdict(t)
    assert (v.allowed, v.reason) == (True, "ok"), v.detail
    assert v.ids == ["cadence.e4", "cadence.e4.offer_proof.reactivation"]

    t = _sr_touch("confirm_email")
    env.approve_ids(t.template_id)
    v = gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[COMPANY, FIRST])
    assert (v.allowed, v.reason) == (True, "ok"), v.detail


def test_kill_switch_reason(env):
    d, tid, offer = _approved_first_reply(env)
    env.kill_switch(True)
    assert _fr_verdict(d, offer).reason == "kill_switch"


def test_parity_failed_reason(env):
    d, tid, offer = _approved_first_reply(env)
    _mismatch_reference(env)
    v = _fr_verdict(d, offer)
    assert (v.allowed, v.reason) == (False, "parity_failed")


def test_no_template_and_not_template_render(env):
    d, tid, offer = _approved_first_reply(env)
    d2 = d.model_copy(update={"template_id": None})
    assert _fr_verdict(d2, offer).reason == "no_template"
    polished = d.model_copy(update={"model": "claude-sonnet"})
    assert _fr_verdict(polished, offer).reason == "not_template_render"
    edited = d.model_copy(update={"model": "edited", "template_id": None})
    assert _fr_verdict(edited, offer).reason == "not_template_render"
    # CT3 phase 2: cadence.build_touch now carries its template id, so an
    # unstamped d1 touch is judged on that id; nothing approved it here, so
    # the reason is "unapproved", not "no_template".
    t = _touch(1)
    assert t.template_id == "cadence.e1"
    assert gate.touch_verdict(t).reason == "unapproved"
    # A real no_template case: a touch-shaped object with no template id at all.
    bare = types.SimpleNamespace(body_text=t.body_text, subject=t.subject, problems=[],
                                 campaign_key=getattr(t, "campaign_key", None), allow_terms=None)
    assert not hasattr(bare, "template_id")
    assert gate.touch_verdict(bare).reason == "no_template"
    assert gate.ids_verdict(None).reason == "no_template"


def test_unknown_id(env):
    assert gate.ids_verdict("cadence.e99").reason == "unknown_id"
    # an id from another kind is refused too: a first-reply id cannot pass as a booking
    d, tid, offer = _approved_first_reply(env)
    v = gate.draft_verdict(d, kind="booking", campaign_key=offer, allow_terms=[COMPANY, FIRST])
    assert v.reason == "unknown_id"


def test_unapproved_and_changed_since_approval(env):
    d, tid, offer = _approved_first_reply(env)
    env.revoke_ids(tid)
    v = _fr_verdict(d, offer)
    assert (v.reason, v.statuses[tid]) == ("unapproved", ta.STATUS_UNAPPROVED)
    env.approve_ids(tid)
    data = json.loads(env.approvals_path.read_text())
    data["approvals"][tid]["sha256"] = "1" * 64
    env.approvals_path.write_text(json.dumps(data))
    v = _fr_verdict(d, offer)
    assert (v.reason, v.statuses[tid]) == ("changed_since_approval", ta.STATUS_CHANGED)


def test_not_approvable(env):
    assert gate.ids_verdict("first_reply.%s.greeting" % _offer()).reason == "not_approvable"
    # d2 with the per-lead LLM research line is always held
    env.approve_ids("cadence.e2")
    v = gate.ids_verdict("cadence.e2", ["cadence.e2.research_line"])
    assert v.reason == "not_approvable"


def test_stale_render(env):
    d, tid, offer = _approved_first_reply(env)
    stale = d.model_copy(update={"template_hash": "2" * 64})
    assert _fr_verdict(stale, offer).reason == "stale_render"
    unstamped = d.model_copy(update={"template_hash": None})
    assert _fr_verdict(unstamped, offer).reason == "stale_render"
    env.approve_ids("cadence.e4", "cadence.e4.offer_proof.reactivation")
    t = _touch(4, stamp_id="cadence.e4", parts=["cadence.e4.offer_proof.reactivation"])
    t.template_parts["cadence.e4.offer_proof.reactivation"] = "3" * 64
    assert gate.touch_verdict(t).reason == "stale_render"


@pytest.mark.parametrize("cls", [
    _cls(label="neutral_question"),
    _cls(confidence=0.5),
    _cls(confidence=classify.CONFIDENCE_FLOOR - 0.01),
    _cls(method="fallback"),
    _cls(label="negative_notnow"),
    None,
])
def test_classification(env, cls):
    d, tid, offer = _approved_first_reply(env)
    v = gate.draft_verdict(d, kind="first_reply", campaign_key=offer, allow_terms=[COMPANY, FIRST],
                           classification=cls)
    assert v.reason == "classification"


def test_classification_floor_itself_passes(env):
    d, tid, offer = _approved_first_reply(env)
    assert _fr_verdict(d, offer, cls=_cls(confidence=classify.CONFIDENCE_FLOOR)).allowed


def test_requested_override(env):
    d, tid, offer = _approved_first_reply(env)
    v = _fr_verdict(d, offer, requested={"slot": START.isoformat(), "status": "weekend"})
    assert v.reason == "requested_override"


def test_copy_gate(env):
    d, tid, offer = _approved_first_reply(env)
    flagged = d.model_copy(update={"problems": ["mentions AI"]})
    v = _fr_verdict(flagged, offer)
    assert (v.reason, v.detail) == ("copy_gate", "mentions AI")
    # the validator is re-run on the final body: a banned word injected after build
    body = d.body_text.replace("Lorenzo", "Our AI assistant\n\nLorenzo")
    assert _fr_verdict(d.model_copy(update={"body_text": body}), offer).reason == "copy_gate"
    # cadence re-asserts touch.problems
    env.approve_ids("cadence.e1")
    t = _touch(1, stamp_id="cadence.e1")
    t.body_text = t.body_text.replace("Lorenzo", "Our bot will follow up!\n\nLorenzo")
    assert gate.touch_verdict(t).reason == "copy_gate"


def test_nonconforming(env):
    d, tid, offer = _approved_first_reply(env)
    body = d.body_text.replace("\n\nLorenzo", "\n\nWe also sell gift cards at a discount this week.\n\nLorenzo")
    v = _fr_verdict(d.model_copy(update={"body_text": body}), offer)
    assert (v.allowed, v.reason) == (False, "nonconforming")


def test_registry_error(env, monkeypatch):
    d, tid, offer = _approved_first_reply(env)

    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(ta, "status", boom)
    v = _fr_verdict(d, offer)
    assert (v.allowed, v.reason, v.detail) == (False, "registry_error", "RuntimeError")
    assert gate.ids_verdict("cadence.e1").reason == "registry_error"
    assert gate.draft_verdict(d, kind="nonsense").reason == "registry_error"


def test_every_reason_is_listed():
    assert set(gate.REASONS) == {
        "ok", "kill_switch", "parity_failed", "no_template", "not_template_render", "unknown_id", "unapproved",
        "changed_since_approval", "not_approvable", "stale_render", "classification", "requested_override",
        "copy_gate", "nonconforming", "registry_error"}


# ------------------------------------------------------------ gate order
def test_order_kill_switch_before_parity_before_ids(env):
    d, tid, offer = _approved_first_reply(env)
    env.revoke_ids(tid)                      # 4 fails
    _mismatch_reference(env)                 # 2 fails
    assert _fr_verdict(d, offer).reason == "parity_failed"
    env.kill_switch(True)                    # 1 fails
    assert _fr_verdict(d, offer).reason == "kill_switch"
    assert env.alerts and len(env.alerts) == 1  # parity alerted once, the kill switch never reads parity


def test_order_ids_before_stamp_before_classification_before_override(env):
    d, tid, offer = _approved_first_reply(env)
    bad = d.model_copy(update={"template_hash": "2" * 64, "problems": ["mentions AI"]})
    low = _cls(confidence=0.1)
    assert _fr_verdict(bad, offer, cls=low, requested={"x": 1}).reason == "stale_render"
    env.revoke_ids(tid)
    assert _fr_verdict(bad, offer, cls=low, requested={"x": 1}).reason == "unapproved"
    env.approve_ids(tid)
    ok_stamp = bad.model_copy(update={"template_hash": d.template_hash})
    assert _fr_verdict(ok_stamp, offer, cls=low, requested={"x": 1}).reason == "classification"
    assert _fr_verdict(ok_stamp, offer, requested={"x": 1}).reason == "requested_override"
    assert _fr_verdict(ok_stamp, offer).reason == "copy_gate"


def test_order_copy_gate_before_conforms(env):
    d, tid, offer = _approved_first_reply(env)
    body = d.body_text.replace("\n\nLorenzo", "\n\nAn extra AI line!\n\nLorenzo")
    assert _fr_verdict(d.model_copy(update={"body_text": body}), offer).reason == "copy_gate"


def test_order_model_before_template_id(env):
    d, tid, offer = _approved_first_reply(env)
    both = d.model_copy(update={"model": "claude-sonnet", "template_id": None})
    assert _fr_verdict(both, offer).reason == "not_template_render"


# ---------------------------------------------------------- kill switch
def test_kill_switch_env_zero(env):
    d, tid, offer = _approved_first_reply(env)
    env.kill_switch(True, via="env")
    assert _fr_verdict(d, offer).reason == "kill_switch"
    assert gate.auto_send_enabled() is False


def test_kill_switch_env_empty_counts_as_off(env, monkeypatch):
    from changesets.deploy import modal_secret

    assert modal_secret.EMPTY_IS_OFF[ta.KILL_SWITCH_ENV] == "off"
    d, tid, offer = _approved_first_reply(env)
    for value in ("", "off", "0", "nope"):
        monkeypatch.setenv(ta.KILL_SWITCH_ENV, value)
        assert _fr_verdict(d, offer).reason == "kill_switch", value
    monkeypatch.setenv(ta.KILL_SWITCH_ENV, "1")
    assert _fr_verdict(d, offer).allowed


def test_kill_switch_file_false(env):
    d, tid, offer = _approved_first_reply(env)
    env.kill_switch(True)
    assert json.loads(env.approvals_path.read_text())["auto_send"] is False
    assert _fr_verdict(d, offer).reason == "kill_switch"
    env.kill_switch(False)
    assert _fr_verdict(d, offer).allowed


def test_kill_switch_unreadable_file(env):
    d, tid, offer = _approved_first_reply(env)
    env.approvals_path.write_text("{not json")
    assert _fr_verdict(d, offer).reason == "kill_switch"
    assert gate.auto_send_enabled() is False
    # the helpers refuse to parse it too
    with pytest.raises(ValueError):
        tf.approve_ids("cadence.e1", path=env.approvals_path)


def test_kill_switch_holds_ladders_too(env):
    env.approve_ids("cadence.e1")
    t = _touch(1, stamp_id="cadence.e1")
    assert gate.touch_verdict(t).allowed
    s = _sr_touch("confirm_email")
    env.approve_ids(s.template_id)
    env.kill_switch(True)
    assert gate.touch_verdict(t).reason == "kill_switch"
    assert gate.appointment_touch_verdict(s, kind="show_rate").reason == "kill_switch"


# --------------------------------------------------------------- parity
def test_parity_ok(env):
    assert gate.parity_status() == {"status": "ok", "ids": []}
    assert gate.auto_send_enabled() is True
    assert env.alerts == []


def test_parity_mismatch_lists_ids_and_alerts_once_per_day(env):
    tid = _mismatch_reference(env)
    ps = gate.parity_status()
    assert ps["status"] == "mismatch" and ps["ids"] == [tid]
    for _ in range(3):
        assert gate.auto_send_enabled() is False
        assert gate.ids_verdict("cadence.e1").reason == "parity_failed"
    assert len(env.alerts) == 1
    alert = env.alerts[0]
    assert alert["priority"] == "urgent"
    assert tid in alert["message"] and "mismatch" in alert["title"]
    assert alert["kw"].get("actions") is None and alert["kw"].get("click") is None
    # ids and counts only: no template text in the alert
    text = ta.catalogue_index()[tid]["text"]
    assert text.splitlines()[0] not in alert["message"]
    # the next day it alerts again, through the same claim
    store = JsonFileStore(env.approvals_path.parent.parent / "store.json")
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    assert gate.alert_parity_failure(ps, store=store, now=tomorrow) is True
    assert gate.alert_parity_failure(ps, store=store, now=tomorrow) is False
    assert len(env.alerts) == 2


def test_parity_reference_missing(env):
    env.reference_path.unlink()
    gate.clear_cache()
    assert gate.parity_status()["status"] == "reference_missing"
    assert gate.auto_send_enabled() is False
    assert gate.ids_verdict("cadence.e1").reason == "parity_failed"
    assert len(env.alerts) == 1 and "reference_missing" in env.alerts[0]["title"]


def test_parity_error(env):
    env.reference_path.write_text("{broken")
    gate.clear_cache()
    assert gate.parity_status()["status"] == "error"
    assert gate.auto_send_enabled() is False
    env.reference_path.write_text(json.dumps({"digest": 5}))
    assert gate.parity_status()["status"] == "error"
    assert len(env.alerts) == 1  # one alert per day, whatever the status


def test_parity_alert_in_shadow_uses_the_notify_path(env, monkeypatch):
    """The alert goes through shared.notify.notify, which in MODE=shadow
    records the intent and sends nothing (the same rule as every alert)."""
    monkeypatch.undo()  # the real notify
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.setenv("NOTIFY", "off")
    monkeypatch.setenv("STORE_PATH", str(env.approvals_path.parent / "store2.json"))
    monkeypatch.setattr(ta, "APPROVALS_PATH", env.approvals_path)
    monkeypatch.setattr(gate, "PARITY_REFERENCE_PATH", env.reference_path)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
    notify.reset_for_tests()
    _mismatch_reference(env)
    assert gate.auto_send_enabled() is False
    assert len(notify.sent_in_test) == 1
    rec = notify.sent_in_test[0]
    assert rec["priority"] == "urgent" and rec["actions"] is None and rec["click"] is None
    notify.reset_for_tests()


def test_parity_cache_follows_the_reference_file(env):
    assert gate.parity_status()["status"] == "ok"
    _mismatch_reference(env)
    assert gate.parity_status()["status"] == "mismatch"
    env.write_reference()
    assert gate.parity_status()["status"] == "ok"


def test_catalogue_digest_is_sorted_id_sha_lines():
    import hashlib

    digest, ids = gate.catalogue_digest()
    idx = ta.catalogue_index()
    assert ids == dict((k, e["sha256"]) for k, e in idx.items() if e.get("approvable"))
    # ZC: no_show.ns_d1_other_channel is one id now (was 4). Section 2 A2: the
    # show-rate ids went from 21 to 11 (no SMS legs, no pre-read, three reminders).
    # Section 2 B: the two generic no_show.ns_d3_value_email (now ns_d2_value_email) ids are gone
    # (N5 is skipped without a niche).
    # The ten-email cadence ladder (2026-09-23): 29 cadence ids, was 23.
    # Go-live no-show ladder (2026-09-24): + no_show.ns_d3_retry_email (one id).
    assert len(ids) == 103
    lines = "\n".join(sorted("%s=%s" % kv for kv in ids.items()))
    assert digest == hashlib.sha256(lines.encode("utf-8")).hexdigest()


# ------------------------------------------------------------- conforms
def test_conforms_exact_renders():
    offer = _offer()
    d = _first_reply(offer)
    assert gate.conforms(_fr_id(offer), d.body_text, d.subject)
    d = _first_reply(offer, first=None, company=None)
    assert gate.conforms(_fr_id(offer), d.body_text, d.subject)
    st = _state()
    for day in range(1, 11):
        for sl in (TWO, TWO[:1]):
            t = _touch(day, slots_=sl)
            name, parts = cadence.touch_template_ids(day, st)
            assert gate.conforms(name, t.body_text, t.subject, parts), (day, len(sl))
        if day != 2:
            # there is no no-slots wording any more: a body without its times never conforms
            t = _touch(day, slots_=[])
            name, parts = cadence.touch_template_ids(day, st)
            assert not gate.conforms(name, t.body_text, t.subject, parts), day
    st = _state()
    body = booking.counter_proposal_text(booking.BookingMatch(slot=None, status=booking.WEEKEND,
                                                              proposed=ta._ct(2030, 1, 12, 14, 0),
                                                              counter_slots=TWO), st)
    assert gate.conforms("booking.counter.weekend", body, "Re: Quick question")
    conf, _ = booking._confirmation_draft(st, START, "America/New_York", ZOOM, True)
    assert gate.conforms("booking.confirmation.zoom_link", conf.body_text, conf.subject)
    assert not gate.conforms("booking.confirmation.no_zoom_link", conf.body_text, conf.subject)


def test_conforms_every_show_rate_and_no_show_render():
    for key in ta.SHOW_RATE_LEAD_FACING:
        for niche, offer in ta.NICHE_COMBOS:
            appt = {"niche": niche, "offer": offer, "booking_url": LINK, "id": "a1", "first_name": FIRST,
                    "company": COMPANY, "zoom_link": ZOOM}
            copy = show_rate.render(key, appt, START, NOW)
            tid = gate.resolve_combo_id("show_rate", key, niche, offer)
            assert tid and gate.conforms(tid, copy["body"], copy.get("subject")), (key, niche, offer)
    for key, count, repeat in [(k, 1, False) for k in ta.NO_SHOW_LEAD_FACING] + [("ns_reschedule_email", 2, True)]:
        for niche, offer in ta.NICHE_COMBOS:
            appt = {"niche": niche, "offer": offer, "booking_url": LINK, "id": "a1", "first_name": FIRST,
                    "company": COMPANY, "zoom_link": ZOOM}
            copy = no_show.render(key, appt, START, "Tue 1:00pm or Thu 3:30pm CT", count)
            if key == "ns_d2_value_email" and niche == "generic":
                # no approved niche line without a campaign: never sendable
                assert no_show.unfilled(copy) == "no_niche_point"
                continue
            tid = gate.resolve_combo_id("no_show", key, niche, offer, repeat=repeat)
            assert tid and gate.conforms(tid, copy["body"], copy.get("subject")), (key, niche, offer)


def test_conforms_refuses_an_injected_sentence():
    offer = _offer()
    d = _first_reply(offer)
    lines = d.body_text.split("\n\n")
    injected = "\n\n".join(lines[:1] + ["Click here to claim your refund today."] + lines[1:])
    assert not gate.conforms(_fr_id(offer), injected, d.subject)
    t = _touch(1)
    assert not gate.conforms("cadence.e1", t.body_text + "\n\nP.S. one more thing.", t.subject)


def test_conforms_refuses_truncated_text():
    t = _touch(3)
    assert not gate.conforms("cadence.e3", t.body_text[:-12], t.subject)
    copy = show_rate.render("confirm_email", {"niche": "cleaning", "offer": "reactivation", "first_name": FIRST,
                                              "company": COMPANY, "zoom_link": ZOOM}, START, NOW)
    tid = gate.resolve_combo_id("show_rate", "confirm_email", "cleaning", "reactivation")
    assert not gate.conforms(tid, copy["body"][: len(copy["body"]) // 2], copy["subject"])


def test_conforms_placeholder_cannot_span_a_newline():
    t = _touch(1)
    assert gate.conforms("cadence.e1", t.body_text, t.subject)
    sneaky = t.body_text.replace("Hey %s," % FIRST, "Hey %s\nWire the deposit to account 12345," % FIRST, 1)
    assert sneaky != t.body_text
    assert not gate.conforms("cadence.e1", sneaky, t.subject)


def test_conforms_repeated_placeholder_must_repeat_its_value():
    tid = gate.resolve_combo_id("show_rate", "confirm_email", "cleaning", "reactivation")
    copy = show_rate.render("confirm_email", {"niche": "cleaning", "offer": "reactivation", "first_name": FIRST,
                                              "company": COMPANY, "zoom_link": ZOOM}, START, NOW)
    when = show_rate.fmt_when(START, None)
    assert when in copy["subject"] and when in copy["body"]
    assert gate.conforms(tid, copy["body"], copy["subject"])
    other = copy["subject"].replace(when, "Fri, Jan 11 at 4:00pm CT")   # a real time, just not the body's
    assert not gate.conforms(tid, copy["body"], other)


def test_conforms_parts_substitution():
    t = _touch(4, offer="outbound")
    right, wrong = "cadence.e4.offer_proof.outbound", "cadence.e4.offer_proof.reactivation"
    assert gate.conforms("cadence.e4", t.body_text, t.subject, [right])
    assert not gate.conforms("cadence.e4", t.body_text, t.subject, [wrong])
    assert not gate.conforms("cadence.e4", t.body_text, t.subject, [])            # the slot must be filled
    assert not gate.conforms("cadence.e4", t.body_text, t.subject, [right, right])
    t2 = _touch(2, offer="reactivation")
    assert gate.conforms("cadence.e2", t2.body_text, t2.subject, ["cadence.e2.research_fallback.reactivation"])
    assert not gate.conforms("cadence.e2", t2.body_text, t2.subject, ["cadence.e2.research_fallback.outbound"])
    # an LLM research line never conforms: its part has no text
    st = _state()
    t3 = cadence.build_touch(st, 2, [s.isoformat() for s in TWO], research_line="Saw your new warehouse in the news.")
    assert not gate.conforms("cadence.e2", t3.body_text, t3.subject, ["cadence.e2.research_line"])
    t5 = _touch(5, niche="bookkeeping", offer="reactivation")
    assert gate.conforms("cadence.e5", t5.body_text, t5.subject, ["cadence.e5.offer_line.reactivation_bookkeeping"])
    assert not gate.conforms("cadence.e5", t5.body_text, t5.subject, ["cadence.e5.offer_line.reactivation"])
    t6 = _touch(6, niche="bookkeeping", offer="outbound")
    assert gate.conforms("cadence.e6", t6.body_text, t6.subject, ["cadence.e6.preview.bookkeeping_outbound"])
    assert not gate.conforms("cadence.e6", t6.body_text, t6.subject, ["cadence.e6.preview.cleaning_outbound"])
    t9 = _touch(9, niche="recruiting", offer="reactivation")
    assert gate.conforms("cadence.e9", t9.body_text, t9.subject, ["cadence.e9.observation.recruiting_reactivation"])
    assert not gate.conforms("cadence.e9", t9.body_text, t9.subject, ["cadence.e9.observation.recruiting_outbound"])


def test_conforms_subject_check():
    offer = _offer()
    d = _first_reply(offer)
    assert gate.conforms(_fr_id(offer), d.body_text, d.subject)
    assert gate.conforms(_fr_id(offer), d.body_text)                      # subject not given: body only
    assert not gate.conforms(_fr_id(offer), d.body_text, "Limited offer inside")
    assert not gate.conforms(_fr_id(offer), d.body_text, "Re: two\nlines")
    copy = show_rate.render("reminder_24h_email", {"niche": "cleaning", "offer": "reactivation", "first_name": FIRST,
                                                   "company": COMPANY, "booking_url": LINK}, START, NOW)
    tid = gate.resolve_combo_id("show_rate", "reminder_24h_email", "cleaning", "reactivation")
    assert gate.conforms(tid, copy["body"], copy["subject"])
    assert not gate.conforms(tid, copy["body"], "Something else entirely")
    assert gate.conforms(tid, copy["body"])


def test_conforms_unknown_or_bad_id_is_false():
    assert gate.conforms("cadence.e99", "Hey") is False
    assert gate.conforms("cadence.e2.research_line", "anything") is False


# ------------------------------------------------------------- records
def test_to_record_contains_no_text(env):
    d, tid, offer = _approved_first_reply(env)
    flagged = d.model_copy(update={"problems": ["dollar figure $999 not in offers.md"]})
    for v in (_fr_verdict(d, offer), _fr_verdict(flagged, offer)):
        rec = v.to_record()
        assert set(rec) == {"allowed", "reason", "template_id", "ids", "statuses"}
        flat = json.dumps(rec)
        assert FIRST not in flat and COMPANY not in flat and "$999" not in flat
        assert "Hey" not in flat and "Lorenzo" not in flat and d.subject not in flat


def test_stamp_sets_ids_and_hashes(env):
    t = _touch(4)
    gate.stamp(t, "cadence.e4", ["cadence.e4.offer_proof.reactivation"])
    idx = ta.catalogue_index()
    assert t.template_id == "cadence.e4" and t.template_hash == idx["cadence.e4"]["sha256"]
    assert t.template_parts == {"cadence.e4.offer_proof.reactivation":
                                idx["cadence.e4.offer_proof.reactivation"]["sha256"]}
    assert gate.current_hash("cadence.e4") == idx["cadence.e4"]["sha256"]
    assert gate.current_hash("cadence.e99") is None


def test_stamp_never_raises_on_an_object_without_the_fields(env):
    d = _first_reply(_offer())
    plain = models.Draft(**d.model_dump(exclude={"template_id", "template_hash", "template_parts"}))
    gate.stamp(plain, _fr_id(_offer()))  # logs, does not raise
    v = gate.draft_verdict(plain, kind="first_reply", classification=_cls())
    assert v.allowed is False


# ------------------------------------------------------------------ FYI
def _store(tmp_path):
    return JsonFileStore(tmp_path / "fyi_store.json")


def test_fyi_record_drain_restore(tmp_path):
    st = _store(tmp_path)
    now = datetime(2030, 1, 8, 15, 0, tzinfo=timezone.utc)
    gate.record_auto_send(st, kind="first_reply", template_id="first_reply.x.default.full", approval_id="tok1",
                          status="sent", now=now)
    gate.record_auto_send(st, kind="booking", template_id="booking.counter.weekend", approval_id="tok2",
                          status="approved_queued", send_after=now + timedelta(hours=10), now=now)
    gate.note_held(st, kind="cadence", template_id="cadence.e3", reason="unapproved", now=now)
    gate.note_held(st, kind="cadence", template_id="cadence.e3", reason="unapproved", now=now)
    gate.note_held(st, kind="show_rate", template_id=None, reason="no_template", now=now)
    entries, held = gate.drain_fyi(st)
    assert [e["approval_id"] for e in entries] == ["tok1", "tok2"]
    assert entries[1]["send_after"] == (now + timedelta(hours=10)).isoformat()
    assert set(entries[0]) == {"kind", "template_id", "approval_id", "status", "send_after", "at"}
    assert held == {"cadence.e3": 2, "show_rate:(no template)": 1}
    assert gate.drain_fyi(st) == ([], {})
    gate.record_auto_send(st, kind="first_reply", template_id="t", approval_id="tok3", status="sent", now=now)
    gate.restore_fyi(st, entries, held)
    entries2, held2 = gate.drain_fyi(st)
    assert [e["approval_id"] for e in entries2] == ["tok1", "tok2", "tok3"]
    assert held2 == held


def test_fyi_cap(tmp_path, monkeypatch):
    assert gate.FYI_CAP == 500 and gate.FYI_MINUTES == 30
    monkeypatch.setattr(gate, "FYI_CAP", 5)
    st = _store(tmp_path)
    now = datetime(2030, 1, 8, 15, 0, tzinfo=timezone.utc)
    for i in range(8):
        gate.record_auto_send(st, kind="first_reply", template_id="t", approval_id="tok%d" % i, status="sent", now=now)
    entries, _ = gate.drain_fyi(st)
    assert [e["approval_id"] for e in entries] == ["tok3", "tok4", "tok5", "tok6", "tok7"]
    gate.record_auto_send(st, kind="first_reply", template_id="t", approval_id="new", status="sent", now=now)
    gate.restore_fyi(st, entries, {})
    back, _ = gate.drain_fyi(st)
    assert len(back) == 5 and back[-1]["approval_id"] == "new"


def test_fyi_keys():
    assert gate.FYI_KEY == "autosend_fyi:pending"
    assert gate.HELD_KEY_PREFIX == "autosend_fyi:held:"
    assert gate.FYI_LEASE_PREFIX == "autosend_fyi:lease:"


def test_note_held_counts_per_template_id(tmp_path):
    st = _store(tmp_path)
    now = datetime(2030, 1, 8, 15, 0, tzinfo=timezone.utc)
    for tid in ("cadence.e1", "cadence.e1", "no_show.ns_still_on_sms", "cadence.e1"):
        gate.note_held(st, kind="cadence", template_id=tid, reason="unapproved", now=now)
    assert st.get(gate.HELD_KEY_PREFIX + "cadence.e1") == 3
    _, held = gate.drain_fyi(st)
    assert held == {"cadence.e1": 3, "no_show.ns_still_on_sms": 1}
    assert st.get(gate.HELD_KEY_PREFIX + "cadence.e1") == 0


# ------------------------------------------------------ resolve_combo_id
def test_resolve_combo_id_show_rate():
    idx = ta.catalogue_index()
    for key in ta.SHOW_RATE_LEAD_FACING:
        for niche, offer in ta.NICHE_COMBOS:
            tid = gate.resolve_combo_id("show_rate", key, niche, offer)
            assert tid and tid.startswith("show_rate.%s" % key), (key, niche, offer)
            assert [niche, offer] in idx[tid]["applies_to"]
    assert gate.resolve_combo_id("show_rate", "confirm_email", "plumbing", "reactivation") is None
    assert gate.resolve_combo_id("show_rate", "unconfirmed_task", "cleaning", "reactivation") is None
    assert gate.resolve_combo_id("show_rate", "no_such_key", "cleaning", "reactivation") is None
    assert gate.resolve_combo_id("cadence", "d1", "cleaning", "reactivation") is None


def test_resolve_combo_id_no_show_with_and_without_repeat():
    idx = ta.catalogue_index()
    for niche, offer in ta.NICHE_COMBOS:
        first = gate.resolve_combo_id("no_show", "ns_reschedule_email", niche, offer)
        again = gate.resolve_combo_id("no_show", "ns_reschedule_email", niche, offer, repeat=True)
        assert first and ".repeat" not in first
        assert again and again.startswith("no_show.ns_reschedule_email.repeat")
        assert [niche, offer] in idx[first]["applies_to"] and [niche, offer] in idx[again]["applies_to"]
        for key in ta.NO_SHOW_LEAD_FACING:
            tid = gate.resolve_combo_id("no_show", key, niche, offer)
            if key == "ns_d2_value_email" and niche == "generic":
                assert tid is None  # N5 is skipped without a niche line, never generic
                continue
            assert tid and [niche, offer] in idx[tid]["applies_to"]
    assert gate.resolve_combo_id("no_show", "ns_still_on_sms", "cleaning", "reactivation", repeat=True) is None


def test_applies_to_covers_every_combo_exactly_once():
    idx = ta.catalogue_index()
    for kind, keys, repeat_key in (("show_rate", ta.SHOW_RATE_LEAD_FACING, None),
                                   ("no_show", ta.NO_SHOW_LEAD_FACING, "ns_reschedule_email")):
        bases = ["%s.%s" % (kind, k) for k in keys] + (["%s.%s.repeat" % (kind, repeat_key)] if repeat_key else [])
        for base in bases:
            entries = [e for tid, e in idx.items()
                       if tid == base or (tid.startswith(base + ".") and not tid[len(base) + 1:].startswith("repeat"))]
            combos = [tuple(c) for e in entries for c in e.get("applies_to", [])]
            want = [c for c in ta.NICHE_COMBOS
                    if not (base == "no_show.ns_d2_value_email" and c[0] == "generic")]
            assert sorted(combos) == sorted(want), base


# ---------------------------------------------------------------- health
def test_health_summary_has_no_text(env):
    env.approve_ids("cadence.e1", "cadence.e3")
    h = gate.health_summary()
    assert h["parity"] == "ok" and h["kill_switch"] is False and h["auto_send_enabled"] is True
    assert h["approved_count"] == 2 and h["approvable_count"] == 103
    assert h["ladder_unapproved_count"] == len(gate.ladder_ids()) - 2
    flat = json.dumps(h)
    assert "Hey" not in flat and "cadence." not in flat and "Lorenzo" not in flat
    env.kill_switch(True)
    _mismatch_reference(env)
    h = gate.health_summary()
    got = (h["parity"], h["parity_differing"], h["kill_switch"], h["auto_send_enabled"])
    assert got == ("mismatch", 1, True, False)


def test_ids_verdict_is_statuses_only(env):
    env.approve_ids("cadence.e1")
    assert gate.ids_verdict("cadence.e1").allowed
    assert gate.ids_verdict("cadence.e3").reason == "unapproved"
    env.approve_ids("cadence.e2", "cadence.e2.research_fallback.outbound")
    assert gate.ids_verdict("cadence.e2", ["cadence.e2.research_fallback.outbound"]).allowed


def test_fixture_ladder_mode(monkeypatch, tmp_path):
    e = tf.make_template_env(monkeypatch, tmp_path / "ladders", approve_ladders=True)
    assert e.approvals_path != REAL_APPROVALS
    for tid in gate.ladder_ids():
        assert ta.status(tid) == ta.STATUS_APPROVED
    assert ta.status(_fr_id(_offer())) == ta.STATUS_UNAPPROVED
    assert gate.parity_status()["status"] == "ok"


def test_fixture_helpers_refuse_the_real_file():
    with pytest.raises(AssertionError):
        tf.approve_ids("cadence.e1", path=REAL_APPROVALS)
    with pytest.raises(AssertionError):
        tf.write_reference(REAL_REFERENCE)


# ------------------------------------------------------------------- CLI
def test_parity_cli_write_check_and_mismatch(env, tmp_path, capsys):
    ref = tmp_path / "cli" / "template_catalogue_hashes.json"
    assert parity_cli.main(["--write", "--reference", str(ref)]) == 0
    rec = json.loads(ref.read_text())
    assert set(rec) == {"python", "pytz", "pydantic", "generated_at", "digest", "ids"}
    assert rec["digest"] == gate.catalogue_digest()[0] and len(rec["ids"]) == 103
    assert "Hey" not in ref.read_text()
    capsys.readouterr()
    assert parity_cli.main(["--check", "--reference", str(ref)]) == 0
    assert capsys.readouterr().out.startswith("OK: 103 ids")
    rec["ids"]["cadence.e1"] = "0" * 64
    rec["digest"] = "0" * 64
    ref.write_text(json.dumps(rec))
    assert parity_cli.main(["--check", "--reference", str(ref)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("MISMATCH: 1 id(s) differ") and "  cadence.e1" in out
    ref.unlink()
    assert parity_cli.main(["--check", "--reference", str(ref)]) == 1


def test_parity_cli_refuses_the_approvals_file(env, capsys):
    assert parity_cli.main(["--write", "--reference", str(env.approvals_path)]) == 2
    assert parity_cli.main(["--write", "--reference", str(REAL_APPROVALS)]) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_parity_cli_report_unapproved(env, capsys):
    ladders = gate.ladder_ids()
    assert parity_cli.main(["--report-unapproved", "--approvals-file", str(env.approvals_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:3] == ["UNAPPROVED LADDER IDS: %d" % len(ladders), "UNEXTRACTABLE LADDER IDS: 0", "KILL SWITCH: off"]
    assert set(line.strip() for line in out[4:4 + len(ladders)]) == set(ladders)
    env.approve_ladders()
    env.approve_ids(_fr_id(_offer()))
    data = json.loads(env.approvals_path.read_text())
    data["approvals"]["cadence.e1"]["sha256"] = "9" * 64   # changed since approval counts as unapproved
    env.approvals_path.write_text(json.dumps(data))
    assert parity_cli.main(["--report-unapproved", "--approvals-file", str(env.approvals_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "UNAPPROVED LADDER IDS: 1" and out[4].strip() == "cadence.e1"
    for line in out:
        assert "Hey" not in line


def test_parity_cli_report_lists_unextractable_ladder_ids_and_the_kill_switch(env, capsys, monkeypatch):
    real = ta._show_rate_entries

    def broken():
        raise RuntimeError("extractor broke")
    monkeypatch.setattr(ta, "_show_rate_entries", lambda: [ta._unextractable("show_rate.confirm_email", "show_rate",
                                                                            "x", "extraction failed: boom")]
                        + [e for e in real() if not e["id"].startswith("show_rate.confirm_email")])
    ta.clear_cache()
    gate.clear_cache()
    env.approve_ladders()
    env.kill_switch(True)
    assert parity_cli.main(["--report-unapproved", "--approvals-file", str(env.approvals_path)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[:3] == ["UNAPPROVED LADDER IDS: 0", "UNEXTRACTABLE LADDER IDS: 1", "KILL SWITCH: on"]
    assert "  show_rate.confirm_email" in lines
    assert "cadence.e2.research_line" not in out          # unextractable by design, not a failure
    assert "every cadence, show-rate and no-show message is held" in out
    ta.clear_cache()


def test_parity_cli_report_refuses_an_unreadable_approvals_file(env, capsys):
    env.approvals_path.write_text("{nope")
    assert parity_cli.main(["--report-unapproved", "--approvals-file", str(env.approvals_path)]) == 2


def test_parity_cli_reference_flag_is_limited(env, tmp_path, capsys):
    ok_name = tmp_path / "anywhere" / "template_catalogue_hashes.json"
    assert parity_cli.main(["--write", "--reference", str(ok_name)]) == 0
    in_tmp = tmp_path / "other_name.json"
    assert parity_cli.main(["--write", "--reference", str(in_tmp)]) == 0      # a temp dir is allowed
    outside = BASE_DIR / ".tmp_ct3_should_not_exist" / "evil.json"
    assert parity_cli.main(["--write", "--reference", str(outside)]) == 2
    assert not outside.exists() and not outside.parent.exists()
    assert "REFUSED" in capsys.readouterr().out


def test_parity_cli_never_writes_the_approvals_file(env, tmp_path):
    before = env.approvals_path.read_bytes()
    ref = tmp_path / "x" / "template_catalogue_hashes.json"
    parity_cli.main(["--write", "--reference", str(ref)])
    parity_cli.main(["--check", "--reference", str(ref)])
    parity_cli.main(["--report-unapproved", "--approvals-file", str(env.approvals_path)])
    assert env.approvals_path.read_bytes() == before
