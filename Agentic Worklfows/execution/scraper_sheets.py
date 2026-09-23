"""
Scraper Sheets - Google Sheets output for the mass lead scraper.
One Google Sheet with separate tabs per industry.
Batch writes leads to avoid API rate limits.

.env config:
    SCRAPER_SHEET_ID=<sheet_id>
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
from typing import Dict, List
from dotenv import load_dotenv
import logging

# Load .env from project root (two levels up from execution/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_env_path = os.path.join(_project_root, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

HEADERS = [
    "company_name", "phone", "address", "city", "state",
    "website", "industry", "source_query", "scraped_at"
]

# Maps industry search terms -> tab name
INDUSTRY_TABS = {
    "pest control": "Pest Control",
    "garage door": "Garage Door",
    "garage door repair": "Garage Door",
    "landscaping": "Landscaping",
    "lawn care": "Landscaping",
    "pool service": "Pool Service",
    "pool service and repair": "Pool Service",
    "pool repair": "Pool Service",
}


def _get_tab_name(industry: str) -> str:
    """Map industry string to tab name."""
    industry_lower = industry.lower().strip()
    if industry_lower in INDUSTRY_TABS:
        return INDUSTRY_TABS[industry_lower]
    for key, tab in INDUSTRY_TABS.items():
        if key in industry_lower or industry_lower in key:
            return tab
    return industry.title()


class ScraperSheets:
    """
    Handles Google Sheets output for scraped leads.
    Single sheet with one tab per industry.
    """

    def __init__(self):
        self.timezone = pytz.timezone(os.getenv("TIMEZONE", "America/New_York"))
        self.sheet_id = os.getenv("SCRAPER_SHEET_ID")

        if not self.sheet_id:
            raise ValueError(
                "SCRAPER_SHEET_ID not set in .env. "
                "Create a Google Sheet, share it with the service account, "
                "and add the ID to .env."
            )

        # Auth
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        # Try environment variable first (for Modal cloud)
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            import json
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            # Fall back to credentials file (for local)
            creds_path = None
            for path in [
                "credentials.json",
                "../credentials.json",
                os.path.join(os.path.dirname(__file__), "..", "credentials.json"),
            ]:
                if os.path.exists(path):
                    creds_path = path
                    break

            if not creds_path:
                raise FileNotFoundError("credentials.json not found and GOOGLE_CREDENTIALS_JSON not in environment")

            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)

        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(self.sheet_id)

        self._ensure_tabs()
        logger.info(f"Connected to scraper sheet: {self.sheet_id}")

    def _ensure_tabs(self):
        """Create industry tabs with headers if they don't exist."""
        existing_tabs = {ws.title for ws in self.spreadsheet.worksheets()}
        needed_tabs = set(INDUSTRY_TABS.values())

        for tab_name in needed_tabs:
            if tab_name not in existing_tabs:
                ws = self.spreadsheet.add_worksheet(
                    title=tab_name, rows=1000, cols=len(HEADERS)
                )
                ws.update(values=[HEADERS], range_name=f"A1:{chr(64 + len(HEADERS))}1")
                logger.info(f"Created tab: {tab_name}")

        # Remove default Sheet1 if our tabs exist
        if "Sheet1" in existing_tabs and len(existing_tabs) > 1:
            try:
                self.spreadsheet.del_worksheet(
                    self.spreadsheet.worksheet("Sheet1")
                )
            except Exception:
                pass

    def clear_tab(self, industry: str):
        """Clear all data from an industry tab (keeps headers)."""
        tab_name = _get_tab_name(industry)
        try:
            ws = self.spreadsheet.worksheet(tab_name)
            ws.clear()
            ws.update(values=[HEADERS], range_name=f"A1:{chr(64 + len(HEADERS))}1")
            logger.info(f"Cleared tab: {tab_name}")
        except Exception as e:
            logger.warning(f"Could not clear tab {tab_name}: {e}")

    def write_leads(self, leads: List[Dict], industry: str, source_query: str = "") -> int:
        """
        Batch write leads to the appropriate industry tab.

        Returns:
            Number of leads written
        """
        if not leads:
            return 0

        tab_name = _get_tab_name(industry)
        timestamp = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")

        try:
            ws = self.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title=tab_name, rows=1000, cols=len(HEADERS)
            )
            ws.update(values=[HEADERS], range_name=f"A1:{chr(64 + len(HEADERS))}1")

        rows = []
        for lead in leads:
            phone = lead.get("phone", "")
            if phone:
                phone = "'" + str(phone)

            rows.append([
                lead.get("company_name", ""),
                phone,
                lead.get("address", ""),
                lead.get("city", ""),
                lead.get("state", ""),
                lead.get("website", ""),
                industry,
                source_query,
                timestamp,
            ])

        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")

        logger.info(f"Wrote {len(rows)} leads to tab '{tab_name}'")
        return len(rows)

    def get_stats(self) -> Dict:
        """Get current lead counts per tab."""
        stats = {}
        for ws in self.spreadsheet.worksheets():
            try:
                row_count = len(ws.get_all_values()) - 1
                stats[ws.title] = max(0, row_count)
            except Exception:
                stats[ws.title] = 0
        stats["total"] = sum(stats.values())
        return stats


def test_sheets():
    """Test Google Sheets connection and write."""
    logging.basicConfig(level=logging.INFO)

    print("Testing Scraper Sheets connection...")
    sheets = ScraperSheets()

    test_leads = [
        {
            "company_name": "Test Pest Control LLC",
            "phone": "(555) 123-4567",
            "address": "123 Test St",
            "city": "Houston",
            "state": "TX",
            "website": "https://testpestcontrol.com",
        },
    ]

    written = sheets.write_leads(test_leads, "pest control", "test query")
    print(f"Wrote {written} test leads")

    stats = sheets.get_stats()
    print(f"Sheet stats: {stats}")


if __name__ == "__main__":
    test_sheets()
