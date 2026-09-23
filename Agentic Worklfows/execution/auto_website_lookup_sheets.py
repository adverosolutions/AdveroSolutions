"""
Automated Website Lookup for Leads - Google Sheets Integration
================================================================

This script automatically looks up websites for companies and writes directly to Google Sheets.

Usage:
    python auto_website_lookup_sheets.py --sheet-id 1XOj3rG1saVUNa_PjqbNwFgNTBfeG6FI_NPU6MjlFdvE --test 10
    python auto_website_lookup_sheets.py --sheet-id 1XOj3rG1saVUNa_PjqbNwFgNTBfeG6FI_NPU6MjlFdvE  # Process all rows
"""

import os
import sys
import argparse
import time
import re
from typing import Dict, Optional
import requests
from urllib.parse import urlparse, quote_plus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from google_sheets_client import get_sheets_client

load_dotenv('../.env')


class WebsiteLookup:
    """Automated website lookup using Google Search."""

    def __init__(self):
        self.requests_made = 0
        self.successful_lookups = 0
        self.failed_lookups = 0

    def search_google(self, company_name: str, phone: str, city: str, state: str) -> Optional[str]:
        """
        Search Google for company website using direct scraping.

        Returns:
            Website URL if found, None otherwise
        """
        try:
            # Build search query
            query = f'"{company_name}" "{phone}" {city} {state}'

            # Build Google search URL
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            response = requests.get(search_url, headers=headers, timeout=10)
            self.requests_made += 1

            if response.status_code != 200:
                return None

            # Extract URLs from search results
            # Look for common website URL patterns in the HTML
            text = response.text

            # Find URLs in href attributes and other locations
            url_pattern = r'https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})(?:/[^\s"<>]*)?'
            urls = re.findall(url_pattern, text)

            # Filter and score candidates
            candidates = []
            skip_domains = ['google', 'facebook', 'youtube', 'twitter', 'instagram', 'yelp', 'yellowpages', 'bbb.org', 'mapquest', 'gstatic']

            for match in urls[:50]:  # Check first 50 URLs
                domain = match

                # Skip common non-company domains
                if any(skip in domain.lower() for skip in skip_domains):
                    continue

                # Reconstruct full URL
                full_url = f"https://{domain}"

                # Score based on company name match
                score = self._score_url(full_url, company_name)

                if score > 0:
                    candidates.append((full_url, score))

            # Sort by score and return best match
            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                return candidates[0][0]

            return None

        except Exception as e:
            print(f"      Error: {e}")
            return None

    def _score_url(self, url: str, company_name: str) -> float:
        """Score how well a URL matches the company name."""
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')

            # Extract significant words from company name (3+ chars)
            company_words = [w.lower() for w in re.findall(r'\w+', company_name) if len(w) >= 3]
            company_words = [w for w in company_words if w not in ['llc', 'inc', 'ltd', 'company', 'corp', 'the', 'and']]

            if not company_words:
                return 0.0

            # Count matches
            matches = sum(1 for word in company_words if word in domain)
            score = matches / len(company_words)

            return score

        except:
            return 0.0

    def validate_website(self, website: str, company_name: str) -> Dict:
        """
        Validate that the website likely belongs to the company.

        Returns:
            Dict with validation results and confidence score
        """
        if not website:
            return {'valid': False, 'confidence': 0.0, 'reason': 'No website found'}

        try:
            score = self._score_url(website, company_name)

            if score >= 0.3:
                return {'valid': True, 'confidence': score, 'reason': 'Good domain match'}
            elif score > 0:
                return {'valid': False, 'confidence': score, 'reason': 'Weak domain match'}
            else:
                return {'valid': False, 'confidence': 0.0, 'reason': 'No domain match'}

        except Exception as e:
            return {'valid': False, 'confidence': 0.0, 'reason': f'Error: {e}'}


def process_google_sheet(sheet_id: str, test_limit: Optional[int] = None):
    """Process Google Sheet and look up websites for each company."""

    print("\n" + "="*110)
    print("AUTOMATED WEBSITE LOOKUP - GOOGLE SHEETS INTEGRATION")
    print("="*110)

    # Get credentials
    creds_path = '../credentials.json'
    if not os.path.exists(creds_path):
        print("❌ credentials.json not found")
        return

    client = get_sheets_client(creds_path)
    lookup = WebsiteLookup()

    # Open the sheet
    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.get_worksheet(0)  # First tab

        print(f"\n📊 Connected to Google Sheet: {spreadsheet.title}")
        print(f"   Tab: {worksheet.title}")

    except Exception as e:
        print(f"❌ Error opening sheet: {e}")
        return

    # Read all data
    data = worksheet.get_all_values()

    if not data or len(data) < 2:
        print("❌ No data found in sheet")
        return

    header = data[0]
    rows = data[1:]

    # Find column indices
    try:
        phone_idx = header.index('Phone')
        company_idx = header.index('Company_Name')
        city_idx = header.index('City')
        state_idx = header.index('State')
        website_idx = header.index('Website_TO_VERIFY')
    except ValueError as e:
        print(f"❌ Missing required column: {e}")
        print(f"   Found columns: {header}")
        return

    # Add new columns if they don't exist
    if 'Confidence' not in header:
        header.append('Confidence')
        confidence_idx = len(header) - 1
        # Update header in sheet
        worksheet.update(f'A1:{chr(65 + len(header) - 1)}1', [header])
    else:
        confidence_idx = header.index('Confidence')

    if 'Validation_Status' not in header:
        header.append('Validation_Status')
        status_idx = len(header) - 1
        # Update header in sheet
        worksheet.update(f'A1:{chr(65 + len(header) - 1)}1', [header])
    else:
        status_idx = header.index('Validation_Status')

    total = len(rows)
    if test_limit:
        rows = rows[:test_limit]
        print(f"\n🧪 TEST MODE: Processing first {test_limit} rows (out of {total:,})")
    else:
        print(f"\n📋 Processing {total:,} companies")

    print(f"\n⚠️  Using free Google scraping - may be rate limited")
    print(f"    Will add 3-5 second delays between requests")

    successful = 0
    failed = 0
    flagged = 0

    for i, row in enumerate(rows, 1):
        # Pad row to ensure it has enough columns
        while len(row) < len(header):
            row.append('')

        phone = row[phone_idx] if len(row) > phone_idx else ''
        company = row[company_idx] if len(row) > company_idx else ''
        city = row[city_idx] if len(row) > city_idx else ''
        state = row[state_idx] if len(row) > state_idx else ''

        print(f"\n[{i}/{len(rows)}] {company[:60]}")
        print(f"    Phone: {phone} | Location: {city}, {state}")

        # Look up website
        website = lookup.search_google(company, phone, city, state)

        if website:
            print(f"    ✅ Found: {website}")
            successful += 1

            # Validate
            validation = lookup.validate_website(website, company)

            if validation['valid']:
                print(f"    ✓ Validated (confidence: {validation['confidence']:.2f})")
                status = 'Valid'
            else:
                print(f"    ⚠️  {validation['reason']} (confidence: {validation['confidence']:.2f})")
                status = 'Needs Review'
                flagged += 1

            # Update row
            row[website_idx] = website
            row[confidence_idx] = f"{validation['confidence']:.2f}"
            row[status_idx] = status

            # Write to sheet (row by row for safety)
            row_number = i + 1  # +1 for header
            worksheet.update(f'A{row_number}:{chr(65 + len(row) - 1)}{row_number}', [row])

        else:
            print(f"    ❌ Not found")
            failed += 1

            row[website_idx] = ''
            row[confidence_idx] = '0.00'
            row[status_idx] = 'Not Found'

            # Write to sheet
            row_number = i + 1
            worksheet.update(f'A{row_number}:{chr(65 + len(row) - 1)}{row_number}', [row])

        # Rate limiting - be very conservative to avoid getting blocked
        if i % 5 == 0:
            print(f"\n    💤 Sleeping 5 seconds to avoid rate limits...")
            time.sleep(5)
        else:
            time.sleep(3)

        # Progress update every 25 rows
        if i % 25 == 0:
            print(f"\n    📊 Progress: {i}/{len(rows)} | Success: {successful} | Failed: {failed} | Flagged: {flagged}")

    # Final summary
    print("\n" + "="*110)
    print("SUMMARY")
    print("="*110)
    print(f"\nTotal processed: {len(rows):,}")
    print(f"Successful lookups: {successful:,} ({100*successful/len(rows):.1f}%)")
    print(f"Failed lookups: {failed:,} ({100*failed/len(rows):.1f}%)")
    print(f"Flagged for review: {flagged:,} ({100*flagged/len(rows) if len(rows) else 0:.1f}%)")
    print(f"\n✅ Results written to Google Sheet: {spreadsheet.url}")
    print("="*110)


def main():
    parser = argparse.ArgumentParser(description='Automated website lookup for companies (Google Sheets)')
    parser.add_argument('--sheet-id', required=True, help='Google Sheet ID')
    parser.add_argument('--test', type=int, help='Test mode: process only first N rows')

    args = parser.parse_args()

    process_google_sheet(args.sheet_id, test_limit=args.test)


if __name__ == "__main__":
    main()
