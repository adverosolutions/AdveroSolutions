"""The one test that says the whole system is safe to leave running.

Lorenzo's rule: in MODE=shadow nothing reaches live Instantly, GHL, Gmail,
Google Calendar, Modal or Skool, and every intended write is recorded as a
would_do entry instead. This module enforces that end to end rather than per
module:

* ``httpx.Client`` and ``httpx.AsyncClient`` are monkeypatched so ANY real
  request raises ``NetworkEscape`` from inside the transport, including one a
  module builds for itself. A test that passes here cannot have talked to
  anything;
* the full 44-reply replay, one cadence tick and one appointments tick all run
  against seeded state;
* every write the run intended is asserted present in the shadow log as a
  would_do record, and every system it touched is asserted to be one of the
  guarded ones;
* no first reply is ever sent without an approval token.

Run it alone with:
    cd "Agentic Worklfows" && python3 -m pytest services/reply_engine/tests/test_shadow_safety.py -q
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytz

from shared import job_log, settings
from shared import slots as slot_rules
from shared.store import JsonFileStore

CT = pytz.timezone("America/Chicago")
NOW = CT.localize(datetime(2026, 9, 21, 22, 0))          # the brief's clock
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPLIES = FIXTURES / "instantly_replies_2026-09.json"

# Every system a guarded write may name. Anything else in the shadow log means
# a new integration was added without a guard.
GUARDED_SYSTEMS = {"instantly", "ghl", "notify", "google_sheets"}

# A first reply to a positive lead is always drafted for approval, never sent.
# These are the only Instantly actions a replay may intend.
REPLAY_ALLOWED_ACTIONS = {
    "update_interest_status", "blocklist_create", "update_lead", "upsert_contact", "add_tags",
    "create_note", "upsert_opportunity", "update_opportunity_stage", "update_opportunity_value",
    "create_task", "create_appointment", "update_appointment_status", "send_message",
    "job_log_append", "push_email",
}


class NetworkEscape(AssertionError):
    """A real HTTP request was attempted during a shadow run."""


@pytest.fixture
def no_network(monkeypatch):
    """Make every httpx client raise instead of reaching the network.

    Patching the transport is not enough: shared.instantly and shared.ghl
    build their own ``httpx.Client``, and so would any module added later. The
    client constructors themselves are wrapped so the escape hatch closes for
    code this test has never seen.
    """
    escapes = []

    def _blocking_handler(request):
        escapes.append("%s %s" % (request.method, request.url))
        raise NetworkEscape("shadow run attempted %s %s" % (request.method, request.url))

    real_client = httpx.Client
    real_async = httpx.AsyncClient

    class GuardedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_blocking_handler)
            super(GuardedClient, self).__init__(*args, **kwargs)

    class GuardedAsyncClient(real_async):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_blocking_handler)
            super(GuardedAsyncClient, self).__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", GuardedClient)
    monkeypatch.setattr(httpx, "AsyncClient", GuardedAsyncClient)
    return escapes


@pytest.fixture
def shadow_world(tmp_path, monkeypatch, no_network):
    """MODE=shadow, faked LLM, notifications off, every file under tmp_path."""
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.setenv("LLM_FAKE", "1")
    monkeypatch.setenv("NOTIFY", "off")
    monkeypatch.delenv("NOTIFY_SHADOW_SEND", raising=False)
    monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN", raising=False)
    monkeypatch.delenv("CADENCE_D6_HOLD", raising=False)
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow_log.jsonl"))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "test-secret")

    from services.reply_engine.classify import install_offline_fakes

    install_offline_fakes()
    assert settings.is_live() is False
    return {"tmp": tmp_path, "store": JsonFileStore(tmp_path / "store.json"), "escapes": no_network}


def _clients():
    """The real client classes. Their transports are the patched httpx ones, so
    a guarded write that leaked would raise NetworkEscape."""
    from shared.ghl import GHL
    from shared.instantly import Instantly

    return Instantly(api_key="shadow-no-key"), GHL()


def _records(path):
    return job_log.read_shadow_log(str(path))


# ------------------------------------------------------------------ replay
@pytest.fixture
def replayed(shadow_world):
    from services.reply_engine import replay as replay_mod

    instantly, ghl = _clients()
    summary = replay_mod.replay(REPLIES, shadow_world["tmp"] / "replay.jsonl",
                                shadow_world["store"], ghl=ghl, instantly=instantly)
    return {"summary": summary, "world": shadow_world}


def test_the_full_replay_runs_with_zero_exceptions_and_zero_http(replayed):
    summary = replayed["summary"]
    assert summary["replies"] == 44
    assert replayed["world"]["escapes"] == []          # nothing left the process
    assert sum(summary["labels"].values()) == 44        # every reply produced a verdict


def test_every_intended_write_in_the_replay_is_a_would_do_record(replayed):
    """The point of shadow: the write is described, not performed."""
    records = _records(replayed["world"]["tmp"] / "shadow_log.jsonl")
    assert records, "a replay that intended writes must leave shadow-log records"
    for rec in records:
        assert rec.get("mode") == "shadow", rec
        assert rec["system"] in GUARDED_SYSTEMS, rec
        assert rec["action"] in REPLAY_ALLOWED_ACTIONS or rec["action"] == "reply_to_email", rec
        assert rec.get("ts_utc")
        assert isinstance(rec.get("payload"), dict)

    # and the counts the replay reported are the records that were written
    intended = sum(replayed["summary"]["would_do"].values())
    logged = len([r for r in records if r["system"] in ("instantly", "ghl")])
    assert logged >= intended > 0


def test_no_first_reply_is_ever_sent_without_an_approval_token(replayed):
    """Blueprint S1 and CLAUDE.md: the first reply to a positive is drafted for
    approval, never auto-sent. In shadow the send would be a would_do record,
    which is exactly how it would slip through unnoticed."""
    world = replayed["world"]
    records = _records(world["tmp"] / "shadow_log.jsonl")
    sends = [r for r in records if r["action"] == "reply_to_email"]
    assert sends == [], "the replay sent a reply: %s" % [s["payload"].get("to") for s in sends]

    # every draft the replay produced is parked behind a token instead
    drafted = [ln for ln in replayed["summary"]["lines"] if ln.get("draft")]
    assert drafted, "the replay produced no drafts at all; the fixture or the router is broken"
    for line in drafted:
        assert line.get("approval_token"), "%s was drafted with no approval token" % line["lead"]
        approval = world["store"].get("approval:%s" % line["approval_token"].split(".")[0])
        # "superseded" is a card a NEWER reply from the same lead retired, and
        # "expired" one that outlived its 48 h TTL. Neither was ever sent, which
        # is the property under test: no status here means "went out".
        assert approval is not None, line["lead"]
        assert approval["status"] in ("pending", "approved_queued", "superseded", "expired"), \
            (line["lead"], approval["status"])

    # and the approval module refuses to send a draft nobody approved
    from services.reply_engine import approval as approval_mod

    pending = [ln for ln in drafted
               if (world["store"].get("approval:%s" % ln["approval_token"].split(".")[0]) or {}).get("status") == "pending"]
    assert pending, "every card was retired; at least one positive must still be waiting on Lorenzo"
    loaded = approval_mod.load(pending[0]["approval_token"], world["store"])
    assert loaded is not None and loaded.status == "pending"


def test_a_booking_in_the_replay_writes_no_calendar_event(replayed):
    """A reply that named a workable time books the call. In shadow the GHL
    appointment must be an intent, and the confirmation must still be a draft."""
    records = _records(replayed["world"]["tmp"] / "shadow_log.jsonl")
    appts = [r for r in records if r["action"] == "create_appointment"]
    for rec in appts:
        assert rec["mode"] == "shadow"
        assert rec["payload"].get("calendarId") == settings.GHL_CALENDAR_ID
    for booking in replayed["summary"].get("booked", []):
        assert booking["shadow"] is True, booking


# ------------------------------------------------------------------- ticks
def _seed_cadence_lead(store, now):
    """One armed lead whose next touch is due, built through the real cadence."""
    from services.reply_engine import cadence

    state = cadence.LeadState(
        lead_email="tiffany@flowerhillfs.com", campaign_id="f347604e-48c7-4813-831c-dc7b9d4b50ae",
        status="positive_question", first_name="Tiffany", company="Flowerhill Facility Services",
        eaccount="lorenzov@theadvero.com", last_email_id="seed-1", last_subject="Re: Tiffany, question")
    cadence.arm(state, now - timedelta(days=1), store=store)
    cad = dict(state.cadence)
    cad["next_send_at"] = (now - timedelta(minutes=5)).isoformat()
    state.cadence = cad
    store.set(state.key if hasattr(state, "key") else "lead:x", cadence.state_to_dict(state))
    return state


def test_one_cadence_tick_makes_no_http_and_records_would_do(shadow_world):
    from jobs import cadence_tick as job

    store = shadow_world["store"]
    state = _seed_cadence_lead(store, NOW)
    instantly, ghl = _clients()
    summary = job.run(NOW, store, instantly, ghl, dry_run=False, notify_fn=lambda *a, **k: None)

    assert shadow_world["escapes"] == []
    assert summary["leads_armed"] >= 1
    assert "error" not in summary["counts"], summary["results"]
    for rec in _records(shadow_world["tmp"] / "shadow_log.jsonl"):
        assert rec["mode"] == "shadow" and rec["system"] in GUARDED_SYSTEMS

    # a touch that went out is a would_do reply, and it names the lead
    sends = [r for r in _records(shadow_world["tmp"] / "shadow_log.jsonl") if r["action"] == "reply_to_email"]
    for send in sends:
        assert send["payload"]["to"] == state.lead_email
        assert send["payload"]["eaccount"] == "lorenzov@theadvero.com"
        assert "Lorenzo" in send["payload"]["body"]["text"]


def test_one_appointments_tick_makes_no_http_and_records_would_do(shadow_world):
    from jobs import appointments_tick as job

    store = shadow_world["store"]
    appointments = json.load(open(str(Path(__file__).resolve().parents[3] / "jobs" / "tests" / "fixtures"
                                   / "appointments_2026-09-21.json"), "r", encoding="utf-8"))
    appointments = appointments.get("appointments", appointments)
    _instantly, ghl = _clients()
    result = job.tick(NOW, store, ghl, appointments)

    assert shadow_world["escapes"] == []
    assert result["show_rate"]["errors"] == 0
    assert result["recovery"]["errors"] == 0
    for rec in _records(shadow_world["tmp"] / "shadow_log.jsonl"):
        assert rec["mode"] == "shadow" and rec["system"] in GUARDED_SYSTEMS
    # the tick scheduled real touches rather than doing nothing at all
    assert result["show_rate"].get("scheduled", 0) + result["pending_touches"] > 0


def test_a_cadence_hold_on_the_calendar_is_never_read_back_as_a_booked_call(shadow_world):
    """cadence writes a day-6 hold titled 'HOLD: ...' with appointmentStatus
    new. If appointments_tick read it as a booking, show_rate would email the
    prospect "Locked in for ..." for a call they never agreed to."""
    from jobs import appointments_tick as job

    hold = {"id": "hold-1", "title": "HOLD: Lorenzo <> Acme: 15-min outbound plan",
            "startTime": (NOW + timedelta(days=1)).isoformat(), "appointmentStatus": "new",
            "contactId": "c1", "contact": {"email": "x@acme.com"}}
    real = {"id": "appt-1", "title": "Lorenzo <> Acme: 15-min outbound plan",
            "startTime": (NOW + timedelta(days=2)).isoformat(), "appointmentStatus": "confirmed",
            "contactId": "c1", "contact": {"email": "x@acme.com"}}
    assert job.normalise_ghl_event(hold) is None
    assert job.normalise_ghl_event(real)["id"] == "appt-1"


# --------------------------------------------------------------- the wiring
def test_the_modal_schedules_resolve_to_real_entrypoints():
    """modal_app looks these up by name; when none exists the scheduled tick
    logs entrypoint_missing and silently does nothing."""
    import importlib

    wanted = [
        ("services.reply_engine.poller", ("run_once", "tick", "poll", "main")),
        ("services.reply_engine.cadence", ("tick", "run_once", "main")),
        ("services.reply_engine.show_rate", ("appointments_tick", "tick", "run_once", "main")),
        ("services.reply_engine.pipeline_sync", ("run_sync",)),
        ("jobs.pipeline_sweep", ("run_sweep",)),
    ]
    for module_name, candidates in wanted:
        module = importlib.import_module(module_name)
        found = [n for n in candidates if callable(getattr(module, n, None))]
        assert found, "%s has none of %s" % (module_name, list(candidates))


def test_a_booking_registers_itself_with_every_job_that_reads_bookings(shadow_world):
    """One booking has to reach four readers, or the pieces stay separate
    systems: the slot registry (so nobody else is offered it), the 07:30 sweep
    (appointment:<id>), the Zoom webhook (appt:<id>) and the show-rate ladder."""
    from services.reply_engine import approval as approval_mod
    from services.reply_engine import booking, cadence, show_rate

    store = shadow_world["store"]
    state = cadence.LeadState(
        lead_email="sopiosvanishvili@taxfoaccounting.com", campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d",
        status="positive_question", first_name="Sopio", company="Taxfo Accounting",
        eaccount="lorenzov@theadvero.com", last_email_id="b-1", last_subject="Re: Sopio, question",
        ghl_contact_id="iDhesF6A9rhdDajGZuYw")
    slot = "2026-09-25T13:00:00-05:00"
    instantly, ghl = _clients()
    result = booking.book(state, slot, ghl, instantly, now=NOW, free_slots=[slot], store=store)

    assert shadow_world["escapes"] == []
    appointment_id = state.cadence["booking"]["appointment_id"]
    assert appointment_id and appointment_id.startswith("shadow-appt-")

    row = store.get("appointment:%s" % appointment_id)
    assert row and row["lead_email"] == state.lead_email and row["start"] == slot and row["confirmed"] is False

    index = store.get("appt:%s" % appointment_id)
    assert index and index["appointment_id"] == appointment_id

    assert slot in approval_mod.offered_slots(store, NOW)
    assert show_rate.pending_touches(store, appointment_id), "the show-rate ladder was not armed"

    # and the confirmation is still only a draft
    assert result.draft.label == "booking_confirmation"
    assert [r for r in _records(shadow_world["tmp"] / "shadow_log.jsonl") if r["action"] == "reply_to_email"] == []


def test_the_replay_the_tick_and_the_webhook_share_one_store(shadow_world, monkeypatch):
    """app.state.store, DEPS.store and the jobs must be the same object, or a
    booking made by the webhook is invisible to the tick that has to chase it."""
    from shared.store import get_store

    from services.reply_engine import app as app_mod

    monkeypatch.setattr(app_mod, "DEPS", app_mod.Deps())
    deps = app_mod.configure()
    assert deps.store is get_store()
    assert app_mod.app.state.store is deps.store
    assert get_store() is get_store()          # cached on (runtime, path)


def test_the_shadow_log_payloads_are_replayable_request_bodies(replayed):
    """Every would_do payload has to be the body a live run would send, or the
    log is a description of something that cannot be checked."""
    records = _records(replayed["world"]["tmp"] / "shadow_log.jsonl")
    for rec in records:
        if rec["action"] == "update_interest_status":
            assert set(rec["payload"]) == {"lead_email", "campaign_id", "interest_value"}, rec
            assert rec["payload"]["interest_value"] in _interest_codes()
        if rec["action"] == "blocklist_create":
            assert rec["payload"] == {"bl_value": rec["payload"]["bl_value"]}, rec
        if rec["action"] == "reply_to_email":
            assert rec["payload"].get("to"), rec       # the recipient guard is never dropped


def _interest_codes():
    return set(int(k) for k in settings.IDS["instantly"]["interest_status_codes"])


def test_nothing_in_this_module_ever_saw_the_network(shadow_world):
    """A belt for the belt: the guard itself is exercised, so a future refactor
    that removes it fails here instead of quietly going live."""
    import httpx as httpx_mod

    with pytest.raises(NetworkEscape):
        httpx_mod.Client().get("https://api.instantly.ai/api/v2/campaigns")
    assert shadow_world["escapes"]


def test_release_slots_cannot_lose_a_concurrent_reservation(tmp_env):
    """release_slots did a read-then-set on the shared offered_slots registry
    while reserve_slots used the atomic store.mutate, so a reservation written
    between the get and the set was silently dropped - which is exactly the
    double-offer the registry exists to prevent. Four schedules write this key
    (poller every 5 min, cadence hourly, appointments every 10 min, the web
    approve/veto handlers), and modal_app runs them as separate functions."""
    import threading

    from services.reply_engine import approval as approval_mod
    from shared import slots as slot_rules
    from shared.store import JsonFileStore

    now = slot_rules.parse_iso("2026-09-22T13:00:00-05:00")
    store = JsonFileStore(str(tmp_env / "slots.json"))
    approval_mod.reserve_slots(store, "old@lead.com", ["2026-09-23T14:00:00-05:00"], "a-old", now)

    errors = []

    def reserve(i):
        try:
            approval_mod.reserve_slots(store, "lead%d@x.com" % i, ["2026-09-24T1%d:00:00-05:00" % i], "a-%d" % i, now)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reserve, args=(i,)) for i in range(8)]
    releaser = threading.Thread(target=approval_mod.release_slots, args=(store, "a-old"))
    for t in threads[:4]:
        t.start()
    releaser.start()
    for t in threads[4:]:
        t.start()
    for t in threads + [releaser]:
        t.join()

    assert not errors
    rows = store.get(approval_mod.OFFERED_KEY, []) or []
    assert sorted(r["approval"] for r in rows) == ["a-%d" % i for i in range(8)]
