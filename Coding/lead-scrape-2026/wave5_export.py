#!/usr/bin/env python3
"""Export wave-5 (five new niches, unverified) leads and append to MASTER + sheet.

  python3 wave5_export.py            # dry run
  python3 wave5_export.py --apply    # append to MASTER_for_sheets.csv, sheet, precheck.csv

Niches: msp, marketing_agency, insurance_broker, landscaping, pest_control.
Rows land as block_type UNVERIFIED / mv_result 'unverified' (no MillionVerifier yet).
Suppression: email against everything ever scraped or on the sheet; company domain
against every domain already on the sheet (keeps landscaping/pest off cleaning contacts).
"""
import csv, glob, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "personalize"))
from final_export import FOREIGN, clean

ROOT = Path(__file__).resolve().parent
PROD = ROOT / "output" / "production"
MASTER = ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv"
PRE = ROOT / "personalize" / "precheck.csv"
SHEET_ID = "1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw"
OUTCSV = ROOT / "output" / "FINAL" / "WAVE5_unverified.csv"

NICHES = {"msp": "MS", "marketing_agency": "MA", "insurance_broker": "IN", "landscaping": "LA", "pest_control": "PE"}
CEILING = {"msp": 100, "marketing_agency": 50, "insurance_broker": 100, "landscaping": 200, "pest_control": 200}
ON = {
 "msp": r"managed (it|service)|\bmsp\b|it support|it service|it solution|network|cyber|help ?desk|cloud|computer (repair|service|support)|technology (service|solution|partner|consult)|tech support",
 "marketing_agency": r"\bseo\b|marketing|advertis|\bppc\b|paid (ads|media)|google ads|web design|brand|lead gen|social media|agency|public relations|creative|media",
 "insurance_broker": r"insurance|benefit|broker|agency|p&c|property (and|&) casualty|coverage|risk",
 "landscaping": r"landscap|lawn|grounds|turf|snow|irrigation|hardscap|tree|green",
 "pest_control": r"pest|extermin|termite|wildlife|rodent|mosquito|bed ?bug|bug",
}
OFF = {
 "msp": r"software development|app development|saas|staffing|recruit|marketing agency|\bsql\b|\bsap\b|salesforce|home automation|audio|manufactur|hr services|product development|generative ai|awards|loyalty|wireless carrier",
 "marketing_agency": r"printing|\bsigns?\b|promotional products|market research|software|saas|platform|staffing|real estate|photograph|radio show|talk radio|event planner",
 "insurance_broker": r"state farm|allstate|farmers insurance|farmers union|geico|liberty mutual|carrier|underwrit|adjust|insurtech|wealth|investment|financial advis|software|medicare only|fmo",
 "landscaping": r"nursery|garden center|architect|supply|dealer|golf|design studio|real estate|general contractor|paving|erosion|concrete|pool|custom home|remodel|painting|plumbing|hvac|rental|recycling|waste|daycare|deck|janitorial|cleaning|pest control|franchise platform",
 "pest_control": r"manufactur|distribut|equipment|orkin|terminix|rentokil|ecolab|janitorial|cleaning|courier|delivery|landscap(?!.*pest)|tree service",
}
OFF_NAME = {
 "insurance_broker": r"carrier|underwrit|wealth|financial|capital|investment|advisors?\b|retirement|bonding|re\b",
 "marketing_agency": r"platform|real estate|software|saas|studio|photo|film|engrav",
 "msp": r"",
 "landscaping": r"",
 "pest_control": r"",
}
BLOB_SKIP = {"insurance_broker": r"carrier|underwrit|investment|wealth|financial advis", "marketing_agency": r"platform|real estate|software|saas"}
OWNER_TITLE = re.compile(r"ceo|chief executive|president|managing partner|managing director|managing member|principal|owner|founder|partner|proprietor", re.I)
NOT_OWNER = re.compile(r"chief (financial|marketing|technology|operating|people|talent|revenue|information|strategy|growth|sales|human)|\bc[fmtoirs]o\b|controller|fractional|outsourced|vice president|\bvp\b|agent\b|producer|account (manager|executive)", re.I)


def niche_of(fname):
    for n in NICHES:
        if fname.startswith(n + "_"): return n
    return None


def main():
    apply = "--apply" in sys.argv
    files = sorted(f for f in glob.glob(str(PROD / "*w5*.json")) + glob.glob(str(ROOT / "output/smoke3/*.json")) if niche_of(Path(f).name))
    master = list(csv.DictReader(MASTER.open(encoding="utf-8-sig")))
    cols = list(master[0].keys())
    known = {r["email"].lower() for r in master}
    known_dom = {(r.get("company_domain") or "").lower() for r in master} | {r["email"].lower().split("@")[-1] for r in master}
    known_dom.discard("")
    for f in glob.glob(str(PROD / "*.json")):
        if f in files: continue
        for l in json.load(open(f)):
            for k in ("email", "personal_email"):
                e = (l.get(k) or "").strip().lower()
                if e: known.add(e)
    for f in glob.glob(str(ROOT / "output/verified/BAD_all.csv")):
        known |= {r["email"].lower() for r in csv.DictReader(open(f, encoding="utf-8-sig"))}
    FREE = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "msn.com", "live.com", "comcast.net", "att.net", "verizon.net", "sbcglobal.net"}
    known_dom -= FREE
    print(f"[w5x] {len(files)} files; {len(known)} known emails; {len(known_dom)} suppressed domains")

    max_id = {n: max([int(r["lead_id"].split("-")[1]) for r in master if r["campaign"] == n] or [0]) for n in NICHES}
    max_so = {n: max([int(r["send_order"]) for r in master if r["campaign"] == n] or [0]) for n in NICHES}
    max_bl = {n: max([int(r["block_no"]) for r in master if r["campaign"] == n] or [0]) for n in NICHES}
    per_co = defaultdict(int)

    raw = defaultdict(list)
    for f in files:
        n = niche_of(Path(f).name)
        for l in json.load(open(f)): raw[n].append(l)

    new_rows = []
    for niche in ("msp", "marketing_agency", "insurance_broker", "pest_control", "landscaping"):
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
            if (cdom and cdom in known_dom) or (edom not in FREE and edom in known_dom):
                drop["domain_on_sheet"] += 1; continue
            if (l.get("company_size") or 0) > CEILING[niche]: drop["oversized"] += 1; continue
            blob = " ".join([l.get("company_name") or "", l.get("company_description") or "", l.get("headline") or "", str(l.get("keywords") or ""), l.get("industry") or ""]).lower()
            name = (l.get("company_name") or "").lower()
            skip = set(BLOB_SKIP.get(niche, "").split("|")) - {""}
            off_blob = "|".join(a for a in OFF[niche].split("|") if a not in skip)
            if (OFF_NAME[niche] and re.search(OFF_NAME[niche], name)) or re.search(off_blob, name) or (re.search(off_blob, blob) and not re.search(ON[niche], name)):
                if niche == "pest_control" and re.search(ON["landscaping"], blob) and not re.search(OFF["landscaping"], name):
                    l["_reroute"] = "landscaping"; raw["landscaping"].append(l); drop["rerouted_to_landscaping"] += 1; continue
                drop["off_niche"] += 1; continue
            if not re.search(ON[niche], blob): drop["no_niche_signal"] += 1; continue
            t = l.get("job_title") or ""
            if not OWNER_TITLE.search(t) or (NOT_OWNER.search(t) and not re.search(r"ceo|president|owner|founder|managing", t, re.I)):
                drop["not_owner_title"] += 1; continue
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
                      "email_quality": "Unverified (Apify validated)", "lead_id": f"{NICHES[niche]}-{max_id[niche]:05d}",
                      "email": clean(l["_email"]), "email_source": l["_src"], "mv_result": "unverified",
                      "contact_rank_at_company": l["_rank"], "company_city": clean(l.get("company_city")), "company_state": clean(cst),
                      "location_note": "contact state differs from company state" if cst and st and cst.lower() != st.lower() else "",
                      "personalization_status": "", "icebreaker": "", "angle": "", "research_notes": "", "personalized_at": ""})
            new_rows.append(r)
        print(f"  {niche:18s} raw={len(raw[niche]):5d} kept={len(kept):5d} dropped={dict(drop)}")

    with OUTCSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(new_rows)
    print(f"[w5x] {len(new_rows)} new unverified leads -> {OUTCSV.name}  ({dict(Counter(r['campaign'] for r in new_rows))})")
    if not apply: return

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
    print(f"[w5x] precheck appended: {dict(Counter(p['route'] for p in pre_rows))}")
    with MASTER.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=cols, extrasaction="ignore").writerows(new_rows)
    from sheet_io import open_tab
    ws = open_tab(SHEET_ID); hdr = ws.row_values(1)
    vals = [[r.get(h, "") for h in hdr] for r in new_rows]
    for i in range(0, len(vals), 1000):
        ws.append_rows(vals[i:i+1000], value_input_option="RAW")
    print(f"[w5x] appended {len(vals)} rows to sheet + MASTER")


if __name__ == "__main__":
    main()
