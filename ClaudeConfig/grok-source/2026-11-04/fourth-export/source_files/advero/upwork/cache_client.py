#!/usr/bin/env python3
"""Upsert ONE job's client details into ~/advero/upwork/runs/client_cache.json (atomic, locked). No network, no MCP.

The routine agent makes the single read-only Upwork `find_jobs get` call per NEW job (from runs/needs_enrichment.json),
then hands the result here. Scripts never call the connector.

Input (pick one):
  --from-get FILE|-      raw `find_jobs get` output (JSON, any text around it is ignored); fields are mapped as in
                         runs/enrich_build_20261021.py. Use --job-id/--url too if the output has no id.
  --json '{...}' | stdin a JSON object with the cache fields below (stdin is read when nothing else is given)
  CLI field flags        --job-id --url --client-feedback --client-spend --hire-rate --total-hires --interviewing
                         --invites --proposals --has-hire --closed --fetched-ct --status ok|error --error
  --seed-dir DIR         every *.txt raw get output in DIR (used once to seed from today's 20 enriched picks)
Cache fields: job_id, url, title, client_feedback, feedback_count, client_spend, hire_rate, total_hires, interviewing,
              invites, proposals, has_hire, closed, workflow_status, client_country, client_state, client_timezone,
              fetched_ct, status (ok|error), error, source
Rules: one attempt per job. An existing entry (ok OR error) is final and is kept; pass --overwrite only on Lorenzo/COO request.
Mapping from find_jobs get: client_feedback = client_record.feedback_score only if feedback_count > 0 and score > 0 (0 = unrated -> n/a);
  client_spend = client_record.spend_total; hire_rate = client_record.hire_rate_percent; total_hires = client_record.contracts_total;
  interviewing = activityStat.jobActivity.totalInvitedToInterview; invites = jobActivity.invitesSent;
  proposals = n/a (proposals_tier_unavailable); has_hire = jobActivity.totalHired > 0; closed = workFlowState.status != ACTIVE;
  client_country = clientCompanyPublic.country.name (often absent -> null); client_state = clientCompanyPublic.state;
  client_timezone = clientCompanyPublic.timezone. The get output has no city field.
--backfill-location DIR ...: fill ONLY client_country/state/timezone of entries already in the cache from raw get files on
  disk (*.txt and other files in each DIR). No other field changes, no network.
Exit: 0 written or kept, 2 bad input.
"""
import argparse, fcntl, glob, json, os, re, sys, tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
HERE = os.path.expanduser("~/advero/upwork")
CACHE = os.path.join(HERE, "runs", "client_cache.json")
sys.path.insert(0, HERE)
from run_selection import job_id_from_url  # noqa: E402

FIELDS = ["job_id", "url", "title", "client_feedback", "feedback_count", "client_spend", "hire_rate", "total_hires", "interviewing",
          "invites", "proposals", "has_hire", "closed", "workflow_status",
          "client_country", "client_state", "client_timezone", "fetched_ct", "status", "error", "source"]


def canon_id(x):
    """Canonical key = run_selection.job_id_from_url form ('~02<19 digits>')."""
    x = (x or "").strip()
    if not x:
        return ""
    if "upwork.com" in x or "/" in x:
        return job_id_from_url(x)
    d = x.lstrip("~")
    if d.isdigit():
        d = d.lstrip("0")
        return "~02" + d if len(d) == 19 else "~0" + d
    return job_id_from_url(x)


def boolish(v):
    if isinstance(v, bool) or v is None:
        return v
    t = str(v).strip().lower()
    return True if t in ("1", "true", "yes", "y") else False if t in ("0", "false", "no", "n") else None


def location(j):
    cp = j.get("clientCompanyPublic") or {}
    return dict(client_country=((cp.get("country") or {}).get("name") or None), client_state=(cp.get("state") or None),
                client_timezone=(cp.get("timezone") or None))


def backfill_location(dirs, path=CACHE):
    found = {}
    for dr in dirs:
        for fp in sorted(glob.glob(os.path.join(dr, "*")), key=os.path.getmtime):
            if not os.path.isfile(fp): continue
            try:
                t = open(fp).read(); d = json.loads(t[t.find("{"): t.rfind("}") + 1])
                j = (d.get("data") or {}).get("marketplaceJobPosting") or {}
            except Exception:
                continue
            if j.get("id"): found[canon_id(j["id"])] = location(j)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        cache = json.load(open(path))
        n = 0
        for k, v in cache.items():
            if k in found:
                v.update(found[k]); n += 1
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".client_cache.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    return n, len(cache), sum(1 for v in cache.values() if v.get("client_country"))


def from_get(text, fetched_ct=None):
    d = json.loads(text[text.find("{"): text.rfind("}") + 1])
    j = (d.get("data") or {}).get("marketplaceJobPosting") or {}
    c = d.get("client_record") or {}
    act = (j.get("activityStat") or {}).get("jobActivity") or {}
    wf = (j.get("workFlowState") or {}).get("status")
    fbn = c.get("feedback_count") or 0
    return dict(job_id=canon_id(j.get("id") or ""), url=(j.get("url") or "").split("?")[0], title=(j.get("content") or {}).get("title", ""),
                client_feedback=c.get("feedback_score") if fbn and c.get("feedback_score") else None, feedback_count=fbn,
                client_spend=c.get("spend_total"), hire_rate=c.get("hire_rate_percent"), total_hires=c.get("contracts_total"),
                interviewing=act.get("totalInvitedToInterview"), invites=act.get("invitesSent"), proposals=None,
                has_hire=(act.get("totalHired") or 0) > 0 if act else None, closed=(wf != "ACTIVE") if wf else None, workflow_status=wf,
                **location(j),
                fetched_ct=fetched_ct, status="ok" if d.get("status", "ok") == "ok" else "error",
                error="" if d.get("status", "ok") == "ok" else str(d.get("status")), source="find_jobs get")


def upsert(entries, path=CACHE, overwrite=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        cache = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
        res = []
        for e in entries:
            k = e["job_id"]
            if k in cache and not overwrite:
                res.append((k, "kept existing (" + cache[k].get("status", "?") + ")"))
                continue
            cache[k] = {f: e.get(f) for f in FIELDS}
            res.append((k, "written (" + (e.get("status") or "?") + ")"))
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".client_cache.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--from-get"); ap.add_argument("--json"); ap.add_argument("--seed-dir")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--backfill-location", nargs="+", metavar="DIR")
    for f in FIELDS:
        if f != "source":
            ap.add_argument("--" + f.replace("_", "-"))
    a = ap.parse_args()
    now = f"{datetime.now(CT):%Y-%m-%d %H:%M} CT"
    if a.backfill_location:
        n, tot, wc = backfill_location(a.backfill_location, a.cache)
        print(f"location backfilled for {n} of {tot} cache entries; with a country: {wc}"); return
    entries = []
    if a.seed_dir:
        for fp in sorted(glob.glob(os.path.join(a.seed_dir, "*.txt"))):
            try:
                e = from_get(open(fp).read(), a.fetched_ct or now)
            except Exception as ex:
                print(f"skip {fp}: {ex}"); continue
            if e["job_id"]:
                e["source"] = f"find_jobs get (seeded from {os.path.basename(fp)})"; entries.append(e)
    elif a.from_get:
        e = from_get(sys.stdin.read() if a.from_get == "-" else open(a.from_get).read(), a.fetched_ct or now)
        entries.append(e)
    else:
        raw = a.json or ""
        if not raw and not sys.stdin.isatty():
            import select
            if select.select([sys.stdin], [], [], 1.0)[0]:
                raw = sys.stdin.read()
        e = json.loads(raw) if raw.strip() else {}
        for f in FIELDS:
            v = getattr(a, f, None)
            if v is not None:
                e[f] = v
        e.setdefault("source", "cli")
        entries.append(e)
    for e in entries:
        if not e.get("job_id") and (a.job_id or a.url or e.get("url")):
            e["job_id"] = a.job_id or a.url or e.get("url")
        e["job_id"] = canon_id(e.get("job_id") or e.get("url"))
        if not e["job_id"]:
            print("FAIL: no job_id/url"); sys.exit(2)
        e.setdefault("fetched_ct", now); e["fetched_ct"] = e["fetched_ct"] or now
        e["status"] = (e.get("status") or "ok").lower()
        if e["status"] not in ("ok", "error"):
            print("FAIL: status must be ok or error"); sys.exit(2)
        for b in ("has_hire", "closed"):
            e[b] = boolish(e.get(b))
    for k, r in upsert(entries, a.cache, a.overwrite):
        print(f"{k}: {r}")


if __name__ == "__main__":
    main()
