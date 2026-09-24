"""The daily Resume reminder of a ladder stopped as ``template_unapproved``
is capped: it ends after TEMPLATE_STOP_REMINDER_MAX_PUSHES reminders, or
TEMPLATE_STOP_REMINDER_MAX_DAYS after the stop, whichever comes first. The
hold itself stays (the ladder remains stopped, nothing sends). A lead in the
90-day nurture gets no reminder; a nurture record that cannot be read still
reminds.

MODE stays shadow and ALLOW_LIVE_WRITES stays unset; NOTIFY stays off, so a
push is only recorded. Lead data is made up.
"""
from datetime import timedelta

from services.reply_engine import cadence
from services.reply_engine import nurture
from services.reply_engine.cadence import LeadState
from services.reply_engine.tests.test_ct3_ladder_holds import (  # noqa: F401 - fixtures
    _key, email_leg, link_of, no_channel, replies, secret, stall, tick_stored)
from services.reply_engine.tests.test_ct3_ladders import (  # noqa: F401 - fixtures
    LEAD, at_day, ct, public_base_url, store)

STOP = ct(2026, 9, 24, 10, 0)  # stall() stops the ladder on Thu 2026-09-24 at 10:00 CT


def _stopped(store, approvals_file):
    approvals_file.revoke_ids("cadence.d3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    pushes = []
    stall(state, store, pushes)
    assert len(pushes) == 1  # the stop push itself, not a reminder
    return pushes


def _hold(store):
    return store.get(_key())["cadence"]["template_hold"]


def _assert_still_held(store):
    cad = store.get(_key())["cadence"]
    assert cad["stopped_reason"] == "template_unapproved" and cad.get("template_hold")
    assert replies() == []


def test_constants():
    assert cadence.TEMPLATE_STOP_REMINDER_MAX_PUSHES == 8
    assert cadence.TEMPLATE_STOP_REMINDER_MAX_DAYS == 14


def test_reminders_stop_after_the_eighth_on_successive_days(store, tmp_env, secret, email_leg, approvals_file):
    pushes = _stopped(store, approvals_file)
    sent = 0
    for n in range(1, 13):  # Fri 09-25 .. Tue 10-06, all within 14 days of the stop
        when = STOP + timedelta(days=n, hours=-3)  # 07:00 CT
        before = len(pushes)
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        if n <= 8:
            assert res["action"] == "resume_link_sent" and len(pushes) == before + 1
            link_of(pushes[-1])
            sent += 1
            assert _hold(store)["link_count"] == sent
        else:
            assert res["action"] == "already_stopped" and res["reason"] == "template_unapproved"
            assert len(pushes) == before
    assert sent == cadence.TEMPLATE_STOP_REMINDER_MAX_PUSHES
    assert _hold(store)["link_count"] == 8 and _hold(store)["link_on"] == "2026-10-02"
    _assert_still_held(store)


def test_reminders_stop_after_fourteen_days_with_fewer_than_eight(store, tmp_env, secret, email_leg,
                                                                  approvals_file):
    pushes = _stopped(store, approvals_file)
    _, res = tick_stored(store, ct(2026, 9, 25, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and _hold(store)["link_count"] == 1
    # just under 14 days after the stop: still reminds
    _, res = tick_stored(store, ct(2026, 10, 8, 9, 59), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and _hold(store)["link_count"] == 2
    # 14 days after the stop, the next CT day and later: nothing, though only 2 went out
    for when in (ct(2026, 10, 9, 7, 0), ct(2026, 10, 12, 7, 0), ct(2026, 11, 2, 7, 0)):
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "already_stopped" and res["reason"] == "template_unapproved"
    assert len(pushes) == 3 and _hold(store)["link_count"] == 2
    _assert_still_held(store)


def test_the_fourteen_day_boundary_is_measured_from_stopped_at(store, tmp_env, secret, email_leg,
                                                               approvals_file):
    pushes = _stopped(store, approvals_file)
    _, res = tick_stored(store, STOP + timedelta(days=14), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "already_stopped" and len(pushes) == 1
    assert "link_count" not in _hold(store)


def test_once_per_day_is_unchanged_within_the_cap(store, tmp_env, secret, email_leg, approvals_file):
    pushes = _stopped(store, approvals_file)
    for day, hours in ((25, (7, 8, 12, 18)), (26, (7, 23)), (28, (7, 10))):
        for i, h in enumerate(hours):
            before = len(pushes)
            _, res = tick_stored(store, ct(2026, 9, day, h, 0), lambda *a, **k: pushes.append((a, k)))
            if i == 0:
                assert res["action"] == "resume_link_sent" and len(pushes) == before + 1
            else:
                assert res["action"] == "already_stopped" and len(pushes) == before
    assert len(pushes) == 4 and _hold(store)["link_count"] == 3


def test_a_legacy_record_without_the_count_loads_as_zero(store, tmp_env, secret, email_leg, approvals_file):
    pushes = _stopped(store, approvals_file)
    row = store.get(_key())
    hold = dict(row["cadence"]["template_hold"], link_on="2026-09-27")  # reminded before the cap existed
    hold.pop("link_count", None)
    row["cadence"] = dict(row["cadence"], template_hold=hold)
    store.set(_key(), row)
    assert "link_count" not in LeadState.from_store(store.get(_key())).cadence["template_hold"]
    _, res = tick_stored(store, ct(2026, 9, 27, 12, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "already_stopped" and len(pushes) == 1  # same-day guard still holds
    _, res = tick_stored(store, ct(2026, 9, 28, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and len(pushes) == 2
    assert _hold(store)["link_count"] == 1


def test_an_unreadable_count_counts_as_zero(store, tmp_env, secret, email_leg, approvals_file):
    pushes = _stopped(store, approvals_file)
    row = store.get(_key())
    row["cadence"] = dict(row["cadence"], template_hold=dict(row["cadence"]["template_hold"], link_count="x"))
    store.set(_key(), row)
    _, res = tick_stored(store, ct(2026, 9, 25, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and _hold(store)["link_count"] == 1


def test_the_hourly_job_persists_the_count(store, tmp_env, secret, email_leg, approvals_file):
    from jobs import cadence_tick as job

    pushes = _stopped(store, approvals_file)
    for n in range(1, 11):
        when = ct(2026, 9, 24, 7, 0) + timedelta(days=n)
        job.run(when, store, notify_fn=lambda *a, **k: pushes.append((a, k)), log_fn=lambda *a, **k: None)
    # Days 9 and 10 are past the cap: the job's once-a-day digest line says the
    # reminders ended (jobs/tests/test_cadence_tick_held_digest.py); no reminder.
    ended = [p for p in pushes if "daily reminders ended" in p[0][1]]
    assert len(ended) == 2
    pushes = [p for p in pushes if p not in ended]
    assert len(pushes) == 1 + cadence.TEMPLATE_STOP_REMINDER_MAX_PUSHES
    assert _hold(store)["link_count"] == 8
    _assert_still_held(store)


def test_an_enrolled_nurture_lead_gets_no_reminder(store, tmp_env, secret, email_leg, approvals_file):
    pushes = _stopped(store, approvals_file)
    nurture.enroll(LEAD, "no_reply_after_sequence", ct(2026, 9, 24, 12, 0), store=store)
    for when in (ct(2026, 9, 25, 7, 0), ct(2026, 9, 28, 7, 0)):
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "already_stopped" and res["resume_withheld"] == "nurture"
    assert len(pushes) == 1 and "link_count" not in _hold(store)
    _assert_still_held(store)


def test_a_nurture_read_error_still_reminds(store, tmp_env, secret, email_leg, approvals_file, monkeypatch):
    pushes = _stopped(store, approvals_file)

    def _boom(state, store=None):
        raise RuntimeError("store unreadable")

    monkeypatch.setattr(cadence, "in_nurture", _boom)
    _, res = tick_stored(store, ct(2026, 9, 25, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and len(pushes) == 2
    _assert_still_held(store)


# ================================ the one-time "ready to resume" push bypasses the cap
def _ready_pushes(pushes):
    return [p for p in pushes if "ready to resume" in p[0][0]]


def test_after_the_push_cap_approving_the_ids_sends_exactly_one_ready_push(store, tmp_env, secret, email_leg,
                                                                           approvals_file):
    pushes = _stopped(store, approvals_file)
    for n in range(1, 9):  # the 8 capped reminders, Fri 09-25 .. Fri 10-02
        tick_stored(store, ct(2026, 9, 24, 7, 0) + timedelta(days=n), lambda *a, **k: pushes.append((a, k)))
    _, res = tick_stored(store, ct(2026, 10, 3, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "already_stopped" and len(pushes) == 9 and _hold(store)["link_count"] == 8

    approvals_file.approve_ids("cadence.d3")
    _, res = tick_stored(store, ct(2026, 10, 3, 11, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and res["ready"] is True and len(pushes) == 10
    assert "approved" in pushes[-1][0][0] and pushes[-1][1]["priority"] == "high"
    link_of(pushes[-1])
    hold = _hold(store)
    assert hold["ready_announced"] is True and hold["link_count"] == 8  # not counted as a reminder
    # said once: the same day and the following days stay quiet (the cap still holds the daily reminder)
    for when in (ct(2026, 10, 3, 12, 0), ct(2026, 10, 4, 7, 0), ct(2026, 10, 5, 7, 0)):
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "already_stopped"
    assert len(pushes) == 10 and len(_ready_pushes(pushes)) == 1
    _assert_still_held(store)


def test_after_the_day_cap_approving_the_ids_sends_exactly_one_ready_push(store, tmp_env, secret, email_leg,
                                                                          approvals_file):
    pushes = _stopped(store, approvals_file)
    _, res = tick_stored(store, ct(2026, 10, 9, 7, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "already_stopped" and len(pushes) == 1

    approvals_file.approve_ids("cadence.d3")
    _, res = tick_stored(store, ct(2026, 10, 9, 8, 0), lambda *a, **k: pushes.append((a, k)))
    assert res["action"] == "resume_link_sent" and res["ready"] is True and len(pushes) == 2
    for when in (ct(2026, 10, 9, 9, 0), ct(2026, 10, 10, 7, 0)):
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "already_stopped"
    assert len(pushes) == 2 and len(_ready_pushes(pushes)) == 1
    _assert_still_held(store)


def test_the_ready_push_is_withheld_for_a_nurture_lead(store, tmp_env, secret, email_leg, approvals_file):
    pushes = _stopped(store, approvals_file)
    nurture.enroll(LEAD, "no_reply_after_sequence", ct(2026, 9, 24, 12, 0), store=store)
    approvals_file.approve_ids("cadence.d3")
    for when in (ct(2026, 9, 25, 7, 0), ct(2026, 10, 9, 7, 0)):
        _, res = tick_stored(store, when, lambda *a, **k: pushes.append((a, k)))
        assert res["action"] == "already_stopped" and res["resume_withheld"] == "nurture"
    assert len(pushes) == 1 and not _hold(store).get("ready_announced")
    _assert_still_held(store)
