"""
Remove Duplicates from Combined - All States Sheet
Removes any leads that already exist in Electrician or Plumbing sheets
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


def get_unique_identifier(row, header):
    """
    Create unique identifier for a lead.
    Uses phone number if available, otherwise company name + location.
    """
    # Try to find phone column
    phone_cols = ['phone', 'phoneNumber', 'Phone', 'PhoneNumber', 'tel']
    for col in phone_cols:
        if col in header:
            idx = header.index(col)
            if idx < len(row) and row[idx]:
                normalized = normalize_phone(row[idx])
                if normalized:
                    return ('phone', normalized)

    # Try company name + location
    name_cols = ['title', 'companyName', 'company_name', 'name']
    location_cols = ['address', 'companyLocation', 'city', 'location']

    name = None
    location = None

    for col in name_cols:
        if col in header:
            idx = header.index(col)
            if idx < len(row) and row[idx]:
                name = row[idx].strip().lower()
                break

    for col in location_cols:
        if col in header:
            idx = header.index(col)
            if idx < len(row) and row[idx]:
                location = row[idx].strip().lower()
                break

    if name:
        if location:
            return ('name_location', f"{name}|{location}")
        return ('name', name)

    return None


def load_existing_leads(client):
    """Load all leads from Electrician and Plumbing sheets."""

    print("=" * 60)
    print("LOADING EXISTING LEADS")
    print("=" * 60)

    outreach_sheet = client.open_by_key(OUTREACH_SHEET_ID)

    existing_leads = set()

    # Load Electrician Leads
    print(f"\nLoading {ELECTRICIAN_SHEET_NAME}...")
    elec_ws = outreach_sheet.worksheet(ELECTRICIAN_SHEET_NAME)
    elec_data = elec_ws.get_all_values()

    if elec_data:
        elec_header = elec_data[0]
        for row in elec_data[1:]:
            if not any(row):
                continue
            identifier = get_unique_identifier(row, elec_header)
            if identifier:
                existing_leads.add(identifier)

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
            identifier = get_unique_identifier(row, plumb_header)
            if identifier:
                existing_leads.add(identifier)

        print(f"  Loaded {len(plumb_data)-1:,} plumbing leads")

    print(f"\nTotal unique existing leads: {len(existing_leads):,}")

    return existing_leads


def remove_duplicates_from_combined(dry_run=True):
    """Remove duplicates from Combined - All States sheet."""

    print("\n" + "=" * 60)
    print("REMOVING DUPLICATES FROM COMBINED SHEET")
    print("=" * 60)

    # Connect to Google Sheets
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)

    # Load existing leads from Electrician and Plumbing sheets
    existing_leads = load_existing_leads(client)

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

    # Identify duplicates
    print("\nIdentifying duplicates...")
    rows_to_delete = []
    duplicate_leads = []
    kept_rows = []

    for i, row in enumerate(data_rows):
        if not any(row):
            continue

        identifier = get_unique_identifier(row, header)

        if identifier and identifier in existing_leads:
            # This is a duplicate
            row_num = i + 2  # 1-indexed, +1 for header
            rows_to_delete.append(row_num)

            # Get company name for display
            name = "Unknown"
            for col in ['title', 'companyName', 'company_name', 'name']:
                if col in header:
                    idx = header.index(col)
                    if idx < len(row) and row[idx]:
                        name = row[idx]
                        break

            duplicate_leads.append({
                'row': row_num,
                'name': name,
                'identifier': identifier
            })
        else:
            kept_rows.append(row)

    duplicates_found = len(rows_to_delete)
    kept_count = len(kept_rows)

    print(f"\n✓ Found {duplicates_found:,} duplicates to remove")
    print(f"✓ Keeping {kept_count:,} unique leads")

    # Show sample duplicates
    if duplicate_leads:
        print("\nSample duplicates (first 20):")
        for i, dup in enumerate(duplicate_leads[:20], 1):
            print(f"  {i}. Row {dup['row']}: {dup['name']}")

        if len(duplicate_leads) > 20:
            print(f"  ... and {len(duplicate_leads) - 20:,} more")

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - NO CHANGES MADE")
        print("=" * 60)
        print("\nTo apply changes, run with --apply flag")
        return {
            'duplicates_found': duplicates_found,
            'kept_count': kept_count
        }

    # Delete duplicates (in reverse order to avoid index shifting)
    if not rows_to_delete:
        print("\nNo duplicates to remove!")
        return

    print("\n" + "=" * 60)
    print("DELETING DUPLICATES")
    print("=" * 60)

    rows_to_delete.sort(reverse=True)

    deleted_count = 0
    batch_size = 50

    for i in range(0, len(rows_to_delete), batch_size):
        batch = rows_to_delete[i:i+batch_size]

        for row_num in batch:
            try:
                combined_ws.delete_rows(row_num)
                deleted_count += 1

                if deleted_count % 100 == 0:
                    print(f"  Deleted {deleted_count:,}/{duplicates_found:,} rows...")

            except Exception as e:
                print(f"ERROR deleting row {row_num}: {e}")
                time.sleep(5)

        # Rate limiting
        if i + batch_size < len(rows_to_delete):
            print(f"  Batch complete ({deleted_count:,}/{duplicates_found:,}). Waiting 3 seconds...")
            time.sleep(3)

    print(f"\n✓ Successfully deleted {deleted_count:,} duplicate rows")

    # Get final count
    remaining_data = combined_ws.get_all_values()
    remaining_count = len(remaining_data) - 1

    print("\n" + "=" * 60)
    print("DEDUPLICATION COMPLETE")
    print("=" * 60)
    print(f"\nBefore: {len(data_rows):,} rows")
    print(f"Removed: {deleted_count:,} duplicates")
    print(f"After: {remaining_count:,} rows")
    print("=" * 60)

    return {
        'before': len(data_rows),
        'duplicates_removed': deleted_count,
        'after': remaining_count
    }


def main():
    """Command-line interface."""
    import sys

    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("\n*** DRY RUN MODE ***")
        print("No changes will be made")
        print("Add --apply to actually remove duplicates\n")

    remove_duplicates_from_combined(dry_run=dry_run)


if __name__ == "__main__":
    main()
