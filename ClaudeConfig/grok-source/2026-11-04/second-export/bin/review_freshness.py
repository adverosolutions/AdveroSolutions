#!/usr/bin/env python3
"""review_freshness.py - flag pest lead rows whose Google review data (rating, review count) is stale or undated.

Why: 2026-10-22 a pest lead (Serv Pest Solutions) replied that his Google rating is 5.0 while our opener
said 4.9 across 288 reviews. Review numbers drift, so every row with review data needs a pull date.

Read only. Never touches the sheet, Instantly or any campaign. Writes one CSV and prints counts.

Sources (pest_control only):
  pool         ~/advero/state/leads/pool/*pest_control*_new.csv
               Uses the row's own rating / reviews / reviews_as_of columns when present. Maps pool rows
               without them are looked up in the Maps output (~/advero/state/leads/maps/pest_*.csv) by
               email, then domain, then Maps place link, preferring the output with the same <TAG>.
               QuickEnrich rows carry no review data and are counted as no_review_data.
  final_leads  ~/advero/state/leads/final-leads/final_pest_control_all_sources_output.csv
               Rows whose opener quotes a rating or review count (Congrats Specific / Specific Rung /
               Specific Evidence). Source is website text, and the file has no capture date, so these
               are unknown unless a reviews_as_of column is added later.
  sheet        Optional: --sheet-csv FILE, a CSV of the Lead Pool pest_control tab A:V with header
               (V = reviews_as_of). Rows with source google_maps are checked on V. The script cannot
               call the Sheets connector itself; an agent reads the tab and saves it to a file first.

Status: fresh (age <= --max-age-days, default 14), stale (older), unknown (no date).
Output: ~/advero/state/leads/review_freshness_latest.csv with stale + unknown rows (--all adds fresh).
Usage:  python3 ~/advero/bin/review_freshness.py [--max-age-days 14] [--all] [--sheet-csv FILE] [--out FILE] [--json]
"""
import argparse, csv, glob, json, os, re, sys
from datetime import datetime, date
from zoneinfo import ZoneInfo
csv.field_size_limit(10**9)

HOME = os.path.expanduser("~")
LEADS = f"{HOME}/advero/state/leads"
POOL_GLOB = f"{LEADS}/pool/*pest_control*_new.csv"
MAPS_GLOB = f"{LEADS}/maps/pest_*.csv"
FINAL = f"{LEADS}/final-leads/final_pest_control_all_sources_output.csv"
OUT = f"{LEADS}/review_freshness_latest.csv"
CT = ZoneInfo("America/Chicago")
REVIEW_TXT = re.compile(r"\d(\.\d)?\s*(-?\s*stars?|rating|out of 5)|\d[\d,]*\+?\s*(google |five-star |5-star )?reviews", re.I)
COLS = ["scope", "file", "row", "company", "email", "domain", "review_source", "rating", "reviews",
        "reviews_as_of", "age_days", "status", "match", "quoted_text"]

def norm_link(u):
    u = (u or "").split("?")[0].split("/data=")[0].rstrip("/")
    return u.lower()

def dom(u):
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u).split("/")[0]
    return u[4:] if u.startswith("www.") else u

def read(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))

def tag_of(path):
    m = re.search(r"maps_([A-Za-z0-9]+)_new\.csv$", path) or re.search(r"/pest_([A-Za-z0-9_]+)\.csv$", path)
    return m.group(1) if m else ""

def classify(as_of, today, max_age):
    as_of = (as_of or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        return "", "", "unknown"
    age = (today - date.fromisoformat(as_of)).days
    return as_of, age, ("fresh" if age <= max_age else "stale")

def load_maps():
    """Index Maps output rows by email, domain and link; keep each row's tag."""
    idx = {"email": {}, "domain": {}, "link": {}}
    for f in sorted(glob.glob(MAPS_GLOB)):
        t = tag_of(f)
        for r in read(f):
            rec = dict(rating=r.get("rating", ""), reviews=r.get("reviews", ""),
                       reviews_as_of=r.get("reviews_as_of", ""), tag=t, file=os.path.basename(f))
            for e in (r.get("emails_all") or "").split(";"):
                if e: idx["email"].setdefault(e.lower(), []).append(rec)
            if r.get("domain"): idx["domain"].setdefault(r["domain"].lower(), []).append(rec)
            if r.get("maps_link"): idx["link"].setdefault(norm_link(r["maps_link"]), []).append(rec)
    return idx

def lookup(idx, row, tag):
    keys = [("email", (row.get("email") or "").lower()),
            ("domain", (row.get("domain") or dom(row.get("website"))).lower()),
            ("link", norm_link(row.get("maps_link")))]
    for same_tag in (True, False):  # the Maps output from the same run first, then any run
        for kind, k in keys:
            hits = [h for h in (idx[kind].get(k) or []) if h["tag"] == tag or not same_tag] if k else []
            if hits:
                return hits[-1], kind
    return None, ""

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-age-days", type=int, default=14)
    ap.add_argument("--all", action="store_true", help="also write fresh rows")
    ap.add_argument("--sheet-csv", help="CSV of the pest_control tab A:V with header row (optional)")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--today", help="YYYY-MM-DD override for tests (default today in CT)")
    ap.add_argument("--json", action="store_true", help="print counts as JSON only")
    a = ap.parse_args()
    today = date.fromisoformat(a.today) if a.today else datetime.now(CT).date()
    maps = load_maps()
    out, counts = [], {}

    def add(scope, rec):
        c = counts.setdefault(scope, {"rows": 0, "with_review_data": 0, "no_review_data": 0,
                                      "fresh": 0, "stale": 0, "unknown": 0})
        c["rows"] += 1
        if rec is None:
            c["no_review_data"] += 1; return
        c["with_review_data"] += 1; c[rec["status"]] += 1
        if rec["status"] != "fresh" or a.all:
            out.append(rec)

    # pool files
    for f in sorted(glob.glob(POOL_GLOB)):
        t = tag_of(f)
        for i, r in enumerate(read(f), start=2):
            rating, reviews, as_of, match = r.get("rating", ""), r.get("reviews", ""), r.get("reviews_as_of", ""), "own_columns"
            if not (rating or reviews) and (r.get("source") or "").startswith("google_maps"):
                hit, kind = lookup(maps, r, t)
                if hit:
                    rating, reviews, as_of, match = hit["rating"], hit["reviews"], hit["reviews_as_of"], f"maps_output:{hit['file']}:{kind}"
            if not (str(rating).strip() or str(reviews).strip()):
                add("pool", None); continue
            d, age, st = classify(as_of, today, a.max_age_days)
            add("pool", dict(scope="pool", file=os.path.basename(f), row=i, company=r.get("company", ""),
                             email=r.get("email", ""), domain=r.get("domain", ""), review_source="google_maps",
                             rating=rating, reviews=reviews, reviews_as_of=d, age_days=age, status=st,
                             match=match, quoted_text=""))

    # final-leads (website-text openers)
    if os.path.exists(FINAL):
        for i, r in enumerate(read(FINAL), start=2):
            txt = " | ".join(x for x in (r.get("Congrats Specific"), r.get("Specific Evidence")) if x)
            rung = (r.get("Specific Rung") or "").lower()
            if not ("rating" in rung or "review" in rung or REVIEW_TXT.search(r.get("Congrats Specific") or "")):
                add("final_leads", None); continue
            d, age, st = classify(r.get("reviews_as_of", ""), today, a.max_age_days)
            add("final_leads", dict(scope="final_leads", file=os.path.basename(FINAL), row=i, company=r.get("Company", ""),
                                    email=r.get("Email", ""), domain=r.get("Company URL", ""),
                                    review_source=(r.get("Personalization Source") or "website").split(";")[0],
                                    rating="", reviews="", reviews_as_of=d, age_days=age, status=st,
                                    match=r.get("Specific Source URL", ""), quoted_text=txt[:300]))

    # sheet snapshot (optional)
    if a.sheet_csv:
        for i, r in enumerate(read(a.sheet_csv), start=2):
            if not (r.get("source") or "").startswith("google_maps"):
                add("sheet", None); continue
            d, age, st = classify(r.get("reviews_as_of", ""), today, a.max_age_days)
            add("sheet", dict(scope="sheet", file="Lead Pool!pest_control", row=i, company=r.get("company", ""),
                              email=r.get("email", ""), domain=r.get("domain", ""), review_source="google_maps",
                              rating="", reviews="", reviews_as_of=d, age_days=age, status=st,
                              match="column V", quoted_text=""))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader(); w.writerows(out)
    os.replace(tmp, a.out)
    summary = dict(today=today.isoformat(), max_age_days=a.max_age_days, out=a.out, rows_written=len(out), scopes=counts)
    if a.json:
        print(json.dumps(summary, indent=1)); return
    print(f"review_freshness {today} (stale = older than {a.max_age_days} days, unknown = no date)")
    for s, c in counts.items():
        print(f"  {s:12s} rows={c['rows']:5d} with_review_data={c['with_review_data']:5d} "
              f"fresh={c['fresh']:5d} stale={c['stale']:5d} unknown={c['unknown']:5d} no_review_data={c['no_review_data']:5d}")
    print(f"  wrote {len(out)} rows to {a.out}")

if __name__ == "__main__":
    main()
