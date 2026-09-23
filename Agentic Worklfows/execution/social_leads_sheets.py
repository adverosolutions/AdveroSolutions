"""
Google Sheets integration for Social Lead Monitor
Logs detected leads to the CRM
"""

import os
import sys
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from google_sheets_client import GoogleSheetsClient
except ImportError:
    print("Warning: google_sheets_client not found. Install gspread and oauth2client.")
    GoogleSheetsClient = None

load_dotenv()

SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8')
SOCIAL_LEADS_TAB = 'Social Leads'


def ensure_social_leads_tab():
    """
    Create the Social Leads tab in Google Sheets if it doesn't exist
    """
    if not GoogleSheetsClient:
        print("Google Sheets client not available")
        return False

    try:
        client = GoogleSheetsClient(SHEET_ID)
        sheet = client.get_sheet()

        # Check if tab exists
        try:
            worksheet = sheet.worksheet(SOCIAL_LEADS_TAB)
            print(f"'{SOCIAL_LEADS_TAB}' tab already exists")
            return True
        except:
            # Tab doesn't exist, create it
            worksheet = sheet.add_worksheet(title=SOCIAL_LEADS_TAB, rows=1000, cols=20)

            # Set up headers
            headers = [
                'Timestamp',
                'Platform',
                'Group Name',
                'Author',
                'Post Text',
                'Post URL',
                'Detected Keywords',
                'AI Classification',
                'Confidence Score',
                'Urgency',
                'Services Needed',
                'Location',
                'Status',
                'Notes'
            ]

            worksheet.update('A1:N1', [headers])

            # Format header row
            worksheet.format('A1:N1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.13, 'green': 0.55, 'blue': 0.13}  # Green
            })

            print(f"Created '{SOCIAL_LEADS_TAB}' tab successfully")
            return True

    except Exception as e:
        print(f"Error setting up Social Leads tab: {e}")
        return False


def log_lead_to_sheets(lead_data: Dict) -> bool:
    """
    Log a detected lead to Google Sheets

    Args:
        lead_data: Dict with keys:
            - timestamp
            - platform
            - groupName
            - author
            - postText
            - postUrl
            - detectedKeywords (list)
            - classification
            - confidence
            - urgency
            - servicesNeeded
            - location
            - status

    Returns:
        True if logged successfully
    """
    if not GoogleSheetsClient:
        print("Google Sheets client not available")
        return False

    try:
        client = GoogleSheetsClient(SHEET_ID)
        worksheet = client.get_sheet().worksheet(SOCIAL_LEADS_TAB)

        # Format the row
        row = [
            lead_data.get('timestamp', datetime.now().isoformat()),
            lead_data.get('platform', 'unknown'),
            lead_data.get('groupName', ''),
            lead_data.get('author', ''),
            lead_data.get('postText', ''),
            lead_data.get('postUrl', ''),
            ', '.join(lead_data.get('detectedKeywords', [])),
            lead_data.get('classification', ''),
            lead_data.get('confidence', 0),
            lead_data.get('urgency', ''),
            lead_data.get('servicesNeeded', ''),
            lead_data.get('location', ''),
            lead_data.get('status', 'new'),
            ''  # Notes column (empty)
        ]

        # Append to sheet
        worksheet.append_row(row)

        print(f"Lead logged to Google Sheets: {lead_data.get('platform')} - {lead_data.get('author')}")
        return True

    except Exception as e:
        print(f"Error logging lead to Google Sheets: {e}")
        return False


def get_recent_leads(limit: int = 10) -> List[Dict]:
    """
    Get recent leads from Google Sheets

    Args:
        limit: Number of recent leads to retrieve

    Returns:
        List of lead dicts
    """
    if not GoogleSheetsClient:
        return []

    try:
        client = GoogleSheetsClient(SHEET_ID)
        worksheet = client.get_sheet().worksheet(SOCIAL_LEADS_TAB)

        # Get all values
        all_values = worksheet.get_all_values()

        if len(all_values) <= 1:  # Only headers or empty
            return []

        # Get headers
        headers = all_values[0]

        # Get recent rows (reverse order, skip header)
        recent_rows = all_values[1:][::-1][:limit]

        # Convert to dicts
        leads = []
        for row in recent_rows:
            lead = {}
            for i, header in enumerate(headers):
                lead[header] = row[i] if i < len(row) else ''
            leads.append(lead)

        return leads

    except Exception as e:
        print(f"Error getting recent leads: {e}")
        return []


def test_sheets_integration():
    """Test the Google Sheets integration"""
    print("=" * 60)
    print("SOCIAL LEADS GOOGLE SHEETS TEST")
    print("=" * 60)
    print()

    # Ensure tab exists
    print("1. Checking/creating Social Leads tab...")
    success = ensure_social_leads_tab()

    if not success:
        print("Failed to set up Social Leads tab")
        return

    print()

    # Test logging a lead
    print("2. Logging test lead...")
    test_lead = {
        'timestamp': datetime.now().isoformat(),
        'platform': 'facebook',
        'groupName': 'Phoenix Home Services (TEST)',
        'author': 'John Smith',
        'postText': 'Need someone to mow my lawn weekly starting next week. Small front yard, easy access.',
        'postUrl': 'https://facebook.com/groups/test/posts/123',
        'detectedKeywords': ['lawn', 'mowing', 'need'],
        'classification': 'genuine_lead',
        'confidence': 85,
        'urgency': 'medium',
        'servicesNeeded': 'weekly mowing',
        'location': 'Phoenix, AZ',
        'status': 'new'
    }

    success = log_lead_to_sheets(test_lead)

    if success:
        print("Test lead logged successfully!")
    else:
        print("Failed to log test lead")

    print()

    # Get recent leads
    print("3. Retrieving recent leads...")
    recent = get_recent_leads(limit=5)

    if recent:
        print(f"Found {len(recent)} recent leads:")
        for i, lead in enumerate(recent, 1):
            print(f"\n  Lead {i}:")
            print(f"    Platform: {lead.get('Platform')}")
            print(f"    Author: {lead.get('Author')}")
            print(f"    Confidence: {lead.get('Confidence Score')}%")
            print(f"    Status: {lead.get('Status')}")
    else:
        print("No recent leads found")

    print()
    print("=" * 60)
    print("Test complete! Check your Google Sheet:")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    print("=" * 60)


if __name__ == "__main__":
    test_sheets_integration()
