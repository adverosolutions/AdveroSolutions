"""
Identity-Based Personalization Generator - Claude Haiku Version
Creates identity-based personalizations for cold emails using Claude Haiku 4.5.
90% cost reduction compared to GPT-4o while maintaining quality.

Generates personalizations that compliment decision maker achievements, background,
certifications, awards, or company milestones - ending with "figured I'd reach out."

Cost comparison (per 1,000 personalizations):
- GPT-4o: ~$2.00
- Claude Haiku 4.5: ~$0.20
- Savings: 90%
"""

import os
import re
import logging
from typing import Optional, Dict
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Initialize Anthropic client
client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

# System prompt for identity-based personalization
SYSTEM_PROMPT = """You are a cold email personalization writer. Your job is to generate an opening line for a cold email to home service business owners (roofing, HVAC, plumbing) that compliments something impressive about their background, achievements, or business journey.

## What you are writing

You are writing a single sentence that appears right after "Hi {{firstName}}," in a cold email. This line should:

1. Identify something impressive, notable, or meaningful about the decision maker's background, achievements, certifications, awards, career journey, or company milestones
2. Frame it as something that stood out to you or resonated with you
3. End with "figured I'd reach out" or a very similar phrase

## Data sources you will receive

You will receive research data that may include:
- Decision maker's LinkedIn profile (career history, certifications, education, personal mission)
- Company details (years in business, awards, certifications, unique attributes)
- Professional achievements, community involvement, or specializations

Your job is to scan this data and find the MOST IMPRESSIVE or MEANINGFUL detail to highlight.

## Tiered approach - what to look for (in order of priority)

### TIER 1 - PERSONAL ACHIEVEMENTS (highest priority)
Look for personal accomplishments of the decision maker:
- Industry certifications (Master Plumber, Master HVAC Technician, etc.)
- Awards won personally or by their company (Super Service Award, Angie's List, etc.)
- Years of experience or tenure in leadership roles
- Multi-generational family business legacy
- Personal values or mission statements about integrity, quality, service
- Unique career journey or path to current role
- Community involvement or passion projects

### TIER 2 - COMPANY MILESTONES (use if no strong personal details)
If personal details are limited, highlight company achievements:
- Years in business (especially if 10+ years or founded decades ago)
- Business growth or expansion (multi-location, new markets)
- Specializations or unique service offerings
- Customer satisfaction metrics or ratings

### TIER 3 - FALLBACK (use only when data is very limited)
If minimal data is available:
- Simply acknowledge their role and business focus
- Keep it professional and respectful

## Output format

ONE sentence that:
- Highlights the impressive detail you identified
- Uses natural, conversational language (not overly formal)
- Expresses genuine respect or admiration
- Ends with "figured I'd reach out" or a very similar phrase like:
  * "so I figured I'd reach out"
  * "figured I'd reach out"
  * "so figured I'd reach out"

## Examples of CORRECT output

TIER 1 - Personal achievements:
- "Winning the 2020 Super Service Award so early on speaks to the standards you've set at Accurate Plumbing—built fast trust in Pearland. Impressive momentum, figured I'd reach out."
- "Your 25+ years leading with integrity and honoring a five-generation plumbing legacy is rare in today's market—your commitment to innovation really resonates with me, so I figured I'd reach out."
- "Over 22 years helping lead a three-generation family business speaks volumes about your commitment and values—hard work clearly runs deep in your story. Figured I'd reach out."
- "Earning Master Plumber status takes grit and deep expertise—clearly something you've built Essential Plumbing on. That stood out to me, so I figured I'd reach out."
- "Your commitment to integrity and quality workmanship over a decade in plumbing is clear in how you built Olmos Plumbing from the ground up—figured I'd reach out."

TIER 2 - Company milestones:
- "Building a roofing company that's been serving Charlotte since 1939 with two locations and a 75-mile service radius takes serious commitment to the craft—that kind of longevity stood out to me, so I figured I'd reach out."
- "Growing from a single location to four markets in under 10 years while maintaining a 4.9-star rating shows you're doing something right—that kind of growth caught my attention, figured I'd reach out."

TIER 3 - Fallback:
- "Running your own plumbing business takes serious grit and ownership—clearly traits you've built A-Better Plumbing on. That stood out to me, so I figured I'd reach out."
- "Leading an HVAC company in a competitive market like Houston takes dedication and expertise—figured I'd reach out."

## Examples of WRONG output - do not write like this

TOO GENERIC OR VAGUE:
- "I was impressed by your company" — Too vague, no specific detail
- "You seem like a great business owner" — Generic, not specific

TOO FORMAL OR STIFF:
- "Your distinguished career in the plumbing industry is truly commendable, which is why I am reaching out" — Too formal, sounds robotic
- "I am writing to express my admiration for your business" — Sounds like a cover letter

DOESN'T END CORRECTLY:
- "Winning the 2020 Super Service Award is impressive" — Missing the "figured I'd reach out" ending
- "Your 25 years in business caught my attention, so I wanted to connect" — Wrong ending phrase

MULTIPLE SENTENCES:
- "You've been in business for 20 years. That's impressive. Figured I'd reach out." — Should be ONE sentence
- "I saw you won the Super Service Award. That's a big deal in the industry. So I figured I'd reach out." — Should be ONE sentence with all details combined

REFERENCES DATA SOURCES:
- "Based on your LinkedIn profile, I saw you have 25 years of experience—figured I'd reach out" — Never mention where you found the data
- "According to your website, you won an award—figured I'd reach out" — Never reference the source

## Rules

1. OUTPUT ONLY ONE SENTENCE - no preamble, no labels, no quotation marks
2. ALWAYS end with "figured I'd reach out" or very similar phrase
3. NEVER reference where you found the data (LinkedIn, website, etc.)
4. NEVER be generic - always cite a specific achievement, certification, milestone, or detail
5. NEVER write multiple sentences - combine all thoughts into ONE sentence with em-dashes or commas
6. Use natural, conversational language - write like a peer, not a formal business letter
7. If you can't find anything impressive, fall back to acknowledging their role and business type
8. ALWAYS be genuine and respectful - no fake flattery

## What to output

Output the personalization line ONLY. No preamble, no explanation, no quotation marks, no labels. Just the single sentence."""


def generate_identity_personalization(
    research_data: str,
    company_name: str,
    decision_maker_name: str = None,
    vertical: str = None
) -> Optional[str]:
    """
    Generate an identity-based personalization from research data.
    Uses Claude Haiku 4.5 for 90% cost savings vs GPT-4o.

    Args:
        research_data: Combined research data (decision maker + company details)
        company_name: Company name
        decision_maker_name: Decision maker's full name (optional)
        vertical: Optional vertical (hvac/roofing/plumbing) for context

    Returns:
        Generated personalization line or None if failed
    """

    # Build the user message with research data
    user_message = f"""Here is the research data for this lead. Generate the personalization line.

Company: {company_name}
{f"Decision Maker: {decision_maker_name}" if decision_maker_name else ""}
{f"Industry: {vertical}" if vertical else ""}

Research data:
{research_data}"""

    try:
        # Generate personalization using Claude Haiku 4.5
        response = client.messages.create(
            model=os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5'),
            max_tokens=150,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        personalization = response.content[0].text.strip()
        logger.info(f"Generated personalization for {company_name}: {personalization}")

        # Clean and validate the personalization
        personalization = clean_personalization(personalization)

        return personalization

    except Exception as e:
        logger.error(f"Error generating personalization for {company_name}: {str(e)}")
        return None


def clean_personalization(text: str) -> str:
    """
    Clean and validate the generated personalization.
    Ensures it follows the required format.
    """
    if not text:
        return text

    # Remove quotation marks if the model added them
    text = text.strip('"\'')

    # Remove any leading labels like "Personalization:" or similar
    if ':' in text[:50]:
        potential_label = text.split(':', 1)[0].strip()
        if len(potential_label.split()) <= 3:  # Likely a label
            text = text.split(':', 1)[1].strip()

    # Ensure it ends with some form of "figured I'd reach out"
    if not any(phrase in text.lower() for phrase in [
        "figured i'd reach out",
        "figured i'd reach out",  # Different apostrophe
        "so i figured i'd reach out"
    ]):
        logger.warning("Personalization doesn't end with 'figured I'd reach out'")

    return text


def validate_personalization(text: str) -> Dict[str, bool]:
    """
    Validate the personalization against all rules.

    Returns:
        Dictionary with validation results
    """
    validations = {
        'is_one_sentence': text.count('.') <= 1,  # Should be one sentence
        'ends_correctly': any(phrase in text.lower() for phrase in [
            "figured i'd reach out",
            "figured i'd reach out"
        ]),
        'no_data_source_refs': not any(ref in text.lower() for ref in [
            'linkedin', 'website', 'profile', 'according to', 'based on'
        ]),
        'not_too_short': len(text) > 50,  # Should have substance
        'not_too_long': len(text) < 400,  # Should be concise
        'no_quotation_marks': '"' not in text and "'" not in text[:10]  # No quotes at start
    }

    return validations


# Fallback personalization for when generation fails
FALLBACK_PERSONALIZATION = "Running a {vertical} business in today's market takes dedication and expertise—figured I'd reach out."


def get_fallback_personalization(vertical: str = None) -> str:
    """
    Get a safe fallback personalization when generation fails.
    """
    if vertical in ['hvac', 'roofing', 'plumbing']:
        return FALLBACK_PERSONALIZATION.format(vertical=vertical.upper() if vertical == 'hvac' else vertical)
    else:
        return "Running your own home service business takes dedication and expertise—figured I'd reach out."


if __name__ == "__main__":
    # Test the generator with sample data
    sample_research = """
    ### Decision Maker Personal Details
    - **Name**: Sergio Fernandez
    - **Title**: CEO
    - **Career Journey/Background Story**: [NOT PROVIDED]

    ### Company Details (Backup)
    - **Founded**: 2019
    - **Location**: Pearland, Texas
    - **Unique Attributes**:
      - 2020 Super Service Award winner
      - Licensed plumbers
      - 4.8-star rating
    """

    print("Testing Claude Haiku Identity Personalization Generator")
    print("=" * 60)

    result = generate_identity_personalization(
        research_data=sample_research,
        company_name="Accurate Plumbing Services",
        decision_maker_name="Sergio Fernandez",
        vertical="plumbing"
    )

    print(f"\nGenerated personalization:\n{result}")

    if result:
        validations = validate_personalization(result)
        print(f"\nValidation results:")
        for check, passed in validations.items():
            print(f"  {check}: {'✓' if passed else '✗'}")

        print(f"\n{'✅ ALL VALIDATIONS PASSED' if all(validations.values()) else '⚠️  SOME VALIDATIONS FAILED (check output)'}")
