"""shared.ghl.upsert_contact with no email (Upwork clients), and the proof that
every existing caller (email given) sends exactly what it sent before.

Live is simulated by patching ``settings.is_live``; the real MODE /
ALLOW_LIVE_WRITES flags are never set. Every request goes to a MockTransport.
"""
import csv
import json

import httpx
import pytest

from shared import ghl as ghl_mod
from shared import job_log, settings
from shared.ghl import GHL, GHLContactNeedsIdentity, GHLError

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


def make(responses=None, **kw):
    rec = Recorder(responses)
    if not kw:
        kw = {"token": "tok"}
    return GHL(transport=httpx.MockTransport(rec), **kw), rec


@pytest.fixture
def fake_live(monkeypatch):
    monkeypatch.setattr(settings, "is_live", lambda: True)


@pytest.fixture
def verified(monkeypatch):
    monkeypatch.setattr(ghl_mod, "CONTACT_WITHOUT_EMAIL_VERIFIED", True)


def job_rows():
    try:
        with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except (IOError, OSError):
        return []


def test_verified_flag_ships_false():
    assert ghl_mod.CONTACT_WITHOUT_EMAIL_VERIFIED is False
    assert ghl_mod.CONTACT_NEEDS_IDENTITY == "ghl_contact_needs_identity"
    assert issubclass(GHLContactNeedsIdentity, GHLError)


def test_needs_identity_status_is_a_literal_the_watch_report_scan_can_see():
    """changesets/tests/test_deploy_watch_report.py collects Job_Log statuses
    from string literals in _log(...) calls only; a constant name hides the
    status from its every-status-is-classified check."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ghl_mod))
    literals = [node.args[1].value for node in ast.walk(tree)
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_log" and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)]
    assert ghl_mod.CONTACT_NEEDS_IDENTITY in literals


# ------------------------------------------------------ existing callers
LEGACY_CALLS = [
    (("a@b.co",), {}),
    (("a@b.co",), {"first_name": "A"}),
    (("a@b.co",), {"first_name": "Tamsin", "last_name": "Quell", "company": "Quell Kilns",
                   "phone": "555-010-0199", "tags": ["cold-email", "instantly-positive-reply"],
                   "custom_fields": [{"id": "f1", "value": "lead-1"}]}),
    (("a@b.co", "Tamsin", None, "Quell Kilns", None, ["x"]), {}),
    # booking.book's shape when state.lead_email is empty (email None), with and
    # without a first name, and with a phone
    ((None,), {"first_name": None, "company": "Quell Kilns", "tags": ["cold-email", "instantly-positive-reply"]}),
    ((None,), {"first_name": "Tamsin", "company": "Quell Kilns", "tags": ["cold-email"]}),
    ((None,), {}),
    ((None,), {"phone": "555-010-0199"}),
    (("",), {"first_name": "Tamsin", "tags": ["cold-email"]}),
]


def legacy_body(args, kwargs):
    """The body exactly as upsert_contact built it before the optional email."""
    names = ("email", "first_name", "last_name", "company", "phone", "tags", "custom_fields")
    a = dict(zip(names, args))
    a.update(kwargs)
    body = {"locationId": LOCATION, "email": a["email"]}
    for key, field in (("first_name", "firstName"), ("last_name", "lastName"), ("company", "companyName"),
                       ("phone", "phone")):
        if a.get(key):
            body[field] = a[key]
    if a.get("tags"):
        body["tags"] = list(a["tags"])
    if a.get("custom_fields"):
        body["customFields"] = a["custom_fields"]
    return body


@pytest.mark.parametrize("args,kwargs", LEGACY_CALLS)
def test_existing_callers_send_byte_identical_bodies_live(tmp_env, fake_live, verified, args, kwargs):
    """With the refusal out of the way (flag True) every legacy shape, email
    None included, POSTs exactly HEAD's body."""
    client, rec = make(responses=[(200, {"contact": {"id": "c1"}})])
    assert client.upsert_contact(*args, **kwargs) == {"contact": {"id": "c1"}}
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/contacts/upsert")
    expected = legacy_body(args, kwargs)
    assert req.content == httpx.Request("POST", "https://x", json=expected).content
    assert list(json.loads(req.content.decode("utf-8"))) == list(expected)
    assert "name" not in json.loads(req.content.decode("utf-8"))
    assert "source" not in json.loads(req.content.decode("utf-8"))


@pytest.mark.parametrize("args,kwargs", LEGACY_CALLS)
def test_existing_callers_shadow_payload_unchanged(tmp_env, shadow_mode, args, kwargs):
    client, rec = make()
    res = client.upsert_contact(*args, **kwargs)
    assert rec.requests == []
    assert res["shadow"] is True and res["payload"] == legacy_body(args, kwargs)
    assert list(res["payload"]) == list(legacy_body(args, kwargs))


def test_booking_shape_with_no_email_is_refused_live_while_unverified(tmp_env, fake_live):
    """booking.book passes lead_email straight through; an empty one reaches
    upsert_contact as None. Live, with no phone, that is refused (a GHLError,
    the same class a GHL rejection of "email": null raises) before any request.
    Documented in upsert_contact's docstring and the CONTACT_WITHOUT_EMAIL_VERIFIED comment."""
    client, rec = make()
    with pytest.raises(GHLError) as exc:
        client.upsert_contact(None, first_name=None, company="Quell Kilns",
                              tags=["cold-email", "instantly-positive-reply"])
    assert isinstance(exc.value, GHLContactNeedsIdentity)
    assert rec.requests == []
    assert [(r["job"], r["status"]) for r in job_rows()] == [("ghl.upsert_contact", "ghl_contact_needs_identity")]


def test_booking_book_with_an_empty_lead_email_still_records_in_shadow(tmp_env, shadow_mode):
    """The U4a review's A4 probe: HEAD recorded a shadow row here; a
    ValueError would make the poller retry forever."""
    from shared import slots as slot_rules
    from services.reply_engine import booking
    from services.reply_engine.cadence import LeadState

    def refuse(request):
        raise AssertionError("HTTP in shadow: %s %s" % (request.method, request.url))

    state = LeadState(lead_email="", campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d",
                      status="positive_question", first_name=None, company="Quell Kilns",
                      eaccount="sender@example.com", last_email_id="01a0c50b-6021-793c-a3b9-81506c6a291b",
                      last_subject="Re: question")
    ghl = GHL(token=None, transport=httpx.MockTransport(refuse))
    res = booking.book(state, "2026-09-25T13:00:00-05:00", ghl, None,
                       now=slot_rules.parse_iso("2026-09-21T21:10:00-05:00"),
                       free_slots=["2026-09-25T13:00:00-05:00"])
    assert res.shadow is True
    contact_rows = [r for r in job_log.read_shadow_log() if r["action"] == "upsert_contact"]
    assert contact_rows and contact_rows[0]["payload"]["email"] is None


# --------------------------------------------- differential: every shape
DIFF_VALUES = {
    "email": ["a@b.co", "", None],
    "first_name": [None, "", "A"],
    "last_name": [None, "B"],
    "company": [None, "Co"],
    "phone": [None, "", "555"],
    "tags": [None, [], ["t"]],
    "custom_fields": [None, [], [{"id": "f", "value": "v"}]],
}
DIFF_ORDER = ["email", "first_name", "last_name", "company", "phone", "tags", "custom_fields"]


def test_every_legacy_call_shape_matches_head(tmp_env, monkeypatch):
    """All 972 legacy argument combinations (email None included), positional
    and by keyword, in shadow and in (simulated) live: the shadow payload and
    the request bytes are HEAD's, and nothing raises ValueError. The only live
    difference is the documented refusal (email None, no phone, flag False)."""
    import itertools

    live = {"on": False}
    monkeypatch.setattr(settings, "is_live", lambda: live["on"])
    sent = []

    def handler(request):
        sent.append(request.content)
        return httpx.Response(200, json={"contact": {"id": "c1"}})

    client = GHL(token="tok", transport=httpx.MockTransport(handler))
    checked = refused = 0
    for is_live in (False, True):
        live["on"] = is_live
        for positional in (True, False):
            for vals in itertools.product(*[DIFF_VALUES[k] for k in DIFF_ORDER]):
                combo = dict(zip(DIFF_ORDER, vals))
                expected = legacy_body((), combo)
                n = len(sent)
                call = (lambda: client.upsert_contact(*vals)) if positional else (
                    lambda: client.upsert_contact(vals[0], **dict(zip(DIFF_ORDER[1:], vals[1:]))))
                if is_live and combo["email"] is None and not combo["phone"]:
                    with pytest.raises(GHLContactNeedsIdentity):
                        call()
                    assert len(sent) == n
                    refused += 1
                    continue
                res = call()
                if is_live:
                    assert res == {"contact": {"id": "c1"}}
                    assert sent[-1] == httpx.Request("POST", "https://x", json=expected).content, combo
                    assert len(sent) == n + 1
                else:
                    assert res["shadow"] is True and len(sent) == n
                    assert res["payload"] == expected and list(res["payload"]) == list(expected), combo
                checked += 1
    assert checked + refused == 972 * 4
    # email None x phone None or "" x 108 other combinations x 2 call styles
    assert refused == 1 * 2 * 108 * 2


# ------------------------------------------------------------- no email
def test_no_email_shadow_records_the_would_do_without_an_email_key(tmp_env, shadow_mode):
    client, rec = make()
    res = client.upsert_contact(None, name="Northwind Kiln Studio", tags=["upwork"], source="Upwork")
    assert rec.requests == []
    assert res["shadow"] is True and res["action"] == "upsert_contact"
    assert res["payload"] == {"locationId": LOCATION, "name": "Northwind Kiln Studio", "tags": ["upwork"],
                              "source": "Upwork"}
    row = job_log.read_shadow_log()[-1]
    assert row["action"] == "upsert_contact" and "email" not in row["payload"]


def test_no_email_accepts_first_last_name_and_default_email_argument(tmp_env, shadow_mode):
    client, _ = make()
    res = client.upsert_contact(first_name="Ottilie", last_name="Brand", source="Upwork")
    assert res["payload"] == {"locationId": LOCATION, "firstName": "Ottilie", "lastName": "Brand", "source": "Upwork"}


@pytest.mark.parametrize("kwargs", [
    {"tags": ["upwork"], "source": "Upwork"},     # no name
    {"name": "Northwind Kiln Studio"},              # no source, no tags
])
def test_no_email_needs_a_name_and_a_source_or_tags(tmp_env, shadow_mode, kwargs):
    client, rec = make()
    with pytest.raises(ValueError):
        client.upsert_contact(None, **kwargs)
    assert rec.requests == []
    assert job_log.read_shadow_log() == []


def test_no_email_no_phone_is_refused_live_while_unverified(tmp_env, fake_live, caplog):
    client, rec = make()
    with caplog.at_level("ERROR"):
        with pytest.raises(GHLContactNeedsIdentity) as exc:
            client.upsert_contact(None, name="Northwind Kiln Studio", tags=["upwork"], source="Upwork")
    assert "ghl_contact_needs_identity" in str(exc.value)
    assert rec.requests == []
    rows = job_rows()
    assert [(r["job"], r["status"]) for r in rows] == [("ghl.upsert_contact", "ghl_contact_needs_identity")]
    assert "live_write_intent" not in [r["status"] for r in rows]
    assert "ghl_contact_needs_identity" in caplog.text


def test_no_email_with_a_phone_is_not_refused_live(tmp_env, fake_live):
    client, rec = make(responses=[(200, {"contact": {"id": "c7"}})])
    client.upsert_contact(None, name="Northwind Kiln Studio", phone="555-010-0142", source="Upwork")
    body = json.loads(rec.requests[0].content.decode("utf-8"))
    assert body == {"locationId": LOCATION, "name": "Northwind Kiln Studio", "phone": "555-010-0142",
                    "source": "Upwork"}


def test_no_email_goes_live_once_verified(tmp_env, fake_live, monkeypatch):
    monkeypatch.setattr(ghl_mod, "CONTACT_WITHOUT_EMAIL_VERIFIED", True)
    client, rec = make(responses=[(200, {"contact": {"id": "c8"}})])
    out = client.upsert_contact(None, name="Northwind Kiln Studio", tags=["upwork"], source="Upwork")
    assert out == {"contact": {"id": "c8"}}
    body = json.loads(rec.requests[0].content.decode("utf-8"))
    assert body == {"locationId": LOCATION, "name": "Northwind Kiln Studio", "tags": ["upwork"], "source": "Upwork"}
    assert [r["status"] for r in job_rows()] == ["live_write_intent", "live_write_ok"]


def test_email_with_source_adds_only_the_source(tmp_env, shadow_mode):
    client, _ = make()
    res = client.upsert_contact("a@b.co", tags=["x"], source="Upwork")
    assert res["payload"] == {"locationId": LOCATION, "email": "a@b.co", "tags": ["x"], "source": "Upwork"}


# ------------------------------------------------------ get_opportunity
def test_get_opportunity_uses_the_read_token(tmp_env):
    stage = settings.GHL_STAGES["call_booked"]
    client, rec = make(responses=[(200, {"opportunity": {"id": "o1", "pipelineStageId": stage}})],
                       read_token="rtok", write_token="wtok")
    out = client.get_opportunity("o1")
    assert out["opportunity"]["pipelineStageId"] == stage
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("GET", "/opportunities/o1")
    assert req.headers["Authorization"] == "Bearer rtok"
