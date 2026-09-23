#!/usr/bin/env python3
"""Step 4b: stage a rewrite pass for lines the gate / variety cap rejected.

  python3 personalize/daily_rewrite.py <batch_dir>            # -> rewrite_needed.json
  python3 personalize/daily_rewrite.py <batch_dir> --merge    # fold lines_rewrite*.json into lines.json

The writer subagent reads rewrite_needed.json (lead, facts, previous line, why it
failed) and returns lines_rewrite_<k>.json. --merge overwrites those lead_ids in
lines.json, then daily_apply.py is run again. Repeat until nothing is flagged or
the remainder is small enough to hand-fix.
"""
import glob, json, sys
from pathlib import Path
from daily_apply import load, all_flags


def main():
    bdir = Path(sys.argv[1])
    import daily_apply; daily_apply.BDIR = bdir
    sel, lines = load(bdir)
    xs = json.loads((bdir / "x.json").read_text()) if (bdir / "x.json").exists() else None
    if "--merge" in sys.argv:
        new = {}
        for f in sorted(glob.glob(str(bdir / "lines_rewrite*.json"))):
            for l in json.load(open(f)): new[l["lead_id"]] = l.get("icebreaker", "")
        for lid, ln in new.items(): lines[lid] = ln
        (bdir / "lines.json").write_text(json.dumps([{"lead_id": k, "icebreaker": v} for k, v in lines.items()], indent=1))
        print(f"[rewrite] merged {len(new)} rewritten lines into lines.json")
        return
    from daily_apply import apply_approvals
    flags = {k: v for k, v in apply_approvals(all_flags(sel, lines, xs), bdir).items() if not v.startswith("skipped:")}
    data = {}
    import glob
    for f in glob.glob(str(bdir / "fill_chunk_*.json")):
        for r in json.load(open(f)): data[r["lead_id"]] = r
    out = [{"lead_id": lid, "campaign": sel[lid]["campaign"], "tier": sel[lid]["tier"], "first_name": sel[lid]["first_name"],
            "company_name": sel[lid]["company_name"], "facts": sel[lid].get("facts", {}),
            "previous_x": (xs or {}).get(lid, {}).get("x", ""), "previous_y": (xs or {}).get(lid, {}).get("y", ""), "rejected_because": why,
            "lead_data": data.get(lid, {})} for lid, why in flags.items()]
    (bdir / "rewrite_needed.json").write_text(json.dumps(out, indent=1))
    print(f"[rewrite] {len(out)} lines need a rewrite -> rewrite_needed.json")
    for o in out[:10]: print(f"   {o['lead_id']} [{o['campaign']}/t{o['tier']}] {o['rejected_because']}")


if __name__ == "__main__":
    main()
