"""The 5-minute reply SLA, enforced instead of measured (GAP 3).

Before this, an approval card Lorenzo did not action got exactly one push, from
create_approval, and then nothing. jobs/pipeline_sweep noticed it the next
morning at 07:30 with a 24-hour threshold. The prospect who replied waited the
whole night for a reply the system had already written.

approval.escalate_pending chases it on the */5 poller tick with a rising
priority. Four things have to hold, and each has a test here:
  1. it chases, repeatedly, while the card sits unactioned inside sending hours;
  2. it goes quiet outside them, and once the card is actioned or expired;
  3. it is never a send;
  4. it is a guarded write, so MODE=shadow delivers nothing.
"""
import inspect
from datetime import datetime, timedelta

import pytest

from shared import notify as notify_mod
from shared.job_log import read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import approval as A
from services.reply_engine import poller as P

TUE = (2026, 9, 22)      # a Tuesday
FRI = (2026, 9, 25)
MON = (2026, 9, 28)


def ct(*args):
    return TZ.localize(datetime(*args))


def card(created, status="pending", expires=None, **kw):
    base = {
        "status": status,
        "label": "positive_interested",
        "lead_email": "tiffany@flowerhillfs.com",
        "state_key": "lead:c1:tiffany@flowerhillfs.com",
        "email_id": "e1",
        "campaign_id": "c1",
        "campaign_key": "cleaning_reactivation",
        "created_at": created.isoformat(),
        "expires_at": (expires or ct(2026, 9, 24, 10, 0)).isoformat(),
        # create_approval keys the store on the token's id half, so the fixture
        # does too: "approval:a1" <-> token "a1.<sig>".
        "token": "a1.sig",
        "notify_result": {"sent": True, "actionable": True},
        "draft": {"subject": "Re: Tiffany, question", "body_text": "Hey Tiffany,\n\nLorenzo",
                  "offered_slots": ["2026-09-23T13:00:00-05:00"], "problems": []},
    }
    base.update(kw)
    return base


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


def recorder():
    sent = []

    def fn(title, message, priority="default", actions=None, tags=None, click=None, **kw):
        sent.append({"title": title, "message": message, "priority": priority,
                     "actions": actions, "click": click})
        return {"sent": True, "test": True}

    return sent, fn


# ------------------------------------------------- the clock the SLA uses
def test_waiting_time_is_counted_in_sending_hours_not_wall_clock():
    """A card raised at 18:58 on a Tuesday is two minutes into its SLA, not
    thirteen hours. Counting the night against him would put every ordinary
    overnight card at the top of the ladder at 07:00 the next morning."""
    assert A.sending_minutes_between(ct(*TUE, 10, 0), ct(*TUE, 10, 6)) == 6
    overnight = A.sending_minutes_between(ct(*TUE, 18, 58), ct(2026, 9, 23, 7, 2))
    assert overnight == 4                      # 18:58-19:00 plus 07:00-07:02
    weekend = A.sending_minutes_between(ct(*FRI, 18, 58), ct(*MON, 7, 2))
    assert weekend == 4                        # Saturday and Sunday do not count
    assert A.sending_minutes_between(ct(*TUE, 10, 6), ct(*TUE, 10, 0)) == 0


def test_the_ladder_rises_and_then_repeats_without_going_quiet():
    assert A.escalation_step(0) == 0
    assert A.escalation_step(4.9) == 0
    assert A.escalation_step(A.REPLY_SLA_MINUTES) == 1
    assert A.escalation_step(15) == 2
    assert A.escalation_step(30) == 3
    assert A.escalation_step(60) == 4
    assert A.escalation_step(60 + A.ESCALATION_REPEAT_MINUTES) == 5
    assert A.escalation_step(10 ** 6) == A.ESCALATION_MAX_PUSHES
    assert A.escalation_priority(1) == "high"
    assert A.escalation_priority(3) == "urgent"
    assert A.escalation_priority(A.ESCALATION_MAX_PUSHES) == "urgent"
    # rising, never falling
    priorities = [A.escalation_priority(s) for s in range(1, A.ESCALATION_MAX_PUSHES + 1)]
    rank = {"default": 0, "low": 1, "high": 2, "urgent": 3}
    assert priorities == sorted(priorities, key=lambda p: rank[p])


# ----------------------------------------------------------- it chases
def test_a_card_past_the_sla_is_chased_and_not_chased_twice_for_the_same_rung(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    sent, fn = recorder()

    first = A.escalate_pending(store=store, now=ct(*TUE, 10, 6), notify_fn=fn)
    assert [e["step"] for e in first] == [1]
    assert len(sent) == 1 and sent[0]["priority"] == "high"
    assert "Still waiting on you" in sent[0]["title"]
    assert store.get("approval:a1")["escalations"] == 1
    assert store.get("approval:a1")["last_escalated_at"] == ct(*TUE, 10, 6).isoformat()

    # the next */5 tick, still rung 1: nothing more goes out
    assert A.escalate_pending(store=store, now=ct(*TUE, 10, 9), notify_fn=fn) == []
    assert len(sent) == 1


def test_the_priority_rises_as_the_card_keeps_sitting(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    sent, fn = recorder()
    for at in (ct(*TUE, 10, 6), ct(*TUE, 10, 16), ct(*TUE, 10, 31), ct(*TUE, 11, 1), ct(*TUE, 12, 1)):
        A.escalate_pending(store=store, now=at, notify_fn=fn)
    assert [s["priority"] for s in sent] == ["high", "high", "urgent", "urgent", "urgent"]
    assert store.get("approval:a1")["escalations"] == 5


def test_chasing_stops_at_the_cap_rather_than_pushing_forever(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 7, 0), expires=ct(2026, 9, 24, 7, 0)))
    sent, fn = recorder()
    at = ct(*TUE, 7, 0)
    for minute in range(0, 12 * 60, 5):
        at = ct(*TUE, 7, 0) + timedelta(minutes=minute)
        if at.hour >= 19:
            break
        A.escalate_pending(store=store, now=at, notify_fn=fn)
    assert len(sent) == A.ESCALATION_MAX_PUSHES
    assert store.get("approval:a1")["escalations"] == A.ESCALATION_MAX_PUSHES


def test_the_chase_carries_the_buttons_so_it_can_actually_be_actioned(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    sent, fn = recorder()
    A.escalate_pending(store=store, now=ct(*TUE, 10, 6), notify_fn=fn)
    labels = [a[0] for a in sent[0]["actions"]]
    assert labels == ["Approve", "Veto", "Edit"]
    assert sent[0]["click"]
    # ... and, like create_approval, the URLs stay out of the body, which is
    # mirrored into the Gmail copy where a safe-link scanner would follow them.
    assert "http" not in sent[0]["message"]


def test_a_card_whose_first_push_never_left_says_so(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0), notify_result={"sent": False, "errors": ["ntfy: boom"]}))
    sent, fn = recorder()
    A.escalate_pending(store=store, now=ct(*TUE, 10, 6), notify_fn=fn)
    assert "never left the process" in sent[0]["message"]


# ------------------------------------------------------- and it goes quiet
@pytest.mark.parametrize("at", [
    ct(*TUE, 6, 59),          # before the window opens
    ct(*TUE, 19, 0),          # after it closes
    ct(2026, 9, 26, 12, 0),   # a Saturday
    ct(2026, 9, 27, 12, 0),   # a Sunday
])
def test_nothing_is_chased_outside_sending_hours(store, tmp_env, at):
    store.set("approval:a1", card(ct(*TUE, 10, 0), expires=ct(2026, 9, 30, 10, 0)))
    sent, fn = recorder()
    assert A.escalate_pending(store=store, now=at, notify_fn=fn) == []
    assert sent == []
    assert store.get("approval:a1").get("escalations", 0) == 0


@pytest.mark.parametrize("status", ["approved_queued", "sending", "sent", "vetoed",
                                    "expired", "blocked", "superseded", "send_failed"])
def test_a_card_he_actioned_is_never_chased_again(store, tmp_env, status):
    store.set("approval:a1", card(ct(*TUE, 10, 0), status=status))
    sent, fn = recorder()
    assert A.escalate_pending(store=store, now=ct(*TUE, 11, 30), notify_fn=fn) == []
    assert sent == []


def test_an_expired_card_is_left_to_the_expiry_path(store, tmp_env):
    store.set("approval:a1", card(ct(2026, 9, 18, 10, 0), expires=ct(*TUE, 9, 0)))
    sent, fn = recorder()
    assert A.escalate_pending(store=store, now=ct(*TUE, 10, 6), notify_fn=fn) == []
    assert sent == []


def test_a_card_inside_the_sla_is_not_chased_at_all(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    sent, fn = recorder()
    assert A.escalate_pending(store=store, now=ct(*TUE, 10, 4), notify_fn=fn) == []
    assert sent == []


def test_two_overlapping_ticks_do_not_both_shout(store, tmp_env):
    """The poller runs every five minutes and a slow tick overlaps the next."""
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    sent, fn = recorder()
    at = ct(*TUE, 10, 6)
    A.escalate_pending(store=store, now=at, notify_fn=fn)
    # a second worker that read the card before the first one saved it
    stale = dict(store.get("approval:a1"))
    stale["escalations"] = 0
    store.set("approval:a1", stale)
    A.escalate_pending(store=store, now=at, notify_fn=fn)
    assert len(sent) == 1


# ------------------------------------------------- it is never a send
def test_escalation_cannot_send_because_it_has_nothing_to_send_with():
    """The structural guarantee, not a behavioural one: escalate_pending takes
    no Instantly client and its body calls nothing that does."""
    params = list(inspect.signature(A.escalate_pending).parameters)
    assert params == ["store", "now", "notify_fn"]
    body = "\n".join(ln for ln in inspect.getsource(A.escalate_pending).splitlines()
                     if not ln.strip().startswith("#") and not ln.strip().startswith("*"))
    for forbidden in ("send_approved", "approve(", "reply_to_email", "flush_queued", "auto_send"):
        assert forbidden not in body, forbidden


def test_a_chased_card_is_still_pending_and_no_reply_was_written(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    sent, fn = recorder()
    A.escalate_pending(store=store, now=ct(*TUE, 11, 30), notify_fn=fn)
    assert sent
    raw = store.get("approval:a1")
    assert raw["status"] == "pending"
    assert raw.get("decided_at") is None and raw.get("send_attempt") is None
    assert [r for r in read_shadow_log() if r["action"] == "reply_to_email"] == []


# -------------------------------------------------- it is a guarded write
def test_the_chase_is_a_guarded_write_so_shadow_delivers_nothing(store, tmp_env, monkeypatch):
    """Everything outbound goes through shared.settings.guard_write. In
    MODE=shadow the chase is a would_do row and no HTTP request is made, the
    same as an Instantly reply or a GHL upsert."""
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.delenv("NOTIFY_SHADOW_SEND", raising=False)
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "advero-test-topic")
    notify_mod.reset_for_tests()
    http = []
    monkeypatch.setattr(notify_mod, "_send_ntfy",
                        lambda *a, **kw: http.append(a) or {"ok": True, "status": 200})

    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    out = A.escalate_pending(store=store, now=ct(*TUE, 10, 6))     # the real notify
    assert len(out) == 1
    assert out[0]["notified"]["shadow"] is True and out[0]["notified"]["sent"] is False
    assert http == []
    pushes = [r for r in read_shadow_log() if r["system"] == "notify"]
    assert pushes and "Still waiting on you" in str(pushes[-1]["payload"])


def test_a_push_that_raises_does_not_lose_the_tick_or_replay_the_rung(store, tmp_env):
    store.set("approval:a1", card(ct(*TUE, 10, 0)))

    def boom(*a, **kw):
        raise RuntimeError("ntfy down")

    out = A.escalate_pending(store=store, now=ct(*TUE, 10, 6), notify_fn=boom)
    assert out and out[0]["step"] == 1
    assert store.get("approval:a1")["escalations"] == 1


# ------------------------------------------------------- wired to a tick
def test_the_five_minute_poller_tick_runs_the_escalation(tmp_env, monkeypatch):
    """The SLA is five minutes, so the chase belongs on the */5 schedule that
    already exists rather than on a new cron nobody regenerated the change-set
    for."""
    store = JsonFileStore(tmp_env / "s.json")
    store.set("approval:a1", card(ct(*TUE, 10, 0)))
    monkeypatch.setattr(P, "fetch_new_replies",
                        lambda *a, **kw: {"items": [], "fetched": 0, "pages": 0,
                                          "truncated": False, "newest_seen": None})
    sent, fn = recorder()
    monkeypatch.setattr(notify_mod, "notify", fn)
    summary = P.run_once(instantly=object(), store=store, now=ct(*TUE, 10, 6))
    assert [e["step"] for e in summary["escalated"]] == [1]
    assert store.get("approval:a1")["escalations"] == 1
    assert store.get("approval:a1")["status"] == "pending"


def test_a_failing_escalation_does_not_stop_the_poll(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "s.json")
    monkeypatch.setattr(P, "fetch_new_replies",
                        lambda *a, **kw: {"items": [], "fetched": 0, "pages": 0,
                                          "truncated": False, "newest_seen": None})
    monkeypatch.setattr(A, "escalate_pending", lambda **kw: (_ for _ in ()).throw(RuntimeError("store down")))
    summary = P.run_once(instantly=object(), store=store, now=ct(*TUE, 10, 6))
    assert summary["escalated"] == []
    assert summary["errors"] == 0


def test_the_counter_is_written_under_the_key_it_was_read_from(store, tmp_env):
    """A card whose token half and store key disagree used to save the counter
    to a key nothing reads, so every tick would have chased it again forever."""
    store.set("approval:a1", card(ct(*TUE, 10, 0), token="somethingelse.sig"))
    sent, fn = recorder()
    A.escalate_pending(store=store, now=ct(*TUE, 10, 6), notify_fn=fn)
    assert store.get("approval:a1")["escalations"] == 1
    assert store.get("approval:somethingelse") is None
