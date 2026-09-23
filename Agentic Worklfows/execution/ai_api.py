"""
OpenAI API Integration
Handles AI response generation for email replies
"""

import os
from openai import OpenAI
from typing import Dict, List, Optional
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

class AIResponseGenerator:
    """Wrapper for OpenAI API operations"""

    def __init__(self):
        """Initialize OpenAI API client"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        model = os.getenv('OPENAI_MODEL', 'gpt-4o')

        self.client = OpenAI(api_key=api_key)
        self.model = model

        logger.info(f"OpenAI API initialized ({model})")

    def generate_email_response(self,
                               lead_info: Dict,
                               reply_content: str,
                               response_type: str = "positive_reply") -> str:
        """
        Generate personalized email response

        Args:
            lead_info: Dict with lead data (name, company, industry, etc.)
            reply_content: The email they sent
            response_type: Type of response (positive_reply, objection, info_request, etc.)

        Returns:
            Generated email response text
        """

        # Build context for AI
        system_prompt = """You are Lorenzo from AdveroSolutions, an AI automation expert helping contractors grow their businesses.

Your communication style:
- Warm, professional, consultative
- Focus on their specific situation
- Never pushy or sales-y
- Emphasize results and transformation
- Use curiosity and insight

Your goal: Get them to book a 15-minute discovery call."""

        user_prompt = f"""Generate a response to this lead's email.

LEAD INFO:
- Name: {lead_info.get('first_name', '')} {lead_info.get('last_name', '')}
- Company: {lead_info.get('company_name', '')}
- Industry: {lead_info.get('industry', '')}

THEIR EMAIL:
{reply_content}

RESPONSE TYPE: {response_type}

Generate a response that:
1. Addresses their specific question/concern
2. Reinforces the value (25-40% growth, AI automation benefits)
3. Includes booking link at the end: [BOOKING_LINK]
4. Keeps it under 150 words
5. Natural, conversational tone

DO NOT include subject line. Just the email body."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            generated_text = response.choices[0].message.content
            logger.info(f"Generated response for {lead_info.get('company_name', 'unknown')}")

            return generated_text

        except Exception as e:
            logger.error(f"OpenAI API request failed: {str(e)}")
            raise

    def classify_reply_sentiment(self, reply_content: str) -> str:
        """
        Classify email reply sentiment

        Returns: positive, neutral, negative, objection, info_request, out_of_office
        """

        system_prompt = """You are an email classifier. Analyze the email and return ONLY ONE WORD from this list:
- positive (interested, wants to learn more, asking questions)
- neutral (acknowledging but not committing)
- negative (not interested, remove me)
- objection (price concern, timing issue, already have solution)
- info_request (what is this, tell me more)
- out_of_office (automated OOO response)"""

        user_prompt = f"""Classify this email reply:

{reply_content}

Return ONLY the classification word, nothing else."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=20,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            classification = response.choices[0].message.content.strip().lower()
            logger.info(f"Classified reply as: {classification}")

            return classification

        except Exception as e:
            logger.error(f"Classification failed: {str(e)}")
            return "neutral"

    def extract_objection(self, reply_content: str) -> str:
        """Extract specific objection from email"""

        system_prompt = "Extract the main objection or concern from this email in 1-2 sentences."

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=100,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email:\n{reply_content}"}
                ]
            )

            objection = response.choices[0].message.content.strip()
            logger.info(f"Extracted objection: {objection[:50]}...")

            return objection

        except Exception as e:
            logger.error(f"Objection extraction failed: {str(e)}")
            return "General objection"


def get_ai_client() -> AIResponseGenerator:
    """Get initialized AI API client"""
    return AIResponseGenerator()


if __name__ == "__main__":
    # Test OpenAI API
    try:
        client = AIResponseGenerator()
        print("✅ OpenAI API connected")
        print(f"📊 Using model: {client.model}")

        # Test classification
        test_reply = "This sounds interesting! I'd love to learn more about how AI automation could help my business grow."

        print("\n🧪 Testing reply classification...")
        sentiment = client.classify_reply_sentiment(test_reply)
        print(f"   Sentiment: {sentiment}")

        # Test response generation
        print("\n🧪 Testing response generation...")
        lead_info = {
            "first_name": "John",
            "last_name": "Smith",
            "company_name": "HVAC Pros LLC",
            "industry": "HVAC"
        }

        response = client.generate_email_response(lead_info, test_reply, "positive_reply")
        print(f"\n   Generated response:\n")
        print(f"   {response}\n")

        print("=" * 60)
        print("✅ OpenAI API fully functional!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ OpenAI API test failed: {str(e)}")
        import traceback
        traceback.print_exc()
