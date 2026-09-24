"""Offer Intel: Maker School wins -> ranked offers (MAKER_SCHOOL_WINS_PLAN.md).

Read-only on Skool. Paid model calls only with ALLOW_PAID_CALLS=1, after
--preflight has printed the price. Data stays under .tmp/offer_intel/.
Runbook: runbooks/offer_intel.md.

CLI (from "Agentic Worklfows/"):
    python3 jobs/offer_intel.py rehearse                    # whole pipeline on made-up posts, free, no network
    python3 jobs/offer_intel.py look                        # Mac: log-in check, categories, payload keys
    python3 jobs/offer_intel.py collect --url "<wins category URL>" --max-posts 40
    python3 jobs/offer_intel.py analyze --sample 30 --preflight          # price only, spends nothing
    ALLOW_PAID_CALLS=1 python3 jobs/offer_intel.py analyze --sample 30   # gate + extract, billed
    python3 jobs/offer_intel.py report [--review]           # free: CSVs, digest, hand-check sheet
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings  # noqa: E402,F401  (loads .env: the Anthropic key on the Mac)
from shared.job_log import log_run  # noqa: E402
from shared.paths import tmp_dir  # noqa: E402
from services.offer_intel import analyze, files, rehearsal, render, rollup, skool_read, taxonomy  # noqa: E402

logger = logging.getLogger("jobs.offer_intel")

JOB = "offer_intel"
REHEARSAL_AS_OF = "2026-09-24T12:00:00+00:00"
REVIEW_LIMIT = 30  # the hand check covers the newest 30 analyzed posts


def _parse_day(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ steps
def do_look(group: str, headless: bool) -> Dict[str, Any]:
    result = asyncio.run(skool_read.look(group, headless=headless))
    log_run(JOB, "look_ok", {"group": group, "labels": len(result["labels"]),
                             "wins_labels": result["wins_labels"], "shape": result["shape"]})
    return result


def do_collect(url: str, max_pages: int, max_posts: int, since: Optional[datetime], threads: bool,
               headless: bool) -> Dict[str, Any]:
    result = asyncio.run(skool_read.collect(url, max_pages=max_pages, max_posts=max_posts, since=since,
                                            threads=threads, headless=headless))
    log_run(JOB, "collect_%s" % result["status"], result)
    return result


def select(sample: int, force: bool) -> List[Dict[str, Any]]:
    todo = analyze.newest_first(analyze.pending(files.all_raw(), force=force))
    return todo[:sample] if sample else todo


def do_analyze(sample: int, force: bool, preflight: bool, now: datetime) -> Dict[str, Any]:
    todo = select(sample, force)
    price = analyze.estimate(todo)
    if preflight:
        log_run(JOB, "analyze_preflight", price)
        return {"status": "preflight", "estimate": price}
    result = analyze.run(todo, now=now)
    result["estimate"] = price
    log_run(JOB, "analyze_%s" % result["status"], {"counts": result["counts"], "errors": result["errors"][:5],
                                                   "estimate": price})
    return result


def do_report(as_of: datetime, review: bool, new_days: int = 7) -> Dict[str, Any]:
    raws = files.all_raw()
    done = files.all_analyzed()
    data = taxonomy.load()
    rows = rollup.win_rows(raws, done, data)
    ranked = rollup.patterns(rows, as_of, data)
    picks = rollup.candidates(ranked)
    people = rollup.winners(rows)
    out = files.out_dir()
    written = {
        "wins_csv": render.write_csv(out / "wins.csv", rows, rollup.WIN_COLUMNS),
        "patterns_csv": render.write_csv(out / "patterns.csv", ranked, render.PATTERN_COLUMNS),
        "winners_csv": render.write_csv(out / "winners.csv", people, render.WINNER_COLUMNS),
    }
    text = render.digest(rows, ranked, picks, rollup.unmatched(rows), as_of,
                         new_since=as_of - timedelta(days=new_days), analyzed_count=len(done))
    digest_path = out / ("digest_%s.md" % as_of.strftime("%Y-%m-%d"))
    digest_path.write_text(text, encoding="utf-8")
    written["digest"] = str(digest_path)
    if review:
        by_new = sorted(done, key=lambda r: str(r.get("analyzed_at") or ""), reverse=True)[:REVIEW_LIMIT]
        review_path = out / "hand_check.md"
        review_path.write_text(render.review_sheet(raws, by_new), encoding="utf-8")
        written["hand_check"] = str(review_path)
    summary = {"raw": len(raws), "analyzed": len(done), "wins": len(rows), "patterns": len(ranked),
               "winners": len(people), "picks": [p["pattern"] for p in picks],
               "push_line": render.push_line(rows, ranked, len(done)), "files": written}
    log_run(JOB, "report_ok", dict(summary, files=sorted(written)))
    return summary


def do_rehearse() -> Dict[str, Any]:
    """Made-up posts, fake model answers, a scratch data folder. Free and offline."""
    os.environ["LLM_FAKE"] = "1"
    os.environ["OFFER_INTEL_DIR"] = str(tmp_dir() / "offer_intel_rehearsal")
    for name in ("raw", "analyzed", "out"):
        for path in files.sub(name).glob("*"):
            path.unlink()
    rehearsal.install_fakes()
    now = datetime.fromisoformat(REHEARSAL_AS_OF)
    records = rehearsal.fixture_records(stamp=now.isoformat())
    for record in records:
        files.save_raw(record)
    analyzed = do_analyze(sample=0, force=True, preflight=False, now=now)
    report = do_report(now, review=True)
    log_run(JOB, "rehearse_ok", {"posts": len(records), "counts": analyzed["counts"], "wins": report["wins"],
                                 "patterns": report["patterns"]})
    return {"posts": len(records), "analyze": analyzed, "report": report,
            "data_dir": os.environ["OFFER_INTEL_DIR"]}


# -------------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Offer Intel: Maker School wins -> ranked offers.")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    p = sub.add_parser("look", help="Mac only: log-in check, list the group's categories")
    p.add_argument("--group", default=skool_read.DEFAULT_GROUP)
    p.add_argument("--headless", action="store_true")

    p = sub.add_parser("collect", help="Mac only: read wins posts into .tmp/offer_intel/raw/")
    p.add_argument("--url", required=True, help="the Wins category page exactly as the browser shows it")
    p.add_argument("--max-pages", type=int, default=3)
    p.add_argument("--max-posts", type=int, default=40)
    p.add_argument("--since", help="YYYY-MM-DD: skip posts created before this day")
    p.add_argument("--no-threads", action="store_true", help="skip opening each post for the author's replies")
    p.add_argument("--headless", action="store_true")

    p = sub.add_parser("analyze", help="gate + extract the posts not analyzed yet (billed)")
    p.add_argument("--sample", type=int, default=0, help="only the N newest pending posts")
    p.add_argument("--force", action="store_true", help="re-analyze posts already done")
    p.add_argument("--preflight", action="store_true", help="print the price and exit; spends nothing")

    p = sub.add_parser("report", help="free: CSVs, digest, and with --review the hand-check sheet")
    p.add_argument("--review", action="store_true")
    p.add_argument("--as-of", help="YYYY-MM-DD (default: now)")

    sub.add_parser("rehearse", help="whole pipeline on made-up posts; free, offline")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if args.cmd == "look":
            result = do_look(args.group, args.headless)
        elif args.cmd == "collect":
            result = do_collect(args.url, args.max_pages, args.max_posts, _parse_day(args.since),
                                not args.no_threads, args.headless)
        elif args.cmd == "analyze":
            result = do_analyze(args.sample, args.force, args.preflight, now)
        elif args.cmd == "report":
            result = do_report(_parse_day(args.as_of) or now, args.review)
        else:
            result = do_rehearse()
    except analyze.PaidCallsOff as exc:
        log_run(JOB, "analyze_paid_calls_off", {"detail": str(exc)})
        print("STOPPED: %s" % exc)
        return 2
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
