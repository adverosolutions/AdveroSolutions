"""
Google Gemini Multi-Account Business Discovery
Free tier: 1,500 requests/day PER ACCOUNT
Supports multiple accounts for 4,500-6,000+ daily capacity

Strategy: Create multiple free Gemini accounts, rotate through them
"""

import os
import requests
import logging
import json
import re
from typing import List, Dict, Optional
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Daily limit per account (conservative - actual is 1,500)
DAILY_LIMIT_PER_ACCOUNT = 1400


class GeminiMultiAccount:
    """
    Multi-account Gemini API manager for business discovery.
    Rotates through multiple free accounts for maximum volume.

    Free tier per account: 1,500 requests/day
    With 3 accounts: 4,500/day
    With 4 accounts: 6,000/day
    """

    def __init__(self, api_keys: List[str] = None):
        """
        Initialize with multiple API keys.

        Keys can be provided directly or via environment:
        - GEMINI_API_KEY (single key)
        - GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc. (multiple)
        """
        self.api_keys = api_keys or self._load_keys_from_env()

        if not self.api_keys:
            raise ValueError(
                "No Gemini API keys found. Set GEMINI_API_KEY or "
                "GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc. in .env"
            )

        self.usage_file = ".tmp/gemini_multi_usage.json"
        self.usage = {}  # {key_index: calls_today}
        self.last_reset = date.today()

        self._load_usage()

        logger.info(f"Gemini initialized with {len(self.api_keys)} accounts")
        logger.info(f"Total daily capacity: {self.get_total_capacity()}")

    def _load_keys_from_env(self) -> List[str]:
        """Load API keys from environment variables."""
        keys = []

        # Try numbered keys first (GEMINI_API_KEY_1, _2, etc.)
        for i in range(1, 20):  # Support up to 20 accounts
            key = os.getenv(f'GEMINI_API_KEY_{i}')
            if key:
                keys.append(key)

        # Fallback to single key
        if not keys:
            single_key = os.getenv('GEMINI_API_KEY')
            if single_key:
                keys.append(single_key)

        return keys

    def _load_usage(self):
        """Load usage tracking from file."""
        try:
            if os.path.exists(self.usage_file):
                with open(self.usage_file, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == str(date.today()):
                        self.usage = {int(k): v for k, v in data.get('usage', {}).items()}
                        self.last_reset = date.today()
                    else:
                        # New day, reset usage
                        self.usage = {}
            else:
                self.usage = {}
        except Exception as e:
            logger.warning(f"Failed to load usage: {e}")
            self.usage = {}

    def _save_usage(self):
        """Save usage tracking to file."""
        try:
            os.makedirs(os.path.dirname(self.usage_file), exist_ok=True)
            with open(self.usage_file, 'w') as f:
                json.dump({
                    'date': str(date.today()),
                    'usage': self.usage
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save usage: {e}")

    def _reset_if_new_day(self):
        """Reset usage counters if it's a new day."""
        if date.today() > self.last_reset:
            self.usage = {}
            self.last_reset = date.today()
            logger.info("New day - usage counters reset")

    def get_available_key(self) -> Optional[tuple]:
        """
        Get the next available API key with capacity.

        Returns:
            Tuple of (key_index, api_key) or (None, None) if exhausted
        """
        self._reset_if_new_day()

        for i, key in enumerate(self.api_keys):
            calls = self.usage.get(i, 0)
            if calls < DAILY_LIMIT_PER_ACCOUNT:
                return i, key

        return None, None

    def get_total_capacity(self) -> int:
        """Get total remaining capacity across all accounts."""
        self._reset_if_new_day()

        total = 0
        for i in range(len(self.api_keys)):
            calls = self.usage.get(i, 0)
            total += max(0, DAILY_LIMIT_PER_ACCOUNT - calls)
        return total

    def get_status(self) -> Dict:
        """Get detailed status of all accounts."""
        self._reset_if_new_day()

        status = {
            'total_accounts': len(self.api_keys),
            'total_capacity': self.get_total_capacity(),
            'accounts': []
        }

        for i in range(len(self.api_keys)):
            calls = self.usage.get(i, 0)
            remaining = max(0, DAILY_LIMIT_PER_ACCOUNT - calls)
            status['accounts'].append({
                'index': i + 1,
                'calls_today': calls,
                'remaining': remaining,
                'exhausted': remaining == 0
            })

        return status

    def has_capacity(self) -> bool:
        """Check if any account has remaining capacity."""
        return self.get_total_capacity() > 0

    def get_remaining(self) -> int:
        """Get total remaining calls across all accounts."""
        return self.get_total_capacity()

    def search_businesses(
        self,
        industry: str,
        location: str,
        count: int = 10
    ) -> List[Dict]:
        """
        Search for businesses using Gemini with Google Search grounding.
        Automatically rotates to next account when current is exhausted.

        Args:
            industry: Industry type (e.g., "HVAC", "Roofing")
            location: Location (e.g., "Houston, TX")
            count: Number of businesses to find

        Returns:
            List of business dicts
        """
        key_index, api_key = self.get_available_key()

        if api_key is None:
            logger.warning("All Gemini accounts exhausted for today")
            return []

        prompt = f"""Search Google for {count} {industry} contractors/companies in {location}.

For each business, find their:
- Company name
- Full address
- Phone number
- Website URL (very important - search for this)
- Google rating and review count

Return ONLY a JSON array with these exact fields:
- company_name: Business name
- address: Full address
- city: City
- state: State code
- phone: Phone number
- website: Website URL
- rating: Rating out of 5
- review_count: Number of reviews

Return ONLY valid JSON, no markdown, no explanation. Example:
[{{"company_name": "Example Co", "address": "123 St", "city": "Houston", "state": "TX", "phone": "555-1234", "website": "https://example.com", "rating": 4.5, "review_count": 50}}]"""

        url = f"{GEMINI_API_URL}?key={api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096
            },
            "tools": [
                {
                    "google_search": {}
                }
            ]
        }

        try:
            response = requests.post(url, json=payload, timeout=120)

            # Track usage
            self.usage[key_index] = self.usage.get(key_index, 0) + 1
            self._save_usage()

            if response.status_code == 200:
                data = response.json()
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts:
                        text = parts[0].get('text', '')
                        return self._parse_response(text, industry)
                return []

            elif response.status_code == 401 or response.status_code == 403:
                logger.error(f"Gemini account {key_index + 1}: Invalid API key")
                # Mark this account as exhausted so we try next one
                self.usage[key_index] = DAILY_LIMIT_PER_ACCOUNT
                self._save_usage()
                # Try next account
                return self.search_businesses(industry, location, count)

            elif response.status_code == 429:
                logger.warning(f"Gemini account {key_index + 1}: Rate limited")
                # Mark as exhausted and try next account
                self.usage[key_index] = DAILY_LIMIT_PER_ACCOUNT
                self._save_usage()
                return self.search_businesses(industry, location, count)

            else:
                logger.error(f"Gemini error: {response.status_code} - {response.text[:200]}")
                return []

        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            return []

    def _parse_response(self, content: str, industry: str) -> List[Dict]:
        """Parse Gemini response into business list."""
        businesses = []

        try:
            # Clean up the response - remove markdown code blocks
            content = content.strip()
            # Remove all markdown code block markers
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()

            # Try to extract JSON array
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                json_str = json_match.group()
                raw_businesses = json.loads(json_str)

                for biz in raw_businesses:
                    if isinstance(biz, dict) and biz.get('company_name'):
                        businesses.append({
                            'company_name': biz.get('company_name', ''),
                            'address': biz.get('address', ''),
                            'city': biz.get('city', ''),
                            'state': biz.get('state', ''),
                            'phone': str(biz.get('phone', '')),
                            'website': biz.get('website', ''),
                            'google_rating': biz.get('rating', 0),
                            'review_count': biz.get('review_count', 0),
                            'category': industry,
                            'source': 'gemini',
                            'discovered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Gemini response: {e}")
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")

        return businesses

    def discover_hvac(self, location: str, max_results: int = 20) -> List[Dict]:
        """Discover HVAC businesses."""
        return self.search_businesses("HVAC", location, max_results)

    def discover_roofing(self, location: str, max_results: int = 20) -> List[Dict]:
        """Discover Roofing businesses."""
        return self.search_businesses("Roofing", location, max_results)


# Alias for backwards compatibility
GeminiDiscovery = GeminiMultiAccount


def test_gemini_discovery():
    """Test Gemini Multi-Account Discovery."""
    print("=" * 60)
    print("GEMINI MULTI-ACCOUNT DISCOVERY TEST")
    print("=" * 60)

    try:
        gemini = GeminiMultiAccount()

        # Show status
        status = gemini.get_status()
        print(f"\nAccounts configured: {status['total_accounts']}")
        print(f"Total daily capacity: {status['total_capacity']}")
        print("\nAccount Status:")
        for acc in status['accounts']:
            status_str = "EXHAUSTED" if acc['exhausted'] else f"{acc['remaining']} remaining"
            print(f"  Account {acc['index']}: {acc['calls_today']} calls today ({status_str})")

        if not gemini.has_capacity():
            print("\nNo capacity available. Try again tomorrow or add more accounts.")
            return

        # Test search
        print("\nSearching for HVAC in Houston, TX...")
        results = gemini.discover_hvac("Houston, TX", max_results=5)

        print(f"\nFound {len(results)} businesses:")
        for biz in results:
            print(f"  - {biz['company_name']}")
            print(f"    Website: {biz['website'] or 'N/A'}")
            print(f"    Phone: {biz['phone'] or 'N/A'}")
            if biz.get('google_rating'):
                print(f"    Rating: {biz['google_rating']} ({biz['review_count']} reviews)")
            print()

        # Show updated status
        print("\nUpdated Status:")
        status = gemini.get_status()
        print(f"Remaining capacity: {status['total_capacity']}")

    except ValueError as e:
        print(f"\nError: {e}")
        print("\nTo set up multiple accounts:")
        print("1. Create free accounts at: https://aistudio.google.com/app/apikey")
        print("2. Add to .env file:")
        print("   GEMINI_API_KEY_1=your_first_key")
        print("   GEMINI_API_KEY_2=your_second_key")
        print("   GEMINI_API_KEY_3=your_third_key")
        print("\nEach account gives you 1,500 free requests/day!")


if __name__ == "__main__":
    test_gemini_discovery()
