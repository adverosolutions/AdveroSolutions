"""The S4 confirmation coupling: which inbound replies may mark a booked call
confirmed, and therefore switch off the 4 h "no C yet" safety net.

``app.py::_appointment_hooks`` is the only place that calls
``show_rate.mark_confirmed``. Its ``confirmation_skipped`` guard had no test
anywhere in the repo (``grep -rn confirmation_skipped`` returned one hit, the
code itself), and eleven of the 44 recorded September replies are
auto-responders whose first words match the confirmation regex.
"""
from datetime import datetime, timedelta

import httpx
import pytest

from shared import slots
from shared.ghl import GHL
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import show_rate as sr
from services.reply_engine.models import Classification, LeadState

NOW = datetime.fromisoformat("2026-09-21T17:10:00-05:00")
START = "2026-09-23T14:00:00-05:00"
APPT_ID = "gcal_confirm_hook_1"

ILMI = {
    "id": APPT_ID,
    "contact_id": "cnfZoGRCRi3JMqZfo0XD",
    "first_name": "Ilmi",
    "company": "Shining Armor Cleaning NJ",
    "email": "ilmi@shiningarmorcleaningnj.com",
    "niche": "cleaning",
    "offer": "reactivation",
    "start_iso": START,
    "end_iso": "2026-09-23T14:15:00-05:00",
    "zoom_link": "https://zoom.us/j/000000000001",
    "booked_at": NOW.isoformat(),
}


class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})


def make_ghl():
    rec = Recorder()
    return GHL(token=None, transport=httpx.MockTransport(rec)), rec


def lead_state():
    return LeadState(lead_email=ILMI["email"], campaign_id="camp1",
                     cadence={"booking": {"appointment_id": APPT_ID, "slot": START}})


def hooks(store, body, label=None):
    classification = Classification(label=label, confidence=0.95, reason="test") if label else None
    return app_mod._appointment_hooks(lead_state(), body, store, NOW, classification)


def names(out):
    return [h["hook"] for h in out]


def scheduled_store(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, _rec = make_ghl()
    sr.run(NOW - timedelta(minutes=5), store, ghl, appointments=[ILMI])
    return store


def test_a_plain_c_confirms_the_call(tmp_env, shadow_mode):
    store = scheduled_store(tmp_env)
    assert names(hooks(store, "C")) == ["show_rate.mark_confirmed"]
    assert store.get(sr.confirmed_key(APPT_ID))["start_iso"] == START
    assert sr.is_confirmed(store, ILMI) is True


def test_an_out_of_office_does_not_confirm_the_call(tmp_env, shadow_mode):
    """An auto-responder that opens "Sure, thanks for reaching out. I am
    currently out of the office" matches the confirmation regex word for word.
    Confirming on it kills the 4 h safety net for a lead who said nothing."""
    store = scheduled_store(tmp_env)
    body = ("Sure, thanks for reaching out. I am currently out of the office and will return "
            "on Tuesday. For anything urgent please contact Barbara.")
    out = hooks(store, body, label="ooo")
    assert names(out) == ["confirmation_skipped"]
    assert out[0]["reason"] == "label:ooo"
    assert store.get(sr.confirmed_key(APPT_ID)) is None
    assert sr.is_confirmed(store, ILMI) is False
    # ...and the 4 h "text or call them personally" task still fires
    ghl, _rec = make_ghl()
    four_hours_before = slots.parse_iso(START) - timedelta(hours=3, minutes=59)
    res = sr.run(four_hours_before, store, ghl)
    assert "unconfirmed_task" in [e["template"] for e in res["would_do"]]


@pytest.mark.parametrize("label", ["auto_reply_unmonitored", "unsubscribe", "negative_hostile",
                                   "negative_notfit", "wrong_person"])
def test_no_non_confirming_label_can_confirm_the_call(tmp_env, shadow_mode, label):
    store = scheduled_store(tmp_env)
    out = hooks(store, "Sure, sounds good.", label=label)
    assert names(out) == ["confirmation_skipped"]
    assert store.get(sr.confirmed_key(APPT_ID)) is None


def test_ilmis_sure_lets_get_together_monday_is_a_reschedule_not_a_confirmation(tmp_env, shadow_mode):
    """Her real recorded reply. It opens with a confirmation word but names a
    different time: treating it as a confirmation both kills the safety net and
    leaves the old time armed."""
    store = scheduled_store(tmp_env)
    out = hooks(store, "Sure Let's get together on Monday at 2 CTS that works for me",
                label="positive_interested")
    assert names(out) == ["confirmation_skipped"]
    assert out[0]["reason"] == "reschedule_request"
    assert store.get(sr.confirmed_key(APPT_ID)) is None
    ghl, _rec = make_ghl()
    res = sr.run(slots.parse_iso(START) - timedelta(hours=3, minutes=59), store, ghl)
    assert "unconfirmed_task" in [e["template"] for e in res["would_do"]]


def test_a_question_that_uses_the_word_confirm_does_not_confirm(tmp_env, shadow_mode):
    store = scheduled_store(tmp_env)
    out = hooks(store, "Before we meet, can you confirm what the percentage would be?",
                label="positive_question")
    assert names(out) == []
    assert store.get(sr.confirmed_key(APPT_ID)) is None


def test_an_unlabelled_out_of_office_does_not_confirm_the_call(tmp_env, shadow_mode):
    """The guard used to be label-driven only, so an auto-responder the
    classifier does not label ooo (or a hook called with classification=None,
    its own default) still confirmed the call. Eleven of the 44 recorded
    September replies are auto-responders whose first words match _CONFIRM_RE.

    app._body_is_out_of_office now reads the body with classify.OOO_STRONG_RE,
    so the label is no longer load-bearing."""
    store = scheduled_store(tmp_env)
    body = ("Sure, thanks for reaching out. I am currently out of the office and will return "
            "on Tuesday.")
    assert names(hooks(store, body)) == ["confirmation_skipped"]
    assert store.get(sr.confirmed_key(APPT_ID)) is None
