"""
ntfy.sh Push Notification System
Sends instant notifications to your phone via ntfy.sh (100% free)
"""

import os
import requests
import logging
from typing import Optional, Dict
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class NtfyNotifier:
    """
    Send push notifications to phone via ntfy.sh.

    No API key required. Completely free. No rate limits.
    Just need to know your topic name.
    """

    def __init__(self, topic: Optional[str] = None):
        """
        Initialize ntfy notifier.

        Args:
            topic: Your ntfy topic name (or set NTFY_TOPIC in .env)
        """
        self.topic = topic or os.getenv('NTFY_TOPIC')

        if not self.topic:
            raise ValueError(
                "ntfy topic not configured. Set NTFY_TOPIC in .env or pass topic parameter.\n"
                "Choose a unique topic name like: lawn-leads-yourname-12345"
            )

        self.base_url = "https://ntfy.sh"

    def send(
        self,
        message: str,
        title: Optional[str] = None,
        priority: str = "default",
        tags: Optional[list] = None,
        click_url: Optional[str] = None,
        attach_url: Optional[str] = None
    ) -> bool:
        """
        Send a notification to your phone.

        Args:
            message: Notification message body
            title: Notification title (optional)
            priority: min, low, default, high, urgent
            tags: List of emoji tags (e.g., ['green_circle', 'palm_tree'])
            click_url: URL to open when notification is clicked
            attach_url: Image URL to show in notification

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            url = f"{self.base_url}/{self.topic}"

            headers = {
                "Content-Type": "text/plain; charset=utf-8"
            }

            if title:
                headers["Title"] = title

            if priority:
                headers["Priority"] = priority

            if tags:
                headers["Tags"] = ",".join(tags)

            if click_url:
                headers["Click"] = click_url

            if attach_url:
                headers["Attach"] = attach_url

            response = requests.post(url, data=message.encode('utf-8'), headers=headers)

            if response.status_code == 200:
                logger.info(f"Notification sent: {title or message[:50]}")
                return True
            else:
                logger.error(f"Failed to send notification: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    def send_lead_alert(
        self,
        lead_data: Dict,
        confidence: int,
        platform: str = "facebook"
    ) -> bool:
        """
        Send a formatted lead notification.

        Args:
            lead_data: Dict with keys: post_text, author, group_name, post_url, location
            confidence: AI confidence score (0-100)
            platform: 'facebook' or 'nextdoor'

        Returns:
            True if sent successfully
        """
        # Extract data
        post_text = lead_data.get('post_text', '')[:150]  # First 150 chars
        author = lead_data.get('author', 'Unknown')
        group_name = lead_data.get('group_name', 'Unknown Group')
        post_url = lead_data.get('post_url', '')
        location = lead_data.get('location', 'Unknown Location')
        services = lead_data.get('services_needed', 'lawn care')

        # Format title
        emoji = "🔥" if confidence >= 90 else "🌿"
        title = f"{emoji} LAWN LEAD: {location}"

        # Format message
        message = f'"{post_text}..."\n\n'
        message += f"Platform: {platform.title()} - {group_name}\n"
        message += f"Confidence: {confidence}%\n"
        message += f"Services: {services}\n"
        message += f"Posted: {datetime.now().strftime('%I:%M %p')}"

        # Determine priority
        priority = "urgent" if confidence >= 90 else "high" if confidence >= 75 else "default"

        # Tags
        tags = ["deciduous_tree", "seedling"] if confidence >= 75 else ["herb"]

        return self.send(
            message=message,
            title=title,
            priority=priority,
            tags=tags,
            click_url=post_url
        )

    def send_test(self) -> bool:
        """Send a test notification."""
        return self.send(
            message="This is a test notification from your lawn lead monitoring system.",
            title="🧪 Test Notification",
            priority="default",
            tags=["white_check_mark"]
        )

    def send_error_alert(self, error_message: str) -> bool:
        """Send an error alert."""
        return self.send(
            message=f"Social lead monitor encountered an error:\n\n{error_message}",
            title="⚠️ System Error",
            priority="high",
            tags=["warning"]
        )


def get_notifier() -> Optional[NtfyNotifier]:
    """Get initialized notifier, or None if not configured."""
    try:
        return NtfyNotifier()
    except ValueError as e:
        logger.warning(f"Notifier not available: {e}")
        return None


def test_ntfy():
    """Test the ntfy notification system."""
    print("=" * 60)
    print("NTFY NOTIFICATION TEST")
    print("=" * 60)
    print()

    try:
        notifier = NtfyNotifier()
        print(f"✓ Notifier initialized")
        print(f"✓ Topic: {notifier.topic}")
        print(f"✓ URL: {notifier.base_url}/{notifier.topic}")
        print()
        print("Make sure you have the ntfy app installed on your phone")
        print("and subscribed to this topic:")
        print()
        print(f"   📱 {notifier.topic}")
        print()
        input("Press Enter to send test notification...")

        # Send test notification
        print("\nSending test notification...")
        success = notifier.send_test()

        if success:
            print("✓ Test notification sent!")
            print("Check your phone - you should see it within a few seconds.")
        else:
            print("✗ Failed to send test notification")
            print("Check the logs for details.")

        print()
        input("Press Enter to send a sample lead notification...")

        # Send sample lead notification
        print("\nSending sample lead notification...")
        sample_lead = {
            'post_text': 'Need someone to mow my lawn weekly starting next week. Small front yard, easy access. Located near downtown Phoenix.',
            'author': 'John Smith',
            'group_name': 'Phoenix Home Services',
            'post_url': 'https://facebook.com/groups/example/posts/123',
            'location': 'Phoenix, AZ',
            'services_needed': 'weekly mowing'
        }

        success = notifier.send_lead_alert(sample_lead, confidence=85, platform="facebook")

        if success:
            print("✓ Sample lead notification sent!")
            print("This is what a real lead notification will look like.")
        else:
            print("✗ Failed to send sample notification")

    except ValueError as e:
        print(f"✗ Error: {e}")
        print()
        print("To fix:")
        print("1. Add NTFY_TOPIC to your .env file")
        print("2. Choose a unique topic name like: lawn-leads-yourname-12345")
        print("3. Install ntfy app on your phone")
        print("4. Subscribe to your topic in the app")
        print("5. Run this test again")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")


if __name__ == "__main__":
    test_ntfy()
