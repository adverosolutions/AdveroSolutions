"""U2 thread state machine tests. Invented rooms only; clock always injected
(America/Chicago calendar); fake classifier; JsonFileStore in tmp_path. No
network, no LLM: the draft-prompt checks call draft.py with a recording fake.

``World.run`` plays the orchestrator: after each run it fills every draft
reservation with ``record_pending`` (``fill=False`` simulates a crashed tick).
"""
import ast
import itertools
import json
import random
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
import pytz

from shared.store import JsonFileStore, StoreError

from services.upwork_followup import draft
from services.upwork_followup import sequence as seq
from services.upwork_followup.sequence import GAPS, thread_key

CT = pytz.timezone("America/Chicago")
D0 = date(2026, 9, 7)  # a Monday
MIN = timedelta(minutes=1)


def ct(days=0, h=14, m=0, base=D0):
    """days after D0 at h:m America/Chicago, as UTC."""
    return CT.localize(datetime.combine(base + timedelta(days=days), time(h, m))).astimezone(timezone.utc)


def batch(days):
    return ct(days, 8, 30)


def midnight(days):
    return ct(days, 0, 0)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def msg(mid, side, when, text="hello"):
    return {"id": mid, "side": side, "at": iso(when), "text": text}


def make_room(rid="room_a1", msgs=None, proposal_id="prop_a1", origin="proposal",
              contract=None, offer_state=None):
    """Default: the client wrote Sunday, Lorenzo answered Monday 14:00 CT
    (the silence starts then)."""
    if msgs is None:
        msgs = [msg("c1", "client", ct(-1, 10), "positive: sounds good"),
                msg("f1", "freelancer", ct(0, 14), "thanks, here is my plan")]
    room = {
        "room_id": rid, "client": "Acme Test Co", "client_first_name": "Dana",
        "room_type": "ONE_ON_ONE", "job_title": "Invented CRM automation", "job_id": None,
        "proposal_id": proposal_id, "origin": origin, "contract": contract,
        "offer_state": offer_state, "messages": list(msgs), "job_folder": None, "job": None,
    }
    _sync_last(room)
    return room


def _sync_last(room):
    """Like collect.py: last_side/last_message_at follow the last message."""
    msgs = room["messages"] or []
    room["last_side"] = msgs[-1]["side"] if msgs else None
    room["last_message_at"] = msgs[-1]["at"] if msgs else None


def snap(rooms, messages=True, **extra):
    s = {"generated_at": "2026-09-07T00:00:00Z", "source": "fixture",
         "sections": {"rooms": True, "messages": messages, "proposals": True,
                      "invitations": True, "contracts": True, "offers": True},
         "truncated": False, "rooms": list(rooms)}
    s.update(extra)
    return s


class FakeClassify(object):
    """Label is the text before the first colon; an optional |YYYY-MM-DD tail
    is the follow_up_at."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, room):
        self.calls.append(text)
        label = text.split(":", 1)[0].strip()
        fu = text.rsplit("|", 1)[1].strip() if "|" in text else None
        return {"label": label, "confidence": 0.95, "follow_up_at": fu}


def fill_reservation(store, rid, when, text="drafted text"):
    def fn(cur):
        p = cur["pending"]
        return seq.record_pending(cur, p["kind"], p["touch"], text, when, "card_%s" % rid)
    return store.mutate(thread_key(rid), fn)


class World(object):
    def __init__(self, tmp_path, store=None):
        self.store = store or JsonFileStore(tmp_path / "store.json")
        self.rooms = {}
        self.cls = FakeClassify()

    def add(self, room):
        self.rooms[room["room_id"]] = room
        return room

    def say(self, rid, mid, side, when, text="hello"):
        self.rooms[rid]["messages"].append(msg(mid, side, when, text))
        _sync_last(self.rooms[rid])

    def event(self, rid, mid, when, text="Acme Test Co sent an offer"):
        """A room event: ``event: true``, side unknown, and (like collect.py) it
        never sets last_side."""
        m = msg(mid, "unknown", when, text)
        m["event"] = True
        self.rooms[rid]["messages"].append(m)

    def run(self, when, first_run=None, messages=True, fill=True, classify=None, **extra):
        res = seq.run(self.store, snap(self.rooms.values(), messages=messages, **extra), when,
                      classify or self.cls, first_run)
        if fill:
            for room, th, acts in res:
                if th is not None and drafts(acts):
                    fill_reservation(self.store, room["room_id"], when)
        return res

    def thread(self, rid):
        return self.store.get(thread_key(rid))


def acts_for(results, rid):
    for room, _thread, acts in results:
        if room["room_id"] == rid:
            return acts
    return None


def types(acts):
    return [a["type"] for a in acts or []]


def drafts(acts):
    return [a for a in acts or [] if a["type"] in seq.DRAFT_TYPES]


def of_type(acts, t):
    return [a for a in acts or [] if a["type"] == t]


def reviews(acts, reason):
    return [a for a in acts or [] if a["type"] == "needs_review" and a["reason"] == reason]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def enrol_silent(world, rid="room_a1", when=None):
    """The default room enrolled Monday 14:05 CT; its silence started 14:00."""
    world.add(make_room(rid))
    res = world.run(when or ct(0, 14, 5))
    assert "enrolled" in types(acts_for(res, rid))
    return res


# ------------------------------------------------------------------ ladder
def _ladder(tmp_path, start, days=50):
    """Silence at ``start``; a daily 08:30 CT batch; every draft sent 15 min
    after its batch. Returns [(touch or event, CT day offset)]."""
    w = World(tmp_path)
    w.add(make_room("room_x", msgs=[msg("c1", "client", start - timedelta(days=1), "positive: hi"),
                                    msg("f1", "freelancer", start, "my answer")]))
    w.run(start + timedelta(minutes=5))
    day0 = start.astimezone(CT).date()
    got, sent = [], 0
    for i in range(1, days):
        b = ct(0, 8, 30, base=day0 + timedelta(days=i))
        acts = acts_for(w.run(b), "room_x")
        for a in drafts(acts):
            got.append((a["touch"], i))
            sent += 1
            w.say("room_x", "f%d" % (sent + 1), "freelancer", b + timedelta(minutes=15), "touch sent")
        for a in acts or []:
            if a["type"] == "status_change" and a["to"] == "closed_out":
                got.append(("closed_out", i))
    return got


EXPECTED_LADDER = [(1, 2), (2, 4), (3, 7), (4, 11), (5, 16), (6, 23), (7, 30), ("closed_out", 44)]


@pytest.mark.parametrize("start", [
    ct(0, 14, 0),                                   # Monday afternoon silence
    ct(0, 8, 0),                                    # early-morning silence
    ct(0, 23, 50),                                  # late-night silence
    ct(0, 8, 40, base=date(2026, 10, 20)),          # crosses the Nov 1 fall-back
    ct(0, 21, 0, base=date(2027, 2, 20)),           # crosses the Mar 14 spring-forward
], ids=["afternoon", "early", "late_night", "dst_fall_back", "dst_spring_forward"])
def test_ladder_lands_in_the_day_n_morning_batch(tmp_path, start):
    assert _ladder(tmp_path, start) == EXPECTED_LADDER


def test_touch_is_due_from_ct_midnight_of_its_day(world):
    enrol_silent(world)
    t = world.thread("room_a1")
    s = seq.due_summary(t, midnight(2) - MIN)
    assert s["kind"] == "touch" and s["touch"] == 1 and s["draft_now"] is False
    assert s["next_due_at"] == iso(midnight(2))
    assert seq.due_summary(t, midnight(2))["draft_now"] is True
    assert not drafts(acts_for(world.run(midnight(2) - MIN), "room_a1"))
    assert drafts(acts_for(world.run(midnight(2)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_follow_up_date_is_a_ct_date_across_dst(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: after the clocks change|2026-11-02")
    world.run(batch(2))
    nov2 = CT.localize(datetime(2026, 11, 2)).astimezone(timezone.utc)
    assert nov2.hour == 6  # CST, after the fall-back
    assert not drafts(acts_for(world.run(nov2 - MIN), "room_a1"))
    assert drafts(acts_for(world.run(nov2), "room_a1")) == [
        {"type": "draft_checkin", "follow_up_at": "2026-11-02"}]


def test_rewritten_send_is_detected_as_sent(world):
    enrol_silent(world)
    world.run(batch(2))
    world.say("room_a1", "f2", "freelancer", ct(2, 11), "totally different words")
    acts = acts_for(world.run(ct(2, 12)), "room_a1")
    assert of_type(acts, "sent_detected") == [
        {"type": "sent_detected", "kind": "touch", "touch": 1, "message_id": "f2"}]
    t = world.thread("room_a1")
    assert t["touch_index"] == 1 and t["pending"] is None
    assert t["silence_started_at"] == iso(ct(2, 11))


def test_freelancer_message_older_than_the_reservation_is_not_the_send(world):
    enrol_silent(world)
    world.run(batch(2))
    world.say("room_a1", "f2", "freelancer", batch(2) - MIN, "written before the draft existed")
    acts = acts_for(world.run(ct(2, 12)), "room_a1")
    assert not of_type(acts, "sent_detected")
    assert world.thread("room_a1")["pending"]["touch"] == 1


def test_resurface_once_on_ct_day_3_then_skip_on_day_7(world):
    enrol_silent(world)
    world.run(batch(2))  # T1 reserved and filled
    assert not types(acts_for(world.run(midnight(5) - MIN), "room_a1"))
    first = acts_for(world.run(batch(5)), "room_a1")
    assert types(first) == ["resurface"] and first[0]["pending"]["touch"] == 1
    assert world.thread("room_a1")["pending"]["resurfaced_at"] == iso(batch(5))
    assert not types(acts_for(world.run(batch(6)), "room_a1"))
    assert not types(acts_for(world.run(midnight(9) - MIN), "room_a1"))

    skip = acts_for(world.run(batch(9)), "room_a1")
    w = of_type(skip, "withdraw_pending")
    assert w and w[0]["reason"] == "skipped" and w[0]["pending"]["touch"] == 1
    assert not drafts(skip)
    t = world.thread("room_a1")
    assert t["touch_index"] == 1 and t["silence_started_at"] == iso(batch(9))
    assert not drafts(acts_for(world.run(batch(10)), "room_a1"))
    assert drafts(acts_for(world.run(batch(11)), "room_a1")) == [{"type": "draft_touch", "touch": 2}]


def test_skip_never_moves_touch_index_past_7(world):
    enrol_silent(world)
    t = world.thread("room_a1")
    t["touch_index"] = 6
    seq._reserve(t, "touch", 7, batch(1))
    t = seq.record_pending(t, "touch", 7, "close-out", batch(1), "card7")
    t2, acts = seq.advance(t, world.rooms["room_a1"], batch(8), world.cls)
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "skipped"
    assert t2["touch_index"] == 7 and t2["status"] == "active"
    t3, _ = seq.advance(t2, world.rooms["room_a1"], batch(22), world.cls)
    assert t3["status"] == "closed_out"


# ------------------------------------------------------------ crashed tick
def test_crashed_tick_reservation_is_released_and_redrafted(world):
    enrol_silent(world)
    first = acts_for(world.run(batch(2), fill=False), "room_a1")  # the tick dies before drafting
    assert drafts(first) == [{"type": "draft_touch", "touch": 1}]
    assert world.thread("room_a1")["pending"]["text"] is None
    assert acts_for(world.run(batch(2), fill=False), "room_a1") == []  # same time: no-op
    for d in (3, 5, 9, 12):
        acts = acts_for(world.run(batch(d), fill=False), "room_a1")
        assert drafts(acts) == [{"type": "draft_touch", "touch": 1}], d
        assert not of_type(acts, "resurface") and not of_type(acts, "withdraw_pending")
        t = world.thread("room_a1")
        assert t["touch_index"] == 0 and t["pending"]["issued_at"] == iso(batch(d))
    world.run(batch(13))  # a healthy tick finally fills it
    assert world.thread("room_a1")["pending"]["text"] == "drafted text"


def test_crashed_reply_reservation_is_redrafted(world):
    world.add(make_room("room_q", msgs=[msg("c1", "client", ct(0, 9), "question: timeline?")]))
    assert drafts(acts_for(world.run(ct(0, 10), fill=False), "room_q"))
    acts = acts_for(world.run(batch(1)), "room_q")
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c1"}]


# ---------------------------------------------------------- record_pending
def test_record_pending_refuses_after_a_stage_move_race(world):
    enrol_silent(world)
    world.run(batch(2), fill=False)  # reserved
    seq.set_stage(world.store, "room_a1", "call_booked", ct(2, 8, 31))
    before = world.thread("room_a1")
    with pytest.raises(seq.PendingRefused) as err:  # the orchestrator fills what the action asked for
        world.store.mutate(thread_key("room_a1"), lambda c: seq.record_pending(
            c, "touch", 1, "drafted text", ct(2, 8, 32), "card_1"))
    assert err.value.reason == "no_reservation"
    assert world.thread("room_a1") == before  # the refusal wrote nothing


def test_record_pending_refusal_reasons(world):
    enrol_silent(world)
    world.run(batch(2), fill=False)
    t = world.thread("room_a1")
    with pytest.raises(seq.PendingRefused) as err:
        seq.record_pending(t, "touch", 2, "x", batch(2), "c")
    assert err.value.reason == "reservation_mismatch"
    bad_stage = dict(t, stage="call_booked")
    with pytest.raises(seq.PendingRefused) as err:
        seq.record_pending(bad_stage, "touch", 1, "x", batch(2), "c")
    assert err.value.reason == "stage_not_drafting"
    bad_status = dict(t, status="lost")
    with pytest.raises(seq.PendingRefused) as err:
        seq.record_pending(bad_status, "touch", 1, "x", batch(2), "c")
    assert err.value.reason == "status_not_live"
    ok = seq.record_pending(t, "touch", 1, "x", ct(2, 9), "c")
    assert ok["pending"]["text"] == "x" and ok["pending"]["issued_at"] == iso(batch(2))


# ------------------------------------------------------------ client reply
@pytest.mark.parametrize("label", ["positive", "question", "neutral"])
def test_reply_labels_end_silence_withdraw_touch_and_draft_reply(world, label):
    enrol_silent(world)
    world.run(batch(2))  # T1 pending
    world.say("room_a1", "c2", "client", ct(3, 7), "%s: tell me more" % label)
    acts = acts_for(world.run(batch(3)), "room_a1")
    w = of_type(acts, "withdraw_pending")
    assert w and w[0]["reason"] == "client_replied" and w[0]["pending"]["touch"] == 1
    assert {"type": "status_change", "from": "active", "to": "awaiting_lorenzo", "reason": label} in acts
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    t = world.thread("room_a1")
    assert t["cycles"] == 1 and t["touch_index"] == 0 and t["silence_started_at"] is None
    assert t["pending"]["kind"] == "reply" and t["stage"] == "new_reply"

    world.say("room_a1", "f2", "freelancer", ct(3, 9), "answer")
    acts = acts_for(world.run(ct(3, 10)), "room_a1")
    assert of_type(acts, "sent_detected")[0]["kind"] == "reply"
    t = world.thread("room_a1")
    assert t["status"] == "active" and t["touch_index"] == 0
    assert not drafts(acts_for(world.run(batch(4)), "room_a1"))
    assert drafts(acts_for(world.run(batch(5)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_not_now_with_date_pauses_and_sets_follow_up_later(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: busy until mid October|2026-10-15")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert {"type": "status_change", "from": "active", "to": "paused_not_now", "reason": "not_now"} in acts
    assert {"type": "ghl_stage", "stage": "follow_up_later", "by": "engine"} in acts
    assert not drafts(acts)
    t = world.thread("room_a1")
    assert t["follow_up_at"] == "2026-10-15" and t["stage"] == "follow_up_later"


def test_not_now_without_date_defaults_to_30_ct_days(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: maybe later")
    world.run(ct(1, 23, 30))  # 04:30 UTC the next day; the CT date is still day 1
    assert world.thread("room_a1")["follow_up_at"] == (D0 + timedelta(days=31)).strftime("%Y-%m-%d")


def test_not_now_check_in_fires_on_its_date_then_returns_to_new_reply(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: after launch|2026-10-15")
    world.say("room_a1", "f2", "freelancer", ct(1, 11), "sure, talk then")
    world.run(batch(2))
    fu_mid = CT.localize(datetime(2026, 10, 15)).astimezone(timezone.utc)
    assert not drafts(acts_for(world.run(fu_mid - MIN), "room_a1"))
    fu_batch = fu_mid + timedelta(hours=8, minutes=30)
    acts = acts_for(world.run(fu_batch), "room_a1")
    assert drafts(acts) == [{"type": "draft_checkin", "follow_up_at": "2026-10-15"}]
    assert {"type": "ghl_stage", "stage": "new_reply", "by": "engine"} in acts
    t = world.thread("room_a1")
    assert t["stage"] == "new_reply" and t["pending"]["kind"] == "checkin"
    assert acts_for(world.run(fu_batch), "room_a1") == []  # one check-in only
    world.say("room_a1", "f3", "freelancer", fu_batch + timedelta(minutes=15), "an idea for launch week")
    acts = acts_for(world.run(fu_batch + timedelta(hours=1)), "room_a1")
    assert of_type(acts, "sent_detected")[0]["kind"] == "checkin"
    assert world.thread("room_a1")["status"] == "active"
    assert drafts(acts_for(world.run(fu_batch + timedelta(days=2)), "room_a1")) == [
        {"type": "draft_touch", "touch": 1}]


def test_skipped_check_in_with_the_client_waiting_drafts_a_reply_not_t1(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: ping me later|2026-10-01")
    world.run(batch(2))  # Lorenzo never answers the not_now
    d = (date(2026, 10, 1) - D0).days
    assert drafts(acts_for(world.run(batch(d)), "room_a1"))[0]["type"] == "draft_checkin"
    acts = acts_for(world.run(batch(d + 7)), "room_a1")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "skipped"
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    assert world.thread("room_a1")["status"] == "awaiting_lorenzo"


def test_skipped_check_in_after_lorenzo_answered_restarts_the_ladder(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: ping me later|2026-10-01")
    world.say("room_a1", "f2", "freelancer", ct(1, 11), "will do")
    world.run(batch(2))
    d = (date(2026, 10, 1) - D0).days
    world.run(batch(d))
    acts = acts_for(world.run(batch(d + 7)), "room_a1")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "skipped" and not drafts(acts)
    assert drafts(acts_for(world.run(batch(d + 9)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


@pytest.mark.parametrize("label", ["declined", "hired_other", "not_interested", "hostile"])
def test_lost_labels_mark_lost_and_stop_drafting(world, label):
    enrol_silent(world)
    world.run(batch(2))
    world.say("room_a1", "c2", "client", ct(3, 7), "%s: no thanks" % label)
    acts = acts_for(world.run(batch(3)), "room_a1")
    assert {"type": "status_change", "from": "active", "to": "lost", "reason": label} in acts
    assert {"type": "ghl_stage", "stage": "lost", "by": "engine"} in acts
    assert of_type(acts, "withdraw_pending")
    t = world.thread("room_a1")
    assert t["status"] == "lost" and t["stage"] == "lost" and t["stop_reason"] == label
    for d in (5, 10, 20, 40):
        assert not drafts(acts_for(world.run(batch(d)), "room_a1"))
    world.say("room_a1", "c3", "client", ct(41, 7), "positive: actually it fell through")
    acts = acts_for(world.run(batch(41)), "room_a1")
    # classified only to drop machine text; the label moves nothing on a lost thread
    assert types(acts) == ["classified", "needs_review"] and acts[1]["reason"] == "client_wrote_after_lost"
    assert world.thread("room_a1")["status"] == "lost" and not drafts(acts)


def test_machine_message_is_ignored(world):
    enrol_silent(world)
    world.run(batch(2))
    world.say("room_a1", "c2", "client", ct(2, 10), "machine: I am out of office")
    acts = acts_for(world.run(ct(2, 11)), "room_a1")
    assert types(acts) == ["classified"] and acts[0]["label"] == "machine"
    t = world.thread("room_a1")
    assert t["status"] == "active" and t["cycles"] == 0 and t["pending"]["touch"] == 1
    assert t["last_seen_message_id"] == "c2"


def test_burst_classifies_newest_non_machine(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "question: what stack?")
    world.say("room_a1", "c3", "client", ct(1, 10, 1), "machine: auto-reply")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert [a["message_id"] for a in of_type(acts, "classified")] == ["c3", "c2"]
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]


@pytest.mark.parametrize("raw", ["declined", "not_now", "hostile"])
def test_low_confidence_read_never_moves_the_stage_but_is_surfaced(world, raw):
    enrol_silent(world)

    def low(text, room):
        return {"label": "neutral", "raw_label": raw, "confidence": 0.62, "follow_up_at": None}

    world.say("room_a1", "c2", "client", ct(1, 10), "hmm, we will see")
    acts = acts_for(world.run(batch(2), classify=low), "room_a1")
    review = reviews(acts, "low_confidence")
    assert review and review[0]["raw_label"] == raw and review[0]["label"] == "neutral"
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    t = world.thread("room_a1")
    assert t["status"] == "awaiting_lorenzo" and t["stage"] == "new_reply"
    assert not of_type(acts, "ghl_stage")


def test_sent_history_entries_carry_touch_and_text(world):
    enrol_silent(world)
    world.run(batch(2))
    world.say("room_a1", "f2", "freelancer", ct(2, 9), "idea: " + "x" * 700)
    world.run(ct(2, 10))
    entry = [h for h in world.thread("room_a1")["history"] if h["event"] == "touch_sent"][-1]
    assert entry["touch"] == 1 and entry["at"] == iso(ct(2, 9))
    assert entry["text"].startswith("idea: ") and len(entry["text"]) == seq.TEXT_CAP
    world.say("room_a1", "c2", "client", ct(3, 7), "question: which CRM?")
    world.run(batch(3))
    world.say("room_a1", "f3", "freelancer", ct(3, 9), "the answer I actually sent")
    world.run(ct(3, 10))
    entry = [h for h in world.thread("room_a1")["history"] if h["event"] == "reply_sent"][-1]
    assert entry["text"] == "the answer I actually sent" and "touch" not in entry
    world.run(batch(5))  # T1 of the new silence, filled with "drafted text"
    world.say("room_a1", "f4", "freelancer", ct(5, 9), "")
    world.run(ct(5, 10))
    entry = [h for h in world.thread("room_a1")["history"] if h["event"] == "touch_sent"][-1]
    assert entry["text"] == "drafted text" and entry["touch"] == 1


# ------------------------------------------------------------ room events
def test_room_event_after_lorenzos_message_does_not_freeze_the_ladder(world):
    enrol_silent(world)
    world.event("room_a1", "e1", ct(1, 9))  # "Acme Test Co sent an offer"
    assert world.rooms["room_a1"]["last_side"] == "freelancer"
    acts = acts_for(world.run(batch(1)), "room_a1")
    assert not reviews(acts, "unknown_last_message")
    assert drafts(acts_for(world.run(batch(2)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_room_event_after_a_client_question_still_gets_a_reply(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 8), "question: can we start Monday?")
    world.event("room_a1", "e1", ct(1, 8, 5), "Acme Test Co joined the room")
    acts = acts_for(world.run(batch(1)), "room_a1")
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    assert not reviews(acts, "unknown_last_message")


def test_flagged_events_are_skipped_in_every_decision(world):
    enrol_silent(world)
    world.run(batch(2))  # T1 pending
    # an event mislabelled with a client or freelancer side is still just an event
    for i, side in enumerate(("client", "freelancer")):
        m = msg("e%d" % i, side, ct(2, 10 + i), "Acme Test Co sent an offer")
        m["event"] = True
        world.rooms["room_a1"]["messages"].append(m)
    acts = acts_for(world.run(ct(2, 12)), "room_a1")
    assert acts == [] and world.cls.calls == []  # no classify, no send, no withdraw
    t = world.thread("room_a1")
    assert t["pending"]["touch"] == 1 and t["cycles"] == 0 and t["touch_index"] == 0
    # an event between two client messages does not split the burst
    world.say("room_a1", "c2", "client", ct(3, 7), "question: which plan?")
    world.event("room_a1", "e9", ct(3, 7, 1))
    world.say("room_a1", "c3", "client", ct(3, 7, 2), "machine: auto-reply")
    acts = acts_for(world.run(batch(3)), "room_a1")
    assert [a["message_id"] for a in of_type(acts, "classified")] == ["c3", "c2"]
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]


def test_event_does_not_reset_the_dormant_clock(world):
    world.add(make_room("room_d", msgs=[msg("c1", "client", ct(0, 9), "question: rates?")]))
    world.run(ct(0, 10))
    world.event("room_d", "e1", ct(50, 9))
    world.run(batch(51))
    acts = acts_for(world.run(batch(60)), "room_d")
    assert {"type": "status_change", "from": "awaiting_lorenzo", "to": "dormant",
            "reason": "no_client_message_60_days"} in acts


def test_room_event_at_enrolment(world):
    world.add(make_room("room_e", msgs=[msg("c1", "client", ct(0, 9), "question: rates?")]))
    world.event("room_e", "e1", ct(0, 9, 1))
    acts = acts_for(world.run(ct(0, 10)), "room_e")
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c1"}]


def test_unknown_last_side_holds_drafts_and_surfaces_once(world):
    enrol_silent(world)
    world.run(batch(2))  # T1 pending
    world.say("room_a1", "u1", "unknown", ct(2, 10), "a message we cannot attribute")
    assert world.rooms["room_a1"]["last_side"] == "unknown"
    acts = acts_for(world.run(ct(2, 11)), "room_a1")
    assert types(acts) == ["needs_review"] and acts[0]["reason"] == "unknown_last_message"
    t = world.thread("room_a1")
    assert t["pending"]["touch"] == 1 and t["touch_index"] == 0  # never counted as a send
    assert acts_for(world.run(ct(2, 12)), "room_a1") == []
    world.run(batch(9))  # skipped
    assert not drafts(acts_for(world.run(batch(12)), "room_a1"))
    assert seq.due_summary(world.thread("room_a1"), batch(12))["hold"] is True
    world.say("room_a1", "f2", "freelancer", ct(12, 9), "hello again")
    world.run(ct(12, 10))
    assert drafts(acts_for(world.run(batch(14)), "room_a1")) == [{"type": "draft_touch", "touch": 2}]


# -------------------------------------------------------------------- won
def test_won_mid_sequence_withdraws_pending(world):
    enrol_silent(world)
    world.run(batch(2))
    world.say("room_a1", "f2", "freelancer", ct(2, 9), "t1")
    world.run(batch(4))
    assert world.thread("room_a1")["pending"]["touch"] == 2
    world.rooms["room_a1"]["contract"] = {"contract_id": "ct_1", "status": "ACTIVE"}
    acts = acts_for(world.run(batch(5)), "room_a1")
    w = of_type(acts, "withdraw_pending")
    assert w and w[0]["reason"] == "won" and w[0]["pending"]["touch"] == 2
    assert {"type": "status_change", "from": "active", "to": "won", "reason": "contract_active"} in acts
    assert {"type": "ghl_stage", "stage": "won", "by": "engine"} in acts
    t = world.thread("room_a1")
    assert t["status"] == "won" and t["stage"] == "won" and t["pending"] is None
    assert acts_for(world.run(batch(40)), "room_a1") == []


@pytest.mark.parametrize("status", ["ACTIVE", "ENDED", "CLOSED"])
def test_contracted_rooms_mark_enrolled_threads_won(world, status):
    enrol_silent(world)
    world.run(batch(2))  # T1 pending
    room = world.rooms.pop("room_a1")  # collect.py omits contracted rooms from ``rooms``
    extra = {"contracted_rooms": [
        {"room_id": "room_a1", "contract_id": "ct_1", "status": status, "proposal_id": "prop_a1"},
        {"room_id": "room_never", "contract_id": "ct_2", "status": "ACTIVE", "proposal_id": None}]}
    res = world.run(batch(3), **extra)
    acts = acts_for(res, "room_a1")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "won"
    assert {"type": "status_change", "from": "active", "to": "won",
            "reason": "contract_" + status.lower()} in acts
    assert {"type": "ghl_stage", "stage": "won", "by": "engine"} in acts
    assert acts_for(res, "room_never") is None and world.thread("room_never") is None
    t = world.thread("room_a1")
    assert t["status"] == "won" and t["stage"] == "won" and t["pending"] is None
    assert acts_for(world.run(batch(4), **extra), "room_a1") == []  # idempotent
    assert room["room_id"] == "room_a1"


def test_contracted_room_overrides_a_lorenzo_stage(world):
    enrol_silent(world)
    seq.set_stage(world.store, "room_a1", "call_booked", batch(1))
    world.rooms.pop("room_a1")
    world.run(batch(2), contracted_rooms=[{"room_id": "room_a1", "contract_id": "c", "status": "ACTIVE"}])
    assert world.thread("room_a1")["stage"] == "won"


@pytest.mark.parametrize("status", ["ENDED", "CLOSED"])
def test_ended_or_closed_contract_on_the_room_means_won(world, status):
    enrol_silent(world)
    world.run(batch(2))
    world.rooms["room_a1"]["contract"] = {"contract_id": "ct_9", "status": status}
    acts = acts_for(world.run(batch(3)), "room_a1")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "won"
    assert world.thread("room_a1")["stage"] == "won"


def test_contract_started_offer_means_won(world):
    enrol_silent(world)
    world.rooms["room_a1"]["offer_state"] = "contract_started"
    acts = acts_for(world.run(batch(1)), "room_a1")
    assert {"type": "status_change", "from": "active", "to": "won",
            "reason": "offer_contract_started"} in acts


@pytest.mark.parametrize("stage", ["new_reply", "proposal_sent", "call_booked", "follow_up_later", "lost"])
@pytest.mark.parametrize("by", ["lorenzo", "ghl"])
def test_won_overrides_every_stage(world, stage, by):
    enrol_silent(world)
    seq.set_stage(world.store, "room_a1", stage, batch(1), by=by)
    world.rooms["room_a1"]["contract"] = {"contract_id": "ct_1", "status": "ACTIVE"}
    acts = acts_for(world.run(batch(2)), "room_a1")
    t = world.thread("room_a1")
    assert t["stage"] == "won" and t["status"] == "won"
    assert {"type": "ghl_stage", "stage": "won", "by": "engine"} in acts


# ------------------------------------------------------- close-out / cycles
def test_cycle_count_and_max_cycles_close_out_on_t7(world):
    enrol_silent(world)
    for c in range(1, 4):
        world.say("room_a1", "c%d" % (c + 1), "client", ct(c, 7), "question: cycle %d" % c)
        world.run(batch(c))
        world.say("room_a1", "fr%d" % c, "freelancer", ct(c, 9), "answer %d" % c)
        world.run(ct(c, 10))
        assert world.thread("room_a1")["cycles"] == c
    t = world.thread("room_a1")
    assert t["cycles"] == seq.MAX_CYCLES and t["status"] == "active"
    t["touch_index"] = 6
    seq._reserve(t, "touch", 7, batch(5))
    world.store.set(thread_key("room_a1"), t)
    world.say("room_a1", "f7", "freelancer", ct(5, 9), "close-out sent")
    acts = acts_for(world.run(ct(5, 10)), "room_a1")
    assert {"type": "status_change", "from": "active", "to": "closed_out", "reason": "max_cycles"} in acts
    assert world.thread("room_a1")["stage"] == "lost"


def test_client_reply_after_close_out_reopens(world):
    enrol_silent(world)
    t = world.thread("room_a1")
    t["touch_index"] = 7
    t["silence_started_at"] = iso(ct(1, 9))
    world.store.set(thread_key("room_a1"), t)
    assert "status_change" not in types(acts_for(world.run(batch(14)), "room_a1"))
    world.run(batch(15))
    assert world.thread("room_a1")["status"] == "closed_out"
    world.say("room_a1", "c2", "client", ct(16, 7), "positive: sorry, back now")
    acts = acts_for(world.run(batch(16)), "room_a1")
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    t = world.thread("room_a1")
    assert t["status"] == "awaiting_lorenzo" and t["stage"] == "new_reply"


# --------------------------------------------------------------- dormant
def test_dormant_after_60_ct_days_without_client_message(world):
    world.add(make_room("room_d1", msgs=[msg("c1", "client", ct(0, 20), "question: can you start soon?")]))
    acts = acts_for(world.run(ct(0, 21)), "room_d1")
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c1"}]
    world.run(batch(7))  # the reply expired unsent: drafted once more
    world.run(batch(14))  # expired again: no redraft, Lorenzo never answered
    assert world.thread("room_d1")["pending"] is None
    assert not drafts(acts_for(world.run(batch(20)), "room_d1"))
    assert "status_change" not in types(acts_for(world.run(midnight(60) - MIN), "room_d1"))
    acts = acts_for(world.run(batch(60)), "room_d1")
    assert {"type": "status_change", "from": "awaiting_lorenzo", "to": "dormant",
            "reason": "no_client_message_60_days"} in acts
    assert {"type": "ghl_stage", "stage": "lost", "by": "engine"} in acts


# -------------------------------------------------------------- enrolment
def test_first_run_revivable_versus_normal_enrolment(world):
    world.add(make_room("room_old", msgs=[msg("c1", "client", ct(-50), "positive: hi"),
                                          msg("f1", "freelancer", ct(-49), "hello")]))
    world.add(make_room("room_new", msgs=[msg("c1", "client", ct(-10), "positive: hi"),
                                          msg("f1", "freelancer", ct(-9), "hello")]))
    res = world.run(batch(0))
    old = acts_for(res, "room_old")
    assert types(old) == ["revivable"] and old[0]["last_client_at"] == iso(ct(-50))
    assert "enrolled" in types(acts_for(res, "room_new"))
    assert world.thread("room_old") is None
    meta = world.store.get(seq.META_KEY)
    assert meta["first_run_at"] == iso(batch(0)) and "room_old" in meta["revivable"]
    assert world.store.keys("upwork:") == ["upwork:room_new"]  # meta lives outside the prefix

    assert acts_for(world.run(batch(1)), "room_old") is None
    assert world.thread("room_old") is None

    world.add(make_room("room_mid", msgs=[msg("c1", "client", ct(-49), "positive: hi"),
                                          msg("f1", "freelancer", ct(-48), "hello")]))
    world.add(make_room("room_ancient", msgs=[msg("c1", "client", ct(-70), "positive: hi"),
                                              msg("f1", "freelancer", ct(-5), "hello")]))
    res = world.run(ct(1, 10))
    assert "enrolled" in types(acts_for(res, "room_mid"))
    assert types(acts_for(res, "room_ancient")) == ["revivable"]

    world.say("room_old", "c2", "client", ct(2, 7), "question: still available?")
    acts = acts_for(world.run(batch(2)), "room_old")
    assert "enrolled" in types(acts) and drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]


def test_first_run_detection_and_enroll_before_the_first_tick(tmp_path):
    w = World(tmp_path)
    w.add(make_room("room_old", msgs=[msg("c1", "client", ct(-50), "positive: hi")]))
    w.add(make_room("room_hand", msgs=[msg("c1", "client", ct(-80), "positive: hi")]))
    seq.enroll(w.store, w.rooms["room_hand"], batch(0) - MIN)  # --enroll before any tick
    res = w.run(batch(0))
    assert types(acts_for(res, "room_old")) == ["revivable"]  # still the first run
    assert w.thread("room_hand")["enrolled_by"] == "manual"

    w2 = World(tmp_path / "second")
    w2.add(make_room("room_old", msgs=[msg("c1", "client", ct(-50), "positive: hi")]))
    assert "enrolled" in types(acts_for(w2.run(batch(0), first_run=False), "room_old"))


def test_legacy_meta_key_is_migrated(tmp_path):
    w = World(tmp_path)
    w.store.set("upwork:meta", {"first_run_at": iso(ct(-5)),
                                "revivable": {"room_old": {"listed_at": iso(ct(-5))}}})
    w.add(make_room("room_old", msgs=[msg("c1", "client", ct(-50), "positive: hi")]))
    res = w.run(batch(0))
    assert acts_for(res, "room_old") is None and w.thread("room_old") is None
    assert w.store.get("upwork:meta") is None
    meta = w.store.get(seq.META_KEY)
    assert meta["first_run_at"] == iso(ct(-5)) and "room_old" in meta["revivable"]


@pytest.mark.parametrize("room_kwargs,reason", [
    ({"proposal_id": None, "origin": "invitation"}, "no_proposal"),
    ({"proposal_id": None, "origin": "unknown"}, "no_proposal"),
    ({"proposal_id": None, "origin": "proposal"}, "no_proposal"),
    ({"contract": {"contract_id": "ct", "status": "ACTIVE"}}, "has_contract"),
    ({"contract": {"contract_id": "ct", "status": "ENDED"}}, "has_contract"),
    ({"contract": {"contract_id": "ct", "status": "CLOSED"}}, "has_contract"),
    ({"contract": {"contract_id": "ct", "status": "PAUSED"}}, "has_contract"),
    ({"offer_state": "contract_started"}, "offer_contract_started"),
    ({"msgs": [msg("f1", "freelancer", ct(-1), "hi")]}, "no_client_message"),
])
def test_eligibility_rules(room_kwargs, reason):
    assert seq.eligible(make_room(**room_kwargs), batch(0), first_run=False) == (False, reason)


def test_revivable_age_counts_ct_days():
    room = make_room(msgs=[msg("c1", "client", ct(-45, 23, 59), "positive: hi")])
    assert seq.eligible(room, batch(0), first_run=True) == (True, "eligible")
    room = make_room(msgs=[msg("c1", "client", ct(-46, 0, 1), "positive: hi")])
    assert seq.eligible(room, batch(0), first_run=True) == (False, "revivable")


def test_invitation_only_rooms_are_never_enrolled(world):
    world.add(make_room("room_inv", proposal_id=None, origin="invitation",
                        msgs=[msg("c1", "client", ct(-1), "positive: I invited you")]))
    for d in (0, 1, 30):
        assert acts_for(world.run(batch(d)), "room_inv") is None
    assert world.thread("room_inv") is None
    with pytest.raises(ValueError):
        seq.enroll(world.store, world.rooms["room_inv"], batch(31))


# ---------------------------------------------------------- CLI helpers
def test_manual_stop_resume_and_enroll(world):
    enrol_silent(world)
    world.run(batch(2))
    t, acts = seq.stop(world.store, "room_a1", ct(2, 9), "lorenzo said so")
    assert t["status"] == "stopped" and t["pending"] is None
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "stopped"
    for d in (5, 10, 30):
        assert not drafts(acts_for(world.run(batch(d)), "room_a1"))

    t, acts = seq.resume(world.store, "room_a1", ct(31, 9))
    assert t["status"] == "active" and t["touch_index"] == 0 and t["silence_started_at"] == iso(ct(31, 9))
    assert not drafts(acts_for(world.run(batch(32)), "room_a1"))
    assert drafts(acts_for(world.run(batch(33)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]
    with pytest.raises(ValueError):
        seq.resume(world.store, "room_a1", batch(34))
    with pytest.raises(seq.ThreadNotFound):
        seq.stop(world.store, "room_nope", batch(34))

    world.add(make_room("room_old", msgs=[msg("c1", "client", ct(-50), "positive: hi"),
                                          msg("f1", "freelancer", ct(-49), "hello")]))
    world.store.mutate(seq.META_KEY, lambda m: dict(m or {}, revivable={"room_old": {"listed_at": iso(batch(0))}}))
    t, acts = seq.enroll(world.store, world.rooms["room_old"], ct(34, 9))
    assert t["enrolled_by"] == "manual" and acts == [{"type": "enrolled", "by": "manual"}]
    assert "room_old" not in world.store.get(seq.META_KEY)["revivable"]
    acts = acts_for(world.run(ct(34, 10)), "room_old")
    assert drafts(acts) == [{"type": "draft_touch", "touch": 1}]
    assert world.thread("room_old")["status"] == "active"  # not instantly dormant
    with pytest.raises(ValueError):
        seq.enroll(world.store, world.rooms["room_old"], batch(35))


def test_resume_with_the_client_waiting_drafts_a_reply(world):
    enrol_silent(world)
    seq.stop(world.store, "room_a1", batch(1))
    world.say("room_a1", "c2", "client", ct(2, 7), "question: are you still on this?")
    world.run(batch(2))
    t, _acts = seq.resume(world.store, "room_a1", ct(3, 7))
    assert t["status"] == "awaiting_lorenzo"
    assert drafts(acts_for(world.run(batch(3)), "room_a1")) == [{"type": "draft_reply", "message_id": "c2"}]


# --------------------------------------------------------------- idempotency
def test_second_run_on_same_snapshot_and_time_is_a_no_op(world):
    world.add(make_room("room_touch"))
    world.add(make_room("room_reply", msgs=[msg("c1", "client", ct(-1), "question: price range?")]))
    world.add(make_room("room_pause", msgs=[msg("f0", "freelancer", ct(-3), "hi"),
                                            msg("c1", "client", ct(-1), "not_now: later")]))
    world.add(make_room("room_unk", msgs=[msg("c1", "client", ct(-2), "positive: ok"),
                                          msg("u1", "unknown", ct(-1), "?")]))
    world.add(make_room("room_old", msgs=[msg("c1", "client", ct(-90), "positive: hi")]))
    world.add(make_room("room_offer", offer_state="awaiting_your_acceptance"))
    world.run(batch(0))
    first = world.run(batch(3))
    assert any(drafts(a) for _r, _t, a in first)
    before = json.loads(json.dumps({k: world.store.get(k) for k in world.store.keys("upwork")}))
    calls = len(world.cls.calls)
    second = world.run(batch(3))
    assert all(a == [] for _r, _t, a in second), [(r["room_id"], a) for r, _t, a in second if a]
    after = {k: world.store.get(k) for k in world.store.keys("upwork")}
    assert after == before
    assert len(world.cls.calls) == calls


# ----------------------------------------------------------------- draft cap
def test_max_new_drafts_cap_orders_replies_then_oldest_silence(world):
    for i in range(12):
        rid = "room_s%02d" % i
        world.add(make_room(rid, msgs=[msg("c1", "client", ct(-20), "positive: hi"),
                                       msg("f1", "freelancer", ct(-10, 1 + i), "hello")]))
    world.add(make_room("room_reply", msgs=[msg("c1", "client", ct(-1), "question: when?")]))
    res = world.run(batch(0))
    drafted = [r["room_id"] for r, _t, a in res if drafts(a)]
    deferred = [r["room_id"] for r, _t, a in res if of_type(a, "deferred")]
    assert len(drafted) == seq.MAX_NEW_DRAFTS_PER_RUN
    assert drafted[0] == "room_reply"
    assert drafted[1:] == ["room_s%02d" % i for i in range(9)]
    assert deferred == ["room_s09", "room_s10", "room_s11"]
    assert of_type(acts_for(res, "room_s10"), "deferred")[0]["draft"] == {"type": "draft_touch", "touch": 1}
    assert world.thread("room_s10")["pending"] is None
    res = world.run(ct(0, 14))  # deferred drafts are retried next run
    assert sorted(r["room_id"] for r, _t, a in res if drafts(a)) == deferred


def test_manual_enrol_sorts_by_its_room_not_last(world):
    for i in range(10):
        world.add(make_room("room_s%02d" % i, msgs=[msg("c1", "client", ct(-20), "positive: hi"),
                                                   msg("f1", "freelancer", ct(-10, 1 + i), "hello")]))
    world.run(ct(-10, 23), first_run=False)  # enrol all ten before anything is due
    hand = make_room("room_hand", msgs=[msg("c1", "client", ct(-30), "positive: hi"),
                                        msg("f1", "freelancer", ct(-15), "hello")])
    world.add(hand)
    seq.enroll(world.store, hand, ct(-10, 23, 30))
    res = world.run(batch(0))
    drafted = [r["room_id"] for r, _t, a in res if drafts(a)]
    assert drafted[0] == "room_hand"  # the oldest silence, although never advanced before
    assert of_type(acts_for(res, "room_s09"), "deferred")


# ------------------------------------------------------------- isolation
class FlakyStore(JsonFileStore):
    def __init__(self, path, bad_keys, ops=("mutate",)):
        super(FlakyStore, self).__init__(path)
        self.bad_keys = set(bad_keys)
        self.ops = ops

    def _check(self, op, key):
        if op in self.ops and key in self.bad_keys:
            raise StoreError("could not acquire the store lock for %r" % key)

    def mutate(self, key, fn, default=None):
        self._check("mutate", key)
        return super(FlakyStore, self).mutate(key, fn, default)

    def get(self, key, default=None):
        self._check("get", key)
        return super(FlakyStore, self).get(key, default)


def test_store_error_on_one_thread_does_not_stop_the_others(tmp_path):
    world = World(tmp_path, store=FlakyStore(tmp_path / "store.json", [thread_key("room_b")]))
    for rid in ("room_a", "room_b", "room_c"):
        world.add(make_room(rid))
    res = world.run(batch(2))
    b = acts_for(res, "room_b")
    assert b and b[0]["type"] == "error" and b[0]["error_type"] == "StoreError"
    for rid in ("room_a", "room_c"):
        assert drafts(acts_for(res, rid)) == [{"type": "draft_touch", "touch": 1}]
    assert world.store.get(thread_key("room_b"), None) is None


def test_corrupt_thread_record_is_that_rooms_error(world):
    world.add(make_room("room_a"))
    world.add(make_room("room_b"))
    world.store.set(thread_key("room_b"), "not a thread")
    res = world.run(batch(2))
    b = acts_for(res, "room_b")
    assert b[0]["type"] == "error" and b[0]["error_type"] == "BadRecord"
    assert drafts(acts_for(res, "room_a")) == [{"type": "draft_touch", "touch": 1}]
    assert world.store.get(thread_key("room_b")) == "not a thread"


@pytest.mark.parametrize("ops", [("mutate",), ("get",), ("get", "mutate")])
def test_meta_store_error_degrades_without_mass_enrolment(tmp_path, ops):
    good = World(tmp_path / "setup")
    good.add(make_room("room_a"))
    good.run(ct(0, 14, 5))  # room_a enrolled while the meta record worked
    store = FlakyStore(good.store.path, [seq.META_KEY], ops=ops)
    world = World(tmp_path, store=store)
    world.add(make_room("room_a"))
    world.add(make_room("room_new"))
    world.add(make_room("room_old", msgs=[msg("c1", "client", ct(-50), "positive: hi")]))
    res = world.run(batch(2))  # does not raise
    assert drafts(acts_for(res, "room_a")) == [{"type": "draft_touch", "touch": 1}]
    for rid in ("room_new", "room_old"):  # not-first-run fallback, and nobody is enrolled
        assert acts_for(res, rid)[0]["error_type"] == "MetaUnavailable"
        assert world.thread(rid) is None
    assert not any("enrolled" in types(a) for _r, _t, a in res)


def test_classifier_failure_is_isolated_and_writes_nothing(world):
    enrol_silent(world, "room_a")
    world.add(make_room("room_b"))
    world.run(batch(1))
    before = world.thread("room_a")
    world.say("room_a", "c2", "client", ct(1, 10), "positive: hi")

    def boom(text, room):
        if room["room_id"] == "room_a":
            raise RuntimeError("llm down")
        return FakeClassify()(text, room)

    res = world.run(batch(2), classify=boom)
    assert acts_for(res, "room_a")[0]["type"] == "error"
    assert world.thread("room_a") == before
    assert drafts(acts_for(res, "room_b")) == [{"type": "draft_touch", "touch": 1}]


# ------------------------------------------------------------- history cap
def test_history_capped_at_50_keeping_newest():
    room = make_room()
    t = seq.new_thread(room, batch(0), "auto")
    t["history"] = [{"at": iso(batch(0)), "event": "old", "n": i} for i in range(60)]
    seq._reserve(t, "touch", 1, batch(1))
    assert len(t["history"]) == seq.HISTORY_CAP
    assert t["history"][-1]["event"] == "draft_reserved" and t["history"][0]["n"] == 11
    t = seq.record_pending(t, "touch", 1, "text", batch(1), "card1")
    assert len(t["history"]) == seq.HISTORY_CAP and t["history"][-1]["event"] == "drafted"
    t2, _acts = seq.advance(t, room, batch(20), FakeClassify())
    assert len(t2["history"]) == seq.HISTORY_CAP
    assert t2["history"][-1]["event"] != "old"


# --------------------------------------------------------- missing messages
def test_missing_messages_freeze_only_the_listed_rooms(world):
    enrol_silent(world, "room_a")
    enrol_silent(world, "room_b")
    world.run(batch(2))  # both T1 pending
    res = world.run(batch(6), messages=False, missing_messages=["room_b"])
    assert types(acts_for(res, "room_a")) == ["resurface"]
    b = acts_for(res, "room_b")
    assert types(b) == ["needs_review"] and b[0]["reason"] == "messages_missing"
    assert world.thread("room_b")["pending"]["resurfaced_at"] is None  # not advanced
    assert acts_for(world.run(ct(6, 9), messages=False, missing_messages=["room_b"]), "room_b") == []
    assert types(acts_for(world.run(ct(6, 10), missing_messages=[]), "room_b")) == ["resurface"]


def test_global_flag_never_freezes_every_room(world):
    enrol_silent(world)
    world.run(batch(2))
    assert types(acts_for(world.run(batch(6), messages=False), "room_a1")) == ["resurface"]


def test_null_messages_freeze_that_room_alone(world):
    enrol_silent(world, "room_a")
    enrol_silent(world, "room_b")
    world.run(batch(2))
    world.rooms["room_b"]["messages"] = None  # not pulled; not in missing_messages either
    res = world.run(batch(6), messages=False)
    assert types(acts_for(res, "room_a")) == ["resurface"]
    b = acts_for(res, "room_b")
    assert types(b) == ["needs_review"] and b[0]["reason"] == "messages_missing"
    assert acts_for(world.run(ct(6, 9)), "room_b") == []


def test_missing_messages_never_enrol_a_new_room(world):
    world.add(make_room("room_x"))
    assert acts_for(world.run(batch(0), missing_messages=["room_x"]), "room_x") is None
    assert world.thread("room_x") is None


def test_live_thread_missing_from_the_snapshot_is_surfaced_weekly(world):
    enrol_silent(world)
    enrol_silent(world, "room_dead")
    world.store.mutate(thread_key("room_dead"), lambda t: dict(t, status="lost"))
    before = world.thread("room_a1")
    del world.rooms["room_a1"]
    del world.rooms["room_dead"]
    res = world.run(batch(10))
    assert acts_for(res, "room_dead") is None
    acts = acts_for(res, "room_a1")
    assert types(acts) == ["needs_review"] and acts[0]["reason"] == "not_in_pull"
    after = world.thread("room_a1")
    assert after["pending"] == before["pending"] and after["touch_index"] == before["touch_index"]
    assert acts_for(world.run(batch(16)), "room_a1") is None
    assert types(acts_for(world.run(batch(17)), "room_a1")) == ["needs_review"]


# ------------------------------------------------------------------ stages
def test_lorenzo_stage_is_respected_when_a_client_reply_would_auto_move(world):
    enrol_silent(world)
    t, acts = seq.set_stage(world.store, "room_a1", "call_booked", batch(1))
    assert t["stage"] == "call_booked" and t["stage_set_by"] == "lorenzo"
    world.say("room_a1", "c2", "client", ct(2, 7), "not_now: after the holidays|2026-10-20")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert not of_type(acts, "ghl_stage") and not of_type(acts, "stage_change")
    kept = reviews(acts, "stage_kept")
    assert kept and kept[0]["label"] == "not_now" and kept[0]["stage"] == "call_booked"
    t = world.thread("room_a1")
    assert t["stage"] == "call_booked" and t["status"] == "paused_not_now"
    assert not drafts(acts_for(world.run(batch((date(2026, 10, 20) - D0).days)), "room_a1"))


@pytest.mark.parametrize("label", ["declined", "hired_other", "not_interested", "hostile", "not_now"])
@pytest.mark.parametrize("by", ["lorenzo", "ghl"])
def test_a_label_never_stops_drafting_in_a_lorenzo_drafting_stage(world, label, by):
    enrol_silent(world)
    seq.set_stage(world.store, "room_a1", "proposal_sent", batch(1), by=by)
    world.say("room_a1", "c2", "client", ct(2, 7), "%s: went another way" % label)
    acts = acts_for(world.run(batch(2)), "room_a1")
    kept = reviews(acts, "stage_kept")
    assert kept and kept[0]["label"] == label and kept[0]["stage"] == "proposal_sent"
    assert kept[0]["set_by"] == by
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    t = world.thread("room_a1")
    assert t["status"] == "awaiting_lorenzo" and t["stage"] == "proposal_sent"
    assert not of_type(acts, "ghl_stage")
    world.say("room_a1", "f2", "freelancer", ct(2, 9), "understood, one question")
    world.run(ct(2, 10))
    assert drafts(acts_for(world.run(batch(4)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_lost_label_under_a_lorenzo_call_booked_is_surfaced(world):
    enrol_silent(world)
    seq.set_stage(world.store, "room_a1", "call_booked", batch(1))
    world.say("room_a1", "c2", "client", ct(2, 7), "declined: cancelling the call")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert reviews(acts, "stage_kept") and not drafts(acts)
    t = world.thread("room_a1")
    assert t["status"] == "lost" and t["stage"] == "call_booked"


@pytest.mark.parametrize("stage", ["call_booked", "lost", "won", "follow_up_later"])
def test_no_draft_in_a_non_drafting_stage(world, stage):
    enrol_silent(world)
    world.run(batch(2))
    _t, acts = seq.set_stage(world.store, "room_a1", stage, ct(2, 9))
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "stage_" + stage
    for d in (3, 5, 9, 12, 20):
        assert not drafts(acts_for(world.run(batch(d)), "room_a1"))
    world.say("room_a1", "c2", "client", ct(21, 7), "question: are you there?")
    assert not drafts(acts_for(world.run(batch(21)), "room_a1"))
    assert seq.due_summary(world.thread("room_a1"), batch(22))["draft_now"] is False


def test_lorenzo_follow_up_later_check_in_fires_on_its_date(world):
    enrol_silent(world)
    t, _acts = seq.set_stage(world.store, "room_a1", "follow_up_later", batch(1))
    fu = t["follow_up_at"]
    assert fu == (D0 + timedelta(days=31)).strftime("%Y-%m-%d") and t["status"] == "paused_not_now"
    s = seq.due_summary(world.thread("room_a1"), midnight(31) - MIN)
    assert s["kind"] == "checkin" and s["draft_now"] is False and s["next_due_at"] == iso(midnight(31))
    assert not drafts(acts_for(world.run(batch(30)), "room_a1"))
    acts = acts_for(world.run(batch(31)), "room_a1")
    assert drafts(acts) == [{"type": "draft_checkin", "follow_up_at": fu}]
    assert {"type": "stage_change", "from": "follow_up_later", "to": "new_reply", "by": "engine",
            "reason": "checkin_due"} in acts
    assert world.thread("room_a1")["stage"] == "new_reply"


def test_follow_up_later_on_a_t7_thread_never_closes_out_and_checks_in_once(world):
    enrol_silent(world)
    t = world.thread("room_a1")
    t["touch_index"] = 7
    t["silence_started_at"] = iso(ct(1, 9))
    world.store.set(thread_key("room_a1"), t)
    t, _ = seq.set_stage(world.store, "room_a1", "follow_up_later", batch(2))
    assert t["status"] == "paused_not_now"
    checkins, statuses = 0, set()
    for d in range(3, 50):
        acts = acts_for(world.run(batch(d)), "room_a1")
        checkins += len([a for a in drafts(acts) if a["type"] == "draft_checkin"])
        statuses.update(a["to"] for a in of_type(acts, "status_change"))
    assert checkins == 1
    assert "closed_out" not in statuses


def test_lorenzo_follow_up_later_on_a_lost_thread_gets_its_check_in(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 7), "declined: not now, not ever")
    world.say("room_a1", "f2", "freelancer", ct(1, 8), "understood")
    world.run(batch(1))
    t, _acts = seq.set_stage(world.store, "room_a1", "follow_up_later", batch(2))
    assert t["status"] == "paused_not_now"
    assert drafts(acts_for(world.run(batch(32)), "room_a1")) == [
        {"type": "draft_checkin", "follow_up_at": t["follow_up_at"]}]


def test_move_back_to_drafting_answers_a_waiting_client(world):
    enrol_silent(world)
    seq.set_stage(world.store, "room_a1", "lost", batch(1))
    world.say("room_a1", "c2", "client", ct(3, 7), "question: is this still possible?")
    acts = acts_for(world.run(batch(3)), "room_a1")
    assert reviews(acts, "client_wrote_after_lost") and not drafts(acts)
    t, acts = seq.set_stage(world.store, "room_a1", "new_reply", ct(4, 7))
    assert t["status"] == "awaiting_lorenzo"
    assert drafts(acts_for(world.run(batch(4)), "room_a1")) == [{"type": "draft_reply", "message_id": "c2"}]


def test_move_back_to_drafting_without_a_waiting_client_starts_a_silence(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 7), "hired_other: went with someone")
    world.say("room_a1", "f2", "freelancer", ct(1, 8), "good luck")
    world.run(batch(1))
    assert world.thread("room_a1")["status"] == "lost"
    t, acts = seq.set_stage(world.store, "room_a1", "new_reply", ct(5, 7))
    assert t["status"] == "active" and t["silence_started_at"] == iso(ct(5, 7))
    assert drafts(acts_for(world.run(batch(7)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_lorenzo_and_ghl_moves_never_emit_ghl_stage(world):
    enrol_silent(world)
    _t, acts = seq.set_stage(world.store, "room_a1", "call_booked", batch(1))
    assert of_type(acts, "stage_change") == [{"type": "stage_change", "from": "new_reply", "to": "call_booked",
                                              "by": "lorenzo", "reason": "set_by_lorenzo"}]
    assert not of_type(acts, "ghl_stage")
    _t, acts = seq.apply_external_stage(world.thread("room_a1"), "proposal_sent", batch(2))
    assert of_type(acts, "stage_change") and not of_type(acts, "ghl_stage")
    seq.stop(world.store, "room_a1", batch(3))
    _t, acts = seq.resume(world.store, "room_a1", batch(4))
    assert not of_type(acts, "ghl_stage")


def test_ghl_read_back_wins_and_does_not_echo(world):
    enrol_silent(world)
    t = world.thread("room_a1")
    same, acts = seq.apply_external_stage(t, "new_reply", batch(1))
    assert acts == [] and same["stage_set_by"] == "engine"  # our own push coming back
    t2, acts = seq.apply_external_stage(t, "call_booked", batch(1))
    assert t2["stage"] == "call_booked" and t2["stage_set_by"] == "ghl"
    world.store.set(thread_key("room_a1"), t2)
    world.rooms["room_a1"]["offer_state"] = "awaiting_your_acceptance"
    world.say("room_a1", "c2", "client", ct(2, 7), "not_now: next quarter")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert not of_type(acts, "stage_change") and not of_type(acts, "ghl_stage")
    assert world.thread("room_a1")["stage"] == "call_booked"
    t3, acts = seq.apply_external_stage(world.thread("room_a1"), "new_reply", batch(3))
    assert t3["stage_set_by"] == "ghl" and t3["status"] == "awaiting_lorenzo"  # the not_now is unanswered
    with pytest.raises(ValueError):
        seq.apply_external_stage(t3, "maybe", batch(3))


def test_offer_awaiting_acceptance_moves_new_reply_to_proposal_sent(world):
    world.add(make_room("room_o", offer_state="awaiting_your_acceptance"))
    acts = acts_for(world.run(ct(0, 14, 5)), "room_o")
    assert {"type": "ghl_stage", "stage": "proposal_sent", "by": "engine"} in acts
    assert world.thread("room_o")["stage"] == "proposal_sent"
    assert drafts(acts_for(world.run(batch(2)), "room_o")) == [{"type": "draft_touch", "touch": 1}]


def test_offer_does_not_override_a_lorenzo_new_reply(world):
    enrol_silent(world)
    _t, acts = seq.set_stage(world.store, "room_a1", "new_reply", batch(1))
    assert acts == [] and world.thread("room_a1")["stage_set_by"] == "lorenzo"
    world.rooms["room_a1"]["offer_state"] = "awaiting_your_acceptance"
    world.run(ct(1, 9))
    assert world.thread("room_a1")["stage"] == "new_reply"


def test_set_stage_validates(world):
    enrol_silent(world)
    with pytest.raises(ValueError):
        seq.set_stage(world.store, "room_a1", "booked", batch(1))
    with pytest.raises(ValueError):
        seq.set_stage(world.store, "room_a1", "lost", batch(1), by="engine")
    with pytest.raises(seq.ThreadNotFound):
        seq.set_stage(world.store, "room_none", "lost", batch(1))


def test_due_summary_lists_next_due_for_drafting_stages(world):
    enrol_silent(world)
    s = seq.due_summary(world.thread("room_a1"), batch(1))
    assert s == {"stage": "new_reply", "status": "active", "draft_now": False, "kind": "touch",
                 "touch": 1, "next_due_at": iso(midnight(2)), "pending": False, "hold": False,
                 "waiting_since": None, "skipped_at": None}
    assert seq.due_summary(world.thread("room_a1"), batch(2))["draft_now"] is True
    world.run(batch(2))
    s = seq.due_summary(world.thread("room_a1"), batch(2))
    assert s["pending"] is True and s["draft_now"] is False and s["kind"] == "touch"


# --------------------------------------------------------------- pending API
def test_clear_pending_retry_redrafts_the_reply(world):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 7), "question: budget?")
    world.run(batch(1))
    t = world.thread("room_a1")
    assert t["pending"]["kind"] == "reply" and t["pending"]["text"] == "drafted text"
    world.store.set(thread_key("room_a1"), seq.clear_pending(t, ct(1, 9), "draft_failed", retry=True))
    assert drafts(acts_for(world.run(ct(1, 10)), "room_a1")) == [
        {"type": "draft_reply", "message_id": "c2"}]


def test_thread_keeps_proposal_and_job_ids_from_the_room(world):
    room = make_room("room_p")
    room["job_id"] = "~02job_one"
    world.add(room)
    world.run(ct(0, 14, 5))
    t = world.thread("room_p")
    assert t["proposal_id"] == "prop_a1" and t["job_id"] == "~02job_one"
    assert seq.new_thread(room, batch(0))["proposal_id"] == "prop_a1"
    # backfill a thread written before the fields existed
    world.store.mutate(thread_key("room_p"), lambda c: {k: v for k, v in c.items()
                                                         if k not in ("proposal_id", "job_id")})
    world.run(batch(1))
    t = world.thread("room_p")
    assert t["proposal_id"] == "prop_a1" and t["job_id"] == "~02job_one"
    # a different non-null value replaces it, with a history note
    world.rooms["room_p"]["proposal_id"] = "prop_b2"
    world.run(ct(1, 9))
    t = world.thread("room_p")
    assert t["proposal_id"] == "prop_b2"
    note = [h for h in t["history"] if h["event"] == "proposal_id_changed"][-1]
    assert note["old"] == "prop_a1" and note["new"] == "prop_b2"
    # a null in the room never erases it, and nothing is re-noted
    world.rooms["room_p"]["proposal_id"] = None
    world.rooms["room_p"]["job_id"] = None
    world.run(ct(1, 10))
    t = world.thread("room_p")
    assert t["proposal_id"] == "prop_b2" and t["job_id"] == "~02job_one"
    assert len([h for h in t["history"] if h["event"].endswith("_changed")]) == 1


def test_reads_collect_room_shape_event_false_and_null_messages(world):
    enrol_silent(world, "room_a")
    enrol_silent(world, "room_b")
    for room in world.rooms.values():
        for m in room["messages"]:
            m["event"] = False  # collect.py writes the key on every message
    world.say("room_a", "c2", "client", ct(1, 7), "question: can we talk?")
    world.rooms["room_a"]["messages"][-1]["event"] = False
    world.rooms["room_b"]["messages"] = None
    res = world.run(batch(1), messages=False, missing_messages=sorted(["room_b"]))
    assert drafts(acts_for(res, "room_a")) == [{"type": "draft_reply", "message_id": "c2"}]
    assert reviews(acts_for(res, "room_b"), "messages_missing")


def test_module_has_no_upwork_write_path():
    import inspect
    src = inspect.getsource(seq)
    for name in ("send_message", "manage_proposals", "respond_to_offer", "manage_meetings",
                 "submit_milestones", "boost_profile", "manage_offers", "update_profile"):
        assert name not in src


# ======================================================================
# Round 3: same-time idempotency, silence boundaries, skipped replies,
# blocked rooms, the 60-day edge, and the history reference in DESIGN.md.
# ======================================================================
class MemStore(object):
    """The Store calls sequence makes (get/set/delete/keys/mutate), in memory.
    Values round-trip through JSON like JsonFileStore, so ``data`` compares
    exactly what a real store would hold."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return json.loads(self.data[key]) if key in self.data else default

    def set(self, key, value):
        self.data[key] = json.dumps(value, sort_keys=True)

    def delete(self, key):
        self.data.pop(key, None)

    def keys(self, prefix=""):
        return sorted(k for k in self.data if k.startswith(prefix))

    def mutate(self, key, fn, default=None):
        value = fn(self.get(key, default))
        self.set(key, value)
        return value


def fill_all(store, when):
    """The healthy tick: every unfilled reservation gets its text and card id
    (a refusal is skipped, as tick.py does)."""
    for key in store.keys(seq.PREFIX):
        cur = store.get(key)
        p = cur.get("pending") if isinstance(cur, dict) else None
        if p and p.get("text") is None and p.get("card_id") is None:
            try:
                store.mutate(key, lambda c, p=p: seq.record_pending(c, p["kind"], p["touch"], "drafted text",
                                                                     when, "card"))
            except seq.PendingRefused:
                pass


def ct_day(when):
    return when.astimezone(CT).strftime("%Y-%m-%d")


def engine_overrides(before, acts):
    """Engine stage moves that overrode a stage Lorenzo or GHL held at that
    moment. The owner is tracked through the run: after the forced check-in
    return (engine, ``checkin_due``) the stage is the engine's again, so the
    offer promotion that follows it in the same run is allowed."""
    owner = (before or {}).get("stage_set_by", "engine")
    bad = []
    for a in acts:
        if a["type"] != "stage_change":
            continue
        if a["by"] == "engine" and owner in seq.MANUAL_SETTERS and a["to"] != "won" \
                and a["reason"] != "checkin_due":
            bad.append(a)
        owner = a["by"]
    return bad


def action_problems(before, thread, room, acts):
    """What a single run must never do, whatever the stored state was."""
    out = []
    for a in acts:
        if a["type"] == "ghl_stage" and a.get("by") != "engine":
            out.append(("ghl_stage not by the engine", a))
    out += [("engine overrode a manual stage", a) for a in engine_overrides(before, acts)]
    if drafts(acts):
        if room.get("blocked"):
            out.append(("draft for a blocked room", drafts(acts)))
        if thread is None or thread["stage"] not in seq.DRAFTING_STAGES or thread["status"] not in seq.LIVE_STATUSES:
            out.append(("draft outside a drafting stage or live status", drafts(acts)))
    if thread is not None and not (0 <= int(thread.get("touch_index") or 0) <= seq.LAST_TOUCH):
        out.append(("touch_index out of range", thread.get("touch_index")))
    return out


class PromptLLM(object):
    """Records every prompt draft.py builds and answers with one short line.
    Nothing reaches shared.llm."""

    def __init__(self):
        self.users = []

    def __call__(self, role, system, user, max_tokens=800, json_mode=False):
        self.users.append(user)
        return "I can walk you through the first week of the build whenever suits you."


def no_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("shared.llm.complete must not be called in these tests")
    monkeypatch.setattr(draft.shared_llm, "complete", boom)


def touch_history(user_message):
    start = user_message.index("=== BEGIN TOUCH_HISTORY ===")
    return user_message[start:user_message.index("=== END TOUCH_HISTORY ===", start)]


CURRENT = "Touches already sent in the current silence"


def reply_prompt(world, rid, when):
    fake = PromptLLM()
    draft.draft_reply(world.rooms[rid], world.thread(rid), when, llm=fake)
    return touch_history(fake.users[0])


def touch_prompt(world, rid, touch, when):
    fake = PromptLLM()
    draft.draft_touch(world.rooms[rid], world.thread(rid), touch, when, llm=fake)
    return touch_history(fake.users[0])


def send_touches(world, rid, n, day=0):
    """Draft and send touches 1..n (each sent at 09:00 CT on its batch day).
    Returns the day of the last send."""
    sent = 0
    while sent < n:
        day += 1
        acts = acts_for(world.run(batch(day)), rid)
        if drafts(acts):
            sent += 1
            world.say(rid, "f_t%d" % sent, "freelancer", ct(day, 9), "touch %d as sent" % sent)
            world.run(ct(day, 10))
        assert day < 60, "the ladder stalled"
    return day


def ext(world, stage, when, rid="room_a1"):
    """A stage read back from GHL."""
    world.store.mutate(thread_key(rid), lambda c: seq.apply_external_stage(c, stage, when)[0])


# ------------------------------------------------ defect 1: stage-step order
@pytest.mark.parametrize("parked_by", ["engine", "lorenzo"])
def test_check_in_return_and_offer_promotion_land_in_the_same_run(world, parked_by):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: after launch|2026-10-15")
    world.run(batch(2))
    if parked_by == "lorenzo":
        seq.set_stage(world.store, "room_a1", "follow_up_later", batch(2) + MIN)  # pins it as his
        assert world.thread("room_a1")["stage_set_by"] == "lorenzo"
    world.rooms["room_a1"]["offer_state"] = "awaiting_your_acceptance"
    assert "stage_change" not in types(acts_for(world.run(batch(3)), "room_a1"))  # parked: no promotion
    due = CT.localize(datetime(2026, 10, 15, 8, 30)).astimezone(timezone.utc)
    acts = acts_for(world.run(due, fill=False), "room_a1")
    assert [(a["from"], a["to"], a["reason"]) for a in of_type(acts, "stage_change")] == [
        ("follow_up_later", "new_reply", "checkin_due"), ("new_reply", "proposal_sent", "offer_awaiting_acceptance")]
    assert of_type(acts, "ghl_stage")[-1]["stage"] == "proposal_sent"
    assert drafts(acts) == [{"type": "draft_checkin", "follow_up_at": "2026-10-15"}]
    assert world.thread("room_a1")["stage"] == "proposal_sent"
    for fill in (False, True):  # the tick died before drafting, then a healthy tick filled it
        if fill:
            fill_reservation(world.store, "room_a1", due)
        before = json.dumps(world.thread("room_a1"), sort_keys=True)
        assert acts_for(world.run(due, fill=False), "room_a1") == []
        assert json.dumps(world.thread("room_a1"), sort_keys=True) == before


def test_check_in_out_holds_the_dormant_clock_on_a_same_time_rerun(world):
    """The check-in return moves the stage off follow_up_later after the
    dormant check; a same-time rerun must not then find the thread dormant."""
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 10), "not_now: next quarter|2026-12-01")
    world.run(batch(2))
    seq.set_stage(world.store, "room_a1", "follow_up_later", batch(2) + MIN)  # Lorenzo pins it
    world.say("room_a1", "c3", "client", ct(3, 10), "positive: one quick question first")
    world.run(batch(4))
    t = world.thread("room_a1")
    assert (t["status"], t["stage"], t["stage_set_by"]) == ("awaiting_lorenzo", "follow_up_later", "lorenzo")
    due = CT.localize(datetime(2026, 12, 1, 8, 30)).astimezone(timezone.utc)  # 84 CT days after c3
    assert drafts(acts_for(world.run(due), "room_a1")) == [{"type": "draft_checkin", "follow_up_at": "2026-12-01"}]
    before = world.thread("room_a1")
    assert acts_for(world.run(due), "room_a1") == []
    assert world.thread("room_a1") == before


def test_same_second_rerun_keeps_an_unfilled_reservation(world):
    """Production passes datetime.now(): the reservation stores whole seconds,
    so a rerun with the same sub-second now must not release it."""
    enrol_silent(world)
    now = batch(2) + timedelta(microseconds=730541)
    assert drafts(acts_for(world.run(now, fill=False), "room_a1")) == [{"type": "draft_touch", "touch": 1}]
    before = world.thread("room_a1")
    assert before["pending"]["issued_at"] == iso(batch(2))
    for again in (now, batch(2), batch(2) + timedelta(microseconds=999999)):
        assert acts_for(world.run(again, fill=False), "room_a1") == []
        assert world.thread("room_a1") == before
    # a later second is a later run: the unfilled reservation is released and redrafted
    assert drafts(acts_for(world.run(batch(2) + timedelta(seconds=1), fill=False), "room_a1")) == [
        {"type": "draft_touch", "touch": 1}]


# ----------------------------------------- generic same-time matrix and walk
M_NOW = ct(100, 8, 30)
M_PENDING = (None, "placeholder", "touch", "touch_week_old", "reply_week_old", "checkin_week_old")
M_CHECKIN = (None, "due", "future")
M_NEW = (None, "client:positive", "client:not_now", "client:declined", "client:machine", "freelancer")


def _matrix_case(stage, set_by, status, pending, offer, contract, checkin, rnd):
    """One stored thread and its room, from the matrix axes plus seeded extras
    (client waiting, ladder position, dormant age, a hold, a block, a new
    message, a skipped reply, sub-second now). Returns (store, snapshot, now)."""
    day = timedelta(days=1)
    now = M_NOW + timedelta(microseconds=rnd.choice((0, 0, 437123)))
    waiting = rnd.random() < 0.5
    old = rnd.random() < 0.25
    idx, silence_days, cycles = rnd.choice(((0, 1, 0), (3, 5, 0), (7, 20, 0), (7, 3, 3)))
    blocked = rnd.random() < 0.15
    hold = not blocked and rnd.random() < 0.1
    new = rnd.choice(M_NEW)
    client_at = now - (70 if old else 12) * day
    base = [msg("f0", "freelancer", client_at - day, "proposal answer"),
            msg("c1", "client", client_at, "question: how would it work?")]
    if not waiting:
        base.append(msg("f1", "freelancer", now - silence_days * day, "my answer"))
    msgs = list(base)
    if new:
        side, _sep, label = new.partition(":")
        msgs.append(msg("n1", side, now - timedelta(hours=1), "%s: new words" % label if label else "a note"))
    if hold:
        msgs.append(msg("u1", "unknown", now - timedelta(minutes=30), "?"))
    room = make_room("room_m", msgs=msgs, offer_state=offer,
                     contract={"contract_id": "ct_m", "status": contract} if contract else None)
    if blocked:
        room["blocked"], room["blocked_at"] = True, iso(now - 2 * day)
    t = seq.new_thread(room, now - 60 * day, "auto")
    marks = t["marks"]
    marks.update(initialized=True, last_seen_at=base[-1]["at"], last_client_at=iso(client_at),
                 dormant_floor=iso(now - 65 * day) if old else None)
    t.update(status=status, stage=stage, stage_set_by=set_by, stage_changed_at=iso(now - 10 * day),
             last_seen_message_id=base[-1]["id"], touch_index=idx, cycles=cycles,
             silence_started_at=None if waiting else iso(now - silence_days * day))
    if waiting:
        marks.update(client_waiting=True, reply_target="c1", reply_for="c1" if rnd.random() < 0.3 else None)
    fu = {None: None, "due": ct_day(now), "future": ct_day(now + 10 * day)}[checkin]
    t["follow_up_at"] = fu
    if fu and rnd.random() < 0.2:
        marks["checkin_for"] = fu
    if pending:
        kind = "touch" if pending == "placeholder" else pending.split("_")[0]
        filled = pending != "placeholder"
        t["pending"] = {"kind": kind, "touch": min(idx + 1, seq.LAST_TOUCH) if kind == "touch" else None,
                        "issued_at": iso(now - (8 if pending.endswith("week_old") else 1) * day),
                        "text": "a draft" if filled else None, "card_id": "card_m" if filled else None,
                        "resurfaced_at": None}
        if kind == "reply":
            marks["reply_for"] = marks.get("reply_target")
        elif kind == "checkin":
            marks["checkin_for"] = fu
    if status == seq.CLOSED or (status == seq.STOPPED and rnd.random() < 0.3):
        # closed by a block (or stopped by Lorenzo while closed): what the block found
        pre = rnd.choice((None, "active", "awaiting_lorenzo", "paused_not_now", "stopped", "lost",
                          "closed_out", "dormant")) if status == seq.CLOSED else "stopped"
        if status == seq.CLOSED:
            t["stop_reason"] = seq.ROOM_BLOCKED
        marks["blocked_at"] = iso(now - 3 * day)
        if pre:
            marks["pre_block"] = {"status": pre, "stop_reason": {"stopped": "stopped_by_lorenzo",
                                                                 "lost": "declined"}.get(pre),
                                  "stage": rnd.choice(("new_reply", "proposal_sent", "follow_up_later", "lost")),
                                  "set_by": rnd.choice(("engine", "engine", "lorenzo"))}
    if rnd.random() < 0.2:
        marks["reply_skipped"] = {"message_id": "c1", "count": rnd.choice((1, 2)), "at": iso(now - 5 * day)}
    store = MemStore()
    store.set(seq.META_KEY, {"first_run_at": iso(now - 90 * day), "revivable": {}})
    store.set(thread_key("room_m"), t)
    return store, snap([room]), now


@pytest.mark.parametrize("stage", seq.STAGES)
def test_same_time_second_run_changes_nothing_over_the_state_matrix(stage):
    """Every stage x setter x status x pending x offer x contract x check-in
    date (plus seeded extras): run() twice at the same time on the same
    snapshot, once as a crashed tick (reservation left unfilled) and once as a
    healthy one (filled). The second run emits nothing and writes nothing."""
    problems = []
    axes = itertools.product(("engine", "lorenzo"), seq.STATUSES, M_PENDING,
                             (None, "awaiting_your_acceptance"), (None, "ACTIVE"), M_CHECKIN)
    for i, (set_by, status, pending, offer, contract, checkin) in enumerate(axes):
        case = (stage, set_by, status, pending, offer, contract, checkin, i)
        store, snapshot, now = _matrix_case(stage, set_by, status, pending, offer, contract, checkin,
                                            random.Random("%s|%d" % (stage, i)))
        cls = FakeClassify()
        before = store.get(thread_key("room_m"))
        first = seq.run(store, snapshot, now, cls)
        for _room, thread, acts in first:
            problems += [(case,) + p for p in action_problems(before, thread, snapshot["rooms"][0], acts)]
        for label in ("crashed tick", "healthy tick"):
            if label == "healthy tick":
                fill_all(store, now)
            held = dict(store.data)
            again = seq.run(store, snapshot, now, cls)
            if any(acts for _r, _t, acts in again) or store.data != held:
                problems.append((case, label, [acts for _r, _t, acts in again if acts]))
        if len(problems) > 20:
            break
    assert not problems, problems[:5]


FUZZ_LABELS = ("positive", "question", "neutral", "not_now", "declined", "hired_other", "machine",
               "not_now: later|2026-12-01")


def _fuzz_walk(seed):
    """The reviewer's random walk, on MemStore: three rooms, forty steps of
    client and freelancer messages, room events, unattributable lines, stage
    moves by Lorenzo and GHL, stops, resumes, offers, blocks and unblocks.
    After each step: run, check what the run did, let the tick fill (or crash),
    and run again at the same time; that second run must be a no-op."""
    rnd = random.Random(seed)
    store = MemStore()
    rooms = {}
    for i in range(3):
        rid = "room_f%d" % i
        rooms[rid] = make_room(rid, msgs=[msg("c0", "client", ct(-2), "positive: hi"),
                                          msg("f0", "freelancer", ct(-1), "plan")])
        rooms[rid].update(blocked=False, blocked_at=None)
    cls = FakeClassify()
    clock = ct(0, 9)
    problems = []
    n = 0

    def say(rid, side, when, text):
        rooms[rid]["messages"].append(msg("m%d" % n, side, when, text))
        _sync_last(rooms[rid])
        if side in ("client", "freelancer"):
            rooms[rid].update(blocked=False, blocked_at=None)  # a spoken line after a block: open again

    for step in range(40):
        clock += timedelta(hours=rnd.choice((1, 5, 13, 24, 30, 50, 80, 170)))
        for rid in sorted(rooms):
            n += 1
            r = rnd.random()
            exists = store.get(thread_key(rid)) is not None
            when = clock - timedelta(minutes=rnd.choice((5, 20, 30)))
            try:
                if r < 0.15:
                    say(rid, "client", when, "%s: some words" % rnd.choice(FUZZ_LABELS))
                elif r < 0.30:
                    say(rid, "freelancer", when, "lorenzo writes")
                elif r < 0.33:
                    say(rid, "unknown", when, "??")
                elif r < 0.36:
                    m = msg("e%d" % n, "unknown", when, "**X** sent an offer")
                    m["event"] = True
                    rooms[rid]["messages"].append(m)
                elif r < 0.42 and exists:
                    stage = rnd.choice(seq.STAGES)
                    if rnd.random() < 0.5:
                        seq.set_stage(store, rid, stage, clock - MIN)
                    else:
                        store.mutate(thread_key(rid), lambda c: seq.apply_external_stage(c, stage, clock - MIN)[0])
                elif r < 0.45 and exists:
                    seq.stop(store, rid, clock - MIN)
                elif r < 0.49 and exists:
                    seq.resume(store, rid, clock - MIN)
                elif r < 0.51:
                    rooms[rid]["offer_state"] = rnd.choice((None, "awaiting_your_acceptance"))
                elif r < 0.55 and not rooms[rid].get("blocked"):
                    m = msg("b%d" % n, "unknown", when, "System event: blocked. View this conversation on "
                                                        "upwork.com for full context.")
                    m.update(event=True, event_name="blocked")
                    rooms[rid]["messages"].append(m)
                    rooms[rid].update(blocked=True, blocked_at=iso(when))
                elif r < 0.58 and rooms[rid].get("blocked"):
                    rooms[rid].update(blocked=False, blocked_at=None)  # unblocked with no new message
            except ValueError:
                pass  # resume of a thread with nothing to resume
        before = dict((rid, store.get(thread_key(rid))) for rid in rooms)
        snapshot = snap(rooms.values(), blocked_rooms=sorted(r for r in rooms if rooms[r].get("blocked")))
        for room, thread, acts in seq.run(store, snapshot, clock, cls):
            problems += [("s%s/%d" % (seed, step),) + p
                         for p in action_problems(before.get(room["room_id"]), thread, rooms.get(room["room_id"], room),
                                                  acts)]
            if thread is not None:
                p = thread.get("pending")
                if p and (thread["stage"] not in seq.DRAFTING_STAGES or thread["status"] not in seq.LIVE_STATUSES):
                    problems.append(("s%s/%d" % (seed, step), "pending outside a drafting stage or live status",
                                     room["room_id"], thread["stage"], thread["status"]))
                if rooms.get(room["room_id"], {}).get("blocked") and (p or thread["status"] not in (seq.CLOSED, seq.WON)):
                    problems.append(("s%s/%d" % (seed, step), "blocked room not closed", room["room_id"],
                                     thread["status"], bool(p)))
        if rnd.random() < 0.9:
            fill_all(store, clock)
        held = dict(store.data)
        again = seq.run(store, snapshot, clock, cls)
        if any(acts for _r, _t, acts in again) or store.data != held:
            problems.append(("s%s/%d" % (seed, step), "second run not a no-op",
                             [(r["room_id"], a) for r, _t, a in again if a]))
        # now and then a draft fails after that and is released for retry
        for rid in sorted(rooms):
            cur = store.get(thread_key(rid))
            if cur and cur.get("pending") and rnd.random() < 0.05:
                store.mutate(thread_key(rid), lambda c: seq.clear_pending(c, clock, "draft_failed", retry=True))
    return problems


@pytest.mark.parametrize("chunk", range(4))
def test_random_walk_keeps_every_same_time_rerun_a_no_op(chunk):
    problems = []
    for seed in range(chunk * 6, chunk * 6 + 6):
        problems += _fuzz_walk(seed)
    assert not problems, problems[:5]


# ------------------------------------ defect 2: silence after stop / lost
@pytest.mark.parametrize("how", ["stop", "lorenzo_lost", "ghl_lost"])
def test_reply_to_a_client_who_wrote_on_a_stopped_or_lost_thread_lists_no_current_silence(world, monkeypatch, how):
    no_model(monkeypatch)
    enrol_silent(world)
    d = send_touches(world, "room_a1", 3)
    assert CURRENT + ": T1 (idea), T2 (show), T3 (proof)" in touch_prompt(world, "room_a1", 4, ct(d, 11))
    if how == "stop":
        seq.stop(world.store, "room_a1", ct(d, 11))
    elif how == "lorenzo_lost":
        seq.set_stage(world.store, "room_a1", "lost", ct(d, 11))
    else:
        ext(world, "lost", ct(d, 11))
    world.say("room_a1", "c2", "client", ct(d + 1, 7), "question: are you still around?")
    acts = acts_for(world.run(batch(d + 1)), "room_a1")
    assert bool(reviews(acts, "client_wrote_after_lost")) == (how != "stop") and not drafts(acts)
    t = world.thread("room_a1")
    ended = [h for h in t["history"] if h["event"] == "silence_ended"][-1]
    assert (ended["cycles"], ended["message_id"]) == (1, "c2") and t["cycles"] == 1
    assert t["touch_index"] == 0 and t["silence_started_at"] is None and t["marks"]["reply_target"] == "c2"
    if how == "stop":
        seq.resume(world.store, "room_a1", ct(d + 1, 9))
    elif how == "lorenzo_lost":
        seq.set_stage(world.store, "room_a1", "new_reply", ct(d + 1, 9))
    else:
        ext(world, "proposal_sent", ct(d + 1, 9))
    assert world.thread("room_a1")["status"] == "awaiting_lorenzo"
    assert drafts(acts_for(world.run(ct(d + 1, 10)), "room_a1")) == [{"type": "draft_reply", "message_id": "c2"}]
    block = reply_prompt(world, "room_a1", ct(d + 1, 10))
    assert CURRENT not in block
    for n, purpose in ((1, "idea"), (2, "show"), (3, "proof")):
        assert "T%d (%s) sent at" % (n, purpose) in block  # still listed as sent history
    world.say("room_a1", "f_reply", "freelancer", ct(d + 1, 12), "yes, still here")
    world.run(ct(d + 1, 13))
    acts = acts_for(world.run(batch(d + 3)), "room_a1")
    assert drafts(acts) == [{"type": "draft_touch", "touch": 1}]
    assert CURRENT not in touch_prompt(world, "room_a1", 1, batch(d + 3))


def _p_stop_resume(w, d):
    seq.stop(w.store, "room_a1", ct(d, 11))
    seq.resume(w.store, "room_a1", ct(d + 1, 9))
    return d + 1


def _p_restage(first, then):
    def path(w, d):
        seq.set_stage(w.store, "room_a1", first, ct(d, 11))
        seq.set_stage(w.store, "room_a1", then, ct(d + 1, 9))
        return d + 1
    return path


def _p_ghl_lost_back(w, d):
    ext(w, "lost", ct(d, 11))
    ext(w, "proposal_sent", ct(d + 1, 9))
    return d + 1


def _p_follow_up_later_resume(w, d):
    seq.set_stage(w.store, "room_a1", "follow_up_later", ct(d, 11))
    seq.resume(w.store, "room_a1", ct(d + 1, 9))
    return d + 1


def _p_check_in_skipped(w, d):
    t, _acts = seq.set_stage(w.store, "room_a1", "follow_up_later", ct(d, 11))
    fu = (datetime.strptime(t["follow_up_at"], "%Y-%m-%d").date() - D0).days
    assert drafts(acts_for(w.run(batch(fu)), "room_a1"))[0]["type"] == "draft_checkin"  # drafted, never sent
    assert of_type(acts_for(w.run(batch(fu + 7)), "room_a1"), "withdraw_pending")[0]["reason"] == "skipped"
    return fu + 7


def _p_resting_then(status, cli):
    def path(w, d):
        w.store.mutate(thread_key("room_a1"), lambda c: dict(c, status=status, stage="lost"))
        if cli == "resume":
            seq.resume(w.store, "room_a1", ct(d + 1, 9))
        else:
            seq.set_stage(w.store, "room_a1", "new_reply", ct(d + 1, 9))
        return d + 1
    return path


REVIVE_PATHS = [
    ("stop_then_resume", _p_stop_resume, 1, False),
    ("lorenzo_lost_then_new_reply", _p_restage("lost", "new_reply"), 1, False),
    ("ghl_lost_then_proposal_sent", _p_ghl_lost_back, 1, False),
    ("lorenzo_won_then_new_reply", _p_restage("won", "new_reply"), 1, False),
    # not a revive: an active thread parked and moved back resumes its ladder
    ("call_booked_then_new_reply", _p_restage("call_booked", "new_reply"), 4, True),
    ("follow_up_later_then_new_reply", _p_restage("follow_up_later", "new_reply"), 1, False),
    ("follow_up_later_then_resume", _p_follow_up_later_resume, 1, False),
    ("follow_up_later_check_in_skipped", _p_check_in_skipped, 1, False),
    ("dormant_then_new_reply", _p_resting_then("dormant", "stage"), 1, False),
    ("closed_out_then_resume", _p_resting_then("closed_out", "resume"), 1, False),
]


@pytest.mark.parametrize("path,expected_touch,current_line", [p[1:] for p in REVIVE_PATHS],
                         ids=[p[0] for p in REVIVE_PATHS])
def test_resume_and_restage_paths_keep_their_next_touch_and_silence_line(world, monkeypatch, path,
                                                                        expected_touch, current_line):
    """The reviewer's cross-check: T1..T3 sent, then each resume or re-stage
    path, then the next touch. Unchanged by the silence-boundary fix."""
    no_model(monkeypatch)
    enrol_silent(world)
    d = path(world, send_touches(world, "room_a1", 3))
    for day in range(d + 1, d + 16):
        acts = acts_for(world.run(batch(day)), "room_a1")
        if drafts(acts):
            break
    assert drafts(acts) == [{"type": "draft_touch", "touch": expected_touch}]
    block = touch_prompt(world, "room_a1", expected_touch, batch(day))
    if current_line:
        assert CURRENT + ": T1 (idea), T2 (show), T3 (proof)" in block
    else:
        assert CURRENT not in block


# ------------------------------------------ auto-replies on stopped / lost
@pytest.mark.parametrize("how", ["stop", "lost"])
def test_machine_text_on_a_stopped_or_lost_thread_is_not_a_waiting_client(world, how):
    enrol_silent(world)
    if how == "stop":
        seq.stop(world.store, "room_a1", batch(1))
    else:
        seq.set_stage(world.store, "room_a1", "lost", batch(1))
    world.say("room_a1", "c2", "client", ct(2, 7), "machine: I am out of office until Monday")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert types(acts) == ["classified"] and acts[0]["label"] == "machine"  # no client_wrote_after_lost
    t = world.thread("room_a1")
    assert t["marks"]["client_waiting"] is False and t["marks"]["reply_target"] is None and t["cycles"] == 0
    assert [h["event"] for h in t["history"]][-1] == "machine_ignored"
    if how == "stop":
        t, _acts = seq.resume(world.store, "room_a1", ct(3, 9))
    else:
        t, _acts = seq.set_stage(world.store, "room_a1", "new_reply", ct(3, 9))
    assert t["status"] == "active" and t["silence_started_at"] == iso(ct(3, 9))
    assert not drafts(acts_for(world.run(ct(3, 10)), "room_a1"))
    assert drafts(acts_for(world.run(batch(5)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_stopped_thread_answers_the_newest_real_message_of_a_burst(world):
    enrol_silent(world)
    seq.stop(world.store, "room_a1", batch(1))
    world.say("room_a1", "c2", "client", ct(2, 7), "question: can we still do this?")
    world.say("room_a1", "c3", "client", ct(2, 7, 1), "machine: auto-reply, away until Monday")
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert [a["message_id"] for a in of_type(acts, "classified")] == ["c3", "c2"]
    entry = world.thread("room_a1")["history"][-1]
    assert (entry["event"], entry["message_id"], entry["label"]) == ("client_message_while_stopped", "c2", "question")
    seq.resume(world.store, "room_a1", ct(2, 9))
    assert drafts(acts_for(world.run(ct(2, 10)), "room_a1")) == [{"type": "draft_reply", "message_id": "c2"}]


def test_low_confidence_read_on_a_stopped_thread_is_surfaced(world):
    enrol_silent(world)
    seq.stop(world.store, "room_a1", batch(1))
    world.say("room_a1", "c2", "client", ct(2, 7), "hmm")

    def low(text, room):
        return {"label": "neutral", "raw_label": "machine", "confidence": 0.55, "follow_up_at": None}

    acts = acts_for(world.run(batch(2), classify=low), "room_a1")
    assert reviews(acts, "low_confidence")[0]["raw_label"] == "machine"
    assert world.thread("room_a1")["status"] == "stopped" and world.thread("room_a1")["marks"]["reply_target"] == "c2"


# --------------------------------------------------------- the 60-day edge
def test_later_run_eligibility_ends_where_dormant_begins(world):
    at60 = make_room("room_60", msgs=[msg("c1", "client", ct(-60, 23, 59), "positive: hi"),
                                      msg("f1", "freelancer", ct(-3), "hello")])
    at59 = make_room("room_59", msgs=[msg("c1", "client", ct(-59, 0, 1), "positive: hi"),
                                      msg("f1", "freelancer", ct(-3), "hello")])
    assert seq.eligible(at60, batch(0), first_run=False) == (False, "revivable")
    assert seq.eligible(at59, batch(0), first_run=False) == (True, "eligible")
    assert seq.eligible(at60, batch(0), first_run=True) == (False, "revivable")
    world.add(at60)
    world.add(at59)
    res = world.run(batch(0), first_run=False)
    only = acts_for(res, "room_60")
    assert types(only) == ["revivable"] and only[0]["reason"] == "last client message 60 or more days old"
    assert world.thread("room_60") is None
    acts = acts_for(res, "room_59")
    assert "enrolled" in types(acts) and "dormant" not in [a.get("to") for a in of_type(acts, "status_change")]
    assert len(of_type(acts, "ghl_stage")) == 1  # enrolled at new_reply only
    acts = acts_for(world.run(batch(1), first_run=False), "room_59")  # dormant the next CT day, as before
    assert {"type": "status_change", "from": "active", "to": "dormant", "reason": "no_client_message_60_days"} in acts


# ------------------------------------------- skipped and released replies
def _unanswered_reply(world):
    world.add(make_room("room_q", msgs=[msg("f0", "freelancer", ct(-2, 9), "my proposal"),
                                        msg("c1", "client", ct(0, 9), "question: what is the timeline?")]))
    assert drafts(acts_for(world.run(ct(0, 10)), "room_q")) == [{"type": "draft_reply", "message_id": "c1"}]
    assert types(acts_for(world.run(batch(3)), "room_q")) == ["resurface"]


def test_reply_that_expires_unsent_is_redrafted_once_then_waits_visibly(world):
    _unanswered_reply(world)
    acts = acts_for(world.run(batch(7)), "room_q")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "skipped"
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c1"}] and not reviews(acts, "reply_skipped")
    t = world.thread("room_q")
    assert t["history"][-3]["event"] == "reply_skipped" and t["history"][-3]["redraft"] is True
    assert t["marks"]["reply_skipped"] == {"message_id": "c1", "count": 1, "at": iso(batch(7))}
    assert types(acts_for(world.run(batch(10)), "room_q")) == ["resurface"]
    acts = acts_for(world.run(batch(14)), "room_q")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "skipped" and not drafts(acts)
    assert reviews(acts, "reply_skipped") == [{
        "type": "needs_review", "reason": "reply_skipped", "message_id": "c1",
        "skipped_at": iso(batch(14)), "waiting_since": iso(ct(0, 9))}]
    entry = [h for h in world.thread("room_q")["history"] if h["event"] == "reply_skipped"][-1]
    assert (entry["at"], entry["message_id"], entry["count"], entry["redraft"]) == (iso(batch(14)), "c1", 2, False)
    before = world.thread("room_q")
    assert acts_for(world.run(batch(14)), "room_q") == [] and world.thread("room_q") == before
    for d in range(15, 30):
        assert acts_for(world.run(batch(d)), "room_q") == [], d
        s = seq.due_summary(world.thread("room_q"), batch(d))
        assert (s["status"], s["kind"], s["draft_now"], s["next_due_at"]) == (
            "awaiting_lorenzo", "reply_skipped", False, None)
        assert (s["skipped_at"], s["waiting_since"]) == (iso(batch(14)), iso(ct(0, 9)))
    world.say("room_q", "c2", "client", ct(30, 7), "question: still keen, any news?")
    assert drafts(acts_for(world.run(batch(30)), "room_q")) == [{"type": "draft_reply", "message_id": "c2"}]


def test_lorenzo_answering_by_hand_ends_the_skipped_reply_state(world):
    _unanswered_reply(world)
    world.run(batch(7))
    world.run(batch(14))
    world.say("room_q", "f1", "freelancer", ct(15, 9), "sorry for the wait, here is the plan")
    acts = acts_for(world.run(ct(15, 10)), "room_q")
    assert {"type": "status_change", "from": "awaiting_lorenzo", "to": "active", "reason": "lorenzo_answered"} in acts
    assert drafts(acts_for(world.run(batch(17)), "room_q")) == [{"type": "draft_touch", "touch": 1}]


@pytest.mark.parametrize("moved", [False, True])
def test_resume_asks_again_for_a_skipped_reply(world, moved):
    _unanswered_reply(world)
    world.run(batch(7))
    world.run(batch(14))
    if moved:  # Lorenzo parked it in a non-drafting stage after the skip
        seq.set_stage(world.store, "room_q", "call_booked", ct(14, 12))
    t, acts = seq.resume(world.store, "room_q", ct(15, 8))
    assert t["status"] == "awaiting_lorenzo" and t["marks"]["reply_for"] is None
    assert t["history"][-1] == {"at": iso(ct(15, 8)), "event": "reply_resumed", "message_id": "c1"}
    if moved:
        assert of_type(acts, "stage_change") == [{"type": "stage_change", "from": "call_booked", "to": "new_reply",
                                                  "by": "lorenzo", "reason": "resumed"}]
        assert t["stage_set_by"] == "lorenzo"
    else:
        assert acts == []
    assert seq.due_summary(t, ct(15, 8))["kind"] == "reply"
    assert drafts(acts_for(world.run(batch(15)), "room_q")) == [{"type": "draft_reply", "message_id": "c1"}]
    with pytest.raises(ValueError):  # a reply out (pending) is nothing to resume
        seq.resume(world.store, "room_q", ct(15, 9))
    acts = acts_for(world.run(batch(22)), "room_q")  # the resumed draft expires too: no auto redraft
    assert reviews(acts, "reply_skipped") and not drafts(acts)


def test_reply_released_for_retry_is_drafted_again_on_the_next_run(world):
    """tick.py releases a reservation with clear_pending(retry=True) when a
    draft fails or the run's budget runs out, in the same run."""
    world.add(make_room("room_q", msgs=[msg("c1", "client", ct(0, 9), "question: rates?")]))
    assert drafts(acts_for(world.run(ct(0, 10), fill=False), "room_q"))
    world.store.mutate(thread_key("room_q"), lambda c: seq.clear_pending(c, ct(0, 10), "run_budget", retry=True))
    s = seq.due_summary(world.thread("room_q"), ct(0, 11))
    assert (s["kind"], s["draft_now"]) == ("reply", True)
    assert drafts(acts_for(world.run(batch(1)), "room_q")) == [{"type": "draft_reply", "message_id": "c1"}]
    assert not any(h["event"] == "reply_skipped" for h in world.thread("room_q")["history"])


def test_reply_cleared_without_retry_is_an_explicit_skip(world):
    world.add(make_room("room_q", msgs=[msg("c1", "client", ct(0, 9), "question: rates?")]))
    world.run(ct(0, 10))
    world.store.mutate(thread_key("room_q"), lambda c: seq.clear_pending(c, ct(0, 11), "lorenzo_dismissed"))
    t = world.thread("room_q")
    assert t["history"][-1] == {"at": iso(ct(0, 11)), "event": "reply_skipped", "message_id": "c1",
                                "count": 1, "redraft": False}
    s = seq.due_summary(t, batch(1))
    assert (s["kind"], s["skipped_at"], s["waiting_since"]) == ("reply_skipped", iso(ct(0, 11)), iso(ct(0, 9)))
    assert acts_for(world.run(batch(1)), "room_q") == []


# ------------------------------------------------------------ blocked rooms
BLOCK_LINE = "System event: blocked. View this conversation on upwork.com for full context."


def block(world, rid, when):
    """What collect.py writes for a blocked room: the MCP line as an event
    (event_name "blocked", never last_side), blocked true, blocked_at its time."""
    m = msg("blk_%s" % when.strftime("%m%d%H%M"), "unknown", when, BLOCK_LINE)
    m.update(event=True, event_name="blocked")
    world.rooms[rid]["messages"].append(m)
    world.rooms[rid].update(blocked=True, blocked_at=iso(when))


def unblock(world, rid):
    world.rooms[rid].update(blocked=False, blocked_at=None)


def test_blocked_room_is_never_enrolled(world):
    world.add(make_room("room_b", msgs=[msg("c1", "client", ct(0, 9), "question: rates?")]))
    block(world, "room_b", ct(0, 9, 30))
    world.add(make_room("room_listed", msgs=[msg("c1", "client", ct(0, 9), "question: rates?")]))
    res = world.run(batch(1), blocked_rooms=["room_b", "room_listed"])  # the list alone also counts
    assert acts_for(res, "room_b") is None and acts_for(res, "room_listed") is None
    assert world.thread("room_b") is None and world.thread("room_listed") is None
    assert seq.eligible(world.rooms["room_b"], batch(1), first_run=False) == (False, "blocked")
    with pytest.raises(ValueError):
        seq.enroll(world.store, world.rooms["room_b"], batch(1))
    unblock(world, "room_b")
    assert "enrolled" in types(acts_for(world.run(batch(2)), "room_b"))


def test_blocked_room_closes_its_thread_withdraws_the_draft_and_freezes(world):
    enrol_silent(world)
    world.run(batch(2))  # T1 drafted
    block(world, "room_a1", ct(2, 12))
    acts = acts_for(world.run(ct(2, 13)), "room_a1")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "room_blocked"
    assert {"type": "status_change", "from": "active", "to": "closed", "reason": "room_blocked"} in acts
    assert {"type": "stage_change", "from": "new_reply", "to": "lost", "by": "engine", "reason": "room_blocked"} in acts
    assert {"type": "ghl_stage", "stage": "lost", "by": "engine"} in acts
    assert reviews(acts, "room_blocked") == [{"type": "needs_review", "reason": "room_blocked",
                                              "blocked_at": iso(ct(2, 12)), "stage": "lost", "set_by": "engine",
                                              "stage_kept": False}]
    t = world.thread("room_a1")
    assert (t["status"], t["stop_reason"], t["pending"]) == ("closed", "room_blocked", None)
    assert {"at": iso(ct(2, 13)), "event": "room_blocked", "blocked_at": iso(ct(2, 12))} in t["history"]
    before = world.thread("room_a1")
    assert acts_for(world.run(ct(2, 13)), "room_a1") == [] and world.thread("room_a1") == before
    for d in range(3, 40, 3):
        assert acts_for(world.run(batch(d)), "room_a1") == [], d
    t = world.thread("room_a1")
    assert (t["touch_index"], t["silence_started_at"]) == (before["touch_index"], before["silence_started_at"])
    assert seq.due_summary(t, batch(40))["draft_now"] is False


@pytest.mark.parametrize("by", ["lorenzo", "ghl"])
def test_blocked_room_keeps_a_stage_lorenzo_set_and_never_drafts(world, by):
    enrol_silent(world)
    seq.set_stage(world.store, "room_a1", "proposal_sent", batch(1), by=by)
    world.run(batch(2))  # T1 drafted
    block(world, "room_a1", ct(2, 12))
    acts = acts_for(world.run(ct(2, 13)), "room_a1")
    assert of_type(acts, "withdraw_pending")[0]["reason"] == "room_blocked"
    assert not of_type(acts, "stage_change") and not of_type(acts, "ghl_stage")
    assert reviews(acts, "room_blocked")[0]["stage_kept"] is True
    assert reviews(acts, "room_blocked")[0]["set_by"] == by
    t = world.thread("room_a1")
    assert (t["status"], t["stage"], t["stage_set_by"]) == ("closed", "proposal_sent", by)
    for d in range(3, 30, 2):  # flagged once, never drafted
        assert acts_for(world.run(batch(d)), "room_a1") == [], d


def test_unblocked_room_reopens_on_a_client_message_written_after_the_block(world, monkeypatch):
    no_model(monkeypatch)
    enrol_silent(world)
    d = send_touches(world, "room_a1", 1)  # T1 sent: the current silence has one touch
    block(world, "room_a1", ct(d, 12))
    world.run(ct(d, 13))
    assert acts_for(world.run(batch(d + 2)), "room_a1") == []
    unblock(world, "room_a1")
    world.say("room_a1", "c2", "client", ct(d + 3, 7), "question: sorry about that, still on?")
    acts = acts_for(world.run(batch(d + 3)), "room_a1")
    assert {"type": "status_change", "from": "closed", "to": "awaiting_lorenzo", "reason": "question"} in acts
    # the stage the block replaced comes back first (it was active in new_reply)
    assert {"type": "stage_change", "from": "lost", "to": "new_reply", "by": "engine",
            "reason": "room_unblocked"} in acts
    assert drafts(acts) == [{"type": "draft_reply", "message_id": "c2"}]
    t = world.thread("room_a1")
    assert t["stop_reason"] is None and t["marks"]["blocked_at"] is None and t["marks"]["pre_block"] is None
    assert {"at": iso(batch(d + 3)), "event": "client_reply", "message_id": "c2", "label": "question"} in t["history"]
    assert CURRENT not in reply_prompt(world, "room_a1", batch(d + 3))
    before = world.thread("room_a1")
    assert acts_for(world.run(batch(d + 3)), "room_a1") == [] and world.thread("room_a1") == before


@pytest.mark.parametrize("reopen", ["resume", "stage"])
def test_unblocked_room_without_a_newer_client_message_stays_closed(world, reopen):
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(2, 11), "question: one more thing")  # before the block, unread
    block(world, "room_a1", ct(2, 12))
    calls = len(world.cls.calls)
    world.run(batch(3))
    assert world.thread("room_a1")["status"] == "closed" and len(world.cls.calls) == calls  # nothing read
    unblock(world, "room_a1")  # Lorenzo unblocked it himself and wrote
    world.say("room_a1", "f2", "freelancer", ct(4, 9), "unblocked, apologies")
    assert acts_for(world.run(batch(4)), "room_a1") == []
    assert acts_for(world.run(batch(9)), "room_a1") == []
    t = world.thread("room_a1")
    assert t["status"] == "closed" and t["marks"]["client_waiting"] is False and len(world.cls.calls) == calls
    if reopen == "resume":
        t, _acts = seq.resume(world.store, "room_a1", ct(9, 9))
    else:
        t, _acts = seq.set_stage(world.store, "room_a1", "new_reply", ct(9, 9))
    assert (t["status"], t["stop_reason"], t["marks"]["blocked_at"]) == ("active", None, None)
    assert drafts(acts_for(world.run(batch(11)), "room_a1")) == [{"type": "draft_touch", "touch": 1}]


def test_resuming_a_room_that_is_still_blocked_closes_it_again(world):
    enrol_silent(world)
    block(world, "room_a1", ct(1, 12))
    world.run(batch(2))
    seq.resume(world.store, "room_a1", ct(2, 9))  # new_reply, now Lorenzo's stage
    acts = acts_for(world.run(batch(3)), "room_a1")
    assert {"type": "status_change", "from": "active", "to": "closed", "reason": "room_blocked"} in acts
    assert reviews(acts, "room_blocked")[0]["stage_kept"] is True and not drafts(acts)


# ------------------------------- what the block found survives the unblock
def _store_dump(store):
    return json.dumps(dict((k, store.get(k)) for k in store.keys("")), sort_keys=True)


def rerun_changes_nothing(world, when):
    """A second run at the same time emits nothing and writes nothing."""
    held = _store_dump(world.store)
    res = world.run(when)
    assert not any(acts for _r, _t, acts in res), [acts for _r, _t, acts in res if acts]
    assert _store_dump(world.store) == held


def _block_twin(tmp_path, how, blocked):
    """T1 sent, then ``how`` (Lorenzo stops it, Lorenzo sets lost, the client
    declines, or nothing), then (``blocked``) the room is blocked for two days
    and opened again, then the client writes. Returns (world, that run's actions)."""
    world = World(tmp_path, store=MemStore())
    enrol_silent(world)
    d = send_touches(world, "room_a1", 1)
    if how == "stop":
        seq.stop(world.store, "room_a1", ct(d, 15))
    elif how == "lorenzo_lost":
        seq.set_stage(world.store, "room_a1", "lost", ct(d, 15))
    elif how == "declined":
        world.say("room_a1", "c2", "client", ct(d, 15), "declined: we hired someone else")
        world.run(ct(d, 16))
    if blocked:
        block(world, "room_a1", ct(d + 1, 12))
        acts = acts_for(world.run(ct(d + 1, 13)), "room_a1")
        assert world.thread("room_a1")["status"] == "closed" and len(reviews(acts, "room_blocked")) == 1
        rerun_changes_nothing(world, ct(d + 1, 13))
        assert acts_for(world.run(batch(d + 2)), "room_a1") == []
        unblock(world, "room_a1")
    world.say("room_a1", "c9", "client", ct(d + 3, 7), "positive: can we pick this up again?")
    acts = acts_for(world.run(batch(d + 3)), "room_a1")
    rerun_changes_nothing(world, batch(d + 3))
    return world, acts


@pytest.mark.parametrize("how,expected", [
    ("stop", ("stopped", "stopped_by_lorenzo", "new_reply", "engine")),
    ("lorenzo_lost", ("lost", "stage_set_by_lorenzo", "lost", "lorenzo")),
    ("declined", ("lost", "declined", "lost", "engine")),
    ("active", ("awaiting_lorenzo", None, "new_reply", "engine")),
])
def test_client_message_after_the_unblock_takes_the_path_it_had_without_the_block(tmp_path, how, expected):
    plain, plain_acts = _block_twin(tmp_path, how, blocked=False)
    reopened, acts = _block_twin(tmp_path, how, blocked=True)
    p, t = plain.thread("room_a1"), reopened.thread("room_a1")
    keys = ("status", "stop_reason", "stage", "stage_set_by", "touch_index", "cycles", "silence_started_at")
    assert [t[k] for k in keys] == [p[k] for k in keys]
    assert (t["status"], t["stop_reason"], t["stage"], t["stage_set_by"]) == expected
    assert drafts(acts) == drafts(plain_acts) == ([{"type": "draft_reply", "message_id": "c9"}] if how == "active" else [])
    assert reviews(acts, "client_wrote_after_lost") == reviews(plain_acts, "client_wrote_after_lost")
    assert bool(reviews(acts, "client_wrote_after_lost")) is (expected[0] == "lost")

    def client_events(th):
        return [h for h in th["history"] if h["event"].startswith("client_")]
    assert client_events(t)[-1]["event"] == client_events(p)[-1]["event"] == {
        "stopped": "client_message_while_stopped", "lost": "client_message_while_lost"}.get(expected[0], "client_reply")
    assert (t["marks"]["reply_target"], t["marks"]["pre_block"], t["marks"]["blocked_at"]) == ("c9", None, None)


@pytest.mark.parametrize("opens", ["after_the_next_close", "before_the_next_run"])
def test_stop_on_a_blocked_room_sticks(world, opens):
    enrol_silent(world)
    d = send_touches(world, "room_a1", 1)
    block(world, "room_a1", ct(d, 12))
    acts = acts_for(world.run(ct(d, 13)), "room_a1")
    assert len(reviews(acts, "room_blocked")) == 1
    t, _acts = seq.stop(world.store, "room_a1", ct(d, 15))
    assert (t["status"], t["stop_reason"]) == ("stopped", "stopped_by_lorenzo")
    if opens == "after_the_next_close":
        acts = acts_for(world.run(batch(d + 1)), "room_a1")  # still blocked: closed again, his stop kept
        assert acts == [{"type": "status_change", "from": "stopped", "to": "closed", "reason": "room_blocked"}]
        t = world.thread("room_a1")
        assert (t["status"], t["stage"], t["stage_set_by"]) == ("closed", "lost", "engine")
        assert t["marks"]["pre_block"] == {"status": "stopped", "stop_reason": "stopped_by_lorenzo",
                                           "stage": "new_reply", "set_by": "engine"}
        rerun_changes_nothing(world, batch(d + 1))
        for day in (d + 2, d + 5):
            assert acts_for(world.run(batch(day)), "room_a1") == []
        unblock(world, "room_a1")
    else:
        unblock(world, "room_a1")
        assert acts_for(world.run(batch(d + 1)), "room_a1") == []  # stopped; nothing to close
        rerun_changes_nothing(world, batch(d + 1))
    world.say("room_a1", "c9", "client", ct(d + 6, 7), "question: are you still available?")
    acts = acts_for(world.run(batch(d + 6)), "room_a1")
    assert not drafts(acts)
    assert {"type": "stage_change", "from": "lost", "to": "new_reply", "by": "engine",
            "reason": "room_unblocked"} in acts
    t = world.thread("room_a1")
    assert (t["status"], t["stop_reason"], t["stage"], t["stage_set_by"]) == (
        "stopped", "stopped_by_lorenzo", "new_reply", "engine")
    assert t["history"][-1]["event"] == "client_message_while_stopped"
    assert (t["marks"]["pre_block"], t["marks"]["blocked_at"]) == (None, None)
    rerun_changes_nothing(world, batch(d + 6))
    seq.resume(world.store, "room_a1", ct(d + 6, 9))  # his resume answers the waiting client
    assert drafts(acts_for(world.run(batch(d + 7)), "room_a1")) == [{"type": "draft_reply", "message_id": "c9"}]


def test_lorenzo_setting_a_blocked_room_lost_keeps_it_lost(world):
    enrol_silent(world)
    block(world, "room_a1", ct(1, 12))
    world.run(ct(1, 13))  # the block moved the stage to lost itself
    t, acts = seq.set_stage(world.store, "room_a1", "lost", ct(1, 15))
    assert (t["status"], t["stop_reason"], t["stage"], t["stage_set_by"]) == (
        "lost", "stage_set_by_lorenzo", "lost", "lorenzo")
    assert acts == [{"type": "status_change", "from": "closed", "to": "lost", "reason": "stage_set_by_lorenzo"}]
    acts = acts_for(world.run(batch(2)), "room_a1")  # still blocked: closed again, no second review
    assert acts == [{"type": "status_change", "from": "lost", "to": "closed", "reason": "room_blocked"}]
    assert world.thread("room_a1")["marks"]["pre_block"] == {
        "status": "lost", "stop_reason": "stage_set_by_lorenzo", "stage": "lost", "set_by": "lorenzo"}
    rerun_changes_nothing(world, batch(2))
    unblock(world, "room_a1")
    world.say("room_a1", "c9", "client", ct(3, 7), "positive: we would like to go ahead after all")
    acts = acts_for(world.run(batch(3)), "room_a1")
    assert reviews(acts, "client_wrote_after_lost") and not drafts(acts)
    assert world.thread("room_a1")["status"] == "lost"
    rerun_changes_nothing(world, batch(3))


# --------------------------------------------- the history reference in DESIGN
DESIGN_PATH = Path(seq.__file__).resolve().parent / "DESIGN.md"


def _written_history_events():
    """Every event name sequence.py passes to ``_hist``, read from its source.
    A ``"...%s..." % x`` name is expanded here; a new pattern fails the test
    until it is added (and documented)."""
    expansions = {
        "%s_changed": ["proposal_id_changed", "job_id_changed"],
        "client_message_while_%s": ["client_message_while_%s" % s for s in (seq.STOPPED, seq.LOST)],
        "%s_sent": ["%s_sent" % k for k in seq.PENDING_KINDS],
    }
    names, unresolved = set(), []
    for node in ast.walk(ast.parse(Path(seq.__file__).read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_hist"):
            continue
        event = node.args[2] if len(node.args) > 2 else None
        if isinstance(event, ast.Constant) and isinstance(event.value, str):
            names.add(event.value)
        elif isinstance(event, ast.Name) and isinstance(getattr(seq, event.id, None), str):
            names.add(getattr(seq, event.id))
        elif isinstance(event, ast.BinOp) and isinstance(event.op, ast.Mod) \
                and isinstance(event.left, ast.Constant) and event.left.value in expansions:
            names.update(expansions[event.left.value])
        else:
            unresolved.append(ast.dump(event) if event is not None else "no event argument")
    assert not unresolved, "history event names the test cannot read: %s" % unresolved
    return names


def _design_bullet(text, start_marker):
    start = text.index(start_marker)
    nxt = re.search(r"\n- \*\*", text[start + 1:])
    return text[start:start + 1 + nxt.start()] if nxt else text[start:]


def test_design_lists_every_history_event_sequence_writes():
    design = DESIGN_PATH.read_text(encoding="utf-8")
    block = _design_bullet(design, "- **History events.**")
    listed = set(re.findall(r"`([a-z][a-z_]*)[^`]*`", block))
    written = _written_history_events()
    assert {"touch_sent", "silence_ended", "client_message_while_lost", "room_blocked", "reply_skipped"} <= written
    missing = sorted(written - listed)
    assert not missing, "sequence.py writes history events DESIGN.md does not list: %s" % missing
    # the boundaries draft.py reads for "the current silence" are named there too
    assert set(draft.SILENCE_BOUNDARIES) <= listed
    marks = _design_bullet(design, "- **`marks`**")
    assert not [k for k in seq._blank_marks() if "`%s`" % k not in marks]


# ------------------------------------------ round 4: classify outside the store lock
class LockWatch(object):
    """A JsonFileStore that knows when one of its mutates is open. Any store
    call made then is recorded and refused before it reaches the file (on the
    real flock it would wait on its own lock forever)."""

    def __init__(self, inner):
        self.inner, self.open, self.nested = inner, [], []

    def _outside(self, call, key):
        if self.open:
            self.nested.append((call, key, self.open[-1]))
            raise AssertionError("store.%s(%r) inside store.mutate(%r)" % (call, key, self.open[-1]))

    def get(self, key, default=None):
        self._outside("get", key)
        return self.inner.get(key, default)

    def set(self, key, value):
        self._outside("set", key)
        self.inner.set(key, value)

    def delete(self, key):
        self._outside("delete", key)
        self.inner.delete(key)

    def keys(self, prefix=""):
        self._outside("keys", prefix)
        return self.inner.keys(prefix)

    def mutate(self, key, fn, default=None):
        self._outside("mutate", key)

        def wrapped(cur):
            self.open.append(key)
            try:
                return fn(cur)
            finally:
                self.open.pop()
        return self.inner.mutate(key, wrapped, default)


def test_run_classifies_with_no_store_lock_held(tmp_path):
    """Every path that classifies (the enrolment tail, a burst with machine
    text, a stopped thread, a blocked room opened again) runs the classifier
    with no mutate open. The classifier also makes a store call per answer,
    as shared.llm.complete does for its spend counter."""
    store = LockWatch(JsonFileStore(tmp_path / "store.json"))
    world = World(tmp_path, store=store)
    seen = []

    def classify(text, room):
        seen.append((text, list(store.open)))
        store.get("llm.spend_usd")
        return world.cls(text, room)

    world.add(make_room("room_a1"))                            # Lorenzo wrote last: nothing to classify
    world.add(make_room("room_q", proposal_id="prop_q",        # the client wrote last: the enrolment tail
                        msgs=[msg("f0", "freelancer", ct(-2, 9), "Here is the Loom."),
                              msg("q1", "client", ct(-1, 9), "question: which CRM?")]))
    world.add(make_room("room_s", proposal_id="prop_s"))
    world.run(ct(0, 14, 5), classify=classify)
    world.say("room_a1", "c2", "client", ct(1, 9), "positive: great, go ahead")
    world.say("room_a1", "c3", "client", ct(1, 9, 5), "machine: out of office until Monday")
    seq.stop(world.store, "room_s", ct(1, 8))
    world.say("room_s", "s2", "client", ct(1, 10), "question: still there?")
    world.run(batch(2), classify=classify)
    block(world, "room_a1", ct(2, 12))
    world.run(batch(3), classify=classify)
    unblock(world, "room_a1")
    world.say("room_a1", "c4", "client", ct(4, 7), "positive: sorry, back now")
    world.run(batch(4), classify=classify)

    assert [t for t, _o in seen] == ["question: which CRM?", "machine: out of office until Monday",
                                     "positive: great, go ahead", "question: still there?",
                                     "positive: sorry, back now"]
    assert all(open_ == [] for _t, open_ in seen) and store.nested == []
    assert world.thread("room_a1")["status"] == "awaiting_lorenzo"
    assert world.thread("room_s")["status"] == "stopped"


def _meddle(**changes):
    """Another writer's edit of the thread (a copy with ``changes`` applied;
    ``marks__x`` edits ``marks["x"]``)."""
    def fn(cur):
        cur = json.loads(json.dumps(cur))
        for k, v in changes.items():
            if k.startswith("marks__"):
                cur["marks"][k[len("marks__"):]] = v
            else:
                cur[k] = v
        return cur
    return fn


class Interloper(JsonFileStore):
    """Another writer gets the thread's lock between run's unlocked read and
    its write: ``meddle`` is applied once, just before the next mutate of
    ``key``."""

    def __init__(self, path, key):
        JsonFileStore.__init__(self, path)
        self.key, self.meddle, self.meddled = key, None, None

    def mutate(self, key, fn, default=None):
        if key == self.key and self.meddle is not None:
            meddle, self.meddle = self.meddle, None
            self.meddled = JsonFileStore.mutate(self, key, meddle, default)
        return JsonFileStore.mutate(self, key, fn, default)


@pytest.mark.parametrize("case", ["new_messages", "other_ids", "fewer_ids"])
def test_a_thread_changed_between_classification_and_write_is_deferred(tmp_path, case):
    """run writes on the answers it got from an unlocked read. When the stored
    thread changed in between so that the write would read other client
    messages, it writes nothing, calls no classifier, and the room comes back
    ``room_deferred`` with the reason; the next run advances it."""
    store = Interloper(tmp_path / "store.json", thread_key("room_a1"))
    world = World(tmp_path, store=store)
    enrol_silent(world)                                        # c1 (client), f1 (Lorenzo)
    world.say("room_a1", "c2", "client", ct(1, 9), "question: does it log calls too?")
    if case == "new_messages":
        world.run(batch(2))                                    # c2 read and answered with a reply draft
        store.meddle = _meddle(last_seen_message_id="f1", marks__last_seen_at=iso(ct(0, 14)))
        want = "new_messages"                                  # the write would read c2 again, unclassified
    elif case == "other_ids":
        store.meddle = _meddle(last_seen_message_id=None, marks__last_seen_at=None)
        want = "message_ids_changed"                           # the write would read c1 first
    else:
        store.meddle = _meddle(last_seen_message_id="c2", marks__last_seen_at=iso(ct(1, 9)))
        want = "message_ids_changed"                           # c2 already read elsewhere: fewer
    calls = len(world.cls.calls)
    when = batch(3)
    res = world.run(when, fill=False)
    acts = acts_for(res, "room_a1")
    assert [(a["type"], a["reason"]) for a in acts] == [("room_deferred", want)]
    assert acts[0]["detail"]
    assert [th for r, th, _a in res if r["room_id"] == "room_a1"] == [None]
    assert world.thread("room_a1") == store.meddled             # nothing of this run's write landed
    assert len(world.cls.calls) - calls == (0 if case == "new_messages" else 1)   # the unlocked pass only
    later = acts_for(world.run(when + MIN), "room_a1")
    assert "room_deferred" not in types(later)


def test_the_write_replays_the_answers_and_calls_no_classifier(tmp_path):
    """The step inside the mutate gets the unlocked pass's answers: the
    classifier runs once per message, and a same-time re-run changes nothing."""
    world = World(tmp_path)
    enrol_silent(world)
    world.say("room_a1", "c2", "client", ct(1, 9), "not_now: busy until November|2026-11-02")
    world.say("room_a1", "c3", "client", ct(1, 9, 1), "machine: auto-reply")
    before = len(world.cls.calls)
    acts = acts_for(world.run(batch(2)), "room_a1")
    assert world.cls.calls[before:] == ["machine: auto-reply", "not_now: busy until November|2026-11-02"]
    assert [a["label"] for a in of_type(acts, "classified")] == ["machine", "not_now"]
    t = world.thread("room_a1")
    assert (t["status"], t["follow_up_at"]) == ("paused_not_now", "2026-11-02")
    rerun_changes_nothing(world, batch(2))
