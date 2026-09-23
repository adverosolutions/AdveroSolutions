"""
List all tabs in both Master CRM and Scraped Leads sheets
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from google_sheets_client import get_sheets_client

load_dotenv()

MASTER_CRM_SHEET_ID = "1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8"
SCRAPED_LEADS_SHEET_ID = "1pqHEYgGOVgf5tcYdcuNQiUArVf3MvavJ9DRlyHsm_2A"

def main():
    creds_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    client = get_sheets_client(creds_path)

    print("\n📊 MASTER CRM V2 TABS:")
    print("="*50)
    master_sheet = client.open_by_key(MASTER_CRM_SHEET_ID)
    for i, ws in enumerate(master_sheet.worksheets(), 1):
        print(f"{i}. {ws.title} ({ws.row_count} rows, {ws.col_count} cols)")

    print("\n📊 SCRAPED LEADS TABS:")
    print("="*50)
    scraped_sheet = client.open_by_key(SCRAPED_LEADS_SHEET_ID)
    for i, ws in enumerate(scraped_sheet.worksheets(), 1):
        print(f"{i}. {ws.title} ({ws.row_count} rows, {ws.col_count} cols)")

    print()

if __name__ == "__main__":
    main()
