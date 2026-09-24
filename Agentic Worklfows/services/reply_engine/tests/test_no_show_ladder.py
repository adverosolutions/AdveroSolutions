"""Section 2 no-show ladder (2026-09-23; go-live timing and copy 2026-09-24):
N1 at S+5, the count 1 / 2 / 3 ladders and their timing, fresh slots with the "taken" line, the nurture
hand-off, the reply stop, the signed-off copy, zero HTTP in shadow."""
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
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == PAIRS[3]  # fresh times, the day-2 pair given back
    assert out["stage_moves"] == [] and out["nurture"] == []
    assert [e["template"] for e in run("ns_d5_yes_no_email")["would_do"]] == ["ns_d5_yes_no_email"]
    assert last_email()["subject"] == "Quick one"

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
    out = ns.run_recovery(slots.parse_iso(armed(store, "ns_d5_yes_no_email", appt)), store, ghl, slots_fn=picker)
    assert [e["template"] for e in out["would_do"]] == ["ns_d5_yes_no_email"]
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
