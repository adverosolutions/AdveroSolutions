"""
Export Cleaned Data for AnyMailFinder Upload
Creates CSV with exact format needed for AnyMailFinder bulk lookup
"""

import gspread
from google.oauth2.service_account import Credentials
import csv
from datetime import datetime

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDS_PATH = '/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows/credentials.json'

VERIFICATION_SHEET_ID = '1XOj3rG1saVUNa_PjqbNwFgNTBfeG6FI_NPU6MjlFdvE'
OUTPUT_DIR = '/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows/execution'


def export_for_anymail():
    """Export cleaned verification sheet to CSV for AnyMailFinder."""

    print("=" * 60)
    print("EXPORTING FOR ANYMAILFINDER")
    print("=" * 60)

    # Connect to Google Sheets
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(VERIFICATION_SHEET_ID)
    ws = sheet.sheet1

    print("Loading data...")
    all_data = ws.get_all_values()

    if not all_data:
        print("ERROR: Sheet is empty")
        return

    header = all_data[0]
    data_rows = all_data[1:]

    print(f"Total companies: {len(data_rows)}")

    # Find column indexes
    phone_idx = header.index('Phone')
    company_idx = header.index('Company_Name')
    website_idx = header.index('Website_TO_VERIFY')
    address_idx = header.index('Address')
    city_idx = header.index('City')
    state_idx = header.index('State')

    # Count stats
    with_websites = 0
    company_name_only = 0

    # Prepare CSV data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{OUTPUT_DIR}/anymail_upload_{timestamp}.csv"

    # AnyMailFinder expects: Company Name, Website (or leave blank for company name search)
    csv_data = []
    csv_data.append(['Company Name', 'Website', 'Phone', 'Address', 'City', 'State'])

    for row in data_rows:
        if len(row) < max(phone_idx, company_idx, website_idx, address_idx, city_idx, state_idx) + 1:
            continue

        phone = row[phone_idx]
        company = row[company_idx]
        website = row[website_idx] if website_idx < len(row) else ""
        address = row[address_idx] if address_idx < len(row) else ""
        city = row[city_idx] if city_idx < len(row) else ""
        state = row[state_idx] if state_idx < len(row) else ""

        if website and website.strip():
            with_websites += 1
        else:
            company_name_only += 1

        csv_data.append([company, website, phone, address, city, state])

    # Write CSV
    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(csv_data)

    print(f"\n✓ CSV exported: {csv_filename}")
    print(f"\nStats:")
    print(f"  Total companies: {len(data_rows)}")
    print(f"  With verified websites: {with_websites} ({with_websites/len(data_rows)*100:.1f}%)")
    print(f"  Company name only: {company_name_only} ({company_name_only/len(data_rows)*100:.1f}%)")

    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. Open AnyMailFinder bulk upload page")
    print(f"2. Upload: {csv_filename}")
    print("3. Map columns:")
    print("   - Company Name → Company Name")
    print("   - Website → Domain/Website")
    print("4. AnyMailFinder will:")
    print("   - Use website when available (faster, more accurate)")
    print("   - Search by company name when website is blank")
    print("5. Download results and run merge script (coming next)")
    print("=" * 60)

    return {
        'csv_path': csv_filename,
        'total': len(data_rows),
        'with_websites': with_websites,
        'company_name_only': company_name_only
    }


if __name__ == "__main__":
    result = export_for_anymail()

    if result:
        print(f"\n✓ Ready for AnyMailFinder upload!")
        print(f"   File: {result['csv_path']}")
