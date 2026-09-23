"""
Discovery Manager - Gemini Multi-Account Rotation

Uses Google Gemini with multiple free accounts for maximum volume:
- 1,500 requests/day per account
- 3 accounts = 4,500/day
- 4 accounts = 6,000/day

Simple strategy: Create multiple Google accounts, get API keys, rotate through them.
"""

import os
import sys
import logging
from typing import List, Dict, Set, Optional
from dotenv import load_dotenv

# Add execution directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

logger = logging.getLogger(__name__)

# Import Gemini multi-account discovery
try:
    from gemini_discovery import GeminiMultiAccount
    GEMINI_AVAILABLE = True
except ImportError as e:
    logger.debug(f"Gemini import failed: {e}")
    GEMINI_AVAILABLE = False


class DiscoveryRotation:
    """
    Manages Gemini multi-account discovery.
    Uses multiple free accounts for maximum volume.
    """

    def __init__(self):
        self.gemini = None
        self._init_gemini()

    def _init_gemini(self):
        """Initialize Gemini multi-account discovery."""
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini module not available")
            return

        try:
            self.gemini = GeminiMultiAccount()
            status = self.gemini.get_status()
            logger.info(f"Gemini initialized: {status['total_accounts']} accounts, {status['total_capacity']} capacity")
        except ValueError as e:
            logger.warning(f"Gemini not configured: {e}")
            logger.info("To set up Gemini:")
            logger.info("  1. Get free API keys at: https://aistudio.google.com/app/apikey")
            logger.info("  2. Add to .env: GEMINI_API_KEY_1=xxx, GEMINI_API_KEY_2=xxx, etc.")

    def get_status(self) -> Dict:
        """Get status of discovery system."""
        if self.gemini:
            return self.gemini.get_status()
        return {
            'total_accounts': 0,
            'total_capacity': 0,
            'accounts': [],
            'error': 'Gemini not configured'
        }

    def get_total_capacity(self) -> int:
        """Get total remaining capacity."""
        if self.gemini:
            return self.gemini.get_total_capacity()
        return 0

    def has_capacity(self) -> bool:
        """Check if we have remaining capacity."""
        return self.get_total_capacity() > 0

    async def discover_businesses(
        self,
        industry: str,
        locations: List[str],
        max_per_location: int = 50,
        dedupe_against: Optional[Set[str]] = None
    ) -> List[Dict]:
        """
        Discover businesses using Gemini multi-account rotation.

        Args:
            industry: "HVAC" or "Roofing"
            locations: List of locations
            max_per_location: Max results per location
            dedupe_against: Set of company names to skip

        Returns:
            List of discovered businesses
        """
        if not self.gemini:
            logger.error("Gemini not configured - cannot discover businesses")
            return []

        all_businesses = []
        seen_names = dedupe_against.copy() if dedupe_against else set()

        # Batch size - 10 works reliably, 20 times out
        BATCH_SIZE = 10

        for location in locations:
            if not self.gemini.has_capacity():
                logger.warning("All Gemini accounts exhausted for today")
                break

            logger.info(f"Discovering {industry} in {location}...")

            # Make multiple requests in batches of 10
            location_businesses = []
            remaining = max_per_location
            batch_num = 0

            while remaining > 0 and self.gemini.has_capacity():
                batch_num += 1
                batch_size = min(BATCH_SIZE, remaining)

                try:
                    businesses = self.gemini.search_businesses(industry, location, batch_size)
                    logger.info(f"Batch {batch_num}: Got {len(businesses)} businesses")

                    # Dedupe within this batch
                    for biz in businesses:
                        name_key = biz['company_name'].lower().strip()
                        if name_key and name_key not in seen_names:
                            seen_names.add(name_key)
                            location_businesses.append(biz)

                    remaining -= batch_size

                except Exception as e:
                    logger.error(f"Batch {batch_num} failed: {e}")
                    break

            # Add to results
            all_businesses.extend(location_businesses)
            with_websites = sum(1 for b in location_businesses if b.get('website'))
            logger.info(f"Added {len(location_businesses)} businesses from {location} ({with_websites} with websites)")

        return all_businesses

    def discover_sync(
        self,
        industry: str,
        locations: List[str],
        max_per_location: int = 50,
        dedupe_against: Optional[Set[str]] = None
    ) -> List[Dict]:
        """Synchronous version of discover_businesses."""
        import asyncio
        return asyncio.run(self.discover_businesses(
            industry, locations, max_per_location, dedupe_against
        ))


def test_rotation():
    """Test the Gemini multi-account discovery system."""
    print("=" * 60)
    print("GEMINI MULTI-ACCOUNT DISCOVERY TEST")
    print("=" * 60)

    rotation = DiscoveryRotation()

    # Show status
    print("\nSystem Status:")
    status = rotation.get_status()

    if status.get('error'):
        print(f"  Error: {status['error']}")
        print("\n  To set up:")
        print("  1. Create free accounts at: https://aistudio.google.com/app/apikey")
        print("  2. Add to .env file:")
        print("     GEMINI_API_KEY_1=your_first_key")
        print("     GEMINI_API_KEY_2=your_second_key")
        print("     GEMINI_API_KEY_3=your_third_key")
        print("\n  Each account = 1,500 free requests/day!")
        return

    print(f"  Accounts: {status['total_accounts']}")
    print(f"  Total Capacity: {status['total_capacity']} requests")

    for acc in status['accounts']:
        status_str = "EXHAUSTED" if acc['exhausted'] else f"{acc['remaining']} remaining"
        print(f"  Account {acc['index']}: {status_str}")

    # Test discovery if we have capacity
    if rotation.get_total_capacity() > 0:
        print("\nTesting HVAC discovery in Houston, TX...")
        results = rotation.discover_sync(
            industry="HVAC",
            locations=["Houston, TX"],
            max_per_location=5
        )

        print(f"\nFound {len(results)} businesses:")
        with_websites = sum(1 for b in results if b.get('website'))
        print(f"  With websites: {with_websites} ({100*with_websites/len(results):.0f}%)" if results else "")

        for biz in results[:5]:
            print(f"\n  {biz['company_name']}")
            print(f"    Website: {biz.get('website') or 'N/A'}")
            print(f"    Phone: {biz.get('phone') or 'N/A'}")
    else:
        print("\nNo capacity available - all accounts exhausted for today.")
        print("Add more accounts or wait until tomorrow.")


if __name__ == "__main__":
    test_rotation()
