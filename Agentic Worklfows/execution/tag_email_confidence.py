"""
Tag Email Confidence
Pure deterministic logic — given the outputs of website scraping + verification,
returns the best email candidate with a confidence tag.

Confidence tiers:
  HIGH    — safe to send: scraped near owner OR pattern-verified + non-catch-all
  MEDIUM  — usable but verify deliverability over time: catch-all domain or partial match
  LOW     — generic role mailbox (info@/contact@) — goes to *someone*, not the owner
  REJECT  — no usable email found, skip the lead
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def select_best_email(
    scraped_emails: List[Dict],
    verified_patterns: List[Dict],
    first_name: str = '',
    last_name: str = '',
) -> Dict:
    """
    Pick the best email + confidence tag from scraping + verification outputs.

    Args:
        scraped_emails: List from scrape_website_emails — each item has
            {email, match: HIGH|MEDIUM|LOW|GENERIC, source_url}
        verified_patterns: List from verify_emails_bulk — each item has
            {email, status, is_deliverable, is_catch_all, is_role, ...}
        first_name, last_name: Owner identifiers for matching

    Returns:
        {
          'email': '...' or None,
          'confidence': 'HIGH' | 'MEDIUM' | 'LOW' | 'REJECT',
          'reason': human-readable explanation,
          'source': 'scraped' | 'pattern' | None,
        }
    """
    # --- Tier 1: scraped email that matches the owner's name (HIGH) ---
    for s in scraped_emails:
        if s.get('match') == 'HIGH':
            return _result(
                s['email'], 'HIGH', 'scraped',
                f"Scraped from {s.get('source_url', 'website')}, matches owner name pattern"
            )

    # --- Tier 2: verified pattern email, deliverable, non-catch-all (HIGH) ---
    for v in verified_patterns:
        if v.get('is_deliverable') and not v.get('is_catch_all') and not v.get('is_role'):
            return _result(
                v['email'], 'HIGH', 'pattern',
                "Pattern-verified deliverable, non-catch-all, non-role"
            )

    # --- Tier 3: scraped email with MEDIUM name match ---
    for s in scraped_emails:
        if s.get('match') == 'MEDIUM':
            return _result(
                s['email'], 'MEDIUM', 'scraped',
                f"Scraped from {s.get('source_url', 'website')}, partial name match"
            )

    # --- Tier 4: verified pattern email, deliverable, but catch-all (MEDIUM) ---
    for v in verified_patterns:
        if v.get('is_deliverable') and v.get('is_catch_all') and not v.get('is_role'):
            return _result(
                v['email'], 'MEDIUM', 'pattern',
                "Pattern-verified deliverable but domain is catch-all (may bounce silently)"
            )

    # --- Tier 5: scraped email with LOW match (last name only or unrelated personal) ---
    for s in scraped_emails:
        if s.get('match') == 'LOW':
            return _result(
                s['email'], 'LOW', 'scraped',
                "Scraped personal email, weak name match"
            )

    # --- Tier 6: scraped generic email (info@, contact@) ---
    for s in scraped_emails:
        if s.get('match') == 'GENERIC':
            return _result(
                s['email'], 'LOW', 'scraped',
                f"Generic role mailbox from {s.get('source_url', 'website')}"
            )

    # --- Tier 7: verified role/generic pattern (info@, etc.) ---
    for v in verified_patterns:
        if v.get('is_deliverable') and v.get('is_role'):
            return _result(
                v['email'], 'LOW', 'pattern',
                "Verified role mailbox (info@/contact@) — not specific to owner"
            )

    # --- No usable email ---
    return _result(None, 'REJECT', None, "No deliverable email found")


def _result(email: Optional[str], confidence: str, source: Optional[str], reason: str) -> Dict:
    return {
        'email': email,
        'confidence': confidence,
        'source': source,
        'reason': reason,
    }


if __name__ == "__main__":
    # Test cases
    tests = [
        {
            'name': 'Scraped HIGH match wins everything',
            'scraped': [{'email': 'john@plumbing.com', 'match': 'HIGH', 'source_url': 'https://plumbing.com/about'}],
            'verified': [{'email': 'jsmith@plumbing.com', 'status': 'valid', 'is_deliverable': True, 'is_catch_all': False, 'is_role': False}],
            'expected_conf': 'HIGH',
        },
        {
            'name': 'No scraped, pattern verified non-catch-all',
            'scraped': [],
            'verified': [{'email': 'jsmith@plumbing.com', 'status': 'valid', 'is_deliverable': True, 'is_catch_all': False, 'is_role': False}],
            'expected_conf': 'HIGH',
        },
        {
            'name': 'Catch-all domain falls to MEDIUM',
            'scraped': [],
            'verified': [{'email': 'john@plumbing.com', 'status': 'valid', 'is_deliverable': True, 'is_catch_all': True, 'is_role': False}],
            'expected_conf': 'MEDIUM',
        },
        {
            'name': 'Only generic info@',
            'scraped': [{'email': 'info@plumbing.com', 'match': 'GENERIC', 'source_url': 'https://plumbing.com/contact'}],
            'verified': [],
            'expected_conf': 'LOW',
        },
        {
            'name': 'Nothing found',
            'scraped': [],
            'verified': [{'email': 'john@plumbing.com', 'is_deliverable': False, 'is_catch_all': False, 'is_role': False}],
            'expected_conf': 'REJECT',
        },
    ]

    for t in tests:
        result = select_best_email(t['scraped'], t['verified'], 'John', 'Smith')
        status = 'PASS' if result['confidence'] == t['expected_conf'] else 'FAIL'
        print(f"{status} | {t['name']}")
        print(f"     → {result['confidence']}: {result['email']} ({result['reason']})")
