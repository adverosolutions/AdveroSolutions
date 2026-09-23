"""Zoom webhook: URL-validation challenge, signature check, event normalisation."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.store import JsonFileStore

from services.reply_engine import zoom_webhook as zw

SECRET = "zoom-test-secret"
NOW = datetime(2026, 9, 24, 20, 3, 0, tzinfo=timezone.utc)  # 15:03 CT
MEETING = "000000000002"


def join_body(name="Sopio S", email="sopiosvanishvili@taxfoaccounting.com", join_time="2026-09-24T20:03:00Z",
              participant_user_id="U9", host_id="HOST1", puuid="p1", meeting=MEETING):
    return {
        "event": "meeting.participant_joined",
        "event_ts": int(NOW.timestamp() * 1000),
        "payload": {"account_id": "acc", "object": {
            "id": meeting, "uuid": "uu==", "host_id": host_id, "topic": "Discovery Call - Sopio Svanishvili",
            "participant": {"user_id": "16778240", "user_name": name, "email": email, "join_time": join_time,
                            "participant_user_id": participant_user_id, "participant_uuid": puuid},
        }},
    }


@pytest.fixture
def client(tmp_env, monkeypatch):
    monkeypatch.setenv(zw.SECRET_ENV, SECRET)
    store = JsonFileStore(tmp_env / "s.json")
    app = FastAPI()
    app.include_router(zw.router)
    app.state.store = store
    zw.set_clock(lambda: NOW)
    yield TestClient(app), store
    zw.set_clock(None)


def signed(body_dict, secret=SECRET, ts=None):
    raw = json.dumps(body_dict).encode("utf-8")
    ts = str(ts if ts is not None else int(NOW.timestamp()))
    return raw, {"x-zm-request-timestamp": ts, "x-zm-signature": zw.expected_signature(secret, ts, raw), "content-type": "application/json"}


# ------------------------------------------------------------ challenge
def test_url_validation_challenge(client):
    c, _ = client
    r = c.post("/webhooks/zoom", json={"event": "endpoint.url_validation", "payload": {"plainToken": "qgg8vlvZRS6UYooatFL8Aw"}})
    assert r.status_code == 200
    expected = hmac.new(SECRET.encode(), b"qgg8vlvZRS6UYooatFL8Aw", hashlib.sha256).hexdigest()
    assert r.json() == {"plainToken": "qgg8vlvZRS6UYooatFL8Aw", "encryptedToken": expected}


def test_missing_secret_returns_503(tmp_env, monkeypatch):
    monkeypatch.delenv(zw.SECRET_ENV, raising=False)
    app = FastAPI()
    app.include_router(zw.router)
    app.state.store = JsonFileStore(tmp_env / "s.json")
    r = TestClient(app).post("/webhooks/zoom", json={"event": "endpoint.url_validation", "payload": {"plainToken": "x"}})
    assert r.status_code == 503 and r.json()["error"] == "zoom_secret_missing"


# ------------------------------------------------------------ signature
def test_valid_signature_stores_join(client):
    c, store = client
    raw, headers = signed(join_body())
    r = c.post("/webhooks/zoom", content=raw, headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    joins = store.get("joins:%s" % MEETING)
    assert len(joins) == 1
    j = joins[0]
    assert j["is_host"] is False and j["name"] == "Sopio S" and j["at_iso"] == "2026-09-24T15:03:00-05:00"
    assert j["email"] == "sopiosvanishvili@taxfoaccounting.com" and j["participant_id"] == "p1"


def test_bad_signature_rejected(client):
    c, store = client
    raw, headers = signed(join_body())
    headers["x-zm-signature"] = "v0=" + "0" * 64
    r = c.post("/webhooks/zoom", content=raw, headers=headers)
    assert r.status_code == 401 and store.get("joins:%s" % MEETING) is None


def test_wrong_secret_rejected(client):
    c, store = client
    raw, headers = signed(join_body(), secret="other")
    assert c.post("/webhooks/zoom", content=raw, headers=headers).status_code == 401


def test_stale_timestamp_rejected(client):
    c, store = client
    raw, headers = signed(join_body(), ts=int((NOW - timedelta(minutes=6)).timestamp()))
    assert c.post("/webhooks/zoom", content=raw, headers=headers).status_code == 401
    raw, headers = signed(join_body(), ts=int((NOW - timedelta(minutes=4)).timestamp()))
    assert c.post("/webhooks/zoom", content=raw, headers=headers).status_code == 200


def test_missing_headers_rejected(client):
    c, _ = client
    raw, _ = signed(join_body())
    assert c.post("/webhooks/zoom", content=raw, headers={"content-type": "application/json"}).status_code == 401


def test_invalid_json_400(client):
    c, _ = client
    assert c.post("/webhooks/zoom", content=b"{not json", headers={"content-type": "application/json"}).status_code == 400


# ------------------------------------------------------------ normalisation
def test_host_detection_and_dedupe(client):
    c, store = client
    raw, headers = signed(join_body(name="Lorenzo Villarreal", email="lorenzovillarreal@adverosolutions.com", participant_user_id="HOST1", puuid="h1"))
    assert c.post("/webhooks/zoom", content=raw, headers=headers).status_code == 200
    raw, headers = signed(join_body())
    c.post("/webhooks/zoom", content=raw, headers=headers)
    r = c.post("/webhooks/zoom", content=raw, headers=headers)  # Zoom retries the same event
    assert r.json()["result"]["stored"] is False
    joins = store.get("joins:%s" % MEETING)
    assert [(j["name"], j["is_host"]) for j in joins] == [("Lorenzo Villarreal", True), ("Sopio S", False)]


def test_meeting_ended_stored(client):
    c, store = client
    body = {"event": "meeting.ended", "payload": {"object": {"id": MEETING, "end_time": "2026-09-24T20:16:00Z", "duration": 13}}}
    raw, headers = signed(body)
    assert c.post("/webhooks/zoom", content=raw, headers=headers).status_code == 200
    assert store.get("meeting_ended:%s" % MEETING) == {"at_iso": "2026-09-24T15:16:00-05:00", "duration": 13, "meeting_id": MEETING}


def test_unknown_event_ignored_and_missing_meeting_id_tolerated(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    assert zw.handle_event({"event": "meeting.sharing_started", "payload": {"object": {"id": MEETING}}}, store, NOW)["reason"] == "ignored_event"
    assert zw.handle_event({"event": "meeting.participant_joined", "payload": {}}, store, NOW)["reason"] == "no_meeting_id"
    assert store.keys() == []


def test_meeting_to_appointment_mapping_via_booking_record(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    # booking.py (another brief) stores appt:<appointment_id> -> {zoom_meeting_id,...}; absence is tolerated
    res = zw.handle_event(join_body(), store, NOW)
    assert res["appointment_id"] is None and res["stored"] is True
    store.set("appt:gcal_j8n9", {"zoom_meeting_id": MEETING, "contact_id": "iDhesF6A9rhdDajGZuYw"})
    res = zw.handle_event(join_body(puuid="p2", join_time="2026-09-24T20:04:00Z"), store, NOW)
    assert res["appointment_id"] == "gcal_j8n9"
    assert store.get("zoom_meeting:%s" % MEETING) == {"appointment_id": "gcal_j8n9"}
    assert len(store.get("joins_by_appt:gcal_j8n9")) == 1
    # the tick's lookup sees both joins (by appointment and by meeting id)
    joins = zw.joins_for_appointment(store, {"id": "gcal_j8n9", "zoom_link": "https://zoom.us/j/%s" % MEETING})
    assert len(joins) == 2
    assert zw.meeting_id_from_link("https://us02web.zoom.us/j/84512345678?pwd=abc") == "84512345678"
    assert zw.meeting_id_from_link("https://meet.google.com/abc-defg-hij") is None


# ------------------------------------------------------------ timestamp units
def test_millisecond_request_timestamp_is_accepted(client):
    """Zoom's x-zm-request-timestamp is a millisecond epoch. Treating it as
    seconds rejected every genuine webhook with 401, so no join was ever
    stored and detect() then saw no telemetry at all."""
    c, store = client
    ms = str(int(NOW.timestamp() * 1000))
    raw, headers = signed(join_body(), ts=ms)
    r = c.post("/webhooks/zoom", content=raw, headers=headers)
    assert r.status_code == 200 and len(store.get("joins:%s" % MEETING)) == 1
    assert zw.normalise_timestamp(ms) == int(NOW.timestamp())
    assert zw.normalise_timestamp(str(int(NOW.timestamp()))) == int(NOW.timestamp())
    # the HMAC message keeps the raw header, not the normalised value
    assert zw.expected_signature(SECRET, ms, raw) == headers["x-zm-signature"]


def test_stale_millisecond_timestamp_is_still_rejected(client):
    c, store = client
    ms = str(int((NOW - timedelta(minutes=6)).timestamp() * 1000))
    raw, headers = signed(join_body(), ts=ms)
    assert c.post("/webhooks/zoom", content=raw, headers=headers).status_code == 401


# ------------------------------------------------------------ signing oracle
def test_url_validation_refuses_to_sign_a_signature_message(client):
    """challenge_response answers before signature verification. Signing a
    caller-chosen "v0:<ts>:<body>" string would hand anyone who knows the URL
    a valid x-zm-signature for a forged event."""
    c, store = client
    forged = {"event": "meeting.participant_joined", "payload": {"object": {"id": MEETING}}}
    ts = str(int(NOW.timestamp()))
    message = "v0:%s:%s" % (ts, json.dumps(forged))
    r = c.post("/webhooks/zoom", json={"event": "endpoint.url_validation", "payload": {"plainToken": message}})
    assert r.status_code == 400 and r.json()["error"] == "invalid_plain_token"
    assert not zw.safe_plain_token(message)
    assert not zw.safe_plain_token("v0:123:{}") and not zw.safe_plain_token("a" * 65)
    assert zw.safe_plain_token("qgg8vlvZRS6UYooatFL8Aw")
    # and a genuine challenge still works
    assert c.post("/webhooks/zoom", json={"event": "endpoint.url_validation",
                                          "payload": {"plainToken": "qgg8vlvZRS6UYooatFL8Aw"}}).status_code == 200


def test_url_validation_can_be_switched_off(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv(zw.URL_VALIDATION_ENV, "off")
    r = c.post("/webhooks/zoom", json={"event": "endpoint.url_validation", "payload": {"plainToken": "abc"}})
    assert r.status_code == 403


# ------------------------------------------------------------ join windows
def test_joins_for_appointment_only_returns_joins_from_that_call(tmp_env):
    """One Zoom link (a Personal Meeting ID) serves every booking, so the join
    list must be filtered to the appointment's own window."""
    store = JsonFileStore(tmp_env / "s.json")
    appt = {"id": "a1", "start_iso": "2026-09-24T15:00:00-05:00", "end_iso": "2026-09-24T15:15:00-05:00",
            "zoom_link": "https://zoom.us/j/%s" % MEETING}
    store.set("joins:%s" % MEETING, [
        {"at_iso": "2026-09-21T15:02:00-05:00", "name": "Earlier Lead"},      # three days before
        {"at_iso": "2026-09-24T15:03:00-05:00", "name": "Sopio S"},           # this call
        {"at_iso": "2026-10-01T15:01:00-05:00", "name": "Next Week"},         # a week later
    ])
    names = [j["name"] for j in zw.joins_for_appointment(store, appt)]
    assert names == ["Sopio S"]
    # joins_by_appt accumulates across reschedules of the same id: same rule
    store.set("joins_by_appt:a1", [{"at_iso": "2026-09-17T15:03:00-05:00", "name": "Old Instance"}])
    assert [j["name"] for j in zw.joins_for_appointment(store, appt)] == ["Sopio S"]


def test_meeting_signals_report_whether_zoom_said_anything(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    appt = {"id": "a1", "start_iso": "2026-09-24T15:00:00-05:00", "zoom_link": "https://zoom.us/j/%s" % MEETING}
    assert zw.meeting_signals(store, appt) == {"meeting_id": MEETING, "started": None, "ended": None}
    store.set("meeting_ended:%s" % MEETING, {"at_iso": "2026-09-24T15:16:00-05:00"})
    assert zw.meeting_signals(store, appt)["ended"]
    meet = {"id": "a2", "start_iso": "2026-09-24T15:00:00-05:00", "zoom_link": "https://meet.google.com/abc-defg-hij"}
    assert zw.meeting_signals(store, meet)["meeting_id"] is None


def test_meeting_signals_ignore_a_meeting_that_ended_outside_this_appointments_window(tmp_env):
    """The Discovery Call link is one reusable Personal Meeting ID.

    Last week's meeting_ended record sits under the same key. Reported as
    telemetry for this week's call it turns "the Zoom webhook told us nothing"
    into "Zoom says the meeting ran and nobody joined", which is a no_show
    verdict and the whole recovery ladder fired at a prospect who may well
    have attended.
    """
    store = JsonFileStore(tmp_env / "s.json")
    appt = {"id": "a1", "start_iso": "2026-09-24T15:00:00-05:00", "end_iso": "2026-09-24T15:15:00-05:00",
            "zoom_link": "https://zoom.us/j/%s" % MEETING}
    store.set("meeting_ended:%s" % MEETING, {"at_iso": "2026-09-17T15:16:00-05:00"})   # last week
    store.set("meeting_started:%s" % MEETING, {"at_iso": "2026-09-17T15:00:00-05:00"})
    sig = zw.meeting_signals(store, appt)
    assert sig["meeting_id"] == MEETING and sig["started"] is None and sig["ended"] is None
    # this week's records are reported
    store.set("meeting_ended:%s" % MEETING, {"at_iso": "2026-09-24T15:16:00-05:00"})
    assert zw.meeting_signals(store, appt)["ended"]
    # a record with no timestamp cannot be attributed to any one call
    store.set("meeting_ended:%s" % MEETING, {"duration": 15})
    assert zw.meeting_signals(store, appt)["ended"] is None


def test_a_retried_join_delivery_is_stored_once(client):
    """Zoom retries deliveries and two containers can handle the same event.

    The old read/compare/append was the get-then-set race shared/store.py
    documents by name; add_once does the whole decision under one lock.
    """
    c, store = client
    raw, headers = signed(join_body())
    first = c.post("/webhooks/zoom", content=raw, headers=headers)
    second = c.post("/webhooks/zoom", content=raw, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["result"]["stored"] is True
    assert second.json()["result"]["stored"] is False
    assert len(store.get("joins:%s" % MEETING)) == 1
