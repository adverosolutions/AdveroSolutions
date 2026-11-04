#!/usr/bin/env python3
"""Upwork job selection run for Lorenzo: FULL ranked list, no cutoff, no auto-pick (Lorenzo 2026-10-21 10:52/10:54/10:57 CT).

Source: the 3 Vollna RSS feeds only (GET). This script makes NO Upwork MCP/connector calls. Client details come only from
runs/client_cache.json, which the routine agent fills with ONE read-only `find_jobs get` per new job (see cache_client.py).

Each normal run:
  1. score_vollna.collect(): fetch feeds, dedupe, drop already-applied (applied-history CSV), score every other job with the
     unchanged rubric. Rubric exclusions (off-topic category, ads-only, SKIP list...) are FLAGS, not drops.
  2. Append every new non-applied job to picks_log.csv (append-only, dedupe on job_id, same 7 columns; score = rubric total;
     flags go in reason as 'flag: off-topic <label>').
  3. Remember static signals per job in runs/jobs_state.json (tools, category, flags, posted time).
  4. Build the carry-forward set: all of today's (CT) jobs still open + yesterday's jobs with rank >= 60 under 24h old.
     Hard exclusions: already applied, picked (lorenzo_picks.csv or outcomes.csv 'selected'), hired/closed in client_cache.json.
     Anything 24h+ old leaves the list.
  5. Rank score 0-100 with weights.json (score_vollna.rank_score); age is recomputed every run.
  6. Write runs/full_list_today.csv + .md (every job, ranked), append one batch to batch_log.csv,
     write runs/needs_enrichment.json (open jobs not yet in the cache, newest first), then record_outcomes.
  --rerank-only: no feed fetch. Re-ranks from jobs_state + cache, rewrites full_list_today and REPLACES the rows of the
     current (latest, same-day) batch in batch_log.csv; earlier batches are never touched.
Exit: 0 ok, 2 real failure (feeds missing/all empty, scorer crash, log header mismatch), 3 another run holds the lock.
Times are America/Chicago. Usage: python3 run_selection.py [--rerank-only] [--root DIR] [--hours 24] [--no-cache]
"""
import argparse, csv, fcntl, json, os, re, sys, tempfile, urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["run_time_ct", "job_id", "url", "title", "posted_time", "score", "reason"]
BATCH_COLS = ["date_ct", "batch_time_ct", "batch_id", "job_id", "url", "title", "tools_matched", "category", "client_feedback",
              "client_spend", "hire_rate", "job_age_hours_at_batch", "interview_count", "rank_score", "sub_tools", "sub_category",
              "sub_feedback", "sub_spend", "sub_age", "sub_interviews", "rank", "weights_version", "outcome", "outcome_time_ct",
              # LOGGING-ONLY candidate signals (2026-10-21 11:3x CT, signals_proposal_20261021.md). Weight 0: not in rank_score.
              "client_country", "country_bucket", "engagement_type"]
LIST_COLS = ["rank", "score", "title", "link", "posted_time", "flags_reason", "age_h", "tools", "category", "client_spend",
             "client_feedback", "hire_rate", "interviewing", "client_data", "pts_tools", "pts_category", "pts_feedback", "pts_spend",
             "pts_age", "pts_interviews", "rubric_score", "job_id"]
CARRY_YESTERDAY_MIN = 60


def job_id_from_url(url):
    """Stable id: '~0<digits>' Upwork cipher if present, else the lowercased URL slug."""
    u = urllib.parse.unquote(urllib.parse.unquote((url or "").strip()))
    m = re.search(r"~0?([0-9]{15,})", u)
    if m:
        return "~0" + m.group(1)
    path = urllib.parse.urlparse(u).path.rstrip("/")
    return path.rsplit("/", 1)[-1].lower() if path else u.lower()


def norm_id(x):
    """Comparison form: strip '~' and leading zeros from cipher ids; slugs lowercased."""
    x = (x or "").strip().lower().lstrip("~")
    return x.lstrip("0") if x.isdigit() else x


def fail(msg, code=2):
    print(f"FAIL {datetime.now(CT):%Y-%m-%d %H:%M} CT: {msg}")
    sys.exit(code)


def parse_ct(s):
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", s or "")
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=CT) if m else None


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def csv_text(cols, rows):
    import io
    b = io.StringIO(); w = csv.writer(b); w.writerow(cols); w.writerows(rows); return b.getvalue()


def load_json(path, default):
    try:
        return json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else default
    except Exception:
        return default


def paths(root):
    r = os.path.abspath(os.path.expanduser(root)); runs = os.path.join(r, "runs")
    return dict(root=r, runs=runs, log=os.path.join(r, "picks_log.csv"), lorenzo=os.path.join(r, "lorenzo_picks.csv"),
                batch=os.path.join(r, "batch_log.csv"), outcomes=os.path.join(r, "outcomes.csv"), weights=os.path.join(r, "weights.json"),
                cache=os.path.join(runs, "client_cache.json"), state=os.path.join(runs, "jobs_state.json"),
                needs=os.path.join(runs, "needs_enrichment.json"), list_csv=os.path.join(runs, "full_list_today.csv"),
                list_md=os.path.join(runs, "full_list_today.md"), scored=os.path.join(runs, "scored_all_latest.csv"))


def picked_ids(P):
    ids = set()
    if os.path.exists(P["lorenzo"]):
        for r in csv.DictReader(open(P["lorenzo"], newline="", encoding="utf-8")):
            k = norm_id(r.get("job_id") or job_id_from_url(r.get("url")))
            if k: ids.add(k)
    if os.path.exists(P["outcomes"]):
        for r in csv.DictReader(open(P["outcomes"], newline="", encoding="utf-8")):
            if r.get("outcome") == "selected": ids.add(norm_id(r.get("job_id")))
    return ids


def backfill_from_log(sv, P, state, today, applied_ids, applied_titles):
    """Today's and yesterday's picks_log rows with no Vollna item in state (logged before 2026-10-21 10:55 CT): approximate static signals."""
    n = 0
    yday = f"{datetime.strptime(today, '%Y-%m-%d') - timedelta(days=1):%Y-%m-%d}"
    if not os.path.exists(P["log"]):
        return 0
    for r in csv.DictReader(open(P["log"], newline="", encoding="utf-8")):
        k = r.get("job_id") or job_id_from_url(r.get("url"))
        if not k or k in state or (r.get("run_time_ct") or "")[:10] not in (today, yday):
            continue
        if sv.job_id(r.get("url")) in applied_ids or sv.norm_title(r.get("title") or "") in applied_titles:
            continue
        tools = [t.strip() for t in (re.search(r"tools: ([^;]*)", r.get("reason") or "") or [None, ""])[1].split(",") if t.strip() in sv.TOOL_W]
        tool_raw = sum(sv.TOOL_W[t] for t in tools)
        try: rub = float(r.get("score") or 0)
        except ValueError: rub = 0
        posted = parse_ct(r.get("posted_time")) or parse_ct(r.get("run_time_ct"))
        state[k] = dict(url=r["url"], title=r["title"], posted_utc=posted.astimezone(timezone.utc).isoformat(), posted_ct=r.get("posted_time"),
                        feed=(re.search(r"feed: (.*)$", r.get("reason") or "") or [None, ""])[1], cats=[], tools=tools,
                        tools_sub=round(min(1, tool_raw / 30), 4), category_sub=round(0.25 + 0.5 * min(1, rub / 100), 4),
                        flags=["backfilled from picks_log (item no longer in feed; category approximated)"], rubric=rub,
                        first_seen_ct=r.get("run_time_ct"))
        n += 1
    return n


def build_list(sv, P, state, now, use_cache, applied_ids, applied_titles):
    version, W = sv.load_weights(P["weights"])
    cache = load_json(P["cache"], {}) if use_cache else {}
    cache_n = {norm_id(k): v for k, v in cache.items()}
    picked = picked_ids(P)
    today = f"{now:%Y-%m-%d}"; yday = f"{now - timedelta(days=1):%Y-%m-%d}"
    rows, ex = [], dict(picked=0, hired_closed=0, applied=0, aged_out=0, yesterday_below_min=0)
    for k, s in state.items():
        posted = datetime.fromisoformat(s["posted_utc"]).astimezone(CT)
        first = (s.get("first_seen_ct") or "")[:10]; pday = f"{posted:%Y-%m-%d}"
        is_today = today in (first, pday); is_yday = not is_today and yday in (first, pday)
        if not (is_today or is_yday):
            continue
        nk = norm_id(k)
        if nk in picked: ex["picked"] += 1; continue
        if sv.job_id(s["url"]) in applied_ids or sv.norm_title(s["title"]) in applied_titles: ex["applied"] += 1; continue
        c = cache_n.get(nk) or {}
        if c.get("status") == "ok" and (c.get("has_hire") or c.get("closed")): ex["hired_closed"] += 1; continue
        age_h = max(0.0, (now - posted).total_seconds() / 3600)
        if age_h >= 24: ex["aged_out"] += 1; continue
        cl = c if c.get("status") == "ok" else {}
        cs = sv.client_subs(dict(feedback=cl.get("client_feedback"), spend=cl.get("client_spend"), interviewing=cl.get("interviewing")))
        subs = dict(tools=s["tools_sub"], category=s["category_sub"], feedback=cs["feedback"][0], spend=cs["spend"][0],
                    age=round(sv.age_sub(age_h), 4), interviews=cs["interviews"][0])
        total, pts = sv.rank_score(subs, W)
        if is_yday and total < CARRY_YESTERDAY_MIN: ex["yesterday_below_min"] += 1; continue
        na = lambda key, val: "n/a" if cs[key][1] else val
        rows.append(dict(k=k, s=s, posted=posted, age_h=age_h, total=total, pts=pts,
                         feedback=na("feedback", cl.get("client_feedback")), spend=na("spend", cl.get("client_spend")),
                         hire=cl.get("hire_rate") if cl.get("hire_rate") is not None else "n/a",
                         interviewing=na("interviews", cl.get("interviewing")),
                         client_data="cache " + (c.get("status") or "") if c else "none (n/a = neutral half points)",
                         country=(c.get("client_country") or "unknown") if c.get("status") == "ok" else "unknown",
                         carried="carried from yesterday" if is_yday else ""))
    rows.sort(key=lambda r: (-r["total"], -r["posted"].timestamp()))
    return rows, ex, version, W, cache_n


def reason_text(r):
    s = r["s"]; parts = []
    parts += [f"flag: {f}" for f in s.get("flags", [])]
    if r["carried"]: parts.append(r["carried"])
    parts.append("tools: " + (", ".join(t for t in s.get("tools", []) if t != "APIs/webhooks") or "none"))
    return "; ".join(parts)


def write_outputs(P, rows, now, version, W, ex, cache_n, summary):
    L = []
    for i, r in enumerate(rows, 1):
        s = r["s"]; p = r["pts"]
        L.append([i, r["total"], s["title"], s["url"], s.get("posted_ct", ""), reason_text(r), round(r["age_h"], 1),
                  ", ".join(s.get("tools", [])), " / ".join(s.get("cats", [])) or "n/a", r["spend"], r["feedback"], r["hire"],
                  r["interviewing"], r["client_data"], p["tools"], p["category"], p["feedback"], p["spend"], p["age"], p["interviews"],
                  s.get("rubric", ""), r["k"]])
    atomic_write(P["list_csv"], csv_text(LIST_COLS, L))
    md = [f"# Upwork full list, {now:%a %b %-d, %Y} (updated {now:%-I:%M %p} CT)", "",
          "Every open job from today's Vollna feeds, ranked by rank score (0-100). No cutoff, nothing auto-picked: Lorenzo picks.",
          f"Weights {version}: " + ", ".join(f"{k} {W[k]:g}" for k in W) + ". Client signals not available = n/a (neutral half points).",
          f"Dropped (hard exclusions only): picked {ex['picked']}, already applied {ex['applied']}, hired/closed {ex['hired_closed']}; "
          f"aged out (24h+) {ex['aged_out']}; yesterday's below {CARRY_YESTERDAY_MIN} {ex['yesterday_below_min']}.",
          summary, "", "| # | Rank | Title | Posted (CT) | Age h | Spend | Feedback | Hire rate | Interviewing | Flags / reason |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for x in L:
        t = str(x[2]).replace("|", "/")
        md.append(f"| {x[0]} | {x[1]} | [{t}]({x[3]}) | {x[4]} | {x[6]} | {x[9]} | {x[10]} | {x[11]} | {x[12]} | {str(x[5]).replace('|', '/')} |")
    atomic_write(P["list_md"], "\n".join(md) + "\n")
    need = [dict(job_id=r["k"], url=r["s"]["url"], title=r["s"]["title"], posted_ct=r["s"].get("posted_ct", ""))
            for r in sorted(rows, key=lambda r: -r["posted"].timestamp()) if norm_id(r["k"]) not in cache_n]
    atomic_write(P["needs"], json.dumps(dict(generated_ct=f"{now:%Y-%m-%d %H:%M} CT", count=len(need),
                 rule="ONE read-only find_jobs get per job, ~3s apart, never for a job already in client_cache.json; then cache_client.py, then run_selection.py --rerank-only",
                 jobs=need), indent=1) + "\n")
    return L, need


def write_batch(P, rows, now, version, rerank):
    import signals  # logging-only signals, weight 0
    bt = f"{now:%Y-%m-%d %H:%M} CT"; bid = f"b{now:%Y%m%d-%H%M}"
    new = []
    def batch_rows(bt, bid):
        out = []
        for i, r in enumerate(rows, 1):
            s = r["s"]; p = r["pts"]
            out.append([f"{now:%Y-%m-%d}", bt, bid, r["k"], s["url"], s["title"], ", ".join(s.get("tools", [])),
                        " / ".join(s.get("cats", [])) or "n/a", r["feedback"], r["spend"], r["hire"], round(r["age_h"], 2),
                        r["interviewing"], r["total"], p["tools"], p["category"], p["feedback"], p["spend"], p["age"], p["interviews"],
                        i, version, "pending", "", r["country"], signals.country_bucket(r["country"] if r["country"] != "unknown" else ""),
                        s.get("engagement") or "unknown"])
        return out
    exists = os.path.exists(P["batch"]) and os.path.getsize(P["batch"]) > 0
    if rerank and exists:
        old = list(csv.reader(open(P["batch"], newline="", encoding="utf-8")))
        if old[0] != BATCH_COLS:
            fail(f"batch_log header mismatch in {P['batch']}")
        last = old[-1] if len(old) > 1 else None
        if last and last[0] == f"{now:%Y-%m-%d}":
            keep = [x for x in old[1:] if x[2] != last[2]]
            new = batch_rows(last[1], last[2])
            ids = {x[3] for x in new}
            # jobs shown in this batch that have since left the list (picked, hired/closed) keep their original row
            gone, seen_gone = [], set()
            for x in old[1:]:
                if x[2] == last[2] and x[3] not in ids and x[3] not in seen_gone:
                    gone.append(x); seen_gone.add(x[3])
            atomic_write(P["batch"], csv_text(BATCH_COLS, keep + new + gone))
            return last[2], len(new), "replaced current batch"
    new = batch_rows(bt, bid)
    with open(P["batch"], "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists: w.writerow(BATCH_COLS)
        w.writerows(new)
    return bid, len(new), "appended new batch"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=HERE, help="folder holding picks_log.csv, lorenzo_picks.csv, batch_log.csv, weights.json, runs/")
    ap.add_argument("--hours", type=float, default=24, help="feed look-back; 24 = every item the feeds return")
    ap.add_argument("--feeds", default="/workspace/vollna_rss.txt")
    ap.add_argument("--history", default="/home/box/Downloads/proposals_2026_10_20_20_16_16.csv")
    ap.add_argument("--rerank-only", action="store_true", help="no feed fetch; re-rank from jobs_state + client_cache")
    ap.add_argument("--no-cache", action="store_true", help="ignore client_cache.json (all client signals n/a)")
    ap.add_argument("--no-outcomes", action="store_true", help="skip record_outcomes at the end")
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    import score_vollna as sv
    P = paths(a.root)
    os.makedirs(P["runs"], exist_ok=True)
    lock = open(os.path.join(P["runs"], ".run_selection.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fail("another run_selection.py is running", 3)
    if not os.path.isfile(a.history):
        fail(f"applied-history CSV unreadable: {a.history}")
    _, _, applied_ids, applied_titles, _, _ = sv.load_history(a.history)
    now = datetime.now(CT); today = f"{now:%Y-%m-%d}"
    state = load_json(P["state"], {})
    summary = ""
    if not a.rerank_only:
        if not os.path.isfile(a.feeds):
            fail(f"feeds file unreadable: {a.feeds}")
        feeds = [l for l in open(a.feeds) if "\t" in l]
        try:
            res, per_feed, window = sv.collect(a.feeds, a.history, a.hours)
        except Exception as e:
            fail(f"scorer crashed: {type(e).__name__}: {e}")
        if not any(per_feed.values()):
            fail(f"all {len(feeds)} feeds returned 0 items (unreachable or not RSS)")
        empty = [n for n in (l.split("\t")[0] for l in feeds) if per_feed.get(n, 0) == 0]
        # scored_all_latest.csv (all jobs, for compare lookups)
        sc = [[j["title"], j["link"], j["feed"], j["pub"].astimezone(CT).strftime("%Y-%m-%d %H:%M CT"), s.get("excluded", ""),
               s.get("total", ""), ", ".join(s.get("tools", []))] for j, s in res]
        atomic_write(P["scored"], csv_text(["title", "url", "feed", "posted_ct", "excluded", "total", "tools"], sc))
        # picks_log append
        new_file = not os.path.exists(P["log"]) or os.path.getsize(P["log"]) == 0
        seen = set(); needs_nl = False
        if not new_file:
            with open(P["log"], newline="", encoding="utf-8") as f:
                rd = csv.reader(f); hdr = next(rd, [])
                if hdr != COLS:
                    fail(f"picks log header mismatch in {P['log']}: {hdr}")
                for row in rd:
                    if len(row) > 2: seen.add(norm_id(row[1] or job_id_from_url(row[2])))
            with open(P["log"], "rb") as f:
                f.seek(-1, 2); needs_nl = f.read(1) not in (b"\n", b"\r")
        applied = [x for x in res if x[1].get("excluded") == "already applied"]
        kept = [x for x in res if x[1].get("excluded") != "already applied"]
        new_rows, dupes, flagged = [], 0, 0
        for j, s in kept:
            k = job_id_from_url(j["link"])
            tsub, csub, flags = sv.static_subs(j, s)
            flagged += bool(flags)
            st = state.get(k, {})
            import signals  # logging-only (weight 0)
            eng = signals.engagement_type(j["title"], j["desc"], j["btype"])[0]
            state[k] = dict(url=j["link"], title=re.sub(r"\s+", " ", j["title"]).strip(), posted_utc=j["pub"].astimezone(timezone.utc).isoformat(),
                            posted_ct=j["pub"].astimezone(CT).strftime("%Y-%m-%d %H:%M CT"), feed=j["feed"], cats=j["cats"],
                            tools=s.get("tools", []), tools_sub=tsub, category_sub=csub, flags=flags, rubric=s.get("total", 0),
                            first_seen_ct=st.get("first_seen_ct") or f"{now:%Y-%m-%d %H:%M} CT", engagement=eng)
            if norm_id(k) in seen:
                dupes += 1; continue
            seen.add(norm_id(k))
            hist = s.get("hist")
            reason = "tools: " + (", ".join(t for t in s.get("tools", []) if t != "APIs/webhooks") or "none")
            reason += "".join(f"; flag: {f}" for f in flags)
            reason += f"; history_fit {hist:+d}" if isinstance(hist, int) else ""
            reason += f"; closest past win: {s['sim_to']}" if s.get("sim_to") else ""
            reason += f"; feed: {j['feed']}"
            new_rows.append([f"{now:%Y-%m-%d %H:%M} CT", k, j["link"], state[k]["title"], state[k]["posted_ct"], s.get("total", 0),
                             re.sub(r"\s+", " ", reason).strip()])
        with open(P["log"], "a", newline="", encoding="utf-8") as f:
            if needs_nl: f.write("\n")
            w = csv.writer(f)
            if new_file: w.writerow(COLS)
            w.writerows(new_rows)
        items = sum(per_feed.values())
        summary = (f"Run {now:%H:%M} CT: feed items {items} ({', '.join(f'{n} {c}' for n, c in per_feed.items())}); unique jobs {len(res)}; "
                   f"already applied (dropped) {len(applied)}; kept {len(kept)} (rubric-flagged {flagged}); "
                   f"new to picks_log {len(new_rows)}; already logged {dupes}" + (f"; WARN empty feeds: {', '.join(empty)}" if empty else ""))
    bf = backfill_from_log(sv, P, state, today, applied_ids, applied_titles)
    atomic_write(P["state"], json.dumps(state, indent=1, sort_keys=True) + "\n")
    rows, ex, version, W, cache_n = build_list(sv, P, state, now, not a.no_cache, applied_ids, applied_titles)
    if a.rerank_only:
        summary = f"Re-rank {now:%H:%M} CT (no feed fetch, client cache {'on' if not a.no_cache else 'off'})"
    L, need = write_outputs(P, rows, now, version, W, ex, cache_n, summary + (f"; backfilled {bf}" if bf else ""))
    bid, nb, how = write_batch(P, rows, now, version, a.rerank_only)
    oc = ""
    if not a.no_outcomes:
        import record_outcomes
        oc = "; outcomes: " + record_outcomes.run(P["root"], quiet=True)
    print(f"OK {summary}{'; backfilled ' + str(bf) if bf else ''}; full list {len(L)} jobs (weights {version}); dropped picked {ex['picked']}, "
          f"applied {ex['applied']}, hired/closed {ex['hired_closed']}, aged out {ex['aged_out']}, yday<{CARRY_YESTERDAY_MIN} {ex['yesterday_below_min']}; "
          f"batch {bid} {how} ({nb} rows); needs enrichment {len(need)}{oc} -> {P['list_md']}")


if __name__ == "__main__":
    main()
