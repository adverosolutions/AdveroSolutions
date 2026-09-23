"""
Perplexity Research - Decision Maker & Company Research via Perplexity API
"""

import os
import requests
import time
import logging
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


def search_perplexity(query: str, system_prompt: str = None) -> Optional[str]:
    """
    Search Perplexity API and return the response text.

    Args:
        query: The search query
        system_prompt: Optional system prompt for context

    Returns:
        Response text or None if failed
    """
    if not PERPLEXITY_API_KEY:
        logger.error("PERPLEXITY_API_KEY not found in environment variables")
        return None

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    default_system = """You are a research assistant gathering information about business owners and their companies.
    Provide factual, specific information. Include dates, numbers, and concrete details when available.
    If information is not found, explicitly state [NOT PROVIDED] for that field.
    Focus on verifiable facts from LinkedIn, company websites, BBB, news articles, and business registrations."""

    payload = {
        "model": "sonar",  # Perplexity's online search model
        "messages": [
            {"role": "system", "content": system_prompt or default_system},
            {"role": "user", "content": query}
        ],
        "temperature": 0.1,
        "max_tokens": 2000
    }

    try:
        response = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        return result['choices'][0]['message']['content']

    except requests.exceptions.Timeout:
        logger.error(f"Perplexity API timeout for query: {query[:50]}...")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Perplexity API error: {str(e)}")
        return None
    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected response format: {str(e)}")
        return None


def research_decision_maker(
    first_name: str,
    last_name: str,
    company_name: str,
    city: str,
    state: str,
    industry: str
) -> Optional[str]:
    """
    Research a decision maker (owner/CEO) via Perplexity.

    Returns structured information about the person.
    """
    query = f"""Research {first_name} {last_name}, the owner/decision maker at {company_name} in {city}, {state} ({industry} industry).

Find and report on:
1. **Current Role**: Their exact title and how long they've been in this position
2. **Career Journey**: Previous companies, roles, and career progression
3. **Education**: Degrees, certifications (especially NATE, EPA, trade certifications)
4. **Personal Mission/Values**: Any quotes, stated priorities, or public statements about their business philosophy
5. **Achievements**: Revenue growth, awards, business milestones, expansion
6. **Community Involvement**: Charity work, local organizations, church involvement
7. **Unique Path**: What makes their career story interesting (career changes, entrepreneurial leap, family business)

Search LinkedIn, company About pages, news articles, BBB profiles, and local business features.

Format as a structured report. For any field where information is not available, explicitly state [NOT PROVIDED]."""

    system_prompt = """You are researching a business owner for B2B outreach.
    Focus on finding SPECIFIC, PERSONAL details that would make good conversation starters.
    Prioritize: years of experience, career transitions, achievements, values, community involvement.
    Be thorough but concise. Include numbers and dates when available."""

    return search_perplexity(query, system_prompt)


def research_company(
    company_name: str,
    city: str,
    state: str,
    industry: str
) -> Optional[str]:
    """
    Research a company via Perplexity.

    Returns structured information about the business.
    """
    query = f"""Research {company_name} located in {city}, {state} ({industry} industry).

Find and report on:
1. **Year Founded**: When was the company established
2. **Company Structure**: Family-owned, franchise, LLC, corporation, etc.
3. **Employee Count**: Number of employees or team size
4. **Service Area**: Cities, counties, or regions served
5. **Certifications & Awards**: BBB rating, manufacturer certifications, industry awards
6. **Unique Attributes**: Specialties, guarantees, notable programs or services
7. **Recent Activity**: Expansions, news mentions, new locations, notable projects

Search BBB, Google Business Profile, company website, local news, and industry directories.

Format as a structured report. For any field where information is not available, explicitly state [NOT PROVIDED]."""

    system_prompt = """You are researching a company for B2B outreach.
    Focus on finding details that indicate company values, quality commitment, and longevity.
    Prioritize: founding year, BBB rating, certifications, family-owned status, years in business.
    Be factual and specific."""

    return search_perplexity(query, system_prompt)


def research_lead(
    first_name: str,
    last_name: str,
    company_name: str,
    city: str,
    state: str,
    industry: str,
    delay_between_calls: float = 2.0
) -> Tuple[Optional[str], Optional[str]]:
    """
    Complete research for a lead - both decision maker and company.

    Args:
        first_name: Decision maker's first name
        last_name: Decision maker's last name
        company_name: Company name
        city: City location
        state: State (2-letter code or full name)
        industry: Industry type (HVAC, Roofing, etc.)
        delay_between_calls: Seconds to wait between API calls

    Returns:
        Tuple of (decision_maker_research, company_research)
    """
    logger.info(f"Researching: {first_name} {last_name} at {company_name}")

    # Research decision maker first
    dm_research = research_decision_maker(
        first_name, last_name, company_name, city, state, industry
    )

    # Brief delay to avoid rate limits
    time.sleep(delay_between_calls)

    # Research company
    company_research = research_company(company_name, city, state, industry)

    return dm_research, company_research


def compile_research_report(
    first_name: str,
    last_name: str,
    company_name: str,
    dm_research: Optional[str],
    company_research: Optional[str]
) -> str:
    """
    Compile research into a structured dataProcessorSummary format.
    """
    report_parts = []

    # Decision Maker Section
    report_parts.append(f"### Decision Maker Personal Details: {first_name} {last_name}")
    if dm_research:
        report_parts.append(dm_research)
    else:
        report_parts.append("- **Research Status**: [NOT PROVIDED] - No detailed information found for decision maker")

    report_parts.append("")

    # Company Section
    report_parts.append(f"### Company Details (Backup): {company_name}")
    if company_research:
        report_parts.append(company_research)
    else:
        report_parts.append("- **Research Status**: [NOT PROVIDED] - No detailed information found for company")

    return "\n".join(report_parts)


def test_connection() -> bool:
    """Test Perplexity API connection"""
    if not PERPLEXITY_API_KEY:
        print("❌ PERPLEXITY_API_KEY not found in .env")
        return False

    print("Testing Perplexity API connection...")
    result = search_perplexity("What year was OpenAI founded?")

    if result:
        print("✅ Perplexity API connection successful")
        print(f"   Test response: {result[:100]}...")
        return True
    else:
        print("❌ Perplexity API connection failed")
        return False


if __name__ == "__main__":
    # Test the connection
    if test_connection():
        print("\n" + "="*50)
        print("Running sample research...")
        print("="*50)

        # Test with a sample lead
        dm_research, company_research = research_lead(
            first_name="Sam",
            last_name="Stilley",
            company_name="Amstill Roofing",
            city="Houston",
            state="TX",
            industry="Roofing"
        )

        report = compile_research_report(
            "Sam", "Stilley", "Amstill Roofing",
            dm_research, company_research
        )

        print("\n" + "="*50)
        print("COMPILED REPORT:")
        print("="*50)
        print(report)
