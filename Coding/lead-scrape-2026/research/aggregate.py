#!/usr/bin/env python3
"""Turn the three *_findings.json files into two review CSVs:
  research/findings_by_company.csv   -- one row per company, every field, for reading
  research/trait_prevalence.csv      -- one row per (niche, trait): how many of 5 had it
                                        + a cold-read verdict
Verdict rule: 5/5 or 4/5 = SAFE to assert blind; 3/5 = COIN FLIP; <=2/5 = DON'T (only
usable if researched per lead). Distinctive facts are listed separately.
"""
import csv, json
from collections import Counter
from pathlib import Path
R = Path(__file__).resolve().parent
rows, prev, distinct = [], [], []
for niche in ("recruiting", "cleaning", "bookkeeping"):
    f = R / f"{niche}_findings.json"
    if not f.exists():
        print(f"  ! missing {f.name}"); continue
    data = json.loads(f.read_text())
    extra = R / f"{niche}_findings_extra.json"
    if extra.exists():
        data += json.loads(extra.read_text())
    valid = [d for d in data if not d.get("off_niche_flag")]
    for d in data:
        r = {"niche": niche}
        for k, v in d.items():
            r[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
        rows.append(r)
        if d.get("most_distinctive_fact"):
            distinct.append({"niche": niche, "company": d["company"], "distinctive_fact": d["most_distinctive_fact"],
                             "off_niche": d.get("off_niche_flag", "")})
    tally = Counter(t for d in valid for t in d.get("generic_traits_present", []))
    n = len(valid)
    # also tally the boolean/known fields so nothing is missed
    for key in [k for k in (valid[0].keys() if valid else []) if isinstance(valid[0].get(k), bool) and k != "site_reachable"]:
        c = sum(1 for d in valid if d.get(key))
        if c: tally[f"[field] {key}"] = c
    for trait, c in tally.most_common():
        share = c / max(1, n)
        verdict = "SAFE" if share >= 0.8 else "COIN FLIP" if share >= 0.5 else "DON'T (needs research)"
        if n < 5: verdict += " (low sample)"
        prev.append({"niche": niche, "trait": trait, "companies_with_it": c, "of": n, "verdict": verdict})

keys = ["niche"] + sorted({k for r in rows for k in r} - {"niche"})
with (R / "findings_by_company.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
with (R / "trait_prevalence.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["niche", "trait", "companies_with_it", "of", "verdict"]); w.writeheader(); w.writerows(prev)
with (R / "distinctive_facts.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["niche", "company", "distinctive_fact", "off_niche"]); w.writeheader(); w.writerows(distinct)

print(f"{len(rows)} companies -> findings_by_company.csv | {len(prev)} trait rows -> trait_prevalence.csv\n")
for niche in ("recruiting", "cleaning", "bookkeeping"):
    print(f"== {niche.upper()} ==")
    for p in [p for p in prev if p["niche"] == niche]:
        print(f"  {p['companies_with_it']}/{p['of']}  {p['verdict']:22s} {p['trait']}")
