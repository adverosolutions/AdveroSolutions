"""Send-safety round 6: after an out-of-office, follow-ups went out while a
newer human reply's card was pending (reviewer-max, round-5 review).

router.route leaves ``cadence.reason = "ooo"`` and ``status = "ooo"`` behind.
cadence.is_auto_reply_pause said "robot" whenever that reason, the status or
only the newest label did, even when the lead had written since the ladder's
baseline and the card was waiting; the tick then un-stopped the ladder and
moved the baseline to its own clock, past the human reply, so the inbound check
never fired and the one-time "waiting on your answer" line was skipped. Our D1,
an instant auto-reply, then the lead's real answer is the common order.

Pinned here, one test per case of the reviewer's round-5 probe (plus the
mirror of case 4) and the lone out-of-office that must still pause and resume:

1. the pause is decided from every reply since the ladder's baseline, by the
   label each one's history entry carries (cadence.inbounds_since_baseline);
2. a resume clears the auto-reply reason and moves the baseline to the
   auto-reply's own received time, and the tick's write re-decides under the
   row's lock (jobs.cadence_tick._stop_for_a_reply_under_lock);
3. nothing goes out while the lead has an open card (cadence.open_cards, in
   tick_lead and in the last look before the POST);
4. one lead's lock timeout no longer ends the hourly tick for every lead after
   it (jobs.cadence_tick.run).

Every client is an in-process fake; live mode is set in-process only.
"""
from datetime import timedelta

from shared.store import JsonFileStore, StoreError

from jobs import cadence_tick as cadence_job
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine.models import Approval, Draft, LeadState

from test_send_safety_round2 import FakeInstantly, _d1_state, ct
from test_send_safety_round5 import (  # noqa: F401 - the tiff fixture and the Tiffany world
    D1_SLOTS, LADDER_SLOTS, TIFF, _first_card, _listed, _reply, _ticks, tiff,
)

OOO_TEXT = "I am out of the office until September 23 with limited access to email."
OOO_SUBJECT = "Automatic reply: Tiffany, question"
HUMAN = "I'm back early. Yes, let's talk: does Thursday afternoon work?"


def _after_d1_and_an_ooo(tiff, monkeypatch):
    """Card A answered Mon 14:05 (ladder armed), D1 out Tue 10:00, and the lead's
    auto-responder answers it: received 10:05, processed by the engine 10:07."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="q-1")
    key = r1["state_key"]
    A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], LADDER_SLOTS, [])
    assert len(d1.sent) == 1
    ooo = _reply(tiff["deps"], "q-ooo", OOO_TEXT, "2026-09-22T15:05:00Z", ct(2026, 9, 22, 10, 7), subject=OOO_SUBJECT)
    assert ooo["label"] == "ooo" and ooo["approval_token"] is None
    raw = st.get(key)
    assert raw["cadence"]["stopped_reason"] == "inbound_reply" and raw["cadence"]["reason"] == "ooo"
    assert raw["status"] == "ooo"
    return st, key


def _human(tiff, email_id, ts, now, text=HUMAN):
    r = _reply(tiff["deps"], email_id, text, ts, now)
    assert r["approval_token"] and A.load(r["approval_token"], tiff["store"]).status == "pending"
    return r


# ====================================================== the reviewer's four
def test_case_1_the_leads_reply_after_an_out_of_office_keeps_the_ladder_stopped(tiff, monkeypatch):
    """OOO 10:05, the lead's real answer 10:55 (card B), tick 11:00."""
    st, key = _after_d1_and_an_ooo(tiff, monkeypatch)
    r2 = _human(tiff, "q-2", "2026-09-22T15:55:00Z", ct(2026, 9, 22, 10, 55))
    # the leftovers that used to decide it are all still saying "robot"
    assert st.get(key)["cadence"]["reason"] == "ooo"
    pings = []
    d, results = _ticks(st, [ct(2026, 9, 22, 11, 0), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 9, 30),
                             ct(2026, 9, 24, 10, 0), ct(2026, 9, 25, 10, 0)], LADDER_SLOTS, pings)
    assert d.sent == []
    assert results[0] == [("awaiting_fresh_draft", "inbound_reply", 2)]            # said once, not skipped
    assert all(r == [("already_stopped", "inbound_reply", None)] for r in results[1:])
    cad = st.get(key)["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert not cad.get("resumed_after_auto_reply_at")
    assert A.load(r2["approval_token"], st).status == "pending"


def test_case_2_a_reply_after_the_pause_resumed_stops_the_ladder_for_good(tiff, monkeypatch):
    """The 11:00 tick resumes the lone OOO; the lead writes at 12:00; the 13:00
    tick must not resume again on the auto-reply's leftover reason."""
    st, key = _after_d1_and_an_ooo(tiff, monkeypatch)
    _, first = _ticks(st, [ct(2026, 9, 22, 11, 0)], LADDER_SLOTS, [])
    assert first == [[("resumed_after_auto_reply", None, 2)]]
    cad = st.get(key)["cadence"]
    # the baseline is the auto-reply's own received time, never the tick's 11:00
    assert cad["resumed_after_auto_reply_at"] == ct(2026, 9, 22, 10, 5).isoformat()
    assert cad["auto_reply_seen_through"] == ct(2026, 9, 22, 10, 7).isoformat()
    assert cad["auto_reply_seen_email_id"] == "q-ooo"
    assert "reason" not in cad and "paused" not in cad                              # cleared with the pause
    r2 = _human(tiff, "q-2", "2026-09-22T17:00:00Z", ct(2026, 9, 22, 12, 0))
    assert st.get(key)["cadence"]["stopped_reason"] == "inbound_reply"
    d, results = _ticks(st, [ct(2026, 9, 22, 13, 0), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 10, 0)],
                        LADDER_SLOTS, [])
    assert d.sent == []
    assert results[0] == [("awaiting_fresh_draft", "inbound_reply", 2)]
    assert A.load(r2["approval_token"], st).status == "pending"


def test_case_3_a_shared_box_auto_reply_right_after_the_leads_reply(tiff, monkeypatch):
    """Mid-ladder: the lead answers D1 with a question (card B) at 12:00 and the
    shared box's auto-responder fires at 12:02. The newest label is the robot's."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="s-1")
    key = r1["state_key"]
    A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], LADDER_SLOTS, [])
    assert len(d1.sent) == 1
    r2 = _human(tiff, "s-2", "2026-09-22T17:00:00Z", ct(2026, 9, 22, 12, 0),
                text="Thanks. What would you need from us to get started?")
    robot = _reply(tiff["deps"], "s-3", "Thank you for your email. This mailbox is checked daily; we will respond "
                                        "within 2 business days. I am out of the office until September 23.",
                   "2026-09-22T17:02:00Z", ct(2026, 9, 22, 12, 2), subject=OOO_SUBJECT)
    raw = st.get(key)
    assert robot["label"] == "ooo" and raw["status"] == "ooo" and raw["cadence"]["reason"] == "ooo"
    d, results = _ticks(st, [ct(2026, 9, 22, 13, 0), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 10, 0)],
                        LADDER_SLOTS, [])
    assert d.sent == []
    assert results[0] == [("awaiting_fresh_draft", "inbound_reply", 2)]
    assert A.load(r2["approval_token"], st).status == "pending"


def test_case_4_a_reply_processed_while_the_tick_holds_its_copy(tiff, monkeypatch):
    """The 11:00 tick reads the row (only the OOO on it) and takes the pause;
    the lead's answer is processed while the tick holds that copy. It left the
    stop fields alone (the ladder was already stopped), so the merge alone kept
    the tick's un-stop. Under the row's lock the reply is visible."""
    st, key = _after_d1_and_an_ooo(tiff, monkeypatch)
    real = cadence.resume_after_auto_reply
    box = {}

    def resume_with_reply(state, now):
        if "r2" not in box:
            box["r2"] = _human(tiff, "q-2", "2026-09-22T15:55:00Z", ct(2026, 9, 22, 10, 58))
        return real(state, now)

    monkeypatch.setattr(cadence, "resume_after_auto_reply", resume_with_reply)
    _, first = _ticks(st, [ct(2026, 9, 22, 11, 0)], LADDER_SLOTS, [])
    monkeypatch.setattr(cadence, "resume_after_auto_reply", real)
    assert "r2" in box
    assert first == [[("stopped", "inbound_reply", 2)]]                          # not "resumed"
    raw = st.get(key)
    cad = raw["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert cad["next_send_at"] is None
    assert _listed(raw, box["r2"]["approval_token"]) and raw["last_inbound_at"] == "2026-09-22T15:55:00+00:00"
    d, results = _ticks(st, [ct(2026, 9, 22, 12, 0), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 10, 0),
                             ct(2026, 9, 25, 10, 0)], LADDER_SLOTS, [])
    assert d.sent == []
    assert results[0] == [("awaiting_fresh_draft", "inbound_reply", 2)]
    assert A.load(box["r2"]["approval_token"], st).status == "pending"


def test_case_4_mirrored_the_tick_resumes_while_the_reply_is_being_processed(tiff, monkeypatch):
    """The other order: the reply's pipeline reads the row (stopped by the
    OOO), the 11:00 tick resumes the pause and writes first, and the reply's
    write lands on a running ladder. The pipeline's own rule, applied under
    the row's lock (app._inbound_stop_hook), stops it again."""
    from services.reply_engine import app as app_mod

    st, key = _after_d1_and_an_ooo(tiff, monkeypatch)
    real_classify = app_mod.classify
    box = {}

    def classify_while_the_tick_runs(event):
        if "tick" not in box:
            box["tick"] = _ticks(st, [ct(2026, 9, 22, 11, 0)], LADDER_SLOTS, [])[1]
            box["cad"] = dict(st.get(key)["cadence"])
        return real_classify(event)

    monkeypatch.setattr(app_mod, "classify", classify_while_the_tick_runs)
    r2 = _human(tiff, "q-2", "2026-09-22T15:55:00Z", ct(2026, 9, 22, 10, 58))
    monkeypatch.setattr(app_mod, "classify", real_classify)
    assert box["tick"] == [[("resumed_after_auto_reply", None, 2)]]
    assert box["cad"]["stopped_reason"] is None                                   # the tick's write landed first
    cad = st.get(key)["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    d, results = _ticks(st, [ct(2026, 9, 22, 12, 0), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 10, 0)],
                        LADDER_SLOTS, [])
    assert d.sent == []
    assert results[0] == [("awaiting_fresh_draft", "inbound_reply", 2)]
    assert A.load(r2["approval_token"], st).status == "pending"


def test_a_lone_out_of_office_still_pauses_and_resumes(tiff, monkeypatch):
    """No human anywhere: the ladder resumes after the return date, and the
    auto-responder answering the next touch too is a second pause, not a stop."""
    st, key = _after_d1_and_an_ooo(tiff, monkeypatch)
    pings = []
    d, results = _ticks(st, [ct(2026, 9, 22, 11, 0), ct(2026, 9, 23, 10, 0)], LADDER_SLOTS, pings)
    assert results[0] == [("resumed_after_auto_reply", None, 2)]
    assert results[1][0][0] == "sent" and len(d.sent) == 1                        # D2, Wed 10:00
    _reply(tiff["deps"], "q-ooo2", OOO_TEXT, "2026-09-23T15:05:00Z", ct(2026, 9, 23, 10, 6), subject=OOO_SUBJECT)
    assert st.get(key)["cadence"]["stopped_reason"] == "inbound_reply"
    d2, results2 = _ticks(st, [ct(2026, 9, 23, 11, 0), ct(2026, 9, 24, 10, 0)], LADDER_SLOTS, pings)
    assert results2[0] == [("resumed_after_auto_reply", None, 3)]
    assert results2[1][0][0] == "sent" and len(d2.sent) == 1                       # D3, Thu 10:00
    cad = st.get(key)["cadence"]
    assert cad["resumed_after_auto_reply_at"] == ct(2026, 9, 23, 10, 5).isoformat()
    assert cad["auto_reply_seen_email_id"] == "q-ooo2" and cad["day"] == 3
    assert not [r for r in results + results2 if r and r[0][0] == "awaiting_fresh_draft"]


# ================================================= 3. no touch over an open card
def _old_resume(cad, at):
    """What the pre-fix tick wrote when it resumed a pause: its own clock as the
    baseline, the auto-reply's reason left behind."""
    out = dict(cad, stopped_reason=None, stopped_at=None, needs_fresh_draft=False,
               next_send_at=ct(2026, 9, 23, 10, 0).isoformat(), resumed_after_auto_reply_at=at.isoformat(),
               stall_notified_at=None)
    out.pop("paused", None)
    return out


def test_a_ladder_left_running_over_a_waiting_card_is_stopped_before_anything_goes_out(tiff, monkeypatch):
    """A row the pre-fix tick already resumed over card B (the deploy meets rows
    like this): the ladder is running and its own fields see nothing new. The
    open card stops it; answering card B re-arms it."""
    st, key = _after_d1_and_an_ooo(tiff, monkeypatch)
    r2 = _human(tiff, "q-2", "2026-09-22T15:55:00Z", ct(2026, 9, 22, 10, 55))
    st.mutate(key, lambda raw: dict(raw, cadence=_old_resume(raw["cadence"], ct(2026, 9, 22, 10, 56))))
    assert cadence.human_reply_since_baseline(LeadState.from_store(st.get(key))) is None   # blind to q-2
    pings = []
    d, results = _ticks(st, [ct(2026, 9, 22, 10, 57), ct(2026, 9, 22, 10, 58), ct(2026, 9, 23, 10, 0)],
                        LADDER_SLOTS, pings)
    assert d.sent == []
    assert results[0] == [("stopped", "open_card", None)]
    assert results[1] == [("awaiting_fresh_draft", "inbound_reply", 2)]
    assert st.get(key)["cadence"]["stopped_reason"] == "inbound_reply"
    # not stranded: Lorenzo's answer to card B (while its times are still 4 h out)
    # re-arms the ladder, and D2 follows it
    out = A.approve(r2["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 22, 10, 59), ghl=tiff["ghl"])
    assert out["ok"] and out["cadence"]["armed"] is True
    d2, results2 = _ticks(st, [ct(2026, 9, 23, 10, 0)], LADDER_SLOTS, pings)
    assert results2[0][0][0] == "sent" and len(d2.sent) == 1


def _card(approval_id, state_key, status, now, email_id="e-0"):
    return Approval(token="%s.sig" % approval_id, state_key=state_key, lead_email=TIFF, email_id=email_id,
                    draft=Draft(subject="Re: x", body_text="Hey Tiffany,\n\nx\n\nLorenzo"), status=status,
                    created_at=now.isoformat(), expires_at=(now + timedelta(hours=A.TTL_HOURS)).isoformat())


def test_a_card_that_opens_while_the_tick_builds_the_touch_holds_the_send(tmp_env, monkeypatch):
    """Lorenzo taps Retry on a failed card while the tick is building D1: the
    card is pending again when the tick takes its last look before the POST."""
    store = JsonFileStore(tmp_env / "look.json")
    state = _d1_state()
    state.approvals = ["x1.sig"]
    store.set(state.key, state.to_store())
    store.set(A.APPROVAL_PREFIX + "x1", _card("x1", state.key, "send_failed", ct(2026, 9, 22, 8, 0))
              .model_dump(mode="json"))
    real = cadence.build_touch

    def build_while_retried(*a, **k):
        row = store.get(A.APPROVAL_PREFIX + "x1")
        store.set(A.APPROVAL_PREFIX + "x1", dict(row, status="pending"))
        return real(*a, **k)

    monkeypatch.setattr(cadence, "build_touch", build_while_retried)
    inst = FakeInstantly(sender=TIFF)
    out = cadence_job.run(ct(2026, 9, 22, 10, 0), store, inst, None, free_slots=D1_SLOTS,
                          notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    monkeypatch.setattr(cadence, "build_touch", real)
    res = out["results"][0]
    assert inst.sent == [] and res["action"] == "stopped" and res["reason"] == "changed_while_ticking:open_card"
    assert store.get(cadence.touch_marker_key(state, 1)) is None                  # the day stays unspent
    # the next tick stops the ladder for the open card itself
    again = cadence_job.run(ct(2026, 9, 22, 11, 0), store, inst, None, free_slots=D1_SLOTS,
                            notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    assert again["results"][0]["action"] == "stopped" and again["results"][0]["reason"] == "open_card"
    assert inst.sent == [] and store.get(state.key)["cadence"]["stopped_reason"] == "inbound_reply"


def test_open_cards_counts_pending_and_queued_inside_their_ttl_and_holds_when_unreadable(tmp_env):
    store = JsonFileStore(tmp_env / "cards.json")
    now = ct(2026, 9, 22, 10, 0)
    key = "lead:c:x"
    rows = {"p": _card("p", key, "pending", now), "q": _card("q", key, "approved_queued", now),
            "s": _card("s", key, "sent", now), "v": _card("v", key, "vetoed", now),
            "old": _card("old", key, "pending", now - timedelta(hours=A.TTL_HOURS + 1))}
    for approval_id, card in rows.items():
        store.set(A.APPROVAL_PREFIX + approval_id, card.model_dump(mode="json"))
    tokens = ["p.sig", "q.sig", "s.sig", "v.sig", "old.sig", "gone.sig", "p.resigned"]
    assert A.open_card_ids(store, tokens, now) == ["p", "q"]
    state = _d1_state()
    state.approvals = tokens
    assert cadence.open_cards(state, store, now) == ["p", "q"]
    assert cadence.open_cards(state, None, now) == []
    # the last look before the POST reads the stored row's cards
    store.set(state.key, state.to_store())
    mine = LeadState.from_store(store.get(state.key))
    assert cadence.changed_in_store(mine, store, now) == "open_card"
    assert cadence.changed_in_store(mine, store) is None                          # no clock, no card check

    class Broken(object):
        def get(self, k, default=None):
            if k.startswith(A.APPROVAL_PREFIX):
                raise StoreError("could not acquire the store lock")
            return store.get(k, default)

    assert cadence.changed_in_store(mine, Broken(), now) == "open_card_unreadable"
    res = cadence.tick_lead(mine, ct(2026, 9, 22, 10, 0), store=Broken(), free_slots=D1_SLOTS,
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "error" and "cards" in res["error"]
    assert mine.cadence["stopped_reason"] is None                                 # held, nothing changed


def test_an_open_card_leaves_the_ladders_own_stop_reasons_as_they_were(tmp_env):
    """A booked or unsubscribed lead is stopped for that, card or no card; the
    open card stops only a ladder nothing else would. Nothing goes out either way."""
    store = JsonFileStore(tmp_env / "why.json")
    now = ct(2026, 9, 22, 10, 0)
    state = _d1_state()
    state.approvals = ["p.sig"]
    store.set(A.APPROVAL_PREFIX + "p", _card("p", state.key, "pending", now).model_dump(mode="json"))
    booked = LeadState.from_store(state.to_store())
    booked.cadence["booking"] = {"slot": "2026-09-24T13:00:00-05:00"}
    unsubscribed = LeadState.from_store(state.to_store())
    unsubscribed.status = "unsubscribed"
    plain = LeadState.from_store(state.to_store())
    inst = FakeInstantly(sender=TIFF)
    out = {}
    for name, lead in (("booked", booked), ("unsubscribe", unsubscribed), ("plain", plain)):
        res = cadence.tick_lead(lead, now, store=store, instantly=inst, free_slots=D1_SLOTS,
                                notify_fn=lambda *a, **k: None)
        out[name] = (res["action"], res.get("reason"), lead.cadence["stopped_reason"])
    assert out == {"booked": ("stopped", "booked", "booked"),
                   "unsubscribe": ("stopped", "unsubscribe", "unsubscribe"),
                   "plain": ("stopped", "open_card", "inbound_reply")}
    assert inst.sent == []


# ======================================== 1. decided from every reply, by label
def _armed(history, **cad):
    state = _d1_state()                                                           # armed Mon 16:00
    state.cadence.update(armed_for_email_id="src", **cad)
    state.history = [dict(e, event="inbound") for e in history]
    return state


def _entry(email_id, label, at):
    return {"email_id": email_id, "label": label, "at": at.isoformat()}


SRC = _entry("src", "positive_question", ct(2026, 9, 21, 15, 0))


def test_the_pause_is_decided_from_every_reply_since_the_baseline_by_label():
    ooo = _entry("o1", "ooo", ct(2026, 9, 22, 10, 7))
    human = _entry("h1", "positive_interested", ct(2026, 9, 22, 10, 55))
    later_robot = _entry("o2", "auto_reply_unmonitored", ct(2026, 9, 22, 10, 58))

    def stopped(state):
        cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 10, 7))
        return state

    # only machines since the baseline: a pause, whatever the status and reason say
    state = stopped(_armed([SRC, ooo]))
    state.status = "positive_interested"
    assert cadence.is_auto_reply_pause(state) is True
    # the lead wrote since the baseline: never a pause, whatever the status,
    # the leftover reason and the newest label say
    state = stopped(_armed([SRC, ooo, human, later_robot], reason="ooo"))
    state.status = "ooo"
    assert cadence.is_auto_reply_pause(state) is False
    assert cadence.human_reply_since_baseline(state) == "h1"
    # a stop nothing on the row explains is not a robot's either
    assert cadence.is_auto_reply_pause(stopped(_armed([SRC]))) is False
    # the email the approved answer covered never counts, even processed again after the arm
    retried = _entry("src", "positive_question", ct(2026, 9, 22, 9, 0))
    assert cadence.is_auto_reply_pause(stopped(_armed([SRC, retried, ooo]))) is True
    # a reply whose pipeline started before the arm and wrote after it counts
    straddled = _entry("h0", "positive_question", ct(2026, 9, 21, 15, 59))
    assert cadence.human_reply_since_baseline(_armed([SRC, straddled])) == "h0"
    assert cadence.human_reply_since_baseline(_armed([straddled, SRC])) is None     # written before: seen


def test_a_resume_measures_from_what_it_took_stock_of_never_the_ticks_clock():
    ooo = _entry("o1", "ooo", ct(2026, 9, 22, 10, 7))
    state = _armed([SRC, ooo], reason="ooo", paused=True, resume_at="2026-09-23")
    state.last_inbound_at = "2026-09-22T15:05:00+00:00"                          # the robot's received time
    cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 10, 7))
    nxt = cadence.resume_after_auto_reply(state, ct(2026, 9, 22, 11, 0))
    cad = state.cadence
    assert nxt == ct(2026, 9, 23, 10, 0)
    assert cad["resumed_after_auto_reply_at"] == ct(2026, 9, 22, 10, 5).isoformat()
    assert cad["auto_reply_seen_through"] == ct(2026, 9, 22, 10, 7).isoformat()
    assert cad["auto_reply_seen_email_id"] == "o1"
    assert "reason" not in cad and "paused" not in cad and cad["stopped_reason"] is None
    # what the resume saw stays seen; anything after it is new
    assert cadence.inbounds_since_baseline(state) == []
    # a reply the lead sent at 10:40, processed while the tick held its copy
    state.history.append(dict(_entry("h1", "positive_interested", ct(2026, 9, 22, 10, 50)), event="inbound"))
    assert cadence.human_reply_since_baseline(state) == "h1"
    # ...and one whose pipeline started before the robot's but wrote after the resume read the row
    state.history[-1]["at"] = ct(2026, 9, 22, 10, 6).isoformat()
    assert cadence.human_reply_since_baseline(state) == "h1"
    # the inbound check reads the robot's received time: a later reply stops the ladder
    state.history.pop()
    state.last_inbound_at = "2026-09-22T15:40:00+00:00"
    assert cadence.stop_reason(state, ct(2026, 9, 22, 12, 0)) == "inbound_reply"
    # a second robot after the resume is a second pause
    state.last_inbound_at = "2026-09-23T15:05:00+00:00"
    state.history.append(dict(_entry("o2", "ooo", ct(2026, 9, 23, 10, 6)), event="inbound"))
    cadence.stop(state, "inbound_reply", ct(2026, 9, 23, 10, 6))
    assert cadence.is_auto_reply_pause(state) is True
    # a re-arm after the resume is the newest stock-take again
    cadence.arm(state, ct(2026, 9, 23, 12, 0))
    state.cadence["armed_for_email_id"] = "o2"
    assert cadence.inbounds_since_baseline(state) == []


# ============================================= 4. one lead's lock timeout
class StuckLockStore(JsonFileStore):
    """The Modal store's per-key lock timing out on one lead row."""

    def __init__(self, path, stuck_key):
        JsonFileStore.__init__(self, path)
        self.stuck_key = stuck_key
        self.stuck = True

    def mutate(self, key, fn, default=None):
        if self.stuck and key == self.stuck_key:
            raise StoreError("could not acquire the store lock for %r within 10s" % key)
        return JsonFileStore.mutate(self, key, fn, default)


def test_a_lock_timeout_on_one_lead_row_does_not_end_the_tick_for_the_rest(tmp_env):
    first = _d1_state()
    first.campaign_id = "0000aaaa-first"
    second = _d1_state()
    second.campaign_id = "ffff0000-second"
    assert first.key < second.key                                                 # the stuck lead goes first
    store = StuckLockStore(tmp_env / "stuck.json", first.key)
    for state in (first, second):
        store.set(state.key, state.to_store())
    inst = FakeInstantly(sender=TIFF)
    logs, pings = [], []
    summary = cadence_job.run(ct(2026, 9, 22, 10, 0), store, inst, None, free_slots=LADDER_SLOTS,
                              notify_fn=lambda *a, **k: pings.append(a),
                              log_fn=lambda job, status, detail: logs.append((status, detail)))
    by_key = {r["key"]: r for r in summary["results"]}
    assert set(by_key) == {first.key, second.key}
    assert by_key[first.key]["action"] in cadence_job.TOUCH_ACTIONS
    assert "StoreError" in by_key[first.key]["persist_error"]
    assert by_key[second.key]["action"] in cadence_job.TOUCH_ACTIONS and "persist_error" not in by_key[second.key]
    assert len(inst.sent) == 2
    assert store.get(second.key)["cadence"]["day"] == 1                         # the rest were saved
    assert store.get(first.key)["cadence"]["day"] == 0                          # this one was not
    assert summary["unsaved"] == 1 and summary["needs_you"] == 1 and logs[-1][0] == "errors"
    assert "NOT SAVED" in pings[-1][1] and "1 needs you" in pings[-1][0]
    assert store.get(cadence_job.lock_key(first.key)) is None                   # its claim was released
    # the next tick repairs the unsaved lead from its touch marker and sends nothing twice
    store.stuck = False
    again = cadence_job.run(ct(2026, 9, 22, 11, 0), store, inst, None, free_slots=LADDER_SLOTS,
                            notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    again_by_key = {r["key"]: r for r in again["results"]}
    assert again_by_key[first.key]["action"] == "already_sent" and again_by_key[second.key]["action"] == "not_due"
    assert len(inst.sent) == 2 and store.get(first.key)["cadence"]["day"] == 1
