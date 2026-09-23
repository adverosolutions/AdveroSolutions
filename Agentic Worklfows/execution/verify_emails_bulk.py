"""
Bulk Email Verification via MillionVerifier
Sends candidate emails to MillionVerifier API and returns verification results.

API docs: https://app.millionverifier.com/api-docs
Cost: $0.0006 per check at the entry tier ($30/mo for 50k verifications/year).

Returns per email:
    status: 'ok' (deliverable) | 'invalid' | 'risky' | 'unknown'
    is_catch_all: True if domain accepts all emails (low confidence)
    is_disposable: True if temp/disposable domain
    is_role: True if role-based (info@, sales@)
    free: True if free email provider (gmail, yahoo)

Caller should:
- Use 'ok' + non-catch-all = HIGH confidence
- Use 'ok' + catch-all = MEDIUM (mailbox might silently bounce)
- Skip 'invalid', 'risky', 'unknown' for personal-pattern emails
- Skip 'is_role' if seeking decision maker specifically
"""

import os
import time
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(_env_path, override=True)

import requests

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

MV_API_KEY = os.getenv('MILLIONVERIFIER_API_KEY')
MV_API_URL = "https://api.millionverifier.com/api/v3/"


def verify_email(email: str, timeout_sec: int = 10) -> Optional[Dict]:
    """
    Verify a single email via MillionVerifier real-time API.

    Returns dict with normalized fields, or None on error.
    """
    if not MV_API_KEY:
        logger.error("MILLIONVERIFIER_API_KEY not set in .env")
        return None

    if not email or '@' not in email:
        return None

    params = {
        'api': MV_API_KEY,
        'email': email,
        'timeout': timeout_sec,
    }

    try:
        resp = requests.get(MV_API_URL, params=params, timeout=timeout_sec + 5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"MillionVerifier error for {email}: {e}")
        return None

    return _normalize_result(email, data)


def verify_emails(emails: List[str], delay: float = 0.2) -> List[Dict]:
    """
    Verify a batch of emails sequentially. Returns list of result dicts
    (one per input email, in same order).

    Args:
        emails: List of email addresses
        delay: Seconds between calls (rate-limit cushion)
    """
    results = []
    for i, email in enumerate(emails):
        result = verify_email(email)
        if result is None:
            result = {
                'email': email,
                'status': 'error',
                'is_deliverable': False,
                'is_catch_all': False,
                'is_disposable': False,
                'is_role': False,
                'is_free': False,
                'raw': None,
            }
        results.append(result)
        if i < len(emails) - 1 and delay > 0:
            time.sleep(delay)
    return results


def _normalize_result(email: str, data: Dict) -> Dict:
    """
    Normalize MillionVerifier response into a stable shape.

    MV v3 response includes 'result' field with values:
        ok, catch_all, unknown, disposable, invalid, error
    Plus subscriber/quality/free fields.
    """
    result = (data.get('result') or '').lower()
    quality = (data.get('quality') or '').lower()

    # Treat both 'ok' and 'catch_all' as deliverable — the mailbox can receive mail
    # in both cases. The is_catch_all flag distinguishes confidence downstream.
    is_deliverable = result in ('ok', 'catch_all')
    is_catch_all = result == 'catch_all' or 'catch' in quality
    is_disposable = result == 'disposable' or bool(data.get('disposable'))
    is_role = bool(data.get('role'))
    is_free = bool(data.get('free'))

    if result == 'ok':
        status = 'valid'
    elif result == 'catch_all':
        status = 'catch_all'
    elif result == 'invalid':
        status = 'invalid'
    elif result == 'disposable':
        status = 'disposable'
    elif result in ('unknown', ''):
        status = 'unknown'
    else:
        status = result

    return {
        'email': email,
        'status': status,
        'is_deliverable': is_deliverable,
        'is_catch_all': is_catch_all,
        'is_disposable': is_disposable,
        'is_role': is_role,
        'is_free': is_free,
        'raw': data,
    }


def check_credits() -> Optional[int]:
    """Returns remaining MillionVerifier credits (None on error)."""
    if not MV_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.millionverifier.com/api/v3/credits",
            params={'api': MV_API_KEY},
            timeout=10,
        )
        return resp.json().get('credits')
    except Exception:
        return None


if __name__ == "__main__":
    if not MV_API_KEY:
        print("MILLIONVERIFIER_API_KEY not set — add it to .env to test")
    else:
        credits = check_credits()
        print(f"Credits remaining: {credits}")
        print("\nTest verifications:")
        for email in ['support@google.com', 'definitely-not-real-1234567@example.com']:
            print(f"\n  {email}")
            r = verify_email(email)
            if r:
                print(f"    status: {r['status']}")
                print(f"    deliverable: {r['is_deliverable']}")
                print(f"    catch_all: {r['is_catch_all']}")
                print(f"    role: {r['is_role']}")
