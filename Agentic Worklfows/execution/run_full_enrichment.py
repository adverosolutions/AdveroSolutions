"""
Full Enrichment Orchestrator (Free Email Pipeline)
====================================================
Chains all 5 enrichment components on a Google Sheet of scraped leads:

  free gates → website scrape → discover_owner → verify patterns →
  confidence tag → icebreaker → save to completed sheet

Cost-gated: never runs paid Perplexity / MillionVerifier calls on dead-end leads.

Usage:
    python3 run_full_enrichment.py <source_sheet_id> <batch_size>

Output:
  - Verified leads with HIGH/MEDIUM confidence emails → completed sheet (industry tab)
  - LOW confidence (generic info@) → completed sheet, tagged in dataProcessorSummary
  - REJECT (no email found) / errors → Failed tab with reason
"""

import os
import sys
import time
import socket
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(_env_path, override=True)

import gspread
from google.oauth2.service_account import Credentials

from discover_owner import discover_owner_and_research
from scrape_website_emails import scrape_website_emails
from generate_email_patterns import generate_owner_patterns, extract_domain
from verify_emails_bulk import verify_emails, check_credits
from tag_email_confidence import select_best_email
from icebreaker_generator import generate_icebreaker
from lookup_whois_email import lookup_domain_email

from lead_enrichment_pipeline_v2 import (
    format_phone_number,
    determine_industry,
    extract_city_state,
    load_processed_emails,
    save_to_completed_sheet,
    save_to_failed_sheet,
    ensure_failed_tab_exists,
)

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
MAX_PATTERNS_TO_VERIFY = 6
SAFE_INDUSTRIES = {'Electrical', 'Plumbing'}


def get_sheets_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'credentials.json'
    )
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)


# ----------------------------------------------------------------------------
# FREE GATES — cheap checks before any paid API call
# ----------------------------------------------------------------------------

def domain_has_mx(domain: str) -> bool:
    """Quick DNS lookup to confirm domain accepts mail. Free, ~50ms."""
    if not domain:
        return False
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def can_extract_domain(website: str, email: str) -> Optional[str]:
    """Get a usable domain from website OR existing email."""
    if website:
        d = extract_domain(website)
        if d:
            return d
    if email and '@' in email:
        return email.split('@', 1)[1].lower().strip()
    return None


# ----------------------------------------------------------------------------
# Per-lead pipeline
# ----------------------------------------------------------------------------

def process_lead(lead: Dict) -> Dict:
    """
    Run a single lead through the full gated pipeline.

    Returns:
        dict with keys: status, reason, enriched (or None)
        status: 'saved' | 'rejected' | 'failed'
    """
    company = lead.get('title', lead.get('company', '')).strip()
    category = lead.get('category', '').strip()
    address = lead.get('address', '')
    website = lead.get('website', '').strip()
    email_hint = lead.get('email', '').lower().strip()
    phone = format_phone_number(lead.get('phoneNumber', lead.get('phonenumber', '')))

    # --- Gate 1: required fields ---
    if not company:
        return {'status': 'failed', 'reason': 'Missing company name', 'enriched': None}

    city, state = extract_city_state(address)
    if not city or not state:
        # Fall back to source state column
        state = state or lead.get('state', '')
    if not state:
        return {'status': 'failed', 'reason': 'Missing location', 'enriched': None}

    # --- Gate 2: industry filter ---
    industry = determine_industry(category)
    if industry not in SAFE_INDUSTRIES:
        return {'status': 'rejected', 'reason': f'Off-target industry: {industry}', 'enriched': None}

    # --- Gate 3: usable domain ---
    domain = can_extract_domain(website, email_hint)
    if not domain:
        return {'status': 'failed', 'reason': 'No website or extractable domain', 'enriched': None}

    # --- Gate 4: domain has MX records (dead domains) ---
    if not domain_has_mx(domain):
        return {'status': 'failed', 'reason': f'Domain has no MX records: {domain}', 'enriched': None}

    # --- Free: website scrape ---
    scraped_emails = []
    if website:
        try:
            scraped_emails = scrape_website_emails(website, '', '', max_pages=8)
        except Exception as e:
            print(f"    (scrape error: {e})", flush=True)

    # --- Free: WHOIS lookup ---
    try:
        whois_email = lookup_domain_email(domain)
        if whois_email and whois_email.split('@', 1)[1] == domain:
            # Only trust WHOIS emails on the same domain (filters out privacy proxies)
            already = {s['email'] for s in scraped_emails}
            if whois_email not in already:
                scraped_emails.append({
                    'email': whois_email,
                    'match': 'LOW',  # rescored after we have owner name
                    'source_url': f'whois:{domain}',
                })
    except Exception as e:
        print(f"    (whois error: {e})", flush=True)

    # --- PAID #1: owner discovery + research ---
    # If source already has a person_name (e.g. from prior AnyMail run), use it
    # and skip the owner-discovery step. Otherwise discover from scratch.
    existing_name = lead.get('person_name', '').strip()
    existing_title = (
        lead.get('result_title')
        or lead.get('decision_maker_category')
        or ''
    ).strip()

    if existing_name and existing_name.upper() != 'UNKNOWN':
        parts = existing_name.split()
        first_name = parts[0]
        last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
        # Still run Perplexity for the research dump used in icebreaker.
        # We pass the known name into the discover function — it returns
        # research even if the company can't independently confirm the owner.
        owner = discover_owner_and_research(
            company_name=company,
            city=city,
            state=state,
            industry=industry,
            website=website,
        )
        # If Perplexity returned UNKNOWN but we have a name from source,
        # synthesize a minimal owner record so research/icebreaker can proceed.
        if not owner:
            owner = {
                'first_name': first_name,
                'last_name': last_name,
                'title': existing_title or 'Owner',
                'confidence': 'LOW',
                'research': '',
            }
        else:
            # Trust the source-provided name over Perplexity's; keep Perplexity research.
            owner['first_name'] = first_name
            owner['last_name'] = last_name
            if existing_title:
                owner['title'] = existing_title
    else:
        owner = discover_owner_and_research(
            company_name=company,
            city=city,
            state=state,
            industry=industry,
            website=website,
        )
        if not owner:
            return {'status': 'failed', 'reason': 'Owner UNKNOWN per Perplexity', 'enriched': None}

        first_name = owner['first_name']
        last_name = owner['last_name']

    # Re-score scraped emails now that we know the owner's name
    if scraped_emails and (first_name or last_name):
        from scrape_website_emails import _name_match_score
        for s in scraped_emails:
            s['match'] = _name_match_score(s['email'], first_name, last_name)
        rank = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'GENERIC': 3}
        scraped_emails.sort(key=lambda e: rank.get(e['match'], 4))

    # If a scraped email already has HIGH match (owner-name match), skip verification entirely
    has_high_scrape = any(s['match'] == 'HIGH' for s in scraped_emails)
    verified = []

    if not has_high_scrape:
        # --- PAID #2: pattern verification ---
        patterns = generate_owner_patterns(first_name, last_name, domain)
        patterns = patterns[:MAX_PATTERNS_TO_VERIFY]
        if patterns:
            verified = verify_emails(patterns)

    # --- Confidence tagging ---
    selection = select_best_email(scraped_emails, verified, first_name, last_name)
    if selection['confidence'] == 'REJECT':
        return {'status': 'failed', 'reason': 'No deliverable email found', 'enriched': None}

    final_email = selection['email']

    # --- PAID #3 (cheap): icebreaker ---
    research_for_icebreaker = (
        f"### Decision Maker: {first_name} {last_name}\n"
        f"Title: {owner.get('title', '')}\n\n"
        f"{owner.get('research', '')}"
    )

    icebreaker = None
    try:
        icebreaker = generate_icebreaker(
            research_report=research_for_icebreaker,
            first_name=first_name,
            last_name=last_name,
            company_name=company,
            industry=industry,
        )
    except Exception as e:
        print(f"    (icebreaker error: {e})", flush=True)

    if not icebreaker:
        return {'status': 'failed', 'reason': 'Icebreaker generation failed', 'enriched': None}

    # --- Build enriched lead for save ---
    enriched = {
        'company_name': company,
        'first_name': first_name,
        'last_name': last_name,
        'email': final_email,
        'phone': phone,
        'address': address,
        'website': website,
        'job_title': owner.get('title', ''),
        'industry': industry,
        'research_report': (
            f"[CONFIDENCE: {selection['confidence']} | SOURCE: {selection['source']}]\n"
            f"{selection['reason']}\n\n"
            f"{research_for_icebreaker}"
        ),
        'icebreaker': icebreaker,
        'state_source': state,
    }

    return {
        'status': 'saved',
        'reason': f"{selection['confidence']} ({selection['source']})",
        'enriched': enriched,
    }


# ----------------------------------------------------------------------------
# Main orchestrator
# ----------------------------------------------------------------------------

def run(source_sheet_id: str, batch_size: int):
    start = datetime.now()
    print(f"\n{'=' * 80}")
    print("FULL ENRICHMENT ORCHESTRATOR")
    print(f"Source sheet: {source_sheet_id}")
    print(f"Batch size: {batch_size}")
    print(f"{'=' * 80}\n", flush=True)

    client = get_sheets_client()

    # Pre-flight: MillionVerifier credits
    credits = check_credits()
    print(f"MillionVerifier credits: {credits}", flush=True)
    if credits is not None and credits < batch_size * MAX_PATTERNS_TO_VERIFY:
        print(f"  WARN: may run out (need ~{batch_size * MAX_PATTERNS_TO_VERIFY})", flush=True)

    # Load dedup sets
    print("Loading dedup sets...", flush=True)
    completed_emails, failed_emails = load_processed_emails(client)
    print(f"  Completed: {len(completed_emails)} | Failed: {len(failed_emails)}\n", flush=True)
    ensure_failed_tab_exists(client)

    # Load source
    sheet = client.open_by_key(source_sheet_id)
    ws = sheet.sheet1
    data = ws.get_all_values()
    headers = data[0]
    rows = data[1:]
    col_map = {h.lower(): i for i, h in enumerate(headers)}

    # Build queue (free gates: dedup + industry filter)
    leads = []
    seen_in_batch = set()
    intra_dupes = 0
    off_target = 0
    cat_idx = col_map.get('category')
    email_idx = col_map.get('email', col_map.get('valid_email_only'))
    state_idx = col_map.get('state')

    for row_idx, row in enumerate(rows):
        if len(leads) >= batch_size:
            break
        email = row[email_idx].lower().strip() if email_idx is not None and email_idx < len(row) else ''
        if email in completed_emails or email in failed_emails:
            continue
        if email in seen_in_batch:
            intra_dupes += 1
            continue
        if not email or '@' not in email:
            continue
        category = row[cat_idx] if cat_idx is not None and cat_idx < len(row) else ''
        if determine_industry(category) not in SAFE_INDUSTRIES:
            off_target += 1
            continue
        seen_in_batch.add(email)
        lead = {
            'row_index': row_idx + 2,
            'state_source': row[state_idx] if state_idx is not None and state_idx < len(row) else '',
        }
        for h, i in col_map.items():
            if i < len(row):
                lead[h] = row[i]
        lead['email'] = email
        lead['phoneNumber'] = lead.get('phonenumber', lead.get('phoneNumber', ''))
        leads.append(lead)

    if intra_dupes:
        print(f"Skipped {intra_dupes} duplicate emails within source", flush=True)
    if off_target:
        print(f"Skipped {off_target} off-target leads (not electrician/plumber)", flush=True)
    print(f"Queued {len(leads)} unprocessed leads\n{'=' * 80}\n", flush=True)

    results = {'saved': 0, 'rejected': 0, 'failed': 0}

    for i, lead in enumerate(leads):
        company = lead.get('title', lead.get('company', ''))
        print(f"[{i + 1}/{len(leads)}] {company}", flush=True)
        try:
            result = process_lead(lead)
        except Exception as e:
            print(f"  ! UNEXPECTED ERROR: {e}\n", flush=True)
            save_to_failed_sheet(client, lead, f'Unexpected error: {e}', lead.get('state', ''))
            results['failed'] += 1
            continue

        status = result['status']
        reason = result['reason']

        if status == 'saved':
            saved_ok = save_to_completed_sheet(client, result['enriched'])
            if saved_ok:
                results['saved'] += 1
                completed_emails.add(result['enriched']['email'].lower())
                print(f"  >> {result['enriched']['icebreaker']}", flush=True)
                print(f"  + Saved [{reason}] → {result['enriched']['email']}\n", flush=True)
            else:
                results['failed'] += 1
                save_to_failed_sheet(client, lead, 'Save to completed failed', lead.get('state', ''))
                print(f"  ! Save failed\n", flush=True)
        else:
            results[status] += 1
            save_to_failed_sheet(client, lead, reason, lead.get('state', ''))
            print(f"  - [{status.upper()}] {reason}\n", flush=True)

        # Brief pause between leads (Perplexity + sheet write courtesy)
        if i < len(leads) - 1:
            time.sleep(1.5)

    duration = (datetime.now() - start).total_seconds()
    print(f"\n{'=' * 80}")
    print("BATCH COMPLETE")
    print(f"  Saved to completed: {results['saved']}")
    print(f"  Rejected (no good email): {results['rejected']}")
    print(f"  Failed (errors / dead leads): {results['failed']}")
    print(f"  Duration: {duration:.0f}s ({duration / max(1, len(leads)):.1f}s/lead)")
    final_credits = check_credits()
    if final_credits is not None:
        print(f"  MillionVerifier credits remaining: {final_credits}")
    print(f"{'=' * 80}\n", flush=True)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 run_full_enrichment.py <source_sheet_id> <batch_size>")
        sys.exit(1)
    run(sys.argv[1], int(sys.argv[2]))


if __name__ == "__main__":
    main()
