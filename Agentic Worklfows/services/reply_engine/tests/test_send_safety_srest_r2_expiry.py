"""Re-review fix piece R1 (slice 2 "S-rest"): the card-expiry and Keep /
Release flow, as regression tests. Each test fails on the code before R1.

1. The Keep / Release push is recorded on the card, re-sent with backoff until
   delivered, escalates loudly after EXPIRY_PUSH_MAX_ATTEMPTS, writes a
   Job_Log status the deploy watch counts as a failure, and the poller's
   stuck-card detector lists an expired card that still holds an undecided call.
2. Cards whose send may have reached Instantly (send_failed, sending, any
   card holding a send claim) and approved_queued cards are never expired;
   the push and the pages say only what the card's history proves; Keep never
   produces a card that cannot be sent.
3. The send's "-> sending" write, Keep's slot claim and reopen, and
   create_approval's post-push write are status-guarded or field-scoped.
4. The card's context row is written first and fails closed; context rows are
   swept once nothing reads them.
5. The sent row carries the approval id, so the metric's created-row fallback
   fires.
6. A card reopened by Keep is chased again, on its own clock and claim keys.

No real names: every lead is an example.com address. Every client is an
in-process fake; nothing is live.
"""
from datetime import datetime, timedelta

import pytest
import pytz
from fastapi.testclient import TestClient

from changesets.deploy import watch_report
from shared import job_log, notify
from shared.job_log import job_log_path
from shared.store import JsonFileStore

from services.metrics import sources
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import poller
from services.reply_engine.models import Approval, Draft, LeadState, ReplyEvent

CT = pytz.timezone("America/Chicago")
CAMPAIGN = "c-r1"
LEAD = "owner@example.com"
OTHER = "someone-else@example.com"
APPT = "appt-r1"
THU_3PM = "2026-09-24T15:00:00-05:00"
FRI_1PM = "2026-09-25T13:00:00-05:00"
LOCKED_IN = "Hey there,\n\nYou are locked in for Thu 3:00pm CT, invite on the way.\n\nLorenzo"
CARD = "c1"


def ct(*args):
    return CT.localize(datetime(*args))


CREATED = ct(2026, 9, 21, 10, 0)          # Mon 10:00, TTL ends Wed 10:00
AT_EXPIRY = ct(2026, 9, 23, 10, 0)


class Pushes(object):
    """Stands in for shared.notify.notify: records each push and answers
    with the next queued result (delivered by default)."""

    def __init__(self):
        self.calls = []
        self.results = []

    def fail_next(self, n):
        self.results.extend([{"sent": False, "errors": ["ntfy HTTP 503", "smtp timed out"]}] * n)

    def __call__(self, title, message, **kw):
        self.calls.append(dict(kw, title=title, message=message))
        if self.results:
            return self.results.pop(0)
        return {"sent": True}

    def titled(self, fragment):
        return [c for c in self.calls if fragment in c["title"]]


class FakeInstantly(object):
    def __init__(self):
        self.sent = []
        self.interest = []

    def get_email(self, email_id):
        return {"id": email_id, "from_address_email": LEAD}

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.sent.append({"reply_to_uuid": reply_to_uuid, "to": to, "body": body})
        return {"id": "sent-%d" % len(self.sent)}

    def update_interest_status(self, lead_email, campaign_id, value):
        self.interest.append((lead_email, campaign_id, value))
        return {"ok": True}


class Recorder(object):
    has_token = False

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*a, **k):
            self.calls.append((name, a, k))
            return {"id": "%s-%d" % (name, len(self.calls))}
        return fn


@pytest.fixture
def world(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    notify.reset_for_tests()
    pushes = Pushes()
    monkeypatch.setattr(notify, "notify", pushes)
    rows = []
    real = job_log.log_run
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: rows.append((job, status, details))
                        or real(job, status, details))
    store = JsonFileStore(tmp_env / "r1.json")
    return {"store": store, "pushes": pushes, "rows": rows}


def _state(store, booked=True, owner=CARD):
    cad = {}
    if booked:
        cad = {"booking": {"slot": THU_3PM, "appointment_id": APPT, "awaiting_approval": True, "owner": owner,
                           "booked_at": CREATED.isoformat()}}
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Lead", cadence=cad,
                      processed_email_ids=["e-%s" % owner])
    store.set(state.key, state.to_store())
    return state


def _card(store, state, status="pending", body=LOCKED_IN, offered=(THU_3PM,), approval_id=CARD, created=CREATED,
          tracked=True, **extra):
    draft = Draft(subject="Re: question", body_text=body, offered_slots=list(offered))
    expires = (created + timedelta(hours=A.TTL_HOURS)).isoformat()
    card = Approval(token="x", state_key=state.key, lead_email=LEAD, campaign_id=CAMPAIGN,
                    email_id="e-%s" % approval_id, eaccount="sender@example.com", draft=draft, status=status,
                    created_at=created.isoformat(), expires_at=expires, label="booking_confirmation",
                    notify_result={"sent": True, "actionable": True}, **extra)
    card.token = A.make_token(approval_id, state.key, A.draft_hash(draft), expires)
    store.set(A.APPROVAL_PREFIX + approval_id, card.model_dump(mode="json"))
    if tracked:
        event = ReplyEvent(email_id=card.email_id, lead_email=LEAD, campaign_id=CAMPAIGN, subject="question",
                           text="yes please", received_at=created - timedelta(minutes=5))
        A.record_card_context(store, approval_id, state, event)
    return card


def _statuses(rows, status):
    return [d for j, s, d in rows if j == "reply_engine.approval" and s == status]


# ================================================= 1. the push is retried
def test_r1_1_an_undelivered_keep_release_push_is_recorded_and_retried_until_delivered(world):
    st, pushes = world["store"], world["pushes"]
    state = _state(st)
    card = _card(st, state)
    pushes.fail_next(2)                                   # ntfy 503 + SMTP timeout, twice
    A.expire_overdue(st, AT_EXPIRY)
    rec = A.expiry_push_record(st.get(A.APPROVAL_PREFIX + CARD))
    assert rec["attempts"] == 1 and rec["delivered"] is False and rec["from_status"] == "pending"
    assert rec["next_at"] == (AT_EXPIRY + timedelta(minutes=5)).isoformat()
    failed = _statuses(world["rows"], "push_failed")
    assert len(failed) == 1 and failed[0]["kind"] == "expired_booking" and failed[0]["attempt"] == 1
    assert "push_failed" not in watch_report.HEALTHY_STATUSES     # the deploy watch fails on it
    A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=3))         # not due yet
    assert len(pushes.calls) == 1
    A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=5))         # attempt 2, fails too
    assert len(pushes.calls) == 2 and "(attempt 2)" in pushes.calls[1]["title"]
    assert "attempt 2" in pushes.calls[1]["message"] and "ntfy HTTP 503" in pushes.calls[1]["message"]
    A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=19))        # 15 minutes later: not due
    assert len(pushes.calls) == 2
    A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=20))        # attempt 3 is delivered
    rec = A.expiry_push_record(st.get(A.APPROVAL_PREFIX + CARD))
    assert len(pushes.calls) == 3 and rec["delivered"] is True and rec["attempts"] == 3
    for minute in (30, 90, 300):
        A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=minute))
    assert len(pushes.calls) == 3                                   # delivered: never again
    assert A.load(card.token, st).status == "expired"


def test_r1_1_after_the_cap_the_push_escalates_loudly_and_keeps_going_hourly(world):
    st, pushes = world["store"], world["pushes"]
    _card(st, _state(st))
    pushes.fail_next(20)
    ts = AT_EXPIRY
    for _ in range(A.EXPIRY_PUSH_MAX_ATTEMPTS):
        A.expire_overdue(st, ts)
        rec = A.expiry_push_record(st.get(A.APPROVAL_PREFIX + CARD))
        ts = A.slots.parse_iso(rec["next_at"])
    assert len(pushes.calls) == A.EXPIRY_PUSH_MAX_ATTEMPTS
    last = pushes.calls[-1]
    assert last["priority"] == "urgent" and last["title"].startswith("UNANSWERED")
    assert rec["escalated"] is True
    assert ts - A.slots.parse_iso(rec["last_at"]) == timedelta(minutes=A.EXPIRY_PUSH_ESCALATED_RETRY_MINUTES)
    escalated = [d for d in _statuses(world["rows"], "push_failed") if d["escalated"]]
    assert len(escalated) == 1
    A.expire_overdue(st, ts)
    assert len(pushes.calls) == A.EXPIRY_PUSH_MAX_ATTEMPTS + 1      # it does not stop at the cap


def test_r1_1_two_workers_on_one_tick_push_one_attempt(world):
    st, pushes = world["store"], world["pushes"]
    _card(st, _state(st))
    pushes.fail_next(1)
    A.expire_overdue(st, AT_EXPIRY)
    later = AT_EXPIRY + timedelta(minutes=5)
    A.expire_overdue(st, later)
    A.expire_overdue(st, later)                                     # the second worker finds nothing due
    assert len(pushes.calls) == 2


def test_r1_1_the_stuck_detector_lists_an_expired_card_holding_an_undecided_call(world):
    st, pushes = world["store"], world["pushes"]
    card = _card(st, _state(st))
    pushes.fail_next(1)
    A.expire_overdue(st, AT_EXPIRY)
    assert poller.pending_approvals(st, AT_EXPIRY + timedelta(minutes=1)) == []    # inside the grace
    waiting = poller.pending_approvals(st, AT_EXPIRY + timedelta(minutes=6))
    assert len(waiting) == 1 and waiting[0]["status"] == "expired" and waiting[0]["pushed"] is False
    assert "Keep or Release not chosen" in waiting[0]["why"] and "NOT delivered" in waiting[0]["why"]
    assert waiting[0]["appointment_id"] == APPT
    # delivered but still undecided: still listed, now as pushed
    A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=6))
    waiting = poller.pending_approvals(st, AT_EXPIRY + timedelta(minutes=7))
    assert len(waiting) == 1 and waiting[0]["pushed"] is True
    # decided: gone
    out = A.decide_expired_booking(card.token, "release", ghl=Recorder(), store=st,
                                   now=AT_EXPIRY + timedelta(minutes=8))
    assert out["ok"] is True
    assert poller.pending_approvals(st, AT_EXPIRY + timedelta(minutes=20)) == []
    assert A.expiry_push_record(st.get(A.APPROVAL_PREFIX + CARD))["settled"] is True


def test_r1_1_an_expired_card_with_no_call_is_settled_and_never_listed(world):
    st = world["store"]
    _card(st, _state(st, booked=False))
    A.expire_overdue(st, AT_EXPIRY)
    assert world["pushes"].calls == []
    assert A.expiry_push_record(st.get(A.APPROVAL_PREFIX + CARD))["settled"] is True
    assert poller.pending_approvals(st, AT_EXPIRY + timedelta(hours=2)) == []


# ============================================ 2. what expires, what it says
@pytest.mark.parametrize("status", ["send_failed", "sending", "approved_queued"])
def test_r1_2_a_card_whose_send_may_have_started_or_that_is_approved_never_expires(world, status):
    st = world["store"]
    card = _card(st, _state(st), status=status)
    A.flush_queued(FakeInstantly(), store=st, now=ct(2026, 9, 23, 20, 0), ghl=Recorder())   # after hours
    assert A.load(card.token, st).status == status
    assert world["pushes"].calls == [] and _statuses(world["rows"], "expired") == []


def test_r1_2_a_pending_card_holding_a_send_claim_never_expires(world):
    st = world["store"]
    card = _card(st, _state(st))
    st.set(A.SEND_CLAIM_PREFIX + CARD, {"attempt": "a1", "at": CREATED.isoformat()})
    A.expire_overdue(st, AT_EXPIRY + timedelta(hours=1))
    assert A.load(card.token, st).status == "pending" and world["pushes"].calls == []


def test_r1_2_a_send_failed_card_past_its_ttl_stays_in_the_retry_flow(world):
    st = world["store"]
    card = _card(st, _state(st, booked=False), status="send_failed", body="Hey there,\n\nThanks.\n\nLorenzo",
                 offered=())
    st.set(A.SEND_CLAIM_PREFIX + CARD, {"attempt": "a1", "at": CREATED.isoformat()})
    later = AT_EXPIRY + timedelta(hours=3)
    A.expire_overdue(st, later)
    out = A.retry(card.token, store=st, now=later)
    assert out["ok"] is True and out["status"] == "pending"
    fresh = A.load(out["token"], st)
    assert fresh is not None and fresh.expires_at == (later + timedelta(hours=A.TTL_HOURS)).isoformat()
    # the dropped claim is on the card's history: nothing can call it unsent now
    assert A.card_history(st, fresh)["send_started"] is True


def test_r1_2_an_approved_queued_card_past_its_ttl_is_not_answered_expired_on_approve(world):
    st = world["store"]
    card = _card(st, _state(st), status="approved_queued")
    out = A.approve(card.token, FakeInstantly(), store=st, now=ct(2026, 9, 23, 20, 0), ghl=Recorder())
    assert out["status"] == "approved_queued" and out.get("error") != "expired"


def test_r1_2_a_never_approved_card_is_said_to_be_so(world):
    st, pushes = world["store"], world["pushes"]
    _card(st, _state(st))
    A.expire_overdue(st, AT_EXPIRY)
    msg = pushes.calls[0]["message"]
    assert "was never approved" in msg and "No reply has been sent from this card." in msg
    assert "The lead has not been told about it." in msg


def test_r1_2_a_blocked_card_he_approved_is_never_called_unapproved_or_unsent(world):
    st, pushes = world["store"], world["pushes"]
    card = _card(st, _state(st), status="blocked")
    card.draft.problems = ["the call is less than 60 minutes away"]
    st.set(A.APPROVAL_PREFIX + CARD, card.model_dump(mode="json"))
    A.expire_overdue(st, AT_EXPIRY)
    msg = pushes.calls[0]["message"]
    assert "never approved" not in msg and "You approved the reply" in msg
    assert "less than 60 minutes away" in msg


def test_r1_2_a_card_whose_earlier_send_was_retried_says_it_may_have_reached_the_lead(world):
    st, pushes = world["store"], world["pushes"]
    card = _card(st, _state(st), status="send_failed")
    st.set(A.SEND_CLAIM_PREFIX + CARD, {"attempt": "a1", "at": CREATED.isoformat()})
    out = A.retry(card.token, store=st, now=CREATED + timedelta(hours=1))
    assert out["ok"] is True
    A.expire_overdue(st, AT_EXPIRY)                    # pending again, and now it expires
    msg = pushes.calls[0]["message"]
    assert "Nothing was sent" not in msg and "No reply has been sent" not in msg
    assert "never approved" not in msg and "may have reached the lead" in msg
    assert "has not been told" not in msg


def test_r1_2_a_card_with_no_history_says_it_cannot_tell(world):
    st, pushes = world["store"], world["pushes"]
    _card(st, _state(st), tracked=False)
    A.expire_overdue(st, AT_EXPIRY)
    msg = pushes.calls[0]["message"]
    assert "never approved" not in msg and "No reply has been sent" not in msg
    assert "cannot say whether a reply went out" in msg


def test_r1_2_keep_on_a_card_holding_a_send_claim_hands_it_to_retry(world):
    """A card expired before R1 while its claim was held (or one that lost a
    race): Keep used to reopen it as pending, and every Approve then answered
    "a send for this approval is already in flight"."""
    st = world["store"]
    card = _card(st, _state(st))
    A.expire_overdue(st, AT_EXPIRY)
    st.set(A.SEND_CLAIM_PREFIX + CARD, {"attempt": "a1", "at": CREATED.isoformat()})
    kept = A.decide_expired_booking(card.token, "keep", ghl=Recorder(), store=st,
                                    now=AT_EXPIRY + timedelta(minutes=30))
    assert kept["ok"] is True and kept["status"] == "send_failed"
    retried = A.retry(kept["token"], store=st, now=AT_EXPIRY + timedelta(minutes=35))
    assert retried["ok"] is True and retried["status"] == "pending"
    inst = FakeInstantly()
    sent = A.approve(retried["token"], inst, store=st, now=AT_EXPIRY + timedelta(minutes=40), ghl=Recorder())
    assert sent["ok"] is True and len(inst.sent) == 1


def test_r1_2_the_keep_and_release_pages_say_only_what_the_history_proves(world):
    st = world["store"]
    card = _card(st, _state(st), status="send_failed")
    st.set(A.SEND_CLAIM_PREFIX + CARD, {"attempt": "a1", "at": CREATED.isoformat()})
    A.retry(card.token, store=st, now=CREATED + timedelta(hours=1))
    A.expire_overdue(st, AT_EXPIRY)
    app_mod.configure(store=st, ghl=Recorder(), instantly=FakeInstantly(),
                      clock=lambda: AT_EXPIRY + timedelta(minutes=10))
    try:
        client = TestClient(app_mod.app)
        release = client.get("/expired/%s/release" % card.token)
        assert release.status_code == 200 and "never told" not in release.text
        assert "may have reached the lead" in release.text
        kept = client.post("/expired/%s/keep" % card.token)
        assert kept.status_code == 200 and "Nothing has been sent" not in kept.text
        assert "may have reached the lead" in kept.text
    finally:
        app_mod.configure()


# ================================================== 3. guarded writes
class _ExpiresDuringTheClaim(JsonFileStore):
    """The tick expires the card between send_approved's unlocked status read
    and its write of 'sending' (here: the moment the send claim is taken)."""

    def set_if_absent(self, key, value):
        won = JsonFileStore.set_if_absent(self, key, value)
        if key.startswith(A.SEND_CLAIM_PREFIX):
            row = JsonFileStore.get(self, A.APPROVAL_PREFIX + CARD)
            JsonFileStore.set(self, A.APPROVAL_PREFIX + CARD, dict(row, status="expired"))
        return won


def test_r1_3_a_send_that_loses_the_race_to_expiry_sends_nothing(world, tmp_env):
    st = _ExpiresDuringTheClaim(tmp_env / "race.json")
    state = _state(st, booked=False)
    card = _card(st, state, body="Hey there,\n\nThanks for the note.\n\nLorenzo", offered=())
    inst = FakeInstantly()
    out = A.approve(card.token, inst, store=st, now=CREATED + timedelta(minutes=10), ghl=Recorder())
    assert out["ok"] is False and "changed" in out["error"] and inst.sent == []
    assert st.get(A.APPROVAL_PREFIX + CARD)["status"] == "expired"
    assert st.get(A.SEND_CLAIM_PREFIX + CARD) is None         # the unused claim is dropped


def test_r1_3_keep_counts_a_registry_error_as_taken(world, monkeypatch):
    st = world["store"]
    card = _card(st, _state(st), offered=(THU_3PM, FRI_1PM))
    A.expire_overdue(st, AT_EXPIRY)

    def broken(*a, **k):
        raise RuntimeError("registry unreadable")

    monkeypatch.setattr(A, "claim_slots", broken)
    kept = A.decide_expired_booking(card.token, "keep", ghl=Recorder(), store=st,
                                    now=AT_EXPIRY + timedelta(minutes=5))
    assert kept["ok"] is True and kept["status"] == "pending"
    assert any("already held" in p for p in kept["problems"])
    stored = A.load(kept["token"], st)
    assert stored.status == "pending" and any("already held" in p for p in stored.draft.problems)


class _VetoedDuringTheClaim(JsonFileStore):
    """Lorenzo vetoes the expired card while Keep is claiming its times."""

    def mutate(self, key, fn, default=None):
        value = JsonFileStore.mutate(self, key, fn, default)
        if key == A.OFFERED_KEY and getattr(self, "arm", False):
            self.arm = False
            row = JsonFileStore.get(self, A.APPROVAL_PREFIX + CARD)
            JsonFileStore.set(self, A.APPROVAL_PREFIX + CARD, dict(row, status="vetoed"))
        return value


def test_r1_3_keep_never_resurrects_a_card_that_changed_meanwhile(world, tmp_env):
    st = _VetoedDuringTheClaim(tmp_env / "keep-race.json")
    card = _card(st, _state(st), offered=(THU_3PM, FRI_1PM))
    A.expire_overdue(st, AT_EXPIRY)
    A.reserve_slots(st, OTHER, [FRI_1PM], "other-card", AT_EXPIRY)     # a taken time: a problem to add
    st.arm = True
    kept = A.decide_expired_booking(card.token, "keep", ghl=Recorder(), store=st,
                                    now=AT_EXPIRY + timedelta(minutes=5))
    assert kept["ok"] is False and kept["status"] == "vetoed"
    assert st.get(A.APPROVAL_PREFIX + CARD)["status"] == "vetoed"


def test_r1_3_an_approve_during_the_card_push_is_never_reverted(world, tmp_env):
    st = world["store"]
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Lead")
    st.set(state.key, state.to_store())
    event = ReplyEvent(email_id="e-new", lead_email=LEAD, campaign_id=CAMPAIGN, subject="q", text="yes",
                       received_at=CREATED)

    def tapped_during_the_push(title, message, **kw):
        for key in st.keys(A.APPROVAL_PREFIX):
            st.set(key, dict(st.get(key), status="sent"))
        return {"sent": True}

    card = A.create_approval(state, Draft(subject="Re: q", body_text="Hey there,\n\nThanks.\n\nLorenzo"), event,
                             store=st, now=CREATED, notify_fn=tapped_during_the_push)
    row = st.get(A.APPROVAL_PREFIX + card.token.split(".")[0])
    assert row["status"] == "sent" and row["notify_result"]["sent"] is True


# ================================================ 4. the card's context row
class _ContextWriteFails(JsonFileStore):
    def set(self, key, value):
        if key.startswith(A.APPROVAL_CONTEXT_PREFIX):
            raise RuntimeError("store down")
        JsonFileStore.set(self, key, value)


def test_r1_4_no_card_is_raised_without_its_context_row(world, tmp_env):
    st = _ContextWriteFails(tmp_env / "ctx.json")
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Lead")
    event = ReplyEvent(email_id="e-ctx", lead_email=LEAD, campaign_id=CAMPAIGN, subject="q", text="yes",
                       received_at=CREATED)
    draft = Draft(subject="Re: q", body_text="Hey there,\n\nWould Fri 1:00pm CT work?\n\nLorenzo",
                  offered_slots=[FRI_1PM])
    with pytest.raises(RuntimeError):
        A.create_approval(state, draft, event, store=st, now=CREATED, notify_fn=lambda *a, **k: {"sent": True})
    assert st.keys(A.APPROVAL_PREFIX) == [] and world["pushes"].calls == []
    assert A.offered_slots(st, CREATED) == []                 # the claimed time went back


def test_r1_4_context_rows_are_swept_once_nothing_reads_them(world):
    st = world["store"]
    state = _state(st, booked=False)
    for approval_id, status in (("k-pending", "pending"), ("k-sent", "sent"), ("k-vetoed", "vetoed"),
                                ("k-superseded", "superseded")):
        _card(st, state, status=status, approval_id=approval_id, body="Hey there,\n\nOk.\n\nLorenzo", offered=(),
              created=AT_EXPIRY - timedelta(hours=1))           # inside its TTL at the sweep
    st.set(A.APPROVAL_CONTEXT_PREFIX + "k-gone", {"email_id": "x"})
    # an expired card with its Keep / Release question open keeps its row
    booked = _state(st)
    _card(st, booked, approval_id=CARD)
    A.expire_overdue(st, AT_EXPIRY)
    left = sorted(k[len(A.APPROVAL_CONTEXT_PREFIX):] for k in st.keys(A.APPROVAL_CONTEXT_PREFIX))
    assert left == [CARD, "k-pending"]
    A.decide_expired_booking(A.load(A._approval_row(st, CARD).token, st).token, "release", ghl=Recorder(),
                             store=st, now=AT_EXPIRY + timedelta(minutes=5))
    A.expire_overdue(st, AT_EXPIRY + timedelta(minutes=10))
    left = sorted(k[len(A.APPROVAL_CONTEXT_PREFIX):] for k in st.keys(A.APPROVAL_CONTEXT_PREFIX))
    assert left == ["k-pending"]


# ================================================ 5. the sent row's approval id
def test_r1_5_the_sent_row_names_its_card_and_the_metric_pairs_it(world):
    st = world["store"]
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Lead")
    st.set(state.key, state.to_store())
    event = ReplyEvent(email_id="e-metric", lead_email=LEAD, campaign_id=CAMPAIGN, subject="q", text="yes",
                       received_at=ct(2026, 9, 22, 9, 0))
    card = A.create_approval(state, Draft(subject="Re: q", body_text="Hey there,\n\nThanks.\n\nLorenzo"), event,
                             store=st, now=ct(2026, 9, 22, 9, 1), notify_fn=lambda *a, **k: {"sent": True})
    card_id = card.token.split(".")[0]
    # a card whose context row is gone: its sent row carries no reply_at, and
    # only the approval id can pair it with the created row
    st.delete(A.APPROVAL_CONTEXT_PREFIX + card_id)
    out = A.approve(card.token, FakeInstantly(), store=st, now=ct(2026, 9, 22, 9, 12), ghl=Recorder())
    assert out["ok"] is True
    sent = _statuses(world["rows"], "sent")
    assert sent and sent[0]["approval"] == card_id and sent[0]["reply_at"] is None
    rows = sources.read_job_log(job_log_path())
    day = sources.ct_day(sources.parse_ts([r for r in rows if r.get("status") == "sent"][0]["ts_utc"]))
    assert sources.first_reply_minutes(rows, day) == pytest.approx(12.0)


# ================================================ 6. the chase after Keep
def test_r1_6_a_card_reopened_by_keep_is_chased_on_its_own_clock_and_keys(world):
    st = world["store"]
    card = _card(st, _state(st), escalations=A.ESCALATION_MAX_PUSHES,
                 last_escalated_at=ct(2026, 9, 21, 17, 0).isoformat())
    for step in range(1, A.ESCALATION_MAX_PUSHES + 1):           # the first life's claim keys
        st.set_if_absent("%s%s:%d" % (A.ESCALATION_CLAIM_PREFIX, CARD, step), {"at": "then"})
    A.expire_overdue(st, AT_EXPIRY)
    keep_at = AT_EXPIRY + timedelta(minutes=30)                   # Wed 10:30, inside sending hours
    kept = A.decide_expired_booking(card.token, "keep", ghl=Recorder(), store=st, now=keep_at)
    assert kept["ok"] is True
    row = st.get(A.APPROVAL_PREFIX + CARD)
    assert row["escalations"] == 0 and row["last_escalated_at"] is None
    chases = []
    notify_fn = lambda *a, **k: chases.append(a) or {"sent": True}     # noqa: E731
    assert A.escalate_pending(st, now=keep_at + timedelta(minutes=2), notify_fn=notify_fn) == []
    out = A.escalate_pending(st, now=keep_at + timedelta(minutes=6), notify_fn=notify_fn)
    assert [o["step"] for o in out] == [1] and len(chases) == 1       # rung 1, on the new clock
    assert st.get("%s%s:r1:1" % (A.ESCALATION_CLAIM_PREFIX, CARD))
    assert A.escalate_pending(st, now=keep_at + timedelta(minutes=7), notify_fn=notify_fn) == []
    assert st.get(A.APPROVAL_PREFIX + CARD)["escalations"] == 1
