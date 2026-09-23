#!/usr/bin/env python3
"""Merge every production batch into campaign-ready CSVs.

Cleanup applied, in order:
  1. coalesce email  -- business address wins, personal only as fallback
  2. drop unreachable -- no address of either kind
  3. drop foreign     -- ccTLD addresses; the campaign is US-only
  4. drop oversized   -- past each niche's size ceiling (recovered orphan
                         shards predate the tightened law filter)
  5. dedupe           -- on the coalesced address, across all batches
  6. rank             -- business-email + first-contact-at-company first,
                         so trimming from the bottom keeps the best leads

Usage: python3 final_export.py
"""
import csv
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROD = ROOT / "output" / "production"
FINAL = ROOT / "output" / "final"

# Employee ceiling per niche. Law runs looser: 25 attorneys is often ~60 staff.
CEILING = {"dental": 50, "recruiting": 50, "law": 100, "cleaning": 200, "bookkeeping": 50}

# Two-letter ccTLDs that mean "not a US business". .co/.io/.me/.ai are
# excluded from this list because they're used generically by US companies.
FOREIGN = {"cl", "uk", "ca", "ie", "rw", "au", "nz", "in", "de", "fr", "es",
           "it", "br", "mx", "za", "ph", "pk", "ng", "ru", "cn", "jp", "nl",
           "ar", "my", "sg", "id", "ae", "il", "pe", "ve", "ec", "cr", "gt"}

JUNK = ("legalshield", "legal aid", "dental lab", "dental laboratory")

COLS = ["niche", "first_name", "last_name", "job_title", "email", "email_source",
        "company_name", "company_size", "company_domain", "company_website",
        "city", "state", "company_phone", "mobile_number", "linkedin",
        "company_linkedin", "industry", "company_annual_revenue_clean",
        "company_full_address", "headline", "company_description",
        "company_technologies", "company_founded_year", "seniority_level",
        "contact_rank_at_company"]


def clean(v) -> str:
    if v is None:
        return ""
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def main() -> None:
    FINAL.mkdir(parents=True, exist_ok=True)
    combined, summary = [], []

    for niche in ("recruiting", "law", "dental", "cleaning", "bookkeeping"):
        raw = []
        pats = [f"{niche}__*.json"] + (["cleaning_cs*.json", "cleaning_unval*.json"] if niche == "cleaning" else [])
        for pat in pats:
            for f in glob.glob(str(PROD / pat)):
                raw += json.loads(Path(f).read_text())

        drop = Counter()
        seen, kept = set(), []
        for l in raw:
            biz = (l.get("email") or "").strip()
            per = (l.get("personal_email") or "").strip()
            email, src = (biz, "business") if biz else ((per, "personal") if per else ("", ""))

            if not email:
                drop["no_email"] += 1
                continue
            edom = email.lower().split("@")[-1]
            cdom = (l.get("company_domain") or "").lower()
            if any(part in FOREIGN for part in edom.split(".")[-2:]) or \
               (cdom and any(part in FOREIGN for part in cdom.split(".")[-2:])):
                drop["foreign"] += 1
                continue
            if (l.get("company_size") or 0) > CEILING[niche]:
                drop["oversized"] += 1
                continue
            blob = f"{l.get('company_name','')} {l.get('keywords','')}".lower()
            if any(j in blob for j in JUNK):
                drop["junk"] += 1
                continue
            k = email.lower()
            if k in seen:
                drop["duplicate"] += 1
                continue
            seen.add(k)
            l["_email"], l["_src"] = email, src
            kept.append(l)

        # rank contacts within each company so trimming keeps one per company first
        per_co = defaultdict(int)
        for l in sorted(kept, key=lambda x: 0 if x["_src"] == "business" else 1):
            co = (l.get("company_name") or "?").lower()
            per_co[co] += 1
            l["_rank"] = per_co[co]
        kept.sort(key=lambda x: (x["_rank"], 0 if x["_src"] == "business" else 1))

        rows = []
        for l in kept:
            r = {c: clean(l.get(c)) for c in COLS}
            r.update({"niche": niche, "email": clean(l["_email"]),
                      "email_source": l["_src"], "contact_rank_at_company": l["_rank"]})
            rows.append(r)

        path = FINAL / f"{niche}_leads.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        combined += rows

        biz = sum(1 for r in rows if r["email_source"] == "business")
        firsts = sum(1 for r in rows if r["contact_rank_at_company"] == 1)
        summary.append((niche, len(raw), len(rows), biz, len(rows) - biz, firsts, dict(drop)))
        print(f"{niche:11s} raw={len(raw):5d} -> kept={len(rows):5d}  "
              f"business={biz:5d} personal={len(rows)-biz:4d} "
              f"unique-co={firsts:5d}  dropped={dict(drop)}")

    # A person can legitimately match two niches (a legal recruiter hits both
    # law and recruiting). Keep the first and drop the rest, or the campaign
    # sends one inbox two different sequences.
    seen_all, deduped, cross = set(), [], 0
    for r in combined:
        k = r["email"].lower()
        if k in seen_all:
            cross += 1
            continue
        seen_all.add(k)
        deduped.append(r)
    combined = deduped
    print(f"\ncross-niche duplicates removed: {cross}")

    allpath = FINAL / "ALL_LEADS.csv"
    with allpath.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(combined)
    print(f"\nTOTAL {len(combined)} leads -> output/final/ALL_LEADS.csv (+ per-niche CSVs)")


if __name__ == "__main__":
    main()
