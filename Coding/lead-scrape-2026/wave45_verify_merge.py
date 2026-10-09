#!/usr/bin/env python3
"""Apply MillionVerifier results for the wave-4/5 unverified rows to MASTER + the sheet.

  python3 wave45_verify_merge.py            # dry run
  python3 wave45_verify_merge.py --apply

ok        -> mv_result ok,        email_quality "Verified clean",   block_type CLEAN_W45
catch_all -> mv_result catch_all, email_quality "Risky: catch-all", block_type RISKY_W45
unknown   -> mv_result unknown,   email_quality "Risky: unknown",   block_type RISKY_W45
invalid/disposable -> mv_result as-is, email_quality "Invalid", block_type INVALID,
                      personalization_status "skipped: invalid email"
"""
import csv, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "personalize"))
ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv"
RES = ROOT / "verify" / "results_w45.csv"
ALLRES = ROOT / "verify" / "results.csv"
SHEET_ID = "1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw"
Q = {"ok": ("Verified clean", "CLEAN_W45"), "catch_all": ("Risky: catch-all", "RISKY_W45"), "unknown": ("Risky: unknown", "RISKY_W45")}


def load_results():
    res = {}
    with RES.open(encoding="utf-8-sig", errors="replace") as f:
        sample = f.read(4096); f.seek(0)
        d = "," if sample.count(",") >= sample.count(";") else ";"
        rdr = csv.reader(f, delimiter=d); hdr = [h.strip().lower() for h in next(rdr)]
        ei = hdr.index("email"); ri = hdr.index("result") if "result" in hdr else hdr.index("quality")
        for row in rdr:
            if len(row) > max(ei, ri): res[row[ei].strip().lower()] = row[ri].strip().lower()
    return res, hdr


def main():
    apply = "--apply" in sys.argv
    res, hdr = load_results()
    print(f"[merge] {len(res)} results: {dict(Counter(res.values()))}")
    master = list(csv.DictReader(MASTER.open(encoding="utf-8-sig"))); cols = list(master[0].keys())
    changed, missing, per = {}, 0, Counter()
    for r in master:
        if r["mv_result"] != "unverified": continue
        v = res.get(r["email"].strip().lower())
        if not v: missing += 1; continue
        r["mv_result"] = v
        if v in Q:
            r["email_quality"], r["block_type"] = Q[v]
        else:
            r["email_quality"], r["block_type"] = "Invalid", "INVALID"
            if not r["personalization_status"].strip(): r["personalization_status"] = "skipped: invalid email"
        changed[r["lead_id"]] = r; per[(r["campaign"], v)] += 1
    print(f"[merge] {len(changed)} rows updated, {missing} unverified rows without a result")
    for c in sorted({k[0] for k in per}):
        tot = sum(n for (cc, v), n in per.items() if cc == c); ok = per[(c, "ok")]
        print(f"  {c:18s} total={tot:5d} ok={ok:5d} ({100*ok//max(1,tot)}%) catch_all={per[(c,'catch_all')]:4d} unknown={per[(c,'unknown')]:3d} invalid={per[(c,'invalid')]+per[(c,'disposable')]:4d}")
    if not apply: return
    with MASTER.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(master)
    with ALLRES.open("a", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "quality", "result", "free", "role"])
        for e, v in res.items(): w.writerow({"email": e, "result": v})
    from sheet_io import open_tab
    import gspread
    ws = open_tab(SHEET_ID); h = ws.row_values(1); col = {n: i + 1 for i, n in enumerate(h)}
    ids = ws.col_values(col["lead_id"])
    a1 = gspread.utils.rowcol_to_a1
    ups = []
    for i, lid in enumerate(ids[1:], start=2):
        r = changed.get(lid)
        if not r: continue
        for k in ("mv_result", "email_quality", "block_type"):
            ups.append({"range": a1(i, col[k]), "values": [[r[k]]]})
        if r["personalization_status"] == "skipped: invalid email":
            ups.append({"range": a1(i, col["personalization_status"]), "values": [[r["personalization_status"]]]})
    for j in range(0, len(ups), 5000):
        ws.batch_update(ups[j:j+5000], value_input_option="RAW")
    print(f"[merge] sheet: {len(ups)} cells updated")


if __name__ == "__main__":
    main()
