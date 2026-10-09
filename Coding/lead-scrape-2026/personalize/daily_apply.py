#!/usr/bin/env python3
"""Step 5+: QA gate every written line, write results to the sheet, export the
day's send-ready CSV.

  python3 personalize/daily_apply.py <batch_dir>

Reads select.json + lines.json (from the writer subagents). A line that fails
the gate is written to the sheet as "flagged: <reason>" (never "done"), so it
can be regenerated or fixed by hand. Prints a summary and 8 sample lines.
"""
import csv, json, re, sys
from datetime import datetime
from pathlib import Path
import gspread
from sheet_io import open_tab, ROOT

SHEET_ID = "1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw"
BANNED = ["that takes", "smart focus", "respect for", "most firms", "most shops", "most crews", "most accountants", "most recruiters", "most cpa", "most tax", "is rare", "getting rare", "is bold", "won't make", "can't do that", "steer clear", "history to lean on", "not an accident", "rarer than it should be", "as it gets", "real systems", "says a lot about", "a different level", "serious run", "that discipline", "that selectivity", "commit that hard", "stay generalist", "i noticed", "i came across", "reaching out", "hope this finds", "touch base", "run something by",
          "my buddy", "my gf", "our team", " we ", "quick question", "wanted to", "just wanted"]
SITE_WORDS = ["your site", "your website", "your page", "about page", "saw your work", "your portfolio"]
# "fact, then a label for the fact" is the template tell: nobody at a bar says "that's a specific lane".
LABEL_RE = re.compile(r"that's an? (?:\w+ )?(?:wide|specific|nice|big|good|solid|smart|tight|narrow|rare|tough|serious|bold|real|different|fun|great|interesting|unusual|cool|clear|strong|healthy|deep|broad|whole|awesome|lot of)\b|that's an? \w+ (?:range|lane|mix|crowd|niche|list|spread|combo|story|specialty|focus|move|call|way)\b")
# tie-in must stay inside the campaign's niche: no other verticals, no "I work with X as well" phrasing
CROSS_NICHE = ["all in on", "i only work with", "my whole world", " man ", " man.", " man,", " bro ", " dude ", "impressive", "commendable", "i appreciate", "medical practices", "the trades", "contractors", "service businesses", "small business owners myself", "lending side", "real estate myself", "i work with a lot", "i've worked with", "i have worked", "as well", "similarly", "likewise", "i have experience"]
# consequence guesses / editorializing: the line proves research and praises, nothing else
GUESS = ["must be", "must have", "gotta be", "have gotta", "probably", " bet ", "no wonder", "those guys", "i'd guess", "i bet"]
STOCK = ["stays interesting", "keeps you sharp", "keeps you busy", "keep you busy", "keeps things interesting", "no two days", "seen some things", "seen it all", "seen just about everything", "never a dull", "on your toes"]
# reaction markers counted for batch variety; any one of them above VARIETY_CAP of the batch flags the extra lines
MARKERS = ["love", "awesome", "congrats", "big fan", "huge", "cool", "nice", "solid", "that's"]
FRAMES = ["looks like", "love that", "just saw", "saw you"]
CRUTCH = ["these days", "caught my eye", "hit home", "totally get it"]
VARIETY_CAP = 0.40


NICHE_WORDS = {"recruiting": ["recruit", "search", "staffing", "placement", "hiring", "talent", "headhunt"],
               "cleaning": ["clean", "janitorial"],
               "bookkeeping": ["tax", "accounting", "bookkeeping", "cpa", "payroll", "audit"],
               "msp": ["it ", "it support", "managed", "network", "cyber", "help desk", "tech support", "computer"],
               "marketing_agency": ["marketing", "seo", "ads", "advertising", "web design", "branding", "social media", "ppc", "lead gen", "pr ", "public relations"],
               "insurance_broker": ["insurance", "benefits", "coverage", "brokerage"],
               "landscaping": ["landscap", "lawn", "grounds", "turf", "tree", "snow", "irrigation", "hardscap"],
               "pest_control": ["pest", "extermin", "termite", "wildlife", "mosquito", "rodent", "bug"]}
MARKETING = ["top-tier", "finest", "human capital", "quality and efficiency", "providing", "finding and implementing", "demanding", "specialized hiring needs", "solutions", "premier", "state of the art", "state-of-the-art", "unparalleled", "full service", "full-service", "tailored", "comprehensive", "cutting edge", "cutting-edge", "world class", "world-class", "innovative", "trusted"]


def x_gate(sel, x, data=None):
    """Template mode: only X varies, so only X is judged."""
    if not x: return "empty"
    if x.lower().startswith("all of "): return "x grammar"
    if data is not None and grounded(x, lead_text(sel, data)) < 0.6: return "x not grounded in the lead's data"
    w = len(x.split())
    if w < 3 or w > 10: return f"x length {w}w"
    low = " " + x.lower() + " "
    if x.rstrip().endswith("."): return "x ends with a period"
    if "—" in x or "–" in x or "?" in x: return "dash or question in x"
    for b in (" you ", " your ", " we ", " our ", " i "):
        if b in low: return f"pronoun in x '{b.strip()}'"
    for b in MARKETING:
        if b in low: return f"marketing word in x '{b}'"
    co = (sel.get("company_name") or "").lower().split(",")[0].strip()
    if co and len(co) > 4 and co in low: return "company name in x"
    if not any(k in low for k in NICHE_WORDS.get(sel["campaign"], [])): return "x does not name the niche"
    return ""


Y_BAN = ["busy", "handful", "grind", "nightmare", "headache", "stress", "tough", "hard", "crazy", "problem", "struggle", "should", "need to", "could be", "?",
         "staffing challenges", "talent network", "deduction rule", "strategy portfolio", "by speed dial", "'s every", "financials on speed dial",
         "in the area", "your market", "the area's", "best talent", "top talent", "talent by", "entire tech scene", "half the continent",
         "two states", "memorized", "in your network", "candidate network", "in your rolodex"]
US_STATES = {"alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana","nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina","south dakota","tennessee","texas","utah","vermont","virginia","washington","west virginia","wisconsin","wyoming","district of columbia"}
STATE_ALIASES = {"new york": ["manhattan", "long island", "nassau", "nyc", "midtown", "brooklyn", "queens", "five boroughs", "buffalo", "westchester"],
                 "florida": ["treasure coast", "south florida", "gulf coast"], "massachusetts": ["new england", "boston"],
                 "new jersey": ["jersey"], "illinois": ["central illinois", "chicagoland"], "pennsylvania": ["main line", "chester county", "the valley"],
                 "california": ["la", "bay area", "san diego county", "socal", "la county"], "south carolina": ["lowcountry"], "west virginia": ["the valley"],
                 "district of columbia": ["dc"], "ohio": ["northern ohio", "northeast ohio"], "michigan": ["metro detroit"]}
# words Y may use without them appearing in the lead's own data
Y_FREE = {"business", "owner", "owners", "manager", "managers", "director", "directors", "office", "offices", "building", "buildings", "facility", "facilities", "property", "properties",
          "hiring", "hire", "hires", "employer", "employers", "engineer", "engineers", "exec", "execs", "executive", "executives", "founder", "founders", "client", "clients", "company", "companies",
          "town", "state", "region", "county", "area", "books", "month's", "return", "returns", "taxes", "tax", "rolodex", "rolodexes", "desk", "half", "every", "sleep", "speed", "dial", "name", "now",
          "able", "close", "know", "have", "must", "you", "one", "the", "of", "in", "on", "by", "at", "a", "an", "your", "and", "or", "to", "be", "with", "all", "around", "entire", "biggest", "deepest", "whole", "kind",
          "small", "local", "firm", "firms", "shop", "shops", "book", "file", "audit", "payroll", "search", "searches", "placement", "placements", "candidates", "candidate", "spot", "sharp", "keep", "run", "service", "handle", "manage", "do",
          "professionals", "people", "talent", "type", "types", "major", "startups", "startup", "entrepreneur", "entrepreneurs", "landlord", "landlords", "contractor", "contractors", "practice", "clinic", "clinics", "hospital", "hospitals",
          "server", "servers", "network", "networks", "password", "passwords", "ticket", "tickets", "policy", "policies", "renewal", "renewals", "claim", "claims", "campaign", "campaigns", "site", "sites", "website", "websites",
          "lawn", "lawns", "yard", "yards", "mower", "mowers", "hedge", "hedges", "bug", "bugs", "termite", "termites", "trap", "traps", "restaurant", "restaurants", "warehouse", "warehouses", "storefront", "storefronts", "plaza", "plazas", "hoa", "hoas", "complex", "complexes", "campus", "campuses", "keyword", "keywords", "quote", "quotes", "rate", "rates"}
NICHE_CLASH = {"recruiting": ["books", "taxes", "tax ", "return", "clean", "facilit", "recruiter"],
               "cleaning": ["staffing", "hire", "hiring", "books", "taxes", "recruit", "talent"],
               "bookkeeping": ["staffing", "hire", "hiring", "clean", "facilit", "recruit", "accountant", "cpa", "talent"],
               "msp": ["books", "taxes", "clean", "recruit", "talent", "hiring", "landscap", "pest"],
               "marketing_agency": ["books", "taxes", "clean", "recruit", "talent", "hiring", "landscap", "pest", "marketer"],
               "insurance_broker": ["books", "taxes", "clean", "recruit", "talent", "hiring", "landscap", "pest", "insurance agent", "salesman"],
               "landscaping": ["books", "taxes", "clean", "recruit", "talent", "hiring", "pest", "landscaper", "janitor"],
               "pest_control": ["books", "taxes", "clean", "recruit", "talent", "hiring", "landscap", "exterminator", "janitor"]}
STOP = {"and", "for", "of", "the", "in", "to", "with", "a", "an", "&", "services", "service", "out", "on", "across", "throughout", "work", "firm", "company", "companies", "professionals", "roles", "business", "businesses", "small", "commercial", "local"}
NICHE_GENERIC = {"recruiting", "recruitment", "recruit", "search", "staffing", "placement", "placements", "hiring", "talent", "executive", "cleaning", "janitorial", "maintenance", "tax", "taxes", "accounting", "bookkeeping", "cpa", "payroll", "planning", "preparation", "consulting", "advisory", "financial", "finance",
                 "managed", "network", "networks", "support", "cyber", "cybersecurity", "cloud", "technology", "marketing", "seo", "ads", "advertising", "branding", "design", "media", "digital",
                 "insurance", "benefits", "coverage", "brokerage", "broker", "commercial", "landscaping", "landscape", "lawn", "grounds", "maintenance", "turf", "tree", "snow", "pest", "control", "termite", "wildlife"}


def lead_text(sel_row, data):
    d = data or {}
    raw = " ".join(str(v) for v in [d.get("named_niche"), d.get("what_it_is"), " ".join(d.get("service_traits") or []), d.get("headline"), d.get("company_description"), d.get("city"), d.get("state"), sel_row.get("company_name")] if v).lower()
    return " " + " ".join(re.findall(r"[a-z0-9]+", raw)) + " "


def grounded(phrase, text, extra_ok=()):
    """Share of a phrase's content words that appear in the lead's own data."""
    words = re.findall(r"[a-z0-9]+", phrase.lower().replace("'s", "").replace("’s", ""))
    words = [w for w in words if w and w not in STOP and w not in NICHE_GENERIC and w not in extra_ok and len(w) > 2]
    if not words: return 1.0
    stems = [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words]
    return sum(1 for w in stems if (" " + w) in text) / len(words)


def place_ok(y, sel_row, data):
    """Every capitalised place-ish token in Y must come from the lead's city/state (or a known alias of its state) or X."""
    d = data or {}
    city = (d.get("city") or "").lower(); state = (d.get("state") or "").lower()
    ok_text = " ".join([city, state, (d.get("x") or "").lower(), " ".join(STATE_ALIASES.get(state, []))])
    toks = re.findall(r"\b[A-Z][a-zA-Z']+(?:\s[A-Z][a-zA-Z']+)*", y[1:] if y[:1].isupper() else y)
    for t in toks:
        tl = t.lower().rstrip("'s").replace("'s", "")
        if tl in {"or", "it", "cpg", "saas", "hvac", "plc", "hr", "dc", "la", "nyc", "ai", "cpa", "cpas", "irs", "hoa", "hoas", "edtech", "cfo", "cfos", "ceo", "ceos", "saas", "cpg", "plc", "it", "pr", "hr", "ai", "ev", "iot", "gtm", "gm", "gms", "vc", "vp", "vps", "cto", "ctos", "ors", "rn", "rns", "erp", "crm", "qa", "qb"}: continue
        if tl in ok_text or any(w in ok_text for w in tl.split() if len(w) > 3): continue
        return f"y names a place not in the lead's data ('{t}')"
    return ""


def y_gate(sel, y, data=None):
    if not y: return "y empty"
    low = " " + y.lower().strip() + " "
    w = len(y.split())
    if w < 4 or w > 12: return f"y length {w}w"
    if not low.strip().startswith("you must"): return "y does not start with 'you must'"
    for b in Y_BAN:
        if re.search(r"(?<![a-z])" + re.escape(b.strip()) + r"(?![a-z])", low): return f"y has '{b.strip()}'"
    if "—" in y or "–" in y: return "dash in y"
    if re.search(r"know (every|half)[^.]* on speed dial", low): return "y grammar ('know every ... on speed dial')"
    for b in NICHE_CLASH.get(sel["campaign"], []):
        if b in low: return f"y clashes with niche ('{b.strip()}')"
    if data is not None:
        why = place_ok(y, sel, data)
        if why: return why
        if grounded(y, lead_text(sel, data) + " " + (data.get("x") or "").lower(), Y_FREE) < 0.5: return "y invents a detail not in the lead's data"
    return ""


def foreign(data):
    st = ((data or {}).get("state") or "").strip().lower()
    return bool(st) and st not in US_STATES


def gate(sel, line):
    if not line: return "empty"
    w = len(line.split())
    if w < 20 or w > 42: return f"length {w}w"
    if "—" in line or "–" in line: return "em dash"
    if "?" in line: return "contains a question"
    low = " " + line.lower() + " "
    for b in BANNED:
        if b in low: return f"banned phrase '{b.strip()}'"
    m = LABEL_RE.search(low)
    if m: return f"labels the fact ('{m.group(0)}')"
    for b in STOCK:
        if b in low: return f"stock reaction '{b}'"
    for b in GUESS:
        if b in low: return f"editorializing '{b.strip()}'"
    for b in CROSS_NICHE:
        if b in low: return f"tie-in off-niche or stiff '{b}'"
    if not re.search(r"\b(i|i've|i'm|my)\b", low): return "missing first-person tie-in"
    fn = (sel.get("first_name") or "").strip()
    if fn and fn.lower() in low and not low.strip().startswith(f"hey {fn.lower()}"): return "name not at the front"
    if re.search(r"\d+\s?%", line) and not re.search(r"\d+\s?%", json.dumps(sel.get("facts", {}))): return "invented percentage"
    if sel["tier"] == 1 and any(s in low for s in SITE_WORDS): return "tier1 implies site was seen"
    if sel["tier"] == 2:
        pool = " ".join(str(v) for v in sel["facts"].values() if v).lower()
        toks = [t for t in re.findall(r"[a-z0-9]{4,}", pool) if t not in {"founded", "years", "since", "with", "that", "this", "your", "their"}]
        if toks and not any(t in low for t in toks): return "no provided fact appears in line (grounding)"
    return ""


def variety_flags(sel, lines):
    """Return {lead_id: reason} for lines that overuse one reaction marker across the batch.
    Each line is charged to its FIRST marker; the first cap-many lines using it pass, the rest flag."""
    import math
    live = [s for s in sorted(sel.values(), key=lambda x: x["sheet_row"]) if s["tier"] != "skip" and lines.get(s["lead_id"])]
    if len(live) < 8: return {}
    cap = max(2, math.ceil(VARIETY_CAP * len(live)))
    seen, out = {}, {}
    fcap = max(2, math.ceil(0.5 * len(live))); ccap = max(1, math.ceil(0.12 * len(live)))
    fseen, cseen = {}, {}
    for s in live:
        low = " " + lines[s["lead_id"]].lower() + " "
        hit = None
        for m in MARKERS:
            i = low.find(" " + m)
            if i >= 0 and (hit is None or i < hit[1]): hit = (m, i)
        if hit:
            seen[hit[0]] = seen.get(hit[0], 0) + 1
            if seen[hit[0]] > cap: out[s["lead_id"]] = f"variety: '{hit[0]}' already used {cap}x in batch"
        for f in FRAMES:
            if " " + f in low:
                fseen[f] = fseen.get(f, 0) + 1
                if fseen[f] > fcap: out.setdefault(s["lead_id"], f"variety: frame '{f}' already used {fcap}x in batch")
                break
        for c in CRUTCH:
            if c in low:
                cseen[c] = cseen.get(c, 0) + 1
                if cseen[c] > ccap: out.setdefault(s["lead_id"], f"variety: crutch '{c}' already used {ccap}x in batch")
    return out


def load(bdir):
    sel = {s["lead_id"]: s for s in json.loads((bdir / "select.json").read_text())}
    lines = {l["lead_id"]: l.get("icebreaker", "") for l in json.loads((bdir / "lines.json").read_text())} if (bdir / "lines.json").exists() else {}
    return sel, lines


BDIR = None


def all_flags(sel, lines, xs=None):
    """{lead_id: reason} for every live lead whose line fails the gate or the variety cap.
    Template mode (xs given): only X is judged; the fixed sentence needs no variety check."""
    out = {}
    if xs is not None:
        import math, collections, glob
        data = {}
        for f in glob.glob(str(BDIR / "fill_chunk_*.json")) if BDIR else []:
            for r in json.load(open(f)): data[r["lead_id"]] = r
        for lid, s in sel.items():
            if s["tier"] == "skip": continue
            v = xs.get(lid, {}) if isinstance(xs.get(lid), dict) else {"x": xs.get(lid, ""), "y": ""}
            d = dict(data.get(lid, {}), x=v.get("x", "")) if lid in data else None
            if d is not None and foreign(d): out[lid] = "skipped: foreign company"; continue
            why = x_gate(s, v.get("x", ""), d) or (y_gate(s, v.get("y", ""), d) if "y" in v else "")
            if why: out[lid] = why
        # y shape variety: no one shape on more than a third of the batch
        live = [lid for lid, s in sel.items() if s["tier"] != "skip" and lid not in out]
        if len(live) >= 8:
            cap = max(2, math.ceil(0.34 * len(live))); seen = collections.Counter()
            for lid in live:
                y = (xs.get(lid, {}) or {}).get("y", "").lower() if isinstance(xs.get(lid), dict) else ""
                for shape in ("speed dial", "by name", "in your sleep", "desk at", "by now", "rolodex"):
                    if shape in y:
                        seen[shape] += 1
                        if seen[shape] > cap: out[lid] = f"variety: y shape '{shape}' already used {cap}x"
                        break
        return out
    for lid, s in sel.items():
        if s["tier"] == "skip": continue
        why = gate(s, (lines.get(lid) or "").strip().replace("—", ",").replace("–", ","))
        if why: out[lid] = why
    for lid, why in variety_flags(sel, lines).items():
        out.setdefault(lid, why)
    return out


def apply_approvals(flags, bdir):
    """approved.json lists lead_ids a human reviewed; their gate flags are dropped (skips stay)."""
    f = bdir / "approved.json"
    if not f.exists(): return flags
    ok = set(json.loads(f.read_text()).get("lead_ids", []))
    return {k: v for k, v in flags.items() if k not in ok or v.startswith("skipped:")}


def main():
    bdir = Path(sys.argv[1])
    global BDIR; BDIR = bdir
    sel, lines = load(bdir)
    xs = json.loads((bdir / "x.json").read_text()) if (bdir / "x.json").exists() else None
    flags = apply_approvals(all_flags(sel, lines, xs), bdir)
    ws = open_tab(SHEET_ID)
    hdr = ws.row_values(1); col = {h: i + 1 for i, h in enumerate(hdr)}
    a1 = gspread.utils.rowcol_to_a1
    ups, done, flagged, skipped, sample, export = [], 0, 0, 0, [], []
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    for lid, s in sel.items():
        row = s["sheet_row"]
        if s["tier"] == "skip":
            status, line = s["angle"], ""; skipped += 1
        else:
            line = (lines.get(lid) or "").strip().replace("—", ",").replace("–", ",")
            why = flags.get(lid, "")
            if why.startswith("skipped:"):
                status, line = why, ""; skipped += 1; why = "skip"
            else:
                status = "done" if not why else f"flagged: {why}"
                done += not why; flagged += bool(why)
            if why == "skip": why = ""; line = ""; status = status  # skipped rows never export
            elif not why and len(sample) < 8: sample.append((s["campaign"], s["tier"], line))
            spec = (xs or {}).get(lid, {}).get("specialty", "") if isinstance((xs or {}).get(lid), dict) else ""
            if not why and line: export.append({"lead_id": lid, "campaign": s["campaign"], "send_order": "", "first_name": s["first_name"],
                                       "company_name": s["company_name"], "personalization": line, "specialty": spec, "tier": s["tier"]})
        notes = (s.get("source_url") or "") + ((" | " + s["facts"].get("anchor", "")) if s.get("facts") else "")
        cells = [("icebreaker", line), ("angle", s["angle"]), ("research_notes", notes),
                 ("personalization_status", status), ("personalized_at", stamp)]
        if "specialty" in col:
            cells.append(("specialty", (xs or {}).get(lid, {}).get("specialty", "") if isinstance((xs or {}).get(lid), dict) else ""))
        for c, v in cells:
            ups.append({"range": a1(row, col[c]), "values": [[v]]})
    for i in range(0, len(ups), 400):
        ws.batch_update(ups[i:i + 400])
    outdir = ROOT / "output" / "daily"; outdir.mkdir(exist_ok=True)
    p = outdir / f"day_{bdir.name}.csv"
    if export:
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(export[0].keys())); w.writeheader(); w.writerows(export)
    print(f"[apply] done={done} flagged={flagged} skipped={skipped} -> sheet updated; send file {p.name if export else '(none)'}")
    for c, t, l in sample: print(f"   [{c}/t{t}] {l}")
    if flags:
        print("   flagged:", [(lid, sel[lid]["campaign"], why) for lid, why in list(flags.items())[:8]])
        print(f"   -> python3 personalize/daily_rewrite.py {bdir} to stage a rewrite pass")


if __name__ == "__main__":
    main()
