"""Cadence pushes to Lorenzo name no lead on a public ntfy topic.

runbooks/reply_engine_alerts.md: with neither NTFY_TOKEN nor
NTFY_ALLOW_SENSITIVE=1 set, pushes carry no lead names. shared.notify.redact
only hides emails and URLs, so cadence.py splits each push itself
(cadence._lead_push, the way _resume_push splits a template_unapproved push):
on a public topic the ntfy text has no email, first name or company and the
lead goes on the email leg only (``email_message``); on a protected topic the
push names the lead.

Every notify here is an in-process fake; live-mode tests set MODE=live in
process only and every client is a fake.
"""
import pytest

from shared import llm
from shared.ghl import GHL
from shared.store import JsonFileStore

from services.reply_engine import cadence

from test_send_safety_round2 import FakeInstantly, _d1_state, _go_live, ct  # noqa: F401

EMAIL = "tiffany@flowerhillfs.com"
COMPANY = "Flowerhill Facility Services"
FIRST = "Tiffany"
PRIVATE = (EMAIL, COMPANY, FIRST)
D1_FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]


@pytest.fixture(params=["public", "protected"])
def topic(request, monkeypatch):
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    if request.param == "protected":
        monkeypatch.setenv("NTFY_ALLOW_SENSITIVE", "1")
    return request.param


@pytest.fixture
def linked(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")


@pytest.fixture
def unlinked(monkeypatch):
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)


def _check(push, topic, title_has):
    (title, message), kw = push
    assert title_has in title
    if topic == "public":
        for private in PRIVATE:
            assert private not in title and private not in message, (private, title, message)
        assert EMAIL in kw["email_message"] and COMPANY in kw["email_message"]
        assert kw["email_message"].startswith(message)
    else:
        assert EMAIL in title and "Lead: %s (%s)." % (EMAIL, COMPANY) in message
        assert "email_message" not in kw


def _tick(state, now, store, pings, **kw):
    return cadence.tick_lead(state, now, store=store, notify_fn=lambda *a, **k: pings.append((a, k)), **kw)


def test_d1_held_without_base_url(topic, unlinked, tmp_env, monkeypatch):
    _go_live(monkeypatch)
    state, pings = _d1_state(), []
    res = _tick(state, ct(2026, 9, 22, 9, 30), JsonFileStore(tmp_env / "s.json"), pings,
                instantly=FakeInstantly(sender=EMAIL), free_slots=D1_FREE)
    assert res["action"] == "veto_undeliverable" and res["reason"] == "no_base_url" and len(pings) == 1
    _check(pings[0], topic, "is HELD: no BASE_URL")


@pytest.mark.parametrize("branch", ["window_due", "overdue_unnotified"])
def test_d1_veto_push(branch, topic, linked, tmp_env, monkeypatch):
    """Both D1 Veto pushes: the 09:30 window, and a due D1 whose window was
    never opened (reached by making veto_notify_due say no)."""
    _go_live(monkeypatch)
    if branch == "overdue_unnotified":
        monkeypatch.setattr(cadence, "veto_notify_due", lambda state, now: False)
        now = ct(2026, 9, 22, 10, 0)
    else:
        now = ct(2026, 9, 22, 9, 30)
    state, pings = _d1_state(), []
    res = _tick(state, now, JsonFileStore(tmp_env / "s.json"), pings, instantly=FakeInstantly(sender=EMAIL),
                free_slots=D1_FREE)
    assert res["action"] == "veto_window_opened" and len(pings) == 1
    _check(pings[0], topic, "sends at")
    (title, message), kw = pings[0]
    assert kw["click"] and kw["actions"]  # the Veto link itself is shared.notify's job to strip


def test_cadence_stopped_for_no_bookable_times(topic, linked, tmp_env, monkeypatch):
    _go_live(monkeypatch)
    store = JsonFileStore(tmp_env / "s.json")
    state = cadence.arm(_d1_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    state.cadence["day"] = 2   # E3 is next: a slot email (E2 carries no times)
    pings = []
    for now in (ct(2026, 9, 22, 10, 5), ct(2026, 9, 23, 10, 5)):
        state.cadence["next_send_at"] = now.replace(minute=0).isoformat()
        res = _tick(state, now, store, pings, ghl=GHL(token=None))
    assert res["action"] == "stopped" and res["reason"] == "slots_unavailable" and len(pings) == 1
    _check(pings[0], topic, "no bookable times")


def test_blocked_copy_push_keeps_the_body_off_a_public_topic(topic, tmp_env):
    """The blocked body opens "Hey Tiffany" and may name the company, so on a
    public topic it rides the email leg with the lead line."""
    llm.register_fake("research", lambda system, user, json_mode: "Our bots recovered $50,000 for a similar shop")
    try:
        state = cadence.arm(_d1_state(), ct(2026, 9, 21, 21, 10))
        state.cadence["day"] = 1
        now = ct(2026, 9, 22, 10, 0)
        state.cadence["next_send_at"] = now.isoformat()
        pings = []
        res = _tick(state, now, JsonFileStore(tmp_env / "s.json"), pings,
                    free_slots=cadence.default_slot_grid(now), research_mode="llm")
    finally:
        llm.clear_fakes()
    assert res["action"] == "blocked_copy" and len(pings) == 1
    _check(pings[0], topic, "was blocked")
    (title, message), kw = pings[0]
    body = res["touch"]["body_text"]
    assert FIRST in body
    if topic == "public":
        assert body not in message and kw["email_message"].endswith(body)
    else:
        assert message.endswith(body)
