"""
Run enrichment from a custom source sheet (single-tab structure).
Reads from the source sheet, dedupes against the completed sheet,
enriches each lead, and writes directly to the completed sheet
(routed by industry tab).

Usage:
    python3 run_enrichment_from_sheet.py <source_sheet_id> <batch_size>
"""

import sys
import time
from dotenv import load_dotenv

load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

from perplexity_research import research_lead, compile_research_report
from icebreaker_generator import generate_icebreaker
from lead_enrichment_pipeline_v2 import (
    format_phone_number,
    split_name,
    determine_industry,
    extract_city_state,
    load_processed_emails,
    save_to_completed_sheet,
    save_to_failed_sheet,
    ensure_failed_tab_exists,
)


def get_sheets_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    return gspread.authorize(creds)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 run_enrichment_from_sheet.py <source_sheet_id> <batch_size>")
        sys.exit(1)

    source_sheet_id = sys.argv[1]
    batch_size = int(sys.argv[2])
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 2.5

    client = get_sheets_client()

    print(f"\n{'='*80}", flush=True)
    print(f"ENRICHMENT BATCH RUN", flush=True)
    print(f"Source: {source_sheet_id}", flush=True)
    print(f"Batch: {batch_size}", flush=True)
    print(f"{'='*80}\n", flush=True)

    # Load dedup sets
    print("Loading dedup sets...", flush=True)
    completed_emails, failed_emails = load_processed_emails(client)
    print(f"  Completed: {len(completed_emails)} | Failed: {len(failed_emails)}\n", flush=True)

    # Ensure Failed tab exists
    ensure_failed_tab_exists(client)

    # Load source sheet
    sheet = client.open_by_key(source_sheet_id)
    ws = sheet.sheet1
    data = ws.get_all_values()
    headers = data[0]
    rows = data[1:]
    col_map = {h.lower(): i for i, h in enumerate(headers)}

    print(f"Source sheet loaded: {len(rows)} total rows\n", flush=True)

    # Build lead queue (also dedupes within source sheet, filters to electricians/plumbers only)
    leads = []
    seen_in_batch = set()
    intra_source_dupes = 0
    off_target = 0
    cat_idx = col_map.get('category')
    for row_idx, row in enumerate(rows):
        if len(leads) >= batch_size:
            break

        email_idx = col_map.get('email', col_map.get('valid_email_only'))
        email = row[email_idx].lower().strip() if email_idx is not None and email_idx < len(row) else ''

        if email in completed_emails or email in failed_emails:
            continue
        if email in seen_in_batch:
            intra_source_dupes += 1
            continue
        if not email or '@' not in email:
            continue

        # Industry filter: only electricians and plumbers
        category = row[cat_idx] if cat_idx is not None and cat_idx < len(row) else ''
        industry = determine_industry(category)
        if industry not in ('Electrical', 'Plumbing'):
            off_target += 1
            continue

        seen_in_batch.add(email)

        lead = {'row_index': row_idx + 2, 'state_source': row[col_map.get('state', 0)] if 'state' in col_map else ''}
        for header, idx in col_map.items():
            if idx < len(row):
                lead[header] = row[idx]
        lead['email'] = email
        lead['phoneNumber'] = lead.get('phonenumber', lead.get('phoneNumber', ''))
        leads.append(lead)

    if intra_source_dupes:
        print(f"Skipped {intra_source_dupes} duplicate emails within source sheet", flush=True)
    if off_target:
        print(f"Skipped {off_target} off-target leads (not electrician/plumber)", flush=True)

    print(f"Queued {len(leads)} unprocessed leads\n", flush=True)
    print(f"{'='*80}\n", flush=True)

    results = {'success': 0, 'failed': 0}

    for i, lead in enumerate(leads):
        name = lead.get('person_name', '')
        company = lead.get('title', '')
        category = lead.get('category', '')
        address = lead.get('address', '')
        email = lead.get('email', '')

        first_name, last_name = split_name(name)
        industry = determine_industry(category)
        city, state = extract_city_state(address)
        phone_fmt = format_phone_number(lead.get('phoneNumber', ''))

        print(f"[{i+1}/{len(leads)}] {first_name} {last_name} @ {company} ({industry})", flush=True)

        # Research
        try:
            dm_research, company_research = research_lead(
                first_name=first_name, last_name=last_name,
                company_name=company, city=city, state=state,
                industry=industry, delay_between_calls=2.0
            )
            report = compile_research_report(first_name, last_name, company, dm_research, company_research)
        except Exception as e:
            print(f"  ! RESEARCH ERROR: {e}", flush=True)
            results['failed'] += 1
            save_to_failed_sheet(client, lead, f'Research error: {e}', state)
            continue

        # Icebreaker
        try:
            has_data = (
                (dm_research and '[NOT PROVIDED]' not in dm_research[:300]) or
                (company_research and '[NOT PROVIDED]' not in company_research[:300])
            )
            icebreaker = None
            if has_data:
                icebreaker = generate_icebreaker(
                    research_report=report, first_name=first_name,
                    last_name=last_name, company_name=company, industry=industry
                )

            if not icebreaker:
                # No personalized icebreaker — skip to Failed tab, do NOT save to completed sheet
                reason = (
                    'No useful research data' if not has_data
                    else 'Icebreaker rejected (hallucination/length/refusal)'
                )
                print(f"  >> [SKIPPED] {reason}\n", flush=True)
                save_to_failed_sheet(client, lead, reason, state)
                results.setdefault('skipped', 0)
                results['skipped'] += 1
                if i < len(leads) - 1:
                    time.sleep(delay)
                continue
        except Exception as e:
            print(f"  ! ICEBREAKER ERROR: {e}", flush=True)
            results['failed'] += 1
            save_to_failed_sheet(client, lead, f'Icebreaker error: {e}', state)
            continue

        print(f"  >> {icebreaker}", flush=True)

        # Save to completed sheet
        enriched = {
            'company_name': company,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone_fmt,
            'address': address,
            'website': lead.get('website', ''),
            'job_title': lead.get('result_title', ''),
            'industry': industry,
            'research_report': report,
            'icebreaker': icebreaker,
        }

        saved = save_to_completed_sheet(client, enriched)
        if saved:
            results['success'] += 1
            completed_emails.add(email.lower())
            print(f"  + Saved to {industry} tab\n", flush=True)
        else:
            results['failed'] += 1
            print(f"  ! Save failed\n", flush=True)

        if i < len(leads) - 1:
            time.sleep(delay)

    print(f"\n{'='*80}", flush=True)
    print(f"BATCH COMPLETE", flush=True)
    print(f"  Saved to completed: {results['success']}", flush=True)
    print(f"  Skipped (no good icebreaker): {results.get('skipped', 0)} (logged to Failed tab)", flush=True)
    print(f"  Failed (errors): {results['failed']}", flush=True)
    print(f"{'='*80}\n", flush=True)


if __name__ == "__main__":
    main()
