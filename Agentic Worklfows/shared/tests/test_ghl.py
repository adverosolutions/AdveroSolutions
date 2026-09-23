import json

import httpx
import pytest

from shared import job_log, settings
from shared.ghl import GHL, GHLError

LOCATION = "ebyNANPagaK7ycf1pfge"


class Recorder(object):
    def __init__(self, responses=None):
        self.requests = []
        self.responses = list(responses or [])

    def __call__(self, request):
        self.requests.append(request)
        if self.responses:
            status, body = self.responses.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"ok": True})


def make(token="tok", responses=None):
    rec = Recorder(responses)
    return GHL(token=token, transport=httpx.MockTransport(rec)), rec


def body_of(request):
    return json.loads(request.content.decode("utf-8"))


# ------------------------------------------------------------ no token
def test_defaults_come_from_ids_json():
    client, _ = make(token=None)
    assert client.token is None
    assert client.location_id == LOCATION
    assert client.pipeline_id == "GCBkIzFpung73cIDVPzn"
    assert client.calendar_id == "GDugwLmZNdsD13RBDnRu"
    assert client.user_id == "gIwBtPohHJXADQBuGAx8"
    assert client.stages["call_booked"] == "f12615dc-66e1-412d-902b-4d1adab812c9"


def test_reads_without_token_return_none_and_log(caplog):
    client, rec = make(token=None)
    with caplog.at_level("WARNING"):
        assert client.get_contact("c1") is None
        assert client.search_contacts("a@b.co") is None
        assert client.search_opportunities(contact_id="c1") is None
        assert client.get_free_slots(None, 1, 2) is None
        assert client.get_appointment("a1") is None
        assert client.get_calendar_events(None, 1, 2) is None
        assert client.search_conversations("c1") is None
    assert rec.requests == []
    assert "ghl_token_missing" in caplog.text


def test_writes_without_token_in_shadow_return_guard_record(tmp_env, shadow_mode):
    client, rec = make(token=None)
    res = client.upsert_contact("a@b.co", first_name="A", company="Acme", tags=["cold-email"])
    assert res["shadow"] is True and res["system"] == "ghl" and res["action"] == "upsert_contact"
    assert res["payload"]["locationId"] == LOCATION
    assert rec.requests == []
    assert job_log.read_shadow_log()[-1]["action"] == "upsert_contact"


def test_writes_without_token_in_live_raise(tmp_env, live_mode, caplog):
    """A dropped write must never be indistinguishable from a successful one:
    ids.json still records the GHL token as 'not yet created', which is exactly
    the state the first live run would be in."""
    client, rec = make(token=None)
    with caplog.at_level("ERROR"):
        with pytest.raises(GHLError) as exc:
            client.add_tags("c1", ["x"])
    assert "ghl_token_missing" in str(exc.value)
    assert rec.requests == []
    assert "ghl_token_missing" in caplog.text


def test_live_write_without_token_is_recorded_in_the_job_log(tmp_env, live_mode):
    """guard_write returns shadow=False in live, so nothing lands in the shadow
    log; the Job_Log is the only place the dropped intent can be reconciled."""
    import csv

    client, rec = make(token=None)
    with pytest.raises(GHLError):
        client.create_appointment(None, "c1", "2026-09-24T14:00:00-05:00", "2026-09-24T14:15:00-05:00",
                                  "Discovery Call", None)
    assert job_log.read_shadow_log() == []
    with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["job"], r["status"]) for r in rows] == [
        ("ghl.create_appointment", "live_write_intent"),
        ("ghl.create_appointment", "skipped_no_token"),
    ]
    assert "2026-09-24T14:00:00-05:00" in rows[0]["details"]


def test_live_write_attempt_and_outcome_are_recorded(tmp_env, live_mode):
    import csv

    client, rec = make(token="tok", responses=[(200, {"id": "appt"}), (500, {"message": "boom"})])
    client.add_tags("c1", ["hot"])
    with pytest.raises(GHLError):
        client.add_tags("c2", ["hot"])
    with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
        statuses = [r["status"] for r in csv.DictReader(fh) if r["job"] == "ghl.add_tags"]
    assert statuses == ["live_write_intent", "live_write_ok", "live_write_intent", "live_write_failed"]


# ---------------------------------------------------------------- reads
def test_get_contact_headers_and_url():
    client, rec = make(responses=[(200, {"contact": {"id": "c1"}})])
    out = client.get_contact("c1")
    assert out == {"contact": {"id": "c1"}}
    req = rec.requests[0]
    assert req.method == "GET"
    assert str(req.url) == "https://services.leadconnectorhq.com/contacts/c1"
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.headers["Version"] == "2021-07-28"


def test_search_contacts_body():
    client, rec = make(responses=[(200, {"contacts": []})])
    client.search_contacts("tiffany@flowerhillfs.com")
    req = rec.requests[0]
    assert req.method == "POST" and req.url.path == "/contacts/search"
    body = body_of(req)
    assert body["locationId"] == LOCATION
    assert body["filters"] == [{"field": "email", "operator": "eq", "value": "tiffany@flowerhillfs.com"}]


def test_search_opportunities_params():
    client, rec = make(responses=[(200, {"opportunities": []})])
    client.search_opportunities(contact_id="c1", pipeline_id="p1", stage_id="s1", limit=5)
    req = rec.requests[0]
    assert req.url.path == "/opportunities/search"
    p = req.url.params
    assert p["location_id"] == LOCATION and p["contact_id"] == "c1"
    assert p["pipeline_id"] == "p1" and p["pipeline_stage_id"] == "s1" and p["limit"] == "5"


def test_free_slots_and_events_and_conversations():
    client, rec = make(responses=[(200, {}), (200, {}), (200, {}), (200, {})])
    client.get_free_slots(None, 1000, 2000)
    client.get_appointment("appt-1")
    client.get_calendar_events(None, 10, 20)
    client.search_conversations("c1")
    r0, r1, r2, r3 = rec.requests
    assert r0.url.path == "/calendars/GDugwLmZNdsD13RBDnRu/free-slots"
    assert r0.url.params["startDate"] == "1000" and r0.url.params["endDate"] == "2000"
    assert r0.url.params["timezone"] == "America/Chicago"
    assert r1.url.path == "/calendars/events/appointments/appt-1"
    assert r2.url.path == "/calendars/events"
    assert r2.url.params["calendarId"] == "GDugwLmZNdsD13RBDnRu" and r2.url.params["locationId"] == LOCATION
    assert r3.url.path == "/conversations/search" and r3.url.params["contactId"] == "c1"


def test_read_http_error_raises():
    client, rec = make(responses=[(401, {"message": "nope"})])
    with pytest.raises(GHLError):
        client.get_contact("c1")


# ------------------------------------------------------- writes: shadow
WRITES = [
    ("upsert_contact", ("a@b.co",), {"first_name": "A"}),
    ("add_tags", ("c1", ["x"]), {}),
    ("create_note", ("c1", "note"), {}),
    ("upsert_opportunity", ("c1", None, "stage", "Acme - A (Cold Email)"), {}),
    ("update_opportunity_stage", ("o1", "stage2"), {"status": "won"}),
    ("create_appointment", (None, "c1", "2026-09-24T14:00:00-05:00", "2026-09-24T14:15:00-05:00", "Discovery Call", None), {}),
    ("update_appointment_status", ("appt-1", "showed"), {}),
    ("send_message", ("c1",), {"type": "Email", "subject": "s", "message": "m"}),
    ("create_task", ("c1", "Ask for intro", "2026-09-23T15:00:00Z"), {}),
]


@pytest.mark.parametrize("name,args,kwargs", WRITES)
def test_writes_make_no_request_in_shadow(tmp_env, shadow_mode, name, args, kwargs):
    client, rec = make(token="tok")
    res = getattr(client, name)(*args, **kwargs)
    assert rec.requests == [], "%s must not hit GHL in shadow" % name
    assert res["shadow"] is True and res["system"] == "ghl" and res["action"] == name
    assert job_log.read_shadow_log()[-1]["action"] == name


# --------------------------------------------------------- writes: live
def test_upsert_contact_live(tmp_env, live_mode):
    client, rec = make(responses=[(200, {"contact": {"id": "new"}})])
    out = client.upsert_contact("a@b.co", first_name="Tiffany", last_name="Spelman", company="FlowerHill",
                                phone="817-422-4740", tags=["cold-email", "instantly-positive-reply"],
                                custom_fields=[{"id": "f1", "value": "lead-1"}])
    assert out == {"contact": {"id": "new"}}
    req = rec.requests[0]
    assert req.method == "POST" and req.url.path == "/contacts/upsert"
    assert body_of(req) == {
        "locationId": LOCATION, "email": "a@b.co", "firstName": "Tiffany", "lastName": "Spelman",
        "companyName": "FlowerHill", "phone": "817-422-4740",
        "tags": ["cold-email", "instantly-positive-reply"], "customFields": [{"id": "f1", "value": "lead-1"}],
    }
    assert job_log.read_shadow_log() == []


def test_opportunity_writes_live(tmp_env, live_mode):
    client, rec = make(responses=[(200, {}), (200, {})])
    client.upsert_opportunity("c1", None, settings.GHL_STAGES["new_reply"], "Acme - A (Cold Email)", monetary_value=1000)
    client.update_opportunity_stage("o1", settings.GHL_STAGES["call_booked"], status="open")
    r0, r1 = rec.requests
    assert (r0.method, r0.url.path) == ("POST", "/opportunities/upsert")
    b0 = body_of(r0)
    assert b0["pipelineId"] == "GCBkIzFpung73cIDVPzn" and b0["locationId"] == LOCATION
    assert b0["pipelineStageId"] == settings.GHL_STAGES["new_reply"] and b0["monetaryValue"] == 1000 and b0["status"] == "open"
    assert (r1.method, r1.url.path) == ("PUT", "/opportunities/o1")
    assert body_of(r1) == {"pipelineStageId": settings.GHL_STAGES["call_booked"], "status": "open"}


def test_appointment_writes_live(tmp_env, live_mode):
    client, rec = make(responses=[(200, {"id": "appt"}), (200, {})])
    client.create_appointment(None, "c1", "2026-09-24T14:00:00-05:00", "2026-09-24T14:15:00-05:00",
                              "Lorenzo <> Acme: 15-min reactivation plan", None)
    client.update_appointment_status("appt", "no-show")
    r0, r1 = rec.requests
    assert (r0.method, r0.url.path) == ("POST", "/calendars/events/appointments")
    b0 = body_of(r0)
    assert b0["calendarId"] == "GDugwLmZNdsD13RBDnRu" and b0["assignedUserId"] == "gIwBtPohHJXADQBuGAx8"
    assert b0["startTime"] == "2026-09-24T14:00:00-05:00" and b0["appointmentStatus"] == "confirmed"
    assert (r1.method, r1.url.path) == ("PUT", "/calendars/events/appointments/appt")
    assert body_of(r1) == {"appointmentStatus": "no-show"}


def test_tags_notes_messages_tasks_live(tmp_env, live_mode):
    client, rec = make(responses=[(200, {}), (200, {}), (200, {}), (200, {})])
    client.add_tags("c1", ["hot"])
    client.create_note("c1", "Replied: what is your percentage?")
    client.send_message("c1", type="SMS", message="See you at 2")
    client.create_task("c1", "Ask for intro", "2026-09-23T15:00:00Z", body="referral")
    r0, r1, r2, r3 = rec.requests
    assert (r0.method, r0.url.path) == ("POST", "/contacts/c1/tags") and body_of(r0) == {"tags": ["hot"]}
    assert (r1.method, r1.url.path) == ("POST", "/contacts/c1/notes") and body_of(r1)["body"].startswith("Replied")
    assert (r2.method, r2.url.path) == ("POST", "/conversations/messages")
    assert body_of(r2) == {"type": "SMS", "contactId": "c1", "message": "See you at 2"}
    assert (r3.method, r3.url.path) == ("POST", "/contacts/c1/tasks")
    assert body_of(r3)["title"] == "Ask for intro" and body_of(r3)["dueDate"] == "2026-09-23T15:00:00Z"
