"""
Unified Personalization Engine
Routes between Claude and GPT-4o (fallback).

The engine key "haiku" is historical and kept so callers, PERSONALIZATION_ENGINE
values and stats keys don't break: since 2026-09-25 it runs Claude Opus 5.5
(operational_fact_pain_generator_haiku.py), because every model call runs on
Opus 5.5.

This module provides a single interface for generating personalizations with:
- Primary ("haiku" key): Claude Opus 5.5, low effort (~$0.025/personalization,
  rough estimate, not measured)
- Fallback: OpenAI GPT-4o (~$0.002/personalization)
- Ultimate fallback: Template-based (free, always works)

Usage:
    from unified_personalization_engine import generate_personalization

    result = generate_personalization(
        research_data="Company serves Houston metro...",
        company_name="ABC Roofing",
        vertical="roofing",
        engine="both"  # or "haiku" or "gpt4o"
    )

    print(result['personalization'])
    print(result['engine_used'])  # 'haiku', 'gpt4o', or 'fallback'
    print(result['cost_estimate'])  # Cost in dollars
"""

import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Import both generators
try:
    from operational_fact_pain_generator_haiku import (
        generate_operational_fact_pain as generate_haiku,
        get_fallback_personalization
    )
    HAIKU_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Claude generator not available: {e}")
    HAIKU_AVAILABLE = False

try:
    from operational_fact_pain_generator import (
        generate_operational_fact_pain as generate_gpt4o
    )
    GPT4O_AVAILABLE = True
except ImportError as e:
    logger.warning(f"GPT-4o generator not available: {e}")
    GPT4O_AVAILABLE = False

# Cost per personalization (in dollars)
COSTS = {
    'haiku': 0.025,   # Claude Opus 5.5 at low effort (key kept; rough estimate)
    'gpt4o': 0.002,   # GPT-4o
    'fallback': 0.0   # Template-based
}


def generate_personalization(
    research_data: str,
    company_name: str,
    vertical: str = None,
    engine: str = None
) -> Dict:
    """
    Generate personalization using intelligent routing between engines.

    Args:
        research_data: Combined research from website/GBP/LinkedIn
        company_name: Company name (will be templated as {{companyName}})
        vertical: Optional vertical (hvac/roofing)
        engine: Engine selection ('haiku', 'gpt4o', 'both', or None for env default)

    Returns:
        Dict with:
            - personalization: str (the generated text)
            - engine_used: str ('haiku', 'gpt4o', or 'fallback')
            - cost_estimate: float (cost in dollars)
            - success: bool
            - error: str (if any)
    """

    # Get engine preference from env if not specified
    if engine is None:
        engine = os.getenv('PERSONALIZATION_ENGINE', 'both')

    result = {
        'personalization': None,
        'engine_used': None,
        'cost_estimate': 0.0,
        'success': False,
        'error': None
    }

    # Route based on engine preference
    if engine in ['haiku', 'both']:
        if not HAIKU_AVAILABLE:
            logger.warning("Claude requested but not available, falling back")
            if engine == 'haiku':
                result['error'] = "Claude generator not available"
                return _try_fallback(result, company_name, vertical)
        else:
            # Try Claude first
            logger.info(f"Generating with Claude Opus 5.5 for {company_name}")
            try:
                personalization = generate_haiku(
                    research_data=research_data,
                    company_name=company_name,
                    vertical=vertical
                )

                if personalization:
                    result['personalization'] = personalization
                    result['engine_used'] = 'haiku'
                    result['cost_estimate'] = COSTS['haiku']
                    result['success'] = True
                    logger.info(f"✓ Claude success for {company_name} (${COSTS['haiku']:.4f})")
                    return result
                else:
                    logger.warning(f"Claude returned empty result for {company_name}")

            except Exception as e:
                logger.error(f"Claude error for {company_name}: {str(e)}")
                result['error'] = f"Claude error: {str(e)}"

    # If Claude failed or not requested, try GPT-4o
    if engine in ['gpt4o', 'both']:
        if not GPT4O_AVAILABLE:
            logger.warning("GPT-4o requested but not available")
            if engine == 'gpt4o':
                result['error'] = "GPT-4o generator not available"
                return _try_fallback(result, company_name, vertical)
        else:
            logger.info(f"Generating with GPT-4o for {company_name}")
            try:
                personalization = generate_gpt4o(
                    research_data=research_data,
                    company_name=company_name,
                    vertical=vertical
                )

                if personalization:
                    result['personalization'] = personalization
                    result['engine_used'] = 'gpt4o'
                    result['cost_estimate'] = COSTS['gpt4o']
                    result['success'] = True
                    logger.info(f"✓ GPT-4o success for {company_name} (${COSTS['gpt4o']:.4f})")
                    return result
                else:
                    logger.warning(f"GPT-4o returned empty result for {company_name}")

            except Exception as e:
                logger.error(f"GPT-4o error for {company_name}: {str(e)}")
                result['error'] = f"GPT-4o error: {str(e)}"

    # Both failed, use template fallback
    return _try_fallback(result, company_name, vertical)


def _try_fallback(result: Dict, company_name: str, vertical: str) -> Dict:
    """
    Use template-based fallback when all AI engines fail.
    """
    logger.warning(f"All AI engines failed for {company_name}, using template fallback")

    try:
        fallback = get_fallback_personalization(vertical)
        result['personalization'] = fallback
        result['engine_used'] = 'fallback'
        result['cost_estimate'] = COSTS['fallback']
        result['success'] = True
        logger.info(f"✓ Fallback success for {company_name}")
    except Exception as e:
        logger.error(f"Even fallback failed for {company_name}: {str(e)}")
        result['error'] = f"All engines failed including fallback: {str(e)}"
        result['success'] = False

    return result


def estimate_batch_cost(
    num_leads: int,
    engine: str = None,
    success_rate: float = 0.95
) -> Dict:
    """
    Estimate cost for a batch of personalizations.

    Args:
        num_leads: Number of leads to process
        engine: Engine to use ('haiku', 'gpt4o', 'both')
        success_rate: Expected success rate (default 95%)

    Returns:
        Dict with cost breakdown
    """
    if engine is None:
        engine = os.getenv('PERSONALIZATION_ENGINE', 'both')

    estimate = {
        'num_leads': num_leads,
        'engine': engine,
        'success_rate': success_rate
    }

    if engine == 'haiku':
        # All leads use Claude (Opus 5.5, "haiku" key)
        estimate['haiku_count'] = int(num_leads * success_rate)
        estimate['fallback_count'] = num_leads - estimate['haiku_count']
        estimate['gpt4o_count'] = 0
        estimate['total_cost'] = (
            estimate['haiku_count'] * COSTS['haiku']
        )

    elif engine == 'gpt4o':
        # All leads use GPT-4o
        estimate['gpt4o_count'] = int(num_leads * success_rate)
        estimate['fallback_count'] = num_leads - estimate['gpt4o_count']
        estimate['haiku_count'] = 0
        estimate['total_cost'] = (
            estimate['gpt4o_count'] * COSTS['gpt4o']
        )

    else:  # 'both'
        # Claude first, GPT-4o fallback
        # Assume 95% Claude success, 5% fall to GPT-4o, 0.25% to template
        estimate['haiku_count'] = int(num_leads * 0.95)
        estimate['gpt4o_count'] = int(num_leads * 0.048)  # 95% of the 5% failures
        estimate['fallback_count'] = num_leads - estimate['haiku_count'] - estimate['gpt4o_count']
        estimate['total_cost'] = (
            estimate['haiku_count'] * COSTS['haiku'] +
            estimate['gpt4o_count'] * COSTS['gpt4o']
        )

    estimate['cost_per_lead'] = estimate['total_cost'] / num_leads if num_leads > 0 else 0
    estimate['cost_formatted'] = f"${estimate['total_cost']:.2f}"

    return estimate


def print_cost_comparison(num_leads: int = 1000):
    """
    Print a cost comparison table for different engines.
    """
    print(f"\n{'='*70}")
    print(f"Cost Comparison for {num_leads:,} Personalizations")
    print(f"{'='*70}")
    print(f"{'Engine':<20} {'Total Cost':<15} {'Per Lead':<15} {'Savings':<15}")
    print(f"{'-'*70}")

    engines = ['gpt4o', 'haiku', 'both']
    baseline_cost = None

    for engine in engines:
        estimate = estimate_batch_cost(num_leads, engine)
        cost = estimate['total_cost']
        per_lead = estimate['cost_per_lead']

        if engine == 'gpt4o':
            baseline_cost = cost
            savings = "baseline"
        else:
            savings_pct = ((baseline_cost - cost) / baseline_cost) * 100 if baseline_cost else 0
            savings = f"{savings_pct:.1f}%"

        print(f"{engine:<20} ${cost:<14.2f} ${per_lead:<14.4f} {savings:<15}")

    print(f"{'='*70}\n")


if __name__ == "__main__":
    # Test the unified engine
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--cost-comparison':
        # Show cost comparison
        num_leads = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
        print_cost_comparison(num_leads)
        sys.exit(0)

    # Test generation
    sample_research = """
    Company website shows they offer 24/7 emergency AC repair services.
    Service area includes Houston, Katy, Sugar Land, The Woodlands, and surrounding areas.
    Google Business Profile shows they've been in business since 2008.
    They advertise free estimates and same-day service on their homepage.
    Multiple crews serving the greater Houston metro area.
    """

    print("Testing Unified Personalization Engine")
    print("=" * 60)

    for engine in ['haiku', 'gpt4o', 'both']:
        print(f"\nTesting with engine='{engine}':")
        print("-" * 60)

        result = generate_personalization(
            research_data=sample_research,
            company_name="Test Company",
            vertical="hvac",
            engine=engine
        )

        if result['success']:
            print(f"✓ Success!")
            print(f"  Engine used: {result['engine_used']}")
            print(f"  Cost: ${result['cost_estimate']:.4f}")
            print(f"  Output: {result['personalization'][:100]}...")
        else:
            print(f"✗ Failed: {result['error']}")

    # Print cost comparison
    print_cost_comparison(1000)
