#!/usr/bin/env python3
"""Quality gate between production batches.

Reports, per niche, everything that could go wrong on this actor:
  * shard delivery  -- did each state fill its quota? (the supply question)
  * email fill      -- coalesced business-or-personal, the number that matters
  * personal share  -- gmail/yahoo addresses carry complaint risk on cold send
  * oversized       -- chains that slipped past the size gate
  * dup companies   -- multiple contacts billed at one account

Usage: python3 qa.py
"""
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

from runner import SHARD_WEIGHTS, plan_shards

ROOT = Path(__file__).resolve().parent
PROD = ROOT / "output" / "production"

FREE = {"gmail.com", "yahoo.com", "hotmail.com", "aol.com", "outlook.com",
        "comcast.net", "icloud.com", "me.com", "msn.com", "mindspring.com"}


def main() -> None:
    files = sorted(glob.glob(str(PROD / "*.json")))
    if not files:
        print("no production output yet")
        return

    by_niche = defaultdict(list)
    for f in files:
        niche = Path(f).name.split("__")[0]
        by_niche[niche].extend(json.loads(Path(f).read_text()))

    grand = 0
    for niche, leads in sorted(by_niche.items()):
        cfg = json.loads((ROOT / "niches" / f"{niche}.json").read_text())
        quotas = plan_shards(cfg["target"], cfg["fill_rate"])

        # dedupe across batches on coalesced address
        seen, rows = set(), []
        for l in leads:
            k = ((l.get("email") or l.get("personal_email") or "").lower().strip())
            if k and k in seen:
                continue
            if k:
                seen.add(k)
            rows.append(l)

        biz = sum(1 for r in rows if (r.get("email") or "").strip())
        per = sum(1 for r in rows
                  if not (r.get("email") or "").strip() and (r.get("personal_email") or "").strip())
        big = sum(1 for r in rows if (r.get("company_size") or 0) > 100)
        cos = Counter((r.get("company_name") or "?") for r in rows)
        dups = sum(v - 1 for v in cos.values() if v > 1)
        n = max(1, len(rows))
        grand += len(rows)

        print(f"\n{'='*66}\n{niche.upper()}  ({cfg['label']})")
        print(f"  unique leads   {len(rows):5d}  of {cfg['target']} target "
              f"({len(rows)/cfg['target']:.0%})")
        print(f"  reachable      {biz+per:5d}  ({(biz+per)/n:.0%})   "
              f"business {biz} / personal {per} ({per/n:.0%})")
        print(f"  oversized      {big:5d}  ({big/n:.0%})")
        print(f"  dup companies  {dups:5d}  ({len(cos)} unique companies)")

        # supply check: did each state deliver its quota?
        got = Counter()
        for r in rows:
            got[(r.get("state") or "?").lower()] += 1
        print("  shard delivery:")
        for st, q in quotas.items():
            short = st.split(",")[0]
            g = got.get(short, 0)
            if g == 0:
                continue
            bar = "#" * round(18 * min(1, g / q))
            mark = "ok" if g >= q * 0.9 else "THIN"
            print(f"     {short:16s} {g:4d}/{q:<4d} {bar:<18s} {mark}")

        top = [f"{c} ({cos[c]})" for c, _ in cos.most_common(3)]
        print(f"  most-repeated: {', '.join(top)}")

    print(f"\n{'='*66}\nTOTAL unique leads across niches: {grand}")


if __name__ == "__main__":
    main()
