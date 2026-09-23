"""
Discover Owner + Research (Combined)
Single Perplexity call that returns:
  - Owner first name, last name, title (for email pattern generation)
  - Full research dump (used downstream for icebreaker)

Replaces both:
  - AnyMail Finder's name lookup ($300/mo gone)
  - The separate research_decision_maker call from perplexity_research.py

Cost: ~$0.005/lookup via Perplexity sonar.

Returns None if owner is UNKNOWN — caller should skip the lead entirely
to avoid further API spend.
"""

import os
import re
import logging
from typing import Optional, Dict
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(_env_path, override=True)

import requests

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


def discover_owner_and_research(
    company_name: str,
    city: str,
    state: str,
    industry: str = "Home Services",
    website: str = "",
) -> Optional[Dict[str, str]]:
    """
    Combined owner discovery + decision-maker research in ONE Perplexity call.

    Returns:
        Dict with keys:
          first_name, last_name, title, confidence (HIGH/MEDIUM/LOW),
          research (full text for icebreaker generation)
        OR None if owner is UNKNOWN — caller should skip this lead.
    """
    if not PERPLEXITY_API_KEY:
        logger.error("PERPLEXITY_API_KEY not set")
        return None

    website_hint = f" Their website is {website}." if website else ""

    query = (
        f"Research the owner/CEO/president of {company_name}, "
        f"a {industry} business in {city}, {state}.{website_hint}\n\n"
        f"Search the company website, BBB, LinkedIn, Google Business Profile, "
        f"news articles, and state contractor licensing databases.\n\n"
        f"Respond in this EXACT format:\n\n"
        f"OWNER_NAME: [First Last] | TITLE: [Owner/CEO/etc.] | CONFIDENCE: [HIGH/MEDIUM/LOW]\n\n"
        f"RESEARCH:\n"
        f"- Current Role: [title and tenure]\n"
        f"- Career Journey: [previous roles, transitions]\n"
        f"- Education / Certifications: [degrees, NATE, EPA, Master license, etc.]\n"
        f"- Achievements: [awards, growth milestones, recognition]\n"
        f"- Family Legacy: [generational business, founding context]\n"
        f"- Community / Values: [stated mission, charity, local involvement]\n"
        f"- Unique Path: [what makes their story stand out]\n\n"
        f"For ANY field where information is not available, write [NOT PROVIDED].\n\n"
        f"If you cannot find a specific person with reasonable confidence, respond ONLY with:\n"
        f"OWNER_NAME: UNKNOWN | TITLE: UNKNOWN | CONFIDENCE: LOW\n\n"
        f"Do not add other commentary outside this structure."
    )

    system_prompt = (
        "You are a research assistant identifying small-business owners for B2B outreach. "
        "Return verifiable, specific information. If sources conflict or are unclear, "
        "return UNKNOWN rather than guessing. Prefer concrete facts (years, revenue, "
        "credentials, awards) over vague claims."
    )

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        "temperature": 0.1,
        "max_tokens": 1200
    }

    try:
        response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        text = response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"Perplexity error for {company_name}: {e}")
        return None

    parsed = _parse_response(text)
    if not parsed:
        logger.warning(f"Could not parse Perplexity response for {company_name}: {text[:200]}")
        return None

    if parsed['first_name'].upper() == 'UNKNOWN' or not parsed['first_name']:
        logger.info(f"Owner UNKNOWN for {company_name} — skipping further spend")
        return None

    return parsed


def _parse_response(text: str) -> Optional[Dict[str, str]]:
    """Parse the structured Perplexity response."""
    name_match = re.search(r"OWNER_NAME:\s*([^|]+?)\s*\|", text, re.IGNORECASE)
    title_match = re.search(r"TITLE:\s*([^|]+?)\s*\|", text, re.IGNORECASE)
    conf_match = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)

    if not name_match:
        return None

    full_name = name_match.group(1).strip()
    if full_name.upper() == 'UNKNOWN':
        return {
            'first_name': 'UNKNOWN',
            'last_name': '',
            'title': '',
            'confidence': 'LOW',
            'research': '',
        }

    parts = full_name.split()
    if len(parts) == 0:
        return None
    elif len(parts) == 1:
        first_name, last_name = parts[0], ''
    else:
        first_name = parts[0]
        last_name = ' '.join(parts[1:])

    research_match = re.search(r"RESEARCH:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    research = research_match.group(1).strip() if research_match else ''

    return {
        'first_name': first_name,
        'last_name': last_name,
        'title': title_match.group(1).strip() if title_match else '',
        'confidence': conf_match.group(1).upper() if conf_match else 'MEDIUM',
        'research': research,
    }


if __name__ == "__main__":
    print("Test: Discover owner + research for a contractor")
    print("=" * 60)
    result = discover_owner_and_research(
        company_name="Amstill Roofing",
        city="Houston",
        state="TX",
        industry="Roofing",
        website="https://amstillroofing.com",
    )
    if result:
        print(f"Owner: {result['first_name']} {result['last_name']}")
        print(f"Title: {result['title']}")
        print(f"Confidence: {result['confidence']}")
        print(f"\nResearch preview:\n{result['research'][:500]}...")
    else:
        print("Owner UNKNOWN or error — would skip this lead")
