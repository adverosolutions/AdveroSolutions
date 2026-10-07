"""Re-review fix plan, slice 2 "S-rest": the remaining reply-engine findings
(runbooks/REREVIEW_2026-09-22.md, SAL-4..SAL-11 and OPS-10's approval half)
plus the round-4, round-5 and round-6 reviewer follow-ups, as regression tests.

1a. The auto-reply pause's baseline moves with the stop group in the merge.
1b. A D1 that an out-of-office pause moved gets a fresh 30-minute veto window
    (the reviewer's probe, scratchpad/review-s/test_r6_d1_veto_after_ooo.py).
1c. An auto-reply after the human reply never overwrites a final status.
1d. The auto-reply marker is the FIRST history entry for its email id.
1e. The "awaiting fresh draft" line only promises an answer when a card is open.
SAL-5  The SLA chase never writes back a stale card (sent stays sent).
SAL-6  Every open card expires at its TTL; a card holding a call writes
       nothing to GHL, pushes one Keep / Release question, and stays unsendable
       until Lorenzo decides.
SAL-9  Every engine-initiated cancel passes to_notify=False.
SAL-10 Slot reservations are claimed atomically across leads.
SAL-11 The cross-offer check covers percentages.
R4     A kept hold keeps its slot reservation; Book-as-asked refuses while a
       cancel is pending.
R5     The arm check covers the card whose own email is not processed yet.
OPS-10 The reply time and the send time are recorded, and the metric reads them.

SAL-4 (a tick erasing a reply's stop) is covered by
test_cadence_tick_stale_write.py. Every client is an in-process fake; live mode
is set in-process only.
"""
import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from shared import job_log, notify
from shared.job_log import job_log_path, read_shadow_log
from shared.store import JsonFileStore

from services.metrics import sources
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import booking as booking_mod
from services.reply_engine import cadence
from services.reply_engine import draft as draft_mod
from services.reply_engine import router as router_mod
from services.reply_engine import show_rate
from services.reply_engine.models import Classification, Draft, Extracted, LeadState, ReplyEvent

from test_approval_sla_escalation import card as sla_card
from test_cadence_engine import make_state
from test_send_safety_round2 import (  # noqa: F401 - shared fakes and worlds
    APPT, CAMPAIGN, FRI, LOCKED_IN, OTHER_TIMES, SOPIO, THU_3PM, FakeInstantly, Recorder, _alerts, _card, _go_live,
    _owner_card, _save_card, _world, ct,
)
from test_send_safety_round5 import (  # noqa: F401 - the tiff fixture and the Tiffany world
    LADDER_SLOTS, TIFF, _first_card, _reply, _ticks, tiff,
)

# These tests cover the E1 Veto window, switched off on 2026-10-06 (cadence.E1_VETO).
pytestmark = pytest.mark.usefixtures("e1_veto_on")

OOO_TEXT = "I am out of the office until September 23 with limited access to email."
OOO_SUBJECT = "Automatic reply: Tiffany, question"


# ======================================================== 1a. the stop group
def test_1a_the_auto_reply_baseline_moves_with_the_stop_group():
    for key in ("resumed_after_auto_reply_at", "auto_reply_seen_through", "auto_reply_seen_email_id"):
        assert key in A.STOP_STATE_KEYS
    # the tick resumed the pause in the store; a writer holding the paused copy
    # changed the baseline too. Its baseline must not be paired with the
    # store's un-stop: the whole group comes from the store.
    base = {"cadence": {"armed_at": "T0", "stopped_reason": "inbound_reply", "next_send_at": None,
                        "resumed_after_auto_reply_at": None, "auto_reply_seen_through": None,
                        "auto_reply_seen_email_id": None}}
    current = {"cadence": {"armed_at": "T0", "stopped_reason": None, "next_send_at": "N2",
                           "resumed_after_auto_reply_at": "R2", "auto_reply_seen_through": "S2",
                           "auto_reply_seen_email_id": "ooo-2"}}
    mine = {"cadence": {"armed_at": "T0", "stopped_reason": "inbound_reply", "next_send_at": None,
                        "resumed_after_auto_reply_at": "R1", "auto_reply_seen_through": "S1",
                        "auto_reply_seen_email_id": "ooo-1"}}
    assert A.merge_stale_write(base, mine, current)["cadence"] == current["cadence"]


# ============================================ 1b. D1 veto after an OOO pause
def test_1b_a_d1_moved_by_an_ooo_pause_gets_a_fresh_veto_window(tiff, monkeypatch):
    """The reviewer's probe: the D1 veto push went out Tue 09:30, the
    auto-responder stopped D1 at 09:45 and the pause moved it to Wed 10:00. D1
    used to go out Wed 10:00 behind Tuesday's push; now Wed 09:30 re-opens the
    window with a fresh push."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="v-1")
    key = r1["state_key"]
    A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    pings = []
    _, first = _ticks(st, [ct(2026, 9, 22, 9, 30)], LADDER_SLOTS, pings)
    assert first == [[("veto_window_opened", None, 1)]]
    _reply(tiff["deps"], "v-ooo", OOO_TEXT, "2026-09-22T14:45:00Z", ct(2026, 9, 22, 9, 45), subject=OOO_SUBJECT)
    d, res = _ticks(st, [ct(2026, 9, 22, 10, 0), ct(2026, 9, 22, 11, 0), ct(2026, 9, 23, 9, 30),
                         ct(2026, 9, 23, 10, 0)], LADDER_SLOTS, pings)
    assert res[0] == [("resumed_after_auto_reply", None, 1)]
    assert st.get(key)["cadence"].get("veto_notified_at") in (None, ct(2026, 9, 23, 9, 30).isoformat())
    assert res[2] == [("veto_window_opened", None, 1)]          # Wed 09:30: a fresh 30-minute window
    assert res[3] == [("sent", None, 1)] and len(d.sent) == 1   # and only then D1
    d1_pushes = [p for p in pings if "D1" in p]
    assert len(d1_pushes) == 2


def test_1b_resume_after_auto_reply_drops_the_veto_stamp():
    state = cadence.arm(make_state(), ct(2026, 9, 21, 14, 5))
    state.cadence["veto_notified_at"] = ct(2026, 9, 22, 9, 30).isoformat()
    cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 9, 45))
    cadence.resume_after_auto_reply(state, ct(2026, 9, 22, 10, 0))
    assert state.cadence["veto_notified_at"] is None


# ================================ 1c. a final status survives a late auto-reply
def _ooo_event(label_text=OOO_TEXT):
    return ReplyEvent(email_id="late-ooo", lead_email=SOPIO, campaign_id=CAMPAIGN, subject=OOO_SUBJECT,
                      text=label_text, received_at=ct(2026, 9, 22, 11, 0))


@pytest.mark.parametrize("final", ["blocklisted", "lost", "wrong_person", "follow_up_later", "call_booked",
                                   "needs_review", "unsubscribed", "negative_hostile"])
@pytest.mark.parametrize("label", ["ooo", "auto_reply_unmonitored"])
def test_1c_an_auto_reply_after_the_human_reply_keeps_the_final_status(tmp_env, final, label):
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, status=final,
                      cadence={"paused": True, "stopped": True, "reason": "unsubscribe"})
    inst = Recorder()
    cls = Classification(label=label, extracted=Extracted(return_date="2026-09-30"))
    actions = router_mod.route(_ooo_event(), cls, state, None, inst, store=None)
    assert state.status == final
    assert inst.calls == []                                   # no interest reset to 0 over -1 / -2 / 2
    assert state.cadence == {"paused": True, "stopped": True, "reason": "unsubscribe"}
    assert any(a.action == "status_kept" for a in actions)


def test_1c_an_open_lead_still_pauses_on_an_ooo(tmp_env):
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, status="replied_awaiting_booking")
    inst = Recorder()
    router_mod.route(_ooo_event(), Classification(label="ooo", extracted=Extracted(return_date="2026-09-30")),
                     state, None, inst, store=None)
    assert state.status == "ooo" and state.cadence["reason"] == "ooo"
    assert [(c[0], c[1][2]) for c in inst.calls] == [("update_interest_status", 0)]


def test_1c_final_statuses_cover_every_status_the_cadence_stops_for():
    for group in (cadence.BOOKED_STATUSES, cadence.UNSUBSCRIBE_STATUSES, cadence.HOSTILE_STATUSES,
                  cadence.NOT_NOW_STATUSES):
        assert set(group) <= set(router_mod.FINAL_STATUSES)


def test_1c_remove_me_then_an_out_of_office_stays_removed(tiff, monkeypatch):
    st = tiff["store"]
    r = _reply(tiff["deps"], "rm-1", "Please remove me from your list.", "2026-09-21T19:00:00Z", ct(2026, 9, 21, 14, 0))
    decided = st.get(r["state_key"])["status"]
    assert decided in router_mod.FINAL_STATUSES
    interest_before = list(tiff["inst"].interest)
    o = _reply(tiff["deps"], "rm-ooo", OOO_TEXT, "2026-09-21T19:02:00Z", ct(2026, 9, 21, 14, 2), subject=OOO_SUBJECT)
    assert o["label"] == "ooo"
    assert st.get(r["state_key"])["status"] == decided
    assert tiff["inst"].interest == interest_before


# ===================================== 1d. the marker is the FIRST entry
def test_1d_the_auto_reply_marker_is_its_first_history_entry():
    """A retry that processed the auto-reply again appends a second entry for
    it. Measuring from the last one skipped the human reply written between
    the two (stamped before the stock-take: its pipeline started earlier)."""
    seen = ct(2026, 9, 22, 10, 7)
    state = LeadState(lead_email=TIFF, campaign_id="c1", cadence={
        "armed_at": ct(2026, 9, 21, 14, 5).isoformat(), "stopped_reason": "inbound_reply",
        "resumed_after_auto_reply_at": ct(2026, 9, 22, 10, 5).isoformat(),
        "auto_reply_seen_through": seen.isoformat(), "auto_reply_seen_email_id": "ooo-1"},
        history=[{"event": "inbound", "email_id": "ooo-1", "label": "ooo", "at": seen.isoformat()},
                 {"event": "inbound", "email_id": "h-1", "label": "positive_interested",
                  "at": ct(2026, 9, 22, 10, 6).isoformat()},
                 {"event": "inbound", "email_id": "ooo-1", "label": "ooo", "at": ct(2026, 9, 22, 10, 8).isoformat()}])
    assert cadence.human_reply_since_baseline(state) == "h-1"
    assert cadence.is_auto_reply_pause(state) is False


# ============================== 1e. the stall line and an open card
def _stopped_for_a_reply(approvals=()):
    state = cadence.arm(make_state(email=SOPIO, campaign_id=CAMPAIGN), ct(2026, 9, 21, 14, 5))
    cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 9, 0))
    state.approvals = list(approvals)
    return state


def test_1e_a_reply_that_raised_no_card_is_not_said_to_await_an_answer(tmp_env):
    store = JsonFileStore(tmp_env / "stall.json")
    res = cadence.tick_lead(_stopped_for_a_reply(), ct(2026, 9, 22, 10, 5), store=store)
    assert res["action"] == "awaiting_fresh_draft" and res["card_open"] is False
    line = cadence.summarize_touch(res)
    assert "raised no card" in line and "waiting on your approved answer" not in line
    assert "—" not in line and "!" not in line


def test_1e_a_reply_with_an_open_card_is_waiting_on_the_answer(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    store = JsonFileStore(tmp_env / "stall2.json")
    state = _stopped_for_a_reply()
    card = _card(state, "stall-card", OTHER_TIMES, FRI, created=ct(2026, 9, 22, 9, 0))
    _save_card(store, card)
    state.approvals = [card.token]
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 5), store=store)
    assert res["action"] == "awaiting_fresh_draft" and res["card_open"] is True
    assert "waiting on your approved answer" in cadence.summarize_touch(res)


# ====================================================== SAL-5. the chase
def test_sal5_the_chase_never_reverts_a_card_sent_while_it_pushed(tmp_path):
    store = JsonFileStore(tmp_path / "sla.json")
    store.set("approval:a1", sla_card(ct(2026, 9, 22, 10, 0)))

    def push_while_lorenzo_approves(title, message, **kw):
        row = store.get("approval:a1")
        store.set("approval:a1", dict(row, status="sent", decided_at=ct(2026, 9, 22, 10, 10).isoformat()))
        return {"sent": True, "test": True}

    out = A.escalate_pending(store, now=ct(2026, 9, 22, 10, 10), notify_fn=push_while_lorenzo_approves)
    assert len(out) == 1
    row = store.get("approval:a1")
    assert row["status"] == "sent"                                 # never back to pending
    assert row["decided_at"] == ct(2026, 9, 22, 10, 10).isoformat()
    assert row["escalations"] == 1 and row["last_escalated_at"] == ct(2026, 9, 22, 10, 10).isoformat()


class _VetoedAfterTheListing(JsonFileStore):
    """The card is vetoed between escalate_pending's listing and its push."""

    def __init__(self, path):
        JsonFileStore.__init__(self, path)
        self.reads = 0

    def get(self, key, default=None):
        value = JsonFileStore.get(self, key, default)
        if key == "approval:a1":
            self.reads += 1
            if self.reads == 2:
                value = dict(value, status="vetoed")
                JsonFileStore.set(self, key, value)
        return value


def test_sal5_a_card_actioned_before_the_push_is_not_chased(tmp_path):
    store = _VetoedAfterTheListing(tmp_path / "sla2.json")
    JsonFileStore.set(store, "approval:a1", sla_card(ct(2026, 9, 22, 10, 0)))
    pushes = []
    out = A.escalate_pending(store, now=ct(2026, 9, 22, 10, 10),
                             notify_fn=lambda *a, **k: pushes.append(a) or {"sent": True, "test": True})
    assert out == [] and pushes == []
    row = JsonFileStore.get(store, "approval:a1")
    assert row["status"] == "vetoed" and int(row.get("escalations") or 0) == 0


# ====================================================== SAL-6. expiry
def _plain_state(store):
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, first_name="Sopio")
    store.set(state.key, state.to_store())
    return state


# send_failed left this list in re-review R1 (item 2): a card whose send may
# have reached Instantly stays with retry() (test_send_safety_srest_r2_expiry).
@pytest.mark.parametrize("status", ["pending", "blocked", "stale_slots"])
def test_sal6_an_open_card_past_its_ttl_is_expired_by_the_poller_tick(tmp_env, monkeypatch, status):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "exp.json")
    state = _plain_state(store)
    card = _card(state, "plain", OTHER_TIMES, FRI, status=status)       # created Mon 18:20, TTL Wed 18:20
    _save_card(store, card)
    A.reserve_slots(store, SOPIO, FRI, "plain", ct(2026, 9, 21, 18, 20))
    ghl = Recorder()
    A.flush_queued(FakeInstantly(sender=SOPIO), store=store, now=ct(2026, 9, 23, 18, 0), ghl=ghl)
    assert A.load(card.token, store).status == status                   # inside its TTL: untouched
    A.flush_queued(FakeInstantly(sender=SOPIO), store=store, now=ct(2026, 9, 23, 20, 0), ghl=ghl)  # after hours
    assert A.load(card.token, store).status == "expired"
    assert ghl.calls == [] and not set(FRI) & set(A.offered_slots(store, ct(2026, 9, 23, 20, 0)))
    assert _alerts("Card expired") == []                                 # it held no call


def test_sal6_an_owner_card_past_its_ttl_holds_the_call_and_asks_once(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    ghl = Recorder()
    inst = FakeInstantly(sender=SOPIO)
    for minute in (30, 35, 40):
        A.flush_queued(inst, store=store, now=ct(2026, 9, 23, 18, minute), ghl=ghl)
    assert ghl.calls == [] and inst.sent == [] and inst.interest == []   # no automatic GHL write, nothing sent
    pushes = _alerts("Card expired with a call still booked")
    assert len(pushes) == 1 and pushes[0]["priority"] == "high"
    assert APPT in pushes[0]["message"] and "Thu Sep 24 3:00pm CT" in pushes[0]["message"]
    assert "Keep the call" in str(pushes[0]["actions"]) and "Release the call" in str(pushes[0]["actions"])
    assert "—" not in pushes[0]["message"]
    raw = store.get(state.key)
    assert raw["cadence"]["booking"]["owner"] == "card2" and raw["cadence"]["booking"]["appointment_id"] == APPT
    assert show_rate.is_held(store, APPT)
    assert THU_3PM in A.offered_slots(store, ct(2026, 9, 23, 18, 40))   # the call's time stays reserved
    assert A.load(card.token, store).status == "expired"
    out = A.approve(card.token, inst, store=store, now=ct(2026, 9, 23, 18, 45), ghl=ghl)
    assert out["ok"] is False and out["error"] == "already expired" and inst.sent == []
    # a newer reply settles it like any retired owner's booking
    assert A.orphaned_booking_owner(store, LeadState.from_store(raw)) == "card2"


def test_sal6_release_cancels_the_call_silently(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    A.flush_queued(FakeInstantly(sender=SOPIO), store=store, now=ct(2026, 9, 23, 18, 30), ghl=Recorder())
    ghl = Recorder()
    out = A.decide_expired_booking(card.token, "release", ghl=ghl, instantly=FakeInstantly(sender=SOPIO),
                                   store=store, now=ct(2026, 9, 23, 18, 45))
    assert out["ok"] is True and out["choice"] == "release"
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"),
                                                                               {"to_notify": False})]
    raw = store.get(state.key)
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"]["reason"] == "released_after_expiry"
    assert A.load(card.token, store).status == "expired"
    again = A.decide_expired_booking(card.token, "keep", ghl=ghl, store=store, now=ct(2026, 9, 23, 18, 50))
    assert again["ok"] is False                                       # nothing left to decide


def test_sal6_keep_reopens_the_card_and_nothing_goes_out_until_approved(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    A.flush_queued(inst, store=store, now=ct(2026, 9, 23, 18, 30), ghl=Recorder())
    ghl = Recorder()
    kept = A.decide_expired_booking(card.token, "keep", ghl=ghl, instantly=inst, store=store,
                                    now=ct(2026, 9, 23, 18, 35))
    assert kept["ok"] is True and kept["status"] == "pending" and kept["token"] != card.token
    assert ghl.calls == [] and inst.sent == []
    assert kept["expires_at"] == ct(2026, 9, 25, 18, 35).isoformat()
    assert store.get(state.key)["cadence"]["booking"]["owner"] == "card2"
    assert A.load(card.token, store) is None                          # the old link is dead
    sent = A.approve(kept["token"], inst, store=store, now=ct(2026, 9, 23, 18, 40), ghl=ghl)
    assert sent["ok"] is True and len(inst.sent) == 1 and "locked in for Thu 3:00pm" in inst.sent[0]["body"]
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "confirmed"),
                                                                               {"to_notify": True})]


def test_sal6_a_call_that_has_passed_offers_only_release(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    A.flush_queued(FakeInstantly(sender=SOPIO), store=store, now=ct(2026, 9, 24, 16, 0), ghl=Recorder())
    push = _alerts("Card expired with a call still booked")[0]
    assert "has passed" in push["message"]
    assert "Keep the call" not in str(push["actions"]) and "Release the call" in str(push["actions"])
    ghl = Recorder()
    kept = A.decide_expired_booking(card.token, "keep", ghl=ghl, store=store, now=ct(2026, 9, 24, 16, 5))
    assert kept["ok"] is False and "has passed" in kept["error"] and ghl.calls == []


def test_sal6_the_keep_and_release_pages_confirm_before_acting(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    A.flush_queued(FakeInstantly(sender=SOPIO), store=store, now=ct(2026, 9, 23, 18, 30), ghl=Recorder())
    ghl = Recorder()
    app_mod.configure(store=store, ghl=ghl, instantly=FakeInstantly(sender=SOPIO),
                      clock=lambda: ct(2026, 9, 23, 18, 45))
    try:
        client = TestClient(app_mod.app)
        for choice in ("keep", "release"):
            page = client.get("/expired/%s/%s" % (card.token, choice))
            assert page.status_code == 200 and "<form method='post'" in page.text
        assert ghl.calls == [] and A.load(card.token, store).status == "expired"   # GET changes nothing
        done = client.post("/expired/%s/release" % card.token)
        assert done.status_code == 200 and "Call released" in done.text
        assert client.post("/expired/%s/keep" % card.token).status_code == 400
        assert client.get("/expired/%s/maybe" % card.token).status_code == 400
    finally:
        app_mod.configure()
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"),
                                                                               {"to_notify": False})]


# ============================================= SAL-9. every cancel is silent
def test_sal9_every_engine_cancel_passes_to_notify_false(tmp_env, monkeypatch):
    def silent(ghl):
        calls = ghl.named("update_appointment_status")
        assert calls and all(c[1][1] == "cancelled" and c[2] == {"to_notify": False} for c in calls), calls

    # approval.cancel_booking (veto, release on edit, passed before approval,
    # superseded, released after expiry all go through it), awaiting or confirmed
    for awaiting in (True, False):
        store, state = _world(tmp_env, monkeypatch, name="s9-%s.json" % awaiting)
        state.cadence["booking"]["awaiting_approval"] = awaiting
        _go_live(monkeypatch)
        ghl = Recorder()
        A.cancel_booking(state, ghl, None, ct(2026, 9, 21, 17, 0), store=store)
        silent(ghl)
    # veto of the card that owns the booking
    store, state = _world(tmp_env, monkeypatch, name="s9-veto.json")
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    ghl = Recorder()
    A.veto(card.token, store=store, now=ct(2026, 9, 21, 19, 0), ghl=ghl, instantly=FakeInstantly(sender=SOPIO))
    silent(ghl)
    # the cancel retry, for a row queued before the flag was written (to_notify None)
    store, state = _world(tmp_env, monkeypatch, name="s9-retry.json")
    state.cadence["booking"]["cancel_failed"] = {"attempts": 1}
    store.set(state.key, state.to_store())
    store.set(A.CANCEL_RETRY_PREFIX + state.key, {"state_key": state.key, "lead": SOPIO, "appointment_id": APPT,
                                                  "to_notify": None, "attempts": 1, "reason": "vetoed",
                                                  "last_at": ct(2026, 9, 21, 17, 0).isoformat()})
    ghl = Recorder()
    A.retry_failed_cancels(store, ghl, None, ct(2026, 9, 21, 17, 5))
    silent(ghl)
    # the guarded shadow write (the cadence's D6 calendar hold is gone with the E1..E10 ladder)
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    A._cancel_appointment({"appointment_id": "appt-shadow", "slot": THU_3PM}, None, None)
    shadow = [r for r in read_shadow_log() if r["action"] == "update_appointment_status"]
    assert [r["payload"].get("toNotify") for r in shadow] == [False]
    # booking.book's reschedule of an existing call
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, first_name="Sopio", ghl_contact_id="contact-1",
                      cadence={"booking": {"slot": THU_3PM, "appointment_id": "old-appt", "awaiting_approval": False}})
    ghl = Recorder()
    booking_mod.book(state, FRI[1], ghl, FakeInstantly(sender=SOPIO), now=ct(2026, 9, 22, 10, 0), free_slots=[FRI[1]])
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [(("old-appt", "cancelled"),
                                                                               {"to_notify": False})]


# ============================================= SAL-10. atomic reservations
def test_sal10_claim_slots_is_all_or_nothing_per_lead(tmp_env):
    store = JsonFileStore(tmp_env / "claim.json")
    now = ct(2026, 9, 22, 10, 0)
    assert A.claim_slots(store, "a@x.com", FRI, now, fields={"approval": "ca"}) == []
    assert A.claim_slots(store, "a@x.com", FRI, now, fields={"approval": "ca"}) == []     # a replay adds nothing
    assert len(store.get(A.OFFERED_KEY)) == 2
    both = FRI + ["2026-09-28T13:00:00-05:00"]
    assert A.claim_slots(store, "b@x.com", both, now, fields={"approval": "cb"}) == FRI
    assert [r["lead"] for r in store.get(A.OFFERED_KEY)] == ["a@x.com", "a@x.com"]         # nothing of b's
    # a time already in the past is no conflict
    past = ct(2026, 9, 21, 13, 0).isoformat()
    A.claim_slots(store, "a@x.com", [past], ct(2026, 9, 21, 9, 0), fields={"approval": "old"})
    assert A.claim_slots(store, "b@x.com", [past], now, fields={"approval": "cb"}) == []


def test_sal10_two_leads_racing_for_the_same_times_one_wins(tmp_env):
    for round_no in range(8):
        store = JsonFileStore(tmp_env / ("race-%d.json" % round_no))
        now = ct(2026, 9, 22, 10, 0)
        gate = threading.Barrier(2)
        results = {}

        def claim(lead):
            gate.wait()
            results[lead] = A.claim_slots(store, lead, FRI, now, fields={"approval": "card-" + lead})

        threads = [threading.Thread(target=claim, args=(lead,)) for lead in ("a@x.com", "b@x.com")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        winners = [lead for lead, taken in results.items() if taken == []]
        assert len(winners) == 1 and sorted(results[[l for l in results if l not in winners][0]]) == sorted(FRI)
        assert {r["lead"] for r in store.get(A.OFFERED_KEY)} == set(winners)


def _event_for(lead, email_id):
    return ReplyEvent(email_id=email_id, lead_email=lead, campaign_id=CAMPAIGN, subject="Re: x",
                      text="Sounds good, what times do you have?", received_at=ct(2026, 9, 22, 9, 58))


def test_sal10_two_cards_drafted_from_the_same_read_never_offer_the_same_time(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "cards.json")
    now = ct(2026, 9, 22, 10, 0)
    cards = {}
    for lead, eid in (("a@x.com", "ea"), ("b@x.com", "eb")):
        state = LeadState(lead_email=lead, campaign_id=CAMPAIGN)
        draft = Draft(subject="Re: x", body_text=OTHER_TIMES, offered_slots=list(FRI))   # both picked from one read
        cards[lead] = A.create_approval(state, draft, _event_for(lead, eid), store=store, now=now)
    assert cards["a@x.com"].draft.problems == []
    assert any("already held for another lead" in p for p in cards["b@x.com"].draft.problems)
    assert {r["lead"] for r in store.get(A.OFFERED_KEY) if r["slot"] in FRI} == {"a@x.com"}
    blocked = A.send_approved(cards["b@x.com"], FakeInstantly(sender="b@x.com"), store=store, now=now)
    assert blocked["ok"] is False and blocked["status"] == "blocked"


def test_sal10_a_cadence_touch_never_sends_a_time_another_lead_took_meanwhile(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "touch.json")
    now = ct(2026, 9, 22, 10, 0)
    grid = cadence.default_slot_grid(now)
    lead = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    stale = cadence.fresh_slots(lead, now, grid, store)
    # another lead's card took both times after this tick read the registry
    assert A.claim_slots(store, "other@x.com", [cadence._iso(s) for s in stale], now,
                         fields={"approval": "other-card"}) == []
    real = cadence.fresh_slots
    monkeypatch.setattr(cadence, "fresh_slots", lambda *a, **k: list(stale))
    res = cadence.tick_lead(lead, now, store=store, free_slots=grid)
    assert res["action"] == "slot_taken" and res["quiet"] is True
    assert not (lead.cadence.get("touches") or []) and int(lead.cadence.get("day") or 0) == 0
    assert store.get(cadence.touch_marker_key(lead, 1)) is None                 # the day is not spent
    assert {r["lead"] for r in store.get(A.OFFERED_KEY)} == {"other@x.com"}
    monkeypatch.setattr(cadence, "fresh_slots", real)
    again = cadence.tick_lead(lead, now, store=store, free_slots=grid)
    assert again["action"] == "would_send"
    assert not set(again["touch"]["slots"]) & {cadence._iso(s) for s in stale}


def test_sal10_booking_refuses_a_time_another_lead_took_meanwhile(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "book.json")
    now = ct(2026, 9, 22, 10, 0)
    assert A.claim_slots(store, "other@x.com", [FRI[1]], now, fields={"approval": "other-card"}) == []
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, first_name="Sopio", ghl_contact_id="contact-1")
    ghl = Recorder()
    res = booking_mod.book(state, FRI[1], ghl, FakeInstantly(sender=SOPIO), now=now, free_slots=[FRI[1]],
                           store=store)          # the free list came from a read made before the claim
    assert booking_mod.SLOT_ALREADY_TAKEN in res.problems
    assert ghl.named("create_appointment") == [] and not (state.cadence or {}).get("booking")
    # the booking that does go through leaves only its own row, no provisional claim
    state2 = LeadState(lead_email="c@x.com", campaign_id=CAMPAIGN, first_name="Cam", ghl_contact_id="contact-2")
    ok = booking_mod.book(state2, FRI[0], Recorder(), FakeInstantly(sender="c@x.com"), now=now, free_slots=[FRI[0]],
                          store=store)
    assert booking_mod.SLOT_ALREADY_TAKEN not in ok.problems
    rows = [r for r in store.get(A.OFFERED_KEY) if r["slot"] == FRI[0]]
    assert len(rows) == 1 and rows[0]["approval"].startswith(A.BOOKING_RESERVATION_PREFIX)


# ============================================= SAL-11. percentages
TRIGGER_BODY = ("Hey Jo,\n\nNothing up front. I take 20 to 30 percent of first-year contract value on the accounts "
                "that come back.\n\nLorenzo")


def test_sal11_another_offers_percentage_is_refused():
    problems = draft_mod.validate_draft(TRIGGER_BODY, campaign_key="cleaning_trigger")
    assert any("percentage 20%" in p and "cleaning_reactivation" in p for p in problems)
    assert any("percentage 30%" in p for p in problems)
    for body in ("Hey Jo,\n\nIt is 20-30% of first-year fees.\n\nLorenzo",
                 "Hey Jo,\n\nIt is 20–30% of first-year fees.\n\nLorenzo"):
        assert any("percentage 20%" in p for p in draft_mod.validate_draft(body, campaign_key="bookkeeping_trigger"))


def test_sal11_an_offers_own_percentage_and_the_ps_proof_pass():
    assert draft_mod.validate_draft(TRIGGER_BODY, campaign_key="cleaning_reactivation") == []
    ps = "Hey Jo,\n\nHappy to walk you through it.\n\nLorenzo\n\nP.S. A consultancy saw +35% reply rate.\n\nLorenzo"
    assert not [p for p in draft_mod.validate_draft(ps, campaign_key="cleaning_trigger") if "percent" in p]
    assert draft_mod.validate_draft(TRIGGER_BODY) == []          # no campaign key: no cross-offer guard


def test_sal11_a_proof_row_percentage_is_kept_to_its_offer():
    md = ("| Offer type | Proof line (verbatim) | Used by |\n|---|---|---|\n"
          "| Reactivation | \"We recovered about 12% of dormant accounts inside six months for a roofer.\" | "
          "cleaning_reactivation |\n"
          "| Outbound / trigger | \"We added about 40% more booked walkthroughs in 90 days for a roofer.\" | "
          "cleaning_trigger |\n")
    body = "Hey Jo,\n\nWe added about 12% more.\n\nLorenzo"
    assert any("percentage 12%" in p for p in draft_mod.wrong_offer_proof_problems(body, "cleaning_trigger", md))
    assert draft_mod.wrong_offer_proof_problems(body, "cleaning_reactivation", md) == []


# ===================================== round-4 notes
def test_r4_a_kept_hold_keeps_its_slot_until_the_deferred_teardown(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    booking = dict(state.cadence["booking"])
    out = A._after_cancel(state, booking, None, None, store, "cancelled_by_hand", keep_hold=True,
                          now=ct(2026, 9, 21, 17, 0))
    assert out["slot_kept_until"] and THU_3PM in A.offered_slots(store, ct(2026, 9, 21, 17, 0))
    assert show_rate.is_held(store, APPT)
    A.run_deferred_teardowns(store, ct(2026, 9, 21, 18, 0))                  # the call has not happened yet
    assert THU_3PM in A.offered_slots(store, ct(2026, 9, 21, 18, 0))
    A.run_deferred_teardowns(store, ct(2026, 9, 24, 16, 30))
    assert THU_3PM not in A.offered_slots(store, ct(2026, 9, 21, 18, 0)) and not show_rate.is_held(store, APPT)


def test_r4_a_cancel_that_did_not_keep_the_hold_frees_the_slot_at_once(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    A._after_cancel(state, dict(state.cadence["booking"]), None, None, store, "vetoed", keep_hold=False,
                    now=ct(2026, 9, 21, 17, 0))
    assert THU_3PM not in A.offered_slots(store, ct(2026, 9, 21, 17, 0))


def test_r4_book_as_asked_refuses_while_the_previous_cancel_is_pending(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    state.cadence["booking"]["cancel_failed"] = {"attempts": 1, "error": "GHL 500"}
    store.set(state.key, state.to_store())
    card = _card(state, "asked", OTHER_TIMES, FRI)
    card.requested_slot = "2026-09-25T11:00:00-05:00"
    card.requested_status = "outside_window"
    _save_card(store, card)
    _go_live(monkeypatch)
    ghl = Recorder()
    inst = FakeInstantly(sender=SOPIO)
    out = A.accept_requested(card.token, ghl, inst, store=store, now=ct(2026, 9, 21, 19, 0))
    assert out["ok"] is False and "still being cancelled" in out["error"]
    assert ghl.calls == [] and inst.sent == []
    assert A.load(card.token, store).status == "pending"
    assert store.get(state.key)["cadence"]["booking"]["appointment_id"] == APPT


# ============================================== round-5 note: the crash gap
def test_r5_arm_refusal_compares_against_what_the_card_saw():
    approval = A.Approval.model_validate(dict(
        token="c1.sig", state_key="lead:c:x", lead_email="x@y.com", email_id="t-1", status="sent",
        created_at=ct(2026, 9, 21, 14, 0).isoformat(), expires_at=ct(2026, 9, 23, 14, 0).isoformat(),
        draft={"subject": "Re", "body_text": "Hey\n\nLorenzo"}))
    row = {"processed_email_ids": ["t-0", "t-2"], "approvals": ["c1.sig"],
           "history": [{"event": "inbound", "email_id": "t-3", "label": "ooo"}]}
    assert A.arm_refusal(row, approval, {}) is None                           # the gap: no check at all
    assert A.arm_refusal(row, approval, {}, seen_before=["t-0"]) == "newer_inbound:t-2"
    assert A.arm_refusal(dict(row, processed_email_ids=["t-0", "t-3"]), approval, {}, seen_before=["t-0"]) is None


def test_r5_a_card_whose_own_email_is_not_processed_yet_does_not_arm_over_a_newer_reply(tiff, monkeypatch):
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="g-1")
    key = r1["state_key"]
    card_id = r1["approval_token"].split(".")[0]
    context = A.card_context(st, card_id)
    assert context["processed_before"] == [] and context["email_id"] == "g-1"
    # the crash gap: card A exists, its own email never made it into the row
    raw = st.get(key)
    st.set(key, dict(raw, processed_email_ids=[x for x in raw["processed_email_ids"] if x != "g-1"]))
    later = _reply(tiff["deps"], "g-2", "Not right now, maybe next quarter.", "2026-09-21T19:02:00Z",
                   ct(2026, 9, 21, 14, 2))
    assert later["approval_token"] is None                                  # a reply that raises no card
    # S-rest round 3: a "not now" holds the lead's open cards when it lands,
    # and the send refuses a card the lead has answered since. This used to
    # send card A (only the ladder stayed unarmed). To pin the crash-gap half
    # of the send's check on its own, the arrival hold is undone and the
    # row's status and classification no longer say "not now": only the
    # history label of g-2, found through the context's processed_before,
    # is left to catch it.
    assert later["cards_held"] == [card_id]
    raw_card = st.get(A.APPROVAL_PREFIX + card_id)
    st.set(A.APPROVAL_PREFIX + card_id, dict(raw_card, status="pending",
                                            draft=dict(raw_card["draft"], problems=[])))
    st.set(key, dict(st.get(key), status="draft_pending_approval", classification=None))
    out = A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and tiff["inst"].sent == []
    assert out["lead_reply"]["email_id"] == "g-2" and out["lead_reply"]["category"] == "negative_notnow"
    assert not st.get(key)["cadence"].get("armed_at")


# ============================================== OPS-10: time to first reply
def test_ops10_the_reply_time_and_the_send_time_are_recorded_and_read(tiff, monkeypatch):
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="f-1")          # the lead's reply landed Mon 19:00Z = 14:00 CT
    card_id = r1["approval_token"].split(".")[0]
    assert A.card_context(st, card_id)["reply_at"] == ct(2026, 9, 21, 14, 0).isoformat()
    A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    r2 = _reply(tiff["deps"], "f-2", "Quick one: how does the pricing work exactly?", "2026-09-21T19:30:00Z",
                ct(2026, 9, 21, 14, 31))
    assert r2["approval_token"]
    A.approve(r2["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 50), ghl=tiff["ghl"])
    sent = [h for h in st.get(r1["state_key"])["history"] if h.get("event") == "reply_sent"]
    assert [(h["reply_at"], h["sent_at"], h["first_reply"]) for h in sent] == [
        (ct(2026, 9, 21, 14, 0).isoformat(), ct(2026, 9, 21, 14, 5).isoformat(), True),
        (ct(2026, 9, 21, 14, 30).isoformat(), ct(2026, 9, 21, 14, 50).isoformat(), False)]
    rows = [r for r in sources.read_job_log(job_log_path())
            if r.get("job") == "reply_engine.approval" and r.get("status") == "sent"]
    assert len(rows) == 2 and rows[0]["details_parsed"]["reply_at"] == ct(2026, 9, 21, 14, 0).isoformat()
    day = sources.ct_day(sources.parse_ts(rows[0]["ts_utc"]))
    # reply landed 14:00, answer sent 14:05: five minutes. The second answer in
    # the thread (20 minutes) is not a first reply and is left out.
    assert sources.first_reply_minutes(rows, day) == pytest.approx(5.0)


def test_ops10_sources_prefers_the_recorded_send_time_and_skips_later_answers():
    def row(ts, **details):
        return {"job": "reply_engine.approval", "status": "sent", "ts_utc": ts, "details_parsed": details}

    day = date(2026, 9, 22)
    rows = [row("2026-09-22T15:00:00+00:00", reply_at="2026-09-22T14:00:00+00:00",
                sent_at="2026-09-22T14:12:00+00:00", first_reply=True),
            row("2026-09-22T16:00:00+00:00", reply_at="2026-09-22T15:00:00+00:00",
                sent_at="2026-09-22T15:40:00+00:00", first_reply=False)]
    assert sources.first_reply_minutes(rows, day) == pytest.approx(12.0)
    assert sources.first_reply_minutes(rows[1:], day) is None


def test_ops10_the_created_row_carries_the_reply_time(tiff, monkeypatch):
    rows = []
    real = job_log.log_run
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: rows.append((job, status, details))
                        or real(job, status, details))
    r = _reply(tiff["deps"], "c-1", "Sounds interesting. How does pricing work?", "2026-09-21T19:00:00Z",
               ct(2026, 9, 21, 14, 0))
    created = [d for j, s, d in rows if j == "reply_engine.approval" and s == "created"]
    assert r["approval_token"] and created[0]["reply_at"] == ct(2026, 9, 21, 14, 0).isoformat()


def test_expiry_and_claim_helpers_exist_for_the_poller():
    assert "blocked" in A.EXPIRABLE_STATUSES and "sending" not in A.EXPIRABLE_STATUSES
    assert "expired" in A.ORPHAN_OWNER_STATUSES
    assert timedelta(hours=A.TTL_HOURS) == timedelta(hours=48)
