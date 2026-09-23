"""
Lead Discovery Pipeline - A-Z Orchestrator
Discovers businesses -> Finds emails -> Saves to staging -> Ready for enrichment

This is the main orchestrator for the Lean Mean Lead Finder Machine.
"""

import os
import sys
import asyncio
import logging
from typing import List, Dict
from datetime import datetime
import argparse
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our modules
from discovery_rotation import DiscoveryRotation
from anymail_finder import AnymailFinder
from discovery_sheets import DiscoverySheets

# Texas cities for discovery
TEXAS_CITIES = [
    "Houston, TX",
    "Dallas, TX",
    "Austin, TX",
    "San Antonio, TX",
    "Fort Worth, TX",
    "El Paso, TX",
    "Arlington, TX",
    "Plano, TX",
    "Corpus Christi, TX",
    "Lubbock, TX",
    "Irving, TX",
    "Laredo, TX",
    "Garland, TX",
    "Frisco, TX",
    "McKinney, TX"
]


class LeadDiscoveryPipeline:
    """
    Main orchestrator for lead discovery.
    Handles: Discovery -> Email Finding -> Deduplication -> Saving
    """

    def __init__(self):
        self.discovery = DiscoveryRotation()
        self.email_finder = None
        self.sheets = None

        self._init_email_finder()
        self._init_sheets()

    def _init_email_finder(self):
        """Initialize email finder if API key available."""
        try:
            self.email_finder = AnymailFinder()
            logger.info("Anymail Finder initialized")
        except ValueError as e:
            logger.warning(f"Anymail Finder not available: {e}")

    def _init_sheets(self):
        """Initialize Google Sheets via DiscoverySheets."""
        try:
            self.sheets = DiscoverySheets()
            logger.info("Discovery Sheets initialized")
        except Exception as e:
            logger.warning(f"Google Sheets not available: {e}")

    async def run_discovery(
        self,
        industries: List[str],
        locations: List[str],
        max_per_location: int = 100,
        find_emails: bool = True,
        save_to_sheets: bool = True
    ) -> Dict:
        """
        Run the full discovery pipeline.

        Args:
            industries: List of industries (e.g., ["HVAC", "Roofing"])
            locations: List of locations
            max_per_location: Max businesses per location
            find_emails: Whether to enrich with emails
            save_to_sheets: Whether to save results to Google Sheets

        Returns:
            Summary dict with results
        """
        start_time = datetime.now()
        results = {
            'started_at': start_time.isoformat(),
            'industries': industries,
            'locations': locations,
            'discovered': 0,
            'with_emails': 0,
            'saved': 0,
            'skipped_duplicates': 0,
            'by_industry': {}
        }

        # Load existing data for deduplication
        existing_companies = set()
        if self.sheets:
            existing_companies = self.sheets.get_existing_companies()
        logger.info(f"Loaded {len(existing_companies)} existing companies for dedup")

        for industry in industries:
            logger.info(f"\n{'='*50}")
            logger.info(f"DISCOVERING {industry.upper()}")
            logger.info(f"{'='*50}")

            # Discover businesses
            businesses = await self.discovery.discover_businesses(
                industry=industry,
                locations=locations,
                max_per_location=max_per_location,
                dedupe_against=existing_companies
            )

            logger.info(f"Discovered {len(businesses)} {industry} businesses")

            # Find emails if enabled
            with_emails = 0
            if find_emails and self.email_finder and businesses:
                logger.info(f"Finding emails for {len(businesses)} businesses...")
                businesses = self._enrich_with_emails(businesses)
                with_emails = sum(1 for b in businesses if b.get('email'))
                logger.info(f"Found emails for {with_emails} businesses")

            # Save to sheets
            saved = 0
            skipped = 0
            if save_to_sheets and self.sheets and businesses:
                save_result = self.sheets.save_to_staging(
                    leads=businesses,
                    industry=industry,
                    source="rotation"
                )
                saved = save_result['saved']
                skipped = save_result['skipped_duplicate']

            # Update results
            results['by_industry'][industry] = {
                'discovered': len(businesses),
                'with_emails': with_emails,
                'saved': saved,
                'skipped': skipped
            }

            results['discovered'] += len(businesses)
            results['with_emails'] += with_emails
            results['saved'] += saved
            results['skipped_duplicates'] += skipped

            # Update existing companies set
            for biz in businesses:
                existing_companies.add(biz['company_name'].lower().strip())

        # Log discovery run
        if self.sheets:
            self.sheets.log_discovery_run(
                industry=', '.join(industries),
                locations=locations,
                leads_found=results['discovered'],
                emails_found=results['with_emails'],
                cost=0.0,  # TODO: Calculate actual cost
                notes=f"Saved: {results['saved']}, Skipped: {results['skipped_duplicates']}"
            )

        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results['completed_at'] = end_time.isoformat()
        results['duration_seconds'] = duration
        results['duration_minutes'] = round(duration / 60, 2)

        # Log summary
        self._log_summary(results)

        return results

    def _enrich_with_emails(self, businesses: List[Dict]) -> List[Dict]:
        """Enrich businesses with email addresses."""
        if not self.email_finder:
            return businesses

        enriched = []

        for i, biz in enumerate(businesses):
            website = biz.get('website', '')
            company_name = biz.get('company_name', '')

            if website or company_name:
                result = self.email_finder.find_decision_maker(website, company_name)

                biz['email'] = result.get('email')
                biz['decision_maker_name'] = result.get('name')
                biz['decision_maker_title'] = result.get('title')
                biz['decision_maker_linkedin'] = result.get('linkedin')
                biz['email_status'] = result.get('status', 'unknown')

            enriched.append(biz)

            # Progress logging
            if (i + 1) % 10 == 0:
                emails_found = sum(1 for b in enriched if b.get('email'))
                logger.info(f"Email enrichment: {i + 1}/{len(businesses)} ({emails_found} emails found)")

        return enriched

    def _log_summary(self, results: Dict):
        """Log a summary of the discovery run."""
        print("\n" + "=" * 60)
        print("DISCOVERY PIPELINE SUMMARY")
        print("=" * 60)
        print(f"Duration: {results['duration_minutes']} minutes")
        print(f"Total Discovered: {results['discovered']}")
        print(f"With Emails: {results['with_emails']}")
        print(f"Saved to Sheets: {results['saved']}")
        print(f"Skipped (duplicates): {results['skipped_duplicates']}")
        print("\nBy Industry:")
        for industry, stats in results['by_industry'].items():
            print(f"  {industry}:")
            print(f"    Discovered: {stats['discovered']}")
            print(f"    With Emails: {stats.get('with_emails', 0)}")
            print(f"    Saved: {stats.get('saved', 0)}")
            print(f"    Skipped: {stats.get('skipped', 0)}")
        print("=" * 60)


def run_pipeline_sync(
    industries: List[str] = None,
    locations: List[str] = None,
    max_per_location: int = 100,
    find_emails: bool = True,
    save_to_sheets: bool = True
) -> Dict:
    """
    Synchronous wrapper for running the pipeline.
    """
    if industries is None:
        industries = ["HVAC", "Roofing"]

    if locations is None:
        locations = TEXAS_CITIES[:5]  # Default to top 5 Texas cities

    pipeline = LeadDiscoveryPipeline()

    return asyncio.run(pipeline.run_discovery(
        industries=industries,
        locations=locations,
        max_per_location=max_per_location,
        find_emails=find_emails,
        save_to_sheets=save_to_sheets
    ))


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description='Lead Discovery Pipeline')

    parser.add_argument(
        '--industries',
        nargs='+',
        default=['HVAC', 'Roofing'],
        help='Industries to discover (default: HVAC Roofing)'
    )

    parser.add_argument(
        '--locations',
        nargs='+',
        default=None,
        help='Locations to search (default: top 5 Texas cities)'
    )

    parser.add_argument(
        '--max-per-location',
        type=int,
        default=100,
        help='Max businesses per location (default: 100)'
    )

    parser.add_argument(
        '--no-emails',
        action='store_true',
        help='Skip email enrichment'
    )

    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Skip saving to Google Sheets'
    )

    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: 10 results per location, no emails, no save'
    )

    args = parser.parse_args()

    if args.test:
        print("\n" + "=" * 60)
        print("RUNNING IN TEST MODE")
        print("=" * 60)
        locations = ["Houston, TX"]
        max_per_location = 10
        find_emails = False
        save_to_sheets = False
    else:
        locations = args.locations or TEXAS_CITIES[:5]
        max_per_location = args.max_per_location
        find_emails = not args.no_emails
        save_to_sheets = not args.no_save

    print(f"\nDiscovery Configuration:")
    print(f"  Industries: {args.industries}")
    print(f"  Locations: {locations}")
    print(f"  Max per location: {max_per_location}")
    print(f"  Find emails: {find_emails}")
    print(f"  Save to sheets: {save_to_sheets}")
    print()

    results = run_pipeline_sync(
        industries=args.industries,
        locations=locations,
        max_per_location=max_per_location,
        find_emails=find_emails,
        save_to_sheets=save_to_sheets
    )

    return results


if __name__ == "__main__":
    main()
