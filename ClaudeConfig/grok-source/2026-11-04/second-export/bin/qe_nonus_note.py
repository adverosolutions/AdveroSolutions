#!/usr/bin/env python3
"""Add a 'non-US:<country code>' note to fit_reason for rows whose country is not US (G-* searches, 2026-10-21).
fit itself is never changed. Idempotent. Usage: qe_nonus_note.py POOL_NEW.csv [...]  (rewrites in place)"""
import csv, sys, json
US = {"", "us", "usa", "united states", "united states of america"}
out = {}
for p in sys.argv[1:]:
    with open(p, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh); hdr = r.fieldnames; rows = list(r)
    n = 0
    for row in rows:
        cc = (row.get("country") or "").strip()
        if cc.lower() in US or "non-US:" in (row.get("fit_reason") or ""):
            continue
        code = {"canada": "CA", "united kingdom": "GB", "uk": "GB", "australia": "AU"}.get(cc.lower(), cc.upper())
        row["fit_reason"] = (row.get("fit_reason") or "").rstrip() + f"; non-US:{code}"; n += 1
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr); w.writeheader(); w.writerows(rows)
    out[p] = n
print(json.dumps(out, indent=1))
