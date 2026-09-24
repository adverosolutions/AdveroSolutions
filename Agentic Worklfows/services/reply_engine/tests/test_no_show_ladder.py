"""Section 2 no-show ladder (2026-09-23; go-live timing and copy 2026-09-24):
N1 at S+5, the count 1 / 2 / 3 ladders and their timing, fresh slots with the "taken" line, the nurture
hand-off, the reply stop, the signed-off copy, the 8 h spacing between ladder emails (late emails, and
no-shows flagged late by hand), zero HTTP in shadow."""
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from shared import job_log, settings, slots
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import no_show as ns
from services.reply_engine import nurture

COPY = Path(__file__).resolve().parents[3] / "sections" / "2_booked_calls" / "copy_signed_off.md"
START = datetime.fromisoformat("2026-09-24T15:00:00-05:00")  # Thursday
APPT = {
    "id": "appt-ladder-1",
    "contact_id": "contact-ladder-1",
    "opportunity_id": "opp-ladder-1",
    "first_name": "Sopio",
    "company": "Taxfo Accounting",
    "email": "sopio@taxfo.test",
    "niche": "bookkeeping",
    "offer": "reactivation",
    "lead_tz": "America/New_York",
    "start_iso": START.isoformat(),
    "end_iso": (START + timedelta(minutes=15)).isoformat(),
    "zoom_link": "https://zoom.us/j/000000000009",
}
PAIRS = [
    ["2026-09-29T13:00:00-05:00", "2026-09-30T14:00:00-05:00"],
    ["2026-10-01T13:00:00-05:00", "2026-10-02T14:00:00-05:00"],
    ["2026-10-05T13:00:00-05:00", "2026-10-06T14:00:00-05:00"],
    ["2026-10-07T13:00:00-05:00", "2026-10-08T14:00:00-05:00"],
    ["2026-10-12T13:00:00-05:00", "2026-10-13T14:00:00-05:00"],
]


class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})


def make_ghl():
    rec = Recorder()
    return GHL(token=None, transport=httpx.MockTransport(rec)), rec


class RotatingSlots(object):
    """A fresh pair per claim, like GHL answering with new free times."""

    def __init__(self):
        self.n = 0

    def __call__(self, now):
        pair = PAIRS[self.n % len(PAIRS)]
        self.n += 1
        two = [slots.parse_iso(i) for i in pair]
        return {"slots": pair, "text": slots.format_slots(two), "source": "ghl"}


def host(appt, minutes=-1):
    start = slots.parse_iso(appt["start_iso"])
    return {"at_iso": (start + timedelta(minutes=minutes)).isoformat(), "name": "Lorenzo Villarreal",
            "email": "lorenzovillarreal@adverosolutions.com", "is_host": True}


def touches(store, appt=APPT):
    return store.get(ns.recovery_key(appt["id"], slots.parse_iso(appt["start_iso"]).isoformat()))["touches"]


def armed(store, key, appt=APPT):
    return [t for t in touches(store, appt) if t["template_key"] == key][0]["when_iso"]


def last_email():
    rows = [r for r in job_log.read_shadow_log() if r["action"] in ("send_message", "reply_to_email")]
    return rows[-1]["payload"]


# ------------------------------------------------------------ signed-off copy
def signed_off():
    """{heading: (subject, body)} and the N5 niche lines from copy_signed_off.md."""
    text = COPY.read_text(encoding="utf-8").split("## No-show recovery", 1)[1]
    out = {}
    for m in re.finditer(r"### (N\d[^\n]*)\nSubject: ([^\n]*)\n```\n(.*?)\n```", text, re.S):
        out[m.group(1).split(",")[0].split(" (")[0] + ("_repeat" if m.group(1).startswith("N3, second missed") else "")] = (
            m.group(2), m.group(3))
    lines = dict(((n.lower(), o.lower()), line) for n, o, line in
                 re.findall(r"^- (\w+), (reactivation|outbound): (.*)$", text, re.M))
    no_link = re.search(r"### N1.*?No link on file: `([^`]*)`", text, re.S).group(1)
    return out, lines, no_link


def fill(s, **kw):
    for k, v in kw.items():
        s = s.replace("{%s}" % k, v)
    return s


def test_every_rendered_message_is_the_signed_off_copy():
    copy, lines, no_link = signed_off()
    two = "Tue 1:00pm or Wed 2:00pm CT"
    vals = dict(first_name="Sopio", company="Taxfo Accounting", slots=two, call_link=APPT["zoom_link"])
    cases = [("N1", ns.N1, 1), ("N3", ns.N3, 1), ("N3_repeat", ns.N3, 2), ("N4", ns.N4, 1), ("N9", ns.N9, 1),
             ("N6", ns.N6, 1), ("N7", ns.N7, 1), ("N8", ns.N8, 3)]
    rendered = []
    for heading, key, count in cases:
        got = ns.render(key, APPT, START, two, count)
        subject, body = copy[heading]
        assert (got["subject"], got["body"]) == (fill(subject, **vals), fill(body, **vals)), heading
        rendered.append(got)
    # N1 with no link on file
    got = ns.render(ns.N1, dict(APPT, zoom_link=None), START, "", 1)
    subject, body = copy["N1"]
    assert got["body"] == fill(body, **vals).replace(
        "I'm on the call now. Here's the link:\n%s" % APPT["zoom_link"], no_link)
    # N5, one approved line per campaign; none without one
    assert len(lines) == 6
    for (niche, offer), line in sorted(lines.items()):
        appt = dict(APPT, niche=niche, offer=offer)
        got = ns.render(ns.N5, appt, START, two, 1)
        subject, body = copy["N5"]
        assert (got["subject"], got["body"]) == (fill(subject, **vals), fill(body, niche_point=line, **vals))
        rendered.append(got)
    generic = ns.render(ns.N5, dict(APPT, niche=None, offer=None, company="Acme"), START, two, 1)
    assert ns.unfilled(generic) == "no_niche_point"
    assert ns.unfilled(ns.render(ns.N3, APPT, START, "", 1)) == "no_slots"
    # never a booking link; the only link anywhere is N1's call link
    for got in rendered:
        text = got["subject"] + "\n" + got["body"]
        assert settings.BOOKING_URL not in text and "grab" not in text.lower()
        assert "http" not in text.replace(APPT["zoom_link"], "")



def test_the_2026_09_24_copy_word_for_word():
    """Lorenzo's go-live copy (2026-09-24), pinned here as well as in copy_signed_off.md."""
    two = "Tue 1:00pm or Wed 2:00pm CT"
    got = ns.render(ns.N1, APPT, START, "", 1)
    assert got == {"subject": "I'm on",
                   "body": "Hey Sopio,\n\nI'm on the call now. Here's the link:\n%s\n\nLorenzo" % APPT["zoom_link"]}
    got = ns.render(ns.N1, dict(APPT, zoom_link=None), START, "", 1)
    assert got == {"subject": "I'm on",
                   "body": "Hey Sopio,\n\nI'm on the call now. The link is on your calendar invite.\n\nLorenzo"}
    got = ns.render(ns.N9, APPT, START, two, 1)
    assert got == {"subject": "Still want to talk?",
                   "body": "Hey Sopio,\n\nTrying once more to get our call back on the calendar. I can do %s. "
                           "Just reply with the one that works.\n\nLorenzo" % two}
    got = ns.render(ns.N3, APPT, START, two, 2)
    assert got == {"subject": "Missed you again",
                   "body": "Hey Sopio,\n\nLooks like I missed you again on today's call. If this isn't a priority "
                           "right now, just let me know. If you still want to talk, I can do %s. If you're not "
                           "looking to grow Taxfo Accounting right now, that's fine too, just tell me.\n\n"
                           "Lorenzo" % two}
    got = ns.render(ns.N8, APPT, START, "", 3)
    assert got == {"subject": "Closing this out",
                   "body": "Hey Sopio,\n\nMissed you again today. I don't think this is worth pursuing anymore, "
                           "and it doesn't make sense for either of us. Wish you the best of luck with Taxfo "
                           "Accounting.\n\nLorenzo"}
    # no times held: the slot emails never go out
    assert ns.unfilled(ns.render(ns.N9, APPT, START, "", 1)) == "no_slots"
    assert ns.unfilled(ns.render(ns.N3, APPT, START, "", 2)) == "no_slots"
    assert ns.unfilled(ns.render(ns.N8, APPT, START, "", 3)) is None
    # no dashes or exclamation marks anywhere in the new copy
    for key, count in ((ns.N1, 1), (ns.N9, 1), (ns.N3, 2), (ns.N8, 3)):
        text = str(ns.render(key, APPT, START, two, count))
        assert "!" not in text and "\u2014" not in text and "\u2013" not in text


def test_no_company_on_file_reads_your_business_as_the_day_2_subject_does():
    bare = dict(APPT, company=None)
    assert ns.render(ns.N5, bare, START, "x or y", 1)["subject"] == "One thing for your business"
    assert "If you're not looking to grow your business right now" in ns.render(ns.N3, bare, START, "x or y", 2)["body"]
    assert "Wish you the best of luck with your business." in ns.render(ns.N8, bare, START, "", 3)["body"]


# ------------------------------------------------------------ N1
def test_n1_goes_at_s5_only_with_zoom_evidence_once_and_never_at_the_flag(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    assert ns.STILL_ON_AFTER == timedelta(minutes=5)
    # S+3 (the old time) and S+4: not yet
    for minutes in (2, 3, 4):
        assert ns.process(START + timedelta(minutes=minutes), APPT, [host(APPT)], store, ghl)["events"] == []
    res = ns.process(START + timedelta(minutes=5), APPT, [host(APPT)], store, ghl)
    assert res["events"] == ["still_on:would_do"] and last_email()["subject"] == "I'm on"
    assert APPT["zoom_link"] in last_email()["message"]
    assert ns.process(START + timedelta(minutes=7), APPT, [host(APPT)], store, ghl)["events"] == []  # once
    # no Zoom evidence (no join data, no meeting-started signal): nothing
    quiet = dict(APPT, id="appt-quiet")
    assert ns.process(START + timedelta(minutes=5), quiet, [], store, ghl)["events"] == []
    # the meeting-started signal alone is evidence
    started = dict(APPT, id="appt-started")
    res = ns.process(START + timedelta(minutes=6), started, [], store, ghl,
                     meeting_signals={"started": {"at": START.isoformat()}})
    assert res["events"] == ["still_on:would_do"]
    # the lead joined: no nudge
    joined = dict(APPT, id="appt-joined")
    lead = {"at_iso": (START + timedelta(minutes=1)).isoformat(), "name": "Sopio", "email": APPT["email"]}
    assert "still_on" not in str(ns.process(START + timedelta(minutes=5), joined, [host(joined), lead], store,
                                            ghl)["events"])
    # first seen at S+9: still inside the window
    s9 = dict(APPT, id="appt-s9")
    assert ns.process(START + timedelta(minutes=9), s9, [host(s9)], store, ghl)["events"] == ["still_on:would_do"]
    # first seen at the flag's moment (S+10): flagged, never "I'm on"
    late = dict(APPT, id="appt-late")
    assert ns.process(START + timedelta(minutes=10), late, [host(late)], store, ghl)["events"] == ["no_show"]
    assert rec.requests == []


# ------------------------------------------------------------ count 1
def test_first_miss_ladder_timing_fresh_slots_and_nurture(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    picker = RotatingSlots()
    flagged = START + timedelta(minutes=10)
    res = ns.process(flagged, APPT, [host(APPT)], store, ghl, slots_fn=picker)
    assert res["no_show_count"] == 1 and res["recovery_touches"] == 6
    timeline = [(t["template_key"], t["when_iso"]) for t in touches(store)]
    assert timeline == [
        ("ns_reschedule_email", "2026-09-24T15:25:00-05:00"),   # max(flag, S+25)
        ("ns_d1_email", "2026-09-25T09:00:00-05:00"),           # 1 business day (Fri), 10:00 ET
        ("ns_d2_value_email", "2026-09-28T09:00:00-05:00"),     # 2 business days (Mon)
        ("ns_d3_retry_email", "2026-09-29T09:00:00-05:00"),     # 3 business days (Tue)
        ("ns_d5_yes_no_email", "2026-10-01T09:00:00-05:00"),    # 5 business days (Thu)
        ("ns_d7_breakup_email", "2026-10-05T09:00:00-05:00"),   # 7 business days (Mon)
    ]
    assert store.get(ns.OFFERED_SLOTS_KEY) is None  # nothing held at the flag

    def run(key):
        return ns.run_recovery(slots.parse_iso(armed(store, key)), store, ghl, slots_fn=picker)

    out = run("ns_reschedule_email")
    assert [e["template"] for e in out["would_do"]] == ["ns_reschedule_email"]
    assert "Tue 1:00pm or Wed 2:00pm CT" in last_email()["message"]
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[0]

    out = run("ns_d1_email")
    assert [e["template"] for e in out["would_do"]] == ["ns_d1_email"]
    msg = last_email()["message"]
    assert "Those two times got taken, but I can do Thu 1:00pm or Fri 2:00pm CT" in msg
    held = sorted(store.get(ns.OFFERED_SLOTS_KEY))
    assert held == PAIRS[1]  # the first pair was given back once the lead was told it was taken
    assert not set(PAIRS[0]) & set(r["slot"] for r in store.get("offered_slots") or [])

    assert [e["template"] for e in run("ns_d2_value_email")["would_do"]] == ["ns_d2_value_email"]
    assert "tax season" in last_email()["message"] and last_email()["subject"] == "One thing for Taxfo Accounting"
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[2]
    out = run("ns_d3_retry_email")
    assert [e["template"] for e in out["would_do"]] == ["ns_d3_retry_email"]
    assert last_email()["subject"] == "Still want to talk?"
    assert ("Trying once more to get our call back on the calendar. I can do Wed 1:00pm or Thu 2:00pm CT. "
            "Just reply with the one that works.") in last_email()["message"]
    # fresh times, and the day-2 pair stays held: N9 never told the lead it was taken
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(PAIRS[2] + PAIRS[3])
    assert out["stage_moves"] == [] and out["nurture"] == []
    assert [e["template"] for e in run("ns_d5_yes_no_email")["would_do"]] == ["ns_d5_yes_no_email"]
    assert last_email()["subject"] == "Quick one"
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[4]  # "the last two times got taken": both pairs back

    out = run("ns_d7_breakup_email")
    assert [e["template"] for e in out["would_do"]] == ["ns_d7_breakup_email"]
    assert last_email()["subject"] == "Leaving the door open"
    assert out["stage_moves"][0]["payload"]["stage"] == "follow_up_later"
    assert [n["status"] for n in out["nurture"]] == ["done"]
    enrolled = nurture.get(APPT["email"], store=store)
    assert enrolled["status"] == "active" and enrolled["reason"] == "no_show_no_rebook"
    assert [e["note"] for e in enrolled["events"]] == [APPT["id"]]
    # nothing left, nothing enrolled twice
    again = ns.run_recovery(START + timedelta(days=20), store, ghl, slots_fn=picker)
    assert again["would_do"] == [] and again["nurture"] == []
    assert len(nurture.get(APPT["email"], store=store)["events"]) == 1
    assert rec.requests == []


def test_a_friday_miss_moves_the_business_day_touches_past_the_weekend():
    friday = datetime.fromisoformat("2026-09-25T13:00:00-05:00")
    appt = dict(APPT, start_iso=friday.isoformat(), lead_tz=None)
    when = {t.template_key: t.when_iso for t in ns.recovery_touches(appt, friday + timedelta(minutes=10), 1)}
    assert when["ns_d1_email"] == "2026-09-28T10:00:00-05:00"          # Monday, 10:00 CT
    assert when["ns_d2_value_email"] == "2026-09-29T10:00:00-05:00"    # Tuesday
    assert when["ns_d3_retry_email"] == "2026-09-30T10:00:00-05:00"    # Wednesday
    assert when["ns_d5_yes_no_email"] == "2026-10-02T10:00:00-05:00"   # the next Friday
    assert when["ns_d7_breakup_email"] == "2026-10-06T10:00:00-05:00"  # the Tuesday after
    assert when["ns_reschedule_email"] == "2026-09-25T13:25:00-05:00"
    # flagged late (a hand-set status): N3 is never before the flag
    late = {t.template_key: t.when_iso for t in ns.recovery_touches(appt, friday + timedelta(minutes=40), 1)}
    assert late["ns_reschedule_email"] == "2026-09-25T13:40:00-05:00"


def test_n5_without_a_campaign_is_skipped_and_the_ladder_goes_on(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    picker = RotatingSlots()
    appt = dict(APPT, id="appt-generic", niche=None, offer=None, company="Acme Group")
    ns.process(START + timedelta(minutes=10), appt, [host(appt)], store, ghl, slots_fn=picker)
    for key in ("ns_reschedule_email", "ns_d1_email"):
        ns.run_recovery(slots.parse_iso(armed(store, key, appt)), store, ghl, slots_fn=picker)
    out = ns.run_recovery(slots.parse_iso(armed(store, "ns_d2_value_email", appt)), store, ghl, slots_fn=picker)
    assert out["would_do"] == [] and [e["reason"] for e in out["skipped"]] == ["no_niche_point"]
    out = ns.run_recovery(slots.parse_iso(armed(store, "ns_d3_retry_email", appt)), store, ghl, slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_d3_retry_email"]
    # N5 skipped: the day-1 pair stays held next to N9's (N9 never called it taken)
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(PAIRS[1] + PAIRS[2])
    out = ns.run_recovery(slots.parse_iso(armed(store, "ns_d5_yes_no_email", appt)), store, ghl, slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_d5_yes_no_email"]
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[3]
    assert rec.requests == []


# ------------------------------------------------------------ counts 2 and 3
def test_second_and_third_misses(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    picker = RotatingSlots()
    second = dict(APPT, id="appt2", start_iso="2026-09-29T14:00:00-05:00", end_iso="2026-09-29T14:15:00-05:00")
    third = dict(APPT, id="appt3", start_iso="2026-10-06T14:00:00-05:00", end_iso="2026-10-06T14:15:00-05:00")
    for appt in (APPT, second, third):
        res = ns.process(slots.parse_iso(appt["start_iso"]) + timedelta(minutes=10), appt, [host(appt)], store,
                         ghl, slots_fn=picker)
    assert store.get("no_show_count:%s" % APPT["contact_id"]) == 3

    # second miss (Tuesday): the .repeat reschedule at S+25, N6 three business days on (Friday)
    t2 = [(t["template_key"], t["when_iso"]) for t in touches(store, second)]
    assert t2 == [("ns_reschedule_email", "2026-09-29T14:25:00-05:00"),
                  ("ns_d5_yes_no_email", "2026-10-02T09:00:00-05:00")]
    out = ns.run_recovery(slots.parse_iso(t2[0][1]), store, ghl, appointment_id="appt2", slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_reschedule_email"]
    assert last_email()["subject"] == "Missed you again"
    assert ("Looks like I missed you again on today's call. If this isn't a priority right now, just let me know. "
            "If you still want to talk, I can do ") in last_email()["message"]
    assert "If you're not looking to grow Taxfo Accounting right now, that's fine too, just tell me." in (
        last_email()["message"])
    assert out["stage_moves"] == [] and out["nurture"] == []
    out = ns.run_recovery(slots.parse_iso(t2[1][1]), store, ghl, appointment_id="appt2", slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_d5_yes_no_email"]
    assert [m["payload"].get("note") for m in out["stage_moves"]] == ["note:second_no_show_pattern"]
    assert [n["status"] for n in out["nurture"]] == ["done"]

    # third miss: N8 at S+25, then Lost and nurture (already active: idempotent)
    t3 = [(t["template_key"], t["when_iso"]) for t in touches(store, third)]
    assert t3 == [("ns_third_miss_email", "2026-10-06T14:25:00-05:00")]
    out = ns.run_recovery(slots.parse_iso(t3[0][1]), store, ghl, appointment_id="appt3", slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_third_miss_email"]
    assert last_email()["subject"] == "Closing this out"
    assert ("Missed you again today. I don't think this is worth pursuing anymore, and it doesn't make sense for "
            "either of us. Wish you the best of luck with Taxfo Accounting.") in last_email()["message"]
    assert "http" not in last_email()["message"] and " or " not in last_email()["message"]  # no slots
    assert out["stage_moves"][0]["payload"]["stage"] == "lost"
    assert out["nurture"][0]["status"] == "done" and out["nurture"][0]["created"] is False
    assert rec.requests == []


# ------------------------------------------------------------ reply stop, in-thread
def test_a_reply_after_the_call_stops_the_ladder_and_emails_go_in_the_thread(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    irec = Recorder()
    instantly = Instantly(api_key="test-key", transport=httpx.MockTransport(irec))
    picker = RotatingSlots()
    campaign = "camp-ladder"
    appt = dict(APPT, campaign_id=campaign)
    row_key = "lead:%s:%s" % (campaign, appt["email"])
    store.set(row_key, {"lead_email": appt["email"], "campaign_id": campaign, "eaccount": "lorenzo@advero.test",
                        "thread_id": "thr-1", "last_email_id": "em-1", "last_subject": "Sopio, question",
                        "last_inbound_at": (START - timedelta(days=2)).isoformat()})
    ns.process(START + timedelta(minutes=10), appt, [host(appt)], store, ghl, slots_fn=picker, instantly=instantly)
    out = ns.run_recovery(START + timedelta(minutes=25), store, ghl, slots_fn=picker, instantly=instantly)
    assert [(e["template"], e.get("transport")) for e in out["would_do"]] == [("ns_reschedule_email",
                                                                               "instantly_thread")]
    reply = last_email()
    assert reply["subject"] == "Re: Sopio, question" and reply["to"] == appt["email"]
    # the lead answers after the call: the rest of the ladder is cancelled
    row = store.get(row_key)
    row["last_inbound_at"] = (START + timedelta(hours=3)).isoformat()
    store.set(row_key, row)
    out = ns.run_recovery(slots.parse_iso(armed(store, "ns_d1_email", appt)), store, ghl, slots_fn=picker,
                          instantly=instantly)
    assert out["would_do"] == [] and [c["reason"] for c in out["cancelled"]] == ["replied"]
    assert out["cancelled"][0]["touches"] == 5
    assert store.get(ns.state_key(appt["id"]))["done_reason"] == "replied"
    assert rec.requests == [] and irec.requests == []


# ------------------------------------------------------------ a late email never meets the next one
def subjects_sent():
    return [r["payload"].get("subject") for r in job_log.read_shadow_log()
            if r["action"] in ("send_message", "reply_to_email")]


class HoldOne(object):
    """dispatch_touch wrapper: the CT3 template gate holds ``template`` while
    ``on`` is True; everything else goes through the real dispatch."""

    def __init__(self, real, template):
        self.real, self.template, self.on = real, template, True

    def __call__(self, touch, *a, **kw):
        if self.on and touch.template_key == self.template:
            return {"status": ns.HELD, "hold": "template", "reason": "template_unapproved",
                    "template_id": "no_show.%s" % touch.template_key, "kind": "no_show"}
        return self.real(touch, *a, **kw)


def ticks(first, last, step):
    t = first
    while t <= last:
        yield t
        t += step


REAL_DISPATCH = ns.sr.dispatch_touch


class FreshSlots(object):
    """A pair never handed out before, inside the offer rules for ``now``
    (12:00-18:00 CT, 1 to 3 business days out): a held touch re-picks on
    every tick once its own pair drifts out of range, and RotatingSlots'
    five pairs would come round again."""

    def __init__(self):
        self.n = 0

    def __call__(self, now):
        self.n += 1
        day = ns._add_business_days(slots.to_tz(now, settings.TZ).date(), 1 + (self.n // 12) % 3)
        first = settings.TZ.localize(datetime(day.year, day.month, day.day, 12, 0)) + timedelta(
            minutes=30 * (self.n % 12))
        two = [first, first + timedelta(minutes=15)]
        return {"slots": [t.isoformat() for t in two], "text": slots.format_slots(two), "source": "ghl"}


def slots_of(store, key, appt=APPT):
    return _isos([t for t in touches(store, appt) if t["template_key"] == key][0].get("slots"))


def _isos(info):
    return list((info or {}).get("slots") or [])


def held_until(store, ghl, picker, hold, release_at, last, appt=APPT, down=None):
    """Tick every 10 minutes (the tick's cadence) from the held template's
    armed time to ``last``, the template gate holding it until ``release_at``.
    ``down`` = (from, to): no tick runs in between (the tick was down)."""
    out = []
    first = slots.parse_iso(armed(store, hold.template, appt))
    for now in ticks(first, last, timedelta(minutes=10)):
        if down and down[0] < now < down[1]:
            continue
        hold.on = now < release_at
        out.append((now, ns.run_recovery(now, store, ghl, slots_fn=picker)))
    return out


def _held_setup(store_path, monkeypatch, template, upto, appt=APPT):
    store = JsonFileStore(store_path)
    ghl, rec = make_ghl()
    picker = FreshSlots()
    ns.process(slots.parse_iso(appt["start_iso"]) + timedelta(minutes=10), appt, [host(appt)], store, ghl,
               slots_fn=picker)
    for key in upto:
        ns.run_recovery(slots.parse_iso(armed(store, key, appt)), store, ghl, slots_fn=picker)
    hold = HoldOne(REAL_DISPATCH, template)
    monkeypatch.setattr(ns.sr, "dispatch_touch", hold)
    return store, ghl, rec, picker, hold


def test_a_held_day_2_email_released_minutes_before_day_3_is_superseded(tmp_env, shadow_mode, monkeypatch):
    n5_at, release = slots.parse_iso("2026-09-28T09:00:00-05:00"), slots.parse_iso("2026-09-29T08:50:00-05:00")
    # the tick running every 10 minutes; and the tick down from just after
    # N5's hold until N9's time, so the first run after it sees both due
    n9_due = release + timedelta(minutes=10)
    for name, down in (("every_tick", None), ("tick_down", (n5_at, n9_due))):
        store, ghl, rec, picker, hold = _held_setup(tmp_env / ("s-%s.json" % name), monkeypatch, ns.N5,
                                                    ("ns_reschedule_email", "ns_d1_email"))
        n9_at = slots.parse_iso(armed(store, "ns_d3_retry_email"))
        assert slots.parse_iso(armed(store, ns.N5)) == n5_at and n9_at == release + timedelta(minutes=10)
        before = len(subjects_sent())
        runs = held_until(store, ghl, picker, hold, release, slots.parse_iso("2026-09-29T09:30:00-05:00"),
                          down=down)
        got = subjects_sent()[before:]
        assert got == ["Still want to talk?"], name  # N9 only; the day-2 email never went out
        n5 = [t for t in touches(store) if t["template_key"] == ns.N5][0]
        assert n5["skipped"] and n5["skip_reason"] == "superseded" and not n5.get("sent")
        # closed once: as soon as N9 was within the margin (a pending email
        # cannot go out after that point, held or not), or on the first run
        # after the outage
        closed = [(now, e["reason"]) for now, out in runs for e in out["skipped"]]
        assert [r for _, r in closed] == ["superseded"]
        assert closed[0][0] == (n9_at - ns.SUPERSEDE_MARGIN if down is None else n9_at)
        # N5's own claims never reached the lead: given back. N4's offer and N9's stay held.
        n4, n9 = slots_of(store, ns.N4), slots_of(store, ns.N9)
        assert slots_of(store, ns.N5) == [] and len(set(n4 + n9)) == 4
        assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(n4 + n9)
        assert [(n, e["template"]) for n, out in runs for e in out["would_do"]] == [(n9_at, ns.N9)]  # on time
        assert rec.requests == []


def test_a_held_day_1_email_released_minutes_before_day_2_is_superseded(tmp_env, shadow_mode, monkeypatch):
    # a Monday call: N4 Tuesday 10:00 ET, N5 Wednesday 10:00 ET (one business day apart, inside N4's day of lateness)
    monday = dict(APPT, id="appt-monday", start_iso="2026-09-28T15:00:00-05:00", end_iso="2026-09-28T15:15:00-05:00")
    store, ghl, rec, picker, hold = _held_setup(tmp_env / "s.json", monkeypatch, ns.N4, ("ns_reschedule_email",),
                                                appt=monday)
    assert armed(store, ns.N5, monday) == "2026-09-30T09:00:00-05:00"
    before = len(subjects_sent())
    held_until(store, ghl, picker, hold, slots.parse_iso("2026-09-30T08:50:00-05:00"),
               slots.parse_iso("2026-09-30T09:30:00-05:00"), appt=monday)
    assert subjects_sent()[before:] == ["One thing for Taxfo Accounting"]  # N5 only
    assert "The last two times got taken" in last_email()["message"]  # true: N3's offer reached the lead
    n4 = [t for t in touches(store, monday) if t["template_key"] == ns.N4][0]
    assert n4["skip_reason"] == "superseded" and not n4.get("sent")
    # N3's pair back (taken), N4's never offered; only N5's is held
    assert slots_of(store, ns.N4, monday) == []
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(slots_of(store, ns.N5, monday))
    assert rec.requests == []


def test_a_held_email_released_the_same_afternoon_still_goes(tmp_env, shadow_mode, monkeypatch):
    """Lateness well short of the next email (N5 held from 09:00 to 14:00 on
    Monday, N9 at 09:00 Tuesday): N5 goes when released, N9 on time."""
    store, ghl, rec, picker, hold = _held_setup(tmp_env / "s.json", monkeypatch, ns.N5,
                                                ("ns_reschedule_email", "ns_d1_email"))
    before = len(subjects_sent())
    held_until(store, ghl, picker, hold, slots.parse_iso("2026-09-28T14:00:00-05:00"),
               slots.parse_iso("2026-09-29T09:30:00-05:00"))
    assert subjects_sent()[before:] == ["One thing for Taxfo Accounting", "Still want to talk?"]
    assert rec.requests == []


def test_a_held_email_never_goes_after_a_later_one_went_out():
    base = {"appointment_id": APPT["id"], "contact_id": APPT["contact_id"], "channel": "email", "body": "x"}
    rec = {"touches": [dict(base, key="a", template_key=ns.N5, when_iso="2026-09-28T09:00:00-05:00"),
                       dict(base, key="b", template_key=ns.N9, when_iso="2026-10-09T09:00:00-05:00", sent=True)]}
    now = slots.parse_iso("2026-09-28T09:30:00-05:00")
    assert ns._superseded_reason("a", rec, APPT, now) == "superseded"
    rec["touches"][1].pop("sent")
    assert ns._superseded_reason("a", rec, APPT, now) is None  # the next one is days away
    assert ns._superseded_reason("b", rec, APPT, now) is None  # the last touch is never superseded


def test_the_on_time_ladder_never_supersedes_anything(tmp_env, shadow_mode):
    for tz in ("America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London"):
        store = JsonFileStore(tmp_env / ("s-%s.json" % tz.replace("/", "-")))
        ghl, rec = make_ghl()
        picker = RotatingSlots()
        appt = dict(APPT, lead_tz=tz)
        for start in ("2026-09-24T12:00:00-05:00", "2026-09-25T18:00:00-05:00"):  # Thu noon, Fri 18:00 (latest)
            a = dict(appt, id="appt-%s-%s" % (tz, start[:10]), start_iso=start,
                     end_iso=(slots.parse_iso(start) + timedelta(minutes=15)).isoformat())
            ns.process(slots.parse_iso(start) + timedelta(minutes=10), a, [host(a)], store, ghl, slots_fn=picker)
            for t in touches(store, a):
                out = ns.run_recovery(slots.parse_iso(t["when_iso"]), store, ghl, appointment_id=a["id"],
                                      slots_fn=picker)
                assert out["skipped"] == [], (tz, start, t["template_key"])
                assert [e["template"] for e in out["would_do"]] == [t["template_key"]], (tz, start)
        assert rec.requests == []


# ------------------------------------------------------------ N9 keeps the earlier offer held
def _registry(store):
    return sorted(r["slot"] for r in store.get("offered_slots") or [] if r.get("lead") == APPT["email"])


def test_n9_keeps_the_day_2_pair_claimed_until_n6_says_it_was_taken(tmp_env, shadow_mode):
    from services.reply_engine import approval

    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    picker = RotatingSlots()
    ns.process(START + timedelta(minutes=10), APPT, [host(APPT)], store, ghl, slots_fn=picker)
    for key in ("ns_reschedule_email", "ns_d1_email", "ns_d2_value_email"):
        ns.run_recovery(slots.parse_iso(armed(store, key)), store, ghl, slots_fn=picker)
    assert _registry(store) == sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[2]

    n9_at = slots.parse_iso(armed(store, "ns_d3_retry_email"))
    ns.run_recovery(n9_at, store, ghl, slots_fn=picker)
    both = sorted(PAIRS[2] + PAIRS[3])
    assert _registry(store) == sorted(store.get(ns.OFFERED_SLOTS_KEY)) == both
    # another lead cannot be offered the day-2 times while this lead may still pick one
    assert approval.claim_slots(store, "other@lead.test", PAIRS[2], n9_at) == PAIRS[2]
    # N6 picks around both pairs: an injected picker offering the day-2 times again is refused
    record = store.get(ns.recovery_key(APPT["id"], START.isoformat()))
    assert sorted(record["held_offers"]) == both

    n6_at = slots.parse_iso(armed(store, "ns_d5_yes_no_email"))
    out = ns.run_recovery(n6_at, store, ghl, slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_d5_yes_no_email"]
    assert "the last two times got taken" in last_email()["message"]
    assert _registry(store) == sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[4]  # both earlier pairs given back
    assert approval.claim_slots(store, "other@lead.test", PAIRS[2], n6_at) == []
    assert rec.requests == []


def test_n6_never_reoffers_a_time_the_lead_still_holds(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    picker = RotatingSlots()
    ns.process(START + timedelta(minutes=10), APPT, [host(APPT)], store, ghl, slots_fn=picker)
    for key in ("ns_reschedule_email", "ns_d1_email", "ns_d2_value_email", "ns_d3_retry_email"):
        ns.run_recovery(slots.parse_iso(armed(store, key)), store, ghl, slots_fn=picker)

    def day_2_again(now):  # the day-2 pair, which N9 did not call taken
        return {"slots": PAIRS[2], "text": "x or y", "source": "ghl"}

    out = ns.run_recovery(slots.parse_iso(armed(store, "ns_d5_yes_no_email")), store, ghl, slots_fn=day_2_again)
    assert out["would_do"] == [] and [e["error"] for e in out["errors"]] == ["no_slots"]
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(PAIRS[2] + PAIRS[3])  # still both held
    assert rec.requests == []


# ------------------------------------------------------------ a no-show flagged late
# The go-live path while the Discovery Call calendar is on Google Meet: no Zoom
# data, so detection says "unknown" at S+10 and asks Lorenzo; he sets noshow in
# GHL by hand and the 10-minute tick picks it up, up to a day later or more. N3
# goes at the flag. No email of the ladder may then reach the lead less than
# SUPERSEDE_MARGIN (8 h) after it: N4 due minutes later ("Those two times got
# taken") closes, the next day email goes on its own day, and the ladder's last
# email waits for the end of the margin instead of closing.
TICK = timedelta(minutes=10)


def ct(text):
    """A Central (CDT) time: ct("2026-09-25 08:40")."""
    return datetime.fromisoformat(text.replace(" ", "T") + ":00-05:00")


class LateRun(object):
    def __init__(self):
        self.sent = []          # (when, template)
        self.emails = {}        # template -> the shadow-log payload
        self.skipped = []       # (when, template, reason)
        self.deferred = []      # (when, template, reason, until)
        self.stage_moves = []   # (when, stage / note)
        self.nurture = []       # (when, status)
        self.held_after = {}    # template -> the times held for the lead right after it went
        self.registry_errors = []


def held_times(store, appt, now):
    """(record, recovery-only key, approval's registry): the times held for
    this lead from ``now`` on. The record's view is every offer that reached
    the lead and no later email called taken (held_offers) plus the claims of
    slot emails still pending; both registries must hold exactly those."""
    record = store.get(ns.recovery_key(appt["id"], slots.parse_iso(appt["start_iso"]).isoformat())) or {}
    mine = set(record.get("held_offers") or [])
    for t in record.get("touches") or []:
        if not t.get("sent") and not t.get("skipped"):
            mine |= set(_isos(t.get("slots")))
    recovery = [r.get("slot") if isinstance(r, dict) else r for r in store.get(ns.OFFERED_SLOTS_KEY) or []]
    approval_rows = [r["slot"] for r in store.get("offered_slots") or []
                     if r.get("lead") == appt["email"] and r.get("source") == ns.RECOVERY_CLAIM_SOURCE
                     and r.get("appointment") == appt["id"]]

    def ahead(isos):
        return sorted(i for i in isos if slots.parse_iso(i) >= now)

    return ahead(mine), ahead(recovery), ahead(approval_rows)


def run_ticks(store, ghl, appt, first, last, run=None, joins=None, step=TICK):
    """The tick from ``first`` to ``last`` every ``step`` (10 minutes), as
    jobs/appointments_tick runs it (no_show.process with run_ladder=False,
    then the recovery sweep), with GHL's free times replaced by the synthetic
    grid (no token). The slot registries are checked after every tick."""
    run = run or LateRun()
    for now in ticks(first, last, step):
        ns.process(now, appt, joins or [], store, ghl, run_ladder=False)
        out = ns.run_recovery(now, store, ghl, upcoming_appointments=[])
        for e in out["would_do"]:
            run.sent.append((now, e["template"]))
            run.emails[e["template"]] = last_email()
            run.held_after[e["template"]] = held_times(store, appt, now)[1]
        run.skipped += [(now, e["template"], e["reason"]) for e in out["skipped"]]
        run.deferred += [(now, e["template"], e["reason"], e.get("until")) for e in out["deferred"]]
        run.stage_moves += [(now, (m.get("payload") or {}).get("stage") or (m.get("payload") or {}).get("note"))
                            for m in out["stage_moves"]]
        run.nurture += [(now, n["status"]) for n in out["nurture"]]
        mine, recovery, approval_rows = held_times(store, appt, now)
        if not mine == recovery == approval_rows:
            run.registry_errors.append((now, mine, recovery, approval_rows))
    return run


def meet_miss(store, ghl, appt, flag, last, count_before=0):
    """No Zoom data at S+10 ("unknown", a task for Lorenzo), then GHL says
    noshow and the tick flags the miss at ``flag``."""
    start = slots.parse_iso(appt["start_iso"])
    if count_before:
        store.set(ns.count_key_for(appt["contact_id"]), count_before)
    first = ns.process(start + timedelta(minutes=10), appt, [], store, ghl, run_ladder=False)
    assert first["verdict"] == "unknown" and first["events"] == ["no_telemetry"]
    marked = dict(appt, ghl_status="noshow")
    res = ns.process(flag, marked, [], store, ghl, run_ladder=False)
    assert res["events"] == ["no_show"] and res["no_show_count"] == count_before + 1
    return run_ticks(store, ghl, marked, flag, last)


def assert_spaced(run):
    """No two ladder emails reached the lead less than SUPERSEDE_MARGIN apart."""
    for (t1, k1), (t2, k2) in zip(run.sent, run.sent[1:]):
        assert t2 - t1 >= ns.SUPERSEDE_MARGIN, (k1, t1, k2, t2)


def assert_fresh_offers(store, appt):
    """Every slot email that went out offered two times this lead was never
    offered before, and each "taken" email came after an earlier offer."""
    seen, offered_before = [], False
    for t in touches(store, appt):
        if not t.get("sent"):
            continue
        if t["template_key"] in ns.TAKEN_TEMPLATES:
            assert offered_before, t["template_key"]
        if t["template_key"] in ns.SLOT_TEMPLATES:
            pair = _isos(t.get("slots"))
            assert len(pair) == 2 and not set(pair) & set(seen), (t["template_key"], pair, seen)
            seen += pair
            offered_before = True


def pair_of(store, key, appt):
    return sorted(_isos([t for t in touches(store, appt) if t["template_key"] == key][0].get("slots")))


def ahead_of(isos, now):
    return sorted(i for i in isos if slots.parse_iso(i) >= now)


def test_marked_by_hand_the_next_morning_before_n4_n3_goes_and_n4_closes(tmp_env, shadow_mode):
    """Thursday 15:00 CT call, Eastern lead, marked Friday 08:40 CT: N4 is due
    at 09:00 CT (10:00 ET). It never goes; N5 goes Monday on its own day."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    appt = dict(APPT, id="appt-late-am")
    run = meet_miss(store, ghl, appt, ct("2026-09-25 08:40"), ct("2026-10-06 12:00"))
    assert [(t["template_key"], t["when_iso"]) for t in touches(store, appt)] == [
        (ns.N3, "2026-09-25T08:40:00-05:00"), (ns.N4, "2026-09-25T09:00:00-05:00"),
        (ns.N5, "2026-09-28T09:00:00-05:00"), (ns.N9, "2026-09-29T09:00:00-05:00"),
        (ns.N6, "2026-10-01T09:00:00-05:00"), (ns.N7, "2026-10-05T09:00:00-05:00")]
    assert run.sent == [(ct("2026-09-25 08:40"), ns.N3), (ct("2026-09-28 09:00"), ns.N5),
                        (ct("2026-09-29 09:00"), ns.N9), (ct("2026-10-01 09:00"), ns.N6),
                        (ct("2026-10-05 09:00"), ns.N7)]
    assert run.skipped == [(ct("2026-09-25 09:00"), ns.N4, "superseded")]
    assert_spaced(run)
    assert_fresh_offers(store, appt)
    assert run.registry_errors == []
    n3, n5, n9, n6 = (pair_of(store, k, appt) for k in (ns.N3, ns.N5, ns.N9, ns.N6))
    assert pair_of(store, ns.N4, appt) == []  # N4 never held anything
    assert run.held_after[ns.N3] == n3
    # N5's "taken" line is true (N3's pair reached the lead) and gives N3's pair back
    assert "The last two times got taken" in run.emails[ns.N5]["message"]
    assert ahead_of(n3, ct("2026-09-28 09:00"))  # N3 offered a time still ahead on Monday morning...
    assert run.held_after[ns.N5] == ahead_of(n5, ct("2026-09-28 09:00"))  # ...released once N5 called it taken
    assert run.held_after[ns.N9] == ahead_of(n5 + n9, ct("2026-09-29 09:00"))
    assert run.held_after[ns.N6] == ahead_of(n6, ct("2026-10-01 09:00"))
    assert run.stage_moves == [(ct("2026-10-05 09:00"), "follow_up_later")]
    assert run.nurture == [(ct("2026-10-05 09:00"), "done")]
    assert rec.requests == []


def test_marked_by_hand_the_next_afternoon_after_n4_time(tmp_env, shadow_mode):
    """Marked Friday 14:00 CT, after N4's 09:00: N3 at the flag, N4 closes on
    the next tick instead of going ten minutes after N3."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    appt = dict(APPT, id="appt-late-pm")
    run = meet_miss(store, ghl, appt, ct("2026-09-25 14:00"), ct("2026-10-06 12:00"))
    assert run.sent == [(ct("2026-09-25 14:00"), ns.N3), (ct("2026-09-28 09:00"), ns.N5),
                        (ct("2026-09-29 09:00"), ns.N9), (ct("2026-10-01 09:00"), ns.N6),
                        (ct("2026-10-05 09:00"), ns.N7)]
    assert run.skipped == [(ct("2026-09-25 14:10"), ns.N4, "superseded")]
    assert_spaced(run)
    assert_fresh_offers(store, appt)
    assert run.registry_errors == []
    assert "The last two times got taken" in run.emails[ns.N5]["message"]
    assert run.held_after[ns.N5] == ahead_of(pair_of(store, ns.N5, appt), ct("2026-09-28 09:00"))
    assert run.stage_moves == [(ct("2026-10-05 09:00"), "follow_up_later")]
    assert rec.requests == []


def test_marked_by_hand_two_and_three_business_days_later(tmp_env, shadow_mode):
    ghl, rec = make_ghl()
    # Monday 14:00 CT (business day 2): N4 (Friday) and N5 (Monday 09:00) are
    # past. N3 at the flag; N4 is too late and N5 closes; N9 goes Tuesday on
    # its own day and keeps N3's pair held next to its own (it calls nothing
    # taken), N6 gives both back.
    store = JsonFileStore(tmp_env / "s-monday.json")
    appt = dict(APPT, id="appt-late-bd2")
    run = meet_miss(store, ghl, appt, ct("2026-09-28 14:00"), ct("2026-10-06 12:00"))
    assert run.sent == [(ct("2026-09-28 14:00"), ns.N3), (ct("2026-09-29 09:00"), ns.N9),
                        (ct("2026-10-01 09:00"), ns.N6), (ct("2026-10-05 09:00"), ns.N7)]
    assert run.skipped == [(ct("2026-09-28 14:10"), ns.N4, "too_late"), (ct("2026-09-28 14:10"), ns.N5, "superseded")]
    assert_spaced(run)
    assert_fresh_offers(store, appt)
    assert run.registry_errors == []
    n3, n9, n6 = (pair_of(store, k, appt) for k in (ns.N3, ns.N9, ns.N6))
    assert run.held_after[ns.N9] == ahead_of(n3 + n9, ct("2026-09-29 09:00"))
    assert "the last two times got taken" in run.emails[ns.N6]["message"]
    assert run.held_after[ns.N6] == ahead_of(n6, ct("2026-10-01 09:00"))
    assert run.stage_moves == [(ct("2026-10-05 09:00"), "follow_up_later")]

    # Tuesday 10:00 CT (business day 3), after N9's 09:00: N9 is due already,
    # so N3 closes under the rule for a late email (the next email that can
    # still go is due) and N9 is the first email; N6 then says N9's times were
    # taken, which is true.
    store = JsonFileStore(tmp_env / "s-tuesday.json")
    appt = dict(APPT, id="appt-late-bd3")
    run = meet_miss(store, ghl, appt, ct("2026-09-29 10:00"), ct("2026-10-06 12:00"))
    assert run.sent == [(ct("2026-09-29 10:00"), ns.N9), (ct("2026-10-01 09:00"), ns.N6),
                        (ct("2026-10-05 09:00"), ns.N7)]
    assert run.skipped == [(ct("2026-09-29 10:00"), ns.N3, "superseded"), (ct("2026-09-29 10:00"), ns.N4, "too_late"),
                           (ct("2026-09-29 10:00"), ns.N5, "too_late")]
    assert_spaced(run)
    assert_fresh_offers(store, appt)
    assert run.registry_errors == []
    assert pair_of(store, ns.N3, appt) == []
    assert run.held_after[ns.N9] == ahead_of(pair_of(store, ns.N9, appt), ct("2026-09-29 10:00"))
    assert "the last two times got taken" in run.emails[ns.N6]["message"]
    assert run.stage_moves == [(ct("2026-10-05 09:00"), "follow_up_later")]
    assert rec.requests == []


def test_a_second_miss_flagged_late_still_hands_off(tmp_env, shadow_mode):
    """Second miss: N3 (.repeat) at the flag, N6 3 business days after the
    call, then the pattern note and nurture. N6 is the ladder's last email: when
    the flag comes on N6's own day it waits 8 h after N3 instead of closing."""
    ghl, rec = make_ghl()
    # flagged the next morning: N6 on its own day
    store = JsonFileStore(tmp_env / "s-next-day.json")
    appt = dict(APPT, id="appt-2nd-a")
    run = meet_miss(store, ghl, appt, ct("2026-09-25 08:40"), ct("2026-10-01 12:00"), count_before=1)
    assert [(t["template_key"], t["when_iso"]) for t in touches(store, appt)] == [
        (ns.N3, "2026-09-25T08:40:00-05:00"), (ns.N6, "2026-09-29T09:00:00-05:00")]
    assert run.sent == [(ct("2026-09-25 08:40"), ns.N3), (ct("2026-09-29 09:00"), ns.N6)]
    assert run.emails[ns.N3]["subject"] == "Missed you again"
    assert run.skipped == [] and run.deferred == []
    assert run.stage_moves == [(ct("2026-09-29 09:00"), "note:second_no_show_pattern")]
    assert run.nurture == [(ct("2026-09-29 09:00"), "done")]
    assert_spaced(run)
    assert_fresh_offers(store, appt)
    assert run.registry_errors == []

    # flagged on N6's morning, before its 09:00: N6 waits until N3 + 8 h
    store = JsonFileStore(tmp_env / "s-same-morning.json")
    appt = dict(APPT, id="appt-2nd-b", contact_id="contact-2nd-b", email="b@taxfo.test")
    run = meet_miss(store, ghl, appt, ct("2026-09-29 08:40"), ct("2026-10-01 12:00"), count_before=1)
    assert run.sent == [(ct("2026-09-29 08:40"), ns.N3), (ct("2026-09-29 16:40"), ns.N6)]
    assert run.deferred == [(ct("2026-09-29 09:00"), ns.N6, "spacing_wait", "2026-09-29T16:40:00-05:00")]
    assert run.skipped == []
    n6 = [t for t in touches(store, appt) if t["template_key"] == ns.N6][0]
    assert (n6["rearmed_from"], n6["when_iso"]) == ("2026-09-29T09:00:00-05:00", "2026-09-29T16:40:00-05:00")
    assert "the last two times got taken" in run.emails[ns.N6]["message"]  # true: N3's pair reached the lead
    assert run.held_after[ns.N6] == ahead_of(pair_of(store, ns.N6, appt), ct("2026-09-29 16:40"))
    assert run.stage_moves == [(ct("2026-09-29 16:40"), "note:second_no_show_pattern")]
    assert run.nurture == [(ct("2026-09-29 16:40"), "done")]
    assert_spaced(run)
    assert_fresh_offers(store, appt)
    assert run.registry_errors == []

    # a Tuesday call, N6 due Friday 09:00; flagged Friday 14:00: the end of the
    # margin is Friday night, so N6 goes Monday 07:00 CT (08:00 ET), within its
    # lateness from the new time, and still hands off
    tuesday = dict(APPT, id="appt-2nd-c", contact_id="contact-2nd-c", email="c@taxfo.test",
                   start_iso="2026-09-29T15:00:00-05:00", end_iso="2026-09-29T15:15:00-05:00")
    store = JsonFileStore(tmp_env / "s-friday.json")
    run = meet_miss(store, ghl, tuesday, ct("2026-10-02 14:00"), ct("2026-10-06 12:00"), count_before=1)
    assert run.sent == [(ct("2026-10-02 14:00"), ns.N3), (ct("2026-10-05 07:00"), ns.N6)]
    assert run.deferred == [(ct("2026-10-02 14:10"), ns.N6, "spacing_wait", "2026-10-05T07:00:00-05:00")]
    assert run.skipped == []
    assert run.stage_moves == [(ct("2026-10-05 07:00"), "note:second_no_show_pattern")]
    assert run.nurture == [(ct("2026-10-05 07:00"), "done")]
    assert_spaced(run)
    assert_fresh_offers(store, tuesday)
    assert run.registry_errors == []
    assert rec.requests == []


def test_a_third_miss_flagged_late_closes_the_file(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()
    appt = dict(APPT, id="appt-3rd")
    run = meet_miss(store, ghl, appt, ct("2026-09-25 08:40"), ct("2026-09-26 12:00"), count_before=2)
    assert run.sent == [(ct("2026-09-25 08:40"), ns.N8)]
    assert run.emails[ns.N8]["subject"] == "Closing this out"
    assert run.stage_moves == [(ct("2026-09-25 08:40"), "lost")]
    assert run.nurture == [(ct("2026-09-25 08:40"), "done")]
    assert_spaced(run)
    assert run.skipped == [] and run.registry_errors == []
    assert store.get(ns.OFFERED_SLOTS_KEY) is None  # N8 offers no times
    assert rec.requests == []


def test_an_email_that_may_have_gone_counts_for_the_spacing(tmp_env, shadow_mode, monkeypatch):
    """N3's send may have been delivered (maybe_sent: closed, never retried).
    It counts as having reached the lead: N4 ten minutes later closes."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl()

    def maybe_n3(touch, *a, **kw):
        if touch.template_key == ns.N3:
            return {"status": ns.MAYBE_SENT, "reason": "send_failed", "error": "timeout",
                    "transport": "instantly_thread"}
        return REAL_DISPATCH(touch, *a, **kw)

    monkeypatch.setattr(ns.sr, "dispatch_touch", maybe_n3)
    appt = dict(APPT, id="appt-maybe")
    run = meet_miss(store, ghl, appt, ct("2026-09-25 08:40"), ct("2026-09-25 09:10"))
    n3 = [t for t in touches(store, appt) if t["template_key"] == ns.N3][0]
    assert n3["maybe_sent"] and n3["maybe_sent_at"] == "2026-09-25T08:40:00-05:00" and not n3.get("sent")
    assert run.sent == [] and run.skipped == [(ct("2026-09-25 09:00"), ns.N4, "superseded")]
    # N3's times may have reached the lead: they stay held until an email calls them taken
    n3_pair = pair_of(store, ns.N3, appt)
    assert len(n3_pair) == 2
    assert held_times(store, appt, ct("2026-09-25 09:10"))[1] == ahead_of(n3_pair, ct("2026-09-25 09:10"))
    run = run_ticks(store, ghl, dict(appt, ghl_status="noshow"), ct("2026-09-25 09:20"), ct("2026-09-28 12:00"),
                    run=run)
    assert run.sent == [(ct("2026-09-28 09:00"), ns.N5)]
    assert run.sent[0][0] - slots.parse_iso(n3["maybe_sent_at"]) >= ns.SUPERSEDE_MARGIN
    assert run.held_after[ns.N5] == ahead_of(pair_of(store, ns.N5, appt), ct("2026-09-28 09:00"))
    assert run.registry_errors == []
    assert rec.requests == []


def test_the_spacing_rule_on_a_bare_record():
    base = {"appointment_id": APPT["id"], "contact_id": APPT["contact_id"], "channel": "email", "body": "x"}
    rec = {"touches": [
        dict(base, key="n3", template_key=ns.N3, when_iso="2026-09-25T08:40:00-05:00", sent=True,
             sent_at="2026-09-25T08:40:00-05:00"),
        dict(base, key="n4", template_key=ns.N4, when_iso="2026-09-25T09:00:00-05:00"),
        dict(base, key="n5", template_key=ns.N5, when_iso="2026-09-28T09:00:00-05:00"),
        dict(base, key="n7", template_key=ns.N7, when_iso="2026-09-25T09:00:00-05:00",
             meta={"after": "stage:follow_up_later", "nurture": True})]}
    # N4 less than 8 h after N3 reached the lead: closed; 8 h and more: free to go
    assert ns._superseded_reason("n4", rec, APPT, ct("2026-09-25 09:00")) == "superseded"
    assert ns._superseded_reason("n4", rec, APPT, ct("2026-09-25 16:39")) == "superseded"
    assert ns._superseded_reason("n4", rec, APPT, ct("2026-09-25 16:40")) is None
    # the last touch is never superseded: it waits for the end of the margin,
    # moved into the send window (16:40 CT is 17:40 ET, inside both)
    assert ns._superseded_reason("n7", rec, APPT, ct("2026-09-25 09:00")) is None
    assert ns._spacing_wait("n7", rec, APPT, ct("2026-09-25 09:00")) == ct("2026-09-25 16:40")
    assert ns._spacing_wait("n7", rec, APPT, ct("2026-09-25 16:40")) is None
    assert ns._spacing_wait("n4", rec, APPT, ct("2026-09-25 09:00")) is None  # only the last touch waits
    # the end of the margin past 19:00 CT on a Friday: Monday 07:00 CT (08:00 ET)
    late = {"touches": [dict(rec["touches"][0], sent_at="2026-09-25T13:00:00-05:00"), rec["touches"][3]]}
    assert ns._spacing_wait("n7", late, APPT, ct("2026-09-25 13:10")) == ct("2026-09-28 07:00")
    # maybe sent counts, from its own stamp; an older record without one uses the armed time
    maybe = {"touches": [dict(rec["touches"][0], sent=False, sent_at=None, skipped=True, maybe_sent=True,
                              maybe_sent_at="2026-09-25T08:50:00-05:00"), rec["touches"][1], rec["touches"][2]]}
    assert ns._superseded_reason("n4", maybe, APPT, ct("2026-09-25 16:45")) == "superseded"
    maybe["touches"][0].pop("maybe_sent_at")
    assert ns._superseded_reason("n4", maybe, APPT, ct("2026-09-25 16:45")) is None
    # nothing reached the lead yet: no spacing (the other rules still apply)
    fresh = {"touches": [dict(rec["touches"][0], sent=False, sent_at=None)] + rec["touches"][1:]}
    assert ns._last_reached_before(fresh, "n4") is None


def test_on_time_n3_and_the_first_day_email_are_always_more_than_12_hours_apart():
    """The proof behind "the on-time ladder never meets the margin": for every
    call start in the offer window (12:00-17:45 CT), every weekday and a spread
    of zones, N3 at S+25 goes by 18:10 CT and the first day email (N4, or N6 on
    a second miss) at 07:00 CT on the next business day at the earliest, at
    least 12 h 50 min later."""
    zones = [None, "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
             "America/Anchorage", "Pacific/Honolulu", "America/Sao_Paulo", "Europe/London", "Europe/Berlin",
             "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney", "Pacific/Auckland"]
    closest = None
    for day in range(21, 26):  # Monday 2026-09-21 .. Friday 2026-09-25
        for minutes in range(0, 6 * 60, 15):  # 12:00 .. 17:45
            start = ct("2026-09-%02d 12:00" % day) + timedelta(minutes=minutes)
            flagged = start + timedelta(minutes=10)
            n3 = ns.touch_time(ns.AT_S25, start, flagged)
            assert n3 == start + timedelta(minutes=25) and (n3.hour, n3.minute) <= (18, 10)
            next_day = ns._add_business_days(start.date(), 1)
            for zone in zones:
                lead_tz = ns.lead_tz_of({"lead_tz": zone})  # as the engine reads it; None is Central
                assert (lead_tz is None) == (zone is None)
                for rule in (ns.LADDERS[1][1][1], ns.LADDERS[2][1][1]):
                    first_day = ns.touch_time(rule, start, flagged, lead_tz)
                    assert first_day >= settings.TZ.localize(datetime(next_day.year, next_day.month, next_day.day, 7))
                    gap = first_day - n3
                    assert gap >= timedelta(hours=12, minutes=50), (start, zone, rule, first_day)
                    closest = gap if closest is None else min(closest, gap)
    assert closest == timedelta(hours=12, minutes=50)  # a 17:45 call, N4 at 07:00 CT the next business day


def test_leads_in_asia_and_australia_on_time(tmp_env, shadow_mode):
    """touch_time keeps each day email inside 07:00-19:00 for both CT and the
    lead. For these zones the two windows overlap only an hour or three on a
    CT afternoon (the next morning there), so an email for a Friday there
    moves past the weekend and can land on the same CT afternoon as the next
    email of the ladder. The earlier one then closes (superseded: the next is
    due within 8 h) and the later one goes, so no two emails reach the lead
    less than 8 h apart. Documented, not redesigned."""
    ghl, rec = make_ghl()
    cases = [
        # Tokyo (07:00-09:00 JST is 17:00-19:00 CDT), Wednesday call: day 1 (Friday in Tokyo) and day 2
        # (Monday) both land on Monday 17:00 CT
        ("Asia/Tokyo", "2026-09-23 15:00",
         [("2026-09-23 15:30", ns.N3), ("2026-09-28 17:00", ns.N5), ("2026-09-29 17:00", ns.N9),
          ("2026-10-01 17:00", ns.N6), ("2026-10-05 17:00", ns.N7)],
         [("2026-09-28 17:00", ns.N4, "superseded")]),
        ("Asia/Singapore", "2026-09-23 15:00",
         [("2026-09-23 15:30", ns.N3), ("2026-09-28 18:00", ns.N5), ("2026-09-29 18:00", ns.N9),
          ("2026-10-01 18:00", ns.N6), ("2026-10-05 18:00", ns.N7)],
         [("2026-09-28 18:00", ns.N4, "superseded")]),
        # Sydney, Thursday call: day 5 (a Friday there) moves to Monday 15:00 CT, three hours before day 7
        ("Australia/Sydney", "2026-09-24 15:00",
         [("2026-09-24 15:30", ns.N3), ("2026-09-28 16:00", ns.N4), ("2026-09-29 16:00", ns.N5),
          ("2026-09-30 16:00", ns.N9), ("2026-10-05 18:00", ns.N7)],
         [("2026-10-05 15:00", ns.N6, "superseded")]),
    ]
    for zone, start_text, sent, skipped in cases:
        store = JsonFileStore(tmp_env / ("s-%s.json" % zone.replace("/", "-")))
        start = ct(start_text)
        appt = dict(APPT, id="appt-%s" % zone, lead_tz=zone, start_iso=start.isoformat(),
                    end_iso=(start + timedelta(minutes=15)).isoformat())
        # Zoom data: flagged on time at S+10; then a tick on every half hour
        # (every armed time here is on the hour or S+25)
        assert ns.process(start + timedelta(minutes=10), appt, [host(appt)], store, ghl,
                          run_ladder=False)["events"] == ["no_show"]
        run = run_ticks(store, ghl, appt, start + timedelta(minutes=30), ct(sent[-1][0]) + TICK,
                        joins=[host(appt)], step=timedelta(minutes=30))
        assert run.sent == [(ct(w), k) for w, k in sent], zone
        assert run.skipped == [(ct(w), k, r) for w, k, r in skipped], zone
        assert_spaced(run)
        assert_fresh_offers(store, appt)
        assert run.registry_errors == [], zone
        assert run.stage_moves == [(ct(sent[-1][0]), "follow_up_later")]
    assert rec.requests == []
