"""
Anymail Finder API Integration
Finds decision maker emails from domain/company name
"""

import os
import requests
import logging
from typing import Dict, Optional, List
from urllib.parse import urlparse
from dotenv import load_dotenv
import time

load_dotenv()

logger = logging.getLogger(__name__)

ANYMAIL_BASE_URL = "https://api.anymailfinder.com/v5.1"


class AnymailFinder:
    """
    Anymail Finder API wrapper for email discovery.
    Finds decision maker emails from company websites.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANYMAIL_FINDER_API_KEY')
        if not self.api_key:
            raise ValueError("ANYMAIL_FINDER_API_KEY not found in environment")

        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        self.calls_made = 0

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return ""

        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return url

    def get_account_info(self) -> Dict:
        """Get account info and remaining credits."""
        url = f"{ANYMAIL_BASE_URL}/account"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'API error: {response.status_code}'}
        except Exception as e:
            return {'error': str(e)}

    def search_domain(self, domain: str) -> Dict:
        """
        Search for email count at a domain (free endpoint).

        Args:
            domain: Company domain (e.g., "example.com")

        Returns:
            Dict with email_count and credits_required
        """
        if not domain:
            return {'email_count': 0, 'error': 'No domain provided'}

        domain = self._extract_domain(domain)

        url = f"{ANYMAIL_BASE_URL}/domain/{domain}/email"

        try:
            response = requests.get(url, headers=self.headers)
            self.calls_made += 1

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error("Anymail Finder: Invalid API key")
                return {'email_count': 0, 'error': 'Invalid API key'}
            elif response.status_code == 429:
                logger.warning("Anymail Finder: Rate limited, waiting...")
                time.sleep(60)
                return self.search_domain(domain)
            else:
                logger.error(f"Anymail Finder error: {response.status_code}")
                return {'email_count': 0, 'error': f'API error: {response.status_code}'}

        except Exception as e:
            logger.error(f"Anymail Finder request failed: {e}")
            return {'email_count': 0, 'error': str(e)}

    def find_email(
        self,
        domain: str,
        first_name: str = None,
        last_name: str = None
    ) -> Dict:
        """
        Find a specific person's email at a domain.

        Args:
            domain: Company domain
            first_name: Person's first name
            last_name: Person's last name

        Returns:
            Dict with email and confidence score
        """
        if not domain:
            return {'email': None, 'error': 'No domain provided'}

        domain = self._extract_domain(domain)

        url = f"{ANYMAIL_BASE_URL}/search/person.json"

        payload = {"domain": domain}
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            self.calls_made += 1

            if response.status_code == 200:
                return response.json()
            else:
                return {'email': None, 'error': f'API error: {response.status_code}'}

        except Exception as e:
            return {'email': None, 'error': str(e)}

    def find_decision_maker(
        self,
        website: str,
        company_name: str = None
    ) -> Dict:
        """
        Find the decision maker (owner/CEO) email for a company.

        Args:
            website: Company website URL
            company_name: Company name (fallback if no website)

        Returns:
            Dict with decision_maker info:
            - email: The email address
            - name: Person's name (if found)
            - title: Their role (if found)
            - status: Email status (valid/risky/not_found)
        """
        domain = self._extract_domain(website)

        if not domain and not company_name:
            return {
                'email': None,
                'name': None,
                'title': None,
                'status': 'error',
                'error': 'No valid domain or company name'
            }

        url = f"{ANYMAIL_BASE_URL}/find-email/decision-maker"

        # Build payload - use domain if available, otherwise company_name
        payload = {
            "decision_maker_category": ["ceo"]  # Target owners/CEOs
        }

        if domain:
            payload["domain"] = domain
        elif company_name:
            payload["company_name"] = company_name

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=180  # Recommended timeout for this endpoint
            )
            self.calls_made += 1

            if response.status_code == 200:
                data = response.json()
                return {
                    'email': data.get('email') or data.get('valid_email'),
                    'name': data.get('person_full_name'),
                    'title': data.get('person_job_title'),
                    'linkedin': data.get('person_linkedin_url'),
                    'status': data.get('email_status', 'unknown')
                }
            elif response.status_code == 401:
                logger.error("Anymail Finder: Invalid API key")
                return {'email': None, 'status': 'error', 'error': 'Invalid API key'}
            elif response.status_code == 429:
                logger.warning("Anymail Finder: Rate limited")
                return {'email': None, 'status': 'error', 'error': 'Rate limited'}
            else:
                logger.error(f"Anymail Finder error: {response.status_code}")
                return {'email': None, 'status': 'error', 'error': f'API error: {response.status_code}'}

        except requests.exceptions.Timeout:
            logger.warning("Anymail Finder: Request timed out")
            return {'email': None, 'status': 'error', 'error': 'Timeout'}
        except Exception as e:
            logger.error(f"Anymail Finder request failed: {e}")
            return {'email': None, 'status': 'error', 'error': str(e)}

    def enrich_businesses(
        self,
        businesses: List[Dict],
        batch_delay: float = 1.0
    ) -> List[Dict]:
        """
        Enrich a list of businesses with email addresses.

        Args:
            businesses: List of business dicts (must have 'website' key)
            batch_delay: Delay between API calls (seconds)

        Returns:
            Same list with added email fields
        """
        enriched = []

        for i, biz in enumerate(businesses):
            website = biz.get('website', '')
            company_name = biz.get('company_name', '')

            if website or company_name:
                result = self.find_decision_maker(website, company_name)

                biz['email'] = result.get('email')
                biz['decision_maker_name'] = result.get('name')
                biz['decision_maker_title'] = result.get('title')
                biz['decision_maker_linkedin'] = result.get('linkedin')
                biz['email_status'] = result.get('status', 'unknown')

                if result.get('error'):
                    biz['email_error'] = result['error']
            else:
                biz['email'] = None
                biz['email_error'] = 'No website or company name'

            enriched.append(biz)

            # Rate limiting
            if batch_delay and i < len(businesses) - 1:
                time.sleep(batch_delay)

            # Progress logging
            if (i + 1) % 10 == 0:
                logger.info(f"Enriched {i + 1}/{len(businesses)} businesses")

        return enriched


def test_anymail_finder():
    """Test the Anymail Finder integration."""
    print("=" * 60)
    print("ANYMAIL FINDER TEST")
    print("=" * 60)

    try:
        finder = AnymailFinder()
        print("Anymail Finder initialized successfully!")

        # Test domain search
        print("\nTesting domain search for 'example.com'...")
        result = finder.search_domain("example.com")
        print(f"Result: {result}")

        # Test decision maker finder
        print("\nTesting decision maker finder...")
        result = finder.find_decision_maker("https://www.acme-hvac.com")
        print(f"Decision maker: {result}")

        print(f"\nTotal API calls made: {finder.calls_made}")

    except ValueError as e:
        print(f"\nError: {e}")
        print("Please add ANYMAIL_FINDER_API_KEY to your .env file")

    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    test_anymail_finder()
