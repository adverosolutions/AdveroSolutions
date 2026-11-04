"""Company-level fit for QuickEnrich Company Finder exports: fit(row, niche='pest_control'|'cleaning'|'ppc').
PPC (added 2026-10-21): see ppc_cf_fit(); returns True/False like pest.
Cleaning (added 2026-10-20 night): see clean_fit() below; returns (kind, why) where kind is
'commercial' / 'cleaning_residential' for keeps and False for drops (pest still returns True/False).
--- pest ---
Layer 1 = qe_fit.pest_fit (name/domain/industry, same rules as the contact pool).
Layer 2 = Services / LinkedIn Bio / Home Page Text (Company Finder only) to (a) rescue real pest
service cos that qe_fit drops on industry/word quirks and (b) admit generic names that are clearly pest cos."""
import csv, re, sys, collections
sys.path.insert(0, '/home/box/advero/bin')
from qe_fit import pest_fit, PEST_SERVICE_IND, cleaning_fit, ppc_fit, PPC_OFF, PPC_SIGNAL, PPC_AGENCYISH
from qe_dedupe import norm_domain

PEST_ITEM = re.compile(r"pest|termit|extermin|rodent|mosquito|wildlife|bed ?bug|\bbats?\b|\bbees?\b|wasp|hornet|\bants?\b|\bticks?\b|flea|roach|fumig|animal (removal|control|trapping|exclusion)|trapping|exclusion|insect|spider|\brats?\b|\bmice\b|squirrel|raccoon|snake|bird|critter|mole|gopher|armadillo|skunk|scorpion|\bfly\b|flies|stinging|nuisance")
VENDOR_ITEM = re.compile(r"products?\b|supplies|supply\b|equipment|distribut|wholesale|marketing|software|lead gen|insurance|training|course|education|exam|consult|manufactur|formulation|repellent|liners?|heaters?\b|bait|pesticide sales|e-?commerce|content|seo\b|google ads|website")
STRONG = re.compile(r"pest control|pest management|pest services?|pest solutions|extermin|termite (control|treatment|inspection|service)|rodent (control|removal|exclusion)|wildlife (control|removal|management|exclusion|trapping)|animal (control|removal|trapping)|bed ?bug (treatment|removal|extermin|control)|mosquito (control|treatment|spray|service)|fumigat|integrated pest")
VENDOR_NAME = re.compile(r"marketing|\bmedia\b|software|\bleads?\b|magazine|insurance|products?\b|\bsupply|supplies|distribut|wholesale|manufactur|\bmfg\b|\blabs?\b|laborator|chemical|equipment|\bsaas\b|\bapp\b|\.io$|association|federation|council|\.org\b|\.in$|\.co\.in")
OFF_NAME = re.compile(r"fireplace|chimney|academy|university|college|school|institute|training|pharma|realty|real estate|property management|roofing|plumb|hvac|heating|electric|solar|construction|builders?\b|remodel|basement|waterproof|foundation|home inspect|inspections?\b|warranty|\bpools?\b|cleaners?\b|janitor|moving|storage|staffing|consult|county|city of|department|district|agricultur|\bfarms?\b|\bfeed\b|seed|nursery|garden|hardware|lumber|building center|vet(erinary)?\b|animal hospital|grooming|kennel|lawn|landscap|\btree|\bturf|irrigat|sprinkler|fertiliz|\bmd\b|\bdds\b|clinic|medical|hotel|restaurant|church")
OFF_IND = re.compile(r"manufactur|software|wholesale|retail|chemical|biotech|research|pharma|advertising|marketing|media|staffing|education|e-learning|government|non-profit|financial|insurance|real estate|technology|it services|investment|veterinary|farming|food|hospital|health|medical|publishing|online and mail|warehousing|distribution|machinery|appliances|landscaping|entertainment|international trade|aviation|airlines|associations|executive offices|wellness")

def items(svc):
    return [s.strip().lower() for s in re.split(r",", svc or "") if s.strip()]

def pest_share(svc):
    it = items(svc)
    if not it: return 0.0, 0.0, 0
    p = sum(1 for s in it if PEST_ITEM.search(s) and not VENDOR_ITEM.search(s))
    v = sum(1 for s in it if VENDOR_ITEM.search(s))
    return p/len(it), v/len(it), len(it)

NON_US_TLD = re.compile(r"\.(uk|au|ca|in|nz|ie|za|ph|pk|ae|sg|my|ng|de|fr|es|it|mx|br)$")
STORE = re.compile(r"\bstore\b|\bshop\b|superstore|rental|\bdiy\b|do it yourself|to-go|india\b")

def fit(row, niche="pest_control"):
    if niche == "cleaning":
        return clean_fit(row)
    if niche == "ppc":
        return ppc_cf_fit(row)
    k, why = _fit(row)
    if k:
        dom = norm_domain(row['URL']) or norm_domain(row['Final Email Domain']) or norm_domain(row['Email Domain'])
        m = NON_US_TLD.search(dom)
        if m:
            return False, f"non-US domain ('{m.group(0)}')"
        m = STORE.search(row['Company Name'].lower() + " " + dom)
        if m:
            return False, f"retail/DIY store or equipment rental ('{m.group(0)}'), not a service co"
    return k, why

def _fit(row):
    name = row['Company Name'].strip()
    dom = norm_domain(row['URL']) or norm_domain(row['Final Email Domain']) or norm_domain(row['Email Domain'])
    ind = row['Industry'].strip().lower()
    nd = f"{name} {dom}".lower()
    svc, bio, home = row['Services'], row['LinkedIn Bio'].lower(), row['Home Page Text'].lower()
    ps, vs, n = pest_share(svc)
    svc_service = ps >= 0.5 and vs < 0.5          # Services mostly pest *service* items
    vn = VENDOR_NAME.search(nd)
    f, why = pest_fit(name, dom, ind, "", "")
    if f is None:   # qe_fit keeps it (pest word in name/domain)
        if vs >= 0.5 and ps < 0.5:
            return False, "pest word in name but Services are mostly products/marketing/training (vendor)"
        return True, "qe_fit: pest keyword in name/domain"
    if why.startswith("no pest word"):
        # generic name: needs clear pest-service evidence and no off-niche name/industry
        m = vn or OFF_NAME.search(nd)
        if m:
            return False, f"no pest word in name; off-niche name word '{m.group(0)}'"
        if OFF_IND.search(ind) and ind not in PEST_SERVICE_IND:
            return False, f"no pest word in name; industry '{ind}'"
        mb = STRONG.search(bio[:400])
        if mb and (ps >= 0.4 or n == 0):
            return True, f"generic name; LinkedIn Bio '{mb.group(0)}' + Services {ps:.0%} pest"
        if svc_service and (STRONG.search(bio) or STRONG.search(home[:3000]) or ind in ("environmental services","consumer services","facilities services")):
            return True, f"generic name; Services {ps:.0%} pest service items (industry '{ind or 'blank'}')"
        return False, f"no pest word in name; pest not the main business (Services {ps:.0%} pest)"
    if why.startswith("lawn/landscape"):
        return False, "qe_fit: lawn/landscape/tree co (pest is a side service)"
    if why.startswith("other business"):
        return False, "qe_fit: " + why
    # qe_fit dropped a pest-named co on industry / word quirks ('remediation' -> media, 'academy', 'investigat', wildlife wording)
    if vn:
        return False, f"qe_fit: {why} (vendor/org name word '{vn.group(0)}')"
    if re.search(r"zoo|museum|sanctuar|refuge|rehab|audubon|aquatic|\blakes?\b|\bponds?\b|insectar|beneficial|handyman|healthcare|\bctr\b", nd):
        return False, "qe_fit: " + why
    if svc_service and re.search(r"pest|termit|extermin|bug|mosquito|wildlife|rodent|critter|animal|bat|bee|wasp|termin|orkin", nd + " " + svc.lower()):
        return True, f"rescued: pest-named, Services {ps:.0%} pest service items (qe_fit said: {why[:60]})"
    return False, "qe_fit: " + why


# ---------------- cleaning (commercial cleaning / janitorial) ----------------
# Services item classes, first match wins
C_VENDOR = re.compile(r"suppl(y|ies|ier)|products?\b|equipment|chemical|manufactur|distribut|wholesale|machines?\b|software|robots?\b|vacuum|\bsales\b|(equipment|machine|vacuum) rentals?|detergent|paper|packaging|foodservice|food service|private label|dispens|lead gen|\bleads\b|outreach|cold (email|call)|soaps?\b|towel|tissue|marketing|advertis|consult|training|coaching|\bcourses?\b|insurance|\bapp\b|platform|e-?commerce|store\b")
C_FRANCH = re.compile(r"franchis|business ownership|business (partnership|opportunit)|launchpad|own your own")
C_TRADE = re.compile(r"\bdoors?\b|landscap|lawn|grounds|snow|hvac|heating|cooling|plumb|electric|remodel|painting|security|guard|staffing|employment|locksmith|pest|handyman|general contract|construction (company|services|management)|commercial construction|property management|parking|concierge|vending|moving serv|hauling|towing|it solutions|cabling|camera|engineering|energy|caregiv|companion|medical staffing|drug test|assembly|logistics")
C_LAUNDRY = re.compile(r"dry clean|laundr|wash and fold|wash & fold|shirt|alteration|tailor|car (detail|wash)|auto(motive)? (detail|steam)|detailing|boat|yacht|marine|aircraft|\bpools?\b")
C_RESTO = re.compile(r"restoration|water damage|fire damage|smoke damage|storm|flood|\bmou?ld\b|remediat|biohazard|crime scene|trauma|hoard|odor|water extraction|disaster")
C_SPEC = re.compile(r"carpet|upholster|\brugs?\b|tile|grout|window|glass|pressure|power ?wash|soft ?wash|house ?wash|gutter|roof|exterior|solar panel|hardwood|chimney|\bducts?\b|dryer vent|trash (bin|can)|bin clean|graffiti|concrete clean|driveway|deck")
C_RES = re.compile(r"residential|house|\bhomes?\b|home clean|maids?\b|move[- ]?(in|out)|moving (in|out|clean)|airbnb|vacation|short[- ]term|rental clean|apartment clean|domestic|tenancy|end of lease|one[- ]time|recurring|standard clean|spring|party|oven|refrigerator|fridge|organiz|ironing|housekeep|turnover|condo|transition|senior|estate clean|regular (schedule )?clean")
C_COM = re.compile(r"commercial|janitor|custodi|office|porter|building|facilit|industrial|medical|healthcare|health care|school|education|restaurant|kitchen|warehouse|retail|church|bank|\bgyms?\b|fitness|floor|disinfect|sanit|post[- ]?construct|construction|restroom|green|eco|special|event|government|laborator|apartment (complex|building)|property|corporate|business|dealership|hotel|hospitality|day porter|clean ?room|infection|electrostatic|covid|stadium|sports|manufacturing facility|plant clean|hoa|common area|strip|wax|burnish|pharma")
C_CLEAN = re.compile(r"clean|janitor|custod|maid|sanit|disinfect|housekeep|tidy|scrub|sweep|swept|dust|polish|shine|wash|mop")
C_COM_ON_SPEC = re.compile(r"commercial|office|building|industrial|facilit|business")

def clean_items(svc):
    """Counter of Services item classes."""
    c = collections.Counter()
    for it in items(svc):
        if C_VENDOR.search(it) and not re.search(r"(clean|janitor)\w* (service|program)s?$", it): c["vendor"] += 1
        elif C_FRANCH.search(it): c["franchise"] += 1
        elif C_LAUNDRY.search(it): c["laundry_auto_pool"] += 1
        elif C_TRADE.search(it) and not C_CLEAN.search(it): c["other"] += 1
        elif C_RESTO.search(it): c["resto"] += 1
        elif C_SPEC.search(it): c["com" if C_COM_ON_SPEC.search(it) else "spec"] += 1
        elif C_RES.search(it) and C_COM.search(it): c["res"] += 0.5; c["com"] += 0.5
        elif C_RES.search(it): c["res"] += 1
        elif C_COM.search(it): c["com"] += 1
        elif C_CLEAN.search(it): c["neutral"] += 1
        else: c["other"] += 1
    c["n"] = len(items(svc))
    return c

C_VENDOR_NAME = re.compile(r"suppl(y|ies)|products?\b|chemical|\bchem\b(?!-?dry)|\bmfg\b|manufactur|distribut|wholesale|software|equipment|vacuum|sweeper shop|\bpaper\b|\bsaas\b|\.io$|\btech(nolog(y|ies))?\b|\blabs?\b|bioscience|\bbio\b|association|institute|academy|marketing|\bmedia\b|directory|\binsurance|consult")
C_FRANCH_NAME = re.compile(r"franchis")
C_OFF_NAME = re.compile(r"staffing|employment|personnel|labor solutions|realty|real estate|property management|properties\b|construction\b|builders?\b|remodel|roofing|plumb|hvac|heating|electric|landscap|lawn|pest|security|moving\b|movers|storage|goodwill|church|school district|university|college|hospital|\bhotel|restaurant|dry clean|laundr|\bauto\b|car wash|auto detail|car detail|detailing\b|painting|painters?\b")
# franchisor head-office domains (local franchisee sites / subdomains are kept, with a note)
C_FRANCHISOR_HQ = re.compile(r"^(jan-pro\.com|janiking\.com|coverall\.com|anagousa\.com|anagocleaning\.com|stratusclean\.com|stratusbuildingsolutions\.com|cleannetusa\.com|vanguardcleaning\.com|officepride\.com|openworksweb\.com|gocitywide\.com|servicemasterclean\.com|servicemaster\.com|servpro\.com|mollymaid\.com|merrymaids\.com|themaids\.com|heavensbest\.com|chemdry\.com|stanleysteemer\.com|buildingstars\.com|bonuscleaning\.com|duraclean\.com|maidpro\.com|mollymaid\.com|thecleaningauthority\.com|maidright\.com|twomaidsandamop\.com|twomaids\.com|sparkleteam\.com|swisherhygiene\.com|vanguardcleans\.com|systems4\.com|chemdry\.net)$")
C_FALSE_WORDS = re.compile(r"(?i)washington|american|mexican|african|dominican|pelican|toucan|vulcan|republican|anglican")
C_PRODUCT_IND = re.compile(r"manufactur|biotech|research|nanotech|wholesale|chemical")
C_OFF_IND = re.compile(r"manufactur|software|wholesale|retail|chemical|staffing|real estate|it services|technology|insurance|advertising|marketing|education|e-learning|government|non-profit|financial|investment|accounting|legal|law practice|human resources|machinery|business supplies|warehousing|transportation|truck|motor vehicle|hospitals|home health|restaurants|food|wellness|landscaping|security|utilities")

def clean_fit(row):
    name = row["Company Name"].strip()
    dom = norm_domain(row["URL"]) or norm_domain(row["Final Email Domain"]) or norm_domain(row["Email Domain"])
    ind = row["Industry"].strip().lower()
    nd = f"{name} {dom}".lower()
    svc = row["Services"]
    bio = (row["LinkedIn Bio"] + " " + row["Home Page Text"][:3000]).lower()
    c = clean_items(svc); n = c["n"] or 1
    cleaning = c["com"] + c["res"] + c["spec"] + c["neutral"]
    sh = lambda k: c[k] / n
    tally = f"Services com {c['com']:g}/res {c['res']:g}/spec {c['spec']:g}/resto {c['resto']:g}/vendor {c['vendor']:g}/other {c['other']:g} of {c['n']}"
    m = NON_US_TLD.search(dom)
    if m: return False, f"non-US domain ('{m.group(0)}')"
    if C_FRANCHISOR_HQ.search(dom): return False, f"franchisor head office domain ('{dom}')"
    if C_FRANCH_NAME.search(nd) or (c["franchise"] and sh("franchise") >= 0.5) or (c["franchise"] and cleaning <= 1):
        return False, "franchise sales / franchisor marketing (Services or name are franchise opportunities)"
    m = C_VENDOR_NAME.search(nd)
    if m and (c["vendor"] or C_OFF_IND.search(ind) or cleaning == 0 or m.group(0) in (".io", "marketing", "media", "directory", "association", "academy", "institute")):
        return False, f"supplier/software/vendor or org name word ('{m.group(0)}')"
    if c["vendor"] and (sh("vendor") >= 0.4 or c["vendor"] >= cleaning):
        return False, f"supplier/equipment/software vendor (Services mostly products) [{tally}]"
    if c["laundry_auto_pool"] and sh("laundry_auto_pool") >= 0.34:
        return False, f"dry cleaner/laundry, auto/boat detailing or pool, not building cleaning [{tally}]"
    if c["resto"] and sh("resto") >= 0.5 and c["com"] <= 1.5:
        return False, f"restoration/remediation-only (cleaning a side line) [{tally}]"
    if re.search(r"servpro|paul davis|puroclean|rainbow (intl|international|restoration)|\brestoration\b", nd) and c["resto"] >= 2:
        return False, f"restoration company (name) [{tally}]"
    if c["other"] and sh("other") > 0.5:
        return False, f"multi-trade / other business, cleaning not the main service [{tally}]"
    m = C_OFF_NAME.search(nd)
    if m and not re.search(r"clean|janitor|custod|maid", nd):
        return False, f"off-niche name word ('{m.group(0)}'), no cleaning word in name"
    if re.search(r"staffing|employment agency|property management", svc.lower()) and sh("other") >= 0.25:
        return False, f"staffing / property management co with janitorial line [{tally}]"
    if C_OFF_IND.search(ind) and (c["vendor"] or c["other"] >= 2) and not re.search(r"clean|janitor|custod|maid|building service", nd):
        return False, f"industry '{ind}' + vendor/other Services, no cleaning word in name [{tally}]"
    if cleaning == 0:
        return False, f"no cleaning service items in Services [{tally}]"
    # layer 1: same name/domain/industry rules as the contact pool
    # mask words that trip qe_fit substring rules ('Washington' -> wash, 'American Cleaning' -> 'can clean')
    q, qwhy = cleaning_fit(C_FALSE_WORDS.sub("_", name), C_FALSE_WORDS.sub("_", dom), ind, "", "")
    resx = c["res"] + c["spec"]
    if q == "off-niche":
        if qwhy.startswith(("pool /", "HVAC/plumbing")):
            return False, "qe_fit: " + qwhy
        # Company Finder filter = commercial cleaning Services; rescue clear cleaning cos with odd names/industries
        strong_bio = re.search(r"janitorial|commercial cleaning|cleaning (company|business|services?|contractor)|custodial", bio)
        if not c["vendor"] and not C_PRODUCT_IND.search(ind) and (
                (cleaning / n >= 0.6 and c["other"] <= max(1, 0.25 * n)) or
                (cleaning / n >= 0.5 and c["other"] <= 0.4 * n and strong_bio)):
            kind = "cleaning_residential" if resx > c["com"] else "commercial"
            return kind, f"rescued: {tally} (qe_fit said: {qwhy[:60]})"
        return False, f"qe_fit: {qwhy} [{tally}]"
    if q == "cleaning_residential":
        if qwhy != "restoration/remediation" and c["com"] / n >= 0.6 and resx / n <= 0.25:
            return "commercial", f"name looks {qwhy} but Services mostly commercial [{tally}]"
        return "cleaning_residential", f"qe_fit name/domain: {qwhy} [{tally}]"
    # qe_fit keeps it (cleaning / commercial keyword or generic janitorial/facilities)
    if qwhy.startswith("commercial") or "janitorial" in qwhy.lower():
        if resx / n >= 0.6 and c["com"] / n <= 0.2:
            return "cleaning_residential", f"commercial word in name but Services mostly home/specialty [{tally}]"
        return "commercial", f"qe_fit: {qwhy} [{tally}]"
    if resx > c["com"]:
        focus = "home/maid" if c["res"] >= c["spec"] else "carpet/window/exterior specialty"
        return "cleaning_residential", f"{focus}-focused: {tally}"
    return "commercial", f"qe_fit: {qwhy}; {tally}"

# ---------------- ppc (PPC / paid media agencies, added 2026-10-21) ----------------
# Reuses qe_fit.ppc_fit (name/domain) plus Services / LinkedIn Bio / Home Page Text.
# Keeps: agency/PPC/ads/paid/digital/performance signal in name/domain, or a marketing/media/growth
# name with PPC Services items, or a generic name whose Services are mostly PPC/paid items.
# Drops: qe_fit PPC_OFF hits (software/SaaS, labs, print/signs, video production, healthcare, investment,
# podcast, music, artist ...), off-niche industries, SaaS/platform bios, non-US TLDs.
P_ITEM = re.compile(r"\bppc\b|pay[- ]?per[- ]?click|google ads|adwords|bing ads|microsoft ads|facebook ads|meta ads|instagram ads|tiktok ads|linkedin ads|amazon (ads|ppc|advertising)|youtube ads|paid (search|media|social|advertising|ads)|\bsem\b|search engine marketing|performance marketing|digital advertising|online advertising|programmatic|display (ads|advertising)|media buy|retargeting|remarketing|shopping ads|\bcpc\b|conversion rate|lead gen")
P_MKT_ITEM = re.compile(r"marketing|advertis|\bseo\b|search engine|social media|digital|branding|web design|website|content|email marketing|strategy|growth|media")
P_OFF_IND = re.compile(r"software|computer|it services|hospital|health|medical|pharma|biotech|financial services|investment|venture capital|banking|insurance|real estate|printing|media production|movies|broadcast|music|entertainment|musicians|artists|retail|manufactur|wholesale|staffing|education|e-learning|non-profit|government|legal|law practice|accounting")
P_OFF_BIO = re.compile(r"\b(saas|our platform|our software|software platform|mobile app|api\b)|ad ?tech platform|self-serve platform")
P_AGENCY_NAME = re.compile(r"agency|agencies|\bppc\b|marketing|advertis|\bmedia\b|digital|\bseo\b")
P_AGENCY_STRICT = re.compile(r"agency|agencies|\bppc\b|advertis")
P_ALLOWED_IND = {"advertising services", "marketing services", "marketing & advertising", "marketing and advertising",
                 "business consulting and services", "online audio and video media", "public relations and communications services", ""}

def ppc_items(svc):
    it = items(svc)
    p = sum(1 for s in it if P_ITEM.search(s))
    m = sum(1 for s in it if not P_ITEM.search(s) and P_MKT_ITEM.search(s))
    return p, m, len(it)

def ppc_cf_fit(row):
    name = row["Company Name"].strip()
    dom = norm_domain(row["URL"]) or norm_domain(row["Final Email Domain"]) or norm_domain(row["Email Domain"])
    ind = row["Industry"].strip().lower()
    nd = f"{name} {dom}".lower()
    svc = row["Services"]
    bio = (row["LinkedIn Bio"] + " " + row["Home Page Text"][:3000]).lower()
    p, mk, n = ppc_items(svc)
    tally = f"Services ppc {p}/mkt {mk} of {n}"
    m = NON_US_TLD.search(dom)
    if m: return False, f"non-US domain ('{m.group(0)}')"
    q, why = ppc_fit(name, dom, ind, "", "")          # name/domain rules incl. PPC_OFF
    if q == "off-niche" and not why.startswith("no agency"):
        return False, "qe_fit: " + why
    strong_name = PPC_SIGNAL.search(nd)
    agency_name = P_AGENCY_NAME.search(nd)
    if P_OFF_IND.search(ind) and ind not in P_ALLOWED_IND and not (P_AGENCY_STRICT.search(nd) and p):
        return False, f"industry '{ind}' (not an agency) [{tally}]"
    if re.search(r"\.(io|ai|app)$", dom) and not agency_name:
        return False, f"software-style domain ('{dom}'), no agency/marketing word in name [{tally}]"
    mb = P_OFF_BIO.search(bio[:1500])
    if mb and not agency_name:
        return False, f"software/platform wording in bio ('{mb.group(0)}'), no agency/marketing word in name [{tally}]"
    if q is None and strong_name:
        if n and p == 0 and mk == 0:
            return False, f"agency word in name but no marketing/PPC Services items [{tally}]"
        return True, f"qe_fit: {why} [{tally}]"
    m2 = PPC_AGENCYISH.search(nd)
    if m2 and p:
        return True, f"agency-type word in name/domain ('{m2.group(0)}') + PPC Services [{tally}]"
    if p and n and p / n >= 0.3:
        return True, f"generic name; Services {p/n:.0%} PPC/paid items [{tally}]"
    if p and re.search(r"agency", bio[:1500]) and re.search(r"ppc|google ads|paid (search|media|social)|performance marketing", bio):
        return True, f"generic name; bio says agency + PPC [{tally}]"
    return False, f"no agency/PPC signal in name/domain and PPC not the main service [{tally}]"

if __name__ == "__main__":
    niche = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--niche=")), "pest_control")
    sys.argv = [a for a in sys.argv if not a.startswith("--niche=")]
    rows = list(csv.DictReader(open(sys.argv[1], newline='', encoding='utf-8-sig')))
    c = collections.Counter(); ex = collections.defaultdict(list)
    for r in rows:
        k, why = fit(r, niche); key = (k, re.sub(r"'.*|\d+%.*", "", why)[:70]); c[key]+=1
        ex[key].append(f"{r['Company Name']} | {r['URL']} | {r['Industry']} | {r['Services'][:70]}")
    for k,v in sorted(c.items(), key=lambda x:-x[1]):
        print(v, k); [print('    ', e) for e in ex[k][:int(sys.argv[2]) if len(sys.argv)>2 else 6]]
