#!/usr/bin/env python3
"""Export wave-4 (unverified) leads and append them to MASTER + the sheet.

  python3 wave4_export.py            # dry run: report only
  python3 wave4_export.py --apply    # append to MASTER_for_sheets.csv, sheet tab Leads, precheck.csv

These leads are Apify 'validated' but NOT MillionVerifier-checked (no MV credits
on 2026-09-16), so they land at the tail of each campaign as block_type
UNVERIFIED / mv_result 'unverified'. daily_pick --only-clean skips them; run
daily_pick without --only-clean (or filter mv_result=unverified) to use them.
"""
import csv, glob, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "personalize"))
from final_export import CEILING, FOREIGN, JUNK, clean

ROOT = Path(__file__).resolve().parent
PROD = ROOT / "output" / "production"
MASTER = ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv"
PRE = ROOT / "personalize" / "precheck.csv"
SHEET_ID = "1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw"
OUTCSV = ROOT / "output" / "FINAL" / "WAVE4_unverified.csv"

W4_GLOBS = ["*w4*.json", "*csuite_smoke_2026091*.json", "recruiting_deep_ca_test_*.json", "*deep*.json"]
OWNER_TITLE = re.compile(r"ceo|chief executive|president|managing partner|managing director|managing member|principal|owner|founder|partner|proprietor", re.I)
NOT_OWNER = re.compile(r"chief (financial|marketing|technology|operating|people|talent|revenue|information|strategy|growth|sales|human)|\bc[fmtoirs]o\b|controller|fractional|outsourced|vice president|\bvp\b", re.I)


def niche_of(fname: str) -> str:
    for n in ("bookkeeping", "recruiting", "cleaning"):
        if fname.startswith(n): return n
    raise ValueError(fname)


def main():
    apply = "--apply" in sys.argv
    files = sorted({f for g in W4_GLOBS for f in glob.glob(str(PROD / g))})
    master = list(csv.DictReader(MASTER.open(encoding="utf-8-sig")))
    cols = list(master[0].keys())
    known = {r["email"].lower() for r in master}
    for f in glob.glob(str(PROD / "*.json")):
        if f in files: continue
        for l in json.load(open(f)):
            for k in ("email", "personal_email"):
                e = (l.get(k) or "").strip().lower()
                if e: known.add(e)
    for f in glob.glob(str(ROOT / "output/verified/BAD_all.csv")):
        known |= {r["email"].lower() for r in csv.DictReader(open(f, encoding="utf-8-sig"))}
    print(f"[w4x] {len(files)} wave-4 files; {len(known)} previously known emails")

    per_co = defaultdict(int)
    for r in master:
        per_co[(r["campaign"], (r["company_name"] or "?").lower())] += 1
    max_id = {c: max(int(r["lead_id"].split("-")[1]) for r in master if r["campaign"] == c) for c in ("recruiting", "bookkeeping", "cleaning")}
    max_so = {c: max(int(r["send_order"]) for r in master if r["campaign"] == c) for c in max_id}
    max_bl = {c: max(int(r["block_no"]) for r in master if r["campaign"] == c) for c in max_id}

    raw = defaultdict(list)
    for f in files:
        n = niche_of(Path(f).name)
        csuite = "csuite" in Path(f).name
        for l in json.load(open(f)):
            l["_csuite"] = csuite
            raw[n].append(l)

    new_rows = []
    for niche in ("recruiting", "bookkeeping", "cleaning"):
        drop, seen, kept = Counter(), set(), []
        for l in raw[niche]:
            biz = (l.get("email") or "").strip(); per = (l.get("personal_email") or "").strip()
            email, src = (biz, "business") if biz else ((per, "personal") if per else ("", ""))
            if not email: drop["no_email"] += 1; continue
            k = email.lower()
            if k in known or k in seen: drop["already_known" if k in known else "duplicate"] += 1; continue
            edom = k.split("@")[-1]; cdom = (l.get("company_domain") or "").lower()
            if any(p in FOREIGN for p in edom.split(".")[-2:]) or (cdom and any(p in FOREIGN for p in cdom.split(".")[-2:])):
                drop["foreign"] += 1; continue
            if (l.get("country") or "").strip().lower() not in ("", "united states", "us", "usa"):
                drop["foreign_contact"] += 1; continue
            if (l.get("company_size") or 0) > CEILING[niche]: drop["oversized"] += 1; continue
            blob = f"{l.get('company_name','')} {l.get('keywords','')}".lower()
            if any(j in blob for j in JUNK): drop["junk"] += 1; continue
            t = l.get("job_title") or ""
            if l["_csuite"] and (not OWNER_TITLE.search(t) or (NOT_OWNER.search(t) and not re.search(r"ceo|president|owner|founder|managing", t, re.I))):
                drop["csuite_not_owner"] += 1; continue
            if not (l.get("first_name") or "").strip(): drop["no_first_name"] += 1; continue
            seen.add(k); l["_email"], l["_src"] = email, src; kept.append(l)
        for l in sorted(kept, key=lambda x: 0 if x["_src"] == "business" else 1):
            key = (niche, (l.get("company_name") or "?").lower()); per_co[key] += 1; l["_rank"] = per_co[key]
        kept.sort(key=lambda x: (x["_rank"], 0 if x["_src"] == "business" else 1))
        for l in kept:
            max_id[niche] += 1; max_so[niche] += 1
            r = {c: clean(l.get(c)) for c in cols}
            cst, st = (l.get("company_state") or "").strip(), (l.get("state") or "").strip()
            r.update({"campaign": niche, "send_order": max_so[niche], "block_no": max_bl[niche] + 1, "block_type": "UNVERIFIED",
                      "email_quality": "Unverified (Apify validated)", "lead_id": f"{niche[:2].upper()}-{max_id[niche]:05d}",
                      "email": clean(l["_email"]), "email_source": l["_src"], "mv_result": "unverified",
                      "contact_rank_at_company": l["_rank"], "company_city": clean(l.get("company_city")), "company_state": clean(cst),
                      "location_note": "contact state differs from company state" if cst and st and cst.lower() != st.lower() else "",
                      "personalization_status": "", "icebreaker": "", "angle": "", "research_notes": "", "personalized_at": "", "specialty": ""})
            new_rows.append(r)
        print(f"  {niche:12s} raw={len(raw[niche]):5d} kept={len(kept):5d} dropped={dict(drop)}")

    with OUTCSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(new_rows)
    print(f"[w4x] {len(new_rows)} new unverified leads -> {OUTCSV.name}  ({Counter(r['campaign'] for r in new_rows)})")
    if not apply:
        return

    # precheck (site status + niche check) for the new rows only
    from precheck import site, niche_check
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(32) as ex:
        sts = list(ex.map(lambda r: site(r["company_website"].strip()), new_rows))
    pre_rows = []
    for r, st in zip(new_rows, sts):
        nc = niche_check(r)
        pre_rows.append({"lead_id": r["lead_id"], "campaign": r["campaign"], "company_name": r["company_name"], "site_status": st, "niche_check": nc,
                         "route": "SKIP" if nc == "OFF_NICHE" else "TIER2_CANDIDATE" if st in ("OK", "BLOCKED") else "TIER1_ONLY"})
    with PRE.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=list(pre_rows[0].keys())).writerows(pre_rows)
    print(f"[w4x] precheck appended: {Counter(p['route'] for p in pre_rows)}")

    with MASTER.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=cols, extrasaction="ignore").writerows(new_rows)
    from sheet_io import open_tab
    ws = open_tab(SHEET_ID)
    hdr = ws.row_values(1)
    vals = [[r.get(h, "") for h in hdr] for r in new_rows]
    for i in range(0, len(vals), 1000):
        ws.append_rows(vals[i:i+1000], value_input_option="RAW")
    print(f"[w4x] appended {len(vals)} rows to sheet + MASTER")


if __name__ == "__main__":
    main()
