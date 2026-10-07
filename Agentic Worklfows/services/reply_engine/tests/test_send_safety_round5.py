"""Send-safety round 5: the reviewer-max round-4 REJECT, as regression tests.

The defect: a follow-up went out after the lead's newer reply while that
reply's card was still pending. send_approved armed the ladder on the copy it
re-read after the Instantly send, stamping armed_at at send time (later than
the newer reply's own timestamp, so the tick's inbound check never fired), and
every lead-row writer put its whole copy back:

* Case X: reply 2 is processed during the Instantly send. Card B pending, the
  ladder armed and unstopped, D1 out Tue 10:00.
* Case Y: reply 2 is written between the send's re-read and its save. Card B
  falls out of the lead's approvals, D1 out.
* Mid-ladder: the lead answered D1; that answer (card A1) is sent while reply 2
  lands. The stop is undone and the canned D2 goes out with no veto ping.
* Resume race: the reply lands while Resume holds its copy. The stop is
  undone, last_inbound_at goes back to None, card B drops out, D1 is sent.

What is pinned here: send_approved decides whether to arm under the row's lock,
against the row as it stands (arm_refusal); every save_lead_state writer merges
three ways (stop fields as a group, last_inbound_at forward-only, the
append-only lists combined); and a reply pipeline that read the row before an
arm and writes after it stops the ladder under the lock (Case Z,
app._inbound_stop_hook), unless that arm answered this very reply.

Scenarios are the reviewer's probes (scratchpad/review-s/test_r4_*.py). Every
client is an in-process fake; live mode is set in-process only.
"""
from datetime import timedelta
from urllib.parse import quote, urlencode

import pytest
from fastapi.testclient import TestClient

from shared import notify
from shared.store import JsonFileStore

from jobs import cadence_tick as cadence_job
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine import show_rate
from services.reply_engine.models import Approval, Draft, LeadState, ReplyEvent

from test_send_safety_round2 import (  # noqa: F401 - shared fakes, worlds and the env fixture
    D1_FREE, SOPIO, FakeInstantly, Recorder, _d1_state, _email_leg, _go_live, _r6_stopped, ct, env, fixture_item,
)
from test_send_safety_round3 import _sopio_confirm_card

# These tests cover the E1 Veto window, switched off on 2026-10-06 (cadence.E1_VETO).
pytestmark = pytest.mark.usefixtures("e1_veto_on")

TIFF = "tiffany@flowerhillfs.com"
D1_SLOTS = D1_FREE + ["2026-09-24T13:00:00-05:00", "2026-09-25T14:00:00-05:00"]
LADDER_SLOTS = D1_SLOTS + ["2026-09-28T13:00:00-05:00", "2026-09-29T14:00:00-05:00", "2026-09-30T13:00:00-05:00"]


class HookInstantly(FakeInstantly):
    """FakeInstantly that runs ``hook`` once, right after the named call
    ("send": reply_to_email, "interest": update_interest_status)."""

    def __init__(self, sender, hook_on=None):
        FakeInstantly.__init__(self, sender=sender)
        self.hook_on = hook_on
        self.hook = None

    def _fire(self, where):
        if self.hook_on == where and self.hook is not None:
            hook, self.hook = self.hook, None
            hook()

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        out = FakeInstantly.reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=to)
        self._fire("send")
        return out

    def update_interest_status(self, *a, **k):
        out = FakeInstantly.update_interest_status(self, *a, **k)
        self._fire("interest")
        return out


def _payload(email_id, text, ts, campaign_id=None, subject=None):
    item = fixture_item(TIFF)
    return {"event_type": "reply_received", "timestamp": ts, "campaign_id": campaign_id or item["campaign_id"],
            "campaign_name": "x", "lead_email": TIFF, "email_account": item["eaccount"], "firstName": "Tiffany",
            "companyName": "Flowerhill Facility Services", "reply_subject": subject or item["subject"],
            "reply_text": text, "email_id": email_id, "thread_id": item["thread_id"],
            "unibox_url": "https://app.instantly.ai/app/unibox"}


def _reply(deps, email_id, text, ts, now, campaign_id=None, subject=None):
    return app_mod.process_event(ReplyEvent.from_webhook(_payload(email_id, text, ts, campaign_id, subject)),
                                 deps=deps, now=now, busy_blocks=[])


def _nf(pings):
    return lambda *a, **k: pings.append(a[0]) or {"sent": True, "email": True}   # noqa: E731


def _ticks(store, whens, free, pings):
    """The real hourly job, live, with a fresh fake Instantly. Returns it and
    (action, reason, day) per tick."""
    inst = FakeInstantly(sender=TIFF)
    out = []
    for when in whens:
        summary = cadence_job.run(when, store, inst, None, free_slots=free, notify_fn=_nf(pings),
                                  log_fn=lambda *a, **k: None)
        out.append([(r.get("action"), r.get("reason"), r.get("day")) for r in summary["results"]])
    return inst, out


def _listed(row, token):
    card = str(token).split(".", 1)[0]
    return any(str(t).split(".", 1)[0] == card for t in row.get("approvals") or [])


def _veto_or_d1_pings(pings):
    return [p for p in pings if "D1" in p or "Veto" in p]


@pytest.fixture
def tiff(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "tiff.json")
    inst = HookInstantly(TIFF)
    ghl = Recorder()
    deps = app_mod.configure(store=store, ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 21, 15, 0))
    yield {"store": store, "inst": inst, "ghl": ghl, "deps": deps}
    app_mod.configure()


def _first_card(tiff, monkeypatch, email_id="t-1"):
    """Tiffany's first reply (Mon 19:00Z) raises card A; then live, email leg on."""
    r1 = _reply(tiff["deps"], email_id, "Sounds interesting. How does pricing work?", "2026-09-21T19:00:00Z",
                ct(2026, 9, 21, 14, 0))
    _email_leg(monkeypatch)
    _go_live(monkeypatch)
    return r1


def _approve_with_reply_during(tiff, token, hook_on, email_id, text, ts, now):
    """Approve ``token`` while the lead's next reply is processed inside the
    named Instantly call. Returns (send result, reply 2 result)."""
    box = {}
    tiff["inst"].hook_on = hook_on
    tiff["inst"].hook = lambda: box.update(r2=_reply(tiff["deps"], email_id, text, ts, now))
    sent = A.approve(token, tiff["inst"], store=tiff["store"], now=now, ghl=tiff["ghl"])
    assert "r2" in box, "the reply was not processed inside the %s call" % hook_on
    return sent, box["r2"]


# ============================================= Case X / Case Y: first reply
@pytest.mark.parametrize("hook_on", ["send", "interest"], ids=["case_x_during_send", "case_y_after_the_re_read"])
def test_a_reply_landing_while_the_answer_goes_out_leaves_the_ladder_unarmed_and_its_card_listed(tiff, monkeypatch,
                                                                                               hook_on):
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch)
    sent, r2 = _approve_with_reply_during(tiff, r1["approval_token"], hook_on, "t-2",
                                          "Also, do you work with commercial cleaning companies in NJ?",
                                          "2026-09-21T20:01:00Z", ct(2026, 9, 21, 15, 1))
    # card A's answer went out once, and did not arm the ladder over reply 2
    assert sent["ok"] and sent["status"] == "sent" and len(tiff["inst"].sent) == 1
    assert sent["cadence"] == {"armed": False, "reason": "newer_inbound:t-2"}
    raw = st.get(r1["state_key"])
    assert not raw["cadence"].get("armed_at") and not cadence.is_armed(LeadState.from_store(raw))
    # reply 2 and its card survived the send's write (Case Y dropped both)
    assert A.load(r2["approval_token"], st).status == "pending"
    assert _listed(raw, r2["approval_token"]) and _listed(raw, r1["approval_token"])
    assert raw["processed_email_ids"] == ["t-1", "t-2"]
    assert raw["last_inbound_at"] == "2026-09-21T20:01:00+00:00"
    assert raw["status"] == "draft_pending_approval"
    # ...and so did the send's own record of the answer
    assert raw["last_outbound_at"] == ct(2026, 9, 21, 15, 1).isoformat()
    events = [h.get("event") for h in raw["history"]]
    assert events.count("inbound") == 2 and events.count("reply_sent") == 1
    # Tuesday's ticks send nothing while card B waits
    pings = []
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0), ct(2026, 9, 23, 10, 0)], D1_SLOTS, pings)
    assert d1.sent == [] and _veto_or_d1_pings(pings) == []
    assert A.load(r2["approval_token"], st).status == "pending"


def test_answering_the_newer_card_then_arms_the_ladder_and_d1_follows_it(tiff, monkeypatch):
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch)
    _, r2 = _approve_with_reply_during(tiff, r1["approval_token"], "send", "t-2",
                                       "Also, do you work with commercial cleaning companies in NJ?",
                                       "2026-09-21T20:01:00Z", ct(2026, 9, 21, 15, 1))
    out = A.approve(r2["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 15, 30), ghl=tiff["ghl"])
    assert out["ok"] and out["cadence"]["armed"] is True
    cad = st.get(r1["state_key"])["cadence"]
    assert cad["armed_at"] == ct(2026, 9, 21, 15, 30).isoformat() and cad["armed_for_email_id"] == "t-2"
    assert cad["next_send_at"] == ct(2026, 9, 22, 10, 0).isoformat() and cad["stopped_reason"] is None
    pings = []
    d1, results = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], D1_SLOTS, pings)
    assert [r[0][0] for r in results] == ["veto_window_opened", "sent"]
    assert len(d1.sent) == 1 and d1.sent[0]["to"] == TIFF
    assert len(_veto_or_d1_pings(pings)) == 1                   # the filter the other tests use does see it


@pytest.mark.parametrize("hook_on", [None, "send"], ids=["before_the_send", "during_the_send"])
def test_an_auto_reply_beside_the_positive_one_does_not_keep_its_answer_from_arming_the_ladder(tiff, monkeypatch,
                                                                                              hook_on):
    """A shared info@ box auto-answers minutes after the lead's positive reply:
    no card, and card A is not superseded. That machine's answer is not the
    lead writing again, so Lorenzo's answer to card A still arms the ladder."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="a-1")
    ooo = {"email_id": "a-2", "text": "I am out of the office until September 30 with limited access to email.",
           "ts": "2026-09-21T19:02:00Z", "subject": "Automatic reply: Tiffany, question"}
    box = {}

    def robot(now):
        box["ooo"] = _reply(tiff["deps"], ooo["email_id"], ooo["text"], ooo["ts"], now, subject=ooo["subject"])

    if hook_on is None:
        robot(ct(2026, 9, 21, 14, 2))
    else:
        tiff["inst"].hook_on = hook_on
        tiff["inst"].hook = lambda: robot(ct(2026, 9, 21, 14, 30))
    sent = A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 30), ghl=tiff["ghl"])
    assert box["ooo"]["label"] == "ooo" and box["ooo"]["approval_token"] is None
    assert sent["ok"] and sent["cadence"]["armed"] is True
    raw = st.get(r1["state_key"])
    assert raw["processed_email_ids"] == ["a-1", "a-2"]
    assert raw["cadence"]["armed_at"] == ct(2026, 9, 21, 14, 30).isoformat()
    assert raw["cadence"]["stopped_reason"] is None
    d1, results = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], D1_SLOTS, [])
    assert [r[0][0] for r in results] == ["veto_window_opened", "sent"] and len(d1.sent) == 1


# ======================================================= mid-ladder: no D2
@pytest.mark.parametrize("hook_on", ["send", "interest"], ids=["during_send", "after_the_re_read"])
def test_mid_ladder_the_answer_sent_while_the_lead_writes_again_keeps_the_stop_and_d2_never_goes(tiff, monkeypatch,
                                                                                                 hook_on):
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="m-1")
    key = r1["state_key"]
    A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], LADDER_SLOTS, [])
    assert len(d1.sent) == 1 and st.get(key)["cadence"]["day"] == 1
    # the lead answers D1 on Tuesday afternoon: the ladder stops, card A1
    r1b = _reply(tiff["deps"], "m-2", "Thanks - what would you need from us to start?", "2026-09-22T20:00:00Z",
                 ct(2026, 9, 22, 15, 0))
    stopped = dict(st.get(key)["cadence"])
    assert stopped["stopped_reason"] == "inbound_reply" and stopped["needs_fresh_draft"] is True
    # card A1 is sent while the lead writes again (card B)
    sent, r2 = _approve_with_reply_during(tiff, r1b["approval_token"], hook_on, "m-3",
                                          "One more thing: can we loop in my ops manager?", "2026-09-22T21:01:00Z",
                                          ct(2026, 9, 22, 16, 1))
    assert sent["ok"] and sent["status"] == "sent"
    assert sent["cadence"] == {"armed": False, "reason": "newer_inbound:m-3"}
    raw = st.get(key)
    cad = raw["cadence"]
    # the stop is preserved exactly: not re-armed, day not moved
    for field in ("armed_at", "stopped_reason", "stopped_at", "next_send_at", "needs_fresh_draft", "day"):
        assert cad.get(field) == stopped.get(field), field
    assert cad["armed_at"] == ct(2026, 9, 21, 14, 5).isoformat() and cad["next_send_at"] is None
    assert A.load(r2["approval_token"], st).status == "pending" and _listed(raw, r2["approval_token"])
    assert raw["processed_email_ids"] == ["m-1", "m-2", "m-3"]
    # Wednesday: no D2, no veto push, only the "waiting on your answer" line
    pings = []
    d2, results = _ticks(st, [ct(2026, 9, 23, 9, 30), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 10, 0)], LADDER_SLOTS,
                         pings)
    assert d2.sent == [] and _veto_or_d1_pings(pings) == []
    assert results[0] == [("awaiting_fresh_draft", "inbound_reply", 2)]
    assert A.load(r2["approval_token"], st).status == "pending"


# ================================================================= Case Z
def test_case_z_a_reply_whose_pipeline_straddles_the_arm_stops_the_ladder_under_the_lock(tiff, monkeypatch):
    """Reply 2's pipeline reads the row, card A's answer is sent and arms the
    ladder (reply 2 is not on the row yet, so nothing refuses it), then reply
    2's pipeline writes. Its stop is applied to the row as it stands."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="z-1")
    real_classify = app_mod.classify
    fired = {}

    def classify_then_approve(event):
        if not fired:
            fired["sent"] = A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 15, 1),
                                      ghl=tiff["ghl"])
        return real_classify(event)

    monkeypatch.setattr(app_mod, "classify", classify_then_approve)
    r2 = _reply(tiff["deps"], "z-2", "Also, do you work with janitorial companies in NJ?", "2026-09-21T20:00:30Z",
                ct(2026, 9, 21, 15, 1))
    monkeypatch.setattr(app_mod, "classify", real_classify)
    assert fired["sent"]["ok"] and fired["sent"]["cadence"]["armed"] is True
    raw = st.get(r1["state_key"])
    cad = raw["cadence"]
    assert cad["armed_at"] == ct(2026, 9, 21, 15, 1).isoformat() and cad["armed_for_email_id"] == "z-1"
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert cad["next_send_at"] is None
    assert A.load(r2["approval_token"], st).status == "pending" and _listed(raw, r2["approval_token"])
    pings = []
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], D1_SLOTS, pings)
    assert d1.sent == [] and _veto_or_d1_pings(pings) == []


def test_a_crashed_pipeline_that_straddled_the_arm_still_stops_the_ladder_and_is_retried(tiff, monkeypatch):
    """process_event's error write goes through the same merge and hook."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="c-1")
    real_classify = app_mod.classify
    fired = {}

    def approve_then_crash(event):
        if not fired:
            fired["sent"] = A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 15, 1),
                                      ghl=tiff["ghl"])
            raise RuntimeError("classifier outage")
        return real_classify(event)

    monkeypatch.setattr(app_mod, "classify", approve_then_crash)
    with pytest.raises(RuntimeError):
        _reply(tiff["deps"], "c-2", "Also, do you work with janitorial companies in NJ?", "2026-09-21T20:00:30Z",
               ct(2026, 9, 21, 15, 1))
    raw = st.get(r1["state_key"])
    assert raw["cadence"]["armed_for_email_id"] == "c-1" and raw["cadence"]["stopped_reason"] == "inbound_reply"
    assert raw["processed_email_ids"] == ["c-1"] and _listed(raw, r1["approval_token"])
    # the claim was released: the retry is real work and raises card B
    r2 = _reply(tiff["deps"], "c-2", "Also, do you work with janitorial companies in NJ?", "2026-09-21T20:00:30Z",
                ct(2026, 9, 21, 15, 6))
    monkeypatch.setattr(app_mod, "classify", real_classify)
    raw = st.get(r1["state_key"])
    assert A.load(r2["approval_token"], st).status == "pending" and raw["processed_email_ids"] == ["c-1", "c-2"]
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], D1_SLOTS, [])
    assert d1.sent == []


def test_approving_a_replys_own_card_before_its_pipeline_writes_does_not_stop_the_ladder(tiff, monkeypatch):
    """The exception in the hook: the arm answered this very reply
    (armed_for_email_id), so the reply's own write leaves it running."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="o-1")
    key = r1["state_key"]
    A.approve(r1["approval_token"], tiff["inst"], store=st, now=ct(2026, 9, 21, 14, 5), ghl=tiff["ghl"])
    d1, _ = _ticks(st, [ct(2026, 9, 22, 9, 30), ct(2026, 9, 22, 10, 0)], LADDER_SLOTS, [])
    assert len(d1.sent) == 1
    real_create = app_mod.approval_mod.create_approval
    fired = {}

    def create_then_approve(*a, **k):
        card = real_create(*a, **k)
        if not fired:
            fired["sent"] = A.approve(card.token, tiff["inst"], store=st, now=ct(2026, 9, 22, 15, 1),
                                      ghl=tiff["ghl"])
        return card

    monkeypatch.setattr(app_mod.approval_mod, "create_approval", create_then_approve)
    r1b = _reply(tiff["deps"], "o-2", "Thanks - what would you need from us to start?", "2026-09-22T20:00:00Z",
                 ct(2026, 9, 22, 15, 0))
    monkeypatch.setattr(app_mod.approval_mod, "create_approval", real_create)
    assert fired["sent"]["ok"] and fired["sent"]["cadence"]["armed"] is True
    raw = st.get(key)
    cad = raw["cadence"]
    assert cad["armed_for_email_id"] == "o-2" and cad["stopped_reason"] is None and cad["day"] == 1
    assert cad["next_send_at"] == ct(2026, 9, 23, 10, 0).isoformat()
    assert A.load(r1b["approval_token"], st).status == "sent" and raw["processed_email_ids"] == ["o-1", "o-2"]
    d2, _ = _ticks(st, [ct(2026, 9, 23, 10, 0)], LADDER_SLOTS, [])
    assert len(d2.sent) == 1                                          # D2, on top of an answered reply


# ============================================================ Resume race
def _resume_world(tmp_env, monkeypatch, name):
    store = JsonFileStore(tmp_env / name)
    pings = []
    state = _r6_stopped(store, monkeypatch, pings)
    store.set(state.key, state.to_store())
    _email_leg(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=TIFF)
    deps = app_mod.configure(store=store, ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 22, 14, 0))
    return store, state, deps, pings[-1][1]["click"][len("https://engine.test"):]


def test_resume_race_the_reply_landing_while_resume_holds_its_copy_survives_and_nothing_is_sent(tmp_env,
                                                                                                monkeypatch):
    store, state, deps, path = _resume_world(tmp_env, monkeypatch, "race.json")
    real_resume = cadence.resume_after_recipient_hold
    box = {}

    def racing_resume(st_obj, now):
        # the webhook worker processes the reply while this handler holds its copy
        box["r2"] = _reply(deps, "t-race", "Quick question before we talk: do you work with janitorial companies "
                                           "in NJ?", "2026-09-22T18:59:00Z", ct(2026, 9, 22, 13, 59),
                           campaign_id=state.campaign_id)
        return real_resume(st_obj, now)

    monkeypatch.setattr(cadence, "resume_after_recipient_hold", racing_resume)
    try:
        page = TestClient(app_mod.app).post(path)
    finally:
        app_mod.configure()
    monkeypatch.setattr(cadence, "resume_after_recipient_hold", real_resume)
    assert page.status_code == 200 and "Resumed" in page.text and "r2" in box
    raw = store.get(state.key)
    card_b = box["r2"]["approval_token"]
    assert raw["last_inbound_at"] == "2026-09-22T18:59:00+00:00"          # not back to None
    assert _listed(raw, card_b) and raw["processed_email_ids"] == ["t-race"]
    assert [h for h in raw["history"] if h.get("event") == "inbound" and h.get("email_id") == "t-race"]
    pings = []
    d, results = _ticks(store, [ct(2026, 9, 22, 15, 0), ct(2026, 9, 22, 15, 31), ct(2026, 9, 22, 16, 0)], D1_FREE,
                        pings)
    assert d.sent == [] and _veto_or_d1_pings(pings) == []
    # stopped for the reply behind card B, which waits on Lorenzo
    assert results[0] == [("stopped", "inbound_reply", None)]
    cad = store.get(state.key)["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert A.load(card_b, store).status == "pending"


def test_resume_tapped_after_the_reply_sends_nothing_while_its_card_waits(tmp_env, monkeypatch):
    store, state, deps, path = _resume_world(tmp_env, monkeypatch, "after.json")
    try:
        r2 = _reply(deps, "t-new", "Quick question before we talk: do you work with janitorial companies in NJ?",
                    "2026-09-22T18:30:00Z", ct(2026, 9, 22, 13, 30), campaign_id=state.campaign_id)
        page = TestClient(app_mod.app).post(path)
    finally:
        app_mod.configure()
    assert page.status_code == 200
    d, results = _ticks(store, [ct(2026, 9, 22, 15, 0), ct(2026, 9, 22, 16, 0)], D1_FREE, [])
    assert d.sent == [] and results[0] == [("stopped", "inbound_reply", None)]
    assert store.get(state.key)["cadence"]["stopped_reason"] == "inbound_reply"
    assert A.load(r2["approval_token"], store).status == "pending"


# ================================================== the other listed writers
def test_a_d6_tap_racing_a_reply_keeps_the_reply_its_card_and_its_stop(tmp_env, monkeypatch):
    """app._cadence_decision wrote back the copy it read before the tap."""
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    notify.reset_for_tests()
    _go_live(monkeypatch)
    _email_leg(monkeypatch)
    store = JsonFileStore(tmp_env / "d6.json")
    state = _d1_state()
    state.cadence["day"] = 5                                          # D6 due Tue 10:00
    store.set(state.key, state.to_store())
    deps = app_mod.configure(store=store, ghl=Recorder(), instantly=FakeInstantly(sender=TIFF),
                             clock=lambda: ct(2026, 9, 22, 9, 0))
    token = cadence.make_decision_token("approve", state, ct(2026, 9, 22, 9, 0))
    real = cadence.record_invite_decision
    box = {}

    def reply_then_record(st_, state_, decision, now, token=None):
        if not box:
            box["r2"] = _reply(deps, "t-d6", "Quick question: can my business partner join the call too?",
                               "2026-09-22T13:55:00Z", ct(2026, 9, 22, 8, 55), campaign_id=state.campaign_id)
        return real(st_, state_, decision, now, token=token)

    monkeypatch.setattr(cadence, "record_invite_decision", reply_then_record)
    try:
        page = TestClient(app_mod.app).post("/cadence/approve/%s/%s?%s" % (state.campaign_id, quote(TIFF),
                                                                            urlencode({"t": token})))
    finally:
        app_mod.configure()
    monkeypatch.setattr(cadence, "record_invite_decision", real)
    assert page.status_code == 200 and "r2" in box
    raw = store.get(state.key)
    assert raw["cadence"]["stopped_reason"] == "inbound_reply" and raw["cadence"]["needs_fresh_draft"] is True
    assert raw["last_inbound_at"] == "2026-09-22T13:55:00+00:00"
    assert _listed(raw, box["r2"]["approval_token"]) and raw["processed_email_ids"] == ["t-d6"]
    assert store.get(cadence.approval_key(state, "d6"))["decision"] == "approve"    # the tap itself landed
    d, _ = _ticks(store, [ct(2026, 9, 22, 10, 0), ct(2026, 9, 23, 10, 0)], LADDER_SLOTS, [])
    assert d.sent == []


def test_a_veto_racing_a_reply_keeps_the_newer_card_and_the_lead_is_not_lost(tiff, monkeypatch):
    """approval.veto wrote back the copy it read before the reply landed."""
    st = tiff["store"]
    r1 = _first_card(tiff, monkeypatch, email_id="v-1")
    real_owns = A.owns_booking
    box = {}

    def reply_then_owns(approval, state):
        if not box:
            box["r2"] = None                                          # reply 2's own pipeline asks owns_booking too
            box["r2"] = _reply(tiff["deps"], "v-2", "Actually, one more question: do you work in New Jersey?",
                               "2026-09-21T20:05:00Z", ct(2026, 9, 21, 15, 5))
        return real_owns(approval, state)

    monkeypatch.setattr(A, "owns_booking", reply_then_owns)
    out = A.veto(r1["approval_token"], store=st, now=ct(2026, 9, 21, 15, 5), ghl=tiff["ghl"],
                 instantly=tiff["inst"])
    monkeypatch.setattr(A, "owns_booking", real_owns)
    assert out["ok"] and box.get("r2")
    raw = st.get(r1["state_key"])
    card_b = box["r2"]["approval_token"]
    assert _listed(raw, card_b) and raw["processed_email_ids"] == ["v-1", "v-2"]
    assert raw["last_inbound_at"] == "2026-09-21T20:05:00+00:00"
    assert [h for h in raw["history"] if h.get("event") == "vetoed"]
    # the lead is not lost: answering card B arms the ladder
    sent = A.approve(card_b, tiff["inst"], store=st, now=ct(2026, 9, 21, 15, 30), ghl=tiff["ghl"])
    assert sent["ok"] and sent["cadence"]["armed"] is True


# ============================================================== the pieces
def _card(approval_id, email_id, status="pending", created=None):
    created = created or ct(2026, 9, 21, 14, 0)
    return Approval(token="%s.sig" % approval_id, state_key="lead:c1:x@y.com", lead_email="x@y.com",
                    email_id=email_id, draft=Draft(subject="Re: x", body_text="Hey X,\n\nx\n\nLorenzo"),
                    status=status, created_at=created.isoformat(),
                    expires_at=(created + timedelta(hours=A.TTL_HOURS)).isoformat())


def test_arm_refusal_reads_the_row_and_the_open_cards_it_was_given():
    card = _card("a1", "e1")
    row = {"processed_email_ids": ["e0", "e1"], "approvals": ["a0.sig", "a1.sig"]}
    assert A.arm_refusal(row, card, {"a0": False}) is None
    assert A.arm_refusal(dict(row, processed_email_ids=["e0", "e1", "e2"]), card, {"a0": False}) == "newer_inbound:e2"
    assert A.arm_refusal(row, card, {"a0": True}) == "open_card:a0"
    # listed on the row after the statuses were read: a card that new is pending
    assert A.arm_refusal(dict(row, approvals=["a0.sig", "a1.sig", "b2.sig"]), card, {"a0": False}) == "open_card:b2"
    # the card's own pipeline has not written yet: nothing on the row is newer
    assert A.arm_refusal({"processed_email_ids": ["e0"], "approvals": ["a0.sig"]}, card, {"a0": False}) is None
    # a machine's answer after the source is not the lead writing again...
    robots = dict(row, processed_email_ids=["e0", "e1", "e2", "e3"],
                  history=[{"event": "inbound", "email_id": "e1", "label": "positive_question"},
                           {"event": "inbound", "email_id": "e2", "label": "ooo"},
                           {"event": "inbound", "email_id": "e3", "label": "auto_reply_unmonitored"}])
    assert A.arm_refusal(robots, card, {"a0": False}) is None
    # ...the lead's own reply after it is, and so is an inbound no history entry labels
    human = dict(robots, processed_email_ids=robots["processed_email_ids"] + ["e4"],
                 history=robots["history"] + [{"event": "inbound", "email_id": "e4", "label": "negative_notnow"}])
    assert A.arm_refusal(human, card, {"a0": False}) == "newer_inbound:e4"
    assert A.arm_refusal(dict(robots, history=robots["history"][:2]), card, {"a0": False}) == "newer_inbound:e3"


def test_open_other_cards_counts_only_live_pending_or_queued_cards(tmp_env):
    st = JsonFileStore(tmp_env / "cards.json")
    now = ct(2026, 9, 21, 15, 0)
    rows = {"a0": _card("a0", "e0", status="sent"), "b1": _card("b1", "e2"),
            "q2": _card("q2", "e3", status="approved_queued"),
            "x3": _card("x3", "e4", created=now - timedelta(hours=A.TTL_HOURS + 1))}      # pending, past its TTL
    for approval_id, card in rows.items():
        st.set(A.APPROVAL_PREFIX + approval_id, card.model_dump(mode="json"))
    own = _card("a1", "e1")
    row = {"approvals": ["a0.sig", "a1.sig", "b1.sig", "q2.sig", "x3.sig", "gone.sig"]}
    assert A._open_other_cards(st, own, row, now) == {"a0": False, "b1": True, "q2": True, "x3": False,
                                                      "gone": False}


def test_merge_combines_the_append_only_lists_and_never_moves_last_inbound_back():
    base = {"approvals": ["a.1"], "processed_email_ids": ["e1"], "processed_keys": ["k1"],
            "history": [{"event": "inbound", "email_id": "e1"}], "offered_slots": ["s1"],
            "drafts": [{"body_text": "d1"}], "last_inbound_at": "2026-09-21T19:00:00+00:00",
            "status": "draft_pending_approval", "cadence": {}}
    # a stale writer (a send) added its own entries to the copy it read...
    mine = dict(base, history=base["history"] + [{"event": "reply_sent", "approval": "a"}],
                offered_slots=["s1", "s2"], last_outbound_at="2026-09-21T15:01:00-05:00")
    # ...while reply 2 was processed
    current = dict(base, approvals=["a.1", "b.2"], processed_email_ids=["e1", "e2"], processed_keys=["k1", "k2"],
                   history=base["history"] + [{"event": "inbound", "email_id": "e2"}],
                   drafts=base["drafts"] + [{"body_text": "d2"}], last_inbound_at="2026-09-21T20:01:00+00:00")
    out = A.merge_stale_write(base, mine, current)
    assert out["approvals"] == ["a.1", "b.2"] and out["processed_email_ids"] == ["e1", "e2"]
    assert out["processed_keys"] == ["k1", "k2"] and out["drafts"] == current["drafts"]
    assert out["history"] == current["history"] + [{"event": "reply_sent", "approval": "a"}]
    assert out["offered_slots"] == ["s1", "s2"] and out["last_outbound_at"] == "2026-09-21T15:01:00-05:00"
    assert out["last_inbound_at"] == "2026-09-21T20:01:00+00:00"
    # both changed a list: combined, nothing dropped
    assert A.merge_stale_write(base, dict(base, approvals=["a.1", "c.3"]), current)["approvals"] == \
        ["a.1", "b.2", "c.3"]
    # an older inbound time (a stale copy, a late email) never moves it back...
    older = dict(current, last_inbound_at="2026-09-21T18:00:00+00:00")
    assert A.merge_stale_write(current, older, current)["last_inbound_at"] == "2026-09-21T20:01:00+00:00"
    assert A.merge_stale_write(base, dict(base, last_inbound_at=None), current)["last_inbound_at"] == \
        "2026-09-21T20:01:00+00:00"
    # ...and a newer one lands
    newer = dict(current, last_inbound_at="2026-09-21T21:00:00+00:00")
    assert A.merge_stale_write(current, newer, current)["last_inbound_at"] == "2026-09-21T21:00:00+00:00"


def test_save_lead_state_moves_the_stop_as_a_group_and_runs_finish_on_the_merged_row(tmp_env):
    store = JsonFileStore(tmp_env / "group.json")
    state = _d1_state()
    cadence.stop(state, "recipient_unconfirmed", ct(2026, 9, 22, 12, 0))
    store.set(state.key, state.to_store())
    base = store.get(state.key)
    resumed = LeadState.from_store(base)
    cadence.resume_after_recipient_hold(resumed, ct(2026, 9, 22, 14, 0))
    # a reply's stop lands before the Resume writes
    store.mutate(state.key, lambda raw: dict(raw, last_inbound_at="2026-09-22T18:59:00+00:00",
                                             cadence=dict(raw["cadence"], stopped_reason="inbound_reply",
                                                          stopped_at=ct(2026, 9, 22, 13, 59).isoformat(),
                                                          needs_fresh_draft=True)))
    seen = []
    A.save_lead_state(store, resumed, base, finish=lambda row: seen.append(dict(row)) or row)
    raw = store.get(state.key)
    cad = raw["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert cad["stopped_at"] == ct(2026, 9, 22, 13, 59).isoformat()
    assert cad["resumed_after_recipient_hold_at"] == ct(2026, 9, 22, 14, 0).isoformat()   # its own change landed
    assert raw["last_inbound_at"] == "2026-09-22T18:59:00+00:00"
    assert len(seen) == 1 and seen[0]["cadence"]["stopped_reason"] == "inbound_reply"
    # a finish that raises never loses the merged write
    other = LeadState.from_store(store.get(state.key))
    other.status = "positive_question"

    def broken(row):
        raise RuntimeError("boom")

    A.save_lead_state(store, other, store.get(state.key), finish=broken)
    assert store.get(state.key)["status"] == "positive_question"


# ============================= round-4 probe: the Keep / Release choice form
def test_the_keep_release_choice_cannot_be_forged_or_replayed(env, monkeypatch):
    """scratchpad/review-s/test_r4_choice_form.py, as assertions."""
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    app_mod.configure(store=st, ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 21, 16, 10))
    c = TestClient(app_mod.app)
    t0 = r["approval_token"]
    link = A.load(t0, st).draft.booking_link
    try:
        assert "booking_choice" in c.get("/edit/%s" % t0).text
        bogus = c.post("/edit/%s" % t0, data={"body": "Hey Sopio,\n\nFri 1:00pm CT? %s\n\nLorenzo" % link,
                                              "booking_choice": "maybe"})
        forged = c.post("/edit/%s" % (t0.split(".")[0] + ".deadbeefdeadbeefdeadbeefdeadbeef"),
                        data={"body": "x %s" % link, "booking_choice": "keep"})
        assert bogus.status_code == 400 and forged.status_code == 400
        # Release, saved at 20:00 so it queues instead of sending
        app_mod.configure(store=st, ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 21, 20, 0))
        c2 = TestClient(app_mod.app)
        rel = c2.post("/edit/%s" % t0, json={"body": "Hey Sopio,\n\nCould you do Fri 1:00pm CT instead? %s\n\n"
                                                     "Lorenzo" % link, "booking_choice": " RELEASE "})
        assert rel.status_code == 200
        card = A._approval_row(st, t0.split(".")[0])
        assert card.status == "approved_queued"
        assert st.get(A.BOOKING_CHOICE_PREFIX + t0.split(".")[0])["choice"] == "release"
        # the original token, replayed with Keep and other words, is dead
        replay = c2.post("/edit/%s" % t0, data={"body": "Hey Sopio,\n\nLocked in Thu 3:00pm CT. %s\n\nLorenzo" % link,
                                                "booking_choice": "keep"})
        assert replay.status_code == 400
    finally:
        app_mod.configure()
    assert inst.sent == [] and ghl.calls == [] and show_rate.is_held(st, "appt-live-9")
