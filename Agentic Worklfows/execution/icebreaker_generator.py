"""
Icebreaker Generator - Creates personalized email icebreakers from research data
Uses Claude Opus 5.5 at low effort (every model call runs on Opus 5.5 since
2026-09-25; rough estimate ~$0.01/icebreaker, not yet measured).
"""

import os
import re
import random
import logging
from typing import Optional
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

MODEL = "claude-opus-5-5"
# Opus 5.5 always thinks: `thinking` can't be disabled and temperature/top_p/
# top_k return a 400. Effort is the control; "low" keeps thinking short on this
# one-line call. Thinking counts toward max_tokens, so leave room for it.
EFFORT = "low"
THINKING_HEADROOM_TOKENS = 1024


def _text_of(response) -> str:
    """Join the text blocks; a thinking block may come first."""
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")

EXAMPLE_ICEBREAKERS = [
    "Shifting from 14 years in restaurant management to nearly three decades leading a service business shows serious entrepreneurial grit—respect that kind of pivot, figured I'd reach out.",
    "Over a decade of delivering top-tier office lighting with a customer-first mindset speaks volumes about your leadership—figured I'd reach out.",
    "50 years growing a family-owned business into the nation's top DC motor remanufacturer speaks to serious dedication—especially across six states—figured I'd reach out.",
    "18 years leading Mister Sparky while uplifting peers in the trade shows serious commitment to both craft and community—your support for others really stood out to me, figured I'd reach out.",
    "Over 13 years leading complex electrical and fiber optic installs across Greater Houston shows serious grit and expertise—impressive track record, figured I'd reach out.",
    "35 years in electrical services and your commitment to Houston's economic stability through quality work say a lot about your values—figured I'd reach out.",
    "A decade of leading Assurance Electric through Houston's competitive market shows real grit and vision—congrats on 10 strong years, figured I'd reach out.",
    "Your commitment to professionalism and educating customers through every step shows how much you value trust—something I deeply respect as well. Figured I'd reach out.",
    "Your journey from field apprentice to president shows serious grit and passion for electrical construction—I share that respect for building from the ground up, figured I'd reach out.",
    "Your journey from Master Electrician to nearly 12 years as CEO shows real grit and vision—especially with your focus on community trust and leadership. Figured I'd reach out.",
    "Serving League City and Dickinson with licensed, code-compliant work shows a serious commitment to safety and quality—values I share as well. Figured I'd reach out.",
    "Serving Pasadena since 2005 and building to an A+ BBB rating speaks to serious long-term commitment—reminds me of my own roots in service-driven work, so I figured I'd reach out.",
    "Your move from hands-on Master Electrician to leading your own firm shows serious drive and mastery of the trade—respect the journey and figured I'd reach out.",
    "Running your own electrical contracting business since 2007 shows serious long-term grit and dedication—over 15 years of leading from the front. Figured I'd reach out.",
    "Over 25 years delivering industrial electrical work with HUB certification shows serious dedication to community and craft—figured I'd reach out.",
    "25 years mastering the electrical trade while building a family-first business speaks volumes about your dedication to quality and trust—figured I'd reach out.",
    "Co-founding Harmony Electric and leading it for nearly 41 years while championing women-owned businesses speaks volumes about your resilience and values—figured I'd reach out.",
    "Starting BCB Electrical in 2023 shows serious drive to build something from the ground up—respect the hustle and figured I'd reach out.",
    "Climbing from VP of Ops to President shows serious long-term vision and grit—your growth mindset in the construction world really stood out to me, so I figured I'd reach out.",
]

HOOK_PRIORITIES = [
    "years_in_business",
    "career_transition",
    "growth_scale",
    "family_owned",
    "certifications",
    "community_involvement",
    "hands_on_leadership",
    "values_driven",
]


INDUSTRY_SUFFIX_WORDS = {
    'plumbing', 'electric', 'electrical', 'electricians', 'electrician',
    'hvac', 'roofing', 'mechanical', 'heating', 'cooling', 'air',
    'services', 'service', 'contractors', 'contractor', 'co', 'inc',
    'llc', 'corp', 'company', 'corporation', 'group', 'and', 'the',
    'pro', 'pros', 'solutions',
}


def _normalize_company_tokens(name: str) -> set:
    """Extract significant (non-industry, non-stopword) tokens from a company name."""
    if not name:
        return set()
    cleaned = re.sub(r"[^\w\s'&-]", ' ', name.lower())
    tokens = {t.strip("'-&") for t in cleaned.split()}
    tokens = {t for t in tokens if len(t) >= 3 and t not in INDUSTRY_SUFFIX_WORDS}
    return tokens


def _extract_company_phrases(text: str) -> list:
    """Find phrases in text that look like company names (capitalized words + industry keyword)."""
    pattern = (
        r"\b((?:[A-Z][\w'&-]*\s+){0,3}[A-Z][\w'&-]*)\s+"
        r"(Plumbing|Electric|Electrical|HVAC|Roofing|Mechanical|Heating|"
        r"Cooling|Services|Service|Contractors|Co\.?|Inc\.?|LLC|Company|Corporation)\b"
    )
    matches = re.findall(pattern, text)
    return [' '.join(m) for m in matches]


def contains_wrong_company(icebreaker: str, actual_company: str) -> bool:
    """
    Returns True if the icebreaker mentions a company-like phrase that
    doesn't share any significant token with the actual company name.
    """
    actual_tokens = _normalize_company_tokens(actual_company)
    if not actual_tokens:
        return False  # nothing distinctive to compare against

    phrases = _extract_company_phrases(icebreaker)
    for phrase in phrases:
        phrase_tokens = _normalize_company_tokens(phrase)
        if not phrase_tokens:
            continue
        if not (phrase_tokens & actual_tokens):
            return True
    return False


def generate_icebreaker(
    research_report: str,
    first_name: str,
    last_name: str,
    company_name: str,
    industry: str
) -> Optional[str]:
    """
    Generate a personalized icebreaker from research data using Claude Opus 5.5.
    """
    examples_text = "\n".join([f"- {ex}" for ex in random.sample(EXAMPLE_ICEBREAKERS, 10)])

    prompt = f"""You are generating a personalized email icebreaker for B2B cold outreach to a contractor.

## RULES:
1. ONE sentence, sometimes two joined with an em dash (—). 25-45 words.
2. Lead with the STRONGEST specific detail from the research: years in business, career pivot, certifications, growth, family legacy.
3. End EXACTLY with "figured I'd reach out." (lowercase f, period).
4. Use natural resonance language: "speaks to serious dedication", "shows real grit", "respect that kind of", "stood out to me", "values I share".
5. NO "I noticed", "I saw", or generic compliments.
6. Sound like a peer who genuinely respects their path—not a salesperson.

## HOOK PRIORITIES (pick the best one available):
1. Career transition / pivot (restaurant mgmt → service business, apprentice → president)
2. Longevity / years in business or trade
3. Growth / scaling (expanded to 6 states, grew from 2 to 50 employees)
4. Family legacy / generational business
5. Certifications / awards (BBB A+, HUB certified, Master Electrician)
6. Community / values driven leadership
7. Hands-on leadership (still in the field, personally leads projects)

## PROVEN EXAMPLES:
{examples_text}

## RESEARCH DATA:
{research_report}

## LEAD:
- Name: {first_name} {last_name}
- Company: {company_name}
- Industry: {industry}

Output ONLY the icebreaker. Nothing else."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=150 + THINKING_HEADROOM_TOKENS,
            output_config={"effort": EFFORT},
            system="You generate personalized B2B email icebreakers for contractor outreach. You write like a peer who respects their journey. You always end with 'figured I'd reach out.' You are concise and specific.",
            messages=[{"role": "user", "content": prompt}],
        )

        icebreaker = _text_of(response).strip()
        # A refusal or a reply cut off at max_tokens (thinking included) must
        # not reach validate_and_fix_icebreaker, which would pad it into a line.
        if not icebreaker or response.stop_reason in ("refusal", "max_tokens"):
            logger.warning(f"No usable icebreaker (stop_reason={response.stop_reason}), rejecting")
            return None

        # Reject refusals or overly long responses — fall back to template
        word_count = len(icebreaker.split())
        if word_count > 60:
            logger.warning(f"Icebreaker too long ({word_count} words), rejecting")
            return None
        if any(phrase in icebreaker.lower() for phrase in [
            "i can't generate", "i cannot generate", "no verifiable",
            "recommendation:", "**recommendation", "not enough information",
        ]):
            logger.warning("Model refused to generate icebreaker, rejecting")
            return None

        # Hallucination guard: reject if icebreaker mentions a different company
        if contains_wrong_company(icebreaker, company_name):
            logger.warning(
                f"Wrong-company hallucination detected for '{company_name}': {icebreaker[:100]}..."
            )
            return None

        icebreaker = validate_and_fix_icebreaker(icebreaker)
        return icebreaker

    except Exception as e:
        logger.error(f"Error generating icebreaker: {str(e)}")
        return None


def validate_and_fix_icebreaker(icebreaker: str) -> str:
    """Validate icebreaker follows rules and fix common issues."""
    icebreaker = icebreaker.strip('"\'')

    if not icebreaker.endswith("figured I'd reach out."):
        variations = [
            "figured I'd reach out",
            "figured i'd reach out.",
            "figured I'd reach out!",
            "Figured I'd reach out.",
            "so I figured I'd reach out.",
        ]
        for var in variations:
            if icebreaker.lower().endswith(var.lower()):
                icebreaker = icebreaker[:-len(var)].rstrip(" —-,") + "—figured I'd reach out."
                break
        else:
            if "figured" not in icebreaker.lower():
                icebreaker = icebreaker.rstrip(".!,") + "—figured I'd reach out."

    icebreaker = icebreaker.replace("--", "—")
    icebreaker = re.sub(r'\s+', ' ', icebreaker)

    return icebreaker.strip()


def generate_fallback_icebreaker(
    company_name: str,
    industry: str,
    city: str = None,
    state: str = None
) -> str:
    """Generate a generic icebreaker when research fails."""
    location = f"{city}, {state}" if city and state else "the area"

    templates = [
        f"Running a {industry} business in {location} takes real dedication to both craft and community—figured I'd reach out.",
        f"Building a {industry} company that serves {location} shows commitment to quality service—figured I'd reach out.",
        f"Staying competitive in {industry} in {location} takes serious grit—figured I'd reach out.",
    ]

    return random.choice(templates)


if __name__ == "__main__":
    sample_research = """### Decision Maker Personal Details: Sam Stilley
- **Current Role**: CEO of Amstill Roofing since 2010s, second-generation family leadership
- **Career Journey**: Took over family business from founder Frank Stilley
- **Achievements**: Celebrated 50 years of business in 2024, highest-rated roofer in Houston
- **Community Involvement**: Strong community ties in Houston area
- **Unique Path**: Second-generation CEO maintaining 50+ year family legacy

### Company Details (Backup): Amstill Roofing
- **Founded**: 1974 by Frank Stilley
- **Structure**: Family-owned and operated
- **Certifications/Awards**: BBB A+ rating"""

    print("Testing icebreaker generator (Claude Opus 5.5)...")
    print("=" * 60)

    icebreaker = generate_icebreaker(
        research_report=sample_research,
        first_name="Sam",
        last_name="Stilley",
        company_name="Amstill Roofing",
        industry="Roofing",
    )

    print(f"\nGenerated: {icebreaker}")
    expected_ending = "figured I'd reach out."
    print(f"Ends correctly: {icebreaker.endswith(expected_ending)}")
    words = icebreaker.split()
    print(f"Word count: {len(words)}")
