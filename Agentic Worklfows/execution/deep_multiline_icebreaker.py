"""
Deep Multiline Icebreaker Generator
====================================

Adapted from the "Deep Multiline Icebreaker System" n8n course template into a
standalone script that fits this repo's directive/execution architecture.

Pipeline per lead:
  1. Scrape the lead's homepage, extract internal links
  2. Pick up to N internal sub-pages (About/Services-style pages tend to win)
  3. Scrape each sub-page's text, summarize it with Claude Opus 5.5 (low effort)
  4. Feed the aggregated research into Claude Opus 5.5 for STRUCTURED SIGNAL
     EXTRACTION (primary treatment, tech brand, founding year, etc.) -- never
     freeform creative writing, just "is X clearly stated, yes/no/value"
  5. Pick the highest-priority ANGLE (from a fixed template library, see
     ANGLES below) whose required signal(s) are present, and fill it in
     deterministically -- no LLM call writes the actual sentence
  6. Prepend a deterministic "Hey {first_name}," greeting and write to CSV

Scope note: this tool's job is PERSONALIZATION ONLY. It does not write or
append a pitch/offer -- the output is a short, human greeting + one-line
reaction meant to be dropped into whatever email template/sequence handles
the actual offer.

Design note (2026-07-25, per Lorenzo): this replaced an earlier freeform-LLM
version. Content is now angle-template + deterministic fill, matching the
med-spa `relevance_line` tool's proven "angle library, auto-selected by
priority" pattern -- see the ANGLES list. Two of the originally-requested
angles are NOT implemented: GoogleReviewCount (this tool never queries Google
Maps -- only usable if a `google_review_count` column is passed in the input
CSV, e.g. from a CRM export that already has it) and SocialPlatform/ContentType
(this tool never visits social platforms at all -- would need a real social
scraper, not built).

Usage:
    python3 deep_multiline_icebreaker.py --input leads.csv --output results.csv
    python3 deep_multiline_icebreaker.py --input leads.csv --limit 5   # test mode
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icebreaker_generator import contains_wrong_company  # reuse hallucination guard
from google_sheets_client import get_sheets_client
import gspread

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Every model call runs on Claude Opus 5.5 (Lorenzo, 2026-09-25). The name
# SUMMARY_MODEL is kept so nothing that reads it breaks.
SUMMARY_MODEL = "claude-opus-5-5"
# No creative-generation model needed anymore -- angle selection + template
# fill is deterministic Python. The model is only ever asked to summarize/extract
# facts, never to write the final sentence.

# Opus 5.5 always thinks (thinking can't be disabled and it rejects
# temperature/top_p/top_k with a 400). Effort is the only control: "low" keeps
# the thinking short on these small extraction calls. Thinking counts toward
# max_tokens, so each call adds this headroom on top of the reply's own size.
SUMMARY_EFFORT = "low"
THINKING_HEADROOM_TOKENS = 1024

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
MAX_PAGE_CHARS = 8000

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js",
    ".zip", ".mp4", ".mov", ".ico", ".xml", ".doc", ".docx",
)
SKIP_PATH_KEYWORDS = (
    "privacy", "terms", "cookie", "login", "cart", "checkout", "wp-admin",
    "wp-login", "sitemap", "account", "signin", "sign-in",
)
PRIORITY_PATH_KEYWORDS = (
    "about", "story", "team", "mission", "service", "treatment", "menu",
    "result", "gallery", "press", "award", "our-", "who-we-are",
)

OUTPUT_FIELDNAMES = ["first_name", "last_name", "email", "website_url", "company_name",
                     "location", "pages_researched", "angle", "personalization"]

# Signals extracted from research (see extract_signals()). Values are
# {"type": "bool"|"int"|"str", ...bounds for sanity-checking}. Extraction
# must return null/False for anything not CLEARLY and EXPLICITLY stated --
# never inferred or guessed.
SIGNAL_SCHEMA = {
    "primary_treatment": {"type": "str", "allowed": ["neurotoxin", "filler", "laser"]},
    "specific_tech_brand": {"type": "str"},
    "has_weight_loss_program": {"type": "bool"},
    "year_founded": {"type": "int", "min": 1950, "max": 2026},
    "ownership_type": {"type": "str", "allowed": ["RN-owned", "NP-owned", "physician-led"]},
    "location_count": {"type": "int", "min": 2, "max": 50},
    "neighborhood": {"type": "str"},
    "has_membership_program": {"type": "bool"},
    "has_active_promo": {"type": "bool"},
    "is_founder_named": {"type": "bool"},
    # min raised from 1 to 150 (2026-07-26): "over 3 reviews is no joke" is
    # absurd -- a count only supports that specific claim once it's genuinely
    # a lot, not merely "greater than zero". 150 matches the threshold
    # already validated in the sibling med-spa relevance_line tool.
    "google_review_count": {"type": "int", "min": 150, "max": 100000},
    "review_rating": {"type": "float", "min": 1.0, "max": 5.0},
    # Derived: "good run in this space" only makes sense if the business is
    # actually old enough for that to be a meaningful claim.
    "long_established": {"type": "bool"},
    # Derived: template 2 claims "noticed a few of the before/afters" -- only
    # fire that specific claim if a before/after gallery is actually confirmed.
    "has_before_after_gallery": {"type": "bool"},
    # Derived (not extracted directly, see extract_signals()): only true when
    # a review claim is actually verifiable, not just asserted. Gates the
    # review-sentiment clauses in templates 1 and 3 (2026-07-25, per Lorenzo:
    # "as long as the actual sentence is factual to the company then its fine
    # if it doesnt apply its bad" -- built real verification rather than
    # dropping the clause or asserting it unconditionally).
    "reviews_confirmed_good": {"type": "bool"},
}
REVIEWS_CONFIRMED_MIN_RATING = 4.5

# Angle library: ordered by priority, first match wins. Each template is
# filled deterministically (no LLM call writes the sentence) -- variety
# comes from which real signal fired, not from a model improvising.
#
# 2026-07-25, Lorenzo: "i dont want your own invention use the templates" --
# these are his 15 reference templates VERBATIM (minus the "Hey {FirstName}, "
# greeting, which is built separately in code), one wording per angle, no
# invented variants. #12 (SocialPlatform/ContentType) is still not built --
# this tool never visits social platforms, not a wording choice.
#
# Known, accepted tradeoff from using literal single templates: if multiple
# leads in one batch match the same angle (e.g. several neurotoxin-heavy
# spas), they WILL get byte-identical text -- Lorenzo chose this over
# rotated variants when asked directly.
#
# Also carried over verbatim, flagged rather than silently kept or dropped:
# - #1/#3 assert "solid reviews on the Botox side"/"reviews are pretty
#   stacked". Lorenzo: "as long as the actual sentence is factual to the
#   company then its fine if it doesnt apply its bad" -- rather than drop
#   the clause or fire it unconditionally, these two angles now ALSO
#   require "reviews_confirmed_good" (see SIGNAL_SCHEMA/extract_signals) --
#   an explicit displayed star rating >= REVIEWS_CONFIRMED_MIN_RATING. A raw
#   review COUNT is not sufficient (500 reviews could be 2-star); if no
#   rating is confirmed, these angles simply don't fire and selection falls
#   through to the next matching angle. Wording is untouched either way.
# - #6 uses "{ReviewCount}+" -- the literal "+" shorthand Lorenzo himself
#   flagged as unnatural earlier this session ("no human would say 20+
#   years ever in conversation").
# - #11 ends "...which is basically what I do" -- pitch language, in
#   tension with the earlier "personalization only, no pitch" scope call.
ANGLES = [
    {"key": "primary_treatment_neurotoxin", "requires": ["primary_treatment:neurotoxin", "reviews_confirmed_good"],
     "templates": [
         "noticed you guys lean pretty heavy into neurotoxin work — solid reviews on the Botox side specifically.",
     ]},
    {"key": "primary_treatment_filler", "requires": ["primary_treatment:filler", "has_before_after_gallery"],
     "templates": [
         "saw {spa_name} does a lot of filler work — noticed a few of the before/afters on the site.",
     ]},
    {"key": "primary_treatment_laser", "requires": ["primary_treatment:laser", "reviews_confirmed_good"],
     "templates": [
         "{spa_name}'s laser hair removal reviews are pretty stacked — good sign.",
     ]},
    {"key": "specific_tech_brand", "requires": ["specific_tech_brand"],
     "templates": [
         "noticed you guys run {specific_tech_brand} — not every spa around here has that.",
     ]},
    {"key": "weight_loss_program", "requires": ["has_weight_loss_program"],
     "templates": [
         "saw {spa_name} added the weight loss/semaglutide side — smart move, a lot of spas have been doing that this year.",
     ]},
    {"key": "google_review_count", "requires": ["google_review_count"],
     "templates": [
         "{google_review_count}+ reviews on Google is no joke for a med spa — you clearly have a solid regular base.",
     ]},
    {"key": "year_founded", "requires": ["year_founded", "long_established"],
     "templates": [
         "noticed {spa_name}'s been around since {year_founded} — good run in this space.",
     ]},
    {"key": "ownership_type", "requires": ["ownership_type"],
     "templates": [
         "saw {spa_name}'s {ownership_type} — always reads better than the franchise spots.",
     ]},
    {"key": "location_count", "requires": ["location_count"],
     "templates": [
         "didn't realize {spa_name} had {location_count} locations now — that's a lot of patients moving through the door.",
     ]},
    {"key": "neighborhood", "requires": ["neighborhood"],
     "templates": [
         "saw you guys are right in {neighborhood} — good spot.",
     ]},
    {"key": "membership_program", "requires": ["has_membership_program"],
     "templates": [
         "noticed you run a membership program — usually means you're already thinking about retention, which is basically what I do.",
     ]},
    {"key": "active_promo", "requires": ["has_active_promo"],
     "templates": [
         "saw you guys are running a promo right now — good sign of an active list.",
     ]},
    {"key": "founder_named", "requires": ["is_founder_named"],
     "templates": [
         "{spa_name} coming up under your name specifically is a nice touch — most spas hide the owner.",
     ]},
    {"key": "fallback", "requires": [],
     "templates": [
         "been checking out a few med spas in the area and {spa_name} kept coming up — good reviews, clean site, the whole thing.",
     ]},
]

SUFFIX_WORDS_TO_STRIP = (
    "medical spa", "med spa", "medspa", "aesthetics", "spa", "clinic",
    "wellness", "beauty bar", "beauty",
)


def shorten_company_name(name: str) -> str:
    if not name:
        return name
    lowered = name.lower().strip()
    for suffix in sorted(SUFFIX_WORDS_TO_STRIP, key=len, reverse=True):
        if lowered.endswith(suffix):
            trimmed = name[: -len(suffix)].strip()
            return trimmed or name
    return name


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _get_text_block(response) -> str:
    # Opus 5.5 always thinks -- content[0] may be a ThinkingBlock, not text.
    # Pick the first block that actually is text.
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


def fetch_url(url: str) -> Optional[str]:
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        logger.warning(f"Fetch failed for {url}: {e}")
        return None


def extract_internal_links(html: str, base_url: str, limit: int) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc.lower().lstrip("www.")

    candidates = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        netloc = parsed.netloc.lower().lstrip("www.")
        if netloc != base_netloc:
            continue

        path = parsed.path.rstrip("/") or "/"
        if path == "/" or path in seen:
            continue
        if path.lower().endswith(SKIP_EXTENSIONS):
            continue
        if any(kw in path.lower() for kw in SKIP_PATH_KEYWORDS):
            continue

        seen.add(path)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{path}"
        candidates.append(clean_url)

    def priority(url: str) -> int:
        path = urlparse(url).path.lower()
        return 0 if any(kw in path for kw in PRIORITY_PATH_KEYWORDS) else 1

    candidates.sort(key=priority)
    return candidates[:limit]


def page_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "svg", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_PAGE_CHARS]


def summarize_page(url: str, text: str) -> Optional[str]:
    if not text or len(text) < 50:
        return None

    system = (
        "You're a research assistant creating factual abstracts of business web "
        "pages for a cold-email research pipeline. Never invent facts not present "
        "in the provided text."
    )
    user = (
        f"Page URL: {url}\n\nPage text:\n{text}\n\n"
        'Return strict JSON: {"abstract": "..."}. 2-4 sentences, comprehensive '
        "level of detail, spartan tone. If the page has no substantive content "
        '(nav-only, login wall, empty), return {"abstract": "no content"}.'
    )

    try:
        response = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=300 + THINKING_HEADROOM_TOKENS,
            output_config={"effort": SUMMARY_EFFORT},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parsed = _extract_json(_get_text_block(response))
        if not parsed:
            return None
        abstract = parsed.get("abstract", "").strip()
        if not abstract or abstract.lower() == "no content":
            return None
        return abstract
    except Exception as e:
        logger.warning(f"Summarization failed for {url}: {e}")
        return None


def research_lead(website_url: str, pages_per_lead: int) -> List[Dict[str, str]]:
    home_html = fetch_url(website_url)
    if not home_html:
        return []

    sub_urls = extract_internal_links(home_html, website_url, pages_per_lead)

    # Fallback: single-page site with no internal links found -- summarize home itself.
    if not sub_urls:
        text = page_to_text(home_html)
        abstract = summarize_page(website_url, text)
        return [{"url": website_url, "abstract": abstract}] if abstract else []

    results = []
    for url in sub_urls:
        html = fetch_url(url)
        if not html:
            continue
        text = page_to_text(html)
        abstract = summarize_page(url, text)
        if abstract:
            results.append({"url": url, "abstract": abstract})
    return results


DERIVED_SIGNALS = {"reviews_confirmed_good", "long_established"}  # computed after extraction, never asked of the model
LONG_ESTABLISHED_MIN_YEARS = 8

# 2026-07-26, per Lorenzo's direct question ("do these actually apply to the
# particular company... do all of them pass a logical analysis?"): a named
# brand alone doesn't mean "not every spa around here has that" is TRUE --
# HydraFacial and Juvederm are near-ubiquitous across the entire med-spa
# industry, so that claim is very likely false for either one, even though
# they're genuine, correctly-extracted brand names. Distinctive capital
# equipment (Emsculpt, Morpheus8, CoolSculpting, Tixel) is a different
# category from commodity consumable brands everyone carries -- filtered out
# mechanically (defense in depth) in addition to the prompt instruction below.
COMMODITY_TECH_BRANDS = {
    "hydrafacial", "botox", "dysport", "xeomin", "jeuveau", "juvederm",
    "juvéderm", "restylane", "belotero", "latisse", "diamondglow", "skinpen",
    "microneedling", "chemical peel", "dermaplaning",
}


def extract_signals(research: List[Dict[str, str]]) -> Dict:
    """Structured, non-creative extraction: is each SIGNAL_SCHEMA field
    clearly and explicitly stated in the research? Never inferred/guessed."""
    research_text = "\n".join(f"- {r['abstract']}" for r in research)

    extractable_schema = {k: v for k, v in SIGNAL_SCHEMA.items() if k not in DERIVED_SIGNALS}
    schema_desc = json.dumps(extractable_schema, indent=2)
    system = (
        "You extract structured facts from med-spa website research for a "
        "cold-email personalization tool. You are NOT writing prose -- you "
        "are filling a strict JSON schema. For every field, only fill it in "
        "if the research EXPLICITLY and CLEARLY states it. If a field is not "
        "clearly stated, use null (for strings/ints) or false (for bools). "
        "NEVER infer, guess, or estimate a value that isn't directly stated.\n\n"
        f"Schema (field: {{type, allowed values or bounds}}):\n{schema_desc}\n\n"
        '- "primary_treatment": only set if the research clearly indicates the '
        "site's menu/content leans heavily toward ONE of neurotoxin/filler/laser "
        "specifically -- not just that they offer it among many services.\n"
        '- "specific_tech_brand": ONLY a distinctive piece of specialized '
        "equipment/technology that NOT every med spa carries -- e.g. "
        "CoolSculpting, Emsculpt, Morpheus8, Tixel, Fraxel, Ultherapy, BBL. "
        "NEVER a commodity consumable brand nearly every med spa carries "
        "(HydraFacial, Botox, Dysport, Xeomin, Juvederm, Restylane, Belotero, "
        "microneedling, chemical peels) -- these provide no genuine "
        "distinctiveness even though they're real brand names.\n"
        '- "has_before_after_gallery": true only if the site explicitly shows '
        "actual before/after photos, not just a general treatments page.\n"
        '- "location_count": only if 2+ locations are explicitly stated.\n'
        '- "neighborhood": a specific named area/district, not just a city.\n'
        '- "google_review_count": only if a specific review count number is '
        "displayed/stated on the site itself.\n"
        '- "review_rating": only if an explicit star rating / score out of 5 '
        "is displayed on the site itself (e.g. a \"4.9 stars\" badge or widget) "
        "-- never estimate this from vague language like \"great reviews.\"\n\n"
        'Output strict JSON matching the schema, e.g. {"primary_treatment": '
        'null, "specific_tech_brand": "Morpheus8", "has_weight_loss_program": '
        'false, "year_founded": 2015, ...} -- include every field.'
    )

    try:
        response = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=400 + THINKING_HEADROOM_TOKENS,
            output_config={"effort": SUMMARY_EFFORT},
            system=system,
            messages=[{"role": "user", "content": f"Research:\n{research_text}"}],
        )
        parsed = _extract_json(_get_text_block(response)) or {}
    except Exception as e:
        logger.warning(f"Signal extraction failed: {e}")
        parsed = {}

    # Mechanical defense-in-depth: drop specific_tech_brand if it's actually
    # a commodity brand despite the prompt instruction above.
    brand = parsed.get("specific_tech_brand")
    if isinstance(brand, str) and brand.strip().lower() in COMMODITY_TECH_BRANDS:
        logger.info(f"Dropping commodity brand '{brand}' from specific_tech_brand (not genuinely distinctive)")
        parsed["specific_tech_brand"] = None

    # Derived signal: a review-sentiment claim is only "confirmed good" if an
    # explicit rating was found and it clears the bar -- a raw review COUNT
    # alone says nothing about sentiment (500 reviews could be 2-star).
    rating = parsed.get("review_rating")
    parsed["reviews_confirmed_good"] = bool(
        isinstance(rating, (int, float)) and rating >= REVIEWS_CONFIRMED_MIN_RATING
    )

    # Derived signal: "good run in this space" only makes sense once the
    # business is actually old enough for that to be a meaningful claim.
    year_founded = parsed.get("year_founded")
    parsed["long_established"] = bool(
        isinstance(year_founded, (int, float))
        and (datetime.now().year - year_founded) >= LONG_ESTABLISHED_MIN_YEARS
    )

    return parsed


def _signal_present(signals: Dict, key: str) -> bool:
    schema = SIGNAL_SCHEMA.get(key, {})
    value = signals.get(key)
    if schema.get("type") == "bool":
        return bool(value)
    if value is None or value == "":
        return False
    if schema.get("type") in ("int", "float"):
        try:
            value = int(value) if schema["type"] == "int" else float(value)
        except (TypeError, ValueError):
            return False
        lo, hi = schema.get("min"), schema.get("max")
        if lo is not None and value < lo:
            return False
        if hi is not None and value > hi:
            return False
        return True
    if schema.get("type") == "str":
        allowed = schema.get("allowed")
        if allowed and value not in allowed:
            return False
        return True
    return False


def select_and_fill_angle(signals: Dict, lead: Dict[str, str], angle_usage: Dict[str, int]) -> Optional[Dict]:
    spa_name = shorten_company_name(lead.get("company_name", ""))

    for angle in ANGLES:
        requires_met = True
        for req in angle["requires"]:
            if ":" in req:
                key, expected = req.split(":", 1)
                if signals.get(key) != expected:
                    requires_met = False
                    break
            else:
                if not _signal_present(signals, req):
                    requires_met = False
                    break
        if not requires_met:
            continue

        fill_values = {"spa_name": spa_name}
        for req in angle["requires"]:
            key = req.split(":", 1)[0]
            fill_values[key] = signals.get(key)

        # Round-robin through this angle's wording variants across the batch
        # so leads sharing an angle (common -- e.g. neurotoxin) don't get
        # byte-identical text.
        variants = angle["templates"]
        variant_index = angle_usage.get(angle["key"], 0) % len(variants)

        try:
            clause = variants[variant_index].format(**fill_values)
        except (KeyError, IndexError):
            continue

        if contains_wrong_company(clause, lead.get("company_name", "")):
            logger.warning(f"Angle '{angle['key']}' rejected: wrong-company hallucination")
            continue

        angle_usage[angle["key"]] = angle_usage.get(angle["key"], 0) + 1
        return {"angle": angle["key"], "clause": clause}

    return None


def generate_personalization(
    lead: Dict[str, str], research: List[Dict[str, str]], angle_usage: Dict[str, int]
) -> Optional[Dict]:
    signals = extract_signals(research)

    # Optional CSV passthrough: trust CRM-sourced values directly (e.g. a
    # `google_review_count` or `year_founded` column exported from a sheet
    # that already researched them) when the live scrape didn't find them.
    # `review_rating` is included here because star-rating widgets are
    # usually JS-rendered and rarely present in raw scraped HTML text --
    # without this, `reviews_confirmed_good` will almost never fire from
    # scraping alone, same limitation as `google_review_count`.
    for passthrough_key in ("google_review_count", "year_founded", "location_count", "review_rating"):
        if not signals.get(passthrough_key) and lead.get(passthrough_key):
            signals[passthrough_key] = lead[passthrough_key]

    if "review_rating" in lead and lead.get("review_rating"):
        try:
            signals["reviews_confirmed_good"] = float(lead["review_rating"]) >= REVIEWS_CONFIRMED_MIN_RATING
        except (TypeError, ValueError):
            pass

    filled = select_and_fill_angle(signals, lead, angle_usage)
    if not filled:
        return None

    first_name = (lead.get("first_name") or "").strip() or "there"
    return {
        "angle": filled["angle"],
        "personalization": f"Hey {first_name}, {filled['clause']}",
    }


def load_leads(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def process_leads(leads: List[Dict[str, str]], pages_per_lead: int, sleep_seconds: float) -> Dict:
    results = []
    stats = {"processed": 0, "success": 0, "skipped_no_website": 0, "skipped_scrape_failed": 0,
              "skipped_no_content": 0, "skipped_generation_failed": 0}
    angle_usage = {}  # tracks variant rotation per angle across this batch

    for i, lead in enumerate(leads):
        website_url = (lead.get("website_url") or "").strip()
        company_name = lead.get("company_name") or lead.get("headline") or ""
        stats["processed"] += 1

        logger.info(f"[{i+1}/{len(leads)}] {lead.get('first_name', '')} {lead.get('last_name', '')} / {company_name}")

        if not website_url:
            logger.info("  -> skipped: no website_url")
            stats["skipped_no_website"] += 1
            continue

        research = research_lead(website_url, pages_per_lead)
        if not research:
            logger.info("  -> skipped: no scrapeable content")
            stats["skipped_no_content"] += 1
            continue

        lead_for_gen = dict(lead)
        lead_for_gen["company_name"] = company_name
        outcome = generate_personalization(lead_for_gen, research, angle_usage)
        if not outcome:
            logger.info("  -> skipped: generation/validation failed")
            stats["skipped_generation_failed"] += 1
            continue

        results.append({
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "email": lead.get("email", ""),
            "website_url": website_url,
            "company_name": company_name,
            "location": lead.get("location", ""),
            "pages_researched": len(research),
            "angle": outcome["angle"],
            "personalization": outcome["personalization"],
        })
        stats["success"] += 1
        logger.info(f"  -> generated (angle: {outcome['angle']}, {len(research)} pages researched)")

        if i < len(leads) - 1:
            time.sleep(sleep_seconds)

    return {"results": results, "stats": stats}


def write_output(results: List[Dict], output_path: str):
    if not results:
        logger.warning("No results to write")
        return
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)
    logger.info(f"Wrote {len(results)} rows to {output_path}")


def _resolve_credentials_source(explicit_path: Optional[str]) -> str:
    if explicit_path:
        return explicit_path
    env_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if env_json:
        return env_json
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "credentials.json")
    if os.path.isfile(default_path):
        return default_path
    raise ValueError(
        "No Google credentials found. Set GOOGLE_CREDENTIALS_JSON in .env, "
        "place a credentials.json in the project root, or pass --credentials."
    )


def append_to_sheet(results: List[Dict], sheet_id: str, tab_name: str, credentials_path: Optional[str]):
    if not results:
        logger.warning("No results to append to sheet")
        return

    credentials_source = _resolve_credentials_source(credentials_path)
    client = get_sheets_client(credentials_source)
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.info(f"Tab '{tab_name}' not found -- creating it")
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(OUTPUT_FIELDNAMES))

    existing_header = worksheet.row_values(1)
    if not existing_header:
        worksheet.append_row(OUTPUT_FIELDNAMES, value_input_option="USER_ENTERED")

    rows = [[r.get(f, "") for f in OUTPUT_FIELDNAMES] for r in results]
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info(f"Appended {len(rows)} rows to sheet '{tab_name}' ({sheet_id})")


def main():
    parser = argparse.ArgumentParser(description="Generate deep multiline icebreakers from a lead CSV.")
    parser.add_argument("--input", required=True, help="Input CSV with columns: first_name,last_name,email,website_url,company_name,location")
    parser.add_argument("--output", default=None, help="Output CSV path (default: timestamped file next to script)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N leads (test mode)")
    parser.add_argument("--pages", type=int, default=3, help="Max internal sub-pages to research per lead (default 3)")
    parser.add_argument("--sleep", type=float, default=1.5, help="Seconds to sleep between leads (default 1.5)")
    parser.add_argument("--sheet-id", default=os.getenv("ICEBREAKER_SHEET_ID"), help="Google Sheet ID to append results to (optional; falls back to ICEBREAKER_SHEET_ID env var)")
    parser.add_argument("--sheet-tab", default="Deep Icebreakers", help="Worksheet/tab name to append to (default 'Deep Icebreakers'; created automatically if missing)")
    parser.add_argument("--credentials", default=None, help="Path to Google service account credentials.json (optional; falls back to GOOGLE_CREDENTIALS_JSON env var or ../credentials.json)")
    args = parser.parse_args()

    leads = load_leads(args.input)
    if args.limit:
        leads = leads[:args.limit]

    if not leads:
        logger.error("No leads found in input CSV")
        sys.exit(1)

    logger.info(f"Processing {len(leads)} leads ({args.pages} pages/lead)...")
    outcome = process_leads(leads, args.pages, args.sleep)

    output_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"deep_icebreakers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    )
    write_output(outcome["results"], output_path)

    if args.sheet_id and outcome["results"]:
        try:
            append_to_sheet(outcome["results"], args.sheet_id, args.sheet_tab, args.credentials)
        except Exception as e:
            logger.error(f"Sheet append failed (CSV output above is still intact): {e}")

    stats = outcome["stats"]
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for key, value in stats.items():
        print(f"{key}: {value}")
    print("=" * 50)


if __name__ == "__main__":
    main()
