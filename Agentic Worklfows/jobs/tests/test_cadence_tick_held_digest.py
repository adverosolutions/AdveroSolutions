"""A ladder stopped as ``template_unapproved`` whose daily Resume reminder has
reached its cap (cadence.template_reminders_ended) still reaches Lorenzo: the
hourly job adds one counts-only line to its digest, at most once a CT day.

MODE stays shadow and ALLOW_LIVE_WRITES stays unset; pushes are captured by
the injected notify_fn. Lead data is made up.
"""
from datetime import timedelta

from jobs import cadence_tick as job
from services.reply_engine import cadence
from services.reply_engine import nurture
from services.reply_engine.cadence import LeadState
from services.reply_engine.tests.test_ct3_ladder_holds import (  # noqa: F401 - fixtures
    _key, email_leg, no_channel, secret, stall)
from services.reply_engine.tests.test_ct3_ladders import (  # noqa: F401 - fixtures
    COMPANY, LEAD, at_day, ct, public_base_url, store)

STOP = ct(2026, 9, 24, 10, 0)  # stall() stops the ladder on Thu 2026-09-24 at 10:00 CT
ENDED = "daily reminders ended"


def _held(**cad):
    return LeadState(lead_email=LEAD, campaign_id="c", cadence=dict(
        {"armed_at": "2026-09-01T10:00:00-05:00", "stopped_reason": "template_unapproved",
         "stopped_at": STOP.isoformat(), "template_hold": {"template_id": "cadence.d3", "link_count": 1}}, **cad))


# -- the helper ---------------------------------------------------------------

def test_helper_true_at_the_eighth_reminder():
    state = _held(template_hold={"link_count": 8})
    assert cadence.template_reminders_ended(state, STOP + timedelta(days=1))
    assert not cadence.template_reminders_ended(_held(template_hold={"link_count": 7}), STOP + timedelta(days=1))


def test_helper_true_fourteen_days_after_the_stop_with_fewer():
    state = _held(template_hold={"link_count": 2})
    assert not cadence.template_reminders_ended(state, STOP + timedelta(days=14, seconds=-1))
    assert cadence.template_reminders_ended(state, STOP + timedelta(days=14))


def test_helper_false_below_both_and_when_not_a_template_stop():
    assert not cadence.template_reminders_ended(_held(), STOP + timedelta(days=3))
    for reason in (None, "inbound_reply", "nurture", "follow_up_later"):
        state = _held(stopped_reason=reason, template_hold={"link_count": 20})
        assert not cadence.template_reminders_ended(state, STOP + timedelta(days=30))
    assert not cadence.template_reminders_ended(LeadState(lead_email=LEAD, campaign_id="c"), STOP)


def test_helper_reads_a_legacy_row_without_the_count():
    state = _held(template_hold={"template_id": "cadence.d3"})
    assert not cadence.template_reminders_ended(state, STOP + timedelta(days=5))
    assert cadence.template_reminders_ended(state, STOP + timedelta(days=15))
    # no stopped_at either: only the count could end it, and there is none
    assert not cadence.template_reminders_ended(_held(stopped_at=None, template_hold={}), STOP + timedelta(days=90))
    assert cadence.template_reminders_ended(_held(stopped_at=None, template_hold={"link_count": "8"}), STOP)


# -- the hourly job -----------------------------------------------------------

def _capped(store, approvals_file):
    """A stopped ladder whose reminders ended by the 14-day rule (no reminder
    sent at all: link_count absent)."""
    approvals_file.revoke_ids("cadence.d3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))
    stall(state, store, [])
    return state


def _run(store, when, pushes, **kw):
    return job.run(when, store, notify_fn=lambda *a, **k: pushes.append((a, k)), log_fn=lambda *a, **k: None, **kw)


def _ended(pushes):
    return [p for p in pushes if ENDED in p[0][1]]


def test_the_line_goes_once_a_ct_day(store, tmp_env, secret, email_leg, approvals_file):
    _capped(store, approvals_file)
    pushes = []
    day1 = STOP + timedelta(days=15, hours=-3)  # Fri 10-09 07:00 CT
    summary = _run(store, day1, pushes)
    assert summary["reminders_ended"] == 1 and len(pushes) == 1
    (title, message), kw = pushes[0]
    assert title.startswith("[shadow] Cadence ")
    assert message == ("1 follow-up ladder is still held on an email you haven't approved yet; its daily reminders "
                       "ended. Approve it in the emails doc (a Resume link then comes at once), or answer the lead "
                       "by hand.")
    assert "approve_templates" not in message
    for private in (LEAD, COMPANY, "Dana", "examplecleaning", "http"):
        assert private not in title and private not in message
    assert store.get(job.REMINDERS_ENDED_KEY)["on"] == "2026-10-09"
    # later the same CT day: nothing new
    for h in (1, 5, 16):
        summary = _run(store, day1 + timedelta(hours=h), pushes)
        assert summary["reminders_ended"] == 1
    assert len(pushes) == 1
    # the next CT day it goes again, once
    _run(store, day1 + timedelta(days=1), pushes)
    _run(store, day1 + timedelta(days=1, hours=2), pushes)
    assert len(_ended(pushes)) == 2 == len(pushes)
    assert store.get(job.REMINDERS_ENDED_KEY)["on"] == "2026-10-10"
    assert store.get(_key())["cadence"]["stopped_reason"] == "template_unapproved"


def test_counts_several_and_says_nothing_at_zero(store, tmp_env, secret, email_leg, approvals_file):
    state = _capped(store, approvals_file)
    pushes = []
    # within the cap the reminder itself goes; no "ended" line
    _run(store, STOP + timedelta(days=1, hours=-3), pushes)
    assert pushes and not _ended(pushes)
    assert store.get(job.REMINDERS_ENDED_KEY) is None
    # a second capped ladder
    other = LeadState.from_store(store.get(_key()))
    other.lead_email = "other@examplecleaning.test"
    store.set(other.key, other.to_store())
    del pushes[:]
    summary = _run(store, STOP + timedelta(days=20), pushes)
    assert summary["reminders_ended"] == 2
    assert [p[0][1] for p in _ended(pushes)] == [
        "2 follow-up ladders are still held on emails you haven't approved yet; their daily reminders ended. "
        "Approve them in the emails doc (a Resume link then comes at once), or answer the leads by hand."]
    assert state.key != other.key


def test_no_push_when_nothing_is_capped(store, tmp_env, approvals_file):
    pushes = []
    summary = _run(store, STOP, pushes)
    assert summary["reminders_ended"] == 0 and pushes == []
    assert store.get(job.REMINDERS_ENDED_KEY) is None


def test_a_nurtured_lead_is_not_counted(store, tmp_env, secret, email_leg, approvals_file):
    _capped(store, approvals_file)
    nurture.enroll(LEAD, "no_reply_after_sequence", ct(2026, 9, 24, 12, 0), store=store)
    pushes = []
    summary = _run(store, STOP + timedelta(days=15), pushes)
    assert summary["reminders_ended"] == 0 and not _ended(pushes)
    assert store.get(job.REMINDERS_ENDED_KEY) is None


def test_dry_run_sends_nothing_and_writes_no_marker(store, tmp_env, secret, email_leg, approvals_file):
    _capped(store, approvals_file)
    pushes = []
    summary = _run(store, STOP + timedelta(days=15), pushes, dry_run=True)
    assert summary["reminders_ended"] == 0 and pushes == []
    assert store.get(job.REMINDERS_ENDED_KEY) is None
    # the live-shadow run afterwards still says it that day
    _run(store, STOP + timedelta(days=15), pushes)
    assert len(_ended(pushes)) == 1
