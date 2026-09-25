"""End to end on the recorded fixture: resume, staging, copy rules, the paid
gate, and the promise that nothing reaches a live system."""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from shared import settings
from shared.job_log import read_shadow_log

import jobs.list_factory as job
from services.list_factory import contacts, ledger as ledger_mod, models, personalize
from services.list_factory import pipeline as pipeline_mod
from services.list_factory import sources as sources_mod
from services.list_factory import stage_out, state as state_mod
from services.list_factory import suppression as supp_mod

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "services", "list_factory", "fixtures", "source_cleaning_50.json",
)


# --------------------------------------------------------------- test doubles
class FakeVerifier(contacts.Verifier):
    """Verifies the FIRST pattern for most domains and nothing at all for a
    named few, which is how a real MillionVerifier run behaves."""

    name = "fake-mv"

    def __init__(self, never=(), role_addresses=()):
        contacts.Verifier.__init__(self)
        self.never = set(never)
        self.role_addresses = set(role_addresses)
        self.calls = []

    def verify(self, emails):
        out = []
        for email in emails:
            self.calls.append(email)
            domain = email.split("@")[-1]
            if domain in self.never:
                out.append({"email": email, "status": "invalid", "is_role": False})
            elif email in self.role_addresses:
                out.append({"email": email, "status": "valid", "is_role": True})
            elif email.split("@")[0].count(".") == 0 and "." not in email.split("@")[0]:
                out.append({"email": email, "status": "valid", "is_role": False, "is_catch_all": False})
            else:
                out.append({"email": email, "status": "invalid", "is_role": False})
        return out


def fake_personalizer(lead):
    return "Hey %s, saw %s handles commercial cleaning around %s, wanted to run something by you." % (
        lead.get("first_name") or "there", lead.get("company_name"), lead.get("city") or "your area",
    )


def suppression_for(domains=(), emails=(), built_utc=None):
    supp = supp_mod.SuppressionList()
    for domain in domains:
        supp.add_domain(domain, "already contacted")
    for email in emails:
        supp.add_email(email, "bounced in Instantly")
    for domain in ("gmail.com", "yahoo.com"):
        supp.add_domain(domain, "free mailbox provider")
    supp.complete = True
    # A list with no built_utc is refused like a stale one, so a test double
    # has to say when it was built, exactly like the real builder does.
    supp.built_utc = built_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return supp


def make_config(tmp_path, **kw):
    defaults = dict(
        niche="cleaning",
        campaign_key="cleaning_trigger",
        target=200,
        source=sources_mod.FixtureSource(FIXTURE),
        verifier=FakeVerifier(),
        personalizer=fake_personalizer,
        suppression_list=suppression_for(),
        max_escalations=0,
    )
    defaults.update(kw)
    return pipeline_mod.Config(**defaults)


def make_run(tmp_path, cfg, run_id="t1"):
    return state_mod.RunState.create(run_id, cfg.to_meta())


# ------------------------------------------------------------------- the run
def test_full_run_on_the_fixture_produces_staged_leads(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = make_run(tmp_path, cfg)
    summary = pipeline_mod.run_pipeline(run, cfg)

    assert summary["status"] == "ok", summary.get("error")
    staged = summary["stages"]["stage"]["staged"]
    assert staged > 10, summary["counts"]
    assert os.path.exists(staged_csv(summary))
    ledger = summary["ledger"]
    # verify counts CONFIRMED mailboxes; catch-alls are counted apart and are
    # staged too, so the deliverable total is what covers the CSV.
    assert ledger["counts"]["verify"] + ledger["counts"]["catch_all"] >= staged
    assert ledger["verdict"] in ("green", "no_verified_contacts")


def staged_csv(summary):
    return summary["stages"]["stage"]["csv"]


# Every business the recorded fixture is allowed to stage, reviewed by hand on
# 2026-09-22. An ALLOW-list, not a deny-list: the old version grepped the
# staged names for four words ("snow", "maid", "servicemaster", "supply") and
# passed happily while "Cleanse Your Bins", "Gillette Window And Solar
# Cleaning" and "Elite Relocation Services" went out as commercial cleaners.
STAGEABLE = {
    "green monster clean", "established janitorial", "bewley's cleaning",
    "allstar commercial cleaning", "b2b cleaning services", "elite services",
    "ramfire building management", "we klean inc.", "mdo cleaning services, inc",
    "pristine services", "base hill", "townsend maintenance co., llc",
    "saylorclean", "summit commercial cleaning services, inc",
    "velocity building solutions", "royal cleaning service, inc. - cleaning company",
    "gem mint cleaning", "branshe", "alameda enterprises", "smart cleaning us",
    "core commercial services, inc.", "bright path building services",
    "harborline facility group",
    # Only reachable with the near-empty test suppression list; the real one
    # suppresses these domains because they are already in a campaign.
    "blue magic cleaning service", "clean valley", "professional maintenance service inc.",
    "significant cleaning services", "the business cleaning company inc.",
    "the cavalry cleaning company",
    # Specialty carpet, rug and upholstery cleaning for commercial accounts.
    # Adjacent rather than core janitorial ("floor care" is an accept signal),
    # and reviewed as acceptable on 2026-09-22.
    "sanitech carpet maintenance",
}


def test_only_real_commercial_cleaners_reach_the_csv(tmp_path, monkeypatch):
    """The brief's headline failure: the snow-removal company mailed as a
    cleaner. Asserted as an allow-list over EVERY staged name, because a
    deny-list only ever catches the miss you already know about."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = make_run(tmp_path, cfg)
    summary = pipeline_mod.run_pipeline(run, cfg)
    with open(staged_csv(summary), "r", encoding="utf-8") as fh:
        names = [row["company_name"].lower() for row in csv.DictReader(fh)]
    assert names
    unexpected = sorted(set(names) - STAGEABLE)
    assert not unexpected, "not commercial cleaners: %s" % unexpected
    # ... and the good handwritten one does get through.
    assert any("bright path" in name for name in names)
    # The named misses, explicitly.
    for miss in ("snow", "maid", "servicemaster", "supply", "cleanse your bins",
                 "gillette", "relocation", "b4schools", "envirokleen", "pressure washing"):
        assert not any(miss in name for name in names), miss


def test_every_staged_row_has_an_email_and_a_line(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    summary = pipeline_mod.run_pipeline(make_run(tmp_path, cfg), cfg)
    with open(staged_csv(summary), "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    for row in rows:
        assert "@" in row["email"]
        assert row["personalization"].startswith("Hey ")
        assert "—" not in row["personalization"]
        assert "!" not in row["personalization"]


def test_nothing_is_uploaded_and_the_intent_is_recorded_as_shadow(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.delenv("SHADOW_LOG_PATH", raising=False)
    cfg = make_config(tmp_path)
    summary = pipeline_mod.run_pipeline(make_run(tmp_path, cfg), cfg)

    assert summary["stages"]["stage"]["shadow"] is True
    records = [r for r in read_shadow_log() if r.get("system") == "instantly"]
    assert records, "the POST /leads intent must be in the shadow log"
    payload = records[-1]["payload"]
    assert payload["endpoint"] == "POST /leads"
    assert payload["skip_if_in_workspace"] is True
    assert payload["verify_leads_on_import"] is True
    assert payload["campaign"] == settings.CAMPAIGNS["cleaning_trigger"]["id"]
    assert payload["sample"], "the record must carry a reviewable per-lead body"
    assert payload["sample"][0]["skip_if_in_workspace"] is True


def test_per_lead_would_do_mode_records_one_per_lead(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.delenv("SHADOW_LOG_PATH", raising=False)
    cfg = make_config(tmp_path, would_do_mode="per-lead")
    summary = pipeline_mod.run_pipeline(make_run(tmp_path, cfg), cfg)
    records = [r for r in read_shadow_log() if r.get("action") == "create_lead"]
    assert len(records) == summary["stages"]["stage"]["staged"]


# ---------------------------------------------------------------- resumption
def test_a_resumed_run_does_not_re_verify_what_it_already_verified(tmp_path, monkeypatch):
    """The money question. A crash after verification must not buy the same
    checks a second time."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    verifier = FakeVerifier()
    cfg = make_config(tmp_path, verifier=verifier)
    run = state_mod.RunState.create("resume-me", cfg.to_meta())

    led = ledger_mod.Ledger(run.run_id, "cleaning")
    pipeline_mod.stage_source(run, cfg, led)
    pipeline_mod.stage_icp(run, cfg, led)
    pipeline_mod.stage_owner(run, cfg, led)
    pipeline_mod.stage_patterns(run, cfg, led)
    pipeline_mod.stage_verify(run, cfg, led)
    first_pass_checks = len(verifier.calls)
    assert first_pass_checks > 0

    # The process dies here. A new run loads the state and continues.
    resumed = state_mod.RunState.load("resume-me")
    assert len(resumed.leads) == len(run.leads)
    cfg2 = make_config(tmp_path, verifier=verifier)
    summary = pipeline_mod.run_pipeline(resumed, cfg2)

    assert summary["status"] == "ok", summary.get("error")
    assert len(verifier.calls) == first_pass_checks, "resume re-paid for verification"
    assert summary["stages"]["verify"].get("skipped")
    assert summary["stages"]["stage"]["staged"] > 0


def test_resume_carries_the_money_already_spent(tmp_path, monkeypatch):
    """Otherwise the 2-cent cap resets on every resume and a run can spend
    forever in small pieces."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("money", cfg.to_meta())
    led = ledger_mod.Ledger(run.run_id, "cleaning")
    led.spend("verify", 4.20)
    led.count("verify", 10)
    run.meta["ledger"] = led.snapshot()
    run.checkpoint(force=True)

    supp_path = str(tmp_path / "supp.json")
    supp_mod.save_cache(suppression_for(), supp_path)
    summary = job.run_factory(_args(resume="money", suppression=supp_path, target=200,
                                    dry_run=False, now=True))
    # $4.20 already spent against very few verified contacts blows the cap the
    # moment the resumed run can see a rate, which is the point.
    assert summary["ledger"]["costs"]["verify"] >= 4.20
    assert summary["status"] in ("halted", "ok")


def test_pending_is_exactly_the_work_left(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("pending", cfg.to_meta())
    led = ledger_mod.Ledger(run.run_id, "cleaning")
    pipeline_mod.stage_source(run, cfg, led)
    assert len(run.pending(models.ICP)) == len(run.leads)
    pipeline_mod.stage_icp(run, cfg, led)
    assert run.pending(models.ICP) == []
    # Rejected leads are finished, not pending.
    assert all(not models.is_rejected(l) for l in run.pending(models.OWNER))


# ----------------------------------------------------------------- the gates
def test_the_paid_gate_blocks_apify_and_prices_what_it_stopped(monkeypatch):
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    source = sources_mod.ApifySource()
    with pytest.raises(sources_mod.PaidCallBlocked) as exc:
        source.fetch("cleaning", 3300, 0.36)
    assert exc.value.usd > 0
    assert "would have cost" in str(exc.value)


def test_the_paid_gate_blocks_millionverifier(monkeypatch):
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    with pytest.raises(sources_mod.PaidCallBlocked):
        contacts.Verifier().verify(["someone@example.com"])


def test_the_paid_finder_is_a_stub_that_still_prices_itself(monkeypatch):
    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")
    finder = contacts.PaidFinder()
    assert finder.enabled is False
    with pytest.raises(sources_mod.PaidCallBlocked) as exc:
        finder.find({"domain": "example.com"})
    assert "no LeadMagic or Prospeo account" in str(exc.value)


def test_a_blocked_paid_source_stops_the_run_without_pretending_it_worked(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    # A cap the preflight clears, so this exercises the paid gate rather than
    # the pre-source budget gate (which halts the documented Apify rates at
    # the 2-cent cap; see test_the_cap_halts_before_the_source_at_real_rates).
    cfg = make_config(tmp_path, source=sources_mod.ApifySource(), max_cost_per_contact=1.0)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("blocked", cfg.to_meta()), cfg)
    assert summary["status"] == "blocked"
    assert summary["stages"]["source"]["would_have_cost_usd"] > 0
    assert summary["counts"] == {}


# -------------------------------------------------------------- suppression
def test_a_suppressed_lead_never_reaches_the_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("supp1", cfg.to_meta())
    led = ledger_mod.Ledger(run.run_id, "cleaning")
    pipeline_mod.stage_source(run, cfg, led)
    victim = run.leads[0]["domain"]
    cfg.suppression_list = suppression_for(domains=[victim])

    summary = pipeline_mod.run_pipeline(run, cfg)
    with open(staged_csv(summary), "r", encoding="utf-8") as fh:
        domains = [models.domain_of(row["email"]) for row in csv.DictReader(fh)]
    assert victim not in domains


def test_the_run_refuses_to_stage_on_an_incomplete_suppression_list(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    broken = supp_mod.SuppressionList()
    broken.errors.append("workspace leads pull failed: boom")
    broken.complete = False
    cfg = make_config(tmp_path, suppression_list=broken)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("refuse", cfg.to_meta()), cfg)
    assert summary["status"] == "refused"
    assert "incomplete" in summary["error"]
    assert "stage" not in summary["stages"]


def test_no_client_and_no_list_refuses_rather_than_staging_blind(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path, suppression_list=None, instantly=None)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("noclient", cfg.to_meta()), cfg)
    assert summary["status"] == "refused"


# ------------------------------------------------------------------- budget
def test_the_run_halts_when_the_projection_breaks_the_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path, max_cost_per_contact=0.000001)
    run = state_mod.RunState.create("broke", cfg.to_meta())
    led = ledger_mod.Ledger(run.run_id, "cleaning", cfg.max_cost_per_contact)
    led.spend("source", 50.0)
    summary = pipeline_mod.run_pipeline(run, cfg, led)
    assert summary["status"] == "halted"
    assert "exceeds" in summary["error"]


# -------------------------------------------------------------- copy + tags
def test_copy_rules_reject_the_things_that_must_never_ship():
    assert personalize.check_copy("Hey Ann, I noticed your AI powered cleaning site, nice work here.", "Ann")
    assert personalize.check_copy("Hey Ann, great to see your growth — really impressive stuff here.", "Ann")
    assert personalize.check_copy("Hey Ann, congrats on the new location, amazing work!", "Ann")
    assert personalize.check_copy("Hey Ann, we help cleaners fill their calendar, worth a chat sometime.", "Ann")
    assert personalize.check_copy("Hi Ann, saw your site and wanted to reach out about something today.", "Ann")
    assert personalize.check_copy("Hey Ann, {{companyName}} looks like it is growing well these days here.", "Ann")
    assert personalize.check_copy("short", "Ann")
    assert personalize.check_copy("Hey Ann, " + "x" * 400, "Ann") is not None


def test_a_clean_line_passes():
    line = "Hey Ann, saw Bright Path handles nightly janitorial for medical offices out in Naperville."
    assert personalize.check_copy(line, "Ann") is None


def test_a_model_line_that_breaks_the_rules_falls_back_rather_than_shipping():
    lead = models.new_lead({"company_name": "Acme Clean", "city": "Tulsa", "website": "https://acme.com",
                            "first_name": "Ann"}, source="test")
    summary = personalize.personalize(
        [lead], niche_label="commercial cleaning",
        generator=lambda l: "Hey Ann, our AI platform can book you calls — guaranteed!",
    )
    assert summary["fallback"] == 1
    assert summary["rejected"] == 0
    assert personalize.check_copy(lead["personalization"], "Ann") is None
    assert lead["personalization_model"] == "template"


def test_trigger_variables_are_filled_or_the_lead_is_marked_a_variant_only():
    from services.list_factory import icp

    rubric = icp.load_rubric("cleaning")
    medical = models.new_lead({"company_name": "Bright Path", "city": "Oak Park", "state": "Illinois",
                               "keywords": "janitorial for medical office buildings and clinics"}, source="t")
    nowhere = models.new_lead({"company_name": "Vanta", "city": "Nowheresville", "state": "Oklahoma",
                               "keywords": "cleaning"}, source="t")
    summary = personalize.tag_triggers([medical, nowhere], rubric)

    assert medical["building_type"] == "medical"
    assert medical["metro"] == "Chicago"          # Oak Park exists only as a Chicago suburb
    assert medical["b_variant_eligible"] is True
    assert nowhere["b_variant_eligible"] is False
    assert "missing" in nowhere["b_variant_reason"]
    assert summary["eligible"] == 1 and summary["not_eligible"] == 1


def test_a_city_that_is_its_own_metro_keeps_its_own_name():
    """Naperville is both a metro and a Chicago suburb. An owner there says
    Naperville, so the more specific answer wins."""
    assert personalize.metro_for("Naperville") == "Naperville"
    assert personalize.metro_for("Oak Park") == "Chicago"


def test_an_unknown_city_gets_no_metro_rather_than_a_plausible_one():
    assert personalize.metro_for("Nowheresville") == ""
    assert personalize.metro_for("") == ""


def test_a_missing_trigger_variable_is_never_filled_with_a_guess():
    from services.list_factory import icp

    rubric = icp.load_rubric("recruiting")
    vague = models.new_lead({"company_name": "Generic Search Partners", "city": "Chicago",
                             "keywords": "executive search"}, source="t")
    personalize.tag_triggers([vague], rubric)
    assert vague["specialty"] == "executive"
    plain = models.new_lead({"company_name": "Generic Search", "city": "Chicago",
                             "keywords": "direct hire placements"}, source="t")
    personalize.tag_triggers([plain], rubric)
    assert plain["specialty"] == ""
    assert plain["b_variant_eligible"] is False


# -------------------------------------------------------------- email rules
def test_only_the_four_blueprint_patterns_are_ever_verified():
    cands = contacts.candidates_for("John", "Smith", "abcclean.com")
    assert cands == [
        "john@abcclean.com", "john.smith@abcclean.com",
        "jsmith@abcclean.com", "johnsmith@abcclean.com",
    ]


def test_a_single_name_still_produces_one_candidate():
    assert contacts.candidates_for("Sam", "", "samclean.com") == ["sam@samclean.com"]


def test_no_name_means_no_candidates_and_no_spend():
    assert contacts.candidates_for("", "", "somewhere.com") == []


def test_verification_stops_at_the_first_hit():
    """Verifying all four patterns per lead would roughly triple the bill for
    the same one address we actually mail."""
    verifier = FakeVerifier()
    lead = models.new_lead({"company_name": "Acme", "website": "https://acme.com",
                            "first_name": "John", "last_name": "Smith"}, source="t")
    contacts.generate_candidates([lead])
    contacts.verify_leads([lead], verifier=verifier)
    assert lead["email"] == "john@acme.com"
    assert verifier.calls == ["john@acme.com"]


def test_a_role_address_is_skipped_even_when_it_verifies():
    verifier = FakeVerifier(role_addresses={"john@acme.com"})
    lead = models.new_lead({"company_name": "Acme", "website": "https://acme.com",
                            "first_name": "John", "last_name": "Smith"}, source="t")
    contacts.generate_candidates([lead])
    contacts.verify_leads([lead], verifier=verifier)
    assert lead.get("email") != "john@acme.com"


def test_a_lead_with_no_domain_is_dropped_before_any_owner_lookup():
    """The $0.005 would buy a name we have nowhere to send."""
    lead = models.new_lead({"company_name": "Vanta Clean Cooperative", "city": "Tulsa"}, source="t")
    summary = contacts.resolve_owners([lead], industry="cleaning", finder=_ExplodingOwnerFinder())
    assert summary["no_domain"] == 1
    assert lead["reject_reason"] == models.REJECT_NO_DOMAIN


class _ExplodingOwnerFinder(contacts.OwnerFinder):
    def discover(self, lead, industry):  # pragma: no cover - must never run
        raise AssertionError("owner look-up must not be attempted without a domain")


# ------------------------------------------------------------------ the CLI
def _args(**kw):
    defaults = dict(
        niche="cleaning", campaign=None, target=200, source="fixture", fixture=FIXTURE,
        fixtures=True, metros=None, resume=None, max_cost_per_contact=0.02, batch_size=20,
        max_escalations=0, refresh_suppression=False, skip_hostile_scan=False, offline=True,
        suppression=None, verify="replay", replay_ok_multiplier=1.0,
        would_do="batch", json=False, dry_run=True, now=False,
        fresh=True, allow_stale_suppression=False, catch_all="include",
    )
    defaults.update(kw)
    return type("Args", (), defaults)


def test_preflight_prices_a_3300_lead_run_and_says_whether_it_fits(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    report = job.run_preflight(_args(target=3300, source="apify", fixtures=False, fixture=None))
    assert report["projected"]["verified"] > 0
    assert report["usd"]["total"] > 0
    assert isinstance(report["within_cap"], bool)
    assert report["cost_per_verified"] > 0


def test_an_offline_run_with_no_suppression_list_refuses_rather_than_staging(tmp_path, monkeypatch, capsys):
    """Offline is not a reason to mail someone twice."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "cost_ledger.csv"))
    rc = job.main(["--dry-run", "--fixtures", "--offline", "--target", "200"])
    assert rc == 1
    assert "refused" in capsys.readouterr().out


def test_cli_dry_run_writes_a_ledger_row_and_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "cost_ledger.csv"))
    monkeypatch.setenv("ALLOW_PAID_CALLS", "")
    supp_path = str(tmp_path / "supp.json")
    supp_mod.save_cache(suppression_for(), supp_path)
    rc = job.main(["--dry-run", "--fixtures", "--offline", "--suppression", supp_path,
                   "--target", "200", "--max-escalations", "0"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "cost per verified contact" in out
    with open(str(tmp_path / "cost_ledger.csv"), "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert int(rows[0]["sourced"]) == 58
    assert int(rows[0]["icp_reject"]) > 0


def test_cli_runs_listing_is_harmless(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    assert job.main(["--runs"]) == 0
    assert "resumable runs" in capsys.readouterr().out


# -------------------------------------------------------- the replay verifier
def test_replay_verifier_spends_nothing_and_is_reproducible():
    v = contacts.ReplayVerifier()
    first = v.verify(["ann@acme.com", "ann.lee@acme.com", "alee@acme.com"])
    second = contacts.ReplayVerifier().verify(["ann@acme.com", "ann.lee@acme.com", "alee@acme.com"])
    assert [r["status"] for r in first] == [r["status"] for r in second]
    assert all(r["raw"]["replay"] for r in first)
    assert v.name == "replay"


def test_replay_draws_roughly_the_recorded_distribution():
    """The recorded plain-pattern rate is about 87% deliverable. A replay that
    drifted far from it would make every rehearsal's cost model fiction."""
    v = contacts.ReplayVerifier()
    rows = v.verify(["owner%d@company%d.com" % (i, i) for i in range(2000)])
    deliverable = sum(1 for r in rows if r["is_deliverable"])
    assert 0.80 < deliverable / float(len(rows)) < 0.94


def test_the_ok_multiplier_moves_the_surplus_to_invalid_not_into_thin_air():
    pessimistic = contacts.ReplayVerifier(ok_multiplier=0.5)
    rows = pessimistic.verify(["owner%d@company%d.com" % (i, i) for i in range(2000)])
    deliverable = sum(1 for r in rows if r["is_deliverable"]) / float(len(rows))
    assert 0.38 < deliverable < 0.50
    assert len(rows) == 2000


def test_a_replayed_row_is_labelled_so_it_cannot_pass_as_a_paid_one(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path, verifier=contacts.ReplayVerifier())
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("replay", cfg.to_meta()), cfg)
    state = state_mod.RunState.load("replay")
    verified = [l for l in state.leads if l.get("email")]
    assert verified
    assert all(l["verify_source"] == "replay" for l in verified)


def test_building_type_picks_the_strongest_signal_not_the_first_listed():
    """Found in the first rehearsal: a cleaner whose page mentions restaurants,
    retail and one medical suite was tagged 'medical' only because medical is
    listed first in the rubric, and that word goes straight into the email."""
    from services.list_factory import icp

    rubric = icp.load_rubric("cleaning")
    lead = models.new_lead({
        "company_name": "Allstar Commercial Cleaning", "city": "San Diego",
        "keywords": "restaurant cleaning, retail cleaning, store cleaning, grocery, medical",
    }, source="t")
    personalize.tag_triggers([lead], rubric)
    assert lead["building_type"] == "retail"


def test_a_single_clear_signal_still_wins():
    from services.list_factory import icp

    rubric = icp.load_rubric("cleaning")
    lead = models.new_lead({"company_name": "Clinic Clean", "city": "Chicago",
                            "keywords": "medical office and clinic cleaning"}, source="t")
    personalize.tag_triggers([lead], rubric)
    assert lead["building_type"] == "medical"


# =====================================================================
# Regressions from the 2026-09-22 review. Each one failed before its fix.
# =====================================================================

# ------------------------------------------------------- the paid model gate
def test_the_paid_gate_blocks_anthropic_when_llm_fake_is_off(monkeypatch):
    """ALLOW_PAID_CALLS guarded Apify, Perplexity and MillionVerifier while the
    two model stages billed real tokens the moment LLM_FAKE was unset, which is
    22 percent of a 3,300-lead run sitting outside every gate the runbook
    advertises."""
    from services.list_factory import icp

    monkeypatch.setenv("LLM_FAKE", "")
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    rubric = icp.load_rubric("cleaning")
    lead = models.new_lead({"company_name": "Vanta Clean", "keywords": "cleaning"}, source="t")
    with pytest.raises(sources_mod.PaidCallBlocked) as exc:
        icp.score_batch([lead], rubric)
    assert "anthropic" in str(exc.value)
    assert exc.value.usd > 0
    with pytest.raises(sources_mod.PaidCallBlocked):
        personalize.generate_line(lead)


def test_a_faked_model_call_is_never_gated(monkeypatch):
    """LLM_FAKE=1 spends nothing, so the gate must not stand in its way."""
    from services.list_factory import icp

    monkeypatch.setenv("LLM_FAKE", "1")
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    rubric = icp.load_rubric("cleaning")
    lead = models.new_lead({"company_name": "Vanta Clean", "keywords": "cleaning"}, source="t")
    assert icp.score_batch([lead], rubric)


# ------------------------------------------------------------ the hard stop
def _always_finds(**kw):
    """Matches execution.discover_owner.discover_owner_and_research's keywords."""
    return {"first_name": "Pat", "last_name": "Owner", "confidence": "HIGH"}


def test_the_hard_stop_fires_before_the_owner_lookups_are_paid_for(tmp_path, monkeypatch):
    """The projection returned None until verification had already happened, so
    the halt was a post-mortem verdict. On a Google Maps run that is $41.25 of
    Perplexity look-ups spent before the cap could produce a number."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path, max_cost_per_contact=0.0001,
                      owner_finder=contacts.OwnerFinder(discover_fn=_always_finds))
    run = state_mod.RunState.create("early-stop", cfg.to_meta())
    led = cfg.new_ledger(run.run_id)
    led.spend("source", 5.00)     # a realistic source bill already on the books
    summary = pipeline_mod.run_pipeline(run, cfg, led)

    assert summary["status"] == "halted", summary.get("error")
    halted_at = [name for name, res in summary["stages"].items()
                 if isinstance(res, dict) and res.get("halted")]
    assert halted_at == ["source"], summary["stages"].keys()
    assert led.costs["owner"] == 0.0, "the owner money was spent before the stop"
    assert led.costs["verify"] == 0.0


def test_the_projection_charges_every_pattern_not_just_one(tmp_path):
    """The future leg priced one MillionVerifier check per remaining lead while
    DEFAULT_RATES assumes 2.6, understating the remaining bill by 60 percent."""
    led = ledger_mod.Ledger("p", "cleaning", 0.02, rates=pipeline_mod.DEFAULT_RATES)
    led.count("verify", 100)
    led.note("verify_attempted", 200)
    one_check = ledger_mod.PRICES["millionverifier_per_check"] * 1000
    projected = led.project_cost_per_verified(1000, verify_rate=0.5)
    expected = round((led.total() + one_check * 2.6) / 600.0, 6)
    assert projected == pytest.approx(expected)


def test_a_projection_exists_before_anything_has_verified():
    led = ledger_mod.Ledger("p", "cleaning", 0.02, rates=pipeline_mod.DEFAULT_RATES)
    led.spend("owner", 41.25)
    assert led.project_cost_per_verified(1000) is not None


# --------------------------------------------------------------- resume safety
def test_a_crash_mid_stage_still_persists_the_ledger(tmp_path, monkeypatch):
    """run.meta['ledger'] was written only after the stage loop, so a kill -9
    left state.json with no ledger and the resumed run inherited $0. The cap
    restarted on every resume."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("crashy", cfg.to_meta())
    led = cfg.new_ledger(run.run_id)
    run.bind_ledger(led)
    pipeline_mod.stage_source(run, cfg, led)
    led.spend("verify", 66.89)
    led.count("verify", 37)
    run.checkpoint(force=True)          # the last thing a dying process does

    reloaded = state_mod.RunState.load("crashy")
    assert "ledger" in reloaded.meta, sorted(reloaded.meta)
    assert reloaded.meta["ledger"]["costs"]["verify"] == pytest.approx(66.89)
    assert reloaded.meta["ledger"]["counts"]["verify"] == 37


def test_a_crash_inside_verify_keeps_the_count_with_the_money(tmp_path, monkeypatch):
    """on_checks charged per check as the stage ran while the verified count
    was assigned only after verify_leads returned, so a crash persisted 100
    percent of the cost and 0 percent of the count."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("midverify", cfg.to_meta())
    led = cfg.new_ledger(run.run_id)
    run.bind_ledger(led)
    for step in (pipeline_mod.stage_source, pipeline_mod.stage_presuppress,
                 pipeline_mod.stage_icp, pipeline_mod.stage_owner, pipeline_mod.stage_patterns):
        step(run, cfg, led)

    class Exploding(FakeVerifier):
        def verify(self, emails):
            if len(self.calls) >= 8:
                raise RuntimeError("process died")
            return FakeVerifier.verify(self, emails)

    cfg.verifier = Exploding()
    with pytest.raises(RuntimeError):
        pipeline_mod.stage_verify(run, cfg, led)
    assert led.counts["verify"] > 0, "the money was charged and the count was not"
    assert led.costs["verify"] > 0
    assert led.cost_per_verified() < 0.02


def test_resuming_a_finished_run_does_not_empty_the_staged_csv(tmp_path, monkeypatch):
    """--resume is the documented recovery path, so an operator who is unsure
    whether Sunday's run finished must not destroy the week's list by asking."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("finished", cfg.to_meta()), cfg)
    path = staged_csv(summary)
    before = stage_out.csv_data_rows(path)
    assert before > 10

    again = pipeline_mod.run_pipeline(state_mod.RunState.load("finished"), make_config(tmp_path))
    assert stage_out.csv_data_rows(path) == before
    assert again["stages"]["stage"].get("skipped")


def test_write_csv_refuses_to_replace_a_staged_list_with_a_header(tmp_path):
    path = str(tmp_path / "staged.csv")
    lead = models.new_lead({"company_name": "Acme", "website": "https://acme.com"}, source="t")
    lead["email"] = "ann@acme.com"
    stage_out.write_csv([lead], path)
    with pytest.raises(stage_out.StagedCsvWouldBeEmptied):
        stage_out.write_csv([], path)
    assert stage_out.csv_data_rows(path) == 1


def test_create_refuses_to_overwrite_an_existing_run(tmp_path, monkeypatch):
    """Two invocations in the same second produced the same id, and create()
    reset leads to [] on the existing directory."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("dup", cfg.to_meta())
    run.add_leads([models.new_lead({"company_name": "A", "website": "https://a.com"}, source="t")])
    run.checkpoint(force=True)
    with pytest.raises(state_mod.RunStateError):
        state_mod.RunState.create("dup", cfg.to_meta())
    assert len(state_mod.RunState.load("dup").leads) == 1


def test_run_ids_do_not_collide_within_a_second():
    from datetime import datetime as dt

    fixed = dt(2026, 9, 27, 1, 0, 0, tzinfo=timezone.utc)
    ids = {state_mod.new_run_id("cleaning", fixed) for _ in range(50)}
    assert len(ids) > 45, ids


def test_the_job_resumes_an_open_run_instead_of_paying_twice(tmp_path, monkeypatch):
    """An at-least-once scheduler fires the Sunday job twice; the second run
    used to start from source and pay for the whole pipeline again."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    supp_path = str(tmp_path / "supp.json")
    supp_mod.save_cache(suppression_for(), supp_path)

    # --now: a dry run never adopts an open run (re-review 2)
    first = job.run_factory(_args(suppression=supp_path, fresh=False, dry_run=False, now=True))
    assert first["resumed"] is False
    # The scheduler fires again before anything closed the run.
    state = state_mod.RunState.load(first["run_id"])
    state.meta["status"] = "open"
    state.meta["stages_done"] = ["source"]
    state.checkpoint(force=True)

    second = job.run_factory(_args(suppression=supp_path, fresh=False, dry_run=False, now=True))
    assert second["run_id"] == first["run_id"]
    assert second["resumed"] is True


# ------------------------------------------------------- verifier behaviour
class ErroringVerifier(contacts.Verifier):
    name = "broken-mv"

    def __init__(self):
        contacts.Verifier.__init__(self)
        self.calls = []

    def verify(self, emails):
        self.calls.extend(emails)
        return [{"email": e, "status": "error", "is_deliverable": False, "raw": None} for e in emails]


def test_a_verifier_outage_holds_leads_instead_of_rejecting_them(tmp_path, monkeypatch):
    """An outage used to burn all four patterns per lead, reject the whole
    week's list terminally, report ok and exit 0. A resume then made zero
    checks, because models.reject is terminal."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    verifier = ErroringVerifier()
    cfg = make_config(tmp_path, verifier=verifier)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("outage", cfg.to_meta()), cfg)

    assert summary["status"] == "error"
    assert "failed outright" in summary["error"]
    state = state_mod.RunState.load("outage")
    assert not any(l.get("reject_reason") == models.REJECT_UNVERIFIABLE for l in state.leads)
    assert any(models.is_held(l) for l in state.leads)
    # One pattern per lead, not four.
    assert len(verifier.calls) <= contacts.MIN_CHECKS_BEFORE_ERROR_STOP + 2

    # ... and a resume with a healthy verifier picks them up.
    healthy = FakeVerifier()
    resumed = pipeline_mod.run_pipeline(state_mod.RunState.load("outage"),
                                        make_config(tmp_path, verifier=healthy))
    assert resumed["status"] == "ok", resumed.get("error")
    assert len(healthy.calls) > 0
    assert resumed["stages"]["stage"]["staged"] > 5


def test_an_unknown_verdict_is_not_an_outage():
    """MillionVerifier's own per-address 'unknown' is a real answer at a steady
    background rate; treating it as a transport failure would stop every run."""
    rows = {"a@x.com": "unknown", "a.b@x.com": "valid"}
    lead = models.new_lead({"company_name": "X", "website": "https://x.com",
                            "first_name": "A", "last_name": "B"}, source="t")
    contacts.generate_candidates([lead])

    class V(contacts.Verifier):
        name = "t"

        def verify(self, emails):
            return [{"email": e, "status": rows.get(e, "invalid"), "raw": {}} for e in emails]

    summary = contacts.verify_leads([lead], verifier=V())
    assert summary["unknown"] == 1
    assert summary["verified"] == 1
    assert lead["email"] == "a.b@x.com"
    assert not models.is_held(lead)


def test_a_credit_balance_below_the_projection_refuses_to_start(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")
    monkeypatch.setattr(contacts, "credits_available", lambda *a, **k: 3)
    cfg = make_config(tmp_path, verifier=contacts.Verifier(verify_fn=lambda e: [
        {"email": x, "status": "valid", "raw": {}} for x in e]))
    cfg.verifier.name = "millionverifier"
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("nocredit", cfg.to_meta()), cfg)
    assert summary["status"] == "error"
    assert "credits" in summary["error"]


def test_a_catch_all_is_counted_apart_from_a_confirmed_mailbox(tmp_path, monkeypatch):
    """A catch-all domain accepts every local part at SMTP time, so a guessed
    address there is not a confirmed contact and must not be the denominator of
    the cost-per-verified KPI."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))

    class Mixed(contacts.Verifier):
        name = "mixed"

        def verify(self, emails):
            out = []
            for e in emails:
                catch = e.startswith("a") or e.startswith("b")
                out.append({"email": e, "status": "catch_all" if catch else "valid",
                            "is_catch_all": catch, "raw": {}})
            return out

    cfg = make_config(tmp_path, verifier=Mixed())
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("catchy", cfg.to_meta()), cfg)
    led = summary["ledger"]
    assert led["counts"]["catch_all"] > 0
    assert led["counts"]["verify"] + led["counts"]["catch_all"] == summary["stages"]["stage"]["staged"]
    assert led["cost_per_verified"] >= led["cost_per_deliverable"]
    assert 0 < summary["stages"]["stage"]["catch_all_share"] < 1


def test_excluding_catch_alls_stages_only_confirmed_mailboxes(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))

    class MostlyCatch(contacts.Verifier):
        """Every third address is a confirmed mailbox, the rest catch-all. (An
        all-catch-all run now halts as unbounded: see the MKT-1 re-review tests
        at the end of this file.)"""
        name = "mostlycatch"

        def __init__(self):
            contacts.Verifier.__init__(self)
            self.n = 0

        def verify(self, emails):
            out = []
            for e in emails:
                self.n += 1
                if self.n % 3 == 0:
                    out.append({"email": e, "status": "valid", "is_role": False, "is_catch_all": False})
                else:
                    out.append({"email": e, "status": "catch_all", "is_role": False, "is_catch_all": True})
            return out

    # Only one address in three is confirmed and the catch-alls are still
    # personalized, so at worst-case thinking (Opus 5.5, 2026-09-25) the
    # projection is honestly over the $0.07 default. This test is about what
    # gets staged, not the cap, so it runs with a loose one.
    cfg = make_config(tmp_path, verifier=MostlyCatch(), include_catch_all=False, max_cost_per_contact=1.0)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("nocatch", cfg.to_meta()), cfg)
    assert summary["status"] in ("ok", "short"), summary.get("error")
    stage = summary["stages"]["stage"]
    assert stage["catch_all_excluded"] > 0
    assert stage["staged"] > 0
    assert stage["catch_all_staged"] == 0


# ----------------------------------------------------------- the paid gate
def test_a_gate_blocked_lead_is_held_and_picked_up_on_the_next_pass(tmp_path, monkeypatch):
    """models.reject is terminal and pending() filters a rejected lead out for
    good, so the runbook's 'rehearse, then open the gate and resume' sequence
    returned an empty list and no explanation."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    # Strip the source rows' names so every lead needs a paid look-up.
    rows = json.load(open(FIXTURE, "r", encoding="utf-8"))
    nameless = str(tmp_path / "nameless.json")
    with open(nameless, "w", encoding="utf-8") as fh:
        json.dump([dict(r, first_name="", last_name="") for r in rows], fh)

    # A high cap: 20 leads at $0.005 an owner look-up genuinely is over 2 cents
    # a contact on a 58-row fixture, and the hard stop would (correctly) fire
    # mid-stage. This test is about the gate, not the budget.
    cfg = make_config(tmp_path, source=sources_mod.FixtureSource(nameless), max_cost_per_contact=1.0)
    first = pipeline_mod.run_pipeline(state_mod.RunState.create("gated", cfg.to_meta()), cfg)
    assert first["status"] == "blocked", first.get("error")
    assert first["held"] > 0
    assert first["stages"]["owner"]["blocked"] > 0

    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")
    cfg2 = make_config(tmp_path, source=sources_mod.FixtureSource(nameless),
                       max_cost_per_contact=1.0,
                       owner_finder=contacts.OwnerFinder(discover_fn=_always_finds))
    second = pipeline_mod.run_pipeline(state_mod.RunState.load("gated"), cfg2)
    assert second["status"] == "ok", second.get("error")
    assert second["stages"]["owner"]["found"] > 0
    assert second["stages"]["stage"]["staged"] > 0


def test_a_closed_paid_gate_at_verify_is_reported_as_blocked_not_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    cfg = make_config(tmp_path, verifier=contacts.Verifier())   # the real paid client
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("vgate", cfg.to_meta()), cfg)
    assert summary["status"] == "blocked", summary.get("error")
    assert summary["stages"]["verify"]["blocked"] > 0


# ------------------------------------------------------------ silent failure
def test_an_empty_source_does_not_report_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    empty = str(tmp_path / "empty.json")
    with open(empty, "w", encoding="utf-8") as fh:
        fh.write("[]")
    cfg = make_config(tmp_path, source=sources_mod.FixtureSource(empty))
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("empty", cfg.to_meta()), cfg)
    assert summary["status"] == "short", summary
    assert summary["staged"] == 0


def test_a_real_run_far_below_target_is_short_not_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))

    class TinyApify(sources_mod.ApifySource):
        def fetch(self, niche, target, fill_rate):
            self.last_run_cost = 0.0
            rows = json.load(open(FIXTURE, "r", encoding="utf-8"))[:5]
            return [models.new_lead(r, source="apify:leads-finder", shard="x") for r in rows]

    cfg = make_config(tmp_path, source=TinyApify(), target=3300, max_cost_per_contact=1.0)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("tiny", cfg.to_meta()), cfg)
    assert summary["status"] == "short"
    assert "3300" in summary["error"]


def test_an_apify_run_whose_shards_mostly_failed_raises(monkeypatch):
    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("APIFY_API_TOKEN", "test")
    source = sources_mod.ApifySource(run_shard=lambda *a, **k: {"error": "actor timed out"})
    with pytest.raises(sources_mod.SourceError) as exc:
        source.fetch("cleaning", 100, 1.0)
    assert "shards failed" in str(exc.value)


def test_the_cli_returns_nonzero_and_notifies_when_nothing_is_staged(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    sent = []
    monkeypatch.setattr(job, "notify", lambda *a, **k: sent.append(a))
    empty = str(tmp_path / "empty.json")
    with open(empty, "w", encoding="utf-8") as fh:
        fh.write("[]")
    supp_path = str(tmp_path / "supp.json")
    supp_mod.save_cache(suppression_for(), supp_path)
    rc = job.main(["--now", "--source", "fixture", "--fixture", empty, "--verify", "replay", "--offline",
                   "--suppression", supp_path, "--target", "200", "--fresh"])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert sent, "an unattended run that produced nothing must page Lorenzo"


# ------------------------------------------------------------- cost model
def test_preflight_prices_the_rows_the_run_actually_fetches(tmp_path, monkeypatch):
    """The preflight priced fill_rate=1.0 while stage_source over-fetched by
    1/niche_fill_rate, so the quote the paid gate is opened on understated the
    bill by 2.78x on cleaning."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = pipeline_mod.Config(niche="cleaning", campaign_key="cleaning_trigger",
                              target=3300, source=sources_mod.ApifySource())
    report = pipeline_mod.preflight(cfg)
    assert report["usd"]["source"] == pytest.approx(
        cfg.source.estimate_cost(cfg.source_target, cfg.source_fill_rate)
    )
    # ... and that is the same number the source stage charges.
    shards = sources_mod.plan_shards(cfg.source_target, cfg.source_fill_rate)
    assert sum(shards.values()) == pytest.approx(cfg.source_target, rel=0.02)


def test_preflight_prices_owner_lookups_for_every_source(tmp_path, monkeypatch):
    """$0 of owner cost was hard-coded for Apify, which is only true at a name
    rate of exactly 1.0."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    apify = pipeline_mod.preflight(pipeline_mod.Config(
        niche="cleaning", campaign_key="cleaning_trigger", target=3300,
        source=sources_mod.ApifySource()))
    gmaps = pipeline_mod.preflight(pipeline_mod.Config(
        niche="cleaning", campaign_key="cleaning_trigger", target=3300,
        source=sources_mod.MapsSource(metros=["Chicago"])))
    assert apify["usd"]["owner"] > 0
    assert gmaps["usd"]["owner"] > apify["usd"]["owner"]
    assert apify["projected"]["owner_lookups"] > 0


def test_the_plan_sizes_the_pull_for_staged_contacts_not_verified_ones():
    """Suppression used to run after verification and drop a quarter of the
    list, so --target 3300 staged about 2,500 and paid to verify leads it
    already knew were suppressed."""
    plan = pipeline_mod.plan_counts(3300)
    assert plan["staged"] == pytest.approx(3300, rel=0.02)
    assert plan["survivors"] < plan["sourced"]
    assert "suppression_survival" in plan["rates"]


def test_domain_suppression_runs_before_anything_is_paid_for(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("early-supp", cfg.to_meta())
    led = cfg.new_ledger(run.run_id)
    pipeline_mod.stage_source(run, cfg, led)
    victim = run.leads[0]["domain"]
    cfg.suppression_list = suppression_for(domains=[victim])
    pipeline_mod.stage_presuppress(run, cfg, led)

    assert models.is_rejected(run.leads[0])
    assert run.leads[0]["reject_reason"] == models.REJECT_SUPPRESSED
    # ... and the ICP, owner and verify stages never see it.
    assert run.leads[0] not in run.pending(models.ICP)
    assert led.costs["owner"] == 0.0 and led.costs["verify"] == 0.0


# -------------------------------------------------------------- validation
def test_an_unknown_campaign_key_fails_before_the_paid_stages(tmp_path, monkeypatch):
    """--campaign cleaning_triger used to source, score, discover, verify and
    personalize the whole list and only then fail on the typo."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        job.build_config(_args(campaign="cleaning_triger"), None)
    assert "unknown campaign key" in str(exc.value)


# --------------------------------------------------------------- copy rules
def test_a_line_about_air_ducts_is_not_ai_talk():
    """"ai " and " ai" were substring tests, so air ducts, airports, aisles,
    Dubai and Mumbai all read as AI talk and the good, checkable line was
    silently swapped for the dull template."""
    for line in (
        "Hey Ann, saw Bright Path cleans the air ducts at the terminal each night now.",
        "Hey Ann, saw you handle the airport terminals and the retail aisles overnight.",
        "Hey Raj, saw you run the Mumbai office cleaning crews, that is a big footprint.",
    ):
        assert personalize.check_copy(line, "Ann" if "Ann" in line else "Raj") is None, line
    # ... and a real mention still fails.
    assert personalize.check_copy(
        "Hey Ann, your AI powered cleaning site looks sharp and well put together.", "Ann")


def test_a_company_name_that_trips_a_rule_does_not_bin_a_paid_for_lead():
    """88 of 13,988 real company names failed BOTH the model line and the
    template ("Bottom Line Bookkeeping", "Allman & Associates", "Pllc"), and
    the lead was dropped at the last stage after being fully paid for."""
    for name in ("Bottom Line Bookkeeping", "Aire-master Of America, Inc.",
                 "Allman & Associates", "A. Abbott Accounting Cpa, Llc"):
        lead = models.new_lead({"company_name": name, "city": "Tulsa",
                                "website": "https://x.com", "first_name": "Ann"}, source="t")
        summary = personalize.personalize([lead], niche_label="the books for small businesses",
                                          generator=lambda l: "")
        assert summary["rejected"] == 0, (name, summary["reasons"])
        assert lead["personalization"]
        assert personalize.check_copy(lead["personalization"], "Ann") is None


def test_a_dollar_sign_is_still_caught_even_though_words_are_whole_phrase():
    assert personalize.check_copy("Hey Ann, saw your crew covers three towers for $500 a night.", "Ann")


def test_a_reject_names_the_lead_it_dropped():
    lead = models.new_lead({"company_name": "X", "website": "https://x.com",
                            "first_name": "Ann"}, source="t")
    lead["lead_key"] = "d:x.com"
    personalize.personalize([lead], niche_label="", generator=lambda l: "Hey Ann, " + "!" * 60)
    # The line, the template and the nameless fallback all pass here, so
    # nothing is rejected; the field exists for the case where they do not.
    assert "rejected_leads" in personalize.personalize(
        [models.new_lead({"company_name": "Y"}, source="t")], niche_label="",
        generator=lambda l: "x")


# ------------------------------------------------------- trigger variables
def test_a_pronoun_does_not_produce_a_specialty():
    """keyword_hit strips the keyword, so the trailing-space entries "it ",
    "hr " and "vp " became the bare words it/hr/vp and matched ordinary
    English. specialty is interpolated into live recruiting_outbound copy."""
    from services.list_factory import icp

    rubric = icp.load_rubric("recruiting")
    pronoun = models.new_lead({
        "company_name": "Generic Search", "city": "Chicago",
        "description": "Direct hire search. We make it simple to hire the people you need.",
    }, source="t")
    personalize.tag_triggers([pronoun], rubric)
    assert pronoun["specialty"] == ""
    assert pronoun["b_variant_eligible"] is False

    legal = models.new_lead({
        "company_name": "Generic Search", "city": "Chicago",
        "description": "Direct hire legal recruiting. We make it simple to hire attorneys and paralegals.",
    }, source="t")
    personalize.tag_triggers([legal], rubric)
    assert legal["specialty"] == "legal", "a legal recruiter is not a technology recruiter"


def test_a_tied_building_type_is_left_empty_rather_than_guessed():
    """Nine of the eighteen tagged leads in the recorded rehearsal were decided
    by a tie and five landed on 'medical' purely because medical is the first
    key in cleaning.json. That word goes into the email."""
    from services.list_factory import icp

    rubric = icp.load_rubric("cleaning")
    tied = models.new_lead({"company_name": "Pristine Services", "city": "Chicago",
                            "keywords": "medical, office, industrial, gym"}, source="t")
    personalize.tag_triggers([tied], rubric)
    assert tied["building_type"] == ""
    assert tied["b_variant_eligible"] is False


def test_a_longer_phrase_outweighs_a_passing_mention():
    from services.list_factory import icp

    rubric = icp.load_rubric("cleaning")
    lead = models.new_lead({
        "company_name": "Bright Path Building Services", "city": "Naperville",
        "description": "Nightly janitorial for medical office buildings and clinics.",
    }, source="t")
    personalize.tag_triggers([lead], rubric)
    assert lead["building_type"] == "medical"


# ------------------------------------------------------------------- dedupe
def test_a_duplicate_business_in_the_source_is_staged_once(tmp_path, monkeypatch):
    """The Apify source is sharded by state on purpose, so cross-shard
    duplicates are expected. Nothing covered this."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    twice = str(tmp_path / "twice.json")
    with open(twice, "w", encoding="utf-8") as fh:
        json.dump([
            {"company_name": "Bright Path Building Services",
             "company_website": "https://brightpathbuilding.example",
             "city": "Naperville", "state": "Illinois", "first_name": "Renata",
             "last_name": "Kowalski", "keywords": "commercial cleaning, janitorial services",
             "company_description": "Nightly commercial cleaning for office buildings."},
            {"company_name": "Bright Path Bldg Svcs",
             "company_website": "https://www.brightpathbuilding.example",
             "city": "Naperville", "state": "Illinois", "first_name": "Renata",
             "last_name": "Kowalski", "keywords": "commercial cleaning, janitorial services",
             "company_description": "Nightly commercial cleaning for office buildings."},
        ], fh)
    # Two businesses: one ICP batch call's worst-case thinking (1,024 tokens)
    # over at most one contact is far past the $0.07 default. This test is
    # about de-duplication, not the cap, so it runs with a loose one.
    cfg = make_config(tmp_path, source=sources_mod.FixtureSource(twice), max_cost_per_contact=1.0)
    summary = pipeline_mod.run_pipeline(state_mod.RunState.create("dedupe", cfg.to_meta()), cfg)
    with open(staged_csv(summary), "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1, [r["company_name"] for r in rows]


def test_add_leads_on_a_resume_does_not_double_add(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = state_mod.RunState.create("readd", cfg.to_meta())
    led = cfg.new_ledger(run.run_id)
    pipeline_mod.stage_source(run, cfg, led)
    first = len(run.leads)
    assert run.add_leads(cfg.source.fetch("cleaning", 1000, 1.0)) == 0
    assert len(run.leads) == first


# ------------------------------------------------------------ evidence hygiene
def test_any_fixture_or_replay_run_uses_scratch_logs(tmp_path, monkeypatch):
    """The gate keyed on the --fixtures shorthand, so an identical replay run
    as --now --source fixture --fixture X put its fabricated create_lead_batch
    record in the real shadow log."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    monkeypatch.delenv("SHADOW_LOG_PATH", raising=False)
    monkeypatch.delenv("JOB_LOG_PATH", raising=False)
    supp_path = str(tmp_path / "supp.json")
    supp_mod.save_cache(suppression_for(), supp_path)
    job.main(["--now", "--source", "fixture", "--fixture", FIXTURE, "--verify", "replay", "--offline",
              "--suppression", supp_path, "--target", "200", "--fresh"])
    from shared.job_log import shadow_log_path, job_log_path

    assert "scratch" in str(shadow_log_path())
    assert "scratch" in str(job_log_path())


# ----------------------------------------------------------------- readability
def test_the_summary_states_target_versus_staged(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    supp_path = str(tmp_path / "supp.json")
    supp_mod.save_cache(suppression_for(), supp_path)
    job.main(["--dry-run", "--fixtures", "--offline", "--suppression", supp_path,
              "--target", "3300", "--max-escalations", "0", "--fresh"])
    out = capsys.readouterr().out
    assert "target 3300, staged" in out
    assert "suppression list:" in out
    assert "next:" in out
    assert "cost per deliverable" in out


def test_the_preflight_and_the_ledger_agree_about_what_verified_means(tmp_path, monkeypatch):
    """The preflight printed WITHIN CAP on a denominator that included
    catch-alls while the ledger graded the same run over_cap on confirmed
    mailboxes only. Step 1 of "Going live" is reading that number."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = pipeline_mod.Config(niche="cleaning", campaign_key="cleaning_trigger",
                              target=3300, source=sources_mod.ApifySource())
    report = pipeline_mod.preflight(cfg)
    assert report["projected"]["confirmed"] < report["projected"]["verified"]
    assert report["cost_per_verified"] == pytest.approx(
        report["usd"]["total"] / report["projected"]["confirmed"], rel=1e-4)
    assert report["cost_per_deliverable"] < report["cost_per_verified"]
    assert report["within_cap"] is (report["cost_per_verified"] <= report["cap"])

    led = cfg.new_ledger("x")
    led.count("verify", report["projected"]["confirmed"])
    led.count("catch_all", report["projected"]["verified"] - report["projected"]["confirmed"])
    led.spend("source", report["usd"]["total"])
    assert led.cost_per_verified() == pytest.approx(report["cost_per_verified"], rel=1e-3)


# ---------------------------------------------- MKT-1: the cap at real rates
class _SpyApify(sources_mod.ApifySource):
    """The documented Apify pricing, and a fetch that must never be reached."""

    def __init__(self):
        sources_mod.ApifySource.__init__(self)
        self.fetched = False

    def fetch(self, niche, target, fill_rate):
        self.fetched = True
        raise AssertionError("the source was fetched on a run the preflight prices over the cap")


def test_the_cap_halts_before_the_source_at_real_rates(tmp_path, monkeypatch):
    """MKT-1. At the documented Apify rates the preflight priced a 3,300-contact
    run at about $55 and $0.0222 per confirmed contact, over the then 2-cent
    cap. The old run did not halt at source, presuppress, icp, owner, patterns,
    verify or suppression; it halted after personalize with the whole $55.05
    spent. It must stop before a cent goes to Apify.

    Since 2026-09-25 every model call is Opus 5.5 priced with worst-case
    thinking: the same run is about $153 and $0.062 per confirmed contact,
    inside the $0.07 default (Lorenzo). The halt is pinned with a $0.05 cap."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")   # the paid gate is open: only the cap can stop it
    default = pipeline_mod.preflight(make_config(tmp_path, source=sources_mod.ApifySource(), target=3300))
    assert default["cap"] == ledger_mod.DEFAULT_MAX_COST_PER_CONTACT == 0.07
    assert default["within_cap"] is True, default["cost_per_verified"]
    assert 0.05 < default["cost_per_verified"] < 0.07

    source = _SpyApify()
    cfg = make_config(tmp_path, source=source, target=3300, max_cost_per_contact=0.05)
    pf = pipeline_mod.preflight(cfg)
    assert pf["within_cap"] is False, pf["cost_per_verified"]
    assert pf["usd"]["total"] > 40

    run = state_mod.RunState.create("real-rates", cfg.to_meta())
    summary = pipeline_mod.run_pipeline(run, cfg)
    assert summary["status"] == "halted", summary.get("error")
    assert "before the source fetch" in summary["error"]
    assert source.fetched is False
    assert summary["ledger"]["total_usd"] == 0.0
    halted_at = [n for n, r in summary["stages"].items() if isinstance(r, dict) and r.get("halted")]
    assert halted_at == ["source"]


def _sourced_leads(n):
    rows = []
    for i in range(n):
        rows.append(models.new_lead({
            "company_name": "Clean Co %d" % i, "website": "https://clean%d.example" % i,
            "first_name": "Pat" if i % 50 else "", "last_name": "Owner",
            "description": "commercial cleaning and janitorial services",
        }, source="apify:leads-finder", shard="texas, us"))
    return rows


def test_the_in_run_projection_uses_the_preflight_denominator(tmp_path, monkeypatch):
    """MKT-1. The source-boundary projection used deliverables (catch-alls in)
    and skipped suppression, so it read $0.0161 where the preflight said
    $0.0222. Priced from the run state it now lands on the preflight's figure."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    # $0.05: under this run's $0.062 projection, so the halt below still bites
    # (the $0.07 default no longer halts it; see the test above).
    cfg = make_config(tmp_path, source=sources_mod.ApifySource(), target=3300, max_cost_per_contact=0.05)
    pf = pipeline_mod.preflight(cfg)
    run = state_mod.RunState.create("denominator", cfg.to_meta())
    run.add_leads(_sourced_leads(pf["projected"]["sourced"]))
    led = cfg.new_ledger(run.run_id)
    led.spend("source", pf["usd"]["source"])
    proj = pipeline_mod.project_run(run, cfg, led)
    projected = led.projected_from(proj["future_usd"], proj["expected_new_confirmed"])
    assert proj["expected_new_confirmed"] == pytest.approx(pf["projected"]["confirmed"], rel=0.02)
    assert projected == pytest.approx(pf["cost_per_verified"], rel=0.03)
    # ... and therefore it halts at the source boundary instead of carrying on.
    with pytest.raises(ledger_mod.BudgetExceeded):
        pipeline_mod._check_budget_at(run, cfg, led, pipeline_mod.STAGE_SOURCE)


def test_the_fixture_preflight_and_in_run_projection_agree_with_thinking_priced(tmp_path, monkeypatch):
    """Opus 5.5 thinking cannot be turned off, so both projections carry the
    worst-case allowance from shared.llm.output_tokens_with_thinking: one per
    personalization line, one per ICP batch and one per possible escalation,
    and the preflight now prices the escalation calls too. The preflight and
    the in-run projection price the ICP stage through the same function, so
    at the source boundary they agree on the recorded fixture."""
    from shared import llm
    from services.list_factory import icp

    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path, max_escalations=icp.DEFAULT_MAX_ESCALATIONS)
    pf = pipeline_mod.preflight(cfg)
    head = llm.THINKING_HEADROOM_TOKENS

    # The allowance is the shared constant, per call.
    assert personalize.usd_per_lead() == llm.estimate_cost(
        llm.model_for("research"), personalize.TOKENS_IN_PER_LEAD, personalize.TOKENS_OUT_PER_LEAD + head)
    survivors = pf["projected"]["survivors"]
    batches = -(-survivors // cfg.batch_size)
    escalations = min(cfg.max_escalations, survivors)
    icp_text_in = icp.TOKENS_IN_PER_BUSINESS * (survivors + escalations)
    icp_text_out = icp.TOKENS_OUT_PER_BUSINESS * (survivors + escalations)
    assert pf["usd"]["icp"] == pytest.approx(llm.estimate_cost(
        llm.model_for("classify"), icp_text_in, icp_text_out + head * (batches + escalations)), abs=1e-4)
    assert pf["usd"]["personalize"] == pytest.approx(
        personalize.usd_per_lead() * pf["projected"]["verified"], abs=1e-4)

    run = state_mod.RunState.create("fixture-agree", cfg.to_meta())
    run.add_leads(_sourced_leads(pf["projected"]["sourced"]))
    led = cfg.new_ledger(run.run_id)
    proj = pipeline_mod.project_run(run, cfg, led)
    assert proj["expected_new_confirmed"] == pytest.approx(pf["projected"]["confirmed"], rel=0.02)
    assert led.projected_from(proj["future_usd"], proj["expected_new_confirmed"]) == pytest.approx(
        pf["cost_per_verified"], rel=0.02)


def test_the_fixture_run_completes_under_the_seven_cent_cap(tmp_path, monkeypatch):
    """Lorenzo, 2026-09-25: the cap is $0.07 per confirmed contact while every
    model call is priced at worst-case thinking. The recorded fixture run (the
    fixture configuration every run test here uses: no escalations) is priced
    inside it and runs to the end without a halt.

    With the default 50 escalations the fixture's 58 businesses would be
    priced for 50 extra calls of worst-case thinking (about $1.07) over about
    9 confirmed contacts, which the in-run projection rightly halts on: the
    escalation allowance is a fixed worst case that only a real-sized run
    absorbs (about $1.08 of a 3,300-contact run's $153)."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    assert cfg.max_cost_per_contact == 0.07 and cfg.max_escalations == 0
    pf = pipeline_mod.preflight(cfg)
    assert pf["within_cap"] is True and pf["cost_per_verified"] < 0.07, pf["cost_per_verified"]
    summary = pipeline_mod.run_pipeline(make_run(tmp_path, cfg, "seven-cents"), cfg)
    assert summary["status"] == "ok", summary.get("error")
    assert summary["ledger"]["cost_per_verified"] < 0.07


def test_a_halt_mid_run_stages_what_is_already_verified(tmp_path, monkeypatch):
    """MKT-1. A halt used to `break` before stage_stage, so every verified
    contact already paid for was thrown away and the run reported 0 staged.
    Leads already verified AND personalized are now suppression-checked and
    staged into a separate _halted.csv, and the main stage step stays open for
    --resume. (A halt before personalization stages nothing: see below.)"""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = make_run(tmp_path, cfg, "halt-salvage")
    led = cfg.new_ledger(run.run_id)

    def blow_the_budget(name, result):
        if name == pipeline_mod.STAGE_PERSONALIZE:
            led.spend("verify", 500.0, "test: an expensive verification bill")

    summary = pipeline_mod.run_pipeline(run, cfg, led, on_stage=blow_the_budget)
    assert summary["status"] == "halted", summary.get("error")
    assert summary["stages"]["personalize"].get("halted")
    salvage = summary["stages"]["salvage"]
    assert salvage["verified_waiting"] > 0
    assert salvage["staged"] > 0, salvage
    assert salvage["csv"].endswith("_halted.csv")
    assert os.path.exists(salvage["csv"])
    assert stage_out.csv_data_rows(salvage["csv"]) == salvage["staged"]
    assert summary["staged"] == salvage["staged"]
    assert not run.stage_done(pipeline_mod.STAGE_STAGE), "a resume must still be able to stage the rest"
    # Nothing new was bought for leads that were not already verified.
    assert led.costs["source"] == 0.0


def test_a_halt_before_anything_verified_stages_nothing_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = make_run(tmp_path, cfg, "halt-early")
    led = cfg.new_ledger(run.run_id)

    def blow_the_budget(name, result):
        if name == pipeline_mod.STAGE_ICP:
            led.spend("icp", 500.0, "test")

    summary = pipeline_mod.run_pipeline(run, cfg, led, on_stage=blow_the_budget)
    assert summary["status"] == "halted"
    assert summary["stages"]["salvage"]["staged"] == 0
    assert "nothing had been verified" in summary["stages"]["salvage"]["note"]


def test_a_finished_run_over_the_cap_is_not_reported_ok(tmp_path, monkeypatch):
    """The halt check used to run after the stage step as well, so a finished
    over-cap run was reported "halted" and told to resume. It is over_cap."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = make_run(tmp_path, cfg, "late-overspend")
    led = cfg.new_ledger(run.run_id)

    def late_bill(name, result):
        if name == pipeline_mod.STAGE_STAGE:
            led.spend("personalize", 500.0, "test")

    summary = pipeline_mod.run_pipeline(run, cfg, led, on_stage=late_bill)
    assert summary["status"] == "over_cap", summary.get("error")
    assert summary["staged"] > 0


# ------------------------------------------- MKT-1 re-review: no paid call after a halt
def test_a_halt_driven_by_personalization_cost_makes_no_personalizer_call(tmp_path, monkeypatch):
    """The reviewer's probe: from the verify boundary on, a personalization line
    costs $1. The cap halted on "$30 still to spend", and the salvage then made
    30 paid personalizer calls and finished at $30.02 while reporting halted."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path)
    run = make_run(tmp_path, cfg, "salvage-probe")
    led = cfg.new_ledger(run.run_id)
    expensive = {"on": False}
    real = pipeline_mod._personalize_usd_per_lead
    monkeypatch.setattr(pipeline_mod, "_personalize_usd_per_lead",
                        lambda: 1.0 if expensive["on"] else real())
    calls = {"n": 0}

    def paid_personalizer(lead):
        calls["n"] += 1
        led.spend("personalize", 1.0, "probe: $1 per line", 1)
        return fake_personalizer(lead)

    cfg.personalizer = paid_personalizer

    def hook(name, result):
        if name == pipeline_mod.STAGE_VERIFY:
            expensive["on"] = True

    summary = pipeline_mod.run_pipeline(run, cfg, led, on_stage=hook)
    assert summary["status"] == "halted", summary.get("error")
    assert "still to spend" in summary["error"]
    assert calls["n"] == 0, "the salvage paid for personalization the cap had refused"
    assert led.costs.get("personalize", 0.0) == 0.0
    salvage = summary["stages"]["salvage"]
    assert salvage["paid_calls"] == 0
    assert salvage["personalized"] == 0
    assert salvage["awaiting_personalization"] > 0
    assert salvage["staged"] == 0
    assert summary["ledger"]["total_usd"] < 1.0
    assert not run.stage_done(pipeline_mod.STAGE_STAGE)


class _AllCatchAll(contacts.Verifier):
    name = "fake-mv-catchall"

    def verify(self, emails):
        return [{"email": e, "status": "catch_all", "is_role": False, "is_catch_all": True, "raw": {}}
                for e in emails]


def test_zero_confirmed_with_money_spent_halts_in_run(tmp_path, monkeypatch):
    """The reviewer's probe: every address catch-all plus a $5 verify bill used
    to finish ok, because the projection had no number and None passed."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    # A high cap, so the only thing that can stop it is the unbounded rule,
    # which needs MIN_OBSERVED_SAMPLE_LEADS (30) leads verified: the fixture
    # has exactly 30 with an owner.
    cfg = make_config(tmp_path, verifier=_AllCatchAll(), max_cost_per_contact=1.0)
    run = make_run(tmp_path, cfg, "zero-confirmed")
    led = cfg.new_ledger(run.run_id)

    def hook(name, result):
        if name == pipeline_mod.STAGE_VERIFY:
            led.spend("verify", 5.0, "probe: an expensive verification bill")

    summary = pipeline_mod.run_pipeline(run, cfg, led, on_stage=hook)
    assert summary["status"] == "halted", summary.get("error")
    assert "unbounded" in summary["error"]
    assert summary["ledger"]["counts"].get("verify", 0) == 0
    assert summary["ledger"]["detail"]["last_projection"]["unbounded"] is True
    assert summary["stages"]["salvage"]["paid_calls"] == 0


def test_a_finished_run_with_money_and_no_confirmed_contact_is_over_cap(tmp_path, monkeypatch):
    """The final status, with the in-run check out of the way: never ok."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline_mod, "_check_budget_at", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_mod, "_gate_before_source", lambda *a, **k: {})
    cfg = make_config(tmp_path, verifier=_AllCatchAll())
    run = make_run(tmp_path, cfg, "zero-confirmed-final")
    led = cfg.new_ledger(run.run_id)
    led.spend("verify", 5.0, "probe")
    summary = pipeline_mod.run_pipeline(run, cfg, led)
    assert summary["status"] == "over_cap", summary.get("error")
    assert "confirmed no contact" in summary["error"]


def test_the_job_exits_1_and_pushes_on_a_zero_confirmed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    rows, pushes = [], []
    monkeypatch.setattr(job, "log_run", lambda j, status, details=None: rows.append(status))
    monkeypatch.setattr(job, "notify", lambda title, body="", **kw: pushes.append((title, body, kw)))
    summary = {"run_id": "r", "niche": "cleaning", "status": "over_cap", "staged": 12, "target": 200,
               "error": "spent $5.0000 and confirmed no contact", "stages": {},
               "ledger": {"total_usd": 5.0, "counts": {"verify": 0, "stage": 12}, "cost_per_verified": None}}

    class A(object):
        json = False
        dry_run = False
        all_campaigns = False

    assert job._report_run(A(), summary) == 1
    assert rows == ["over_cap"]
    assert pushes and pushes[-1][2]["priority"] == "high"


# --------------------------- re-review 2: an unlucky first batch is not a verdict
class _UnluckyStart(contacts.Verifier):
    """The reviewer's probe: the first 20 checks come back catch-all, after that
    the first pattern verifies as usual."""
    name = "fake-mv-unlucky"

    def __init__(self):
        contacts.Verifier.__init__(self)
        self.n = 0

    def verify(self, emails):
        out = []
        for e in emails:
            self.n += 1
            if self.n <= 20:
                out.append({"email": e, "status": "catch_all", "is_role": False, "is_catch_all": True})
            elif "." not in e.split("@")[0]:
                out.append({"email": e, "status": "valid", "is_role": False, "is_catch_all": False})
            else:
                out.append({"email": e, "status": "invalid", "is_role": False})
        return out


def _resume_ledger(run, cfg):
    """What jobs.list_factory.run_factory does on --resume."""
    led = cfg.new_ledger(run.run_id)
    prev = run.meta.get("ledger") or {}
    for stage, amount in (prev.get("costs") or {}).items():
        led.spend(stage, amount, "resumed", 0)
    for stage, count in (prev.get("counts") or {}).items():
        led.count(stage, count)
    for key, value in (prev.get("detail") or {}).items():
        led.note(key, value)
    return led


def test_an_unlucky_first_batch_runs_through_on_the_plan_rate(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    verifier = _UnluckyStart()
    # A high cap: on a 30-lead fixture the ratio line itself is crossed while
    # nothing is confirmed yet ($0.017 of ICP spend over 4 expected contacts).
    # This test is about the unbounded rule, which ignores the cap.
    cfg = make_config(tmp_path, verifier=verifier, max_cost_per_contact=1.0)
    summary = pipeline_mod.run_pipeline(make_run(tmp_path, cfg, "unlucky"), cfg)
    assert summary["status"] in ("ok", "short"), summary.get("error")
    assert summary["ledger"]["counts"]["verify"] > 0
    assert summary["stages"]["stage"]["staged"] > 0


def test_an_unbounded_halt_is_re_tested_on_resume_and_the_run_stages(tmp_path, monkeypatch):
    """Halt on a small sample (the minimum forced down to 5 for the first pass),
    then resume with the real minimum: the resume re-tests verification on a
    fresh sample instead of re-halting at the source boundary on the saved
    zero rate, and the list stages."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    verifier = _UnluckyStart()
    cfg = make_config(tmp_path, verifier=verifier, max_cost_per_contact=1.0)
    run = make_run(tmp_path, cfg, "unlucky-resume")
    monkeypatch.setattr(ledger_mod, "MIN_OBSERVED_SAMPLE_LEADS", 5)
    first = pipeline_mod.run_pipeline(run, cfg, cfg.new_ledger(run.run_id))
    assert first["status"] == "halted", first.get("error")
    assert "unbounded" in first["error"]
    assert "re-tests on a fresh sample" in first["error"]
    assert first["ledger"]["counts"].get("verify", 0) == 0

    monkeypatch.setattr(ledger_mod, "MIN_OBSERVED_SAMPLE_LEADS", 30)
    resumed = state_mod.RunState.load("unlucky-resume")
    cfg2 = make_config(tmp_path, verifier=verifier, max_cost_per_contact=1.0)
    led2 = _resume_ledger(resumed, cfg2)
    checks_before = verifier.n
    second = pipeline_mod.run_pipeline(resumed, cfg2, led2)
    assert second["status"] in ("ok", "short"), second.get("error")
    assert verifier.n > checks_before, "the resume did not re-test verification"
    assert second["ledger"]["detail"]["rate_sample_from"]["reason"].startswith("resume after")
    assert second["ledger"]["counts"]["verify"] > 0
    assert second["stages"]["stage"]["staged"] > 0


def test_a_finished_run_names_the_line_it_crossed():
    """With --max-cost-per-contact 1000 it said "over the $1000.0000 cap (verdict
    alert)" when the line crossed was Section 6's $0.04 alert line."""
    msg = pipeline_mod._over_line_message(0.05, 1000.0)
    assert "Section 6's $0.04 alert line" in msg
    assert "over the run's" not in msg
    assert "inside the run's own $1000.0000 cap" in msg
    msg = pipeline_mod._over_line_message(0.03, 0.02)
    assert "over the run's $0.0200 cap" in msg and "alert line" not in msg
    msg = pipeline_mod._over_line_message(0.05, 0.02)
    assert "the run's $0.0200 cap and Section 6's $0.04 alert line" in msg


def test_the_finished_status_with_a_high_cap_names_the_alert_line(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    cfg = make_config(tmp_path, max_cost_per_contact=1000.0)
    run = make_run(tmp_path, cfg, "alert-line")
    led = cfg.new_ledger(run.run_id)

    def hook(name, result):
        if name == pipeline_mod.STAGE_STAGE:
            led.spend("verify", 0.05 * max(1, led.verified_count()), "test: pushes it past $0.04")

    summary = pipeline_mod.run_pipeline(run, cfg, led, on_stage=hook)
    assert summary["status"] == "over_cap", summary.get("error")
    assert "Section 6's $0.04 alert line" in summary["error"]
    assert "$1000.0000 cap" not in summary["error"].split("(")[0]
