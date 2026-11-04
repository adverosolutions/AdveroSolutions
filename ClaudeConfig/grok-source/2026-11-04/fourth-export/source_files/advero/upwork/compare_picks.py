#!/usr/bin/env python3
"""Compare the bot's top-ranked Upwork jobs with Lorenzo's own picks (read-only).

Since 2026-10-21 10:55 CT picks_log.csv holds EVERY job (no cutoff), so the bot's "picks" for comparison are its TOP-RANKED jobs:
  per job, its best rank_score in any batch that day (batch_log.csv; picked jobs leave later batches, so best-ever is used),
  falling back to the picks_log rubric score for jobs with no batch row (e.g. Oct 20). Then optional --min on that score,
  then the top --top N (default 12; 0 = all) per CT date.
Inputs:
  ~/advero/upwork/picks_log.csv      every job seen (appended by run_selection.py)
  ~/advero/upwork/batch_log.csv      rank_score per job per batch
  ~/advero/upwork/lorenzo_picks.csv  Lorenzo's picks (he or an agent adds rows; url is enough, job_id is derived)
Match on job_id (derived from the url when blank), falling back to the normalized url.
Prints bot-only, Lorenzo-only and shared (title, url, bot score), then
match rate = shared / union and shared / Lorenzo picks.
For Lorenzo-only jobs it looks up the bot's score in runs/scored_all_latest.csv and scored_all_*.csv
(below 63, excluded, or never seen in the feed window).
Usage: python3 compare_picks.py [--date YYYY-MM-DD | --since YYYY-MM-DD] [--top 12] [--min 0] [--out report.md]
Date filter uses run_time_ct (falls back to posted_time). Rows with no date are always kept.
"""
import argparse, csv, glob, os, re, sys, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_selection import job_id_from_url, norm_id, COLS  # noqa: E402

CT = ZoneInfo("America/Chicago")
HERE = os.path.expanduser("~/advero/upwork")


def norm_url(u):
    u = urllib.parse.unquote(urllib.parse.unquote((u or "").strip())).lower()
    p = urllib.parse.urlparse(u)
    return (p.netloc.replace("www.", "") + p.path).rstrip("/")


def row_date(r):
    for k in ("run_time_ct", "posted_time"):
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", r.get(k) or "")
        if m:
            return m.group(1)
    return ""


def load(path, a):
    if not os.path.exists(path):
        return [], f"missing: {path}"
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not any((r.get(c) or "").strip() for c in COLS):
                continue
            d = row_date(r)
            if d and a.date and d != a.date:
                continue
            if d and a.since and d < a.since:
                continue
            r["_key"] = norm_id(r.get("job_id") or job_id_from_url(r.get("url"))) or norm_url(r.get("url"))
            r["_url"] = norm_url(r.get("url"))
            rows.append(r)
    return rows, ""


def scored_lookup():
    """job key -> (score or excluded reason, file). Newest file wins."""
    files = sorted(glob.glob(os.path.join(HERE, "scored_all_*.csv")) + glob.glob(os.path.join(HERE, "runs", "scored_all_latest.csv")),
                   key=os.path.getmtime)
    out = {}
    for fp in files:
        try:
            for r in csv.DictReader(open(fp, newline="", encoding="utf-8")):
                k = norm_id(job_id_from_url(r.get("url")))
                v = f"excluded: {r['excluded']}" if r.get("excluded") else (r.get("total") or "")
                out[k] = (v, os.path.basename(fp))
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default=os.path.join(HERE, "picks_log.csv"))
    ap.add_argument("--lorenzo", default=os.path.join(HERE, "lorenzo_picks.csv"))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--date", help="only rows from this CT date (YYYY-MM-DD)")
    g.add_argument("--since", help="only rows on/after this CT date (YYYY-MM-DD)")
    ap.add_argument("--out", help="also write a markdown report here")
    ap.add_argument("--top", type=int, default=12, help="bot picks = top N ranked jobs per CT date (0 = all)")
    ap.add_argument("--min", type=float, default=0, help="only jobs with best score >= this count as bot picks")
    ap.add_argument("--batch", default=os.path.join(HERE, "batch_log.csv"))
    a = ap.parse_args()

    bot, e1 = load(a.bot, a)
    lor, e2 = load(a.lorenzo, a)
    for e in (e1, e2):
        if e:
            print("NOTE", e)

    best = {}  # key -> (best rank_score, best rank, date)
    if os.path.exists(a.batch):
        for b in csv.DictReader(open(a.batch, newline="", encoding="utf-8")):
            d = b.get("date_ct", "")
            if (a.date and d != a.date) or (a.since and d < a.since):
                continue
            k = norm_id(b.get("job_id") or job_id_from_url(b.get("url")))
            try: sc_, rk = float(b["rank_score"]), int(b["rank"])
            except (ValueError, KeyError): continue
            o = best.get(k)
            best[k] = (max(sc_, o[0]) if o else sc_, min(rk, o[1]) if o else rk, d)
    everyone = {}
    for r in bot:
        everyone.setdefault(r["_key"], r)
    for k, r in everyone.items():
        if k in best:
            r["_score"], r["_src"] = best[k][0], f"rank {best[k][0]:g} (best #{best[k][1]})"
        else:
            try: r["_score"] = float(r.get("score") or 0)
            except ValueError: r["_score"] = 0.0
            r["_src"] = f"rubric {r.get('score')} (no batch row)"
        r["_date"] = best[k][2] if k in best else row_date(r)
    bot_by, per_day = {}, {}
    for k, r in sorted(everyone.items(), key=lambda kv: -kv[1]["_score"]):
        if r["_score"] < a.min:
            continue
        n = per_day.get(r["_date"], 0)
        if a.top and n >= a.top:
            continue
        per_day[r["_date"]] = n + 1
        bot_by[k] = r
    bot_url = {r["_url"]: k for k, r in everyone.items() if r["_url"]}
    lor_by = {}
    for r in lor:
        k = r["_key"] if r["_key"] in everyone else bot_url.get(r["_url"], r["_key"])  # url fallback
        lor_by.setdefault(k, r)

    shared = [k for k in bot_by if k in lor_by]
    bot_only = [k for k in bot_by if k not in lor_by]
    lor_only = [k for k in lor_by if k not in bot_by]
    union = len(set(bot_by) | set(lor_by))
    sc = scored_lookup() if lor_only else {}

    def line(r, score):
        return f"- {r.get('title') or '(no title)'} | {r.get('url')} | bot score: {score}"

    flt = f"date {a.date}" if a.date else f"since {a.since}" if a.since else "all dates"
    L = [f"# Upwork picks: bot vs Lorenzo ({flt})",
         f"Generated {datetime.now(CT):%Y-%m-%d %H:%M} CT. Bot picks = top {a.top or 'all'} ranked per day"
         f"{f' with score >= {a.min:g}' if a.min else ''}: {len(bot_by)} (of {len(everyone)} jobs in the log). Lorenzo picks: {len(lor_by)}.", ""]
    L.append(f"## Shared ({len(shared)})")
    L += [line(bot_by[k], bot_by[k]["_src"]) for k in shared] or ["- none"]
    L.append(f"\n## Bot only ({len(bot_only)})")
    L += [line(bot_by[k], bot_by[k]["_src"]) for k in bot_only] or ["- none"]
    L.append(f"\n## Lorenzo only ({len(lor_only)})")
    for k in lor_only:
        if k in everyone:
            L.append(line(lor_by[k], everyone[k]["_src"] + " - in the full list but below the bot's top cut"))
            continue
        v, fp = sc.get(k, ("not seen in any scored file (outside feed window or not in Vollna feeds)", ""))
        L.append(line(lor_by[k], v + (f" ({fp})" if fp else "")))
    if not lor_only:
        L.append("- none")
    L.append("\n## Match rate")
    L.append(f"- shared / union: {len(shared)}/{union} = {len(shared)/union:.0%}" if union else "- shared / union: n/a (no picks)")
    L.append(f"- shared / Lorenzo picks: {len(shared)}/{len(lor_by)} = {len(shared)/len(lor_by):.0%}" if lor_by
             else "- shared / Lorenzo picks: n/a (lorenzo_picks.csv has no rows yet)")
    L.append("\n## Caveat")
    L.append("- Client signals (spend, hires, reviews) are absent from Vollna RSS, so rubric item 1 never applies: every job is "
             "scored as a thin/unknown client on keyword fit, tool depth and similarity to past wins. Lorenzo sees client stats on "
             "Upwork, so some differences are expected from that alone.")
    L.append("- Client signals now come from runs/client_cache.json (one find_jobs get per new job, filled by the routine agent); jobs not yet enriched get neutral half points.")
    L.append("- Already-applied exclusion uses the static Oct 20 proposals export; jobs applied to after that are not excluded.")
    txt = "\n".join(L)
    print(txt)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
