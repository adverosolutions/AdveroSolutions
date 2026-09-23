"""
Google Sheets CRM - Core Data Layer
Handles all CRM read/write operations following Master SOP stage definitions
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Valid lead stages per Master SOP (SOP-001)
VALID_STAGES = [
    "New Lead",
    "Contacted",
    "Engaged",
    "Non-Booker",
    "Booked",
    "No-Show",
    "Discovery Done",
    "Closed Won",
    "Closed Lost"
]

# Terminal stages (cannot transition out)
TERMINAL_STAGES = ["Closed Won", "Closed Lost"]

# Stage transition rules (from -> to)
VALID_TRANSITIONS = {
    "New Lead": ["Contacted", "Closed Lost"],
    "Contacted": ["Engaged", "Closed Lost"],
    "Engaged": ["Non-Booker", "Booked", "Closed Lost"],
    "Non-Booker": ["Booked", "Closed Lost"],
    "Booked": ["No-Show", "Discovery Done", "Closed Lost"],
    "No-Show": ["Booked", "Closed Lost"],
    "Discovery Done": ["Closed Won", "Closed Lost"],
    "Closed Won": [],  # Terminal
    "Closed Lost": []  # Terminal
}

class GoogleSheetsCRM:
    """Core CRM operations for AdveroSolutions lead management"""

    def __init__(self):
        """Initialize connection to Google Sheets CRM"""
        self.sheet_id = os.getenv('GOOGLE_SHEET_ID')
        self.timezone = pytz.timezone(os.getenv('TIMEZONE', 'America/New_York'))

        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID not found in environment variables")

        # Set up Google Sheets authentication
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        creds = Credentials.from_service_account_file(
            'credentials.json',
            scopes=scopes
        )

        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(self.sheet_id)

        # Access to each sheet
        self.master_leads = self.spreadsheet.worksheet('Master_Leads')
        self.email_activity = self.spreadsheet.worksheet('Email_Activity')
        self.active_sequences = self.spreadsheet.worksheet('Active_Sequences')
        self.call_records = self.spreadsheet.worksheet('Call_Records')
        self.metrics_dashboard = self.spreadsheet.worksheet('Metrics_Dashboard')

        logger.info(f"Connected to CRM: {self.sheet_id}")

    def _get_timestamp(self) -> str:
        """Get current timestamp in configured timezone"""
        return datetime.now(self.timezone).strftime('%Y-%m-%d %H:%M:%S')

    def _generate_lead_id(self) -> str:
        """Generate unique lead ID"""
        timestamp = datetime.now(self.timezone).strftime('%Y%m%d_%H%M%S')
        return f"LEAD_{timestamp}"

    def _validate_stage_transition(self, current_stage: str, new_stage: str) -> bool:
        """Validate that stage transition is allowed per SOP-001"""
        if current_stage not in VALID_STAGES:
            raise ValueError(f"Invalid current stage: {current_stage}")

        if new_stage not in VALID_STAGES:
            raise ValueError(f"Invalid new stage: {new_stage}")

        if current_stage in TERMINAL_STAGES:
            logger.warning(f"Cannot transition from terminal stage: {current_stage}")
            return False

        if new_stage not in VALID_TRANSITIONS[current_stage]:
            logger.warning(
                f"Invalid transition: {current_stage} -> {new_stage}. "
                f"Valid transitions: {VALID_TRANSITIONS[current_stage]}"
            )
            return False

        return True

    def add_lead(self, lead_data: Dict[str, Any]) -> str:
        """
        Add new lead to CRM

        Args:
            lead_data: Dict with keys: first_name, last_name, email, company_name, industry

        Returns:
            lead_id of created lead
        """
        lead_id = self._generate_lead_id()
        timestamp = self._get_timestamp()

        # Required fields
        required_fields = ['first_name', 'last_name', 'email', 'company_name', 'industry']
        for field in required_fields:
            if field not in lead_data:
                raise ValueError(f"Missing required field: {field}")

        # Build row data matching Master_Leads schema
        row = [
            lead_id,
            lead_data['first_name'],
            lead_data['last_name'],
            lead_data['email'],
            lead_data['company_name'],
            lead_data['industry'],
            lead_data.get('phone', ''),
            lead_data.get('website', ''),
            lead_data.get('city', ''),
            lead_data.get('state', ''),
            'New Lead',  # current_stage
            timestamp,   # stage_updated_at
            timestamp,   # created_at
            '',          # booking_link_sent_at
            '',          # call_scheduled_at
            '',          # call_completed_at
            '',          # last_reply_at
            '',          # last_reply_sentiment
            lead_data.get('source', 'Manual Import'),
            lead_data.get('notes', '')
        ]

        self.master_leads.append_row(row)
        logger.info(f"Added lead: {lead_id} - {lead_data['company_name']}")

        return lead_id

    def get_lead(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get lead by ID"""
        try:
            cell = self.master_leads.find(lead_id)
            row = self.master_leads.row_values(cell.row)

            # Map to dict (matching Master_Leads schema)
            headers = self.master_leads.row_values(1)
            lead = dict(zip(headers, row))

            return lead
        except gspread.exceptions.CellNotFound:
            logger.warning(f"Lead not found: {lead_id}")
            return None

    def update_stage(self, lead_id: str, new_stage: str, reason: str = "") -> bool:
        """
        Update lead stage with validation

        Args:
            lead_id: Lead identifier
            new_stage: New stage (must be valid per SOP-001)
            reason: Optional reason for transition

        Returns:
            True if successful, False otherwise
        """
        lead = self.get_lead(lead_id)
        if not lead:
            logger.error(f"Cannot update stage - lead not found: {lead_id}")
            return False

        current_stage = lead['current_stage']

        # Validate transition
        if not self._validate_stage_transition(current_stage, new_stage):
            return False

        # Find row and update
        try:
            cell = self.master_leads.find(lead_id)
            row_num = cell.row
            timestamp = self._get_timestamp()

            # Update stage columns (columns K and L)
            self.master_leads.update_cell(row_num, 11, new_stage)
            self.master_leads.update_cell(row_num, 12, timestamp)

            logger.info(
                f"Stage updated: {lead_id} - {current_stage} -> {new_stage}"
                + (f" (Reason: {reason})" if reason else "")
            )

            return True

        except Exception as e:
            logger.error(f"Error updating stage for {lead_id}: {str(e)}")
            return False

    def get_leads_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        """Get all leads in a specific stage"""
        if stage not in VALID_STAGES:
            raise ValueError(f"Invalid stage: {stage}")

        all_rows = self.master_leads.get_all_records()
        leads = [row for row in all_rows if row['current_stage'] == stage]

        logger.info(f"Found {len(leads)} leads in stage: {stage}")
        return leads

    def log_email_activity(self, lead_id: str, email_type: str, subject: str,
                          status: str = "sent") -> None:
        """
        Log email activity to Email_Activity sheet

        Args:
            lead_id: Lead identifier
            email_type: Type of email (cold_1, cold_2, cold_3, response, non_booker_1, etc.)
            subject: Email subject line
            status: sent, opened, replied, bounced
        """
        timestamp = self._get_timestamp()

        row = [
            timestamp,
            lead_id,
            email_type,
            subject,
            status,
            ''  # reply_content (filled when status = replied)
        ]

        self.email_activity.append_row(row)
        logger.info(f"Logged email: {lead_id} - {email_type} - {status}")

    def update_booking_link_sent(self, lead_id: str) -> bool:
        """Update timestamp when booking link is sent"""
        try:
            cell = self.master_leads.find(lead_id)
            row_num = cell.row
            timestamp = self._get_timestamp()

            # Column N: booking_link_sent_at
            self.master_leads.update_cell(row_num, 14, timestamp)

            logger.info(f"Booking link sent timestamp updated: {lead_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating booking link timestamp: {str(e)}")
            return False

    def update_call_scheduled(self, lead_id: str, call_time: str) -> bool:
        """Update when call is scheduled"""
        try:
            cell = self.master_leads.find(lead_id)
            row_num = cell.row

            # Column O: call_scheduled_at
            self.master_leads.update_cell(row_num, 15, call_time)

            # Update stage to Booked
            self.update_stage(lead_id, "Booked", "Call scheduled")

            logger.info(f"Call scheduled: {lead_id} at {call_time}")
            return True

        except Exception as e:
            logger.error(f"Error updating call schedule: {str(e)}")
            return False

    def log_call_record(self, lead_id: str, outcome: str, notes: str = "",
                       next_action: str = "") -> None:
        """
        Log discovery call record

        Args:
            outcome: Verbal Commit, Think About It, Ghost, Bad Timing, Not Qualified
            notes: Call notes
            next_action: Next step determined on call
        """
        timestamp = self._get_timestamp()
        lead = self.get_lead(lead_id)

        if not lead:
            logger.error(f"Cannot log call - lead not found: {lead_id}")
            return

        row = [
            timestamp,
            lead_id,
            lead['company_name'],
            outcome,
            notes,
            next_action,
            lead.get('call_scheduled_at', '')
        ]

        self.call_records.append_row(row)

        # Update stage to Discovery Done
        self.update_stage(lead_id, "Discovery Done", f"Call completed - {outcome}")

        # Update call_completed_at timestamp
        try:
            cell = self.master_leads.find(lead_id)
            row_num = cell.row
            self.master_leads.update_cell(row_num, 16, timestamp)
        except Exception as e:
            logger.error(f"Error updating call completed timestamp: {str(e)}")

        logger.info(f"Call logged: {lead_id} - {outcome}")

    def get_leads_for_non_booker_sequence(self) -> List[Dict[str, Any]]:
        """
        Get leads in Engaged stage where booking link was sent 72+ hours ago
        Triggers Non-Booker follow-up sequence per SOP-004
        """
        leads = self.get_leads_by_stage("Engaged")
        now = datetime.now(self.timezone)

        eligible_leads = []
        for lead in leads:
            booking_link_sent = lead.get('booking_link_sent_at', '')
            if not booking_link_sent:
                continue

            sent_time = datetime.strptime(booking_link_sent, '%Y-%m-%d %H:%M:%S')
            sent_time = self.timezone.localize(sent_time)
            hours_elapsed = (now - sent_time).total_seconds() / 3600

            if hours_elapsed >= 72:
                eligible_leads.append(lead)

        logger.info(f"Found {len(eligible_leads)} leads eligible for Non-Booker sequence")
        return eligible_leads

    def get_no_shows(self) -> List[Dict[str, Any]]:
        """Get leads who missed their scheduled call"""
        return self.get_leads_by_stage("No-Show")

    def get_lead_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Look up a lead by email address.
        Returns the first matching lead or None.
        """
        try:
            cell = self.master_leads.find(email)
            if not cell:
                return None
            row = self.master_leads.row_values(cell.row)
            headers = self.master_leads.row_values(1)
            lead = dict(zip(headers, row))
            lead['_row_num'] = cell.row  # Include row number for direct updates
            return lead
        except gspread.exceptions.CellNotFound:
            return None

    def update_last_reply_at(self, lead_id: str, timestamp: str = None) -> bool:
        """Update last_reply_at timestamp (column Q/17) for a lead"""
        try:
            cell = self.master_leads.find(lead_id)
            row_num = cell.row
            ts = timestamp or self._get_timestamp()
            self.master_leads.update_cell(row_num, 17, ts)
            logger.info(f"Updated last_reply_at for {lead_id}: {ts}")
            return True
        except Exception as e:
            logger.error(f"Error updating last_reply_at for {lead_id}: {str(e)}")
            return False

    def bulk_get_all_leads(self) -> List[Dict[str, Any]]:
        """
        Get all leads from Master_Leads sheet in a single API call.
        Returns list of dicts with header keys. Much more efficient than
        individual lookups when processing many leads.
        """
        all_records = self.master_leads.get_all_records()
        logger.info(f"Bulk retrieved {len(all_records)} leads from CRM")
        return all_records

    def bulk_import_leads(self, leads_list: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Bulk import multiple leads

        Returns:
            Dict with success/failure counts
        """
        results = {"success": 0, "failed": 0}

        for lead_data in leads_list:
            try:
                self.add_lead(lead_data)
                results["success"] += 1
            except Exception as e:
                logger.error(f"Failed to import lead {lead_data.get('email', 'unknown')}: {str(e)}")
                results["failed"] += 1

        logger.info(f"Bulk import complete: {results['success']} success, {results['failed']} failed")
        return results


# Utility functions for common operations

def get_crm() -> GoogleSheetsCRM:
    """Get initialized CRM instance"""
    return GoogleSheetsCRM()


if __name__ == "__main__":
    # Test connection
    try:
        crm = GoogleSheetsCRM()
        print("✅ CRM connection successful")
        print(f"📊 Sheet ID: {crm.sheet_id}")

        # Test getting leads by stage
        new_leads = crm.get_leads_by_stage("New Lead")
        print(f"📥 New Leads: {len(new_leads)}")

    except Exception as e:
        print(f"❌ CRM connection failed: {str(e)}")
