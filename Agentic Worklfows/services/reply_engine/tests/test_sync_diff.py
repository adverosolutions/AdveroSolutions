"""compute_diff / compute_reverse / compute_value_fixes: pure computations."""
import json
from pathlib import Path

from shared import settings
from services.reply_engine import pipeline_sync as ps

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STAGES = settings.GHL_STAGES
SALES = settings.GHL_SALES_PIPELINE_ID

CLEANING_REACT = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
CLEANING_TRIGGER = "f347604e-48c7-4813-831c-dc7b9d4b50ae"
BOOKKEEPING_REACT = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"


def opp(email, stage_key, oid="opp1", cid="c1", value=None, **extra):
    row = {
        "id": oid,
        "name": "%s (Cold Email)" % email,
        "pipelineId": SALES,
        "pipelineStageId": STAGES[stage_key],
        "status": "won" if stage_key == "won" else ("lost" if stage_key == "lost" else "open"),
        "contactId": cid,
        "contact": {"id": cid, "email": email},
        "monetaryValue": value,
    }
    row.update(extra)
    return row


def lead(email, campaign, lt, first="A", last="B", company="Co"):
    return {"id": "l-" + email, "email": email, "campaign": campaign, "lt_interest_status": lt,
            "first_name": first, "last_name": last, "company_name": company}


def load_leads():
    with open(FIXTURES / "instantly_replied_leads_2026-09.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------- stage map
def test_stage_map_matches_brief():
    assert ps.STAGE_TO_INTEREST == {
        "new_reply": 1, "call_booked": 2, "proposal_sent": 3, "won": 4, "lost": -1, "follow_up_later": -1,
    }
    assert ps.INTEREST_NO_SHOW == -4
    assert ps.INTEREST_WRONG_PERSON == -2


def test_follow_up_later_agrees_with_models_interest_for_label():
    """The router parks a "not now" lead in Follow Up Later and sets Instantly
    -1. If the mirror disagrees it relabels every not-now lead Interested the
    night after the router classified it."""
    from services.reply_engine import models

    assert ps.STAGE_TO_INTEREST["follow_up_later"] == models.INTEREST_FOR_LABEL["negative_notnow"]
    assert models.STAGE_FOR_LABEL["negative_notnow"] == "follow_up_later"


def test_interest_targets_are_all_valid_ids_json_codes():
    codes = set(int(k) for k in settings.IDS["instantly"]["interest_status_codes"])
    produced = set(ps.STAGE_TO_INTEREST.values())
    produced.update({ps.INTEREST_NO_SHOW, ps.INTEREST_WRONG_PERSON, ps.INTEREST_LOST, ps.INTEREST_NOT_INTERESTED})
    assert produced <= codes, produced - codes


def test_stage_key_resolves_by_stage_id_then_status():
    assert ps.stage_key_for(opp("a@x.co", "call_booked")) == "call_booked"
    assert ps.stage_key_for({"pipelineStageId": "unknown", "status": "won"}) == "won"
    assert ps.stage_key_for({"stage": "proposal_sent"}) == "proposal_sent"
    assert ps.stage_key_for({"pipelineStageId": "unknown", "status": "open"}) is None


def test_desired_interest_per_stage():
    assert ps.desired_interest(opp("a@x.co", "new_reply"))[0] == 1
    assert ps.desired_interest(opp("a@x.co", "call_booked"))[0] == 2
    assert ps.desired_interest(opp("a@x.co", "proposal_sent"))[0] == 3
    assert ps.desired_interest(opp("a@x.co", "won"))[0] == 4
    assert ps.desired_interest(opp("a@x.co", "lost"))[0] == -1
    value, reason, note = ps.desired_interest(opp("a@x.co", "follow_up_later"))
    assert value == -1 and "follow_up_later" in reason and note and "Follow Up Later" in note


def test_lost_reason_no_show_or_ghosted_maps_to_no_show_code():
    """-4 is Instantly's no_show (config/ids.json); -3 lost hides a no-show
    among the price losses and leaves the no-show segment empty forever."""
    assert ps.desired_interest(opp("a@x.co", "lost", lostReason="No show x2"))[0] == -4
    assert ps.desired_interest(opp("a@x.co", "lost", lost_reason="ghosted after proposal"))[0] == -4
    assert ps.desired_interest(opp("a@x.co", "lost", customFields=[{"id": "f", "fieldValue": "No-Show"}]))[0] == -4
    assert ps.desired_interest(opp("a@x.co", "lost", lostReason="Price"))[0] == -1
    assert ps.desired_interest(opp("a@x.co", "lost", lostReason="Wrong person, she left the company"))[0] == -2


# ----------------------------------------------------- negative stickiness
def test_a_negative_lead_is_not_relabelled_interested_by_a_stage_mirror():
    """The router set -1 on ignacio's "touch base next month". The nightly
    mirror must not turn that back into Interested."""
    diff = ps.compute_diff([opp("ignacio@ariacleaningservices.com", "follow_up_later")],
                           [lead("ignacio@ariacleaningservices.com", CLEANING_TRIGGER, -1)])
    assert diff == []
    # New Reply is not proof of a re-open either
    assert ps.compute_diff([opp("a@b.co", "new_reply")], [lead("a@b.co", CLEANING_REACT, -1)]) == []
    # a real re-open does move it
    booked = ps.compute_diff([opp("a@b.co", "call_booked")], [lead("a@b.co", CLEANING_REACT, -1)])
    assert [(r["from"], r["to"]) for r in booked] == [(-1, 2)]


def test_wrong_person_is_not_flattened_into_not_interested():
    """-2 wrong_person is a distinct code; a generic Lost must not overwrite it,
    but a Lost that names the wrong person may."""
    assert ps.compute_diff([opp("a@b.co", "lost", lostReason="Budget")], [lead("a@b.co", CLEANING_REACT, -2)]) == []
    named = ps.compute_diff([opp("a@b.co", "lost", lostReason="No show, never joined the Zoom")],
                            [lead("a@b.co", CLEANING_REACT, -1)])
    assert [(r["from"], r["to"]) for r in named] == [(-1, -4)]


def test_a_stale_positive_stage_does_not_overwrite_a_fresh_negative():
    """Nothing moves an opportunity out of Call Booked after the call
    (no_show.py says so), so a lead Lorenzo marks No Show (-4) tonight sits
    against a stage that last moved weeks ago. The mirror read that as a
    re-open, wrote 2 over the -4, and agreed with itself the next night: the
    negative was gone permanently with no alert."""
    stale = opp("ilmi@shiningarmorcleaningnj.com", "call_booked", updatedAt="2026-08-01T12:00:00Z",
                lastStageChangeAt="2026-08-01T12:00:00Z")
    fresh_negative = dict(lead("ilmi@shiningarmorcleaningnj.com", CLEANING_REACT, -4),
                          timestamp_last_reply="2026-09-21T23:00:00Z")
    conflicts = []
    assert ps.compute_diff([stale], [fresh_negative], conflicts=conflicts) == []
    assert len(conflicts) == 1 and conflicts[0]["from"] == -4 and conflicts[0]["to"] == 2
    assert conflicts[0]["reason"].startswith("stale_reopen")
    # the same for -1 and -2
    for code in (-1, -2):
        assert ps.compute_diff([stale], [dict(fresh_negative, lt_interest_status=code)]) == []


def test_a_ghl_move_after_the_negative_still_re_opens_the_lead():
    """The escape hatch has to stay open: a lead marked not interested who then
    books a call really is a re-open."""
    moved = opp("a@b.co", "call_booked", lastStageChangeAt="2026-09-21T23:30:00Z")
    negative = dict(lead("a@b.co", CLEANING_REACT, -1), timestamp_last_reply="2026-09-21T23:00:00Z")
    rows = ps.compute_diff([moved], [negative])
    assert [(r["from"], r["to"]) for r in rows] == [(-1, 2)]
    # and with no timestamps on either side there is nothing to compare, so the
    # old behaviour stands rather than blocking every re-open
    assert [(r["from"], r["to"]) for r in ps.compute_diff([opp("a@b.co", "call_booked")],
                                                          [lead("a@b.co", CLEANING_REACT, -1)])] == [(-1, 2)]


def test_mirror_allowed_compares_the_two_moments_directly():
    import datetime as dt

    older = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
    newer = dt.datetime(2026, 9, 21, tzinfo=dt.timezone.utc)
    assert ps.mirror_allowed(-4, 2, "call_booked", ghl_changed_at=older, negative_set_at=newer)[0] is False
    assert ps.mirror_allowed(-4, 2, "call_booked", ghl_changed_at=newer, negative_set_at=older)[0] is True
    assert ps.mirror_allowed(-4, 2, "call_booked")[0] is True          # nothing to compare
    assert ps.mirror_allowed(1, 2, "call_booked", ghl_changed_at=older, negative_set_at=newer)[0] is True


# ------------------------------------------- two opportunities per contact
def test_duplicate_opportunities_prefer_the_furthest_stage():
    """GHL /opportunities/search does not guarantee an order, so first-wins let
    an old Lost opportunity overwrite a live Call Booked one."""
    booked = opp("ilmi@shiningarmorcleaningnj.com", "call_booked", oid="new")
    lost = opp("ilmi@shiningarmorcleaningnj.com", "lost", oid="old", lostReason="Ghosted")
    leads = [lead("ilmi@shiningarmorcleaningnj.com", CLEANING_REACT, 1)]
    for order in ([booked, lost], [lost, booked]):
        diff = ps.compute_diff(order, leads)
        assert [(r["opportunity_id"], r["to"]) for r in diff] == [("new", 2)], order
    assert ps.pick_opportunity([lost, booked])["id"] == "new"


# --------------------------------------------------------------- diff
def test_compute_diff_emits_only_changes():
    opps = [
        opp("ilmi@shiningarmorcleaningnj.com", "call_booked", oid="o1", cid="c1"),
        opp("sopiosvanishvili@taxfoaccounting.com", "new_reply", oid="o2", cid="c2"),
        opp("tiffany@flowerhillfs.com", "lost", oid="o3", cid="c3", lostReason="Ghosted"),
    ]
    leads = [
        lead("ilmi@shiningarmorcleaningnj.com", CLEANING_REACT, 1),
        lead("sopiosvanishvili@taxfoaccounting.com", BOOKKEEPING_REACT, 1),
        lead("tiffany@flowerhillfs.com", CLEANING_TRIGGER, 1),
    ]
    diff = ps.compute_diff(opps, leads)
    by_email = {d["lead_email"]: d for d in diff}
    assert set(by_email) == {"ilmi@shiningarmorcleaningnj.com", "tiffany@flowerhillfs.com"}
    ilmi = by_email["ilmi@shiningarmorcleaningnj.com"]
    assert ilmi["from"] == 1 and ilmi["to"] == 2 and ilmi["campaign_id"] == CLEANING_REACT
    assert ilmi["reason"] == "ghl_stage:call_booked" and ilmi["opportunity_id"] == "o1" and ilmi["contact_id"] == "c1"
    tiff = by_email["tiffany@flowerhillfs.com"]
    assert tiff["to"] == -4 and "no show" in tiff["reason"]
    for row in diff:
        assert set(row) >= {"lead_email", "campaign_id", "from", "to", "reason"}


def test_compute_diff_one_row_per_campaign_and_case_insensitive():
    opps = [opp("Bob@Acme.com", "won")]
    leads = [lead("bob@acme.com", CLEANING_REACT, 1), lead("bob@acme.com", CLEANING_TRIGGER, 4)]
    diff = ps.compute_diff(opps, leads)
    assert len(diff) == 1
    assert diff[0]["campaign_id"] == CLEANING_REACT and diff[0]["to"] == 4


def test_compute_diff_skips_unknown_stage_and_unknown_email():
    opps = [{"id": "x", "pipelineStageId": "nope", "status": "open", "contact": {"email": "a@b.co"}},
            opp("nobody@x.co", "new_reply")]
    leads = [lead("a@b.co", CLEANING_REACT, 0)]
    assert ps.compute_diff(opps, leads) == []


def test_follow_up_later_carries_note():
    diff = ps.compute_diff([opp("a@b.co", "follow_up_later", cid="c9")], [lead("a@b.co", CLEANING_REACT, 0)])
    assert len(diff) == 1 and diff[0]["to"] == -1 and diff[0]["note"] and diff[0]["contact_id"] == "c9"


# ------------------------------------------------------------ reverse
def test_compute_reverse_finds_positive_leads_without_opportunity():
    leads = load_leads()
    opps = [opp("ilmi@shiningarmorcleaningnj.com", "call_booked"), opp("sopiosvanishvili@taxfoaccounting.com", "new_reply")]
    rows = ps.compute_reverse(opps, leads)
    emails = [r["lead_email"] for r in rows]
    # Tiffany and Ignacio are Interested (1) in Instantly and missing from GHL
    assert emails == ["ignacio@ariacleaningservices.com", "tiffany@flowerhillfs.com"]
    tiff = [r for r in rows if r["lead_email"] == "tiffany@flowerhillfs.com"][0]
    assert tiff["action"] == "create_opportunity" and tiff["stage"] == "new_reply"
    assert tiff["campaign_id"] == CLEANING_TRIGGER and tiff["offer"] == "outbound" and tiff["monetary_value"] == 7500.0
    assert tiff["name"] == "Flowerhill Facility Services - Tiffany Spelman (Cold Email)"
    # negative / neutral leads never create opportunities
    assert "rob@cjsglobal.com" not in emails


def test_an_opportunity_with_no_contact_email_is_not_treated_as_missing():
    """GHL can return a contact created from a booking with no email on it.
    `compute_reverse` keys "already in GHL" on that address, so the lead looks
    missing and a SECOND contact and Call Booked opportunity get proposed for
    a lead whose opportunity is right there in the input."""
    blind = {"id": "oIlmi", "name": "Ilmi", "pipelineStageId": STAGES["call_booked"], "status": "open",
             "contactId": "cIlmi", "contact": {"id": "cIlmi", "name": "Ilmi Curovic"}}
    leads = [lead("ilmi@shiningarmorcleaningnj.com", CLEANING_REACT, 2)]
    assert [o["id"] for o in ps.opportunities_without_email([blind])] == ["oIlmi"]
    # the raw computation still cannot see it, which is exactly why run_sync
    # refuses to apply the reverse check while any such row exists
    assert [r["lead_email"] for r in ps.compute_reverse([blind], leads)] == ["ilmi@shiningarmorcleaningnj.com"]
    assert ps.opportunities_without_email([opp("a@b.co", "new_reply")]) == []


def test_compute_reverse_stage_follows_interest_value():
    leads = [lead("a@b.co", CLEANING_REACT, 2), lead("c@d.co", CLEANING_REACT, 4)]
    rows = {r["lead_email"]: r for r in ps.compute_reverse([], leads)}
    assert rows["a@b.co"]["stage"] == "call_booked" and rows["a@b.co"]["monetary_value"] == 6000.0
    assert rows["a@b.co"]["status"] == "open"
    assert rows["c@d.co"]["stage"] == "won"


def test_a_won_lead_is_not_mirrored_as_open_pipeline_at_a_guessed_value():
    """Instantly 4 is closed-won. Writing it back as an open $6,000 deal
    inflates exactly the pipeline number the sweep orders Lorenzo's day by."""
    rows = {r["lead_email"]: r for r in ps.compute_reverse([], [lead("c@d.co", CLEANING_REACT, 4)])}
    assert rows["c@d.co"]["status"] == "won"
    assert rows["c@d.co"]["monetary_value"] is None
    assert ps.status_for_stage("won") == "won" and ps.status_for_stage("lost") == "lost"
    assert ps.status_for_stage("new_reply") == "open"


# -------------------------------------------------------- value fixes
def test_value_fixes_only_open_opps_without_value():
    opps = [
        opp("a@b.co", "new_reply", oid="o1", value=None),
        opp("c@d.co", "call_booked", oid="o2", value=0),
        opp("e@f.co", "proposal_sent", oid="o3", value=6000),
        opp("g@h.co", "lost", oid="o4", value=None),
    ]
    leads = [lead("a@b.co", CLEANING_TRIGGER, 1), lead("c@d.co", CLEANING_REACT, 2)]
    rows = {r["opportunity_id"]: r for r in ps.compute_value_fixes(opps, leads)}
    assert set(rows) == {"o1", "o2"}
    assert rows["o1"]["monetary_value"] == 7500.0 and rows["o1"]["offer"] == "outbound"
    assert rows["o2"]["monetary_value"] == 6000.0 and rows["o2"]["stage"] == "call_booked"


def test_value_fixes_skip_unknown_stage():
    """compute_diff already skips an unknown stage; compute_value_fixes used to
    emit stage None, which apply() then defaulted to New Reply, dragging a live
    deal back to the top of the funnel as a side effect of setting a value."""
    unknown = {"id": "ox", "name": "X", "pipelineStageId": "a-stage-not-in-ids-json", "status": "open",
               "contactId": "cx", "contact": {"id": "cx", "email": "x@y.co"}, "monetaryValue": None}
    assert ps.compute_diff([unknown], [lead("x@y.co", CLEANING_REACT, 1)]) == []
    assert ps.compute_value_fixes([unknown], []) == []


def test_value_fixes_flag_a_contact_with_two_opportunities():
    opps = [opp("dup@acme.com", "new_reply", oid="o1", cid="cdup"),
            opp("dup@acme.com", "proposal_sent", oid="o2", cid="cdup")]
    rows = {r["opportunity_id"]: r for r in ps.compute_value_fixes(opps, [])}
    assert set(rows) == {"o1", "o2"}
    assert all(r["ambiguous_contact"] for r in rows.values())
    assert rows["o2"]["stage_id"] == STAGES["proposal_sent"]


def test_defaults_documented_in_config_constants():
    assert ps.OPPORTUNITY_VALUE_DEFAULTS == {"reactivation": 6000.0, "outbound": 7500.0}
    assert ps.default_value_for_campaign("unknown-campaign") == 6000.0
    assert ps.default_value_for_campaign(CLEANING_TRIGGER) == 7500.0
