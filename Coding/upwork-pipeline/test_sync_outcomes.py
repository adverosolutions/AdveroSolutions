"""Tests for sync_outcomes.py on synthetic data shaped like the real Upwork MCP output."""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync_outcomes as so  # noqa: E402

HEADER = ("applied_at,job_title,job_url,job_created_utc,age_hours_at_apply,platform,build_slug,node_count,"
          "loom_url,opener_variant,opener_visible_chars,connects,boosted,viewed,replied,interviewed,hired,notes\n")


def node(pid, jid, title, status, label, modified="2026-09-10T00:00:00.000Z", reason=None):
    st = {"status": status, "status_label": label}
    if reason:
        st["reason"] = {"id": "85", "reason": reason}
    return {"node": {
        "auditDetails": {"createdDateTime": {"displayValue": "2026-09-09T10:00:00.000Z", "rawValue": "1"},
                         "modifiedDateTime": {"displayValue": modified, "rawValue": "2"}},
        "boosted": True, "id": pid,
        "marketplaceJobPosting": {"content": {"title": title}, "id": jid,
                                  "url": "https://www.upwork.com/jobs/~02%s?utm_campaign=LLM_claude_MCP_jobpost" % jid},
        "status": st,
        "terms": {"chargeRate": {"currency": "USD", "displayValue": "USD 20.0", "rawValue": "20.0"}, "connectsBid": 30}}}


def page(nodes):
    return {"data": {"vendorProposals": {"edges": nodes, "pageInfo": {"endCursor": "x", "hasNextPage": False},
                                         "totalCount": len(nodes)}},
            "hasMore": False, "status": "ok"}


PAGES = [
    page([node("p1", "1000000000000000001", "Submitted Job", "Accepted", "Submitted"),
          node("p2", "1000000000000000002", "Chatty Client", "Accepted", "Submitted")]),
    page([node("p3", "1000000000000000003", "Closed Job", "Archived", "Archived (job closed)",
               reason="Job Posting Expired")]),
    page([node("p4", "1000000000000000004", "Declined Job", "Declined", "Declined by client")]),
    page([node("p5", "1000000000000000005", "Hired Job", "Hired", "Hired")]),
    page([node("p6", "1000000000000000006", "Interview Job", "Activated", "Invitation accepted")]),
    page([node("p7", "1000000000000000007", "Not In Log", "Accepted", "Submitted")]),
    page([node("p8", "1000000000000000008", "Legacy Row Without Url For Title Match Long", "Archived",
               "Archived (job closed)")]),
]
ROOMS = {
    "p2": {"data": {"proposalRoom": {"id": "room_abc", "roomType": "INTERVIEW", "last_message_side": "client"}},
           "status": "ok"},
    "p1": {"error_code": "NOT_FOUND", "status": "error"},  # open proposal: NOT_FOUND alone proves nothing
    "p4": {"error_code": "NOT_FOUND", "status": "error"},  # declined + explicit NOT_FOUND -> replied/interviewed "no"
}
CONTRACTS = {"data": {"vendorContracts": {"contracts": [
    {"createDate": "2026-09-14T19:50:17.587Z", "id": "44501032", "offerId": "1", "status": "CLOSED",
     "title": "Chatty Client"}]}}, "status": "ok"}


def url(jid):
    return "https://www.upwork.com/jobs/~02%s" % jid


def row(title, jid, platform="n8n", opener="a", outcomes=",,,", notes="n"):
    return "2026-09-09T11:00,%s,%s,,,%s,slug,10,loom,%s,140,,,%s,%s\n" % (
        title, url(jid) if jid else "", platform, opener, outcomes, notes)


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER
                 + row("Submitted Job", "1000000000000000001")
                 + row("Chatty Client", "1000000000000000002", platform="make", opener="b")
                 + row("Closed Job", "1000000000000000003")
                 + row("Declined Job", "1000000000000000004", outcomes="yes,,,")
                 + row("Hired Job", "1000000000000000005", outcomes=",no,,")
                 + row("Interview Job", "1000000000000000006", platform="make", opener="b")
                 + row("Legacy Row Without Url For Title", None)
                 # unquoted comma in the last column: must survive byte-for-byte
                 + "2026-09-09T12:00,Untouched,%s,,,n8n,s,1,l,a,1,,,,,,,notes with, a comma\n"
                 % url("1000000000000000099"))
    return p


def run(csv_path, tmp_path, *extra):
    pj = tmp_path / "proposals.json"
    pj.write_text(json.dumps(PAGES))
    rj = tmp_path / "rooms.json"
    rj.write_text(json.dumps(ROOMS))
    cj = tmp_path / "contracts.json"
    cj.write_text(json.dumps(CONTRACTS))
    args = ["--proposals", str(pj), "--rooms", str(rj), "--contracts", str(cj), "--csv", str(csv_path)]
    return subprocess.run([sys.executable, os.path.join(HERE, "sync_outcomes.py")] + args + list(extra),
                          capture_output=True, text=True, check=True).stdout


def read(path):
    return {r["job_title"]: r for r in so.read_csv(str(path))[1]}


def test_job_id_from_url():
    assert so.job_id_from_url("https://www.upwork.com/jobs/~022102492072733453020") == "2102492072733453020"
    assert so.job_id_from_url("https://www.upwork.com/jobs/~022102068652468734100?utm_campaign=x") \
        == "2102068652468734100"
    assert so.job_id_from_url("") is None


def test_extract_handles_single_list_and_get_shapes():
    assert len(so.extract_proposals(PAGES)) == 8
    assert len(so.extract_proposals({"pages": PAGES})) == 8
    single = so.extract_proposals(PAGES[0])
    assert {p["proposal_id"] for p in single} == {"p1", "p2"}
    got = {"data": {"vendorProposal": PAGES[3]["data"]["vendorProposals"]["edges"][0]["node"]}, "status": "ok"}
    assert so.extract_proposals(got)[0]["status"] == "Hired"


def test_sync_fills_outcomes(csv_path, tmp_path):
    run(csv_path, tmp_path)
    r = read(csv_path)
    s = r["Submitted Job"]
    assert (s["viewed"], s["replied"], s["interviewed"], s["hired"]) == ("", "", "", "")
    assert s["notes"] == "n"  # no new info -> note untouched
    c = r["Chatty Client"]  # room + contract title match
    assert (c["viewed"], c["replied"], c["interviewed"], c["hired"]) == ("yes", "yes", "yes", "yes")
    assert "client messaged" in c["notes"] and "contract 44501032" in c["notes"]
    a = r["Closed Job"]  # archived, no rooms entry: only hired can be "no"
    assert (a["viewed"], a["replied"], a["interviewed"], a["hired"]) == ("", "", "", "no")
    assert "upwork: Archived (job closed) (Job Posting Expired)" in a["notes"]
    d = r["Declined Job"]
    assert (d["viewed"], d["replied"], d["interviewed"], d["hired"]) == ("yes", "no", "no", "no")
    h = r["Hired Job"]  # "no" upgraded to "yes"
    assert (h["viewed"], h["replied"], h["interviewed"], h["hired"]) == ("yes", "yes", "yes", "yes")
    i = r["Interview Job"]
    assert (i["viewed"], i["replied"], i["interviewed"], i["hired"]) == ("yes", "yes", "yes", "")
    legacy = r["Legacy Row Without Url For Title"]  # truncated title, unique prefix match
    assert (legacy["replied"], legacy["hired"]) == ("", "no")


def test_never_downgrades_or_clears(csv_path, tmp_path):
    text = csv_path.read_text().replace(
        row("Declined Job", "1000000000000000004", outcomes="yes,,,"),
        row("Declined Job", "1000000000000000004", outcomes="yes,yes,maybe,"))
    csv_path.write_text(text)
    run(csv_path, tmp_path)
    d = read(csv_path)["Declined Job"]
    assert (d["viewed"], d["replied"], d["interviewed"], d["hired"]) == ("yes", "yes", "maybe", "no")


def test_idempotent_and_untouched_rows_preserved(csv_path, tmp_path):
    untouched = [l for l in csv_path.read_text().splitlines(True) if "Untouched" in l or "Submitted Job" in l]
    run(csv_path, tmp_path)
    once = csv_path.read_text()
    for l in untouched:
        assert l in once
    out = run(csv_path, tmp_path)
    assert csv_path.read_text() == once
    assert "No new outcome info" in out


def test_dry_run_leaves_csv_and_prints_diff(csv_path, tmp_path):
    before = csv_path.read_text()
    out = run(csv_path, tmp_path, "--dry-run")
    assert csv_path.read_text() == before
    assert "Dry run: wrote" in out and "+++ proposals.csv (synced)" in out
    assert "Unmatched proposals since log start" in out and "Not In Log" in out
    assert "matched: 7 (job_id 6, title 1)" in out


def test_report_rates(csv_path, tmp_path):
    out = run(csv_path, tmp_path, "--report")
    assert "Rates by platform" in out and "Rates by opener_variant" in out
    make = [l for l in out.splitlines() if l.startswith("make ")][0]
    assert "2/2 100%" in make  # both make rows replied
    # Row 8 ("Untouched", loom_url 'l') is a skipped malformed row, so it is not in ALL (round 3, defect 1).
    assert [l for l in out.splitlines() if l.startswith("ALL")][0].split()[1] == "7"
    assert out.count("not counted (malformed, fix by hand): row 8\n") == 2


def test_report_only_without_proposals(csv_path):
    buf = io.StringIO()
    so.report(so.read_csv(str(csv_path))[1], out=buf)
    assert "Rates by platform" in buf.getvalue()


# ------------------------------------------------ reviewer defects (2026-09-22)

def write_inputs(tmp_path, pages, rooms=None, contracts=None):
    pj = tmp_path / "p.json"
    pj.write_text(json.dumps(pages))
    args = ["--proposals", str(pj)]
    if rooms is not None:
        rj = tmp_path / "r.json"
        rj.write_text(json.dumps(rooms))
        args += ["--rooms", str(rj)]
    if contracts is not None:
        cj = tmp_path / "c.json"
        cj.write_text(json.dumps(contracts))
        args += ["--contracts", str(cj)]
    return args


def sync(csv_path, args, *extra):
    return subprocess.run([sys.executable, os.path.join(HERE, "sync_outcomes.py"), "--csv", str(csv_path)]
                          + args + list(extra), capture_output=True, text=True, check=True).stdout


def contract(cid, title, date="2026-09-14T19:50:17.587Z"):
    return {"createDate": date, "id": cid, "offerId": "o" + cid, "status": "CLOSED", "title": title}


def contracts_of(*cs):
    return {"data": {"vendorContracts": {"contracts": list(cs)}}, "status": "ok"}


# Defect 1: contracts need exactly one same-title proposal, a start on/after it, and an open status.
def test_contract_with_duplicate_generic_title_is_not_applied(tmp_path):
    pages = [page([node("g1", "2000000000000000001", "AI automation", "Hired", "Hired"),
                   node("g2", "2000000000000000002", "AI Automation", "Accepted", "Submitted"),
                   node("d1", "2000000000000000003", "Cold email outreach setup!", "Declined", "Declined by client"),
                   node("u1", "2000000000000000004", "Unique Build", "Accepted", "Submitted"),
                   node("e1", "2000000000000000005", "Early Contract Job", "Accepted", "Submitted")])]
    cs = contracts_of(contract("44491561", "AI automation"),
                      contract("44501032", "Cold Email Outreach Setup"),
                      contract("50000001", "Unique Build"), contract("50000002", "Unique Build"),
                      contract("50000003", "Early Contract Job", date="2026-09-01T00:00:00.000Z"),
                      contract("50000004", "Never Proposed"))
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + row("AI automation", "2000000000000000001") + row("AI Automation", "2000000000000000002")
                 + row("Cold email outreach setup!", "2000000000000000003")
                 + row("Unique Build", "2000000000000000004") + row("Early Contract Job", "2000000000000000005"))
    out = sync(p, write_inputs(tmp_path, pages, contracts=cs))
    rows = so.read_csv(str(p))[1]
    hired_row, generic, declined, unique, early = rows
    assert hired_row["hired"] == "yes" and "contract" not in hired_row["notes"]  # yes from status only
    assert (generic["replied"], generic["hired"]) == ("", "")  # generic title: contract not applied
    assert (declined["replied"], declined["hired"]) == ("", "no") and "contract" not in declined["notes"]
    assert unique["hired"] == "yes" and "contracts 50000001, 50000002" in unique["notes"]  # no overwrite
    assert early["hired"] == ""  # contract predates the proposal
    assert "Unmatched contracts (not applied): 4" in out
    assert "50000004" in out and "no fetched proposal has this title" in out
    assert "44491561" in out and "2 fetched proposals share this title" in out
    assert "44501032" in out and "its proposal is Declined" in out
    assert "50000003" in out and "before the proposal" in out


def test_match_contracts_rejects_closed_proposal():
    props = so.extract_proposals([page([node("d", "3000000000000000001", "Some Job", "Declined", "Declined")])])
    hires, unmatched = so.match_contracts([{"id": "9", "title": "Some Job", "start": "2026-09-14"}], props)
    assert hires == {} and unmatched[0][1] == "its proposal is Declined"


# Defect 2: all job-id matches first; a URL-less row cannot claim a job that a URL row owns.
def test_url_less_legacy_row_above_url_row_of_same_job(tmp_path):
    pages = [page([node("q1", "4000000000000000001", "Duplicate Job Title Here", "Hired", "Hired")])]
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + row("Duplicate Job Title Here", None, notes="legacy")
                 + row("Duplicate Job Title Here", "4000000000000000001", notes="url row"))
    out = sync(p, write_inputs(tmp_path, pages))
    legacy, url_row = so.read_csv(str(p))[1]
    assert (legacy["hired"], legacy["notes"]) == ("", "legacy")
    assert url_row["hired"] == "yes" and url_row["notes"].startswith("url row; upwork: Hired")
    assert "matched: 1 (job_id 1, title 0)" in out


def test_proposal_claimed_by_at_most_one_row():
    props = so.extract_proposals([page([node("q", "4000000000000000002", "Twice Logged Job Title", "Hired", "Hired")])])
    rows = [{"job_url": "", "job_title": "Twice Logged Job Title"},
            {"job_url": "", "job_title": "Twice Logged Job Title"},
            {"job_url": url("4000000000000000002"), "job_title": "x"},
            {"job_url": url("4000000000000000002"), "job_title": "x"}]
    matches, _, ambiguous = so.match_rows(rows, props)
    assert list(matches) == [2] and ambiguous == []


# Defect 3: replied/interviewed "no" only with an explicit NOT_FOUND room; hired "no" for closed proposals.
def test_no_values_need_explicit_not_found():
    rooms, no_rooms = so.extract_rooms({"w2": {"error_code": "NOT_FOUND", "status": "error"},
                                        "a1": {"error_code": "NOT_FOUND", "status": "error"},
                                        "x": {"error_code": "RATE_LIMITED", "status": "error"}})
    assert rooms == {} and no_rooms == {"w2", "a1"}

    def prop(pid, status):
        return {"proposal_id": pid, "status": status, "title": "t"}
    assert so.outcomes_for(prop("w1", "Withdrawn"), rooms, no_rooms, {}) == {"hired": "no"}
    assert so.outcomes_for(prop("w2", "Withdrawn"), rooms, no_rooms, {}) == \
        {"replied": "no", "interviewed": "no", "hired": "no"}
    assert so.outcomes_for(prop("r1", "Archived"), rooms, no_rooms, {}) == {"hired": "no"}
    assert so.outcomes_for(prop("a1", "Accepted"), rooms, no_rooms, {}) == {}
    assert so.outcomes_for(prop("x", "Declined"), rooms, no_rooms, {}) == {"viewed": "yes", "hired": "no"}


# Defect 4: byte fidelity, verification before replace, mode and .bak.
def test_byte_fidelity_form_feed_u2028_and_no_final_newline(tmp_path):
    pages = [page([node("h", "5000000000000000001", "Hired Last Row", "Hired", "Hired")])]
    unchanged = [
        "2026-09-07T12:15,Form Feed Row,,,,n8n,s,1,l,a,1,,,,,,,pivot\x0cfrom VA role\n",
        "2026-09-09T17:52,\"Quoted, Title\",%s,,,n8n,s,1,l,a,1,,,,,,,\"phase 2 pasted line; A/B\"\n"
        % url("5000000000000000009"),
        "\n",
        "2026-09-10T10:00,Multi Line,,,,n8n,s,1,l,a,1,,,,,,,\"line one\nline two\x1e\x85\"\n",
    ]
    last = "2026-09-11T10:00,Hired Last Row,%s,,,n8n,s,1,l,a,1,,,,,,,n" % url("5000000000000000001")
    original = (HEADER + "".join(unchanged) + last).encode("utf-8")
    p = tmp_path / "proposals.csv"
    p.write_bytes(original)
    os.chmod(str(p), 0o640)
    sync(p, write_inputs(tmp_path, pages))
    got = p.read_bytes()
    assert got.startswith((HEADER + "".join(unchanged)).encode("utf-8"))
    assert not got.endswith(b"\n")  # last record keeps its (missing) terminator
    assert got.split(b"\n")[-1].startswith(b"2026-09-11T10:00,Hired Last Row,")
    assert so.read_csv(str(p))[1][-1]["hired"] == "yes"
    assert (tmp_path / "proposals.csv.bak").read_bytes() == original
    assert oct(os.stat(str(p)).st_mode & 0o777) == oct(0o640)
    assert [f for f in os.listdir(str(tmp_path)) if f.startswith(".proposals.")] == []


def test_split_records_round_trips_exotic_line_breaks():
    text = HEADER + "a,\"x\ny\",\x0c \x1c\r\nb\n\nc"
    recs = so.split_records(text)
    assert "".join(recs) == text and len(recs) == 5


def test_verification_mismatch_aborts_without_replacing(tmp_path, monkeypatch):
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + row("Keep Me", "6000000000000000001") + row("Change Me", "6000000000000000002"))
    before = p.read_bytes()
    header, rows, doc = so.read_csv(str(p))
    rows[1]["hired"] = "yes"
    real = so.split_records
    monkeypatch.setattr(so, "split_records", lambda t: real(t)[:-1])  # re-read loses a record
    with pytest.raises(SystemExit) as e:
        so.write_csv(str(p), header, rows, doc, {1}, backup=True)
    assert "not replaced" in str(e.value)
    assert p.read_bytes() == before
    assert os.listdir(str(tmp_path)) == ["proposals.csv"]  # no temp file, no .bak


# Defect 5: overflow fields fold into notes only when provably safe.
SLACK_ROW = ("2026-09-21T12:35,Slack Automation Specialist - Trello & Google Drive Setup,"
             "https://www.upwork.com/jobs/~022102003118918315398,2026-09-21,,make,"
             "your-slack-team-hub-trello-and-drive-wired-in,10,https://www.loom.com/share/a0e6cf1975c84adda836ef3d68a57ade,"
             "template-a-wire-setups-all-the-time-propercase,141,11,,,,,,fixed $200 UAE; SLACK first word; "
             "no price or hours stated, scope locked on call; NDA; call this week; sentence case; 1-min loom\n")


def test_malformed_slack_row_folds_safely_when_changed(tmp_path):
    pages = [page([node("2102044359068123137", "2102003118918315398",
                        "Slack Automation Specialist – Trello & Google Drive Setup", "Activated",
                        "Invitation accepted")])]
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + SLACK_ROW)
    sync(p, write_inputs(tmp_path, pages))
    recs = so.split_records(p.read_text())
    vals = next(__import__("csv").reader([recs[1]]))
    assert len(vals) == 18
    r = so.read_csv(str(p))[1][0]
    assert (r["replied"], r["interviewed"], r["hired"]) == ("yes", "yes", "")
    assert r["notes"] == ("fixed $200 UAE; SLACK first word; no price or hours stated, scope locked on call; NDA; "
                          "call this week; sentence case; 1-min loom; upwork: Invitation accepted")
    assert r["job_url"] == "https://www.upwork.com/jobs/~022102003118918315398" and r["platform"] == "make"


def test_malformed_rows_with_shifted_columns_are_skipped(tmp_path):
    pages = [page([node("m1", "7000000000000000001", "Go High Level and Meta Lead Forms Expert", "Archived",
                        "Archived (job closed)", reason="Job Posting Expired"),
                   node("m2", "7000000000000000002", "Shifted Slug Job", "Hired", "Hired")])]
    bad_url = "2026-08-11T10:00,Go High Level and Meta Lead Forms Expert, urgent,,,,n8n,slug,5,loom,v,120,,,,,,,notes\n"
    bad_outcomes = ("2026-08-12T10:00,Shifted Slug Job,%s,,,n8n,slug,extra,5,loom,v,120,,true,,,,,notes\n"
                    % url("7000000000000000002"))
    p = tmp_path / "proposals.csv"
    original = (HEADER + bad_url + bad_outcomes + SLACK_ROW).encode("utf-8")
    p.write_bytes(original)
    out = sync(p, write_inputs(tmp_path, pages), "--dry-run")
    assert out.count("WARNING: skipped malformed row") == 2
    assert "matched: 0 (job_id 0, title 0)" in out
    assert "No new outcome info" in out
    sync(p, write_inputs(tmp_path, pages))
    assert p.read_bytes() == original


def test_dry_run_report_is_labelled(csv_path, tmp_path):
    before = csv_path.read_bytes()
    out = run(csv_path, tmp_path, "--dry-run", "--report")
    assert "Rates by platform (yes / all rows in group) (dry run, not written)" in out
    assert "Rates by opener_variant (yes / all rows in group) (dry run, not written)" in out
    assert csv_path.read_bytes() == before
    assert "(dry run" not in run(csv_path, tmp_path, "--report").split("Rates by platform")[1].splitlines()[0]


# ------------------------------------------------ re-review round 2 (2026-09-22)

def full_row(title, jid, platform="n8n", opener="template-a", outcomes=",,,", notes="orig notes",
             loom="https://www.loom.com/share/aaa", slug="my-slug", nodes="12"):
    return "2026-09-10T10:00,%s,%s,2026-09-10,,%s,%s,%s,%s,%s,140,15,,%s,%s\n" % (
        title, url(jid) if jid else "", platform, slug, nodes, loom, opener, outcomes, notes)


def hired_pages(*jobs):
    return [page([node("p%d" % k, jid, title, "Hired", "Hired") for k, (jid, title) in enumerate(jobs)])]


# Defect 1: a wrong field count is synced only if the fold into notes validates every earlier column.
@pytest.mark.parametrize("bad_row, why", [
    (full_row("Comma In Platform Job", "8000000000000000001", platform="n8n, make"), "node_count='my-slug'"),
    (full_row("Comma In Opener Job", "8000000000000000001", opener="hey, built this"),
     "opener_visible_chars=' built this', boosted='15'"),
    # 17 fields: node_count missing, everything after it shifts left
    ("2026-09-10T11:00,Short Row Job,%s,2026-09-10,,n8n,my-slug,https://www.loom.com/share/bbb,template-b,140,15,"
     ",,,,,orig notes b\n" % url("8000000000000000001"), "17 fields for 18 columns (short row)"),
])
def test_wrong_field_count_rows_are_skipped_unless_fold_validates(tmp_path, bad_row, why):
    pages = hired_pages(("8000000000000000001", bad_row.split(",")[1]))
    p = tmp_path / "proposals.csv"
    original = (HEADER + bad_row + full_row("Fine Job", "8000000000000000002")).encode("utf-8")
    p.write_bytes(original)
    out = sync(p, write_inputs(tmp_path, pages), "--report")
    assert out.count("WARNING: skipped malformed row 1 ") == 1 and "line 2" in out and why in out
    assert "matched: 0 (job_id 0, title 0)" in out and "No new outcome info" in out
    assert p.read_bytes() == original  # never padded, never folded
    assert "Rates by platform" in out


def read_text_csv(tmp_path, text):
    p = tmp_path / "x.csv"
    p.write_text(text)
    return so.read_csv(str(p))


def test_fold_rules_accept_valid_extra_commas_in_notes(tmp_path):
    two = full_row("Two Commas", "8000000000000000001", notes="a, b, c")
    header, rows, doc = read_text_csv(tmp_path, HEADER + SLACK_ROW + two)
    assert doc["skip"] == {} and rows[1][None] == [" b", " c"]
    assert so.fold_problems(dict(rows[0], notes="x"), header) == []


def test_fold_rules_each_column():
    header = HEADER.strip().split(",")
    base = next(__import__("csv").DictReader([HEADER, full_row("J", "8000000000000000001", nodes="3")]))
    assert so.fold_problems(base, header) == []
    for col, v in [("applied_at", ""), ("applied_at", "Sept 10"), ("job_created_utc", "soon"),
                   ("age_hours_at_apply", "2h"), ("node_count", "1.5"), ("opener_visible_chars", " 140"),
                   ("connects", "x"), ("job_url", " urgent"), ("loom_url", "https://evil.com/loom.com"),
                   ("boosted", "maybe"), ("platform", "make "), ("platform", "n8n|excel"), ("hired", "true")]:
        assert so.fold_problems(dict(base, **{col: v}), header), (col, v)
    for col, v in [("age_hours_at_apply", "2.75"), ("platform", "n8n|make"), ("boosted", "TRUE"),
                   ("job_created_utc", "2026-09-10T10:00:00Z"), ("job_url", ""), ("loom_url", ""),
                   ("viewed", "Yes"), ("connects", "")]:
        assert so.fold_problems(dict(base, **{col: v}), header) == [], (col, v)


def test_real_slack_row_still_folds_among_bad_rows(tmp_path):
    pages = [page([node("s", "2102003118918315398", "Slack Automation Specialist - Trello & Google Drive Setup",
                        "Activated", "Invitation accepted"),
                   node("c", "8000000000000000001", "Comma In Platform Job", "Hired", "Hired")])]
    bad = full_row("Comma In Platform Job", "8000000000000000001", platform="n8n, make")
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + bad + SLACK_ROW)
    out = sync(p, write_inputs(tmp_path, pages))
    assert "matched: 1 (job_id 1, title 0)" in out and out.count("WARNING: skipped malformed row") == 1
    recs = so.split_records(p.read_text())
    assert recs[1] == bad
    r = so.read_csv(str(p))[1][1]
    assert (r["replied"], r["interviewed"]) == ("yes", "yes") and r["notes"].endswith("upwork: Invitation accepted")


# Defect 2: a proposal whose title matches several URL-less rows updates none of them.
def test_title_fallback_ambiguous_rows_match_none(tmp_path):
    pages = hired_pages(("8000000000000000004", "Generic Legacy Title Here"),
                        ("8000000000000000005", "Unique Legacy Title Here"))
    p = tmp_path / "proposals.csv"
    original = HEADER + row("Generic Legacy Title Here", None, notes="first legacy") \
        + row("Generic Legacy Title Here", None, notes="second legacy") + row("Unique Legacy Title Here", None)
    p.write_text(original)
    out = sync(p, write_inputs(tmp_path, pages))
    first, second, unique = so.read_csv(str(p))[1]
    assert (first["hired"], first["notes"]) == ("", "first legacy")
    assert (second["hired"], second["notes"]) == ("", "second legacy")
    assert unique["hired"] == "yes"
    assert "matched: 1 (job_id 0, title 1)" in out
    assert "AMBIGUOUS: 2 URL-less rows (row 1, row 2) share the title of proposal 'Generic Legacy Title Here'" in out
    assert "Unmatched proposals since log start (2026-09-09): 0" in out  # listed once, as ambiguous


def test_match_rows_reports_ambiguous_prefix_matches():
    props = so.extract_proposals(hired_pages(("8000000000000000006", "A Very Long Truncated Job Title Indeed")))
    rows = [{"job_url": "", "job_title": "A Very Long Truncated"}, {"job_url": "", "job_title": "A Very Long Truncated Job"}]
    matches, unmatched, ambiguous = so.match_rows(rows, props)
    assert matches == {} and unmatched == [] and [(p["job_id"], i) for p, i in ambiguous] == \
        [("8000000000000000006", [0, 1])]


# Defect 3: quotes are split like the csv module; unparseable records are skipped, never fatal.
def test_split_records_quote_only_opens_at_field_start():
    assert so.split_records('a,27" monitor\nb,c\n') == ['a,27" monitor\n', 'b,c\n']
    assert so.split_records('a,"x""y\nz",w\nb\n') == ['a,"x""y\nz",w\n', 'b\n']
    assert so.split_records('a,"q"tail "\nb\n') == ['a,"q"tail "\n', 'b\n']  # literal after the close
    assert so._scan_records('a,"open\nb\n') == (['a,"open\nb\n'], True)


def test_stray_quote_in_notes_does_not_swallow_rows(tmp_path):
    pages = hired_pages(("9000000000000000001", "Z Job"), ("9000000000000000002", "Other Job"))
    z = row("Z Job", "9000000000000000001", notes='client wants 27" monitor dashboard')
    other = row("Other Job", "9000000000000000002", notes="plain")
    after = row("After Job", "9000000000000000003", notes='also 12" wide')
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + z + other + after)
    out = sync(p, write_inputs(tmp_path, pages), "--report")
    assert "Rows in log: 3 | matched: 2 (job_id 2, title 0)" in out and "WARNING" not in out
    rows = so.read_csv(str(p))[1]
    assert rows[0]["notes"] == 'client wants 27" monitor dashboard; upwork: Hired' and rows[0]["hired"] == "yes"
    assert rows[1]["hired"] == "yes"
    assert so.split_records(p.read_text())[3] == after
    assert "Rates by platform" in out


@pytest.mark.parametrize("broken", [
    "2026-09-10T10:00,Broken CR,,,,n8n,s,1,l,v,1,,,,,,,notes with a lone\rcarriage return\n",  # csv.Error
    '2026-09-10T10:00,Never Closed,,,,n8n,s,1,l,v,1,,,,,,,"quote opened\n',  # EOF inside quotes
])
def test_unparseable_record_is_skipped_and_copied(tmp_path, broken):
    pages = hired_pages(("9000000000000000001", "Z Job"))
    p = tmp_path / "proposals.csv"
    z = row("Z Job", "9000000000000000001")
    tail = "" if "Never Closed" in broken else row("Tail Job", "9000000000000000009")
    p.write_text(HEADER + z + broken + tail)
    out = sync(p, write_inputs(tmp_path, pages), "--report")
    assert "WARNING: skipped malformed record, line 3" in out
    assert "Rows in log: %d | matched: 1" % (2 if tail else 1) in out
    recs = so.split_records(p.read_bytes().decode("utf-8"))  # read_text would turn \r into \n
    assert recs[2] == broken and so.read_csv(str(p))[1][0]["hired"] == "yes"
    assert "Rates by platform" in out
    rep = subprocess.run([sys.executable, os.path.join(HERE, "sync_outcomes.py"), "--csv", str(p), "--report"],
                         capture_output=True, text=True, check=True).stdout
    assert "WARNING: skipped malformed record" in rep and "Rates by opener_variant" in rep


# Defect 4: the CSV is re-checked (size, mtime, hash) immediately before os.replace.
def _append(path):
    with open(str(path), "a") as f:
        f.write("2026-09-22T17:00,Concurrent Append,,,,n8n,s,1,l,v,1,,,,,,,added by other process\n")


@pytest.mark.parametrize("hook", ["mkstemp", "copymode", "copy2", "touch"])
def test_concurrent_write_aborts_before_replace(tmp_path, monkeypatch, hook):
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + row("Keep Me", "6000000000000000001") + row("Change Me", "6000000000000000002"))
    header, rows, doc = so.read_csv(str(p))
    rows[1]["hired"] = "yes"
    if hook == "mkstemp":
        real = so.tempfile.mkstemp
        monkeypatch.setattr(so.tempfile, "mkstemp", lambda *a, **k: (real(*a, **k), _append(p))[0])
    elif hook == "copymode":
        real_cm = so.shutil.copymode
        monkeypatch.setattr(so.shutil, "copymode", lambda *a, **k: (real_cm(*a, **k), _append(p)))
    elif hook == "copy2":
        real_c2 = so.shutil.copy2
        monkeypatch.setattr(so.shutil, "copy2", lambda *a, **k: (real_c2(*a, **k), _append(p)))
    else:  # same bytes, new mtime: still refused
        real_cm = so.shutil.copymode
        monkeypatch.setattr(so.shutil, "copymode",
                            lambda *a, **k: (real_cm(*a, **k), os.utime(str(p), (1, 1))))
    replaced = []
    monkeypatch.setattr(so.os, "replace", lambda *a: replaced.append(a))
    before = p.read_bytes()
    with pytest.raises(SystemExit) as e:
        so.write_csv(str(p), header, rows, doc, {1}, backup=True)
    assert "changed since it was read" in str(e.value)
    assert replaced == []
    now = p.read_bytes()
    assert now == before if hook == "touch" else now == before + b"2026-09-22T17:00,Concurrent Append," \
        b",,,n8n,s,1,l,v,1,,,,,,,added by other process\n"
    assert [f for f in os.listdir(str(tmp_path)) if f.startswith(".proposals.")] == []
    assert not (tmp_path / "proposals.csv.bak").exists()  # an aborted run leaves no backup


def test_harness_append_between_read_and_write_aborts(tmp_path, monkeypatch):
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + row("Hired Job", "1000000000000000005"))
    args = write_inputs(tmp_path, PAGES)
    real_sum = so.summarize
    monkeypatch.setattr(so, "summarize", lambda *a, **k: (real_sum(*a, **k), _append(p))[0])
    with pytest.raises(SystemExit) as e:
        so.main(args + ["--csv", str(p)])
    assert "changed since it was read" in str(e.value)
    assert "Concurrent Append" in p.read_text() and not (tmp_path / "proposals.csv.bak").exists()


# ------------------------------------------------ re-review round 3 (2026-09-22)

def report_only(csv_path):
    return subprocess.run([sys.executable, os.path.join(HERE, "sync_outcomes.py"), "--csv", str(csv_path),
                           "--report"], capture_output=True, text=True, check=True).stdout


def rate_table(out):
    """{(dimension, group): (n, [viewed, replied, interviewed, hired] as "k/n")} from --report output."""
    got, dim = {}, None
    for line in out.splitlines():
        m = re.match(r"Rates by (\w+) ", line)
        if m:
            dim = m.group(1)
            continue
        cells = re.findall(r"(\d+/\d+) +(?:\d+%|-)", line)
        if dim and len(cells) == 4:
            name, n = re.match(r"(.*?) +(\d+) +\d+/\d+", line).groups()
            got[(dim, name)] = (int(n), cells)
    return got


# Defect 1: --report never counts a skipped row, and report-only mode names them.
A_ROWS = (  # review_sync3/a/a.csv
    "2026-09-10T10:00,Interviewed Not Hired,%s,2026-09-10,,n8n, make,my-slug,12,https://www.loom.com/share/aaa,"
    "opener-X,140,15,,yes,yes,yes,no,lost to cheaper bid\n" % url("8100000000000000001"),
    "2026-09-10T11:00,Short Hired,%s,2026-09-10,,n8n,my-slug,https://www.loom.com/share/bbb,opener-Y,140,15,,"
    "yes,yes,yes,yes,won\n" % url("8100000000000000002"),
    "2026-09-10T12:00,Clean Row,%s,2026-09-10,,n8n,my-slug,9,https://www.loom.com/share/ccc,opener-X,140,15,,"
    ",,,,plain\n" % url("8100000000000000003"),
)


@pytest.mark.parametrize("mode", ["report only", "sync and report"])
def test_comma_shifted_row_cannot_create_a_hire_in_report(tmp_path, mode):
    p = tmp_path / "proposals.csv"
    original = (HEADER + "".join(A_ROWS)).encode("utf-8")
    p.write_bytes(original)
    if mode == "report only":
        out = report_only(p)
        assert ("WARNING: skipped malformed row 1 (Interviewed Not Hired): line 2: 19 fields for 18 columns"
                in out and "WARNING: skipped malformed row 2 (Short Hired): line 3: 17 fields" in out)
        assert out.count("; not counted in the report\n") == 2
    else:
        out = sync(p, write_inputs(tmp_path, hired_pages(("8100000000000000001", "Interviewed Not Hired"))),
                   "--report")
        assert out.count("WARNING: skipped malformed row") == 2 and "matched: 0 (job_id 0, title 0)" in out
    table = rate_table(out)
    assert all(cells[3].startswith("0/") for _, cells in table.values()), table  # no hire from a shifted row
    assert table[("opener_variant", "opener-X")] == (1, ["0/1", "0/1", "0/1", "0/1"])
    assert {g for d, g in table if d == "opener_variant"} == {"opener-X", "ALL"}  # no "140" or loom-url group
    assert table[("platform", "ALL")][0] == table[("opener_variant", "ALL")][0] == 1
    assert out.count("not counted (malformed, fix by hand): row 1, row 2\n") == 2
    assert p.read_bytes() == original


def test_report_names_unparseable_records_it_leaves_out(tmp_path):
    p = tmp_path / "proposals.csv"
    p.write_bytes((HEADER + row("Fine Job", "8100000000000000009") + "2026-09-10T10:00,Broken,,,,n8n,s,1,l,v,1,"
                   ",,,,,,lone\rCR\n").encode("utf-8"))
    out = report_only(p)
    assert "WARNING: skipped malformed record, line 3" in out
    assert out.count("not counted (malformed, fix by hand): record at line 3\n") == 2
    assert rate_table(out)[("platform", "ALL")][0] == 1


# Defect 2: a quote left open is cut at the next row; the rows below are read, matched and kept on their own.
WORKIZ_OPEN_QUOTE = (  # the real Workiz row with its notes turned into an unclosed quote (review_sync3/b)
    "2026-09-09T16:27,Automation (Workiz + Quo/OpenPhone + Make + OpenAI),"
    "https://www.upwork.com/jobs/~022097783228908878142,,,make,"
    "workiz-job-to-sms-follow-up-system-ai-replies-human-approval,15,"
    "https://www.loom.com/share/41198c23ccf8408aba7cca7ca8094b69,TEST-built-yours-same-system-last-week,140,"
    ",,,,,,\"Hey Mark opener; A/B test\n")
PARTNER_ROW = (
    "2026-09-09T17:39,AI Workflow Automation & Full Stack Developer (partnerships company),"
    "https://www.upwork.com/jobs/~022097776575830928205,,,n8n,"
    "partner-operations-hub-one-record-tier-activation-ai-deliver,23,"
    "https://www.loom.com/share/8b5d6ef4889545909ccbf2d90f7392e9,TEST-built-yours-similar-build-week-ago,139,"
    ",,,,,,batch 3; hourly $25-40 vs $75-120 market; ongoing; opener A/B test\n")
OTTER_ROW = (
    "2026-09-09T17:52,\"Integrate and Automate Otter AI, Microsoft 365, RingCentral, and Docketwise\","
    "https://www.upwork.com/jobs/~022097756000490147321,,,n8n,otter-to-docketwise-case-notes-system-meetings-and-calls,"
    "18,https://www.loom.com/share/844e36944dd040c8b5d818f279700d39,TEST-built-yours-similar-build-week-ago,134,"
    ",,,,,,\"batch 3; $400 fixed for research+PDF, build is phase 2; opener A/B test\"\n")
COLD_ROW = (
    "2026-09-09T18:21,Cold Email Outreach Setup,https://www.upwork.com/jobs/~022097751877937707326,,,chart,"
    "your-cold-email-sending-infrastructure-setup-to-handover,13,"
    "https://www.loom.com/share/7812111b1d934e2388c487ab57885f6e,TEST-built-yours-similar-build-week-ago,140,"
    ",,,,,,\"batch 3; hourly no rate, avg $30; home turf; same-day setup; first native excalidraw chart\"\n")
SWALLOW_PAGES = [page([  # the real proposals for those four jobs
    node("2097800061666410497", "2097783228908878142", "Automation", "Accepted", "Submitted"),
    node("2097817664040419329", "2097776575830928205", "AI Workflow Automation & Full Stack Developer",
         "Accepted", "Submitted"),
    node("2097821513577492481", "2097756000490147321",
         "Integrate and Automate Otter AI, Microsoft 365, RingCentral, and Docketwise", "Accepted", "Submitted"),
    node("2097828606604861441", "2097751877937707326", "Cold Email Outreach Setup", "Hired", "Hired")])]
ROOM = {"data": {"proposalRoom": {"id": "room_x", "roomType": "INTERVIEW"}}, "status": "ok"}


@pytest.mark.parametrize("swallowed_row_changes", [False, True])
def test_open_quote_never_swallows_the_rows_below(tmp_path, swallowed_row_changes):
    rooms = {"2097800061666410497": ROOM}  # the swallowing Workiz row has news (review_sync3/b2)
    if swallowed_row_changes:
        rooms["2097821513577492481"] = ROOM  # and so does the swallowed Otter row
    text = HEADER + WORKIZ_OPEN_QUOTE + PARTNER_ROW + OTTER_ROW + COLD_ROW
    records, cut, open_quote = so._scan(text)
    assert records[1:] == [WORKIZ_OPEN_QUOTE, PARTNER_ROW, OTTER_ROW, COLD_ROW] and cut == {1} and not open_quote
    p = tmp_path / "proposals.csv"
    p.write_bytes(text.encode("utf-8"))
    out = sync(p, write_inputs(tmp_path, SWALLOW_PAGES, rooms=rooms), "--report")
    assert "Rows in log: 4 | matched: 3 (job_id 3, title 0)" in out
    assert ("WARNING: skipped malformed row 1 (Automation (Workiz + Quo/OpenPhone + Make + OpenAI): line 2: "
            "a quoted field is not closed before line 3, which starts the next row; left byte-for-byte") in out
    assert "(job 2097783228908878142, belongs to skipped row 1)" in out
    assert out.count("not counted (malformed, fix by hand): row 1\n") == 2
    recs = so.split_records(p.read_bytes().decode("utf-8"))
    assert recs[1] == WORKIZ_OPEN_QUOTE and recs[2] == PARTNER_ROW  # byte for byte
    header, rows, doc = so.read_csv(str(p))
    assert list(doc["skip"]) == [0] and (rows[0]["viewed"], rows[0]["replied"]) == ("", "")
    matches, _, _ = so.match_rows(rows, so.extract_proposals(SWALLOW_PAGES), skip=doc["skip"])
    assert {i: how for i, (_, how) in matches.items()} == {1: "job_id", 2: "job_id", 3: "job_id"}
    assert rows[3]["hired"] == "yes" and recs[4] != COLD_ROW
    otter = rows[2]
    if swallowed_row_changes:  # updated on its own; its quoted title is still one field
        assert (otter["replied"], otter["job_title"]) == \
            ("yes", "Integrate and Automate Otter AI, Microsoft 365, RingCentral, and Docketwise")
        assert otter["notes"] == ("batch 3; $400 fixed for research+PDF, build is phase 2; opener A/B test; "
                                  "upwork: Submitted, client messaged")
        assert recs[3].startswith('2026-09-09T17:52,"Integrate and Automate Otter AI, Microsoft 365, RingCentral, '
                                  'and Docketwise",https://www.upwork.com/jobs/~022097756000490147321,')
    else:
        assert recs[3] == OTTER_ROW
    assert len(recs) == 5 and "".join(recs[1:3]) == WORKIZ_OPEN_QUOTE + PARTNER_ROW


def test_scan_cuts_open_quote_before_next_row_with_crlf():
    text = 'h\r\n2026-01-01,"open\r\n2026-01-02,b\r\n'
    assert so._scan(text) == (["h\r\n", '2026-01-01,"open\r\n', "2026-01-02,b\r\n"], {1}, False)


def test_any_multi_line_record_is_skipped(tmp_path):
    pages = hired_pages(("8500000000000000001", "Multi Line Note Job"), ("8500000000000000002", "Plain Job"),
                        ("8500000000000000003", "Open Quote Job"))
    multi = full_row("Multi Line Note Job", "8500000000000000001", notes='"call notes:\nclient wants a demo"')
    open_quote = full_row("Open Quote Job", "8500000000000000003", notes='"left open') + "no date on this line\n"
    plain = full_row("Plain Job", "8500000000000000002")
    p = tmp_path / "proposals.csv"
    kept = (HEADER + multi + open_quote).encode("utf-8")
    p.write_bytes(kept + plain.encode("utf-8"))
    out = sync(p, write_inputs(tmp_path, pages), "--report")
    assert "Rows in log: 3 | matched: 1 (job_id 1, title 0)" in out
    assert "WARNING: skipped malformed row 1 (Multi Line Note Job): lines 2-3: a quoted field runs over" in out
    assert ("WARNING: skipped malformed row 2 (Open Quote Job): lines 4-5: a quoted field is not closed before "
            "line 6, which starts the next row") in out
    got = p.read_bytes()
    assert got.startswith(kept) and so.read_csv(str(p))[1][2]["hired"] == "yes"
    assert out.count("not counted (malformed, fix by hand): row 1, row 2\n") == 2


# Defect 3: a URL-less row whose exact title is a claimed proposal never falls back to a prefix match.
def test_exact_title_of_claimed_proposal_is_not_prefix_matched(tmp_path):
    pages = [page([
        node("pa", "8400000000000000001", "AI Automation Specialist", "Accepted", "Submitted"),
        node("pb", "8400000000000000002", "AI Automation Specialist Needed For Roofing CRM", "Hired", "Hired"),
        node("pf", "8400000000000000003",
             "n8n+Claude Automation for Freight Quoting Workflow (Email Parsing, Rates, Negotiation)",
             "Archived", "Archived (job closed)")])]
    p = tmp_path / "proposals.csv"
    p.write_text(HEADER + full_row("AI Automation Specialist", "8400000000000000001", notes="url row")
                 + full_row("AI Automation Specialist", None, notes="url-less duplicate")
                 + full_row("n8n+Claude Automation for Freight Quoting Workflow", None, notes="truncated title"))
    out = sync(p, write_inputs(tmp_path, pages))
    url_row, dup, freight = so.read_csv(str(p))[1]
    assert (dup["viewed"], dup["hired"], dup["notes"]) == ("", "", "url-less duplicate")  # not the Roofing hire
    assert (freight["hired"], freight["notes"]) == ("no", "truncated title; upwork: Archived (job closed)")
    assert "matched: 2 (job_id 1, title 1)" in out  # the prefix fallback itself stays (real Freight row)
    assert ("UNMATCHED: row 2 (AI Automation Specialist) has no job_url and its exact title is that of job "
            "8400000000000000001, already claimed by another row; not prefix-matched") in out
    assert "Unmatched proposals since log start (2026-09-10): 0 (plus 1 older)" in out  # the Roofing job
    blocked = []
    rows = so.read_csv(str(p))[1]
    matches, _, _ = so.match_rows(rows, so.extract_proposals(pages), blocked=blocked)
    assert sorted(matches) == [0, 2] and blocked == [(1, ["8400000000000000001"])]


# Should fix: an extra comma that reads as valid in opener_variant as well as notes is ambiguous.
F_ROW = ("2026-09-10T10:00,Opener Digit Job,%s,2026-09-10,,n8n,slug,12,https://www.loom.com/share/aaa,"
         "variant,2,140,,,,yes,yes,,note\n" % url("8300000000000000001"))  # review_sync3/f/f.csv


def test_extra_comma_that_also_fits_opener_is_skipped(tmp_path):
    header = HEADER.strip().split(",")
    vals = next(csv.reader([F_ROW]))
    assert so.fold_problems(dict(zip(header, vals), notes="note"), header) == []  # the round-2 check passed it
    assert so.fold_alternative(vals, header) == "opener_variant"
    assert so.fold_alternative(next(csv.reader([SLACK_ROW])), header) is None  # the real Slack row still folds
    two = next(csv.reader([full_row("Two Commas", "8000000000000000001", notes="a, b, c")]))
    assert so.fold_alternative(two, header) is None
    pages = [page([node("f", "8300000000000000001", "Opener Digit Job", "Activated", "Invitation accepted")])]
    p = tmp_path / "proposals.csv"
    original = (HEADER + F_ROW + SLACK_ROW).encode("utf-8")
    p.write_bytes(original)
    out = sync(p, write_inputs(tmp_path, pages), "--report")
    assert out.count("WARNING: skipped malformed row") == 1
    assert ("WARNING: skipped malformed row 1 (Opener Digit Job): line 2: 19 fields for 18 columns; the extra "
            "comma could be in opener_variant (or an earlier text column) as well as in notes") in out
    assert "matched: 0 (job_id 0, title 0)" in out and "No new outcome info" in out
    assert p.read_bytes() == original
    assert out.count("not counted (malformed, fix by hand): row 1\n") == 2


# Should fix: a byte-order mark does not hide the applied_at column and is written back unchanged.
def test_byte_order_mark_is_ignored_for_parsing_and_kept(tmp_path):
    pages = [page([node("s", "2102003118918315398", "Slack Automation Specialist - Trello & Google Drive Setup",
                        "Activated", "Invitation accepted")])]
    other = row("Other Row", "8600000000000000001")
    original = (so.BOM + HEADER + SLACK_ROW + other).encode("utf-8")
    p = tmp_path / "proposals.csv"
    p.write_bytes(original)
    header, rows, doc = so.read_csv(str(p))
    assert header[0] == "applied_at" and doc["skip"] == {} and so.split_records(original.decode("utf-8"))[0] \
        == so.BOM + HEADER
    out = sync(p, write_inputs(tmp_path, pages), "--dry-run")
    assert "WARNING" not in out and "matched: 1 (job_id 1, title 0)" in out
    assert "Unmatched proposals since log start (2026-09-09)" in out and p.read_bytes() == original
    sync(p, write_inputs(tmp_path, pages))
    got = p.read_bytes()
    assert got.startswith(b"\xef\xbb\xbf" + HEADER.encode("utf-8")) and got.endswith(other.encode("utf-8"))
    assert (so.read_csv(str(p))[1][0]["replied"], so.read_csv(str(p))[1][0]["interviewed"]) == ("yes", "yes")
    assert (tmp_path / "proposals.csv.bak").read_bytes() == original


# Should fix: a skipped row's proposal is listed apart, and is never title-matched to another row.
def test_proposals_of_skipped_rows_are_listed_apart(tmp_path):
    # comma in the title: every column shifts and the job URL lands in job_created_utc
    shifted = ("2026-09-08T10:00,Build me a CRM, fast,%s,2026-09-10,,n8n,slug,12,https://www.loom.com/share/a,"
               "v,140,15,,,,,,notes\n" % url("8700000000000000001"))
    pages = [page([node("k1", "8700000000000000001", "Build me a CRM, fast", "Hired", "Hired"),
                   node("k2", "8700000000000000002", "Not In Log Job", "Accepted", "Submitted")])]
    p = tmp_path / "proposals.csv"
    original = (HEADER + shifted + row("Build me a CRM fast", None, notes="url-less")).encode("utf-8")
    p.write_bytes(original)
    out = sync(p, write_inputs(tmp_path, pages))
    free = out.split("\nUnmatched proposals since log start", 1)[1]
    free, owned = free.split("Proposals that belong to a skipped row (not updated until the row is fixed): 1\n")
    assert free.startswith(" (2026-09-08): 1 (plus 0 older)\n")
    assert "Not In Log Job" in free and "8700000000000000001" not in free
    assert "Build me a CRM, fast  (job 8700000000000000001, belongs to skipped row 1)" in owned
    assert "UNMATCHED: row 2 (Build me a CRM fast)" in out and "matched: 0 (job_id 0, title 0)" in out
    assert p.read_bytes() == original  # the URL-less row did not take the skipped row's hire


# Should fix: dry runs remove their temp folder, also when the write aborts.
def test_dry_run_leaves_no_temp_folder(csv_path, tmp_path):
    tmp = tmp_path / "tmpdir"
    tmp.mkdir()
    env = dict(os.environ, TMPDIR=str(tmp))
    out = subprocess.run([sys.executable, os.path.join(HERE, "sync_outcomes.py"), "--csv", str(csv_path),
                          "--dry-run"] + write_inputs(tmp_path, PAGES, ROOMS, CONTRACTS),
                         capture_output=True, text=True, check=True, env=env).stdout
    assert "Dry run: wrote" in out and "+++ proposals.csv (synced)" in out
    assert os.listdir(str(tmp)) == []


def test_dry_run_temp_folder_removed_when_write_aborts(csv_path, tmp_path, monkeypatch):
    tmp = tmp_path / "tmpdir"
    tmp.mkdir()
    monkeypatch.setattr(so.tempfile, "tempdir", str(tmp))

    def abort(*a, **k):
        assert len(os.listdir(str(tmp))) == 1  # the temp folder exists while writing
        raise SystemExit("ABORT: test")
    monkeypatch.setattr(so, "write_csv", abort)
    with pytest.raises(SystemExit):
        so.main(write_inputs(tmp_path, PAGES, ROOMS, CONTRACTS) + ["--csv", str(csv_path), "--dry-run"])
    assert os.listdir(str(tmp)) == []


# ------------------------------------------------ insights (viewed) and --fill-boosted (2026-09-28)

def insight(opened, total, messaged=0, shortlisted=0, computed="2026-09-28T13:33:51.648Z"):
    return {"data": {"vendorProposal": {"id": "x"}}, "status": "ok",
            "insights": {"proposals_opened": opened, "proposals_total": total,
                         "proposals_unopened": total - opened, "messaged": messaged,
                         "shortlisted": shortlisted, "computed_at": computed}}


def test_insights_give_no_on_open_proposals_and_never_yes(csv_path, tmp_path):
    ij = tmp_path / "insights.json"
    ij.write_text(json.dumps({
        "p1": insight(0, 40),               # open, nobody opened anything: no
        "p3": insight(3, 3),                # Archived, everything opened: stays blank
        "p8": insight(0, 4),                # Archived, nothing opened: stays blank too
        "p7": insight(0, 9),                # not in the log
        "p2": insight(0, 5, messaged=2),    # opened 0 but a client messaged: proves nothing
    }))
    run(csv_path, tmp_path, "--insights", str(ij))
    r = read(csv_path)
    assert r["Submitted Job"]["viewed"] == "no" and "upwork: Submitted" in r["Submitted Job"]["notes"]
    assert r["Closed Job"]["viewed"] == ""
    assert r["Legacy Row Without Url For Title"]["viewed"] == ""
    assert r["Chatty Client"]["viewed"] == "yes"  # the room still says yes


def test_insights_everything_opened_never_gives_yes(csv_path, tmp_path):
    ij = tmp_path / "insights.json"
    ij.write_text(json.dumps({"p1": insight(40, 40, messaged=3, shortlisted=2)}))  # open, all opened
    run(csv_path, tmp_path, "--insights", str(ij))
    assert read(csv_path)["Submitted Job"]["viewed"] == ""
    for status in ("Accepted", "Archived", "Withdrawn", "Declined"):
        p = {"proposal_id": "p1", "status": status, "created": "2026-09-09T10:00:00.000Z"}
        assert so.viewed_from_insights(p, insight(3, 3)["insights"]) == ""
        if status in so.CLOSED_STATUSES:
            assert so.viewed_from_insights(p, insight(0, 3)["insights"]) == ""


def test_insights_no_is_upgraded_by_a_later_reply(csv_path, tmp_path):
    ij = tmp_path / "insights.json"
    ij.write_text(json.dumps({"p1": insight(0, 40)}))
    run(csv_path, tmp_path, "--insights", str(ij))
    assert read(csv_path)["Submitted Job"]["viewed"] == "no"
    rooms = dict(ROOMS, p1=ROOMS["p2"])  # the client has since messaged on p1
    sync(csv_path, write_inputs(tmp_path, PAGES, rooms, CONTRACTS), "--insights", str(ij))
    s = read(csv_path)["Submitted Job"]
    assert (s["viewed"], s["replied"]) == ("yes", "yes")


def test_insights_older_than_the_proposal_prove_nothing():
    p = {"proposal_id": "p1", "status": "Accepted", "created": "2026-09-09T10:00:00.000Z"}
    assert so.viewed_from_insights(p, insight(0, 1, computed="2026-09-09T09:00:00.000Z")["insights"]) == ""
    assert so.viewed_from_insights(p, insight(0, 1)["insights"]) == "no"
    assert so.viewed_from_insights(p, {"proposals_opened": "?"}) == ""
    assert so.extract_insights([insight(0, 1)]) == {"x": insight(0, 1)["insights"]}


def test_fill_boosted_is_opt_in_and_adds_no_note(csv_path, tmp_path):
    run(csv_path, tmp_path)
    assert all(r["boosted"] == "" for r in read(csv_path).values())
    out = run(csv_path, tmp_path, "--fill-boosted")
    r = read(csv_path)
    assert r["Submitted Job"]["boosted"] == "yes" and r["Submitted Job"]["notes"] == "n"
    assert "boosted +" in out
