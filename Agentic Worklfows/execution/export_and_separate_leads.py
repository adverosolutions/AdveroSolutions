#!/usr/bin/env python3
"""
Export leads from Google Sheets CRM and separate contacted from fresh leads
"""

import os
import sys
import csv
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
from dotenv import load_dotenv

# Add the execution directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from separate_contacted_leads import (
    get_all_contacted_leads,
    separate_csv_leads,
    calculate_reintroduction_date,
    save_separated_leads
)
from instantly_api import InstantlyAPI

load_dotenv()

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

def get_google_sheets_service():
    """Get authenticated Google Sheets service"""
    creds = None

    # Token file stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('sheets', 'v4', credentials=creds)

def export_leads_from_sheet():
    """Export leads from Google Sheets to CSV"""
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID not found in .env")

    print(f"Connecting to Google Sheet: {sheet_id}")

    service = get_google_sheets_service()

    # Get all data from the CRM sheet
    range_name = 'CRM!A:Z'  # Adjust if your sheet name is different

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=range_name).execute()

        values = result.get('values', [])

        if not values:
            print("No data found in sheet")
            return None

        # First row is headers
        headers = values[0]
        data_rows = values[1:]

        # Create CSV file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"leads_export_{timestamp}.csv"

        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            for row in data_rows:
                # Pad row to match header length if needed
                while len(row) < len(headers):
                    row.append('')
                writer.writerows([row[:len(headers)]])

        print(f"✅ Exported {len(data_rows)} leads to {csv_filename}")
        return csv_filename

    except Exception as e:
        print(f"Error accessing Google Sheet: {e}")
        raise

def main():
    """Main execution"""
    print("=" * 60)
    print("LEAD SEPARATION PROCESS")
    print("=" * 60)

    try:
        # Step 1: Export leads from Google Sheets
        print("\n📊 Step 1: Exporting leads from Google Sheets...")
        csv_file = export_leads_from_sheet()

        if not csv_file:
            print("No CSV file to process")
            return 1

        # Step 2: Connect to Instantly
        print("\n🔌 Step 2: Connecting to Instantly API...")
        client = InstantlyAPI()
        print("✅ Connected to Instantly")

        # Step 3: Get all contacted leads
        print("\n📧 Step 3: Fetching contacted leads from all campaigns...")
        contacted_emails, contact_details = get_all_contacted_leads(client)
        print(f"✅ Found {len(contacted_emails)} unique contacted emails")

        # Step 4: Separate the leads
        print("\n🔍 Step 4: Separating fresh leads from contacted leads...")
        fresh_leads, previously_contacted = separate_csv_leads(
            csv_file, contacted_emails, contact_details
        )

        # Step 5: Calculate reintroduction dates (2 weeks default)
        print("\n📅 Step 5: Calculating reintroduction dates (2-week minimum)...")
        reintroduction_dates = calculate_reintroduction_date(
            contact_details, min_weeks=2
        )

        # Step 6: Save the results
        print("\n💾 Step 6: Saving separated lead files...")
        save_separated_leads(
            fresh_leads, previously_contacted,
            reintroduction_dates, output_dir="."
        )

        # Clean up temporary export file
        os.remove(csv_file)
        print(f"\n🗑️  Cleaned up temporary file: {csv_file}")

        print("\n" + "=" * 60)
        print("✅ PROCESS COMPLETE!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Upload the fresh_leads file to your new Instantly campaign")
        print("2. Schedule the previously_contacted file for 2+ weeks from now")
        print("3. Check the summary file for detailed breakdown")

        return 0

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())