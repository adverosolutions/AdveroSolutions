"""
Instantly Lead Sync — Pulls all lead statuses from Instantly and updates Master CRM.

Works directly with the actual Google Sheet tabs (HVAC Leads, Roofing Leads)
and maps Instantly numeric status codes to CRM stage names.

Handles:
- Bulk retrieval of leads across all Instantly campaigns
- Cross-references with CRM by email
- Updates Stage column (only forward progression, never downgrades)
- Updates Last Updated timestamp
- Supports dry-run mode for safe testing

Usage:
    python instantly_lead_sync.py              # Full sync
    python instantly_lead_sync.py --dry-run    # Preview changes without writing
    python instantly_lead_sync.py --campaign "HVAC Instant Response v1"  # Single campaign
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import pytz

load_dotenv()

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import Instantly API wrapper
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from instantly_api import InstantlyAPI

# ── CRM Stage Definitions (from Pipeline Stages tab) ──────────────────────
# Ordered by pipeline progression — higher index = further along
STAGE_ORDER = [
    "New/Uncontacted",    # 0 - Fresh lead
    "Contacted",          # 1 - Initial email sent
    "Follow Up 1",        # 2 - 1st follow-up
    "Follow Up 2",        # 3 - 2nd follow-up
    "Follow Up 3",        # 4 - 3rd follow-up
    "Call 1",             # 5 - 1st call attempt
    "Call 2",             # 6 - 2nd call attempt
    "Call 3",             # 7 - 3rd call attempt
    "Replied - Neutral",  # 8 - Lead responded, no clear interest
    "Replied - Positive", # 9 - Lead responded positively (interested)
    "Meeting Scheduled",  # 10 - Call/meeting booked
    "No-Show",            # 11 - Missed meeting
    "Nurture",            # 12 - Holding for re-engagement
    "Closed - Won",       # 13 - Customer
    "Closed - Lost",      # 14 - Not interested
]

TERMINAL_STAGES = {"Closed - Won", "Closed - Lost", "Meeting Scheduled", "No-Show", "Nurture"}

# ── Column indices (1-based) in HVAC Leads / Roofing Leads ────────────────
COL_STAGE = 1          # A: Stage
COL_EMAIL = 5          # E: Email
COL_LAST_UPDATED = 16  # P: Last Updated
COL_NOTES = 17         # Q: Notes

# ── Instantly status code → CRM stage mapping ─────────────────────────────
# Instantly lead `status` field:
#   1 = active (in campaign, emails sending or queued)
#  -1 = bounced/failed delivery
#   3 = replied
#
# Instantly `esp_code` field:
#   999 = not sent yet (queued)
#   1   = sending/scheduled
#   2   = successfully delivered
#   3   = bounced
#   1000 = warmup email
#
# Instantly `lt_interest_status`:
#  -2 = wrong person / do not contact
#  -1 = not interested
#   0 = neutral
#   1 = interested

# Campaign name → Sheet tab mapping
CAMPAIGN_TO_SHEET = {
    "HVAC Instant Response v1": "HVAC Leads",
    "Roofing Instant Response v1": "Roofing Leads",
}


def get_stage_index(stage: str) -> int:
    """Get numeric index for a stage. Higher = further in pipeline."""
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def determine_crm_stage(lead: Dict) -> Optional[str]:
    """
    Map Instantly lead data to the appropriate CRM stage.

    Priority order:
    1. If replied + interested (lt_interest_status=1) → "Replied - Positive"
    2. If replied + neutral/unknown (lt_interest_status=0 or none) → "Replied - Neutral"
    3. If replied + not interested (lt_interest_status=-1) → "Closed - Lost"
    4. If wrong person (lt_interest_status=-2) → "Closed - Lost"
    5. If bounced (status=-1 or esp_code=3) → "Closed - Lost"
    6. If email delivered (esp_code=2, status=1) → "Contacted"
    7. If queued/sending/warmup (esp_code=999,1,1000) → no change (not yet received)
    """
    status = lead.get("status", 0)
    esp_code = lead.get("esp_code", 0)
    reply_count = lead.get("email_reply_count", 0)
    interest = lead.get("lt_interest_status")

    # Replied — check sentiment via lt_interest_status
    if status == 3 or reply_count > 0:
        if interest == 1:
            return "Replied - Positive"
        elif interest == -1:
            return "Closed - Lost"  # Replied saying not interested
        elif interest == -2:
            return "Closed - Lost"  # Wrong person
        else:
            return "Replied - Neutral"  # Replied but no clear sentiment (0 or None)

    # Interest set without a reply (manually tagged in Instantly)
    if interest == 1:
        return "Replied - Positive"
    if interest == -1:
        return "Closed - Lost"
    if interest == -2:
        return "Closed - Lost"

    # Bounced
    if status == -1 or esp_code == 3:
        return "Closed - Lost"

    # Successfully delivered email — only then mark as Contacted
    if esp_code == 2 and status == 1:
        return "Contacted"

    # All other states (queued, sending, warmup) — don't change stage
    # esp_code 999 = queued, 1 = sending/scheduled, 1000 = warmup
    return None


def should_update(current_stage: str, proposed_stage: str) -> bool:
    """
    Only update if the proposed stage is a forward progression.
    Never downgrade. Never overwrite terminal stages.
    """
    if current_stage in TERMINAL_STAGES:
        return False

    current_idx = get_stage_index(current_stage)
    proposed_idx = get_stage_index(proposed_stage)

    # Only move forward
    return proposed_idx > current_idx


class InstantlyLeadSync:
    """Syncs lead statuses from Instantly to Google Sheets CRM"""

    def __init__(self):
        self.instantly = InstantlyAPI()
        self.timezone = pytz.timezone('US/Central')

        # Connect to Google Sheets directly
        sheet_id = os.getenv('GOOGLE_SHEET_ID')
        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID not found in environment")

        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
        client = gspread.authorize(creds)
        self.spreadsheet = client.open_by_key(sheet_id)

        logger.info(f"Connected to CRM sheet: {sheet_id}")

        self.stats = {
            "total_instantly_leads": 0,
            "matched_in_crm": 0,
            "stages_updated": 0,
            "timestamps_updated": 0,
            "skipped_terminal": 0,
            "skipped_no_change": 0,
            "skipped_downgrade": 0,
            "not_in_crm": 0,
            "errors": 0,
            "changes": [],
        }

    def _get_timestamp(self) -> str:
        return datetime.now(self.timezone).strftime('%Y-%m-%d')

    def sync(self, campaign_name: str = None, dry_run: bool = False) -> Dict:
        """Main sync orchestrator."""
        mode = "DRY RUN" if dry_run else "LIVE"
        logger.info(f"=== Instantly Lead Sync ({mode}) ===")

        # Get campaigns
        campaigns = self.instantly.get_campaigns()
        if campaign_name:
            campaigns = [c for c in campaigns if c.get("name") == campaign_name]
            if not campaigns:
                logger.error(f"Campaign not found: {campaign_name}")
                return self.stats

        logger.info(f"Processing {len(campaigns)} campaign(s)")

        for campaign in campaigns:
            camp_name = campaign.get("name", "Unknown")
            camp_id = campaign.get("id", "")

            # Determine which sheet tab this campaign maps to
            sheet_tab = CAMPAIGN_TO_SHEET.get(camp_name)
            if not sheet_tab:
                logger.warning(f"No sheet mapping for campaign: {camp_name}, skipping")
                continue

            logger.info(f"\n--- Campaign: {camp_name} → Sheet: {sheet_tab} ---")
            self._sync_campaign(camp_id, camp_name, sheet_tab, dry_run)

        self._print_summary(dry_run)
        return self.stats

    def _sync_campaign(self, campaign_id: str, campaign_name: str,
                       sheet_tab: str, dry_run: bool) -> None:
        """Sync a single campaign against its corresponding sheet tab."""

        # Step 1: Load all CRM leads from this tab
        try:
            worksheet = self.spreadsheet.worksheet(sheet_tab)
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Sheet tab not found: {sheet_tab}")
            self.stats["errors"] += 1
            return

        all_rows = worksheet.get_all_values()
        if len(all_rows) < 2:
            logger.warning(f"Sheet {sheet_tab} is empty")
            return

        headers = all_rows[0]
        email_col_idx = headers.index("Email") if "Email" in headers else 4
        stage_col_idx = headers.index("Stage") if "Stage" in headers else 0
        last_updated_idx = headers.index("Last Updated") if "Last Updated" in headers else 15

        # Build email → row mapping (row numbers are 1-indexed, +1 for header)
        crm_by_email = {}
        for i, row in enumerate(all_rows[1:], start=2):  # start=2 because row 1 is header
            if len(row) > email_col_idx:
                email = row[email_col_idx].lower().strip()
                if email:
                    crm_by_email[email] = {
                        "row_num": i,
                        "stage": row[stage_col_idx] if len(row) > stage_col_idx else "",
                        "last_updated": row[last_updated_idx] if len(row) > last_updated_idx else "",
                    }

        logger.info(f"  Loaded {len(crm_by_email)} leads from {sheet_tab}")

        # Step 2: Pull all leads from Instantly for this campaign
        try:
            instantly_leads = self.instantly.list_leads(campaign_id=campaign_id)
        except Exception as e:
            logger.error(f"  Failed to pull leads from Instantly: {e}")
            self.stats["errors"] += 1
            return

        logger.info(f"  Found {len(instantly_leads)} leads in Instantly")
        self.stats["total_instantly_leads"] += len(instantly_leads)

        # Step 3: Process each Instantly lead
        # Collect batch updates for efficiency
        batch_updates = []
        today = self._get_timestamp()

        for lead in instantly_leads:
            email = lead.get("email", "").lower().strip()
            if not email:
                continue

            crm_entry = crm_by_email.get(email)
            if not crm_entry:
                self.stats["not_in_crm"] += 1
                continue

            self.stats["matched_in_crm"] += 1
            current_stage = crm_entry["stage"]
            row_num = crm_entry["row_num"]

            # Determine proposed stage from Instantly data
            proposed_stage = determine_crm_stage(lead)
            if not proposed_stage:
                self.stats["skipped_no_change"] += 1
                continue

            # Check if we should update
            if current_stage in TERMINAL_STAGES:
                self.stats["skipped_terminal"] += 1
                continue

            if not should_update(current_stage, proposed_stage):
                current_idx = get_stage_index(current_stage)
                proposed_idx = get_stage_index(proposed_stage)
                if proposed_idx <= current_idx:
                    self.stats["skipped_downgrade"] += 1
                else:
                    self.stats["skipped_no_change"] += 1
                continue

            # Stage update needed
            change = {
                "email": email,
                "row": row_num,
                "campaign": campaign_name,
                "sheet": sheet_tab,
                "from_stage": current_stage,
                "to_stage": proposed_stage,
                "reply_count": lead.get("email_reply_count", 0),
                "last_reply": lead.get("timestamp_last_reply", ""),
            }
            self.stats["changes"].append(change)
            batch_updates.append((row_num, proposed_stage, today))

            if dry_run:
                logger.info(f"  [DRY RUN] {email}: {current_stage} -> {proposed_stage}")

        # Step 4: Apply batch updates using gspread batch_update for speed
        # Google Sheets API allows up to 60,000 cells per batch request
        if not dry_run and batch_updates:
            logger.info(f"  Applying {len(batch_updates)} updates to {sheet_tab} (batch mode)...")

            # Build cell list for batch update
            stage_col_letter = chr(ord('A') + stage_col_idx)  # e.g., 'A'
            updated_col_letter = chr(ord('A') + last_updated_idx)  # e.g., 'P'

            # Process in chunks of 500 to stay within API limits
            chunk_size = 500
            for chunk_start in range(0, len(batch_updates), chunk_size):
                chunk = batch_updates[chunk_start:chunk_start + chunk_size]
                cells_to_update = []

                for row_num, new_stage, timestamp in chunk:
                    # Stage cell
                    cells_to_update.append({
                        'range': f'{stage_col_letter}{row_num}',
                        'values': [[new_stage]]
                    })
                    # Last Updated cell
                    cells_to_update.append({
                        'range': f'{updated_col_letter}{row_num}',
                        'values': [[timestamp]]
                    })

                try:
                    worksheet.batch_update(cells_to_update, value_input_option='USER_ENTERED')
                    self.stats["stages_updated"] += len(chunk)
                    self.stats["timestamps_updated"] += len(chunk)
                    logger.info(f"  Batch updated {chunk_start + len(chunk)}/{len(batch_updates)} rows")
                except Exception as e:
                    logger.error(f"  Batch update failed at chunk {chunk_start}: {e}")
                    self.stats["errors"] += len(chunk)

    def _print_summary(self, dry_run: bool) -> None:
        """Print sync summary"""
        mode = "DRY RUN" if dry_run else "LIVE"
        print(f"\n{'='*55}")
        print(f"  Instantly Lead Sync Summary ({mode})")
        print(f"{'='*55}")
        print(f"  Total leads in Instantly:    {self.stats['total_instantly_leads']}")
        print(f"  Matched in CRM:              {self.stats['matched_in_crm']}")
        print(f"  Stages updated:              {self.stats['stages_updated'] if not dry_run else len(self.stats['changes'])}")
        print(f"  Timestamps updated:          {self.stats['timestamps_updated'] if not dry_run else len(self.stats['changes'])}")
        print(f"  Skipped (terminal stage):    {self.stats['skipped_terminal']}")
        print(f"  Skipped (no change needed):  {self.stats['skipped_no_change']}")
        print(f"  Skipped (would downgrade):   {self.stats['skipped_downgrade']}")
        print(f"  Not in CRM:                  {self.stats['not_in_crm']}")
        print(f"  Errors:                      {self.stats['errors']}")
        print(f"{'='*55}")

        if self.stats["changes"]:
            print(f"\n  Changes {'(proposed)' if dry_run else '(applied)'}:")
            for c in self.stats["changes"]:
                reply_info = f" [replied {c['reply_count']}x]" if c['reply_count'] > 0 else ""
                print(f"    {c['email']}: {c['from_stage']} -> {c['to_stage']}{reply_info} ({c['sheet']})")
        else:
            print("\n  No stage changes needed — CRM is up to date.")

        print()


def run_sync(campaign_name: str = None, dry_run: bool = False) -> Dict:
    """Entry point for other scripts/directives to call"""
    syncer = InstantlyLeadSync()
    return syncer.sync(campaign_name=campaign_name, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Instantly lead statuses to CRM")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--campaign", type=str, help="Sync a specific campaign only")
    args = parser.parse_args()

    try:
        results = run_sync(campaign_name=args.campaign, dry_run=args.dry_run)
        sys.exit(0 if results["errors"] == 0 else 1)
    except Exception as e:
        logger.error(f"Sync failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
