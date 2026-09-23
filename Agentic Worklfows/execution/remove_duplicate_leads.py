"""
Remove Duplicate Leads - Prevent paying for the same lead twice
================================================================

This script compares verified leads in Master CRM v2 with freshly scraped leads
and removes duplicates from the scraped leads sheet to prevent double-payment.

Process:
1. Read all HVAC leads from Master CRM v2 (verified, paid leads)
2. Read all HVAC leads from Scraped Leads sheet
3. Identify duplicates using phone number and company name
4. Remove duplicate rows from Scraped Leads HVAC tab ONLY
5. Report statistics

Master CRM v2 is NEVER modified - it's the source of truth.
"""

import os
import sys
from typing import Set, List, Dict
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from google_sheets_client import get_sheets_client, open_sheet

# Load environment variables
load_dotenv()

# Sheet IDs
MASTER_CRM_SHEET_ID = "1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8"
SCRAPED_LEADS_SHEET_ID = "1pqHEYgGOVgf5tcYdcuNQiUArVf3MvavJ9DRlyHsm_2A"

# Tab names
MASTER_CRM_HVAC_TAB = "HVAC Leads"
SCRAPED_LEADS_HVAC_TAB = "Hvac"


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number for comparison.
    Removes all non-digit characters.
    """
    if not phone:
        return ""
    return ''.join(c for c in str(phone) if c.isdigit())


def normalize_company(company: str) -> str:
    """
    Normalize company name for comparison.
    Lowercase, strip whitespace, remove common suffixes.
    """
    if not company:
        return ""

    company = str(company).lower().strip()

    # Remove common business suffixes
    suffixes = [
        ' llc', ' inc', ' incorporated', ' corp', ' corporation',
        ' ltd', ' limited', ' co', ' company', ',', '.'
    ]
    for suffix in suffixes:
        if company.endswith(suffix):
            company = company[:-len(suffix)].strip()

    return company


def create_lead_signature(row: List, phone_col: int, company_col: int) -> tuple:
    """
    Create a unique signature for a lead based on phone and company name.
    Returns tuple of (normalized_phone, normalized_company).
    """
    phone = row[phone_col] if phone_col < len(row) else ""
    company = row[company_col] if company_col < len(row) else ""

    return (normalize_phone(phone), normalize_company(company))


def find_column_index(headers: List[str], possible_names: List[str]) -> int:
    """
    Find column index by checking multiple possible header names.
    Returns -1 if not found.
    """
    headers_lower = [h.lower().strip() for h in headers]

    for name in possible_names:
        name_lower = name.lower().strip()
        if name_lower in headers_lower:
            return headers_lower.index(name_lower)

    return -1


def main(auto_confirm: bool = False):
    print("\n" + "="*70)
    print("DUPLICATE LEAD REMOVAL - Prevent Double Payment")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Step 1: Authenticate
    print("🔐 Authenticating with Google Sheets...")
    creds_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")

    if not os.path.exists(creds_path):
        print(f"❌ credentials.json not found at: {creds_path}")
        return

    client = get_sheets_client(creds_path)

    # Step 2: Read Master CRM v2 HVAC (source of truth)
    print(f"\n📖 Reading Master CRM v2 - HVAC Leads tab (READ ONLY)...")
    try:
        master_ws = open_sheet(client, MASTER_CRM_SHEET_ID, MASTER_CRM_HVAC_TAB)
    except ValueError as e:
        if "not found" in str(e).lower():
            print(f"❌ HVAC tab not found in Master CRM v2")
            print(f"   Available tabs: Check the sheet manually")
            return
        raise

    master_data = master_ws.get_all_values()

    if not master_data:
        print("⚠️  Master CRM HVAC tab is empty!")
        return

    master_headers = master_data[0]
    master_rows = master_data[1:]

    print(f"   ✓ Found {len(master_rows)} leads in Master CRM")

    # Find phone and company columns in Master CRM
    master_phone_col = find_column_index(master_headers, ['phone', 'phone_number', 'phone number'])
    master_company_col = find_column_index(master_headers, ['company', 'company_name', 'company name', 'business', 'business_name'])

    if master_phone_col == -1:
        print(f"⚠️  Could not find phone column in Master CRM")
        print(f"   Headers: {master_headers}")
        print(f"   Please verify column names")
        return

    if master_company_col == -1:
        print(f"⚠️  Could not find company column in Master CRM")
        print(f"   Headers: {master_headers}")
        print(f"   Please verify column names")
        return

    print(f"   ✓ Phone column: {master_headers[master_phone_col]} (index {master_phone_col})")
    print(f"   ✓ Company column: {master_headers[master_company_col]} (index {master_company_col})")

    # Build signature set from Master CRM
    print(f"\n🔍 Building signature set from Master CRM leads...")
    master_signatures = set()

    for row in master_rows:
        sig = create_lead_signature(row, master_phone_col, master_company_col)
        # Only add if we have at least phone or company
        if sig[0] or sig[1]:
            master_signatures.add(sig)

    print(f"   ✓ Created {len(master_signatures)} unique signatures from Master CRM")

    # Step 3: Read Scraped Leads HVAC
    print(f"\n📖 Reading Scraped Leads - Hvac tab (WILL BE MODIFIED)...")
    try:
        scraped_ws = open_sheet(client, SCRAPED_LEADS_SHEET_ID, SCRAPED_LEADS_HVAC_TAB)
    except ValueError as e:
        if "not found" in str(e).lower():
            print(f"❌ HVAC tab not found in Scraped Leads sheet")
            print(f"   Available tabs: Check the sheet manually")
            return
        raise

    scraped_data = scraped_ws.get_all_values()

    if not scraped_data:
        print("⚠️  Scraped Leads HVAC tab is empty!")
        return

    scraped_headers = scraped_data[0]
    scraped_rows = scraped_data[1:]

    print(f"   ✓ Found {len(scraped_rows)} leads in Scraped Leads")

    # Find phone and company columns in Scraped Leads
    scraped_phone_col = find_column_index(scraped_headers, ['phone', 'phone_number', 'phone number'])
    scraped_company_col = find_column_index(scraped_headers, ['company', 'company_name', 'company name', 'business', 'business_name'])

    if scraped_phone_col == -1:
        print(f"⚠️  Could not find phone column in Scraped Leads")
        print(f"   Headers: {scraped_headers}")
        return

    if scraped_company_col == -1:
        print(f"⚠️  Could not find company column in Scraped Leads")
        print(f"   Headers: {scraped_headers}")
        return

    print(f"   ✓ Phone column: {scraped_headers[scraped_phone_col]} (index {scraped_phone_col})")
    print(f"   ✓ Company column: {scraped_headers[scraped_company_col]} (index {scraped_company_col})")

    # Step 4: Identify duplicates in Scraped Leads
    print(f"\n🔍 Identifying duplicates...")

    duplicate_indices = []
    unique_rows = []

    for i, row in enumerate(scraped_rows):
        sig = create_lead_signature(row, scraped_phone_col, scraped_company_col)

        if sig in master_signatures:
            # This is a duplicate - already in Master CRM
            duplicate_indices.append(i + 2)  # +2 because 0-indexed and header row
        else:
            # This is unique - keep it
            unique_rows.append(row)

    duplicates_found = len(duplicate_indices)

    print(f"\n📊 Results:")
    print(f"   • Total scraped leads: {len(scraped_rows)}")
    print(f"   • Duplicates found: {duplicates_found}")
    print(f"   • Unique leads to keep: {len(unique_rows)}")

    if duplicates_found == 0:
        print(f"\n✅ No duplicates found! All scraped leads are unique.")
        return

    # Step 5: Confirm before deletion
    print(f"\n⚠️  WARNING: About to remove {duplicates_found} duplicate leads from Scraped Leads HVAC tab")
    print(f"   Master CRM will NOT be modified.")

    if not auto_confirm:
        confirm = input(f"\n   Type 'DELETE' to proceed: ").strip()

        if confirm != 'DELETE':
            print(f"\n❌ Cancelled. No changes made.")
            return
    else:
        print(f"\n✓ Auto-confirm enabled. Proceeding with deletion...")

    # Step 6: Remove duplicates from Scraped Leads
    print(f"\n🗑️  Removing duplicates from Scraped Leads...")

    # Clear the sheet and rewrite with header + unique rows
    scraped_ws.clear()

    # Write headers
    scraped_ws.update('A1', [scraped_headers])

    # Write unique rows (if any)
    if unique_rows:
        scraped_ws.update(f'A2', unique_rows)

    print(f"   ✓ Removed {duplicates_found} duplicate leads")
    print(f"   ✓ Kept {len(unique_rows)} unique leads")

    # Step 7: Final summary
    print(f"\n" + "="*70)
    print(f"✅ DUPLICATE REMOVAL COMPLETE")
    print(f"="*70)
    print(f"Master CRM HVAC: {len(master_rows)} leads (unchanged)")
    print(f"Scraped Leads HVAC: {len(scraped_rows)} → {len(unique_rows)} leads")
    print(f"Duplicates removed: {duplicates_found}")
    print(f"\nYou will NOT be charged for the {duplicates_found} duplicate leads.")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")


if __name__ == "__main__":
    # Check for --confirm flag
    auto_confirm = '--confirm' in sys.argv or '-y' in sys.argv

    try:
        main(auto_confirm=auto_confirm)
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
