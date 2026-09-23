"""S-rest round 3: no approved reply goes out after the lead said no.

Defect 1. approved_queued cards stopped expiring at 48 h (kept, per the
rulings), and send_approved never looked at the lead's newer replies. A lead
who replied Fri 15:30 CT, whose answer Lorenzo approved at 20:00 (queued for
Mon 07:00), and who wrote "Please remove me from your list" on Saturday got
the Friday answer at 07:05 on Monday. Now:

* at arrival, an opt-out or a final no (router.OPT_OUT_LABELS) blocks every
  open card of the lead's (pending, approved_queued, blocked, stale_slots,
  send_failed) with a stated problem, releases their offered times and
  tells Lorenzo once; a card holding a send claim is left to the send
  (round 4: except a send_failed one, whose claim is stale);
* at send (approval.lead_reply_hold, before the claim and again once the card
  is "sending"), the lead row refuses the send: a later reply with an
  opt-out label, an opt-out status or classification, or any later reply a
  machine did not write. An out-of-office never blocks.

Defect 2. approve()'s queue write is status-guarded: losing to an expiry or a
veto answers "card changed" and leaves no queued card without reservations.

Defect 3. send_approved reads the card context before "sending", and the
sweep keeps a card's row for 10 minutes after it is sent.

Every lead is an example.com address; every client is an in-process fake.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from shared import job_log, notify
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import router
from services.reply_engine import show_rate
from services.reply_engine.models import Approval, Draft, LeadState, ReplyEvent

CT = pytz.timezone("America/Chicago")
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"
LEAD = "owner@example.com"
EACCOUNT = "lorenzo@advero-example.com"
THREAD = "thread-optout-1"
SUBJECT = "Re: Owner, question"
POSITIVE = "Sounds interesting. How does pricing work?"
APPT = "appt-optout-1"


def ct(*args):
    return CT.localize(datetime(*args))


FRI_REPLY = ct(2026, 9, 25, 15, 30)       # Friday 15:30 CT
FRI_APPROVE = ct(2026, 9, 25, 20, 0)      # outside the window: queued for Monday 07:00
SAT = ct(2026, 9, 26, 10, 12)
MON_FLUSH = ct(2026, 9, 28, 7, 5)


class FakeInstantly(object):
    def __init__(self):
        self.sent = []
        self.interest = []
        self.blocklist = []
        self.hook_on = None
        self.hook = None

    def _fire(self, where):
        if self.hook_on == where and self.hook is not None:
            hook, self.hook = self.hook, None
            hook()

    def get_email(self, email_id):
        return {"id": email_id, "from_address_email": LEAD}

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.sent.append({"reply_to_uuid": reply_to_uuid, "to": to, "body": body})
        self._fire("send")
        return {"id": "sent-%d" % len(self.sent)}

    def update_interest_status(self, lead_email, campaign_id, value):
        self.interest.append((lead_email, campaign_id, value))
        self._fire("interest")
        return {"ok": True}

    def blocklist_create(self, value):
        self.blocklist.append(value)
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
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    notify.reset_for_tests()
    rows = []
    real = job_log.log_run
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: rows.append((job, status, details))
                        or real(job, status, details))
    store = JsonFileStore(tmp_env / "optout.json")
    inst = FakeInstantly()
    ghl = Recorder()
    deps = app_mod.configure(store=store, ghl=ghl, instantly=inst, clock=lambda: FRI_REPLY)
    yield {"store": store, "inst": inst, "ghl": ghl, "deps": deps, "rows": rows}
    app_mod.configure()


def _reply(world, email_id, text, received, now, subject=SUBJECT):
    payload = {"event_type": "reply_received", "timestamp": received.astimezone(pytz.utc).isoformat(),
               "campaign_id": CAMPAIGN, "campaign_name": "x", "lead_email": LEAD, "email_account": EACCOUNT,
               "firstName": "Owner", "companyName": "Example Services", "reply_subject": subject,
               "reply_text": text, "email_id": email_id, "thread_id": THREAD,
               "unibox_url": "https://app.instantly.ai/app/unibox"}
    return app_mod.process_event(ReplyEvent.from_webhook(payload), deps=world["deps"], now=now, busy_blocks=[])


def _alerts(fragment):
    return [n for n in notify.sent_in_test if fragment in n["title"]]


def _registry_rows(store, card_id):
    return [r for r in store.get(A.OFFERED_KEY, []) or [] if isinstance(r, dict) and r.get("approval") == card_id]


def _card_id(token):
    return token.split(".", 1)[0]


def _queued_friday_card(world):
    """Friday 15:30 reply -> card; approved at 20:00 -> queued for Monday 07:00."""
    r1 = _reply(world, "e-1", POSITIVE, FRI_REPLY, FRI_REPLY)
    assert r1["label"].startswith("positive") and r1["approval_token"]
    token = r1["approval_token"]
    out = A.approve(token, world["inst"], store=world["store"], now=FRI_APPROVE, ghl=world["ghl"])
    assert out["ok"] and out["status"] == "approved_queued"
    assert out["send_after"] == ct(2026, 9, 28, 7, 0).isoformat()
    return r1, token


# ====================================================== vocabulary
def test_the_opt_out_statuses_are_the_routers_final_statuses_without_the_booked_ones():
    assert set(router.OPT_OUT_STATUSES) == set(router.FINAL_STATUSES) - set(router.BOOKED_FINAL_STATUSES)
    for label in router.OPT_OUT_LABELS:
        assert label in router.FINAL_STATUSES
    assert "call_booked" not in router.OPT_OUT_STATUSES and "needs_review" in router.OPT_OUT_STATUSES


# ============================================== defect 1: the weekend scenario
def test_weekend_unsubscribe_holds_the_queued_card_and_monday_sends_nothing(world):
    st = world["store"]
    r1, token = _queued_friday_card(world)
    card_id = _card_id(token)
    offered = A.load(token, st).draft.offered_slots
    assert offered and _registry_rows(st, card_id)                    # the Friday card holds its times
    before = len(notify.sent_in_test)

    sat = _reply(world, "e-2", "Please remove me from your list", SAT, SAT)
    assert sat["label"] == "unsubscribe" and sat["approval_token"] is None
    assert sat["cards_held"] == [card_id]
    card = A.load(token, st)
    assert card.status == "blocked"
    problem = [p for p in card.draft.problems if "asked to be removed" in p]
    assert problem and "unsubscribe" in problem[0] and "Sat Sep 26" in problem[0]
    assert "Please remove me" not in problem[0]                     # category and time, never the text
    assert _registry_rows(st, card_id) == []                        # its times are back in the pool
    held = _alerts("HELD: the lead asked to be removed")
    assert len(held) == 1 and len(notify.sent_in_test) == before + 1
    assert card_id in held[0]["message"] and "Nothing was sent" in held[0]["message"]

    out = A.flush_queued(world["inst"], store=st, now=MON_FLUSH, ghl=world["ghl"])
    assert out == [] and world["inst"].sent == []
    # a blocked card is not approved_queued: it expires at its 48 h (Sunday 15:30) and is never sent
    assert A.load(token, st).status == "expired"
    assert st.get(A.SEND_CLAIM_PREFIX + card_id) is None


def test_weekend_unsubscribe_is_refused_at_send_even_when_the_arrival_hold_never_ran(world, monkeypatch):
    """The send-time check on its own: the arrival hold is switched off, so
    the queued card is still approved_queued on Monday morning."""
    st = world["store"]
    r1, token = _queued_friday_card(world)
    card_id = _card_id(token)
    monkeypatch.setattr(A, "hold_cards_for_lead_reply", lambda *a, **k: [])
    sat = _reply(world, "e-2", "Please remove me from your list", SAT, SAT)
    assert sat["label"] == "unsubscribe" and A.load(token, st).status == "approved_queued"
    assert _registry_rows(st, card_id)
    before = len(notify.sent_in_test)

    out = A.flush_queued(world["inst"], store=st, now=MON_FLUSH, ghl=world["ghl"])
    assert world["inst"].sent == []
    assert len(out) == 1 and out[0]["ok"] is False and out[0]["status"] == "blocked"
    assert out[0]["lead_reply"]["category"] == "unsubscribe" and out[0]["lead_reply"]["email_id"] == "e-2"
    card = A.load(token, st)
    assert card.status == "blocked" and any("asked to be removed" in p for p in card.draft.problems)
    assert _registry_rows(st, card_id) == [] and st.get(A.SEND_CLAIM_PREFIX + card_id) is None
    assert len(_alerts("HELD: the lead asked to be removed")) == 1 and len(notify.sent_in_test) == before + 1
    assert any(r[1] == "blocked_lead_replied" for r in world["rows"])
    # the next tick does not send it either
    A.flush_queued(world["inst"], store=st, now=MON_FLUSH + timedelta(minutes=5), ghl=world["ghl"])
    assert world["inst"].sent == []


@pytest.mark.parametrize("text,label,said", [
    ("Stop emailing me. This is spam and I will report you.", "negative_hostile", "sent a hostile reply"),
    ("I'm not the right person for this, I don't handle marketing here.", "wrong_person",
     "said they are the wrong person"),
    ("Not interested, thanks.", "negative_notfit", "said it is not a fit"),
    ("Not right now, maybe next quarter.", "negative_notnow", "said not now"),
], ids=["hostile", "wrong_person", "not_interested", "not_now"])
@pytest.mark.parametrize("arrival_hold", [True, False], ids=["held_at_arrival", "held_at_send"])
def test_a_final_no_over_the_weekend_keeps_the_queued_card_from_going_out(world, monkeypatch, text, label, said,
                                                                          arrival_hold):
    st = world["store"]
    r1, token = _queued_friday_card(world)
    card_id = _card_id(token)
    if not arrival_hold:
        monkeypatch.setattr(A, "hold_cards_for_lead_reply", lambda *a, **k: [])
    sat = _reply(world, "e-2", text, SAT, SAT)
    assert sat["label"] == label and sat["approval_token"] is None
    A.flush_queued(world["inst"], store=st, now=MON_FLUSH, ghl=world["ghl"])
    assert world["inst"].sent == []
    card = A.load(token, st)
    # held at arrival: blocked on Saturday, expired at its 48 h on Sunday;
    # held at send: approved_queued never expires, the Monday flush blocks it
    assert card.status == ("expired" if arrival_hold else "blocked")
    assert any(said in p and label in p for p in card.draft.problems)
    assert _registry_rows(st, card_id) == [] and st.get(A.SEND_CLAIM_PREFIX + card_id) is None
    assert len(_alerts("HELD: the lead %s" % said)) == 1


# ============================================ newer human reply / machine reply
def _direct_card(store, card_id="c1", status="pending", email_id="e-1", offered=None, created=None):
    created = created or ct(2026, 9, 28, 9, 0)
    offered = offered if offered is not None else ["2026-09-30T13:00:00-05:00"]
    d = Draft(subject=SUBJECT, body_text="Hey Owner,\n\nHappy to explain. Does Wed 1:00pm CT work?\n\nLorenzo",
              offered_slots=offered, label="positive_question")
    expires = (created + timedelta(hours=48)).isoformat()
    state_key = "lead:%s:%s" % (CAMPAIGN, LEAD)
    card = Approval(token=A.make_token(card_id, state_key, A.draft_hash(d), expires), state_key=state_key,
                    lead_email=LEAD, campaign_id=CAMPAIGN, email_id=email_id, eaccount=EACCOUNT, reply_to=LEAD,
                    draft=d, status=status, created_at=created.isoformat(), expires_at=expires,
                    label="positive_question")
    store.set(A.APPROVAL_PREFIX + card_id, card.model_dump(mode="json"))
    store.set(A.APPROVAL_CONTEXT_PREFIX + card_id,
              {"email_id": email_id, "reply_at": created.isoformat(), "processed_before": [],
               "processed_count": 0, "tracks_history": True, "approved_at": None, "send_attempts": 0})
    if offered:
        A.reserve_slots(store, LEAD, offered, card_id, created)
    return card


def _lead_row(store, tokens, processed, history, status="draft_pending_approval", classification=None,
              cadence=None):
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Owner", eaccount=EACCOUNT,
                      approvals=list(tokens), processed_email_ids=list(processed), cadence=cadence or {})
    row = dict(state.to_store(), history=list(history), status=status, classification=classification)
    last = history[-1] if history else {}
    row["last_email_id"] = last.get("email_id")
    row["last_inbound_at"] = last.get("at")
    store.set(state.key, row)
    return state.key


def _inbound(email_id, label, at):
    return {"at": at.isoformat(), "event": "inbound", "email_id": email_id, "label": label, "source": "webhook"}


IN_HOURS = ct(2026, 9, 28, 10, 0)


@pytest.mark.parametrize("label", ["neutral_question", None], ids=["labelled", "unlabelled"])
def test_a_newer_human_reply_that_raised_no_card_blocks_the_send(world, label):
    st = world["store"]
    card = _direct_card(st)
    history = [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0))]
    if label is not None:
        history.append(_inbound("e-2", label, ct(2026, 9, 28, 9, 40)))
    _lead_row(st, [card.token], ["e-1", "e-2"], history)
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and world["inst"].sent == []
    assert out["lead_reply"]["reason"] == "newer_reply" and out["lead_reply"]["email_id"] == "e-2"
    assert any("wrote again after this card was drafted" in p for p in A.load(card.token, st).draft.problems)
    assert _registry_rows(st, "c1") == [] and st.get(A.SEND_CLAIM_PREFIX + "c1") is None
    assert len(_alerts("HELD: the lead wrote again")) == 1


@pytest.mark.parametrize("label", ["ooo", "auto_reply_unmonitored", "auto_reply"])
def test_a_machine_reply_after_the_card_does_not_block_the_send(world, label):
    st = world["store"]
    card = _direct_card(st)
    status = "ooo" if label == "ooo" else "auto_reply"
    _lead_row(st, [card.token], ["e-1", "e-2"],
              [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0)),
               _inbound("e-2", label, ct(2026, 9, 28, 9, 2))], status=status,
              classification={"label": label if label != "auto_reply" else "auto_reply_unmonitored",
                              "confidence": 1.0, "method": "rules", "reason": "x"})
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent" and len(world["inst"].sent) == 1
    assert _alerts("HELD") == []


def test_an_out_of_office_through_the_pipeline_does_not_block_the_queued_card(world):
    st = world["store"]
    r1, token = _queued_friday_card(world)
    ooo = _reply(world, "e-2", "I am out of the office until September 30 with limited access to email.",
                 SAT, SAT, subject="Automatic reply: Owner, question")
    assert ooo["label"] == "ooo" and ooo["cards_held"] == []
    assert A.load(token, st).status == "approved_queued"
    out = A.flush_queued(world["inst"], store=st, now=MON_FLUSH, ghl=world["ghl"])
    assert len(world["inst"].sent) == 1 and out[0]["ok"] is True
    assert _alerts("HELD") == []


# ============================================== approve after an opt-out
def _opted_out_row(st, card, status="blocklisted", label="unsubscribe"):
    return _lead_row(st, [card.token], ["e-1", "e-2"],
                     [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0)),
                      _inbound("e-2", label, ct(2026, 9, 28, 9, 30))], status=status,
                     classification={"label": label, "confidence": 1.0, "method": "rules", "reason": "x"})


def test_a_pending_card_approved_after_an_opt_out_is_refused_at_send(world):
    st = world["store"]
    card = _direct_card(st)
    _opted_out_row(st, card)
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and world["inst"].sent == []
    assert out["lead_reply"] == {"reason": "opt_out", "category": "unsubscribe", "email_id": "e-2",
                                 "at": ct(2026, 9, 28, 9, 30).isoformat()}
    assert _registry_rows(st, "c1") == [] and len(_alerts("HELD: the lead asked to be removed")) == 1
    # a second tap answers "already blocked", nothing else
    again = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert again["ok"] is False and "blocked" in again["error"] and world["inst"].sent == []


def test_a_pending_card_approved_outside_hours_after_an_opt_out_is_held_not_queued(world):
    st = world["store"]
    card = _direct_card(st)
    _opted_out_row(st, card)
    out = A.approve(card.token, world["inst"], store=st, now=ct(2026, 9, 28, 20, 0), ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked"
    assert A.load(card.token, st).status == "blocked" and _registry_rows(st, "c1") == []
    A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5), ghl=world["ghl"])
    assert world["inst"].sent == []


@pytest.mark.parametrize("status", ["blocklisted", "needs_review", "lost", "follow_up_later", "wrong_person"])
def test_an_opt_out_status_alone_refuses_the_send(world, status):
    """Only the row's status says it (the history does not reach back to it)."""
    st = world["store"]
    card = _direct_card(st)
    _lead_row(st, [card.token], ["e-1"], [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0))],
              status=status)
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and world["inst"].sent == []
    assert out["lead_reply"]["category"] == status


def test_a_booked_status_does_not_refuse_the_send(world):
    st = world["store"]
    card = _direct_card(st)
    _lead_row(st, [card.token], ["e-1"], [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0))],
              status="call_booked")
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is True and len(world["inst"].sent) == 1


# ============================================== Retry and Keep
def test_retry_on_an_opted_out_leads_card_is_refused(world):
    """Round 4 (the reviewer's non-blocking item): a send_failed card is held
    at arrival whether or not it still holds its failed attempt's claim.
    Nothing of it can be in flight (a send never starts from send_failed),
    so the claim is stale: it is written to the card's history and dropped.
    Round 3 left the claim-holder at send_failed, and the stuck-card push
    kept asking Lorenzo to Retry a reply to a lead who asked to be removed.
    Retry now has nothing to retry on either card, and the push says the
    failed attempt may have reached the lead instead of "Nothing was sent"."""
    st = world["store"]
    free = _direct_card(st, card_id="c1", status="send_failed")
    claimed = _direct_card(st, card_id="c2", status="send_failed", email_id="e-0",
                           offered=["2026-10-01T13:00:00-05:00"])
    st.set(A.SEND_CLAIM_PREFIX + "c2", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    _lead_row(st, [claimed.token, free.token], ["e-0", "e-1"],
              [_inbound("e-0", "positive_question", ct(2026, 9, 28, 8, 0)),
               _inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0))])
    unsub = _reply(world, "e-2", "Please remove me from your list", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 30))
    assert unsub["label"] == "unsubscribe" and unsub["cards_held"] == ["c2", "c1"]
    assert A.load(free.token, st).status == "blocked"
    assert A.load(claimed.token, st).status == "blocked"
    assert st.get(A.SEND_CLAIM_PREFIX + "c2") is None                   # the stale claim is gone...
    history = A.card_history(st, A.load(claimed.token, st))
    assert history["send_started"] is True and history["send_attempts"] == 1   # ...but its attempt is on record
    for token in (free.token, claimed.token):
        refused = A.retry(token, store=st, now=IN_HOURS)
        assert refused["ok"] is False and "nothing to retry" in refused["error"]
    held = _alerts("HELD: the lead asked to be removed")
    assert len(held) == 1 and "c1" in held[0]["message"] and "c2" in held[0]["message"]
    assert "Nothing more was sent" in held[0]["message"] and "nothing of them is still in flight" in held[0]["message"]
    assert "reply by hand" not in held[0]["message"]
    assert world["inst"].sent == []


def test_keep_on_an_opted_out_leads_expired_card_never_sends(world):
    st = world["store"]
    created = ct(2026, 9, 28, 9, 0)
    card = _direct_card(st, created=created, offered=["2026-10-01T15:00:00-05:00"])
    booking = {"slot": "2026-10-01T15:00:00-05:00", "appointment_id": APPT, "awaiting_approval": True,
               "owner": "c1", "booked_at": created.isoformat()}
    show_rate.hold(st, APPT, reason="awaiting_approval", now=created,
                   meta={"lead_email": LEAD, "start_iso": booking["slot"]})
    _lead_row(st, [card.token], ["e-1"], [_inbound("e-1", "positive_question", created)],
              cadence={"booking": booking})
    expired = A.expire_overdue(st, now=created + timedelta(hours=48, minutes=5))
    assert [e["approval"] for e in expired] == ["c1"]
    # Wednesday: the lead writes "remove me"; the expired card is not open, so nothing is held at arrival
    unsub = _reply(world, "e-2", "Please remove me from your list", ct(2026, 9, 30, 10, 0), ct(2026, 9, 30, 10, 0))
    assert unsub["label"] == "unsubscribe" and unsub["cards_held"] == []
    kept = A.decide_expired_booking(card.token, "keep", ghl=world["ghl"], instantly=world["inst"], store=st,
                                    now=ct(2026, 9, 30, 10, 5))
    assert kept["ok"] is True and kept["status"] == "pending"
    out = A.approve(kept["token"], world["inst"], store=st, now=ct(2026, 9, 30, 10, 10), ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and world["inst"].sent == []
    assert "Veto the card to cancel it" in _alerts("HELD: the lead asked to be removed")[-1]["message"]
    assert not [c for c in world["ghl"].calls if c[0] == "update_appointment_status"]


# ============================================== the arrival-time hold
def test_the_arrival_hold_covers_every_open_status_and_leaves_a_claim_holder_alone(world):
    st = world["store"]
    statuses = ["pending", "approved_queued", "blocked", "stale_slots", "send_failed"]
    cards = []
    for i, status in enumerate(statuses):
        cards.append(_direct_card(st, card_id="k%d" % i, status=status, email_id="e-%d" % i,
                                  offered=["2026-10-0%dT13:00:00-05:00" % (i + 1)]))
    claimed = _direct_card(st, card_id="kc", status="approved_queued", email_id="e-c",
                           offered=["2026-10-06T13:00:00-05:00"])
    st.set(A.SEND_CLAIM_PREFIX + "kc", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    sending = _direct_card(st, card_id="ks", status="sending", email_id="e-s",
                           offered=["2026-10-07T13:00:00-05:00"])
    done = _direct_card(st, card_id="kd", status="sent", email_id="e-d", offered=[])
    tokens = [c.token for c in cards] + [claimed.token, sending.token, done.token]
    _lead_row(st, tokens, ["e-%d" % i for i in range(5)],
              [_inbound("e-%d" % i, "positive_question", ct(2026, 9, 28, 8, i)) for i in range(5)])
    out = _reply(world, "e-9", "Please remove me from your list", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 30))
    assert out["label"] == "unsubscribe"
    assert sorted(out["cards_held"]) == ["k%d" % i for i in range(5)]
    for i, card in enumerate(cards):
        stored = A._approval_row(st, "k%d" % i)
        assert stored.status == "blocked", statuses[i]
        assert any("asked to be removed" in p for p in stored.draft.problems), statuses[i]
        assert _registry_rows(st, "k%d" % i) == [], statuses[i]
    assert A._approval_row(st, "kc").status == "approved_queued" and _registry_rows(st, "kc")
    assert A._approval_row(st, "ks").status == "sending" and _registry_rows(st, "ks")
    assert A._approval_row(st, "kd").status == "sent"
    held = _alerts("HELD: the lead asked to be removed")
    assert len(held) == 1 and all("k%d" % i in held[0]["message"] for i in range(5))


def test_an_opt_out_landing_while_the_send_takes_its_claim_is_caught_once_the_card_is_sending(world, monkeypatch):
    """The race the arrival hold hands to the send: the opt-out lands after
    the send took its claim but before the card moved to "sending". The
    arrival hold leaves the claim-holder alone; the send's second look at the
    lead row, made once the card is "sending", holds it."""
    st = world["store"]
    card = _direct_card(st)
    _lead_row(st, [card.token], ["e-1"], [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0))])
    real = A._claim_send
    box = {}

    def claim_then_opt_out(store, approval_id, ts):
        attempt = real(store, approval_id, ts)
        box["unsub"] = _reply(world, "e-2", "Please remove me from your list", ct(2026, 9, 28, 9, 58),
                              ct(2026, 9, 28, 9, 58))
        return attempt

    monkeypatch.setattr(A, "_claim_send", claim_then_opt_out)
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert box["unsub"]["label"] == "unsubscribe" and box["unsub"]["cards_held"] == []
    assert out["ok"] is False and out["status"] == "blocked" and world["inst"].sent == []
    assert A.load(card.token, st).status == "blocked"
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None and _registry_rows(st, "c1") == []
    assert len(_alerts("HELD: the lead asked to be removed")) == 1


# ============================================== defect 2: the queue write
def _pending_owner_card(world, created):
    st = world["store"]
    card = _direct_card(st, created=created, offered=["2026-10-01T15:00:00-05:00"])
    _lead_row(st, [card.token], ["e-1"], [_inbound("e-1", "positive_question", created)])
    return card


def test_the_queue_write_loses_to_an_expiry_and_answers_card_changed(world, monkeypatch):
    """Approved at 20:59, one minute before the TTL; the tick on another
    worker expires the card (releasing its times) before the queue write."""
    st = world["store"]
    created = ct(2026, 9, 28, 21, 0)
    card = _pending_owner_card(world, created)
    at_approve = created + timedelta(hours=47, minutes=59)
    real = A._note_card_history

    def note_then_expire(store, approval_id, ts, **kw):
        real(store, approval_id, ts, **kw)
        A.expire_overdue(store, now=created + timedelta(hours=48))

    monkeypatch.setattr(A, "_note_card_history", note_then_expire)
    out = A.approve(card.token, world["inst"], store=st, now=at_approve, ghl=world["ghl"])
    assert out["ok"] is False and "card changed" in out["error"] and out["status"] == "expired"
    assert A.load(card.token, st).status == "expired"
    assert _registry_rows(st, "c1") == []
    assert [k for k in st.keys(A.APPROVAL_PREFIX) if st.get(k).get("status") == "approved_queued"] == []
    A.flush_queued(world["inst"], store=st, now=ct(2026, 10, 1, 7, 5), ghl=world["ghl"])
    assert world["inst"].sent == []


def test_the_queue_write_loses_to_a_veto_and_answers_card_changed(world, monkeypatch):
    st = world["store"]
    card = _pending_owner_card(world, ct(2026, 9, 28, 9, 0))
    real = A._note_card_history

    def note_then_veto(store, approval_id, ts, **kw):
        real(store, approval_id, ts, **kw)
        A.veto(card.token, store=store, now=ts, ghl=world["ghl"], instantly=world["inst"])

    monkeypatch.setattr(A, "_note_card_history", note_then_veto)
    out = A.approve(card.token, world["inst"], store=st, now=ct(2026, 9, 28, 20, 0), ghl=world["ghl"])
    assert out["ok"] is False and "card changed" in out["error"] and out["status"] == "vetoed"
    assert A.load(card.token, st).status == "vetoed" and _registry_rows(st, "c1") == []
    A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5), ghl=world["ghl"])
    assert world["inst"].sent == []


def test_the_queue_write_still_queues_an_untouched_card(world):
    st = world["store"]
    card = _pending_owner_card(world, ct(2026, 9, 28, 9, 0))
    out = A.approve(card.token, world["inst"], store=st, now=ct(2026, 9, 28, 20, 0), ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "approved_queued"
    assert A.load(card.token, st).status == "approved_queued" and _registry_rows(st, "c1")


# ============================================== defect 3: the sweep mid-send
def test_a_sweep_during_the_send_leaves_seen_before_and_reply_at_intact(world):
    """The crash gap (the card's own email never recorded as processed) plus
    a sweep that runs after the card is saved "sent", with a clock far enough
    ahead that the grace window does not protect the row. The context was
    read before "sending" and carried through: the newer reply that landed
    during the send is still seen (newer_inbound, not the open-card
    fallback), and reply_at still lands on the history and the Job_Log row."""
    st = world["store"]
    r1 = _reply(world, "g-1", POSITIVE, FRI_REPLY, FRI_REPLY)
    token = r1["approval_token"]
    card_id = _card_id(token)
    key = r1["state_key"]
    raw = st.get(key)
    st.set(key, dict(raw, processed_email_ids=[x for x in raw["processed_email_ids"] if x != "g-1"]))
    reply_at = A.card_context(st, card_id)["reply_at"]
    assert reply_at
    send_at = ct(2026, 9, 25, 15, 40)
    box = {}

    def during():
        box["r2"] = _reply(world, "g-2", "Also, do you work with offices in NJ?", ct(2026, 9, 25, 15, 41),
                           ct(2026, 9, 25, 15, 41))
        box["swept"] = A.sweep_card_contexts(st, send_at + timedelta(hours=1))

    world["inst"].hook_on = "interest"
    world["inst"].hook = during
    out = A.approve(token, world["inst"], store=st, now=send_at, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent" and len(world["inst"].sent) == 1
    assert box["swept"] >= 1 and st.get(A.APPROVAL_CONTEXT_PREFIX + card_id) is None
    assert out["cadence"] == {"armed": False, "reason": "newer_inbound:g-2"}
    sent_entries = [h for h in st.get(key)["history"] if h.get("event") in ("reply_sent", "reply_would_send")]
    assert sent_entries and sent_entries[-1]["reply_at"] == reply_at
    logged = [r for r in world["rows"] if r[1] in ("sent", "would_send")]
    assert logged and logged[-1][2]["reply_at"] == reply_at


def test_the_sweep_keeps_a_just_sent_cards_context_for_ten_minutes(world):
    st = world["store"]
    card = _direct_card(st, status="sent", offered=[])
    sent_at = ct(2026, 9, 28, 10, 0)
    st.set(A.APPROVAL_PREFIX + "c1", dict(st.get(A.APPROVAL_PREFIX + "c1"), decided_at=sent_at.isoformat()))
    assert A.sweep_card_contexts(st, sent_at + timedelta(minutes=9)) == 0
    assert st.get(A.APPROVAL_CONTEXT_PREFIX + "c1") is not None
    assert A.sweep_card_contexts(st, sent_at + timedelta(minutes=10)) == 1
    assert st.get(A.APPROVAL_CONTEXT_PREFIX + "c1") is None


# ============================================== _keep_hold reads tri-state
class _FlakyReads(object):
    """Wraps a store; the first ``fail`` reads of the hold key raise."""

    def __init__(self, store, fail):
        self._store = store
        self.fail = fail

    def get(self, key, default=None):
        if key == show_rate.hold_key(APPT) and self.fail > 0:
            self.fail -= 1
            raise IOError("store read timed out")
        return self._store.get(key, default)

    def __getattr__(self, name):
        return getattr(self._store, name)


def test_keep_hold_reports_kept_missing_and_unknown(world):
    st = world["store"]
    booking = {"appointment_id": APPT, "slot": "2026-10-01T15:00:00-05:00"}
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN)
    assert A._keep_hold(st, state, booking, IN_HOURS) is True and show_rate.is_held(st, APPT)
    # an unreadable marker is written anyway (fail closed) and reported as kept once it reads back
    st.delete(show_rate.hold_key(APPT))
    assert A._keep_hold(_FlakyReads(st, 1), state, booking, IN_HOURS) is True and show_rate.is_held(st, APPT)
    # a read-back that also fails is unknown, not "not held"
    assert A._keep_hold(_FlakyReads(st, 2), state, booking, IN_HOURS) is None
