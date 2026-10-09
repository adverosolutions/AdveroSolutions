import copy as copymod
import json
import re
from pathlib import Path

import pytest

import apply_ai_agents_campaigns as m

HERE = Path(__file__).resolve().parent
TEMPLATE = json.loads((HERE / "fixture_template.json").read_text())
PRE = [{"id": "t", "name": "2026 Service - AI Agents", "status": 1},
       {"id": "p", "name": "2026 Cleaning - Reactivation", "status": 2}]


def test_all_18_bodies_round_trip():
    copy = m.load_copy()
    assert sorted(copy) == sorted(ck for _, _, ck in m.CAMPAIGNS)
    n = 0
    for ck in copy:
        for v in ("A", "B", "step2"):
            plain = copy[ck][v]
            html = m.to_html(plain)
            assert m.structure_check(plain, html)
            assert "<div>{Thanks|Thank you|Speak soon},</div><div>Lorenzo</div>" in html or \
                "},</div><div>Lorenzo</div>" in html
            assert "&amp;" not in html and "&#" not in html
            n += 1
    assert n == 18


def test_html_rule():
    assert m.to_html("a\n\nb's {{x}}") == "<div>a</div><div><br /></div><div>b's {{x}}</div>"
    with pytest.raises(AssertionError):
        m.structure_check("a\nb", "<div>a</div><div><br /></div><div>b</div>")


def test_payload_shape_and_settings():
    built = m.build_all(TEMPLATE)
    assert [b["name"] for b in built] == [n for n, _, _ in m.CAMPAIGNS]
    for b in built:
        p = b["payload"]
        steps = p["sequences"][0]["steps"]
        assert len(p["sequences"]) == 1 and len(steps) == 2
        assert len(steps[0]["variants"]) == 2
        assert all(v["subject"] == "{{firstName}}, question" for v in steps[0]["variants"])
        assert len(steps[1]["variants"]) == 1 and steps[1]["variants"][0]["subject"] == ""
        for s in steps:
            assert (s["type"], s["delay"], s["delay_unit"]) == ("email", 3, "days")
        for k in m.COPIED_SETTINGS:
            assert p[k] == TEMPLATE[k]
        assert p["campaign_schedule"]["schedules"] == TEMPLATE["campaign_schedule"]["schedules"]
        assert p["insert_unsubscribe_header"] is True and p["allow_risky_contacts"] is False
        assert len(p["email_list"]) == 12 and p["daily_limit"] == 50
        assert "status" not in p
        assert all(b["structure"].values())


# ---------------------------------------------------------------- mocked Instantly
class FakeInstantly:
    """Records every call. POST stores the payload; GET campaigns/<id> reads it back as a draft."""

    def __init__(self, live=None, after=None, post_fail_at=None, mutate=None,
                 get_fail=(), relist_fail=False):
        self.live = live if live is not None else copymod.deepcopy(PRE)
        self.after = after
        self.post_fail_at = post_fail_at  # 1-based POST number that raises
        self.mutate = mutate or {}  # id -> fn(readback)
        self.get_fail = set(get_fail)
        self.relist_fail = relist_fail
        self.calls = []
        self.store = {}
        self.list_calls = 0

    def __call__(self, method, path, body=None, tok=None):
        self.calls.append((method, path))
        if method == "GET" and path.startswith("campaigns?"):
            self.list_calls += 1
            if self.list_calls > 1:
                if self.relist_fail:
                    raise TimeoutError("timed out")
                return {"items": self.after if self.after is not None else self.live}
            return {"items": self.live}
        if method == "GET" and path == "campaigns/" + m.TEMPLATE_ID:
            return TEMPLATE
        if method == "POST" and path == "campaigns":
            n = len([c for c in self.calls if c[0] == "POST"])
            if n == self.post_fail_at:
                raise TimeoutError("timed out")
            cid = "c{}".format(n)
            self.store[cid] = copymod.deepcopy(body)
            return {"id": cid, "name": body["name"], "status": 0}
        if method == "GET" and path.startswith("campaigns/"):
            cid = path.split("/", 1)[1]
            if cid in self.get_fail:
                raise SystemExit("GET {} -> HTTP 500: boom".format(path))
            got = copymod.deepcopy(self.store[cid])
            got["status"] = 0
            if cid in self.mutate:
                self.mutate[cid](got)
            return got
        raise AssertionError("unexpected call " + method + " " + path)

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "IDS_FILE", tmp_path / "ids.json")
    monkeypatch.setattr(m, "TMP_DIR", tmp_path / "tmpdir")
    monkeypatch.setattr(m, "APPLIED_FILE", tmp_path / "APPLIED.md")
    monkeypatch.setattr(m.instantly_push, "key", lambda: "tok")
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)

    def use(fake):
        monkeypatch.setattr(m, "call", fake)
        return fake
    return use


def _ids(tmp_path):
    return json.loads((tmp_path / "ids.json").read_text())


def test_refuses_when_name_exists(sandbox, tmp_path):
    fake = sandbox(FakeInstantly(live=[{"id": "x", "name": "2026 MSP - AI Agents", "status": 0}]))
    assert m.dry_run("tok") == 2
    assert m.apply("tok") == 2
    assert fake.writes() == []
    assert not (tmp_path / "ids.json").exists()


def test_dry_run_ok_and_read_only(sandbox, tmp_path):
    fake = sandbox(FakeInstantly())
    assert m.main(["--dry-run"]) == 0
    assert m.main([]) == 0
    assert fake.writes() == []
    assert len(json.loads((tmp_path / "tmpdir" / "dryrun_payloads.json").read_text())) == 6


@pytest.mark.parametrize("env", [{}, {"MODE": "live"}, {"ALLOW_LIVE_WRITES": "1"},
                                 {"MODE": "shadow", "ALLOW_LIVE_WRITES": "1"},
                                 {"MODE": "live", "ALLOW_LIVE_WRITES": "true"}])
def test_apply_refused_without_live_gate(sandbox, monkeypatch, tmp_path, capsys, env):
    fake = sandbox(FakeInstantly())
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert m.main(["--apply", "--yes"]) == 2
    assert fake.calls == []  # refused before any request, not only before the POST
    assert "MODE=live" in capsys.readouterr().out
    assert not (tmp_path / "ids.json").exists()


def test_apply_refused_without_yes_or_with_dry_run(sandbox, monkeypatch):
    fake = sandbox(FakeInstantly())
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert m.main(["--apply"]) == 2
    assert m.main(["--apply", "--yes", "--dry-run"]) == 2
    assert fake.calls == []


def test_apply_clean_run(sandbox, monkeypatch, tmp_path):
    fake = sandbox(FakeInstantly())
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert m.main(["--apply", "--yes"]) == 0
    assert fake.writes() == [("POST", "campaigns")] * 6
    assert _ids(tmp_path) == {key: "c{}".format(i) for i, (_, key, _) in enumerate(m.CAMPAIGNS, 1)}
    applied = (tmp_path / "APPLIED.md").read_text()
    assert applied.count("| PASS |") == 6 and "unchanged: yes" in applied
    assert list((tmp_path / "tmpdir").glob("before_*.json"))


def test_post_fails_on_third(sandbox, tmp_path, capsys):
    fake = sandbox(FakeInstantly(post_fail_at=3))
    assert m.apply("tok") == 3
    assert len(fake.writes()) == 3
    assert _ids(tmp_path) == {"bookkeeping_ai": "c1", "insurance_broker_ai": "c2"}
    out = capsys.readouterr().out
    assert "TimeoutError" in out and "may exist without a recorded id; check by name in Instantly" in out


def test_readback_body_rewritten(sandbox, tmp_path):
    def rewrite(got):
        v = got["sequences"][0]["steps"][0]["variants"][1]
        v["body"] = v["body"].replace("'", "&#39;", 1)
    sandbox(FakeInstantly(mutate={"c2": rewrite}))
    assert m.apply("tok") == 3
    applied = (tmp_path / "APPLIED.md").read_text()
    assert "step 1 variant 2 body differs at char" in applied
    assert applied.count("| PASS |") == 5


def test_readback_body_missing_no_crash(sandbox, tmp_path):
    def drop(got):
        got["sequences"][0]["steps"][0]["variants"][0]["body"] = None
        del got["sequences"][0]["steps"][1]["variants"][0]["body"]
    sandbox(FakeInstantly(mutate={"c4": drop}))
    assert m.apply("tok") == 3
    applied = (tmp_path / "APPLIED.md").read_text()
    assert "step 1 variant 1 body missing" in applied and "step 2 variant 1 body missing" in applied


def test_preexisting_status_changed(sandbox, tmp_path, capsys):
    after = copymod.deepcopy(PRE)
    after[1]["status"] = 1
    sandbox(FakeInstantly(after=after))
    assert m.apply("tok") == 3
    assert "PRE-EXISTING STATUS CHANGED: 2026 Cleaning - Reactivation 2 -> 1" in capsys.readouterr().out
    assert "unchanged: NO" in (tmp_path / "APPLIED.md").read_text()


def test_verify_get_and_relist_failures_recorded(sandbox, tmp_path):
    sandbox(FakeInstantly(get_fail={"c2"}, relist_fail=True))
    assert m.apply("tok") == 3
    applied = (tmp_path / "APPLIED.md").read_text()
    assert "read-back GET failed" in applied and applied.count("| PASS |") == 5
    assert "UNVERIFIED: re-list GET failed (TimeoutError" in applied


def test_verify_compares_step_and_settings_fields():
    payload = m.build_all(TEMPLATE)[0]["payload"]
    got = copymod.deepcopy(payload)
    got["status"] = 0
    assert m.verify_campaign(got, payload) == []
    got["sequences"][0]["steps"][1]["delay"] = 2
    got["sequences"][0]["steps"][0]["delay_unit"] = "hours"
    got["email_gap"] = 10
    got["open_tracking"] = True
    got["pl_value"] = None
    got["campaign_schedule"]["schedules"][0]["timing"]["to"] = "17:00"
    probs = "\n".join(m.verify_campaign(got, payload))
    for s in ("step 2 delay 2 != sent 3", "step 1 delay_unit 'hours' != sent 'days'",
              "email_gap 10 != sent 7", "open_tracking True != sent False", "pl_value None != sent 1000"):
        assert s in probs
    assert '"to": "17:00"' in probs and '"to": "19:00"' in probs


def test_source_never_touches_campaign_state_endpoints():
    src = (HERE / "apply_ai_agents_campaigns.py").read_text().splitlines()
    bad = []
    for i, line in enumerate(src, 1):
        code = line.split("#", 1)[0]
        if re.search(r"activate|/pause|resume", code, re.I):
            bad.append((i, line))
    assert bad == []
