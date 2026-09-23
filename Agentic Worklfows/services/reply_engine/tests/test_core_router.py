"""Routing produces would_do records in shadow with zero HTTP requests; live mode parses ids."""
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytz

from shared import job_log, settings
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import classify as C
from services.reply_engine.models import Classification, Extracted, LeadState, ReplyEvent
from services.reply_engine.router import route, tags_for

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
STAGES = settings.GHL_STAGES


class Failing(object):
    def __call__(self, request):
        raise AssertionError("HTTP request attempted in shadow: %s %s" % (request.method, request.url))


def failing_clients():
    t = httpx.MockTransport(Failing())
    return GHL(token=None, transport=t), Instantly(api_key="x", transport=t)


def ev(email, ts_prefix="", **over):
    for r in REPLIES:
        if r["from_address_email"] == email and r["timestamp_created"].startswith(ts_prefix):
            return ReplyEvent.from_poller_item(dict(r, **over))
    raise KeyError(email)


def run(event, cls=None, store=None, ghl=None, instantly=None):
    if ghl is None or instantly is None:
        g, i = failing_clients()
        ghl, instantly = ghl or g, instantly or i
    cls = cls or C.classify(event)
    state = LeadState.from_store(None, event)
    actions = route(event, cls, state, ghl, instantly, now=event.received_at, store=store)
    return cls, state, actions


def by_action(actions):
    return {"%s.%s" % (a.system, a.action): a for a in actions}


def test_positive_routes_to_new_reply_with_would_do_records(tmp_env):
    cls, state, actions = run(ev("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42"))
    acts = by_action(actions)
    assert set(acts) == {"ghl.upsert_contact", "ghl.upsert_opportunity", "ghl.create_note", "instantly.update_interest_status"}
    assert all(a.kind == "would_do" for a in actions)
    assert all(a.result["shadow"] is True for a in actions)
    assert acts["ghl.upsert_contact"].payload["tags"] == ["cold-email", "bookkeeping", "bookkeeping_reactivation", "instantly-positive-reply"]
    assert acts["ghl.upsert_opportunity"].payload["stage"] == "new_reply"
    assert acts["ghl.upsert_opportunity"].result["payload"]["pipelineStageId"] == STAGES["new_reply"]
    assert acts["ghl.upsert_opportunity"].result["payload"]["name"] == "Taxfoaccounting - Sopio (Cold Email)"
    assert acts["instantly.update_interest_status"].payload["interest_value"] == 1
    assert state.status == "positive_awaiting_draft"
    log = job_log.read_shadow_log()
    assert [r["action"] for r in log] == ["upsert_contact", "upsert_opportunity", "create_note", "update_interest_status"]
    assert all(r["mode"] == "shadow" for r in log)


def test_hostile_blocklists_and_marks_lost_with_dnd(tmp_env):
    cls, state, actions = run(ev("maggie@northwestsnowremoval.com"))
    acts = by_action(actions)
    assert cls.label == "negative_hostile"
    assert "instantly.blocklist_create" in acts and acts["instantly.blocklist_create"].kind == "would_do"
    assert acts["instantly.blocklist_create"].result["payload"]["bl_value"] == "maggie@northwestsnowremoval.com"
    assert "dnd" in acts["ghl.upsert_contact"].payload["tags"]
    assert acts["ghl.upsert_opportunity"].payload == dict(acts["ghl.upsert_opportunity"].payload, stage="lost", status="lost")
    assert acts["instantly.update_interest_status"].payload["interest_value"] == -1
    assert state.status == "blocklisted" and state.cadence["stopped"] is True


def test_unsubscribe_same_as_hostile_for_writes(tmp_env):
    for email in ("buck@cgavery.com", "loniskey@wowwindowcleaners.com", "lewis@freightappointments.com"):
        cls, state, actions = run(ev(email))
        acts = by_action(actions)
        assert cls.label == "unsubscribe"
        assert "instantly.blocklist_create" in acts
        assert acts["ghl.upsert_opportunity"].result["payload"]["pipelineStageId"] == STAGES["lost"]


def test_notnow_goes_to_follow_up_later_with_dated_task(tmp_env):
    cls, state, actions = run(ev("ignacio@ariacleaningservices.com"))
    acts = by_action(actions)
    assert cls.label == "negative_notnow"
    assert acts["ghl.upsert_opportunity"].result["payload"]["pipelineStageId"] == STAGES["follow_up_later"]
    assert acts["ghl.create_task"].payload["due"] == "2026-10-16T10:00:00-05:00"
    assert state.cadence["follow_up_at"] == "2026-10-16" and state.status == "follow_up_later"
    assert acts["instantly.update_interest_status"].payload["interest_value"] == -1


def test_notfit_is_lost_with_reason(tmp_env):
    cls, state, actions = run(ev("gary.kaufman@excellisearch.com"))
    acts = by_action(actions)
    assert cls.label == "negative_notfit"
    assert acts["ghl.upsert_opportunity"].payload["status"] == "lost"
    assert "Lost reason: not a fit" in acts["ghl.create_note"].result["payload"]["body"]
    assert "instantly.blocklist_create" not in acts
    assert state.status == "lost"


def test_ooo_only_touches_instantly_and_pauses_cadence(tmp_env):
    cls, state, actions = run(ev("jkohl@kohlbm.com"))
    assert cls.label == "ooo"
    assert [(a.system, a.action) for a in actions] == [("instantly", "update_interest_status")]
    assert actions[0].payload["interest_value"] == 0
    assert state.cadence == {"paused": True, "resume_at": "2026-09-22", "reason": "ooo"}


def test_auto_reply_records_for_monitor_and_writes_nothing(tmp_env, tmp_path):
    store = JsonFileStore(tmp_path / "s.json")
    cls, state, actions = run(ev("eva@rbgjanitorial.com"), store=store)
    assert cls.label == "auto_reply_unmonitored"
    # store-only: no GHL, no Instantly, no HTTP. The second row is the hand-off
    # Eva's auto-reply names ("you can reach current RBG management by ...").
    assert [(a.system, a.action, a.kind) for a in actions] == [
        ("store", "record_auto_responder", "done"), ("store", "queue_list_factory", "done")]
    assert store.get("auto_responders")[0]["email"] == "eva@rbgjanitorial.com"
    assert job_log.read_shadow_log() == []


def test_an_auto_responder_that_names_a_new_contact_keeps_the_handover(tmp_env, tmp_path):
    """The record kept only {at, campaign_id, email, subject}, so the one place
    the new contact ever existed - the reply body - was thrown away: no
    list-factory row, nothing for the deliverability monitor to recover, and
    offers.md rule 7 (queue a named new contact) silently unmet."""
    store = JsonFileStore(tmp_path / "s.json")
    cls, state, actions = run(ev("dayers@atwork.com"), store=store)
    assert cls.label == "auto_reply_unmonitored"
    record = store.get("auto_responders")[0]
    assert "dayers@ayerspartners.com" in record["body"]
    assert {"name": "Daryl Ayers", "email": "dayers@ayerspartners.com", "same_domain": False} in record["handover_contacts"]
    queued = store.get("list_factory_queue")
    assert "dayers@ayerspartners.com" in [q["named_email"] for q in queued]
    assert all(q["source"] == "auto_responder_handover" for q in queued)
    # the hand-off is queued, never emailed from this thread
    assert job_log.read_shadow_log() == []


def test_an_auto_responder_with_no_handover_queues_nothing(tmp_env, tmp_path):
    store = JsonFileStore(tmp_path / "s.json")
    e = ev("eva@rbgjanitorial.com")
    e.text = "Thank you for your email. This mailbox is no longer monitored."
    cls, state, actions = run(e, store=store)
    assert cls.label == "auto_reply_unmonitored"
    assert [a.action for a in actions] == ["record_auto_responder"]
    assert store.get("list_factory_queue") is None


def test_referral_creates_intro_task(tmp_env):
    e = ev("rob@cjsglobal.com", "2026-09-15T22:58")
    cls = Classification(label="positive_referral", extracted=Extracted(referral_name="Dustin"))
    _, state, actions = run(e, cls=cls)
    acts = by_action(actions)
    assert acts["ghl.create_task"].payload["title"] == "Ask for intro to Dustin"
    assert acts["ghl.create_task"].payload["due"] == "2026-09-16T10:00:00-05:00"
    assert acts["ghl.upsert_opportunity"].payload["stage"] == "new_reply"


def test_wrong_person_queues_list_factory(tmp_env, tmp_path):
    store = JsonFileStore(tmp_path / "s.json")
    e = ev("rob@cjsglobal.com", "2026-09-15T22:58")
    cls = Classification(label="wrong_person", extracted=Extracted(referral_name="Gary"))
    _, state, actions = run(e, cls=cls, store=store)
    acts = by_action(actions)
    assert acts["instantly.update_interest_status"].payload["interest_value"] == -2
    assert store.get("list_factory_queue")[0]["named_contact"] == "Gary"
    assert "queued for the list factory" in acts["ghl.create_note"].result["payload"]["body"]
    assert "wrong-person" in acts["ghl.upsert_contact"].payload["tags"]


def test_all_44_route_without_any_http(tmp_env):
    for r in REPLIES:
        e = ReplyEvent.from_poller_item(r)
        run(e)
    log = job_log.read_shadow_log()
    assert log and all(rec["mode"] == "shadow" for rec in log)
    assert sum(1 for rec in log if rec["action"] == "blocklist_create") == 6


def test_existing_opportunity_moves_stage_instead_of_upsert(tmp_env):
    e = ev("ignacio@ariacleaningservices.com")
    g, i = failing_clients()
    state = LeadState.from_store(None, e)
    state.ghl_contact_id = "c123"
    state.ghl_opportunity_id = "o456"
    actions = route(e, C.classify(e), state, g, i, now=e.received_at)
    acts = by_action(actions)
    assert "ghl.update_opportunity_stage" in acts and "ghl.upsert_opportunity" not in acts
    assert acts["ghl.update_opportunity_stage"].result["payload"]["opportunity_id"] == "o456"
    assert acts["ghl.create_note"].payload["contact_id"] == "c123"


# ---------------------------------------------------------------- live (mocked)
class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        url = str(request.url)
        if url.endswith("/contacts/search"):
            return httpx.Response(200, json={"contacts": [{"id": "ghl-c-1", "email": "sopiosvanishvili@taxfoaccounting.com"}]})
        if url.endswith("/contacts/upsert"):
            return httpx.Response(200, json={"contact": {"id": "ghl-c-1"}})
        if url.endswith("/opportunities/upsert"):
            return httpx.Response(200, json={"opportunity": {"id": "ghl-o-9"}})
        return httpx.Response(200, json={"ok": True})


def test_live_mode_parses_ids_and_sends_expected_bodies(tmp_env, live_mode):
    rec = Recorder()
    t = httpx.MockTransport(rec)
    ghl = GHL(token="tok", transport=t)
    instantly = Instantly(api_key="x", transport=t)
    e = ev("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    state = LeadState.from_store(None, e)
    actions = route(e, C.classify(e), state, ghl, instantly, now=e.received_at)
    assert all(a.kind == "done" for a in actions)
    assert state.ghl_contact_id == "ghl-c-1" and state.ghl_opportunity_id == "ghl-o-9"
    paths = [(r.method, r.url.path) for r in rec.requests]
    assert paths == [
        ("POST", "/contacts/search"), ("POST", "/contacts/upsert"), ("POST", "/opportunities/upsert"),
        ("POST", "/contacts/ghl-c-1/notes"), ("POST", "/api/v2/leads/update-interest-status"),
    ]
    upsert = json.loads(rec.requests[1].content)
    assert upsert["locationId"] == settings.GHL_LOCATION_ID and "instantly-positive-reply" in upsert["tags"]
    opp = json.loads(rec.requests[2].content)
    assert opp["pipelineStageId"] == STAGES["new_reply"] and opp["contactId"] == "ghl-c-1" and opp["pipelineId"] == settings.GHL_SALES_PIPELINE_ID
    interest = json.loads(rec.requests[4].content)
    assert interest == {"lead_email": "sopiosvanishvili@taxfoaccounting.com", "campaign_id": e.campaign_id, "interest_value": 1}
    assert job_log.read_shadow_log() == []


def test_live_without_ghl_token_records_failed_writes_without_losing_the_reply(tmp_env, live_mode, caplog):
    """shared.ghl raises on a live write with no token; route() must survive it.

    The reply's email id is already claimed by the time route() runs, so an
    exception escaping here would lose the lead's words entirely. Each failed
    CRM write becomes a 'failed' Action and the Instantly side still runs.
    """
    rec = Recorder()
    t = httpx.MockTransport(rec)
    ghl = GHL(token=None, transport=t)
    instantly = Instantly(api_key="x", transport=t)
    e = ev("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    state = LeadState.from_store(None, e)
    with caplog.at_level("WARNING"):
        actions = route(e, C.classify(e), state, ghl, instantly, now=e.received_at)
    acts = by_action(actions)
    assert acts["ghl.upsert_contact"].kind == "failed" and acts["ghl.create_note"].kind == "failed"
    assert "ghl_token_missing" in acts["ghl.upsert_contact"].note
    assert acts["instantly.update_interest_status"].kind == "done"
    assert "ghl_token_missing" in caplog.text
    assert [r.url.path for r in rec.requests] == ["/api/v2/leads/update-interest-status"]


def test_tags_for_labels():
    e = ev("rob@cjsglobal.com", "2026-09-15T22:58")
    assert tags_for(e, Classification(label="positive_question")) == ["cold-email", "cleaning", "cleaning_reactivation", "instantly-positive-reply"]
    assert tags_for(e, Classification(label="unsubscribe")) == ["cold-email", "cleaning", "cleaning_reactivation", "dnd"]
