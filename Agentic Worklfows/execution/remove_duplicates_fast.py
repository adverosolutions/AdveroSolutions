"""
Remove Duplicates from Combined - All States Sheet (FAST VERSION)
Instead of deleting rows one by one, rebuilds sheet with only unique leads
"""

import gspread
from google.oauth2.service_account import Credentials
import time

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDS_PATH = '/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows/credentials.json'

# P&E Leads spreadsheet (has Combined - All States)
PE_SHEET_ID = '1d3Uu_J7vQOdRs9Wha4lJYoax9P_oqF3_oIj7skkYa1Y'
COMBINED_SHEET_NAME = 'Combined - All States'

# Ready To Outreach spreadsheet (has Electrician and Plumbing)
OUTREACH_SHEET_ID = '1JVhfoBlaPiTGqvnBPz32tL-h69U9GMInnSvLNRwZnh0'
ELECTRICIAN_SHEET_NAME = 'Electrician Leads'
PLUMBING_SHEET_NAME = 'Plumbing Leads'


def normalize_phone(phone_str):
    """Normalize phone number to digits only for comparison."""
    if not phone_str:
        return None
    # Remove all non-digit characters
    digits = ''.join(c for c in str(phone_str) if c.isdigit())
    # Remove leading 1 if present (US country code)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) >= 10 else None


def get_phone_from_row(row, header):
    """Extract and normalize phone number from row."""
    phone_cols = ['phone', 'phoneNumber', 'Phone', 'PhoneNumber', 'tel']
    for col in phone_cols:
        if col in header:
            idx = header.index(col)
            if idx < len(row) and row[idx]:
                return normalize_phone(row[idx])
    return None


def load_existing_phones(client):
    """Load all phone numbers from Electrician and Plumbing sheets."""

    print("=" * 60)
    print("LOADING EXISTING PHONE NUMBERS")
    print("=" * 60)

    outreach_sheet = client.open_by_key(OUTREACH_SHEET_ID)

    existing_phones = set()

    # Load Electrician Leads
    print(f"\nLoading {ELECTRICIAN_SHEET_NAME}...")
    elec_ws = outreach_sheet.worksheet(ELECTRICIAN_SHEET_NAME)
    elec_data = elec_ws.get_all_values()

    if elec_data:
        elec_header = elec_data[0]
        for row in elec_data[1:]:
            if not any(row):
                continue
            phone = get_phone_from_row(row, elec_header)
            if phone:
                existing_phones.add(phone)

        print(f"  Loaded {len(elec_data)-1:,} electrician leads")

    # Load Plumbing Leads
    print(f"\nLoading {PLUMBING_SHEET_NAME}...")
    plumb_ws = outreach_sheet.worksheet(PLUMBING_SHEET_NAME)
    plumb_data = plumb_ws.get_all_values()

    if plumb_data:
        plumb_header = plumb_data[0]
        for row in plumb_data[1:]:
            if not any(row):
                continue
            phone = get_phone_from_row(row, plumb_header)
            if phone:
                existing_phones.add(phone)

        print(f"  Loaded {len(plumb_data)-1:,} plumbing leads")

    print(f"\nTotal unique phone numbers: {len(existing_phones):,}")

    return existing_phones


def remove_duplicates_fast(dry_run=True):
    """Remove duplicates by rebuilding sheet with only unique leads."""

    print("\n" + "=" * 60)
    print("REMOVING DUPLICATES (FAST METHOD)")
    print("=" * 60)

    # Connect to Google Sheets
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)

    # Load existing phones from Electrician and Plumbing sheets
    existing_phones = load_existing_phones(client)

    # Load Combined - All States sheet
    print(f"\nLoading {COMBINED_SHEET_NAME}...")
    pe_sheet = client.open_by_key(PE_SHEET_ID)
    combined_ws = pe_sheet.worksheet(COMBINED_SHEET_NAME)

    all_data = combined_ws.get_all_values()

    if not all_data:
        print("ERROR: Combined sheet is empty")
        return

    header = all_data[0]
    data_rows = all_data[1:]

    print(f"  Loaded {len(data_rows):,} rows from Combined sheet")

    # Filter out duplicates
    print("\nFiltering duplicates...")
    kept_rows = [header]  # Start with header
    duplicate_count = 0

    for row in data_rows:
        if not any(row):
            continue

        phone = get_phone_from_row(row, header)

        if phone and phone in existing_phones:
            # This is a duplicate
            duplicate_count += 1
        else:
            # Keep this row
            kept_rows.append(row)

    unique_count = len(kept_rows) - 1  # Exclude header

    print(f"\n✓ Found {duplicate_count:,} duplicates")
    print(f"✓ Keeping {unique_count:,} unique leads")

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - NO CHANGES MADE")
        print("=" * 60)
        print("\nTo apply changes, run with --apply flag")
        return {
            'duplicates_found': duplicate_count,
            'kept_count': unique_count
        }

    # Clear and rebuild sheet
    print("\n" + "=" * 60)
    print("REBUILDING SHEET WITH UNIQUE LEADS")
    print("=" * 60)

    print("\nClearing existing data...")
    combined_ws.clear()

    print("Writing unique leads...")

    # Write in batches
    batch_size = 5000
    for i in range(0, len(kept_rows), batch_size):
        batch = kept_rows[i:i+batch_size]
        start_row = i + 1
        end_row = start_row + len(batch) - 1

        # Calculate column range
        end_col_letter = chr(65 + len(header) - 1) if len(header) <= 26 else 'Z'
        range_name = f'A{start_row}:{end_col_letter}{end_row}'

        print(f"  Writing rows {start_row:,} to {end_row:,}...")

        try:
            combined_ws.update(values=batch, range_name=range_name)
            time.sleep(2)  # Rate limiting
        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"  Waiting 10 seconds and retrying...")
            time.sleep(10)
            combined_ws.update(values=batch, range_name=range_name)
            time.sleep(2)

    print("\n" + "=" * 60)
    print("DEDUPLICATION COMPLETE")
    print("=" * 60)
    print(f"\nBefore: {len(data_rows):,} rows")
    print(f"Removed: {duplicate_count:,} duplicates")
    print(f"After: {unique_count:,} unique rows")
    print("=" * 60)

    return {
        'before': len(data_rows),
        'duplicates_removed': duplicate_count,
        'after': unique_count
    }


def main():
    """Command-line interface."""
    import sys

    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("\n*** DRY RUN MODE ***")
        print("No changes will be made")
        print("Add --apply to actually remove duplicates\n")

    remove_duplicates_fast(dry_run=dry_run)


if __name__ == "__main__":
    main()
