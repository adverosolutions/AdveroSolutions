"""S-rest round 4, defect 1 (the ingest half): replies processed out of order.

The poller processes oldest first, but a reply whose processing raised is
retried on a later tick, after newer replies succeeded, and a reply a killed
run still held is skipped until its claim goes stale. So a lead's positive
reply sent at 09:00 could be processed after their "remove me" sent at 09:30:
it overwrote the row's status and classification, raised a fresh card, and an
approved answer then armed the follow-up ladder for a lead who asked to be
removed.

What is pinned here (the round-4 shared contract, items 1 to 3):

* every inbound history entry carries ``received_at``, when the lead sent it
  (the email's own time), or the processing time with
  ``received_at_source: "processing"`` when the payload carried none;
* the sticky opt-out marker ``LeadState.opt_out`` is set by any
  router.OPT_OUT_LABELS reply unless the marker records a later one, and is
  cleared only by a human reply provably sent after it: never by a machine,
  never by an older reply, whatever the processing order;
* a reply sent before the marker is recorded and rewrites nothing: no status or
  classification change, no draft, no card, no cadence stop or arm, and one
  alert;
* the cadence reads the marker (stop_reason, and the pre-send re-read,
  changed_in_store, which also holds the day when the row cannot be read);
* GET|POST /mark-sent/{token}, the operator's way out of a send_failed card
  whose reply did go out.

Every lead is an example.com address; every client is an in-process fake.
Live mode is set in-process only.
"""
from datetime import datetime, timedelta

import pytest
import pytz
from fastapi.testclient import TestClient

from shared import job_log, notify
from shared.store import JsonFileStore

from jobs import cadence_tick as cadence_job
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine import models
from services.reply_engine import poller as P
from services.reply_engine import router
from services.reply_engine import show_rate
from services.reply_engine.models import Approval, Classification, Draft, LeadState, ReplyEvent

CT = pytz.timezone("America/Chicago")
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"   # a configured campaign (bookkeeping reactivation)
LEAD = "pat@example.com"
EACCOUNT = "lorenzo@advero-example.com"
THREAD = "thread-r4-order"
SUBJECT = "Re: Pat, question"
KEY = "lead:%s:%s" % (CAMPAIGN, LEAD)
POSITIVE = "Sounds interesting. How does pricing work?"
REMOVE = "Please remove me from your list"
STALE_TITLE = "An older reply from %s arrived after their opt-out; not drafted" % LEAD


def ct(*args):
    return CT.localize(datetime(*args))


def utc(dt):
    return dt.astimezone(pytz.utc).isoformat()


class FakeInstantly(object):
    """Records every call. The lead is the sender of every thread it is asked
    about; ``inbox`` is what GET /emails returns (one page, newest first)."""

    def __init__(self, inbox=None):
        self.sent = []
        self.interest = []
        self.blocklist = []
        self.reads = []
        self.inbox = list(inbox or [])

    def get_email(self, email_id):
        self.reads.append(email_id)
        return {"id": email_id, "from_address_email": LEAD}

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.sent.append({"reply_to_uuid": reply_to_uuid, "eaccount": eaccount, "to": to, "body": body})
        return {"id": "sent-%d" % len(self.sent)}

    def update_interest_status(self, lead_email, campaign_id, value):
        self.interest.append((lead_email, campaign_id, value))
        return {"ok": True}

    def blocklist_create(self, value):
        self.blocklist.append(value)
        return {"ok": True}

    def list_emails(self, email_type=None, limit=100, starting_after=None, **kwargs):
        assert email_type == "received"
        items = sorted(self.inbox, key=lambda it: it["timestamp_created"], reverse=True)
        return {"items": items, "next_starting_after": None}


class Recorder(object):
    """Permissive GHL fake: records every call as (name, args, kwargs)."""

    has_token = False

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*a, **k):
            self.calls.append((name, a, k))
            return {"id": "%s-%d" % (name, len(self.calls))}
        return fn


@pytest.fixture
def world(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    notify.reset_for_tests()
    rows = []
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: rows.append((job, status, details)))
    store = JsonFileStore(tmp_env / "r4_order.json")
    inst = FakeInstantly()
    ghl = Recorder()
    clock = {"now": ct(2026, 9, 28, 10, 0)}
    deps = app_mod.configure(store=store, ghl=ghl, instantly=inst, clock=lambda: clock["now"])
    yield {"store": store, "inst": inst, "ghl": ghl, "deps": deps, "rows": rows, "clock": clock}
    app_mod.configure()


def _go_live(monkeypatch):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")


def _payload(email_id, text, received=None, subject=SUBJECT, time_field="timestamp"):
    payload = {"event_type": "reply_received", "campaign_id": CAMPAIGN, "campaign_name": "x", "lead_email": LEAD,
               "email_account": EACCOUNT, "firstName": "Pat", "companyName": "Example Bookkeeping",
               "reply_subject": subject, "reply_text": text, "email_id": email_id, "thread_id": THREAD}
    if received is not None:
        payload[time_field] = utc(received)
    return payload


def _reply(world, email_id, text, received, now, subject=SUBJECT):
    """One webhook reply through the real pipeline. ``received`` None: the
    payload carries no time."""
    event = ReplyEvent.from_webhook(_payload(email_id, text, received, subject))
    return app_mod.process_event(event, deps=world["deps"], now=now, busy_blocks=[])


def _item(email_id, text, created):
    """One GET /emails row in the live API's shape."""
    return {"id": email_id, "thread_id": THREAD, "campaign_id": CAMPAIGN, "eaccount": EACCOUNT,
            "from_address_email": LEAD, "to_address_email_list": EACCOUNT, "subject": SUBJECT,
            "timestamp_created": created, "i_status": 1, "lead": LEAD, "step": "0_1_0", "body": {"text": text}}


def _entry(row, email_id):
    found = [e for e in row.get("history") or [] if e.get("event") == "inbound" and e.get("email_id") == email_id]
    assert len(found) == 1, found
    return found[0]


def _stale_alerts():
    return [n for n in notify.sent_in_test if n["title"] == STALE_TITLE]


def _calls(world):
    """Every outbound call the fakes saw, as copies."""
    inst = world["inst"]
    return (list(inst.sent), list(inst.interest), list(inst.blocklist), list(world["ghl"].calls))


def _cards(store):
    return store.keys(A.APPROVAL_PREFIX)


def _assert_rewrote_nothing(row, before, marker_email_id):
    """The row as the opt-out left it: status, classification, marker, cards,
    last reply and cadence all unchanged; the ladder not armed."""
    assert row["status"] == before["status"]
    assert row["classification"] == before["classification"]
    assert row["opt_out"] == before["opt_out"] and row["opt_out"]["email_id"] == marker_email_id
    assert row["approvals"] == before["approvals"]
    assert row["last_email_id"] == before["last_email_id"]
    assert row["last_inbound_at"] == before["last_inbound_at"]
    assert row["cadence"] == before["cadence"] and not (row["cadence"] or {}).get("armed_at")


# ====================================================== P14: through the app
def test_p14_an_older_positive_processed_after_the_remove_me_rewrites_nothing(world):
    st = world["store"]
    unsub = _reply(world, "m-2", REMOVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    assert unsub["label"] == "unsubscribe" and unsub["opt_out"] == "set" and unsub["stale"] is None
    before = st.get(KEY)
    marker = before["opt_out"]
    assert marker["label"] == "unsubscribe" and marker["email_id"] == "m-2"
    assert marker["received_at"] == "2026-09-28T14:30:00+00:00"
    assert marker["set_at"] == ct(2026, 9, 28, 9, 31).isoformat() and "received_at_source" not in marker
    calls = _calls(world)
    pushes = len(notify.sent_in_test)

    pos = _reply(world, "m-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert pos["label"] == "positive_question" and pos["stale"] == "opt_out"
    assert pos["approval_token"] is None and pos["draft"] is None and pos["cards_held"] == []
    assert pos["cadence_stopped"] is None and pos["superseded"] == [] and pos["opt_out"] is None
    assert [(a["system"], a["action"], a["kind"]) for a in pos["actions"]] == [("store", "stale_reply", "skipped")]
    row = st.get(KEY)
    _assert_rewrote_nothing(row, before, "m-2")
    assert row["classification"]["label"] == "unsubscribe"
    entry = _entry(row, "m-1")
    assert entry["stale"] == "opt_out" and entry["label"] == "positive_question"
    assert entry["received_at"] == "2026-09-28T14:00:00+00:00" and entry["at"] == ct(2026, 9, 28, 9, 40).isoformat()
    assert "m-1" in row["processed_email_ids"]
    assert _cards(st) == []                                     # no card anywhere
    assert _calls(world) == calls                               # no GHL write, no Instantly call
    alerts = _stale_alerts()
    assert len(alerts) == 1 and len(notify.sent_in_test) == pushes + 1
    assert alerts[0]["priority"] == "high" and "Nothing was sent" in alerts[0]["message"]
    assert "unsubscribe" in alerts[0]["message"] and "positive_question" in alerts[0]["message"]
    logged = [d for job, status, d in world["rows"] if job == "reply_engine.process_event" and d.get("stale")]
    assert len(logged) == 1 and logged[0]["draft"] is False and logged[0]["received_at"] == entry["received_at"]

    # the same reply delivered again (the webhook and the poller both see it): a duplicate, no second alert
    again = _reply(world, "m-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 45))
    assert again["skipped"] == "duplicate"
    assert len(_stale_alerts()) == 1 and st.get(KEY)["history"] == row["history"]


# ===================================== P14b: through the poller, first attempt fails
@pytest.mark.parametrize("where", ["classify", "route"], ids=["classifier_timeout", "fails_after_classifying"])
def test_p14b_the_poller_retries_the_older_positive_after_the_remove_me_and_drafts_nothing(world, monkeypatch, where):
    st = world["store"]
    world["inst"].inbox = [_item("pa-1", POSITIVE, "2026-09-28T14:00:00.000Z"),
                           _item("pb-2", REMOVE, "2026-09-28T14:30:00.000Z")]
    failed = []
    real = getattr(app_mod, where)

    def flaky(event, *a, **k):
        if event.email_id == "pa-1" and not failed:
            failed.append(event.email_id)
            raise RuntimeError("classifier timed out")
        return real(event, *a, **k)

    monkeypatch.setattr(app_mod, where, flaky)

    def process(event, now=None):
        return app_mod.process_event(event, deps=world["deps"], now=now, busy_blocks=[])

    first = P.run_once(world["inst"], st, now=ct(2026, 9, 28, 9, 35), campaign_filter=[CAMPAIGN], process=process)
    assert failed == ["pa-1"] and first["errors"] == 1 and first["processed"] == 1
    assert first["failed_pending"] == ["pa-1"]
    before = st.get(KEY)
    assert before["opt_out"]["email_id"] == "pb-2" and before["classification"]["label"] == "unsubscribe"
    assert "pa-1" not in before["processed_email_ids"]            # the failed attempt is retried
    calls = _calls(world)

    second = P.run_once(world["inst"], st, now=ct(2026, 9, 28, 9, 40), campaign_filter=[CAMPAIGN], process=process)
    assert second["errors"] == 0 and second["processed"] == 1 and second["failed_pending"] == []
    retried = [r for r in second["results"] if r.get("email_id") == "pa-1"]
    assert len(retried) == 1 and retried[0]["label"] == "positive_question"
    assert retried[0]["approval"] is False and retried[0]["draft"] is False
    row = st.get(KEY)
    _assert_rewrote_nothing(row, before, "pb-2")
    entry = _entry(row, "pa-1")
    assert entry["stale"] == "opt_out" and entry["received_at"] == "2026-09-28T14:00:00+00:00"
    assert entry["source"] == "poller" and row["processed_email_ids"].count("pa-1") == 1
    assert _cards(st) == [] and _calls(world) == calls and world["inst"].sent == []
    assert len(_stale_alerts()) == 1


# ================================================ P14c: live, then the ladder
def test_p14c_live_the_older_positive_sends_nothing_and_no_d1_follows(world, monkeypatch):
    st = world["store"]
    _go_live(monkeypatch)
    unsub = _reply(world, "l-2", REMOVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    assert unsub["label"] == "unsubscribe" and world["inst"].blocklist == [LEAD]
    before = st.get(KEY)
    calls = _calls(world)

    pos = _reply(world, "l-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert pos["stale"] == "opt_out" and pos["approval_token"] is None
    assert _calls(world) == calls                        # live: no interest back to positive, no CRM stage, no reply
    assert world["inst"].sent == [] and _cards(st) == []
    _assert_rewrote_nothing(st.get(KEY), before, "l-2")

    # the queue flush and the hourly ladder, live, on the days D1 and D2 would go
    assert A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"]) == []
    ladder = FakeInstantly()
    pings = []
    for when in (ct(2026, 9, 29, 9, 30), ct(2026, 9, 29, 10, 0), ct(2026, 9, 30, 10, 0)):
        cadence_job.run(when, st, ladder, None, free_slots=FREE, notify_fn=lambda *a, **k: pings.append(a),
                        log_fn=lambda *a, **k: None)
    assert ladder.sent == [] and world["inst"].sent == [] and pings == []
    assert st.get(KEY)["opt_out"]["email_id"] == "l-2" and len(_stale_alerts()) == 1


# ======================================= P14d: every final no, not only "remove me"
@pytest.mark.parametrize("text,label", [
    ("Not interested, thanks.", "negative_notfit"),
    ("I'm not the right person for this, I don't handle marketing here.", "wrong_person"),
    ("Stop emailing me. This is spam and I will report you.", "negative_hostile"),
    ("Not right now, maybe next quarter.", "negative_notnow"),
], ids=["not_a_fit", "wrong_person", "hostile", "not_now"])
def test_p14d_every_final_no_keeps_an_older_positive_from_being_drafted(world, text, label):
    st = world["store"]
    no = _reply(world, "d-2", text, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    assert no["label"] == label and no["opt_out"] == "set"
    before = st.get(KEY)
    assert before["opt_out"]["label"] == label and before["opt_out"]["email_id"] == "d-2"
    calls = _calls(world)

    pos = _reply(world, "d-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert pos["stale"] == "opt_out" and pos["approval_token"] is None
    row = st.get(KEY)
    _assert_rewrote_nothing(row, before, "d-2")
    assert row["classification"]["label"] == label
    assert _cards(st) == [] and _calls(world) == calls and len(_stale_alerts()) == 1


# ======================================================== the marker's rules
def test_a_positive_sent_after_the_opt_out_clears_the_marker_and_gets_a_normal_card(world):
    st = world["store"]
    _reply(world, "c-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))
    assert st.get(KEY)["opt_out"]["email_id"] == "c-1"

    later = _reply(world, "c-2", POSITIVE, ct(2026, 9, 28, 10, 15), ct(2026, 9, 28, 10, 16))
    assert later["label"] == "positive_question" and later["stale"] is None and later["opt_out"] == "cleared"
    assert later["approval_token"] and later["cards_held"] == []
    row = st.get(KEY)
    assert row.get("opt_out") is None
    assert row["classification"]["label"] == "positive_question" and row["status"] == "draft_pending_approval"
    assert _entry(row, "c-2").get("stale") is None and _stale_alerts() == []
    card = A.load(later["approval_token"], st)
    assert card.status == "pending"
    # nothing of the lead's holds it any more: it approves and goes out like any card (to the fake client)
    out = A.approve(later["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 10, 30), ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent"
    assert len(world["inst"].sent) == 1 and world["inst"].sent[0]["to"] == LEAD


@pytest.mark.parametrize("subject,text,label", [
    ("Automatic reply: Re: Pat, question", "Automatic reply from the office.", "ooo"),
    ("Thank you for reaching out", "", "auto_reply_unmonitored"),
], ids=["out_of_office", "unmonitored_mailbox"])
def test_a_machine_reply_sent_after_the_opt_out_never_clears_it(world, subject, text, label):
    st = world["store"]
    _reply(world, "a-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))
    before = st.get(KEY)
    res = _reply(world, "a-2", text, ct(2026, 9, 28, 10, 0), ct(2026, 9, 28, 10, 1), subject=subject)
    assert res["label"] == label and res["stale"] is None and res["opt_out"] is None
    assert res["approval_token"] is None
    row = st.get(KEY)
    assert row["opt_out"] == before["opt_out"] and row["status"] == before["status"]
    # and the ladder never takes the opted-out lead's stop for an auto-reply pause to resume: armed
    # after the opt-out was processed, only the machine's reply came since
    armed = dict(row.get("cadence") or {}, armed_at=ct(2026, 9, 28, 9, 30).isoformat(), stopped_reason="inbound_reply")
    state = LeadState.from_store(dict(row, cadence=armed))
    assert cadence.is_auto_reply_pause(state) is False
    assert cadence.is_auto_reply_pause(state.model_copy(update={"opt_out": None})) is True


def test_an_older_opt_out_processed_late_keeps_the_newer_marker(world):
    st = world["store"]
    _reply(world, "o-2", REMOVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    marker = st.get(KEY)["opt_out"]
    res = _reply(world, "o-1", "Not interested, thanks.", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert res["label"] == "negative_notfit" and res["stale"] == "opt_out" and res["opt_out"] is None
    assert st.get(KEY)["opt_out"] == marker


def test_a_removal_request_sent_before_the_marker_is_still_honoured_but_rewrites_nothing(world):
    """A stale reply changes nothing on the row, but a lead who asked to be
    removed is removed whatever else they wrote: the blocklist still goes."""
    st = world["store"]
    no = _reply(world, "r-2", "Not interested, thanks.", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    assert no["label"] == "negative_notfit" and world["inst"].blocklist == []
    before = st.get(KEY)
    res = _reply(world, "r-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert res["label"] == "unsubscribe" and res["stale"] == "opt_out"
    assert world["inst"].blocklist == [LEAD]
    assert ("store", "stale_reply", "skipped") in [(a["system"], a["action"], a["kind"]) for a in res["actions"]]
    row = st.get(KEY)
    _assert_rewrote_nothing(row, before, "r-2")
    assert row["status"] == "lost" and row["classification"]["label"] == "negative_notfit"
    alerts = _stale_alerts()
    assert len(alerts) == 1 and "The removal request in it was still applied" in alerts[0]["message"]


def test_an_older_reply_processed_after_a_newer_one_is_recorded_only(world):
    """Case (b): no opt-out involved. Round 4 processed the older reply as a
    new one that only kept the newer classification, which superseded the
    newer card; round 5 makes it stale (router.STALE_OLDER_REPLY): recorded,
    rewriting nothing, the newer card left pending (test_srest_r5_older_reply
    has the rest)."""
    st = world["store"]
    newer = _reply(world, "b-2", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    assert newer["label"] == "positive_question"
    older = _reply(world, "b-1", "Are you a bot or a real person?", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert older["label"] == "neutral_question" and older["stale"] == router.STALE_OLDER_REPLY
    assert older["approval_token"] is None and older["superseded"] == []
    row = st.get(KEY)
    assert row["classification"]["label"] == "positive_question" and row.get("opt_out") is None
    assert A.load(newer["approval_token"], st).status == "pending"
    assert _entry(row, "b-1")["received_at"] == "2026-09-28T14:00:00+00:00"
    assert _entry(row, "b-1")["stale"] == router.STALE_OLDER_REPLY
    assert _entry(row, "b-2")["received_at"] == "2026-09-28T14:30:00+00:00"
    # an opt-out always takes effect, whatever came after it
    assert router.sent_before_a_newer_reply(LeadState.from_store(row), "unsubscribe", ct(2026, 9, 28, 9, 0)) is False
    assert router.sent_before_a_newer_reply(LeadState.from_store(row), "neutral_question", ct(2026, 9, 28, 9, 0),
                                            email_id="b-1") is True


def test_a_failed_pipeline_sets_the_marker_but_never_clears_it(world, monkeypatch):
    st = world["store"]
    real = app_mod.route
    fail = {"ids": {"p-1", "p-2"}}

    def flaky(event, *a, **k):
        if event.email_id in fail["ids"]:
            fail["ids"].discard(event.email_id)
            raise RuntimeError("GHL timed out")
        return real(event, *a, **k)

    monkeypatch.setattr(app_mod, "route", flaky)
    with pytest.raises(RuntimeError):
        _reply(world, "p-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))
    marker = st.get(KEY)["opt_out"]
    assert marker["email_id"] == "p-1"                              # the opt-out's intent is kept at once
    with pytest.raises(RuntimeError):
        _reply(world, "p-2", POSITIVE, ct(2026, 9, 28, 10, 0), ct(2026, 9, 28, 10, 1))
    assert st.get(KEY)["opt_out"] == marker                          # a half-run reply never clears it
    retried = _reply(world, "p-2", POSITIVE, ct(2026, 9, 28, 10, 0), ct(2026, 9, 28, 10, 6))
    assert retried["opt_out"] == "cleared" and retried["approval_token"]   # its retry decides
    assert st.get(KEY).get("opt_out") is None


def test_a_stale_reply_whose_write_fails_is_retried_and_still_alerts_once(world, monkeypatch):
    """Nothing of a stale reply is saved when its write fails: a saved copy
    would mark it processed with no alert sent, and the retry would then be a
    duplicate."""
    st = world["store"]
    _reply(world, "w-2", REMOVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    before = st.get(KEY)
    real = A.save_lead_state
    failed = []

    def flaky(store, state, base, *a, **k):
        if not failed and any(e.get("stale") for e in state.history or []):
            failed.append(state.history[-1]["email_id"])
            raise OSError("store lock timed out")
        return real(store, state, base, *a, **k)

    monkeypatch.setattr(A, "save_lead_state", flaky)
    with pytest.raises(OSError):
        _reply(world, "w-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    row = st.get(KEY)
    assert failed == ["w-1"] and "w-1" not in row["processed_email_ids"] and row["history"] == before["history"]
    assert _stale_alerts() == []
    retried = _reply(world, "w-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 45))
    assert retried["stale"] == "opt_out" and retried["approval_token"] is None
    assert len(_stale_alerts()) == 1 and st.get(KEY)["processed_email_ids"].count("w-1") == 1


def test_the_history_implies_a_marker_a_concurrent_first_write_dropped():
    unsub = {"at": "2026-09-28T09:31:00-05:00", "event": "inbound", "email_id": "u-1", "label": "unsubscribe",
             "source": "webhook", "received_at": "2026-09-28T14:30:00+00:00"}
    ooo = {"at": "2026-09-28T10:01:00-05:00", "event": "inbound", "email_id": "u-2", "label": "ooo",
           "source": "webhook", "received_at": "2026-09-28T15:00:00+00:00"}
    unknown_time = {"at": "2026-09-28T10:02:00-05:00", "event": "inbound", "email_id": "u-3",
                    "label": "positive_question", "source": "webhook", "received_at": "2026-09-28T15:02:00+00:00",
                    "received_at_source": "processing"}
    later = dict(unknown_time, email_id="u-4")
    later.pop("received_at_source")
    implied = router.implied_opt_out([unsub, ooo, unknown_time])
    assert implied == {"label": "unsubscribe", "email_id": "u-1", "received_at": "2026-09-28T14:30:00+00:00",
                       "set_at": "2026-09-28T09:31:00-05:00"}
    assert router.implied_opt_out([unsub, later]) is None             # a human reply provably after it
    assert router.implied_opt_out([dict(unsub, received_at=None)]) is None   # an entry from before round 4

    # under the lock: a row that lost its marker gets it back from the history
    event = ReplyEvent.from_webhook(_payload("u-0", POSITIVE, ct(2026, 9, 28, 9, 0)))
    ctx = {"label": "positive_question", "received_at": ct(2026, 9, 28, 9, 0), "received_at_source": "email"}
    merged = app_mod._settle_opt_out_marker({"history": [unsub], "opt_out": None}, event, ctx, ct(2026, 9, 28, 9, 40))
    assert merged["opt_out"] == implied and ctx["opt_out"] == "restored"


# ====================================================== received_at and old rows
def test_received_at_is_the_emails_own_time_and_falls_back_to_the_processing_time(world):
    st = world["store"]
    _reply(world, "f-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 5))
    first = _entry(st.get(KEY), "f-1")
    assert first["received_at"] == "2026-09-28T14:00:00+00:00" and first["at"] == ct(2026, 9, 28, 9, 5).isoformat()
    assert "received_at_source" not in first

    _reply(world, "f-2", "Also, do you work with firms our size?", None, ct(2026, 9, 28, 9, 20))
    second = _entry(st.get(KEY), "f-2")
    assert second["received_at"] == "2026-09-28T14:20:00+00:00" and second["received_at_source"] == "processing"
    assert second["at"] == ct(2026, 9, 28, 9, 20).isoformat()

    # the event's own sources
    with_time = ReplyEvent.from_webhook(_payload("f-3", "x", ct(2026, 9, 28, 9, 0), time_field="timestamp_created"))
    assert with_time.received_at_source == "email" and utc(with_time.received_at) == "2026-09-28T14:00:00+00:00"
    assert ReplyEvent.from_webhook(_payload("f-4", "x")).received_at_source == "processing"
    polled = ReplyEvent.from_poller_item(_item("f-5", "x", "2026-09-28T14:10:00.000Z"))
    assert polled.received_at_source == "email" and utc(polled.received_at) == "2026-09-28T14:10:00+00:00"
    email_time = dict(_item("f-6", "x", None), timestamp_email="2026-09-28T14:11:00.000Z")
    email_time.pop("timestamp_created")
    assert utc(ReplyEvent.from_poller_item(email_time).received_at) == "2026-09-28T14:11:00+00:00"
    processed = ct(2026, 9, 28, 9, 30)
    assert models.reply_received_at(ReplyEvent.from_webhook(_payload("f-7", "x")), processed) == (processed,
                                                                                                "processing")
    # readers: an entry written before round 4 falls back to "at", and only an email time proves an order
    old = {"at": "2026-09-28T09:00:00-05:00", "event": "inbound", "email_id": "f-8", "label": "positive_question"}
    assert models.entry_received_at(old) == ct(2026, 9, 28, 9, 0) and models.entry_email_time(old) is None
    assert models.entry_email_time(second) is None and models.entry_email_time(first) == ct(2026, 9, 28, 9, 0)


def test_a_reply_with_no_time_can_neither_clear_nor_escape_the_marker(world):
    st = world["store"]
    _reply(world, "n-1", REMOVE, None, ct(2026, 9, 28, 9, 0))
    marker = st.get(KEY)["opt_out"]
    assert marker["received_at"] == "2026-09-28T14:00:00+00:00" and marker["received_at_source"] == "processing"
    # processed after the opt-out, but its time is only when the engine saw it: not provably later
    unknown = _reply(world, "n-2", POSITIVE, None, ct(2026, 9, 28, 9, 30))
    assert unknown["stale"] == "opt_out" and unknown["approval_token"] is None
    assert st.get(KEY)["opt_out"] == marker
    said = _stale_alerts()[0]["message"]
    assert "It carried no send time of its own" in said and "cannot be shown to come after" in said
    # a reply whose own time is after the opt-out was seen is provably later
    known = _reply(world, "n-3", "Sure, what times do you have next week?", ct(2026, 9, 28, 9, 45),
                   ct(2026, 9, 28, 9, 46))
    assert known["stale"] is None and known["opt_out"] == "cleared"


def test_rows_stored_before_the_marker_existed_load_and_process(world):
    st = world["store"]
    old = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Pat", eaccount=EACCOUNT,
                    status="positive_awaiting_draft", processed_email_ids=["o-0"],
                    history=[{"at": "2026-09-25T09:00:00-05:00", "event": "inbound", "email_id": "o-0",
                              "label": "positive_question", "source": "webhook"}]).to_store()
    old.pop("opt_out")
    st.set(KEY, old)
    state = LeadState.from_store(st.get(KEY))
    assert state.opt_out is None and state.to_store()["opt_out"] is None
    assert cadence.state_from_dict(st.get(KEY)).opt_out is None
    assert cadence.stop_reason(cadence.arm(state, ct(2026, 9, 25, 16, 0)), ct(2026, 9, 28, 10, 0)) is None

    res = _reply(world, "o-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))
    assert res["label"] == "unsubscribe" and res["opt_out"] == "set"
    row = st.get(KEY)
    assert row["opt_out"]["email_id"] == "o-1" and "received_at" not in _entry(row, "o-0")
    # the marker round-trips, and a malformed value neither breaks the row nor stops holding
    assert LeadState.from_store(row).to_store()["opt_out"] == row["opt_out"]
    for bad in (True, "yes", ["o-1"], 1):
        assert LeadState.from_store(dict(row, opt_out=bad)).opt_out == {"malformed": str(bad)}
    assert LeadState.from_store(dict(row, opt_out={})).opt_out is None
    assert router.stale_reason(LeadState.from_store(dict(row, opt_out="yes")), "positive_question",
                               ct(2026, 9, 28, 12, 0)) == "opt_out"


# ================================================================ the cadence
ARMED_AT = ct(2026, 9, 21, 16, 0)
FREE = ["2026-09-24T13:00:00-05:00", "2026-09-25T14:00:00-05:00", "2026-09-28T13:00:00-05:00",
        "2026-09-29T14:00:00-05:00", "2026-09-30T13:00:00-05:00", "2026-10-01T14:00:00-05:00"]
MARKER = {"label": "unsubscribe", "email_id": "x-9", "received_at": "2026-09-23T14:00:00+00:00",
          "set_at": "2026-09-23T09:01:00-05:00"}


def _d2_ladder(store, **fields):
    """Pat, armed Mon 21st 16:00, day 1 done: D2 due Wed 23rd 10:00."""
    state = cadence.arm(LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, status="positive_question", first_name="Pat",
                                  company="Example Bookkeeping", eaccount=EACCOUNT, thread_id=THREAD,
                                  last_email_id="e-0", last_subject=SUBJECT, **fields), ARMED_AT)
    state.cadence["day"] = 1
    state.cadence["next_send_at"] = ct(2026, 9, 23, 10, 0).isoformat()
    store.set(state.key, cadence.state_to_dict(state))
    return state


class Flaky(object):
    """The store, except that reading the lead's row raises while ``down``."""

    def __init__(self, inner):
        self.inner = inner
        self.down = False

    def get(self, key, default=None):
        if key == KEY and self.down:
            raise OSError("store read timed out")
        return self.inner.get(key, default)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_the_pre_send_re_read_holds_on_an_unreadable_row_and_on_the_marker():
    state = cadence.arm(LeadState(lead_email=LEAD, campaign_id=CAMPAIGN), ARMED_AT)
    same = cadence.state_to_dict(state)

    class Store(object):
        def __init__(self, row=None, error=None):
            self.row, self.error = row, error

        def get(self, key, default=None):
            if self.error is not None:
                raise self.error
            return self.row

    assert cadence.changed_in_store(state, Store(error=OSError("timed out"))) == "row_unreadable"
    assert cadence.changed_in_store(state, Store(error=ValueError("bad json")), ct(2026, 9, 23, 10, 0)) == \
        "row_unreadable"
    assert cadence.changed_in_store(state, Store(dict(same, opt_out=MARKER))) == "opt_out"
    assert cadence.changed_in_store(state, Store(dict(same, opt_out="yes"))) == "opt_out"
    assert cadence.changed_in_store(state, Store(dict(same, opt_out=None))) is None
    assert cadence.changed_in_store(state, Store(same)) is None
    assert cadence.changed_in_store(state, Store(None)) is None        # nothing stored for the lead: proceeds

    marked = state.model_copy(update={"opt_out": MARKER})
    assert cadence.stop_reason(marked, ct(2026, 9, 23, 10, 0)) == "opt_out"
    assert cadence.stop_reason(state, ct(2026, 9, 23, 10, 0)) is None


@pytest.mark.parametrize("change", ["opt_out", "row_unreadable"])
def test_a_marker_landing_or_an_unreadable_row_mid_tick_holds_the_day_and_sends_nothing(tmp_env, monkeypatch,
                                                                                         change):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    inner = JsonFileStore(tmp_env / "tick.json")
    store = Flaky(inner)
    state = _d2_ladder(inner)
    _go_live(monkeypatch)
    inst = FakeInstantly()
    real_build = cadence.build_touch

    def mid_tick(*a, **k):
        # the tick has read the row and is building D2
        if change == "opt_out":
            inner.set(KEY, dict(inner.get(KEY), opt_out=MARKER))
        else:
            store.down = True
        return real_build(*a, **k)

    monkeypatch.setattr(cadence, "build_touch", mid_tick)
    summary = cadence_job.run(ct(2026, 9, 23, 10, 5), store, inst, None, free_slots=FREE,
                              notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    monkeypatch.setattr(cadence, "build_touch", real_build)
    store.down = False
    result = summary["results"][0]
    assert result["action"] == "stopped" and result["reason"] == "changed_while_ticking:%s" % change
    assert result["day"] == 2 and inst.sent == []
    assert inner.get(cadence.touch_marker_key(state, 2)) is None          # the day is not spent
    row = inner.get(KEY)
    assert row["cadence"]["day"] == 1 and not row["cadence"].get("touches")
    later = cadence_job.run(ct(2026, 9, 23, 11, 5), store, inst, None, free_slots=FREE,
                            notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    if change == "opt_out":
        # the marker stops the ladder for good; nothing goes out, then or later
        assert [(r["action"], r.get("reason")) for r in later["results"]] == [("stopped", "opt_out")]
        assert inst.sent == [] and inner.get(KEY)["cadence"]["stopped_reason"] == "opt_out"
    else:
        # a read error only held that one attempt: the row reads again, and D2 goes
        assert [r["action"] for r in later["results"]] == ["sent"] and len(inst.sent) == 1
        assert inst.sent[0]["to"] == LEAD


def test_an_opted_out_lead_whose_status_says_otherwise_is_stopped_by_the_marker(tmp_env, monkeypatch):
    """The marker stops the ladder even when the row's status and
    classification do not say opt-out (the order of processing can no longer
    leave a positive status on an opted-out lead, and this holds either way)."""
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    store = JsonFileStore(tmp_env / "tick2.json")
    _d2_ladder(store, opt_out=MARKER)
    _go_live(monkeypatch)
    inst = FakeInstantly()
    summary = cadence_job.run(ct(2026, 9, 23, 10, 5), store, inst, None, free_slots=FREE,
                              notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    assert [(r["action"], r.get("reason")) for r in summary["results"]] == [("stopped", "opt_out")]
    assert inst.sent == [] and store.get(KEY)["cadence"]["stopped_reason"] == "opt_out"


def test_the_routers_machine_labels_are_the_cadences_auto_reply_statuses():
    assert set(router.MACHINE_LABELS) == set(cadence.AUTO_REPLY_STATUSES)


def test_a_stale_auto_responder_still_queues_its_hand_off_and_moves_nothing(tmp_env):
    store = JsonFileStore(tmp_env / "handoff.json")
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, status="blocklisted", opt_out=dict(MARKER))
    event = ReplyEvent.from_webhook(_payload("h-1", "This mailbox is no longer monitored.", ct(2026, 9, 23, 8, 0)))
    cls = Classification(label="auto_reply_unmonitored", confidence=0.99, method="rule", reason="mailbox")
    actions = router.route(event, cls, state, None, None, now=ct(2026, 9, 23, 9, 30), store=store)
    assert [a.action for a in actions][:2] == ["stale_reply", "record_auto_responder"]
    assert state.status == "blocklisted" and state.classification is None and state.last_inbound_at is None
    assert len(store.get(router.AUTO_RESPONDERS_KEY)) == 1


# ================================================================ /mark-sent
def _send_failed_card(world):
    """A real card, stuck at send_failed (its send raised after the POST)."""
    res = _reply(world, "s-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))
    token = res["approval_token"]
    assert token
    card_id = token.split(".", 1)[0]
    row = world["store"].get(A.APPROVAL_PREFIX + card_id)
    row.update(status="send_failed", decided_at=ct(2026, 9, 28, 9, 30).isoformat())
    world["store"].set(A.APPROVAL_PREFIX + card_id, row)
    return token, card_id


def _fake_mark(calls, answer=None):
    """Stands in for approval.mark_sent_manually (its final signature):
    send_failed -> sent_manually."""

    def mark(approval_id, now, by="lorenzo", store=None, ghl=None):
        calls.append({"approval_id": approval_id, "now": now, "by": by, "store": store, "ghl": ghl})
        if answer is not None:
            return answer
        row = store.get(A.APPROVAL_PREFIX + approval_id)
        if row.get("status") != "send_failed":
            return {"ok": False, "status": row.get("status"), "error": "the card changed before it could be marked"}
        store.set(A.APPROVAL_PREFIX + approval_id, dict(row, status="sent_manually"))
        return {"ok": True, "status": "sent_manually", "shadow": False, "invite": None}
    return mark


def test_mark_sent_get_confirms_post_records_and_the_link_is_one_use(world, monkeypatch):
    st = world["store"]
    token, card_id = _send_failed_card(world)
    calls = []
    monkeypatch.setattr(A, "mark_sent_manually", _fake_mark(calls))
    client = TestClient(app_mod.app)

    page = client.get("/mark-sent/%s" % token)
    assert page.status_code == 200 and "Mark this reply as sent?" in page.text
    assert "action='/mark-sent/%s'" % token in page.text and "method='post'" in page.text
    assert "Nothing is sent from this page" in page.text
    assert calls == [] and A.load(token, st).status == "send_failed"      # a GET changes nothing

    world["clock"]["now"] = ct(2026, 9, 28, 11, 0)
    done = client.post("/mark-sent/%s" % token)
    assert done.status_code == 200 and "Marked as sent" in done.text and "Shadow mode" in done.text
    assert "Nothing was sent from this page" in done.text
    assert len(calls) == 1 and calls[0]["approval_id"] == card_id and calls[0]["by"] == "lorenzo"
    assert calls[0]["store"] is st and calls[0]["now"] == ct(2026, 9, 28, 11, 0)
    assert calls[0]["ghl"] is world["ghl"]                  # the app's own GHL client, as /approve passes it
    assert A.load(token, st).status == "sent_manually"

    again = client.post("/mark-sent/%s" % token)
    assert again.status_code == 400 and "this approval is sent_manually" in again.text
    assert client.get("/mark-sent/%s" % token).status_code == 400
    assert len(calls) == 1 and A.load(token, st).status == "sent_manually"

    # a reply that went out, by hand or not, cannot be vetoed (a veto cancels the lead's call)
    veto_page = client.get("/veto/%s" % token)
    assert veto_page.status_code == 400 and "Nothing to veto" in veto_page.text
    veto = client.post("/veto/%s" % token)
    assert veto.status_code == 400 and "Not vetoed" in veto.text
    assert A.load(token, st).status == "sent_manually"


def test_mark_sent_refuses_a_bad_token_and_a_card_that_is_not_stuck(world, monkeypatch):
    st = world["store"]
    token, card_id = _send_failed_card(world)
    calls = []
    monkeypatch.setattr(A, "mark_sent_manually", _fake_mark(calls))
    client = TestClient(app_mod.app)
    forged = "%s.%s" % (card_id, "0" * 64)
    for bad in (forged, "nope.abc", "no-dot"):
        page = client.get("/mark-sent/%s" % bad)
        assert page.status_code == 400 and "Unknown token" in page.text
        post = client.post("/mark-sent/%s" % bad)
        assert post.status_code == 400 and "Not recorded" in post.text
    assert calls == [] and A.load(token, st).status == "send_failed"

    pending = _reply(world, "s-2", "Interested but I have to ask, this is not a scam is it? How much does it cost?",
                     ct(2026, 9, 28, 9, 50), ct(2026, 9, 28, 9, 51))["approval_token"]
    card = A.load(pending, st)
    assert card.status == "pending"
    # No reply of ours reached this lead yet: a first-contact card, which
    # Mark sent takes from pending (Lorenzo sent it himself from the thread).
    assert client.get("/mark-sent/%s" % pending).status_code == 200
    # Once a reply of ours reached the lead it is an ordinary pending card,
    # which Mark sent refuses as before.
    row = st.get(card.state_key)
    row["history"].append({"event": "reply_sent", "at": ct(2026, 9, 28, 9, 52).isoformat()})
    st.set(card.state_key, row)
    assert client.get("/mark-sent/%s" % pending).status_code == 400
    refused = client.post("/mark-sent/%s" % pending)
    assert refused.status_code == 400 and "Nothing to mark" in refused.text
    assert calls == [] and A.load(pending, st).status == "pending"


def test_mark_sent_reports_a_lost_race_a_crash_and_a_call_left_held(world, monkeypatch):
    token, card_id = _send_failed_card(world)
    client = TestClient(app_mod.app)

    calls = []
    lost = {"ok": False, "status": "pending", "error": "the card changed before it could be marked sent"}
    monkeypatch.setattr(A, "mark_sent_manually", _fake_mark(calls, answer=lost))
    page = client.post("/mark-sent/%s" % token)
    assert page.status_code == 400 and "the card changed before it could be marked sent" in page.text
    assert calls[0]["ghl"] is world["ghl"]

    def crash(approval_id, now, by="lorenzo", store=None, ghl=None):
        raise RuntimeError("store lock timed out")

    monkeypatch.setattr(A, "mark_sent_manually", crash)
    page = client.post("/mark-sent/%s" % token)
    assert page.status_code == 500 and "store lock timed out" in page.text

    held = {"ok": True, "status": "sent_manually", "invite": None,
            "booking_left_held": {"slot": "2026-09-30T13:00:00-05:00", "why": "its time has passed"}}
    monkeypatch.setattr(A, "mark_sent_manually", _fake_mark([], answer=held))
    page = client.post("/mark-sent/%s" % token)
    assert page.status_code == 200 and "was NOT confirmed" in page.text and "its time has passed" in page.text
    assert "Wed Sep 30" in page.text                                # the call's time, with its date


APPT = "appt-r4-keep"
KEEP_SLOT = "2026-09-30T13:00:00-05:00"      # Wed 1:00pm CT


def _keep_card(world):
    """A booking confirmation card, stuck at send_failed, that owns the lead's
    unconfirmed call and restates its time (so a send would confirm it: the
    unedited draft's Keep)."""
    st = world["store"]
    created = ct(2026, 9, 28, 9, 0)
    draft = Draft(subject=SUBJECT, body_text="Hey Pat,\n\nYou're booked for Wed 1:00pm CT. The invite is on its way."
                                             "\n\nLorenzo", offered_slots=[KEEP_SLOT], label="booking_confirmation")
    expires = (created + timedelta(hours=48)).isoformat()
    card = Approval(token=A.make_token("k1", KEY, A.draft_hash(draft), expires), state_key=KEY, lead_email=LEAD,
                    campaign_id=CAMPAIGN, email_id="k-1", eaccount=EACCOUNT, reply_to=LEAD, draft=draft,
                    status="send_failed", created_at=created.isoformat(), expires_at=expires,
                    decided_at=ct(2026, 9, 28, 9, 30).isoformat(), label="booking_confirmation")
    st.set(A.APPROVAL_PREFIX + "k1", card.model_dump(mode="json"))
    st.set(A.APPROVAL_CONTEXT_PREFIX + "k1",
           {"email_id": "k-1", "reply_at": created.isoformat(), "processed_before": [], "processed_count": 0,
            "tracks_history": True, "approved_at": ct(2026, 9, 28, 9, 29).isoformat(), "send_attempts": 1})
    A.reserve_slots(st, LEAD, [KEEP_SLOT], "k1", created)
    show_rate.hold(st, APPT, reason="awaiting_approval", now=created, meta={"lead_email": LEAD, "start_iso": KEEP_SLOT})
    booking = {"slot": KEEP_SLOT, "appointment_id": APPT, "awaiting_approval": True, "owner": "k1",
               "booked_at": created.isoformat()}
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Pat", eaccount=EACCOUNT, thread_id=THREAD,
                      status="call_booked", approvals=[card.token], processed_email_ids=["k-1"], last_email_id="k-1",
                      cadence={"booking": booking},
                      history=[{"at": created.isoformat(), "event": "inbound", "email_id": "k-1",
                                "label": "positive_interested", "source": "webhook", "received_at": utc(created)}])
    st.set(KEY, state.to_store())
    return card


def test_mark_sent_confirms_a_kept_call_through_the_apps_ghl_client(world, monkeypatch):
    """Live: the invite of the call the card owns is released through the
    app's GHL client. Without it, mark_sent_manually reports the invite as not
    released and alerts."""
    st = world["store"]
    card = _keep_card(world)
    _go_live(monkeypatch)
    world["clock"]["now"] = ct(2026, 9, 28, 11, 0)
    client = TestClient(app_mod.app)
    assert client.get("/mark-sent/%s" % card.token).status_code == 200
    assert world["ghl"].calls == []                                  # a GET confirms nothing

    done = client.post("/mark-sent/%s" % card.token)
    assert done.status_code == 200 and "Marked as sent" in done.text
    assert "NOT released" not in done.text and "Shadow mode" not in done.text
    confirms = [c for c in world["ghl"].calls if c[0] == "update_appointment_status"]
    assert confirms == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
    booking = st.get(KEY)["cadence"]["booking"]
    assert booking["awaiting_approval"] is False and booking["confirmed_by"] == "k1"
    assert booking["invite_released"] is True
    assert A.load(card.token, st).status == "sent_manually"
    assert world["inst"].sent == []                                  # nothing went through Instantly


@pytest.mark.parametrize("where", ["on_the_card", "hold_row_only"])
def test_mark_sent_is_not_offered_for_a_card_its_recipient_check_held(world, where):
    st = world["store"]
    token, card_id = _send_failed_card(world)
    hold = {"reason": "recipient_mismatch", "attempts": 1, "escalated": True, "at": ct(2026, 9, 28, 9, 30).isoformat()}
    if where == "on_the_card":
        row = st.get(A.APPROVAL_PREFIX + card_id)
        row["notify_result"] = dict(row.get("notify_result") or {}, **{A.RECIPIENT_HELD_KEY: hold})
        st.set(A.APPROVAL_PREFIX + card_id, row)
    else:
        st.set(A.RECIPIENT_HOLD_PREFIX + card_id, hold)
    before_card = st.get(A.APPROVAL_PREFIX + card_id)
    before_row = st.get(KEY)
    ghl_before = list(world["ghl"].calls)
    assert A.mark_sent_url(before_card, st) is None                  # the push carries no Mark sent button
    client = TestClient(app_mod.app)

    page = client.get("/mark-sent/%s" % token)
    assert page.status_code == 400 and A.RECIPIENT_HELD_REFUSAL in page.text
    assert "method='post'" not in page.text                          # no form to press

    direct = client.post("/mark-sent/%s" % token)
    assert direct.status_code == 400 and A.RECIPIENT_HELD_REFUSAL in direct.text
    assert st.get(A.APPROVAL_PREFIX + card_id) == before_card and st.get(KEY) == before_row
    assert st.get(A.SEND_CLAIM_PREFIX + card_id) is None and world["ghl"].calls == ghl_before


def test_mark_sent_through_the_real_approval_side(world):
    st = world["store"]
    token, card_id = _send_failed_card(world)
    client = TestClient(app_mod.app)
    assert client.get("/mark-sent/%s" % token).status_code == 200
    assert A.load(token, st).status == "send_failed"
    done = client.post("/mark-sent/%s" % token)
    assert done.status_code == 200 and "Marked as sent" in done.text
    assert A.load(token, st).status == "sent_manually"
    assert any(e.get("event") == "reply_sent_manually" and e.get("approval") == card_id
               for e in st.get(KEY)["history"])
    again = client.post("/mark-sent/%s" % token)
    assert again.status_code == 400 and A.load(token, st).status == "sent_manually"
