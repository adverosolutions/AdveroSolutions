#!/usr/bin/env python3
"""
Separate Contacted Leads from Fresh Leads
Checks Instantly campaigns for already-contacted leads and separates them from new CSV leads.
Creates two output files: fresh leads (priority) and previously contacted (for later re-engagement).
"""

import os
import csv
import json
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple
from dotenv import load_dotenv
import logging
from instantly_api import InstantlyAPI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_contacted_leads(client: InstantlyAPI) -> Tuple[Set[str], Dict[str, Dict]]:
    """
    Get all leads that have been contacted across all campaigns.

    Returns:
        Tuple of (set of contacted emails, dict of email -> lead data with contact info)
    """
    contacted_emails = set()
    contact_details = {}

    try:
        # Get all campaigns
        campaigns = client.get_campaigns()
        logger.info(f"Found {len(campaigns)} campaigns to check")

        for campaign in campaigns:
            campaign_name = campaign.get('name', 'Unknown')
            campaign_id = campaign.get('id')

            if not campaign_id:
                logger.warning(f"Campaign '{campaign_name}' has no ID, skipping")
                continue

            logger.info(f"Checking campaign: {campaign_name}")

            # Get all leads from this campaign
            try:
                leads = client.list_leads(campaign_id=campaign_id, limit=100)

                for lead in leads:
                    email = lead.get('email', '').lower().strip()
                    if not email:
                        continue

                    # Check if lead has been contacted (sent > 0 or opened > 0)
                    stats = lead.get('stats', {})
                    sent_count = stats.get('sent', 0)
                    opened_count = stats.get('opened', 0)
                    replied_count = stats.get('replied', 0)

                    if sent_count > 0:  # Lead has been contacted
                        contacted_emails.add(email)

                        # Store contact details
                        if email not in contact_details:
                            contact_details[email] = {
                                'email': email,
                                'campaigns': [],
                                'total_sent': 0,
                                'total_opened': 0,
                                'total_replied': 0,
                                'last_contacted': None,
                                'first_name': lead.get('first_name', ''),
                                'last_name': lead.get('last_name', ''),
                                'company': lead.get('company_name', '')
                            }

                        contact_details[email]['campaigns'].append(campaign_name)
                        contact_details[email]['total_sent'] += sent_count
                        contact_details[email]['total_opened'] += opened_count
                        contact_details[email]['total_replied'] += replied_count

                        # Track last contact date if available
                        last_sent = lead.get('last_sent')
                        if last_sent and (not contact_details[email]['last_contacted'] or
                                         last_sent > contact_details[email]['last_contacted']):
                            contact_details[email]['last_contacted'] = last_sent

                logger.info(f"  - Found {len([l for l in leads if l.get('stats', {}).get('sent', 0) > 0])} contacted leads in {campaign_name}")

            except Exception as e:
                logger.error(f"Error fetching leads for campaign {campaign_name}: {str(e)}")
                continue

        logger.info(f"Total unique contacted emails found: {len(contacted_emails)}")
        return contacted_emails, contact_details

    except Exception as e:
        logger.error(f"Error getting contacted leads: {str(e)}")
        raise


def separate_csv_leads(csv_path: str, contacted_emails: Set[str], contact_details: Dict[str, Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Separate CSV leads into fresh and previously contacted.

    Args:
        csv_path: Path to input CSV file
        contacted_emails: Set of already contacted email addresses
        contact_details: Details about contacted leads

    Returns:
        Tuple of (fresh leads list, previously contacted leads list)
    """
    fresh_leads = []
    previously_contacted = []

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Get email field (try common variations)
                email = None
                for field in ['email', 'Email', 'EMAIL', 'email_address', 'Email Address']:
                    if field in row:
                        email = row[field].lower().strip()
                        break

                if not email:
                    logger.warning(f"No email found in row: {row}")
                    continue

                if email in contacted_emails:
                    # Add contact history to the row
                    history = contact_details.get(email, {})
                    row['contact_history'] = json.dumps({
                        'campaigns': history.get('campaigns', []),
                        'total_sent': history.get('total_sent', 0),
                        'total_opened': history.get('total_opened', 0),
                        'total_replied': history.get('total_replied', 0),
                        'last_contacted': history.get('last_contacted')
                    })
                    previously_contacted.append(row)
                else:
                    fresh_leads.append(row)

        logger.info(f"Separated {len(fresh_leads)} fresh leads and {len(previously_contacted)} previously contacted leads")
        return fresh_leads, previously_contacted

    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
        raise


def calculate_reintroduction_date(contact_details: Dict[str, Dict], min_weeks: int = 2) -> Dict[str, datetime]:
    """
    Calculate when previously contacted leads can be reintroduced.

    Args:
        contact_details: Details about contacted leads
        min_weeks: Minimum weeks to wait before recontacting

    Returns:
        Dict of email -> reintroduction date
    """
    reintroduction_dates = {}
    min_days = min_weeks * 7

    for email, details in contact_details.items():
        last_contacted = details.get('last_contacted')

        if last_contacted:
            # Parse the date if it's a string
            if isinstance(last_contacted, str):
                try:
                    last_date = datetime.fromisoformat(last_contacted.replace('Z', '+00:00'))
                except:
                    last_date = datetime.now()
            else:
                last_date = last_contacted

            reintroduction_date = last_date + timedelta(days=min_days)
        else:
            # If no last contact date, use current date + min_days
            reintroduction_date = datetime.now() + timedelta(days=min_days)

        reintroduction_dates[email] = reintroduction_date

    return reintroduction_dates


def save_separated_leads(fresh_leads: List[Dict], previously_contacted: List[Dict],
                         reintroduction_dates: Dict[str, datetime], output_dir: str = "."):
    """
    Save separated leads to CSV files.

    Args:
        fresh_leads: List of fresh lead dictionaries
        previously_contacted: List of previously contacted lead dictionaries
        reintroduction_dates: Dict of email -> reintroduction date
        output_dir: Directory to save output files
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save fresh leads (priority)
    fresh_path = os.path.join(output_dir, f"fresh_leads_{timestamp}.csv")
    if fresh_leads:
        fieldnames = list(fresh_leads[0].keys())
        with open(fresh_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(fresh_leads)
        logger.info(f"✅ Saved {len(fresh_leads)} fresh leads to: {fresh_path}")
    else:
        logger.warning("No fresh leads to save")

    # Save previously contacted leads with reintroduction dates
    contacted_path = os.path.join(output_dir, f"previously_contacted_{timestamp}.csv")
    if previously_contacted:
        # Add reintroduction date to each row
        for row in previously_contacted:
            email = None
            for field in ['email', 'Email', 'EMAIL', 'email_address', 'Email Address']:
                if field in row:
                    email = row[field].lower().strip()
                    break

            if email and email in reintroduction_dates:
                row['reintroduction_date'] = reintroduction_dates[email].strftime("%Y-%m-%d")
                row['days_until_ready'] = max(0, (reintroduction_dates[email] - datetime.now()).days)

        fieldnames = list(previously_contacted[0].keys())
        with open(contacted_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(previously_contacted)
        logger.info(f"✅ Saved {len(previously_contacted)} previously contacted leads to: {contacted_path}")
    else:
        logger.info("No previously contacted leads found")

    # Create summary report
    summary_path = os.path.join(output_dir, f"lead_separation_summary_{timestamp}.txt")
    with open(summary_path, 'w') as f:
        f.write("Lead Separation Summary\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Fresh Leads (Ready to Contact): {len(fresh_leads)}\n")
        f.write(f"Previously Contacted (Delayed): {len(previously_contacted)}\n")
        f.write(f"Total Leads Processed: {len(fresh_leads) + len(previously_contacted)}\n\n")

        if previously_contacted:
            f.write("Reintroduction Schedule:\n")
            f.write("-" * 30 + "\n")

            # Group by reintroduction date
            date_groups = {}
            for row in previously_contacted:
                reintro_date = row.get('reintroduction_date', 'Unknown')
                if reintro_date not in date_groups:
                    date_groups[reintro_date] = 0
                date_groups[reintro_date] += 1

            for date_str in sorted(date_groups.keys()):
                f.write(f"{date_str}: {date_groups[date_str]} leads\n")

        f.write("\n" + "=" * 50 + "\n")
        f.write(f"Fresh leads saved to: {fresh_path}\n")
        if previously_contacted:
            f.write(f"Previously contacted saved to: {contacted_path}\n")

    logger.info(f"📊 Summary saved to: {summary_path}")

    # Print summary to console
    print("\n" + "=" * 60)
    print("LEAD SEPARATION COMPLETE")
    print("=" * 60)
    print(f"✅ Fresh Leads (Ready for New Offer): {len(fresh_leads)}")
    print(f"⏰ Previously Contacted (Delayed 2+ Weeks): {len(previously_contacted)}")
    print(f"📁 Files saved with timestamp: {timestamp}")
    print("=" * 60)


def main():
    """Main execution function"""
    import argparse

    parser = argparse.ArgumentParser(description="Separate contacted leads from fresh leads")
    parser.add_argument("csv_file", help="Path to CSV file with leads to process")
    parser.add_argument("--min-weeks", type=int, default=2,
                       help="Minimum weeks before recontacting (default: 2)")
    parser.add_argument("--output-dir", default=".",
                       help="Directory to save output files (default: current directory)")

    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        logger.error(f"CSV file not found: {args.csv_file}")
        return 1

    try:
        # Initialize Instantly client
        logger.info("Connecting to Instantly API...")
        client = InstantlyAPI()

        # Get all contacted leads from Instantly
        logger.info("Fetching contacted leads from all campaigns...")
        contacted_emails, contact_details = get_all_contacted_leads(client)

        # Separate CSV leads
        logger.info(f"Processing CSV file: {args.csv_file}")
        fresh_leads, previously_contacted = separate_csv_leads(
            args.csv_file, contacted_emails, contact_details
        )

        # Calculate reintroduction dates
        logger.info(f"Calculating reintroduction dates (minimum {args.min_weeks} weeks)...")
        reintroduction_dates = calculate_reintroduction_date(
            contact_details, min_weeks=args.min_weeks
        )

        # Save results
        logger.info("Saving separated lead files...")
        save_separated_leads(
            fresh_leads, previously_contacted,
            reintroduction_dates, args.output_dir
        )

        return 0

    except Exception as e:
        logger.error(f"Error during lead separation: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())