"""Weekly campaign verdicts and experiment log (Blueprint M4, O6; brief A7).

    python3 -m jobs.campaign_verdicts --dry-run
    python3 -m jobs.campaign_verdicts --dry-run --as-of 2026-10-12
    python3 -m jobs.campaign_verdicts --json
    python3 -m jobs.campaign_verdicts --out .tmp/verdicts.md

Pulls Instantly campaign analytics read-only (overview, per-step and
per-variant), counts positives off the replied-lead list, applies the M4
verdict rules, projects the date each campaign reaches its next decision
point at today's volume and at the 2026-10-11 volume, refreshes
``config/experiments.json``, writes one Job_Log row and alerts Lorenzo on
failure.

It never writes to a live system. The only file it changes is
``config/experiments.json``; ``--dry-run`` does not write it (``--out`` is
still honoured, because a markdown file at a path you asked for is the point of
the flag). Runs Friday with the rest of O6, with notifications ON so a failed
pull reaches Lorenzo.

``--campaign`` narrows the pull, so a run that names a subset of the campaigns
**never writes the experiment log**: the experiments span all six campaigns and
rebuilding their sample from one campaign's numbers would silently throw the
other five away.
"""
import argparse
import datetime
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # run as a script: make "shared"/"services" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings
from shared.job_log import log_run
from shared.notify import notify
from shared.settings import TZ, get_mode

from services.experiments import analytics, experiment_log, report as report_mod
from services.experiments import verdicts as V

logger = logging.getLogger("jobs.campaign_verdicts")

JOB = "campaign_verdicts"
DAILY_WINDOW_DAYS = 14


def _client():
    from shared.instantly import default_client
    return default_client()


def run(
    client,
    as_of: datetime.date,
    campaign_keys: Optional[List[str]] = None,
    experiments_path: Optional[str] = None,
    dry_run: bool = False,
    ids: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Everything the job does, with the client injected so tests can mock the
    transport. Returns the summary the CLI prints and logs."""
    ids = ids if ids is not None else settings.IDS
    capacity = V.capacity_from_ids(ids)
    daily_end = as_of.isoformat()
    daily_start = (as_of - datetime.timedelta(days=DAILY_WINDOW_DAYS)).isoformat()

    stats_by_key = analytics.collect(
        client, campaign_keys=campaign_keys, daily_start=daily_start, daily_end=daily_end
    )
    verdict_map = V.run(stats_by_key, capacity, as_of)
    order = list(stats_by_key.keys())
    verdict_list = [verdict_map[k] for k in order]

    variant_verdicts = []  # type: List[Any]
    for key in order:
        variant_verdicts.extend(V.judge_all_steps(stats_by_key[key]))

    # A partial pull must never rewrite a log whose tests span every campaign.
    # experiment_log.update() rebuilds current_sample from scratch, so one
    # `--campaign cleaning_trigger` run would drop the other five campaigns'
    # sample out of a running test, and could drag a decided test back under
    # its sample line.
    all_keys = set((settings.CAMPAIGNS or {}).keys()) or set(order)
    partial_pull = bool(campaign_keys) and set(order) < all_keys

    # An incomplete read is not a quiet week. An empty analytics overview used
    # to log "ok", exit 0 and send nothing, while every campaign showed 0 sends,
    # every date was projected from zero and config/experiments.json was
    # rewritten from those zeros (MKT-9). Now: any campaign without its
    # overview row, or whose replied-lead walk was cut short, makes the run
    # "partial" (all of them: "empty"), the log is not written, the job exits
    # non-zero and Lorenzo gets a push.
    missing_overview = sorted(k for k in order
                              if "no analytics row returned for this campaign" in (stats_by_key[k].notes or []))
    truncated = sorted(k for k in order if getattr(stats_by_key[k], "partial", False))
    status = "ok"
    incomplete = None
    if order and len(missing_overview) == len(order):
        status = "empty"
        incomplete = ("the analytics overview returned no row for any of the %d campaigns, so every "
                      "number below is a zero from a failed read, not a measurement" % len(order))
    elif missing_overview or truncated:
        status = "partial"
        parts = []
        if missing_overview:
            parts.append("no analytics overview row for %s" % ", ".join(missing_overview))
        if truncated:
            parts.append("the replied-lead walk was cut short for %s (positives undercounted)"
                         % ", ".join(truncated))
        incomplete = "; ".join(parts)

    doc = experiment_log.load(experiments_path)
    changes = experiment_log.update(doc, stats_by_key, as_of.isoformat())
    written = None
    skipped = None
    if partial_pull:
        skipped = ("this run pulled %d of %d campaigns (%s), so config/experiments.json was not "
                   "written: the experiments span every campaign and a partial sample would "
                   "overwrite the rest" % (len(order), len(all_keys), ", ".join(sorted(order))))
    elif incomplete:
        skipped = ("the pull was incomplete (%s), so config/experiments.json was not written: a "
                   "sample rebuilt from a failed read would reset running tests" % incomplete)
    elif not dry_run:
        written = experiment_log.save(doc, experiments_path)

    extra_notes = []
    if incomplete:
        extra_notes.append("INCOMPLETE PULL: %s" % incomplete)
    if skipped:
        extra_notes.append(skipped)
    markdown = report_mod.render(verdict_list, variant_verdicts, doc, capacity, as_of, get_mode(),
                                 extra_notes=extra_notes)
    return {
        "job": JOB,
        "as_of": as_of.isoformat(),
        "mode": get_mode(),
        "dry_run": dry_run,
        "status": status,
        "incomplete": incomplete,
        "partial_pull": partial_pull,
        "capacity": capacity.to_dict(),
        "verdicts": [v.to_dict() for v in verdict_list],
        "variants": [vv.to_dict() for vv in variant_verdicts],
        "experiments": changes,
        "experiments_written": written,
        "experiments_skipped": skipped,
        "markdown": markdown,
    }


def _log_details(summary: Dict[str, Any]) -> Dict[str, Any]:
    """The Job_Log row stays small: one line per campaign, not the whole pull."""
    return {
        "as_of": summary["as_of"],
        "dry_run": summary["dry_run"],
        "verdicts": {
            v["campaign"]: {
                "sends": v["stats"]["sent"],
                "positives": v["stats"]["positives"],
                "recommendation": v["recommendation"],
                "next": v["next_decision_point"],
                "eta_blended": v["eta_blended"],
                "flags": v["flags"],
            }
            for v in summary["verdicts"]
        },
        "experiments": {e["id"]: {"status": e["status"], "winner": e["winner"],
                                  "sample_met": e.get("sample_met")}
                        for e in summary["experiments"]},
        "experiments_written": summary["experiments_written"],
        "experiments_skipped": summary.get("experiments_skipped"),
        "incomplete": summary.get("incomplete"),
    }


def _print_human(summary: Dict[str, Any]) -> None:
    print(summary["markdown"])
    retire = [v for v in summary["verdicts"] if v["recommendation"] == "retire"]
    if retire:
        print("ACTION: %d campaign(s) are at the retirement line: %s"
              % (len(retire), ", ".join([v["campaign"] for v in retire])))
        print("        Retiring a campaign is a live write. Stage it as a change-set and let "
              "Lorenzo approve it; this job only proposes.")
    if summary.get("experiments_skipped"):
        print("\n(experiments log NOT written: %s)" % summary["experiments_skipped"])
    elif summary["dry_run"]:
        print("\n(dry run: config/experiments.json was NOT written)")
    elif summary["experiments_written"]:
        print("\nexperiments log: %s" % summary["experiments_written"])


def main(argv: Optional[List[str]] = None, client=None, as_of: Optional[datetime.date] = None) -> int:
    p = argparse.ArgumentParser(prog=JOB, description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="pull and report, but do not write config/experiments.json")
    p.add_argument("--as-of", help="date to evaluate at (YYYY-MM-DD, default today in CT)")
    p.add_argument("--campaign", action="append", dest="campaigns",
                   help="limit to one campaign key from config/ids.json (repeatable)")
    p.add_argument("--experiments", help="path to the experiments JSON (default config/experiments.json)")
    p.add_argument("--json", action="store_true", help="print the full summary as JSON")
    p.add_argument("--out", help="also write the markdown report to this path (honoured under "
                                 "--dry-run too; only config/experiments.json is withheld)")
    args = p.parse_args(argv)

    # use_scratch_logs() sets JOB_LOG_PATH and SHADOW_LOG_PATH process-wide.
    # Without restoring them, a real run that follows a dry run in the same
    # process (an in-process O6 runner, or the runbook's two-call one-liner)
    # writes its evidence row into the dry-run scratch directory, where the
    # 48-hour shadow watch - which reads .tmp/job_log.csv - never sees it.
    saved_log_env = {name: os.environ.get(name) for name in ("JOB_LOG_PATH", "SHADOW_LOG_PATH")}
    if args.dry_run:
        # A dry run must not write into the job log the 48-hour shadow watch
        # reads. See shared.job_log.use_scratch_logs.
        from shared.job_log import use_scratch_logs

        use_scratch_logs("campaign_verdicts_dryrun")

    if as_of is None:
        if args.as_of:
            as_of = datetime.datetime.strptime(args.as_of, "%Y-%m-%d").date()
        else:
            as_of = datetime.datetime.now(TZ).date()

    try:
        return _main_guarded(args, client, as_of)
    finally:
        for name, value in saved_log_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _main_guarded(args, client, as_of: datetime.date) -> int:
    owned_client = False
    if client is None:
        client = _client()
        owned_client = True
    try:
        summary = run(
            client,
            as_of,
            campaign_keys=args.campaigns,
            experiments_path=args.experiments,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - a failed weekly job must alert, not vanish
        log_run(JOB, "failed", {"error": str(exc)[:400], "as_of": as_of.isoformat(),
                                "traceback": traceback.format_exc()[-1200:]})
        notify("Campaign verdicts failed", "%s: %s" % (JOB, str(exc)[:300]), priority="high")
        logger.exception("campaign_verdicts failed")
        return 1
    finally:
        if owned_client:
            try:
                client.close()
            except Exception:  # noqa: BLE001 - closing a client must not fail the run
                logger.warning("could not close the Instantly client")

    status = summary.get("status") or "ok"
    log_run(JOB, ("dry_run" if status == "ok" else "dry_run_" + status) if args.dry_run else status,
            _log_details(summary))
    if status != "ok" and not args.dry_run:
        notify("Campaign verdicts %s" % status.upper(),
               "%s: %s\nconfig/experiments.json was NOT written." % (JOB, summary.get("incomplete")),
               priority="high")

    if args.out:
        directory = os.path.dirname(args.out)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(summary["markdown"])

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        _print_human(summary)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
