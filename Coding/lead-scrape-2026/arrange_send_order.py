#!/usr/bin/env python3
"""Arrange each niche's leads into a send order that keeps the rolling bounce
rate low: repeating blocks of CLEAN then a few RISKY, with surplus risky pushed
to the end so a campaign can be cut cleanly without losing clean sends.

  python3 arrange_send_order.py                 # default 25 clean : 5 catch-all
  python3 arrange_send_order.py --clean 30 --risky 3

Adds, per row: campaign, send_order, block_no, block_type, email_quality.
Rewrites output/FINAL/MASTER_for_sheets.csv (sorted campaign -> send_order).
"""
import argparse, csv
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path("output/FINAL/SENDABLE_3niches.csv")
OUT = Path("output/FINAL/MASTER_for_sheets.csv")
QUALITY = {"ok": "Verified clean", "catch_all": "Risky: catch-all", "unknown": "Risky: unknown"}

FRONT = ["campaign", "send_order", "block_no", "block_type", "email_quality",
         "lead_id", "first_name", "last_name", "job_title", "email", "email_source", "mv_result",
         "company_name", "company_website", "company_domain", "city", "state", "company_size", "industry"]
PERS = ["personalization_status", "icebreaker", "angle", "research_notes", "personalized_at"]
BACK = ["company_phone", "mobile_number", "linkedin", "company_linkedin", "company_annual_revenue_clean",
        "company_full_address", "headline", "company_description", "company_technologies",
        "company_founded_year", "seniority_level", "contact_rank_at_company"]


def arrange(rows, clean_n, risky_n):
    """Return rows in send order with block labels."""
    src_first = lambda r: (int(r["contact_rank_at_company"] or 1), 0 if r["email_source"] == "business" else 1)
    clean = sorted([r for r in rows if r["mv_result"] == "ok"], key=src_first)
    catch = sorted([r for r in rows if r["mv_result"] == "catch_all"], key=src_first)
    unk = sorted([r for r in rows if r["mv_result"] == "unknown"], key=src_first)
    out, block, ci, ki = [], 0, 0, 0
    while ci < len(clean):
        block += 1
        for r in clean[ci:ci + clean_n]:
            out.append({**r, "block_no": block, "block_type": "CLEAN"})
        ci += clean_n
        for r in catch[ki:ki + risky_n]:
            out.append({**r, "block_no": block, "block_type": "RISKY_MIX"})
        ki += risky_n
    block += 1
    for r in catch[ki:]:
        out.append({**r, "block_no": block, "block_type": "RISKY_OVERFLOW"})
    block += 1
    for r in unk:
        out.append({**r, "block_no": block, "block_type": "UNKNOWN_LAST"})
    for i, r in enumerate(out, 1):
        r["send_order"] = i
        r["campaign"] = r["niche"]
        r["email_quality"] = QUALITY.get(r["mv_result"], r["mv_result"])
        r["lead_id"] = f"{r['niche'][:2].upper()}-{i:05d}"
        for p in PERS:
            r.setdefault(p, "")
    return out, ki


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", type=int, default=25); ap.add_argument("--risky", type=int, default=5)
    a = ap.parse_args()
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    by = defaultdict(list)
    for r in rows:
        by[r["niche"]].append(r)

    final, cols = [], FRONT + PERS + BACK
    print(f"pattern: {a.clean} clean -> {a.risky} catch-all, repeat; surplus catch-all then unknown at the end\n")
    print(f"{'campaign':12s} {'clean':>6s} {'mixed-in':>9s} {'overflow':>9s} {'unknown':>8s} {'total':>6s}   risky share in mixed zone")
    for niche in ("recruiting", "bookkeeping", "cleaning"):
        ordered, used = arrange(by[niche], a.clean, a.risky)
        c = Counter(r["block_type"] for r in ordered)
        mix_share = used / max(1, c["CLEAN"] + used)
        print(f"{niche:12s} {c['CLEAN']:6d} {c['RISKY_MIX']:9d} {c['RISKY_OVERFLOW']:9d} {c['UNKNOWN_LAST']:8d} {len(ordered):6d}   {mix_share:.0%}")
        final += ordered

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(final)
    print(f"\n-> {OUT}  ({len(final)} rows, {len(cols)} cols)")

    # what the mix means for bounce rate, under three catch-all bounce assumptions
    share = a.risky / (a.clean + a.risky)
    print(f"\nexpected bounce rate inside the mixed zone (clean assumed ~2%):")
    for ca in (0.08, 0.15, 0.25):
        print(f"   if catch-alls bounce {ca:.0%}: {(1-share)*0.02 + share*ca:.1%}")


if __name__ == "__main__":
    main()
