"""P3b: Lorenzo's own first reply, found in the Instantly thread, is day 0.

The engine never sends a first reply (approval.FIRST_REPLY_LOCK_REASON): it
raises a card and Lorenzo sends the draft himself from the thread. The hourly
tick reads the thread (GET /emails, read-only) for every unarmed lead with an
unanswered card, records his send the way Mark sent does and arms the ladder
from its time (cadence.detect_manual_first_reply). Shadow only, every client
a fake: the thread read is a fake list_emails, nothing is sent.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from shared import job_log, notify, settings
from shared.instantly import InstantlyError
from shared.store import JsonFileStore

from jobs import cadence_tick
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine import nurture
from services.reply_engine.models import Draft, LeadState, ReplyEvent
from services.reply_engine.tests.test_ct3_card_autosend import FakeInstantly

CT = pytz.timezone("America/Chicago")
CAMPAIGN = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"   # cleaning reactivation (config/ids.json)
LEAD = "owner@example.com"
EACCOUNT = "lorenzo@advero-example.com"
THREAD = "thread-day0-1"
LINK = "https://example.invalid/book"


def ct(*args):
    return CT.localize(datetime(*args))


REPLY_AT = ct(2030, 1, 11, 14, 0)    # Friday 14:00 CT: the lead's "interested" reply
CARD_AT = ct(2030, 1, 11, 14, 5)     # the first-reply card is raised
SENT_AT = ct(2030, 1, 11, 16, 30)    # Friday 16:30 CT: Lorenzo sends the draft from the thread
TICK = ct(2030, 1, 11, 17, 5)        # the next hourly tick
E1_AT = "2030-01-14T10:00:00-06:00"  # E1: the next business day after the send (Monday 10:00 CT)
SLOTS = ["2030-01-14T13:00:00-06:00", "2030-01-15T14:00:00-06:00"]


class ThreadInstantly(FakeInstantly):
    """test_ct3_card_autosend's fake plus the one read the detection makes."""

    def __init__(self, rows=None, error=None, on_read=None):
        super(ThreadInstantly, self).__init__()
        self.rows = list(rows or [])
        self.error = error
        self.on_read = on_read
        self.reads = []

    def list_emails(self, **params):
        self.reads.append(params)
        if self.on_read is not None:
            self.on_read()
        if self.error is not None:
            raise self.error
        return {"items": list(self.rows), "next_starting_after": None}


def _row(email_id, when, outbound=True, thread=THREAD):
    """One GET /emails?email_type=manual row in the live shape
    (instantly_emails_api_shape_2026-09-21.json): ue_type 3 is ours, 2 theirs."""
    return {"id": email_id, "thread_id": thread, "eaccount": EACCOUNT, "campaign_id": CAMPAIGN,
            "timestamp_created": when.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "ue_type": 3 if outbound else 2,
            "from_address_email": EACCOUNT if outbound else LEAD,
            "to_address_email_list": LEAD if outbound else EACCOUNT,
            "subject": "Re: Jordan, question"}


@pytest.fixture
def env(tmp_env, monkeypatch):
    """test_ct3_card_autosend's world settings (a signing secret, a usable
    BASE_URL, shadow), with the conftest's ladder approvals left in place so
    E1 renders, and every Job_Log row captured."""
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.setattr(settings, "BOOKING_URL", LINK)
    notify.reset_for_tests()
    rows = []
    real = job_log.log_run
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: rows.append((job, status, details))
                        or real(job, status, details))
    return {"store": JsonFileStore(tmp_env / "day0.json"), "rows": rows}


def _seed(store):
    """The lead as the reply pipeline leaves it: the inbound on its history,
    the first-reply card (two held times, no booking link) pending."""
    ev = ReplyEvent(email_id="in-1", thread_id=THREAD, campaign_id=CAMPAIGN, eaccount=EACCOUNT, lead_email=LEAD,
                    first_name="Jordan", company="Brightline Cleaning", subject="Jordan, question",
                    text="Sounds good, tell me more.", received_at=REPLY_AT)
    state = LeadState.from_store(None, ev)
    state.status = "positive_interested"
    state.last_inbound_at = REPLY_AT.isoformat()
    state.last_email_id = "in-1"
    state.last_subject = "Re: Jordan, question"
    state.history.append({"at": CARD_AT.isoformat(), "event": "inbound", "email_id": "in-1",
                          "label": "positive_interested", "received_at": REPLY_AT.isoformat()})
    draft = Draft(subject="Re: Jordan, question", label="positive_interested", model="template",
                  body_text="Hey Jordan, happy to walk you through it. Does Monday at 1pm or Tuesday at 2pm work?",
                  offered_slots=list(SLOTS), template_id="first_reply.reactivation.default.full")
    card = A.create_approval(state, draft, ev, store=store, now=CARD_AT)
    state.processed_email_ids.append("in-1")
    store.set(state.key, state.to_store())
    return state, card


def _card_id(card):
    return card.token.split(".", 1)[0]


def _lead(store, state):
    return cadence.state_from_dict(store.get(state.key))


# ====================================================== the detection itself
def test_lorenzos_reply_in_the_thread_is_recorded_as_mark_sent_would_and_starts_the_ladder(env):
    store = env["store"]
    state, card = _seed(store)
    inst = ThreadInstantly([_row("out-2", SENT_AT + timedelta(hours=1)), _row("out-1", SENT_AT)])
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)

    assert res["action"] == "ladder_started" and res["email_id"] == "out-1"   # the earliest of the two
    assert res["next_send_at"] == E1_AT
    # one read, filtered as narrowly as the API documents; the thread is picked here
    assert inst.reads == [{"email_type": "manual", "eaccount": EACCOUNT, "campaign_id": CAMPAIGN, "limit": 100}]
    lead = _lead(store, state)
    assert lead.last_outbound_at == SENT_AT.isoformat()
    assert [s for s in SLOTS if s in lead.offered_slots] == SLOTS
    sent = [e for e in lead.history if e.get("event") in A.REPLY_SENT_EVENTS]
    assert sent == [{"at": TICK.isoformat(), "event": "reply_sent_manually", "approval": _card_id(card),
                     "by": "lorenzo", "reply_at": REPLY_AT.isoformat(), "sent_at": SENT_AT.isoformat(),
                     "send_failed_at": None, "first_reply": True, "from_status": "pending",
                     "send_started_at": None, "source": "thread", "email_id": "out-1"}]
    # day 0 is the send, so E1 is the next business day after it (Friday -> Monday)
    assert lead.cadence["armed_at"] == SENT_AT.isoformat() and lead.cadence["day"] == 0
    assert lead.cadence["next_send_at"] == E1_AT and lead.cadence["armed_for_email_id"] == "in-1"
    assert lead.status == "replied_awaiting_booking" and cadence.is_armed(lead)
    assert A._is_first_reply(lead) is False
    # the caller's copy is what was written
    assert state.cadence == lead.cadence and state.history == lead.history
    # its own Job_Log row, and nothing was sent
    logged = [d for j, s, d in env["rows"] if (j, s) == ("reply_engine.cadence", "first_reply_from_thread")]
    assert len(logged) == 1 and logged[0]["cadence_armed"] is True and logged[0]["sent_at"] == SENT_AT.isoformat()
    assert inst.sent == []
    # the card still reads pending (approval.py retires it, not this), but it
    # answers nothing any more, so it never stops the ladder its reply started
    assert A._approval_row(store, _card_id(card)).status == "pending"
    assert cadence.open_cards(lead, store, TICK) == []
    assert cadence.changed_in_store(lead, store, TICK) is None
    # and a second check finds nothing more to do: no second read, no second arm
    again = cadence.detect_manual_first_reply(lead, TICK + timedelta(hours=1), inst, store)
    assert again["action"] == "not_candidate" and again["reason"] == "reply_recorded" and len(inst.reads) == 1


def test_an_outbound_before_the_reply_one_in_another_thread_and_an_inbound_are_not_his_reply(env):
    store = env["store"]
    state, card = _seed(store)
    rows = [_row("cold-1", REPLY_AT - timedelta(days=3)),                 # the cold email, before the reply
            _row("other-1", SENT_AT, thread="thread-someone-else"),       # his reply to another lead
            _row("in-2", SENT_AT, outbound=False)]                         # the lead writing again
    before = store.get(state.key)
    res = cadence.detect_manual_first_reply(state, TICK, ThreadInstantly(rows), store)
    assert res["action"] == "no_reply_found" and res["rows_read"] == 3
    assert store.get(state.key) == before and not cadence.is_armed(_lead(store, state))


def test_nothing_happens_once_a_reply_is_recorded_even_when_mark_sent_lands_during_the_read(env):
    store = env["store"]
    state, card = _seed(store)
    # (a) already on the history when the tick reads the row: not even a read
    done = cadence.state_from_dict(store.get(state.key))
    done.history.append({"at": TICK.isoformat(), "event": "reply_sent", "approval": _card_id(card)})
    inst = ThreadInstantly([_row("out-1", SENT_AT)])
    res = cadence.detect_manual_first_reply(done, TICK, inst, store)
    assert (res["action"], res["reason"]) == ("not_candidate", "reply_recorded") and inst.reads == []

    # (b) the card's Mark sent writes its event while the thread is being read:
    # the locked write sees it and records nothing, so the ladder is armed once
    marked = {"at": TICK.isoformat(), "event": "reply_sent_manually", "approval": _card_id(card), "by": "lorenzo"}

    def _mark_sent_meanwhile():
        row = store.get(state.key)
        row["history"] = list(row["history"]) + [marked]
        store.set(state.key, row)

    inst = ThreadInstantly([_row("out-1", SENT_AT)], on_read=_mark_sent_meanwhile)
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert (res["action"], res["reason"]) == ("already_recorded", "reply_already_recorded")
    lead = _lead(store, state)
    assert [e for e in lead.history if e.get("event") in A.REPLY_SENT_EVENTS] == [marked]
    assert not lead.cadence.get("armed_at") and lead.last_outbound_at is None


def test_a_dry_run_reads_the_thread_and_reports_but_writes_nothing(env):
    store = env["store"]
    state, card = _seed(store)
    nurture.enroll(LEAD, "not_now_reply", REPLY_AT - timedelta(days=30), store)
    before = {k: store.get(k) for k in store.keys()}
    res = cadence.detect_manual_first_reply(state, TICK, ThreadInstantly([_row("out-1", SENT_AT)]), store,
                                            dry_run=True)
    assert res["action"] == "ladder_would_start" and res["next_send_at"] == E1_AT
    assert res["would_leave_nurture"] is True
    assert {k: store.get(k) for k in store.keys()} == before
    assert [r for r in env["rows"] if r[0] == "reply_engine.cadence"] == []


def test_an_enrolled_lead_leaves_the_nurture_as_re_engaged(env):
    store = env["store"]
    state, card = _seed(store)
    nurture.enroll(LEAD, "not_now_reply", REPLY_AT - timedelta(days=30), store)
    res = cadence.detect_manual_first_reply(state, TICK, ThreadInstantly([_row("out-1", SENT_AT)]), store)
    assert res["action"] == "ladder_started" and res["left_nurture"] is True
    rec = nurture.get(LEAD, store)
    assert rec["status"] == "left" and rec["left_reason"] == "re_engaged" and not nurture.is_enrolled(LEAD, store)
    # so the tick does not stop the fresh ladder as "nurture" on Monday
    monday = ct(2030, 1, 14, 10, 5)
    lead = _lead(store, state)
    out = cadence.tick_lead(lead, monday, store=store, dry_run=True, free_slots=cadence.default_slot_grid(monday))
    assert out.get("reason") != "nurture" and out["action"] == "would_send" and out["day"] == 1


# ============================================================ through the tick
def test_one_hourly_tick_starts_the_ladder_counts_it_and_e1_goes_out_on_monday(env):
    store = env["store"]
    state, card = _seed(store)
    inst = ThreadInstantly([_row("out-1", SENT_AT)])
    notify.reset_for_tests()
    summary = cadence_tick.run(TICK, store, instantly=inst, free_slots=cadence.default_slot_grid(TICK))
    assert summary["first_reply_candidates"] == 1 and summary["first_reply_counts"] == {"ladder_started": 1}
    assert summary["ladders_started"] == 1 and summary["problems"] == 0
    assert summary["digest"] == ["1 ladder started after your reply"]
    assert len(notify.sent_in_test) == 1 and notify.sent_in_test[0]["message"] == "1 ladder started after your reply"
    assert LEAD not in notify.sent_in_test[0]["message"]
    assert store.get(cadence_tick.lock_key(state.key)) is None       # the claim was released
    # the next tick: an armed ladder now, no second read, nothing due before Monday
    summary = cadence_tick.run(TICK + timedelta(hours=1), store, instantly=inst)
    assert summary["first_reply_candidates"] == 0 and len(inst.reads) == 1
    assert summary["counts"] == {"not_due": 1}
    # Monday 10:05: E1 goes out (a would_do in shadow); the pending card does not stop it
    monday = ct(2030, 1, 14, 10, 5)
    summary = cadence_tick.run(monday, store, instantly=inst, free_slots=cadence.default_slot_grid(monday))
    assert summary["counts"] == {"would_send": 1}
    assert [(r["action"], r["day"]) for r in summary["results"]] == [("would_send", 1)]


def test_an_instantly_error_is_counted_never_raised_and_the_next_tick_retries(env):
    store = env["store"]
    state, card = _seed(store)
    before = store.get(state.key)
    inst = ThreadInstantly([_row("out-1", SENT_AT)], error=InstantlyError("Instantly GET /emails -> HTTP 429"))
    summary = cadence_tick.run(TICK, store, instantly=inst)
    assert summary["first_reply_counts"] == {"check_failed": 1} and summary["problems"] == 1
    assert summary["first_reply_results"][0]["reason"] == "instantly_read_failed"
    assert any("thread check for your replies failed" in line for line in summary["digest"])
    assert store.get(state.key) == before
    inst.error = None
    summary = cadence_tick.run(TICK + timedelta(hours=1), store, instantly=inst)
    assert summary["first_reply_counts"] == {"ladder_started": 1} and summary["problems"] == 0
    assert _lead(store, state).cadence["next_send_at"] == E1_AT
