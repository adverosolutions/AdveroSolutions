"""Section 2 review fixes (2026-09-24): one email per lead per run, and the
in-thread "Re:" subject is checked from the same lookup that sends it.

1. appointments_tick ran the no-show ladder twice per tick (inside
   no_show.process and again in the recovery sweep): a no-show marked by hand
   the next morning got N3 and N4 in the same minute.
2. show_rate.run sent every due touch of a schedule: after a gap, R3 and R4
   went out together. Only the latest due reminder goes; earlier ones close
   as superseded.
3. dispatch_touch checked the thread subject from its own lookup and skipped
   the check when that lookup raised; send_lead_email now checks the subject
   it actually sends and holds on any problem.
"""
from datetime import datetime, timedelta

import httpx
import pytest

from shared import job_log, slots
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore
from jobs import appointments_tick as tick_mod
from services.reply_engine import no_show as ns
from services.reply_engine import show_rate as sr
from services.reply_engine import thread_reply as tr
from services.reply_engine.tests.conftest import install_template_env


@pytest.fixture(autouse=True)
def approvals_file(monkeypatch, tmp_path_factory):
    own = tmp_path_factory.mktemp("ct3")
    monkeypatch.setenv("STORE_PATH", str(own / "store.json"))
    return install_template_env(monkeypatch, own)


def _recorder():
    requests = []
    return requests, httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200, json={}))


def _emails():
    return [r for r in job_log.read_shadow_log() if r["action"] in ("send_message", "reply_to_email")]


# ------------------------------------------------ 1. no-show: one per tick
def test_a_no_show_marked_the_next_morning_gets_one_email_per_tick(tmp_env, shadow_mode, monkeypatch):
    start = datetime.fromisoformat("2026-09-28T14:00:00-05:00")   # Monday 14:00 CT
    appt = {"id": "appt-hand-1", "contact_id": "c-hand-1", "first_name": "Sopio", "company": "Taxfo Accounting",
            "email": "sopio@taxfo.test", "niche": "bookkeeping", "offer": "reactivation",
            "start_iso": start.isoformat(), "end_iso": (start + timedelta(minutes=15)).isoformat(),
            "zoom_link": "https://zoom.us/j/000000000009", "ghl_status": "noshow"}
    pairs = [["2026-10-01T13:00:00-05:00", "2026-10-02T14:00:00-05:00"],
             ["2026-10-05T13:00:00-05:00", "2026-10-06T14:00:00-05:00"]]
    n = {"i": 0}

    def picker(now, *a, **k):
        pair = pairs[n["i"] % 2]
        n["i"] += 1
        return {"slots": pair, "text": slots.format_slots([slots.parse_iso(p) for p in pair]), "source": "ghl"}

    real = ns.claim_recovery_slots
    monkeypatch.setattr(ns, "claim_recovery_slots",
                        lambda now, ghl, store, a, slots_fn=None, **kw: real(now, ghl, store, a, slots_fn=picker, **kw))
    store = JsonFileStore(tmp_env / "s.json")
    requests, transport = _recorder()
    ghl = GHL(token=None, transport=transport)
    # Tuesday 11:00 CT: N3 is due at the flag and N4 (10:00) is due too
    result = tick_mod.tick(start + timedelta(hours=21), store, ghl, [appt])
    assert [e["template"] for e in result["recovery_detail"]["would_do"]] == ["ns_reschedule_email"]
    assert [r["payload"]["subject"] for r in _emails()] == ["New time for our call"]
    # N4 goes on a later tick, not in the same one
    result = tick_mod.tick(start + timedelta(hours=21, minutes=10), store, ghl, [appt])
    assert [e["template"] for e in result["recovery_detail"]["would_do"]] == ["ns_d1_email"]
    assert requests == []


# ------------------------------------------ 2. reminders: one per call per run
def test_r3_still_pending_when_r4_is_due_is_superseded(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    requests, transport = _recorder()
    ghl = GHL(token=None, transport=transport)
    booked = datetime.fromisoformat("2026-09-28T16:00:00-05:00")   # Monday afternoon: R2 skipped (6 h rule)
    start = datetime.fromisoformat("2026-09-29T12:00:00-05:00")    # Tuesday noon CT
    appt = {"id": "appt-r3r4", "contact_id": "c-r3r4", "first_name": "Ana", "company": "Shine Cleaning",
            "email": "ana@r3r4.test", "niche": "cleaning", "offer": "reactivation", "lead_tz": "America/Los_Angeles",
            "start_iso": start.isoformat(), "end_iso": (start + timedelta(minutes=15)).isoformat(),
            "zoom_link": "https://zoom.us/j/000000000015", "booked_at": booked.isoformat()}
    sr.run(booked, store, ghl, appointments=[appt])   # the widget-booking confirmation
    before = len(_emails())
    # the 10:30 CT tick (R3 at 08:30 PT) did not run; the next one is 11:05 CT, when R4 is due too
    out = sr.run(datetime.fromisoformat("2026-09-29T11:05:00-05:00"), store, ghl, appointments=[appt])
    assert [e["template"] for e in out["would_do"]] == ["reminder_1h_email"]
    assert [(e["template"], e["reason"]) for e in out["skipped"]] == [("reminder_morning_email", "superseded")]
    assert [r["payload"]["subject"] for r in _emails()[before:]] == ["See you at 12:00pm CT (10:00am PT)"]
    assert requests == []


# -------------------------------------- 3. the thread subject that is sent
LEAD = "ana@subj.test"
CAMPAIGN = "camp-subj"


def _subject_env(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    # the lead's own reply changed the thread subject to one the subject rules refuse
    store.set("lead:%s:%s" % (CAMPAIGN, LEAD), {"lead_email": LEAD, "campaign_id": CAMPAIGN,
                                                 "eaccount": "lorenzo@advero.test", "thread_id": "thr-1",
                                                 "last_email_id": "em-1",
                                                 "last_subject": "call me at 555-123-4567 www.example.com!!!"})
    start = datetime.fromisoformat("2026-09-29T14:00:00-05:00")
    appt = {"id": "appt-subj", "contact_id": "c-subj", "first_name": "Ana", "company": "Shine Cleaning",
            "email": LEAD, "campaign_id": CAMPAIGN, "niche": "cleaning", "offer": "reactivation",
            "start_iso": start.isoformat(), "end_iso": (start + timedelta(minutes=15)).isoformat(),
            "zoom_link": "https://zoom.us/j/000000000014"}
    touch = [sr.Touch.from_dict(t) for t in sr.ensure_scheduled(store, appt, start - timedelta(days=3))["touches"]
             if t["template_key"] == "reminder_1h_email"][0]
    now = start - timedelta(hours=1)
    sr.refresh_copy(touch, appt, now)
    requests, transport = _recorder()
    inst = Instantly(api_key="x", transport=transport, sleep=lambda s: None)
    ghl = GHL(token=None, transport=transport)
    return store, appt, touch, now, inst, ghl, requests


def test_a_refused_thread_subject_holds_even_when_the_first_lookup_fails(tmp_env, shadow_mode, monkeypatch):
    store, appt, touch, now, inst, ghl, requests = _subject_env(tmp_env)
    out = sr.dispatch_touch(touch, ghl, now, store=store, appointment=appt, kind="show_rate", instantly=inst)
    assert (out["status"], out["reason"]) == ("held", "thread_subject_refused")
    assert out["template_id"] == touch.template_id and out["problems"]

    real = tr.find_thread
    calls = {"n": 0}

    def flaky(store_, appt_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient store read error")
        return real(store_, appt_)

    monkeypatch.setattr(tr, "find_thread", flaky)
    out = sr.dispatch_touch(touch, ghl, now, store=store, appointment=appt, kind="show_rate", instantly=inst)
    assert out["status"] == "held" and out["reason"] == tr.LEAD_ROW_UNREADABLE
    out = sr.dispatch_touch(touch, ghl, now, store=store, appointment=appt, kind="show_rate", instantly=inst)
    assert (out["status"], out["reason"]) == ("held", "thread_subject_refused")
    assert _emails() == [] and requests == []


def test_send_lead_email_holds_when_the_subject_check_fails_or_raises(tmp_env, shadow_mode):
    store, appt, touch, now, inst, ghl, requests = _subject_env(tmp_env)
    seen = []
    rec = tr.send_lead_email(store, appt, "Subject", "Hey Ana,\n\nBody\n\nLorenzo", now, instantly=inst, ghl=ghl,
                             contact_id="c-subj", subject_check=lambda s: seen.append(s) or ["bad subject"])
    assert seen == ["Re: call me at 555-123-4567 www.example.com!!!"]
    assert rec["skipped"] and rec["reason"] == tr.THREAD_SUBJECT_REFUSED and not rec["shadow"]

    def boom(s):
        raise ValueError("rules unreadable")

    rec = tr.send_lead_email(store, appt, "Subject", "Hey Ana,\n\nBody\n\nLorenzo", now, instantly=inst, ghl=ghl,
                             contact_id="c-subj", subject_check=boom)
    assert rec["skipped"] and rec["reason"] == tr.THREAD_SUBJECT_REFUSED
    assert _emails() == [] and requests == []
