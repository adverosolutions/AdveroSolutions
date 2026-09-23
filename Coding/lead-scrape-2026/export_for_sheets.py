#!/usr/bin/env python3
"""Consolidate every run into one Google Sheets-ready CSV.

Email handling: the actor splits contacts across `email` (business) and
`personal_email`. Outreach needs ONE address per row, and a company address
always beats a gmail/yahoo one -- so `email` below is coalesced business-first
and `email_source` records which it came from. The raw personal address is kept
at the far right so nothing is lost.

Review columns added on top of the actor's own fields:
    variant      -- ungated (wave 2) vs size-gated (wave 3)
    email_source -- business / personal
    qa_flag      -- OVERSIZED / NO_EMAIL / DUP_COMPANY / OK
    company_seen -- contacts held for that company in this export

Usage: python3 export_for_sheets.py
"""
import csv
import glob
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

COLS = [
    "niche", "variant", "qa_flag", "company_name", "company_size",
    "first_name", "last_name", "job_title", "email", "email_source",
    "mobile_number", "city", "state", "company_domain", "company_website",
    "company_phone", "linkedin", "company_linkedin", "industry",
    "company_annual_revenue_clean", "company_full_address", "headline",
    "company_description", "company_technologies", "keywords",
    "company_founded_year", "seniority_level", "company_seen",
    "personal_email_raw",
]

RUNS = [
    ("recruiting", "ungated"), ("law", "ungated"), ("dental", "ungated"),
    ("recruiting_v2", "size-gated"), ("dental_v2", "size-gated"),
]


def clean(v) -> str:
    """Stringify, and defuse anything Sheets would read as a formula."""
    if v is None:
        return ""
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def main() -> None:
    rows, tally = [], Counter()
    for name, variant in RUNS:
        files = sorted(glob.glob(str(OUT / f"{name}_2*.json")))
        if not files:
            print(f"  ! no output for {name}")
            continue
        leads = json.loads(Path(files[-1]).read_text())
        counts = Counter((l.get("company_name") or "?") for l in leads)

        for l in leads:
            biz = (l.get("email") or "").strip()
            per = (l.get("personal_email") or "").strip()
            # Business address wins whenever both exist.
            email, source = (biz, "business") if biz else ((per, "personal") if per else ("", ""))

            co = l.get("company_name") or "?"
            if (l.get("company_size") or 0) > 100:
                flag = "OVERSIZED"
            elif not email:
                flag = "NO_EMAIL"
            elif counts[co] > 1:
                flag = "DUP_COMPANY"
            else:
                flag = "OK"

            row = {c: clean(l.get(c)) for c in COLS}
            row.update({
                "niche": name.replace("_v2", ""),
                "variant": variant,
                "qa_flag": flag,
                "email": clean(email),
                "email_source": source,
                "company_seen": counts[co],
                "personal_email_raw": clean(per),
            })
            rows.append(row)
            tally[source] += 1
        print(f"  {name:14s} {variant:11s} {len(leads):3d} rows")

    path = OUT / "ALL_TEST_LEADS_for_sheets.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n  {len(rows)} rows -> {path.name}")
    print("  email source:", dict(tally))
    print("  qa flags:", dict(Counter(r["qa_flag"] for r in rows)))


if __name__ == "__main__":
    main()
