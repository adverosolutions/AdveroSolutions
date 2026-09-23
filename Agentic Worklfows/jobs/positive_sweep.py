"""Positive-reply sweep (Blueprint O3), 07:30 CT.

**This job does not sweep anything itself. It calls jobs/pipeline_sweep.py.**

Phase 1 already built `jobs/pipeline_sweep.py` and it is O3 in full: positive
replies with no outbound from Lorenzo in 24 h, booked calls inside 24 h with no
confirmation, proposals older than 7 days with no touch, and the Upwork rooms
waiting, ordered booked > positive > proposal > upwork and inside a kind by
pipeline value then age. Its email pagination is sized against the 20/min limit
on `GET /emails`, its auto-reply and outbound detection are pinned by tests on
the 44 recorded September replies, and its ntfy digest is already redacted for
a public topic.

A second sweep would mean two implementations of "is this reply positive",
two pagination budgets against one rate limit and two digests that can
disagree. So this module is an **entry point, not an engine**: it exists
because Section 6 names an O3 job at 07:30 and because the morning list is
more useful with the KPI dashboard under it. It adds exactly two things:

1. `--kpi` appends the Section 6 dashboard (services/metrics/kpi) to the list,
   so the 07:30 read says both "what is waiting" and "what is off";
2. its own `positive_sweep` Job_Log row recording the delegation and the
   counts, so the schedule has one row per scheduled run even though the work
   is logged under `pipeline_sweep`.

Read-only against every live system: pipeline_sweep has no write path and the
dashboard is built from GETs and local files.

CLI (from "Agentic Worklfows/"):
    python3 jobs/positive_sweep.py --dry-run                 # pull, print, Job_Log rows, no digest
    python3 jobs/positive_sweep.py --now                     # same plus the ntfy digest
    python3 jobs/positive_sweep.py --dry-run --kpi           # list plus the KPI dashboard
    python3 jobs/positive_sweep.py --dry-run --fixtures --as-of 2026-09-21T07:30:00-05:00
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings  # noqa: E402
from shared.ghl import GHL  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.paths import tmp_file  # noqa: E402
from jobs import pipeline_sweep  # noqa: E402
from services.metrics import kpi, sources  # noqa: E402

logger = logging.getLogger("jobs.positive_sweep")

JOB = "positive_sweep"


def run(
    now: datetime,
    dry_run: bool = True,
    with_kpi: bool = False,
    kpi_rows: Optional[List[Dict[str, Any]]] = None,
    job_log_path: Optional[Any] = None,
    stage_files: bool = True,
    **sweep_kwargs
) -> Dict[str, Any]:
    """Delegate to pipeline_sweep, optionally append the KPI dashboard."""
    result = pipeline_sweep.run_sweep(now, dry_run=dry_run, **sweep_kwargs)
    day = sources.ct_day(now)

    dashboard = None
    staged = None
    if with_kpi:
        if kpi_rows is None:
            kpi_rows = build_kpi_rows(now, day, job_log_path=job_log_path)
        dashboard = kpi.render(kpi_rows, day, now)
        if stage_files:
            # Printed to stdout it reaches a process log nobody opens: the
            # scheduled 07:30 run sends pipeline_sweep's own digest and that
            # digest carries no dashboard. Staging it means the morning read
            # still exists after the run.
            staged = write_dashboard(day, dashboard, dry_run=dry_run)

    alerts = [r["metric"] for r in (kpi_rows or []) if r["state"] == kpi.ALERT]
    log_run(JOB, "delegated_%s" % result.get("status", "unknown"), {
        "as_of": now.isoformat(),
        "delegate": pipeline_sweep.JOB_NAME,
        "counts": result.get("counts"),
        "notes": result.get("notes"),
        "kpi_alerts": alerts,
        "kpi_included": bool(with_kpi),
        "staged": staged,
    })

    text = result["digest"]
    if dashboard:
        text = "%s\n\n%s" % (text, dashboard)
    elif kpi_rows:
        # One line, metric names and numbers only, so it can ride along with a
        # digest that goes to a public ntfy topic.
        text = "%s\n\n%s" % (text, kpi.headline(kpi_rows))
    return dict(result, job=JOB, delegate=pipeline_sweep.JOB_NAME,
                dashboard=dashboard, kpi=kpi_rows, text=text, staged=staged)


def write_dashboard(day, dashboard: str, dry_run: bool = False) -> Optional[str]:
    suffix = ".dryrun" if dry_run else ""
    path = tmp_file("kpi_dashboard_%s%s.md" % (day.isoformat(), suffix))
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(dashboard.rstrip() + "\n")
    except OSError as exc:
        logger.warning("could not stage the dashboard at %s: %s", path, exc)
        return None
    return str(path)


def build_kpi_rows(now: datetime, day, job_log_path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """The dashboard for the morning read, built from the same collectors O4 uses."""
    from jobs import daily_metrics

    data = daily_metrics.collect(now, day, notes=[], job_log_path=job_log_path)
    return kpi.build(daily_metrics.kpi_snapshot(data), daily_metrics.kpi_prior(data))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Positive-reply sweep (O3). Delegates to jobs/pipeline_sweep.py.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="pull (read-only), print, Job_Log rows; no digest")
    group.add_argument("--now", action="store_true", help="pull, print, Job_Log rows and send the ntfy digest")
    parser.add_argument("--as-of", help="ISO timestamp used as 'now' (replay / tests)")
    parser.add_argument("--kpi", action="store_true", help="append the Section 6 KPI dashboard")
    parser.add_argument("--fixtures", action="store_true",
                        help="use the recorded September fixtures instead of the Instantly API")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Captured before use_scratch_logs() redirects JOB_LOG_PATH: the dashboard
    # reads the reply engine's rows out of the Job_Log, and a dry run that reads
    # its own empty scratch file reports the engine as silent.
    job_log_source = sources.job_log_read_path()
    if args.dry_run:
        from shared.job_log import use_scratch_logs

        use_scratch_logs("positive_sweep_dryrun")

    now = pipeline_sweep._parse_as_of(args.as_of) if args.as_of else datetime.now(timezone.utc)
    kwargs = {}  # type: Dict[str, Any]
    kpi_rows = None
    if args.fixtures:
        kwargs.update(pipeline_sweep.load_fixtures())
        kwargs["ghl"] = GHL(token=None)
        if args.kpi:
            from jobs import daily_metrics

            fx = daily_metrics.load_fixtures()
            data = daily_metrics.collect(now, sources.ct_day(now), ghl=GHL(token=None), notes=[],
                                         job_log_path=job_log_source, **fx)
            kpi_rows = kpi.build(daily_metrics.kpi_snapshot(data), daily_metrics.kpi_prior(data))

    try:
        result = run(now, dry_run=bool(args.dry_run), with_kpi=bool(args.kpi),
                     kpi_rows=kpi_rows, job_log_path=job_log_source, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the 07:30 job must not fail silently
        # pipeline_sweep constructs its own clients and can raise anywhere; the
        # brief's contract is one Job_Log row per run and an alert on failure.
        log_run(JOB, "failed", {"error": "%s: %s" % (type(exc).__name__, str(exc)[:400]),
                                "as_of": now.isoformat(), "dry_run": bool(args.dry_run)})
        notify("Positive sweep failed", "%s: %s" % (type(exc).__name__, str(exc)[:300]),
               priority="high", tags=["warning"])
        raise
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "kpi"}, indent=1, default=str))
    else:
        print(result["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
