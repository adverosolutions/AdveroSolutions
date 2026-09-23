"""
Instantly Campaign Builder
Creates campaigns in Instantly with proper 3-email sequences per Master SOP
"""

import os
import requests
from typing import Dict, List
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)


class InstantlyCampaignBuilder:
    """Builds and manages campaigns in Instantly"""

    def __init__(self):
        """Initialize Instantly Campaign Builder"""
        api_key = os.getenv('INSTANTLY_API_KEY')
        if not api_key:
            raise ValueError("INSTANTLY_API_KEY not found in environment")

        self.api_key = api_key
        self.base_url = "https://api.instantly.ai/api/v2"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        logger.info("Instantly Campaign Builder initialized")

    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make API request to Instantly"""
        url = f"{self.base_url}/{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, params=data, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, json=data, headers=self.headers)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=self.headers)
            elif method == "DELETE":
                response = requests.delete(url, json=data, headers=self.headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Instantly API request failed: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise

    def create_cold_campaign(self, industry: str = "Mixed", test_mode: bool = False) -> Dict:
        """
        Create cold email campaign per Master SOP.
        Routes to SOP-002 (HVAC/Plumbing/Electrical) or SOP-002R (Roofing)
        based on industry.

        Args:
            industry: Target industry (HVAC, Roofing, Plumbing, Electrical, Mixed)
            test_mode: If True, add TEST suffix to campaign name

        Returns:
            Campaign details including ID
        """
        if industry == "Roofing":
            return self.create_roofing_campaign(test_mode=test_mode)

        return self._create_standard_campaign(industry=industry, test_mode=test_mode)

    def _create_standard_campaign(self, industry: str = "Mixed", test_mode: bool = False) -> Dict:
        """
        Create SOP-002 campaign (HVAC, Plumbing, Electrical).
        3-email sequence over 7-10 days.
        """
        from datetime import datetime

        timestamp = datetime.now().strftime('%Y%m%d')
        campaign_name = f"Cold_{industry}_{timestamp}"
        if test_mode:
            campaign_name += "_TEST"

        logger.info(f"Creating SOP-002 campaign: {campaign_name}")

        campaign_config = {
            "name": campaign_name,
            "status": 2,  # Active
            "sequences": [
                {
                    "steps": [
                        {
                            "type": "email",
                            "delay": 0,
                            "variants": [
                                {
                                    "subject": f"What top {industry} contractors are doing differently",
                                    "body": self._get_email_1_body(industry)
                                }
                            ]
                        },
                        {
                            "type": "email",
                            "delay": 4,
                            "variants": [
                                {
                                    "subject": f"AI is transforming {industry} - early vs. late adopters",
                                    "body": self._get_email_2_body(industry)
                                }
                            ]
                        },
                        {
                            "type": "email",
                            "delay": 3,
                            "variants": [
                                {
                                    "subject": "Last one from me",
                                    "body": self._get_email_3_body(industry)
                                }
                            ]
                        }
                    ]
                }
            ],
            "email_gap": 9,
            "text_only": False,
            "stop_on_reply": True,
            "link_tracking": True,
            "open_tracking": True,
            "daily_limit": 1000,
            "campaign_schedule": {
                "schedules": [
                    {
                        "name": "Contractor Hours",
                        "timing": {
                            "from": "07:00",
                            "to": "17:00"
                        },
                        "days": {
                            "0": False,
                            "1": True,
                            "2": True,
                            "3": True,
                            "4": True,
                            "5": True,
                            "6": False
                        },
                        "timezone": "America/Chicago"
                    }
                ]
            }
        }

        try:
            result = self._make_request("POST", "campaigns", campaign_config)
            logger.info(f"✅ SOP-002 campaign created: {campaign_name}")
            return result
        except Exception as e:
            logger.error(f"❌ SOP-002 campaign creation failed: {str(e)}")
            raise

    def create_roofing_campaign(self, test_mode: bool = False) -> Dict:
        """
        Create SOP-002R campaign (Roofing only).
        4-email Written-First sequence over 7 days.

        Key rules:
        - No links in emails (hurts deliverability)
        - No AI mentions — talk about outcomes only
        - No bullet points — conversational prose
        - Frame as "system" not "website"
        - Ambiguous subject lines (look like personal email)
        - 100-130 words per email
        - Prototype link delivered AFTER reply via automated sequence
        """
        from datetime import datetime

        timestamp = datetime.now().strftime('%Y%m%d')
        campaign_name = f"Cold_Roofing_{timestamp}"
        if test_mode:
            campaign_name += "_TEST"

        logger.info(f"Creating SOP-002R campaign: {campaign_name}")

        campaign_config = {
            "name": campaign_name,
            "status": 2,  # Active
            "sequences": [
                {
                    "steps": [
                        # Email 1: Day 1 — Traffic not converting
                        {
                            "type": "email",
                            "delay": 0,
                            "variants": [
                                {
                                    "subject": "{{firstName}}",
                                    "body": self._get_roofing_email_1_body()
                                },
                                {
                                    "subject": "question",
                                    "body": self._get_roofing_email_1_body()
                                },
                                {
                                    "subject": "quick thought",
                                    "body": self._get_roofing_email_1_body()
                                }
                            ]
                        },
                        # Email 2: Day 3 — Referral verification
                        {
                            "type": "email",
                            "delay": 2,
                            "variants": [
                                {
                                    "subject": "Re: {{firstName}}",
                                    "body": self._get_roofing_email_2_body()
                                },
                                {
                                    "subject": "forgot to mention",
                                    "body": self._get_roofing_email_2_body()
                                },
                                {
                                    "subject": "one more thing",
                                    "body": self._get_roofing_email_2_body()
                                }
                            ]
                        },
                        # Email 3: Day 5 — Buying behavior shift
                        {
                            "type": "email",
                            "delay": 2,
                            "variants": [
                                {
                                    "subject": "honest question",
                                    "body": self._get_roofing_email_3_body()
                                },
                                {
                                    "subject": "thought about this",
                                    "body": self._get_roofing_email_3_body()
                                },
                                {
                                    "subject": "real quick",
                                    "body": self._get_roofing_email_3_body()
                                }
                            ]
                        },
                        # Email 4: Day 7 — Graceful exit
                        {
                            "type": "email",
                            "delay": 2,
                            "variants": [
                                {
                                    "subject": "no hard feelings",
                                    "body": self._get_roofing_email_4_body()
                                },
                                {
                                    "subject": "last thing",
                                    "body": self._get_roofing_email_4_body()
                                },
                                {
                                    "subject": "all good either way",
                                    "body": self._get_roofing_email_4_body()
                                }
                            ]
                        }
                    ]
                }
            ],
            "email_gap": 9,
            "text_only": True,  # Plain text — no HTML, looks like personal email
            "stop_on_reply": True,
            "link_tracking": False,  # No link tracking — no links in roofing emails
            "open_tracking": True,
            "daily_limit": 1000,
            "campaign_schedule": {
                "schedules": [
                    {
                        "name": "Contractor Hours",
                        "timing": {
                            "from": "07:00",
                            "to": "17:00"
                        },
                        "days": {
                            "0": False,
                            "1": True,
                            "2": True,
                            "3": True,
                            "4": True,
                            "5": True,
                            "6": False
                        },
                        "timezone": "America/Chicago"
                    }
                ]
            }
        }

        try:
            result = self._make_request("POST", "campaigns", campaign_config)
            logger.info(f"✅ SOP-002R roofing campaign created: {campaign_name}")
            return result
        except Exception as e:
            logger.error(f"❌ SOP-002R roofing campaign creation failed: {str(e)}")
            raise

    # =========================================================================
    # Roofing email bodies (SOP-002R) — plain text, no HTML
    # =========================================================================

    def _get_roofing_email_1_body(self) -> str:
        """Roofing Email 1: Traffic not converting (Day 1)
        Note: Starts AFTER automated personalized opener ending with
        'I figured I'd reach out right?'"""
        return """One thing I notice with a lot of roofing companies is the traffic is there but most of that traffic isn't converting at the rate it should be.

People are finding you, checking out your page — but a big chunk of them leave without ever calling or booking an estimate. And if you're driving traffic through ads or SEO, that's money you're spending on leads that could be turning into jobs but aren't.

I built a system specifically for roofing companies that's designed to close that gap — takes the traffic you're already getting and converts more of it into actual phone calls and booked estimates.

It's live right now, you can click through the whole thing. Not a concept, not a pitch.

Want me to send it over?"""

    def _get_roofing_email_2_body(self) -> str:
        """Roofing Email 2: Referral verification (Day 3)"""
        return """Hey {{firstName}}, shot you a note a couple days ago — figured it might've gotten buried.

Wanted to bring up something most roofers don't think about. Even your referrals — the people who already heard your name from someone they trust — most of them are still Googling you before they ever pick up the phone.

And when they land on your page, they're making a snap decision. Does this look legit? Do I trust these guys with my roof? If anything feels off or outdated, they hesitate. And a lot of the time that hesitation is enough to lose them even though they were practically sold before they got there.

I built a system that makes sure that doesn't happen. Want me to send it over?"""

    def _get_roofing_email_3_body(self) -> str:
        """Roofing Email 3: Buying behavior shift (Day 5)"""
        return """{{firstName}}, when's the last time you actually browsed through a bunch of websites before making a decision? Nobody does that anymore. People show up with their mind almost made up, card half out, and they're deciding in seconds — not minutes.

So when someone lands on your page ready to book a roofer, you either convince them right there or they're gone. Back button, on to the next guy.

Most roofing sites were built for a world where people browsed around and compared. That's not how buyers work now. They show up ready to act and if your page doesn't close them on the spot, someone else's will.

I built a system specifically for roofing companies that's designed to close on the spot. Takes two minutes to look through — want me to shoot it over?"""

    def _get_roofing_email_4_body(self) -> str:
        """Roofing Email 4: Graceful exit (Day 7)"""
        return """Hey {{firstName}}, I know running a roofing company doesn't leave a lot of time for emails from people you don't know so I get it.

I've reached out a few times because I genuinely think what I built could help you book more jobs from the traffic you're already getting. It's live right now, built specifically for roofing companies, and it takes a couple minutes to see the whole thing.

I'm not going to keep filling up your inbox. This is my last one.

But if you ever want to see it, just reply to this email and I'll send it right over. The offer doesn't expire, I just won't keep reaching out."""

    def _get_email_1_body(self, industry: str) -> str:
        """Email 1: Personalized Curiosity Hook per Master SOP"""
        return f"""<div>Hi {{{{firstName}}}},</div>
<div><br /></div>
<div>{{{{personalization}}}}</div>
<div><br /></div>
<div>I've been studying what separates the fastest-growing {industry} contractors from everyone else, and I found something interesting.</div>
<div><br /></div>
<div>The top 15% are using AI and automation in ways most contractors haven't even considered yet - not just for one thing, but for completely transforming how they grow and operate.</div>
<div><br /></div>
<div>The difference in results is honestly stunning. We're talking 25-40% growth without working longer hours.</div>
<div><br /></div>
<div>I've mapped out the main strategies that are working right now in your local market, and I'd love to share what I'm seeing.</div>
<div><br /></div>
<div>Would you be open to a quick 15-minute call? I can show you exactly what's possible for {{{{companyName}}}} based on your specific situation.</div>
<div><br /></div>
<div>Best,</div>
<div>Lorenzo</div>
<div><br /></div>
<div>P.S. Even if it's not a fit, you'll walk away with actionable ideas you can use immediately.</div>"""

    def _get_email_2_body(self, industry: str) -> str:
        """Email 2: AI Transformation + Scarcity per Master SOP"""
        return f"""<div>Hey {{{{firstName}}}},</div>
<div><br /></div>
<div>The AI automation systems I mentioned are helping {industry} contractors generate 20-35% more leads AND streamline their operations.</div>
<div><br /></div>
<div>AI is transforming every industry, and {industry} is no exception. Every smart contractor will eventually automate their business - the question is whether you're early or late to adopt.</div>
<div><br /></div>
<div>Most contractors are still handling service requests manually, chasing follow-ups by hand, and scheduling with spreadsheets - while forward-thinking competitors implement AI automation and scale rapidly.</div>
<div><br /></div>
<div>The contractors who implement complete AI-powered lead generation and operational automation now will dominate their markets while others scramble to catch up later.</div>
<div><br /></div>
<div>I have 2 spots remaining this month. After that, enrollment closes until next quarter.</div>
<div><br /></div>
<div>Ready to future-proof {{{{companyName}}}} with AI automation? Reply and I'll send my calendar.</div>
<div><br /></div>
<div>Best,</div>
<div>Lorenzo</div>"""

    def _get_email_3_body(self, industry: str) -> str:
        """Email 3: Breakup + Feedback per Master SOP"""
        return f"""<div>Hey {{{{firstName}}}},</div>
<div><br /></div>
<div>I'm going to stop reaching out since I haven't heard back, but I'm genuinely curious - what made you decide against exploring growth strategies for {{{{companyName}}}}?</div>
<div><br /></div>
<div>Was it:</div>
<div>- Bad timing?</div>
<div>- Already have systems in place?</div>
<div>- Skeptical about new approaches?</div>
<div>- Happy with current growth rate?</div>
<div>- Something else?</div>
<div><br /></div>
<div>No judgment at all - just helps me understand what {industry} contractors are prioritizing these days.</div>
<div><br /></div>
<div>If things change and you want to explore what's possible for your business, just reply to this email.</div>
<div><br /></div>
<div>Best,</div>
<div>Lorenzo</div>"""

    def get_campaigns(self) -> List[Dict]:
        """Get all campaigns"""
        result = self._make_request("GET", "campaigns")
        campaigns = result.get('items', result)
        return campaigns

    def delete_campaign(self, campaign_id: str) -> Dict:
        """Delete a campaign"""
        result = self._make_request("DELETE", f"campaigns/{campaign_id}", {})
        logger.info(f"Deleted campaign: {campaign_id}")
        return result


def create_all_industry_campaigns(test_mode: bool = False) -> Dict:
    """
    Create campaigns for all industries.
    Routes each industry to the correct SOP:
    - HVAC, Plumbing, Electrical → SOP-002 (3-email)
    - Roofing → SOP-002R (4-email Written-First)

    Args:
        test_mode: If True, creates test campaigns

    Returns:
        Results dict with created campaigns
    """
    builder = InstantlyCampaignBuilder()

    industries = ["HVAC", "Roofing", "Plumbing", "Electrical"]

    results = {
        "created": [],
        "failed": [],
        "test_mode": test_mode
    }

    for industry in industries:
        try:
            sop = "SOP-002R" if industry == "Roofing" else "SOP-002"
            campaign = builder.create_cold_campaign(industry=industry, test_mode=test_mode)
            results["created"].append({
                "industry": industry,
                "sop": sop,
                "campaign": campaign
            })
            logger.info(f"✅ Created {industry} campaign ({sop})")

        except Exception as e:
            results["failed"].append({
                "industry": industry,
                "error": str(e)
            })
            logger.error(f"❌ Failed to create {industry} campaign: {str(e)}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Create Instantly campaigns')
    parser.add_argument('--test', action='store_true', help='Create test campaigns')
    parser.add_argument('--industry', type=str, help='Create single industry campaign (HVAC, Roofing, Plumbing, Electrical)')
    parser.add_argument('--list', action='store_true', help='List existing campaigns')

    args = parser.parse_args()

    builder = InstantlyCampaignBuilder()

    if args.list:
        print("\n📊 Existing Campaigns:")
        campaigns = builder.get_campaigns()
        for camp in campaigns:
            print(f"   - {camp.get('name', 'Unnamed')} (ID: {camp.get('id')})")

    elif args.industry:
        sop = "SOP-002R" if args.industry == "Roofing" else "SOP-002"
        print(f"\n🚀 Creating {args.industry} campaign ({sop})...")
        result = builder.create_cold_campaign(industry=args.industry, test_mode=args.test)
        print(f"✅ Campaign created: {result.get('name')}")
        if args.industry == "Roofing":
            print("   📋 4-email Written-First pathway")
            print("   🚫 No links, no AI mentions, plain text")
            print("   📩 Prototype delivered after reply via automated sequence")

    else:
        print("\n🚀 Creating all industry campaigns...")
        print("   SOP-002: HVAC, Plumbing, Electrical (3-email)")
        print("   SOP-002R: Roofing (4-email Written-First)")
        results = create_all_industry_campaigns(test_mode=args.test)
        print(f"\n✅ Created: {len(results['created'])}")
        for c in results['created']:
            print(f"   - {c['industry']} ({c['sop']}): {c['campaign'].get('name', 'created')}")
        print(f"❌ Failed: {len(results['failed'])}")
