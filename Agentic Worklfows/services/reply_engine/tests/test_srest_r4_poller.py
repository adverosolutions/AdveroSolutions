"""S-rest round 4, defect 2: the "Replies with no owner" push after delivery.

One send_failed card whose pushes were all delivered got 26 pushes in 24
hours, 21 of them urgent and 8 of them at night (reviewer probe P16), and an
expired card whose Keep / Release push was delivered was chased again by the
poller without the Keep / Release links (P17). Now:

* the fast ladder (5, 15, 30, 60, 120 minutes, then hourly) and the urgent
  UNANSWERED escalation run only while no push about the card has been
  delivered, at any hour;
* once one has been delivered, the card is reminded at most once per business
  day, inside sending hours (07:00-19:00 CT, Mon-Fri), at high priority, never
  urgent, never at night or at a weekend; a reminder that is not delivered is
  retried inside sending hours, still high;
* an expired card with its own recorded Keep / Release push is listed, never
  pushed by the poller;
* a card Lorenzo closed with Mark sent (sent_manually) is done: no push;
* the send_failed push carries a Mark sent button when approval.mark_sent_url
  returns a link, and says what it does; never for a card held because its
  recipient could not be confirmed, whose line says Veto or check the thread;
* all of it is recorded in poller:stuck_push, so a restart changes nothing.

Every clock here is a fake (explicit ``now``); every lead is fictional.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from shared import job_log, notify
from shared import slots
from shared.store import JsonFileStore

from services.reply_engine import approval as A
from services.reply_engine import poller as P
from services.reply_engine import show_rate
from services.reply_engine.models import Approval, Draft, LeadState

from services.reply_engine.tests.test_srest_r3_silent_paths import T0, _stuck_card

CT = pytz.timezone("America/Chicago")


def ct(*args):
    return CT.localize(datetime(*args))


LEAD = "owner@brightfieldcleaning.example"
OTHER = "office@maplegrovebooks.example"
THIRD = "frontdesk@lakeshoredental.example"
FOURTH = "hello@cedarparkplumbing.example"
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"
EACCOUNT = "sender@adveromedia.example"
APPT = "appt-r4-1"

FRI = ct(2026, 9, 25, 16, 40)          # Friday 16:40 CT
MON_OPEN = ct(2026, 9, 28, 7, 0)       # the next business day's opening of sending hours


@pytest.fixture(autouse=True)
def _engine_env(monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    notify.reset_for_tests()


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


def _card(store, card_id, lead=LEAD, status="send_failed", decided_at=None, created=None, offered=None,
          label="positive_question"):
    """A real, token-signed card, so approval.Approval reads it back."""
    created = created or ct(2026, 9, 21, 9, 0)
    offered = offered if offered is not None else ["2026-10-01T13:00:00-05:00"]
    d = Draft(subject="Re: quick question", body_text="Hey Dana,\n\nThu 1:00pm CT works. Invite on the way.\n\nLorenzo",
              offered_slots=offered, label=label)
    expires = (created + timedelta(hours=48)).isoformat()
    state_key = "lead:%s:%s" % (CAMPAIGN, lead)
    card = Approval(token=A.make_token(card_id, state_key, A.draft_hash(d), expires), state_key=state_key,
                    lead_email=lead, campaign_id=CAMPAIGN, email_id="e-%s" % card_id, eaccount=EACCOUNT,
                    reply_to=lead, draft=d, status=status, created_at=created.isoformat(), expires_at=expires,
                    decided_at=decided_at.isoformat() if decided_at is not None else None, label=label,
                    notify_result={"sent": True})
    store.set(A.APPROVAL_PREFIX + card_id, card.model_dump(mode="json"))
    return card


def _set_status(store, card_id, status):
    row = store.get(A.APPROVAL_PREFIX + card_id)
    row["status"] = status
    store.set(A.APPROVAL_PREFIX + card_id, row)


def _tick(store, now):
    return P._push_stuck(store, P.pending_approvals(store, now), now)


def _run(store, start, hours, step_minutes=5, fresh=None):
    """Poller ticks every ``step_minutes`` from ``start`` for ``hours``
    (inclusive). ``fresh`` builds a new store object per tick: a restart."""
    pushed = []
    for i in range(int(hours * 60 // step_minutes) + 1):
        now = slots.to_tz(start + timedelta(minutes=step_minutes * i))
        if _tick(fresh() if fresh is not None else store, now):
            pushed.append(now)
    return pushed


def _stuck_pushes(pushes=None):
    source = notify.sent_in_test if pushes is None else pushes
    return [n for n in source if "Replies with no owner" in n["title"]]


def _scripted_notify(monkeypatch, deliver):
    """notify() that records every push and delivers it when ``deliver(title,
    message)`` says so."""
    pushes = []

    def fake(title, message, **kw):
        ok = bool(deliver(title, message))
        pushes.append({"title": title, "message": message, "priority": kw.get("priority"),
                       "actions": notify.format_actions(kw.get("actions")), "click": kw.get("click"),
                       "delivered": ok})
        if ok:
            return {"sent": True, "test": False, "shadow": False, "errors": []}
        return {"sent": False, "test": False, "shadow": False, "errors": ["ntfy: connection refused"]}

    monkeypatch.setattr(notify, "notify", fake)
    return pushes


# ============================================ P16: delivered pushes, one a day
def test_p16_the_reviewers_card_is_pushed_twice_in_24_hours_not_26(tmp_env):
    """The probe as the reviewer wrote it (T0 = Monday 21:10 CT, a tick every
    5 minutes for 24 hours, every push delivered). It found 26 pushes, 21
    urgent, 8 between 22:00 and 07:00."""
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    pushed = _run(store, T0, 24)
    stuck = _stuck_pushes()
    assert pushed == [T0, ct(2026, 9, 22, 7, 0)]
    assert len(stuck) == 2
    assert [n["priority"] for n in stuck] == ["high", "high"]
    assert [p for p in pushed if p.hour < 7 or p.hour >= 22] == []
    assert stuck[1]["title"] == "Replies with no owner: 1 (reminder)"
    rec = store.get(P.STUCK_PUSH_KEY)["failed"]
    assert rec["delivered"] == 2 and rec["escalated"] is False
    assert rec["next_at"] == ct(2026, 9, 23, 7, 0).isoformat()


def test_p16_every_push_delivered_one_a_business_day_in_sending_hours_across_a_weekend(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    pushed = _run(store, FRI, 72)                               # Friday 16:40 to Monday 16:40
    stuck = _stuck_pushes()
    assert len(stuck) == len(pushed)
    assert pushed == [FRI, MON_OPEN]
    days = [p.date() for p in pushed]
    assert len(days) == len(set(days)), "more than one push on a day"
    assert all(slots.is_business_day(p) for p in pushed), "a push at a weekend"
    assert all(slots.is_send_time(p) for p in pushed), "a push outside sending hours"
    assert all(n["priority"] == "high" for n in stuck)
    assert not any("UNANSWERED" in n["title"] for n in stuck)
    assert stuck[1]["title"] == "Replies with no owner: 1 (reminder)"
    assert "once a business day" in stuck[1]["message"]


def test_p16_a_week_of_ticks_gives_one_reminder_each_business_morning(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    start = ct(2026, 9, 24, 21, 10)                             # Thursday night
    _card(store, "c1", decided_at=start - timedelta(minutes=10))
    pushed = _run(store, start, 5 * 24 + 12)                    # to Wednesday 09:10
    assert pushed == [start, ct(2026, 9, 25, 7, 0), ct(2026, 9, 28, 7, 0), ct(2026, 9, 29, 7, 0),
                      ct(2026, 9, 30, 7, 0)]
    stuck = _stuck_pushes()
    assert all(n["priority"] == "high" for n in stuck)
    assert [n["title"] for n in stuck[1:]] == ["Replies with no owner: 1 (reminder)"] * 4


@pytest.mark.parametrize("first, second", [
    (ct(2026, 9, 22, 5, 0), ct(2026, 9, 23, 7, 0)),     # delivered Tuesday 05:00: not again that Tuesday
    (ct(2026, 9, 26, 10, 0), ct(2026, 9, 28, 7, 0)),    # delivered Saturday: Monday
    (ct(2026, 9, 25, 18, 55), ct(2026, 9, 28, 7, 0)),   # delivered Friday evening: Monday
], ids=["before-opening", "weekend", "friday-evening"])
def test_the_reminder_after_a_delivered_push_is_the_next_business_days_opening(tmp_env, first, second):
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=first - timedelta(minutes=10))
    pushed = _run(store, first, (second - first).total_seconds() / 3600.0 + 2)
    assert pushed == [first, second]


# ================================ undelivered: the fast ladder and escalation
def test_undelivered_pushes_keep_the_fast_ladder_at_night_and_escalate(tmp_env, monkeypatch, rows):
    outcome = {"deliver": False}
    pushes = _scripted_notify(monkeypatch, lambda title, message: outcome["deliver"])
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)                                          # stuck since Monday 20:02
    ts = T0                                                     # Monday 21:10
    assert _tick(store, ts) == ["failed"]
    times = [ts]
    for wait in (5, 15, 30, 60, 120, 60):
        assert _tick(store, ts + timedelta(minutes=wait - 1)) == [], "pushed before the backoff was up"
        ts = ts + timedelta(minutes=wait)
        assert _tick(store, ts) == ["failed"]
        times.append(ts)
    # 21:10, 21:15, 21:30, 22:00, 23:00, 01:00 and 02:00: nothing got through, so night does not stop it
    assert [t.strftime("%a %H:%M") for t in times] == ["Mon 21:10", "Mon 21:15", "Mon 21:30", "Mon 22:00",
                                                       "Mon 23:00", "Tue 01:00", "Tue 02:00"]
    assert [p["priority"] for p in pushes] == ["high"] * 5 + ["urgent"] * 2
    assert pushes[1]["title"] == "Replies with no owner: 1 (attempt 2)"
    assert pushes[5]["title"].startswith("UNANSWERED (attempt 6)")
    assert "Earlier pushes not delivered" in pushes[1]["message"]
    failed = _statuses(rows, "push_failed")
    assert len(failed) == 7 and [d["escalated"] for d in failed] == [False] * 5 + [True] * 2
    assert all(d["reminder"] is False for d in failed)
    # the eighth push (03:00, still the fast ladder's, so urgent) gets through
    outcome["deliver"] = True
    ts = ts + timedelta(minutes=60)
    assert _tick(store, ts) == ["failed"]
    assert pushes[-1]["priority"] == "urgent" and pushes[-1]["title"].startswith("UNANSWERED (attempt 8)")
    rec = store.get(P.STUCK_PUSH_KEY)["failed"]
    assert rec["delivered"] == 1 and rec["failed_streak"] == 0
    assert rec["next_at"] == ct(2026, 9, 23, 7, 0).isoformat()      # Tuesday already had its push
    # from here on he knows: nothing more that Tuesday, then one high reminder
    for hour in (4, 7, 12, 18):
        assert _tick(store, ct(2026, 9, 22, hour, 0)) == []
    assert _tick(store, ct(2026, 9, 23, 7, 0)) == ["failed"]
    assert pushes[-1]["title"] == "Replies with no owner: 1 (reminder)" and pushes[-1]["priority"] == "high"
    assert len(_statuses(rows, "push_failed")) == 7


def test_a_reminder_that_is_not_delivered_is_retried_inside_sending_hours_and_stays_high(tmp_env, monkeypatch,
                                                                                         rows):
    outcome = {"deliver": True}
    pushes = _scripted_notify(monkeypatch, lambda title, message: outcome["deliver"])
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]                          # delivered: reminders only from now on
    outcome["deliver"] = False
    pushed = _run(store, ct(2026, 9, 28, 5, 0), 27)             # Monday 05:00 to Tuesday 08:00
    labels = [p.strftime("%a %H:%M") for p in pushed]
    assert labels[:6] == ["Mon 07:00", "Mon 07:05", "Mon 07:20", "Mon 07:50", "Mon 08:50", "Mon 10:50"]
    assert labels[-3:] == ["Mon 18:50", "Tue 07:00", "Tue 08:00"]
    assert all(slots.is_send_time(p) for p in pushed), "a retry outside sending hours"
    reminders = pushes[1:]
    assert len(reminders) == len(pushed)
    assert all(p["priority"] == "high" for p in reminders)
    assert all(p["title"] == "Replies with no owner: 1 (reminder)" for p in reminders)
    assert not any("UNANSWERED" in p["title"] for p in reminders)
    failed = _statuses(rows, "push_failed")
    assert len(failed) == len(pushed) and all(d["reminder"] is True and d["escalated"] is False for d in failed)
    # it gets through at Tuesday 09:00: the next one is Wednesday 07:00
    outcome["deliver"] = True
    assert _tick(store, ct(2026, 9, 29, 9, 0)) == ["c1"]
    rec = store.get(P.STUCK_PUSH_KEY)["c1"]
    assert rec["failed_streak"] == 0 and rec["next_at"] == ct(2026, 9, 30, 7, 0).isoformat()


def test_a_reminder_never_rides_in_an_urgent_push(tmp_env, monkeypatch):
    """Two cards due on the same tick, one nobody has heard about (escalated)
    and one Lorenzo already knows about: two pushes, and the reminder is high."""
    pushes = _scripted_notify(monkeypatch, lambda title, message: OTHER not in message)
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "known", decided_at=ct(2026, 9, 21, 9, 55))
    assert _tick(store, ct(2026, 9, 21, 10, 0)) == ["known"]            # delivered Monday 10:00
    _card(store, "silent", lead=OTHER, decided_at=ct(2026, 9, 21, 21, 0))
    _run(store, ct(2026, 9, 21, 21, 10), 9.5)                           # its pushes fail all night
    before = len(pushes)
    assert sorted(_tick(store, ct(2026, 9, 22, 7, 0))) == ["known", "silent"]
    tick = pushes[before:]
    assert len(tick) == 2
    urgent = [p for p in tick if p["priority"] == "urgent"]
    high = [p for p in tick if p["priority"] == "high"]
    assert len(urgent) == 1 and urgent[0]["title"].startswith("UNANSWERED") and LEAD not in urgent[0]["message"]
    assert len(high) == 1 and high[0]["title"] == "Replies with no owner: 1 (reminder)"
    assert LEAD in high[0]["message"] and OTHER not in high[0]["message"]


def test_a_record_left_by_the_old_ladder_is_not_pushed_at_night(tmp_env):
    """A record written before this fix (every push delivered, the last at
    23:10 on Monday, the next one due an hour later) is read as delivered:
    nothing at night, one reminder at the opening of sending hours."""
    store = JsonFileStore(tmp_env / "s.json")
    _stuck_card(store)
    store.set(P.STUCK_PUSH_KEY, {"failed": {
        "episode": "send_failed|2026-09-21T20:02:00-05:00", "status": "send_failed", "lead": LEAD,
        "first_at": "2026-09-21T21:10:00-05:00", "attempts": 8, "delivered": 8, "errors": [],
        "last_at": "2026-09-21T23:10:00-05:00", "next_at": "2026-09-22T00:10:00-05:00",
        "delivered_at": "2026-09-21T23:10:00-05:00", "last_delivered": True, "escalated": True}})
    pushed = _run(store, ct(2026, 9, 21, 23, 15), 9)           # Monday 23:15 to Tuesday 08:15
    assert pushed == [ct(2026, 9, 22, 7, 0)]
    push = _stuck_pushes()[-1]
    assert push["priority"] == "high" and push["title"] == "Replies with no owner: 1 (reminder)"
    # that was Tuesday's reminder: the next one is Wednesday's opening
    rec = store.get(P.STUCK_PUSH_KEY)["failed"]
    assert rec["next_at"] == ct(2026, 9, 23, 7, 0).isoformat() and rec["escalated"] is False


# ===================================== P17: expired cards have their own push
def _owner_card_that_expires(store, created):
    """An owner card that expires at created + 48 h still holding the lead's
    unconfirmed call, through approval's own expiry path."""
    slot = "2026-10-01T15:00:00-05:00"
    card = _card(store, "c1", status="pending", created=created, offered=[slot], label="booking_confirmation")
    store.set(A.APPROVAL_CONTEXT_PREFIX + "c1",
              {"email_id": "e-c1", "reply_at": created.isoformat(), "processed_before": [], "processed_count": 0,
               "tracks_history": True, "approved_at": None, "send_attempts": 0})
    booking = {"slot": slot, "appointment_id": APPT, "awaiting_approval": True, "owner": "c1",
               "booked_at": created.isoformat()}
    show_rate.hold(store, APPT, reason="awaiting_approval", now=created, meta={"lead_email": LEAD, "start_iso": slot})
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Dana", eaccount=EACCOUNT,
                      approvals=[card.token], processed_email_ids=["e-c1"], cadence={"booking": booking})
    store.set(state.key, state.to_store())
    return card


@pytest.mark.parametrize("delivered", [True, False], ids=["keep-release-delivered", "keep-release-not-delivered"])
def test_p17_an_expired_card_with_its_own_keep_release_push_is_not_chased_by_the_poller(tmp_env, monkeypatch,
                                                                                        delivered):
    pushes = _scripted_notify(monkeypatch, lambda title, message: delivered or "Card expired" not in title)
    store = JsonFileStore(tmp_env / "s.json")
    created = ct(2026, 9, 28, 9, 0)
    _owner_card_that_expires(store, created)
    t_exp = created + timedelta(hours=48, minutes=5)
    A.expire_overdue(store, now=t_exp)
    rec = A.expiry_push_record(store.get(A.APPROVAL_PREFIX + "c1"))
    assert rec and not rec.get("settled") and bool(rec.get("delivered")) is delivered
    for i in range(1, 12 * 8 + 1):                              # eight hours of ticks
        now = t_exp + timedelta(minutes=5 * i)
        A.expire_overdue(store, now=now)
        assert _tick(store, now) == []
    assert _stuck_pushes(pushes) == []
    assert store.get(P.STUCK_PUSH_KEY) in (None, {})
    keep_release = [p for p in pushes if "Card expired with a call still booked" in p["title"]]
    if delivered:
        assert len(keep_release) == 1                           # approval stops once it is delivered
    else:
        assert len(keep_release) >= 6                           # approval re-sends its own push...
        assert any(p["title"].startswith("UNANSWERED") for p in keep_release)
        assert all("Keep the call" in (p["actions"] or "") for p in keep_release)   # ...with the links
    # still listed for the digest, marked as chased by its own push
    waiting = P.pending_approvals(store, t_exp + timedelta(hours=8))
    assert len(waiting) == 1 and waiting[0]["status"] == "expired"
    assert waiting[0]["chased_by"] == "expiry_push" and waiting[0]["pushed"] is delivered


def test_p17_through_run_once_the_expired_card_gets_no_stuck_push(tmp_env):
    from services.reply_engine.tests.test_core_poller import make

    store = JsonFileStore(tmp_env / "s.json")
    created = ct(2026, 9, 28, 9, 0)
    _owner_card_that_expires(store, created)
    t_exp = created + timedelta(hours=48, minutes=5)

    def process(event, now=None):  # pragma: no cover - no replies are fetched
        raise AssertionError("nothing to process")

    for i in range(0, 12 * 4):
        instantly, _server = make([], page_size=10)
        summary = P.run_once(instantly, store, now=t_exp + timedelta(minutes=5 * i), process=process)
    assert _stuck_pushes() == []
    assert len([n for n in notify.sent_in_test if "Card expired" in n["title"]]) == 1
    assert [w.get("chased_by") for w in summary["pending_approvals"]] == ["expiry_push"]


# ========================================= sent_manually: done, never pushed
def test_a_sent_manually_card_is_done_and_never_pushed(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    _set_status(store, "c1", "sent_manually")                   # Lorenzo pressed Mark sent
    assert P.pending_approvals(store, MON_OPEN) == []
    assert _run(store, FRI + timedelta(minutes=5), 5 * 24) == []     # the weekend and three business days
    assert len(_stuck_pushes()) == 1


def test_a_card_already_sent_manually_is_never_listed_or_pushed(tmp_env):
    from services.reply_engine.tests.test_core_poller import make

    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", status="sent_manually", decided_at=ct(2026, 9, 28, 6, 0))
    assert P.pending_approvals(store, MON_OPEN) == []
    assert _tick(store, MON_OPEN) == []
    instantly, _server = make([], page_size=10)
    summary = P.run_once(instantly, store, now=ct(2026, 9, 28, 9, 0), process=lambda event, now=None: {})
    assert summary["pending_approvals"] == [] and _stuck_pushes() == []


def test_a_superseded_card_beside_a_sent_manually_one_is_not_an_orphan(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    store.set("approval:old", {"status": "superseded", "lead_email": LEAD, "created_at": "2026-09-28T08:00:00-05:00",
                               "notify_result": {"sent": True}})
    _card(store, "new", status="sent_manually", decided_at=ct(2026, 9, 28, 8, 30))
    assert "sent_manually" in P.SETTLED_STATUSES
    assert P.pending_approvals(store, MON_OPEN + timedelta(hours=3)) == []


# ==================================================== the Mark sent button
def test_the_send_failed_push_carries_mark_sent_when_the_helper_returns_a_url(tmp_env, monkeypatch):
    seen = []

    def url_for(card):
        seen.append(card)
        return "https://engine.test/mark-sent/%s" % card.token

    monkeypatch.setattr(A, "mark_sent_url", url_for, raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    card = _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    _card(store, "s1", lead=OTHER, status="stale_slots", decided_at=FRI - timedelta(minutes=10))
    assert sorted(_tick(store, FRI)) == ["c1", "s1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] == "view, Mark sent, https://engine.test/mark-sent/%s" % card.token
    assert P.MARK_SENT_LINE in push["message"]
    assert "If the reply did go out, press Mark sent. That stops these reminders and keeps the call." \
        in push["message"]
    assert push["click"] is None                                # a tap on the push never opens it
    assert "no Mark sent button" not in push["message"]
    assert [type(c) for c in seen] == [Approval] and seen[0].token == card.token   # only the send_failed card
    assert "\u2014" not in push["message"]
    # the next business day's reminder carries it too
    assert sorted(_tick(store, MON_OPEN)) == ["c1", "s1"]
    reminder = _stuck_pushes()[-1]
    assert reminder["title"].endswith("(reminder)")
    assert reminder["actions"] == "view, Mark sent, https://engine.test/mark-sent/%s" % card.token
    assert P.MARK_SENT_LINE in reminder["message"]


@pytest.mark.parametrize("helper", ["returns-none", "absent", "raises"])
def test_no_mark_sent_button_when_the_helper_gives_no_url(tmp_env, monkeypatch, helper):
    if helper == "returns-none":
        monkeypatch.setattr(A, "mark_sent_url", lambda card: None, raising=False)
    elif helper == "absent":
        monkeypatch.delattr(A, "mark_sent_url", raising=False)
    else:
        def boom(card):
            raise RuntimeError("BASE_URL is unset")

        monkeypatch.setattr(A, "mark_sent_url", boom, raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] is None
    assert P.MARK_SENT_LINE not in push["message"]
    assert "This push has no Mark sent button for %s" % LEAD in push["message"]
    assert "do not press Retry or Veto" in push["message"]


def test_several_send_failed_cards_get_one_named_button_each_up_to_three(tmp_env, monkeypatch):
    monkeypatch.setattr(A, "mark_sent_url", lambda card: "https://engine.test/mark-sent/%s" % card.token,
                        raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    for card_id, lead in (("c1", LEAD), ("c2", OTHER), ("c3", THIRD), ("c4", FOURTH)):
        _card(store, card_id, lead=lead, decided_at=FRI - timedelta(minutes=10))
    assert sorted(_tick(store, FRI)) == ["c1", "c2", "c3", "c4"]
    push = _stuck_pushes()[-1]
    buttons = [piece.strip() for piece in push["actions"].split(";")]
    assert len(buttons) == P.STUCK_PUSH_MAX_ACTIONS == 3
    assert all(b.startswith("view, Mark sent ") and "/mark-sent/" in b for b in buttons)
    leads = (LEAD, OTHER, THIRD, FOURTH)
    named = [b.split(",")[1].strip()[len("Mark sent "):] for b in buttons]
    assert len(set(named)) == 3 and set(named) <= set(leads)
    left = [lead for lead in leads if lead not in named]
    assert P.MARK_SENT_LINE in push["message"]
    assert "This push has no Mark sent button for %s." % left[0] in push["message"]


def test_the_real_mark_sent_url_puts_a_working_button_on_the_push(tmp_env):
    """Integration with approval.mark_sent_url once it exists (M1a)."""
    if not callable(getattr(A, "mark_sent_url", None)):
        pytest.skip("approval.mark_sent_url is not in this tree yet")
    store = JsonFileStore(tmp_env / "s.json")
    card = _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] and push["actions"].startswith("view, Mark sent, https://engine.test/")
    assert "/mark-sent/" in push["actions"] and card.token.split(".", 1)[0] in push["actions"]
    assert P.MARK_SENT_LINE in push["message"]


# ============ a card held because its recipient could not be confirmed
HELD_LINE = "No Mark sent for %s: held because the recipient could not be confirmed. Veto it, or check the " \
            "thread in Instantly."


def _real_recipient_check():
    if not (callable(getattr(A, "mark_sent_url", None)) and callable(getattr(A, "recipient_held", None))):
        pytest.skip("approval.mark_sent_url / recipient_held are not in this tree yet")


def test_a_card_held_for_its_recipient_gets_no_mark_sent_button_and_says_what_to_do(tmp_env):
    """The hold's record on the card itself (written when the hold escalated
    it to send_failed): no button for it, the other send_failed card keeps
    its own, and the push says Veto or check the thread."""
    _real_recipient_check()
    store = JsonFileStore(tmp_env / "s.json")
    held = _card(store, "h1", lead=OTHER, decided_at=FRI - timedelta(minutes=10))
    row = store.get(A.APPROVAL_PREFIX + "h1")
    row["notify_result"] = dict(row.get("notify_result") or {}, **{A.RECIPIENT_HELD_KEY: {
        "reason": "recipient_mismatch", "attempts": 1, "at": (FRI - timedelta(minutes=10)).isoformat(),
        "to": OTHER}})
    store.set(A.APPROVAL_PREFIX + "h1", row)
    ok = _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert sorted(_tick(store, FRI)) == ["c1", "h1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] == "view, Mark sent, https://engine.test/mark-sent/%s" % ok.token
    assert held.token not in push["actions"]
    assert HELD_LINE % OTHER in push["message"]
    assert P.MARK_SENT_LINE in push["message"]                  # for the other card
    assert "This push has no Mark sent button" not in push["message"]
    # the next business day's reminder says the same
    assert sorted(_tick(store, MON_OPEN)) == ["c1", "h1"]
    reminder = _stuck_pushes()[-1]
    assert reminder["title"].endswith("(reminder)") and HELD_LINE % OTHER in reminder["message"]
    assert held.token not in reminder["actions"]


def test_a_card_whose_hold_is_only_in_its_own_row_gets_no_mark_sent_button(tmp_env, monkeypatch):
    """A card escalated before the hold was recorded on the card itself: its
    hold lives only in approval_recipient_hold:<id>. The poller hands the
    real mark_sent_url the store, which refuses it; the push has no button."""
    _real_recipient_check()
    real = A.mark_sent_url
    calls = []

    def spy(card, store=None):
        url = real(card, store=store)
        calls.append((store, url))
        return url

    monkeypatch.setattr(A, "mark_sent_url", spy)
    store = JsonFileStore(tmp_env / "s.json")
    held = _card(store, "h1", decided_at=FRI - timedelta(minutes=10))
    assert A.RECIPIENT_HELD_KEY not in (store.get(A.APPROVAL_PREFIX + "h1").get("notify_result") or {})
    store.set(A.RECIPIENT_HOLD_PREFIX + "h1", {"attempts": 3, "reason": "recipient_unconfirmed",
                                               "first_at": (FRI - timedelta(hours=1)).isoformat(),
                                               "last_at": (FRI - timedelta(minutes=10)).isoformat(),
                                               "to": LEAD, "email_id": "e-h1"})
    assert real(held) is not None                               # the card alone does not show the hold...
    assert real(held, store=store) is None                      # ...its row does
    assert _tick(store, FRI) == ["h1"]
    assert calls == [(store, None)]                             # called with the store, and it refused
    push = _stuck_pushes()[-1]
    assert push["actions"] is None
    assert HELD_LINE % LEAD in push["message"] and P.MARK_SENT_LINE not in push["message"]


def test_the_poller_hands_the_store_to_a_mark_sent_url_that_takes_one(tmp_env, monkeypatch):
    stores = []

    def url_for(card, store=None):
        stores.append(store)
        return "https://engine.test/mark-sent/%s" % card.token

    monkeypatch.setattr(A, "mark_sent_url", url_for, raising=False)
    monkeypatch.setattr(A, "recipient_held", lambda card, store=None: None, raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    assert stores == [store]
    assert _stuck_pushes()[-1]["actions"].startswith("view, Mark sent, ")


def test_an_older_one_argument_mark_sent_url_is_still_called_with_the_card(tmp_env, monkeypatch):
    calls = []

    def old_url_for(card):
        calls.append(card)
        return "https://engine.test/mark-sent/%s" % card.token

    monkeypatch.setattr(A, "mark_sent_url", old_url_for, raising=False)
    monkeypatch.delattr(A, "recipient_held", raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    card = _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    assert [c.token for c in calls] == [card.token]             # the store= call failed at the signature
    assert _stuck_pushes()[-1]["actions"] == "view, Mark sent, https://engine.test/mark-sent/%s" % card.token


def test_a_type_error_inside_a_mark_sent_url_that_takes_the_store_is_not_retried_without_it(tmp_env,
                                                                                            monkeypatch):
    """Only the old signature falls back to the one-argument call: a builder
    that takes ``store`` and fails is a failure (no button), never a second
    call that would skip the store's recipient-hold check."""
    calls = []

    def url_for(card, store=None):
        calls.append(store)
        raise TypeError("unsupported operand")

    monkeypatch.setattr(A, "mark_sent_url", url_for, raising=False)
    monkeypatch.setattr(A, "recipient_held", lambda card, store=None: None, raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    assert calls == [store]
    push = _stuck_pushes()[-1]
    assert push["actions"] is None
    assert "This push has no Mark sent button for %s" % LEAD in push["message"]


def test_a_recipient_hold_that_cannot_be_read_gives_no_button(tmp_env, monkeypatch):
    def unreadable(card, store=None):
        raise RuntimeError("store read failed")

    monkeypatch.setattr(A, "mark_sent_url", lambda card, store=None: "https://engine.test/mark-sent/x",
                        raising=False)
    monkeypatch.setattr(A, "recipient_held", unreadable, raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    _card(store, "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(store, FRI) == ["c1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] is None
    assert "This push has no Mark sent button for %s" % LEAD in push["message"]
    assert "held because the recipient" not in push["message"]


# ================================================= restarts change nothing
def test_a_restart_on_every_tick_gives_the_same_pushes(tmp_env):
    path = tmp_env / "s.json"
    _card(JsonFileStore(path), "c1", decided_at=FRI - timedelta(minutes=10))
    pushed = _run(None, FRI, 72, fresh=lambda: JsonFileStore(path))
    assert pushed == [FRI, MON_OPEN]
    assert len(_stuck_pushes()) == 2
    rec = JsonFileStore(path).get(P.STUCK_PUSH_KEY)["c1"]
    assert rec["attempts"] == 2 and rec["delivered"] == 2


def test_a_restart_right_after_a_reminder_does_not_repeat_it(tmp_env):
    path = tmp_env / "s.json"
    _card(JsonFileStore(path), "c1", decided_at=FRI - timedelta(minutes=10))
    assert _tick(JsonFileStore(path), FRI) == ["c1"]
    assert _tick(JsonFileStore(path), MON_OPEN) == ["c1"]
    for minutes in (0, 1, 10, 60, 11 * 60 + 55):               # a new process each time, through Monday
        assert _tick(JsonFileStore(path), MON_OPEN + timedelta(minutes=minutes)) == []
    assert len(_stuck_pushes()) == 2


# ============================================ sent_manually in the metrics
def test_a_sent_manually_row_counts_as_a_draft_sent_but_not_as_time_to_first_reply():
    """The row approval.mark_sent_manually writes: a draft sent, on the day it
    was marked; its sent_at is the Mark sent press, so Time to first reply
    leaves it out rather than guess when the reply really left."""
    from services.metrics import sources

    day = MON_OPEN.date()
    marked = ct(2026, 9, 28, 9, 30)
    row = {"job": "reply_engine.approval", "status": "sent_manually",
           "ts_utc": marked.astimezone(pytz.utc).isoformat(),
           "details_parsed": {"approval": "c1", "reply_at": ct(2026, 9, 25, 16, 0).isoformat(),
                              "sent_at": marked.isoformat(), "send_failed_at": ct(2026, 9, 25, 16, 30).isoformat(),
                              "first_reply": True}}
    assert "sent_manually" in sources.DRAFT_SENT_STATUSES
    assert sources.engine_metrics([row], None, day)["drafts_sent"] == 1
    assert sources.engine_metrics([row], None, day + timedelta(days=1))["drafts_sent"] == 0
    assert sources.first_reply_minutes([row], day) is None
    sent = dict(row, status="sent")
    assert sources.first_reply_minutes([sent], day) is not None      # the same row as a real send is paired


def test_the_deploy_watch_reads_a_sent_manually_row_as_healthy_and_a_record_not_updated_as_a_failure():
    """Mark sent is an operator action that resolves a failure the watch
    already flagged (the send_failed row); the row itself is healthy. A Mark
    sent whose lead row was not read or written has its own row, which fails
    the watch."""
    from changesets.deploy import watch_report

    assert watch_report.classify("sent_manually") == "healthy"
    assert watch_report.classify("send_failed") == "fail"
    assert "sent_manually" not in watch_report.KNOWN_FAILURES
    assert watch_report.classify("mark_sent_record_not_updated") == "fail"
    assert "mark_sent_record_not_updated" in watch_report.KNOWN_FAILURES
