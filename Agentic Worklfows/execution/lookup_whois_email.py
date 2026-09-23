"""
WHOIS Email Lookup
Some domain registrations expose the registrant's email directly in WHOIS data.
Free, fast (~1-2 sec), no API costs.

Most registrars now use privacy proxies (Whoisguard, GoDaddy redact, etc.) which
mask the email behind a forwarding address — those are filtered out.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Privacy proxy domains we should ignore (registrar-provided forwarders)
PRIVACY_PROXY_DOMAINS = {
    'whoisguard.com', 'whoisproxy.org', 'privacyprotect.org',
    'domainsbyproxy.com', 'contactprivacy.com', 'privatewhois.net',
    'privacy.link', 'nameshield.net', 'gandi.net',
    'godaddy.com', 'wildwestdomains.com', 'registrar-servers.com',
    'enom.com', 'tucows.com', 'porkbun.com',
    'cloudflare.com', 'amazonregistrar.com',
}


def lookup_domain_email(domain: str) -> Optional[str]:
    """
    Look up the registrant email for a domain via WHOIS.

    Returns the email, or None if not found / hidden behind privacy proxy.
    """
    if not domain:
        return None

    try:
        import whois
    except ImportError:
        logger.warning("python-whois not installed — skipping WHOIS lookup")
        return None

    try:
        record = whois.whois(domain)
    except Exception as e:
        logger.debug(f"WHOIS lookup failed for {domain}: {e}")
        return None

    candidates = []
    raw = record.emails if hasattr(record, 'emails') else None
    if raw:
        if isinstance(raw, str):
            candidates.append(raw)
        elif isinstance(raw, (list, tuple)):
            candidates.extend(raw)

    for email in candidates:
        if not email or '@' not in str(email):
            continue
        email = str(email).lower().strip()
        domain_part = email.split('@', 1)[1]
        if domain_part in PRIVACY_PROXY_DOMAINS:
            continue
        if any(domain_part.endswith('.' + p) for p in PRIVACY_PROXY_DOMAINS):
            continue
        if 'abuse' in email or 'noreply' in email:
            continue
        return email

    return None


if __name__ == "__main__":
    print("Test 1: amstillroofing.com")
    print(f"  → {lookup_domain_email('amstillroofing.com')}")
    print("Test 2: google.com (will be privacy-protected)")
    print(f"  → {lookup_domain_email('google.com')}")
