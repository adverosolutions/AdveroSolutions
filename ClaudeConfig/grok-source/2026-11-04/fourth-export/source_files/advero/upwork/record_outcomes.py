#!/usr/bin/env python3
"""Record batch outcomes for the learning loop (append-only, idempotent). No network, no MCP.

Store: outcomes.csv (job_id, outcome, outcome_time_ct, source) is the ONLY place outcomes are written. batch_log.csv rows are
never edited for outcomes (they are written 'pending'); the effective outcome of a job is derived from outcomes.csv:
  selected  if outcomes.csv has any 'selected' row for the job (a late pick overrides an earlier 'skipped')
  skipped   else if it has a 'skipped' row
  pending   otherwise
runs/batch_log_outcomes.csv is a derived, rebuildable view (batch_log + effective outcome) for reading.

Marks 'selected' from: lorenzo_picks.csv rows (time = their run_time_ct, else now) and --select <job_id|url> ... [--time "YYYY-MM-DD HH:MM"]
  for approvals relayed by COO. --skip <job_id|url> ... marks relayed "shown but not picked" jobs (ignored for a job already selected).
Marks 'skipped' for jobs shown in some batch, never picked, and no longer open: not in the latest batch (left the carry-forward),
  24h+ old now, or hired/closed in runs/client_cache.json.
Re-running adds nothing new (one selected row max per job, one skipped row max per job).
Usage: python3 record_outcomes.py [--select ID ...] [--skip ID ...] [--time "YYYY-MM-DD HH:MM"] [--source TEXT] [--root DIR]
"""
import argparse, csv, json, os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_selection import job_id_from_url, norm_id, parse_ct, BATCH_COLS, atomic_write, csv_text, load_json  # noqa: E402

OUT_COLS = ["job_id", "outcome", "outcome_time_ct", "source"]


def read_outcomes(path):
    return list(csv.DictReader(open(path, newline="", encoding="utf-8"))) if os.path.exists(path) else []


def effective(outs):
    eff = {}
    for r in outs:
        k = norm_id(r["job_id"])
        if r["outcome"] == "selected" or k not in eff:
            if eff.get(k, {}).get("outcome") == "selected": continue
            eff[k] = r
    return eff


def run(root=HERE, select=(), sel_time=None, source="COO relay", quiet=False, skip=()):
    root = os.path.abspath(os.path.expanduser(root))
    bpath = os.path.join(root, "batch_log.csv"); opath = os.path.join(root, "outcomes.csv")
    lpath = os.path.join(root, "lorenzo_picks.csv"); cpath = os.path.join(root, "runs", "client_cache.json")
    now = datetime.now(CT); nowt = f"{now:%Y-%m-%d %H:%M} CT"
    batch = list(csv.DictReader(open(bpath, newline="", encoding="utf-8"))) if os.path.exists(bpath) else []
    outs = read_outcomes(opath); eff = effective(outs)
    canon = {norm_id(b["job_id"]): b["job_id"] for b in batch}
    add = []
    def mark(k_raw, outcome, t, src):
        k = norm_id(k_raw)
        cur = eff.get(k, {}).get("outcome")
        if cur == "selected" or (outcome == "skipped" and cur == "skipped"):
            return
        row = dict(job_id=canon.get(k, k_raw), outcome=outcome, outcome_time_ct=t, source=src)
        add.append(row); eff[k] = row
    # selected: lorenzo_picks.csv
    if os.path.exists(lpath):
        for r in csv.DictReader(open(lpath, newline="", encoding="utf-8")):
            k = r.get("job_id") or job_id_from_url(r.get("url"))
            if k: mark(k, "selected", r.get("run_time_ct") or nowt, "lorenzo_picks.csv")
    # selected / skipped: CLI (COO relay)
    cli_t = (sel_time + " CT") if sel_time and "CT" not in sel_time else (sel_time or nowt)
    cid = lambda x: job_id_from_url(x) if ("/" in x or "upwork" in x) else ("~0" + norm_id(x) if norm_id(x).isdigit() else x)
    for x in select:
        mark(cid(x), "selected", cli_t, source)
    for x in skip:
        mark(cid(x), "skipped", cli_t, source)
    # skipped: shown, never picked, no longer open
    if batch:
        latest = batch[-1]["batch_id"]
        in_latest = {norm_id(b["job_id"]) for b in batch if b["batch_id"] == latest}
        cache = {norm_id(k): v for k, v in load_json(cpath, {}).items()}
        last_row = {}
        for b in batch: last_row[norm_id(b["job_id"])] = b
        for k, b in last_row.items():
            if k in eff: continue
            bt = parse_ct(b["batch_time_ct"]); age_now = float(b["job_age_hours_at_batch"] or 0) + (now - bt).total_seconds() / 3600 if bt else 0
            c = cache.get(k) or {}
            why = ("hired/closed in client cache" if c.get("status") == "ok" and (c.get("has_hire") or c.get("closed"))
                   else "past 24h" if age_now >= 24 else "left the carry-forward list" if k not in in_latest else "")
            if why: mark(b["job_id"], "skipped", nowt, f"auto: {why} (last shown {b['batch_id']})")
    if add:
        new = not os.path.exists(opath) or os.path.getsize(opath) == 0
        with open(opath, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=OUT_COLS)
            if new: w.writeheader()
            w.writerows(add)
    # derived view
    if batch:
        view = []
        for b in batch:
            e = eff.get(norm_id(b["job_id"]))
            row = dict(b); row["outcome"] = e["outcome"] if e else "pending"; row["outcome_time_ct"] = e["outcome_time_ct"] if e else ""
            view.append([row.get(c, "") for c in BATCH_COLS])
        os.makedirs(os.path.join(root, "runs"), exist_ok=True)
        atomic_write(os.path.join(root, "runs", "batch_log_outcomes.csv"), csv_text(BATCH_COLS, view))
    jobs = {norm_id(b["job_id"]) for b in batch}
    cnt = {o: sum(1 for k in jobs if eff.get(k, {}).get("outcome") == o) for o in ("selected", "skipped")}
    msg = (f"added {len(add)} ({sum(r['outcome']=='selected' for r in add)} selected, {sum(r['outcome']=='skipped' for r in add)} skipped); "
           f"jobs in batches {len(jobs)}: selected {cnt['selected']}, skipped {cnt['skipped']}, pending {len(jobs)-cnt['selected']-cnt['skipped']}")
    if not quiet: print(msg)
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=HERE)
    ap.add_argument("--select", nargs="*", default=[], help="job_id(s) or Upwork url(s) Lorenzo approved (relayed by COO)")
    ap.add_argument("--skip", nargs="*", default=[], help="job_id(s) or url(s) shown but not picked (relayed by COO)")
    ap.add_argument("--time", help='CT time of the approval, "YYYY-MM-DD HH:MM" (default now)')
    ap.add_argument("--source", default="COO relay")
    a = ap.parse_args()
    run(a.root, a.select, a.time, a.source, skip=a.skip)


if __name__ == "__main__":
    main()
