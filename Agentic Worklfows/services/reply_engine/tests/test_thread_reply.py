"""A1: the in-thread transport for the reminder and no-show ladders.

Every client is a real shared client on an httpx.MockTransport recorder, so
the tests see the exact requests (or their absence). Shadow tests assert zero
requests; live tests (``live_mode``) are still fully mocked."""
import json
from datetime import datetime

import httpx
import pytest

from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import thread_reply as tr
from services.reply_engine.models import LeadState

LEAD = "sopiosvanishvili@taxfoaccounting.com"
CAMPAIGN = "c0ffee00-0000-7000-8000-00000000000a"
OTHER_CAMPAIGN = "c0ffee00-0000-7000-8000-00000000000b"
EMAIL_ID = "01a0c5aa-0000-7000-8000-000000000001"
EACCOUNT = "lorenzo@adveromedia.com"
CONTACT = "iDhesF6A9rhdDajGZuYw"
APPT_ID = "gcal_j8n9pmfjl3cufeiu58g4kp12c8"
# Thursday 10:00 CT: inside the 07:00-19:00 weekday send window
NOW = datetime.fromisoformat("2026-09-24T10:00:00-05:00")
SUBJECT = "Tomorrow at 2:00pm CT"
BODY = "Hi Sopio,\n\nQuick reminder about our call tomorrow at 2:00pm CT.\n\nLorenzo"


class Recorder(object):
    """Records every request; answers GET /emails/<id> with ``sender`` (None:
    no from_address_email) and every POST with ``post_json`` (or
    ``post_status`` / the raw ``post_content``, or raises ``post_raises``)."""

    def __init__(self, sender=LEAD, post_json=None, get_status=200, post_status=200, post_content=None,
                 post_raises=None, post_error="bad"):
        self.requests = []
        self.post_error = post_error
        self.sender = sender
        self.post_json = post_json if post_json is not None else {"id": "sent-1"}
        self.get_status = get_status
        self.post_status = post_status
        self.post_content = post_content
        self.post_raises = post_raises

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            if self.get_status != 200:
                return httpx.Response(self.get_status, json={"error": "boom"})
            payload = {"id": EMAIL_ID}
            if self.sender is not None:
                payload["from_address_email"] = self.sender
            return httpx.Response(200, json=payload)
        if self.post_raises is not None:
            raise self.post_raises("simulated", request=request)
        if self.post_status != 200:
            return httpx.Response(self.post_status, json={"error": self.post_error})
        if self.post_content is not None:
            return httpx.Response(200, content=self.post_content)
        return httpx.Response(200, json=self.post_json)

    def methods(self):
        return [r.method for r in self.requests]

    def posts(self):
        return [(str(r.url), json.loads(r.content or b"{}")) for r in self.requests if r.method == "POST"]


def clients(sender=LEAD, get_status=200, inst_post=None, ghl_post=None):
    irec = Recorder(sender=sender, get_status=get_status, **(inst_post or {}))
    grec = Recorder(post_json={"messageId": "m-1"}, **(ghl_post or {}))
    inst = Instantly(api_key="x", transport=httpx.MockTransport(irec), sleep=lambda s: None)
    ghl = GHL(token="tok", transport=httpx.MockTransport(grec))
    return inst, irec, ghl, grec


@pytest.fixture
def store(tmp_env):
    return JsonFileStore(tmp_env / "s.json")


def lead_row(email=LEAD, campaign_id=CAMPAIGN, **kw):
    base = dict(lead_email=email, campaign_id=campaign_id, first_name="Sopio", company="Taxfo Accounting",
                eaccount=EACCOUNT, thread_id="thread-1", last_email_id=EMAIL_ID,
                last_subject="Re: Sopio, question")
    base.update(kw)
    return LeadState(**base).to_store()


def put_lead(store, email=LEAD, campaign_id=CAMPAIGN, **kw):
    key = "lead:%s:%s" % (campaign_id, email)
    store.set(key, lead_row(email=email, campaign_id=campaign_id, **kw))
    return key


def appt(**kw):
    base = {"id": APPT_ID, "contact_id": CONTACT, "email": LEAD, "campaign_id": CAMPAIGN,
            "start_iso": "2026-09-25T14:00:00-05:00"}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not None}


def send(store, appointment, inst, ghl, now=NOW, contact_id=CONTACT):
    return tr.send_lead_email(store, appointment, SUBJECT, BODY, now, instantly=inst, ghl=ghl,
                              contact_id=contact_id)


# ------------------------------------------------------------ find_thread routes
def test_find_thread_route_campaign_id_and_email(store):
    key = put_lead(store)
    put_lead(store, campaign_id=OTHER_CAMPAIGN)  # another campaign's row is never looked at on this route
    got = tr.find_thread(store, appt())
    assert got["route"] == tr.ROUTE_CAMPAIGN and got["key"] == key and got["reason"] is None
    assert got["state"].last_email_id == EMAIL_ID and got["state"].eaccount == EACCOUNT


def test_find_thread_route_campaign_matches_the_email_case_insensitively(store):
    key = put_lead(store)
    got = tr.find_thread(store, appt(email=LEAD.upper()))
    assert got["route"] == tr.ROUTE_CAMPAIGN and got["key"] == key


def test_find_thread_route_appointment_row(store):
    """A GHL calendar event carries neither campaign nor (sometimes) email: the
    appointment:<id> row booking.register_booking wrote has both."""
    key = put_lead(store)
    put_lead(store, campaign_id=OTHER_CAMPAIGN)
    store.set("appointment:%s" % APPT_ID, {"lead_email": LEAD, "campaign_id": CAMPAIGN})
    got = tr.find_thread(store, appt(email=None, campaign_id=None))
    assert got["route"] == tr.ROUTE_APPOINTMENT and got["key"] == key


def test_find_thread_route_appointment_row_fills_only_the_campaign(store):
    key = put_lead(store)
    store.set("appointment:%s" % APPT_ID, {"lead_email": "someone-else@example.com", "campaign_id": CAMPAIGN})
    got = tr.find_thread(store, appt(campaign_id=None))
    # the appointment's own email wins, as no_show._lead_identity
    assert got["route"] == tr.ROUTE_APPOINTMENT and got["key"] == key


def test_find_thread_route_scan_for_a_widget_booking(store):
    key = put_lead(store)
    got = tr.find_thread(store, appt(campaign_id=None))
    assert got["route"] == tr.ROUTE_SCAN and got["key"] == key and got["candidates"] == [key]


def test_find_thread_scan_when_the_campaign_row_is_missing(store):
    key = put_lead(store, campaign_id=OTHER_CAMPAIGN)
    got = tr.find_thread(store, appt())
    assert got["route"] == tr.ROUTE_SCAN and got["key"] == key


def test_find_thread_ambiguous_when_two_rows_carry_a_thread(store):
    a = put_lead(store)
    b = put_lead(store, campaign_id=OTHER_CAMPAIGN, last_email_id="other-email", thread_id="thread-2")
    got = tr.find_thread(store, appt(campaign_id=None))
    assert got["state"] is None and got["reason"] == tr.AMBIGUOUS_THREAD
    assert sorted(got["candidates"]) == sorted([a, b])


def test_find_thread_several_rows_only_one_with_a_thread_is_that_one(store):
    key = put_lead(store)
    put_lead(store, campaign_id=OTHER_CAMPAIGN, eaccount=None, thread_id=None, last_email_id=None)
    got = tr.find_thread(store, appt(campaign_id=None))
    assert got["key"] == key and got["reason"] is None


def test_find_thread_none(store):
    assert tr.find_thread(store, appt(campaign_id=None))["reason"] == tr.NO_LEAD_ROW
    assert tr.find_thread(store, appt(email=None, campaign_id=None))["reason"] == tr.NO_LEAD_EMAIL


# ------------------------------------------------------------ thread reply, shadow
def test_shadow_thread_reply_makes_no_request_and_records_the_reply(store, shadow_mode):
    put_lead(store)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert irec.requests == [] and grec.requests == []
    assert res["transport"] == tr.TRANSPORT_THREAD and res["shadow"] is True
    assert res["sent"] is False and res["skipped"] is False and res["reason"] is None
    payload = res["result"]["payload"]
    assert res["result"]["action"] == "reply_to_email"
    assert payload["to"] == LEAD and payload["reply_to_uuid"] == EMAIL_ID and payload["eaccount"] == EACCOUNT
    assert payload["subject"] == "Re: Sopio, question"  # cadence.subject_for: one "Re:", the thread's subject
    assert payload["body"]["text"] == BODY


@pytest.mark.parametrize("route", [tr.ROUTE_CAMPAIGN, tr.ROUTE_APPOINTMENT, tr.ROUTE_SCAN])
def test_shadow_zero_http_on_every_route(store, shadow_mode, route):
    """Each case resolves through its own route (asserted), and none of them
    makes a request."""
    if route == tr.ROUTE_CAMPAIGN:
        put_lead(store)
        a = appt()
    elif route == tr.ROUTE_APPOINTMENT:
        put_lead(store)
        put_lead(store, campaign_id=OTHER_CAMPAIGN, last_email_id="other-email")  # a scan would be ambiguous
        store.set("appointment:%s" % APPT_ID, {"lead_email": LEAD, "campaign_id": CAMPAIGN})
        a = appt(email=None, campaign_id=None)
    else:
        put_lead(store, campaign_id=OTHER_CAMPAIGN)  # no appointment row, no campaign on the appointment
        a = appt(campaign_id=None)
    inst, irec, ghl, grec = clients()
    res = send(store, a, inst, ghl)
    assert res["route"] == route
    assert res["shadow"] is True and res["transport"] == tr.TRANSPORT_THREAD
    assert res["result"]["payload"]["to"] == LEAD
    assert irec.requests == [] and grec.requests == []


def test_shadow_ghl_fallback_makes_no_request(store, shadow_mode):
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert irec.requests == [] and grec.requests == []
    assert res["transport"] == tr.TRANSPORT_GHL and res["shadow"] is True and res["sent"] is False
    assert res["result"]["action"] == "send_message"
    payload = res["result"]["payload"]
    assert payload["contactId"] == CONTACT and payload["type"] == "Email"
    assert payload["subject"] == SUBJECT and payload["message"] == BODY


# ------------------------------------------------------------ thread reply, live
def test_live_true_verdict_rereads_then_replies_in_thread_to_the_lead(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients(sender=LEAD)
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["sent"] is True and res["skipped"] is False
    assert res["result"] == {"id": "sent-1"}
    assert irec.methods() == ["GET", "POST"] and grec.requests == []
    assert str(irec.requests[0].url).endswith("/emails/%s" % EMAIL_ID)
    url, body = irec.posts()[0]
    assert url.endswith("/emails/reply")
    assert body["to"] == LEAD and body["reply_to_uuid"] == EMAIL_ID and body["eaccount"] == EACCOUNT
    assert body["subject"] == "Re: Sopio, question" and body["body"]["text"] == BODY


def test_live_false_verdict_holds_recipient_mismatch_and_never_falls_back_to_ghl(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients(sender="assistant@taxfoaccounting.com")
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["skipped"] is True and res["sent"] is False
    assert res["reason"] == tr.RECIPIENT_MISMATCH
    assert irec.methods() == ["GET"] and grec.requests == []


@pytest.mark.parametrize("sender,get_status", [(None, 200), (LEAD, 500)])
def test_live_none_verdict_holds_recipient_unverified_and_never_falls_back_to_ghl(store, live_mode, tmp_env,
                                                                                  sender, get_status):
    """No readable sender, or a re-read that fails: cannot tell, so hold."""
    put_lead(store)
    inst, irec, ghl, grec = clients(sender=sender, get_status=get_status)
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["skipped"] is True
    assert res["reason"] == tr.RECIPIENT_UNVERIFIED
    assert "POST" not in irec.methods() and grec.requests == []


def test_live_verdict_that_raises_holds_unverified(store, live_mode, tmp_env, monkeypatch):
    put_lead(store)
    inst, irec, ghl, grec = clients()

    def boom(state, instantly):
        raise RuntimeError("re-read crashed")

    monkeypatch.setattr(tr.cadence, "thread_recipient_ok", boom)
    res = send(store, appt(), inst, ghl)
    assert res["reason"] == tr.RECIPIENT_UNVERIFIED and irec.requests == [] and grec.requests == []


def test_to_is_the_address_that_wrote_the_thread(store, live_mode, tmp_env):
    """cadence.recipient_for: the thread's own sender (cadence reply_from), not
    the CRM key, and the re-read compares against that same address."""
    put_lead(store, cadence={"reply_from": "sopio@taxfo.co"})
    inst, irec, ghl, grec = clients(sender="sopio@taxfo.co")
    res = send(store, appt(), inst, ghl)
    assert res["sent"] is True
    assert irec.posts()[0][1]["to"] == "sopio@taxfo.co"


def test_to_is_never_the_sending_inbox_or_missing(store, live_mode, tmp_env):
    for campaign in (CAMPAIGN, OTHER_CAMPAIGN):
        put_lead(store, campaign_id=campaign, last_email_id="e-%s" % campaign[-1])
    for campaign in (CAMPAIGN, OTHER_CAMPAIGN):
        inst, irec, ghl, grec = clients()
        send(store, appt(campaign_id=campaign), inst, ghl)
        posts = irec.posts()
        assert len(posts) == 1
        assert posts[0][1]["to"] == LEAD and posts[0][1]["to"] != EACCOUNT


# ------------------------------------------------------------ ambiguous / broken thread
def test_ambiguous_thread_holds_and_sends_nothing(store, live_mode, tmp_env):
    a = put_lead(store)
    b = put_lead(store, campaign_id=OTHER_CAMPAIGN, last_email_id="other-email")
    inst, irec, ghl, grec = clients()
    res = send(store, appt(campaign_id=None), inst, ghl)
    assert res["transport"] is None and res["skipped"] is True and res["reason"] == tr.AMBIGUOUS_THREAD
    assert res["needs_attention"] is True and sorted(res["result"]["candidates"]) == sorted([a, b])
    assert irec.requests == [] and grec.requests == []


def test_half_a_thread_holds_missing_thread_ids_without_ghl(store, live_mode, tmp_env):
    put_lead(store, eaccount=None)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["reason"] == tr.MISSING_THREAD_IDS
    assert irec.requests == [] and grec.requests == []


@pytest.mark.parametrize("broken_method", ["get", "keys"])
def test_unreadable_store_holds_without_ghl(store, live_mode, tmp_env, monkeypatch, broken_method):
    put_lead(store)
    inst, irec, ghl, grec = clients()

    def broken(*a, **k):
        raise OSError("store down")

    monkeypatch.setattr(store, broken_method, broken)
    res = send(store, appt(), inst, ghl)
    assert res["reason"] == tr.LEAD_ROW_UNREADABLE and res["skipped"] is True
    assert res["retryable"] is True and res["needs_attention"] is True and res["maybe_sent"] is False
    assert irec.requests == [] and grec.requests == []


def test_shadow_without_an_instantly_client_records_the_would_do_reply(store, shadow_mode):
    """As cadence._send: in shadow the record is the deliverable, with no
    client and no request."""
    put_lead(store)
    inst, irec, ghl, grec = clients()
    res = tr.send_lead_email(store, appt(), SUBJECT, BODY, NOW, instantly=None, ghl=ghl, contact_id=CONTACT)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["shadow"] is True and res["reason"] is None
    assert res["sent"] is False and res["skipped"] is False and res["retryable"] is False
    assert res["result"]["shadow"] is True and res["result"]["action"] == "reply_to_email"
    assert res["result"]["skipped"] == tr.NO_INSTANTLY_CLIENT
    payload = res["result"]["payload"]
    assert payload["to"] == LEAD and payload["reply_to_uuid"] == EMAIL_ID and payload["eaccount"] == EACCOUNT
    assert payload["subject"] == "Re: Sopio, question" and payload["body"]["text"] == BODY
    assert grec.requests == []


def test_live_without_an_instantly_client_holds_and_never_falls_back_to_ghl(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients()
    res = tr.send_lead_email(store, appt(), SUBJECT, BODY, NOW, instantly=None, ghl=ghl, contact_id=CONTACT)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["reason"] == tr.NO_INSTANTLY_CLIENT
    assert res["skipped"] is True and res["retryable"] is True
    assert grec.requests == []


# ------------------------------------------------------------ no thread -> GHL
def test_no_lead_row_falls_back_to_ghl_email_live(store, live_mode, tmp_env):
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_GHL and res["sent"] is True
    assert irec.requests == [] and grec.methods() == ["POST"]
    url, body = grec.posts()[0]
    assert url.endswith("/conversations/messages")
    assert body["contactId"] == CONTACT and body["type"] == "Email"
    assert body["subject"] == SUBJECT and body["message"] == BODY and body["html"].startswith("<p>")


def test_lead_row_without_any_thread_ids_falls_back_to_ghl(store, live_mode, tmp_env):
    put_lead(store, eaccount=None, thread_id=None, last_email_id=None)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_GHL and res["sent"] is True
    assert irec.requests == [] and grec.methods() == ["POST"]


def test_several_rows_none_with_a_thread_falls_back_to_ghl(store, live_mode, tmp_env):
    put_lead(store, eaccount=None, thread_id=None, last_email_id=None)
    put_lead(store, campaign_id=OTHER_CAMPAIGN, eaccount=None, thread_id=None, last_email_id=None)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(campaign_id=None), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_GHL and res["sent"] is True and irec.requests == []


def test_ghl_fallback_needs_a_contact_id(store, live_mode, tmp_env):
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl, contact_id=None)
    assert res["transport"] == tr.TRANSPORT_GHL and res["reason"] == tr.NO_CONTACT_ID
    assert grec.requests == []


# ------------------------------------------------------------ send window
@pytest.mark.parametrize("when", [
    "2026-09-24T19:30:00-05:00",  # Thursday evening
    "2026-09-24T06:30:00-05:00",  # Thursday before 07:00
    "2026-09-26T10:00:00-05:00",  # Saturday
])
@pytest.mark.parametrize("with_thread", [True, False])
def test_outside_send_window_refuses_before_anything(store, live_mode, tmp_env, when, with_thread):
    if with_thread:
        put_lead(store)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl, now=datetime.fromisoformat(when))
    assert res["reason"] == tr.OUTSIDE_SEND_WINDOW and res["skipped"] is True and res["sent"] is False
    assert res["transport"] is None
    assert irec.requests == [] and grec.requests == []


# ------------------------------------------------------------ subject
def test_thread_subject_skips_an_auto_reply_subject(store, shadow_mode):
    put_lead(store, last_subject="Automatic reply: Sopio, question")
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["result"]["payload"]["subject"] == "Re: Sopio, question"
    assert irec.requests == []


# ------------------------------------------------------------ the row must be the lead's (defect 1)
VICTIM = "victim@other.com"


@pytest.mark.parametrize("route_appt,appointment_row", [
    (appt(), None),                                                          # campaign
    (appt(email=None, campaign_id=None), {"lead_email": LEAD, "campaign_id": CAMPAIGN}),  # appointment
    (appt(campaign_id=None), None),                                          # scan
])
def test_row_under_the_leads_key_naming_somebody_else_holds_in_live(store, live_mode, tmp_env, route_appt,
                                                                    appointment_row):
    """A mis-keyed row (key: the lead, content: somebody else with their own
    thread) used to pass both belts: to= and the re-read both came from the
    row. Now it holds before any request, and never goes to GHL."""
    store.set("lead:%s:%s" % (CAMPAIGN, LEAD), lead_row(email=VICTIM, last_email_id="victim-email"))
    if appointment_row:
        store.set("appointment:%s" % APPT_ID, appointment_row)
    inst, irec, ghl, grec = clients(sender=VICTIM)
    res = send(store, route_appt, inst, ghl)
    assert res["reason"] == tr.LEAD_ROW_MISMATCH and res["skipped"] is True and res["sent"] is False
    assert res["transport"] is None and res["request_issued"] is False
    assert res["needs_attention"] is True and res["result"] == {"candidates": ["lead:%s:%s" % (CAMPAIGN, LEAD)]}
    assert irec.requests == [] and grec.requests == []


def test_find_thread_reports_the_mismatched_key(store):
    key = "lead:%s:%s" % (CAMPAIGN, LEAD)
    store.set(key, lead_row(email=VICTIM))
    got = tr.find_thread(store, appt())
    assert got["state"] is None and got["reason"] == tr.LEAD_ROW_MISMATCH and got["candidates"] == [key]


def test_scan_matches_on_the_rows_own_lead_email_not_the_keys_last_segment(store, live_mode, tmp_env):
    """lead:C:bob:<lead> ends in the lead's address but is bob's row: it is
    not the lead's thread, and nothing is sent to bob."""
    other = "bob:" + LEAD
    store.set("lead:%s:%s" % (CAMPAIGN, other), lead_row(email=other, last_email_id="bob-email"))
    got = tr.find_thread(store, appt(campaign_id=None))
    assert got["state"] is None and got["reason"] == tr.NO_LEAD_ROW
    inst, irec, ghl, grec = clients(sender=other)
    res = send(store, appt(campaign_id=None), inst, ghl)
    assert irec.requests == []  # never a GET or POST on bob's thread
    assert res["transport"] == tr.TRANSPORT_GHL and res["reason"] == tr.NO_LEAD_ROW


def test_key_email_keeps_everything_after_the_campaign():
    assert tr._key_email("lead:%s:bob:%s" % (CAMPAIGN, LEAD)) == "bob:" + LEAD
    assert tr._key_email("lead:%s:%s" % (CAMPAIGN, LEAD.upper())) == LEAD


# ------------------------------------------------------------ retry safety (defect 2)
def test_exported_reason_tuples_are_disjoint_and_complete():
    assert not set(tr.RETRYABLE_REASONS) & set(tr.MAYBE_SENT_REASONS)
    assert set(tr.NEEDS_ATTENTION_REASONS) <= set(tr.RETRYABLE_REASONS)
    assert set(tr.MAYBE_SENT_REASONS) == {tr.SEND_FAILED, tr.NO_RESPONSE}
    assert not set(tr.GHL_FALLBACK_REASONS) & set(tr.NEEDS_ATTENTION_REASONS)
    for reason in (tr.OUTSIDE_SEND_WINDOW, tr.RECIPIENT_UNVERIFIED, tr.INSTANTLY_KEY_MISSING,
                   tr.GHL_TOKEN_MISSING, tr.CONNECT_FAILED, tr.NO_CONTACT_ID):
        assert reason in tr.RETRYABLE_REASONS and reason not in tr.NEEDS_ATTENTION_REASONS
    for reason in (tr.LEAD_ROW_UNREADABLE, tr.NO_LEAD_EMAIL, tr.AMBIGUOUS_THREAD, tr.LEAD_ROW_MISMATCH):
        assert reason in tr.NEEDS_ATTENTION_REASONS


@pytest.mark.parametrize("status", [503, 429, 422, 500])
def test_thread_post_that_fails_after_going_out_is_maybe_sent_never_retryable(store, live_mode, tmp_env, status):
    put_lead(store)
    inst, irec, ghl, grec = clients(inst_post={"post_status": status})
    res = send(store, appt(), inst, ghl)
    assert irec.methods() == ["GET", "POST"]  # one POST: shared/instantly.py never retries a write
    assert res["reason"] == tr.SEND_FAILED and res["reason"] in tr.MAYBE_SENT_REASONS
    assert res["sent"] is False and res["skipped"] is False
    assert res["request_issued"] is True and res["maybe_sent"] is True and res["retryable"] is False
    assert grec.requests == []


def test_server_error_quoting_the_key_missing_phrase_is_still_maybe_sent(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients(inst_post={"post_status": 500, "post_error": "so no write can be sent"})
    res = send(store, appt(), inst, ghl)
    assert irec.methods() == ["GET", "POST"]
    assert res["reason"] == tr.SEND_FAILED and res["maybe_sent"] is True and res["retryable"] is False


def test_thread_post_timeout_is_maybe_sent(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients(inst_post={"post_raises": httpx.ReadTimeout})
    res = send(store, appt(), inst, ghl)
    assert irec.methods() == ["GET", "POST"]
    assert res["reason"] == tr.SEND_FAILED and res["maybe_sent"] is True and res["retryable"] is False


def test_thread_post_that_never_connected_is_retryable(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients(inst_post={"post_raises": httpx.ConnectError})
    res = send(store, appt(), inst, ghl)
    assert res["reason"] == tr.CONNECT_FAILED and res["skipped"] is True
    assert res["request_issued"] is False and res["maybe_sent"] is False and res["retryable"] is True


def test_thread_post_with_an_empty_2xx_is_no_response_maybe_sent(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients(inst_post={"post_content": b"null"})
    res = send(store, appt(), inst, ghl)
    assert irec.methods() == ["GET", "POST"]
    assert res["reason"] == tr.NO_RESPONSE and res["sent"] is False and res["skipped"] is False
    assert res["maybe_sent"] is True and res["retryable"] is False


def test_missing_instantly_write_key_is_retryable_and_not_maybe_sent(store, live_mode, tmp_env):
    """shared/instantly.py raises before the request when there is no write
    key: nothing left the process."""
    put_lead(store)
    inst, irec, ghl, grec = clients()
    inst._write_key = None
    res = send(store, appt(), inst, ghl)
    assert irec.methods() == ["GET"]  # the re-read only; no POST was made
    assert res["reason"] == tr.INSTANTLY_KEY_MISSING and res["skipped"] is True
    assert res["retryable"] is True and res["maybe_sent"] is False and res["request_issued"] is False
    assert grec.requests == []


def test_missing_ghl_write_token_is_retryable_and_not_maybe_sent(store, live_mode, tmp_env):
    inst, irec, ghl, grec = clients()
    ghl.write_token = None
    res = send(store, appt(), inst, ghl)
    assert grec.requests == []
    assert res["transport"] == tr.TRANSPORT_GHL and res["reason"] == tr.GHL_TOKEN_MISSING
    assert res["retryable"] is True and res["maybe_sent"] is False


@pytest.mark.parametrize("ghl_post,reason", [
    ({"post_status": 503}, tr.SEND_FAILED),
    ({"post_raises": httpx.ReadTimeout}, tr.SEND_FAILED),
    ({"post_content": b"null"}, tr.NO_RESPONSE),
])
def test_ghl_fallback_failure_after_the_request_is_maybe_sent(store, live_mode, tmp_env, ghl_post, reason):
    """A GHL write that returns None can only be a 2xx with a null body: it
    was received, so it is no_response (maybe sent), not ghl_token_missing."""
    inst, irec, ghl, grec = clients(ghl_post=ghl_post)
    res = send(store, appt(), inst, ghl)
    assert grec.methods() == ["POST"]
    assert res["transport"] == tr.TRANSPORT_GHL and res["reason"] == reason
    assert res["maybe_sent"] is True and res["retryable"] is False and res["sent"] is False


def test_outside_window_is_retryable(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl, now=datetime.fromisoformat("2026-09-24T20:00:00-05:00"))
    assert res["reason"] == tr.OUTSIDE_SEND_WINDOW
    assert res["retryable"] is True and res["request_issued"] is False and res["maybe_sent"] is False


def test_a_live_send_is_neither_retryable_nor_maybe_sent(store, live_mode, tmp_env):
    put_lead(store)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["sent"] is True and res["request_issued"] is True
    assert res["maybe_sent"] is False and res["retryable"] is False


def test_ghl_html_matches_show_rate(store):
    from services.reply_engine import show_rate

    text = "Hi <Sopio> & co,\n\nline one\nline two"
    assert tr._text_to_html(text) == show_rate._text_to_html(text)


# ------------------------------------------------------------ thread-less campaign row (defect 3)
def test_threadless_campaign_row_scans_for_the_thread_in_another_campaign(store, live_mode, tmp_env):
    put_lead(store, eaccount=None, thread_id=None, last_email_id=None)
    other = put_lead(store, campaign_id=OTHER_CAMPAIGN, last_email_id="other-email")
    got = tr.find_thread(store, appt())
    assert got["route"] == tr.ROUTE_SCAN and got["key"] == other
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_THREAD and res["sent"] is True and grec.requests == []
    assert irec.posts()[0][1]["reply_to_uuid"] == "other-email" and irec.posts()[0][1]["to"] == LEAD


def test_threadless_campaign_row_with_two_threads_elsewhere_is_ambiguous(store):
    put_lead(store, eaccount=None, thread_id=None, last_email_id=None)
    put_lead(store, campaign_id=OTHER_CAMPAIGN, last_email_id="other-email")
    put_lead(store, campaign_id="c0ffee00-0000-7000-8000-00000000000c", last_email_id="third-email")
    got = tr.find_thread(store, appt())
    assert got["state"] is None and got["reason"] == tr.AMBIGUOUS_THREAD


# ------------------------------------------------------------ unknown lead: no usable email holds
@pytest.mark.parametrize("appointment", [None, {"id": "WIDGET1"}])
def test_no_lead_email_and_no_contact_holds_without_ghl(store, live_mode, tmp_env, appointment):
    inst, irec, ghl, grec = clients()
    res = send(store, appointment, inst, ghl, contact_id=None)
    assert res["reason"] == tr.NO_LEAD_EMAIL and res["skipped"] is True and res["transport"] is None
    assert irec.requests == [] and grec.requests == []


def test_no_email_holds_even_when_a_row_claims_the_contact_id(store, live_mode, tmp_env):
    """The lead is never found by GHL contact id: a row's contact id cannot
    prove whose thread it is. No email: hold, no request, no GHL."""
    put_lead(store, ghl_contact_id=CONTACT)
    inst, irec, ghl, grec = clients()
    res = send(store, {"id": "WIDGET1", "contact_id": CONTACT}, inst, ghl)
    assert res["reason"] == tr.NO_LEAD_EMAIL and res["skipped"] is True and res["transport"] is None
    assert res["needs_attention"] is True and res["retryable"] is True
    assert irec.requests == [] and grec.requests == []


@pytest.mark.parametrize("junk", ["N/A", "lead", "unknown"])
def test_appointment_email_without_an_at_sign_is_no_email(store, live_mode, tmp_env, junk):
    put_lead(store)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(email=junk), inst, ghl)
    assert res["reason"] == tr.NO_LEAD_EMAIL and res["transport"] is None
    assert irec.requests == [] and grec.requests == []


@pytest.mark.parametrize("setup,reason", [
    ("none", tr.NO_LEAD_ROW),
    ("threadless", tr.NO_THREAD_IDS),
])
def test_ghl_fallback_record_carries_why_the_thread_was_not_used(store, live_mode, tmp_env, setup, reason):
    if setup == "threadless":
        put_lead(store, eaccount=None, thread_id=None, last_email_id=None)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["transport"] == tr.TRANSPORT_GHL and res["sent"] is True and res["reason"] == reason


# ------------------------------------------------------------ unreadable rows (defect 5)
@pytest.mark.parametrize("value", ["garbage", {}, [1, 2]])
@pytest.mark.parametrize("route_appt", [appt(), appt(campaign_id=None)])
def test_unreadable_row_under_the_leads_key_holds_without_ghl(store, live_mode, tmp_env, value, route_appt):
    store.set("lead:%s:%s" % (CAMPAIGN, LEAD), value)
    inst, irec, ghl, grec = clients()
    res = send(store, route_appt, inst, ghl)
    assert res["reason"] == tr.LEAD_ROW_UNREADABLE and res["skipped"] is True and res["retryable"] is True
    assert irec.requests == [] and grec.requests == []


def test_unreadable_row_of_another_lead_is_ignored(store, shadow_mode):
    key = put_lead(store)
    store.set("lead:%s:someone-else@example.com" % OTHER_CAMPAIGN, "garbage")
    got = tr.find_thread(store, appt(campaign_id=None))
    assert got["key"] == key and got["reason"] is None


def test_row_that_fails_to_parse_holds(store, live_mode, tmp_env):
    put_lead(store)
    key = "lead:%s:%s" % (CAMPAIGN, LEAD)
    bad = dict(store.get(key), drafts="not-a-list")
    store.set(key, bad)
    inst, irec, ghl, grec = clients()
    res = send(store, appt(), inst, ghl)
    assert res["reason"] == tr.LEAD_ROW_UNREADABLE and irec.requests == [] and grec.requests == []


# ------------------------------------------------------------ case variants in one campaign (defect 7)
def test_case_variant_keys_in_one_campaign_both_threaded_are_ambiguous(store):
    put_lead(store)
    store.set("lead:%s:%s" % (CAMPAIGN, LEAD.upper()), lead_row(last_email_id="upper-email"))
    got = tr.find_thread(store, appt())
    assert got["state"] is None and got["reason"] == tr.AMBIGUOUS_THREAD


def test_case_variant_keys_in_one_campaign_one_threaded_is_that_one(store):
    put_lead(store, eaccount=None, thread_id=None, last_email_id=None)
    upper = "lead:%s:%s" % (CAMPAIGN, LEAD.upper())
    store.set(upper, lead_row(last_email_id="upper-email"))
    got = tr.find_thread(store, appt())
    assert got["key"] == upper and got["route"] == tr.ROUTE_CAMPAIGN


# ------------------------------------------------------------ live end to end through the scan (defect 8)
def test_live_end_to_end_through_the_scan_route(store, live_mode, tmp_env):
    """Widget booking: no campaign on the appointment, no appointment row; the
    thread is found by the scan, re-read, and replied to the lead."""
    key = put_lead(store, campaign_id=OTHER_CAMPAIGN)
    inst, irec, ghl, grec = clients(sender=LEAD)
    res = send(store, appt(campaign_id=None), inst, ghl)
    assert res["route"] == tr.ROUTE_SCAN and res["lead_key"] == key
    assert res["transport"] == tr.TRANSPORT_THREAD and res["sent"] is True
    assert irec.methods() == ["GET", "POST"] and grec.requests == []
    url, body = irec.posts()[0]
    assert url.endswith("/emails/reply") and body["to"] == LEAD and body["reply_to_uuid"] == EMAIL_ID
