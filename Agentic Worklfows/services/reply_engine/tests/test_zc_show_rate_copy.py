"""ZC copy round (2026-09-23): show-rate and no-show copy, the call link and
the engine-booked confirmation.

One test per fix in the round's item list (7, 8, 12, 13, 14, 17, 21, 22,
23, 24, 29) plus the platform-neutral call link and jobs/appointments_tick's
link pick. Lead data is made up. No network, no live flags.
"""
from datetime import timedelta

import pytest
import pytz

from shared import slots as slot_rules
from shared.store import JsonFileStore

from jobs import appointments_tick as tick_job
from services.reply_engine import approval as A
from services.reply_engine import no_show as ns
from services.reply_engine import show_rate as sr
from services.reply_engine import template_approvals as ta

import test_send_safety_srest_r3_optout as r3
import test_srest_r4_approval as r4
from test_send_safety_srest_r3_optout import APPT, LEAD, world  # noqa: F401 - the r3 world fixture
from test_srest_r4_approval import SLOT

NOW = ta._ct(2030, 1, 7, 9, 0)                 # Monday 09:00 CT
START = ta._ct(2030, 1, 8, 13, 0)              # Tuesday 1:00pm CT
LINK = "https://example.invalid/book"
ZOOM = "https://us06web.zoom.us/j/81234567890"
MEET = "https://meet.google.com/abc-defg-hij"
SLOTS = "Wed 2:00pm or Thu 3:30pm CT"
OFFERS = open(str(ta.BASE_DIR / "config" / "offers.md"), encoding="utf-8").read()
NICHES = ("cleaning", "bookkeeping", "recruiting", "generic")
SHOW_RATE_KEYS = ("confirm_email", "confirm_sms", "preread_email", "reminder_24h_sms", "reminder_24h_email",
                  "reminder_1h_sms", "reminder_15m_sms")
NO_SHOW_KEYS = ("ns_still_on_sms", "ns_still_on_email", "ns_reschedule_email", "ns_d1_other_channel",
                "ns_d3_value_email", "ns_d7_yes_no_email", "ns_d14_breakup_email")


def appt(niche="cleaning", offer="reactivation", **extra):
    a = {"id": "zc-1", "niche": niche, "offer": offer, "booking_url": LINK, "first_name": "Jordan",
         "company": "Brightline Test Co", "zoom_link": ZOOM}
    a.update(extra)
    return {k: v for k, v in a.items() if v is not None}


def sr_copy(key, **kw):
    return sr.render(key, appt(**kw), START, NOW)


def ns_copy(key, slots_text=SLOTS, count=1, **kw):
    return ns.render(key, appt(**kw), START, slots_text, count)


def text_of(copy):
    return (copy.get("subject") or "") + "\n" + copy["body"]


# ------------------------------------------------------------------ item 7
BOOKED_AT = ta._ct(2030, 1, 7, 10, 0)
CALL = ta._ct(2030, 1, 10, 14, 0).isoformat()


def _call():
    return {"id": "zc-appt", "contact_id": "contact-zc", "start_iso": CALL, "email": "lead@example.invalid",
            "first_name": "Jordan", "company": "Brightline Test Co", "booked_at": BOOKED_AT.isoformat(),
            "niche": "cleaning", "offer": "reactivation", "zoom_link": ZOOM}


def _touches(store):
    key = sr.schedule_key("zc-appt", slot_rules.to_tz(slot_rules.parse_iso(CALL)).isoformat())
    return key, dict((t["template_key"], t) for t in store.get(key)["touches"])


def test_item7_an_engine_confirmed_call_skips_the_ladders_confirmation(tmp_path):
    """Held by booking.register_booking, released by approval.send_approved
    (reason "approved") once the engine's own unedited confirming draft is
    out: confirm_email and confirm_sms are skipped, the pre-read goes 15
    minutes after the release."""
    store = JsonFileStore(str(tmp_path / "s.json"))
    sr.hold(store, "zc-appt", reason="awaiting_approval", now=BOOKED_AT)
    sr.ensure_scheduled(store, _call(), BOOKED_AT, a2p=True)
    approved = BOOKED_AT + timedelta(minutes=40)
    out = sr.release_hold(store, "zc-appt", approved, a2p=True, reason="approved")
    assert out["released"] is True and "error" not in out
    key, t = _touches(store)
    for k in ("confirm_email", "confirm_sms"):
        assert t[k]["skipped"] is True and t[k]["skip_reason"] == "engine_confirmation_sent", k
    assert not t["preread_email"]["skipped"]
    assert t["preread_email"]["when_iso"] == (approved + timedelta(minutes=15)).isoformat()
    assert store.get(key)["engine_confirmation_sent_at"] == approved.isoformat()
    # the reminders anchored to the call are untouched
    assert not t["reminder_24h_email"]["skipped"] and not t["reminder_1h_sms"]["skipped"]


def test_item7_a_widget_or_hand_made_booking_keeps_its_confirmation(tmp_path):
    """Never held, never released: the ladder's confirmation is the only one
    the lead gets."""
    store = JsonFileStore(str(tmp_path / "s.json"))
    sr.ensure_scheduled(store, _call(), BOOKED_AT + timedelta(minutes=5), a2p=True)
    _, t = _touches(store)
    assert not t["confirm_email"]["skipped"] and not t["confirm_sms"]["skipped"]


@pytest.mark.parametrize("reason", ["approved_edited", "marked_sent", "released", "manual_release"])
def test_item7_only_the_engines_own_text_counts_as_a_sent_confirmation(tmp_path, reason):
    """Keep on the Edit page ("approved_edited": Lorenzo's words went out),
    Mark sent ("marked_sent": he sent it by hand, the engine never saw it),
    approval.release_show_rate_hold's default and anything else: the
    ladder's own confirmation is re-anchored to the release and goes."""
    store = JsonFileStore(str(tmp_path / "s.json"))
    sr.hold(store, "zc-appt", reason="awaiting_approval", now=BOOKED_AT)
    sr.ensure_scheduled(store, _call(), BOOKED_AT, a2p=True)
    released = BOOKED_AT + timedelta(minutes=40)
    out = sr.release_hold(store, "zc-appt", released, a2p=True, reason=reason)
    assert out["released"] is True and out["reason"] == reason
    key, t = _touches(store)
    for k in ("confirm_email", "confirm_sms"):
        assert not t[k]["skipped"] and t[k]["when_iso"] == released.isoformat(), k
    assert "engine_confirmation_sent_at" not in store.get(key)
    assert sr.ENGINE_CONFIRMED_RELEASE_REASONS == ("approved",)


# item 7 through the approval paths (example.com world): what went out, not
# the tap, decides whether the ladder's confirmation is a duplicate.
ZC_ZOOM = "https://us06web.zoom.us/j/81234567890"


def _held_world_call(st, created):
    """The r4 card that owns the lead's unconfirmed call for SLOT, with its
    held show-rate schedule, as booking.book() leaves them."""
    appt = {"id": APPT, "contact_id": "contact-zc7", "start_iso": SLOT, "email": LEAD, "first_name": "Owner",
            "company": "Example Services", "booked_at": created.isoformat(), "niche": "cleaning",
            "offer": "reactivation", "zoom_link": ZC_ZOOM}
    res = sr.ensure_scheduled(st, appt, created, a2p=True)
    assert res["created"] and st.get(res["key"]).get("held")
    return res["key"]


def _confirmations(st, key):
    touches = dict((t["template_key"], t) for t in st.get(key)["touches"])
    return dict((k, touches[k]) for k in ("confirm_email", "confirm_sms"))


def test_item7_approving_the_engines_unedited_draft_skips_the_ladders_confirmation(world):
    st = world["store"]
    card = r4._booked(st, status="pending")
    key = _held_world_call(st, r4.T_POS)
    out = A.approve(card.token, r3.FakeInstantly(), store=st, now=r3.IN_HOURS, ghl=r3.Recorder())
    assert out["ok"] is True and out["status"] == "sent" and out["show_rate"]["reason"] == "approved"
    for k, t in _confirmations(st, key).items():
        assert t["skipped"] is True and t["skip_reason"] == sr.ENGINE_CONFIRMATION_SKIP, k
    assert st.get(key)["engine_confirmation_sent_at"] == r3.IN_HOURS.isoformat()


def test_item7_keep_on_the_edit_page_keeps_the_ladders_confirmation(world):
    st = world["store"]
    card = r4._booked(st, status="pending")
    key = _held_world_call(st, r4.T_POS)
    body = "Hey Owner,\n\nLocked in for Thu 3:00pm CT, talk then.\n\nLorenzo"
    ed = A.edit(card.token, body, store=st, now=r3.IN_HOURS - timedelta(minutes=5), booking_choice="keep")
    assert ed["ok"] is True and ed["booking_choice"] == "keep"
    out = A.approve(ed["token"], r3.FakeInstantly(), store=st, now=r3.IN_HOURS, ghl=r3.Recorder())
    assert out["ok"] is True and out["status"] == "sent" and out["show_rate"]["reason"] == "approved_edited"
    for k, t in _confirmations(st, key).items():
        assert not t.get("skipped") and t.get("skip_reason") != sr.ENGINE_CONFIRMATION_SKIP, k
    assert _confirmations(st, key)["confirm_email"]["when_iso"] == r3.IN_HOURS.isoformat()
    assert "engine_confirmation_sent_at" not in st.get(key)
    assert not sr.is_held(st, APPT)


def test_item7_mark_sent_keeps_the_ladders_confirmation(world):
    st = world["store"]
    r4._booked(st, status="send_failed")
    key = _held_world_call(st, r4.T_POS)
    out = A.mark_sent_manually("c1", r3.IN_HOURS, store=st, ghl=r3.Recorder())
    assert out["ok"] is True and out["status"] == "sent_manually" and out["show_rate"]["reason"] == "marked_sent"
    for k, t in _confirmations(st, key).items():
        assert not t.get("skipped") and t.get("skip_reason") != sr.ENGINE_CONFIRMATION_SKIP, k
    assert _confirmations(st, key)["confirm_email"]["when_iso"] == r3.IN_HOURS.isoformat()
    assert "engine_confirmation_sent_at" not in st.get(key)
    assert not sr.is_held(st, APPT)


# ------------------------------------------------------------------ item 8
def test_item8_every_show_rate_and_no_show_time_has_am_or_pm():
    lead = pytz.timezone("America/Los_Angeles")
    assert sr.fmt_when(START) == "Tue, Jan 8 at 1:00pm CT"
    assert sr.fmt_when(ta._ct(2030, 1, 8, 12, 5), lead) == "Tue, Jan 8 at 12:05pm CT (10:05am PT)"
    assert sr.fmt_time_only(ta._ct(2030, 1, 8, 16, 30)) == "4:30pm CT"
    assert sr_copy("reminder_24h_email")["subject"] == "Tomorrow at 1:00pm CT, still good?"
    assert "I was on the line at 1:00pm CT" in ns_copy("ns_reschedule_email")["body"]
    block = ta.value_formats_text()
    assert "{time_ct}: 12:05pm CT | 4:30pm CT" in block
    assert "{weekday}" not in block


# ------------------------------------------------------------------ item 12
@pytest.mark.parametrize("niche,terms,offer_sheet", [
    ("cleaning", "$24,000 a year in new cleaning contracts signed within 90 days",
     "$24,000/yr in new cleaning contracts signed within 90 days"),
    ("bookkeeping", "$15,000 in new annual client fees within 90 days",
     "$15,000 in new annual client fees within 90 days"),
    ("recruiting", "$40,000 in new placement fees within 180 days",
     "$40,000 in new placement fees within 180 days"),
])
def test_item12_the_guarantee_bullet_reads_as_a_sentence(niche, terms, offer_sheet):
    body = sr_copy("confirm_email", niche=niche, offer="outbound")["body"]
    assert "- the guarantee (%s) and what it would cost" % terms in body
    assert offer_sheet in OFFERS            # the figures are config/offers.md's


# ------------------------------------------------------------------ item 13
def test_item13_the_sms_confirmation_has_one_parenthetical():
    body = sr_copy("confirm_sms", lead_tz="America/New_York")["body"]
    assert body == ("Hey Jordan, Lorenzo here. We are locked in for a 15-min call on Tue, Jan 8 at 1:00pm CT "
                    "(2:00pm ET). Call link: %s. Reply here if anything changes." % ZOOM)
    assert ") (" not in body


# ------------------------------------------------------------------ item 14
def test_item14_the_second_no_show_keeps_the_call_and_never_offers_writing():
    body = ns_copy("ns_reschedule_email", count=2)["body"]
    assert ("I know this is the second time the timing did not work out, so if a shorter call or a different "
            "day works better, just tell me.") in body
    assert "in writing" not in body and "numbers" not in body


# ------------------------------------------------------------------ item 17
@pytest.mark.parametrize("start", [START, ta._ct(2030, 1, 7, 15, 0), ta._ct(2030, 1, 11, 13, 0)])
def test_item17_the_preread_subject_names_no_weekday(start):
    copy = sr.render("preread_email", appt(), start, NOW)
    assert copy["subject"] == "Before our call: the one-page version"


# ------------------------------------------------------------------ item 21
@pytest.mark.parametrize("key,count", [("ns_reschedule_email", 1), ("ns_reschedule_email", 2),
                                       ("ns_d1_other_channel", 1), ("ns_d3_value_email", 1)])
def test_item21_no_orphan_or_without_the_times(key, count):
    bare = ns_copy(key, slots_text="", count=count)["body"]
    assert "Grab any time that suits you here: %s" % LINK in bare
    assert "Or " not in bare and "Two times" not in bare
    full = ns_copy(key, count=count)["body"]
    assert "Two times that work on my side: %s. Or grab any time here: %s" % (SLOTS, LINK) in full


# ------------------------------------------------------------------ item 22
def test_item22_generic_outbound_gets_outbound_copy():
    body = sr_copy("confirm_email", niche="generic", offer="outbound")["body"]
    for line in ("- who is in market for what you sell right now",
                 "- how the outreach runs under your name and books calls on your calendar",
                 "- the guarantee and what it would cost"):
        assert line in body
    assert "dormant" not in body
    d3 = ns_copy("ns_d3_value_email", niche="generic", offer="outbound")["body"]
    assert ("the first step is the same: watching for the events that put a buyer in the market and putting "
            "those calls on your calendar under your name.") in d3
    assert "went quiet" not in d3
    assert "reactivation" not in ns_copy("ns_d1_other_channel", niche="generic", offer="outbound")["body"]
    # generic reactivation keeps the reactivation copy
    assert "dormant" in sr_copy("confirm_email", niche="generic", offer="reactivation")["body"]


# ------------------------------------------------------------------ item 23
def test_item23_the_confirmation_subject_names_no_company():
    for kw in ({}, {"company": None}, {"lead_tz": "America/Denver"}):
        subject = sr_copy("confirm_email", **kw)["subject"]
        assert subject.startswith("Confirmed: Tue, Jan 8 at 1:00pm CT")
        assert subject.endswith(", 15 minutes with Lorenzo")
        assert "your business" not in subject and "Brightline" not in subject


# ------------------------------------------------------------------ item 24
def test_item24_the_breakup_email_signs_off_plainly():
    for kw in ({}, {"company": None}):
        body = ns_copy("ns_d14_breakup_email", **kw)["body"]
        assert "Best of luck with everything.\n\nLorenzo" in body
        assert "at your business" not in body and "Brightline" not in body


# ------------------------------------------------------------------ item 29
@pytest.mark.parametrize("niche", NICHES)
def test_item29_day_one_says_the_plan(niche):
    body = ns_copy("ns_d1_other_channel", niche=niche)["body"]
    assert "Still happy to walk through the plan for Brightline Test Co." in body
    for word in ("cleaning plan", "bookkeeping plan", "recruiting plan", "reactivation plan"):
        assert word not in body
    idx = ta.catalogue_index()
    assert "no_show.ns_d1_other_channel" in idx
    assert not [i for i in idx if i.startswith("no_show.ns_d1_other_channel.")]


def test_day_seven_has_no_comma_splice():
    body = ns_copy("ns_d7_yes_no_email")["body"]
    assert "Either answer is fine. It just helps me update my notes." in body


# --------------------------------------------------------- the call link
@pytest.mark.parametrize("link", [ZOOM, MEET, None])
@pytest.mark.parametrize("niche,offer", [("cleaning", "reactivation"), ("generic", "outbound")])
def test_lead_facing_copy_never_says_zoom(link, niche, offer):
    for key in SHOW_RATE_KEYS:
        text = text_of(sr_copy(key, niche=niche, offer=offer, zoom_link=link))
        assert "Zoom" not in text and "zoom" not in text.replace(ZOOM, ""), key
        if link:
            assert link in text or key in ("preread_email", "reminder_24h_sms", "reminder_24h_email"), key
    for key in NO_SHOW_KEYS:
        text = text_of(ns_copy(key, niche=niche, offer=offer, zoom_link=link))
        assert "Zoom" not in text and "zoom" not in text.replace(ZOOM, ""), key


def test_no_link_on_file_claims_no_link_in_the_message():
    body = sr_copy("confirm_email", zoom_link=None)["body"]
    assert "Locked in for Tue, Jan 8 at 1:00pm CT. The calendar invite is on its way with the call link.\n" in body
    assert "here it is too" not in body
    for key in ("confirm_sms", "reminder_1h_sms", "reminder_15m_sms"):
        assert "The link is on your calendar invite." in sr_copy(key, zoom_link=None)["body"], key
    for key in ("ns_still_on_sms", "ns_still_on_email"):
        body = ns_copy(key, zoom_link=None)["body"]
        assert "I am on the call now. The link is on your calendar invite." in body, key
    assert sr.call_link_of({"meeting_link": MEET}) == MEET
    assert sr.call_link_of({}) == ""


def test_the_task_for_lorenzo_is_platform_neutral_too():
    for link in (ZOOM, None):
        body = sr_copy("unconfirmed_task", zoom_link=link)["body"]
        assert "Zoom" not in body
        assert ("Call link: %s" % link) in body if link else "The link is on your calendar invite." in body


# ------------------------------------------------- appointments_tick's link pick
@pytest.mark.parametrize("ev,want", [
    ({"address": ZOOM}, ZOOM),
    ({"address": "Suite 200", "meetingLocation": ZOOM}, ZOOM),
    ({"address": MEET}, MEET),
    ({"meetingLocation": MEET}, MEET),
    ({"address": MEET, "meetingLocation": ZOOM}, ZOOM),               # Zoom first, as before
    ({"meetingLocation": "Google Meet"}, None),                        # free text is not a link
    ({"meetingLocation": "call me at 555 0100"}, None),
    ({"address": "http://meet.google.com/abc-defg-hij"}, None),       # https only
    ({"address": "javascript:alert(1)"}, None),
    ({"address": "%s please join early" % MEET}, None),               # a link plus words is not a bare link
    ({}, None),
])
def test_appointments_tick_picks_only_a_bare_https_call_link(ev, want):
    assert tick_job.call_link(ev) == want
    full = dict(ev, id="ev-1", startTime="2030-01-08T13:00:00-06:00", title="Discovery Call - Jordan Lee")
    assert tick_job.normalise_ghl_event(full)["zoom_link"] == want
