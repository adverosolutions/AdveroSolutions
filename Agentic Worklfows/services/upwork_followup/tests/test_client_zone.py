"""client_zone: which zone a jd.txt location sentence means, and its label.
Invented clients only; no network."""
from datetime import datetime, timezone

import pytest

from services.upwork_followup import client_zone
from services.upwork_followup.client_zone import ZoneInfo, label, resolve, resolve_text


@pytest.mark.parametrize("location,zone", [
    # DC, with or without the comma and periods, beats Washington state
    ("Client in Washington, DC, US (America/New_York)", "America/New_York"),
    ("Client in Washington DC", "America/New_York"),
    ("Client in Washington D.C.", "America/New_York"),
    ("Client in Washington D.C", "America/New_York"),          # as the old collect regex cut it
    ("Client in Washington, D.C., USA", "America/New_York"),
    ("Client in D.C.", "America/New_York"),
    ("Client in Washington DC, timezone UTC", "America/New_York"),
    ("Client in Washington, US", "America/Los_Angeles"),       # the state
    # the place stated first wins; a description after it is not a place
    ("Client in Ohio, US, a staffing agency that hires from the Philippines", "America/New_York"),
    # a US state name or code beats a world city
    ("Dublin, Ohio (US)", "America/New_York"),
    ("Client in Dublin, Ohio (US)", "America/New_York"),
    ("Client in Paris, TX", "America/Chicago"),
    ("Client in Dublin, OH", "America/New_York"),
    ("Client in the United States (NJ)", "America/New_York"),
    # world cities still work on their own or with their own country
    ("Client in Paris, France", "Europe/Paris"),
    ("Client in Dublin", "Europe/Dublin"),
    ("Client in Sydney, Australia", "Australia/Sydney"),
    ("Client in Punjab, Pakistan, brand new account (0 contracts)", "Asia/Karachi"),
])
def test_first_stated_place_wins(location, zone):
    assert resolve_text(location) == (zone, "location")


@pytest.mark.parametrize("location", [
    "Client in Panama, a firm that hires from the Philippines",    # Panama is not in the table
    "Client in London, Canada",                                    # a city outside the named country
    "Client in Paris, US",                                         # a US marker keeps US places only
    "client in United States",
])
def test_no_place_when_the_first_location_names_none(location):
    assert resolve_text(location) == (None, client_zone.DEFAULT_SOURCE)


def test_a_bracketed_iana_zone_in_the_same_country_wins():
    """Indiana is mostly ET; the job page said Chicago."""
    assert resolve_text("Client in Indiana, US (America/Chicago)") == ("America/Chicago", "location")
    assert resolve_text("Client in Virginia, US (America/New_York)") == ("America/New_York", "location")
    # another country: the place wins
    assert resolve_text("Client in Ukraine (Asia/Jerusalem)")[0] in ("Europe/Kiev", "Europe/Kyiv")
    assert resolve_text("Client in Ohio (Europe/London)") == ("America/New_York", "location")
    # no place, only the bracket
    assert resolve_text("Client in the US (America/New_York), practice in South Florida") == (
        "America/New_York", "timezone")


def test_location_still_beats_an_account_time_zone():
    assert resolve_text("Client in California (US), timezone America/New_York") == (
        "America/Los_Angeles", "location")
    assert resolve_text("Client in Nevada (US), timezone Chicago") == ("America/Los_Angeles", "location")
    assert resolve_text("Client in United States, timezone Chicago") == ("America/Chicago", "timezone")


def test_resolve_reads_the_location_before_a_room_time_zone():
    room = {"client_timezone": "Europe/Paris", "job": {"client_location": "Client in Ohio (US)"}}
    assert resolve(room) == (ZoneInfo("America/New_York"), "location")
    # no place: the room's stated zone, before a zone the text states
    room = {"client_timezone": "Europe/Paris",
            "job": {"client_location": "Client in the US, timezone Chicago"}}
    assert resolve(room) == (ZoneInfo("Europe/Paris"), "timezone")
    assert resolve({"job": {"client_location": "Client in the US, timezone Chicago"}}) == (
        ZoneInfo("America/Chicago"), "timezone")
    assert resolve({"client_timezone": "Europe/Paris"}) == (ZoneInfo("Europe/Paris"), "timezone")
    assert resolve({}) == (ZoneInfo("America/Chicago"), client_zone.DEFAULT_SOURCE)


@pytest.mark.parametrize("key,expected", [
    ("America/Phoenix", "Arizona time"),
    ("America/Regina", "Saskatchewan time"),
    ("America/Denver", "MT"),
    ("America/Chicago", "CT"),
])
def test_zones_without_dst_keep_their_own_label_in_summer(key, expected):
    """July: Arizona matches PT and Saskatchewan matches MT, so "MT" and "CT"
    would be an hour off."""
    zone = ZoneInfo(key)
    assert label(datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc), zone) == expected
    assert label(datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc), zone) == expected
