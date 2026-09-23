"""Pipeline sweep on the recorded September fixtures served through
httpx.MockTransport. Clock injected: 2026-09-21T21:10:00-05:00."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytz

from shared import job_log
from shared import notify as notify_mod
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore
from jobs import pipeline_sweep as sweep

FIXTURES = Path(__file__).resolve().parent.parent.parent / "services" / "reply_engine" / "tests" / "fixtures"
CT = pytz.timezone("America/Chicago")
NOW = CT.localize(datetime(2026, 9, 21, 21, 10))  # == 2026-09-22T02:10Z

SOPIO = "sopiosvanishvili@taxfoaccounting.com"
ILMI = "ilmi@shiningarmorcleaningnj.com"


def load(name):
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fixture_transport(recorder=None):
    """MockTransport serving GET /emails (received | manual) and POST /leads/list from the fixtures."""
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    leads = load("instantly_replied_leads_2026-09.json")

    def handler(request):
        if recorder is not None:
            recorder.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/emails":
            kind = request.url.params.get("email_type")
            rows = {"received": received, "manual": manual}.get(kind, [])
            rows = sorted(rows, key=lambda r: r["timestamp_created"], reverse=True)
            return httpx.Response(200, json={"items": rows, "next_starting_after": None})
        if request.method == "POST" and request.url.path == "/api/v2/leads/list":
            body = json.loads(request.content)
            wanted = set(c.lower() for c in body.get("contacts", []))
            rows = [l for l in leads if not wanted or l["email"].lower() in wanted]
            return httpx.Response(200, json={"items": rows})
        return httpx.Response(404, json={"message": "unmocked %s %s" % (request.method, request.url.path)})

    return httpx.MockTransport(handler)


def make_store(tmp_path):
    return JsonFileStore(tmp_path / "sweep_store.json")


# ----------------------------------------------------------- (a) positives
def test_sopio_flagged_and_ilmi_not(tmp_env, shadow_mode):
    requests = []
    instantly = Instantly(api_key="k", transport=fixture_transport(requests))
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env), dry_run=True)
    positives = {p["lead_email"]: p for p in result["items"] if p["kind"] == "positive"}

    # Sopio: inbound 2026-09-21T23:17Z after Lorenzo's 18:30Z outbound -> awaiting reply
    assert SOPIO in positives
    sopio = positives[SOPIO]
    assert sopio["inbound_at"].startswith("2026-09-21T23:17:28")
    assert sopio["last_outbound_at"].startswith("2026-09-21T18:30:18")
    assert sopio["overdue"] is False and 2.5 < sopio["age_hours"] < 3.5
    assert sopio["name"] == "Sopio Svanishvili" and sopio["company"] == "Taxfo Accounting"
    assert sopio["campaign"] == "bookkeeping_reactivation" and sopio["eaccount"] == "lorenzov@theadvero.com"
    assert "3pm-6pm" in sopio["snippet"]

    # Ilmi: 19:00:48Z inbound answered by the 19:03:06Z outbound -> not flagged
    assert ILMI not in positives
    # every request was a read (GET /emails, POST /leads/list); nothing else
    assert all(r.url.path in ("/api/v2/emails", "/api/v2/leads/list") for r in requests)
    assert job_log.read_shadow_log() == []


def test_find_awaiting_replies_pure():
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    items = sweep.find_awaiting_replies(received, manual, NOW)
    emails = sorted(i["lead_email"] for i in items)
    # Sopio is the only positive whose latest inbound has no later outbound;
    # Tiffany and Ignacio were answered the same day; Rob is explicitly lost (-3).
    assert emails == [SOPIO]


def test_overdue_after_24h():
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    later = NOW + timedelta(hours=30)
    items = sweep.find_awaiting_replies(received, manual, later)
    assert items[0]["lead_email"] == SOPIO and items[0]["overdue"] is True


def test_positive_rule_and_outbound_detection():
    assert sweep.is_positive_reply({"i_status": 1, "ai_interest_value": 0})
    assert sweep.is_positive_reply({"i_status": None, "ai_interest_value": 1})
    assert sweep.is_positive_reply({"i_status": 0, "ai_interest_value": 1})
    assert not sweep.is_positive_reply({"i_status": -3, "ai_interest_value": 1})   # Lorenzo's explicit lost wins
    assert not sweep.is_positive_reply({"i_status": None, "ai_interest_value": None})
    assert sweep.is_outbound({"eaccount": "lorenzov@theadvero.com", "to_address_email_list": SOPIO})
    assert not sweep.is_outbound({"eaccount": "lorenzov@theadvero.com", "to_address_email_list": "lorenzov@theadvero.com"})
    assert not sweep.is_outbound({"eaccount": "x@y.co", "to_address_email_list": ""})


# ------------------------------------------------------------- (b) booked
def test_unconfirmed_booked_calls_from_store(tmp_env):
    store = make_store(tmp_env)
    soon = (NOW + timedelta(hours=14)).isoformat()
    later = (NOW + timedelta(hours=40)).isoformat()
    store.set("appointment:1", {"lead_email": ILMI, "name": "Ilmi Curovic", "company": "Shining Armor", "start": soon,
                                "confirmed": False, "campaign_id": "8086b41e-b546-4b36-9fa0-2d01f5cc119a"})
    store.set("appointment:2", {"lead_email": "ok@x.co", "name": "Confirmed", "start": soon, "confirmed": True})
    store.set("appointment:3", {"lead_email": "far@x.co", "name": "Far", "start": later, "confirmed": False})
    items = sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW)
    assert [i["lead_email"] for i in items] == [ILMI]
    assert items[0]["kind"] == "booked" and items[0]["value"] == 6000.0 and 13.9 < items[0]["hours_until"] < 14.1


def test_booked_seed_from_ids_json_only_future(monkeypatch):
    monkeypatch.setattr(sweep.settings, "IDS", dict(sweep.settings.IDS, google_calendar={"booked_this_week": [
        {"who": "Past", "start": "2026-09-20T15:00:00-05:00"},
        {"who": "Future", "start": "2026-09-22T15:00:00-05:00", "note": "awaiting confirmation"},
    ]}))
    seeded = sweep._seed_appointments_from_ids(NOW)
    assert [s["name"] for s in seeded] == ["Future"]
    items = sweep.find_unconfirmed_calls(seeded, NOW)
    assert len(items) == 1 and items[0]["source"] == "ids.json"


# ---------------------------------------------------------- (c) proposals
def test_stale_proposals_respect_touches(tmp_env):
    store = make_store(tmp_env)
    ten_days = (NOW - timedelta(days=10)).isoformat()
    store.set("proposal:a", {"lead_email": "a@x.co", "name": "A", "sent_at": ten_days, "value": 9000})
    store.set("proposal:b", {"lead_email": "b@x.co", "name": "B", "sent_at": ten_days, "last_touch": (NOW - timedelta(days=2)).isoformat()})
    store.set("proposal:c", {"lead_email": "c@x.co", "opportunity_id": "oc", "name": "C", "sent_at": ten_days})
    store.set("opptouch:oc", (NOW - timedelta(days=1)).isoformat())
    ghl_rows = [{"id": "og", "name": "G", "contact": {"email": "g@x.co"}, "lastStageChangeAt": ten_days, "monetaryValue": 12000, "source": "ghl"}]
    items = sweep.find_stale_proposals(ghl_rows + sweep.proposals_from_store(store), NOW, touches=sweep.touches_from_store(store))
    assert sorted(i["lead_email"] for i in items) == ["a@x.co", "g@x.co"]
    by = {i["lead_email"]: i for i in items}
    assert by["a@x.co"]["value"] == 9000.0 and by["g@x.co"]["value"] == 12000.0 and by["g@x.co"]["age_days"] >= 10


def test_proposals_from_ghl_without_token_is_none():
    assert sweep.proposals_from_ghl(GHL(token=None)) is None


def test_the_touch_namespace_does_not_collide_with_cadence(tmp_env):
    """cadence.py owns `touch:<campaign>:<lead>:<n>:<kind>` and its values are
    dicts, so the sweep's old `touch:` prefix matched cadence rows and never an
    opportunity id: the proposal last-touch signal was dead."""
    store = make_store(tmp_env)
    store.set("touch:8086b41e:lead@x.co:1:d1", {"sent_at": NOW.isoformat()})
    store.set("opptouch:oc", (NOW - timedelta(days=1)).isoformat())
    assert sweep.touches_from_store(store) == {"oc": (NOW - timedelta(days=1)).isoformat()}
    assert sweep.STORE_OPP_TOUCH_PREFIX == "opptouch:"


# ------------------------------------------------------------- (d) upwork
def test_upwork_hook_reads_file_when_present(tmp_path):
    assert sweep.load_upwork_rooms(tmp_path / "missing.json") is None
    path = tmp_path / "upwork_rooms.json"
    path.write_text(json.dumps({"rooms": [
        {"room_id": "r1", "client": "Jennifer Lawson", "awaiting": "lorenzo", "last_message_at": "2026-09-21T20:00:00Z", "last": "contract ended"},
        {"room_id": "r2", "client": "Someone", "awaiting": "client"},
    ]}), encoding="utf-8")
    rooms = sweep.load_upwork_rooms(path)
    items = sweep.find_upwork_awaiting(rooms, NOW)
    assert len(items) == 1 and items[0]["name"] == "Jennifer Lawson" and items[0]["overdue"] is True


# --------------------------------------------------------------- ordering
def test_order_booked_then_positive_then_proposal_then_upwork():
    items = [
        {"kind": "upwork", "name": "u", "value": 0, "age_hours": 50},
        {"kind": "proposal", "name": "p", "value": 20000, "age_days": 9},
        {"kind": "positive", "lead_email": "small@x.co", "value": 6000, "age_hours": 30},
        {"kind": "positive", "lead_email": "big@x.co", "value": 7500, "age_hours": 3},
        {"kind": "positive", "lead_email": "older@x.co", "value": 7500, "age_hours": 40},
        {"kind": "booked", "lead_email": "b@x.co", "value": 6000, "hours_until": 5},
    ]
    ordered = sweep.order_items(items)
    assert [i["kind"] for i in ordered] == ["booked", "positive", "positive", "positive", "proposal", "upwork"]
    assert [i["lead_email"] for i in ordered[1:4]] == ["older@x.co", "big@x.co", "small@x.co"]


# ------------------------------------------------------------ end to end
def test_run_sweep_full_digest_joblog_and_notify(tmp_env, shadow_mode):
    notify_mod.reset_for_tests()
    store = make_store(tmp_env)
    store.set("appointment:ilmi", {"lead_email": ILMI, "name": "Ilmi Curovic", "company": "Shining Armor Cleaning NJ",
                                   "start": (NOW + timedelta(hours=14)).isoformat(), "confirmed": False})
    store.set("proposal:old", {"lead_email": "old@x.co", "name": "Old Co", "sent_at": (NOW - timedelta(days=8)).isoformat()})
    rooms = tmp_env / "upwork_rooms.json"
    rooms.write_text(json.dumps([{"room_id": "r", "client": "Jennifer Lawson", "awaiting": True}]), encoding="utf-8")

    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=store, upwork_rooms_path=rooms, dry_run=False)

    kinds = [i["kind"] for i in result["items"]]
    assert kinds == ["booked", "positive", "proposal", "upwork"]
    assert result["items"][0]["lead_email"] == ILMI
    assert result["items"][1]["lead_email"] == SOPIO
    assert result["counts"] == {"booked": 1, "positive": 1, "positive_overdue": 0, "proposal": 1, "upwork": 1, "total": 4}
    assert any("ghl_token_missing" in n for n in result["notes"])

    digest = result["digest"]
    assert digest.splitlines()[0].startswith("Pipeline sweep") and "4 item(s)" in digest
    assert "1. BOOKED Ilmi Curovic" in digest and "2. POSITIVE Sopio Svanishvili" in digest
    assert "3. PROPOSAL Old Co" in digest and "4. UPWORK Jennifer Lawson" in digest
    assert "\u2014" not in digest  # no em dashes

    assert result["notified"]["sent"] is False and result["notified"]["test"] is True
    assert notify_mod.sent_in_test[-1]["title"] == "Pipeline sweep: 4 waiting on you"
    assert notify_mod.sent_in_test[-1]["priority"] == "high"

    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "pipeline_sweep" in rows and '""total"": 4' in rows
    assert job_log.read_shadow_log() == []


def test_dry_run_logs_but_does_not_notify(tmp_env, shadow_mode):
    notify_mod.reset_for_tests()
    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env), dry_run=True)
    assert result["notified"] is None and notify_mod.sent_in_test == []
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "dry_run" in rows


def test_cli_fixtures_replay(tmp_env, shadow_mode, capsys):
    rc = sweep.main(["--dry-run", "--fixtures", "--as-of", "2026-09-21T21:10:00-05:00"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "POSITIVE Sopio Svanishvili" in out and "Ilmi" not in out.split("POSITIVE")[0]
    assert "ilmi@shiningarmorcleaningnj.com" not in out


def test_parse_ts_variants():
    assert sweep.parse_ts("2026-09-21T23:17:28.000Z") == datetime(2026, 9, 21, 23, 17, 28, tzinfo=timezone.utc)
    assert sweep.parse_ts("2026-09-21T21:10:00-05:00") == NOW
    epoch_ms = sweep.parse_ts(1790000000000)   # ms -> seconds branch
    epoch_s = sweep.parse_ts(1790000000)
    assert epoch_ms == epoch_s and epoch_ms.tzinfo is not None
    assert sweep.parse_ts(None) is None and sweep.parse_ts("garbage") is None


# ------------------------------------------------- direction of a manual row
def cc_reply(base, minutes, to_field):
    """The same inbound row again, later, with a colleague CC'd."""
    ts = (sweep.parse_ts(base["timestamp_created"]) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    row = dict(base, id=base["id"] + "-cc", timestamp_created=ts, to_address_email_list=to_field)
    row.pop("from_address_email", None)          # manual rows carry no sender
    return row


def test_multi_recipient_inbound_is_not_counted_as_lorenzos_reply():
    """A lead who replies again and CCs their office still addresses the Advero
    inbox. Reading that as Lorenzo's outbound marks the thread answered and
    drops the unanswered positive from the sweep entirely."""
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    sopio_inbound = [m for m in manual if m["id"] == "01a0c642-758e-7b81-b648-3fe284537096"][0]
    chase = cc_reply(sopio_inbound, 1, "lorenzov@theadvero.com, office@taxfoaccounting.com")

    assert sweep.is_outbound(chase) is False
    items = sweep.find_awaiting_replies(received, manual + [chase], NOW)
    assert [i["lead_email"] for i in items] == [SOPIO]


def test_outbound_is_decided_by_the_sender_when_instantly_gives_one():
    assert sweep.is_outbound({"eaccount": "lorenzov@theadvero.com",
                              "from_address_email": "lorenzov@theadvero.com",
                              "to_address_email_list": SOPIO}) is True
    assert sweep.is_outbound({"eaccount": "lorenzov@theadvero.com",
                              "from_address_email": SOPIO,
                              "to_address_email_list": "lorenzov@theadvero.com, ops@x.co"}) is False


# ------------------------------------------------- suppressed positive rules
def test_negative_lead_who_replies_again_is_still_surfaced():
    """Instantly stamps the lead's CURRENT status on every row, so once Lorenzo
    marks a lead lost their comeback would be invisible forever."""
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    rob = [r for r in received if r["lead"] == "rob@cjsglobal.com"][0]
    comeback = dict(rob, id="rob-comeback", timestamp_created="2026-09-21T20:00:00.000Z",
                    text="Sorry I missed Friday. Still want to do this. Tuesday 2pm EST?")
    items = {i["lead_email"]: i for i in sweep.find_awaiting_replies(received + [comeback], manual, NOW)}
    assert "rob@cjsglobal.com" in items
    assert items["rob@cjsglobal.com"]["previously_negative"] is True
    assert items[SOPIO]["previously_negative"] is False
    assert "previously marked lost" in sweep.render_digest([items["rob@cjsglobal.com"]], NOW)


def test_no_show_is_not_an_explicit_negative():
    """-4 is meeting attendance, not a statement of interest: a no-show who
    writes back to reschedule is exactly what the sweep is for."""
    assert sweep.is_positive_reply({"i_status": -4, "ai_interest_value": 1}) is True
    assert sweep.is_positive_reply({"i_status": -4, "ai_interest_value": 0}) is False
    assert sweep.is_positive_reply({"i_status": -3, "ai_interest_value": 1}) is False


# ----------------------------------------------------------- the email pull
def emails_transport(rows_by_type, status=200):
    def handler(request):
        if request.method == "GET" and request.url.path == "/api/v2/emails":
            if status != 200:
                return httpx.Response(status, json={"message": "boom"})
            kind = request.url.params.get("email_type")
            return httpx.Response(200, json={"items": rows_by_type.get(kind, []), "next_starting_after": None})
        if request.method == "POST" and request.url.path == "/api/v2/leads/list":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_out_of_order_old_row_does_not_truncate_the_pull():
    """GET /emails is not guaranteed newest-first; breaking on the first old
    row threw away both unanswered positives behind it."""
    old = {"id": "old", "timestamp_created": (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    fresh = [{"id": "a", "timestamp_created": (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")},
             {"id": "b", "timestamp_created": (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    instantly = Instantly(api_key="k", transport=emails_transport({"received": [old] + fresh}))
    rows, err = sweep.fetch_emails(instantly, "received", NOW)
    assert err is None
    assert [r["id"] for r in rows] == ["a", "b"]      # the 30-day-old row is filtered, not a stop sign


def test_failed_email_pull_is_reported_not_silently_empty(tmp_env, shadow_mode):
    """A sweep that could not read a single reply must never tell Lorenzo he is
    clear."""
    notify_mod.reset_for_tests()
    instantly = Instantly(api_key="k", transport=emails_transport({}, status=500))
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env), dry_run=False)
    assert result["read_failed"] is True
    assert result["status"] == "partial"
    assert any("instantly_read_failed" in n for n in result["notes"])
    assert any("positives were NOT fully checked" in n for n in result["notes"])
    assert notify_mod.sent_in_test[-1]["priority"] == "high"
    assert "could not read Instantly" in notify_mod.sent_in_test[-1]["title"]
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "partial" in rows


def test_page_cap_fits_the_documented_rate_limit():
    """GET /emails is 20 requests per minute and the sweep pulls two types."""
    assert sweep.MAX_EMAIL_PAGES * 2 <= 20


def paging_transport(rows_per_page, total_pages, cursors_seen=None):
    """GET /emails answering `rows_per_page` rows per page for `total_pages`
    pages; only the last page carries a null cursor. `cursors_seen` records the
    `starting_after` value of every request."""
    seen = cursors_seen if cursors_seen is not None else []

    def handler(request):
        if request.method == "GET" and request.url.path == "/api/v2/emails":
            seen.append(request.url.params.get("starting_after"))
            page_no = len(seen)
            rows = [{"id": "r%d-%d" % (page_no, i),
                     "timestamp_created": (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
                    for i in range(rows_per_page)]
            cursor = ("cur%d" % page_no) if page_no < total_pages else None
            return httpx.Response(200, json={"items": rows, "next_starting_after": cursor})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_page_cap_is_reported_even_when_pages_are_smaller_than_the_limit():
    """Instantly answers a filtered list with fewer rows than `limit` while the
    cursor is still alive. Counting accumulated rows never reached a whole
    page, so the 9-page cap was hit silently and the 07:30 push read
    "0 waiting on you" with unread replies behind the cap."""
    calls = []
    instantly = Instantly(api_key="k", transport=paging_transport(50, 50, calls))
    rows, err = sweep.fetch_emails(instantly, "received", NOW)
    assert len(calls) == sweep.MAX_EMAIL_PAGES        # the cap, not the row count, stopped it
    assert len(rows) == 50 * sweep.MAX_EMAIL_PAGES
    assert err is not None and err.startswith("instantly_page_cap(received)")
    assert "cursor still open" in err


def test_nine_complete_pages_that_end_cleanly_are_not_a_read_failure():
    """The inverse false alarm: nine full pages ending with a null cursor is a
    complete pull, and reporting it as the cap made run_sweep log a `partial`
    row and breaks the deployment runbook's shadow gate."""
    calls = []
    instantly = Instantly(api_key="k", transport=paging_transport(100, sweep.MAX_EMAIL_PAGES, calls))
    rows, err = sweep.fetch_emails(instantly, "received", NOW)
    assert err is None and len(rows) == 100 * sweep.MAX_EMAIL_PAGES
    assert calls[0] is None and calls[1] == "cur1"    # the cursor really was followed


def test_a_truncated_pull_makes_the_run_partial_and_shouts(tmp_env, shadow_mode):
    notify_mod.reset_for_tests()
    instantly = Instantly(api_key="k", transport=paging_transport(50, 50, []))
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env), dry_run=False)
    assert result["read_failed"] is True and result["status"] == "partial"
    assert notify_mod.sent_in_test[-1]["priority"] == "high"


# -------------------------------------------- the ids.json calendar seed
def test_ids_seed_merges_with_store_appointments(tmp_env, monkeypatch):
    """The seed used to run only when the store had no appointment:* key at
    all, so the first appointment the engine wrote hid Lorenzo's real calls."""
    now = CT.localize(datetime(2026, 9, 23, 7, 30))    # the morning of Ilmi's 11:30 call
    store = make_store(tmp_env)
    store.set("appointment:other", {"lead_email": "other@x.co", "name": "Other",
                                    "start": (now + timedelta(hours=10)).isoformat(), "confirmed": False})
    merged = sweep.merge_appointments(sweep.appointments_from_store(store), sweep._seed_appointments_from_ids(now))
    names = sorted(a.get("name") or "" for a in merged)
    assert "Other" in names
    assert any("Ilmi" in n for n in names), names
    booked = sweep.find_unconfirmed_calls(merged, now)
    assert sorted(b["name"] for b in booked) == ["Ilmi Curovic / Shining Armor Cleaning NJ", "Other"]


def test_merge_does_not_double_count_a_call_the_store_already_holds():
    seeded = [{"name": "Ilmi Curovic / Shining Armor Cleaning NJ", "start": "2026-09-23T11:30:00-05:00",
               "lead_email": None, "source": "ids.json"}]
    stored = [{"name": "Ilmi Curovic / Shining Armor Cleaning NJ", "start": "2026-09-23T11:30:00-05:00",
               "lead_email": ILMI, "confirmed": False, "source": "store"}]
    merged = sweep.merge_appointments(stored, seeded)
    assert len(merged) == 1 and merged[0]["source"] == "store"


def test_booked_digest_line_is_unambiguous(tmp_env):
    """11:30 with no meridiem and no zone is the one line Lorenzo acts on at
    07:30."""
    now = CT.localize(datetime(2026, 9, 23, 7, 30))
    booked = sweep.find_unconfirmed_calls(sweep._seed_appointments_from_ids(now), now)
    digest = sweep.render_digest(sweep.order_items(booked), now)
    assert "11:30 AM CT" in digest, digest


# ------------------------------------------------------- what leaves the box
def test_a_call_confirmed_by_a_c_reply_leaves_the_sweep(tmp_env):
    """booking.appointment_payload hard-codes `confirmed: False` and never
    patches it; the lead's "C" reply is recorded by show_rate.mark_confirmed
    under a DIFFERENT key, `confirmed:<appointment_id>`. Reading only the
    appointment row re-emitted the confirmed call at the top of every digest."""
    from services.reply_engine import show_rate

    store = make_store(tmp_env)
    start = NOW + timedelta(hours=6)
    store.set("appointment:APPT-1", {"lead_email": ILMI, "name": "Ilmi Curovic", "company": "Shining Armor",
                                     "start": start.isoformat(), "confirmed": False, "appointment_id": "APPT-1"})
    appts = sweep.appointments_from_store(store)
    assert len(sweep.find_unconfirmed_calls(appts, NOW, store=store)) == 1

    show_rate.mark_confirmed(store, "APPT-1", NOW, start_iso=start.isoformat())
    assert sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW, store=store) == []
    # without the store the sweep can only see the row's own flag (unchanged)
    assert len(sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW)) == 1


def test_a_reschedule_drops_a_confirmation_that_was_for_the_old_start(tmp_env):
    from services.reply_engine import show_rate

    store = make_store(tmp_env)
    old = NOW + timedelta(hours=6)
    new = NOW + timedelta(hours=9)
    store.set("appointment:APPT-2", {"lead_email": ILMI, "name": "Ilmi", "start": old.isoformat(),
                                     "confirmed": False, "appointment_id": "APPT-2"})
    show_rate.mark_confirmed(store, "APPT-2", NOW, start_iso=old.isoformat())
    assert sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW, store=store) == []
    store.set("appointment:APPT-2", dict(store.get("appointment:APPT-2"), start=new.isoformat()))
    items = sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW, store=store)
    assert len(items) == 1 and items[0]["confirmed"] is False


def test_the_appointment_id_falls_back_to_the_store_key(tmp_env):
    from services.reply_engine import show_rate

    store = make_store(tmp_env)
    start = NOW + timedelta(hours=6)
    store.set("appointment:GHL-77", {"lead_email": ILMI, "name": "Ilmi", "start": start.isoformat(), "confirmed": False})
    show_rate.mark_confirmed(store, "GHL-77", NOW, start_iso=start.isoformat())
    assert sweep.appointment_id_of(sweep.appointments_from_store(store)[0]) == "GHL-77"
    assert sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW, store=store) == []


def test_the_same_call_in_the_store_and_the_seed_is_listed_once(tmp_env, monkeypatch):
    """The booking engine stores the start in UTC; config/ids.json holds the
    same instant as -05:00. Comparing isoformat() strings kept the offset, so
    the money-ordered digest led with the identical call twice."""
    now = CT.localize(datetime(2026, 9, 23, 7, 30))
    stored = [{"lead_email": ILMI, "name": "Ilmi Curovic", "start": "2026-09-23T16:30:00+00:00",
               "confirmed": False, "source": "store"}]
    seeded = sweep._seed_appointments_from_ids(now)          # carries -05:00 and the "/ company" suffix
    merged = sweep.merge_appointments(stored, seeded)
    ilmi_rows = [a for a in merged if _is_ilmi(a)]
    assert len(ilmi_rows) == 1 and ilmi_rows[0]["source"] == "store"
    booked = sweep.find_unconfirmed_calls(merged, now)
    assert len([b for b in booked if b["lead_email"] == ILMI or "Ilmi" in (b["name"] or "")]) == 1


def _is_ilmi(appt):
    return "ilmi" in ((appt.get("lead_email") or "") + " " + (appt.get("name") or appt.get("who") or "")).lower()


def test_a_malformed_store_row_does_not_kill_the_sweep(tmp_env, shadow_mode):
    """`float("TBD")` raised straight out of find_unconfirmed_calls /
    find_stale_proposals, so Lorenzo got no digest and no Job_Log row at all on
    the morning one bad store row existed."""
    notify_mod.reset_for_tests()
    store = make_store(tmp_env)
    soon = (NOW + timedelta(hours=6)).isoformat()
    store.set("appointment:bad", {"lead_email": "bad@x.co", "name": "Bad Row", "start": soon,
                                  "confirmed": False, "value": "TBD"})
    store.set("appointment:good", {"lead_email": "good@x.co", "name": "Good Row", "start": soon,
                                   "confirmed": False, "value": 9000})
    store.set("proposal:bad", {"lead_email": "p@x.co", "name": "Bad Proposal",
                               "sent_at": (NOW - timedelta(days=9)).isoformat(), "value": "ask Lorenzo"})

    items = sweep.find_unconfirmed_calls(sweep.appointments_from_store(store), NOW, notes=[])
    assert sorted(i["name"] for i in items) == ["Bad Row", "Good Row"]

    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=store, dry_run=False)
    names = [i["name"] for i in result["items"]]
    assert "Good Row" in names and "Bad Row" in names and "Bad Proposal" in names
    bad = [i for i in result["items"] if i["name"] == "Bad Row"][0]
    assert bad["value"] == sweep.default_value_for_campaign(None)     # the campaign default, not a crash
    assert any("appointment:bad" in n and "TBD" in n for n in result["notes"]), result["notes"]
    assert any("proposal:bad" in n for n in result["notes"]), result["notes"]
    assert result["status"] == "partial" and result["degraded"] is True


# ------------------------------------------------- what the sweep must not miss
def test_a_positive_reply_the_sweep_cannot_thread_is_still_reported():
    """A received row with no thread_id (a forwarded message, a shape change)
    used to be dropped before it reached `items`, with no count and no note:
    the one thing this job exists to prevent, failing silently."""
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    orphan = dict(received[0], id="orphan", lead="orphan@x.co", thread_id=None,
                  timestamp_created="2026-09-21T20:00:00.000Z", i_status=1, ai_interest_value=1,
                  subject="Re: question", text="Yes, let's talk. Thursday works.")
    notes = []
    items = {i["lead_email"]: i for i in sweep.find_awaiting_replies(received + [orphan], manual, NOW, notes=notes)}
    assert "orphan@x.co" in items
    assert items["orphan@x.co"]["thread_id"] is None          # never the synthetic grouping key
    assert items["orphan@x.co"]["threaded"] is False
    assert items[SOPIO]["threaded"] is True
    assert any(n.startswith("unthreadable_positives: 1") for n in notes), notes


def test_an_auto_responder_the_ai_labelled_interested_is_not_a_positive():
    """Instantly's code 0 is "out_of_office_or_neutral", so it cannot demote a
    row on its own; the subject the auto-responder writes about itself can."""
    ooo = {"i_status": 0, "ai_interest_value": 1, "subject": "Automatic reply: Patty, question",
           "lead": "patty.simpson@dwsimpson.com"}
    assert sweep.is_auto_reply(ooo) is True
    assert sweep.is_positive_reply(ooo) is False
    assert sweep.is_positive_reply({"i_status": 0, "ai_interest_value": 1, "subject": "Re: Sopio, question"}) is True
    # Lorenzo's own explicit "interested" click still wins
    assert sweep.is_positive_reply(dict(ooo, i_status=1)) is True
    # a do-not-reply mailbox is an auto-responder whatever the subject says
    assert sweep.is_auto_reply({"subject": "Re: question", "from_address_email": "no-reply@acme.com"}) is True
    assert sweep.is_auto_reply({"subject": "Re: question", "from_address_email": "rob@cjsglobal.com"}) is False


def test_no_recorded_september_auto_reply_reaches_the_digest():
    """22 of the 44 recorded rows are auto-replies and every one announces
    itself in the subject; exactly four leads really replied."""
    received = load("instantly_replies_2026-09.json")
    positives = set(r["lead"] for r in received if sweep.is_positive_reply(r) or sweep.is_reengagement(r))
    assert positives == {SOPIO, ILMI, "tiffany@flowerhillfs.com", "ignacio@ariacleaningservices.com",
                         "rob@cjsglobal.com"}
    for row in received:
        if sweep.is_auto_reply(row):
            assert not sweep.is_positive_reply(row), row["subject"]
    assert sum(1 for r in received if sweep.is_auto_reply(r)) >= 20


def test_two_replies_in_the_same_second_show_the_later_one():
    """Instantly stamps timestamp_created to whole seconds, so `ts > current`
    kept whichever row was iterated first, with reply_to_uuid pointing at the
    wrong email."""
    received = load("instantly_replies_2026-09.json")
    manual = load("instantly_manual_sent_2026-09.json")
    base = [r for r in received if r["lead"] == SOPIO][0]
    stamp = "2026-09-21T23:20:00.000Z"
    first = dict(base, id="01a0d000-0000-7000-0000-000000000001", timestamp_created=stamp,
                 text="Actually hold on.")
    second = dict(base, id="01a0d000-0000-7000-0000-000000000002", timestamp_created=stamp,
                  text="Thursday 4pm works, send the invite.")
    for order in ([first, second], [second, first]):
        items = {i["lead_email"]: i for i in sweep.find_awaiting_replies(received + order, manual, NOW)}
        assert "Thursday 4pm works" in items[SOPIO]["snippet"], order
        assert items[SOPIO]["reply_to_uuid"] == second["id"]


def test_the_push_still_hides_the_address_when_the_lead_record_is_missing(tmp_env, shadow_mode):
    """fetch_leads swallows an InstantlyError, so `name` falls back to the
    address; `_first_name` split on spaces and slashes and returned it whole.
    notify.redact() masks it only while the topic is unprotected, and
    deployment.md recommends NTFY_TOKEN as hardening."""
    notify_mod.reset_for_tests()
    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env),
                             leads_by_email={}, dry_run=False)
    pushed = notify_mod.sent_in_test[-1]["message"]
    assert "@" not in pushed, pushed
    assert SOPIO in result["digest"]          # the full version still names them


def test_a_nameless_booked_call_does_not_leak_the_address(tmp_env, shadow_mode):
    notify_mod.reset_for_tests()
    store = make_store(tmp_env)
    store.set("appointment:anon", {"lead_email": "sopiosvanishvili@taxfoaccounting.com",
                                   "start": (NOW + timedelta(hours=5)).isoformat(), "confirmed": False})
    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=store, dry_run=False)
    assert result["items"][0]["kind"] == "booked"
    assert "@" not in notify_mod.sent_in_test[-1]["message"]


def test_the_push_carries_no_prospect_pii(tmp_env, shadow_mode):
    """ntfy topics are unauthenticated: anyone who learns the topic can read
    every message. The push gets first names and counts; the addresses,
    companies and the prospect's own words stay in the console and Job_Log."""
    notify_mod.reset_for_tests()
    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env), dry_run=False)
    pushed = notify_mod.sent_in_test[-1]["message"]
    assert "Sopio" in pushed                      # enough for Lorenzo to know who
    assert SOPIO not in pushed
    assert "Taxfo Accounting" not in pushed
    assert "3pm-6pm" not in pushed                # not the prospect's own words
    assert "Taxfo Accounting" in result["digest"] and "3pm-6pm" in result["digest"]
    assert result["items"][0]["lead_email"] == SOPIO
