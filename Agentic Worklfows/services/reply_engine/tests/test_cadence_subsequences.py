"""Change-set tests: the Interested-quiet fallback subsequence and its apply
script (read-only in shadow).

The script under test lives in changesets/instantly_subsequences/; its copy
source is changesets/instantly_phase0/subsequence_interested_quiet.json and the
payload-shape rules are in config/instantly_api_contract.md.
"""
import importlib.util
import json
import re
from pathlib import Path

import httpx
import pytest

from shared import settings
from shared.instantly import Instantly

BASE = Path(__file__).resolve().parents[3]
CHANGESET_DIR = BASE / "changesets" / "instantly_subsequences"
COPY_SOURCE = BASE / "changesets" / "instantly_phase0" / "subsequence_interested_quiet.json"


def load_module():
    spec = importlib.util.spec_from_file_location("apply_subsequences", CHANGESET_DIR / "apply_subsequences.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return load_module()


def _text(html):
    return re.sub(r"<[^>]+>", " ", html)


def test_payload_shape_matches_post_subsequences(mod):
    payloads = mod.build_payloads()
    assert len(payloads) == 6
    ids = {c["id"] for c in settings.CAMPAIGNS.values()}
    for p in payloads:
        assert p["parent_campaign"] in ids
        assert p["name"].startswith("Interested-quiet: ")
        # conditions is required by the API and is sent carrying no trigger: an
        # auto-enrol on crm_status 1 would sweep in the positives who already
        # hold a call. `reply_contains` is omitted rather than sent as "",
        # because an empty substring is contained in every reply and that is the
        # one reading under which the create would enrol the whole campaign.
        # Whether an empty condition set enrols nobody is UNVERIFIED and is
        # settled by the post-create check in runbooks/phase0.md go-live step 10.
        assert p["conditions"] == {"crm_status": [], "lead_activity": []}
        assert "reply_contains" not in p["conditions"]
        steps = p["sequences"][0]["steps"]
        assert steps[0]["pre_delay"] == 1 and steps[0]["pre_delay_unit"] == "days"
        assert [s["delay"] for s in steps] == [2, 4, 0]
        assert mod.send_days(p) == [1, 3, 7]
        for s in steps:
            assert s["type"] == "email" and s["delay_unit"] == "days"
            body = _text(s["variants"][0]["body"])
            assert s["variants"][0]["subject"] == ""  # same thread
            assert mod.BOOKING_URL in body
            assert "—" not in body and "!" not in body
            assert body.rstrip().endswith("Lorenzo")
            assert "{{firstName}}" in body
            assert not re.search(r"\bAI\b|automat", body, re.I)
        sched = p["subsequence_schedule"]["schedules"][0]
        assert sched["timezone"] == "America/Chicago"
        assert sorted(sched["days"]) == ["0", "1", "2", "3", "4", "5", "6"]
        assert sched["days"]["0"] is False and sched["days"]["6"] is False
        stripped = mod.strip_meta(p)
        assert not any(k.startswith("_") for k in stripped)
        assert "campaign_schedule" not in stripped  # the contract's key is subsequence_schedule


def test_the_subsequence_applier_sends_the_phase0_approved_copy(mod):
    """There is one copy source. The script used to hold its own STEPS constant,
    so Lorenzo reviewed spintax copy in changesets/instantly_phase0/ while a
    different, un-spun version would have been created."""
    approved = json.loads(COPY_SOURCE.read_text(encoding="utf-8"))["campaigns"]
    for payload in mod.build_payloads():
        key = payload["_meta"]["campaign_key"]
        assert mod.strip_meta(payload) == mod.strip_meta(approved[key])
    assert not (CHANGESET_DIR / "interested_quiet_subsequences.json").exists(), \
        "a second Interested-quiet change-set is back; there must be exactly one"
    source = (CHANGESET_DIR / "apply_subsequences.py").read_text(encoding="utf-8")
    assert "STEPS = [" not in source


def test_dry_run_only_reads_and_diffs(mod, capsys):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        if request.method == "GET" and request.url.path.endswith("/subsequences"):
            parent = request.url.params.get("parent_campaign")
            if parent == settings.CAMPAIGNS["cleaning_reactivation"]["id"]:
                return httpx.Response(200, json={"items": [{"id": "sub-1", "name": "Interested-quiet: 2026 Cleaning - Client Reactivation"}]})
            return httpx.Response(200, json={"items": []})
        raise AssertionError("write attempted in dry-run: %s %s" % (request.method, request.url))

    client = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    rc = mod.main(["--dry-run"], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "plan: 5 to create, 1 already exist" in out
    assert "dry-run only; nothing was created" in out
    # the approval surface has to show what actually fires, not just a name, and
    # it must not claim verified semantics it does not have
    assert "intended: manual move only" in out
    assert "UNVERIFIED" in out
    assert "conditions match no lead" not in out
    assert "move only if: slots were offered and went unanswered" in out
    assert '"crm_status": []' in out
    assert "sends on day: [1, 3, 7]" in out
    assert "The times I floated have filled up on my end" in out
    assert all(m == "GET" for m, _, _ in calls) and len(calls) == 6


def test_apply_refused_without_a_campaign(mod, capsys):
    rc = mod.main(["--apply", "--yes"], client=None)
    assert rc == 2
    assert "one campaign at a time" in capsys.readouterr().out


def test_apply_refused_offline(mod, capsys):
    rc = mod.main(["--apply", "--campaign", "cleaning_reactivation", "--offline", "--yes"], client=None)
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().out


def test_apply_aborts_when_the_typed_confirmation_does_not_match(mod, live_mode, tmp_env, capsys):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        raise AssertionError("write attempted after a failed confirmation")

    client = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    rc = mod.main(["--apply", "--campaign", "cleaning_reactivation"], client=client, confirm=lambda p: "nope")
    assert rc == 2
    assert "aborted" in capsys.readouterr().out


def test_apply_refused_in_shadow(mod, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        raise AssertionError("write attempted in shadow: %s %s" % (request.method, request.url))

    client = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    rc = mod.main(["--apply", "--campaign", "cleaning_reactivation", "--yes"], client=client)
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []  # no backup written, nothing created


def test_apply_live_writes_one_campaign_not_six(mod, live_mode, tmp_env, tmp_path):
    """The sibling phase0 script refuses --apply without --campaign; this one
    used to create six subsequences on six live campaigns in one command."""
    posted = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        assert request.method == "POST" and request.url.path.endswith("/subsequences")
        posted.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "new-%d" % len(posted)})

    client = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    payloads = [p for p in mod.build_payloads()
                if p["_meta"]["campaign_key"] == "bookkeeping_reactivation"]
    rows = mod.plan(client, payloads)
    results = mod.apply(client, rows, backup_dir=tmp_path)
    assert len(posted) == 1
    assert posted[0]["parent_campaign"] == settings.CAMPAIGNS["bookkeeping_reactivation"]["id"]
    assert "_meta" not in posted[0]
    assert [r["result"]["id"] for r in results] == ["new-1"]
    assert len(list(tmp_path.glob("subsequences_before_*.json"))) == 1

    with pytest.raises(ValueError):
        mod.apply(client, mod.plan(client, mod.build_payloads()), backup_dir=tmp_path)


def test_apply_live_skips_a_subsequence_that_already_exists(mod, live_mode, tmp_env, tmp_path):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"items": [
                {"id": "sub-1", "name": "Interested-quiet: 2026 Cleaning - Client Reactivation"}]})
        raise AssertionError("created a duplicate subsequence")

    client = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    payloads = [p for p in mod.build_payloads() if p["_meta"]["campaign_key"] == "cleaning_reactivation"]
    results = mod.apply(client, mod.plan(client, payloads), backup_dir=tmp_path)
    assert [r["result"] for r in results] == ["skipped_exists"]
    backups = list(tmp_path.glob("subsequences_before_*.json"))
    assert json.loads(backups[0].read_text())[settings.CAMPAIGNS["cleaning_reactivation"]["id"]][0]["id"] == "sub-1"
