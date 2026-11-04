#!/usr/bin/env python3
"""Vollna RSS pull -> raw handoff file for Upwork Coordinator (ORG_STRUCTURE.md section 8a).

Read-only: one HTTP GET per Vollna feed (curl). Makes NO Upwork MCP/connector calls, opens no browser, does no scoring.
Writes (never overwrites anything except the pointer):
  ~/advero/upwork/runs/vollna_rss_xml_<YYYYMMDD_HHMM>/<filter_id>.xml   raw feed bodies (audit / re-parse)
  ~/advero/upwork/runs/vollna_raw_<YYYYMMDD_HHMM>.csv                  one row per unique job (dedupe by Upwork job id)
  ~/advero/upwork/runs/vollna_raw_latest.json                          pointer {path,row_count,pulled_at,source,...}
Usage:
  python3 vollna_rss_pull.py                       # live pull (feeds from /workspace/vollna_rss.txt)
  python3 vollna_rss_pull.py --from-dir DIR        # re-parse saved XML in DIR, no network (pulled_at = dir stamp)
  python3 vollna_rss_pull.py --no-pointer          # do not touch vollna_raw_latest.json
  python3 vollna_rss_pull.py --max-age-hours 2     # drop rows whose posted_utc is older than run time minus N hours
Rule 2026-10-22 9:51 AM CT (Lorenzo via COO): routine runs are live pulls with --max-age-hours 2. The live path never reads
earlier vollna_raw files or saved XML; --from-dir re-parses cached XML and is for audit only, never for routine runs.
Exit: 0 ok; 2 all feeds failed/empty; 1 partial (some feed failed; files still written).
Times are America/Chicago (box local); pulled_at carries its offset.
"""
import argparse, csv, html, json, os, re, subprocess, sys, tempfile, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
RUNS = os.path.expanduser("~/advero/upwork/runs")
FEEDS = "/workspace/vollna_rss.txt"
# feed token -> Vollna filter id (from ORG docs / vollna_coverage_20261021.md)
FILTER_IDS = {"FQmqrEHHyJqA9YUzN7jz": "45023", "AVibQDgZrXGU4JngJW8P": "45024", "KqJFbhVQxqGDhMEAiUBC": "45365"}
COLS = ["job_id", "title", "title_raw", "url", "posted_ct", "posted_utc", "budget_type", "budget", "budget_min", "budget_max",
        "budget_currency", "skills", "categories", "filter_ids", "filter_names", "vollna_links", "desc_words", "description",
        "source", "pulled_at"]

def job_id_from_url(url):  # same rule as run_selection.job_id_from_url
    u = urllib.parse.unquote(urllib.parse.unquote((url or "").strip()))
    m = re.search(r"~0?([0-9]{15,})", u)
    if m: return "~0" + m.group(1)
    p = urllib.parse.urlparse(u).path.rstrip("/")
    return p.rsplit("/", 1)[-1].lower() if p else u.lower()

def unesc(s):  # Vollna double-escapes (&amp;amp;, &amp;#039;)
    s = s or ""
    for _ in range(3):
        n = html.unescape(s)
        if n == s: break
        s = n
    return s

def strip_html(s):
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = unesc(s).replace("\r", "")
    s = "\n".join(l.strip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()

BUDGET_RX = re.compile(r"\s*\((Fixed Price|Hourly Rate|Hourly)(?::\s*([^)]*))?\)\s*$", re.I)

def parse_budget(title):
    m = BUDGET_RX.search(title)
    if not m: return title.strip(), "unknown", "", "", "", ""
    kind = "fixed" if m.group(1).lower().startswith("fixed") else "hourly"
    amt = (m.group(2) or "").strip()
    nums = [x.replace(",", "") for x in re.findall(r"\d[\d,]*(?:\.\d+)?", amt)]
    cur = (re.search(r"\b([A-Z]{3})\b", amt) or [None, ""])[1]
    lo = nums[0] if nums else ""; hi = nums[1] if len(nums) > 1 else lo
    return title[:m.start()].strip(), kind, amt, lo, hi, cur

def split_tail(desc):
    """Vollna appends 'Skills: a, b' and 'Categories: x, y' at the end of the description."""
    skills = cats = ""
    m = re.search(r"\n\s*Categories:\s*(.*)\s*$", desc, re.S)
    if m: cats = " ".join(m.group(1).split()); desc = desc[:m.start()]
    m = re.search(r"\n\s*Skills:\s*(.*)\s*$", desc, re.S)
    if m: skills = " ".join(m.group(1).split()); desc = desc[:m.start()]
    return desc.strip(), skills, cats

def fetch(url):
    r = subprocess.run(["curl", "-sSL", "-m", "40", "-A", "Mozilla/5.0 (VollnaBot read-only RSS)", "-w", "\n__HTTP__%{http_code}", url],
                       capture_output=True, text=True)
    body, _, code = r.stdout.rpartition("\n__HTTP__")
    return body, code, (r.stderr.strip() if r.returncode else "")

def parse(xml_text, fid, fname, errors):
    try: root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        errors.append(f"{fid}: XML parse error {e}"); return []
    out = []
    for it in root.iter("item"):
        try:
            title_raw = unesc(it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [link])[0]
            up = urllib.parse.unquote(urllib.parse.unquote(q))
            pub = parsedate_to_datetime(it.findtext("pubDate"))
            desc, skills, cats_txt = split_tail(strip_html(it.findtext("description") or ""))
            cats = [unesc(c.text or "").strip() for c in it.iter("category") if (c.text or "").strip()]
            title, kind, amt, lo, hi, cur = parse_budget(title_raw)
            out.append(dict(job_id=job_id_from_url(up), title=title, title_raw=title_raw, url=up, pub=pub,
                            budget_type=kind, budget=amt, budget_min=lo, budget_max=hi, budget_currency=cur,
                            skills=skills, categories="; ".join(cats) if cats else cats_txt, description=desc,
                            fid=fid, fname=fname, vlink=link))
        except Exception as e:
            errors.append(f"{fid}: item parse error {type(e).__name__}: {e}")
    return out

def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f: f.write(text)
    os.chmod(tmp, 0o644); os.replace(tmp, path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", default=FEEDS); ap.add_argument("--runs", default=RUNS)
    ap.add_argument("--from-dir", default=""); ap.add_argument("--no-pointer", action="store_true")
    ap.add_argument("--max-age-hours", type=float, default=None,
                    help="drop rows whose posted_utc is older than run time minus N hours (posted time, not first-seen)")
    a = ap.parse_args()
    if a.from_dir:
        print("NOTE: --from-dir re-parses cached XML; audit only, not for routine runs (rule 2026-10-22 9:51 AM CT)", file=sys.stderr)
    feeds = []
    for line in open(a.feeds, encoding="utf-8"):
        if "\t" not in line: continue
        name, url = line.rstrip("\n").split("\t", 1); url = url.strip()
        feeds.append((FILTER_IDS.get(url.rsplit("/", 1)[-1], url.rsplit("/", 1)[-1]), name.strip(), url))
    errors = []; items = []; per_feed = {}
    if a.from_dir:
        m = re.search(r"(\d{8}_\d{4})", a.from_dir.rstrip("/"))
        now = datetime.strptime(m.group(1), "%Y%m%d_%H%M").replace(tzinfo=CT) if m else datetime.now(CT)
        xdir = a.from_dir
    else:
        now = datetime.now(CT); xdir = os.path.join(a.runs, f"vollna_rss_xml_{now:%Y%m%d_%H%M}")
        os.makedirs(xdir, exist_ok=True)
    for fid, name, url in feeds:
        xp = os.path.join(xdir, f"{fid}.xml")
        if a.from_dir:
            body = open(xp, encoding="utf-8").read() if os.path.exists(xp) else ""
            if not body: errors.append(f"{fid}: no saved XML at {xp}")
        else:
            body, code, err = fetch(url)
            if code != "200" or err: errors.append(f"{fid}: HTTP {code} {err}".strip())
            if body and not os.path.exists(xp): open(xp, "w", encoding="utf-8").write(body)
        got = parse(body, fid, name, errors) if body else []
        per_feed[fid] = len(got); items += got
    # dedupe by job id across feeds, keep feed order of first appearance
    jobs = {}
    for j in items:
        k = j["job_id"]
        if k in jobs:
            d = jobs[k]
            if j["fid"] not in d["fids"]: d["fids"].append(j["fid"]); d["fnames"].append(j["fname"]); d["vlinks"].append(j["vlink"])
            if len(j["description"]) > len(d["description"]): d["description"] = j["description"]
            continue
        j["fids"] = [j["fid"]]; j["fnames"] = [j["fname"]]; j["vlinks"] = [j["vlink"]]; jobs[k] = j
    pulled = now.isoformat(timespec="seconds")
    cutoff = None; dropped_age = 0
    if a.max_age_hours is not None:
        cutoff = datetime.now(CT) - timedelta(hours=a.max_age_hours)   # measured at run time
        before = len(jobs)
        jobs = {k: j for k, j in jobs.items() if j["pub"] >= cutoff}
        dropped_age = before - len(jobs)
    rows = []
    for j in sorted(jobs.values(), key=lambda x: x["pub"], reverse=True):
        rows.append(dict(job_id=j["job_id"], title=j["title"], title_raw=j["title_raw"], url=j["url"],
                         posted_ct=j["pub"].astimezone(CT).strftime("%Y-%m-%d %H:%M CT"),
                         posted_utc=j["pub"].astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         budget_type=j["budget_type"], budget=j["budget"], budget_min=j["budget_min"], budget_max=j["budget_max"],
                         budget_currency=j["budget_currency"], skills=j["skills"], categories=j["categories"],
                         filter_ids="+".join(j["fids"]), filter_names=" + ".join(j["fnames"]), vollna_links=" | ".join(j["vlinks"]),
                         desc_words=len(j["description"].split()), description=j["description"], source="rss", pulled_at=pulled))
    if not items:
        print("FAIL: 0 items from all feeds;", "; ".join(errors)); sys.exit(2)
    if not rows and cutoff is None:
        print("FAIL: 0 items from all feeds;", "; ".join(errors)); sys.exit(2)
    base = os.path.join(a.runs, f"vollna_raw_{now:%Y%m%d_%H%M}")
    path = base + ".csv"; n = 1
    while os.path.exists(path): n += 1; path = f"{base}_{n}.csv"   # never overwrite
    import io
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=COLS, quoting=csv.QUOTE_MINIMAL); w.writeheader(); w.writerows(rows)
    atomic_write(path, buf.getvalue())
    overlap = sum(1 for r in rows if "+" in r["filter_ids"])
    ptr = dict(path=path, row_count=len(rows), pulled_at=pulled, source="rss", per_feed=per_feed, overlap_rows=overlap,
               newest_posted_ct=rows[0]["posted_ct"] if rows else "", oldest_posted_ct=rows[-1]["posted_ct"] if rows else "",
               xml_dir=os.path.abspath(xdir), errors=errors)
    if cutoff is not None:
        ptr.update(max_age_hours=a.max_age_hours, cutoff_ct=cutoff.strftime("%Y-%m-%d %H:%M:%S CT"),
                   cutoff_utc=cutoff.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"), dropped_over_age=dropped_age)
    if not a.no_pointer:
        atomic_write(os.path.join(a.runs, "vollna_raw_latest.json"), json.dumps(ptr, indent=2) + "\n")
    print(json.dumps(ptr, indent=2))
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
