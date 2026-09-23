"""
Lead Enrichment Pipeline v2
Full pipeline with:
- Deduplication against completed + failed sheets (by email)
- Phone number formatting (remove country codes)
- Industry-based routing to correct sheet
- Failed leads tracking
"""

import os
import time
import logging
import re
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime

from perplexity_research import research_lead, compile_research_report
from icebreaker_generator import generate_icebreaker, generate_fallback_icebreaker

load_dotenv()

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sheet IDs
COMPLETED_SHEET_ID = "1JVhfoBlaPiTGqvnBPz32tL-h69U9GMInnSvLNRwZnh0"
INCOMPLETE_SHEET_ID = "1buDQoo3acX8kNgrfLHcO96mRCeGAz-7wgT7XVz8b_pE"

# Industry to tab mapping
INDUSTRY_TAB_MAP = {
    'HVAC': 'HVAC Leads',
    'Roofing': 'Roofing Leads',
    'Plumbing': 'Plumbing Leads',
    'Electrical': 'Electrician Leads',
    'Home Services': 'HVAC Leads'
}


def get_sheets_client():
    """Initialize Google Sheets client"""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    return gspread.authorize(creds)


# ============================================================================
# PHONE NUMBER FORMATTING
# ============================================================================

def format_phone_number(phone: str) -> str:
    """
    Format phone number to just 10 digits (no country code).

    Examples:
        +1 559-550-6398 → 5595506398
        +1 (555) 123-4567 → 5551234567
        15551234567 → 5551234567
        555-123-4567 → 5551234567
    """
    if not phone:
        return ""

    digits = re.sub(r'\D', '', str(phone))

    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]

    return digits


# ============================================================================
# NAME PARSING
# ============================================================================

def split_name(full_name: str) -> Tuple[str, str]:
    """
    Split full name into first and last name.

    Examples:
        "Mike Feazel" → ("Mike", "Feazel")
        "John" → ("John", "")
        "Mary Jane Watson" → ("Mary", "Jane Watson")
    """
    if not full_name:
        return "", ""

    parts = full_name.strip().split()
    if len(parts) == 0:
        return "", ""
    elif len(parts) == 1:
        return parts[0], ""
    else:
        return parts[0], " ".join(parts[1:])


# ============================================================================
# INDUSTRY DETECTION
# ============================================================================

def determine_industry(category: str) -> str:
    """Determine industry from Google Maps category."""
    if not category:
        return 'Home Services'

    category_lower = category.lower()

    if any(x in category_lower for x in ['hvac', 'air conditioning', 'heating', 'cooling', 'furnace', 'heat']):
        return 'HVAC'
    elif any(x in category_lower for x in ['roof', 'roofing']):
        return 'Roofing'
    elif any(x in category_lower for x in ['plumb', 'plumbing', 'drain', 'sewer', 'water heater']):
        return 'Plumbing'
    elif any(x in category_lower for x in ['electric', 'electrical', 'electrician']):
        return 'Electrical'
    else:
        return 'Home Services'


# ============================================================================
# DEDUPLICATION
# ============================================================================

def load_processed_emails(client) -> Tuple[Set[str], Set[str]]:
    """
    Load all emails from completed sheet and failed sheet for deduplication.

    Returns:
        Tuple of (completed_emails, failed_emails)
    """
    logger.info("Loading processed emails for deduplication...")

    completed_emails = set()
    failed_emails = set()

    # Load from completed sheet
    try:
        completed_sheet = client.open_by_key(COMPLETED_SHEET_ID)
        for ws in completed_sheet.worksheets():
            data = ws.get_all_records()
            for row in data:
                email = str(row.get('email', '')).lower().strip()
                if email and '@' in email:
                    completed_emails.add(email)
        logger.info(f"  Completed sheet: {len(completed_emails)} unique emails")
    except Exception as e:
        logger.error(f"Error loading completed sheet: {e}")

    # Load from failed tab (if exists)
    try:
        incomplete_sheet = client.open_by_key(INCOMPLETE_SHEET_ID)
        try:
            failed_ws = incomplete_sheet.worksheet('Failed')
            data = failed_ws.get_all_records()
            for row in data:
                email = str(row.get('email', '')).lower().strip()
                if email and '@' in email:
                    failed_emails.add(email)
            logger.info(f"  Failed sheet: {len(failed_emails)} unique emails")
        except gspread.WorksheetNotFound:
            logger.info("  Failed sheet: Not found (will be created)")
    except Exception as e:
        logger.error(f"Error loading failed sheet: {e}")

    return completed_emails, failed_emails


def ensure_failed_tab_exists(client) -> gspread.Worksheet:
    """Ensure the Failed tab exists in the incomplete sheet."""
    incomplete_sheet = client.open_by_key(INCOMPLETE_SHEET_ID)

    try:
        return incomplete_sheet.worksheet('Failed')
    except gspread.WorksheetNotFound:
        logger.info("Creating 'Failed' tab in incomplete sheet...")
        ws = incomplete_sheet.add_worksheet(title='Failed', rows=1000, cols=15)

        headers = [
            'email', 'person_name', 'company', 'category', 'address',
            'phone', 'website', 'failure_reason',
            'failed_at', 'state', 'original_row'
        ]
        ws.append_row(headers)

        logger.info("'Failed' tab created successfully")
        return ws


# ============================================================================
# LEAD PROCESSING
# ============================================================================

def extract_city_state(address: str) -> Tuple[str, str]:
    """Extract city and state from address string"""
    if not address:
        return "", ""

    parts = address.split(',')

    if len(parts) >= 3:
        city_part = parts[-3].strip() if len(parts) >= 3 else ""
        state_part = parts[-2].strip() if len(parts) >= 2 else ""

        state_match = re.search(r'\b([A-Z]{2})\b', state_part)
        state = state_match.group(1) if state_match else ""

        city = city_part.split()[-1] if city_part else ""

        return city, state

    return "", ""


def process_single_lead(
    lead: Dict,
    completed_emails: Set[str],
    failed_emails: Set[str],
    delay: float = 2.0
) -> Tuple[str, Optional[Dict], Optional[str]]:
    """
    Process a single lead through the enrichment pipeline.

    Returns:
        Tuple of (status, enriched_lead, failure_reason)
        status: 'success', 'skipped', 'failed'
    """
    email = str(lead.get('email', '')).lower().strip()

    # Deduplication check
    if email in completed_emails:
        return 'skipped', None, 'Already in completed sheet'

    if email in failed_emails:
        return 'skipped', None, 'Already in failed sheet'

    if not email or '@' not in email:
        return 'failed', lead, 'Invalid or missing email'

    # Parse and format data
    full_name = lead.get('person_name', '')
    first_name, last_name = split_name(full_name)

    company_name = lead.get('title', lead.get('company', ''))
    phone = format_phone_number(lead.get('phoneNumber', ''))
    category = lead.get('category', '')
    industry = determine_industry(category)
    address = lead.get('address', '')
    city, state = extract_city_state(address)
    website = lead.get('website', '')

    if not company_name:
        return 'failed', lead, 'Missing company name'

    logger.info(f"Processing: {first_name} {last_name} at {company_name} ({industry})")

    # Perplexity research
    try:
        dm_research, company_research = research_lead(
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            city=city,
            state=state,
            industry=industry,
            delay_between_calls=delay
        )
    except Exception as e:
        logger.error(f"Research failed: {str(e)}")
        return 'failed', lead, f'Research error: {str(e)}'

    # Compile research report
    research_report = compile_research_report(
        first_name, last_name, company_name,
        dm_research, company_research
    )

    # Generate icebreaker
    try:
        has_useful_data = (
            (dm_research and "[NOT PROVIDED]" not in dm_research[:300]) or
            (company_research and "[NOT PROVIDED]" not in company_research[:300])
        )

        if has_useful_data:
            icebreaker = generate_icebreaker(
                research_report=research_report,
                first_name=first_name,
                last_name=last_name,
                company_name=company_name,
                industry=industry
            )
        else:
            icebreaker = generate_fallback_icebreaker(
                company_name=company_name,
                industry=industry,
                city=city,
                state=state
            )

        if not icebreaker:
            icebreaker = generate_fallback_icebreaker(company_name, industry, city, state)

    except Exception as e:
        logger.error(f"Icebreaker generation failed: {str(e)}")
        return 'failed', lead, f'Icebreaker error: {str(e)}'

    # Build enriched lead
    enriched_lead = {
        'company_name': company_name,
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'address': address,
        'website': website,
        'job_title': lead.get('result_title', ''),
        'industry': industry,
        'research_report': research_report,
        'icebreaker': icebreaker,
        'state_source': lead.get('state_source', '')
    }

    return 'success', enriched_lead, None


# ============================================================================
# SHEET OPERATIONS
# ============================================================================

def save_to_completed_sheet(client, lead: Dict) -> bool:
    """Save enriched lead to the correct industry tab in completed sheet."""
    industry = lead.get('industry', 'HVAC')
    tab_name = INDUSTRY_TAB_MAP.get(industry, 'HVAC Leads')

    try:
        spreadsheet = client.open_by_key(COMPLETED_SHEET_ID)
        ws = spreadsheet.worksheet(tab_name)

        row = [
            lead.get('company_name', ''),
            lead.get('first_name', ''),
            lead.get('last_name', ''),
            lead.get('research_report', ''),
            lead.get('address', ''),
            'valid',
            lead.get('email', ''),
            lead.get('phone', ''),
            lead.get('job_title', ''),
            '',  # linkedin_url removed
            lead.get('website', ''),
            lead.get('icebreaker', '')
        ]

        ws.append_row(row, value_input_option='RAW')
        logger.info(f"  Saved to {tab_name}")
        return True

    except Exception as e:
        logger.error(f"Error saving to completed sheet: {str(e)}")
        return False


def save_to_failed_sheet(client, lead: Dict, reason: str, state: str) -> bool:
    """Save failed lead to the Failed tab."""
    try:
        failed_ws = ensure_failed_tab_exists(client)

        row = [
            lead.get('email', ''),
            lead.get('person_name', ''),
            lead.get('title', lead.get('company', '')),
            lead.get('category', ''),
            lead.get('address', ''),
            lead.get('phoneNumber', ''),
            lead.get('website', ''),
            reason,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            state,
            str(lead.get('row_index', ''))
        ]

        failed_ws.append_row(row, value_input_option='RAW')
        logger.info(f"  Saved to Failed tab: {reason}")
        return True

    except Exception as e:
        logger.error(f"Error saving to failed sheet: {str(e)}")
        return False


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def get_unprocessed_leads(
    client,
    state: str,
    limit: int,
    completed_emails: Set[str],
    failed_emails: Set[str]
) -> List[Dict]:
    """Get unprocessed leads from a state tab."""
    logger.info(f"Loading leads from {state}...")

    try:
        spreadsheet = client.open_by_key(INCOMPLETE_SHEET_ID)
        ws = spreadsheet.worksheet(state)
    except gspread.WorksheetNotFound:
        logger.error(f"State tab '{state}' not found")
        return []

    data = ws.get_all_values()
    if len(data) < 2:
        return []

    headers = data[0]
    rows = data[1:]

    col_map = {h.lower(): i for i, h in enumerate(headers)}

    leads = []
    for row_idx, row in enumerate(rows):
        if len(leads) >= limit:
            break

        email_idx = col_map.get('email', col_map.get('valid_email_only'))
        email = row[email_idx].lower().strip() if email_idx is not None and email_idx < len(row) else ''

        if email in completed_emails or email in failed_emails:
            continue

        if not email or '@' not in email:
            continue

        lead = {'row_index': row_idx + 2, 'state_source': state}

        for header, idx in col_map.items():
            if idx < len(row):
                lead[header] = row[idx]

        lead['person_name'] = lead.get('person_name', '')
        lead['email'] = email
        lead['title'] = lead.get('title', '')
        lead['category'] = lead.get('category', '')
        lead['address'] = lead.get('address', '')
        lead['phoneNumber'] = lead.get('phonenumber', lead.get('phoneNumber', ''))
        lead['website'] = lead.get('website', '')
        lead['result_title'] = lead.get('result_title', '')

        leads.append(lead)

    logger.info(f"Found {len(leads)} unprocessed leads")
    return leads


def run_pipeline(
    state: str,
    batch_size: int = 100,
    delay_between_leads: float = 3.0,
    test_mode: bool = False
) -> Dict:
    """
    Run the full enrichment pipeline.

    Args:
        state: State tab to process
        batch_size: Number of leads to process
        delay_between_leads: Seconds between leads
        test_mode: If True, don't save to sheets

    Returns:
        Summary dict
    """
    start_time = datetime.now()

    logger.info("=" * 70)
    logger.info("LEAD ENRICHMENT PIPELINE v2")
    logger.info("=" * 70)
    logger.info(f"State: {state}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Test mode: {test_mode}")
    logger.info("=" * 70)

    client = get_sheets_client()

    # Load processed emails for deduplication
    completed_emails, failed_emails = load_processed_emails(client)

    if not test_mode:
        ensure_failed_tab_exists(client)

    # Get unprocessed leads
    leads = get_unprocessed_leads(client, state, batch_size, completed_emails, failed_emails)

    if not leads:
        logger.warning("No unprocessed leads found!")
        return {'state': state, 'processed': 0, 'success': 0, 'failed': 0, 'skipped': 0}

    # Process leads
    results = {'success': 0, 'failed': 0, 'skipped': 0}

    for i, lead in enumerate(leads):
        logger.info(f"\n[{i+1}/{len(leads)}] {lead.get('person_name', 'Unknown')} @ {lead.get('title', 'Unknown')}")

        status, enriched_lead, failure_reason = process_single_lead(
            lead=lead,
            completed_emails=completed_emails,
            failed_emails=failed_emails,
            delay=2.0
        )

        if status == 'success' and enriched_lead:
            if not test_mode:
                saved = save_to_completed_sheet(client, enriched_lead)
                if saved:
                    results['success'] += 1
                    completed_emails.add(enriched_lead['email'].lower())
                else:
                    results['failed'] += 1
            else:
                logger.info(f"  [TEST] Would save: {enriched_lead['company_name']}")
                logger.info(f"  [TEST] Industry: {enriched_lead['industry']}")
                logger.info(f"  [TEST] Icebreaker: {enriched_lead['icebreaker'][:80]}...")
                results['success'] += 1

        elif status == 'skipped':
            results['skipped'] += 1
            logger.info(f"  Skipped: {failure_reason}")

        elif status == 'failed':
            results['failed'] += 1
            if not test_mode and lead:
                save_to_failed_sheet(client, lead, failure_reason or 'Unknown error', state)

        # Rate limiting
        if i < len(leads) - 1:
            time.sleep(delay_between_leads)

    # Summary
    duration = (datetime.now() - start_time).total_seconds()

    summary = {
        'state': state,
        'total_found': len(leads),
        'processed': results['success'] + results['failed'],
        'success': results['success'],
        'failed': results['failed'],
        'skipped': results['skipped'],
        'duration_seconds': round(duration, 1)
    }

    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"State: {state}")
    logger.info(f"Success: {results['success']}")
    logger.info(f"Failed: {results['failed']}")
    logger.info(f"Skipped: {results['skipped']}")
    logger.info(f"Duration: {duration:.1f} seconds")

    return summary


def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Lead Enrichment Pipeline v2')
    parser.add_argument('--state', type=str, required=True, help='State to process')
    parser.add_argument('--batch', type=int, default=100, help='Batch size (default: 100)')
    parser.add_argument('--delay', type=float, default=3.0, help='Delay between leads (default: 3.0)')
    parser.add_argument('--test', action='store_true', help='Test mode (no saving)')

    args = parser.parse_args()

    run_pipeline(
        state=args.state,
        batch_size=args.batch,
        delay_between_leads=args.delay,
        test_mode=args.test
    )


if __name__ == "__main__":
    main()
