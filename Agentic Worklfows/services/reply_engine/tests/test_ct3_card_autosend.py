"""CT3 piece B: the card send path (approval.py, poller.py). Shadow only,
zero HTTP, no LLM.

A reply whose draft is exactly an approved template is sent with no tap,
through the same path as Approve (_approve_loaded(actor="template"), then
send_approved with every check it runs, and the gate run again inside it).
Anything else is an ordinary approval card, with a "Not auto-sent: <reason>"
line when the gate refused it. A first reply is never auto-sent, whatever the
gate says (test_first_reply_draft_only.py), so the auto-send path is driven
here with a counter-proposal template (TID). Plus the three S-rest round 6 prerequisites
(flags 18-20): guarded supersede and orphan-owner writes, the time-mark race,
and the Book-as-asked undo that never resets the opportunity or interest
under another call or an opt-out.

Every test builds its own gate environment (template_fixtures.
make_template_env: a tmp approvals file and a tmp parity reference) and
checks the real config files are unchanged. Every lead is an example.com
address; every client is an in-process fake.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from shared import job_log, notify, settings, slots
from shared.paths import BASE_DIR
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import booking as B
from services.reply_engine import draft as D
from services.reply_engine import poller as P
from services.reply_engine import template_gate as gate
from services.reply_engine.models import Classification, Draft, LeadState, ReplyEvent
from services.reply_engine.tests import template_fixtures as tf

CT = pytz.timezone("America/Chicago")
REAL_APPROVALS = BASE_DIR / "config" / "approved_templates.json"
REAL_REFERENCE = BASE_DIR / "config" / "template_catalogue_hashes.json"
CAMPAIGN = "camp-ct3-1"
LEAD = "owner@example.com"
FIRST = "Jordan"
COMPANY = "Brightline Test Co"
EACCOUNT = "lorenzo@advero-example.com"
THREAD = "thread-ct3-1"
LINK = "https://example.invalid/book"
OFFER = sorted(D.PRICING)[0]
# The auto-sendable template these tests drive the card machinery with: a
# counter-proposal (kind booking, two offered times). First replies are never
# auto-sent (approval.FIRST_REPLY_LOCK_REASON, Lorenzo's rule of 2026-09-23):
# FIRST_TID is the first reply the lock tests below use.
TID = "booking.counter.window_no_fit"
FIRST_TID = "first_reply.%s.default.full" % OFFER


def ct(*args):
    return CT.localize(datetime(*args))


NOW = ct(2030, 1, 7, 10, 0)        # Monday 10:00 CT: inside the send window
NIGHT = ct(2030, 1, 7, 20, 0)      # Monday 20:00 CT: queued for Tuesday 07:00
FLUSH = ct(2030, 1, 8, 7, 5)       # Tuesday 07:05 CT


def _bytes(p):
    return p.read_bytes() if p.exists() else None


class FakeInstantly(object):
    def __init__(self):
        self.sent = []
        self.interest = []

    def get_email(self, email_id):
        return {"id": email_id, "from_address_email": LEAD}

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.sent.append({"reply_to_uuid": reply_to_uuid, "to": to, "subject": subject, "body": body})
        # What the guarded client answers in shadow: a would_do, nothing sent.
        return settings.guard_write("instantly", "reply_to_email", {"reply_to_uuid": reply_to_uuid, "to": to})

    def update_interest_status(self, lead_email, campaign_id, value):
        self.interest.append((lead_email, campaign_id, value))
        return {"shadow": True}


@pytest.fixture
def world(tmp_env, monkeypatch):
    before = (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE))
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.setattr(settings, "BOOKING_URL", LINK)
    notify.reset_for_tests()
    tpl = tf.make_template_env(monkeypatch, tmp_env)
    rows = []
    real = job_log.log_run
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: rows.append((job, status, details))
                        or real(job, status, details))
    store = JsonFileStore(tmp_env / "ct3_cards.json")
    yield {"store": store, "inst": FakeInstantly(), "tpl": tpl, "rows": rows, "tmp": tmp_env}
    gate.clear_cache()
    assert (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE)) == before, "a test wrote a real config file"


def _cls(label="positive_interested", confidence=0.95, method="llm"):
    return Classification(label=label, confidence=confidence, method=method)


def _event(email_id="e-1", now=NOW):
    return ReplyEvent(email_id=email_id, thread_id=THREAD, campaign_id=CAMPAIGN, campaign_key=OFFER,
                      eaccount=EACCOUNT, lead_email=LEAD, first_name=FIRST, company=COMPANY,
                      subject="Quick question", text="Sounds good, tell me more.", received_at=now)


def _counter_draft(ev, cls, state, now):
    """The counter-proposal the pipeline writes when nothing inside the
    lead's window is open (app._reply_draft's counter branch), offering the
    two times a first reply would, and its gate bindings."""
    d = D.build_draft(ev, cls, now=now, booking_link=LINK, use_llm=False, already_offered=[], busy_blocks=[])
    times = [slots.parse_iso(iso) for iso in d.offered_slots[:2]]
    match = B.BookingMatch(slot=None, status=B.WINDOW_NO_FIT, counter_slots=times)
    body = B.counter_proposal_text(match, state)
    # no booking link on a counter-proposal (Lorenzo, 2026-09-23; app.py 2c8d34f)
    counter = Draft(subject=D.reply_subject(ev.subject), body_text=body,
                    offered_slots=[t.isoformat() for t in times], booking_link=None, model="template",
                    label=cls.label, rationale="counter-proposal (window_no_fit)",
                    problems=D.validate_draft(body, booking_link=None, campaign_key=OFFER,
                                              allow_terms=D.lead_terms(ev, state)),
                    template_id=B.counter_template_id(match))
    assert counter.template_id == TID
    return counter, B.counter_bindings(match, state)


def _card(world, now=NOW, approve=True, email_id="e-1", cls=None, verdict=True):
    """The pipeline's steps for one positive reply, piece B's half: a
    template draft (the counter-proposal, TID), stamped, its verdict, the
    card (create_approval(auto=)), and the lead row saved as the pipeline
    saves it."""
    st = world["store"]
    if approve:
        world["tpl"].approve_ids(TID)
    cls = cls or _cls()
    ev = _event(email_id, now)
    raw = st.get("lead:%s:%s" % (CAMPAIGN, LEAD))
    state = LeadState.from_store(raw, ev)
    state.classification = cls
    d, bindings = _counter_draft(ev, cls, state, now)
    gate.stamp(d, TID)
    v = gate.draft_verdict(d, kind="booking", campaign_key=OFFER, allow_terms=D.lead_terms(ev, state),
                           classification=cls, bindings=bindings)
    card = A.create_approval(state, d, ev, store=st, now=now, campaign_key=OFFER, auto=v if verdict else None)
    state.processed_email_ids.append(email_id)
    state.history.append({"at": now.isoformat(), "event": "inbound", "email_id": email_id,
                          "label": cls.label, "received_at": now.isoformat()})
    st.set(state.key, state.to_store())
    return card, v


def _stored(world, card):
    return A._approval_row(world["store"], A._approval_id(card))


def _pushes(fragment="Reply to approve"):
    return [n for n in notify.sent_in_test if n["title"].startswith(fragment)]


def _rows(world, status):
    return [r[2] for r in world["rows"] if r[1] == status]


def _fyi_entries(world):
    return world["store"].get(gate.FYI_KEY) or []


# ======================================================= the auto-send path
def test_an_approved_template_reply_in_shadow_is_one_would_do_no_push_and_one_fyi_entry(world):
    card, v = _card(world)
    assert (v.allowed, v.reason) == (True, "ok"), v.detail
    stored = _stored(world, card)
    assert stored.status == "pending" and stored.notify_result["deferred"] == A.DEFERRED_AUTO_SEND
    assert stored.auto_send["allowed"] is True and stored.auto_send["template_id"] == TID
    assert stored.auto_send["classification"] == {"label": "positive_interested", "confidence": 0.95, "method": "llm"}
    assert _pushes() == []                                   # nothing pushed at create
    assert [r["auto"] for r in _rows(world, "created")] == [True]

    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is True and out["status"] == "sent" and out["shadow"] is True and out["auto"] is True
    assert len(world["inst"].sent) == 1
    assert [x for x in job_log.read_shadow_log() if x["action"] == "reply_to_email"] != []
    assert world["inst"].sent[0]["body"] == card.draft.body_text and world["inst"].sent[0]["to"] == LEAD
    stored = _stored(world, card)
    assert stored.status == "sent" and stored.approved_by == "template"
    assert _pushes() == []                                   # still no card push
    assert [(e["template_id"], e["status"], e["approval_id"]) for e in _fyi_entries(world)] == [
        (TID, "sent", A._approval_id(card))]
    assert A.card_context(world["store"], A._approval_id(card))["approved_by"] == "template"
    assert [r["template_id"] for r in _rows(world, "template_auto_sent")] == [TID]
    # a second call refuses: the card is no longer waiting on an auto-send
    again = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert again["ok"] is False and len(world["inst"].sent) == 1


@pytest.mark.parametrize("how", ["unapproved", "kill_switch", "changed_since_approval"])
def test_an_unapproved_template_is_an_ordinary_card_with_a_not_auto_sent_line(world, how):
    if how == "unapproved":
        card, v = _card(world, approve=False)
    else:
        world["tpl"].approve_ids(TID)
        if how == "kill_switch":
            world["tpl"].kill_switch(True)
        else:
            # the approvals sha edited: the template changed since approval
            path = world["tpl"].approvals_path
            data = __import__("json").loads(path.read_text())
            data["approvals"][TID]["sha256"] = "0" * 64
            path.write_text(__import__("json").dumps(data))
            gate.clear_cache()
        card, v = _card(world, approve=False)
    assert v.allowed is False and v.reason == how
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT[how])
    stored = _stored(world, card)
    assert stored.status == "pending" and "deferred" not in stored.notify_result
    assert stored.auto_send["allowed"] is False and stored.auto_send["reason"] == how
    assert world["inst"].sent == [] and _fyi_entries(world) == []
    assert [r["auto"] for r in _rows(world, "created")] == [False]
    # the auto path refuses a card that was pushed
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and world["inst"].sent == [] and len(_pushes()) == 1


def test_a_card_raised_without_a_verdict_is_pushed_as_before(world):
    card, _ = _card(world, verdict=False)
    pushes = _pushes()
    assert len(pushes) == 1 and not pushes[0]["message"].startswith("Not auto-sent")
    assert _stored(world, card).auto_send is None


def test_a_verdict_for_another_template_is_never_honoured(world):
    card, v = _card(world)
    wrong = gate.Verdict(True, "ok", "booking.counter.weekend", [], {})
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=wrong)
    assert out["ok"] is False and out["reason"] == "the template check was for another draft."
    assert world["inst"].sent == []
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith("Not auto-sent: the template check was for another")


def test_outside_sending_hours_the_card_is_queued_and_sent_at_the_flush(world):
    card, v = _card(world, now=NIGHT)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    assert out["ok"] is True and out["status"] == "approved_queued" and world["inst"].sent == []
    stored = _stored(world, card)
    assert stored.approved_by == "template" and stored.send_after == ct(2030, 1, 8, 7, 0).isoformat()
    assert [e["status"] for e in _fyi_entries(world)] == ["approved_queued"]
    flushed = A.flush_queued(world["inst"], store=world["store"], now=FLUSH)
    assert [f["status"] for f in flushed] == ["sent"] and len(world["inst"].sent) == 1
    assert _pushes() == []
    assert [e["status"] for e in _fyi_entries(world)] == ["approved_queued", "sent"]


@pytest.mark.parametrize("change", ["revoke", "kill_switch_env", "kill_switch_file"])
def test_a_revoke_between_queueing_and_the_flush_turns_the_card_back_to_pending_and_pushes_it(world, change):
    card, v = _card(world, now=NIGHT)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    assert _stored(world, card).status == "approved_queued"
    if change == "revoke":
        world["tpl"].revoke_ids(TID)
        reason = "unapproved"
    elif change == "kill_switch_env":
        world["tpl"].kill_switch(True, via="env")
        reason = "kill_switch"
    else:
        world["tpl"].kill_switch(True)
        reason = "kill_switch"
    flushed = A.flush_queued(world["inst"], store=world["store"], now=FLUSH)
    assert [(f["status"], f["reason"]) for f in flushed] == [("pending", reason)]
    assert world["inst"].sent == []
    stored = _stored(world, card)
    assert stored.status == "pending" and stored.approved_by is None and stored.send_after is None
    assert stored.decided_at is None and stored.auto_send["reason"] == reason
    assert "deferred" not in stored.notify_result
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT[reason])
    assert [r["reason"] for r in _rows(world, "template_auto_send_refused")] == [reason]
    # the next flush does nothing more; Lorenzo's own Approve sends it
    assert A.flush_queued(world["inst"], store=world["store"], now=FLUSH + timedelta(minutes=5)) == []
    assert len(_pushes()) == 1
    sent = A.approve(stored.token, world["inst"], store=world["store"], now=FLUSH + timedelta(minutes=6))
    assert sent["ok"] is True and sent["status"] == "sent" and _stored(world, card).approved_by == "lorenzo"


def test_a_hash_change_before_the_send_is_stale_render_and_a_card(world, monkeypatch):
    """A redeploy that changes the template text between the verdict and the
    send: the stamped hash no longer matches (the re-check in send_approved)."""
    card, v = _card(world, now=NIGHT)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    real = gate._hash_of

    def moved(index, template_id):
        return "f" * 64 if template_id == TID else real(index, template_id)
    monkeypatch.setattr(gate, "_hash_of", moved)
    flushed = A.flush_queued(world["inst"], store=world["store"], now=FLUSH)
    assert flushed[0]["status"] == "pending" and flushed[0]["reason"] in ("stale_render", "changed_since_approval")
    assert world["inst"].sent == [] and len(_pushes()) == 1


def test_the_gate_runs_again_inside_send_approved_even_in_the_sending_window(world, monkeypatch):
    """Flag 5: between the auto-approve and the Instantly call the gate is
    judged again on the exact subject and body the send uses."""
    card, v = _card(world)
    seen = []
    real = gate.draft_verdict

    def spy(d, **kw):
        seen.append((d.subject, d.body_text, kw.get("kind"), kw.get("requested")))
        return real(d, **kw)
    monkeypatch.setattr(gate, "draft_verdict", spy)
    world["tpl"].revoke_ids(TID)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and out["status"] == "pending" and out["reason"] == "unapproved"
    assert seen == [(card.draft.subject, card.draft.body_text, "booking", None)]
    assert world["inst"].sent == [] and len(_pushes()) == 1


def test_an_allowed_verdict_never_bypasses_the_opt_out_marker(world):
    """Flag 6: the lead's sticky opt-out marker on the row holds the card
    (lead_reply_hold), with its own HELD alert; the card itself is not
    pushed as a card to answer."""
    card, v = _card(world)
    st = world["store"]
    row = st.get(card.state_key)
    row["opt_out"] = {"label": "unsubscribe", "email_id": "e-2", "received_at": NOW.isoformat(),
                      "set_at": NOW.isoformat()}
    st.set(card.state_key, row)
    out = A.auto_send_approved(card, world["inst"], store=st, now=NOW, verdict=v)
    assert out["ok"] is False and out["status"] == "blocked" and out["held"] is True
    assert world["inst"].sent == [] and _fyi_entries(world) == []
    assert _pushes() == []                                          # not a card to answer
    assert [n["title"] for n in notify.sent_in_test if "HELD" in n["title"] or "held" in n["title"].lower()]
    assert _rows(world, "blocked_lead_replied")


def test_an_allowed_verdict_never_bypasses_a_problem_on_the_draft(world):
    """A time the draft offers that another lead's card took meanwhile: the
    card is raised with a problem, so it is never deferred."""
    st = world["store"]
    world["tpl"].approve_ids(TID)
    ev = _event()
    d = D.build_draft(ev, _cls(), now=NOW, booking_link=LINK, use_llm=False, already_offered=[], busy_blocks=[])
    A.claim_slots(st, "other@example.com", list(d.offered_slots), NOW, fields={"approval": "other"})
    card, v = _card(world)
    assert v.allowed is True
    stored = _stored(world, card)
    assert stored.draft.problems and "deferred" not in stored.notify_result
    assert _pushes()[0]["message"].startswith("Not auto-sent: the draft has a problem to fix first")


def test_edit_clears_the_template_fields_and_the_auto_path_refuses_it(world):
    card, v = _card(world, approve=False)        # a pushed card Lorenzo edits
    st = world["store"]
    raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    raw["approved_by"] = "template"                # as if a template path had touched it
    st.set(A.APPROVAL_PREFIX + A._approval_id(card), raw)
    body = card.draft.body_text.replace("Hey %s," % FIRST, "Hi %s," % FIRST)
    out = A.edit(card.token, body, store=st, now=NOW)
    assert out["ok"] is True, out
    stored = _stored(world, card)
    assert stored.draft.model == "edited" and stored.draft.template_id is None
    assert stored.draft.template_hash is None and stored.draft.template_parts == {}
    assert stored.approved_by is None and stored.auto_send is None
    # the auto path refuses it even with an allowed verdict for the template
    world["tpl"].approve_ids(TID)
    raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    raw["notify_result"] = dict(raw["notify_result"], deferred=A.DEFERRED_AUTO_SEND)
    st.set(A.APPROVAL_PREFIX + A._approval_id(card), raw)
    fresh = A.load(out["token"], st)
    refused = A.auto_send_approved(fresh, world["inst"], store=st, now=NOW, verdict=v)
    assert refused["ok"] is False and world["inst"].sent == []
    # and the send-time re-check refuses an edited body marked "template"
    fresh.approved_by = "template"
    verdict = A._template_verdict(fresh, st.get(fresh.state_key))
    assert verdict.allowed is False and verdict.reason in ("not_template_render", "no_template")


def test_retry_and_book_as_asked_go_through_approve_as_lorenzo(world):
    card, v = _card(world, approve=False)
    out = A.approve(card.token, world["inst"], store=world["store"], now=NOW)
    assert out["status"] == "sent" and _stored(world, card).approved_by == "lorenzo"
    assert A.card_context(world["store"], A._approval_id(card))["approved_by"] == "lorenzo"
    # retry clears the approval: the next Approve records who
    st = world["store"]
    raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    st.set(A.APPROVAL_PREFIX + A._approval_id(card), dict(raw, status="stale_slots", approved_by="template"))
    back = A.retry(card.token, store=st, now=NOW)
    assert back["ok"] is True and _stored(world, card).approved_by is None


def test_every_reason_code_has_a_plain_sentence_with_no_lead_data(world):
    """REASON_TEXT covers every gate reason and the pipeline's cancel_pending;
    each is one sentence, with no placeholder, address or link in it; an
    unknown code is shown as itself; the stored record keeps the code."""
    assert set(gate.REASONS) <= set(A.REASON_TEXT) and "cancel_pending" in A.REASON_TEXT
    assert A.REASON_TEXT["cancel_pending"] == ("the lead's previous call is still being cancelled in GHL; check "
                                               "the calendar before sending.")
    for code, text in A.REASON_TEXT.items():
        assert text.endswith(".") and text[:1].islower(), code
        for bad in ("{", "}", "@", "http", "%s", LEAD, FIRST, COMPANY):
            assert bad not in text, (code, bad)
    assert A.reason_text("something_new") == "something_new"
    card, v = _card(world, approve=False)
    assert _pushes()[0]["message"].startswith("Not auto-sent: its template is not approved yet")
    assert A.REASON_TEXT["unapproved"] == 'its template is not approved yet; approve it in the emails doc, then tell Claude "done".'
    assert A.REASON_TEXT["changed_since_approval"] == ('its template changed since you approved it; review it and '
                                                       'approve it again in the emails doc, then tell Claude "done".')
    assert A.REASON_TEXT["first_reply_draft_only"] == "first replies are drafts you send yourself from the thread."
    assert "approve_templates" not in "".join(A.REASON_TEXT.values())
    assert _stored(world, card).auto_send["reason"] == "unapproved"
    cancel = gate.Verdict(False, "cancel_pending", TID, [TID], {})
    note = A._auto_decision(cancel, card.draft)
    assert note == (False, "Not auto-sent: " + A.REASON_TEXT["cancel_pending"])


# ============================================================ crash window
def test_a_crash_between_create_and_auto_send_is_pushed_exactly_once_by_the_orphan_sweep(world):
    card, v = _card(world)
    st = world["store"]
    # younger than min_age: left to the pipeline still running it
    assert A.push_orphaned_deferred(st, now=NOW + timedelta(minutes=1)) == []
    assert _pushes() == []
    later = NOW + timedelta(minutes=3)
    swept = A.push_orphaned_deferred(st, now=later)
    assert [s["approval"] for s in swept] == [A._approval_id(card)]
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith(A.ORPHAN_NOTE + "\n")
    stored = _stored(world, card)
    assert "deferred" not in stored.notify_result and stored.notify_result[A.DEFERRED_PUSHED_KEY]["note"] == A.ORPHAN_NOTE
    # never twice, and the auto-send that finally runs refuses a pushed card
    assert A.push_orphaned_deferred(st, now=later + timedelta(minutes=5)) == []
    out = A.auto_send_approved(card, world["inst"], store=st, now=later, verdict=v)
    assert out["ok"] is False and world["inst"].sent == [] and len(_pushes()) == 1
    assert len(_rows(world, "template_auto_send_orphan_pushed")) == 1


def test_two_sweeps_racing_push_the_card_once(world, monkeypatch):
    card, _ = _card(world)
    st = world["store"]
    later = NOW + timedelta(minutes=3)
    real = A._claim_deferred_push
    box = {}

    def racing(store, approval_id, ts, note, orphan_only=False):
        if not box:
            box["started"] = True
            box["other"] = A.push_orphaned_deferred(st, now=later)
        return real(store, approval_id, ts, note, orphan_only=orphan_only)
    monkeypatch.setattr(A, "_claim_deferred_push", racing)
    mine = A.push_orphaned_deferred(st, now=later)
    assert len(box["other"]) + len(mine) == 1 and len(_pushes()) == 1


def test_the_sweep_leaves_a_card_whose_auto_send_is_running(world):
    card, v = _card(world)
    st = world["store"]
    assert A._claim_auto_send(st, A._approval_id(card), NOW + timedelta(minutes=2))
    assert A.push_orphaned_deferred(st, now=NOW + timedelta(minutes=5)) == []
    # an auto-send that died holding its claim is swept once the claim is old
    swept = A.push_orphaned_deferred(st, now=NOW + timedelta(minutes=2 + A.AUTO_SEND_CLAIM_MINUTES + 1))
    assert len(swept) == 1 and len(_pushes()) == 1


def test_an_auto_send_that_raises_pushes_the_card(world, monkeypatch):
    card, v = _card(world)

    def boom(*a, **k):
        raise RuntimeError("store hiccup")
    monkeypatch.setattr(A, "_approve_loaded", boom)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and "auto-send raised" in out["error"]
    assert len(_pushes()) == 1 and _pushes()[0]["message"].startswith("Not auto-sent: the auto-send failed")
    assert len(_rows(world, "template_auto_send_failed")) == 1


# =============================================================== the poller
def test_the_digest_counts_a_deferred_card_as_not_pushed_and_the_stuck_push_names_it(world):
    card, _ = _card(world)
    st = world["store"]
    later = NOW + timedelta(minutes=45)
    waiting = P.pending_approvals(st, later)
    assert [(w["approval"], w["pushed"], w.get("deferred"), w.get("status")) for w in waiting] == [
        (A._approval_id(card), False, True, "pending")]
    assert P._push_stuck(st, waiting, later) == [A._approval_id(card)]
    assert "never pushed" in notify.sent_in_test[-1]["message"]
    # an ordinary pending card that was pushed is not a stuck card
    raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    raw["notify_result"] = {"sent": True, "actionable": True}
    st.set(A.APPROVAL_PREFIX + A._approval_id(card), raw)
    waiting = P.pending_approvals(st, later)
    assert waiting[0]["pushed"] is True and "status" not in waiting[0]
    assert P._push_stuck(st, waiting, later) == []


def test_run_once_sweeps_orphans_and_sends_the_fyi(world):
    card, v = _card(world)
    st = world["store"]
    later = NOW + timedelta(minutes=3)
    gate.record_auto_send(st, kind="booking", template_id=TID, approval_id="other", status="sent", now=NOW)

    class NoReplies(object):
        def list_emails(self, **kw):
            return {"items": [], "next_starting_after": None}

    summary = P.run_once(NoReplies(), st, now=later, process=lambda e, now=None: {})
    assert summary["orphans_pushed"] == [A._approval_id(card)] and summary["autosend_fyi"] is True
    assert len(_pushes()) == 1
    assert [n for n in notify.sent_in_test if n["title"].startswith("Auto-sent from approved templates")]


# =================================================================== FYI
def test_the_fyi_on_a_public_topic_carries_counts_only(world):
    card, v = _card(world, now=NIGHT)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    gate.note_held(world["store"], kind="cadence", template_id="cadence.e3", reason="unapproved", now=NIGHT)
    calls = []

    def capture(title, message, **kw):
        calls.append(dict(kw, title=title, message=message))
        return {"sent": True}
    out = A.flush_auto_send_fyi(world["store"], now=NIGHT + timedelta(minutes=1), notify_fn=capture)
    assert out["sent"] is True and out["entries"] == 1 and out["held"] == {"cadence.e3": 1}
    assert len(calls) == 1
    c = calls[0]
    assert c["actions"] is None and c["click"] is None
    public = c["title"] + "\n" + c["message"]
    stored = _stored(world, card)
    body_line = [ln for ln in stored.draft.body_text.splitlines() if len(ln) > 20][0]
    for secret in (LEAD, FIRST, COMPANY, stored.draft.subject, body_line, "http", "example.com", "engine.test",
                   A._approval_id(card)):
        assert secret not in public, secret
    assert TID in c["message"] and "cadence.e3: 1 held" in c["message"]
    assert c["message"].endswith('To stop these, set the kill switch, or revoke a template from your terminal '
                                 '(jobs/approve_templates.py --revoke <id>).')
    # the email leg (Lorenzo's inbox) has the per-card line and a Veto link
    assert LEAD in c["email_message"] and ("/veto/%s" % stored.token) in c["email_message"]
    assert "/approve/" not in c["email_message"]
    assert world["store"].get(gate.FYI_KEY) == []


def test_one_fyi_per_30_minute_bucket(world):
    st = world["store"]
    calls = []

    def capture(title, message, **kw):
        calls.append(title)
        return {"sent": True}
    gate.record_auto_send(st, kind="booking", template_id=TID, approval_id="a1", status="sent", now=NOW)
    assert A.flush_auto_send_fyi(st, now=ct(2030, 1, 7, 10, 1), notify_fn=capture)["sent"] is True
    gate.record_auto_send(st, kind="booking", template_id=TID, approval_id="a2", status="sent", now=NOW)
    assert A.flush_auto_send_fyi(st, now=ct(2030, 1, 7, 10, 20), notify_fn=capture) is None   # same bucket
    assert len(calls) == 1 and len(st.get(gate.FYI_KEY)) == 1
    assert A.flush_auto_send_fyi(st, now=ct(2030, 1, 7, 10, 31), notify_fn=capture)["entries"] == 1
    assert len(calls) == 2
    # nothing pending: no push, and the bucket is not spent
    assert A.flush_auto_send_fyi(st, now=ct(2030, 1, 7, 11, 1), notify_fn=capture) is None
    gate.record_auto_send(st, kind="booking", template_id=TID, approval_id="a3", status="sent", now=NOW)
    assert A.flush_auto_send_fyi(st, now=ct(2030, 1, 7, 11, 2), notify_fn=capture)["sent"] is True


@pytest.mark.parametrize("failure", ["not_sent", "raises"])
def test_a_failed_fyi_push_restores_the_entries(world, failure):
    st = world["store"]
    gate.record_auto_send(st, kind="booking", template_id=TID, approval_id="a1", status="sent", now=NOW)
    gate.note_held(st, kind="show_rate", template_id="show_rate.t24", reason="unapproved", now=NOW)

    def bad(title, message, **kw):
        if failure == "raises":
            raise RuntimeError("ntfy down")
        return {"sent": False, "errors": ["ntfy: 500"]}
    out = A.flush_auto_send_fyi(st, now=NOW, notify_fn=bad)
    assert out["sent"] is False
    assert [e["approval_id"] for e in st.get(gate.FYI_KEY)] == ["a1"]
    assert gate.drain_fyi(st)[1] == {"show_rate.t24": 1}
    assert _rows(world, "push_failed")


# =============================================================== booking
class BookingGhl(object):
    """A GHL with a token and a free calendar; every call recorded."""

    has_token = True
    calendar_id = "cal-1"
    user_id = "user-1"

    def __init__(self, free):
        self.free = list(free)
        self.calls = []

    def get_free_slots(self, calendar_id, start_ms, end_ms, timezone="America/Chicago", user_id=None):
        return {"slots": list(self.free)}

    def search_contacts(self, email):
        return {"contacts": []}

    def create_appointment(self, *a, **kw):
        self.calls.append(("create_appointment", a, kw))
        return {"id": "appt-ct3-1"}

    def update_appointment_status(self, appointment_id, status, **kw):
        self.calls.append(("update_appointment_status", (appointment_id, status), kw))
        return {"id": appointment_id, "status": status}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*a, **k):
            self.calls.append((name, a, k))
            return {"id": "%s-1" % name}
        return fn


BOOK_NOW = ct(2030, 1, 7, 10, 0)
BOOK_SLOT = "2030-01-09T15:00:00-06:00"     # Wednesday 3:00pm CT


@pytest.fixture
def booking_world(world):
    ghl = BookingGhl([BOOK_SLOT, "2030-01-10T14:00:00-06:00"])
    deps = app_mod.configure(store=world["store"], ghl=ghl, instantly=world["inst"], clock=lambda: BOOK_NOW)
    world.update(ghl=ghl, deps=deps)
    yield world
    app_mod.configure()


def _booking_reply(world, email_id="b-1"):
    payload = {"event_type": "reply_received", "timestamp": BOOK_NOW.astimezone(pytz.utc).isoformat(),
               "campaign_id": CAMPAIGN, "campaign_name": "x", "lead_email": LEAD, "email_account": EACCOUNT,
               "firstName": FIRST, "companyName": COMPANY, "reply_subject": "Re: Quick question",
               "reply_text": "Wednesday at 3pm works for me.", "email_id": email_id, "thread_id": THREAD}
    ev = ReplyEvent.from_webhook(payload)
    ev.campaign_key = OFFER
    return app_mod.process_event(ev, deps=world["deps"], now=BOOK_NOW, busy_blocks=[])


def _appt_statuses(ghl):
    return [(c[1], c[2]) for c in ghl.calls if c[0] == "update_appointment_status"]


def test_an_approved_booking_confirmation_releases_the_invite_once_after_the_send(booking_world):
    w = booking_world
    for tid in ("booking.confirmation.no_zoom_link", "booking.confirmation.zoom_link"):
        w["tpl"].approve_ids(tid)
    res = _booking_reply(w)
    assert res.get("booking"), res.get("draft")
    creates = [c for c in w["ghl"].calls if c[0] == "create_appointment"]
    assert len(creates) == 1
    create_kw = creates[0][2]
    assert create_kw.get("to_notify", create_kw.get("toNotify")) is False
    assert create_kw.get("status", create_kw.get("appointment_status", "new")) in ("new", None)
    auto = res.get("auto_send") or {}
    if not auto.get("allowed"):
        pytest.skip("piece C's pipeline did not allow the confirmation here: %s" % auto)
    card = A.load(res["approval_token"], w["store"])
    assert card.status == "sent" and card.approved_by == "template" and len(w["inst"].sent) == 1
    assert _appt_statuses(w["ghl"]) == [(("appt-ct3-1", "confirmed"), {"to_notify": True})]
    assert _pushes() == []


def test_an_unapproved_booking_confirmation_stays_new_and_is_a_card(booking_world):
    w = booking_world
    res = _booking_reply(w)
    assert res.get("booking")
    card = A.load(res["approval_token"], w["store"])
    assert card.status == "pending" and w["inst"].sent == []
    assert _appt_statuses(w["ghl"]) == []                    # the appointment stays "new"
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith("Not auto-sent: %s" % A.REASON_TEXT["unapproved"])


# ========================================== S-rest round 6 prerequisites
def test_flag18_supersede_never_writes_over_a_send_that_started_after_its_read(world, monkeypatch):
    card, _ = _card(world, approve=False)
    st = world["store"]
    state = LeadState.from_store(st.get(card.state_key))
    real = A._approval_row
    box = {}

    def read_then_send(store, approval_id):
        found = real(store, approval_id)
        if not box:
            box["send"] = A.approve(card.token, world["inst"], store=st, now=NOW)
        return found
    monkeypatch.setattr(A, "_approval_row", read_then_send)
    out = A.supersede_pending(st, state, NOW)
    assert box["send"]["status"] == "sent" and out == []
    assert _stored(world, card).status == "sent"             # never overwritten with superseded
    held = [r for r in (st.get(A.OFFERED_KEY) or []) if isinstance(r, dict)
            and r.get("approval") == A._approval_id(card)]
    assert held                                              # the sent reply's times stay held


def test_flag18_supersede_writes_only_the_status(world):
    card, _ = _card(world, approve=False)
    st = world["store"]
    out = A.supersede_pending(st, LeadState.from_store(st.get(card.state_key)), NOW)
    assert out == [card.token]
    stored = _stored(world, card)
    assert stored.status == "superseded" and stored.decided_at == NOW.isoformat()


def test_flag18_retiring_an_orphan_owner_never_writes_over_a_send(world, monkeypatch):
    card, _ = _card(world, approve=False)
    st = world["store"]
    approval_id = A._approval_id(card)
    raw = st.get(A.APPROVAL_PREFIX + approval_id)
    st.set(A.APPROVAL_PREFIX + approval_id, dict(raw, status="send_failed"))
    real = A._approval_row
    box = {}

    def read_then_move(store, aid):
        found = real(store, aid)
        if not box:
            box["moved"] = True
            cur = st.get(A.APPROVAL_PREFIX + aid)
            st.set(A.APPROVAL_PREFIX + aid, dict(cur, status="sending", send_attempt="att-9"))
        return found
    monkeypatch.setattr(A, "_approval_row", read_then_move)
    A._retire_orphan_owner(st, approval_id, NOW)
    stored = st.get(A.APPROVAL_PREFIX + approval_id)
    assert stored["status"] == "sending" and stored["send_attempt"] == "att-9"
    monkeypatch.setattr(A, "_approval_row", real)
    st.set(A.APPROVAL_PREFIX + approval_id, dict(stored, status="send_failed"))
    A._retire_orphan_owner(st, approval_id, NOW)
    assert st.get(A.APPROVAL_PREFIX + approval_id)["status"] == "superseded"


TIME_MARK = "the lead's older reply (sent Mon) proposed a call at Thu 3:00pm CT; Edit the card"


def test_flag19_a_time_mark_that_lands_after_the_send_read_its_card_refuses_the_send(world, monkeypatch):
    """The probe's H1: Approve read the card (no problems); an older reply
    that proposes a time marks it before it moves to sending. The send
    refuses in the same locked write, the card is blocked with the mark,
    and nothing is sent."""
    card, _ = _card(world, approve=False)
    st = world["store"]
    approval_id = A._approval_id(card)
    real = A.card_context
    box = {}

    def ctx_then_mark(store, aid):
        if not box:
            def _add(current):
                draft = dict(current.get("draft") or {})
                draft["problems"] = list(draft.get("problems") or []) + [TIME_MARK]
                return dict(current, draft=draft)
            box["marked"] = A._transition(st, approval_id, A.SENDABLE_STATUSES, _add)
        return real(store, aid)
    monkeypatch.setattr(A, "card_context", ctx_then_mark)
    out = A.approve(card.token, world["inst"], store=st, now=NOW)
    assert box["marked"] is True
    assert out["ok"] is False and out["status"] == "blocked" and out["problems"] == [TIME_MARK]
    assert world["inst"].sent == []
    stored = st.get(A.APPROVAL_PREFIX + approval_id)
    assert stored["status"] == "blocked" and stored["draft"]["problems"] == [TIME_MARK]
    assert st.get(A.SEND_CLAIM_PREFIX + approval_id) is None
    assert _rows(world, "blocked_marked_meanwhile")


def test_flag19_a_whole_card_save_keeps_a_mark_added_meanwhile(world, monkeypatch):
    """A refusal the send writes over the whole card (here: times that have
    passed... replaced by an invite-claim block) never drops a mark another
    writer put on the stored card since the send read it."""
    card, _ = _card(world, approve=False)
    st = world["store"]
    approval_id = A._approval_id(card)
    loaded = A.load(card.token, st)
    raw = st.get(A.APPROVAL_PREFIX + approval_id)
    raw["draft"]["problems"] = [TIME_MARK]
    st.set(A.APPROVAL_PREFIX + approval_id, raw)
    loaded.status = "blocked"
    loaded.draft.problems = ["another problem"]
    assert A._save_open(loaded, st) is True
    assert st.get(A.APPROVAL_PREFIX + approval_id)["draft"]["problems"] == ["another problem", TIME_MARK]
    loaded.status = "sent"
    assert A._save_unless_sent(loaded, st) is None
    assert st.get(A.APPROVAL_PREFIX + approval_id)["draft"]["problems"] == ["another problem", TIME_MARK]


class _UndoGhl(object):
    """Records every call; create_appointment runs ``during`` first."""

    def __init__(self):
        self.calls = []
        self.during = None

    def create_appointment(self, *a, **k):
        self.calls.append(("create_appointment", a, k))
        hook, self.during = self.during, None
        if hook is not None:
            hook()
        return {"id": "appt-asked-9"}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*a, **k):
            self.calls.append((name, a, k))
            return {"id": "%s-1" % name}
        return fn


ASKED = "2030-01-08T09:00:00-06:00"   # Tuesday 9:00am CT: before Lorenzo's 12:00 rule


def _resets(ghl, world):
    """The undo's reset only (the booking itself moves the stage to Call
    Booked and the interest to 2): opportunity to New Reply, interest 1."""
    new_reply = settings.GHL_STAGES.get("new_reply")
    stages = [c for c in ghl.calls if c[0] == "update_opportunity_stage" and new_reply in c[1]]
    return stages, [i for i in world["inst"].interest if i[2] == 1]


def _asked_card(world):
    card, _ = _card(world, approve=False)
    st = world["store"]
    raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    st.set(A.APPROVAL_PREFIX + A._approval_id(card), dict(raw, requested_slot=ASKED, requested_status="outside_window",
                                                          requested_lead_tz="America/Chicago"))
    row = st.get(card.state_key)
    row["ghl_opportunity_id"] = "opp-1"
    st.set(card.state_key, row)
    return A.load(card.token, st)


@pytest.mark.parametrize("label,said", [("unsubscribe", "asked to be removed"), ("negative_notnow", "said not now")])
def test_flag20_the_book_as_asked_undo_never_resets_interest_or_stage_after_an_opt_out(world, label, said):
    """The probe's G1: Lorenzo presses Book as asked; while the call is being
    written the lead's no lands (the card is held). The undo cancels the call
    it made, but leaves the opportunity and the Instantly interest alone,
    and the push names the opt-out."""
    st = world["store"]
    card = _asked_card(world)
    ghl = _UndoGhl()

    def opt_out():
        row = st.get(card.state_key)
        row["opt_out"] = {"label": label, "email_id": "e-9", "received_at": NOW.isoformat(),
                          "set_at": NOW.isoformat()}
        st.set(card.state_key, row)
        raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
        st.set(A.APPROVAL_PREFIX + A._approval_id(card), dict(raw, status="blocked"))
    ghl.during = opt_out
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=NOW)
    assert out["ok"] is False and out["status"] == "blocked"
    assert out["undone"]["cancelled"] is True
    assert ("update_appointment_status", ("appt-asked-9", "cancelled"), {"to_notify": False}) in ghl.calls
    assert _resets(ghl, world) == ([], [])
    assert world["inst"].sent == []
    pushes = [n for n in notify.sent_in_test if n["title"].startswith("Book as asked undone")]
    assert len(pushes) == 1
    msg = pushes[0]["message"]
    assert "left the opportunity and the Instantly interest as they are, because the lead has since %s." % said in msg
    assert A.opt_out_advice(label) in msg
    assert "set the opportunity back to New Reply" not in msg
    logged = _rows(world, "book_as_asked_undone")
    assert logged[0]["reset_skipped"] == "opt_out" and logged[0]["opt_out"] == label


def test_flag20_the_undo_still_resets_when_the_row_shows_no_other_call_and_no_opt_out(world):
    st = world["store"]
    card = _asked_card(world)
    ghl = _UndoGhl()

    def superseded():
        raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
        st.set(A.APPROVAL_PREFIX + A._approval_id(card), dict(raw, status="superseded"))
    ghl.during = superseded
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=NOW)
    assert out["undone"]["cancelled"] is True
    stages, interest = _resets(ghl, world)
    assert len(stages) == 1 and interest == [(LEAD, CAMPAIGN, 1)]
    msg = [n for n in notify.sent_in_test if n["title"].startswith("Book as asked undone")][0]["message"]
    assert "set the opportunity back to New Reply and Instantly interest to 1." in msg
    assert "reset_skipped" not in _rows(world, "book_as_asked_undone")[0]


def test_flag20_cancel_booking_guard_reset_reads_the_stored_row(world):
    """The flag itself, on cancel_booking: another call on the stored row."""
    card, _ = _card(world, approve=False)
    st = world["store"]
    row = st.get(card.state_key)
    row["ghl_opportunity_id"] = "opp-1"
    row["cadence"] = {"booking": {"slot": "2030-01-10T14:00:00-06:00", "appointment_id": "appt-other"}}
    st.set(card.state_key, row)
    state = LeadState.from_store(row)
    state.cadence = {"booking": {"slot": ASKED, "appointment_id": "appt-mine"}}
    ghl = _UndoGhl()
    out = A.cancel_booking(state, ghl, world["inst"], NOW, store=st, reason="test", guard_reset=True)
    assert out["cancelled"] is True and out["reset_skipped"]["reason"] == "other_call"
    assert out["reset_skipped"]["appointment_id"] == "appt-other"
    assert _resets(ghl, world) == ([], [])
    # without the flag the old behaviour stands
    state.cadence = {"booking": {"slot": ASKED, "appointment_id": "appt-mine"}}
    out = A.cancel_booking(state, ghl, world["inst"], NOW, store=st, reason="test")
    assert "reset_skipped" not in out and world["inst"].interest == [(LEAD, CAMPAIGN, 1)]


class _RefusingGhl(_UndoGhl):
    """Refuses every cancel until ``refuse`` is turned off."""

    def __init__(self):
        _UndoGhl.__init__(self)
        self.refuse = True

    def update_appointment_status(self, appointment_id, status, **k):
        self.calls.append(("update_appointment_status", (appointment_id, status), k))
        if status == "cancelled" and self.refuse:
            raise RuntimeError("GHL 500 on cancel")
        return {"id": appointment_id, "status": status}


@pytest.mark.parametrize("case", ["clear", "opt_out", "other_call", "row_unreadable"])
def test_flag20_a_delayed_cancel_that_succeeds_later_uses_the_same_reset_rule(world, monkeypatch, case):
    """retry_failed_cancels: a cancel GHL refused, retried and done later,
    sets the opportunity and the interest back only when the stored row
    shows no other call, no opt-out, and can be read."""
    card, _ = _card(world, approve=False)
    st = world["store"]
    row = st.get(card.state_key)
    row["ghl_opportunity_id"] = "opp-1"
    row["cadence"] = {"booking": {"slot": ASKED, "appointment_id": "appt-late", "awaiting_approval": True}}
    st.set(card.state_key, row)
    state = LeadState.from_store(row)
    ghl = _RefusingGhl()
    failed = A.cancel_booking(state, ghl, world["inst"], NOW, store=st, reason="vetoed")
    assert failed["cancel_failed"] is True
    st.set(card.state_key, state.to_store())            # the row as the caller saves it
    if case == "opt_out":
        row = st.get(card.state_key)
        row["opt_out"] = {"label": "unsubscribe", "email_id": "e-9", "received_at": NOW.isoformat(),
                          "set_at": NOW.isoformat()}
        st.set(card.state_key, row)
    if case in ("other_call", "row_unreadable"):
        real = A._finish_pending_cancel

        def finish_then(store, state_key, *a, **k):
            removed = real(store, state_key, *a, **k)
            if case == "other_call":
                cur = store.get(state_key)
                cur["cadence"] = dict(cur.get("cadence") or {}, booking={
                    "slot": "2030-01-10T14:00:00-06:00", "appointment_id": "appt-newer", "owner": "c9"})
                store.set(state_key, cur)
            else:
                plain = store.get

                def broken(key, default=None):
                    if key == state_key:
                        raise OSError("store read failed")
                    return plain(key, default)
                monkeypatch.setattr(store, "get", broken)
            return removed
        monkeypatch.setattr(A, "_finish_pending_cancel", finish_then)
    ghl.refuse = False
    done = A.retry_failed_cancels(st, ghl, world["inst"], NOW + timedelta(minutes=5))
    assert [d.get("cancelled") for d in done] == [True]
    stages, interest = _resets(ghl, world)
    logged = _rows(world, "booking_cancel_retry_ok")
    if case == "clear":
        assert len(stages) == 1 and interest == [(LEAD, CAMPAIGN, 1)]
        assert "reset_skipped" not in done[0] and "reset_skipped" not in logged[0]
        return
    assert (stages, interest) == ([], [])
    assert done[0]["reset_skipped"]["reason"] == case and logged[0]["reset_skipped"] == case
