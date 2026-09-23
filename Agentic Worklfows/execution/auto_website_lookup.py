"""
Automated Website Lookup for Leads
===================================

This script automatically looks up websites for companies using:
1. Google Search (via SerpAPI or direct scraping)
2. Company name + phone number + location

It validates results and flags suspicious matches for manual review.

Usage:
    python auto_website_lookup.py --input clean_landscaping_for_website_lookup_20260401_125532.csv --output verified_websites.csv
    python auto_website_lookup.py --input clean_landscaping_for_website_lookup_20260401_125532.csv --test 10  # Test on first 10 rows
"""

import os
import sys
import csv
import argparse
import time
import re
from typing import Dict, List, Optional
from datetime import datetime
import requests
from urllib.parse import urlparse, quote_plus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv('../.env')


class WebsiteLookup:
    """Automated website lookup using Google Search."""

    def __init__(self, use_serp_api=False):
        self.use_serp_api = use_serp_api
        self.serp_api_key = os.getenv('SERP_API_KEY')
        self.requests_made = 0
        self.successful_lookups = 0
        self.failed_lookups = 0

    def search_google(self, company_name: str, phone: str, city: str, state: str) -> Optional[str]:
        """
        Search Google for company website.

        Returns:
            Website URL if found, None otherwise
        """
        # Build search query
        query = f'"{company_name}" "{phone}" {city} {state} website'

        if self.use_serp_api and self.serp_api_key:
            return self._search_via_serp_api(query)
        else:
            return self._search_via_scraping(query, company_name, phone)

    def _search_via_serp_api(self, query: str) -> Optional[str]:
        """Search using SerpAPI (paid service, more reliable)."""
        try:
            url = "https://serpapi.com/search"
            params = {
                "q": query,
                "api_key": self.serp_api_key,
                "num": 5
            }

            response = requests.get(url, params=params, timeout=10)
            self.requests_made += 1

            if response.status_code == 200:
                data = response.json()

                # Extract first organic result with a valid URL
                organic_results = data.get('organic_results', [])
                for result in organic_results:
                    link = result.get('link', '')
                    if link and self._is_valid_url(link):
                        return link

            return None

        except Exception as e:
            print(f"    SerpAPI error: {e}")
            return None

    def _search_via_scraping(self, query: str, company_name: str, phone: str) -> Optional[str]:
        """
        Search using direct Google scraping (free, but may be rate limited).
        """
        try:
            # Clean phone for search
            clean_phone = re.sub(r'[^\d]', '', phone)

            # Build Google search URL
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(search_url, headers=headers, timeout=10)
            self.requests_made += 1

            if response.status_code != 200:
                return None

            # Extract URLs from search results (basic regex)
            # This is a simple approach - Google's HTML structure changes frequently
            urls = re.findall(r'https?://[^\s<>"]+', response.text)

            # Filter to likely company websites
            candidates = []
            for url in urls:
                # Skip Google's own URLs and common non-company domains
                if any(skip in url.lower() for skip in ['google.com', 'youtube.com', 'facebook.com', 'yelp.com', 'yellowpages.com']):
                    continue

                if self._is_valid_url(url):
                    candidates.append(url)

            # Return first candidate
            if candidates:
                return self._clean_url(candidates[0])

            return None

        except Exception as e:
            print(f"    Scraping error: {e}")
            return None

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and not a common non-company domain."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False

            # Skip common non-company domains
            skip_domains = ['google', 'facebook', 'youtube', 'twitter', 'yelp', 'yellowpages', 'bbb.org']
            for skip in skip_domains:
                if skip in parsed.netloc.lower():
                    return False

            return True
        except:
            return False

    def _clean_url(self, url: str) -> str:
        """Clean and normalize URL."""
        # Remove tracking parameters, fragments, etc.
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')

    def validate_website(self, website: str, company_name: str, phone: str) -> Dict:
        """
        Validate that the website likely belongs to the company.

        Returns:
            Dict with validation results and confidence score
        """
        if not website:
            return {'valid': False, 'confidence': 0.0, 'reason': 'No website found'}

        try:
            # Extract domain from company name
            company_words = re.findall(r'\w+', company_name.lower())

            # Check if domain contains company name keywords
            domain = urlparse(website).netloc.lower().replace('www.', '')

            # Calculate match score
            matches = sum(1 for word in company_words if len(word) > 3 and word in domain)
            confidence = matches / max(len(company_words), 1)

            if confidence > 0.3:
                return {'valid': True, 'confidence': confidence, 'reason': 'Domain matches company name'}
            else:
                return {'valid': False, 'confidence': confidence, 'reason': 'Domain does not match company name well'}

        except Exception as e:
            return {'valid': False, 'confidence': 0.0, 'reason': f'Validation error: {e}'}


def process_csv(input_file: str, output_file: str, test_limit: Optional[int] = None, use_serp_api: bool = False):
    """Process CSV and look up websites for each company."""

    print("\n" + "="*110)
    print("AUTOMATED WEBSITE LOOKUP")
    print("="*110)

    lookup = WebsiteLookup(use_serp_api=use_serp_api)

    # Read input CSV
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))

    total = len(reader)
    if test_limit:
        reader = reader[:test_limit]
        print(f"\n🧪 TEST MODE: Processing first {test_limit} rows (out of {total:,})")
    else:
        print(f"\n📋 Processing {total:,} companies")

    print(f"Method: {'SerpAPI' if use_serp_api else 'Direct Google Scraping'}")
    if not use_serp_api:
        print("⚠️  Warning: Direct scraping may be rate limited by Google. Consider using SerpAPI for large batches.")

    results = []
    flagged_for_review = []

    for i, row in enumerate(reader, 1):
        phone = row['Phone']
        company = row['Company_Name']
        city = row['City']
        state = row['State']

        print(f"\n[{i}/{len(reader)}] {company[:50]}")
        print(f"  Phone: {phone} | Location: {city}, {state}")

        # Look up website
        website = lookup.search_google(company, phone, city, state)

        if website:
            print(f"  ✅ Found: {website}")
            lookup.successful_lookups += 1

            # Validate
            validation = lookup.validate_website(website, company, phone)

            if validation['valid']:
                print(f"  ✓ Validated (confidence: {validation['confidence']:.2f})")
            else:
                print(f"  ⚠️  Low confidence ({validation['confidence']:.2f}): {validation['reason']}")
                flagged_for_review.append({
                    'row': i,
                    'company': company,
                    'website': website,
                    'reason': validation['reason']
                })

            row['Website_TO_VERIFY'] = website
            row['Confidence'] = f"{validation['confidence']:.2f}"
            row['Validation_Status'] = 'Valid' if validation['valid'] else 'Needs Review'
        else:
            print(f"  ❌ Not found")
            lookup.failed_lookups += 1
            row['Website_TO_VERIFY'] = ''
            row['Confidence'] = '0.00'
            row['Validation_Status'] = 'Not Found'

        results.append(row)

        # Rate limiting (be nice to Google)
        if not use_serp_api and i % 10 == 0:
            print(f"\n  💤 Sleeping 5 seconds to avoid rate limits...")
            time.sleep(5)
        elif i % 50 == 0:
            time.sleep(2)

    # Write output CSV
    if results:
        fieldnames = list(results[0].keys())
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    # Summary
    print("\n" + "="*110)
    print("SUMMARY")
    print("="*110)
    print(f"\nTotal processed: {len(results):,}")
    print(f"Successful lookups: {lookup.successful_lookups:,} ({100*lookup.successful_lookups/len(results):.1f}%)")
    print(f"Failed lookups: {lookup.failed_lookups:,} ({100*lookup.failed_lookups/len(results):.1f}%)")
    print(f"Flagged for review: {len(flagged_for_review):,}")
    print(f"\n📁 Output file: {output_file}")

    if flagged_for_review:
        print(f"\n⚠️  {len(flagged_for_review)} websites flagged for manual review:")
        for item in flagged_for_review[:10]:
            print(f"  Row {item['row']}: {item['company'][:40]} - {item['reason']}")
        if len(flagged_for_review) > 10:
            print(f"  ... and {len(flagged_for_review) - 10} more")

    print("="*110)


def main():
    parser = argparse.ArgumentParser(description='Automated website lookup for companies')
    parser.add_argument('--input', required=True, help='Input CSV file')
    parser.add_argument('--output', default='verified_websites.csv', help='Output CSV file')
    parser.add_argument('--test', type=int, help='Test mode: process only first N rows')
    parser.add_argument('--use-serp-api', action='store_true', help='Use SerpAPI (requires SERP_API_KEY in .env)')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input file not found: {args.input}")
        return

    if args.use_serp_api and not os.getenv('SERP_API_KEY'):
        print("❌ SERP_API_KEY not found in .env file")
        print("Get an API key from https://serpapi.com/ and add to .env:")
        print("SERP_API_KEY=your_key_here")
        return

    process_csv(args.input, args.output, test_limit=args.test, use_serp_api=args.use_serp_api)


if __name__ == "__main__":
    main()
