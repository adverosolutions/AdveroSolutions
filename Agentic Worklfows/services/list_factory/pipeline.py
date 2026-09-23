"""The state machine.

    source -> icp -> owner -> patterns -> verify -> finder -> suppression
           -> personalize -> stage

Each stage is a function of (RunState, config) that operates only on the leads
that have not been through it. That is what makes a run resumable: after a
crash, ``RunState.pending(stage)`` is exactly the work left, so a run that died
after paying for 2,000 verifications does not pay for them again.

The ledger is consulted before the source fetch (the preflight's own figure),
inside the owner and verify loops, and at every stage boundary. When the
projected cost per CONFIRMED contact breaks the cap the run halts and makes no
further paid call of any kind: leads already verified AND personalized are
suppression-checked (free) and staged into a separate ``_halted.csv``
(``_salvage_after_halt``), verified leads still without a personalization line
wait for a ``--resume`` with a raised cap, and the Job_Log row says ``halted``.
Spending money with no confirmed contact so far or still to come is over any
cap: it halts in-run and a finished run reports ``over_cap``.
"""
import logging
from typing import Any, Callable, Dict, Optional

from shared import settings
from shared import thresholds as TH

from services.list_factory import contacts, icp, ledger as ledger_mod, models, personalize
from services.list_factory import sources as sources_mod
from services.list_factory import stage_out, state as state_mod
from services.list_factory import suppression as suppression_mod

logger = logging.getLogger("list_factory.pipeline")

STAGE_SOURCE = "source"
STAGE_PRESUPPRESS = "presuppress"
STAGE_ICP = "icp"
STAGE_OWNER = "owner"
STAGE_PATTERNS = "patterns"
STAGE_VERIFY = "verify"
STAGE_SUPPRESSION = "suppression"
STAGE_PERSONALIZE = "personalize"
STAGE_STAGE = "stage"

PIPELINE_STAGES = [
    STAGE_SOURCE, STAGE_PRESUPPRESS, STAGE_ICP, STAGE_OWNER, STAGE_PATTERNS,
    STAGE_VERIFY, STAGE_SUPPRESSION, STAGE_PERSONALIZE, STAGE_STAGE,
]

# Measured September rates, used to work backwards from "3,300 staged contacts"
# to "how many businesses must be sourced". The ledger overrides them with
# observed rates as soon as a run has any; these only size the source pull and
# the preflight estimate.
DEFAULT_RATES = {
    "icp_pass": 0.65,       # share of sourced businesses that survive the rubric
    "owner_rate": 0.80,     # share of those with a usable owner name and domain
    "checks_per_lead": 2.6, # verifications spent before a hit or a give-up
    "verify_rate": 0.50,    # share of those that yield a deliverable mailbox
    # Share of sourced rows that are NOT already suppressed. Measured on the
    # recorded rehearsal: 9 of 37 verified leads were suppressed afterwards,
    # every one of them for "domain already contacted or uploaded" - a reason
    # knowable for free the moment the row arrives. Without this term the plan
    # sized the pull for 3,300 verified and staged about 2,500, and paid to
    # verify roughly 800 leads a week it already knew it would discard. The
    # suppression list only grows (4,269 domains against 3,594 uploaded leads),
    # so re-measure it after every paid run.
    "suppression_survival": 0.76,
    # Share of deliverable results that are CATCH-ALL rather than a confirmed
    # mailbox. Measured: 1,392 of 5,737 recorded plain-pattern checks (24.3%),
    # and 26% in the fixture rehearsal. A catch-all domain accepts every local
    # part at SMTP time, so for an address the factory guessed there is no
    # evidence the mailbox exists. They are staged (Instantly imports them as
    # accept_all) but they are NOT the denominator of the cost KPI.
    "catch_all_share": 0.25,
}

# Share of a source's rows that already carry an owner name, so no Perplexity
# look-up is needed. Apify measured 57 of 58 on the recorded fixture; a Google
# Maps row never carries one. The preflight used to hard-code $0 of owner cost
# for Apify, which is only true at a name rate of exactly 1.0 and understated
# the quote by up to $8.25 at the plan's own 80% owner rate.
SOURCE_NAME_RATES = {"apify": 0.98, "fixture": 0.98, "gmaps": 0.0}
DEFAULT_SOURCE_NAME_RATE = 0.0   # conservative: assume every row needs a look-up


def source_name_rate(source_name: str) -> float:
    return SOURCE_NAME_RATES.get(source_name or "", DEFAULT_SOURCE_NAME_RATE)


def plan_counts(target: int, rates: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """How many businesses a run must source to STAGE ``target`` contacts.

    One function, used by both the preflight estimate and the source stage, so
    the number the estimate priced is the number the run actually fetches.
    """
    merged = dict(DEFAULT_RATES)
    merged.update(rates or {})
    survival = max(0.01, min(1.0, merged.get("suppression_survival", 1.0)))
    per_staged = max(
        0.001,
        merged["icp_pass"] * merged["owner_rate"] * merged["verify_rate"] * survival,
    )
    sourced = int(round(max(0, target) / per_staged))
    survivors = int(round(sourced * survival))
    icp_pass = int(round(survivors * merged["icp_pass"]))
    owners = int(round(icp_pass * merged["owner_rate"]))
    verified = int(round(owners * merged["verify_rate"]))
    return {
        "rates": merged,
        "sourced": sourced,
        "survivors": survivors,
        "icp_pass": icp_pass,
        "owners": owners,
        "checks": int(round(owners * merged["checks_per_lead"])),
        "verified": verified,
        # Of those, the ones MillionVerifier actually confirmed. The rest are
        # guesses on catch-all domains: staged and mailed, but never counted as
        # verified contacts, here or in the ledger.
        "confirmed": int(round(verified * (1.0 - merged.get("catch_all_share", 0.0)))),
        # Suppression now runs BEFORE the paid stages, so everything verified
        # is staged. The two numbers are equal by construction and both are
        # reported so the change of meaning is visible.
        "staged": verified,
    }


class Config(object):
    """Everything a run needs, so the stages take no globals."""

    def __init__(
        self,
        niche,
        campaign_key,
        target=TH.LIST_FACTORY_WEEKLY_TARGET,
        source=None,
        max_cost_per_contact=ledger_mod.DEFAULT_MAX_COST_PER_CONTACT,
        batch_size=icp.DEFAULT_BATCH_SIZE,
        max_escalations=icp.DEFAULT_MAX_ESCALATIONS,
        verifier=None,
        owner_finder=None,
        paid_finder=None,
        personalizer=None,
        instantly=None,
        refresh_suppression=False,
        read_hostile_emails=True,
        suppression_list=None,
        would_do_mode="batch",
        dry_run=False,
        include_catch_all=True,
        suppression_max_age_hours=suppression_mod.DEFAULT_MAX_AGE_HOURS,
        min_staged_share=0.5,
        campaign_targets=None,
    ):
        self.niche = niche
        # [(campaign_key, target), ...] when one source pull feeds several
        # campaigns of this niche (the Sunday --all-campaigns run). The staged
        # leads are handed out in this order, so the first campaign is served
        # first. None means the single campaign_key gets everything.
        self.campaign_targets = [(str(k), int(t)) for k, t in (campaign_targets or [])] or None
        if self.campaign_targets:
            campaign_key = self.campaign_targets[0][0]
            target = sum(t for _k, t in self.campaign_targets)
        self.campaign_key = campaign_key
        self.target = int(target)
        self.source = source
        self.max_cost_per_contact = float(max_cost_per_contact)
        self.batch_size = int(batch_size)
        self.max_escalations = int(max_escalations)
        self.verifier = verifier
        self.owner_finder = owner_finder
        self.paid_finder = paid_finder
        self.personalizer = personalizer
        self.instantly = instantly
        self.refresh_suppression = bool(refresh_suppression)
        self.read_hostile_emails = bool(read_hostile_emails)
        self.suppression_list = suppression_list
        self.would_do_mode = would_do_mode
        self.dry_run = bool(dry_run)
        self.include_catch_all = bool(include_catch_all)
        self.suppression_max_age_hours = suppression_max_age_hours
        self.min_staged_share = float(min_staged_share)
        self.rubric = icp.load_rubric(niche)
        # How many raw businesses this run has to pull to stage ``target``
        # contacts. A fixture source ignores it (it has what it has).
        self.plan = plan_counts(self.target)
        self.source_target = self.plan["sourced"]
        # ONE fill rate, used by the preflight and by the source stage.
        # ``plan_counts`` already carries every attrition term (ICP, owner,
        # verify, suppression), so dividing the pull by the niche's email
        # fill_rate on top over-fetched by 1/0.36 = 2.78x: the preflight quoted
        # 12,693 Apify rows at $25.63 and the run asked for 35,254 at $70.75,
        # which took the same run from $0.0140 to $0.0277 per contact, over the
        # 2-cent cap, on the very number Lorenzo opens the paid gate on.
        self.source_fill_rate = 1.0
        self.source_name_rate = source_name_rate(getattr(self.source, "name", ""))

    def to_meta(self) -> Dict[str, Any]:
        return {
            "niche": self.niche,
            "campaign_key": self.campaign_key,
            "target": self.target,
            "source": getattr(self.source, "name", "none"),
            "verifier": getattr(self.verifier, "name", "millionverifier"),
            "max_cost_per_contact": self.max_cost_per_contact,
            "dry_run": self.dry_run,
            "campaign_targets": [list(pair) for pair in (self.campaign_targets or [])],
        }

    def new_ledger(self, run_id: str) -> ledger_mod.Ledger:
        return ledger_mod.Ledger(
            run_id, self.niche, self.max_cost_per_contact,
            source=getattr(self.source, "name", "none"),
            verifier=getattr(self.verifier, "name", "millionverifier"),
            dry_run=self.dry_run, target=self.target, rates=self.plan["rates"],
        )


# ------------------------------------------------------------------ stages
def _ensure_suppression(cfg: Config) -> "suppression_mod.SuppressionList":
    """The run's suppression list, built read-only once and reused."""
    if cfg.suppression_list is not None:
        return cfg.suppression_list
    if cfg.instantly is None:
        raise suppression_mod.SuppressionError(
            "no Instantly client and no suppression list: the factory cannot prove a lead "
            "has not already been mailed, so it will not stage one."
        )
    cfg.suppression_list = suppression_mod.get(
        cfg.instantly, refresh=cfg.refresh_suppression, read_emails=cfg.read_hostile_emails,
    )
    return cfg.suppression_list


def stage_source(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    if run.stage_done(STAGE_SOURCE):
        return {"skipped": "already sourced", "leads": len(run.leads)}
    # Hard stop BEFORE the fetch: the source is the largest single line of a
    # paid run. Raises BudgetExceeded, which run_pipeline reports as halted.
    _gate_before_source(cfg, led)
    fill_rate = cfg.source_fill_rate
    # cfg.source_target, not cfg.target: the target is staged contacts, and
    # suppression, ICP, owner discovery and verification each take a cut on the
    # way there. Sourcing cfg.target rows lands roughly a fifth of the list
    # that was asked for, and the shortfall only shows up at the end of a
    # four-hour run.
    estimate = cfg.source.estimate_cost(cfg.source_target, fill_rate)
    try:
        fetched = cfg.source.fetch(cfg.niche, cfg.source_target, fill_rate)
    except sources_mod.PaidCallBlocked as exc:
        led.note("source_blocked", str(exc))
        led.note("source_would_have_cost", exc.usd)
        raise
    added = run.add_leads(models.dedupe(fetched))
    # What the source ACTUALLY incurred when it can say (Apify bills per lead
    # returned, so a run whose shards half failed is not billed for rows it
    # never received); the plan estimate otherwise.
    actual = getattr(cfg.source, "last_run_cost", None)
    charged = estimate if actual is None else float(actual)
    led.count("source", added)
    led.spend("source", charged, getattr(cfg.source, "name", "source"), added)
    with_name = sum(1 for lead in run.leads if lead.get("first_name"))
    observed_name_rate = round(float(with_name) / len(run.leads), 4) if run.leads else None
    led.note("source_fill_rate", fill_rate)
    led.note("source_target", cfg.source_target)
    led.note("source_estimated_usd", estimate)
    # Recorded so the owner-cost assumption self-corrects after the first paid
    # run instead of staying a constant in the source code.
    led.note("observed_name_rate", observed_name_rate)
    run.mark_stage_done(STAGE_SOURCE)
    return {
        "fetched": len(fetched), "added": added, "estimated_usd": estimate,
        "charged_usd": round(charged, 6), "fill_rate": fill_rate,
        "source_target": cfg.source_target, "observed_name_rate": observed_name_rate,
    }


def stage_presuppress(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    """The free half of suppression, run before anything is paid for.

    Domain-level only: "this company is already in a campaign" is knowable from
    ``lead['domain']`` the moment the row is sourced, and costs nothing. The
    address-level half still runs after verification, where the candidate
    addresses exist.
    """
    if run.stage_done(STAGE_PRESUPPRESS):
        return {"skipped": "already checked"}
    supp = _ensure_suppression(cfg)
    supp.require_complete(max_age_hours=cfg.suppression_max_age_hours)
    pending = run.pending(models.ICP)
    if not pending:
        run.mark_stage_done(STAGE_PRESUPPRESS)
        return {"skipped": "nothing pending", "suppression": supp.summary()}
    summary = suppression_mod.apply(pending, supp, max_age_hours=cfg.suppression_max_age_hours,
                                    domain_only=True)
    led.note("presuppressed", summary["suppressed"])
    led.note("presuppress_detail", summary)
    led.note("suppression_sources", supp.summary())
    run.mark_stage_done(STAGE_PRESUPPRESS)
    run.checkpoint(force=True)
    return summary


def stage_icp(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    pending = run.pending(models.ICP)
    if not pending:
        run.mark_stage_done(STAGE_ICP)
        return {"skipped": "nothing pending"}
    with led.llm_stage("icp"):
        summary = icp.score(
            pending, cfg.rubric,
            batch_size=cfg.batch_size,
            max_escalations=cfg.max_escalations,
            on_batch=lambda n: run.tick(n),
        )
    passed = 0
    rejected = 0
    for lead in pending:
        if lead.get("icp_verdict") == icp.VERDICT_ACCEPT:
            models.advance(lead, models.ICP, lead.get("icp_decided_by") or "")
            passed += 1
        else:
            models.reject(lead, models.REJECT_ICP, lead.get("icp_reason") or "not a match")
            rejected += 1
    led.count("icp", passed)
    led.note("icp_rejected", rejected)
    led.note("icp_detail", summary)
    run.mark_stage_done(STAGE_ICP)
    run.checkpoint(force=True)
    return dict(summary, passed=passed, rejected=rejected)


def stage_owner(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    pending = run.pending(models.OWNER)
    if not pending:
        run.mark_stage_done(STAGE_OWNER)
        return {"skipped": "nothing pending"}
    remaining = {"n": len(pending)}
    spent_since_check = {"n": 0}

    def on_lookup(n):
        led.spend_units("owner", "perplexity_per_owner_lookup", n)
        run.tick(n)
        remaining["n"] = max(0, remaining["n"] - n)
        spent_since_check["n"] += n
        # The owner stage alone is $41.25 of a $61.84 Google Maps run, so
        # waiting for the stage boundary to check the budget means the money is
        # already gone. Check inside the loop.
        if spent_since_check["n"] >= max(1, cfg.batch_size):
            spent_since_check["n"] = 0
            _check_budget_at(run, cfg, led, STAGE_OWNER, remaining_override=remaining["n"])

    summary = contacts.resolve_owners(
        pending,
        industry=cfg.rubric.get("label") or cfg.niche,
        finder=cfg.owner_finder,
        on_lookup=on_lookup,
    )
    found = summary["from_source"] + summary["found"]
    led.count("owner", found)
    led.note("owner_detail", summary)
    run.mark_stage_done(STAGE_OWNER)
    run.checkpoint(force=True)
    return summary


def stage_patterns(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    pending = run.pending(models.PATTERNS)
    if not pending:
        run.mark_stage_done(STAGE_PATTERNS)
        return {"skipped": "nothing pending"}
    summary = contacts.generate_candidates(pending)
    led.count("patterns", summary["with_candidates"])
    led.note("candidate_addresses", summary["candidates"])
    run.mark_stage_done(STAGE_PATTERNS)
    run.checkpoint(force=True)
    return summary


def stage_verify(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    pending = run.pending(models.VERIFIED)
    if not pending:
        run.mark_stage_done(STAGE_VERIFY)
        return {"skipped": "nothing pending"}
    total = len(pending)
    remaining = {"n": total}
    since_check = {"n": 0}

    def on_checks(n):
        led.spend_units("verify", "millionverifier_per_check", n)
        run.tick(n)
        since_check["n"] += n
        if since_check["n"] >= max(1, cfg.batch_size):
            since_check["n"] = 0
            _check_budget_at(run, cfg, led, STAGE_VERIFY, remaining_override=remaining["n"])

    def on_result(outcome):
        # Counted AS IT HAPPENS, not after verify_leads returns. A crash
        # mid-stage used to persist 100% of the verification cost and 0% of the
        # matching count, and the resumed run then divided the whole bill by
        # the few contacts it bought afterwards, reported roughly 2.5x the true
        # cost per verified contact and halted a run that was inside the cap.
        remaining["n"] = max(0, remaining["n"] - 1)
        if outcome == "valid":
            led.count("verify", 1)
        elif outcome == "catch_all":
            led.count("catch_all", 1)
        elif outcome == "undecided":
            led.note("verify_errors", int(led.detail.get("verify_errors") or 0) + 1)
        if outcome in ("valid", "catch_all", "miss", "undecided"):
            led.note("verify_attempted", int(led.detail.get("verify_attempted") or 0) + 1)
        run.tick(1)

    def on_finder(n):
        # The finder is a stub, so this records what a real one would cost.
        led.note("finder_would_have_cost",
                 round(float(led.detail.get("finder_would_have_cost") or 0.0)
                       + ledger_mod.PRICES["paid_finder_per_find"] * n, 6))
        led.count("finder", n)

    credits = None
    if getattr(cfg.verifier, "name", "millionverifier") == "millionverifier" and sources_mod.paid_calls_allowed():
        # Free, read-only. An empty balance turns every check into an 'error',
        # which used to read as "this mailbox does not exist" and rejected the
        # whole week's list terminally while reporting the run ok.
        credits = contacts.credits_available()
        needed = int(round(total * cfg.plan["rates"]["checks_per_lead"]))
        led.note("millionverifier_credits", credits)
        if credits is not None and credits < needed:
            raise contacts.VerifyStageError(
                "MillionVerifier has %d credits and this stage projects %d checks (%d leads x %.1f). "
                "Refusing to start: a run that exhausts credits mid-stage rejects every remaining "
                "lead as unverifiable." % (credits, needed, total, cfg.plan["rates"]["checks_per_lead"])
            )

    summary = contacts.verify_leads(
        pending, verifier=cfg.verifier, paid_finder=cfg.paid_finder,
        on_checks=on_checks, on_finder=on_finder, on_result=on_result,
        accept_catch_all=True,
    )
    led.note("verify_detail", summary)
    run.mark_stage_done(STAGE_VERIFY)
    run.checkpoint(force=True)
    return dict(summary, credits=credits)


def stage_suppression(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    pending = run.pending(models.SUPPRESSED_CHECK)
    supp = _ensure_suppression(cfg)
    led.note("suppression_sources", supp.summary())
    if not pending:
        supp.require_complete(max_age_hours=cfg.suppression_max_age_hours)
        run.mark_stage_done(STAGE_SUPPRESSION)
        return {"skipped": "nothing pending", "suppression": supp.summary()}
    summary = suppression_mod.apply(pending, supp, max_age_hours=cfg.suppression_max_age_hours)
    led.count("suppression", summary["passed"])
    led.note("suppressed", summary["suppressed"])
    led.note("suppression_detail", summary)
    run.mark_stage_done(STAGE_SUPPRESSION)
    run.checkpoint(force=True)
    return summary


def stage_personalize(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    pending = run.pending(models.PERSONALIZED)
    if not pending:
        run.mark_stage_done(STAGE_PERSONALIZE)
        return {"skipped": "nothing pending"}
    triggers = personalize.tag_triggers(pending, cfg.rubric)
    with led.llm_stage("personalize"):
        summary = personalize.personalize(
            pending,
            # short_label, not label: the fallback line reads "saw you handle
            # <label>", and the long label makes that sentence unsendable.
            niche_label=cfg.rubric.get("short_label") or cfg.rubric.get("label") or cfg.niche,
            generator=cfg.personalizer,
            on_lead=lambda n: run.tick(n),
        )
    led.count("personalize", summary["written"])
    led.note("personalize_detail", summary)
    led.note("trigger_detail", triggers)
    run.mark_stage_done(STAGE_PERSONALIZE)
    run.checkpoint(force=True)
    return dict(summary, triggers=triggers)


def stage_stage(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    csv_path = run.artifact("staged_%s_%s.csv" % (models.slug(cfg.niche), models.slug(cfg.campaign_key)))
    if run.stage_done(STAGE_STAGE):
        # Every other stage had this guard; this one did not. On a resume every
        # lead was already STAGED, so ``pending`` was empty, ``write_csv([])``
        # replaced the week's deliverable with a header row, a second would_do
        # record was emitted, and the run reported ok. The runbook tells the
        # operator to --resume any run that died, so checking whether Sunday's
        # run finished destroyed the list.
        return {
            "skipped": "already staged",
            "csv": csv_path,
            "staged": int(led.counts.get("stage", 0)),
            "rows_on_disk": stage_out.csv_data_rows(csv_path),
        }
    ready = run.pending(models.STAGED)
    if not ready:
        held = len(run.held())
        # Nothing to write. Do NOT emit a would_do record for zero leads, and
        # do not mark the stage done while leads are still held: a pass that
        # was blocked at the owner or verify gate would otherwise close the
        # staging step for good, and the resume that opens the gate would find
        # it already "done" and stage nothing.
        if held:
            return {"skipped": "nothing ready; %d leads are held" % held,
                    "staged": 0, "held": held, "csv": csv_path}
        run.mark_stage_done(STAGE_STAGE)
        return {"skipped": "nothing ready", "staged": 0, "csv": csv_path,
                "rows_on_disk": stage_out.csv_data_rows(csv_path)}
    if cfg.campaign_targets and len(cfg.campaign_targets) > 1:
        summary = _stage_split(run, cfg, ready)
    else:
        summary = stage_out.stage(ready, cfg.campaign_key, csv_path, mode=cfg.would_do_mode,
                                  include_catch_all=cfg.include_catch_all)
    led.count("stage", summary["staged"])
    led.note("stage_detail", summary)
    run.mark_stage_done(STAGE_STAGE)
    run.checkpoint(force=True)
    return summary


def _campaign_offer(campaign_key: str) -> str:
    return ((settings.CAMPAIGNS.get(campaign_key) or {}).get("offer") or "")


def split_for_campaigns(leads, campaign_targets, include_catch_all=True):
    """Hand staged-ready leads out to several campaigns of one niche.

    In order, each campaign up to its target; anything left over goes to the
    FIRST campaign, which is the one the run order says to scale first. A lead
    goes to exactly one campaign. Where a lead's ``b_variant_eligible`` flag
    matters (a trigger campaign's B copy interpolates the trigger variables),
    trigger campaigns take eligible leads first and reactivation campaigns take
    the rest first, so a reactivation campaign never uses up the leads the
    trigger B copy can actually be sent to.
    """
    pool = [lead for lead in leads
            if not models.is_rejected(lead) and lead.get("email") and lead.get("personalization")
            and (include_catch_all or not lead.get("verify_catch_all"))]
    out = dict((key, []) for key, _t in campaign_targets)
    for key, target in campaign_targets:
        want_eligible = _campaign_offer(key) != "reactivation"
        pool.sort(key=lambda lead: 0 if bool(lead.get("b_variant_eligible")) == want_eligible else 1)
        take = pool[:max(0, int(target))]
        pool = pool[len(take):]
        out[key].extend(take)
    if pool and campaign_targets:
        out[campaign_targets[0][0]].extend(pool)
    return out


def _stage_split(run, cfg, ready):
    allocation = split_for_campaigns(ready, cfg.campaign_targets, cfg.include_catch_all)
    per_campaign = {}
    staged = 0
    records = 0
    shadow = True
    for key, target in cfg.campaign_targets:
        leads = allocation.get(key) or []
        csv_path = run.artifact("staged_%s_%s.csv" % (models.slug(cfg.niche), models.slug(key)))
        if not leads:
            per_campaign[key] = {"campaign_key": key, "target": target, "staged": 0, "csv": None,
                                 "note": "nothing left for this campaign after the ones before it"}
            continue
        result = stage_out.stage(leads, key, csv_path, mode=cfg.would_do_mode,
                                 include_catch_all=cfg.include_catch_all)
        result["target"] = target
        per_campaign[key] = result
        staged += result["staged"]
        records += result.get("would_do_records", 0)
        shadow = shadow and bool(result.get("shadow", True))
    return {
        "campaign_key": cfg.campaign_key,
        "staged": staged,
        "csv": (per_campaign.get(cfg.campaign_key) or {}).get("csv"),
        "campaigns": per_campaign,
        "would_do_records": records,
        "shadow": shadow,
        "b_variant_eligible": sum(int(r.get("b_variant_eligible") or 0) for r in per_campaign.values()),
    }


STAGE_FUNCS = [
    (STAGE_SOURCE, stage_source),
    (STAGE_PRESUPPRESS, stage_presuppress),
    (STAGE_ICP, stage_icp),
    (STAGE_OWNER, stage_owner),
    (STAGE_PATTERNS, stage_patterns),
    (STAGE_VERIFY, stage_verify),
    (STAGE_SUPPRESSION, stage_suppression),
    (STAGE_PERSONALIZE, stage_personalize),
    (STAGE_STAGE, stage_stage),
]

def _personalize_usd_per_lead() -> float:
    from shared import llm

    return llm.estimate_cost(llm.model_for("research"),
                             personalize.TOKENS_IN_PER_LEAD, personalize.TOKENS_OUT_PER_LEAD)


def _icp_usd_per_business() -> float:
    from shared import llm

    return llm.estimate_cost(llm.model_for("classify"),
                             icp.TOKENS_IN_PER_BUSINESS, icp.TOKENS_OUT_PER_BUSINESS)


def _projection_rates(cfg: Config, led: ledger_mod.Ledger) -> Dict[str, float]:
    """The per-lead rates the projection runs on.

    The deliverable and confirmed rates are the run's OBSERVED ones once it has
    verified anything, and the plan's otherwise. Confirmed is deliverable with
    the catch-all share taken out: it is the cost-KPI denominator, the same one
    ``Ledger.cost_per_verified`` and ``preflight`` divide by.
    """
    rates = cfg.plan["rates"]
    planned_deliverable = float(rates.get("verify_rate", 0.5))
    planned_confirmed = planned_deliverable * (1.0 - float(rates.get("catch_all_share", 0.0)))
    observed_deliverable = led.observed_verify_rate()
    observed_confirmed = led.observed_confirmed_rate()
    return {
        "suppression_survival": float(rates.get("suppression_survival", 1.0)),
        "icp_pass": float(rates.get("icp_pass", 1.0)),
        "owner_rate": float(rates.get("owner_rate", 1.0)),
        "checks_per_lead": float(rates.get("checks_per_lead", 2.6)),
        "deliverable": planned_deliverable if observed_deliverable is None else observed_deliverable,
        "confirmed": planned_confirmed if observed_confirmed is None else observed_confirmed,
        "name_rate": float(cfg.source_name_rate),
        "rate_source": "planned" if observed_confirmed is None else "observed",
    }


def project_run(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    """Money still to spend and CONFIRMED contacts still to come, from the run state.

    Every live lead is priced from where it actually stands, with the same
    attrition terms the preflight uses, so the in-run projection and the
    preflight agree by construction:

    * sourced, not yet through the free domain suppression: x suppression_survival
    * sourced: ICP call, then x icp_pass
    * past ICP, no owner yet: a Perplexity look-up when the row has no name
      (the preflight's name rate before ICP, the row itself after), then x owner_rate
    * with an owner, not yet verified: checks_per_lead MillionVerifier checks
    * verified, not yet personalized: one personalization call per DELIVERABLE
      (catch-alls are personalized and staged too, they are just not counted)

    The old boundary projection divided by deliverables (catch-alls included)
    and ignored suppression at the source boundary, so on the documented Apify
    run it read $0.0161 while the preflight said $0.0222, and the run spent all
    $55.05 before it halted. Held and rejected leads cost nothing further.
    """
    r = _projection_rates(cfg, led)
    mv = ledger_mod.PRICES["millionverifier_per_check"]
    lookup = ledger_mod.PRICES["perplexity_per_owner_lookup"]
    pers = _personalize_usd_per_lead()
    icp_usd = _icp_usd_per_business()
    presuppressed = run.stage_done(STAGE_PRESUPPRESS)
    survival_ahead = 1.0 if presuppressed else r["suppression_survival"]

    # Per-lead future cost and confirmed yield once a lead has an owner.
    after_owner_usd = r["checks_per_lead"] * mv + r["deliverable"] * pers
    after_owner_yield = r["confirmed"]

    future = 0.0
    expected = 0.0
    counts = {"to_icp": 0, "to_owner": 0, "to_verify": 0, "to_personalize": 0}
    for lead in run.leads:
        if models.is_rejected(lead) or models.is_held(lead):
            continue
        stage = lead.get("stage") or models.SOURCED
        if stage == models.STAGED:
            continue
        if not models.stage_at_least(lead, models.ICP):
            counts["to_icp"] += 1
            per = (icp_usd
                   + r["icp_pass"] * (1.0 - r["name_rate"]) * lookup
                   + r["icp_pass"] * r["owner_rate"] * after_owner_usd)
            future += survival_ahead * per
            expected += survival_ahead * r["icp_pass"] * r["owner_rate"] * after_owner_yield
        elif not models.stage_at_least(lead, models.OWNER):
            counts["to_owner"] += 1
            per = (0.0 if lead.get("first_name") else lookup) + r["owner_rate"] * after_owner_usd
            future += per
            expected += r["owner_rate"] * after_owner_yield
        elif not models.stage_at_least(lead, models.VERIFIED):
            counts["to_verify"] += 1
            future += after_owner_usd
            expected += after_owner_yield
        elif not models.stage_at_least(lead, models.PERSONALIZED):
            counts["to_personalize"] += 1
            future += pers
    return {
        "future_usd": round(future, 6),
        "expected_new_confirmed": round(expected, 4),
        "counts": counts,
        "rates": r,
    }


def _check_budget_at(run, cfg, led, stage, remaining_override=None):
    """Stage-boundary and in-loop hard stop, projected from the run state.

    ``remaining_override`` is accepted for backwards compatibility and ignored:
    the leads themselves say what is left, and the in-loop callers mutate them
    as they go.
    """
    proj = project_run(run, cfg, led)
    if proj["expected_new_confirmed"] <= 0 and led.verified_count() <= 0:
        # The unbounded case ("no confirmed contact so far or to come") is only
        # true when the run state agrees:
        # * leads held by a closed paid gate (or an unanswered verifier) come
        #   back on the resume that opens the gate; the run reports ``blocked``;
        # * confirmed leads already in the state (a resume whose ledger was not
        #   carried over) are confirmed contacts the ledger has not counted.
        confirmed_in_state = sum(1 for lead in run.leads
                                 if not models.is_rejected(lead)
                                 and models.stage_at_least(lead, models.VERIFIED)
                                 and not lead.get("verify_catch_all"))
        if run.held() or confirmed_in_state:
            return
    led.check_projection(
        proj["future_usd"], proj["expected_new_confirmed"], where=stage,
        detail="$%.4f still to spend for %.0f more confirmed; %s rates; pending %s"
               % (proj["future_usd"], proj["expected_new_confirmed"], proj["rates"]["rate_source"],
                  ", ".join("%s=%d" % kv for kv in sorted(proj["counts"].items()))),
    )


def _gate_before_source(cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    """The preflight's own projection, enforced before a cent goes to the source.

    Apify is about 61% of a documented run's bill, so a cap that is first
    consulted after the fetch is consulted after most of the money is gone. The
    figure is the preflight's, so ``--preflight`` saying OVER CAP and a
    ``--now`` run halting here are the same statement.
    """
    pf = preflight(cfg)
    total = float((pf.get("usd") or {}).get("total") or 0.0)
    confirmed = float((pf.get("projected") or {}).get("confirmed") or 0)
    led.note("preflight_gate", {"usd_total": total, "confirmed": confirmed,
                                "cost_per_verified": pf.get("cost_per_verified")})
    led.check_projection(
        total, confirmed, where="before the source fetch",
        detail="the preflight prices this run at $%.2f for %d confirmed contacts; nothing was fetched"
               % (total, int(confirmed)),
    )
    return pf


def run_pipeline(
    run: "state_mod.RunState",
    cfg: Config,
    led: Optional[ledger_mod.Ledger] = None,
    on_stage: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Run every stage that is not already done. Returns the run summary."""
    led = led or cfg.new_ledger(run.run_id)
    # The ledger now rides along with every checkpoint, so a kill -9 mid-stage
    # still leaves the spend in state.json and a resume inherits it.
    run.bind_ledger(led)
    released = run.release_holds()
    if released:
        logger.info("released %d leads held by a closed gate on the previous pass", released)
    last = led.detail.get("last_projection") or {}
    if last.get("unbounded") and not led.halted:
        # The previous pass halted on "no confirmed contact". Re-test on a
        # fresh sample instead of re-halting at the first boundary on the rate
        # it saved: until MIN_OBSERVED_SAMPLE_LEADS new leads are verified the
        # projection runs on the plan's rates again. (Before this, a resume
        # re-halted at the source boundary whatever the cap, and the pull was
        # wasted.)
        led.restart_rate_sample("resume after the no-confirmed-contact halt at %s" % last.get("where"))
        led.note("last_projection", dict(last, unbounded=False, retested_on_resume=True))
    stages = {}  # type: Dict[str, Any]
    status = "ok"
    error = ""
    for name, func in STAGE_FUNCS:
        try:
            result = func(run, cfg, led)
        except ledger_mod.BudgetExceeded as exc:
            stages[name] = {"halted": exc.snapshot["halt_reason"]}
            status = "halted"
            error = exc.snapshot["halt_reason"]
            stages["salvage"] = _salvage_after_halt(run, cfg, led)
            break
        except sources_mod.PaidCallBlocked as exc:
            stages[name] = {"blocked": str(exc), "would_have_cost_usd": exc.usd}
            status = "blocked"
            error = str(exc)
            break
        except suppression_mod.SuppressionError as exc:
            stages[name] = {"error": str(exc)}
            status = "refused"
            error = str(exc)
            break
        except (sources_mod.SourceError, contacts.VerifyStageError) as exc:
            stages[name] = {"error": str(exc)}
            status = "error"
            error = "%s: %s" % (name, exc)
            break
        except Exception as exc:  # noqa: BLE001 - one stage failing must not lose the run
            logger.exception("stage %s failed", name)
            stages[name] = {"error": str(exc)}
            status = "error"
            error = "%s: %s" % (name, exc)
            break
        stages[name] = result
        if on_stage is not None:
            on_stage(name, result)
        if name == STAGE_STAGE:
            # Nothing is left to spend after staging, so there is nothing to
            # halt. A finished run that came in over the cap is reported as
            # over_cap below rather than as "halted", which would tell Lorenzo
            # to resume a run that has nothing left to do.
            break
        try:
            _check_budget_at(run, cfg, led, name)
        except ledger_mod.BudgetExceeded as exc:
            stages[name] = dict(result, halted=exc.snapshot["halt_reason"])
            status = "halted"
            error = exc.snapshot["halt_reason"]
            stages["salvage"] = _salvage_after_halt(run, cfg, led)
            break

    staged = int(led.counts.get("stage", 0))
    blocked = sum(int(r.get("blocked") or 0) for r in stages.values()
                  if isinstance(r, dict) and isinstance(r.get("blocked"), int))
    held = len(run.held())
    if status == "ok" and (blocked or held):
        # The runbook promised status: blocked when a paid call was refused,
        # and that was only ever true for the source stage. A run whose owner
        # or verify stage was blocked per-lead reported ok with nothing staged.
        status = "blocked"
        error = error or ("%d leads were held by a closed paid gate or an unanswered verifier"
                          % (held or blocked))
    unbounded = led.cost_per_verified() is None and led.total() > 0
    if status == "ok" and (unbounded or led.verdict() in ("over_cap", "alert")):
        status = "over_cap"
        if unbounded:
            # Spent money and confirmed nobody: over any cap, never "ok".
            error = ("spent $%.4f and confirmed no contact (%d catch-all), so the cost per verified "
                     "contact is unbounded, over the $%.4f cap"
                     % (led.total(), led.catch_all_count(), cfg.max_cost_per_contact))
        else:
            error = _over_line_message(led.cost_per_verified() or 0.0, cfg.max_cost_per_contact)
    if status == "ok" and _is_short(cfg, staged):
        # A run that produced nothing (empty source, every shard failed, every
        # lead blocked) used to be indistinguishable from success: ok, exit 0,
        # no push. Blueprint Section 6 asks for >= 5 days of uncontacted leads
        # per campaign; a silent Sunday miss is found on Thursday.
        status = "short"
        error = "staged %d of a target of %d" % (staged, cfg.target)

    run.meta["ledger"] = led.snapshot()
    run.close(status)
    return {
        "run_id": run.run_id,
        "niche": cfg.niche,
        "campaign_key": cfg.campaign_key,
        "target": cfg.target,
        "staged": staged,
        "held": held,
        "status": status,
        "error": error,
        "stages": stages,
        "counts": run.counts(),
        "ledger": led.snapshot(),
        "suppression": (cfg.suppression_list.summary() if cfg.suppression_list is not None else {}),
        "mode": settings.get_mode(),
        "live": settings.is_live(),
        "dry_run": cfg.dry_run,
    }


def _salvage_after_halt(run: "state_mod.RunState", cfg: Config, led: ledger_mod.Ledger) -> Dict[str, Any]:
    """Stage what is already verified AND personalized when the cap halts a run.

    The halt is the cap refusing further spend, so this makes NO paid call of
    any kind: no source, owner, verification or personalization money. It used
    to personalize the verified leads after the halt, and a run the cap stopped
    on "$30 still to spend" then made 30 paid personalizer calls and finished at
    $1.00 per contact while reporting "halted" (MKT-1 re-review). What it does:

    * the address-level suppression check on verified leads (free: it reads
      the suppression list the run already holds, and it is never skipped);
    * stages the leads that are verified, suppression-checked and already
      personalized into a SEPARATE CSV, ``staged_<niche>_<campaign>_halted.csv``,
      so a later ``--resume`` writing the main CSV can never overwrite it;
    * counts the verified leads still waiting for their personalization line
      and says so. They are not staged without one (the copy interpolates it).
      Paying for those lines needs explicit authorization: ``--resume <run_id>``
      with a raised ``--max-cost-per-contact``.

    The ``stage`` step is not marked done, so that resume finishes the list.
    """
    out = {"verified_waiting": 0, "suppressed": 0, "personalized": 0, "staged": 0, "csv": None,
           "awaiting_personalization": 0, "paid_calls": 0}
    try:
        verified = [lead for lead in run.leads
                    if not models.is_rejected(lead) and not models.is_held(lead)
                    and models.stage_at_least(lead, models.VERIFIED)
                    and not models.stage_at_least(lead, models.STAGED)]
        out["verified_waiting"] = len(verified)
        if not verified:
            out["note"] = "nothing had been verified when the run halted; nothing to stage"
            return out
        to_check = [lead for lead in verified if not models.stage_at_least(lead, models.SUPPRESSED_CHECK)]
        if to_check:
            supp = _ensure_suppression(cfg)
            summary = suppression_mod.apply(to_check, supp, max_age_hours=cfg.suppression_max_age_hours)
            out["suppressed"] = int(summary.get("suppressed") or 0)
            led.note("suppressed", int(led.detail.get("suppressed") or 0) + out["suppressed"])
        waiting = [lead for lead in verified if not models.is_rejected(lead)
                   and not models.stage_at_least(lead, models.PERSONALIZED)]
        out["awaiting_personalization"] = len(waiting)
        ready = [lead for lead in verified if not models.is_rejected(lead)
                 and models.stage_at_least(lead, models.PERSONALIZED)
                 and not models.stage_at_least(lead, models.STAGED)]
        if waiting:
            out["note"] = ("%d verified lead(s) have no personalization line yet and were NOT staged: "
                           "writing them costs money the cap refused. Resume with a raised "
                           "--max-cost-per-contact to pay for them" % len(waiting))
        if not ready:
            out["note"] = out.get("note") or "no verified lead survived suppression"
            led.note("salvage_detail", out)
            run.checkpoint(force=True)
            return out
        if cfg.campaign_targets and len(cfg.campaign_targets) > 1:
            allocation = split_for_campaigns(ready, cfg.campaign_targets, cfg.include_catch_all)
        else:
            allocation = {cfg.campaign_key: ready}
        out["campaigns"] = {}
        out["would_do_records"] = 0
        for key, leads in allocation.items():
            if not leads:
                continue
            csv_path = run.artifact("staged_%s_%s_halted.csv" % (models.slug(cfg.niche), models.slug(key)))
            summary = stage_out.stage(leads, key, csv_path, mode=cfg.would_do_mode,
                                      include_catch_all=cfg.include_catch_all)
            out["campaigns"][key] = {"staged": summary["staged"], "csv": csv_path}
            out["staged"] += summary["staged"]
            out["would_do_records"] += int(summary.get("would_do_records") or 0)
            if out["csv"] is None:
                out["csv"] = csv_path
        led.count("stage", out["staged"])
        led.note("salvage_detail", out)
        run.checkpoint(force=True)
    except Exception as exc:  # noqa: BLE001 - the halt must still be reported
        logger.exception("staging the verified leads after a halt failed")
        out["error"] = str(exc)
    return out


def _over_line_message(cpv: float, cap: float) -> str:
    """Name the line a finished run actually crossed.

    It used to say "over the $1000.0000 cap (verdict alert)" for a run with a
    $1,000 cap that had crossed Section 6's $0.04 alert line, naming a line it
    was nowhere near.
    """
    alert = ledger_mod.ALERT_COST_PER_CONTACT
    crossed = []
    if cpv > cap:
        crossed.append("the run's $%.4f cap" % cap)
    if cpv > alert:
        crossed.append("Section 6's $%.2f alert line" % alert)
    text = "finished at $%.5f per verified contact, over %s" % (cpv, " and ".join(crossed) or "no line")
    if cpv > alert and cpv <= cap:
        text += " (inside the run's own $%.4f cap, which was set above the alert line)" % cap
    return text


def _is_short(cfg: Config, staged: int) -> bool:
    """A fixture replay has what the file has, so it is never 'short'."""
    if getattr(cfg.source, "name", "") == "fixture":
        return staged <= 0
    floor = max(1, int(round(cfg.min_staged_share * cfg.target)))
    return staged < floor


def preflight(cfg: Config, expected: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Price the run before it starts, from the measured pass rates.

    Token counts are per-lead averages measured on the fixture rehearsal: about
    140 input and 25 output tokens of an ICP batch call per business, and about
    700 input / 70 output for one personalization line. Priced through
    ``shared.llm.estimate_cost`` so a model price change lands here too.
    """
    from shared import llm

    plan = plan_counts(cfg.target, expected)
    sourced, survivors = plan["sourced"], plan["survivors"]
    icp_pass, checks, verified = plan["icp_pass"], plan["checks"], plan["verified"]

    # The SAME (target, fill_rate) pair ``stage_source`` will pass. Previously
    # the preflight priced fill_rate=1.0 while the run over-fetched by
    # 1/niche_fill_rate, so the quote Lorenzo authorises the first paid Sunday
    # run on understated the bill by 2.78x on cleaning.
    fill_rate = cfg.source_fill_rate
    source_usd = cfg.source.estimate_cost(sourced, fill_rate) if cfg.source is not None else 0.0
    # Owner look-ups cost for every row that arrives WITHOUT a name, whatever
    # the source. Hard-coding $0 for Apify was only true at a name rate of
    # exactly 1.0; the recorded fixture is 57 of 58, and the plan's own
    # owner_rate of 0.80 says 20% of ICP survivors yield no owner at all.
    lookups = int(round(icp_pass * max(0.0, 1.0 - cfg.source_name_rate)))
    owner_usd = lookups * ledger_mod.PRICES["perplexity_per_owner_lookup"]
    verify_usd = checks * ledger_mod.PRICES["millionverifier_per_check"]
    # ICP only scores what survived the free domain-suppression pass.
    icp_usd = llm.estimate_cost(llm.model_for("classify"),
                                icp.TOKENS_IN_PER_BUSINESS * survivors,
                                icp.TOKENS_OUT_PER_BUSINESS * survivors)
    personalize_usd = llm.estimate_cost(llm.model_for("research"),
                                        personalize.TOKENS_IN_PER_LEAD * verified,
                                        personalize.TOKENS_OUT_PER_LEAD * verified)

    total = round(source_usd + owner_usd + verify_usd + icp_usd + personalize_usd, 4)
    confirmed = plan["confirmed"]
    # The headline divides by CONFIRMED mailboxes, the same denominator
    # Ledger.cost_per_verified uses, so the preflight's verdict and the run's
    # verdict can never disagree. Dividing by deliverables instead reported
    # $0.0167 where the run then reported $0.0222 and graded itself over_cap.
    cpv = round(total / max(1, confirmed), 6)
    cpd = round(total / max(1, verified), 6)
    return {
        "target_verified": cfg.target,
        "assumed_rates": plan["rates"],
        "source": getattr(cfg.source, "name", "none"),
        "source_fill_rate": fill_rate,
        "source_name_rate": cfg.source_name_rate,
        "niche_email_fill_rate": sources_mod.niche_fill_rate(cfg.niche),
        "projected": {
            "sourced": sourced, "survivors": survivors, "icp_pass": icp_pass,
            "owners": plan["owners"], "owner_lookups": lookups,
            "checks": checks, "verified": verified, "confirmed": confirmed,
            "staged": plan["staged"],
        },
        "usd": {
            "source": round(source_usd, 4), "icp": round(icp_usd, 4),
            "owner": round(owner_usd, 4), "verify": round(verify_usd, 4),
            "personalize": round(personalize_usd, 4), "total": total,
        },
        "cost_per_verified": cpv,
        "cost_per_deliverable": cpd,
        "cap": cfg.max_cost_per_contact,
        "within_cap": cpv <= cfg.max_cost_per_contact,
    }
