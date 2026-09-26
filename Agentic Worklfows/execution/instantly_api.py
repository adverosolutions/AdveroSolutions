"""
Instantly API Integration
Handles all email sending, campaign management, and reply monitoring
"""

import os
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

class InstantlyAPI:
    """Wrapper for Instantly API operations"""

    def __init__(self):
        """Initialize Instantly API client"""
        api_key = os.getenv('INSTANTLY_API_KEY')
        if not api_key:
            raise ValueError("INSTANTLY_API_KEY not found in environment")

        self.api_key = api_key
        # Use v2 API with Bearer token authentication
        self.base_url = "https://api.instantly.ai/api/v2"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # API key is already Base64 encoded
        }

        logger.info("Instantly API initialized (v2)")

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request to Instantly"""
        url = f"{self.base_url}/{endpoint}"

        # Prepare data (API key now in Authorization header)
        if data is None:
            data = {}

        try:
            if method == "GET":
                response = requests.get(url, params=data, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, json=data, headers=self.headers)
            elif method == "DELETE":
                response = requests.delete(url, json=data, headers=self.headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Instantly API request failed: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise

    def get_campaigns(self) -> List[Dict]:
        """Get all campaigns (GET /api/v2/campaigns), following the
        ``next_starting_after`` cursor until it is absent or a page is empty."""
        campaigns = []
        starting_after = None

        while True:
            params = {"limit": 100}
            if starting_after:
                params["starting_after"] = starting_after

            result = self._make_request("GET", "campaigns", params)
            if isinstance(result, list):
                items = result
                next_cursor = None
            else:
                items = result.get("items") or []
                next_cursor = result.get("next_starting_after")

            if not items:
                break
            campaigns.extend(items)

            if not next_cursor:
                break
            starting_after = next_cursor

        logger.info(f"Retrieved {len(campaigns)} campaigns")
        return campaigns

    def add_lead_to_campaign(self, campaign_name: str, email: str,
                            first_name: str, last_name: str,
                            company_name: str, **custom_variables) -> Dict:
        """
        Add lead to campaign

        Args:
            campaign_name: Name of campaign
            email: Lead email
            first_name: First name
            last_name: Last name
            company_name: Company name
            **custom_variables: Additional merge variables (industry, city, etc.)
        """
        data = {
            "campaign_name": campaign_name,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "company_name": company_name,
            **custom_variables
        }

        result = self._make_request("POST", "lead/add", data)
        logger.info(f"Added lead to campaign: {email} -> {campaign_name}")
        return result

    def get_campaign_analytics(self, campaign_name: str) -> Dict:
        """Get analytics for specific campaign"""
        data = {"campaign_name": campaign_name}
        result = self._make_request("GET", "analytics/campaign", data)
        logger.info(f"Retrieved analytics for: {campaign_name}")
        return result

    def check_replies(self, campaign_name: Optional[str] = None,
                     limit: int = 100) -> List[Dict]:
        """
        Check for new replies

        Args:
            campaign_name: Optional campaign filter
            limit: Max replies to return

        Returns:
            List of reply objects with email, body, timestamp, etc.
        """
        data = {"limit": limit}
        if campaign_name:
            data["campaign_name"] = campaign_name

        result = self._make_request("GET", "analytics/replies", data)
        logger.info(f"Retrieved {len(result)} replies")
        return result

    def send_email(self, from_email: str, to_email: str, subject: str,
                  body_html: str, campaign_name: Optional[str] = None) -> Dict:
        """
        Send individual email

        Args:
            from_email: Sender email (must be in your Instantly account)
            to_email: Recipient email
            subject: Email subject
            body_html: HTML email body
            campaign_name: Optional campaign to associate with
        """
        data = {
            "from_email": from_email,
            "to_email": to_email,
            "subject": subject,
            "body": body_html
        }

        if campaign_name:
            data["campaign_name"] = campaign_name

        result = self._make_request("POST", "email/send", data)
        logger.info(f"Sent email: {to_email} - {subject}")
        return result

    def get_account_status(self) -> Dict:
        """Get account status and limits"""
        try:
            result = self._make_request("GET", "account/status", {})
            logger.info("Retrieved account status")
            return result
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Some Instantly accounts don't have access to this endpoint
                logger.warning("Account status endpoint not available for this API key")
                return {"status": "limited_access", "note": "Account status endpoint requires higher tier"}
            raise

    def remove_lead(self, email: str, campaign_name: str) -> Dict:
        """Remove lead from campaign"""
        data = {
            "email": email,
            "campaign_name": campaign_name
        }
        result = self._make_request("DELETE", "lead/delete", data)
        logger.info(f"Removed lead: {email} from {campaign_name}")
        return result

    def get_lead_status(self, email: str, campaign_name: str) -> Dict:
        """Get status of specific lead in campaign"""
        data = {
            "email": email,
            "campaign_name": campaign_name
        }
        result = self._make_request("GET", "lead/get", data)
        return result

    def list_leads(self, campaign_id: str = None, limit: int = 100) -> List[Dict]:
        """
        List all leads, optionally filtered by campaign.
        Uses POST /api/v2/leads/list with cursor-based pagination.

        Args:
            campaign_id: Optional campaign ID to filter by
            limit: Number of leads per page (max 100)

        Returns:
            List of all lead objects across all pages
        """
        all_leads = []
        starting_after = None

        while True:
            data = {"limit": limit}
            if campaign_id:
                # The v2 body field is `campaign`; `campaign_id` is not a documented
                # leads/list field (developer.instantly.ai/api-reference/lead/list-leads.md).
                data["campaign"] = campaign_id
            if starting_after:
                data["starting_after"] = starting_after

            result = self._make_request("POST", "leads/list", data)

            items = result.get("items", result if isinstance(result, list) else [])
            if not items:
                break

            all_leads.extend(items)

            # Cursor-based pagination
            next_cursor = result.get("next_starting_after")
            if not next_cursor:
                break
            starting_after = next_cursor

            logger.debug(f"Paginated: {len(all_leads)} leads so far...")

        logger.info(f"Listed {len(all_leads)} leads" + (f" for campaign {campaign_id}" if campaign_id else ""))
        return all_leads


def get_instantly_client() -> InstantlyAPI:
    """Get initialized Instantly API client"""
    return InstantlyAPI()


if __name__ == "__main__":
    # Test connection
    try:
        client = InstantlyAPI()
        print("✅ Instantly API connected")

        # Test getting campaigns
        campaigns = client.get_campaigns()
        print(f"📊 Found {len(campaigns)} campaigns")

        if campaigns:
            print("\nCampaigns:")
            for camp in campaigns[:5]:  # Show first 5
                print(f"   - {camp.get('name', 'Unnamed')}")

        # Test account status
        status = client.get_account_status()
        print(f"\n📈 Account status retrieved")
        print(f"   Active campaigns: {status.get('active_campaigns', 'N/A')}")

    except Exception as e:
        print(f"❌ Instantly API test failed: {str(e)}")
        import traceback
        traceback.print_exc()
