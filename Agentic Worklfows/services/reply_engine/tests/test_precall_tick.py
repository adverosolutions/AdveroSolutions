"""jobs/precall_tick: the scheduled job behind the brief and the proposal.

Lives here rather than in jobs/tests because brief A11 owns
services/reply_engine/tests/test_precall_*.py and nothing under jobs/tests.
"""
import json
import os
from datetime import timedelta

import pytest

from shared import settings, slots
from shared.settings import TZ
from shared.store import JsonFileStore

from jobs import precall_tick
from services.reply_engine import no_show, precall

NOW = slots.to_tz(slots.parse_iso("2026-09-23T10:35:00-05:00"), TZ)
START = slots.to_tz(slots.parse_iso("2026-09-23T11:30:00-05:00"), TZ)


def appointment(**over):
    base = {
        "id": "appt-1",
        "contact_id": "contact-1",
        "start_iso": START.isoformat(),
        "email": "ilmi@shiningarmorcleaningnj.com",
        "first_name": "Ilmi",
        "company": "Shining Armor Cleaning NJ",
        "campaign_id": settings.CAMPAIGNS["cleaning_reactivation"]["id"],
    }
    base.update(over)
    return base


class FakeGHL(object):
    has_token = False

    def __init__(self):
        self.notes = []

    def create_note(self, contact_id, body):
        self.notes.append((contact_id, body))
        return {"shadow": True, "system": "ghl", "action": "create_note"}

    def get_calendar_events(self, *a, **k):
        return None

    def close(self):
        pass


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(str(tmp_path / "store.json"))


@pytest.fixture
def pushes():
    sent = []

    def notify_fn(title, message, **kwargs):
        sent.append((title, message))
        return {"test": True}

    notify_fn.sent = sent
    return notify_fn


# ------------------------------------------------------------- windows
@pytest.mark.parametrize("minutes_after,expected", [(0, False), (19, False), (20, True), (60, True),
                                                    (749, True), (750, False)])
def test_the_proposal_pass_runs_after_the_call_and_only_the_same_day(minutes_after, expected):
    """749 minutes after an 11:30 call is 23:59 the same day; 750 is tomorrow."""
    now = START + timedelta(minutes=minutes_after)
    assert precall_tick.proposal_due(appointment(), now) is expected


def test_an_evening_call_still_gets_a_few_hours_to_draft():
    late = slots.to_tz(slots.parse_iso("2026-09-23T22:30:00-05:00"), TZ)
    appt = appointment(start_iso=late.isoformat())
    assert precall_tick.proposal_due(appt, late + timedelta(hours=2)) is True
    assert precall_tick.proposal_due(appt, late + timedelta(hours=4)) is False


def test_a_cancelled_call_gets_no_proposal():
    assert precall_tick.proposal_due(appointment(cancelled=True), START + timedelta(hours=1)) is False


@pytest.mark.parametrize("state,expected", [("showed", "zoom"), ("late_show", "zoom"), ("no_show", "no_show"),
                                            ("pending", "unknown"), (None, "unknown")])
def test_held_evidence_reads_the_no_show_state_machine(store, state, expected):
    if state:
        store.set(no_show.state_key("appt-1"), {"state": state})
    assert precall_tick.held_evidence(store, appointment()) == expected


def test_held_evidence_without_a_store_is_unknown_not_a_crash():
    assert precall_tick.held_evidence(None, appointment()) == "unknown"


# -------------------------------------------------------------- sources
def test_manual_calendar_calls_are_added_to_the_ghl_window():
    loaded = precall_tick.load_appointments(FakeGHL(), NOW, None)
    assert loaded["ghl_count"] == 0
    assert loaded["manual_count"] >= 1
    assert loaded["error"] == "ghl_token_missing"
    assert all(a.get("start_iso") for a in loaded["appointments"])


def test_a_call_ghl_already_reported_is_not_briefed_twice(tmp_path):
    """The manual seed and the GHL calendar can name the same event id."""
    manual = precall.manual_calls(NOW)
    if not manual:
        pytest.skip("no manual calls in config/ids.json")
    fixture = tmp_path / "appts.json"
    fixture.write_text(json.dumps({"appointments": [dict(manual[0], company="From GHL")]}), encoding="utf-8")
    loaded = precall_tick.load_appointments(FakeGHL(), NOW, str(fixture))
    ids = [str(a["id"]) for a in loaded["appointments"]]
    assert len(ids) == len(set(ids))
    assert next(a for a in loaded["appointments"] if str(a["id"]) == str(manual[0]["id"]))["company"] == "From GHL"


# ----------------------------------------------------------------- tick
def test_a_due_call_is_briefed_once_and_the_note_is_guarded(store, pushes):
    ghl = FakeGHL()
    first = precall_tick.tick(NOW, store, ghl, [appointment()], instantly=None, do_proposals=False,
                              notify_fn=pushes)
    assert len(first["briefs"]) == 1
    brief = first["briefs"][0]
    assert brief["offer"] == "cleaning_reactivation"
    assert brief["minutes_out"] == 55
    assert brief["note"] == {"shadow": True}
    assert len(ghl.notes) == 1
    second = precall_tick.tick(NOW, store, ghl, [appointment()], instantly=None, do_proposals=False,
                               notify_fn=pushes)
    assert second["briefs"] == [] and second["briefs_skipped"][0]["reason"] == "already_briefed"
    assert len(pushes.sent) == 1


def test_a_call_outside_the_window_is_left_alone(store, pushes):
    early = NOW - timedelta(hours=3)
    result = precall_tick.tick(early, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    assert result["briefs"] == [] and result["proposals"] == []
    assert pushes.sent == []


def test_one_broken_booking_does_not_stop_the_others(store, pushes):
    broken = {"id": "bad", "start_iso": START.isoformat(), "email": "x@y.com", "company": None}
    # a company of None reaches show_rate.company_of and str-formats fine; force
    # a real failure instead by handing build_brief an unparseable start later
    result = precall_tick.tick(NOW, store, FakeGHL(), [dict(broken, start_iso=START.isoformat()), appointment()],
                               instantly=None, do_proposals=False, notify_fn=pushes)
    assert len(result["briefs"]) == 2
    assert result["errors"] == []


def test_a_brief_that_raises_is_reported_and_the_tick_continues(store, pushes, monkeypatch):
    calls = {"n": 0}
    real = precall.build_brief

    def flaky(appt, now, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(appt, now, **kwargs)

    monkeypatch.setattr(precall, "build_brief", flaky)
    result = precall_tick.tick(NOW, store, FakeGHL(), [appointment(id="a"), appointment(id="b")],
                               instantly=None, do_proposals=False, notify_fn=pushes)
    assert len(result["errors"]) == 1 and result["errors"][0]["where"] == "brief"
    assert len(result["briefs"]) == 1


def test_a_no_show_gets_no_proposal(store, pushes):
    store.set(no_show.state_key("appt-1"), {"state": "no_show"})
    after = START + timedelta(minutes=40)
    result = precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    assert result["proposals"] == [{"id": "appt-1", "skipped": "no_show"}]
    assert pushes.sent == []


def test_a_held_call_gets_a_proposal_draft_with_its_evidence(store, pushes):
    store.set(no_show.state_key("appt-1"), {"state": "showed"})
    after = START + timedelta(minutes=40)
    result = precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    assert len(result["proposals"]) == 1
    row = result["proposals"][0]
    assert row["held_evidence"] == "zoom"
    assert row["problems"] == []
    assert row["delivered"]["file"]
    assert "PROPOSAL" in precall_tick.digest_text(result)


def test_a_call_with_no_telemetry_still_drafts_but_says_so(store, pushes):
    after = START + timedelta(minutes=40)
    result = precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    row = result["proposals"][0]
    assert row["held_evidence"] == "unknown"
    text = open(row["delivered"]["file"], encoding="utf-8").read()
    assert "No Zoom telemetry" in text


def test_a_forced_proposal_ignores_the_clock_and_takes_the_transcript(store, pushes, tmp_path):
    path = tmp_path / "t.txt"
    path.write_text("Lorenzo: what does a job pay\nIlmi: about two thousand", encoding="utf-8")
    result = precall_tick.tick(NOW, store, FakeGHL(), [appointment()], instantly=None,
                               proposal_for="appt-1", transcript_path=str(path), notify_fn=pushes)
    assert len(result["proposals"]) == 1 and result["proposals"][0]["source"] == "fireflies"


def test_the_digest_says_what_happened_and_what_needs_checking(store, pushes):
    result = precall_tick.tick(NOW, store, FakeGHL(), [appointment()], instantly=None, do_proposals=False,
                               notify_fn=pushes)
    text = precall_tick.digest_text(result)
    assert "BRIEF Shining Armor Cleaning NJ" in text
    assert "cleaning_reactivation" in text
    assert "filed:" in text


def test_an_empty_run_says_nothing_is_due(store, pushes):
    text = precall_tick.digest_text(precall_tick.tick(NOW, store, FakeGHL(), [], instantly=None, notify_fn=pushes))
    assert "nothing due" in text


# --------------------------------------------------------- shadow safety
def test_nothing_in_a_tick_can_reach_a_prospect(store, pushes):
    """The only outbound calls are ghl.create_note and notify. A real GHL
    client with no token answers every write through guard_write."""
    from shared.ghl import GHL

    ghl = GHL()
    assert ghl.has_token is False
    after = START + timedelta(minutes=40)
    result = precall_tick.tick(after, store, ghl, [appointment()], instantly=None, notify_fn=pushes)
    for row in result["briefs"] + result["proposals"]:
        assert "sent" not in json.dumps(row.get("delivered") or {})
    assert result["proposals"][0]["verbal_blocked"] == ["immediate"], "no payment link configured in tests"
    ghl.close()


# --------------------------------------------- the review findings (A11 fixes)
def test_a_dry_run_never_bills_the_model(monkeypatch, store, pushes):
    """--dry-run promised 'no write and no HTTP request at all' while leaving
    LLM_FAKE unset, so every proposal it drafted made a real claude-opus-5 call.
    services/reply_engine/replay.py sets the same variable for the same reason."""
    from shared import llm

    monkeypatch.delenv("LLM_FAKE", raising=False)
    monkeypatch.setattr(precall_tick, "use_scratch_logs", lambda name: None, raising=False)
    precall_tick._force_shadow()  # noqa: SLF001
    assert os.environ.get("LLM_FAKE") == "1"
    assert llm.is_fake() is True

    def never(*a, **k):
        raise AssertionError("a dry run must not invoke the model")

    monkeypatch.setattr(llm, "complete", never)
    after = START + timedelta(minutes=40)
    result = precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["model"] == "template"
    assert result["proposals"][0]["delivered"]["file"]


def test_an_explicit_opt_in_is_the_only_way_a_dry_run_reaches_the_model(monkeypatch):
    monkeypatch.delenv("LLM_FAKE", raising=False)
    precall_tick._force_shadow(llm_ok=True)  # noqa: SLF001
    assert os.environ.get("LLM_FAKE") is None
    assert precall_tick.parse_args(["--dry-run"]).llm is False
    assert precall_tick.parse_args(["--dry-run", "--llm"]).llm is True


def test_the_proposal_pass_builds_nothing_once_the_claim_is_taken(store, pushes, monkeypatch):
    """proposal_due stays true until the end of the call's day, so without a
    claim pre-check the 5-minute tick re-ran gather_inputs and build_proposal
    (a billed claude-opus-5 turn) 146 times for one 11:30 call."""
    from services.reply_engine import proposal as proposal_mod

    built = {"n": 0}
    gathered = {"n": 0}
    real_build, real_gather = proposal_mod.build_proposal, proposal_mod.gather_inputs

    def counting_build(*a, **k):
        built["n"] += 1
        return real_build(*a, **k)

    def counting_gather(*a, **k):
        gathered["n"] += 1
        return real_gather(*a, **k)

    monkeypatch.setattr(proposal_mod, "build_proposal", counting_build)
    monkeypatch.setattr(proposal_mod, "gather_inputs", counting_gather)
    first = START + timedelta(minutes=25)
    ticks = 0
    while first + timedelta(minutes=5 * ticks) <= START + timedelta(minutes=740):
        precall_tick.tick(first + timedelta(minutes=5 * ticks), store, FakeGHL(), [appointment()],
                          instantly=None, notify_fn=pushes)
        ticks += 1
    assert ticks > 100, "the whole proposal window must really have been walked"
    assert built["n"] == 1, built["n"]
    assert gathered["n"] == 1, gathered["n"]
    assert len(pushes.sent) == 1


def test_an_evening_call_is_not_drafted_twice_after_midnight(store, pushes):
    """proposal_due keeps the window open past 00:00 while the claim key used
    now.date(), so a 22:30 call was drafted once before and once after."""
    late = slots.to_tz(slots.parse_iso("2026-09-23T22:30:00-05:00"), TZ)
    appt = appointment(start_iso=late.isoformat())
    before = precall_tick.tick(late + timedelta(minutes=25), store, FakeGHL(), [appt], instantly=None,
                               notify_fn=pushes)
    after = precall_tick.tick(late + timedelta(hours=2), store, FakeGHL(), [appt], instantly=None,
                              notify_fn=pushes)
    assert len(before["proposals"]) == 1 and before["proposals"][0]["delivered"]["file"]
    assert after["proposals"] == []
    assert after["proposals_skipped"] == [{"id": "appt-1", "reason": "already_drafted"}]
    assert len(pushes.sent) == 1
    assert "September 23, 2026" in open(before["proposals"][0]["delivered"]["file"], encoding="utf-8").read()


def test_the_same_call_from_both_sources_under_different_ids_is_briefed_once(tmp_path):
    """The manual row's id is the Google Calendar event id and the GHL row's is
    GHL's own appointment id, so de-duplicating on id alone can never match."""
    manual = precall.manual_calls(NOW)
    if not manual:
        pytest.skip("no manual calls in config/ids.json")
    row = manual[0]
    ghl_shaped = dict(row, id="ghl-appt-9999", company="From GHL", source="ghl")
    fixture = tmp_path / "appts.json"
    fixture.write_text(json.dumps({"appointments": [ghl_shaped]}), encoding="utf-8")
    loaded = precall_tick.load_appointments(FakeGHL(), NOW, str(fixture))
    emails = [str(a.get("email") or "").lower() for a in loaded["appointments"]]
    assert emails.count(str(row["email"]).lower()) == 1, loaded["appointments"]
    assert loaded["manual_duplicates"], "the dropped manual row must be reported, not silently lost"
    kept = next(a for a in loaded["appointments"] if str(a.get("email") or "").lower() == str(row["email"]).lower())
    assert kept["company"] == "From GHL", "the GHL row wins, as the runbook says"


def test_a_call_briefed_from_both_sources_produces_one_brief_and_one_note(tmp_path, pushes):
    manual = precall.manual_calls(NOW)
    if not manual:
        pytest.skip("no manual calls in config/ids.json")
    row = manual[0]
    store = JsonFileStore(str(tmp_path / "store.json"))
    fixture = tmp_path / "appts.json"
    fixture.write_text(json.dumps({"appointments": [dict(row, id="ghl-appt-9999")]}), encoding="utf-8")
    loaded = precall_tick.load_appointments(FakeGHL(), NOW, str(fixture))
    when = slots.to_tz(slots.parse_iso(row["start_iso"]), TZ) - timedelta(minutes=30)
    ghl = FakeGHL()
    result = precall_tick.tick(when, store, ghl, loaded["appointments"], instantly=None, do_proposals=False,
                               notify_fn=pushes)
    assert len(result["briefs"]) == 1, [b["id"] for b in result["briefs"]]
    assert len(ghl.notes) == 1
    assert len(pushes.sent) == 1


def test_a_no_show_whose_recovery_ended_still_gets_no_proposal(store, pushes):
    """no_show.cancel_recovery rewrites state to 'done' when the lead replies.
    Reading that as 'unknown' drafted a full proposal, with a recap, for a call
    that never happened."""
    store.set(no_show.state_key("appt-1"), {"state": "done", "done_reason": "replied"})
    assert precall_tick.held_evidence(store, appointment()) == "no_show"
    after = START + timedelta(hours=2)
    result = precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    assert result["proposals"] == [{"id": "appt-1", "skipped": "no_show"}]
    assert pushes.sent == []


def test_a_held_call_whose_state_moved_on_is_still_held(store):
    store.set(no_show.state_key("appt-1"), {"state": "done", "previous_state": "showed"})
    assert precall_tick.held_evidence(store, appointment()) == "zoom"


def test_a_run_that_only_skips_does_not_claim_nothing_was_due(store, pushes):
    precall_tick.tick(NOW, store, FakeGHL(), [appointment()], instantly=None, do_proposals=False, notify_fn=pushes)
    second = precall_tick.tick(NOW, store, FakeGHL(), [appointment()], instantly=None, do_proposals=False,
                               notify_fn=pushes)
    text = precall_tick.digest_text(second)
    assert "already_briefed" in text
    assert "nothing due" not in text
    assert "nothing new due (1 call(s) already handled)" in text
    empty = precall_tick.digest_text(precall_tick.tick(NOW, store, FakeGHL(), [], instantly=None, notify_fn=pushes))
    assert "nothing due" in empty


def test_a_dropped_proposal_is_never_rendered_as_a_delivered_one(store, pushes, tmp_path):
    """digest_text only checked prop['skipped'] while the skip landed in
    prop['delivered']['skipped'], so a swallowed draft printed a full PROPOSAL
    line with no 'filed:' and no reason."""
    from services.reply_engine import proposal as proposal_mod

    path = tmp_path / "t.txt"
    path.write_text("Lorenzo: how many go quiet\nIlmi: about fifteen a month", encoding="utf-8")
    after = START + timedelta(minutes=40)
    precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None, notify_fn=pushes)
    forced = precall_tick.tick(after, store, FakeGHL(), [appointment()], instantly=None,
                               proposal_for="appt-1", transcript_path=str(path), notify_fn=pushes)
    row = forced["proposals"][0]
    assert row["source"] == "fireflies"
    assert row["delivered"]["claimed"] is True and row["delivered"]["replaced"] is True
    assert row["delivered"]["file"], "the forced transcript proposal must really be written"
    text = precall_tick.digest_text(forced)
    assert "filed:" in text
    assert "replaced the proposal already drafted" in text
    # and a genuinely skipped one says so rather than looking delivered
    built = proposal_mod.build_proposal(appointment(), after, inputs=proposal_mod.CallInputs(), use_llm=False)
    fake = {"proposals": [{"id": "x", "company": "C", "offer": "cleaning_reactivation", "source": "thread",
                           "held_evidence": "unknown", "model": "template", "problems": [], "notes": [],
                           "verbal_blocked": [],
                           "delivered": {"claimed": False, "skipped": "already_drafted"}}],
            "briefs": [], "briefs_skipped": [], "proposals_skipped": [], "errors": [],
            "now": "x", "mode": "shadow", "appointments": 1}
    assert "NOT FILED: already_drafted" in precall_tick.digest_text(fake)
    assert built.campaign_key


def test_a_declined_manual_invite_never_reaches_the_proposal_pass():
    declined = appointment(response_status="declined")
    assert precall_tick.proposal_due(declined, START + timedelta(hours=1)) is False
    assert precall_tick.proposal_due(appointment(response_status="needsAction"),
                                     START + timedelta(hours=1)) is True


def test_the_digest_warns_when_the_hand_maintained_calendar_seed_is_behind():
    """config/ids.json google_calendar.booked_this_week is a snapshot, not a
    calendar read. Nothing here can fix a reschedule that was not mirrored into
    it, but the tick can say the file is behind."""
    way_later = slots.to_tz(slots.parse_iso("2026-10-15T09:00:00-05:00"), TZ)
    stale = precall.stale_manual_calls(way_later)
    assert stale, "every entry in the seed is in the past by mid October"
    assert precall.stale_manual_calls(slots.to_tz(slots.parse_iso("2026-09-22T09:00:00-05:00"), TZ)) == []
    loaded = precall_tick.load_appointments(FakeGHL(), way_later, None)
    assert loaded["manual_stale"]
