#!/usr/bin/env python3
"""Quality report for a scraped lead file: fill rates, domain mix, precision signals."""
import json, sys, collections, re
from pathlib import Path

FREE = {"gmail.com", "yahoo.com", "aol.com", "hotmail.com", "outlook.com", "icloud.com",
        "comcast.net", "sbcglobal.net", "msn.com", "bellsouth.net", "att.net",
        "verizon.net", "me.com", "live.com", "cox.net", "charter.net"}
ROLE = re.compile(r"^(info|contact|admin|office|hello|support|sales|team|help|billing)@", re.I)


def field(rec, *names):
    for n in names:
        v = rec.get(n)
        if v:
            return v
    return None


def report(path, expect_terms):
    rows = json.load(open(path))
    rows = [r for r in rows if isinstance(r, dict) and len(r) > 1]
    n = len(rows)
    print(f"\n===== {Path(path).name} =====")
    if not n:
        print("  NO RECORDS")
        return
    print(f"  records: {n}")
    print(f"  keys: {sorted(rows[0].keys())}")

    emails = [e for r in rows if (e := field(r, "email", "business_email", "work_email"))]
    print(f"  email fill: {len(emails)}/{n} ({100*len(emails)/n:.0f}%)")
    if emails:
        consumer = sum(1 for e in emails if e.split("@")[-1].lower() in FREE)
        role = sum(1 for e in emails if ROLE.match(e))
        print(f"    consumer-domain: {consumer} ({100*consumer/len(emails):.0f}%)  role-based: {role}")

    for f in ("phone", "mobile", "phone_number", "linkedin_url", "company_website",
              "website", "company_name", "organization_name"):
        c = sum(1 for r in rows if r.get(f))
        if c:
            print(f"  {f}: {100*c/n:.0f}%")

    # Precision: does the company name/industry actually match the ICP?
    blob = [" ".join(str(v) for v in r.values()).lower() for r in rows]
    hits = sum(1 for b in blob if any(t in b for t in expect_terms))
    print(f"  PRECISION: {hits}/{n} ({100*hits/n:.0f}%) mention {expect_terms}")

    for f in ("company_industry", "industry", "seniority", "title", "job_title"):
        vals = [r.get(f) for r in rows if r.get(f)]
        if vals:
            print(f"  {f}: {dict(collections.Counter(vals).most_common(5))}")

    ex = rows[0]
    keep = [k for k in ("full_name", "name", "title", "job_title", "email",
                        "company_name", "organization_name", "company_website") if ex.get(k)]
    print("  sample:", {k: ex[k] for k in keep})


if __name__ == "__main__":
    TERMS = {
        "recruiting": ["recruit", "search", "talent", "staffing", "placement"],
        "law_personal": ["law", "injury", "attorney", "legal", "lawyer", "firm"],
        "dental": ["dental", "dentist", "orthodont", "smile", "oral"],
    }
    for path in sys.argv[1:]:
        key = next((k for k in TERMS if k.split("_")[0] in path), "dental")
        report(path, TERMS[key])
