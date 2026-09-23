"""
Discovery Sheets - Google Sheets integration for Lead Discovery Pipeline
Handles staging, deduplication, and moving leads to final sheet
"""

import os
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Headers for discovery staging
STAGING_HEADERS = [
    'discovery_id', 'company_name', 'address', 'city', 'state', 'phone',
    'website', 'email', 'decision_maker_name', 'decision_maker_title',
    'decision_maker_linkedin', 'email_status', 'google_rating', 'review_count',
    'category', 'source', 'discovered_at', 'status'
]


class DiscoverySheets:
    """
    Handles all Google Sheets operations for the discovery pipeline.
    """

    def __init__(self):
        self.staging_sheet_id = os.getenv('DISCOVERY_STAGING_SHEET_ID')
        self.completed_sheet_id = os.getenv('COMPLETED_LEADS_SHEET_ID')
        self.timezone = pytz.timezone(os.getenv('TIMEZONE', 'America/New_York'))

        if not self.staging_sheet_id:
            raise ValueError("DISCOVERY_STAGING_SHEET_ID not found in environment")

        # Set up authentication
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        # Find credentials.json - check current dir, parent dir, and project root
        creds_path = None
        for path in ['credentials.json', '../credentials.json', os.path.join(os.path.dirname(__file__), '..', 'credentials.json')]:
            if os.path.exists(path):
                creds_path = path
                break

        if not creds_path:
            raise FileNotFoundError("credentials.json not found. Place it in the project root.")

        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        self.client = gspread.authorize(creds)

        # Open sheets
        self.staging = self.client.open_by_key(self.staging_sheet_id)

        if self.completed_sheet_id:
            self.completed = self.client.open_by_key(self.completed_sheet_id)
        else:
            self.completed = None

        logger.info("Connected to Discovery Sheets")

    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        return datetime.now(self.timezone).strftime('%Y-%m-%d %H:%M:%S')

    def _generate_id(self) -> str:
        """Generate unique discovery ID"""
        return datetime.now(self.timezone).strftime('%Y%m%d_%H%M%S_%f')[:20]

    def get_existing_companies(self) -> Set[str]:
        """
        Get all existing company names from completed leads for deduplication.
        Returns normalized company names (lowercase, stripped).
        """
        existing = set()

        if not self.completed:
            logger.warning("No completed leads sheet configured")
            return existing

        try:
            # Get all worksheets in completed sheet
            for ws in self.completed.worksheets():
                try:
                    # Company name is in "title" column (column B = 2)
                    values = ws.col_values(2)
                    for name in values[1:]:  # Skip header
                        if name:
                            # Normalize: lowercase, remove common suffixes
                            normalized = name.lower().strip()
                            for suffix in [' llc', ' inc', ' corp', ' co', ' company']:
                                normalized = normalized.replace(suffix, '')
                            existing.add(normalized)
                except Exception as e:
                    logger.warning(f"Error reading {ws.title}: {e}")

            logger.info(f"Loaded {len(existing)} existing companies for deduplication")

        except Exception as e:
            logger.error(f"Error loading existing companies: {e}")

        return existing

    def get_staging_companies(self, industry: str) -> Set[str]:
        """
        Get company names already in staging for an industry.
        """
        existing = set()

        try:
            # Handle existing sheet naming convention
            if industry.upper() == 'HVAC':
                tab_name = 'HVAC_Pending'
            else:
                tab_name = f"{industry.title()}_Pending"
            ws = self.staging.worksheet(tab_name)
            values = ws.col_values(2)  # company_name is column B

            for name in values[1:]:  # Skip header
                if name:
                    normalized = name.lower().strip()
                    existing.add(normalized)

        except Exception as e:
            logger.warning(f"Error reading staging for {industry}: {e}")

        return existing

    def save_to_staging(
        self,
        leads: List[Dict],
        industry: str,
        source: str = "discovery"
    ) -> Dict:
        """
        Save discovered leads to staging sheet.

        Args:
            leads: List of lead dicts
            industry: HVAC or Roofing
            source: Discovery source (yelp, google_maps, etc.)

        Returns:
            Dict with counts: saved, skipped_duplicate
        """
        # Handle existing sheet naming convention
        if industry.upper() == 'HVAC':
            tab_name = 'HVAC_Pending'
        else:
            tab_name = f"{industry.title()}_Pending"
        timestamp = self._get_timestamp()

        # Refresh sheet metadata to avoid caching issues
        self.staging.fetch_sheet_metadata()

        try:
            ws = self.staging.worksheet(tab_name)
        except WorksheetNotFound:
            # Create tab if it doesn't exist
            ws = self.staging.add_worksheet(title=tab_name, rows=1000, cols=20)
            ws.update(values=[STAGING_HEADERS], range_name='A1:R1')

        # Get existing to avoid duplicates
        existing = self.get_staging_companies(industry)
        completed_existing = self.get_existing_companies()

        saved = 0
        skipped = 0
        rows_to_add = []

        for lead in leads:
            company = lead.get('company_name', '')
            normalized = company.lower().strip()

            # Check for duplicates
            if normalized in existing or normalized in completed_existing:
                skipped += 1
                continue

            # Build row
            row = [
                self._generate_id(),                          # discovery_id
                company,                                      # company_name
                lead.get('address', ''),                      # address
                lead.get('city', ''),                         # city
                lead.get('state', ''),                        # state
                "'" + str(lead.get('phone', '')) if lead.get('phone') else '',  # phone (prefix ' for Sheets)
                lead.get('website', ''),                      # website
                lead.get('email', ''),                        # email
                lead.get('decision_maker_name', ''),          # decision_maker_name
                lead.get('decision_maker_title', ''),         # decision_maker_title
                lead.get('decision_maker_linkedin', ''),      # decision_maker_linkedin
                lead.get('email_status', ''),                 # email_status
                str(lead.get('google_rating', '')),           # google_rating
                str(lead.get('review_count', '')),            # review_count
                lead.get('category', industry),               # category
                source,                                       # source
                timestamp,                                    # discovered_at
                'pending'                                     # status
            ]

            rows_to_add.append(row)
            existing.add(normalized)  # Add to set to catch dups in same batch
            saved += 1

        # Batch append to sheet
        if rows_to_add:
            ws.append_rows(rows_to_add, value_input_option='USER_ENTERED')

        logger.info(f"Saved {saved} leads to {tab_name}, skipped {skipped} duplicates")

        return {'saved': saved, 'skipped_duplicate': skipped}

    def log_discovery_run(
        self,
        industry: str,
        locations: List[str],
        leads_found: int,
        emails_found: int,
        cost: float,
        notes: str = ""
    ):
        """Log a discovery run to the Discovery_Log tab."""
        try:
            ws = self.staging.worksheet('Discovery_Log')
            row = [
                self._get_timestamp(),
                industry,
                ', '.join(locations),
                leads_found,
                emails_found,
                f"${cost:.2f}",
                notes
            ]
            ws.append_row(row)
            logger.info(f"Logged discovery run: {industry} - {leads_found} leads")
        except Exception as e:
            logger.error(f"Error logging discovery run: {e}")

    def get_pending_leads(self, industry: str, limit: int = 100) -> List[Dict]:
        """
        Get pending leads from staging for enrichment.

        Args:
            industry: HVAC or Roofing
            limit: Max leads to return

        Returns:
            List of lead dicts
        """
        # Handle existing sheet naming convention
        if industry.upper() == 'HVAC':
            tab_name = 'HVAC_Pending'
        else:
            tab_name = f"{industry.title()}_Pending"

        try:
            ws = self.staging.worksheet(tab_name)
            records = ws.get_all_records()

            # Filter for pending status
            pending = [r for r in records if r.get('status') == 'pending']

            return pending[:limit]

        except Exception as e:
            logger.error(f"Error getting pending leads: {e}")
            return []

    def update_lead_status(
        self,
        discovery_id: str,
        industry: str,
        new_status: str,
        email: str = None,
        decision_maker_name: str = None,
        decision_maker_title: str = None
    ):
        """Update a lead's status and optionally email info."""
        # Handle existing sheet naming convention
        if industry.upper() == 'HVAC':
            tab_name = 'HVAC_Pending'
        else:
            tab_name = f"{industry.title()}_Pending"

        try:
            ws = self.staging.worksheet(tab_name)
            cell = ws.find(discovery_id)

            if cell:
                row_num = cell.row

                # Update status (column R = 18)
                ws.update_cell(row_num, 18, new_status)

                # Update email info if provided
                if email:
                    ws.update_cell(row_num, 8, email)  # email
                if decision_maker_name:
                    ws.update_cell(row_num, 9, decision_maker_name)
                if decision_maker_title:
                    ws.update_cell(row_num, 10, decision_maker_title)

        except Exception as e:
            logger.error(f"Error updating lead status: {e}")

    def get_stats(self) -> Dict:
        """Get current staging statistics."""
        stats = {
            'hvac_pending': 0,
            'roofing_pending': 0,
            'hvac_enriched': 0,
            'roofing_enriched': 0,
            'total_in_staging': 0
        }

        try:
            for industry in ['HVAC', 'Roofing']:
                # Handle existing sheet naming convention
                if industry.upper() == 'HVAC':
                    tab_name = 'HVAC_Pending'
                else:
                    tab_name = f"{industry.title()}_Pending"
                try:
                    ws = self.staging.worksheet(tab_name)
                    records = ws.get_all_records()

                    pending = len([r for r in records if r.get('status') == 'pending'])
                    enriched = len([r for r in records if r.get('status') == 'enriched'])

                    stats[f'{industry.lower()}_pending'] = pending
                    stats[f'{industry.lower()}_enriched'] = enriched
                    stats['total_in_staging'] += pending + enriched

                except WorksheetNotFound:
                    pass

        except Exception as e:
            logger.error(f"Error getting stats: {e}")

        return stats


def get_sheets() -> DiscoverySheets:
    """Get initialized DiscoverySheets instance."""
    return DiscoverySheets()


def test_discovery_sheets():
    """Test the discovery sheets integration."""
    print("=" * 60)
    print("DISCOVERY SHEETS TEST")
    print("=" * 60)

    try:
        sheets = DiscoverySheets()
        print("Connected to Discovery Sheets!")

        # Get stats
        stats = sheets.get_stats()
        print(f"\nStaging Stats:")
        print(f"  HVAC Pending: {stats['hvac_pending']}")
        print(f"  Roofing Pending: {stats['roofing_pending']}")
        print(f"  Total: {stats['total_in_staging']}")

        # Count existing companies
        existing = sheets.get_existing_companies()
        print(f"\nExisting companies in completed sheet: {len(existing)}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_discovery_sheets()
