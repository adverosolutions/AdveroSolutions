"""Guarded apply: shadow -> would_do with zero HTTP; live (mocked) -> HTTP.
Also run_sync end to end on fixtures and the CLI."""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from shared import job_log, settings
from shared.ghl import GHL
from shared.instantly import Instantly
from services.reply_engine import pipeline_sync as ps

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STAGES = settings.GHL_STAGES
NOW = datetime(2026, 9, 22, 2, 10, tzinfo=timezone.utc)  # 2026-09-21T21:10-05:00

CLEANING_REACT = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
BOOKKEEPING_REACT = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"


class Recorder(object):
    def __init__(self, handler=None):
        self.requests = []
        self.handler = handler

    def __call__(self, request):
        self.requests.append(request)
        if self.handler:
            return self.handler(request)
        return httpx.Response(200, json={"ok": True})


def load(name):
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def opp(email, stage_key, oid="opp1", cid="c1", value=None, **extra):
    row = {"id": oid, "name": "%s (Cold Email)" % email, "pipelineStageId": STAGES[stage_key],
           "status": "open", "contactId": cid, "contact": {"id": cid, "email": email}, "monetaryValue": value}
    row.update(extra)
    return row


def lead(email, campaign, lt, **kw):
    row = {"id": "l-" + email, "email": email, "campaign": campaign, "lt_interest_status": lt,
           "first_name": "A", "last_name": "B", "company_name": "Co"}
    row.update(kw)
    return row


# ------------------------------------------------------------- shadow
def test_apply_in_shadow_makes_no_http_and_returns_would_do(tmp_env, shadow_mode):
    rec_i, rec_g = Recorder(), Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec_i))
    ghl = GHL(token="t", transport=httpx.MockTransport(rec_g))
    diff = [{"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": 2, "reason": "ghl_stage:call_booked",
             "contact_id": "c1", "note": None},
            {"lead_email": "f@g.co", "campaign_id": CLEANING_REACT, "from": 0, "to": 1, "reason": "ghl_stage:follow_up_later",
             "contact_id": "c2", "note": "Pipeline sync: follow up later"}]
    reverse = [{"action": "create_opportunity", "lead_email": "t@f.co", "campaign_id": CLEANING_REACT, "interest": 1,
                "stage": "new_reply", "name": "T (Cold Email)", "first_name": "T", "last_name": "F", "company": "F",
                "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"}]
    fixes = [{"action": "set_value", "opportunity_id": "o9", "contact_id": "c9", "lead_email": "z@z.co",
              "campaign_id": None, "stage": "new_reply", "name": "Z", "monetary_value": 6000.0, "offer": "reactivation",
              "reason": "x"}]

    out = ps.apply(diff, instantly, ghl=ghl, reverse=reverse, value_fixes=fixes)

    assert rec_i.requests == [] and rec_g.requests == []
    assert out["done"] == 0 and out["errors"] == []
    # 2 interest updates + 1 reverse (opportunity outcome) + 1 value fix
    assert out["would_do"] == 4
    outcomes = [r["outcome"] for r in out["results"]]
    assert outcomes == ["would_do"] * 4
    follow_up = out["results"][1]
    assert follow_up["note_outcome"] == "would_do"
    assert out["results"][2]["contact_outcome"] == "would_do"

    records = job_log.read_shadow_log()
    actions = [(r["system"], r["action"]) for r in records]
    assert ("instantly", "update_interest_status") in actions
    assert ("ghl", "create_note") in actions
    assert ("ghl", "upsert_contact") in actions
    # the reverse row creates an opportunity; the value fix goes through
    # GHL.update_opportunity_value (PUT /opportunities/{id} with monetaryValue
    # only), so it can never move a deal or hit a sibling opportunity.
    assert actions.count(("ghl", "upsert_opportunity")) == 1
    assert actions.count(("ghl", "update_opportunity_value")) == 1
    interest = [r for r in records if r["action"] == "update_interest_status"][0]
    assert interest["payload"] == {"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "interest_value": 2}
    opp_rec = [r for r in records if r["action"] == "upsert_opportunity"][0]
    assert opp_rec["payload"]["monetaryValue"] == 6000.0
    assert opp_rec["payload"]["pipelineStageId"] == STAGES["new_reply"]
    value_rec = [r for r in records if r["action"] == "update_opportunity_value"][0]
    assert value_rec["payload"] == {"monetaryValue": 6000.0, "opportunity_id": "o9"}


def test_apply_shadow_without_ghl_token_still_records_intent(tmp_env, shadow_mode):
    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    reverse = [{"action": "create_opportunity", "lead_email": "t@f.co", "campaign_id": CLEANING_REACT, "interest": 1,
                "stage": "new_reply", "name": "T", "first_name": "T", "last_name": "F", "company": "F",
                "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"}]
    out = ps.apply([], instantly, ghl=ghl, reverse=reverse)
    assert rec.requests == []
    assert out["would_do"] == 1 and out["results"][0]["outcome"] == "would_do"


# --------------------------------------------------------------- live
def test_apply_live_mocked_sends_http(tmp_env, live_mode):
    def instantly_handler(request):
        assert request.url.path == "/api/v2/leads/update-interest-status"
        body = json.loads(request.content)
        assert body == {"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "interest_value": 2}
        return httpx.Response(200, json={"status": "ok"})

    def ghl_handler(request):
        if request.url.path == "/contacts/upsert":
            return httpx.Response(200, json={"contact": {"id": "new-c"}})
        if request.url.path == "/opportunities/upsert":
            body = json.loads(request.content)
            assert body["contactId"] == "new-c" and body["monetaryValue"] == 7500.0
            return httpx.Response(200, json={"opportunity": {"id": "new-o"}})
        return httpx.Response(404, json={})

    rec_i, rec_g = Recorder(instantly_handler), Recorder(ghl_handler)
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec_i))
    ghl = GHL(token="t", transport=httpx.MockTransport(rec_g))
    diff = [{"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": 2, "reason": "r", "contact_id": "c1", "note": None}]
    reverse = [{"action": "create_opportunity", "lead_email": "t@f.co", "campaign_id": "f347604e-48c7-4813-831c-dc7b9d4b50ae",
                "interest": 1, "stage": "new_reply", "name": "T", "first_name": "T", "last_name": None, "company": None,
                "monetary_value": 7500.0, "offer": "outbound", "reason": "x"}]
    out = ps.apply(diff, instantly, ghl=ghl, reverse=reverse)
    assert out["done"] == 2 and out["would_do"] == 0 and out["errors"] == []
    assert len(rec_i.requests) == 1 and len(rec_g.requests) == 2


def test_apply_live_without_ghl_token_reports_an_error_not_a_success(tmp_env, live_mode):
    """shared.ghl raises in live with no token on purpose: a dropped write must
    never be reported as done or quietly skipped."""
    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    out = ps.apply([], instantly, ghl=ghl, value_fixes=[{"action": "set_value", "opportunity_id": "o", "contact_id": "c",
                                                          "lead_email": "e", "campaign_id": None, "stage": "new_reply",
                                                          "name": "n", "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"}])
    assert rec.requests == [] and out["done"] == 0
    assert len(out["errors"]) == 1 and out["results"][0]["outcome"] == "error"


def test_reverse_check_skips_when_the_contact_id_cannot_be_read(tmp_env, live_mode):
    """A contacts/upsert envelope we do not recognise must never become the
    literal string "<contact from upsert>" in a live opportunity POST."""
    posted = []

    def ghl_handler(request):
        posted.append(request.url.path)
        if request.url.path == "/contacts/upsert":
            return httpx.Response(200, json={"succeded": True})     # no id anywhere
        return httpx.Response(200, json={"opportunity": {"id": "o"}})

    rec_g = Recorder(ghl_handler)
    ghl = GHL(token="t", transport=httpx.MockTransport(rec_g))
    reverse = [{"action": "create_opportunity", "lead_email": "t@f.co", "campaign_id": CLEANING_REACT, "interest": 1,
                "stage": "new_reply", "status": "open", "name": "T", "first_name": "T", "last_name": None,
                "company": None, "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"}]
    out = ps.apply([], None, ghl=ghl, reverse=reverse)
    assert posted == ["/contacts/upsert"]          # the opportunity was NOT written
    assert out["results"][0]["outcome"] == "error" and out["done"] == 0
    assert "no contact id" in out["errors"][0]


def test_contact_id_is_read_from_every_envelope_shape():
    assert ps.contact_id_from_upsert({"contact": {"id": "a"}}) == "a"
    assert ps.contact_id_from_upsert({"id": "b"}) == "b"
    assert ps.contact_id_from_upsert({"_id": "c"}) == "c"
    assert ps.contact_id_from_upsert({"contact": {"_id": "d"}}) == "d"
    assert ps.contact_id_from_upsert({"succeded": True}) is None
    assert ps.contact_id_from_upsert(None) is None


def test_a_won_lead_is_written_as_won_not_as_open_pipeline(tmp_env, live_mode):
    bodies = []

    def ghl_handler(request):
        if request.url.path == "/contacts/upsert":
            return httpx.Response(200, json={"contact": {"id": "new-c"}})
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"opportunity": {"id": "new-o"}})

    ghl = GHL(token="t", transport=httpx.MockTransport(Recorder(ghl_handler)))
    reverse = ps.compute_reverse([], [lead("won@x.co", CLEANING_REACT, 4)])
    out = ps.apply([], None, ghl=ghl, reverse=reverse)
    assert out["done"] == 1 and out["errors"] == []
    assert bodies[0]["status"] == "won"
    assert bodies[0]["pipelineStageId"] == STAGES["won"]
    assert "monetaryValue" not in bodies[0]        # no guessed value on a closed deal


def test_value_fix_without_a_resolvable_stage_or_a_contact_is_refused(tmp_env, live_mode):
    """The contact-keyed fallback, used only by a client that cannot update an
    opportunity by id. Upserting by contact is a whole-opportunity write, so a
    row with no stage, no contact, or a contact holding two Sales opportunities
    is an error row rather than a guess."""
    rec = Recorder()

    class GHLWithoutValueUpdate(GHL):
        update_opportunity_value = None      # the pre-cursor shared client

    ghl = GHLWithoutValueUpdate(token="t", transport=httpx.MockTransport(rec))
    fixes = [{"action": "set_value", "opportunity_id": "o1", "contact_id": "c1", "lead_email": "a@b.co",
              "campaign_id": None, "stage": None, "stage_id": None, "name": "A", "monetary_value": 6000.0,
              "offer": "reactivation", "reason": "x"},
             {"action": "set_value", "opportunity_id": "o2", "contact_id": None, "lead_email": "b@b.co",
              "campaign_id": None, "stage": "new_reply", "stage_id": STAGES["new_reply"], "name": "B",
              "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"},
             {"action": "set_value", "opportunity_id": "o3", "contact_id": "c3", "lead_email": "c@b.co",
              "campaign_id": None, "stage": "new_reply", "stage_id": STAGES["new_reply"], "name": "C",
              "ambiguous_contact": True, "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"}]
    out = ps.apply([], None, ghl=ghl, value_fixes=fixes)
    assert rec.requests == []                       # nothing was sent
    assert len(out["errors"]) == 3 and out["done"] == 0


def test_value_fix_uses_the_opportunity_id_when_the_client_can_update_by_id(tmp_env, live_mode):
    """Preferred path: PUT /opportunities/{id} with monetaryValue only, so a
    value fix can never move a deal or hit the wrong opportunity."""
    calls = []

    class GHLWithValueUpdate(GHL):
        def update_opportunity_value(self, opportunity_id, monetary_value):
            calls.append((opportunity_id, monetary_value))
            return {"opportunity": {"id": opportunity_id}}

    ghl = GHLWithValueUpdate(token="t", transport=httpx.MockTransport(Recorder()))
    fixes = [{"action": "set_value", "opportunity_id": "o9", "contact_id": "c9", "lead_email": "z@z.co",
              "campaign_id": None, "stage": "proposal_sent", "stage_id": STAGES["proposal_sent"], "name": "Z",
              "ambiguous_contact": True, "monetary_value": 6000.0, "offer": "reactivation", "reason": "x"}]
    out = ps.apply([], None, ghl=ghl, value_fixes=fixes)
    assert calls == [("o9", 6000.0)] and out["done"] == 1 and out["errors"] == []


def test_a_failed_ghl_note_does_not_report_the_interest_update_as_failed(tmp_env, live_mode):
    """The note shared the interest update's try block, so a 429 on the note
    rewrote the outcome to "error" for a write Instantly had already accepted
    (live answers 202), and whoever reconciled from the digest re-applied a
    change that had landed."""
    def instantly_handler(request):
        return httpx.Response(200, json={"status": "ok"})

    def ghl_handler(request):
        return httpx.Response(429, json={"message": "rate limited"})

    instantly = Instantly(api_key="k", transport=httpx.MockTransport(Recorder(instantly_handler)))
    ghl = GHL(token="t", transport=httpx.MockTransport(Recorder(ghl_handler)))
    diff = [{"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": -1,
             "reason": "ghl_stage:follow_up_later", "contact_id": "c1", "note": "Pipeline sync: follow up later"}]
    out = ps.apply(diff, instantly, ghl=ghl)
    assert out["done"] == 1 and out["error"] == 0
    entry = out["results"][0]
    assert entry["outcome"] == "done"            # the interest status really was applied
    assert entry["note_outcome"] == "error"
    assert len(out["errors"]) == 1 and "interest status applied" in out["errors"][0]


def test_a_failed_interest_update_does_not_attempt_the_note(tmp_env, live_mode):
    def boom(request):
        return httpx.Response(400, text="nope")

    ghl_calls = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(Recorder(boom)))
    ghl = GHL(token="t", transport=httpx.MockTransport(ghl_calls))
    diff = [{"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": -1, "reason": "r",
             "contact_id": "c1", "note": "n"}]
    out = ps.apply(diff, instantly, ghl=ghl)
    assert out["results"][0]["outcome"] == "error" and "note_outcome" not in out["results"][0]
    assert ghl_calls.requests == []


def test_an_opportunity_with_no_contact_email_blocks_the_reverse_check(tmp_env, shadow_mode):
    """Same failure mode the ghl_truncated guard exists for: an opportunity the
    check cannot match looks missing, so the lead gets a second contact and a
    second Call Booked opportunity in the single source of truth."""
    blind = {"id": "oIlmi", "name": "Ilmi", "pipelineStageId": STAGES["call_booked"], "status": "open",
             "contactId": "cIlmi", "contact": {"id": "cIlmi", "name": "Ilmi Curovic"}, "monetaryValue": 6000}
    leads = [lead("ilmi@shiningarmorcleaningnj.com", CLEANING_REACT, 2)]
    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    ghl = GHL(token="t", transport=httpx.MockTransport(Recorder()))
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=ghl, ghl_opportunities=[blind],
                         instantly_leads=leads, notify_digest=False)
    assert report["reverse_blocked"] and "ghl_rows_without_email" in report["reverse_blocked"]
    assert [r["lead_email"] for r in report["reverse"]] == ["ilmi@shiningarmorcleaningnj.com"]  # reported
    assert report["applied"]["would_do"] == 0                                                  # not proposed
    assert report["applied"]["skipped"] == 1
    assert [r["action"] for r in job_log.read_shadow_log()] == []
    assert "NOT APPLIED" in ps.render_summary(report)


def test_run_sync_status_is_error_when_every_applied_row_failed(tmp_env, live_mode):
    """`partial` reads as healthy enough to pass the deployment runbook's
    48-hour shadow gate; a night where every interest update failed is not."""
    def boom(request):
        return httpx.Response(400, text="nope")

    instantly = Instantly(api_key="k", transport=httpx.MockTransport(Recorder(boom)))
    opps = [opp("ilmi@shiningarmorcleaningnj.com", "call_booked", oid="o1", cid="c1", value=6000)]
    leads = [lead("ilmi@shiningarmorcleaningnj.com", CLEANING_REACT, 1)]
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=GHL(token=None),
                         ghl_opportunities=opps, instantly_leads=leads, notify_digest=False)
    assert report["applied"]["done"] == 0 and report["applied"]["errors"]
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "pipeline_sync,error," in rows
    assert "pipeline_sync,partial," not in rows


def test_apply_isolates_row_errors(tmp_env, live_mode):
    def boom(request):
        return httpx.Response(500, text="nope")

    instantly = Instantly(api_key="k", transport=httpx.MockTransport(boom))
    ghl = GHL(token=None)
    diff = [{"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": 2, "reason": "r"},
            {"lead_email": "b@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": 4, "reason": "r"}]
    out = ps.apply(diff, instantly, ghl=ghl)
    assert len(out["errors"]) == 2 and all(r["outcome"] == "error" for r in out["results"])


# ----------------------------------------------------------- fetching
def leads_list_handler(leads):
    def handler(request):
        assert request.method == "POST" and request.url.path == "/api/v2/leads/list"
        body = json.loads(request.content)
        rows = leads
        if body.get("contacts"):
            wanted = set(c.lower() for c in body["contacts"])
            rows = [l for l in rows if l["email"].lower() in wanted]
        if body.get("campaign"):
            rows = [l for l in rows if l["campaign"] == body["campaign"]]
        flt = body.get("filter")
        if flt:
            want = {"FILTER_LEAD_INTERESTED": 1, "FILTER_LEAD_MEETING_BOOKED": 2,
                    "FILTER_LEAD_MEETING_COMPLETED": 3, "FILTER_LEAD_CLOSED": 4}.get(flt)
            if want is None:
                return httpx.Response(400, json={"message": "bad filter"})
            rows = [l for l in rows if l.get("lt_interest_status") == want]
        return httpx.Response(200, json={"items": rows})
    return handler


def test_fetch_instantly_leads_uses_contacts_and_positive_filters():
    leads = load("instantly_replied_leads_2026-09.json")
    rec = Recorder(leads_list_handler(leads))
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    out, note = ps.fetch_instantly_leads(instantly, ["ilmi@shiningarmorcleaningnj.com"], campaign_ids=[CLEANING_REACT])
    emails = sorted(l["email"] for l in out)
    assert emails == ["ilmi@shiningarmorcleaningnj.com"]
    assert note is None
    # one contacts lookup + four positive filters for the campaign
    assert len(rec.requests) == 5


def test_fetch_instantly_leads_falls_back_to_full_pull_when_filter_rejected():
    leads = load("instantly_replied_leads_2026-09.json")
    base = leads_list_handler(leads)

    def handler(request):
        body = json.loads(request.content)
        if body.get("filter"):
            return httpx.Response(400, json={"message": "unknown filter"})
        return base(request)

    rec = Recorder(handler)
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    out, note = ps.fetch_instantly_leads(instantly, [], campaign_ids=[CLEANING_REACT])
    assert len(out) == len([l for l in leads if l["campaign"] == CLEANING_REACT])
    # a rejected filter is the documented fallback, not a failed read
    assert note is None


def test_a_failed_lead_pull_is_reported_and_blocks_apply(tmp_env, shadow_mode):
    """fetch_instantly_leads used to log and return [], so a 503 on
    POST /leads/list was indistinguishable from "no positive leads": the
    interest mirror silently did nothing while value fixes were still emitted
    with campaign_id None, writing the wrong dollar default into GHL on a run
    reported as ok."""
    def dead(request):
        return httpx.Response(503, json={"message": "service unavailable"})

    # sleep=... so the client's real retry backoff does not stretch the test
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(Recorder(dead)), sleep=lambda _s: None)
    rows, note = ps.fetch_instantly_leads(instantly, ["a@b.co"], campaign_ids=[CLEANING_REACT])
    assert rows == []
    assert note is not None and note.startswith("instantly_unreadable")

    opps = [opp("tiffany@flowerhillfs.com", "new_reply", oid="o1", cid="c1", value=None)]
    ghl = GHL(token="t", transport=httpx.MockTransport(
        Recorder(lambda r: httpx.Response(200, json={"opportunities": opps, "meta": {"total": 1}}))))
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=ghl, notify_digest=False)
    assert report["apply_blocked"] == "instantly_unreadable"
    assert any(n.startswith("instantly_unreadable") for n in report["notes"])
    assert report["applied"]["would_do"] == 0 and report["applied"]["done"] == 0
    assert job_log.read_shadow_log() == []
    assert "Apply blocked: instantly_unreadable" in ps.render_summary(report)


def test_fetch_ghl_opportunities_without_token_notes_missing():
    rows, note = ps.fetch_ghl_opportunities(GHL(token=None))
    assert rows == [] and note == "ghl_token_missing"


def test_fetch_ghl_opportunities_with_token():
    def handler(request):
        assert request.url.path == "/opportunities/search"
        assert request.url.params["pipeline_id"] == settings.GHL_SALES_PIPELINE_ID
        return httpx.Response(200, json={"opportunities": [opp("a@b.co", "new_reply")]})

    rows, note = ps.fetch_ghl_opportunities(GHL(token="t", transport=httpx.MockTransport(handler)))
    assert note is None and len(rows) == 1


# ------------------------------------------------------------ run_sync
def test_run_sync_dry_run_on_fixtures_logs_and_does_not_apply(tmp_env, shadow_mode):
    leads = load("instantly_replied_leads_2026-09.json")
    opps = [opp("ilmi@shiningarmorcleaningnj.com", "call_booked", oid="HOPG", cid="cnfZ"),
            opp("sopiosvanishvili@taxfoaccounting.com", "new_reply", oid="hStq", cid="iDhe")]
    report = ps.run_sync(dry_run=True, now=NOW, ghl=GHL(token=None), ghl_opportunities=opps, instantly_leads=leads, notify_digest=False)
    assert report["applied"] is None
    assert [d["lead_email"] for d in report["diff"]] == ["ilmi@shiningarmorcleaningnj.com"]
    assert report["diff"][0]["from"] == 1 and report["diff"][0]["to"] == 2
    assert [r["lead_email"] for r in report["reverse"]] == ["ignacio@ariacleaningservices.com", "tiffany@flowerhillfs.com"]
    assert [v["opportunity_id"] for v in report["value_fixes"]] == ["HOPG", "hStq"]
    assert job_log.read_shadow_log() == []
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "pipeline_sync" in rows and "dry_run" in rows
    text = ps.render_summary(report)
    assert "DRY RUN" in text and "ilmi@shiningarmorcleaningnj.com" in text


def test_run_sync_now_in_shadow_produces_would_do(tmp_env, shadow_mode):
    leads = load("instantly_replied_leads_2026-09.json")
    opps = [opp("ilmi@shiningarmorcleaningnj.com", "call_booked", oid="HOPG", cid="cnfZ")]
    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=GHL(token=None), ghl_opportunities=opps,
                         instantly_leads=leads, notify_digest=True)
    applied = report["applied"]
    assert rec.requests == []
    assert applied["done"] == 0 and applied["errors"] == []
    # 1 diff + 3 reverse (sopio, ignacio, tiffany) + 1 value fix
    assert applied["would_do"] == 5
    assert len(job_log.read_shadow_log()) >= 5
    from shared import notify as notify_mod
    assert notify_mod.sent_in_test and "Pipeline sync" in notify_mod.sent_in_test[-1]["title"]


def test_run_sync_without_ghl_seeds_snapshot_and_blocks_apply(tmp_env, shadow_mode):
    """No GHL token: opportunities come from the config/ids.json snapshot for
    reporting, and --now applies nothing, not even in shadow."""
    leads = load("instantly_replied_leads_2026-09.json")
    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=GHL(token=None), instantly_leads=leads, notify_digest=False)
    assert "ghl_token_missing" in report["notes"]
    assert report["ghl_opportunities"] == 3          # ids.json opportunities_observed_2026-09-21
    assert report["apply_blocked"] == "ghl_unreadable"
    # the snapshot says Ilmi is Call Booked while Instantly says Interested
    assert [(d["lead_email"], d["from"], d["to"]) for d in report["diff"]] == [("ilmi@shiningarmorcleaningnj.com", 1, 2)]
    assert [r["lead_email"] for r in report["reverse"]] == ["ignacio@ariacleaningservices.com"]
    assert len(report["value_fixes"]) == 3
    assert report["applied"]["would_do"] == 0 and report["applied"]["done"] == 0 and report["applied"]["skipped"] == 5
    assert rec.requests == [] and job_log.read_shadow_log() == []
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "skipped_ghl_unreadable" in rows
    assert "Apply blocked: ghl_unreadable" in ps.render_summary(report)


def test_cli_dry_run_fixtures(tmp_env, shadow_mode, capsys):
    rc = ps.main(["--dry-run", "--fixtures", "--as-of", "2026-09-21T21:10:00-05:00", "--no-notify"])
    out = capsys.readouterr().out
    assert rc == 0 and "DRY RUN" in out and "Missing GHL opportunities (4)" in out
    assert job_log.read_shadow_log() == []


# --------------------------------------------------- GHL paging / truncation
def paged_opportunity(i, stage="proposal_sent"):
    return opp("lead%03d@x.co" % i, stage, oid="o%03d" % i, cid="c%03d" % i)


def test_fetch_ghl_opportunities_reports_truncation_instead_of_silently_stopping():
    """One page of 100 with more behind it must not look like the whole
    pipeline: every opportunity past the page would read as "missing from GHL"
    to the reverse check and be created a second time.

    The shared client DOES take a cursor now (`start_after_id`), so the pull
    asks once more using the last row's id; this stub answers the same page
    again, which is the "cursor is not advancing" hard stop -- one extra call,
    not the full 20-page cap."""
    calls = []

    def handler(request):
        calls.append(request.url)
        rows = [paged_opportunity(i) for i in range(100)]
        return httpx.Response(200, json={"opportunities": rows, "meta": {"total": 250, "nextPageUrl": "https://x/2"}})

    rows, note = ps.fetch_ghl_opportunities(GHL(token="t", transport=httpx.MockTransport(Recorder(handler))))
    assert len(rows) == 100
    assert note is not None and note.startswith("ghl_truncated")
    assert "not advancing" in note
    assert len(calls) == 2
    assert "startAfterId=o099" in str(calls[1])


def test_fetch_ghl_opportunities_follows_a_cursor_when_the_client_offers_one():
    pages = [
        {"opportunities": [paged_opportunity(i) for i in range(100)], "meta": {"total": 150, "startAfterId": "o099"}},
        {"opportunities": [paged_opportunity(i) for i in range(100, 150)], "meta": {"total": 150}},
    ]
    seen = []

    class GHLWithCursor(GHL):
        def search_opportunities(self, contact_id=None, pipeline_id=None, stage_id=None, limit=20, start_after_id=None):
            seen.append(start_after_id)
            return pages[len(seen) - 1]

    rows, note = ps.fetch_ghl_opportunities(GHLWithCursor(token="t"))
    assert note is None and len(rows) == 150
    assert seen == [None, "o099"]


def test_cursor_forwards_start_after_with_start_after_id():
    """GHL's /opportunities/search cursor is the PAIR. The old code picked the
    first name out of one flat list, which always resolved to `start_after_id`,
    so the timestamp the page meta had just handed us was dropped and GHL could
    re-serve or skip records."""
    pages = [
        {"opportunities": [paged_opportunity(i) for i in range(100)],
         "meta": {"total": 150, "startAfterId": "o099", "startAfter": 1790000000000}},
        {"opportunities": [paged_opportunity(i) for i in range(100, 150)], "meta": {"total": 150}},
    ]
    seen = []

    class GHLWithPairCursor(GHL):
        def search_opportunities(self, contact_id=None, pipeline_id=None, stage_id=None, limit=20,
                                 start_after_id=None, start_after=None):
            seen.append({"start_after_id": start_after_id, "start_after": start_after})
            return pages[len(seen) - 1]

    rows, note = ps.fetch_ghl_opportunities(GHLWithPairCursor(token="t"))
    assert note is None and len(rows) == 150
    assert seen == [{"start_after_id": None, "start_after": None},
                    {"start_after_id": "o099", "start_after": 1790000000000}]
    assert ps._cursor_params(GHLWithPairCursor(token="t")) == ("start_after_id", "start_after")


def test_a_page_number_in_meta_is_not_used_as_a_cursor():
    """`meta.nextPage` is a page NUMBER. Sending 2 as startAfterId asks GHL for
    the rows after an opportunity called "2", which is page 1 again, and the
    loop used to burn all 20 calls a night and block the mirror forever."""
    calls = []

    def handler(request):
        calls.append(request.url)
        rows = [paged_opportunity(i) for i in range(100)]
        return httpx.Response(200, json={"opportunities": rows,
                                         "meta": {"nextPageUrl": "https://x/2", "nextPage": 2}})

    rows, note = ps.fetch_ghl_opportunities(GHL(token="t", transport=httpx.MockTransport(Recorder(handler))))
    assert note is not None and note.startswith("ghl_truncated")
    assert len(calls) == 2, [str(c) for c in calls]     # one probe, then the hard stop
    assert "startAfterId=2" not in str(calls[1])
    assert "nextPage" not in ps.GHL_CURSOR_PARAMS and "page" not in ps.GHL_CURSOR_PARAMS


def test_exactly_one_full_page_with_no_cursor_is_settled_by_asking_ghl():
    """A complete pull of exactly `limit` rows with an empty meta is ambiguous.
    `startAfterId` means "the id to continue after", so the pull asks for the
    page after the last row instead of guessing; an empty answer proves the
    pipeline ended there and the note stays None."""
    calls = []

    def handler(request):
        calls.append(request.url)
        if len(calls) == 1:
            return httpx.Response(200, json={"opportunities": [paged_opportunity(i) for i in range(100)]})
        return httpx.Response(200, json={"opportunities": []})

    rows, note = ps.fetch_ghl_opportunities(GHL(token="t", transport=httpx.MockTransport(Recorder(handler))))
    assert note is None and len(rows) == 100
    assert len(calls) == 2 and "startAfterId=o099" in str(calls[1])


def test_a_short_page_with_no_cursor_is_a_complete_pull():
    def handler(request):
        return httpx.Response(200, json={"opportunities": [paged_opportunity(i) for i in range(7)]})

    rows, note = ps.fetch_ghl_opportunities(GHL(token="t", transport=httpx.MockTransport(Recorder(handler))))
    assert note is None and len(rows) == 7


def test_a_truncated_ghl_pull_blocks_apply_the_way_an_unreadable_one_does(tmp_env, shadow_mode):
    def handler(request):
        rows = [paged_opportunity(i) for i in range(100)]
        return httpx.Response(200, json={"opportunities": rows, "meta": {"total": 250, "nextPageUrl": "https://x/2"}})

    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    ghl = GHL(token="t", transport=httpx.MockTransport(Recorder(handler)))
    leads = [lead("lead200@x.co", CLEANING_REACT, 2)]   # its opportunity is on page 2
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=ghl, instantly_leads=leads, notify_digest=False)
    assert report["apply_blocked"] == "ghl_truncated"
    assert [r["lead_email"] for r in report["reverse"]] == ["lead200@x.co"]   # computed for the report
    assert report["applied"]["would_do"] == 0 and report["applied"]["done"] == 0
    assert job_log.read_shadow_log() == []          # and nothing was even proposed as a write


# ------------------------------------------------------------ fixture replay
def test_fixtures_replay_cannot_be_applied(tmp_env, shadow_mode, capsys):
    """--now --fixtures used to compute from a recorded September file and push
    it: ghl_opportunities=[] left ghl_readable True, so the apply guard never
    fired. In live that writes months-old state into GHL."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        ps.main(["--now", "--fixtures", "--no-notify"])
    assert exc.value.code == 2
    assert "cannot be applied" in capsys.readouterr().err
    assert job_log.read_shadow_log() == []


def test_replay_flag_blocks_apply_even_when_run_sync_is_called_directly(tmp_env, shadow_mode):
    leads = load("instantly_replied_leads_2026-09.json")
    rec = Recorder()
    instantly = Instantly(api_key="k", transport=httpx.MockTransport(rec))
    report = ps.run_sync(dry_run=False, now=NOW, instantly=instantly, ghl=GHL(token=None),
                         ghl_opportunities=[], instantly_leads=leads, notify_digest=False, replay=True)
    assert report["apply_blocked"] == "fixture_replay"
    assert report["applied"]["would_do"] == 0 and rec.requests == []
    assert job_log.read_shadow_log() == []


def test_a_200_that_reports_failure_is_not_counted_as_done(tmp_env, live_mode):
    """GHL answers 200 with {"succeded": false} on a rejected write; counting
    that as done puts a clean row in Job_Log for a change that never landed."""
    def instantly_handler(request):
        return httpx.Response(200, json={"succeded": False})

    instantly = Instantly(api_key="k", transport=httpx.MockTransport(Recorder(instantly_handler)))
    diff = [{"lead_email": "a@b.co", "campaign_id": CLEANING_REACT, "from": 1, "to": 2, "reason": "r"}]
    out = ps.apply(diff, instantly, ghl=GHL(token=None))
    assert out["done"] == 0 and out["error"] == 1 and len(out["errors"]) == 1
