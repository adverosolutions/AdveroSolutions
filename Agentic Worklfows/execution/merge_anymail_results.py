"""
Merge AnyMailFinder Results Back to Master CRM v2
Safely matches by phone number to avoid data corruption
"""

import gspread
from google.oauth2.service_account import Credentials
import csv
import sys
import time
from typing import Dict, List

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDS_PATH = '/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows/credentials.json'

MASTER_CRM_SHEET_ID = '1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8'
MASTER_CRM_TAB = 'Landscaping'


def load_anymail_results(csv_path: str) -> Dict[str, Dict]:
    """
    Load AnyMailFinder results and create phone -> email/decision maker lookup.

    Args:
        csv_path: Path to AnyMailFinder results CSV

    Returns:
        Dict mapping phone numbers to email data
    """
    phone_to_data = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # AnyMailFinder columns may vary, adapt as needed
            phone = row.get('Phone', '').strip()
            email = row.get('Email', '').strip()
            name = row.get('Decision Maker Name', '').strip()
            title = row.get('Decision Maker Title', '').strip()
            linkedin = row.get('LinkedIn', '').strip()
            email_status = row.get('Email Status', '').strip()

            if phone:
                phone_to_data[phone] = {
                    'email': email,
                    'name': name,
                    'title': title,
                    'linkedin': linkedin,
                    'email_status': email_status
                }

    return phone_to_data


def merge_to_master_crm(csv_path: str, dry_run: bool = True):
    """
    Merge AnyMailFinder results to Master CRM v2 by phone number.

    Args:
        csv_path: Path to AnyMailFinder results CSV
        dry_run: If True, only show what would be updated
    """
    print("=" * 60)
    print("MERGING ANYMAILFINDER RESULTS TO MASTER CRM V2")
    print("=" * 60)

    # Load AnyMailFinder results
    print(f"Loading AnyMailFinder results from: {csv_path}")
    phone_to_data = load_anymail_results(csv_path)
    print(f"Loaded {len(phone_to_data)} results from AnyMailFinder")

    # Connect to Master CRM
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(MASTER_CRM_SHEET_ID)
    ws = sheet.worksheet(MASTER_CRM_TAB)

    print(f"Loading Master CRM v2 - {MASTER_CRM_TAB}...")
    all_data = ws.get_all_values()

    if not all_data:
        print("ERROR: Master CRM sheet is empty")
        return

    header = all_data[0]
    data_rows = all_data[1:]

    print(f"Master CRM has {len(data_rows)} rows")

    # Find column indexes
    phone_idx = header.index('phone')

    # Email columns to update (create if don't exist)
    email_cols = {
        'email': 'email',
        'person_name': 'person_name',
        'person_title': 'person_title',
        'person_linkedin': 'person_linkedin',
        'email_status': 'email_status'
    }

    # Get or create column indexes
    col_indexes = {}
    for key, col_name in email_cols.items():
        if col_name in header:
            col_indexes[key] = header.index(col_name)
        else:
            # Will need to add this column
            col_indexes[key] = len(header)
            header.append(col_name)

    # Track updates
    matched = 0
    updated = 0
    no_email_found = 0

    updates_to_make = []

    # Process each row
    for i, row in enumerate(data_rows):
        # Ensure row is long enough
        while len(row) < len(header):
            row.append('')

        phone = row[phone_idx].strip()

        if phone in phone_to_data:
            matched += 1
            email_data = phone_to_data[phone]

            # Check if we have email
            if email_data['email']:
                # Prepare update
                row_num = i + 2  # 1-indexed, +1 for header

                updates = {
                    'row_num': row_num,
                    'phone': phone,
                    'email': email_data['email'],
                    'name': email_data['name'],
                    'title': email_data['title'],
                    'linkedin': email_data['linkedin'],
                    'status': email_data['email_status']
                }

                updates_to_make.append(updates)
                updated += 1

                # Update row data for display
                row[col_indexes['email']] = email_data['email']
                row[col_indexes['person_name']] = email_data['name']
                row[col_indexes['person_title']] = email_data['title']
                row[col_indexes['person_linkedin']] = email_data['linkedin']
                row[col_indexes['email_status']] = email_data['email_status']
            else:
                no_email_found += 1

    # Show summary
    print("\n" + "=" * 60)
    print("MERGE SUMMARY")
    print("=" * 60)
    print(f"Matched by phone: {matched}")
    print(f"With valid emails: {updated}")
    print(f"No email found: {no_email_found}")
    print(f"Not matched: {len(data_rows) - matched}")

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - NO CHANGES MADE")
        print("=" * 60)
        print("\nSample of updates (first 10):")
        for i, update in enumerate(updates_to_make[:10], 1):
            print(f"\n{i}. Row {update['row_num']} - {update['phone']}")
            print(f"   Email: {update['email']}")
            print(f"   Name: {update['name']}")
            print(f"   Title: {update['title']}")

        if len(updates_to_make) > 10:
            print(f"\n... and {len(updates_to_make) - 10} more")

        print("\nTo apply changes, run: python merge_anymail_results.py <csv_path> --apply")
        return

    # Apply updates
    print("\n" + "=" * 60)
    print("APPLYING UPDATES")
    print("=" * 60)

    # Batch update in chunks
    batch_size = 50
    applied = 0

    for i in range(0, len(updates_to_make), batch_size):
        batch = updates_to_make[i:i+batch_size]

        # Prepare batch update data
        batch_data = []
        for update in batch:
            row_num = update['row_num']

            # Update each column
            batch_data.append({
                'range': f'{chr(65 + col_indexes["email"])}{row_num}',
                'values': [[update['email']]]
            })
            batch_data.append({
                'range': f'{chr(65 + col_indexes["person_name"])}{row_num}',
                'values': [[update['name']]]
            })
            batch_data.append({
                'range': f'{chr(65 + col_indexes["person_title"])}{row_num}',
                'values': [[update['title']]]
            })
            batch_data.append({
                'range': f'{chr(65 + col_indexes["person_linkedin"])}{row_num}',
                'values': [[update['linkedin']]]
            })
            batch_data.append({
                'range': f'{chr(65 + col_indexes["email_status"])}{row_num}',
                'values': [[update['status']]]
            })

        # Apply batch
        try:
            ws.batch_update(batch_data)
            applied += len(batch)
            print(f"  Applied {applied}/{len(updates_to_make)} updates...")
            time.sleep(2)  # Rate limiting
        except Exception as e:
            print(f"ERROR on batch {i//batch_size + 1}: {e}")
            time.sleep(5)

    print(f"\n✓ Successfully applied {applied} updates to Master CRM v2")
    print("=" * 60)
    print("MERGE COMPLETE")
    print("=" * 60)

    return {
        'matched': matched,
        'updated': updated,
        'no_email_found': no_email_found,
        'applied': applied
    }


def main():
    """Command-line interface."""
    if len(sys.argv) < 2:
        print("Usage: python merge_anymail_results.py <anymail_results.csv> [--apply]")
        print("\nWithout --apply, runs in dry-run mode (no changes)")
        sys.exit(1)

    csv_path = sys.argv[1]
    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("\n*** DRY RUN MODE ***")
        print("No changes will be made to Master CRM v2")
        print("Add --apply to actually update the sheet\n")

    merge_to_master_crm(csv_path, dry_run=dry_run)


if __name__ == "__main__":
    main()
