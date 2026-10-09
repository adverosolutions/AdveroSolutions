#!/usr/bin/env python3
"""Step 1 of the personalization pipeline. Zero model tokens.

For every lead: is the website live, and does the company look like the niche
it was scraped for? Writes personalize/precheck.csv with:
  site_status   OK | BLOCKED (403/429, treat as live) | DEAD | PARKED | ERROR
  niche_check   OK | OFF_NICHE | UNSURE
  route         TIER2_CANDIDATE | TIER1_ONLY | SKIP
Never touches the sheet; the daily job reads this file.
"""
import csv, re, ssl, socket, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv"
OUT = ROOT / "personalize" / "precheck.csv"
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
PARKED = ["domain is for sale", "buy this domain", "this domain may be for sale", "parked", "coming soon",
          "under construction", "account suspended", "website expired", "godaddy.com/domainsearch"]

ON = {"recruiting": ["recruit", "staffing", "search", "talent", "placement", "headhunt", "hiring", "personnel", "workforce", "executive", "career"],
      "cleaning":   ["clean", "janitor", "custodial", "maint", "sanit", "floor", "porter", "disinfect", "facility"],
      "bookkeeping": ["bookkeep", "tax", "account", "cpa", "payroll", "financial", "audit", "advisor"],
      "msp": ["managed", "msp", "it support", "it service", "network", "cyber", "help desk", "computer", "cloud", "technology"],
      "marketing_agency": ["marketing", "seo", "advertis", "agency", "ppc", "media", "brand", "web design", "creative", "public relations"],
      "insurance_broker": ["insurance", "benefit", "broker", "agency", "coverage", "risk"],
      "landscaping": ["landscap", "lawn", "grounds", "turf", "tree", "snow", "irrigation", "green"],
      "pest_control": ["pest", "extermin", "termite", "wildlife", "rodent", "mosquito", "bug"]}
OFF = {"recruiting": ["software", "saas", "app ", "platform", "consulting firm", "marketing", "real estate", "insurance"],
       "cleaning":   ["sign", "furniture", "restoration", "water damage", "fire damage", "remediation", "plumb", "hvac", "electric",
                      "landscap", "lawn", "pest", "roof", "paint", "moving", "storage", "car wash", "auto", "laundr", "linen", "security"],
       "bookkeeping": ["software", "saas", "wealth", "investment", "insurance", "mortgage", "real estate", "staffing", "law "],
       "msp": ["software development", "app development", "saas", "staffing", "recruit", "marketing agency", "sql", "sap", "salesforce", "home automation", "manufactur"],
       "marketing_agency": ["printing", "sign", "promotional products", "market research", "software", "saas", "staffing", "photograph"],
       "insurance_broker": ["state farm", "allstate", "farmers insurance", "geico", "carrier", "underwrit", "adjust", "wealth", "investment", "software"],
       "landscaping": ["janitorial", "cleaning", "pest", "pool", "deck", "general contractor", "paving", "concrete", "custom home", "franchise"],
       "pest_control": ["landscap", "lawn", "tree", "cleaning", "janitorial", "courier", "delivery", "manufactur", "distribut"]}

def site(url):
    if not url: return "NONE"
    if not url.startswith("http"): url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            body = r.read(60000).decode("utf-8", "ignore").lower()
            return "PARKED" if any(k in body for k in PARKED) else "OK"
    except urllib.error.HTTPError as e:
        return "BLOCKED" if e.code in (401, 403, 429, 503) else "ERROR"
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return "DEAD"

def niche_check(r):
    n = r["campaign"]
    blob = " ".join([r["company_name"], r["company_description"], r["headline"], r["industry"]]).lower()
    name = r["company_name"].lower()
    if any(k in name for k in OFF[n]) and not any(k in name for k in ON[n]): return "OFF_NICHE"
    if any(k in blob for k in ON[n]): return "OK"
    if any(k in blob for k in OFF[n]): return "OFF_NICHE"
    return "UNSURE"

def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    with ThreadPoolExecutor(32) as ex:
        statuses = list(ex.map(lambda r: site(r["company_website"].strip()), rows))
    out = []
    for r, st in zip(rows, statuses):
        nc = niche_check(r)
        route = ("SKIP" if nc == "OFF_NICHE" else
                 "TIER2_CANDIDATE" if st in ("OK", "BLOCKED") else "TIER1_ONLY")
        out.append({"lead_id": r["lead_id"], "campaign": r["campaign"], "company_name": r["company_name"],
                    "site_status": st, "niche_check": nc, "route": route})
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    from collections import Counter
    print(f"{len(out)} leads -> {OUT.name}")
    for n in ("recruiting", "bookkeeping", "cleaning"):
        s = [o for o in out if o["campaign"] == n]
        print(f"  {n:12s} site: {dict(Counter(o['site_status'] for o in s))}")
        print(f"  {'':12s} niche: {dict(Counter(o['niche_check'] for o in s))}  -> route: {dict(Counter(o['route'] for o in s))}")

if __name__ == "__main__":
    main()
