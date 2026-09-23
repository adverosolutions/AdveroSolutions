"""O8 - the Sunday list factory (Blueprint M5).

    python3 jobs/list_factory.py --preflight --niche cleaning --target 3300 --source apify
    python3 jobs/list_factory.py --dry-run --fixtures
    python3 jobs/list_factory.py --now --fixtures --verify replay --campaign cleaning_trigger
    python3 jobs/list_factory.py --now --all-campaigns --refresh-suppression    # the Sunday run
    python3 jobs/list_factory.py --resume cleaning_20260922_004500 --now    # keeps the run's split, target, sources
    python3 jobs/list_factory.py --attribution --dry-run
    python3 jobs/list_factory.py --runs

Produces verified, ICP-scored, personalized leads staged as a CSV plus one
``POST /leads`` intent per campaign. **It uploads nothing.** Every write goes
through ``shared.settings.guard_write``; in shadow that is a record in
``.tmp/shadow_log.jsonl`` and no HTTP request.

``--all-campaigns`` feeds every enabled campaign in
``config/list_factory_targets.json`` (one entry per campaign in
config/ids.json, Cleaning Reactivation first; owner decision R10), one source
pull per niche split between that niche's campaigns. Disabled entries are
printed and logged with their reason on every run.

Paid calls (Apify, Perplexity, MillionVerifier, a paid finder, and this job's
own Anthropic calls for ICP scoring and personalization) are gated by
``ALLOW_PAID_CALLS=1`` ALONE (owner decision R7). Live mode is NOT required: a
shadow run with the flag set spends real money and still uploads nothing. The
flag does NOT stop Anthropic spend anywhere else: the reply engine,
``precall_tick.py`` and ``retro_packet.py`` bill Anthropic through
``shared/llm.py``, gated only by ``LLM_FAKE`` and the ceiling in
``config/llm_budget.json``. Without the flag this job holds every paid call and
the ledger reports what it would have cost.

``--now`` never falls back to the recorded fixture or the replay verifier: it
takes its source and verifier from ``--source``/``--verify``, from
``--fixtures`` (a rehearsal), or from the targets file with ``--all-campaigns``.
The old defaults made the scheduled Sunday run raise before it started. A
``--dry-run`` never takes a paid source from the targets file: fixture and
replay unless paid ones are named on the command line. It always starts a
fresh run whose state and logs live in its scratch directory, never picks up
an open run and refuses ``--resume``.

``--resume <run id>`` continues a run with the niche, campaign split, target,
source and verifier stored in its state file; a flag naming something else is
refused. A niche pull of an --all-campaigns run is resumed this way, on its own.
After a cap halt nothing more is paid for until such a resume raises
``--max-cost-per-contact``.

Writes one Job_Log row per run and notifies Lorenzo (high priority) on anything
that is not ``ok``, including a crash, an argument error and a refused start.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.settings import TZ  # noqa: E402

from services.list_factory import contacts, icp, ledger as ledger_mod  # noqa: E402
from services.list_factory import pipeline as pipeline_mod  # noqa: E402
from services.list_factory import sources as sources_mod  # noqa: E402
from services.list_factory import state as state_mod  # noqa: E402
from services.list_factory import suppression as suppression_mod  # noqa: E402
from services.list_factory import targets as targets_mod  # noqa: E402

# The --all-campaigns (Sunday) outcome when every pull stopped at its first
# paid call because paid calls are off: designed, exit 0. The marker line is
# what changesets/schedules/laptop_runner.py reads to record it as such.
PAID_CALLS_OFF = "paid_calls_off"
OUTCOME_MARKER = "ADVERO_OUTCOME="

logger = logging.getLogger("jobs.list_factory")

JOB = "list_factory"

DEFAULT_FIXTURE = os.path.join(
    HERE, "services", "list_factory", "fixtures", "source_cleaning_50.json",
)

# niche -> the campaign a single-niche run (--niche without --campaign) stages
# for. This is only the default of a hand-run command. The Sunday run is
# --all-campaigns, which feeds every campaign in config/list_factory_targets.json: the
# reactivation campaigns are cold campaigns to sourced businesses too (the
# comment that used to sit here said otherwise, and O8 fed only cleaning_trigger).
DEFAULT_CAMPAIGN = {
    "cleaning": "cleaning_trigger",
    "bookkeeping": "bookkeeping_trigger",
    "recruiting": "recruiting_outbound",
}


def _instantly(offline: bool):
    if offline:
        return None
    try:
        from shared.instantly import default_client
        return default_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Instantly client unavailable (%s)", exc)
        return None


def _max_suppression_age(args):
    """None disables the age check; --allow-stale-suppression is the only way."""
    if getattr(args, "allow_stale_suppression", False):
        return None
    return suppression_mod.DEFAULT_MAX_AGE_HOURS


def _suppression_for(args):
    """The list an offline run uses, or None to let the pipeline build one.

    ``--refresh-suppression`` WINS over ``--suppression``: the two were not
    mutually exclusive and the saved file silently took precedence, so asking
    for a rebuild alongside a file was a no-op.

    A saved file is checked for age here, not only at staging time, so a run
    that is going to be refused is refused before it spends anything.
    ``built_utc`` used to be stored and never read: a 16-week-old list passed
    the fail-closed check exactly like a fresh one and staged 9 leads whose
    domains were already in a campaign.
    """
    shared = getattr(args, "_shared_suppression", None)
    if shared is not None:
        # Built (and checked) by the previous niche of this --all-campaigns run.
        shared.require_complete(max_age_hours=_max_suppression_age(args))
        return shared
    path = getattr(args, "suppression", None)
    if path and args.refresh_suppression:
        logger.warning("--refresh-suppression overrides --suppression %s", path)
        path = None
    if path:
        supp = suppression_mod.load_cached(path)
        if supp is None:
            raise SystemExit("could not read the suppression list at %s" % path)
        supp.require_complete(max_age_hours=_max_suppression_age(args))
        return supp
    if args.offline:
        supp = suppression_mod.load_cached()
        if supp is not None:
            supp.require_complete(max_age_hours=_max_suppression_age(args))
        return supp
    return None


class UsageError(Exception):
    """The run was asked for in a way it must refuse (logged and pushed)."""


def resolve_source_and_verifier(args, group: Optional[Dict[str, Any]] = None):
    """(source name, verifier name) for this run, or UsageError.

    ``--now`` has NO fallback to the recorded fixture or the replay verifier.
    Those used to be the argparse defaults, so the scheduled
    ``--now --niche cleaning`` raised ``source=fixture needs --fixture <path>``
    every Sunday, before anything was logged or pushed. A rehearsal still gets
    them by asking: ``--fixtures`` (which implies ``--verify replay``), or
    ``--source fixture --fixture X --verify replay``. ``--dry-run`` and
    ``--preflight`` keep the free defaults because neither can stage a list.

    A ``--dry-run`` never takes a PAID source or verifier from the targets file
    or a resumed run's meta: ``--dry-run --all-campaigns`` used to resolve to
    Apify and MillionVerifier because the file names them. It uses the fixture
    and the replay unless the paid ones are named on the command line.
    ``--preflight`` still reads them from the group, because pricing the real
    run is its whole job and it makes no call.
    """
    source = "fixture" if getattr(args, "fixtures", False) else (getattr(args, "source", None) or "")
    verify = getattr(args, "verify", None) or ""
    if group is not None and not getattr(args, "dry_run", False):
        source = source or group.get("source") or ""
        verify = verify or group.get("verify") or ""
    rehearsal = bool(getattr(args, "dry_run", False) or getattr(args, "preflight", False))
    if not source and rehearsal:
        source = "fixture"
    if not verify and (rehearsal or getattr(args, "fixtures", False)):
        verify = "replay"
    missing = [flag for flag, value in (("--source", source), ("--verify", verify)) if not value]
    if missing:
        raise UsageError(
            "--now needs %s. The old defaults were the recorded fixture and the replay verifier, "
            "so the scheduled run failed every Sunday. Name them (the Sunday run is "
            "--now --all-campaigns, which takes them from config/list_factory_targets.json; "
            "a real single-niche run is --source apify --verify millionverifier; a rehearsal is "
            "--fixtures --verify replay)." % " and ".join(missing))
    return source, verify


def _verifier_for(verify_name: str, args):
    """MillionVerifier, or the offline replay.

    ``replay`` spends nothing and draws each answer from the recorded outcome
    distribution. It is the right choice for a rehearsal and the wrong one for
    a real list, so the run summary and every staged row say which was used
    (``advero_verify_status`` and the lead's ``verify_source``).
    """
    if verify_name == "replay":
        return contacts.ReplayVerifier(ok_multiplier=args.replay_ok_multiplier)
    return None  # the real MillionVerifier client, behind ALLOW_PAID_CALLS=1


def build_config(args, instantly, group: Optional[Dict[str, Any]] = None) -> pipeline_mod.Config:
    """One pipeline Config. ``group`` is a niche group from
    ``services.list_factory.targets.niche_groups`` (the --all-campaigns run)."""
    campaign_targets = None
    target = args.target
    if group is not None:
        niche = group["niche"]
        campaign_targets = [tuple(pair) for pair in (group.get("campaigns") or [])] or None
        campaign_key = campaign_targets[0][0] if campaign_targets else group.get("campaign_key")
        if group.get("target") is not None:
            target = int(group["target"])
    else:
        niche = args.niche
        campaign_key = args.campaign or DEFAULT_CAMPAIGN.get(niche)
    if not campaign_key:
        raise SystemExit("no default campaign for niche %r; pass --campaign" % niche)
    for key in [k for k, _t in (campaign_targets or [(campaign_key, 0)])]:
        if key not in settings.CAMPAIGNS:
            # Validated HERE, before the run id exists and before a single paid
            # stage runs. The check used to live in stage_out.stage, at the end:
            # `--campaign cleaning_triger` (one missing g) sourced, scored,
            # discovered, verified and personalized the whole list and only then
            # failed, having spent the entire run's budget on a list it could not
            # stage.
            raise SystemExit(
                "unknown campaign key %r; config/ids.json knows %s"
                % (key, ", ".join(sorted(settings.CAMPAIGNS)))
            )
    source_name, verify_name = resolve_source_and_verifier(args, group)
    if source_name == "fixture":
        source = sources_mod.FixtureSource(args.fixture or DEFAULT_FIXTURE)
    else:
        source = sources_mod.build(source_name, fixture=args.fixture, metros=args.metros)
    return pipeline_mod.Config(
        niche=niche,
        campaign_key=campaign_key,
        target=target,
        source=source,
        max_cost_per_contact=args.max_cost_per_contact,
        batch_size=args.batch_size,
        max_escalations=args.max_escalations,
        verifier=_verifier_for(verify_name, args),
        instantly=instantly,
        refresh_suppression=args.refresh_suppression,
        read_hostile_emails=not args.skip_hostile_scan,
        suppression_list=_suppression_for(args),
        would_do_mode=args.would_do,
        dry_run=args.dry_run,
        include_catch_all=(args.catch_all == "include"),
        suppression_max_age_hours=_max_suppression_age(args),
        campaign_targets=campaign_targets,
    )


def resume_group(args, run_id: str, meta: Dict[str, Any],
                 asked: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The niche, campaign split, target, source and verifier a resumed run was
    started with, as a group for ``build_config``. UsageError on a conflict.

    A flag that names something different from the stored run is refused
    rather than obeyed or ignored: obeying it re-targets half a run, and
    ignoring it silently runs something other than what was typed.
    ``asked`` is the group an --all-campaigns run wanted for this niche when it
    found the run open.
    """
    stored_targets = [tuple(pair) for pair in (meta.get("campaign_targets") or [])]
    # Only a source or verifier this job can build is carried over. A test
    # fake's name ("fake-mv") is not one, and resolving an unknown verifier
    # name would silently fall through to the real, paid MillionVerifier.
    stored_source = meta.get("source") if meta.get("source") in ("fixture", "apify", "gmaps") else None
    stored_verify = meta.get("verifier") if meta.get("verifier") in ("replay", "millionverifier") else None
    stored = {
        "niche": meta.get("niche") or args.niche,
        "campaign_key": meta.get("campaign_key"),
        "target": meta.get("target"),
        "campaigns": stored_targets,
        "source": stored_source,
        "verify": stored_verify,
    }
    conflicts = []
    if getattr(args, "_niche_explicit", False) and args.niche != stored["niche"]:
        conflicts.append("--niche %s (the run is %s)" % (args.niche, stored["niche"]))
    if args.campaign and args.campaign != stored["campaign_key"]:
        conflicts.append("--campaign %s (the run feeds %s)" % (
            args.campaign, ", ".join(k for k, _t in stored_targets) or stored["campaign_key"]))
    if getattr(args, "_target_explicit", False) and args.target != stored["target"]:
        conflicts.append("--target %s (the run's target is %s)" % (args.target, stored["target"]))
    source_flag = "fixture" if getattr(args, "fixtures", False) else args.source
    if source_flag and stored["source"] and source_flag != stored["source"]:
        conflicts.append("--source %s (the run used %s)" % (source_flag, stored["source"]))
    if args.verify and stored["verify"] and args.verify != stored["verify"]:
        conflicts.append("--verify %s (the run used %s)" % (args.verify, stored["verify"]))
    if asked is not None:
        # An --all-campaigns run that finds this run open: it may only adopt a
        # run made with the targets file's own source and verifier, never a
        # rehearsal (fixture / replay) left open, or the Sunday run would
        # finish a rehearsal and report it as the week's list.
        for flag, want, have in (("source", asked.get("source"), meta.get("source")),
                                 ("verifier", asked.get("verify"), meta.get("verifier"))):
            if want and have != want:
                conflicts.append("the targets file's %s %s (open run %s used %s)" % (flag, want, run_id, have))
    if asked is not None and [tuple(p) for p in asked.get("campaigns") or []] != stored_targets:
        conflicts.append("the targets file now asks for %s but open run %s feeds %s" % (
            ", ".join("%s %d" % tuple(p) for p in asked.get("campaigns") or []), run_id,
            ", ".join("%s %d" % p for p in stored_targets) or "%s %s" % (stored["campaign_key"],
                                                                        stored["target"])))
    if conflicts:
        raise UsageError(
            "run %s keeps the campaign split, target and sources it was started with; refusing %s. "
            "Resume it with no such flag (python3 -m jobs.list_factory --now --resume %s), or start "
            "over with --fresh." % (run_id, "; ".join(conflicts), run_id))
    return stored


def run_factory(args, now: Optional[datetime] = None, group: Optional[Dict[str, Any]] = None,
                instantly=None) -> Dict[str, Any]:
    """One pipeline run. ``instantly`` may be passed in so an --all-campaigns
    run builds its suppression list once and shares the client; a client this
    function opened itself is closed here."""
    now = now or datetime.now(TZ)
    owns_client = instantly is None
    if owns_client:
        instantly = _instantly(args.offline)
    try:
        dry_run = bool(getattr(args, "dry_run", False))
        if args.resume and dry_run:
            raise UsageError("--dry-run never resumes a run")
        run_id = args.resume
        resumed = bool(args.resume)
        if not run_id and not args.fresh and not dry_run:
            # An at-least-once scheduler that re-fires the Sunday job used to
            # start from ``source`` and pay for the whole pipeline again.
            # Continue the open run instead; --fresh forces a new one.
            open_run = state_mod.find_open_run(group["niche"] if group is not None else args.niche)
            if open_run:
                logger.warning("resuming open run %s instead of starting a new one", open_run)
                run_id = open_run
                resumed = True
        run = None
        if resumed:
            run = state_mod.RunState.load(run_id)
            # The run's own campaign split and target, never the CLI defaults:
            # an --all-campaigns run resumed as ``--resume <id>`` used to be
            # rebuilt from the flags and staged everything into cleaning_trigger
            # against a target of 3,300 (R10 re-review).
            group = resume_group(args, run.run_id, run.meta, asked=group)
        cfg = build_config(args, instantly, group)
        if run is not None:
            # Belt and braces for the rule above: a resumed run is never run
            # with a source or verifier other than the ones it was started
            # with (a dry run used to swap in the fixture and the replay).
            for label, stored, now_using in (
                    ("source", run.meta.get("source"), getattr(cfg.source, "name", None)),
                    ("verifier", run.meta.get("verifier"), getattr(cfg.verifier, "name", "millionverifier"))):
                known = ("fixture", "apify", "gmaps", "replay", "millionverifier")
                if stored in known and now_using != stored:
                    raise UsageError("run %s was started with %s %s and would resume with %s; refused"
                                     % (run.run_id, label, stored, now_using))
        if not run_id:
            run_id = state_mod.new_run_id(cfg.niche, now)
        if run is None:
            run = state_mod.RunState.create(run_id, cfg.to_meta())
        led = cfg.new_ledger(run.run_id)
        # A resumed run keeps the money it already spent, or the cap is
        # meaningless the second time around.
        previous = (run.meta.get("ledger") or {}) if resumed else {}
        for stage, amount in (previous.get("costs") or {}).items():
            led.spend(stage, amount, "resumed", 0)
        for stage, count in (previous.get("counts") or {}).items():
            led.count(stage, count)
        for key, value in (previous.get("detail") or {}).items():
            led.note(key, value)

        try:
            summary = pipeline_mod.run_pipeline(run, cfg, led)
        except ledger_mod.BudgetExceeded as exc:
            run.close("halted")
            summary = {
                "run_id": run.run_id, "niche": cfg.niche, "campaign_key": cfg.campaign_key,
                "target": cfg.target, "staged": int(led.counts.get("stage", 0)),
                "status": "halted", "error": exc.snapshot["halt_reason"],
                "stages": {}, "counts": run.counts(), "ledger": exc.snapshot,
                "suppression": (cfg.suppression_list.summary() if cfg.suppression_list is not None else {}),
                "mode": settings.get_mode(), "live": settings.is_live(), "dry_run": cfg.dry_run,
            }
        summary["resumed"] = resumed
        summary["ledger_csv"] = led.append_csv(settings.get_mode())
        summary["state_file"] = run.path
        summary["campaign_targets"] = cfg.campaign_targets
        if cfg.suppression_list is not None and getattr(args, "_shared_suppression", None) is None:
            # Handed to the next niche of an --all-campaigns run: one read of
            # the workspace per Sunday, not one per niche.
            args._shared_suppression = cfg.suppression_list
        return summary
    finally:
        if owns_client and instantly is not None:
            try:
                instantly.close()
            except Exception:  # noqa: BLE001
                logger.warning("could not close the Instantly client")


def run_preflight(args) -> Dict[str, Any]:
    cfg = build_config(args, None)
    return pipeline_mod.preflight(cfg)


def run_attribution(args) -> Dict[str, Any]:
    instantly = _instantly(args.offline)
    if instantly is None:
        return {"error": "no Instantly client; attribution needs a read-only pull"}
    try:
        def reader():
            walk = instantly.iterate("leads/list", body={"limit": 100}, max_pages=200)
            rows = list(walk)
            if walk.truncated:
                logger.warning("attribution pull truncated; the numbers below are partial")
            return rows

        return ledger_mod.source_attribution(reader)
    finally:
        try:
            instantly.close()
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ output
NEXT_ACTION = {
    "ok": "nothing. Read 20 rows of the CSV before anyone uploads it.",
    "short": "the run produced far fewer contacts than asked for. Read the stage lines above "
             "for where they were lost, then resume with --resume <run id>.",
    "halted": "the projected cost broke the cap and nothing more was paid for. Leads already "
              "verified and personalized are staged in the _halted.csv beside the run state. To pay "
              "for the rest, decide on a higher cap and resume: python3 -m jobs.list_factory --now "
              "--resume {run_id} --max-cost-per-contact <new cap>. The resume keeps the run's "
              "campaign split, target and sources.",
    "over_cap": "the run finished but came in over the cap. Read the ledger lines and correct "
                "pipeline.DEFAULT_RATES before the next paid run.",
    "blocked": "a paid call was refused. Intended in a rehearsal; for a real run set "
               "ALLOW_PAID_CALLS=1 and resume with --resume <run id> (held leads are picked up).",
    "refused": "the suppression list is incomplete or stale. Re-run with --refresh-suppression.",
    "error": "a stage raised. Read the error above; the run is resumable with --resume <run id>.",
}


def next_action(summary: Dict[str, Any], all_campaigns: bool = False) -> str:
    """The next step for this status, with the real run id filled in.

    A halted run is closed, so an --all-campaigns re-run does not pick it up
    (it would start a new run and pay again), and --all-campaigns refuses
    --resume. Both modes therefore resume the one niche's run by id; the text
    says so instead of telling an --all-campaigns user to pass a flag that run
    refuses.
    """
    status = summary.get("status") or "ok"
    text = NEXT_ACTION.get(status, "read the run state")
    run_id = summary.get("run_id") or "<run id>"
    text = text.replace("{run_id}", run_id).replace("--resume <run id>", "--resume %s" % run_id)
    if all_campaigns and status in ("halted", "short", "blocked", "error"):
        text += (" This was the %s pull of an --all-campaigns run: resume it on its own, WITHOUT "
                 "--all-campaigns (which refuses --resume); the other niches are unaffected."
                 % (summary.get("niche") or "?"))
    return text


def print_summary(summary: Dict[str, Any], led_snapshot: Optional[Dict[str, Any]] = None,
                  all_campaigns: bool = False) -> None:
    print("list_factory %s  niche=%s campaign=%s  mode=%s live=%s dry_run=%s resumed=%s"
          % (summary.get("run_id"), summary.get("niche"), summary.get("campaign_key"),
             summary.get("mode"), summary.get("live"), summary.get("dry_run"),
             summary.get("resumed")))
    target = int(summary.get("target") or 0)
    staged = int(summary.get("staged") or 0)
    print("target %d, staged %d (%s)"
          % (target, staged, "%.0f%%" % (100.0 * staged / target) if target else "n/a"))
    supp = summary.get("suppression") or {}
    if supp:
        print("suppression list: %s addresses / %s domains, built %s (%s h old)%s"
              % (supp.get("emails"), supp.get("domains"), supp.get("built_utc") or "unknown",
                 supp.get("age_hours"),
                 "  SKIPPED SOURCES: %s" % ",".join(supp.get("skipped_sources") or [])
                 if supp.get("skipped_sources") else ""))
        hostile = (supp.get("sources") or {}).get("hostile_replies") or {}
        if hostile.get("hostile") is not None:
            print("  hostile replies: %s of %s received, from %s senders"
                  % (hostile.get("hostile"), hostile.get("rows"), hostile.get("senders")))
    print("status: %s%s" % (summary.get("status"), ("  (%s)" % summary["error"]) if summary.get("error") else ""))
    print("next: %s" % next_action(summary, all_campaigns))
    print("\nstages:")
    for name, result in (summary.get("stages") or {}).items():
        brief = {k: v for k, v in (result or {}).items() if not isinstance(v, (dict, list))}
        print("  %-13s %s" % (name, json.dumps(brief, default=str)))
    print("\nlead stages:")
    for key, count in sorted((summary.get("counts") or {}).items(), key=lambda kv: -kv[1]):
        print("  %-28s %5d" % (key, count))
    snapshot = led_snapshot or summary.get("ledger") or {}
    if snapshot:
        print("\ncost ledger:")
        print("  stage         count        usd")
        for stage in ledger_mod.STAGES:
            print("    %-11s %6d  %9.4f"
                  % (stage, (snapshot.get("counts") or {}).get(stage, 0),
                     (snapshot.get("costs") or {}).get(stage, 0.0)))
        cpv = snapshot.get("cost_per_verified")
        cpd = snapshot.get("cost_per_deliverable")
        share = snapshot.get("catch_all_share")
        print("    %-11s %6s  %9.4f" % ("TOTAL", "", snapshot.get("total_usd") or 0.0))
        print("  cost per verified contact: %s (cap $%.4f) -> %s"
              % ("n/a" if cpv is None else "$%.5f" % cpv,
                 snapshot.get("max_cost_per_contact") or 0.0, snapshot.get("verdict")))
        print("  cost per deliverable (catch-alls included): %s%s"
              % ("n/a" if cpd is None else "$%.5f" % cpd,
                 "" if share is None else "   catch-all share %.1f%% (unconfirmed mailboxes)"
                 % (100.0 * share)))
        print("  source=%s verifier=%s dry_run=%s"
              % (snapshot.get("source"), snapshot.get("verifier"), snapshot.get("dry_run")))
        would = (snapshot.get("detail") or {})
        for key in ("source_would_have_cost", "finder_would_have_cost"):
            if would.get(key):
                print("  %s: $%.4f (not spent: the paid gate was closed)" % (key, float(would[key])))
    stage_detail = ((summary.get("stages") or {}).get("stage") or {})
    per_campaign = stage_detail.get("campaigns") or {}
    if per_campaign:
        print("\nstaged per campaign (one source pull, each business goes to one campaign):")
        for key, result in per_campaign.items():
            print("  %-26s %4d of %s  %s" % (key, int((result or {}).get("staged") or 0),
                                             (result or {}).get("target"), (result or {}).get("csv") or "-"))
    if stage_detail.get("csv"):
        print("\nstaged CSV: %s" % stage_detail["csv"])
    if stage_detail.get("csv") or per_campaign:
        print("would_do records: %d (shadow=%s)"
              % (stage_detail.get("would_do_records", 0), stage_detail.get("shadow")))
    salvage = ((summary.get("stages") or {}).get("salvage") or {})
    if salvage:
        print("\nhalted: %d verified lead(s) were waiting; %d staged into %s; %d not staged because "
              "they have no personalization line and writing one costs money the cap refused"
              % (int(salvage.get("verified_waiting") or 0), int(salvage.get("staged") or 0),
                 salvage.get("csv") or "(nothing staged)", int(salvage.get("awaiting_personalization") or 0)))


def print_attribution(report: Dict[str, Any]) -> None:
    if report.get("error"):
        print("attribution unavailable: %s" % report["error"])
        return
    print("source attribution over %d workspace leads, %d sources"
          % (report.get("total_leads", 0), report.get("sources", 0)))
    print("  replies = Instantly email_reply_count: auto-responders and OOO included, so this is")
    print("  a number for comparing sources against each other, not the real reply rate.")
    print("  %-34s %6s %6s %7s %9s %8s" % ("source", "leads", "sends", "replies", "repl/1k", "bounce%"))
    for row in report.get("by_source") or []:
        print("  %-34s %6d %6d %7d %9s %8s"
              % (row["source"][:34], row["leads"], row["sends"], row["replies"],
                 "-" if row["replies_per_1k_sends"] is None else "%.1f" % row["replies_per_1k_sends"],
                 "-" if row["bounce_rate_pct"] is None else "%.2f" % row["bounce_rate_pct"]))


# --------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="list_factory", description=__doc__.split("\n\n")[0])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="run the pipeline, write nothing outside a scratch log, send no notification")
    mode.add_argument("--now", action="store_true", help="run for real (still shadow unless live is enabled)")
    mode.add_argument("--preflight", action="store_true", help="price the run and stop")
    mode.add_argument("--attribution", action="store_true", help="replies per 1,000 sends by source (read-only)")
    mode.add_argument("--runs", action="store_true", help="list resumable runs")

    p.add_argument("--all-campaigns", action="store_true",
                   help="feed every enabled campaign in config/list_factory_targets.json, "
                        "one source pull per niche, in the file's order (the Sunday O8 run)")
    p.add_argument("--targets", help="path to a campaign targets file (default: the bundled one)")
    p.add_argument("--niche", default=None, help="cleaning, bookkeeping, recruiting (config/icp/; default cleaning)")
    p.add_argument("--campaign", help="campaign key from config/ids.json (default: the niche's trigger campaign)")
    p.add_argument("--target", type=int, default=None,
                   help="verified contacts wanted for a single-niche run (default %d)" % DEFAULT_TARGET)
    p.add_argument("--source", default=None, choices=("fixture", "apify", "gmaps"),
                   help="required with --now unless --fixtures or --all-campaigns names it")
    p.add_argument("--fixture", help="path to a recorded source file")
    p.add_argument("--fixtures", action="store_true",
                   help="shorthand for --source fixture on the bundled 50-business file (a rehearsal)")
    p.add_argument("--metros", nargs="*", help="metros for --source gmaps")
    p.add_argument("--resume", help="run id to continue")
    p.add_argument("--max-cost-per-contact", type=float, default=ledger_mod.DEFAULT_MAX_COST_PER_CONTACT)
    p.add_argument("--batch-size", type=int, default=icp.DEFAULT_BATCH_SIZE, help="businesses per ICP model call")
    p.add_argument("--max-escalations", type=int, default=icp.DEFAULT_MAX_ESCALATIONS)
    p.add_argument("--fresh", action="store_true",
                   help="start a new run even when an unfinished one exists for this niche")
    p.add_argument("--refresh-suppression", action="store_true",
                   help="rebuild the suppression list instead of using today's cache (wins over --suppression)")
    p.add_argument("--skip-hostile-scan", action="store_true",
                   help="skip the received-email pull (GET /emails is capped at 20 requests/minute). "
                        "This makes the list INCOMPLETE and the run will refuse to stage: it is a "
                        "diagnostic flag, not a way to run faster")
    p.add_argument("--offline", action="store_true", help="no live reads; needs a cached suppression list")
    p.add_argument("--suppression", help="path to a saved suppression list (offline replay)")
    p.add_argument("--allow-stale-suppression", action="store_true",
                   help="accept a suppression list older than %d hours. Every address that "
                        "unsubscribed, bounced or replied hostile since it was built will be "
                        "mailed again" % int(suppression_mod.DEFAULT_MAX_AGE_HOURS))
    p.add_argument("--catch-all", default="include", choices=("include", "exclude"),
                   help="whether to stage guessed addresses on catch-all domains. They are always "
                        "counted separately and never enter the cost-per-verified denominator")
    p.add_argument("--verify", default=None, choices=("replay", "millionverifier"),
                   help="replay draws from recorded outcomes and spends nothing; millionverifier is the "
                        "real paid client and needs ALLOW_PAID_CALLS=1. Required with --now unless "
                        "--fixtures (replay) or --all-campaigns names it")
    p.add_argument("--replay-ok-multiplier", type=float, default=1.0,
                   help="scale the replay deliverable rate down to stress the cost model (1.0 = the "
                        "recorded rates, which are an upper bound)")
    p.add_argument("--would-do", default="batch", choices=("batch", "per-lead"),
                   help="one POST /leads record per campaign, or one per lead")
    p.add_argument("--json", action="store_true", help="print the summary as JSON")
    return p


DEFAULT_TARGET = TH.LIST_FACTORY_WEEKLY_TARGET   # M5: 3,300 contacts a week
DEFAULT_NICHE = "cleaning"


def _fail(args, status: str, message: str, rc: int = 2, details: Optional[Dict[str, Any]] = None) -> int:
    """One Job_Log row and one high-priority push for a run that could not run.

    The cron path used to catch only RubricError and SuppressionError, so the
    scheduled Sunday run's ValueError wrote no Job_Log row and sent no push.
    A dry run is logged but never pushes (its contract is "no notification").
    """
    row = {"error": message}
    row.update(details or {})
    log_run(JOB, status, row)
    if not getattr(args, "dry_run", False):
        notify("List factory %s" % ("refused to start" if status == "refused" else "failed"),
               message, priority="high", tags=["warning"])
    print("%s: %s" % (status, message))
    return rc


def main(argv: Optional[List[str]] = None, now: Optional[datetime] = None) -> int:
    p = build_parser()
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        if exc.code in (0, None):
            raise
        # A mistyped flag in the scheduled command is a Sunday with no list.
        return _fail(argparse.Namespace(dry_run=False), "error",
                     "the list factory's arguments were rejected: %r" % (list(argv) if argv is not None
                                                                         else sys.argv[1:]))
    try:
        return _main(p, args, now)
    except UsageError as exc:
        return _fail(args, "refused", str(exc))
    except SystemExit as exc:
        if exc.code in (0, None):
            raise
        return _fail(args, "error", str(exc.code))
    except Exception as exc:  # noqa: BLE001 - an unattended job must always leave a row and a push
        logger.exception("list factory crashed")
        return _fail(args, "error", "%s: %s" % (type(exc).__name__, exc))


def _main(p: argparse.ArgumentParser, args, now: Optional[datetime]) -> int:
    # Nothing in this function may log (a refusal included) before the
    # rehearsal-or-real decision below has pointed the logs at scratch for a
    # rehearsal. ``--dry-run --all-campaigns --target 5`` used to be refused
    # first, and its refused row landed in the real Job_Log (re-review 3).
    args._target_explicit = args.target is not None
    args._niche_explicit = args.niche is not None
    if args.target is None:
        args.target = DEFAULT_TARGET
    if args.niche is None:
        args.niche = DEFAULT_NICHE

    # Evidence runs never write into the Job_Log the 48-hour shadow watch
    # reads. The gate keys on the SOURCE and VERIFIER the run will actually
    # use, decided here BEFORE any log is written: the typed flags, and for a
    # resume (explicit, or the open run a --now picks up) the run's STORED
    # ones. It used to look at typed flags only, so
    # ``--now --resume <replay rehearsal>`` wrote a Job_Log row and a fake
    # create_lead_batch record into the real logs (re-review 2). An identical
    # replay run typed as ``--now --source fixture --fixture X --verify replay``
    # is evidence too. See shared.job_log.use_scratch_logs.
    # planned_sources only reads (the targets file, a stored run's meta); it
    # never logs, so it may run before the logs are pointed anywhere.
    planned = planned_sources(args)
    if args.now and args.all_campaigns:
        # A targets file that mixes paid and rehearsal pulls is refused
        # outright, into the REAL Job_Log with a push, before any pull runs.
        # Treating the whole run as a rehearsal hid a paid pull's real spend
        # in scratch; treating it as real would put the rehearsal pull's made-up
        # create_lead_batch record in the log the shadow watch reads (re-review 4).
        _refuse_mixed_pulls(planned, args)
    typed_evidence = bool(args.dry_run or args.preflight or args.attribution or args.fixtures
                          or args.source == "fixture" or args.verify == "replay")
    scratch = None
    if typed_evidence:
        # Switched on the typed flags first, so nothing that follows can log to
        # the real files.
        scratch = _use_scratch(args, args.source == "fixture" or args.fixtures)
    rehearsal_sources = any(src == "fixture" or ver == "replay" for src, ver in planned)
    if rehearsal_sources and scratch is None:
        scratch = _use_scratch(args, any(src == "fixture" for src, _v in planned))

    if args.all_campaigns and (args.campaign or args.resume or args._target_explicit):
        raise UsageError("--all-campaigns takes its campaigns and targets from the targets file; "
                         "drop --campaign, --resume and --target. To continue one niche's run, use "
                         "--resume <run id> WITHOUT --all-campaigns (it keeps its campaign split); an open "
                         "run that merely died is picked up automatically, a halted one is not")

    if not args.dry_run:
        return _dispatch(p, args, now)
    # A dry run never loads, resumes, mutates or closes an existing run: its
    # run state lives in its own scratch directory and it always starts fresh.
    # It used to adopt an open REAL (Apify + MillionVerifier) run through
    # find_open_run, verify that run's paid leads with the replay verifier,
    # write a staged CSV into the real run folder and close it as ok.
    if args.resume:
        raise UsageError("--dry-run never resumes a run (it would run the stored run's leads through "
                         "the fixture and the replay verifier and close it). Resume with --now, or "
                         "drop --resume for a fresh rehearsal")
    args.fresh = True
    previous = state_mod.use_runs_dir(str((scratch or Path(".")) / "runs"))
    try:
        return _dispatch(p, args, now)
    finally:
        state_mod.use_runs_dir(previous)


PAID_NAMES = ("apify", "gmaps", "millionverifier")
REHEARSAL_NAMES = ("fixture", "replay")


def _refuse_mixed_pulls(planned: List[Any], args) -> None:
    """UsageError when the pulls of one --now --all-campaigns run name both a
    paid source or verifier and a rehearsal one (across pulls, or inside one
    pull such as apify + replay)."""
    names = set(n for pair in planned for n in pair if n)
    paid = sorted(names & set(PAID_NAMES))
    rehearsal = sorted(names & set(REHEARSAL_NAMES))
    if paid and rehearsal:
        raise UsageError(
            "the targets file %s mixes paid (%s) and rehearsal (%s) sources or verifiers across its "
            "niche pulls (%s). One run is either real or a rehearsal: its logs go to the real Job_Log "
            "or to scratch, never both. Nothing was fetched. Make every entry paid for the Sunday run, "
            "or every entry fixture/replay (or use --dry-run) for a rehearsal."
            % (getattr(args, "targets", None) or targets_mod.DEFAULT_PATH, ", ".join(paid),
               ", ".join(rehearsal), "; ".join("%s + %s" % pair for pair in planned)))


def _use_scratch(args, fixture_source: bool):
    """Point the Job_Log, the shadow log and the cost ledger at scratch."""
    from shared.job_log import use_scratch_logs

    label = "dryrun" if args.dry_run else ("fixtures" if fixture_source else "replay")
    scratch = use_scratch_logs("list_factory_%s" % label)
    # The cost ledger is evidence too. Without this a free replay row lands
    # in the same .tmp/list_factory/cost_ledger.csv as a real paid run.
    os.environ.setdefault("LIST_FACTORY_LEDGER_PATH", str(scratch / "cost_ledger.csv"))
    return scratch


def planned_sources(args) -> List[Any]:
    """Every (source, verifier) pair this invocation will actually run with, as
    far as they can be known before anything is logged: one per niche pull for
    ``--all-campaigns``, one otherwise.

    Flags win; the gaps are filled exactly as ``resolve_source_and_verifier``
    and ``resume_group`` will fill them: from the targets file's groups for
    ``--all-campaigns`` (a targets file whose defaults are ``fixture`` and
    ``replay`` is a rehearsal, and its rows used to go to the real logs,
    re-review 3), and from a resumed run's stored names otherwise. Any pair
    naming ``fixture`` or ``replay`` makes the whole invocation a rehearsal.
    """
    source = "fixture" if getattr(args, "fixtures", False) else (args.source or None)
    verify = args.verify or None
    if getattr(args, "dry_run", False):
        # A dry run never resumes and never takes a paid source from a file.
        return [(source or "fixture", verify or "replay")]
    if getattr(args, "all_campaigns", False):
        # An --all-campaigns run refuses to adopt an open run whose source or
        # verifier differs from the targets file, so the file decides.
        try:
            groups = targets_mod.niche_groups(targets_mod.load(args.targets))
        except targets_mod.TargetsError:
            return [(source, verify)]   # the run itself refuses with the reason
        return [(source or g.get("source"), verify or g.get("verify")) for g in groups] or [(source, verify)]
    meta = {}  # type: Dict[str, Any]
    if args.resume:
        meta = state_mod.run_meta(args.resume)
    elif getattr(args, "now", False) and not args.fresh:
        open_run = state_mod.find_open_run(args.niche)
        if open_run:
            meta = state_mod.run_meta(open_run)
    stored_source = meta.get("source") if meta.get("source") in ("fixture", "apify", "gmaps") else None
    stored_verify = meta.get("verifier") if meta.get("verifier") in ("replay", "millionverifier") else None
    return [(source or stored_source, verify or stored_verify)]


def _dispatch(p: argparse.ArgumentParser, args, now: Optional[datetime]) -> int:

    if args.runs:
        runs = state_mod.list_runs()
        print("resumable runs (%d):" % len(runs))
        for run_id in runs:
            print("  %s" % run_id)
        return 0

    if args.preflight:
        if args.all_campaigns:
            return _preflight_all(args)
        report = run_preflight(args)
        print(json.dumps(report, indent=2, default=str) if args.json else _preflight_table(report))
        log_run(JOB, "preflight", report)
        return 0 if report.get("within_cap") else 1

    if args.attribution:
        report = run_attribution(args)
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print_attribution(report)
        log_run(JOB, "attribution", {"sources": report.get("sources"), "total_leads": report.get("total_leads")})
        return 0

    if not (args.dry_run or args.now):
        p.error("pick --dry-run, --now, --preflight, --attribution or --runs")

    if args.all_campaigns:
        return _run_all_campaigns(args, now)

    try:
        summary = run_factory(args, now=now)
    except icp.RubricError as exc:
        return _fail(args, "error", str(exc))
    except suppression_mod.SuppressionError as exc:
        return _fail(args, "refused", str(exc))
    except UsageError as exc:
        return _fail(args, "refused", str(exc))
    return _report_run(args, summary)


def _log_details(summary: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = summary.get("ledger") or {}
    staged = int(summary.get("staged") or (snapshot.get("counts") or {}).get("stage", 0))
    stage_detail = ((summary.get("stages") or {}).get("stage") or {})
    salvage = ((summary.get("stages") or {}).get("salvage") or {})
    per_campaign = dict((k, int((v or {}).get("staged") or 0))
                        for k, v in ((stage_detail.get("campaigns") or salvage.get("campaigns") or {}).items()))
    return {
        "run_id": summary.get("run_id"),
        "niche": summary.get("niche"),
        "campaign_key": summary.get("campaign_key"),
        "campaign_targets": summary.get("campaign_targets"),
        "staged_by_campaign": per_campaign or None,
        "counts": summary.get("counts"),
        "target": summary.get("target"),
        "staged": staged,
        "salvaged": salvage.get("staged"),
        "awaiting_personalization": salvage.get("awaiting_personalization"),
        "next": next_action(summary, bool(summary.get("_all_campaigns"))),
        "verified": (snapshot.get("counts") or {}).get("verify", 0),
        "catch_all": (snapshot.get("counts") or {}).get("catch_all", 0),
        "held": summary.get("held"),
        "source": snapshot.get("source"),
        "verifier": snapshot.get("verifier"),
        "total_usd": snapshot.get("total_usd"),
        "cost_per_verified": snapshot.get("cost_per_verified"),
        "verdict": snapshot.get("verdict"),
        "error": summary.get("error"),
        "state_file": summary.get("state_file"),
    }


def _report_run(args, summary: Dict[str, Any], push: bool = True) -> int:
    summary["_all_campaigns"] = bool(getattr(args, "all_campaigns", False))
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print_summary(summary, all_campaigns=summary["_all_campaigns"])
    snapshot = summary.get("ledger") or {}
    status = summary.get("status") or "ok"
    details = _log_details(summary)
    staged = details["staged"]
    log_run(JOB, "dry_run" if args.dry_run else status, details)

    # Notify on anything that is not a clean, productive run. A run that staged
    # zero used to report ok, exit 0 and send nothing, so a total failure of
    # the unattended Sunday job looked exactly like success.
    if push and not args.dry_run and (status != "ok" or staged <= 0):
        notify(
            "List factory %s: %s" % (status if status != "ok" else "produced nothing", summary.get("niche")),
            "%s\nrun %s\nstaged %d of a target of %s\nspent $%.4f, %s verified, %s per contact\nnext: %s"
            % (summary.get("error") or "see the run state",
               summary.get("run_id"), staged, summary.get("target"),
               snapshot.get("total_usd") or 0.0,
               (snapshot.get("counts") or {}).get("verify", 0),
               "n/a" if snapshot.get("cost_per_verified") is None else "$%.5f" % snapshot["cost_per_verified"],
               details["next"]),
            priority="high", tags=["warning"],
        )
    return 0 if (status == "ok" and staged > 0) else 1


def _print_disabled(targets: Dict[str, Any]) -> List[Dict[str, Any]]:
    off = targets_mod.disabled(targets)
    if off:
        print("campaigns NOT fed this run (%d), each disabled in %s:" % (len(off), targets["path"]))
        for entry in off:
            print("  %-26s %s" % (entry["campaign_key"], entry.get("disabled_reason")))
    return [{"campaign_key": e["campaign_key"], "reason": e.get("disabled_reason")} for e in off]


def _preflight_all(args) -> int:
    targets = targets_mod.load(args.targets)
    disabled = _print_disabled(targets)
    reports = []
    for group in targets_mod.niche_groups(targets):
        cfg = build_config(args, None, group)
        report = pipeline_mod.preflight(cfg)
        report["niche"] = group["niche"]
        report["campaign_targets"] = group["campaigns"]
        reports.append(report)
        print("\n== %s: %s" % (group["niche"], ", ".join("%s %d" % pair for pair in group["campaigns"])))
        print(json.dumps(report, indent=2, default=str) if args.json else _preflight_table(report))
    over = [r["niche"] for r in reports if not r.get("within_cap")]
    log_run(JOB, "preflight", {"all_campaigns": True, "disabled": disabled, "over_cap": over,
                               "groups": [{"niche": r["niche"], "usd": (r.get("usd") or {}).get("total"),
                                           "cost_per_verified": r.get("cost_per_verified")} for r in reports]})
    return 1 if over else 0


def _run_all_campaigns(args, now: Optional[datetime]) -> int:
    """The Sunday run: every enabled campaign, Cleaning Reactivation first."""
    targets = targets_mod.load(args.targets)
    groups = targets_mod.niche_groups(targets)
    print("list factory --all-campaigns: %d niche pull(s), campaigns in run order: %s"
          % (len(groups), ", ".join("%s (%d)" % pair for g in groups for pair in g["campaigns"])))
    disabled = _print_disabled(targets)
    if not groups:
        return _fail(args, "refused", "no campaign is enabled in %s" % targets["path"],
                     details={"disabled": disabled})
    instantly = _instantly(args.offline)
    results = []
    try:
        for group in groups:
            print("\n== %s pull for %s" % (group["niche"], ", ".join(k for k, _t in group["campaigns"])))
            try:
                summary = run_factory(args, now=now, group=group, instantly=instantly)
            except (icp.RubricError, suppression_mod.SuppressionError, UsageError) as exc:
                status = "refused" if not isinstance(exc, icp.RubricError) else "error"
                summary = {"niche": group["niche"], "campaign_key": group["campaigns"][0][0],
                           "campaign_targets": group["campaigns"], "target": group["target"],
                           "status": status, "error": str(exc), "staged": 0}
                print("%s: %s" % (status, exc))
                log_run(JOB, "dry_run" if args.dry_run else status, _log_details(summary))
            except Exception as exc:  # noqa: BLE001 - one niche failing must not lose the others
                logger.exception("list factory pull for %s crashed", group["niche"])
                summary = {"niche": group["niche"], "campaign_key": group["campaigns"][0][0],
                           "campaign_targets": group["campaigns"], "target": group["target"],
                           "status": "error", "error": "%s: %s" % (type(exc).__name__, exc), "staged": 0}
                print("error: %s" % summary["error"])
                log_run(JOB, "dry_run" if args.dry_run else "error", _log_details(summary))
            else:
                _report_run(args, summary, push=False)
            results.append(summary)
    finally:
        if instantly is not None:
            try:
                instantly.close()
            except Exception:  # noqa: BLE001
                logger.warning("could not close the Instantly client")

    failed = [r for r in results if (r.get("status") or "ok") != "ok" or int(r.get("staged") or 0) <= 0]
    overall = "ok" if not failed else "partial"
    # Paid calls are off by design until Lorenzo approves the figure (DECISIONS
    # M3): every pull stops at its first paid call and stages nothing. That is
    # the designed Sunday outcome, not a failure: exit 0, its own status, one
    # normal-priority note (the laptop runner records it as paid_calls_off).
    paid_off = bool(results) and not args.dry_run and not sources_mod.paid_calls_allowed() and all(
        r.get("status") == "blocked" and int(r.get("staged") or 0) <= 0 for r in results)
    if paid_off:
        overall = PAID_CALLS_OFF
    lines = ["%s: %s, staged %d of %s%s" % (r.get("niche"), r.get("status"), int(r.get("staged") or 0),
                                            r.get("target"), ("  (%s)" % r["error"]) if r.get("error") else "")
             for r in results]
    print("\nall campaigns: %s" % overall)
    for line in lines:
        print("  %s" % line)
    log_run(JOB, "dry_run" if args.dry_run else overall, {
        "all_campaigns": True,
        "run_order": [pair[0] for g in groups for pair in g["campaigns"]],
        "disabled": disabled,
        "groups": [{"niche": r.get("niche"), "status": r.get("status"), "staged": r.get("staged"),
                    "target": r.get("target"), "run_id": r.get("run_id"), "error": r.get("error")}
                   for r in results],
    })
    if paid_off:
        notify("List factory: paid calls are off, nothing staged",
               "The Sunday run stopped at its first paid call, by design: ALLOW_PAID_CALLS is 0 because "
               "LAPTOP_PAID_JOBS in .env does not name list_factory (DECISIONS M3, about $55 a run).\n"
               + "\n".join(lines), priority="default")
        print("%s%s" % (OUTCOME_MARKER, PAID_CALLS_OFF))
        return 0
    if failed and not args.dry_run:
        notify("List factory: %d of %d niche pull(s) did not deliver" % (len(failed), len(results)),
               "\n".join(lines) + ("\nnot fed by design: %s" % ", ".join(d["campaign_key"] for d in disabled)
                                   if disabled else ""),
               priority="high", tags=["warning"])
    return 0 if not failed else 1


def _preflight_table(report: Dict[str, Any]) -> str:
    projected = report.get("projected") or {}
    usd = report.get("usd") or {}
    lines = ["preflight for %d staged contacts" % report.get("target_verified", 0), "", "  projected counts:"]
    for key in ("sourced", "survivors", "icp_pass", "owners", "owner_lookups", "checks",
                "verified", "confirmed", "staged"):
        lines.append("    %-14s %8d" % (key, projected.get(key, 0)))
    lines.append("  source: %s (fill_rate %s, name_rate %s)"
                 % (report.get("source"), report.get("source_fill_rate"), report.get("source_name_rate")))
    lines.append("  projected cost:")
    for key in ("source", "icp", "owner", "verify", "personalize", "total"):
        lines.append("    %-12s $%9.4f" % (key, usd.get(key, 0.0)))
    lines.append("  cost per CONFIRMED contact: $%.5f (cap $%.4f) -> %s"
                 % (report.get("cost_per_verified", 0.0), report.get("cap", 0.0),
                    "WITHIN CAP" if report.get("within_cap") else "OVER CAP"))
    lines.append("  cost per deliverable (catch-alls included): $%.5f"
                 % report.get("cost_per_deliverable", 0.0))
    lines.append("  catch-all share assumed: %.0f%% (a catch-all domain accepts every local part,"
                 % (100.0 * (report.get("assumed_rates") or {}).get("catch_all_share", 0.0)))
    lines.append("  so a GUESSED address there is not a confirmed mailbox)")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
