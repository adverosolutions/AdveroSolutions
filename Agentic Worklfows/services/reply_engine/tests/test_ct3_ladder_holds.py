"""CT3 phase 2 fixes (reviewer-max P1 and P4, and the resume gap):

1. A live D1 whose FULL template check fails (a subject or first name the
   placeholder rules refuse) sends no "sends at" Veto ping, and after a
   refused check the window re-opens only once something changed (the
   lead's data, the template, the gate's rules version or catalogue), or
   after a Resume, as a fresh, full 30-minute window.
2. A ladder stopped as ``template_unapproved`` can be resumed by Lorenzo: the
   stop push carries a signed Resume link on whichever leg can carry it (the
   push itself on a protected topic, the email leg on a public one) and says
   so when neither can; the link is re-signed every day the ladder stays
   stopped and as soon as the held ids are approved, never for a lead the
   ladder is over for, and the /cadence/resume page and POST work for this
   stop.
3. A gate-wide hold (kill switch, parity, registry error) never stops a
   ladder and never counts toward the stall; the stall counts the business
   days held for any other cause, in any order, and the stop's advice is the
   stopping cause's (a nonconforming hold: the lead's data, not "approve the
   ids").

"Live" here is ``cadence.is_live`` patched to True: MODE stays shadow and
ALLOW_LIVE_WRITES stays unset, so every write is a would_do. NOTIFY stays
off, so a push is only recorded. Lead data is made up.
"""
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from shared import slots as slot_rules
from shared.job_log import read_shadow_log
from shared.settings import is_live as settings_is_live

from services.reply_engine import app as app_mod
from services.reply_engine import cadence
from services.reply_engine import template_gate as gate
from services.reply_engine.cadence import LeadState
from services.reply_engine.tests.test_ct3_ladders import (  # noqa: F401 - fixtures
    COMPANY, FREE, LEAD, at_day, ct, make_state, public_base_url, store)

RESUME_RE = re.compile(r"Resume: (https://\S+)")


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")


@pytest.fixture
def d1_live(monkeypatch, secret):
    """cadence's own live switch only: guarded writes stay shadow."""
    monkeypatch.setattr(cadence, "is_live", lambda: True)
    assert settings_is_live() is False


NOTIFY_KEYS = ("NTFY_TOKEN", "NTFY_ALLOW_SENSITIVE", "NOTIFY_EMAIL", "NOTIFICATION_EMAIL", "GMAIL_SENDER_EMAIL",
               "GMAIL_APP_PASSWORD")


@pytest.fixture
def no_channel(monkeypatch):
    """A public ntfy topic and no email leg (the conftest's default)."""
    for key in NOTIFY_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert cadence.resume_link_channel() is None


@pytest.fixture
def email_leg(no_channel, monkeypatch):
    """A public ntfy topic with the email leg set. Fake values; NOTIFY stays
    off, so nothing is sent: notify() only records."""
    monkeypatch.setenv("NOTIFY_EMAIL", "owner@example.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "engine@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x" * 16)
    assert cadence.resume_link_channel() == cadence.RESUME_LINK_VIA_EMAIL


@pytest.fixture
def protected_topic(no_channel, monkeypatch):
    """A protected ntfy topic (a fake NTFY_TOKEN) and no email leg."""
    monkeypatch.setenv("NTFY_TOKEN", "unit-token-not-real")
    assert cadence.resume_link_channel() == cadence.RESUME_LINK_VIA_NTFY


def replies():
    return [r for r in read_shadow_log() if r["action"] == "reply_to_email"]


def d1_day(state, store, pings, hours, free=FREE):
    out = []
    for h, m in hours:
        res = cadence.tick_lead(state, ct(2026, 9, 22, h, m), store=store, free_slots=free,
                                notify_fn=lambda *a, **k: pings.append((a, k)) or {"email": True})
        out.append(res)
    return out


DAY_HOURS = [(9, 30), (10, 0), (11, 0), (12, 0), (13, 0), (14, 0), (15, 0), (16, 0), (17, 0), (18, 0)]


def veto_pings(pings):
    return [p for p in pings if "sends at" in p[0][0]]


# ============================================================ 1. D1 veto
@pytest.mark.parametrize("field,value", [
    ("last_subject", "Re: Dana, quick question?"),   # "?" is refused in the subject placeholder
    ("first_name", "N/A"),                           # "/" is refused in a name
])
def test_d1_whose_full_check_fails_sends_no_veto_ping_all_day(store, tmp_env, d1_live, field, value):
    state = cadence.arm(make_state(**{field: value}), ct(2026, 9, 21, 16, 0))
    pings = []
    results = d1_day(state, store, pings, DAY_HOURS)
    assert [r["action"] for r in results] == ["held_template"] * len(DAY_HOURS)
    assert {r["reason"] for r in results} == {"nonconforming"}
    assert [r["quiet"] for r in results] == [False] + [True] * (len(DAY_HOURS) - 1)
    assert veto_pings(pings) == [] and pings == []
    assert state.cadence.get("veto_notified_at") is None and replies() == []
    line = cadence.summarize_touch(results[0])
    assert "Approving changes nothing" in line and "first name" in line and "Approve the ids" not in line


def test_d1_fixed_lead_data_reopens_a_fresh_full_window(store, tmp_env, d1_live):
    state = cadence.arm(make_state(first_name="N/A"), ct(2026, 9, 21, 16, 0))
    pings = []
    d1_day(state, store, pings, [(9, 30), (10, 0), (11, 0)])
    assert pings == []
    state.first_name = "Dana"
    opened = cadence.tick_lead(state, ct(2026, 9, 22, 12, 0), store=store, free_slots=FREE,
                               notify_fn=lambda *a, **k: pings.append((a, k)) or {"email": True})
    assert opened["action"] == "veto_window_opened" and len(veto_pings(pings)) == 1
    pinged = slot_rules.parse_iso(state.cadence["veto_notified_at"])
    send_at = slot_rules.parse_iso(state.cadence["next_send_at"])
    assert send_at - pinged >= timedelta(minutes=cadence.VETO_WINDOW_MINUTES)
    assert cadence.tick_lead(state, pinged + timedelta(minutes=20), store=store, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)["action"] == "not_due"
    sent = cadence.tick_lead(state, send_at, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert sent["action"] == "would_send" and len(replies()) == 1
    assert "d1_gate_hold" not in state.cadence and "template_hold" not in state.cadence


def test_d1_refused_at_send_reopens_only_after_a_change(store, tmp_env, d1_live, monkeypatch):
    """The pre-check passes but the send-time check refuses (here: only the
    tick's real slots fail). The window must not re-open every hour on the
    same inputs; a change to what the check looks at re-opens it once."""
    grid = cadence.default_slot_grid(ct(2026, 9, 22, 9, 30))
    monkeypatch.setattr(cadence, "_d1_precheck_slots",
                        lambda state, now, store, free: cadence.fresh_slots(state, now, grid, None))
    real_verdict = cadence._template_touch_verdict
    offered = set(slot_rules.to_tz(slot_rules.parse_iso(s)).isoformat() for s in FREE)

    def verdict(state, touch):
        v = real_verdict(state, touch)
        if v.allowed and set(touch.slots) == offered:
            return gate.Verdict(False, "nonconforming", v.template_id, list(v.ids), dict(v.statuses))
        return v
    monkeypatch.setattr(cadence, "_template_touch_verdict", verdict)

    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    results = d1_day(state, store, pings, DAY_HOURS)
    assert results[0]["action"] == "veto_window_opened"
    assert results[1]["action"] == "held_template" and results[1]["reason"] == "nonconforming"
    assert [r["action"] for r in results[2:]] == ["held_template"] * (len(DAY_HOURS) - 2)
    assert len(veto_pings(pings)) == 1 and replies() == []
    # a change the check looks at (the company) re-opens it once, for a full window
    state.company = "Brightside Facility Care"
    opened = cadence.tick_lead(state, ct(2026, 9, 23, 9, 30), store=store, free_slots=FREE,
                               notify_fn=lambda *a, **k: pings.append((a, k)) or {"email": True})
    assert opened["action"] == "veto_window_opened" and len(veto_pings(pings)) == 2
    pinged = slot_rules.parse_iso(state.cadence["veto_notified_at"])
    assert slot_rules.parse_iso(state.cadence["next_send_at"]) - pinged >= timedelta(minutes=30)


def test_d1_copy_blocked_opens_no_window_and_is_reported_as_blocked_copy(store, tmp_env, d1_live, monkeypatch):
    monkeypatch.setattr(cadence.Touch, "problems", property(lambda self: ["banned phrase: test"]))
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    first = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, free_slots=FREE,
                              notify_fn=lambda *a, **k: pings.append((a, k)))
    assert first["action"] == "not_due" and first["reason"] == "d1_copy_blocked" and pings == []
    due = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=FREE,
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert due["action"] == "blocked_copy" and veto_pings(pings) == [] and replies() == []
    assert state.cadence.get("veto_notified_at") is None


def test_d1_never_goes_out_live_without_a_window_even_past_a_copy_block(store, tmp_env, d1_live, monkeypatch):
    """The pre-check saw a copy problem the send-time build does not: the day
    is not sent without its Veto window (belt and braces)."""
    calls = {"n": 0}

    def problems(self):
        calls["n"] += 1
        return ["banned phrase: test"] if calls["n"] == 1 else []
    monkeypatch.setattr(cadence.Touch, "problems", property(problems))
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "not_due" and res["reason"] == "veto_window_not_open" and replies() == []


# ======================================================= 3. stall causes
def test_every_gate_reason_has_a_hold_cause():
    classified = (set(cadence.SYSTEM_HOLD_REASONS) | set(cadence.APPROVE_HOLD_REASONS)
                  | set(cadence.LEAD_DATA_HOLD_REASONS) | set(cadence.CODE_HOLD_REASONS))
    assert set(gate.REASONS) - {"ok"} <= classified
    for reason in ("kill_switch", "parity_failed", "registry_error", "not_ready", "something_new"):
        assert cadence.hold_cause(reason) == "system"
    assert cadence.hold_cause("unapproved") == cadence.hold_cause("changed_since_approval") == "approve"
    assert cadence.hold_cause("nonconforming") == cadence.hold_cause("copy_gate") == "lead_data"
    for reason in gate.REASONS:
        advice = cadence.hold_advice(reason)
        assert advice and "http" not in advice and "@" not in advice


def test_kill_switch_for_a_week_holds_never_stops_and_sends_late_once_off(store, tmp_env, approvals_file):
    approvals_file.kill_switch(True)
    state = at_day(2, ct(2026, 9, 21, 10, 0))  # Monday, D3 due
    pushes = []
    results = []
    for day in (21, 22, 23, 24, 25, 28):  # Mon .. Fri, then Mon
        now = ct(2026, 9, day, 10, 0)
        results.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                         notify_fn=lambda *a, **k: pushes.append((a, k))))
    assert [r["action"] for r in results] == ["held_template"] * 6
    assert {r["reason"] for r in results} == {"kill_switch"} and {r["cause"] for r in results} == {"system"}
    assert not state.cadence.get("stopped_reason") and pushes == []
    assert state.cadence["template_hold"]["since"] is None
    line = cadence.summarize_touch(results[0])
    assert "kill switch" in line and "Approve the ids" not in line and "Nothing is stopped" in line
    approvals_file.kill_switch(False)
    now = ct(2026, 9, 28, 11, 0)
    sent = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                             notify_fn=lambda *a, **k: None)
    assert sent["action"] == "would_send" and sent["day"] == 3 and len(replies()) == 1


def test_kill_switch_on_a_d1_pings_nothing_and_a_fresh_window_opens_once_off(store, tmp_env, d1_live,
                                                                            approvals_file):
    approvals_file.kill_switch(True)
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    for day in (22, 23, 24, 25):
        for h, m in ((9, 30), (10, 0), (15, 0)):
            res = cadence.tick_lead(state, ct(2026, 9, day, h, m), store=store, free_slots=FREE,
                                    notify_fn=lambda *a, **k: pings.append((a, k)) or {"email": True})
            assert res["action"] == "held_template" and res["reason"] == "kill_switch"
    assert pings == [] and not state.cadence.get("stopped_reason")
    approvals_file.kill_switch(False)
    opened = cadence.tick_lead(state, ct(2026, 9, 25, 16, 0), store=store, free_slots=FREE,
                               notify_fn=lambda *a, **k: pings.append((a, k)) or {"email": True})
    assert opened["action"] == "veto_window_opened"
    pinged = slot_rules.parse_iso(state.cadence["veto_notified_at"])
    assert slot_rules.parse_iso(state.cadence["next_send_at"]) - pinged >= timedelta(minutes=30)
    assert replies() == []


@pytest.mark.parametrize("reason", ["parity_failed", "registry_error"])
def test_other_gate_wide_holds_never_stop_a_ladder(store, tmp_env, monkeypatch, reason):
    def refused(template_id, parts=()):
        return gate.Verdict(False, reason, template_id, [template_id] + list(parts or ()), {})
    monkeypatch.setattr(cadence, "_template_ids_verdict", refused)
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    for day in (21, 22, 23, 24, 25):
        now = ct(2026, 9, day, 10, 0)
        res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                notify_fn=lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "held_template" and res["cause"] == "system"
    assert not state.cadence.get("stopped_reason") and pushes == []


def test_three_days_nonconforming_stops_with_lead_data_advice(store, tmp_env, secret, email_leg):
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    state.first_name = "N/A"
    pushes = []
    results = []
    for day in (21, 22, 23, 24):
        now = ct(2026, 9, day, 10, 0)
        results.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                         notify_fn=lambda *a, **k: pushes.append((a, k))))
    assert [r["action"] for r in results] == ["held_template"] * 3 + ["stopped"]
    assert results[-1]["held_reason"] == "nonconforming"
    assert state.cadence["stopped_reason"] == "template_unapproved"
    assert len(pushes) == 1
    (title, message), kw = pushes[0]
    assert "Approving changes nothing" in message and "Approve the ids" not in message
    line = cadence.summarize_touch(results[-1])
    assert "Approving changes nothing" in line and "Resume" in line
    for private in (LEAD, COMPANY, "Dana", "http"):
        assert private not in title and private not in message
    assert LEAD in kw["email_message"] and RESUME_RE.search(kw["email_message"])
    assert not kw.get("actions") and not kw.get("click")


def test_a_gate_wide_hold_does_not_advance_the_stall_clock(store, tmp_env, approvals_file):
    """Kill switch Mon to Wed, then the template is unapproved from Thursday:
    the stall counts from Thursday, so it stops the following Tuesday."""
    approvals_file.kill_switch(True)
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    for day in (21, 22, 23):
        now = ct(2026, 9, day, 10, 0)
        cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                          notify_fn=lambda *a, **k: None)
    approvals_file.kill_switch(False)
    approvals_file.revoke_ids("cadence.e3")
    actions = []
    for day in (24, 25, 28, 29):
        now = ct(2026, 9, day, 10, 0)
        actions.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                         notify_fn=lambda *a, **k: None)["action"])
    assert actions == ["held_template", "held_template", "held_template", "stopped"]


def _ten_oclock_ticks(state, store, days, pushes, before=None):
    """One 10:00 CT tick per September 2026 date in ``days``; ``before`` maps
    a date to what changes just before that day's tick. Returns the results
    and, per tick, (day, action, cause, reason, days)."""
    results = []
    for day in days:
        if before and day in before:
            before[day]()
        now = ct(2026, 9, day, 10, 0)
        results.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                         notify_fn=lambda *a, **k: pushes.append((a, k))))
    return results, [(day, r["action"], r.get("cause"), r.get("held_reason") or r.get("reason"), r.get("days"))
                     for day, r in zip(days, results)]


def test_an_approval_hold_then_the_kill_switch_never_stops_on_a_kill_switch_tick(store, tmp_env, approvals_file):
    """Unapproved Mon and Tue, then the kill switch Wed to Fri: those ticks
    hold and never stop the ladder, however long ago the first hold was, and
    they do not count. Still unapproved once the switch is off: the second
    approval hold continues the count (Mon 28 is the third held day, Tue 29
    the fourth), and the stop is worded for that cause."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    _, ticks = _ten_oclock_ticks(state, store, (21, 22, 23, 24, 25, 28, 29), pushes, before={
        23: lambda: approvals_file.kill_switch(True), 28: lambda: approvals_file.kill_switch(False)})
    assert ticks == [
        (21, "held_template", "approve", "unapproved", 0),
        (22, "held_template", "approve", "unapproved", 1),
        (23, "held_template", "system", "kill_switch", 1),
        (24, "held_template", "system", "kill_switch", 1),
        (25, "held_template", "system", "kill_switch", 1),
        (28, "held_template", "approve", "unapproved", 2),
        (29, "stopped", "approve", "unapproved", 3),
    ]
    assert len(pushes) == 1
    message = pushes[0][0][1]
    assert "reason: unapproved" in message and cadence.hold_advice("unapproved") in message
    assert cadence.hold_advice("kill_switch") not in message
    assert state.cadence["template_hold"]["held_days"] == 4


def test_an_id_approved_during_the_kill_switch_goes_out_once_it_is_off(store, tmp_env, approvals_file):
    """Unapproved Mon and Tue; the kill switch goes on Wednesday and the id is
    approved while it is on. Nothing stops the ladder in the meantime (the
    old clock stopped it on Thursday, a kill-switch tick); the day goes out
    on the first tick after the switch is off."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    _, ticks = _ten_oclock_ticks(state, store, (21, 22, 23, 24, 25, 28), pushes, before={
        23: lambda: approvals_file.kill_switch(True), 24: lambda: approvals_file.approve_ids("cadence.e3"),
        28: lambda: approvals_file.kill_switch(False)})
    assert [t[1] for t in ticks] == ["held_template"] * 5 + ["would_send"]
    assert [t[2] for t in ticks[2:5]] == ["system"] * 3
    assert pushes == [] and not state.cadence.get("stopped_reason") and len(replies()) == 1
    assert "template_hold" not in state.cadence


def test_unapproved_kill_switch_unapproved_counts_only_the_unapproved_days(store, tmp_env, approvals_file):
    """Unapproved, kill switch, unapproved, kill switch, unapproved, kill
    switch, unapproved: only the four unapproved days count, the ladder is
    never stopped on a kill-switch tick (Thu 24 and Mon 28 are three and
    five business days after the first hold), and it stops on the fourth
    unapproved day."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    on, off = (lambda: approvals_file.kill_switch(True)), (lambda: approvals_file.kill_switch(False))
    _, ticks = _ten_oclock_ticks(state, store, (21, 22, 23, 24, 25, 28, 29), pushes,
                                 before={22: on, 23: off, 24: on, 25: off, 28: on, 29: off})
    assert [(t[0], t[1], t[2]) for t in ticks] == [
        (21, "held_template", "approve"), (22, "held_template", "system"), (23, "held_template", "approve"),
        (24, "held_template", "system"), (25, "held_template", "approve"), (28, "held_template", "system"),
        (29, "stopped", "approve")]
    assert [t[4] for t in ticks] == [0, 0, 1, 1, 2, 2, 3]
    assert len(pushes) == 1 and cadence.hold_advice("unapproved") in pushes[0][0][1]


def test_the_stall_counts_across_causes_and_the_stop_names_the_last_one(store, tmp_env, approvals_file):
    """Unapproved Mon to Wed, then approved on Thursday, when the lead's first
    name fails the placeholder rules: the count goes on, and the stop's
    advice is about the lead's data, not "approve the ids"."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    state.first_name = "N/A"
    pushes = []
    results, ticks = _ten_oclock_ticks(state, store, (21, 22, 23, 24), pushes,
                                       before={24: lambda: approvals_file.approve_ids("cadence.e3")})
    assert [t[1:4] for t in ticks] == [("held_template", "approve", "unapproved")] * 3 + [
        ("stopped", "lead_data", "nonconforming")]
    assert len(pushes) == 1
    message = pushes[0][0][1]
    assert "reason: nonconforming" in message and cadence.hold_advice("nonconforming") in message
    assert cadence.hold_advice("unapproved") not in message
    line = cadence.summarize_touch(results[-1])
    assert "(nonconforming)" in line and "Approving changes nothing" in line and "Approve the ids" not in line


# ======================================================== 2. resume link
def stall(state, store, pushes, notify_fn=None):
    """Held Mon to Thu, stopped on Thursday; the stop push goes to ``pushes``
    (or to ``notify_fn``, e.g. shared.notify.notify, which only records)."""
    fn = notify_fn or (lambda *a, **k: pushes.append((a, k)))
    for day in (21, 22, 23, 24):  # Mon .. Thu
        now = ct(2026, 9, day, 10, 0)
        res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now), notify_fn=fn)
    assert res["action"] == "stopped" and res["reason"] == "template_unapproved"
    store.set(state.key, state.to_store())
    return res


def link_of(push):
    """The Resume link of a push on a public topic with the email leg set:
    ids and counts on ntfy, the lead and the link on the email leg only."""
    (title, message), kw = push
    for private in (LEAD, COMPANY, "Dana", "http"):
        assert private not in title and private not in message
    assert not kw.get("actions") and not kw.get("click")
    found = RESUME_RE.search(kw["email_message"])
    assert found and LEAD in kw["email_message"]
    return found.group(1)


def ntfy_link_of(push):
    """The Resume link of a push on a protected topic: the push itself names
    the lead and carries the link, as text and as a Resume button (a view
    action); no click, and no separate email body."""
    (title, message), kw = push
    found = RESUME_RE.search(message)
    assert found and LEAD in message and "email_message" not in kw and not kw.get("click")
    assert kw["actions"] == [("Resume", found.group(1))]
    return found.group(1)


def tick_stored(store, now, notify_fn):
    state = LeadState.from_store(store.get(_key()))
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                            notify_fn=notify_fn)
    store.set(state.key, state.to_store())
    return state, res


def _key():
    return make_state().key


@pytest.fixture
def client(store):
    app_mod.configure(store=store, clock=lambda: ct(2026, 9, 24, 11, 30))
    try:
        yield TestClient(app_mod.app)
    finally:
        app_mod.configure()


def test_template_stop_resume_end_to_end(store, tmp_env, secret, email_leg, approvals_file, client):
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    stall(state, store, pushes)
    assert len(pushes) == 1
    url = link_of(pushes[0])
    assert url.startswith("https://engine.test/cadence/resume/") and "?t=" in url
    path = url[len("https://engine.test"):]

    # before the ids are approved: the page says so, GET changes nothing
    page = client.get(path)
    assert page.status_code == 200 and "do NOT pass" in page.text and "cadence.e3" in page.text
    assert LEAD not in page.text and COMPANY not in page.text
    assert store.get(_key())["cadence"]["stopped_reason"] == "template_unapproved"
    assert client.post(path.split("?")[0]).status_code == 403
    assert client.post(path.split("?")[0] + "?t=2026-09-30T00:00:00-05:00.deadbeef").status_code == 403

    # approved: the next tick re-signs the link at once, on the email leg
    approvals_file.approve_ids("cadence.e3")
    later = []
    _, res = tick_stored(store, ct(2026, 9, 24, 11, 0), lambda *a, **k: later.append((a, k)))
    assert res["action"] == "resume_link_sent" and res["ready"] is True and len(later) == 1
    assert "approved" in later[0][0][0] and later[0][1]["priority"] == "high"
    path = link_of(later[0])[len("https://engine.test"):]
    # said once: the next tick stays quiet
    _, res = tick_stored(store, ct(2026, 9, 24, 11, 15), lambda *a, **k: later.append((a, k)))
    assert res["action"] == "already_stopped" and len(later) == 1

    page = client.get(path)
    assert page.status_code == 200 and "pass the template gate now" in page.text
    ok = client.post(path)
    assert ok.status_code == 200 and "Resumed" in ok.text and "template gate" in ok.text
    resumed = LeadState.from_store(store.get(_key()))
    assert not resumed.cadence.get("stopped_reason") and "template_hold" not in resumed.cadence

    # the next tick sends: approved, every send check passes
    now = ct(2026, 9, 24, 12, 0)
    sent = cadence.tick_lead(resumed, now, store=store, free_slots=cadence.default_slot_grid(now),
                             notify_fn=lambda *a, **k: None)
    assert sent["action"] == "would_send" and sent["day"] == 3 and len(replies()) == 1


def test_resume_before_approval_sends_nothing_and_holds_again(store, tmp_env, secret, email_leg, approvals_file,
                                                              client):
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    stall(state, store, pushes)
    path = link_of(pushes[0])[len("https://engine.test"):]
    assert client.post(path).status_code == 200
    resumed = LeadState.from_store(store.get(_key()))
    now = ct(2026, 9, 24, 12, 0)
    held = cadence.tick_lead(resumed, now, store=store, free_slots=cadence.default_slot_grid(now),
                             notify_fn=lambda *a, **k: None)
    assert held["action"] == "held_template" and held["reason"] == "unapproved" and replies() == []
    assert not resumed.cadence.get("stopped_reason")


def test_resume_with_an_opted_out_lead_still_sends_nothing(store, tmp_env, secret, email_leg, approvals_file,
                                                           client):
    """An approved template never bypasses a send check: the opt-out marker
    set while the ladder was stopped still stops it after the Resume."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    stall(state, store, pushes)
    path = link_of(pushes[0])[len("https://engine.test"):]
    approvals_file.approve_ids("cadence.e3")
    assert client.post(path).status_code == 200
    resumed = LeadState.from_store(store.get(_key()))
    resumed.opt_out = {"reason": "unsubscribe"}
    now = ct(2026, 9, 24, 12, 0)
    res = cadence.tick_lead(resumed, now, store=store, free_slots=cadence.default_slot_grid(now),
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "stopped" and res["reason"] == "opt_out" and replies() == []


def test_the_resume_link_is_re_signed_every_day_the_ladder_stays_stopped(store, tmp_env, secret, email_leg,
                                                                          approvals_file):
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    stall(state, store, pushes)
    links = [link_of(pushes[0])]
    for day, hours in ((24, (11, 12)), (25, (7, 8, 12)), (26, (7,)), (27, (7,)), (28, (7, 10))):
        for h in hours:
            before = len(pushes)
            _, res = tick_stored(store, ct(2026, 9, day, h, 0), lambda *a, **k: pushes.append((a, k)))
            if len(pushes) > before:
                assert res["action"] == "resume_link_sent" and res["ready"] is False
                assert pushes[-1][1]["priority"] == "low" and "Approve the ids" in pushes[-1][0][1]
                links.append(link_of(pushes[-1]))
            else:
                assert res["action"] == "already_stopped"
    assert len(links) == 5  # Thu (the stop), Fri, Sat, Sun, Mon: never more than a day old
    stopped = LeadState.from_store(store.get(_key()))
    token = links[-1].split("?t=", 1)[1]
    from urllib.parse import unquote

    assert cadence.verify_decision_token("resume", stopped, unquote(token), ct(2026, 9, 29, 10, 0)) is True


def test_no_secret_means_no_link_and_says_so(store, tmp_env, email_leg, approvals_file, monkeypatch):
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    res = stall(state, store, pushes)
    assert res["resume_link"] is False
    assert "No Resume link could be signed" in pushes[0][1]["email_message"]
    assert not RESUME_RE.search(pushes[0][1]["email_message"])
    _, res = tick_stored(store, ct(2026, 9, 25, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "already_stopped" and len(pushes) == 1


def test_the_hourly_job_persists_the_re_signed_link(store, tmp_env, secret, email_leg, approvals_file):
    from jobs import cadence_tick as job

    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    stall(state, store, [])
    pushes = []
    summary = job.run(ct(2026, 9, 25, 7, 0), store, notify_fn=lambda *a, **k: pushes.append((a, k)),
                      log_fn=lambda *a, **k: None)
    assert summary["counts"] == {"resume_link_sent": 1} and len(pushes) == 1
    assert store.get(_key())["cadence"]["template_hold"]["link_on"] == "2026-09-25"
    summary = job.run(ct(2026, 9, 25, 8, 0), store, notify_fn=lambda *a, **k: pushes.append((a, k)),
                      log_fn=lambda *a, **k: None)
    assert summary["counts"] == {"already_stopped": 1} and len(pushes) == 1


# ================================================ 4. where the link goes
def test_a_protected_topic_without_email_carries_the_link_in_the_push(store, tmp_env, secret, protected_topic,
                                                                      approvals_file, client):
    """NTFY_TOKEN and no email leg (deployment.md accepts it): the stop push
    itself names the lead and carries the signed link, as text and as a
    Resume button; the link resumes the ladder. shared.notify's own record
    shows what a live run would put on each leg."""
    from shared import notify

    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    notify.reset_for_tests()
    res = stall(state, store, None, notify_fn=notify.notify)
    assert res["resume_link"] is True and res["resume_link_via"] == "ntfy" and "resume_link_missing" not in res
    rec = notify.sent_in_test[-1]
    found = RESUME_RE.search(rec["message"])
    assert found and LEAD in rec["message"] and "/cadence/resume/" in found.group(1)
    assert rec["actions"] == "view, Resume, %s" % found.group(1)
    assert rec["click"] is None and "email_message" not in rec
    hold = store.get(_key())["cadence"]["template_hold"]
    assert hold["link_on"] == "2026-09-24" and hold["link_via"] == "ntfy"
    line = cadence.summarize_touch(res)
    assert "Resume link in the push" in line and "http" not in line

    # the next morning's link goes the same way, and it works
    pushes = []
    _, again = tick_stored(store, ct(2026, 9, 25, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert again["action"] == "resume_link_sent" and again["resume_link_via"] == "ntfy"
    url = ntfy_link_of(pushes[0])
    assert "fresh Resume link was sent in the push" in cadence.summarize_touch(dict(again, lead_email=LEAD))
    approvals_file.approve_ids("cadence.e3")
    path = url[len("https://engine.test"):]
    assert client.post(path).status_code == 200
    assert not LeadState.from_store(store.get(_key())).cadence.get("stopped_reason")


def test_a_public_topic_with_email_carries_the_link_on_the_email_leg_only(store, tmp_env, secret, email_leg,
                                                                           approvals_file):
    from shared import notify

    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    notify.reset_for_tests()
    res = stall(state, store, None, notify_fn=notify.notify)
    assert res["resume_link"] is True and res["resume_link_via"] == "email"
    rec = notify.sent_in_test[-1]
    for private in (LEAD, COMPANY, "Dana", "http", "/cadence/resume/"):
        assert private not in rec["title"] and private not in rec["message"]
    assert "in the email for this stop" in rec["message"]
    assert not rec["actions"] and rec["click"] is None
    assert RESUME_RE.search(rec["email_message"]) and LEAD in rec["email_message"]
    hold = store.get(_key())["cadence"]["template_hold"]
    assert hold["link_on"] == "2026-09-24" and hold["link_via"] == "email"
    assert "Resume link in the email" in cadence.summarize_touch(res)


def test_a_public_topic_without_email_says_no_channel_and_records_no_link(store, tmp_env, secret, no_channel,
                                                                          approvals_file, monkeypatch):
    """No leg can carry the link: the push says so and what to set, the
    result and the row do not claim a link went out, and no daily
    reminder claims one either. Once a leg exists, the next tick sends it."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    res = stall(state, store, pushes)
    assert res["resume_link"] is False and res["resume_link_via"] is None
    assert res["resume_link_missing"] == "no_channel"
    (title, message), kw = pushes[0]
    assert set(kw) == {"priority", "tags"}  # no email_message, no actions, no click
    assert "No channel can carry the Resume link" in message
    for key in ("NTFY_TOKEN", "NOTIFY_EMAIL", "GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "deployment.md"):
        assert key in message
    for private in (LEAD, COMPANY, "Dana", "http"):
        assert private not in title and private not in message
    hold = store.get(_key())["cadence"]["template_hold"]
    assert "link_on" not in hold and "link_via" not in hold and "link_at" not in hold
    line = cadence.summarize_touch(res)
    assert "No Resume link was sent: no channel can carry one" in line and "Then open" not in line
    # the next mornings: nothing claims a link
    for when in (ct(2026, 9, 25, 7, 0), ct(2026, 9, 28, 7, 0)):
        _, quiet = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert quiet["action"] == "already_stopped"
    assert len(pushes) == 1
    # a protected topic is set up: the next tick sends the link on it
    monkeypatch.setenv("NTFY_TOKEN", "unit-token-not-real")
    _, sent = tick_stored(store, ct(2026, 9, 28, 8, 0), lambda *a, **k: pushes.append((a, k)))
    assert sent["action"] == "resume_link_sent" and sent["resume_link_via"] == "ntfy" and len(pushes) == 2
    ntfy_link_of(pushes[-1])
    assert store.get(_key())["cadence"]["template_hold"]["link_on"] == "2026-09-28"


# ============================================ 5. a lead the ladder is over for
@pytest.mark.parametrize("mark,expected", [
    ({"opt_out": {"reason": "unsubscribe"}}, "opt_out"),
    ({"status": "blocklisted"}, "unsubscribe"),
    ({"status": "booked"}, "booked"),
    ({"status": "negative_notnow"}, "follow_up_later"),
    ({"status": "negative_hostile"}, "hostile"),
])
def test_no_reminder_and_no_ready_push_for_a_lead_the_ladder_is_over_for(store, tmp_env, secret, email_leg,
                                                                         approvals_file, mark, expected):
    """A Resume would stop such a ladder again at once, so once the lead
    opted out, was blocklisted, booked or answered for good while the ladder
    was stopped, no daily link and no "ready to resume" push goes out, even
    after the held ids are approved."""
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    stall(state, store, pushes)
    stopped = LeadState.from_store(store.get(_key()))
    for field, value in mark.items():
        setattr(stopped, field, value)
    store.set(stopped.key, stopped.to_store())
    approvals_file.approve_ids("cadence.e3")
    for when in (ct(2026, 9, 24, 11, 0), ct(2026, 9, 25, 7, 0), ct(2026, 9, 28, 7, 0)):
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "already_stopped" and res["resume_withheld"] == expected
    assert len(pushes) == 1
    hold = store.get(_key())["cadence"]["template_hold"]
    assert hold["link_on"] == "2026-09-24" and not hold.get("ready_announced")


# =============================================== 6. a stale D1 refusal
def _old_name_rule(monkeypatch):
    """The "old" gate: its name rule refuses Dana. Returns the real rule."""
    real = gate._name_ok
    monkeypatch.setattr(gate, "_name_ok", lambda v, *a, **k: False if v == "Dana" else real(v, *a, **k))
    gate.clear_cache()
    return real


def _deploy(monkeypatch, real_rule, bump):
    """A deploy that relaxes the rule again (a new process: empty caches),
    bumping template_gate.GATE_RULES_VERSION with it or not."""
    monkeypatch.setattr(gate, "_name_ok", real_rule)
    if bump:
        monkeypatch.setattr(gate, "GATE_RULES_VERSION", gate.GATE_RULES_VERSION + 1)
    gate.clear_cache()


def _d1_ticks(state, store, pings, day, hours=((9, 30), (10, 0), (11, 0), (14, 0), (18, 0))):
    """Live ticks on one September 2026 date, each with fresh free slots."""
    out = []
    for h, m in hours:
        now = ct(2026, 9, day, h, m)
        out.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                     notify_fn=lambda *a, **k: pings.append((a, k)) or {"email": True}))
    return out


def _window_then_send(state, store, pings):
    """The window that just opened lasts its full 30 minutes, pings nothing
    more, and the D1 goes out at its send time."""
    pinged = slot_rules.parse_iso(state.cadence["veto_notified_at"])
    send_at = slot_rules.parse_iso(state.cadence["next_send_at"])
    assert send_at - pinged >= timedelta(minutes=cadence.VETO_WINDOW_MINUTES)
    for when in (pinged + timedelta(minutes=20), send_at):
        res = cadence.tick_lead(state, when, store=store, free_slots=cadence.default_slot_grid(when),
                                notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "would_send" and res["day"] == 1 and len(replies()) == 1
    assert "d1_gate_hold" not in state.cadence


def test_a_rule_relaxed_by_a_deploy_reopens_the_d1_window_exactly_once(store, tmp_env, d1_live, monkeypatch):
    real = _old_name_rule(monkeypatch)
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    held = _d1_ticks(state, store, pings, 22, ((9, 30), (10, 0), (11, 0)))
    assert [r["action"] for r in held] == ["held_template"] * 3 and pings == []
    assert state.cadence["d1_gate_hold"]["reason"] == "nonconforming"
    _deploy(monkeypatch, real, bump=True)
    opened = _d1_ticks(state, store, pings, 22, ((12, 0),))[0]
    assert opened["action"] == "veto_window_opened" and len(veto_pings(pings)) == 1
    _window_then_send(state, store, pings)
    assert len(veto_pings(pings)) == 1


def test_the_d1_fingerprint_follows_the_gate_rules_version_and_the_catalogue(tmp_env, monkeypatch):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    touch = cadence.build_touch(state, 1, cadence.fresh_slots(state, ct(2026, 9, 22, 9, 30), FREE, None))
    verdict = cadence._template_touch_verdict(state, touch)
    base = cadence._d1_gate_fingerprint(state, touch, verdict)
    assert cadence._d1_gate_fingerprint(state, touch, verdict) == base
    monkeypatch.setattr(gate, "GATE_RULES_VERSION", gate.GATE_RULES_VERSION + 1)
    bumped = cadence._d1_gate_fingerprint(state, touch, verdict)
    assert bumped != base
    monkeypatch.setattr(gate, "catalogue_digest_cached", lambda: "0" * 64)
    assert cadence._d1_gate_fingerprint(state, touch, verdict) not in (base, bumped)


def test_the_catalogue_digest_is_computed_once_per_catalogue_build(tmp_env, monkeypatch):
    gate.clear_cache()
    calls = []
    real = gate.catalogue_digest
    monkeypatch.setattr(gate, "catalogue_digest", lambda index=None: calls.append(1) or real(index))
    first = gate.catalogue_digest_cached()
    for _ in range(50):
        assert gate.catalogue_digest_cached() == first
    assert len(calls) == 1 and first == real()[0]
    gate.clear_cache()
    assert gate.catalogue_digest_cached() == first and len(calls) == 2


def test_resume_after_a_stale_refusal_gives_one_fresh_window(store, tmp_env, d1_live, monkeypatch):
    """A rule relaxed without the version bump leaves the refusal's
    fingerprint as it was: no false ping, the D1 stays held and the stall
    stops the ladder on its fourth held day. Resume drops the refusal: the
    next tick runs the full check afresh, and its pass opens exactly one
    fresh 30-minute window."""
    real = _old_name_rule(monkeypatch)
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    _d1_ticks(state, store, pings, 22, ((9, 30),))
    _deploy(monkeypatch, real, bump=False)
    results = []
    for day in (22, 23, 24, 25):
        results += _d1_ticks(state, store, pings, day)
    assert [r["action"] for r in results] == ["held_template"] * 15 + ["stopped"] + ["already_stopped"] * 4
    assert state.cadence["stopped_reason"] == "template_unapproved" and veto_pings(pings) == []
    assert cadence.resume_after_recipient_hold(state, ct(2026, 9, 28, 9, 0))["resumed"] is True
    assert "d1_gate_hold" not in state.cadence
    opened = _d1_ticks(state, store, pings, 28, ((9, 30),))[0]
    assert opened["action"] == "veto_window_opened" and len(veto_pings(pings)) == 1
    _window_then_send(state, store, pings)
    assert len(veto_pings(pings)) == 1


def test_a_send_time_refusal_after_resume_is_recorded_again_and_pings_once(store, tmp_env, d1_live, monkeypatch):
    """The pre-check passes but the send-time check refuses. Held for the
    stall, stopped, resumed: Resume gives one fresh window, the send-time
    check refuses again and that refusal is recorded again, so the window
    does not re-open on the later ticks."""
    real_slots, real_verdict = cadence._d1_precheck_slots, cadence._template_touch_verdict
    pre = {"check": False}

    def precheck_slots(state, now, store, free):
        pre["check"] = True
        return real_slots(state, now, store, free)

    def verdict(state, touch):
        v = real_verdict(state, touch)
        at_precheck, pre["check"] = pre["check"], False
        if v.allowed and not at_precheck:
            return gate.Verdict(False, "nonconforming", v.template_id, list(v.ids), dict(v.statuses))
        return v
    monkeypatch.setattr(cadence, "_d1_precheck_slots", precheck_slots)
    monkeypatch.setattr(cadence, "_template_touch_verdict", verdict)

    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    first = _d1_ticks(state, store, pings, 22)
    assert [r["action"] for r in first] == ["veto_window_opened"] + ["held_template"] * 4
    for day in (23, 24, 25):
        _d1_ticks(state, store, pings, day)
    assert state.cadence["stopped_reason"] == "template_unapproved" and len(veto_pings(pings)) == 1
    assert cadence.resume_after_recipient_hold(state, ct(2026, 9, 28, 9, 0))["resumed"] is True
    after = _d1_ticks(state, store, pings, 28)
    assert [r["action"] for r in after] == ["veto_window_opened"] + ["held_template"] * 4
    assert after[1]["reason"] == "nonconforming" and not after[1]["quiet"]
    assert state.cadence["d1_gate_hold"]["reason"] == "nonconforming"
    later = _d1_ticks(state, store, pings, 29)
    assert [r["action"] for r in later] == ["held_template"] * 5
    assert len(veto_pings(pings)) == 2 and replies() == []
