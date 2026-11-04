#!/usr/bin/env python3
"""Tag lead rows with fit + fit_reason (keyword rules; no web lookups, no MillionVerifier).

fit values (first match wins, in this order):
  off-niche   - the company isn't in the niche
  cleaning_residential - (approved own campaign, Lorenzo 2026-10-20) cleaning work aimed at homes / exteriors (house or soft wash, maid,
                move-out, carpet-only, restoration/SERVPRO, windows, gutters ...)
  non-owner   - title isn't a real owner/founder/CEO/president/principal/partner
  good        - everything else
Signals: company name, domain, QuickEnrich Industry, title. The exports carry no
description column, so the LinkedIn Description filter used in the search is the
only "description" signal (it is implied for every row of that search).

Usage:  qe_fit.py POOL.csv [POOL2.csv ...]   (rewrites in place, idempotent)
        python3 -c "import qe_fit; qe_fit.classify(row, niche)"  (used by qe_dedupe.py)
fit, fit_reason, mv_result (sheet R:S:T) and source_search (CSV only, column U) follow pulled_at.
source_search ids: P0/C0a/C0b/A0 = first batch; P1-P3, C1-C3, A1-A3 = second batch (see the skill).
Pest is good only with a pest word in name/domain or a P2 Services Offered match; PPC is good only with an
agency/PPC/ads/paid/digital/performance signal in name/domain or an A2/A3 search.
"""
import csv, json, os, re, sys
from collections import Counter

def _rx(words):
    return re.compile("|".join(words))

# ---------- title ----------
TITLE_FALSE = _rx([r"vice[\s-]*president", r"\bvp\b", r"\bsvp\b", r"\bevp\b",
    r"partner (success|account|acquisition|manager|relations|marketing|development|programs?|enablement|sales)",
    r"(channel|business|strategic|agency) partner", r"partnerships?\b",
    r"principal (ux|ui|web|graphic|software|engineer|developer|designer|scientist|architect|product|data|analyst|account)",
    r"president of (sales|marketing|operations|business)", r"product owner",
    r"(former|ex)[\s-]+(owner|founder|ceo|president)"])
TITLE_OWNER = _rx([r"\bowner", r"founder", r"founding", r"\bceo\b", r"chief executive", r"president",
    r"principal", r"partner", r"proprietor", r"managing director", r"chairman", r"\bmd\b", r"operator"])

# Lorenzo via COO 2026-10-20 9:49 PM: these words make any title non-owner
# (Executive Assistant to CEO, Past President, Division/Regional President ...)
TITLE_NONOWNER = re.compile(r"\bassistant\b|\bpast\b|\bformer\b|\bdivision(al)?\b|\bregional\b")

def owner_title(title):
    t = re.sub(r"\s+", " ", (title or "").lower())
    if not t.strip():
        return False, "no title"
    m = TITLE_NONOWNER.search(t)
    if m:
        return False, f"title '{title.strip()[:40]}' ({m.group(0)})"
    t2 = TITLE_FALSE.sub(" ", t)
    if TITLE_OWNER.search(t2):
        return True, ""
    return False, f"title '{title.strip()[:40]}'"

# ---------- pest ----------
PEST_KW = _rx([r"pest", r"termit", r"extermin", r"\bbugs?\b", r"bug", r"mosquito", r"wildlife", r"rodent",
    r"critter", r"\bmoles?\b", r"fumigat", r"wasp", r"\bbees?\b", r"\bants?\b", r"insect", r"\brats?\b",
    r"\bmice\b", r"squirrel", r"\bbats?\b", r"tick", r"flea", r"roach", r"spider", r"gopher", r"varmint",
    r"skunk", r"raccoon", r"snake", r"bird control", r"orkin", r"terminix", r"rollins", r"truly nolen",
    r"aptive", r"\bhawx\b"])
PEST_SERVICE_IND = {"consumer services", "facilities services", "environmental services", "",
    "individual and family services", "services for the elderly and disabled",
    "environmental services", "public safety", "pet services"}
PEST_LAWN = _rx([r"fertiliz", r"\bfert", r"nutri", r"weed", r"lawn", r"landscap", r"\bturf", r"\btree", r"garden", r"nursery", r"sprinkler", r"irrigat"])
# industries / name words that mean "sells to or makes things for pest companies", not a service company
PRODUCT_IND = _rx([r"consumer goods", r"software", r"manufactur", r"chemical", r"wholesale", r"retail", r"advertising",
    r"marketing", r"staffing", r"biotech", r"broadcast", r"media", r"technology", r"it services",
    r"telecom", r"venture", r"investment", r"financial", r"insurance", r"accounting", r"law practice",
    r"real estate", r"consulting", r"writing", r"photograph", r"public relations", r"pharma",
    r"research", r"e-learning", r"education", r"non-profit", r"banking", r"capital markets",
    r"online and mail", r"warehousing", r"food", r"beverage", r"farming", r"agricultur", r"textile",
    r"book", r"publishing", r"health", r"hospital", r"construction", r"utilities", r"building materials",
    r"business supplies", r"renewable", r"appliances"])
PRODUCT_NAME = _rx([r"products?\b", r"\bmfg\b", r"manufactur", r"supply", r"supplies", r"chemical",
    r"\blabs?\b", r"\bbio", r"organics", r"wholesale", r"software", r"\bapp\b", r"marketing", r"media",
    r"leads?\b", r"magazine", r"academy", r"distribut", r"\binc\.? *$"])

# searches whose filter alone is a strong niche signal
PEST_STRONG_SEARCH = {"P2"}
# Lead Gen Manager 2026-10-23: later searches reuse a base search's filter, so they get its search-id rules
# (C5/G-C2 -> C2 has no search-id rule in cleaning_fit; P5 not mapped).
SEARCH_ALIAS = {"A5": "A2", "G-A0": "A0", "G-A2": "A2", "G-P2": "P2"}

def pest_fit(name, dom, ind, title, search=""):
    s = f"{name} {dom}".lower()
    if re.search(r"insectar|beneficial|aquatic|\blakes?\b|\bponds?\b|handyman|museum|\bzoo\b|zoo\.|sanctuar|refuge|rehab|audubon|nature (center|center)|wildlife (center|centre|society|foundation|park|conservation|rescue)|\.org$|\.org\b", s):
        return "off-niche", "insectary/aquatics/wildlife non-profit, zoo or museum, not a pest control service"
    if re.search(r"wildlife", s) and not re.search(r"pest|termit|extermin|bug|mosquito|rodent|critter|control|removal|remove|exclu|trapp|wildlife (services?|solutions|management|specialists?|pros?)", s):
        return "off-niche", "wildlife org without control/removal service wording"
    if re.search(r"federation|association|investigat|reporters|audit|\.in$|\.co\.in", s):
        return "off-niche", "association/media/audit or non-US domain, not a pest control service"
    if PEST_KW.search(s):
        if PRODUCT_IND.search(ind) and ind not in PEST_SERVICE_IND and not re.search(r"pest control|extermin|termite control", s):
            return "off-niche", f"pest-related but industry '{ind}' (product/vendor, not a service co)"
        if re.search(r"marketing|media|leads|software|academy|staffing|magazine|insurance|products?\b|supply", s):
            return "off-niche", "pest-related vendor (marketing/software/products), not a service co"
        return None, "pest keyword in name/domain"
    if re.search(r"cleaners?\b|crop|agro|discount|inspect|restor|plumb|heating|property|management|realty|insurance|\blaw\b", s):
        return "off-niche", "other business (cleaners/ag supply/inspection/restoration/property mgmt), no pest keyword"
    if PEST_LAWN.search(s):
        return "off-niche", "lawn/landscape/garden co (pest only as a side service), no pest keyword in name"
    if SEARCH_ALIAS.get(search, search) in PEST_STRONG_SEARCH:
        if PRODUCT_IND.search(ind) and ind not in PEST_SERVICE_IND:
            return "off-niche", f"Services Offered pest match but industry '{ind}' (vendor/product)"
        if PRODUCT_NAME.search(s):
            return "off-niche", "Services Offered pest match but name suggests products/vendor"
        return None, "no pest word in name, but Services Offered lists pest control"
    return "off-niche", f"no pest word in name/domain; industry '{ind or 'blank'}' (description match only)"

# ---------- cleaning ----------
CLEAN_KW = _rx([r"clean", r"janitor", r"custodi", r"maint", r"sanit", r"disinfect", r"porter",
    r"building services", r"facility|facilities", r"maid", r"\bshine", r"sparkl", r"spotless", r"\bspic",
    r"\bjan\b", r"\bjani", r"tidy", r"swept|sweep", r"scrub", r"polish", r"dust", r"\bmop", r"\bbroom",
    r"housekeep", r"enviro"])
COMMERCIAL_KW = _rx([r"janitor", r"custodi", r"commercial", r"office", r"building", r"facilit",
    r"corporate", r"\bjan\b", r"\bjani", r"porter", r"industrial", r"medical clean", r"healthcare"])
RES_KW = [(r"house ?wash|home ?wash|soft ?wash|softwash", "house/soft washing"),
    (r"pressure ?wash|power ?wash|powerwash|pressurewash|exterior|wash(ing)?\b|wash", "pressure/exterior washing"),
    (r"roof clean|gutter|window|glass|\bpanes?\b", "window/gutter/roof cleaning (exterior, some commercial)"),
    (r"\bmaids?\b|maid service|housekeep|house ?clean|home ?clean|residential|homes?\b|house\b", "home/maid cleaning"),
    (r"move ?out|move ?in|moveout|movein|moving clean", "move-out cleaning"),
    (r"carpet|upholster|rug|tile ?(and|&) ?grout", "carpet/upholstery"),
    (r"\bdry (guys|out|pros?)\b|drying|contents|restor|servpro|water damage|fire damage|flood|mold|mould|remediat|biohazard|crime scene|trauma", "restoration/remediation"),
    (r"chimney|dryer ?vent|air ?duct|duct clean", "chimney/duct/vent"),
    (r"trash ?bin|bin clean|can clean", "trash bin cleaning"),
    (r"pool", "pool")]
CLEAN_OFF = _rx([r"\bpools?\b", r"\bspa\b", r"hvac", r"heating", r"plumb", r"roofing", r"electric", r"pest",
    r"lawn", r"landscap", r"\btree", r"snow", r"security", r"\bguard", r"parking", r"junk", r"haul",
    r"moving\b|movers?\b", r"waste", r"dumpster", r"septic", r"painting|painters?\b", r"construct",
    r"staffing", r"property manage", r"realty|real estate", r"elevator", r"fire protect", r"solar",
    r"garage door", r"locksmith", r"appliance", r"handyman", r"flooring", r"pav(ing|ers)", r"fenc",
    r"concrete", r"remodel", r"irrigat", r"sprinkler", r"towing", r"storage", r"laundr", r"dry clean",
    r"\bauto\b|car wash|detail", r"software", r"consult", r"marketing", r"insurance", r"supply|supplies",
    r"\bfurniture", r"\bmechanical", r"plant services", r"interiorscap"])

def cleaning_fit(name, dom, ind, title, search=""):
    s = f"{name} {dom}".lower()
    has_clean = bool(CLEAN_KW.search(s))
    commercial = bool(COMMERCIAL_KW.search(s))
    # pools / car detailing / dry cleaners are not cleaning-of-buildings at all
    if re.search(r"\bpools?\b|car wash|auto ?detail|\bdetailing\b|dry clean|laundr|marine|\bboats?\b|yacht", s) and not commercial:
        return "off-niche", "pool / auto or boat detailing / laundry, not building cleaning"
    if re.search(r"hvac|heating|\ba/?c\b|air condition|plumbing", f"{name}".lower()) and not re.search(r"janitor|custodi", s):
        return "off-niche", "HVAC/plumbing trade (duct cleaning side line)"
    if not has_clean and re.search(r"gutter|window(s)? (install|replace)|seamless", s):
        return "off-niche", "gutter/window installer, not cleaning"
    if not has_clean and CLEAN_OFF.search(s):
        return "off-niche", f"other trade ('{CLEAN_OFF.search(s).group(0)}'), no cleaning keyword"
    for pat, why in RES_KW:
        if re.search(pat, s):
            # exterior washing stays residential even with 'commercial' in the name
            if commercial and why not in ("house/soft washing", "pressure/exterior washing",
                                          "window/gutter/roof cleaning (exterior, some commercial)", "restoration/remediation"):
                continue
            return "cleaning_residential", why
    if has_clean:
        return None, "commercial cleaning/janitorial keyword" if commercial else "cleaning keyword in name/domain"
    if re.search(r"repair|labor|design|architect|construct|realty|propert", s):
        return "off-niche", "generic name suggests repair/labor/design/property, not cleaning"
    if ind == "janitorial services":
        return None, "generic name; industry Janitorial Services"
    if ind == "facilities services":
        return None, "generic name; Facilities Services + cleaning/janitorial search match"
    return "off-niche", f"generic name, industry '{ind or 'blank'}' (no cleaning signal)"

# ---------- ppc ----------
PPC_GOOD = _rx([r"ppc", r"\bads\b|ads\b", r"click", r"paid", r"search", r"\bsem\b", r"digital", r"marketing",
    r"agency", r"media", r"advertis", r"growth", r"performance", r"\bleads?\b", r"seo", r"web", r"brand",
    r"creative", r"strateg", r"interactive", r"online", r"social", r"funnel", r"conversion", r"\bppc"])
PPC_OFF = [(r"pictures|television|\btv\b|radio|broadcast|film|cinema", "broadcast/film"),
    (r"magazine|publish|news(paper)?\b|journal", "publisher"),
    (r"print(ing)?\b|signs?\b|signage|promotional products|promo products|apparel|merch|embroider|billboard|outdoor advertising|wraps?\b", "print/signs/promo products"),
    (r"photograph|video production|productions\b", "photo/video production"),
    (r"staffing|recruit", "staffing"),
    (r"capital\b|ventures?\b|\bvc\b|invest", "investment"),
    (r"software|saas|\bapp\b|platform|\bai\b|\.ai\b|technolog(y|ies)\b|\blabs?\b|analytics platform", "software/tech product"),
    (r"health|medical|clinic|dental|pharma", "healthcare co"),
    (r"real estate|realty|law firm|attorney|insurance|accounting|cpa\b", "non-marketing business"),
    (r"event(s)?\b|wedding", "events"),
    (r"podcast|artist|music|records\b|\bband\b|quotes\b|outdoors?\b", "media/entertainment/lead-gen product")]

PPC_SIGNAL = _rx([r"agency", r"agencies", r"ppc", r"adwords", r"(?<![a-z])ads(?![a-z])", r"(?<![eo])ads(?=[a-z]*\.)", r"(google|facebook|meta|amazon|bing|tiktok|linkedin) ?ads", r"\bad\b", r"\bdigi", r"\bbid", r"bidview", r"paid", r"digital", r"performance", r"advertis", r"click", r"\bsem\b", r"search marketing",
    r"search engine", r"pay ?per", r"\bcpc\b", r"\bppm\b"])
PPC_AGENCYISH = _rx([r"marketing", r"media", r"growth", r"digital", r"interactive", r"creative"])
PPC_SEARCHES = {"A0", "A1", "A2", "A3"}
PPC_STRONG_SEARCH = {"A2": "Services Offered PPC/Google Ads/Paid", "A3": "Company Name PPC/paid/performance"}

def ppc_fit(name, dom, ind, title, search=""):
    s = f"{name} {dom}".lower()
    t = (title or "").lower()
    for pat, why in PPC_OFF:
        m = re.search(pat, s)
        if m and not re.search(r"marketing|agency|ppc|\bads\b|advertis|digital|seo|growth", s.replace(m.group(0), " ")):
            return "off-niche", f"{why} ('{m.group(0)}'), no agency signal"
    # title says they own something other than this company, e.g. '... at Distill Health'
    if re.search(r"\bat\s+[a-z]", t) and not any(w in t for w in re.findall(r"[a-z]{4,}", name.lower())[:2]):
        return "off-niche", "title names a different company"
    m = PPC_SIGNAL.search(s)
    if not m and re.search(r"agency|ppc|paid (media|search|social)|media buy|performance market", t):
        return None, "agency/PPC wording in title"
    if m:
        return None, f"agency/PPC signal in name/domain ('{m.group(0).strip()}')"
    base = SEARCH_ALIAS.get(search, search)
    if base in PPC_STRONG_SEARCH:
        return None, f"generic name, but search {search} ({PPC_STRONG_SEARCH[base]}) is a PPC signal"
    # Lorenzo 2026-10-20 9:38 PM: A0-A3 rows already matched PPC terms inside Advertising/Marketing
    # Services, so a marketing-agency word in the name/domain is enough (off-niche rules above still win).
    m2 = PPC_AGENCYISH.search(s)
    if m2 and base in PPC_SEARCHES:
        return None, f"agency-type word in name/domain ('{m2.group(0)}') + PPC search {search}"
    return "off-niche", "no agency/PPC/ads/paid/digital/performance signal in name/domain (industry only)"

NICHE_FN = {"pest_control": pest_fit, "cleaning": cleaning_fit, "ppc": ppc_fit}

def classify(row, niche):
    name = row.get("company", "") or ""
    dom = row.get("domain", "") or row.get("website", "") or ""
    ind = (row.get("Industry") or row.get("industry") or "").strip().lower()
    title = row.get("title", "") or ""
    search = (row.get("source_search") or "").strip()
    fit, why = NICHE_FN[niche](name, dom, ind, title, search)
    if search:
        why = f"[{search}] {why}"
    if fit:
        return fit, why
    ok, twhy = owner_title(title)
    if not ok:
        return "non-owner", twhy
    return "good", why

# search ids for files staged before source_search existed (2026-10-20 first batch)
LEGACY_SEARCH = {"quickenrich_p1-102_new": "P0", "quickenrich_janitorial_p1-46_new": "C0a",
                 "quickenrich_facilities_p1-147_new": "C0b", "quickenrich_p1-177_new": "A0"}

def search_from_name(path):
    b = os.path.basename(path)
    for k, v in LEGACY_SEARCH.items():
        if b.endswith(k + ".csv"):
            return v
    m = re.search(r"_([A-Z]\d+[a-z]?)_p\d", b)
    return m.group(1) if m else ""

def tag_file(path, niche=None):
    with open(path, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh); hdr = list(r.fieldnames); rows = list(r)
    if niche is None:
        niche = next((n for n in NICHE_FN if f"_{n}_" in os.path.basename(path)), None) or rows[0]["niche"]
    hdr = [h for h in hdr if h not in ("fit", "fit_reason", "mv_result", "source_search")]
    i = hdr.index("pulled_at") + 1 if "pulled_at" in hdr else len(hdr)
    hdr = hdr[:i] + ["fit", "fit_reason", "mv_result", "source_search"] + hdr[i:]
    sid = search_from_name(path)
    c = Counter()
    for row in rows:
        if not row.get("source_search"):
            row["source_search"] = sid
        if (row.get("fit_reason") or "").strip().lower().startswith("manual override"):
            c[row.get("fit") or "manual"] += 1; continue  # keep manual overrides
        row["fit"], row["fit_reason"] = classify(row, niche); c[row["fit"]] += 1
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr); w.writeheader(); w.writerows(rows)
    return niche, dict(c)

if __name__ == "__main__":
    out = {}
    for p in sys.argv[1:]:
        n, c = tag_file(p); out[os.path.basename(p)] = {"niche": n, **c}
    print(json.dumps(out, indent=2))
