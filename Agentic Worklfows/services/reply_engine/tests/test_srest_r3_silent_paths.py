"""S-rest round 3: the last silent paths the max-effort reviewer found.

1. poller._push_stuck: the "Replies with no owner" push is recorded, repeats
   on the expired-card backoff (5/15/30/60/120 min, then hourly) while no push
   about the card has been delivered, is UNANSWERED from attempt 6, logs
   push_failed when it is not delivered, says what send_failed really means,
   and survives a restart. Once a push has been delivered, the card is
   reminded once a business day inside sending hours (round 4, defect 2;
   test_srest_r4_poller.py covers that schedule).
2. show_rate.release_hold: a marker whose read AND delete fail is an error,
   logged once per call (and alerted by the approval path), and retried on
   every later tick until it goes through.
3. no_show.reserve_recovery_slots is gone; the real claim_recovery_slots path
   never leaves one time held by two leads.
4. booking._hold_new_appointment reads the hold tri-state and re-reads once
   before rolling back; the rollback line says the hold could not be checked.

Every lead here is fictional; every client is an in-process fake.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from shared import job_log, notify
from shared import slots as slot_rules
from shared.store import JsonFileStore

from services.reply_engine import approval as A
from services.reply_engine import booking
from services.reply_engine import no_show as ns
from services.reply_engine import poller as P
from services.reply_engine import show_rate
from services.reply_engine.models import LeadState

CT = pytz.timezone("America/Chicago")


def ct(*args):
    return CT.localize(datetime(*args))


LEAD = "owner@brightfieldcleaning.example"
OTHER = "office@maplegrovebooks.example"
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"


@pytest.fixture
def rows(monkeypatch):
    out = []
    real = job_log.log_run

    def capture(job, status, details=None):
        out.append((job, status, details))
        return real(job, status, details)

    monkeypatch.setattr(job_log, "log_run", capture)
    return out


def _statuses(rows, status):
    return [d for (_job, s, d) in rows if s == status]


# ====================================================== 1. the stuck push
T0 = ct(2026, 9, 21, 21, 10)


def _stuck_card(store, approval_id="failed", status="send_failed", lead=LEAD,
                decided_at="2026-09-21T20:02:00-05:00"):
    store.set("approval:%s" % approval_id, {"status": status, "lead_email": lead,
                                            "created_at": "2026-09-21T20:00:00-05:00",
                                            "decided_at": decided_at, "notify_result": {"sent": True}})


def _tick(store, now):
    return P._push_stuck(store, P.pending_approvals(store, now), now)


def _undelivered(monkeypatch, pushes):
    def down(title, message, **kw):
        pushes.append({"title": title, "message": message, "priority": kw.get("priority")})
        return {"sent": False, "test": False, "shadow": False, "errors": ["ntfy: connection refused"]}

    monkeypatch.setattr(notify, "notify", down)


def test_send_failed_wording_says_the_send_may_have_gone_out(tmp_env):
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    _stuck_card(store, "stale", status="stale_slots", lead=OTHER)
    waiting = {w["lead"]: w for w in P.pending_approvals(store, T0)}
    failed_why = waiting[LEAD]["why"]
    assert "the send failed or may not have gone out" in failed_why
    assert "Check the thread in Instantly before you press Retry" in failed_why
    assert "no answer" not in failed_why
    assert "no answer" in waiting[OTHER]["why"]           # stale_slots: refused before it started
    assert "no answer" not in P.stuck_why("sending")
    assert sorted(P._push_stuck(store, list(waiting.values()), T0)) == ["failed", "stale"]
    push = notify.sent_in_test[-1]
    assert "may not have gone out" in push["message"]
    assert "have not been answered" not in push["message"]
    assert "\u2014" not in push["message"]


def test_the_stuck_push_is_recorded_backs_off_and_escalates_to_unanswered(tmp_env, monkeypatch, rows):
    pushes = []
    _undelivered(monkeypatch, pushes)
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    ts = T0
    assert _tick(store, ts) == ["failed"]
    rec = store.get(P.STUCK_PUSH_KEY)["failed"]
    assert rec["attempts"] == 1 and rec["status"] == "send_failed" and rec["errors"]
    assert rec["next_at"] == (ts + timedelta(minutes=5)).isoformat()
    attempts = [1]
    # the expired-card ladder: 5, 15, 30, 60, 120 minutes, then hourly
    for wait in (5, 15, 30, 60, 120, 60, 60):
        assert _tick(store, ts + timedelta(minutes=wait - 1)) == [], "pushed before the backoff was up"
        ts = ts + timedelta(minutes=wait)
        assert _tick(store, ts) == ["failed"]
        attempts.append(store.get(P.STUCK_PUSH_KEY)["failed"]["attempts"])
    assert attempts == [1, 2, 3, 4, 5, 6, 7, 8]
    titles = [p["title"] for p in pushes]
    assert titles[0] == "Replies with no owner: 1"
    assert titles[1] == "Replies with no owner: 1 (attempt 2)"
    assert not any("UNANSWERED" in t for t in titles[:5])
    assert titles[5].startswith("UNANSWERED (attempt 6)") and titles[7].startswith("UNANSWERED (attempt 8)")
    assert [p["priority"] for p in pushes] == ["high"] * 5 + ["urgent"] * 3
    assert "Earlier pushes not delivered" in pushes[1]["message"]
    failed = _statuses(rows, "push_failed")
    assert len(failed) == 8 and all(d["kind"] == "stuck_card" for d in failed)
    assert failed[0]["approvals"] == ["failed"] and failed[0]["leads"] == [LEAD]
    assert [d["escalated"] for d in failed] == [False] * 5 + [True] * 3
    assert store.get(P.STUCK_PUSH_KEY)["failed"]["escalated"] is True


def test_a_delivered_push_still_repeats_while_the_card_stays_stuck(tmp_env, rows):
    """Delivered is not handled: a send_failed owner card never expires, so
    this push is the only alert for its held call. Round 4 (defect 2): once a
    push was delivered it repeats once a business day inside sending hours,
    not 5 minutes later (it used to: 26 pushes in 24 hours, 8 at night)."""
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    assert _tick(store, T0) == ["failed"]                              # Monday 21:10
    assert _tick(store, T0 + timedelta(minutes=4)) == []
    assert _tick(store, T0 + timedelta(minutes=5)) == []
    assert _tick(store, ct(2026, 9, 22, 6, 55)) == []                  # not before sending hours
    assert _tick(store, ct(2026, 9, 22, 7, 0)) == ["failed"]           # Tuesday 07:00
    assert _tick(store, ct(2026, 9, 22, 12, 0)) == []                  # once that business day
    assert len(notify.sent_in_test) == 2
    assert notify.sent_in_test[1]["title"] == "Replies with no owner: 1 (reminder)"
    assert notify.sent_in_test[1]["priority"] == "high"
    assert store.get(P.STUCK_PUSH_KEY)["failed"]["delivered"] == 2
    assert _statuses(rows, "push_failed") == []


def test_a_restart_neither_re_spams_nor_forgets(tmp_env, monkeypatch):
    pushes = []
    _undelivered(monkeypatch, pushes)
    path = tmp_env / "s.json"
    _stuck_card(JsonFileStore(path))
    assert _tick(JsonFileStore(path), T0) == ["failed"]
    # a new process on the same store, one minute later: nothing is due
    assert _tick(JsonFileStore(path), T0 + timedelta(minutes=1)) == []
    # ...and it remembers where the ladder was
    assert _tick(JsonFileStore(path), T0 + timedelta(minutes=5)) == ["failed"]
    assert len(pushes) == 2 and pushes[1]["title"].endswith("(attempt 2)")


def test_two_overlapping_ticks_push_once(tmp_env):
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    waiting = P.pending_approvals(store, T0)
    assert P._push_stuck(store, waiting, T0) == ["failed"]
    assert P._push_stuck(JsonFileStore(tmp_env / "s.json"), waiting, T0) == []
    assert len(notify.sent_in_test) == 1


def test_a_card_that_gets_stuck_again_starts_from_attempt_one(tmp_env, monkeypatch):
    pushes = []
    _undelivered(monkeypatch, pushes)
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    for minutes in (0, 5, 20):
        _tick(store, T0 + timedelta(minutes=minutes))
    assert store.get(P.STUCK_PUSH_KEY)["failed"]["attempts"] == 3
    # Retry, approve, and the send fails again: a new episode
    _stuck_card(store, decided_at="2026-09-21T21:40:00-05:00")
    later = T0 + timedelta(minutes=40)
    assert _tick(store, later) == ["failed"]
    assert store.get(P.STUCK_PUSH_KEY)["failed"]["attempts"] == 1
    assert pushes[-1]["title"] == "Replies with no owner: 1"


def test_a_record_store_error_still_pushes(tmp_env):
    notify.reset_for_tests()

    class NoRecords(JsonFileStore):
        def mutate(self, key, fn, default=None):
            if key == P.STUCK_PUSH_KEY:
                raise OSError("store down")
            return super(NoRecords, self).mutate(key, fn, default)

    store = NoRecords(tmp_env / "s.json")
    _stuck_card(store)
    assert _tick(store, T0) == ["failed"]
    assert len(notify.sent_in_test) == 1


def test_run_once_repushes_a_stuck_card_on_later_ticks(tmp_env):
    from services.reply_engine.tests.test_core_poller import make

    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)

    def process(event, now=None):  # pragma: no cover - no replies are fetched
        raise AssertionError("nothing to process")

    # The first push is delivered, so (round 4) the next one is the next
    # business day's reminder at 07:00, not a second push five minutes later.
    for now in (T0, T0 + timedelta(minutes=3), T0 + timedelta(minutes=5), ct(2026, 9, 22, 7, 0)):
        instantly, _server = make([], page_size=10)
        P.run_once(instantly, store, now=now, process=process)
    stuck = [n for n in notify.sent_in_test if n["title"].startswith("Replies with no owner")]
    assert len(stuck) == 2 and stuck[1]["title"].endswith("(reminder)")


# ================================================ 2. release_hold double failure
APPT = "appt-r3-1"
BOOKED_AT = ct(2026, 9, 21, 16, 0)
CALL = "2026-09-24T15:00:00-05:00"


class HoldDownStore(JsonFileStore):
    """``showrate_hold:`` reads and deletes fail while ``failing``."""

    failing = False

    def get(self, key, default=None):
        if self.failing and str(key).startswith(show_rate.HOLD_PREFIX):
            raise OSError("store read timed out")
        return super(HoldDownStore, self).get(key, default)

    def delete(self, key):
        if self.failing and str(key).startswith(show_rate.HOLD_PREFIX):
            raise OSError("store delete timed out")
        return super(HoldDownStore, self).delete(key)


def _appt():
    return {"id": APPT, "contact_id": "contact-r3", "start_iso": CALL, "email": LEAD, "first_name": "Dana",
            "company": "Brightfield Cleaning", "booked_at": BOOKED_AT.isoformat(), "niche": "cleaning",
            "offer": "reactivation"}


def _held_world(tmp_env):
    store = HoldDownStore(tmp_env / "s.json")
    show_rate.hold(store, APPT, reason="awaiting_approval", now=BOOKED_AT, meta={"lead_email": LEAD})
    show_rate.ensure_scheduled(store, _appt(), BOOKED_AT)
    key = show_rate.schedule_key(APPT, CALL)
    assert store.get(key).get("held")
    return store, key


def _shadow_ghl():
    from services.reply_engine.tests.test_hold_status_and_hold_checks import _shadow_ghl as make

    return make()


def _spoken(summary):
    return list(summary.get("sent") or []) + list(summary.get("would_do") or [])


def test_release_with_an_unreadable_undeletable_marker_is_an_error(tmp_env, shadow_mode, rows):
    store, key = _held_world(tmp_env)
    store.failing = True
    approved_at = BOOKED_AT + timedelta(minutes=30)
    out = show_rate.release_hold(store, APPT, approved_at)
    assert out["released"] is False
    assert "could not be released" in out["error"] and "read:" in out["error"] and "delete:" in out["error"]
    assert out["retry_recorded"] is True
    pending = store.get(show_rate.release_pending_key(APPT))
    assert pending["attempts"] == 1 and pending["reason"] == "approved"
    failed = _statuses(rows, "show_rate_release_failed")
    assert len(failed) == 1 and failed[0]["appointment_id"] == APPT


def test_the_approval_path_reports_the_error_so_lorenzo_is_alerted(tmp_env, shadow_mode):
    """approval.send_approved alerts "Show-rate reminders NOT started" when the
    release comes back with an error. It used to come back clean."""
    store, key = _held_world(tmp_env)
    store.failing = True
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN,
                      cadence={"booking": {"slot": CALL, "appointment_id": APPT, "awaiting_approval": True}})
    out = A.release_show_rate_hold(state, store, BOOKED_AT + timedelta(minutes=30))
    assert isinstance(out, dict) and out.get("error")


def test_a_failed_release_is_retried_every_tick_and_logged_once(tmp_env, shadow_mode, rows):
    notify.reset_for_tests()
    store, key = _held_world(tmp_env)
    store.failing = True
    approved_at = BOOKED_AT + timedelta(minutes=30)
    show_rate.release_hold(store, APPT, approved_at)
    # two ticks while the store still fails: retried, silent to the prospect,
    # and no second failure row or push
    for minutes in (10, 20):
        summary = show_rate.run(approved_at + timedelta(minutes=minutes), store, _shadow_ghl(), a2p=False,
                                appointments=[_appt()])
        assert summary["release_retried"][0]["error"]
        assert _spoken(summary) == []
    assert store.get(show_rate.release_pending_key(APPT))["attempts"] == 3
    assert len(_statuses(rows, "show_rate_release_failed")) == 1
    assert notify.sent_in_test == []
    # the store recovers: the next tick releases the hold, drops the record,
    # says so once, and the approved call's confirmation goes out
    store.failing = False
    tick = approved_at + timedelta(minutes=30)
    summary = show_rate.run(tick, store, _shadow_ghl(), a2p=False, appointments=[_appt()])
    assert summary["release_retried"] == [{"appointment_id": APPT, "released": True, "error": None,
                                           "attempts": 3}]
    assert store.get(show_rate.release_pending_key(APPT)) is None
    assert show_rate.read_hold(store, APPT) == (None, None)
    assert "held" not in store.get(key)
    # ZC item 7: the approved reply was the confirmation, so the ladder's own
    # is skipped and the pre-read (re-anchored to this release) follows
    touches = dict((t["template_key"], t) for t in store.get(key)["touches"])
    assert touches["confirm_email"]["skip_reason"] == show_rate.ENGINE_CONFIRMATION_SKIP
    assert _spoken(summary) == []
    started = [n for n in notify.sent_in_test if n["title"].startswith("Show-rate reminders started")]
    assert len(started) == 1
    # and nothing is retried after that; the pre-read goes out
    later = show_rate.run(tick + timedelta(minutes=15), store, _shadow_ghl(), a2p=False, appointments=[_appt()])
    assert "release_retried" not in later
    assert [e["template"] for e in _spoken(later)] == ["preread_email"]


def test_without_the_retry_the_surviving_marker_would_re_hold_the_call(tmp_env, shadow_mode):
    """The reviewer's shape: the tick re-stamps ``held`` from a marker that
    survived the release. With the retry the marker is gone first."""
    store, key = _held_world(tmp_env)
    store.failing = True
    show_rate.release_hold(store, APPT, BOOKED_AT + timedelta(minutes=30))
    assert "held" not in store.get(key)       # released on the schedule...
    store.failing = False
    assert show_rate.read_hold(store, APPT)[0] is not None   # ...but the marker survived
    summary = show_rate.run(BOOKED_AT + timedelta(minutes=40), store, _shadow_ghl(), a2p=False,
                            appointments=[_appt()])
    assert "held" not in store.get(key)
    # the retried release re-anchored the pre-read to +40; it goes out 15 minutes on
    summary = show_rate.run(BOOKED_AT + timedelta(minutes=55), store, _shadow_ghl(), a2p=False,
                            appointments=[_appt()])
    assert "held" not in store.get(key) and _spoken(summary)


def test_a_clean_release_writes_no_pending_record(tmp_env, shadow_mode, rows):
    store, key = _held_world(tmp_env)
    out = show_rate.release_hold(store, APPT, BOOKED_AT + timedelta(minutes=30))
    assert out["released"] is True and "error" not in out
    assert store.keys(show_rate.RELEASE_PENDING_PREFIX) == []
    assert _statuses(rows, "show_rate_release_failed") == []


# ======================================= 3. recovery claims against a rival lead
FREE = ["2026-09-28T13:00:00-05:00", "2026-09-28T14:00:00-05:00", "2026-09-29T13:00:00-05:00",
        "2026-09-29T14:00:00-05:00", "2026-09-30T13:00:00-05:00", "2026-09-30T14:00:00-05:00"]
FLAG_AT = datetime.fromisoformat("2026-09-24T15:20:00-05:00")


def test_reserve_recovery_slots_is_gone():
    assert not hasattr(ns, "reserve_recovery_slots")


def _owners(store):
    owners = {}
    for r in store.get(A.OFFERED_KEY, []) or []:
        owners.setdefault(r["slot"], set()).add(r["lead"])
    return owners


def test_claim_recovery_slots_against_a_rival_claim_leaves_no_double_hold(tmp_env, shadow_mode, monkeypatch):
    """The reviewer's replacement probe: a rival lead claims the very times the
    recovery is about to pick, in the gap between its read and its claim."""
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "ghl"))
    first = ns.fresh_two_slots(FLAG_AT, None, JsonFileStore(tmp_env / "pick.json"), free_slots=(FREE, "ghl"))
    rival = {"isos": list(first["slots"])}

    class Racing(JsonFileStore):
        def mutate(self, key, fn, default=None):
            if key == A.OFFERED_KEY and rival.get("isos"):
                isos, rival["isos"] = rival["isos"], None
                assert A.claim_slots(self, OTHER, isos, FLAG_AT, fields={"approval": "rival-card"}) == []
            return super(Racing, self).mutate(key, fn, default)

    store = Racing(tmp_env / "s.json")
    appt = {"id": "appt-ns-r3", "email": LEAD, "start_iso": "2026-09-24T15:00:00-05:00",
            "end_iso": "2026-09-24T15:15:00-05:00"}
    info = ns.claim_recovery_slots(FLAG_AT, None, store, appt)
    owners = _owners(store)
    assert all(len(leads) == 1 for leads in owners.values()), owners
    assert all(owners[s] == {OTHER} for s in first["slots"])
    assert len(info["slots"]) == 2 and not set(info["slots"]) & set(first["slots"])
    assert all(owners[s] == {LEAD} for s in info["slots"])
    # and the rival, arriving after, is refused the recovery's times
    assert sorted(A.claim_slots(store, OTHER, info["slots"], FLAG_AT, fields={"approval": "late"})) == \
        sorted(info["slots"])
    assert all(len(leads) == 1 for leads in _owners(store).values())


# ============================================ 4. _hold_new_appointment
START = slot_rules.parse_iso("2026-09-25T13:00:00-05:00")
NOW = slot_rules.parse_iso("2026-09-21T21:10:00-05:00")


class HoldReadFails(JsonFileStore):
    """The first ``fails`` reads of a ``showrate_hold:`` key raise."""

    fails = 0

    def get(self, key, default=None):
        if self.fails and str(key).startswith(show_rate.HOLD_PREFIX):
            self.fails -= 1
            raise OSError("store read timed out")
        return super(HoldReadFails, self).get(key, default)


def _state():
    return LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Dana", company="Brightfield Cleaning")


def test_one_read_error_then_a_clean_re_read_keeps_the_booking(tmp_env):
    store = HoldReadFails(tmp_env / "s.json")
    store.fails = 1
    assert booking._hold_new_appointment(store, _state(), "appt-h1", START, NOW) is None
    assert store.fails == 0
    assert show_rate.read_hold(store, "appt-h1")[0]["reason"] == "awaiting_approval"


def test_one_read_error_then_no_marker_is_hold_not_written(tmp_env, monkeypatch):
    store = HoldReadFails(tmp_env / "s.json")
    store.fails = 1
    monkeypatch.setattr(show_rate, "hold", lambda *a, **k: {"reason": "awaiting_approval"})
    assert booking._hold_new_appointment(store, _state(), "appt-h2", START, NOW) == "hold_not_written"


def test_two_read_errors_roll_back_with_an_accurate_card_line(tmp_env):
    store = HoldReadFails(tmp_env / "s.json")
    store.fails = 2
    why = booking._hold_new_appointment(store, _state(), "appt-h3", START, NOW)
    assert why.startswith(booking.HOLD_UNVERIFIED)
    cancels = []

    class GHLOk(object):
        def update_appointment_status(self, appointment_id, status, to_notify=True):
            cancels.append((appointment_id, status, to_notify))
            return {"ok": True}

    line = booking._silent_rollback(GHLOk(), "appt-h3", LEAD, START, why)
    assert cancels == [("appt-h3", "cancelled", False)]
    assert "could not be checked" in line and "cancelled silently" in line
    assert "could not be held" not in line and "not written" not in line


def test_book_rolls_back_a_call_whose_hold_cannot_be_checked(tmp_env, shadow_mode):
    store = HoldReadFails(tmp_env / "s.json")
    store.fails = 2
    state = _state()
    res = booking.book(state, START.isoformat(), None, None, now=NOW, free_slots=[START.isoformat()], store=store)
    assert booking.APPOINTMENT_NOT_CREATED in res.problems
    assert any("could not be checked" in p for p in res.problems)
    assert not (state.cadence or {}).get("booking")


def test_book_keeps_a_call_after_one_read_blip(tmp_env, shadow_mode):
    store = HoldReadFails(tmp_env / "s.json")
    store.fails = 1
    state = _state()
    res = booking.book(state, START.isoformat(), None, None, now=NOW, free_slots=[START.isoformat()], store=store)
    assert booking.APPOINTMENT_NOT_CREATED not in res.problems
    appointment_id = state.cadence["booking"]["appointment_id"]
    assert show_rate.read_hold(store, appointment_id)[0] is not None


def test_a_failed_cancel_after_an_unchecked_hold_still_alerts_unheld_call(tmp_env):
    notify.reset_for_tests()

    class GHLRefuses(object):
        def update_appointment_status(self, appointment_id, status, to_notify=True):
            raise RuntimeError("GHL 502")

    why = "%s: OSError: store read timed out" % booking.HOLD_UNVERIFIED
    line = booking._silent_rollback(GHLRefuses(), "appt-h4", LEAD, START, why)
    assert "could not be checked" in line and "cancel it by hand" in line
    alerts = [n for n in notify.sent_in_test if n["title"].startswith("Unheld call on the calendar")]
    assert len(alerts) == 1 and alerts[0]["priority"] == "urgent"
    assert "could not confirm its reminders are held" in alerts[0]["message"]


def test_approving_the_call_with_the_marker_stuck_alerts_once_then_the_tick_retries(tmp_env, shadow_mode, rows,
                                                                                     monkeypatch):
    """End to end: the approved confirmation goes out, the release cannot
    remove the marker, Lorenzo gets one "Show-rate reminders NOT started"
    push, and later ticks retry without pushing it again."""
    from services.reply_engine.tests.test_send_safety_round2 import FakeInstantly, Recorder

    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    notify.reset_for_tests()
    store, key = _held_world(tmp_env)
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Dana", ghl_contact_id="contact-r3",
                      ghl_opportunity_id="opp-r3",
                      cadence={"booking": {"slot": CALL, "appointment_id": APPT, "awaiting_approval": True,
                                           "owner": "cardr3", "booked_at": BOOKED_AT.isoformat()}})
    A.reserve_slots(store, LEAD, [CALL], "booking:%s" % APPT, BOOKED_AT)
    store.set(state.key, state.to_store())
    created = ct(2026, 9, 21, 18, 20)
    expires = (created + timedelta(hours=48)).isoformat()
    body = "Hey Dana,\n\nYou are locked in for Thu 3:00pm CT, invite on the way.\n\nLorenzo"
    d = A.Draft(subject="Re: x", body_text=body, offered_slots=[CALL])
    card = A.Approval(token="x", state_key=state.key, lead_email=LEAD, campaign_id=CAMPAIGN, email_id="e-r3",
                      eaccount="sender@adveromedia.example", draft=d, status="pending",
                      created_at=created.isoformat(), expires_at=expires, label="booking_confirmation")
    card.token = A.make_token("cardr3", state.key, A.draft_hash(d), expires)
    store.set(A.APPROVAL_PREFIX + "cardr3", card.model_dump(mode="json"))

    store.failing = True
    approved_at = ct(2026, 9, 21, 18, 40)
    out = A.approve(card.token, FakeInstantly(sender=LEAD), store=store, now=approved_at, ghl=Recorder())
    assert out["ok"] is True, out
    assert out["show_rate"]["error"]
    alerts = [n for n in notify.sent_in_test if n["title"].startswith("Show-rate reminders NOT started")]
    assert len(alerts) == 1 and "retries the release" in alerts[0]["message"]
    for minutes in (10, 20):
        show_rate.run(approved_at + timedelta(minutes=minutes), store, _shadow_ghl(), a2p=False,
                      appointments=[_appt()])
    alerts = [n for n in notify.sent_in_test if n["title"].startswith("Show-rate reminders NOT started")]
    assert len(alerts) == 1
    assert len(_statuses(rows, "show_rate_release_failed")) == 1
    store.failing = False
    show_rate.run(approved_at + timedelta(minutes=30), store, _shadow_ghl(), a2p=False, appointments=[_appt()])
    assert store.get(show_rate.release_pending_key(APPT)) is None
    assert "held" not in store.get(key)
