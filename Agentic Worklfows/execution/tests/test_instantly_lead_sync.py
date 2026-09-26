"""execution/instantly_lead_sync.py: the Instantly -> CRM stage mapping and the
sync flow, on recorded leads.

Inputs: execution/tests/fixtures/instantly_leads_recorded_2026-09-25.json (the
Instantly MCP list_leads, 5 per filter, PII scrubbed, every enum/count/timestamp
kept) and config/snapshots/instantly_replied_leads_2026-09-21.json. Every HTTP
call is a fake patched over ``requests`` inside instantly_api; Google auth and
the spreadsheet are fakes. Nothing here reaches Instantly or Google.

The bug these pin: until 2026-09-25 determine_crm_stage read ``esp_code`` (the
recipient's email PROVIDER: 1 Google, 2 Microsoft, 3 Zoho, ...) as a delivery
status, read lead ``status`` 3 (Completed) as "replied" and treated
``lt_interest_status`` 0 (Out of Office) as a neutral reply.
"""
import copy
import json
import os
import sys

import pytest

EXEC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.dirname(EXEC_DIR)
if EXEC_DIR not in sys.path:
    sys.path.insert(0, EXEC_DIR)

import instantly_api  # noqa: E402
import instantly_lead_sync as ils  # noqa: E402

RECORDED = os.path.join(EXEC_DIR, "tests", "fixtures", "instantly_leads_recorded_2026-09-25.json")
SNAPSHOT = os.path.join(ROOT, "config", "snapshots", "instantly_replied_leads_2026-09-21.json")

# Every documented esp_code value (list-leads.md / get-lead.md).
ESP_CODES = (0, 1, 2, 3, 8, 9, 10, 12, 13, 999, 1000)
ABSENT = object()


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


REC = _load(RECORDED)
SNAP_LEADS = _load(SNAPSHOT)["items"]
FILTERS = [k for k in REC if not k.startswith("_")]


def recorded(filter_name, index=0):
    """A deep copy of one recorded lead, safe to edit."""
    return copy.deepcopy(REC[filter_name][index])


def all_recorded_leads():
    out = []
    for name in FILTERS:
        for i, lead in enumerate(REC[name]):
            out.append(("%s[%d]" % (name, i), lead))
    for i, lead in enumerate(SNAP_LEADS):
        out.append(("snapshot_2026-09-21[%d]" % i, lead))
    return out


def _old_determine_crm_stage(lead):
    """The mapping as it was before 2026-09-25, verbatim in behaviour, kept only
    so the regression tests below prove what the old code returned."""
    status = lead.get("status", 0)
    esp_code = lead.get("esp_code", 0)
    reply_count = lead.get("email_reply_count", 0)
    interest = lead.get("lt_interest_status")
    if status == 3 or reply_count > 0:
        if interest == 1:
            return "Replied - Positive"
        elif interest in (-1, -2):
            return "Closed - Lost"
        return "Replied - Neutral"
    if interest == 1:
        return "Replied - Positive"
    if interest in (-1, -2):
        return "Closed - Lost"
    if status == -1 or esp_code == 3:
        return "Closed - Lost"
    if esp_code == 2 and status == 1:
        return "Contacted"
    return None


# ------------------------------------------------------------ fixture sanity
def test_recorded_fixture_matches_the_documented_enums():
    """If Instantly's data ever contradicts the docs, this fails first."""
    assert set(FILTERS) == set(REC["_meta"]["filters"])
    assert all(l["status"] == -1 for l in REC["FILTER_VAL_BOUNCED"])
    assert all(l["status"] == -2 for l in REC["FILTER_VAL_UNSUBSCRIBED"])
    assert all(l["status"] == 1 and not ils.was_contacted(l) for l in REC["FILTER_VAL_NOT_CONTACTED"])
    assert all(l["status"] == 3 and l["email_reply_count"] == 0 for l in REC["FILTER_VAL_COMPLETED_NO_REPLY"])
    assert all(l["email_reply_count"] > 0 for l in REC["FILTER_VAL_REPLIED"])
    assert all(l["lt_interest_status"] == 0 for l in REC["FILTER_LEAD_OUT_OF_OFFICE"])
    assert REC["FILTER_VAL_SKIPPED"] == []
    for name in FILTERS:
        for lead in REC[name]:
            assert lead["email"].endswith(".test")  # scrubbed


# ------------------------------------------------------ 1. esp_code invariance
@pytest.mark.parametrize("label,lead", all_recorded_leads(), ids=[x[0] for x in all_recorded_leads()])
def test_esp_code_never_changes_the_stage(label, lead):
    results = set()
    for esp in ESP_CODES + (ABSENT,):
        variant = copy.deepcopy(lead)
        if esp is ABSENT:
            variant.pop("esp_code", None)
        else:
            variant["esp_code"] = esp
        results.add(ils.determine_crm_stage(variant))
    assert len(results) == 1, "%s: stage depends on esp_code: %r" % (label, results)


# ------------------------------------------------------- 2. named regressions
def _active_contacted(esp_code):
    """A recorded completed-no-reply lead (contact timestamps present, 0 replies,
    no interest) turned into an ACTIVE one: ``status`` 3 -> 1, and ``esp_code``
    set to the provider under test. Only those two fields change; no Active
    contacted no-reply lead came back from the recording."""
    lead = recorded("FILTER_VAL_COMPLETED_NO_REPLY", 0)
    lead["status"] = 1
    lead["esp_code"] = esp_code
    assert ils.was_contacted(lead) and lead["email_reply_count"] == 0 and lead.get("lt_interest_status") is None
    return lead


def test_zoho_active_contacted_lead_is_contacted_not_closed_lost():
    lead = _active_contacted(3)  # 3 = Zoho
    assert _old_determine_crm_stage(lead) == "Closed - Lost"
    assert ils.determine_crm_stage(lead) == "Contacted"


def test_microsoft_active_lead_without_contact_is_left_alone():
    # Recorded as-is: FILTER_VAL_NOT_CONTACTED, status 1, esp_code 2 (Microsoft),
    # empty status_summary, no contact timestamps. Nothing changed.
    lead = next(l for l in REC["FILTER_VAL_NOT_CONTACTED"] if l["esp_code"] == 2)
    assert lead["status"] == 1 and not ils.was_contacted(lead)
    assert _old_determine_crm_stage(lead) == "Contacted"
    assert ils.determine_crm_stage(lead) is None


def test_google_active_contacted_lead_is_contacted():
    lead = _active_contacted(1)  # 1 = Google
    assert _old_determine_crm_stage(lead) is None
    assert ils.determine_crm_stage(lead) == "Contacted"


def test_completed_with_no_reply_is_contacted_not_replied():
    # Recorded as-is: status 3 (Completed), 0 replies.
    lead = recorded("FILTER_VAL_COMPLETED_NO_REPLY", 0)
    assert lead["status"] == 3 and lead["email_reply_count"] == 0
    assert _old_determine_crm_stage(lead) == "Replied - Neutral"
    assert ils.determine_crm_stage(lead) == "Contacted"


def test_out_of_office_reply_is_contacted_not_replied():
    # Recorded as-is: FILTER_LEAD_OUT_OF_OFFICE, status 3, 1 reply, interest 0.
    lead = next(l for l in REC["FILTER_LEAD_OUT_OF_OFFICE"] if l["status"] == 3)
    assert lead["lt_interest_status"] == 0 and lead["email_reply_count"] > 0
    assert _old_determine_crm_stage(lead) == "Replied - Neutral"
    assert ils.determine_crm_stage(lead) == "Contacted"


@pytest.mark.parametrize("interest,stage", sorted(ils.INTEREST_TO_STAGE.items()))
def test_each_interest_status_maps_to_its_stage(interest, stage):
    # Recorded out-of-office lead (status 3, 1 reply); only lt_interest_status changes.
    lead = recorded("FILTER_LEAD_OUT_OF_OFFICE", 0)
    lead["lt_interest_status"] = interest
    assert ils.determine_crm_stage(lead) == stage


def test_interest_table_is_the_documented_one():
    assert ils.INTEREST_TO_STAGE == {
        1: "Replied - Positive", 2: "Meeting Scheduled", 3: "Meeting Scheduled", 4: "Closed - Won",
        -1: "Closed - Lost", -2: "Closed - Lost", -3: "Closed - Lost", -4: "No-Show",
    }


def test_skipped_status_is_no_change():
    # Recorded completed-no-reply lead (contact evidence present); only status -> -3 (Skipped).
    lead = recorded("FILTER_VAL_COMPLETED_NO_REPLY", 0)
    lead["status"] = -3
    assert ils.determine_crm_stage(lead) is None


def test_reply_with_unset_or_custom_interest_is_replied_neutral():
    # Recorded replied lead with no lt_interest_status key.
    lead = next(l for l in REC["FILTER_VAL_REPLIED"] if "lt_interest_status" not in l)
    assert ils.determine_crm_stage(lead) == "Replied - Neutral"
    custom = copy.deepcopy(lead)
    custom["lt_interest_status"] = 77  # a workspace custom value: not in the table
    assert ils.determine_crm_stage(custom) == "Replied - Neutral"


def test_was_contacted_tolerates_missing_and_malformed_fields():
    assert not ils.was_contacted({})
    assert not ils.was_contacted({"timestamp_last_contact": None, "last_step_timestamp_executed": ""})
    for summary in (None, "x", [], {}, {"lastStep": None}, {"lastStep": "x"},
                    {"lastStep": {}}, {"lastStep": {"timestamp_executed": None}},
                    {"lastStep": {"timestamp_executed": "  "}}):
        assert not ils.was_contacted({"status_summary": summary})
    assert ils.was_contacted({"timestamp_last_contact": "2026-09-15T16:24:04.702Z"})
    assert ils.was_contacted({"last_step_timestamp_executed": "2026-09-15T16:24:04.702Z"})
    assert ils.was_contacted({"status_summary": {"lastStep": {"timestamp_executed": "2026-09-15T16:24:04.637Z"}}})


# ------------------------------------------------ 3. every recorded group
def test_every_recorded_bounce_is_closed_lost():
    assert REC["FILTER_VAL_BOUNCED"]
    for lead in REC["FILTER_VAL_BOUNCED"]:
        assert ils.determine_crm_stage(lead) == "Closed - Lost", lead["email"]


def test_every_recorded_unsubscribe_is_closed_lost():
    assert REC["FILTER_VAL_UNSUBSCRIBED"]
    for lead in REC["FILTER_VAL_UNSUBSCRIBED"]:
        assert ils.determine_crm_stage(lead) == "Closed - Lost", lead["email"]


def test_every_recorded_not_contacted_lead_is_no_change():
    for lead in REC["FILTER_VAL_NOT_CONTACTED"]:
        assert ils.determine_crm_stage(lead) is None, lead["email"]


@pytest.mark.parametrize("group", ["FILTER_VAL_COMPLETED_NO_REPLY", "FILTER_VAL_CONTACTED"])
def test_every_recorded_completed_no_reply_lead_is_contacted(group):
    for lead in REC[group]:
        expected = ils.INTEREST_TO_STAGE.get(lead.get("lt_interest_status"), "Contacted")
        assert ils.determine_crm_stage(lead) == expected, lead["email"]


def test_recorded_replied_and_out_of_office_leads():
    def stages(group):
        return [(l["status"], l.get("lt_interest_status"), ils.determine_crm_stage(l)) for l in REC[group]]

    assert stages("FILTER_VAL_REPLIED") == [
        (3, -3, "Closed - Lost"),       # Lost
        (3, None, "Replied - Neutral"),
        (3, -1, "Closed - Lost"),       # Not Interested
        (3, 0, "Contacted"),            # Out of Office auto-reply
        (3, None, "Replied - Neutral"),
    ]
    assert stages("FILTER_LEAD_OUT_OF_OFFICE") == [
        (3, 0, "Contacted"),
        (3, 0, "Contacted"),
        (3, 0, "Contacted"),
        (-1, 0, "Closed - Lost"),       # auto-reply, then the address bounced
        (3, 0, "Contacted"),
    ]


# ------------------------------------------------------- 4. sync end to end
class FakeResponse(object):
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return copy.deepcopy(self._payload)


class FakeTransport(object):
    """Stands in for requests.get / requests.post inside instantly_api."""

    def __init__(self, campaign_pages, lead_pages):
        self.campaign_pages = list(campaign_pages)
        self.lead_pages = list(lead_pages)
        self.gets = []
        self.posts = []

    def get(self, url, params=None, headers=None, **kwargs):
        self.gets.append((url, dict(params or {})))
        assert url.endswith("/api/v2/campaigns"), url
        return FakeResponse(self.campaign_pages.pop(0))

    def post(self, url, json=None, headers=None, **kwargs):
        self.posts.append((url, dict(json or {})))
        assert url.endswith("/api/v2/leads/list"), url
        return FakeResponse(self.lead_pages.pop(0))


class FakeWorksheet(object):
    def __init__(self, values):
        self.values = values
        self.batch_updates = []

    def get_all_values(self):
        return copy.deepcopy(self.values)

    def batch_update(self, data, value_input_option=None):
        self.batch_updates.append((copy.deepcopy(data), value_input_option))
        return {}


class FakeSpreadsheet(object):
    def __init__(self, tabs):
        self.tabs = tabs

    def worksheet(self, name):
        if name not in self.tabs:
            import gspread

            raise gspread.exceptions.WorksheetNotFound(name)
        return self.tabs[name]


HEADERS = ["Stage", "Business", "First Name", "Last Name", "Email", "Phone", "City", "State",
           "Website", "Industry", "Source", "Campaign", "Owner", "Created", "Next Action",
           "Last Updated", "Notes"]
assert HEADERS.index("Email") == ils.COL_EMAIL - 1 and HEADERS.index("Last Updated") == ils.COL_LAST_UPDATED - 1


def _row(stage, email):
    row = [""] * len(HEADERS)
    row[0] = stage
    row[4] = email
    row[15] = "2026-09-01"
    return row


@pytest.fixture
def world(monkeypatch):
    """Three recorded leads in "HVAC Instant Response v1" and their CRM rows."""
    zoho = _active_contacted(3)                       # contacted, Zoho-hosted
    microsoft = next(copy.deepcopy(l) for l in REC["FILTER_VAL_NOT_CONTACTED"] if l["esp_code"] == 2)
    bounce = recorded("FILTER_VAL_BOUNCED", 0)        # status -1, recorded as-is
    stranger = recorded("FILTER_VAL_COMPLETED_NO_REPLY", 1)  # not in the CRM

    transport = FakeTransport(
        campaign_pages=[
            {"items": [{"id": "camp-other", "name": "Some Unmapped Campaign"}],
             "next_starting_after": "camp-other"},
            {"items": [{"id": "camp-hvac", "name": "HVAC Instant Response v1"}]},
        ],
        lead_pages=[
            {"items": [zoho, microsoft], "next_starting_after": microsoft["id"]},
            {"items": [bounce, stranger]},
        ],
    )
    monkeypatch.setattr(instantly_api.requests, "get", transport.get)
    monkeypatch.setattr(instantly_api.requests, "post", transport.post)

    sheet = FakeWorksheet([
        HEADERS,
        _row("New/Uncontacted", zoho["email"]),        # row 2
        _row("New/Uncontacted", microsoft["email"]),   # row 3
        _row("Contacted", bounce["email"]),            # row 4
    ])
    spreadsheet = FakeSpreadsheet({"HVAC Leads": sheet})

    class FakeCredentials(object):
        @staticmethod
        def from_service_account_file(path, scopes=None):
            return "fake-creds"

    class FakeClient(object):
        def open_by_key(self, key):
            assert key == "fake-sheet-id"
            return spreadsheet

    monkeypatch.setenv("GOOGLE_SHEET_ID", "fake-sheet-id")
    monkeypatch.setattr(ils, "Credentials", FakeCredentials)
    monkeypatch.setattr(ils.gspread, "authorize", lambda creds: FakeClient())
    assert ils.CAMPAIGN_TO_SHEET["HVAC Instant Response v1"] == "HVAC Leads"
    return {"transport": transport, "sheet": sheet, "zoho": zoho, "microsoft": microsoft, "bounce": bounce}


def _assert_transport(transport):
    # Campaigns: two GET pages, the second carrying the first page's cursor.
    assert len(transport.gets) == 2
    assert transport.gets[0][1] == {"limit": 100}
    assert transport.gets[1][1] == {"limit": 100, "starting_after": "camp-other"}
    # Leads: only the mapped campaign, two POST pages, v2 body field `campaign`.
    assert len(transport.posts) == 2
    for _, body in transport.posts:
        assert body["campaign"] == "camp-hvac"
        assert "campaign_id" not in body
    assert "starting_after" not in transport.posts[0][1]
    assert transport.posts[1][1]["starting_after"]


def test_sync_dry_run_writes_nothing(world):
    stats = ils.InstantlyLeadSync().sync(dry_run=True)
    _assert_transport(world["transport"])
    assert world["sheet"].batch_updates == []
    assert [(c["row"], c["from_stage"], c["to_stage"]) for c in stats["changes"]] == [
        (2, "New/Uncontacted", "Contacted"),
        (4, "Contacted", "Closed - Lost"),
    ]
    assert stats["not_in_crm"] == 1


def test_sync_live_writes_only_the_expected_cells(world):
    syncer = ils.InstantlyLeadSync()
    today = syncer._get_timestamp()
    stats = syncer.sync(dry_run=False)
    _assert_transport(world["transport"])
    assert world["sheet"].batch_updates == [([
        {"range": "A2", "values": [["Contacted"]]},       # Zoho-hosted, contacted
        {"range": "P2", "values": [[today]]},
        {"range": "A4", "values": [["Closed - Lost"]]},   # genuine bounce
        {"range": "P4", "values": [[today]]},
    ], "USER_ENTERED")]
    # Row 3 (Microsoft-hosted, never contacted) is untouched.
    assert stats["stages_updated"] == 2 and stats["errors"] == 0
