#!/usr/bin/env python3
"""
Batch Personalization for CRM Leads
Processes leads from Google Sheets CRM and adds AI-generated personalizations.

This script:
1. Reads leads from HVAC Leads or Roofing Leads sheets
2. Filters to leads with research data but no personalization
3. Generates personalizations with Claude Opus 5.5 (engine key "haiku", name kept) with GPT-4o fallback
4. Writes results back to sheet
5. Reports cost and quality stats

Usage:
    python batch_personalize_crm.py --vertical hvac --count 100    # Process 100 HVAC leads
    python batch_personalize_crm.py --vertical roofing --all       # Process all roofing leads
    python batch_personalize_crm.py --test                         # Test mode: 10 leads, no writes
    python batch_personalize_crm.py --dry-run                      # Show what would be processed
"""

import os
import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict, Tuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from google_sheets_client import get_sheets_client, open_sheet
from unified_personalization_engine import generate_personalization, estimate_batch_cost

CRM_SHEET_ID = "1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8"

# Column names
COL_COMPANY_NAME = 'Company Name'
COL_DATA_SUMMARY = 'Data Summary'
COL_COMPANY_LOCATION = 'Company Location'
COL_PERSONALIZATION = 'Personalization'


class BatchPersonalizer:
    """Batch personalization processor for CRM leads."""

    def __init__(self, credentials_path: str):
        self.client = get_sheets_client(credentials_path)
        self.stats = {
            'total_processed': 0,
            'haiku_success': 0,
            'gpt4o_fallback': 0,
            'template_fallback': 0,
            'failures': 0,
            'total_cost': 0.0
        }

    def get_sheet_for_vertical(self, vertical: str):
        """Get the appropriate sheet for vertical."""
        sheet_map = {
            'hvac': 'HVAC Leads',
            'roofing': 'Roofing Leads'
        }

        sheet_name = sheet_map.get(vertical.lower())
        if not sheet_name:
            raise ValueError(f"Unknown vertical: {vertical}")

        return open_sheet(self.client, CRM_SHEET_ID, sheet_name)

    def get_personalization_column_index(self, worksheet) -> Tuple[int, bool]:
        """
        Get the column index for Personalization column.
        Creates it if it doesn't exist.

        Returns:
            (column_index, was_created)
        """
        headers = worksheet.row_values(1)

        if COL_PERSONALIZATION in headers:
            return headers.index(COL_PERSONALIZATION) + 1, False

        # Create the column
        next_col = len(headers) + 1
        worksheet.update_cell(1, next_col, COL_PERSONALIZATION)
        print(f"✓ Created '{COL_PERSONALIZATION}' column at position {next_col}")
        return next_col, True

    def get_leads_to_process(
        self,
        vertical: str,
        count: int = None,
        skip_existing: bool = True
    ) -> List[Dict]:
        """
        Get leads that need personalization.

        Args:
            vertical: 'hvac' or 'roofing'
            count: Max number to return (None = all)
            skip_existing: Skip leads that already have personalizations

        Returns:
            List of lead dicts with row_num, company_name, research_data, vertical
        """
        worksheet = self.get_sheet_for_vertical(vertical)
        records = worksheet.get_all_records()

        # Get personalization column index
        pers_col_idx, _ = self.get_personalization_column_index(worksheet)

        leads = []

        for i, record in enumerate(records, start=2):  # Start at row 2 (after header)
            company_name = str(record.get(COL_COMPANY_NAME, '')).strip()
            data_summary = str(record.get(COL_DATA_SUMMARY, '')).strip()
            existing_pers = str(record.get(COL_PERSONALIZATION, '')).strip()

            # Skip if missing required data
            if not company_name or not data_summary:
                continue

            # Skip if already has personalization
            if skip_existing and existing_pers and existing_pers != 'nan':
                continue

            # Build research data
            company_location = str(record.get(COL_COMPANY_LOCATION, '')).strip()
            research_parts = []

            if data_summary and data_summary != 'nan':
                research_parts.append(data_summary)
            if company_location and company_location != 'nan':
                research_parts.append(f"Service area: {company_location}")

            research_data = "\n\n".join(research_parts)

            leads.append({
                'row_num': i,
                'company_name': company_name,
                'research_data': research_data,
                'vertical': vertical
            })

            # Stop if we hit the count limit
            if count and len(leads) >= count:
                break

        return leads

    def process_lead(self, lead: Dict, worksheet, pers_col_idx: int, dry_run: bool = False) -> Dict:
        """
        Process a single lead.

        Args:
            lead: Lead dict
            worksheet: Google Sheet worksheet
            pers_col_idx: Column index for Personalization
            dry_run: If True, don't write to sheet

        Returns:
            Result dict
        """
        result = generate_personalization(
            research_data=lead['research_data'],
            company_name=lead['company_name'],
            vertical=lead['vertical']
        )

        # Update stats
        self.stats['total_processed'] += 1
        self.stats['total_cost'] += result['cost_estimate']

        if result['success']:
            engine_used = result['engine_used']

            if engine_used == 'haiku':
                self.stats['haiku_success'] += 1
            elif engine_used == 'gpt4o':
                self.stats['gpt4o_fallback'] += 1
            elif engine_used == 'fallback':
                self.stats['template_fallback'] += 1

            # Write to sheet (unless dry run)
            if not dry_run:
                try:
                    worksheet.update_cell(
                        lead['row_num'],
                        pers_col_idx,
                        result['personalization']
                    )
                except Exception as e:
                    print(f"✗ Error writing to sheet: {e}")
                    result['write_error'] = str(e)
        else:
            self.stats['failures'] += 1

        return result

    def run_batch(
        self,
        vertical: str,
        count: int = None,
        dry_run: bool = False,
        test_mode: bool = False
    ):
        """
        Run batch personalization.

        Args:
            vertical: 'hvac' or 'roofing'
            count: Max leads to process (None = all)
            dry_run: Don't write to sheet
            test_mode: Process 10 leads max, don't write
        """
        if test_mode:
            count = min(count or 10, 10)
            dry_run = True
            print(f"{'='*70}")
            print("TEST MODE: Processing 10 leads, no writes to sheet")
            print(f"{'='*70}\n")

        # Get leads to process
        print(f"Fetching {vertical.upper()} leads to process...")
        leads = self.get_leads_to_process(vertical, count=count)

        if not leads:
            print(f"✗ No leads found to process for {vertical}")
            return

        print(f"✓ Found {len(leads)} leads to process\n")

        # Show cost estimate
        estimate = estimate_batch_cost(len(leads))
        print(f"📊 Cost Estimate:")
        print(f"   Engine: {estimate['engine']}")
        print(f"   Expected cost: ${estimate['total_cost']:.4f}")
        print(f"   Cost per lead: ${estimate['cost_per_lead']:.6f}")
        print(f"   Claude (Opus 5.5): {estimate['haiku_count']}, GPT-4o: {estimate['gpt4o_count']}, Template: {estimate['fallback_count']}")
        print()

        # Get worksheet and column index
        worksheet = self.get_sheet_for_vertical(vertical)
        pers_col_idx, _ = self.get_personalization_column_index(worksheet)

        # Process leads
        print(f"{'='*70}")
        print(f"Processing {len(leads)} {vertical.upper()} leads...")
        print(f"{'='*70}\n")

        start_time = time.time()

        for i, lead in enumerate(leads, 1):
            print(f"[{i}/{len(leads)}] {lead['company_name'][:50]}", end=' ')

            result = self.process_lead(lead, worksheet, pers_col_idx, dry_run)

            if result['success']:
                engine = result['engine_used']
                print(f"✓ {engine} (${result['cost_estimate']:.6f})")
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")

            # Rate limiting: ~2 per second
            time.sleep(0.5)

        elapsed = time.time() - start_time

        # Print summary
        self.print_summary(elapsed)

    def print_summary(self, elapsed_seconds: float):
        """Print batch summary."""
        print(f"\n{'='*70}")
        print("BATCH SUMMARY")
        print(f"{'='*70}\n")

        s = self.stats

        print(f"Processed: {s['total_processed']} leads in {elapsed_seconds:.1f}s")
        print(f"  Claude (Opus 5.5) success: {s['haiku_success']} ({s['haiku_success']/s['total_processed']*100:.1f}%)")
        print(f"  GPT-4o fallback: {s['gpt4o_fallback']} ({s['gpt4o_fallback']/s['total_processed']*100:.1f}%)")
        print(f"  Template fallback: {s['template_fallback']} ({s['template_fallback']/s['total_processed']*100:.1f}%)")
        print(f"  Failures: {s['failures']} ({s['failures']/s['total_processed']*100:.1f}%)")

        print(f"\n💰 Cost:")
        print(f"  Total: ${s['total_cost']:.4f}")
        print(f"  Per lead: ${s['total_cost']/s['total_processed']:.6f}")

        # Calculate savings vs GPT-4o only
        gpt4o_cost = s['total_processed'] * 0.002
        savings = gpt4o_cost - s['total_cost']
        savings_pct = (savings / gpt4o_cost * 100) if gpt4o_cost > 0 else 0

        print(f"\n💸 Savings vs GPT-4o only:")
        print(f"  ${savings:.4f} ({savings_pct:.1f}%)")

        # Extrapolate to 1,000 leads
        cost_per_1k = (s['total_cost'] / s['total_processed']) * 1000
        gpt4o_per_1k = 2.00
        savings_per_1k = gpt4o_per_1k - cost_per_1k

        print(f"\n📈 Projected for 1,000 leads:")
        print(f"  Your cost: ${cost_per_1k:.2f}")
        print(f"  GPT-4o cost: ${gpt4o_per_1k:.2f}")
        print(f"  Savings: ${savings_per_1k:.2f}")

        print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description='Batch personalize CRM leads')
    parser.add_argument('--vertical', choices=['hvac', 'roofing'], required=True,
                       help='Which leads to process')
    parser.add_argument('--count', type=int, help='Max number of leads to process')
    parser.add_argument('--all', action='store_true', help='Process all leads without limit')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: 10 leads max, no writes')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without writing')

    args = parser.parse_args()

    # Validate args
    if args.all and args.count:
        print("✗ Error: Cannot use both --all and --count")
        sys.exit(1)

    if not args.all and not args.count and not args.test:
        print("✗ Error: Must specify --count N, --all, or --test")
        sys.exit(1)

    # Check credentials
    credentials_path = '/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows/credentials.json'
    if not os.path.exists(credentials_path):
        print(f"✗ Error: credentials.json not found at {credentials_path}")
        sys.exit(1)

    # Check API keys
    if not os.getenv('ANTHROPIC_API_KEY') and not os.getenv('OPENAI_API_KEY'):
        print("✗ Error: No API keys found in .env")
        print("   Set ANTHROPIC_API_KEY (for Claude Opus 5.5) or OPENAI_API_KEY (for GPT-4o)")
        sys.exit(1)

    # Run batch
    processor = BatchPersonalizer(credentials_path)

    try:
        processor.run_batch(
            vertical=args.vertical,
            count=args.count,
            dry_run=args.dry_run or args.test,
            test_mode=args.test
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        processor.print_summary(0)
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
