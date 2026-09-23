#!/usr/bin/env python3
"""Template mode, step 4: stage the X-fill for the writer, then merge and template.

  python3 personalize/daily_fill.py <batch_dir>            # -> fill_chunk_<k>.json (50 leads each)
  python3 personalize/daily_fill.py <batch_dir> --merge    # x_*.json -> x.json -> lines.json

Each fill chunk carries everything the writer may use for X: extracted niche facts,
the scrape's company description / headline, city and state. The writer returns
x_<k>.json: [{"lead_id":"", "x":"", "y":""}]. --merge renders prompts.json's template.
"""
import glob, json, sys
from pathlib import Path

CHUNK = 50


def main():
    bdir = Path(sys.argv[1]); root = Path(__file__).resolve().parent
    P = json.loads((root / "prompts.json").read_text())
    sel = {s["lead_id"]: s for s in json.loads((bdir / "select.json").read_text())}
    leads = {l["lead_id"]: l for l in json.loads((bdir / "leads.json").read_text())}
    if "--merge" in sys.argv:
        xs = {}
        files = sorted(f for f in glob.glob(str(bdir / "x_*.json")) if "rewrite" not in f) + sorted(glob.glob(str(bdir / "x_rewrite*.json")))
        for f in files:
            for o in json.load(open(f)):
                xs[o["lead_id"]] = {"x": (o.get("x") or "").strip().rstrip("."), "y": (o.get("y") or "").strip().rstrip(".,"),
                                    "specialty": (o.get("specialty") or "").strip().rstrip(".")}
        (bdir / "x.json").write_text(json.dumps(xs, indent=1))
        lines = []
        for lid, v in xs.items():
            fn = (sel[lid].get("first_name") or "").strip()
            t = P["template"] if fn else P["template_no_name"]
            ok = v["x"] and ("{y}" not in t or v["y"])
            lines.append({"lead_id": lid, "icebreaker": t.format(first_name=fn, x=v["x"], y=v["y"]) if ok else ""})
        (bdir / "lines.json").write_text(json.dumps(lines, indent=1))
        print(f"[fill] merged {len(xs)} X values -> x.json, lines.json")
        return
    ex = {}
    if (bdir / "extract.json").exists():
        ex = {o["lead_id"]: o for o in json.loads((bdir / "extract.json").read_text())}
    rows = []
    for lid, s in sel.items():
        if s["tier"] == "skip": continue
        l = leads[lid]; e = ex.get(lid, {})
        rows.append({"lead_id": lid, "campaign": s["campaign"], "company_name": s["company_name"],
                     "named_niche": e.get("named_niche", ""), "what_it_is": e.get("what_it_is", ""),
                     "service_traits": e.get("service_traits", []), "headline": l.get("headline", ""),
                     "company_description": (l.get("company_description") or "")[:400],
                     "city": l.get("company_city", ""), "state": l.get("company_state", "")})
    for k in range(0, len(rows), CHUNK):
        (bdir / f"fill_chunk_{k // CHUNK + 1}.json").write_text(json.dumps(rows[k:k + CHUNK], indent=1))
    print(f"[fill] {len(rows)} leads -> {(len(rows) + CHUNK - 1) // CHUNK} fill chunks of {CHUNK}")


if __name__ == "__main__":
    main()
