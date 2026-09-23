#!/usr/bin/env python3
"""Step 3: rules that decide tier + anchor for each lead from extract.json.

  python3 personalize/daily_select.py <batch_dir>

Reads leads.json + extract.json (from the extraction subagent), writes
select.json: per lead -> tier (2 / 1 / skip), anchor text, the facts the
writer may use, and the source URL. Guessability bar is encoded here:
generic credentials (CPA for a CPA firm) and commodity services never anchor.
"""
import json, sys
from pathlib import Path

GENERIC = {"cpa", "certified public accountant", "licensed", "insured", "bonded", "professional", "quality", "experienced"}


SLOGAN_WORDS = {"relationship", "relationships", "passion", "vision", "headache", "headaches", "quality", "trust",
                "trusted", "service", "services", "solution", "solutions", "partner", "partners", "excellence", "mission",
                "dedicated", "commitment", "committed", "care", "peace of mind", "one-stop", "one stop", "re-imagine",
                "reimagine", "clearer", "better", "best", "your success", "we help", "we build", "we don't just"}


def distinctive_quote(q):
    """A voice quote counts only if it is not a generic marketing slogan."""
    q = (q or "").strip()
    if not (4 <= len(q.split()) <= 14): return ""
    low = q.lower()
    return "" if any(w in low for w in SLOGAN_WORDS) else q


def pick_anchor(niche, e):
    """Return (anchor_label, anchor_text) or (None, None). Order = least guessable first."""
    g = (e.get("guarantee") or "").strip()
    if g: return "guarantee", g
    n = (e.get("named_niche") or "").strip()
    if n and len(n) > 3 and n.lower() not in {"small business", "small businesses", "individuals", "businesses", "commercial", "businesses and individuals"}:
        return "named niche", n
    c = (e.get("credential") or "").strip()
    if c and c.lower() not in GENERIC and not (niche == "bookkeeping" and c.lower().startswith("cpa")):
        return "credential", c
    y = e.get("founded_year")
    try:
        y = int(y)
        if 1900 < y <= 2026 and 2026 - y >= 15: return "years in business", f"founded {y} ({2026 - y} years)"
    except (TypeError, ValueError):
        pass
    yc = (e.get("years_claim") or "").strip()
    if yc: return "years in business", yc
    q = distinctive_quote(e.get("about_voice_quote"))
    if q: return "about-page voice", q
    return None, None


def main():
    bdir = Path(sys.argv[1])
    leads = json.loads((bdir / "leads.json").read_text())
    ext = {}
    if (bdir / "extract.json").exists():
        ext = {e["lead_id"]: e for e in json.loads((bdir / "extract.json").read_text())}
    out, tally = [], {"2": 0, "1": 0, "skip": 0}
    for l in leads:
        e = ext.get(l["lead_id"], {})
        rec = {"lead_id": l["lead_id"], "campaign": l["campaign"], "first_name": l["first_name"],
               "company_name": l["company_name"], "sheet_row": l["sheet_row"], "source_url": "", "facts": {}}
        if e and e.get("is_in_niche") is False:
            rec.update(tier="skip", angle=f"skipped: extraction says not a {l['campaign']} company ({e.get('what_it_is','')[:60]})")
        elif l["route"] == "TIER2_CANDIDATE" and e:
            label, text = pick_anchor(l["campaign"], e)
            if label:
                rec.update(tier=2, angle=f"researched: {label}: {text[:80]}", source_url=e.get("source_url", ""),
                           facts={"anchor_type": label, "anchor": text, "named_niche": e.get("named_niche", ""),
                                  "founded_year": e.get("founded_year"), "guarantee": e.get("guarantee", ""),
                                  "credential": e.get("credential", ""), "about_voice_quote": e.get("about_voice_quote", ""),
                                  "service_traits": e.get("service_traits", [])})
            else:
                rec.update(tier=1, angle="cold-read: no distinctive fact found on site")
        else:
            rec.update(tier=1, angle="cold-read: " + ("site dead/unreachable" if l["route"] == "TIER1_ONLY" else "no extraction"))
        tally[str(rec["tier"])] += 1
        out.append(rec)
    (bdir / "select.json").write_text(json.dumps(out, indent=1))
    print(f"[select] tier2={tally['2']} tier1={tally['1']} skip={tally['skip']} -> {bdir/'select.json'}")


if __name__ == "__main__":
    main()
