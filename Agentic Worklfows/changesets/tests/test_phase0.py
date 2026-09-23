"""Phase 0 change-set tests: validator, diff generator, build freshness and the
apply script's refusal paths. Every HTTP call is httpx.MockTransport; the
clock is injected; nothing here can reach Instantly."""
import copy
import json
import os
import pathlib
import re
from datetime import datetime, timezone

import httpx
import pytest

from shared import job_log
from shared.instantly import Instantly
from changesets.instantly_phase0 import apply_instantly_phase0 as app
from changesets.instantly_phase0 import build_sequences, phase0_lib as L

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT = os.path.join(ROOT, "config", "snapshots", "instantly_campaigns_2026-09-21.json")
NOW = datetime(2026, 9, 22, 2, 10, tzinfo=timezone.utc)
KEYS = [
    "cleaning_reactivation", "cleaning_trigger", "bookkeeping_reactivation",
    "bookkeeping_trigger", "recruiting_reactivation", "recruiting_outbound",
]


@pytest.fixture(scope="module")
def snapshot():
    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
        return {c["id"]: c for c in json.load(fh)["items"]}


@pytest.fixture(scope="module")
def cfg():
    return L.load_settings()


@pytest.fixture(scope="module")
def offers_md():
    with open(os.path.join(ROOT, "config", "offers.md"), "r", encoding="utf-8") as fh:
        return fh.read()


class Recorder(object):
    """MockTransport handler: serves the snapshot on GET /campaigns/{id},
    applies a PATCH /campaigns/{id} to its own copy and answers with the
    updated campaign (what the real API returns), serves an empty label list,
    and 200 for anything else. Records every request."""

    def __init__(self, snapshot):
        self.snapshot = copy.deepcopy(snapshot)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path.startswith("/api/v2/campaigns/"):
            cid = path.rsplit("/", 1)[1]
            return httpx.Response(200, json=self.snapshot[cid])
        if request.method == "PATCH" and path.startswith("/api/v2/campaigns/"):
            cid = path.rsplit("/", 1)[1]
            self.snapshot[cid].update(json.loads(request.content))
            return httpx.Response(200, json=self.snapshot[cid])
        if request.method == "GET" and path == "/api/v2/lead-labels":
            return httpx.Response(200, json={"items": [], "next_starting_after": None})
        return httpx.Response(200, json={"ok": True, "echo": json.loads(request.content or b"{}")})

    @property
    def methods(self):
        return [r.method for r in self.requests]


def make_client(snapshot):
    rec = Recorder(snapshot)
    return Instantly(api_key="test-key", transport=httpx.MockTransport(rec), sleep=lambda s: None), rec


def collector():
    lines = []
    return lines, lines.append


# ------------------------------------------------------------ pure helpers
def test_find_tags_and_spins_nested():
    text = "{{RANDOM | Hey | Hi}} {{firstName}}, {{RANDOM | a {{companyName}} b | c}}"
    tags = L.find_tags(text)
    assert [t[2].strip().split("|")[0].strip() for t in tags] == ["RANDOM", "firstName", "RANDOM"]
    spins = list(L.iter_spins(text))
    assert [opts for _r, opts in spins] == [["Hey", "Hi"], ["a {{companyName}} b", "c"]]
    assert L.merge_variables(text) == {"firstName", "companyName"}


@pytest.mark.parametrize("bad", ["{{RANDOM | a | b}", "hello }} there", "{{firstName"])
def test_unbalanced_spintax_raises(bad):
    with pytest.raises(L.TagError):
        L.find_tags(bad)


def test_html_text_roundtrip_matches_snapshot_shape():
    text = "{{personalization}}\n\nline two\n- bullet\n\nThanks,\nLorenzo"
    html = L.text_to_html(text)
    assert html.startswith("<div>{{personalization}}</div><div><br /></div><div>line two</div>")
    assert L.html_to_text(html) == text


def test_html_to_text_on_live_body(snapshot):
    body = snapshot["8086b41e-b546-4b36-9fa0-2d01f5cc119a"]["sequences"][0]["steps"][0]["variants"][0]["body"]
    text = L.html_to_text(body)
    assert text.split("\n")[0] == "{{personalization}}"
    assert "\n\n\n" not in text
    assert text.endswith("Thanks,\nLorenzo")


def test_campaign_variables_from_snapshot(snapshot):
    names = L.campaign_variables(snapshot["f347604e-48c7-4813-831c-dc7b9d4b50ae"])
    assert {"firstName", "companyName", "personalization", "specialty"} <= names
    assert "buildingType" not in names


def test_proof_lines_parsed_from_offers(offers_md):
    proof = L.proof_lines_from_offers(offers_md)
    assert proof["reactivation"].startswith("I built a similar system for a commercial roofer doing $150M/year.")
    assert proof["outbound"].endswith("about $180,000 in new contracts in 90 days.")


# --------------------------------------------------------------- validator
@pytest.mark.parametrize("key", KEYS)
def test_staged_sequence_validates(key, snapshot, cfg, offers_md):
    doc = L.load_sequence(key)
    rep = L.validate_sequence(key, doc, snapshot[cfg["campaigns"][key]["id"]], cfg, offers_md)
    assert rep.ok, rep.summary()
    steps = doc["sequences"][0]["steps"]
    assert len(steps) == 3
    assert len(steps[0]["variants"]) == 2
    assert steps[1]["variants"][0]["subject"] == ""
    assert steps[2]["variants"][0]["subject"] == cfg["campaigns"][key]["step3_subject"]
    assert steps[0]["delay"] + steps[1]["delay"] == 7
    for _s, _v, _st, var in L.iter_variants(doc):
        text = L.html_to_text(var["body"])
        assert "—" not in text and "–" not in text
        assert text.rstrip().endswith("Lorenzo") or "P.S." in text
        n = len(list(L.iter_spins(var["subject"] + "\n" + text)))
        assert 3 <= n <= 5


def test_cleaning_trigger_new_variables_only_warn(snapshot, cfg, offers_md):
    key = "cleaning_trigger"
    rep = L.validate_sequence(key, L.load_sequence(key), snapshot[cfg["campaigns"][key]["id"]], cfg, offers_md)
    assert rep.ok
    assert any("{{buildingType}} is NEW" in w for w in rep.warnings)
    assert any("{{metro}} is NEW" in w for w in rep.warnings)


def _mutate(doc, step, variant, fn):
    import copy as _copy

    d = _copy.deepcopy(doc)
    v = d["sequences"][0]["steps"][step]["variants"][variant]
    v["body"] = fn(L.html_to_text(v["body"]))
    v["body"] = L.text_to_html(v["body"])
    return d


def _report(key, doc, snapshot, cfg, offers_md):
    return L.validate_sequence(key, doc, snapshot[cfg["campaigns"][key]["id"]], cfg, offers_md)


def test_validator_catches_em_dash(snapshot, cfg, offers_md):
    key = "cleaning_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 0, lambda t: t.replace("About me:", "About me —"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("em dash" in e for e in rep.errors)


def test_validator_catches_unknown_merge_variable(snapshot, cfg, offers_md):
    key = "bookkeeping_trigger"
    doc = _mutate(L.load_sequence(key), 1, 0, lambda t: t.replace("{{companyName}}", "{{compnyName}}"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("{{compnyName}} not in campaign variables" in e for e in rep.errors)


def test_validator_catches_unbalanced_spintax(snapshot, cfg, offers_md):
    key = "recruiting_outbound"
    doc = _mutate(L.load_sequence(key), 0, 1, lambda t: t.replace("Quick one: |", "Quick one: ", 1).replace("}} I build", " I build", 1))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("spintax/tag error" in e or "spin" in e for e in rep.errors)


def test_validator_catches_wrong_proof_point(snapshot, cfg, offers_md):
    key = "cleaning_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 0, lambda t: t.replace("$6M worth of contracts within 6 months", "$180,000 in new contracts in 90 days"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("other offer's proof number" in e for e in rep.errors)
    assert any("verbatim" in e for e in rep.errors)


def test_validator_requires_personalization_first(snapshot, cfg, offers_md):
    key = "recruiting_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 1, lambda t: "Hey there,\n" + t)
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("must start with {{personalization}}" in e for e in rep.errors)


def test_validator_spin_count_bounds(snapshot, cfg, offers_md):
    key = "cleaning_trigger"
    doc = _mutate(L.load_sequence(key), 2, 0, lambda t: t.replace("{{RANDOM | Hey | Hi}}", "Hey").replace(
        "{{RANDOM | Thanks, | Appreciate it,}}", "Thanks,").replace(build_sequences.LAST_ONE, "Last one from me on this."))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("spin points; need 3-5" in e for e in rep.errors)


def test_validator_catches_known_typo(snapshot, cfg, offers_md):
    key = "cleaning_trigger"
    doc = _mutate(L.load_sequence(key), 0, 0, lambda t: t.replace("{{personalization}}", "{{personaliztion}}", 1))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("personaliztion" in e for e in rep.errors)


def test_validator_flags_proof_drift_between_settings_and_offers(snapshot, cfg, offers_md):
    key = "cleaning_reactivation"
    drifted = offers_md.replace("$6M worth of contracts within 6 months", "$7M worth of contracts within 6 months")
    rep = _report(key, L.load_sequence(key), snapshot, cfg, drifted)
    assert any("differs from offers.md" in e for e in rep.errors)


def test_labels_taxonomy_valid():
    doc = L.load_json(L.LABELS_PATH)
    assert L.validate_labels(doc["labels"], app.EXPECTED_LABELS) == []
    assert len(doc["labels"]) == 11
    by_name = {l["label"]: l for l in doc["labels"]}
    assert by_name["unsubscribe"]["interest_status_label"] == "negative"
    assert by_name["ooo"]["interest_status_label"] == "neutral"
    assert L.validate_labels(doc["labels"][:-1], app.EXPECTED_LABELS)[0].startswith("missing labels")


# ------------------------------------------------------------------- diffs
def test_sequence_diff_on_snapshot(snapshot, cfg):
    key = "cleaning_reactivation"
    live = snapshot[cfg["campaigns"][key]["id"]]
    diff = L.sequence_diff(live, L.load_sequence(key), key)
    assert "### step1/A" in diff
    assert "### step1/B (NEW)" in diff
    assert "### step3/A (NEW)" in diff
    assert "+SUBJECT: lost bids" in diff
    assert "-DELAY: 3\n+DELAY: 4" in diff
    assert "-Know this is out of left field, if I could help recover" in diff
    assert "+{{RANDOM | Know this is out of left field, but" in diff


def test_sequence_diff_unchanged_when_identical(snapshot, cfg):
    key = "cleaning_trigger"
    live = snapshot[cfg["campaigns"][key]["id"]]
    diff = L.sequence_diff(live, {"sequences": live["sequences"]}, key)
    assert diff.count("(unchanged)") == 2 and "NEW" not in diff


def test_settings_delta_changes_pl_value_and_the_send_schedule(snapshot, cfg):
    """Tracking and stop_on_auto_reply are already right on all six; pl_value and
    campaign_schedule are the two things this change-set moves."""
    for key, c in cfg["campaigns"].items():
        delta = L.settings_delta(snapshot[c["id"]], L.desired_settings(cfg, key))
        changed = sorted(k for k, v in delta.items() if v["changed"])
        assert changed == ["campaign_schedule", "pl_value"], key
        assert delta["pl_value"]["desired"] == (6000 if c["offer"] == "reactivation" else 7500)


def test_campaign_schedule_matches_the_send_window(snapshot, cfg):
    """Five of six campaigns send 07:00-19:00 America/Detroit with Saturday on,
    which is 06:00 CT and weekends: outside shared.settings.SEND_WINDOW and the
    cadence's weekday rule."""
    from shared import settings as sh

    for key in KEYS:
        sched = L.desired_settings(cfg, key)["campaign_schedule"]["schedules"][0]
        assert sched["timezone"] == "America/Chicago", key
        assert int(sched["timing"]["from"].split(":")[0]) >= sh.SEND_WINDOW[0], key
        assert int(sched["timing"]["to"].split(":")[0]) <= sh.SEND_WINDOW[1], key
        assert sched["days"]["0"] is False and sched["days"]["6"] is False, key
        assert sorted(sched["days"]) == ["0", "1", "2", "3", "4", "5", "6"], key
        # and the live object really is the thing being corrected
        live = snapshot[cfg["campaigns"][key]["id"]]["campaign_schedule"]["schedules"][0]
        assert live["timezone"] != "America/Chicago" or live["days"].get("6") is True, key


def test_build_patch_shape(cfg):
    key = "recruiting_outbound"
    patch = L.build_patch(L.load_sequence(key), L.desired_settings(cfg, key))
    assert sorted(patch) == ["campaign_schedule", "link_tracking", "open_tracking", "pl_value", "sequences",
                             "stop_on_auto_reply"]
    assert patch["sequences"][0]["steps"][0]["type"] == "email"


def test_patch_keeps_every_step_key_the_live_steps_carry(snapshot, cfg):
    """PATCH replaces `sequences` wholesale. Every live step carries delay_unit
    and pre_delay_unit; a staged step that omits them deletes them from the live
    object and leaves the unit to a server default on all six campaigns."""
    for key in KEYS:
        live = snapshot[cfg["campaigns"][key]["id"]]
        doc = L.load_sequence(key)
        assert L.dropped_step_keys(live, doc) == [], key
        for step in doc["sequences"][0]["steps"]:
            assert step["delay_unit"] == "days" and step["pre_delay_unit"] == "days", key


def test_dropped_step_keys_reports_a_key_the_patch_would_delete(snapshot, cfg):
    import copy as _copy

    live = snapshot[cfg["campaigns"]["cleaning_reactivation"]["id"]]
    doc = _copy.deepcopy(L.load_sequence("cleaning_reactivation"))
    for step in doc["sequences"][0]["steps"]:
        step.pop("delay_unit")
    assert L.dropped_step_keys(live, doc) == ["delay_unit"]


def test_generated_files_are_fresh():
    """sequences/*.json and the subsequence file must match build_sequences.py."""
    seqs, quiet = build_sequences.build_all()
    for key, doc in seqs.items():
        assert L.load_sequence(key) == doc, "run build_sequences.py: %s is stale" % key
    assert L.load_json(L.SUBSEQUENCE_PATH) == quiet


def test_subsequence_fallback_copy(cfg):
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    assert set(quiet["campaigns"]) == set(KEYS)
    for key, sub in quiet["campaigns"].items():
        assert sub["parent_campaign"] == cfg["campaigns"][key]["id"]
        steps = sub["sequences"][0]["steps"]
        for s in steps:
            text = L.html_to_text(s["variants"][0]["body"])
            assert "—" not in text
            assert "widget/booking" in text
            assert text.rstrip().endswith("Lorenzo")
            assert s["variants"][0]["subject"] == ""


# ------------------------------------------------------------ apply script
def test_dry_run_from_snapshot_zero_requests(tmp_env, shadow_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--from-snapshot", "--no-diff"], client=client, now=NOW, out=out,
                    backup_dir=str(tmp_path / "b"), dryrun_dir=str(tmp_path / "dry"))
    assert code == 0
    assert rec.requests == []
    assert "WRITES PERFORMED: 0" in lines[-1]
    # SAF-10: a dry-run writes nothing into the backups folder...
    assert not (tmp_path / "b").exists()
    # ...its copies are suffixed .dryrun and are not rollback points: a dry-run
    # of an already-applied campaign captures the new copy.
    copies = sorted(os.listdir(tmp_path / "dry"))
    assert len(copies) == 6
    assert all(c.startswith("phase0_") and c.endswith("_20260922T021000Z.dryrun.json") for c in copies)
    with open(tmp_path / "dry" / copies[0]) as fh:
        saved = json.load(fh)
    assert "sequences" in saved and saved["_rollback_point"]["kind"] == "dryrun"
    assert job_log.read_shadow_log() == []
    # GOL-20 item 5: the dry-run rows went to a scratch log, not the real one.
    assert not job_log.job_log_path().exists()
    scratch = tmp_env / "scratch" / "phase0_dryrun" / "job_log.csv"
    assert scratch.read_text().count("phase0.dry_run,ok") == 6


def test_the_default_dry_run_uses_tmp_not_changesets_backups(tmp_env, shadow_mode, snapshot):
    client, _rec = make_client(snapshot)
    code = app.main(["--campaign", "cleaning_reactivation", "--no-diff"], client=client, now=NOW,
                    out=lambda s: None, backup_dir=str(tmp_env / "never"))
    assert code == 0
    assert not (tmp_env / "never").exists()
    dry = tmp_env / "changeset_dryruns" / "phase0"
    assert [p.name for p in dry.iterdir()] == [
        "phase0_8086b41e-b546-4b36-9fa0-2d01f5cc119a_20260922T021000Z.dryrun.json"]


def test_dry_run_combined_with_apply_is_refused_before_anything(tmp_env, live_mode, tmp_path, snapshot):
    """GOL-20 item 6: --dry-run defaulted to True and was ignored, so
    `--dry-run --apply` applied."""
    client, rec = make_client(snapshot)
    lines, out = collector()
    for argv in (["--dry-run", "--apply", "--campaign", "cleaning_reactivation", "--yes"],
                 ["--dry-run", "--apply", "--restore", "x.json", "--campaign", "cleaning_reactivation"],
                 ["--dry-run", "--labels", "--apply", "--yes"]):
        assert app.main(argv, client=client, now=NOW, out=out, backup_dir=str(tmp_path)) == app.EXIT_REFUSED
    assert rec.requests == [] and os.listdir(str(tmp_path)) == []
    assert "cannot be combined" in lines[0]


def test_dry_run_live_get_only(tmp_env, shadow_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--campaign", "bookkeeping_trigger"], client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert code == 0
    assert rec.methods == ["GET"]
    assert rec.requests[0].url.path == "/api/v2/campaigns/87ebb167-9b64-4b6f-b658-88f3d1af9980"
    text = "\n".join(lines)
    assert "CHANGE pl_value             live=1000 -> desired=7500" in text
    assert "### step3/A (NEW)" in text and "+SUBJECT: new business filings" in text


def test_apply_refused_in_shadow(tmp_env, shadow_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--apply", "--campaign", "cleaning_reactivation", "--yes"], client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert code == app.EXIT_REFUSED
    assert rec.requests == []
    assert any(l.startswith("REFUSED") for l in lines)
    with open(job_log.job_log_path()) as fh:
        assert "phase0.apply,refused" in fh.read()


def test_apply_refused_with_mode_live_but_no_allow_flag(tmp_env, monkeypatch, tmp_path, snapshot):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    client, rec = make_client(snapshot)
    code = app.main(["--apply", "--campaign", "cleaning_reactivation", "--yes"], client=client, now=NOW, out=lambda s: None, backup_dir=str(tmp_path))
    assert code == app.EXIT_REFUSED
    assert rec.requests == []


def test_apply_refused_without_campaign_even_when_live(tmp_env, live_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--apply", "--yes"], client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert code == app.EXIT_REFUSED
    assert rec.requests == []
    assert "one campaign at a time" in lines[0]


def test_apply_confirmation_mismatch_aborts(tmp_env, live_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    code = app.main(["--apply", "--campaign", "cleaning_reactivation"], client=client, now=NOW, out=lambda s: None,
                    backup_dir=str(tmp_path), confirm=lambda prompt: "nope")
    assert code == app.EXIT_REFUSED
    assert rec.requests == []


def test_apply_live_mocked_patches_once_with_backup(tmp_env, live_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--apply", "--campaign", "recruiting_reactivation", "--yes", "--no-diff"], client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"))
    assert code == 0
    # one GET, one PATCH; the PATCH response (the updated campaign) verifies it
    assert rec.methods == ["GET", "PATCH"]
    patch_req = rec.requests[1]
    assert patch_req.url.path == "/api/v2/campaigns/1d4d5bb3-40a7-4333-bf34-b269d2cc9955"
    body = json.loads(patch_req.content)
    # only the fields that differ from live are sent, all in the PATCH allow-list
    assert sorted(body) == ["campaign_schedule", "pl_value", "sequences"]
    assert body["pl_value"] == 6000
    assert len(body["sequences"][0]["steps"]) == 3
    assert "WRITES PERFORMED: 1" in lines[-1]
    written = os.listdir(tmp_path / "b")
    assert written == ["phase0_1d4d5bb3-40a7-4333-bf34-b269d2cc9955_20260922T021000Z.json"]
    with open(tmp_path / "b" / written[0]) as fh:
        point = json.load(fh)
    meta = point["_rollback_point"]
    assert meta["kind"] == "apply" and meta["script"] == "phase0" and meta["outcome"] == "landed_verified"
    assert meta["fields"] == ["campaign_schedule", "pl_value", "sequences"]
    assert point["pl_value"] == 1000                       # the BEFORE image
    with open(job_log.job_log_path()) as fh:
        assert "phase0.apply,applied" in fh.read()


def test_apply_refuses_new_variables_without_flag(tmp_env, live_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--apply", "--campaign", "cleaning_trigger", "--yes", "--no-diff"], client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert code == app.EXIT_INVALID
    assert rec.methods == ["GET"]
    assert any("--allow-new-variables" in l for l in lines)
    code = app.main(["--apply", "--campaign", "cleaning_trigger", "--yes", "--no-diff", "--allow-new-variables"], client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert code == 0
    assert rec.methods == ["GET", "GET", "PATCH"]


def test_guard_write_is_the_last_line_of_defence(tmp_env, shadow_mode, tmp_path, snapshot, cfg):
    """Even if main()'s gate were bypassed, Instantly.update_campaign returns a
    shadow record and sends nothing in shadow mode."""
    client, rec = make_client(snapshot)
    args = app.build_parser().parse_args(["--apply", "--campaign", "cleaning_reactivation", "--no-diff", "--from-snapshot"])
    lines, out = collector()
    # process_campaign re-checks live_allowed() and refuses before the write...
    result = app.process_campaign("cleaning_reactivation", cfg, client, args, out, NOW, str(tmp_path))
    assert result["writes"] == 0 and rec.requests == []
    # ...and the client itself would still only produce a would_do record.
    rec2 = client.update_campaign("8086b41e-b546-4b36-9fa0-2d01f5cc119a", {"pl_value": 6000})
    assert rec2["shadow"] is True and rec2["action"] == "update_campaign"
    assert rec.requests == []
    assert job_log.read_shadow_log()[0]["action"] == "update_campaign"


def _backup_file(tmp_path, snapshot, cid="8086b41e-b546-4b36-9fa0-2d01f5cc119a", name=None):
    """A bare campaign object: what the old scripts wrote. Not a rollback point."""
    path = tmp_path / (name or (cid + "_x.json"))
    path.write_text(json.dumps(snapshot[cid]))
    return path


def _applied(tmp_path, snapshot, key="cleaning_reactivation"):
    """Apply once in mocked live and return (client, recorder, rollback point)."""
    client, rec = make_client(snapshot)
    bdir = tmp_path / "b"
    assert app.main(["--apply", "--campaign", key, "--yes", "--no-diff"], client=client, now=NOW,
                    out=lambda s: None, backup_dir=str(bdir)) == 0
    points = [p for p in os.listdir(str(bdir)) if not p.endswith((".preapply.json", ".prerestore.json"))]
    assert len(points) == 1
    return client, rec, bdir / points[0]


def test_restore_refused_in_shadow_writes_nothing(tmp_env, live_mode, tmp_path, snapshot, monkeypatch):
    _client_, _rec, point = _applied(tmp_path, snapshot)
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    client, rec = make_client(snapshot)
    before = sorted(os.listdir(str(tmp_path / "b")))
    code = app.main(["--apply", "--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                    client=client, now=NOW, out=lambda s: None, backup_dir=str(tmp_path / "b"))
    assert code == app.EXIT_REFUSED
    assert rec.requests == []
    assert sorted(os.listdir(str(tmp_path / "b"))) == before


def test_restore_live_mocked(tmp_env, live_mode, tmp_path, snapshot):
    client, rec, point = _applied(tmp_path, snapshot)
    lines, out = collector()
    n = len(rec.requests)
    code = app.main(["--apply", "--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                    client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"))
    assert code == 0, lines
    # GET first: a restore is itself a destructive write, so the state it is
    # about to overwrite is saved before the PATCH.
    assert rec.methods[n:] == ["GET", "GET", "PATCH"]      # read, confirm, read again, write
    body = json.loads(rec.requests[n + 2].content)
    # GOL-9: only the fields the apply changed, never the full campaign body
    # (PATCH /campaigns is additionalProperties: false).
    assert sorted(body) == ["campaign_schedule", "pl_value", "sequences"]
    assert body["pl_value"] == 1000 and len(body["sequences"][0]["steps"]) == 2
    assert rec.requests[n + 1].url.path == "/api/v2/campaigns/8086b41e-b546-4b36-9fa0-2d01f5cc119a"
    pre = sorted(n_ for n_ in os.listdir(str(tmp_path / "b")) if n_.endswith(".prerestore.json"))
    assert pre == ["phase0_8086b41e-b546-4b36-9fa0-2d01f5cc119a_20260922T021000Z.prerestore.json"]
    assert "restored and verified" in "\n".join(lines)
    # a second restore is a no-op: live already matches the rollback point
    n = len(rec.requests)
    lines2, out2 = collector()
    assert app.main(["--apply", "--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                    client=client, now=NOW, out=out2, backup_dir=str(tmp_path / "b")) == 0
    assert rec.methods[n:] == ["GET"]
    assert "already matches" in "\n".join(lines2)


@pytest.mark.parametrize("outcome", ["restored_unverified", "partial", "landed_after_error",
                                     "not_restored_at_reread", "unknown"])
def test_a_restore_that_exits_3_is_logged_restore_failed(tmp_env, live_mode, tmp_path, monkeypatch, outcome):
    """Every exit-3 restore outcome is a failed restore, not an API error: the
    Job_Log row the runbook tells Lorenzo to read says restore_failed."""
    from changesets import rollback as R

    monkeypatch.setattr(R, "restore", lambda *a, **k: (R.EXIT_API, {"outcome": outcome}))
    cfg = {"campaigns": {"cleaning_reactivation": {"id": "8086b41e-b546-4b36-9fa0-2d01f5cc119a"}}}
    code = app.restore_campaign("x.json", None, lambda s: None, cfg, "cleaning_reactivation",
                                str(tmp_path), NOW)
    assert code == R.EXIT_API == 3
    with open(job_log.job_log_path()) as fh:
        text = fh.read()
    assert "phase0.restore,restore_failed" in text and "api_error" not in text


@pytest.mark.parametrize("kind", ["dryrun", "prerestore", "not_applied", "preapply", "evidence"])
def test_restore_refuses_every_file_that_is_not_a_rollback_point(tmp_env, live_mode, tmp_path, snapshot, kind):
    from changesets import rollback as R

    client, rec = make_client(snapshot)
    cid = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
    point = R.build_point("phase0", kind, snapshot[cid], ["pl_value"], NOW, cid, "cleaning_reactivation")
    path = R.write_point(str(tmp_path), "phase0_%s_x" % cid, point)
    lines, out = collector()
    code = app.main(["--apply", "--restore", path, "--campaign", "cleaning_reactivation", "--yes"],
                    client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"))
    assert code == app.EXIT_INVALID
    assert rec.requests == [] and not (tmp_path / "b").exists()
    assert "is not a rollback point" in "\n".join(lines)


def test_restore_refuses_a_legacy_bare_backup_and_another_scripts_point(tmp_env, live_mode, tmp_path, snapshot):
    """GOL-9: --restore used to accept any file with `id` and `sequences`,
    including a promotion or inbox-action backup, print "restored" and leave
    email_list untouched."""
    from changesets import rollback as R

    client, rec = make_client(snapshot)
    cid = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
    legacy = _backup_file(tmp_path, snapshot)
    other = R.write_point(str(tmp_path), "promotion_%s_x" % cid,
                          R.build_point("promotion", "apply", snapshot[cid], ["email_list"], NOW, cid))
    for path, why in ((str(legacy), "no _rollback_point block"), (other, "written by 'promotion'")):
        lines, out = collector()
        assert app.main(["--apply", "--restore", path, "--campaign", "cleaning_reactivation", "--yes"],
                        client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b")) == app.EXIT_INVALID
        assert why in "\n".join(lines)
    assert rec.requests == []


def test_a_preapply_left_by_a_crash_restores_only_with_accept_interrupted(tmp_env, live_mode, tmp_path, snapshot):
    from changesets import rollback as R

    client, rec = make_client(snapshot)
    cid = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
    rec.snapshot[cid]["pl_value"] = 6000
    path = R.write_point(str(tmp_path), "phase0_%s_x" % cid,
                         R.build_point("phase0", "preapply", snapshot[cid], ["pl_value"], NOW, cid,
                                       after={"pl_value": 6000}))
    argv = ["--apply", "--restore", path, "--campaign", "cleaning_reactivation", "--yes"]
    assert app.main(argv, client=client, now=NOW, out=lambda s: None, backup_dir=str(tmp_path / "b")) == 1
    assert rec.requests == []
    assert app.main(argv + ["--accept-interrupted"], client=client, now=NOW, out=lambda s: None,
                    backup_dir=str(tmp_path / "b")) == 0
    assert json.loads(rec.requests[-1].content) == {"pl_value": 1000}


def test_restore_without_apply_is_refused_before_any_write(tmp_env, live_mode, tmp_path, snapshot):
    """--restore used to dispatch before the --apply gate, so in live mode it
    PATCHed a campaign with no --apply, no --yes and no confirmation prompt."""
    client, rec = make_client(snapshot)
    prompts = []
    backup = _backup_file(tmp_path, snapshot)
    code = app.main(["--restore", str(backup), "--campaign", "cleaning_reactivation"], client=client, now=NOW,
                    out=lambda s: None, backup_dir=str(tmp_path), confirm=lambda p: prompts.append(p) or "yes")
    assert code == app.EXIT_REFUSED
    assert rec.requests == [] and prompts == []


def test_restore_refuses_a_backup_whose_id_is_another_campaign(tmp_env, live_mode, tmp_path, snapshot):
    """A copied or hand-edited backup file used to PATCH whatever id was inside
    it, so cleaning copy could land on the recruiting campaign."""
    client, rec = make_client(snapshot)
    backup = _backup_file(tmp_path, snapshot, name="cleaning_looking_backup.json")
    code = app.main(["--apply", "--restore", str(backup), "--campaign", "recruiting_outbound", "--yes"],
                    client=client, now=NOW, out=lambda s: None, backup_dir=str(tmp_path))
    assert code == app.EXIT_INVALID
    assert rec.requests == []


def test_apply_against_a_snapshot_is_refused_before_a_backup_is_written(tmp_env, live_mode, tmp_path, snapshot):
    """--apply --from-snapshot used to validate, print, write a backup of stale
    snapshot data and then die with AttributeError because no client existed."""
    lines, out = collector()
    backup_dir = tmp_path / "b"
    code = app.main(["--apply", "--campaign", "recruiting_reactivation", "--yes", "--no-diff", "--from-snapshot"],
                    client=None, now=NOW, out=out, backup_dir=str(backup_dir))
    assert code == app.EXIT_REFUSED
    assert lines[0].startswith("REFUSED")
    assert not backup_dir.exists()


def test_apply_with_no_backup_is_refused(tmp_env, live_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--apply", "--campaign", "recruiting_reactivation", "--yes", "--no-diff", "--no-backup"],
                    client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"))
    assert code == app.EXIT_REFUSED
    assert rec.requests == []
    assert any("no rollback point" in l for l in lines)


def test_labels_dry_run_get_only(tmp_env, shadow_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    code = app.main(["--labels"], client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert code == 0
    assert rec.methods == ["GET"]
    assert "11 would be created" in lines[0]
    assert "writes=0" in lines[-1]


def test_labels_apply_refused_in_shadow(tmp_env, shadow_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    code = app.main(["--labels", "--apply", "--yes"], client=client, now=NOW, out=lambda s: None, backup_dir=str(tmp_path))
    assert code == app.EXIT_REFUSED
    assert rec.requests == []


def test_unknown_campaign_key(tmp_env, shadow_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    code = app.main(["--campaign", "hvac"], client=client, now=NOW, out=lambda s: None, backup_dir=str(tmp_path))
    assert code == app.EXIT_INVALID and rec.requests == []


# ---------------------------------------------------------- hard copy rules
def test_validator_errors_on_exclamation_mark(snapshot, cfg, offers_md):
    key = "cleaning_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 0, lambda t: t.replace("Let me know.", "Let me know!"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("exclamation mark" in e for e in rep.errors)
    assert not rep.ok


def test_validator_errors_on_ai_or_automation_mention(snapshot, cfg, offers_md):
    key = "cleaning_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 0,
                  lambda t: t.replace("About me: I build client reactivation systems.",
                                      "About me: I build AI automation that does this for you."))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("AI/automation" in e for e in rep.errors)
    assert not rep.ok


@pytest.mark.parametrize("key", KEYS)
def test_no_staged_variant_contains_an_exclamation_mark_or_mentions_ai(key):
    doc = L.load_sequence(key)
    for _s, _v, _st, var in L.iter_variants(doc):
        combined = var["subject"] + "\n" + L.html_to_text(var["body"])
        assert "!" not in combined
        assert not L.AI_RE.search(combined)
    quiet = L.load_json(L.SUBSEQUENCE_PATH)["campaigns"][key]
    for step in quiet["sequences"][0]["steps"]:
        text = L.html_to_text(step["variants"][0]["body"])
        assert "!" not in text
        assert not L.AI_RE.search(text)


def test_validator_catches_a_guarantee_number_not_in_offers_md(snapshot, cfg, offers_md):
    """A typo or an edit in build_sequences.py must not be able to promise a
    number Lorenzo never agreed to: every $ figure is a contractual promise."""
    key = "cleaning_trigger"
    doc = _mutate(L.load_sequence(key), 0, 0, lambda t: t.replace("$24,000", "$240,000"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("$240,000 is not in this campaign" in e for e in rep.errors)

    doc = _mutate(L.load_sequence("recruiting_outbound"), 0, 0, lambda t: t.replace("$200", "$500"))
    rep = _report("recruiting_outbound", doc, snapshot, cfg, offers_md)
    assert any("$500 is not in this campaign" in e for e in rep.errors)


def test_validator_catches_a_time_window_not_in_offers_md(snapshot, cfg, offers_md):
    key = "cleaning_trigger"
    doc = _mutate(L.load_sequence(key), 0, 0, lambda t: t.replace("90 days", "30 days"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("time window 30 days is not in this campaign" in e for e in rep.errors)


def test_validator_rejects_a_guarantee_on_a_reactivation_campaign(snapshot, cfg, offers_md):
    """offers.md gives the three reactivation offers no guarantee at all."""
    key = "bookkeeping_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 0,
                  lambda t: t + "\n\nI guarantee $50,000 in recovered fees in 60 days or your money back.")
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("guarantee language" in e for e in rep.errors)
    assert any("$50,000 is not in this campaign" in e for e in rep.errors)


@pytest.mark.parametrize("key", ["cleaning_reactivation", "bookkeeping_reactivation", "recruiting_reactivation"])
def test_no_reactivation_copy_promises_a_guarantee(key):
    doc = L.load_sequence(key)
    for _s, _v, _st, var in L.iter_variants(doc):
        text = L.html_to_text(var["body"])
        assert not L.GUARANTEE_RE.search(text), text


def test_validator_rejects_identical_ab_variants(snapshot, cfg, offers_md):
    """The M3.3 verdict rule judges A against B at 500 sends each; identical
    variants make it compare a variant with itself for 1,000 sends."""
    import copy as _copy

    key = "cleaning_reactivation"
    doc = _copy.deepcopy(L.load_sequence(key))
    step = doc["sequences"][0]["steps"][0]
    step["variants"][1] = _copy.deepcopy(step["variants"][0])
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("identical to step1/variantA" in e for e in rep.errors)


def test_validator_rejects_duplicate_spin_options(snapshot, cfg, offers_md):
    key = "cleaning_reactivation"
    doc = _mutate(L.load_sequence(key), 0, 0,
                  lambda t: t.replace("{{RANDOM | Let me know. | Worth a look? | Open to it?}}",
                                      "{{RANDOM | Let me know. | Let me know.}}"))
    rep = _report(key, doc, snapshot, cfg, offers_md)
    assert any("repeats an option" in e for e in rep.errors)


# --------------------------------------------------------------- the labels
def _hostile_replies():
    path = os.path.join(ROOT, "services", "reply_engine", "tests", "fixtures", "instantly_replies_2026-09.json")
    with open(path, "r", encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("i_status") == -1]


def test_label_examples_do_not_reuse_a_hostile_reply():
    """The AI labeler follows these descriptions. If a positive or neutral label
    quotes a line from a reply that was actually hostile, that lead is labeled
    neutral and never reaches the blocklist + DND route."""
    labels = L.load_json(L.LABELS_PATH)["labels"]
    hostile = _hostile_replies()
    assert hostile, "fixture has no negative replies to check against"
    for lab in labels:
        if lab["interest_status_label"] == "negative":
            continue
        for ex in lab["examples"]:
            for reply in hostile:
                assert ex.lower() not in (reply.get("text") or "").lower(), (
                    "%s teaches the labeler a line from %s's hostile reply: %r"
                    % (lab["label"], reply["from_address_email"], ex))


def test_every_label_example_is_in_the_description_the_api_receives():
    for lab in L.load_json(L.LABELS_PATH)["labels"]:
        assert lab["examples"]
        for ex in lab["examples"]:
            assert ex in lab["description"]


# --------------------------------------------------------- the subsequence
def test_subsequence_uses_pre_delay_so_the_first_touch_lands_on_day_1(cfg):
    """config/instantly_api_contract.md: on a subsequence `delay` is the wait
    before the NEXT email and `pre_delay` the wait before the FIRST. Without
    pre_delay the "D1/D3/D7" fallback fires on day 0, 1 and 3: three chases in
    three days to a warm positive, the first one minutes after Lorenzo's own
    reply."""
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    for key, sub in quiet["campaigns"].items():
        steps = sub["sequences"][0]["steps"]
        assert steps[0]["pre_delay"] == 1 and steps[0]["pre_delay_unit"] == "days", key
        days, day = [], 0
        for i, step in enumerate(steps):
            day += int(step.get("pre_delay") or 0) if i == 0 else int(steps[i - 1]["delay"])
            days.append(day)
        assert days == [1, 3, 7], (key, days)
        assert sub["_meta"]["send_days"] == [1, 3, 7]


def test_subsequence_payload_matches_the_api_contract(cfg):
    """POST /subsequences: required parent_campaign, name, conditions; the
    schedule key is subsequence_schedule; timing is HH:MM; days are "0".."6"."""
    import re as _re

    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    allowed = {"parent_campaign", "name", "conditions", "subsequence_schedule", "sequences", "daily_limit_mode"}
    for key, sub in quiet["campaigns"].items():
        payload = {k: v for k, v in sub.items() if not k.startswith("_")}
        assert {"parent_campaign", "name", "conditions", "sequences"} <= set(payload), key
        assert set(payload) <= allowed, (key, sorted(set(payload) - allowed))
        assert "trigger" not in payload, key
        sched = payload["subsequence_schedule"]["schedules"][0]
        for bound in ("from", "to"):
            assert _re.match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", sched["timing"][bound]), key
        assert sorted(sched["days"]) == ["0", "1", "2", "3", "4", "5", "6"], key
        assert sched["timezone"] == "America/Chicago", key


def test_subsequence_enrols_nobody_automatically(cfg):
    """No lead in any campaign carries crm_status 2 (meeting booked), so
    "already has a call booked" cannot be expressed in Instantly today and a
    crm_status [1] condition would enrol the positives who hold discovery calls
    and email them that their slot is gone. Enrolment is by explicit move."""
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    for key, sub in quiet["campaigns"].items():
        assert sub["conditions"]["crm_status"] == [], key
        assert sub["_meta"]["enrolment"] == "manual move only", key


def test_subsequence_d3_mechanism_matches_the_campaign_niche(cfg):
    """quiet_copy used to branch on offer type only, so a bookkeeping or
    recruiting positive was told to send "the accounts that cancelled or
    stopped renewing"."""
    quiet = L.load_json(L.SUBSEQUENCE_PATH)

    def d3(key):
        return L.html_to_text(quiet["campaigns"][key]["sequences"][0]["steps"][1]["variants"][0]["body"]).lower()

    assert "tax season" in d3("bookkeeping_reactivation") and "former clients" in d3("bookkeeping_reactivation")
    assert "placements" in d3("recruiting_reactivation") and "dormant" in d3("recruiting_reactivation")
    assert "cancelled" in d3("cleaning_reactivation")
    assert "cancelled" not in d3("bookkeeping_reactivation") and "cancelled" not in d3("recruiting_reactivation")
    assert "new leases" in d3("cleaning_trigger")
    assert "new business filings" in d3("bookkeeping_trigger")
    assert "job boards" in d3("recruiting_outbound")
    bodies = [d3(k) for k in KEYS]
    assert len(set(bodies)) == len(bodies), "two campaigns share the same D3 mechanism line"


def test_changeset_docs_match_the_api_contract():
    """POST /leads/subsequence/move takes ONE lead as `id`; there is no `ids`
    array. Anyone following a doc that says otherwise moves nobody and never
    finds out, because nothing in the change-set calls the endpoint."""
    paths = [os.path.join(ROOT, "runbooks", n) for n in os.listdir(os.path.join(ROOT, "runbooks"))
             if n.endswith(".md")]
    paths.append(os.path.join(ROOT, "config", "instantly_api_contract.md"))
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "changesets")):
        if "backups" in dirpath or os.path.basename(dirpath) == "tests":
            continue  # this file quotes both shapes on purpose
        paths += [os.path.join(dirpath, n) for n in files if n.endswith((".json", ".md", ".py"))]
    mentions = 0
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if "subsequence/move" not in text:
            continue
        mentions += 1
        assert "{ids," not in text and '"ids"' not in text, path
        assert ("{id, subsequence_id}" in text or '{"id", "subsequence_id"}' in text
                or '{"id": "<lead uuid>", "subsequence_id"' in text), path
    assert len(paths) > 10 and mentions >= 2


def test_booking_url_and_note_come_from_ids_json():
    ids = L.load_json(os.path.join(ROOT, "config", "ids.json"))
    cal = ids["ghl"]["calendars"]["discovery_call"]
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    assert quiet["booking_url_note"] == cal["booking_url_note"]
    assert "VERIFIED" in cal["booking_url_note"]
    for sub in quiet["campaigns"].values():
        for step in sub["sequences"][0]["steps"]:
            assert cal["booking_url"] in L.html_to_text(step["variants"][0]["body"])
    # the checklist and the runbook must not tell Lorenzo to verify it again
    for path in (os.path.join(ROOT, "changesets", "PHASE0_MANUAL_CHECKLIST.md"),
                 os.path.join(ROOT, "runbooks", "phase0.md")):
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "verify before using in copy" not in text, path
        assert "verify the public widget URL" not in text, path


# -------------------------------------------------------------- the drafts
DRAFTS_DIR = os.path.join(ROOT, "changesets", "drafts")
CONFERENCING = {"zoom": "zoom", "google meet": "google_conference", "teams": "teams", "whereby": "whereby"}

# The two calls already on the books are hand-made Zoom meetings on Lorenzo's own
# Google Calendar, NOT GHL Discovery Call bookings, so ids.json's
# google_conference / isZoomAdded=false does not describe them. Both events were
# read read-only on 2026-09-22 and both carry a us06web.zoom.us location.
BOOKED_EVENT_CONFERENCING = {
    "ilmi_wednesday_confirmation.md": "zoom",
    "sopio_confirmation.md": "zoom",
}
BOOKED_EVENT_IDS = {
    "ilmi_wednesday_confirmation.md": "eqlug7qn67rnjdppja91ffuto0",
    "sopio_confirmation.md": "j8n9pmfjl3cufeiu58g4kp12c8",
}

# Positives in the recorded replies who deliberately get no draft, each with the
# reason the checklist has to repeat. A name may only be added here with an
# outcome that is already recorded somewhere Lorenzo can check.
DISPOSITIONED = {
    "rob@cjsglobal.com": "proposed 2pm EST Fri 2026-09-18; marked lt_interest_status -3 (lost) 13:25 CT that day",
    "ignacio@ariacleaningservices.com": "asked on 2026-09-16 to touch base next month; answered and parked until October",
}


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _draft_campaign_key(name):
    """The campaign key a draft's header names, or None for the Upwork drafts."""
    text = _read(os.path.join(DRAFTS_DIR, name))
    head = text.split("Subject:")[0]
    for key in KEYS:
        if key in head:
            return key
    return None


def _draft_bodies():
    out = {}
    for name in sorted(os.listdir(DRAFTS_DIR)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(DRAFTS_DIR, name), "r", encoding="utf-8") as fh:
            text = fh.read()
        body = text.split("\n---\n")[0]
        # everything from the Subject line down is what the client reads
        idx = body.find("Subject:")
        out[name] = body[idx:] if idx >= 0 else body
    return out


NOT_A_MESSAGE_MARKER = "NOT A MESSAGE:"


def test_drafts_obey_the_copy_rules(offers_md):
    """These go to real clients by hand. Nothing checked them before.

    A file carrying NOT_A_MESSAGE_MARKER is a hand-step note rather than copy
    (the ClosePoint/RoutVox invitations cannot be read through the API, so
    there is nothing to draft against). It still obeys every copy rule; it is
    only excused the signature, and it has to say so in the file, where a
    reviewer sees it.
    """
    import re as _re

    bodies = _draft_bodies()
    assert len(bodies) >= 6
    for name, body in bodies.items():
        assert "—" not in body and "–" not in body, name
        assert "!" not in body, name
        assert not L.AI_RE.search(body), name
        if NOT_A_MESSAGE_MARKER in body:
            continue
        assert body.rstrip().endswith("Lorenzo"), name
        for money in _re.findall(r"\$\d[\d,]*(?:\.\d+)?[KkMm]?", body):
            assert money in offers_md, "%s promises %s, which is not in offers.md" % (name, money)


def test_no_draft_promises_a_conferencing_provider_that_is_not_connected():
    """ids.json records the GHL Discovery Call calendar as google_conference
    with isZoomAdded=false, so a draft that points a lead at the booking widget
    and then says "the Zoom link is on the invite" sends them looking for a link
    that is not there.

    The two calls already on the books are the exception, and it is a verified
    one: they are hand-made Zoom meetings on Lorenzo's own Google Calendar, not
    GHL bookings, and both invites really do carry a us06web.zoom.us link (see
    BOOKED_EVENT_CONFERENCING). A draft for one of those leads may name the
    provider that is actually on that lead's event, and no other.
    """
    ids = L.load_json(os.path.join(ROOT, "config", "ids.json"))
    conferencing = ids["ghl"]["calendars"]["discovery_call"]["conferencing"]
    primary = conferencing.split("(")[0].strip().lower()
    for name, body in _draft_bodies().items():
        allowed = {primary, BOOKED_EVENT_CONFERENCING.get(name)}
        for label, token in CONFERENCING.items():
            if token in allowed:
                continue
            assert label not in body.lower(), "%s names %s, but the calendar is %s" % (name, label, primary)


def test_a_draft_that_names_zoom_is_one_whose_lead_holds_a_verified_zoom_event():
    """The inverse guard: BOOKED_EVENT_CONFERENCING is an exception list, so it
    must not be possible to add a draft to it without the evidence. Every entry
    names a Google Calendar event id, and the draft has to quote that id."""
    bodies_and_headers = {}
    for fname in sorted(os.listdir(DRAFTS_DIR)):
        if fname.endswith(".md"):
            with open(os.path.join(DRAFTS_DIR, fname), "r", encoding="utf-8") as fh:
                bodies_and_headers[fname] = fh.read()
    for fname, provider in BOOKED_EVENT_CONFERENCING.items():
        assert fname in bodies_and_headers, fname
        text = bodies_and_headers[fname]
        event_id = BOOKED_EVENT_IDS[fname]
        assert event_id in text, "%s claims a %s event but never names event %s" % (fname, provider, event_id)
        assert "us06web.zoom.us" in text, "%s must quote the verified link host" % fname
    # and nothing outside the exception list mentions a non-primary provider
    ids = L.load_json(os.path.join(ROOT, "config", "ids.json"))
    primary = ids["ghl"]["calendars"]["discovery_call"]["conferencing"].split("(")[0].strip().lower()
    for fname, body in _draft_bodies().items():
        if fname in BOOKED_EVENT_CONFERENCING:
            continue
        for label, token in CONFERENCING.items():
            if token != primary:
                assert label not in body.lower(), fname


def test_every_dollar_figure_in_a_draft_is_in_that_leads_own_offers_md_row(cfg, offers_md):
    """`money in offers_md` only asks whether a figure appears SOMEWHERE in the
    offer sheet. Appending "the $24,000 guarantee" to the Sopio draft passes
    that check ($24,000 is cleaning_trigger's guarantee) and hands a
    bookkeeping_reactivation prospect a written guarantee her offer does not
    have. Check each draft against its own campaign's row instead."""
    for name, body in _draft_bodies().items():
        key = _draft_campaign_key(name)
        if key is None:
            assert not L.money_values(body), "%s quotes money but names no campaign key" % name
            continue
        offer = cfg["campaigns"][key]["offer"]
        allowed_money, allowed_periods = L.allowed_offer_numbers(key, offer, offers_md)
        extra = sorted(L.money_values(body) - allowed_money)
        assert not extra, "%s (%s) promises %s, not in that campaign's offers.md row" % (name, key, extra)
        extra_windows = sorted(L.period_phrases(body) - allowed_periods)
        assert not extra_windows, "%s (%s) promises the window %s" % (name, key, extra_windows)
        if offer == "reactivation":
            g = L.GUARANTEE_RE.search(body)
            assert g is None, "%s is on a reactivation offer but says %r" % (name, g.group(0) if g else "")


def test_every_positive_reply_in_the_recorded_fixtures_has_a_draft_or_a_named_disposition():
    """test_every_open_positive_in_ids_json_has_a_draft reads ids.json, so a
    positive who never became a GHL opportunity is invisible to it, and one is:
    rob@cjsglobal.com replied twice with ai_interest_value 1 (the second one
    proposing 2pm EST Friday) and is now lt_interest_status -3."""
    path = os.path.join(ROOT, "services", "reply_engine", "tests", "fixtures",
                        "instantly_replies_2026-09.json")
    replies = L.load_json(path)
    positives = sorted({r["from_address_email"] for r in replies
                        if r.get("i_status") == 1 or r.get("ai_interest_value") == 1})
    assert positives, "fixture has no positives; the test would be vacuous"
    files = " ".join(os.listdir(DRAFTS_DIR)).lower()
    checklist = _read(os.path.join(ROOT, "changesets", "PHASE0_MANUAL_CHECKLIST.md"))
    for addr in positives:
        if addr in DISPOSITIONED:
            assert addr in checklist, (
                "%s is dispositioned as %r but the checklist never says so, so nobody reading it "
                "knows why there is no draft" % (addr, DISPOSITIONED[addr]))
            continue
        local = addr.split("@")[0].lower()
        domain_word = addr.split("@")[1].split(".")[0].lower()
        assert local in files or domain_word in files or local in checklist, (
            "positive %s has no draft in changesets/drafts and no entry in DISPOSITIONED" % addr)


def test_every_open_positive_in_ids_json_has_a_draft():
    """Ilmi held the only call inside 48 hours and had no draft at all."""
    ids = L.load_json(os.path.join(ROOT, "config", "ids.json"))
    people = []
    for opp in ids["ghl"].get("opportunities_observed_2026-09-21", []):
        name = opp["name"]
        people.append(name.split(" - ")[-1].split("(")[0].strip().split()[0])
    for booked in ids["google_calendar"].get("booked_this_week", []):
        people.append(booked["who"].split("/")[0].strip().split()[0])
    files = " ".join(os.listdir(DRAFTS_DIR)).lower()
    missing = sorted({p for p in people if p.lower() not in files})
    assert missing == [], "no draft in changesets/drafts for %s" % missing


# ------------------------------------------------- the subsequence copy gate
def test_subsequence_copy_passes_the_same_validator_as_the_campaign_sequences(snapshot, cfg, offers_md):
    """The Interested-quiet copy used to reach POST /subsequences without a
    single offers.md check: an edit to build_sequences.QUIET_WHY could put a
    "$95,000 in 45 days or your money back" guarantee in front of a warm
    positive on a reactivation offer and every gate in the change-set said OK."""
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    for key, sub in quiet["campaigns"].items():
        known = L.campaign_variables(snapshot[cfg["campaigns"][key]["id"]])
        rep = L.validate_subsequence_copy(key, sub, cfg, offers_md, known_vars=known)
        assert rep.ok, rep.summary()


def test_the_subsequence_gate_catches_a_guarantee_smuggled_into_the_copy(snapshot, cfg, offers_md):
    """The negative half. Without it the test above only proves today's copy."""
    import copy as _copy

    quiet = _copy.deepcopy(L.load_json(L.SUBSEQUENCE_PATH))
    sub = quiet["campaigns"]["cleaning_reactivation"]
    step = sub["sequences"][0]["steps"][1]
    step["variants"][0]["body"] = L.text_to_html(
        "Hey {{firstName}},\n\nI guarantee $95,000 of recovered contracts in 45 days or your money back.\n\nLorenzo")
    known = L.campaign_variables(snapshot[cfg["campaigns"]["cleaning_reactivation"]["id"]])
    rep = L.validate_subsequence_copy("cleaning_reactivation", sub, cfg, offers_md, known_vars=known)
    assert not rep.ok
    joined = " ".join(rep.errors)
    assert "$95,000" in joined and "45 days" in joined and "guarantee" in joined


def test_the_applier_refuses_to_post_subsequence_copy_that_fails_the_gate(monkeypatch, tmp_path):
    """The gate has to run inside build_payloads(), not only in pytest: a live
    --apply must refuse on a copy edit that never went through the suite."""
    import json as _json

    import changesets.instantly_subsequences.apply_subsequences as subs

    good = L.load_json(L.SUBSEQUENCE_PATH)
    bad = _json.loads(_json.dumps(good))
    sub = bad["campaigns"]["cleaning_reactivation"]
    sub["sequences"][0]["steps"][0]["variants"][0]["body"] = L.text_to_html(
        "Hey {{firstName}},\n\nI guarantee $95,000 in 45 days or your money back.\n\nLorenzo")
    path = tmp_path / "quiet.json"
    path.write_text(_json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(subs, "COPY_SOURCE", path)
    with pytest.raises(ValueError) as exc:
        subs.build_payloads()
    assert "offers.md gate" in str(exc.value)


def test_subsequence_conditions_carry_no_trigger_and_no_empty_reply_contains(cfg):
    """`reply_contains: ""` is an empty substring, contained in every reply. It
    is omitted rather than sent, and no file claims the empty condition set is
    verified to enrol nobody."""
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    for key, sub in quiet["campaigns"].items():
        assert sub["conditions"] == {"crm_status": [], "lead_activity": []}, key
        assert "reply_contains" not in sub["conditions"], key
        assert sub["_meta"]["enrolment"] == "manual move only", key
        assert "UNVERIFIED" in sub["_meta"]["conditions_semantics"], key
        assert sub["_meta"]["enrolment_precondition"] == "slots were offered and went unanswered", key
    assert "UNVERIFIED" in quiet["_about"]
    for stale in ("conditions deliberately matches nobody", "conditions match no lead"):
        assert stale not in _json_dump(quiet), stale


def _json_dump(obj):
    return json.dumps(obj)


def test_the_dry_run_enrolment_line_reads_every_condition_field():
    """_print_plan used to decide the line from crm_status alone, so a
    subsequence that auto-enrolled on lead_activity 2 (email opened) still
    printed "manual move only" on the screen Lorenzo approves from."""
    import changesets.instantly_subsequences.apply_subsequences as subs

    auto = subs.enrolment_summary({"crm_status": [], "lead_activity": [2], "reply_contains": "yes"})
    assert auto.startswith("AUTO-ENROLS")
    assert "lead_activity=[2]" in auto and "reply_contains" in auto
    empty_substring = subs.enrolment_summary({"crm_status": [], "lead_activity": [], "reply_contains": ""})
    assert empty_substring.startswith("AUTO-ENROLS") and "EVERY reply" in empty_substring
    none_set = subs.enrolment_summary({"crm_status": [], "lead_activity": []})
    assert "manual move only" in none_set and "UNVERIFIED" in none_set
    assert "conditions match no lead" not in none_set


def test_the_subsequence_applier_refuses_apply_without_a_client(tmp_env, live_mode, monkeypatch):
    """main() used to fall back to client=None and carry on into --apply, where
    the backup recorded "there were none" for a campaign whose real subsequence
    list had never been read, then died on AttributeError."""
    import shared.instantly as _inst

    import changesets.instantly_subsequences.apply_subsequences as subs

    def _no_client(*a, **k):
        raise _inst.InstantlyError("INSTANTLY_API_KEY missing")

    monkeypatch.setattr(_inst, "Instantly", _no_client)
    lines, out = collector()
    rc = subs.main(["--apply", "--campaign", "cleaning_reactivation", "--yes"], client=None, out=out)
    assert rc == subs.EXIT_REFUSED
    assert any("needs a working Instantly client" in l for l in lines), lines
    with pytest.raises(ValueError):
        subs._existing(None, "any-campaign-id")


def test_the_subsequence_backup_lands_where_the_runbook_says():
    import changesets.instantly_subsequences.apply_subsequences as subs

    assert subs.BACKUP_DIR == pathlib.Path(ROOT) / "changesets" / "backups"
    runbook = _read(os.path.join(ROOT, "runbooks", "phase0.md"))
    assert "subsequences_before_<ts>.json" in runbook


# --------------------------------------------------------- copy vs offers.md
TEXT_CHANNEL_RE = re.compile(r"\btext(s|ing)?\b|\bSMS\b", re.I)


def test_no_variant_promises_a_channel_absent_from_its_offers_md_row(cfg, offers_md):
    """recruiting_reactivation promised "email and text sequences" in two
    variants while its offers.md row offers no text leg. validate_sequence
    checks figures and windows, never the mechanism sentence."""
    rows = L.offer_rows_from_offers(offers_md)
    promising = []
    for key in KEYS:
        doc = L.load_sequence(key)
        hit = False
        for _si, _vi, _step, var in L.iter_variants(doc):
            body = L.html_to_text(var.get("body") or "")
            if TEXT_CHANNEL_RE.search(body):
                hit = True
                assert "text" in rows[key].lower(), (
                    "%s promises a text channel but its offers.md row does not: %r" % (key, rows[key]))
        if hit:
            promising.append(key)
    assert promising == ["cleaning_reactivation"], promising
    # A2P is not registered, so every campaign that promises texting has to be
    # named in the checklist, where the pending registration is tracked.
    ids = L.load_json(os.path.join(ROOT, "config", "ids.json"))
    if str(ids["instantly"].get("a2p_10dlc", "")).startswith("not registered"):
        checklist = _read(os.path.join(ROOT, "changesets", "PHASE0_MANUAL_CHECKLIST.md"))
        for key in promising:
            assert key in checklist, "%s promises texting while A2P is pending and the checklist never says so" % key


def test_a_guarantee_remedy_phrase_appears_in_the_campaigns_own_offers_md_row(cfg, offers_md):
    """bookkeeping_trigger and recruiting_outbound promised a "$200 gift card to
    your favorite steakhouse"; offers.md gives the steakhouse wording only to
    cleaning_trigger. The validator only ever checked the dollar amount."""
    rows = L.offer_rows_from_offers(offers_md)
    for key in KEYS:
        doc = L.load_sequence(key)
        for _si, _vi, _step, var in L.iter_variants(doc):
            body = L.html_to_text(var.get("body") or "")
            if "steakhouse" in body.lower():
                assert "steakhouse" in rows[key].lower(), (
                    "%s promises a steakhouse gift card, which is not in its offers.md row" % key)


def test_every_opener_passes_the_copy_rules_for_its_segment(cfg, offers_md):
    """No test touched the opener pools, and the threshold table tells Lorenzo
    to swap a losing variant for "the next opener from openers_<niche>.md".
    recruiting_outbound opener 9 introduced a "45 days" window that is in
    neither the offers.md row nor the proof line, so the swap would fail
    validation at apply time, after the 500-send verdict had been taken."""
    import glob

    files = sorted(glob.glob(os.path.join(ROOT, "changesets", "instantly_phase0", "openers_*.md")))
    assert len(files) == 3, files
    checked = 0
    for path in files:
        segment = None
        for line in _read(path).splitlines():
            m = re.match(r"^##\s+Segment:\s+([a-z_]+)", line)
            if m:
                segment = m.group(1)
                assert segment in KEYS, (path, segment)
                continue
            m = re.match(r"^\s*\d+\.\s+(.*\S)\s*$", line)
            if not m or segment is None:
                continue
            opener = m.group(1)
            checked += 1
            where = "%s/%s: %r" % (os.path.basename(path), segment, opener[:50])
            assert L.EM_DASH not in opener and L.EN_DASH not in opener, where
            assert "!" not in opener, where
            assert not L.AI_RE.search(opener), where
            offer = cfg["campaigns"][segment]["offer"]
            allowed_money, allowed_periods = L.allowed_offer_numbers(segment, offer, offers_md)
            assert L.money_values(opener) <= allowed_money, where
            assert L.period_phrases(opener) <= allowed_periods, where
    assert checked == 72, checked  # 3 files x 2 segments x 12 openers


# ------------------------------------------------------- ids cross-check (9)
def test_campaign_settings_ids_equal_ids_json(cfg):
    ids = L.load_json(os.path.join(ROOT, "config", "ids.json"))["instantly"]["campaigns"]
    for key in KEYS:
        assert cfg["campaigns"][key]["id"] == ids[key]["id"], key


def test_apply_refuses_when_campaign_settings_disagrees_with_ids_json(tmp_env, shadow_mode, tmp_path, snapshot):
    """campaign_settings.json is a second copy of ids that is what the script
    actually PATCHes. With cleaning_reactivation's id swapped for
    bookkeeping_reactivation's, process_campaign fetched the bookkeeping
    campaign, reported OK and would have PATCHed it with cleaning copy."""
    import copy as _copy

    cfg_all = _copy.deepcopy(L.load_settings())
    cfg_all["campaigns"]["cleaning_reactivation"]["id"] = cfg_all["campaigns"]["bookkeeping_reactivation"]["id"]
    with pytest.raises(app.IdMismatch) as exc:
        app.assert_ids_match_ids_json(cfg_all, ["cleaning_reactivation"])
    assert "config/ids.json" in str(exc.value) and "cleaning_reactivation" in str(exc.value)

    client, rec = make_client(snapshot)
    lines, out = collector()
    rc = app.main(["--campaign", "cleaning_reactivation", "--no-diff"], client=client,
                  now=NOW, out=out, backup_dir=str(tmp_path))
    assert rc == app.EXIT_OK  # the real files agree
    # and with a mismatched file the run is refused before a single GET
    calls_before = len(rec.requests)
    with pytest.raises(app.IdMismatch):
        app.assert_ids_match_ids_json(cfg_all)
    assert len(rec.requests) == calls_before


# --------------------------------------------- backup naming on a refusal (10)
def test_a_refused_apply_leaves_no_file_at_all(tmp_env, live_mode, tmp_path, snapshot):
    """The suffix used to come from args.apply, so a run refused AFTER the
    backup (new merge variables, the live_allowed re-check, an API error) wrote
    an unsuffixed file holding the POST-change copy. Every refusal now happens
    before the before-image is written."""
    client, rec = make_client(snapshot)
    lines, out = collector()
    rc = app.main(["--apply", "--campaign", "cleaning_trigger", "--yes", "--no-diff"],
                  client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"))
    assert rc != app.EXIT_OK
    assert any("REFUSED" in l or "refused" in l for l in lines), lines[-4:]
    assert rec.methods == ["GET"]
    assert not (tmp_path / "b").exists()


def test_a_successful_apply_promotes_the_backup_to_the_rollback_name(tmp_env, live_mode, tmp_path, snapshot):
    client, rec = make_client(snapshot)
    lines, out = collector()
    rc = app.main(["--apply", "--campaign", "cleaning_reactivation", "--yes", "--no-diff"],
                  client=client, now=NOW, out=out, backup_dir=str(tmp_path))
    assert rc == app.EXIT_OK
    assert "PATCH" in rec.methods
    written = sorted(n for n in os.listdir(str(tmp_path)) if n.endswith(".json"))
    cid = L.load_settings()["campaigns"]["cleaning_reactivation"]["id"]
    assert written == ["phase0_%s_%s.json" % (cid, NOW.strftime("%Y%m%dT%H%M%SZ"))], written


def test_a_reapply_sends_nothing_and_keeps_the_rollback_point(tmp_env, live_mode, tmp_path, snapshot):
    """GOL-9: re-running --apply on an applied campaign used to write a second
    unsuffixed file holding the NEW copy."""
    client, rec, point = _applied(tmp_path, snapshot)
    original = point.read_text()
    n = len(rec.requests)
    lines, out = collector()
    later = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)
    assert app.main(["--apply", "--campaign", "cleaning_reactivation", "--yes", "--no-diff"],
                    client=client, now=later, out=out, backup_dir=str(tmp_path / "b")) == 0
    assert rec.methods[n:] == ["GET"]
    assert os.listdir(str(tmp_path / "b")) == [point.name]
    assert point.read_text() == original
    assert any("already matches" in l for l in lines)


def _failing_patch_client(snapshot, landed, reread_fails=False):
    """PATCH answers 504; `landed` says whether the change stuck anyway."""
    rec = Recorder(snapshot)
    state = {"reads": 0}

    def handler(request):
        rec.requests.append(request)
        path = request.url.path
        cid = path.rsplit("/", 1)[1]
        if request.method == "PATCH":
            if landed:
                rec.snapshot[cid].update(json.loads(request.content))
            return httpx.Response(504, text="gateway timeout")
        state["reads"] += 1
        if reread_fails and state["reads"] > 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=rec.snapshot[cid])

    client = Instantly(api_key="test-key", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    return client, rec


@pytest.mark.parametrize("landed,reread_fails,expect_name,outcome", [
    (True, False, ".json", "landed_after_error"),
    (False, False, ".json", "unchanged_at_reread"),
    (True, True, ".json", "unknown_after_error"),
])
def test_a_timed_out_patch_is_settled_by_a_re_read(tmp_env, live_mode, tmp_path, snapshot,
                                                    landed, reread_fails, expect_name, outcome):
    """GOL-9: after a 5xx on a PATCH that actually landed, the true
    before-image stayed `.preapply` and the runbook called that "wrote
    nothing". Re-review defect 2: whatever the re-read shows, an error leaves
    the before-image as the restorable, unsuffixed point, because a 504 can
    land after the re-read. The outcome records what the re-read saw."""
    client, rec = _failing_patch_client(snapshot, landed, reread_fails)
    lines, out = collector()
    rc = app.main(["--apply", "--campaign", "cleaning_reactivation", "--yes", "--no-diff"],
                  client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"))
    assert rc == app.EXIT_API
    assert [r.method for r in rec.requests][:2] == ["GET", "PATCH"]
    assert [r.method for r in rec.requests].count("PATCH") == 1       # a write is never retried
    files = os.listdir(str(tmp_path / "b"))
    assert len(files) == 1 and not files[0].endswith(".preapply.json")
    stem = "phase0_8086b41e-b546-4b36-9fa0-2d01f5cc119a_20260922T021000Z"
    assert files[0] == stem + expect_name
    with open(str(tmp_path / "b" / files[0])) as fh:
        assert json.load(fh)["_rollback_point"]["outcome"] == outcome


# ------------------------------------------------ what the runbook may claim
def test_a_step1_with_a_single_variant_is_refused(snapshot, cfg, offers_md):
    """Go-live step 5 used to offer "apply with variant B removed" as a way past
    the new merge variables on cleaning_trigger. The validator forbids it."""
    import copy as _copy

    doc = _copy.deepcopy(L.load_sequence("cleaning_trigger"))
    doc["sequences"][0]["steps"][0]["variants"].pop(1)
    rep = _report("cleaning_trigger", doc, snapshot, cfg, offers_md)
    assert not rep.ok
    assert any("needs exactly variants A and B" in e for e in rep.errors), rep.errors
    runbook = _read(os.path.join(ROOT, "runbooks", "phase0.md"))
    assert "variant B removed" not in runbook
    assert "needs exactly variants A and B" in runbook


def test_the_runbook_warns_about_the_completed_lead_backlog():
    """Adding a third step to six running campaigns makes ~100 completed leads
    per campaign due for step 3 at once, which also makes go-live step 11's
    "step 3 on day 7" check unreadable unless it is split."""
    runbook = _read(os.path.join(ROOT, "runbooks", "phase0.md"))
    assert "completed_count" in runbook
    assert "backlog" in runbook.lower()
    assert "after the apply" in runbook
    analytics = L.load_json(os.path.join(ROOT, "config", "snapshots",
                                         "instantly_campaign_analytics_2026-09-21.json"))
    items = analytics if isinstance(analytics, list) else analytics.get("items", [])
    completed = [int(i.get("completed_count") or 0) for i in items]
    assert len(completed) == 6 and min(completed) >= 100, completed


def test_the_runbook_does_not_state_an_absolute_test_count():
    """78 drifted to 88 while the suite grew. A count that is ten short on the
    one screen that gates a live PATCH invites the reader to assume collection
    failed."""
    runbook = _read(os.path.join(ROOT, "runbooks", "phase0.md"))
    assert not re.search(r"\b\d+ tests in `changesets/tests`", runbook)


def test_the_interested_quiet_move_candidates_were_actually_offered_slots():
    """The D1 email opens by saying the times offered have filled up. Go-live
    step 10 used to name Tiffany and Ignacio; Ignacio was never offered a time
    and asked to be contacted next month, so the opening line would be false."""
    runbook = _read(os.path.join(ROOT, "runbooks", "phase0.md"))
    quiet = L.load_json(L.SUBSEQUENCE_PATH)
    precondition = quiet["campaigns"]["cleaning_reactivation"]["_meta"]["enrolment_precondition"]
    assert precondition in runbook, "the runbook must repeat the precondition verbatim"
    step10 = runbook.split("10. [ ]")[1].split("11. [ ]")[0]
    assert "Tiffany" in step10
    assert re.search(r"[Dd]o \*\*not\*\* move Ignacio|not\*\* move Ignacio", step10), step10[-600:]
    for name in DISPOSITIONED:
        first = name.split("@")[0].capitalize()
        if first == "Ignacio":
            assert "Ignacio" in step10


def test_no_draft_claims_a_thread_was_unanswered_when_an_outbound_is_newer(offers_md):
    """The Ilmi draft and the checklist both said "around 11:30" was never
    confirmed back to her, while the recorded sent fixture holds an outbound in
    that exact thread three minutes after her reschedule request."""
    sent = L.load_json(os.path.join(ROOT, "services", "reply_engine", "tests", "fixtures",
                                    "instantly_manual_sent_2026-09.json"))
    lead_of = {"ilmi_wednesday_confirmation.md": "info@shiningarmorcleaningnj.com",
               "sopio_confirmation.md": "sopiosvanishvili@taxfoaccounting.com",
               "tiffany_upfront_cost.md": "tiffany@flowerhillfs.com"}
    claims = ("never confirmed", "no reply", "has been quiet since", "never answered", "nobody replied")
    for fname, lead in lead_of.items():
        text = _read(os.path.join(DRAFTS_DIR, fname))
        inbounds = [r["timestamp_created"] for r in sent
                    if r["eaccount"] == r["to_address_email_list"] and lead.split("@")[1] in (r.get("text") or "")]
        outbounds = [r["timestamp_created"] for r in sent if r["to_address_email_list"] == lead]
        assert outbounds, fname
        newest_out = max(outbounds)
        if inbounds and newest_out > max(inbounds):
            for claim in claims:
                assert claim not in text.lower(), (
                    "%s says %r although an outbound at %s is newer than the last inbound"
                    % (fname, claim, newest_out))


def test_every_draft_names_its_inbox_and_the_lead_address_from_the_recorded_thread():
    """The Ilmi draft said only "from the inbox the cold email came from". If
    Lorenzo composes rather than replies it goes from the wrong domain and reads
    as a fresh cold email."""
    expected = {
        "ilmi_wednesday_confirmation.md": ("lorenzo@adveromedia.com", "info@shiningarmorcleaningnj.com"),
        "sopio_confirmation.md": ("lorenzov@theadvero.com", "sopiosvanishvili@taxfoaccounting.com"),
        "tiffany_upfront_cost.md": ("lorenzovillarreal@adveromedia.com", "tiffany@flowerhillfs.com"),
    }
    sent = L.load_json(os.path.join(ROOT, "services", "reply_engine", "tests", "fixtures",
                                    "instantly_manual_sent_2026-09.json"))
    for fname, (eaccount, lead) in expected.items():
        header = _read(os.path.join(DRAFTS_DIR, fname)).split("Subject:")[0]
        assert eaccount in header, "%s never names the sending inbox" % fname
        assert lead in header, "%s never names the recipient" % fname
        assert any(r["eaccount"] == eaccount and r["to_address_email_list"] == lead for r in sent), (
            "%s: %s -> %s is not a pair the recorded thread contains" % (fname, eaccount, lead))


# ------------------------------------------- labels: R9, read-back, backup
class LabelServer(object):
    """GET /lead-labels and POST /lead-labels with server-assigned values."""

    def __init__(self, existing=None, value_key="interest_status", fail_on=None):
        self.rows = list(existing or [])
        self.requests = []
        self.value_key = value_key
        self.fail_on = fail_on
        self.next_value = 1001

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/lead-labels":
            return httpx.Response(200, json={"items": self.rows, "next_starting_after": None})
        if request.method == "POST" and request.url.path == "/api/v2/lead-labels":
            body = json.loads(request.content)
            if body["label"] == self.fail_on:
                return httpx.Response(500, text="boom")
            row = dict(body, id="lab-%d" % self.next_value)
            row[self.value_key] = self.next_value
            self.next_value += 1
            self.rows.append(row)
            return httpx.Response(200, json=row)
        return httpx.Response(404, text="unexpected %s %s" % (request.method, request.url.path))


def _label_client(server):
    return Instantly(api_key="test-key", transport=httpx.MockTransport(server), sleep=lambda s: None)


def test_every_staged_label_is_created_with_ai_off():
    """R9 (owner decision): use_with_ai false until every detector reads the
    custom values; the validator refuses a label that says otherwise."""
    labels = L.load_json(L.LABELS_PATH)["labels"]
    assert all(lab["use_with_ai"] is False for lab in labels)
    flipped = [dict(labels[0], use_with_ai=True)] + labels[1:]
    assert any("use_with_ai must be false" in e for e in L.validate_labels(flipped, app.EXPECTED_LABELS))


def test_labels_apply_backs_up_creates_with_ai_off_reads_back_and_logs(tmp_env, live_mode, tmp_path):
    server = LabelServer(existing=[{"id": "lab-1", "label": "ooo", "interest_status_label": "neutral",
                                   "use_with_ai": False, "interest_status": 999}])
    client = _label_client(server)
    values = tmp_path / "values.json"
    lines, out = collector()
    code = app.main(["--labels", "--apply", "--yes"], client=client, now=NOW, out=out,
                    backup_dir=str(tmp_path / "b"), label_values_path=str(values))
    assert code == 0, lines
    posts = [r for r in server.requests if r.method == "POST"]
    assert len(posts) == 10                                   # ooo already existed
    for r in posts:
        assert r.url.path == "/api/v2/lead-labels"
        body = json.loads(r.content)
        assert sorted(body) == ["description", "interest_status_label", "label", "use_with_ai"]
        assert body["use_with_ai"] is False
    # the backup came first, and is evidence, not a restorable campaign point
    assert server.requests[0].method == "GET"
    backups = os.listdir(str(tmp_path / "b"))
    assert backups == ["phase0_lead_labels_20260922T021000Z.evidence.json"]
    # every label's value was read back into the change-set output file
    rec = json.loads(values.read_text())
    assert rec["complete"] is True and rec["problems"] == []
    assert len(rec["labels"]) == 11
    assert rec["labels"]["ooo"]["value"] == 999
    assert rec["labels"]["positive_interested"]["value"] >= 1001
    assert all(v["use_with_ai"] is False for v in rec["labels"].values())
    with open(job_log.job_log_path()) as fh:
        assert "phase0.labels_apply,applied" in fh.read()
    # re-run: nothing created, mapping rewritten from the read-back
    n = len(server.requests)
    assert app.main(["--labels", "--apply", "--yes"], client=client, now=NOW, out=lambda s: None,
                    backup_dir=str(tmp_path / "b2"), label_values_path=str(values)) == 0
    assert [r.method for r in server.requests[n:]] == ["GET", "GET"]


def test_labels_apply_reports_a_value_it_cannot_find_instead_of_guessing(tmp_env, live_mode, tmp_path):
    server = LabelServer(value_key="some_future_field")
    values = tmp_path / "values.json"
    code = app.main(["--labels", "--apply", "--yes"], client=_label_client(server), now=NOW,
                    out=lambda s: None, backup_dir=str(tmp_path / "b"), label_values_path=str(values))
    assert code == app.EXIT_API
    rec = json.loads(values.read_text())
    assert rec["complete"] is False
    assert rec["labels"]["ooo"]["value"] is None
    with open(job_log.job_log_path()) as fh:
        assert "phase0.labels_apply,errors" in fh.read()


def test_labels_apply_stops_at_the_first_failed_create(tmp_env, live_mode, tmp_path):
    server = LabelServer(fail_on="positive_question")
    values = tmp_path / "values.json"
    code = app.main(["--labels", "--apply", "--yes"], client=_label_client(server), now=NOW,
                    out=lambda s: None, backup_dir=str(tmp_path / "b"), label_values_path=str(values))
    assert code == app.EXIT_API
    posts = [json.loads(r.content)["label"] for r in server.requests if r.method == "POST"]
    assert posts == ["positive_interested", "positive_question"]
    assert not json.loads(values.read_text())["complete"]


def test_labels_dry_run_writes_nothing_and_logs_to_scratch(tmp_env, shadow_mode, tmp_path):
    server = LabelServer()
    values = tmp_path / "values.json"
    assert app.main(["--labels"], client=_label_client(server), now=NOW, out=lambda s: None,
                    backup_dir=str(tmp_path / "b"), label_values_path=str(values)) == 0
    assert [r.method for r in server.requests] == ["GET"]
    assert not values.exists() and not (tmp_path / "b").exists()
    assert not job_log.job_log_path().exists()
