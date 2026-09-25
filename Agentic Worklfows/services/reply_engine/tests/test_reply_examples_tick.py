"""Lorenzo's reply examples on the hourly tick (reply_examples, 2026-09-25).

* The GET /emails/{id} for his text is a single try (no backoff retries):
  a failing read must not eat the tick's 240 s.
* A failed read is its own result (skipped, read_failed): the lead's day 0
  stays recorded, the tick defers the rest of its thread checks, and a read
  that was made counts toward FIRST_REPLY_MAX_READS.
* The first_reply_from_thread Job_Log row and the tick summary carry the
  example's outcome.
* A card with no lead_reply takes the lead's message from the thread rows
  already read, never from one of our own rows.

Shadow only, every client a fake, every clock fixed, every lead fictional.
"""
from datetime import timedelta
from types import SimpleNamespace

import httpx

from shared.instantly import Instantly, InstantlyError

from jobs import cadence_tick
from services.reply_engine import cadence
from services.reply_engine import reply_examples as RX
from services.reply_engine.tests.test_day0_detection import (  # noqa: F401 - env is a fixture
    EACCOUNT, LEAD, REPLY_AT, SENT_AT, THREAD, TICK, ThreadInstantly, _row, _seed, env)


class ByIdInstantly(ThreadInstantly):
    """ThreadInstantly plus a GET /emails/{id} that records its ``retry``
    kwarg and answers ``text``, or raises ``get_error``."""

    def __init__(self, rows=None, text="Hey Jordan, Monday at 1pm works on my side.", get_error=None):
        super(ByIdInstantly, self).__init__(rows)
        self.text = text
        self.get_error = get_error
        self.gets = []

    def get_email(self, email_id, retry=None):
        self.gets.append((email_id, retry))
        if self.get_error is not None:
            raise self.get_error
        return {"id": email_id, "body": {"text": self.text}}


def _rows_of(env, status):
    return [d for job, s, d in env["rows"] if job == "reply_engine.cadence" and s == status]


# ======================================================== A: a single try
def test_the_client_passes_retry_through_to_the_request():
    """Instantly.get_email(id, retry=False) is one attempt; the default keeps
    a read's retries."""
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503, json={"error": "down"})

    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    try:
        client.get_email("e-1", retry=False)
    except InstantlyError:
        pass
    assert len(calls) == 1 and calls[0].endswith("/emails/e-1")
    del calls[:]
    try:
        client.get_email("e-1")
    except InstantlyError:
        pass
    assert len(calls) == 4     # the first try and MAX_RETRIES retries


def test_the_tick_reads_his_text_with_a_single_try(env):
    store = env["store"]
    state, card = _seed(store)
    inst = ByIdInstantly([_row("out-1", SENT_AT)])
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert res["action"] == "ladder_started" and res["example"] == "recorded" and res["example_read"] == "ok"
    assert inst.gets == [("out-1", False)]
    assert store.get(RX.key_for("out-1"))["reply"] == "Hey Jordan, Monday at 1pm works on my side."


def test_a_fake_without_retry_is_called_with_the_id_alone():
    got = []
    fake = SimpleNamespace(get_email=lambda email_id: got.append(email_id) or {"text": "Monday works."})
    assert RX.read_text(fake, {"id": "e-1"}, single_try=True) == ("Monday works.", "ok")
    assert got == ["e-1"]


def test_no_read_is_made_when_the_row_carries_his_text():
    fake = SimpleNamespace(get_email=lambda email_id, retry=None: 1 / 0)
    assert RX.read_text(fake, {"id": "e-1", "text": "Monday works."}, single_try=True) == ("Monday works.", None)


# =============================================== B: a failed read on the tick
def test_a_failing_read_is_read_failed_and_the_ladder_still_starts(env):
    store = env["store"]
    state, card = _seed(store)
    inst = ByIdInstantly([_row("out-1", SENT_AT)], get_error=InstantlyError("Instantly GET /emails/out-1 -> 503"))
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert res["action"] == "ladder_started" and res["example"] == "skipped" and res["example_read"] == "failed"
    assert inst.gets == [("out-1", False)] and store.keys(RX.PREFIX) == []
    assert cadence.is_armed(cadence.state_from_dict(store.get(state.key)))
    # C: the Job_Log row of the find says what happened to the example
    logged = _rows_of(env, "first_reply_from_thread")
    assert len(logged) == 1
    assert logged[0]["example"] == "skipped" and logged[0]["example_reason"] == "read_failed"
    assert logged[0]["cadence_armed"] is True


def test_the_job_log_row_carries_a_recorded_example(env):
    store = env["store"]
    state, card = _seed(store)
    res = cadence.detect_manual_first_reply(state, TICK, ByIdInstantly([_row("out-1", SENT_AT)]), store)
    assert res["example"] == "recorded"
    logged = _rows_of(env, "first_reply_from_thread")
    assert logged[0]["example"] == "recorded" and logged[0]["example_reason"] is None


def _two_leads(store):
    """The first lead (newest reply, checked first) and a second one."""
    state, card = _seed(store)
    other, _ = _seed(store, lead="second@example.com", thread="thread-day0-2",
                     reply_at=REPLY_AT - timedelta(minutes=30), card_at=REPLY_AT - timedelta(minutes=25),
                     slots=["2030-01-14T15:00:00-06:00", "2030-01-15T16:00:00-06:00"])
    return state, other


def test_a_failed_read_defers_the_next_candidate(env):
    store = env["store"]
    state, other = _two_leads(store)
    inst = ByIdInstantly([_row("out-1", SENT_AT), _row("out-2", SENT_AT, thread="thread-day0-2",
                                                        lead="second@example.com")],
                         get_error=InstantlyError("Instantly GET /emails/out-1 -> 503"))
    logged = []
    summary = cadence_tick.run(TICK, store, instantly=inst, log_fn=lambda job, status, d: logged.append(d))
    # the first lead's day 0 is recorded; the second waits for the next tick
    assert summary["first_reply_counts"] == {"ladder_started": 1, "deferred": 1}
    deferred = [r for r in summary["first_reply_results"] if r["action"] == "deferred"]
    assert deferred[0]["lead_email"] == "second@example.com" and deferred[0]["reason"] == "after_read_failure"
    assert len(inst.reads) == 1 and inst.gets == [("out-1", False)]
    # C: per-outcome counts in the summary and its Job_Log row
    counts = {"recorded": 0, "duplicate": 0, "skipped": 1, "failed": 0}
    assert summary["first_reply_examples"] == counts and logged[0]["first_reply_examples"] == counts
    assert not cadence.is_armed(cadence.state_from_dict(store.get(other.key)))


def test_a_read_for_his_text_counts_toward_the_read_cap(env, monkeypatch):
    store = env["store"]
    state, other = _two_leads(store)
    monkeypatch.setattr(cadence, "FIRST_REPLY_MAX_READS", 2)
    inst = ByIdInstantly([_row("out-1", SENT_AT), _row("out-2", SENT_AT, thread="thread-day0-2",
                                                        lead="second@example.com")])
    summary = cadence_tick.run(TICK, store, instantly=inst)
    # the list read and the GET /emails/{id} of the first lead reach the cap
    assert summary["first_reply_counts"] == {"ladder_started": 1, "deferred": 1}
    assert [r.get("reason") for r in summary["first_reply_results"] if r["action"] == "deferred"] == ["read_cap"]
    assert summary["first_reply_examples"] == {"recorded": 1, "duplicate": 0, "skipped": 0, "failed": 0}


def test_no_extra_read_is_counted_when_the_row_has_his_text(env, monkeypatch):
    store = env["store"]
    _two_leads(store)
    monkeypatch.setattr(cadence, "FIRST_REPLY_MAX_READS", 2)
    his = dict(_row("out-1", SENT_AT), body={"text": "Hey Jordan, Monday at 1pm?"})
    inst = ByIdInstantly([his])
    summary = cadence_tick.run(TICK, store, instantly=inst)
    # one list read each; the second lead's thread holds no reply of his
    assert summary["first_reply_counts"] == {"ladder_started": 1, "no_reply_found": 1}
    assert inst.gets == [] and len(inst.reads) == 2
    assert summary["first_reply_examples"] == {"recorded": 1, "duplicate": 0, "skipped": 0, "failed": 0}


def test_only_results_with_an_example_step_are_counted(env):
    store = env["store"]
    _seed(store)
    summary = cadence_tick.run(TICK, store, instantly=ByIdInstantly([]))
    assert summary["first_reply_counts"] == {"no_reply_found": 1}
    assert summary["first_reply_examples"] == {"recorded": 0, "duplicate": 0, "skipped": 0, "failed": 0}


# ======================================= D: the lead's message from the thread
HIS = {"email_id": "out-1", "sent_at": SENT_AT}


def _state():
    return SimpleNamespace(lead_email=LEAD, thread_id=THREAD, eaccount=EACCOUNT, campaign_id=None, history=[])


def _card(email_id="in-1", lead_reply=None):
    return SimpleNamespace(email_id=email_id, lead_reply=lead_reply, label="positive_interested", draft=None)


def _lead_row(email_id, when, text, **extra):
    return dict(_row(email_id, when, outbound=False), body={"text": text}, **extra)


def _capture(store, card, rows):
    his = dict(_row("out-1", SENT_AT), body={"text": "Hey Jordan, Monday at 1pm?"})
    return RX.capture_first_reply(store, _state(), card, HIS, his, {}, now=TICK, instantly=None,
                                  thread_rows=[his] + list(rows))


def test_an_empty_lead_reply_is_taken_from_the_row_with_the_cards_id(env):
    store = env["store"]
    rows = [_lead_row("in-1", REPLY_AT, "Sounds good, tell me more."),
            _lead_row("in-0", REPLY_AT + timedelta(minutes=5), "Also, what does it cost?")]
    assert _capture(store, _card("in-1"), rows)["example"] == "recorded"
    ex = store.get(RX.key_for("out-1"))
    assert ex["lead_message"] == "Sounds good, tell me more." and ex["lead_message_id"] == "in-1"
    assert ex["lead_message_at"] == REPLY_AT.isoformat()


def test_else_the_newest_lead_row_before_his_reply(env):
    store = env["store"]
    rows = [_lead_row("in-a", REPLY_AT - timedelta(hours=1), "Who is this?"),
            _lead_row("in-b", REPLY_AT, "Sounds good, tell me more."),
            # an auto-reply, a message after his reply and another thread are never taken
            _lead_row("ooo", REPLY_AT + timedelta(minutes=10), "I am away until Monday.",
                      subject="Automatic reply: Jordan, question"),
            _lead_row("in-late", SENT_AT + timedelta(minutes=5), "Monday is fine."),
            _lead_row("in-other", REPLY_AT + timedelta(minutes=20), "Other thread.", thread_id="thread-x")]
    assert _capture(store, _card(email_id=None), rows)["example"] == "recorded"
    ex = store.get(RX.key_for("out-1"))
    assert ex["lead_message"] == "Sounds good, tell me more." and ex["lead_message_id"] == "in-b"
    assert ex["lead_message_at"] == REPLY_AT.isoformat()


def test_the_cards_own_lead_reply_wins(env):
    store = env["store"]
    rows = [_lead_row("in-1", REPLY_AT, "From the thread.")]
    _capture(store, _card("in-1", lead_reply="From the card."), rows)
    assert store.get(RX.key_for("out-1"))["lead_message"] == "From the card."


def test_no_fallback_picks_one_of_our_own_rows(env):
    store = env["store"]
    before = REPLY_AT
    rows = [
        dict(_row("in-1", before), body={"text": "ours by hand"}),                            # ue_type 3, the card's id
        dict(_row("step-1", before, ue_type=1), body={"text": "a campaign step"}),
        dict(_row("sched", before, ue_type=4), body={"text": "a scheduled send"}),
        # the lead's flag with our sender is contradictory: not taken
        dict(_row("odd", before, ue_type=2), from_address_email=EACCOUNT, body={"text": "odd"}),
        # no ue_type: from our inbox, or to the lead with no sender
        {"id": "nf-1", "thread_id": THREAD, "eaccount": EACCOUNT, "from_address_email": EACCOUNT,
         "timestamp_created": "2030-01-11T19:00:00.000Z", "text": "ours, no flag"},
        {"id": "nf-2", "thread_id": THREAD, "eaccount": EACCOUNT, "to_address_email_list": LEAD,
         "timestamp_created": "2030-01-11T19:00:00.000Z", "text": "ours, no sender"},
    ]
    assert _capture(store, _card("in-1"), rows)["example"] == "recorded"
    ex = store.get(RX.key_for("out-1"))
    assert ex["lead_message"] is None and ex["lead_message_id"] == "in-1"


def test_a_row_with_no_flag_and_no_sender_addressed_to_our_inbox_is_the_leads(env):
    """The recorded September list's shape: no ue_type, no sender."""
    store = env["store"]
    rows = [{"id": "in-9", "thread_id": THREAD, "eaccount": EACCOUNT, "to_address_email_list": EACCOUNT,
             "timestamp_created": "2030-01-11T20:00:00.000Z", "text": "Sounds good."}]
    _capture(store, _card(email_id=None), rows)
    assert store.get(RX.key_for("out-1"))["lead_message"] == "Sounds good."


def test_no_lead_rows_in_the_list_leaves_the_lead_message_empty(env):
    store = env["store"]
    _capture(store, _card("in-1"), [])
    assert store.get(RX.key_for("out-1"))["lead_message"] is None


def test_the_tick_takes_the_lead_message_from_the_thread_when_the_card_has_none(env):
    """End to end: an older card without lead_reply; the manual list read by
    the thread check carries the lead's row (ue_type 2)."""
    from services.reply_engine import approval as A

    store = env["store"]
    state, card = _seed(store)
    key = A.APPROVAL_PREFIX + card.token.split(".", 1)[0]
    raw = store.get(key)
    raw["lead_reply"] = None
    store.set(key, raw)
    his = dict(_row("out-1", SENT_AT), body={"text": "Hey Jordan, Monday at 1pm?"})
    lead = _lead_row("in-1", REPLY_AT, "Sounds good, tell me more.")
    inst = ByIdInstantly([his, lead])
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert res["action"] == "ladder_started" and res["example"] == "recorded"
    assert res["example_read"] is None and inst.gets == [] and len(inst.reads) == 1
    ex = store.get(RX.key_for("out-1"))
    assert ex["lead_message"] == "Sounds good, tell me more." and ex["lead_message_id"] == "in-1"
