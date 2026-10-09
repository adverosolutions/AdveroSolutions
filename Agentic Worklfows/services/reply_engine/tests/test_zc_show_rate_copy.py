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
SHOW_RATE_KEYS = ("confirm_email", "reminder_24h_email", "reminder_morning_email", "reminder_1h_email")
NO_SHOW_KEYS = ("ns_still_on_email", "ns_reschedule_email", "ns_d1_email", "ns_d2_value_email",
                "ns_d3_retry_email", "ns_d5_yes_no_email", "ns_d7_breakup_email", "ns_third_miss_email")


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
    out: confirm_email is skipped, the reminders anchored to the call stay."""
    store = JsonFileStore(str(tmp_path / "s.json"))
    sr.hold(store, "zc-appt", reason="awaiting_approval", now=BOOKED_AT)
    sr.ensure_scheduled(store, _call(), BOOKED_AT, a2p=True)
    approved = BOOKED_AT + timedelta(minutes=40)
    out = sr.release_hold(store, "zc-appt", approved, a2p=True, reason="approved")
    assert out["released"] is True and "error" not in out
    key, t = _touches(store)
    assert t["confirm_email"]["skipped"] is True and t["confirm_email"]["skip_reason"] == "engine_confirmation_sent"
    assert store.get(key)["engine_confirmation_sent_at"] == approved.isoformat()
    # the reminders anchored to the call are untouched
    assert not t["reminder_24h_email"]["skipped"] and not t["reminder_1h_email"]["skipped"]


def test_item7_a_widget_or_hand_made_booking_keeps_its_confirmation(tmp_path):
    """Never held, never released: the ladder's confirmation is the only one
    the lead gets."""
    store = JsonFileStore(str(tmp_path / "s.json"))
    sr.ensure_scheduled(store, _call(), BOOKED_AT + timedelta(minutes=5), a2p=True)
    _, t = _touches(store)
    assert not t["confirm_email"]["skipped"]


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
    for k in ("confirm_email",):
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
    return dict((k, touches[k]) for k in ("confirm_email",))


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
    assert sr_copy("reminder_1h_email")["subject"] == "See you at 1:00pm CT"
    assert sr_copy("reminder_1h_email", lead_tz="America/New_York")["subject"] == "See you at 1:00pm CT (2:00pm ET)"
    block = ta.value_formats_text()
    assert "{time_ct}: 12:05pm CT | 4:30pm CT" in block
    assert "{weekday}" not in block


# ------------------------------------------------------------------ item 12
@pytest.mark.parametrize("niche", ["cleaning", "bookkeeping", "recruiting", "generic"])
def test_item12_the_confirmation_quotes_no_guarantee(niche):
    """The agenda Lorenzo approved on 2026-09-24 drops the guarantee bullet:
    terms are for the call, not the confirmation."""
    body = sr_copy("confirm_email", niche=niche, offer="outbound")["body"]
    assert "guarantee" not in body and "$" not in body


# ------------------------------------------------------------------ item 14
def test_item14_the_second_no_show_keeps_the_call_and_never_offers_writing():
    body = ns_copy("ns_reschedule_email", count=2)["body"]
    assert "Looks like I missed you again on today's call." in body
    assert "If you still want to talk, I can do %s." % SLOTS in body
    assert "in writing" not in body and "numbers" not in body


# ------------------------------------------------------------------ item 21
@pytest.mark.parametrize("key,count", [("ns_reschedule_email", 1), ("ns_reschedule_email", 2),
                                       ("ns_d1_email", 1), ("ns_d2_value_email", 1), ("ns_d3_retry_email", 1),
                                       ("ns_d5_yes_no_email", 1)])
def test_item21_no_times_is_never_sendable_and_never_a_link(key, count):
    bare = ns_copy(key, slots_text="", count=count)
    assert ns.unfilled(bare) == "no_slots"  # the slot email waits for two held times
    full = ns_copy(key, count=count)["body"]
    assert SLOTS in full and LINK not in full and "http" not in full


# ------------------------------------------------------------------ item 22
def test_item22_generic_outbound_gets_outbound_copy():
    body = sr_copy("confirm_email", niche="generic", offer="outbound")["body"]
    for line in ("- your company, who you sell to, and how you bring work in today",
                 "a concrete plan for getting in front of new customers."):
        assert line in body
    assert "past customers" not in body
    # no niche on file: no approved N5 line, never a generic one
    assert ns.unfilled(ns_copy("ns_d2_value_email", niche="generic", offer="outbound")) == "no_niche_point"
    assert "watch for new leases" in ns_copy("ns_d2_value_email", niche="cleaning", offer="outbound")["body"]
    # generic reactivation keeps the reactivation copy
    assert "winning those customers back" in sr_copy("confirm_email", niche="generic", offer="reactivation")["body"]


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
        body = ns_copy("ns_d7_breakup_email", **kw)["body"]
        assert body.endswith("just reply here and I'll send over a couple of times.\n\nLorenzo")
        assert "at your business" not in body and "Brightline" not in body


# ------------------------------------------------------------------ item 29
@pytest.mark.parametrize("niche", NICHES)
def test_item29_day_one_is_one_email_for_every_niche(niche):
    body = ns_copy("ns_d1_email", niche=niche)["body"]
    assert "Those two times got taken, but I can do %s if you still want to find 15 minutes." % SLOTS in body
    for word in ("cleaning plan", "bookkeeping plan", "recruiting plan", "reactivation plan"):
        assert word not in body
    idx = ta.catalogue_index()
    assert "no_show.ns_d1_email" in idx
    assert not [i for i in idx if i.startswith("no_show.ns_d1_email.")]


def test_day_five_yes_no_has_no_comma_splice():
    body = ns_copy("ns_d5_yes_no_email")["body"]
    assert "A one-word answer is plenty. If it's later, just tell me roughly when." in body


# --------------------------------------------------------- the call link
@pytest.mark.parametrize("link", [ZOOM, MEET, None])
@pytest.mark.parametrize("niche,offer", [("cleaning", "reactivation"), ("generic", "outbound")])
def test_lead_facing_copy_never_says_zoom(link, niche, offer):
    for key in SHOW_RATE_KEYS:
        text = text_of(sr_copy(key, niche=niche, offer=offer, zoom_link=link))
        assert "Zoom" not in text and "zoom" not in text.replace(ZOOM, ""), key
        if link:
            assert link in text, key
    for key in NO_SHOW_KEYS:
        text = text_of(ns_copy(key, niche=niche, offer=offer, zoom_link=link))
        assert "Zoom" not in text and "zoom" not in text.replace(ZOOM, ""), key


def test_no_link_on_file_claims_no_link_in_the_message():
    body = sr_copy("confirm_email", zoom_link=None)["body"]
    assert "Locked in for Tue, Jan 8 at 1:00pm CT. The calendar invite is on its way with the call link.\n" in body
    assert "here it is too" not in body
    for key, where in (("reminder_24h_email", "The link is on your calendar invite."),
                       ("reminder_morning_email", "The link's on your calendar invite."),
                       ("reminder_1h_email", "The call link is on the calendar invite from when we booked.")):
        assert where in sr_copy(key, zoom_link=None)["body"], key
    body = ns_copy("ns_still_on_email", zoom_link=None)["body"]
    assert "I'm on the call now. The link is on your calendar invite." in body
    assert sr.call_link_of({"meeting_link": MEET}) == MEET
    assert sr.call_link_of({}) == ""


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
