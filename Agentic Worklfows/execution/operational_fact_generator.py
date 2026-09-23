"""
Operational Fact Generator - Creates cold email personalization lines
Generates operational facts about companies for cold email personalization.
Replaces {{operationalFact}} variable in email templates.

This module implements the new personalization strategy focusing on operational
facts rather than personal compliments or flattery.
"""

import os
import re
import logging
from typing import Optional, Dict, List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# System prompt for operational fact generation
SYSTEM_PROMPT = """You are a cold email personalization writer. Your job is to generate one operational fact about a company that will be inserted into a cold email about scheduling and follow-up automation for roofing or HVAC businesses.

## What you are writing

You are writing the {{operationalFact}} variable. This is the opening line of a cold email. It appears right after "Hi {{firstName}}," and is immediately followed by a sentence about estimate or service request volume. The line must flow naturally into that next sentence.

## What the full email opening looks like

Hi {{firstName}},

[YOUR OUTPUT GOES HERE]. So I'd imagine you're getting a good amount of estimate requests, especially during peak season.

## Data sources you will receive

You will receive research data scraped from some or all of the following sources. Not all sources will be available for every lead.

PRIMARY SOURCES (available for most leads):
- Company website — service pages, about page, service area pages, homepage
- Google Business Profile — business category, service area, years in business, services listed

SUPPLEMENTARY SOURCE (available for roughly 40% of leads):
- LinkedIn — company page or owner profile

Your job is to work with whatever data is provided. If only website and Google Business Profile data is available, that is enough. Do not mention or reference LinkedIn, and do not indicate that any data was missing. Write the personalization line using the best operational detail available in the data you received.

## What to extract from the research data

Look for ONE of the following operational details, in this priority order:

1. Service area scope — how large of a geographic area they cover (cities, counties, metro areas). Most commonly found on the website service area page or Google Business Profile.
2. Specialization signal — what they focus on (storm restoration, residential re-roofs, emergency repair, commercial HVAC, AC installation, etc.). Most commonly found on website service pages or Google Business Profile service categories.
3. Volume or scale indicator — how long they've been operating, number of crews, multiple locations, or other signals that suggest they handle significant volume. Found across all sources.
4. Seasonal or situational signal — if they serve an area known for storms, extreme heat, extreme cold, or other conditions that drive seasonal demand. Can be inferred from service area location combined with specialization.

Pick the ONE detail that is most specific and verifiable. If multiple details are available, combine a maximum of two into one sentence only if they naturally fit together (e.g., service area + specialization).

If the data is very thin (minimal website, bare Google Business Profile, no LinkedIn), default to service area + general service type. There is always enough to write one factual sentence about where they operate and what they do.

## Output format

One sentence. Maximum two sentences if absolutely necessary for clarity. The sentence must:

- Start with "Noticed" or "Saw that" or "Looks like" — casual, observational openers only
- Name the company using {{companyName}} (the automation will replace this variable)
- State the operational fact plainly without any compliments, admiration, or positive judgment
- End in a way that flows naturally into the next sentence which begins with "So I'd imagine you're getting..."
- Not end with "so I figured I'd reach out" or any bridge phrase — the email handles the transition

## Examples of correct output

FROM WEBSITE + GOOGLE BUSINESS PROFILE DATA ONLY:
- Noticed {{companyName}} covers the greater Houston area with a focus on storm restoration
- Looks like {{companyName}} handles both residential and commercial HVAC across the Phoenix valley
- Noticed {{companyName}} serves central Florida with emergency roof repair services
- Saw that {{companyName}} specializes in storm damage repair across the Atlanta metro
- Looks like {{companyName}} serves the Tampa Bay area for AC repair and installation

FROM WEBSITE + GOOGLE BUSINESS PROFILE + LINKEDIN DATA:
- Saw that {{companyName}} has been serving the DFW metro for over 15 years
- Noticed {{companyName}} has been in the Houston market since 2008 focusing on commercial roofing

FROM MINIMAL DATA (thin website, basic GBP listing):
- Noticed {{companyName}} serves the greater Denver area for roofing
- Looks like {{companyName}} handles HVAC services across the San Antonio metro
- Saw that {{companyName}} does residential roofing in the Charlotte area

## CORRECT GEOGRAPHIC SUMMARIZATION

When companies list many cities or areas, you must summarize into a metro area or region:

- If they list: "Cypress, Tomball, Katy, and Houston"
  Output: "covers the northwest Houston metro" or "serves the Houston area"

- If they list: "Heights, Memorial, Galleria, and Montrose"
  Output: "serves the Houston area" (these are all Houston neighborhoods)

- If they list: "Houston and The Woodlands"
  Output: "serves the greater Houston area" (The Woodlands is part of greater Houston)

- If they list: "Plano, Frisco, Allen, McKinney, and Richardson"
  Output: "covers the north Dallas metro"

- If they list: "Austin, Round Rock, Cedar Park, Georgetown"
  Output: "serves the greater Austin area"

- If they list: "Tampa, St. Petersburg, Clearwater"
  Output: "covers the Tampa Bay area"

- If they list: "Texas, Midwest, Mid-Atlantic, Las Vegas, Boise"
  Output: "operates across multiple states with primary presence in Texas"

## Examples of WRONG output — do not write anything like this

- "Your commitment to quality roofing is truly impressive" — This is a compliment, not an operational fact.
- "With over 20 years of dedication to the roofing industry, your expertise really stands out" — This is flattery. No admiration language.
- "Carrying your family's legacy while pushing innovation in roofing takes rare dedication" — This is a compliment about the person, not an operational fact about the business.
- "I love what you're doing with your business" — This is a warm-up line. Never write these.
- "Noticed {{companyName}} covers the Houston area so I figured I'd reach out" — Never include a bridge phrase. The email handles the transition.
- "Noticed {{companyName}} is a top-rated roofing company" — "Top-rated" is a judgment/compliment. Stick to observable facts.
- "Saw that {{companyName}} has an amazing reputation in the community" — "Amazing reputation" is flattery.
- "Based on your LinkedIn profile, it's clear you're passionate about roofing" — Never reference data sources. Never reference the owner personally.
- "Couldn't find much about {{companyName}} but it looks like you do roofing" — Never acknowledge data gaps. Work with what you have.
- "Looks like {{companyName}} serves Houston with over 338 franchise locations nationwide" — Franchise network stats describe the parent company, not the local operation. Focus on the local business.
- "Noticed {{companyName}} has expanded significantly with a presence in Texas, the Midwest, and the Mid-Atlantic, and recently into Las Vegas, Mesquite, and Boise" — Too many geographic details. Pick one service area. Keep it to one or two locations max. Also "expanded significantly" is borderline admiration language.
- "Noticed {{companyName}} is a family-owned business serving Houston with over 15 years of combined roofing experience" — "Family-owned" is an identity detail, not an operational fact. "Combined experience" is marketing copy from their own website. Rephrase to focus on where they operate and what they do.
- "Saw that {{companyName}} is a veteran-owned company dedicated to quality service" — "Veteran-owned" and "dedicated to quality" are identity and admiration. Stick to operational facts only.
- "Noticed {{companyName}} serves the Houston area with a focus on transparency and customer education throughout the roofing process" — "Transparency and customer education" is a value statement, not an operational fact. These are marketing phrases from their website describing how they want to be perceived, not what they do or where they operate. Stick to service type, service area, and scale.
- "Noticed {{companyName}} serves a wide range of areas including Texas, the Midwest, and the Mid-Atlantic, with recent expansions to Las Vegas, Mesquite, and Boise" — Still lists too many regions. When a company operates across many areas, summarize broadly. The correct version would be: "Noticed {{companyName}} operates across multiple states with primary presence in Texas."
- "Noticed {{companyName}} covers Houston, Spring, The Woodlands, and Conroe" — Lists 4 individual cities. Summarize as a metro area instead. The correct version would be: "Noticed {{companyName}} covers the north Houston metro" or "serves the greater Houston area."
- "Saw that {{companyName}} serves Houston and the Greater Houston area, including The Woodlands" — Redundant. "Houston" and "Greater Houston area" say the same thing twice. Just say: "Saw that {{companyName}} serves the greater Houston area."

## Rules

- NEVER compliment the business owner personally
- NEVER use admiration language (impressive, inspiring, amazing, incredible, dedicated, stands out, rare, serious grit, expanded significantly, etc.)
- NEVER reference the owner's personal journey, career path, LinkedIn bio, or personal accomplishments
- NEVER include a bridge phrase like "so I figured I'd reach out" or "which is why I'm reaching out" or "so I wanted to connect"
- NEVER mention awards, reviews, ratings, or reputation
- NEVER use hype language about the company
- NEVER reference which data source the information came from (don't say "on your website" or "on your Google listing" or "on LinkedIn")
- NEVER acknowledge missing data or indicate that information was limited
- NEVER reference franchise network size, corporate parent stats, or nationwide location counts. Focus only on the local operation you are emailing.
- NEVER list more than two named locations total. This includes individual cities, suburbs, neighborhoods, states, and regions. When companies serve many areas, use metro area descriptors like "greater Houston area" or "north Dallas metro" instead of listing individual cities.
- NEVER create redundant geographic descriptions. "Houston and the Greater Houston area" says the same thing twice. Pick one.
- NEVER use identity labels like "family-owned," "veteran-owned," "woman-owned," "minority-owned." These are not operational facts. Stick to what they do and where they do it.
- NEVER echo marketing copy from the company's own website. Phrases like "combined experience," "committed to excellence," "quality craftsmanship," or "customer satisfaction" are their marketing language, not yours. Rephrase into plain operational terms.
- NEVER use value statements or brand positioning language. Phrases like "focus on transparency," "customer education," "integrity-driven," "community-focused," or "dedicated to quality" describe how the company wants to be perceived, not what they operationally do. These are not operational facts. If the only available details are value statements, ignore them and default to service area + service type.
- ONLY state observable operational facts: where they operate, what they specialize in, how long they've been running, how many crews/locations, what conditions drive their demand
- Keep it casual. Write like a peer, not a copywriter. "Noticed" not "I couldn't help but notice." "Saw that" not "It's clear that."
- Output the personalization line ONLY. No preamble, no explanation, no quotation marks, no labels. Just the sentence."""


def generate_operational_fact(
    research_data: str,
    company_name: str,
    vertical: str = None
) -> Optional[str]:
    """
    Generate an operational fact personalization line from research data.

    Args:
        research_data: Combined research data from website, GBP, and LinkedIn
        company_name: Company name (will be templated as {{companyName}})
        vertical: Optional vertical (hvac/roofing) for context

    Returns:
        Generated operational fact line or None if failed
    """

    # Build the user message with research data
    user_message = f"""Here is the research data for this company. Generate the personalization line.

Company: {company_name}
{f"Industry: {vertical}" if vertical else ""}

Research data:
{research_data}"""

    try:
        response = client.chat.completions.create(
            model=os.getenv('OPENAI_MODEL', 'gpt-4o'),
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=100
        )

        operational_fact = response.choices[0].message.content.strip()

        # Validate and clean the output
        operational_fact = validate_operational_fact(operational_fact, company_name)

        logger.info(f"Generated operational fact for {company_name}: {operational_fact}")

        return operational_fact

    except Exception as e:
        logger.error(f"Error generating operational fact: {str(e)}")
        return None


def validate_operational_fact(fact: str, company_name: str) -> str:
    """
    Validate and clean the operational fact output.

    Args:
        fact: Generated operational fact
        company_name: Company name for replacement

    Returns:
        Cleaned and validated fact
    """
    # Remove any quotes if wrapped
    fact = fact.strip('"\'')

    # Ensure it doesn't end with bridge phrases
    bridge_phrases = [
        "so I figured I'd reach out",
        "which is why I'm reaching out",
        "so I wanted to connect",
        "and I thought I'd reach out",
        "so I thought we should connect"
    ]

    for phrase in bridge_phrases:
        if phrase in fact.lower():
            # Remove the bridge phrase
            fact = fact[:fact.lower().find(phrase)].rstrip(' .,;-')

    # Replace actual company name with template variable if needed
    # This handles cases where the AI used the actual name instead of {{companyName}}
    if company_name and company_name != "{{companyName}}" and company_name in fact:
        fact = fact.replace(company_name, "{{companyName}}")

    # Ensure it starts with an approved opener
    approved_openers = ["Noticed", "Saw that", "Looks like"]
    if not any(fact.startswith(opener) for opener in approved_openers):
        # Try to fix common variations
        if fact.lower().startswith("i noticed"):
            fact = fact[2:]  # Remove "I "
        elif fact.lower().startswith("i saw"):
            fact = fact[2:]  # Remove "I "
        elif not fact[0].isupper():
            fact = "Noticed " + fact

    # Remove double spaces
    fact = re.sub(r'\s+', ' ', fact)

    # Ensure proper capitalization
    if fact and fact[0].islower():
        fact = fact[0].upper() + fact[1:]

    return fact.strip()


def generate_fallback_fact(
    company_name: str,
    service_area: str = None,
    vertical: str = None,
    services: List[str] = None
) -> str:
    """
    Generate a fallback operational fact when research is minimal.

    Args:
        company_name: Company name
        service_area: Service area if known
        vertical: Industry vertical (hvac/roofing)
        services: List of services if known

    Returns:
        Fallback operational fact
    """
    # Default values if not provided
    if not service_area:
        service_area = "your area"

    if not vertical:
        vertical = "contracting"
    elif vertical.lower() == "hvac":
        vertical = "HVAC"
    elif vertical.lower() == "roofing":
        vertical = "roofing"

    # Build service string
    if services and len(services) > 0:
        if len(services) == 1:
            service_str = services[0]
        elif len(services) == 2:
            service_str = f"{services[0]} and {services[1]}"
        else:
            service_str = f"{', '.join(services[:2])} and more"
    else:
        service_str = f"{vertical} services"

    # Templates for minimal data
    templates = [
        f"Noticed {{{{companyName}}}} serves {service_area} for {service_str}",
        f"Looks like {{{{companyName}}}} handles {service_str} across {service_area}",
        f"Saw that {{{{companyName}}}} provides {vertical} services in {service_area}"
    ]

    import random
    return random.choice(templates)


def combine_research_data(
    website_data: str = None,
    gbp_data: str = None,
    linkedin_data: str = None,
    crm_data_summary: str = None
) -> str:
    """
    Combine research data from multiple sources into a single string.

    Args:
        website_data: Data scraped from company website
        gbp_data: Google Business Profile data
        linkedin_data: LinkedIn profile data
        crm_data_summary: Data summary from CRM

    Returns:
        Combined research data string
    """
    sections = []

    if website_data:
        sections.append(f"WEBSITE DATA:\n{website_data}")

    if gbp_data:
        sections.append(f"GOOGLE BUSINESS PROFILE:\n{gbp_data}")

    if linkedin_data:
        sections.append(f"LINKEDIN DATA:\n{linkedin_data}")

    if crm_data_summary:
        sections.append(f"CRM SUMMARY:\n{crm_data_summary}")

    if not sections:
        return "[NO DATA AVAILABLE]"

    return "\n\n".join(sections)


def test_generator():
    """Test the operational fact generator with sample data."""

    # Sample research data combining multiple sources
    sample_research = """WEBSITE DATA:
- Services: Residential roofing, Commercial roofing, Storm damage repair, Roof inspections
- Service area: Greater Houston area including Harris County, Fort Bend County, Montgomery County
- About: Family-owned since 1998, fully licensed and insured
- Specialties: Storm restoration specialist, 24/7 emergency service

GOOGLE BUSINESS PROFILE:
- Category: Roofing contractor
- Service area: Houston, TX and surrounding areas
- Years in business: 25+ years
- Services listed: Roof repair, Roof installation, Storm damage, Emergency roofing

LINKEDIN DATA:
- Company size: 11-50 employees
- Founded: 1998
- Specialties: Commercial roofing, Residential roofing, Storm restoration"""

    print("Testing operational fact generator...")
    print("="*60)

    # Test with full data
    fact = generate_operational_fact(
        research_data=sample_research,
        company_name="Apex Roofing",
        vertical="roofing"
    )

    print(f"\nGenerated operational fact (full data):")
    print(f"  {fact}")

    # Test with minimal data
    minimal_research = """GOOGLE BUSINESS PROFILE:
- Category: HVAC contractor
- Service area: San Antonio, TX"""

    fact_minimal = generate_operational_fact(
        research_data=minimal_research,
        company_name="CoolTech HVAC",
        vertical="hvac"
    )

    print(f"\nGenerated operational fact (minimal data):")
    print(f"  {fact_minimal}")

    # Test fallback
    fallback = generate_fallback_fact(
        company_name="Test Company",
        service_area="Dallas-Fort Worth",
        vertical="roofing",
        services=["Roof Repair", "Installation"]
    )

    print(f"\nFallback operational fact:")
    print(f"  {fallback}")

    # Validation checks
    print("\nValidation:")
    for test_fact in [fact, fact_minimal, fallback]:
        if test_fact:
            has_company_var = "{{companyName}}" in test_fact
            starts_correctly = any(test_fact.startswith(o) for o in ["Noticed", "Saw that", "Looks like"])
            no_bridge = not any(phrase in test_fact.lower() for phrase in ["figured i'd reach out", "why i'm reaching out"])
            print(f"  Has {{{{companyName}}}}: {has_company_var}")
            print(f"  Starts correctly: {starts_correctly}")
            print(f"  No bridge phrases: {no_bridge}")
            print()


if __name__ == "__main__":
    test_generator()