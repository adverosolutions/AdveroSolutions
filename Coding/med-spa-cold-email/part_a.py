#!/usr/bin/env python3
"""
Part A - Google Maps CSV Cleaner  (med spa cold-email lead gen)

Reads an Instant Data Scraper CSV (a Google Maps scrape of med spa /
medical-aesthetics businesses), filters out unqualified rows and national
chains, extracts an owner first name and a clean base domain, and writes a CSV
that is ready to feed into a Hunter.io bulk domain search.

Instant Data Scraper exports Google's obfuscated CSS-class names as headers
(e.g. "qBF1Pd", "lcr4fd href") instead of friendly names, and those class
names change whenever Google updates Maps. So this script detects each column
by its CONTENT (URLs vs ratings vs review counts vs names), not by header
text. If the file already has friendly headers ("Business Name", "Website
URL", ...) those are used directly.

Run:   python part_a.py
Standard library only. No external API calls of any kind.
"""

import csv
import math
import os
import re
import sys
import time

# --- Step 2 blocklist: national MED SPA chains / franchises (lower-cased) ---
# Only distinctive brand strings safe for case-insensitive SUBSTRING matching.
# Generic-sounding chains (e.g. "Radiance Medspa") are left to the AI step so
# they don't false-match independent local businesses.
CHAINS = {
    "ideal image", "laseraway", "milan laser", "sono bello", "skinspirit",
    "ever/body", "restore hyper wellness", "sev laser", "sona medspa",
    "european wax", "hand & stone", "woodhouse spa", "spavia", "heyday",
    "skin laundry", "face foundrie", "dermani medspa", "medspa810",
    "vio med spa", "4ever young", "icryo", "nakedmd", "elase medspa",
    "kalologie medspa", "dripbar", "liquivida", "hydreight", "massage envy",
    "skinney medspa", "skinnyme", "laser lounge spa", "facial mania",
    "skin pharm", "laserie", "slender me medical", "amazing lash studio",
    "westlake dermatology", "schweiger dermatology", "forefront dermatology",
    "u.s. dermatology partners",
}

# --- Step 3 reject lists for extracted owner names ---
# A wrong first name ("Hi Aesthetics,") hurts a cold campaign more than a
# generic "Hi there," so these lists are deliberately broad. They are the main
# tuning knob: add any junk "name" you see in the output here.
# NOTE: ambiguous words that are ALSO common first names (Rose, Bella, Pearl,
# Crystal, and the surnames Le / Do) are intentionally NOT listed, so a real
# owner named that still gets personalized.

# (1) Generic quality / geo words (niche-agnostic).
SERVICE_WORDS = {
    "pro", "premier", "elite", "care", "local", "best", "quality",
    "professional", "expert", "master", "total",
    "texas", "fort", "dallas", "north", "south", "east", "west",
}
# (2) Med spa / medical-aesthetics industry words (never owner names).
SERVICE_WORDS |= {
    "spa", "med", "medi", "medspa", "medspas", "medical", "aesthetic",
    "aesthetics", "aesthetica", "esthetic", "esthetics", "esthetician",
    "estheticians", "skin", "skincare", "skins", "dermal", "derma", "derm",
    "dermatology", "dermatologist", "laser", "lasers", "wellness", "clinic",
    "clinical", "clinique", "cosmetic", "cosmetics", "cosmetology",
    "injectable", "injectables", "botox", "filler", "fillers", "dysport",
    "juvederm", "restylane", "kybella", "sculptra", "microneedling",
    "microblading", "peel", "peels", "hydrafacial", "hydrafacials", "facial",
    "facials", "face", "body", "contour", "contouring", "coolsculpting",
    "sculpt", "sculpting", "lipo", "liposuction", "beauty", "glow",
    "rejuvenation", "rejuvenate", "renewal", "lounge", "bar", "studio",
    "studios", "boutique", "salon", "parlor", "lash", "lashes", "brow",
    "brows", "wax", "waxing", "ageless", "antiaging", "aging", "center",
    "centre", "institute", "academy", "infusion", "infusions", "hydration",
    "hydra", "slim", "slimming", "weightloss", "tan", "tanning", "cryotherapy",
    "cryo", "sauna", "massage", "vitality", "regen", "complexion", "collagen",
    "dermaplaning", "morpheus", "emsculpt", "threadlift", "esthetique",
    "glowing", "beautiful", "services", "solutions",
    # generic role / group words that sneak in via possessives ("Women's...")
    "women", "womens", "men", "mens", "age", "physician", "physicians",
    "ladies", "gents", "kids", "patient", "patients", "client", "clients",
    "guest", "guests", "doctors",
}
# (3) Marketing / brand adjectives common in med spa / beauty names.
BRAND_WORDS = {
    "luxe", "luxury", "luxurious", "deluxe", "allure", "alluring", "radiance",
    "radiant", "pure", "purity", "bliss", "blissful", "serenity", "serene",
    "revive", "revival", "renew", "renewed", "refine", "refined", "flawless",
    "premium", "prestige", "prestigious", "timeless", "eternal", "divine",
    "glamour", "glam", "glamorous", "polished", "opulent", "elegance",
    "elegant", "exquisite", "essence", "harmony", "tranquil", "tranquility",
    "zen", "oasis", "sanctuary", "haven", "retreat", "indulge", "pamper",
    "ethereal", "gilded", "platinum", "velvet", "silk", "satin", "ivory",
    "porcelain", "noble", "royal", "regal", "majestic", "imperial", "vogue",
    "chic", "posh", "fabulous", "stunning", "gorgeous", "youthful", "youth",
    "fresh", "vibrant", "luminous", "shine", "shimmer", "sparkle", "dazzle",
    "brilliance", "brilliant", "dewy", "supple", "reborn", "transform",
    "transformation", "reflection", "modern", "sleek", "minimal", "urban",
    "metro", "uptown", "signature", "bespoke", "couture", "atelier", "supreme",
    "ultimate", "apex", "pinnacle", "peak", "summit", "perfect", "ideal",
    "flourish", "lush", "blossom", "bloom", "elevate", "uplift", "awaken",
    "balance", "calm", "soothe", "comfort", "prime", "premiere", "advanced",
}
# (4) Medical titles / credentials that precede a name (never the name itself).
# 'le' and 'do' are deliberately omitted (common Vietnamese surnames).
TITLE_WORDS = {
    "dr", "drs", "doctor", "md", "dpm", "rn", "lpn", "np", "nurse", "fnp",
    "aprn", "crna", "pa", "dds", "dmd", "faad", "facs", "msn", "bsn", "dnp",
    "phd", "esthetician", "prof", "mr", "mrs", "ms", "miss",
}
# (5) DFW-area cities / regions (a city is not an owner name).
PLACE_WORDS = {
    "dfw", "plano", "frisco", "allen", "irving", "mckinney", "garland",
    "denton", "arlington", "richardson", "carrollton", "lewisville",
    "rockwall", "mesquite", "grapevine", "mansfield", "keller", "southlake",
    "coppell", "addison", "prosper", "celina", "wylie", "sachse", "murphy",
    "metroplex", "county", "city",
}
# Structural / connector / pronoun words that can leak through the patterns
# but are obviously not owner names (e.g. "By the Spa" -> "By",
# "It's A Secret" -> "It", "Let's Glow" -> "Let").
STOP_WORDS = {"by", "and", "the", "of", "a", "an", "for", "your", "&",
              "it", "its", "let", "lets", "that", "what", "who", "this"}

# Everything we refuse to treat as a first name.
NOT_A_NAME = (SERVICE_WORDS | BRAND_WORDS | TITLE_WORDS
              | PLACE_WORDS | STOP_WORDS)

# Name-extraction strictness:
#   True  = CONSERVATIVE. Only high-confidence patterns - possessive ("Jay's"
#           -> Jay), "by Name" ("...by Steve" -> Steve), and family names
#           ("Smith & Sons" / "Johnson and Sons" -> Smith / Johnson).
#           Bare first words are NOT used, so brand words like "Empire" or
#           "Greenland" become "there". Fewer names, virtually no wrong ones.
#   False = AGGRESSIVE. Also use the bare first word ("Vargas Med Spa" ->
#           Vargas). More names, but some will be brand/place words.
CONSERVATIVE = True

# Review-count thresholds.
#   MIN_REVIEWS drops brand-new / inactive listings.
#   MAX_REVIEWS is the UPPER ceiling and is OFF (None) by default: a high
#   review count usually means an established, cash-rich INDEPENDENT spa (a
#   great lead). Franchises/chains are already removed by the chain blocklist
#   + AI verification, NOT by review count - so capping reviews mostly throws
#   away qualified independents. Set MAX_REVIEWS to a number (e.g. 1000) only
#   if you deliberately want to drop very large listings.
MIN_REVIEWS = 25
MAX_REVIEWS = None

# AI verification: after the keyword chain filter and de-dup, ask Claude to
# classify each surviving company and keep only true LOCAL businesses.
# Needs ANTHROPIC_API_KEY (in a .env file) and `pip install anthropic`.
# Set to False to skip it entirely (no API calls, no cost).
AI_VERIFY = True
AI_MODEL = "claude-haiku-4-5-20251001"
AI_DELAY_SECONDS = 0.5
CLASSIFIER_SYSTEM = (
    "You are a business classifier. Classify this company into one of four "
    "categories:\n"
    "LOCAL - local independent med spa, medical aesthetics, or skincare "
    "service business\n"
    "CHAIN - national franchise or corporate chain (multi-location brand)\n"
    "SUPPLIER - supply store, equipment/product distributor, or product "
    "brand, not a service\n"
    "WRONG - not related to med spa / medical aesthetics / skincare at all\n"
    "Respond with ONE word only: LOCAL, CHAIN, SUPPLIER, or WRONG"
)

# Google / infrastructure hosts that are never a real business website.
INFRA_HOSTS = ("google.", "gstatic.", "ggpht.", "googleusercontent.",
               "schema.org", "g-m/")

# Shared platforms / social profiles: these are real URLs, but Hunter can't
# find an owner's email behind them, so they're treated as "no usable site".
# Add or remove hosts here to taste.
PLATFORM_DOMAINS = {
    "facebook.com", "m.facebook.com", "fb.com", "fb.me", "instagram.com",
    "linktr.ee", "linktree.com", "yelp.com", "nextdoor.com",
    "twitter.com", "x.com", "youtube.com", "tiktok.com", "threads.net",
    "pinterest.com", "business.site", "sites.google.com", "google.com",
    # Med spa booking / scheduling platforms (no findable owner email there)
    "vagaro.com", "booksy.com", "mindbodyonline.com", "fresha.com",
    "schedulicity.com", "glossgenius.com", "squareup.com", "square.site",
    "setmore.com", "zenoti.com", "boulevard.io", "nextpatient.co",
}

URL_RE = re.compile(r"^\s*https?://", re.I)
# Google Maps place URLs embed the GPS pin as "!3d<lat>!4d<lon>".
COORD_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")

# Offline city centroids (lat, lon). Used to turn the GPS pin in the Maps URL
# into a city WITHOUT any API. Covers the DFW metroplex + major Texas metros;
# add rows here for other areas you scrape. A business is tagged with the
# nearest city within CITY_MAX_KM, else it falls back to the prompt city.
CITY_MAX_KM = 30.0
CITY_COORDS = {
    # --- DFW metroplex ---
    "Dallas": (32.7767, -96.7970), "Fort Worth": (32.7555, -97.3308),
    "Arlington": (32.7357, -97.1081), "Plano": (33.0198, -96.6989),
    "Garland": (32.9126, -96.6389), "Irving": (32.8140, -96.9489),
    "Frisco": (33.1507, -96.8236), "McKinney": (33.1972, -96.6398),
    "Grand Prairie": (32.7459, -96.9978), "Denton": (33.2148, -97.1331),
    "Mesquite": (32.7668, -96.5992), "Carrollton": (32.9537, -96.8903),
    "Richardson": (32.9483, -96.7299), "Lewisville": (33.0462, -96.9942),
    "Allen": (33.1032, -96.6706), "Flower Mound": (33.0146, -97.0969),
    "North Richland Hills": (32.8343, -97.2289), "Mansfield": (32.5632, -97.1417),
    "Rowlett": (32.9029, -96.5639), "Euless": (32.8371, -97.0820),
    "Grapevine": (32.9343, -97.0781), "Bedford": (32.8440, -97.1431),
    "Cedar Hill": (32.5885, -96.9561), "Wylie": (33.0151, -96.5388),
    "Keller": (32.9346, -97.2517), "Coppell": (32.9546, -96.9900),
    "Hurst": (32.8235, -97.1706), "Duncanville": (32.6518, -96.9083),
    "DeSoto": (32.5896, -96.8570), "Haltom City": (32.7996, -97.2692),
    "Rockwall": (32.9312, -96.4597), "The Colony": (33.0890, -96.8861),
    "Burleson": (32.5421, -97.3208), "Little Elm": (33.1626, -96.9375),
    "Farmers Branch": (32.9265, -96.8961), "Colleyville": (32.8807, -97.1550),
    "Southlake": (32.9412, -97.1342), "Sachse": (32.9762, -96.5916),
    "Murphy": (33.0151, -96.6130), "Addison": (32.9618, -96.8292),
    "Lancaster": (32.5921, -96.7561), "Prosper": (33.2362, -96.8011),
    "Celina": (33.3245, -96.7847), "Waxahachie": (32.3865, -96.8483),
    "Midlothian": (32.4823, -96.9944), "Balch Springs": (32.7287, -96.6228),
    "Forney": (32.7482, -96.4719), "Crowley": (32.5793, -97.3625),
    "Saginaw": (32.8601, -97.3645), "Watauga": (32.8579, -97.2547),
    "Trophy Club": (32.9929, -97.1849), "Roanoke": (33.0040, -97.2256),
    "Anna": (33.3490, -96.5483), "Melissa": (33.2857, -96.5728),
    "Princeton": (33.1801, -96.4978), "Corinth": (33.1540, -97.0647),
    "Aubrey": (33.3043, -96.9861), "Terrell": (32.7357, -96.2753),
    # NOTE: tiny enclaves fully inside Dallas (University Park, Highland Park)
    # are intentionally omitted so those businesses roll up to "Dallas".
    "Greenville": (33.1384, -96.1108), "Sherman": (33.6357, -96.6089),
    # --- other major Texas metros ---
    "Houston": (29.7604, -95.3698), "Austin": (30.2672, -97.7431),
    "San Antonio": (29.4241, -98.4936), "El Paso": (31.7619, -106.4850),
    "Corpus Christi": (27.8006, -97.3964), "Lubbock": (33.5779, -101.8552),
    "Amarillo": (35.2220, -101.8313), "Waco": (31.5493, -97.1467),
    "Killeen": (31.1171, -97.7278), "College Station": (30.6280, -96.3344),
    "Tyler": (32.3513, -95.3011), "Abilene": (32.4487, -99.7331),
    "Midland": (31.9974, -102.0779), "Odessa": (31.8457, -102.3676),
    "Beaumont": (30.0802, -94.1266), "Round Rock": (30.5083, -97.6789),
    "Sugar Land": (29.6197, -95.6349), "Galveston": (29.3013, -94.7977),
}


def base_domain(url):
    """https://www.glowmedspa.com/services -> glowmedspa.com  ('' if none)."""
    d = (url or "").strip().lower()
    if not d:
        return ""
    d = d.split("://", 1)[-1]      # drop scheme
    d = d.split("/", 1)[0]         # drop path
    d = d.split("?", 1)[0]         # drop query
    d = d.split("#", 1)[0]         # drop fragment
    if d.startswith("www."):
        d = d[4:]
    return d.split(":", 1)[0]      # drop port


def nearest_city(lat, lon):
    """Nearest city in CITY_COORDS within CITY_MAX_KM (haversine), else ''."""
    best, best_km = "", None
    for name, (clat, clon) in CITY_COORDS.items():
        dlat = math.radians(clat - lat)
        dlon = math.radians(clon - lon)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat)) * math.cos(math.radians(clat))
             * math.sin(dlon / 2) ** 2)
        km = 2 * 6371 * math.asin(math.sqrt(a))
        if best_km is None or km < best_km:
            best, best_km = name, km
    return best if best_km is not None and best_km <= CITY_MAX_KM else ""


def load_api_key():
    """Find ANTHROPIC_API_KEY in the environment or a nearby .env file."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    # Walk up from the script dir and the current dir looking for a .env file.
    candidates, seen = [], set()
    for base in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        d = base
        while True:
            candidates.append(os.path.join(d, ".env"))
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    for path in candidates:
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY"):
                        line = line.split("export ", 1)[-1]
                        _, _, val = line.partition("=")
                        return val.strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def classify_business(client, company_name):
    """Classify one company via the Anthropic API.

    Returns LOCAL / CHAIN / SUPPLIER / WRONG, or 'ERROR' if the call failed
    (caller keeps ERROR rows by default).
    """
    try:
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=10,
            system=CLASSIFIER_SYSTEM,
            messages=[{"role": "user",
                       "content": "Company name: {}".format(company_name)}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").upper()
        for category in ("LOCAL", "CHAIN", "SUPPLIER", "WRONG"):
            if category in text:
                return category
        return "LOCAL"            # unrecognized reply -> keep by default
    except Exception:
        return "ERROR"            # API failure -> keep by default


def clean_maps_csv(input_path, city=""):
    """Filter, de-chain, extract owner name + base domain.

    `city` is stamped onto every output row (one Maps search = one city);
    pass "" to leave the city blank / derive it from an address column.
    Returns the path of the CSV that was written.
    """
    folder = os.path.dirname(os.path.abspath(input_path))
    stem = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(folder, stem + "_cleaned_for_hunter.csv")

    with open(input_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    # ================= COLUMN DETECTION =================
    # Pass 1: friendly headers (used only if the export was renamed).
    name_col = web_col = rating_col = review_col = addr_col = maps_col = None
    for h in fields:
        norm = h.lower().replace("_", " ").replace("-", " ")
        if name_col is None and any(k in norm for k in
                                    ("business name", "company name", "title")):
            name_col = h
        if web_col is None and any(k in norm for k in
                                   ("website", "site url", "web url")):
            web_col = h
        if addr_col is None and any(k in norm for k in ("address", "location")):
            addr_col = h
        if rating_col is None and ("rating" in norm or "stars" in norm):
            rating_col = h
        if review_col is None and "review" in norm:
            review_col = h

    # Pass 2: content profiling (handles obfuscated class-name headers).
    profile = {}
    for c in fields:
        vals = [(row.get(c) or "").strip() for row in rows]
        ne = [v for v in vals if v]
        denom = len(ne) or 1
        n_url = n_site = n_maps = n_float = n_05 = n_gt5 = 0
        for v in ne:
            if URL_RE.match(v):
                n_url += 1
                host = base_domain(v)
                if "google.com/maps" in v.lower() or "/maps/place" in v.lower():
                    n_maps += 1
                elif (re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}", host)
                      and not any(b in host for b in INFRA_HOSTS)
                      and host not in PLATFORM_DOMAINS
                      and not any(host.endswith("." + p)
                                  for p in PLATFORM_DOMAINS)):
                    # Count only REAL business websites - not booking/social
                    # platforms (Zenoti/Vagaro/Square/etc.) - so the website
                    # column isn't mistaken for the "Book online" column.
                    n_site += 1
            try:
                x = abs(float(v.replace(",", "").replace("−", "-")))
                n_float += 1
                if 0 < x <= 5:
                    n_05 += 1
                elif x > 5:
                    n_gt5 += 1
            except ValueError:
                pass
        first_chars = [v[:1] for v in ne]
        profile[c] = {
            "ne": ne, "card": len(set(ne)), "denom": denom,
            "url": n_url, "site": n_site, "maps": n_maps,
            "fnum": n_float / denom, "f05": n_05 / denom, "fgt5": n_gt5 / denom,
            "avglen": sum(len(v) for v in ne) / denom,
            "quote_lead": sum(1 for ch in first_chars if ch in ('"', "·"))
            / denom,
        }

    def best(key, predicate=lambda c: True, minimum=1):
        cands = [c for c in fields if predicate(c)]
        if not cands:
            return None
        top = max(cands, key=lambda c: profile[c][key])
        return top if profile[top][key] >= minimum else None

    if maps_col is None:
        maps_col = best("maps")
    if web_col is None:
        # Require a meaningful number of REAL business sites, so a column of
        # booking links or images (≈0 real sites) is never picked as "website".
        web_min = max(8, int(0.02 * len(rows)))
        web_col = best("site", lambda c: c != maps_col, minimum=web_min)
    if rating_col is None:
        rating_col = best("f05", lambda c: profile[c]["fnum"] > 0.5, minimum=0.4)
    if review_col is None:
        review_col = best("fgt5", lambda c: profile[c]["fnum"] > 0.5
                          and c != rating_col, minimum=0.2)
        if review_col is None:   # fall back to any numeric col that isn't rating
            review_col = best("fnum", lambda c: c != rating_col, minimum=0.5)

    if name_col is None:
        # Prefer the text column whose values appear in the Maps place URL.
        # Require HIGH distinct-value cardinality so category/status/hours
        # columns ("Medical spa" repeated 1000x) can't be mistaken for names.
        text_cols = [c for c in fields
                     if profile[c]["url"] == 0 and profile[c]["fnum"] < 0.3
                     and profile[c]["card"] >= max(5, 0.2 * profile[c]["denom"])
                     and profile[c]["quote_lead"] < 0.3
                     and profile[c]["avglen"] < 60]
        if maps_col and text_cols:
            maps_vals = [(row.get(maps_col) or "").lower() for row in rows]
            scored = {}
            for c in text_cols:
                hits = 0
                for row, mv in zip(rows, maps_vals):
                    v = (row.get(c) or "").strip().lower().replace(" ", "+")
                    if len(v) >= 3 and v in mv:
                        hits += 1
                scored[c] = hits
            name_col = max(scored, key=scored.get) if scored else None
            if name_col and scored[name_col] == 0:
                name_col = None
        if name_col is None and text_cols:   # fallback: most-unique short text
            name_col = max(text_cols, key=lambda c: profile[c]["card"])

    # Did we actually find a column of REAL business websites? If the best
    # candidate has almost none, the scrape probably captured "Book online" /
    # social links instead of the Website link (see the warning at the end).
    web_real_sites = profile[web_col]["site"] if web_col else 0

    # ================= PROCESS ROWS =================
    total_in = len(rows)
    removed = {"low_reviews": 0, "high_reviews": 0, "low_rating": 0,
               "no_website": 0, "chain": 0}
    out_rows = []

    for row in rows:
        name = (row.get(name_col, "") if name_col else "").strip()
        website = (row.get(web_col, "") if web_col else "").strip()
        rating_raw = (row.get(rating_col, "") if rating_col else "").strip()
        review_raw = (row.get(review_col, "") if review_col else "").strip()

        # review count -> int (handles "1,234", "(57)", "-156", "57 reviews")
        digits = re.sub(r"[^0-9]", "", review_raw)
        reviews = int(digits) if digits else None
        # rating -> float (handles "4.5", "4.5 stars")
        m = re.search(r"[0-9]+(?:\.[0-9]+)?", rating_raw)
        rating = float(m.group()) if m else None

        domain = base_domain(website)
        # Valid = a real registrable domain (dot + alphabetic TLD, ASCII only).
        # Rejects empty cells, Google ad-redirects, embedded header junk, and
        # the Material-icon glyph chars Instant Data Scraper captures for the
        # "no website" rows (e.g. U+E80B). Also drops shared-platform domains
        # Hunter can't resolve to an owner email.
        is_platform = (domain in PLATFORM_DOMAINS
                       or any(domain.endswith("." + p) for p in PLATFORM_DOMAINS))
        is_infra = any(b in domain for b in INFRA_HOSTS)   # google/gstatic images
        has_site = (
            re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}", domain) is not None
            and not is_platform and not is_infra)

        # ---- Step 1: quality filter (review floor; ceiling optional) ----
        if reviews is None or reviews < MIN_REVIEWS:
            removed["low_reviews"] += 1
            continue
        if MAX_REVIEWS is not None and reviews > MAX_REVIEWS:
            removed["high_reviews"] += 1
            continue
        if rating is None or rating < 4.0:
            removed["low_rating"] += 1
            continue
        if not has_site:
            removed["no_website"] += 1
            continue

        # ---- Step 2: drop national chains / large franchises ----
        if any(chain in name.lower() for chain in CHAINS):
            removed["chain"] += 1
            continue

        # ---- Step 3: owner first-name extraction ----
        nm = name.replace("’", "'")   # curly -> straight apostrophe
        candidates = []
        # High-confidence patterns (used in both modes):
        if "'" in nm:                       # Pattern 1: "Name's ..." -> Jay
            before = nm.split("'", 1)[0].split()
            if before:
                candidates.append(before[-1])
        mm = re.search(r"\bby\s+(\w+)", nm, re.IGNORECASE)    # Pattern 4: by Name
        if mm:
            candidates.append(mm.group(1))
        # Family name before "& Sons / and Brothers / and Family":
        mm = re.search(r"(\w+)\s*(?:&|\band)\s+"
                       r"(?:sons?|bro(?:s|ther|thers)?|family)\b",
                       nm, re.IGNORECASE)
        if mm:
            candidates.append(mm.group(1))
        if not CONSERVATIVE:
            # Lower-confidence patterns (aggressive mode only):
            words = nm.split()                                # Pattern 2: 1st word
            if words:
                candidates.append(words[0])
            mm = re.search(r"(\w+)\s+and\b", nm, re.IGNORECASE)   # Pattern 3
            if mm:
                candidates.append(mm.group(1))
            mm = re.search(r"(\w+)\s*&", nm)                      # Pattern 5
            if mm:
                candidates.append(mm.group(1))

        first_name = "there"
        for cand in candidates:
            c = cand.strip(" .,&-'\"")
            if (2 <= len(c) <= 12 and c.isalpha() and c[0].isupper()
                    and c.lower() not in NOT_A_NAME):
                first_name = c
                break

        # ---- Google Maps link (kept in the output) ----
        maps_url = (row.get(maps_col, "") if maps_col else "").strip()

        # ---- City: per-business sources first (GPS pin, then the address
        #      column), then the single prompt value as a last resort. This
        #      keeps a multi-city scrape (e.g. all of DFW) tagged per row. ----
        row_city = ""
        cm = COORD_RE.search(maps_url)
        if cm:
            row_city = nearest_city(float(cm.group(1)), float(cm.group(2)))
        if not row_city and addr_col:
            parts = [p.strip() for p in (row.get(addr_col) or "").split(",")
                     if p.strip()]
            while parts and parts[-1].lower() in (
                    "usa", "us", "united states", "united states of america"):
                parts = parts[:-1]
            # "123 Main St, Fort Worth, TX 76104" -> city is 2nd-from-last.
            row_city = parts[-2] if len(parts) >= 2 else ""
        if not row_city:
            row_city = city            # prompt fallback

        out_rows.append({
            "domain": domain,
            "googleMapsUrl": maps_url,
            "firstName": first_name,
            "companyName": name,
            "city": row_city,
            "reviewCount": reviews,
        })

    # ---- De-duplicate by domain (same business scraped more than once) ----
    # One row per domain saves Hunter credits and avoids double-emailing. Keep
    # the first hit, but upgrade its firstName if a later duplicate has one.
    unique = {}
    dup_count = 0
    for r in out_rows:
        key = r["domain"]
        if key not in unique:
            unique[key] = r
        else:
            dup_count += 1
            if unique[key]["firstName"] == "there" and r["firstName"] != "there":
                unique[key] = r
    out_rows = list(unique.values())

    # ---- AI verification (Anthropic API): keep only true LOCAL businesses ----
    ai_removed = {"CHAIN": 0, "SUPPLIER": 0, "WRONG": 0}
    ai_removed_list = []          # (companyName, category) for the report
    ai_errors = 0
    if AI_VERIFY and out_rows:
        api_key = load_api_key()
        try:
            import anthropic
        except ImportError:
            anthropic = None
        if not api_key:
            print("  AI verification SKIPPED: ANTHROPIC_API_KEY not found in "
                  "the environment or a .env file. Keeping all rows.\n")
        elif anthropic is None:
            print("  AI verification SKIPPED: the 'anthropic' package is not "
                  "installed (run: python3 -m pip install anthropic). "
                  "Keeping all rows.\n")
        else:
            client = anthropic.Anthropic(api_key=api_key)
            total = len(out_rows)
            print("  AI-verifying {} companies with {} "
                  "(~{} min)...".format(total, AI_MODEL, max(1, total // 100)))
            kept = []
            for i, r in enumerate(out_rows, 1):
                category = classify_business(client, r["companyName"])
                remove = category in ("CHAIN", "SUPPLIER", "WRONG")
                if remove:
                    ai_removed[category] += 1
                    ai_removed_list.append((r["companyName"], category))
                else:
                    if category == "ERROR":
                        ai_errors += 1
                    kept.append(r)
                print("    [{}/{}] {:<36} {}{}".format(
                    i, total, r["companyName"][:36], category,
                    "  REMOVED" if remove else ""))
                time.sleep(AI_DELAY_SECONDS)
            out_rows = kept
            print()

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["domain", "googleMapsUrl", "firstName",
                           "companyName", "city", "reviewCount"])
        writer.writeheader()
        writer.writerows(out_rows)

    # ================= SUMMARY =================
    named = sum(1 for r in out_rows if r["firstName"] != "there")
    print("=" * 60)
    print("PART A - GOOGLE MAPS CSV CLEANER - SUMMARY")
    print("=" * 60)
    print("Detected columns:")
    print("  business name -> {}".format(name_col or "NOT FOUND"))
    print("  website       -> {}".format(web_col or "NOT FOUND"))
    print("  rating        -> {}".format(rating_col or "NOT FOUND"))
    print("  review count  -> {}".format(review_col or "NOT FOUND"))
    print("  google link   -> {}".format(maps_col or "(none)"))
    print("  city          -> GPS from Maps link"
          + (" (fallback: " + city + ")" if city else ""))
    print("-" * 60)
    print("Rows in:                       {}".format(total_in))
    print("Removed - under {} reviews:    {}".format(
        MIN_REVIEWS, removed["low_reviews"]))
    if MAX_REVIEWS is None:
        print("Removed - high reviews:        0  (ceiling OFF - kept all)")
    else:
        print("Removed - over {} reviews:    {}".format(
            MAX_REVIEWS, removed["high_reviews"]))
    print("Removed - rating under 4.0:    {}".format(removed["low_rating"]))
    print("Removed - no/invalid website:  {}".format(removed["no_website"]))
    print("Removed - chain / franchise:   {}".format(removed["chain"]))
    print("Removed - duplicate domain:    {}".format(dup_count))
    print("Removed - AI (not local):      {}".format(sum(ai_removed.values())))
    print("    chain:    {}".format(ai_removed["CHAIN"]))
    print("    supplier: {}".format(ai_removed["SUPPLIER"]))
    print("    wrong:    {}".format(ai_removed["WRONG"]))
    if ai_errors:
        print("    (api errors, kept by default: {})".format(ai_errors))
    print("Total removed:                 {}".format(
        sum(removed.values()) + dup_count + sum(ai_removed.values())))
    print("Rows out:                      {}".format(len(out_rows)))
    print("  owner name found:            {} of {}".format(named, len(out_rows)))
    print("  city found:                  {} of {}".format(
        sum(1 for r in out_rows if r["city"]), len(out_rows)))
    if ai_removed_list:
        print("-" * 60)
        print("Removed by AI verification ({}):".format(len(ai_removed_list)))
        for nm, cat in ai_removed_list:
            print("  [{:<8}] {}".format(cat, nm))
    print("Output file:                   {}".format(output_path))
    print("=" * 60)
    if not name_col or not web_col:
        print("WARNING: a key column was not detected. Check the mapping above;")
        print("headers in file: " + (", ".join(fields) or "(none)"))
    # Scrape-quality alarm: hardly any real websites in the chosen column
    # (under 5% of rows). Fraction-based so small/test scrapes don't false-fire.
    if web_real_sites < 0.05 * total_in:
        print("!" * 60)
        print("WARNING - NO REAL WEBSITES FOUND IN THIS SCRAPE")
        print("The website column ({}) has only {} real business".format(
            web_col or "NOT FOUND", web_real_sites))
        print("websites out of {} rows. This scrape almost certainly".format(
            total_in))
        print("captured the 'Book online' / social link instead of the")
        print("'Website' link, so nearly everything was dropped as")
        print("'no/invalid website' and the output is tiny.")
        print("FIX: re-scrape and capture the WEBSITE column (the link behind")
        print("the 'Website' button on each Google Maps listing).")
        print("!" * 60)
    return output_path


if __name__ == "__main__":
    print("Part A - Google Maps CSV cleaner\n")
    path = ""
    for _ in range(3):
        raw = input("Path to the Instant Data Scraper CSV: ").strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            raw = raw[1:-1]
        raw = raw.strip().replace("\\ ", " ")   # unescape drag-and-drop spaces
        if os.path.isfile(raw):
            path = raw
            break
        print("  File not found: {!r} - try again.\n".format(raw))
    if not path:
        print("No valid file provided. Exiting.")
        sys.exit(1)
    city = input("Fallback city (used only when GPS can't match; optional): ").strip()
    try:
        clean_maps_csv(path, city)
    except Exception as e:
        print("\nERROR: {}".format(e))
        sys.exit(1)
