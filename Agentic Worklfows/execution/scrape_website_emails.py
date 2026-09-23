"""
Scrape Website Emails
Fetches a contractor's website and extracts any email addresses found.

Tries common email-publishing pages first (Contact, About, Team, Footer)
to get higher quality emails (vs random emails buried in blog posts).

Returns emails with priority hints:
  - HIGH: found near owner's name on About/Team page
  - MEDIUM: found on Contact page
  - LOW: generic email patterns (info@, contact@, hello@)

Free — no API costs. Just compute time.
"""

import os
import re
import logging
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Pages most likely to contain owner contact info
PRIORITY_PAGES = [
    '/contact', '/contact-us', '/contact_us',
    '/about', '/about-us', '/about_us',
    '/team', '/our-team', '/staff', '/leadership',
    '/meet-the-team', '/meet-our-team',
    '/news', '/press', '/press-releases', '/blog',
    '/careers', '/jobs',
    '/testimonials', '/reviews',
]

EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Detect obfuscated emails: "name [at] domain.com", "name (at) domain (dot) com"
OBFUSCATED_REGEX = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*[\[\(]?\s*(?:at|AT)\s*[\]\)]?\s*"
    r"([A-Za-z0-9.-]+)\s*[\[\(]?\s*(?:dot|DOT|\.)\s*[\]\)]?\s*([A-Za-z]{2,})"
)

# Garbage emails to ignore
JUNK_DOMAINS = {
    'sentry.io', 'wixpress.com', 'wix.com', 'godaddy.com',
    'squarespace.com', 'example.com', 'email.com', 'domain.com',
    'yourdomain.com', 'company.com', 'mail.com',
}
JUNK_PREFIXES = {'noreply', 'no-reply', 'donotreply', 'test', 'example'}

GENERIC_PREFIXES = {
    'info', 'contact', 'office', 'hello', 'admin', 'support',
    'service', 'help', 'sales', 'inquiries', 'team',
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _is_junk_email(email: str) -> bool:
    email = email.lower()
    if '@' not in email:
        return True
    prefix, domain = email.split('@', 1)
    if domain in JUNK_DOMAINS:
        return True
    if prefix in JUNK_PREFIXES:
        return True
    if domain.endswith('.png') or domain.endswith('.jpg') or domain.endswith('.gif'):
        return True
    return False


def _is_generic_email(email: str) -> bool:
    prefix = email.split('@', 1)[0].lower()
    return prefix in GENERIC_PREFIXES


def _normalize_url(website: str) -> Optional[str]:
    """Normalize website URL to https://domain.com format."""
    if not website:
        return None
    website = website.strip()
    if not website.startswith(('http://', 'https://')):
        website = 'https://' + website
    try:
        parsed = urlparse(website)
        if not parsed.netloc:
            return None
        return f"https://{parsed.netloc}"
    except Exception:
        return None


def _fetch_page(url: str, timeout: int = 8) -> Optional[str]:
    """Fetch a URL and return HTML text, or None on failure."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={'User-Agent': USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception as e:
        logger.debug(f"Fetch failed for {url}: {e}")
    return None


def _extract_emails_from_html(html: str, target_domain: Optional[str] = None) -> Set[str]:
    """Extract emails from HTML, including obfuscated forms. Optionally filter to a domain."""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(' ', strip=True)
    # Also pull mailto links + href/data attributes (sometimes contain emails)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().startswith('mailto:'):
            text += ' ' + href[7:].split('?', 1)[0]

    found = set()
    # Direct emails
    for match in EMAIL_REGEX.findall(text):
        email = match.lower()
        if _is_junk_email(email):
            continue
        if target_domain:
            domain = email.split('@', 1)[1]
            if domain != target_domain and not domain.endswith('.' + target_domain):
                continue
        found.add(email)

    # Deobfuscate "name [at] domain [dot] com" style
    for prefix, mid, tld in OBFUSCATED_REGEX.findall(text):
        email = f"{prefix.lower()}@{mid.lower()}.{tld.lower()}"
        if _is_junk_email(email):
            continue
        if target_domain:
            domain = email.split('@', 1)[1]
            if domain != target_domain and not domain.endswith('.' + target_domain):
                continue
        found.add(email)

    return found


def _name_match_score(email: str, first_name: str = '', last_name: str = '') -> str:
    """
    Score an email's match against an owner's name.

    Returns: 'HIGH' | 'MEDIUM' | 'LOW' | 'GENERIC'
    """
    if _is_generic_email(email):
        return 'GENERIC'

    if not first_name and not last_name:
        return 'LOW'

    prefix = email.split('@', 1)[0].lower()
    fn = first_name.lower().strip() if first_name else ''
    ln = last_name.lower().strip() if last_name else ''

    if fn and ln:
        patterns = [
            f"{fn}.{ln}", f"{fn}{ln}", f"{fn[0]}{ln}",
            f"{fn}{ln[0]}", f"{ln}.{fn}", f"{ln}{fn[0]}",
        ]
        if prefix in patterns:
            return 'HIGH'
    if fn and prefix == fn:
        return 'HIGH'
    if ln and prefix == ln:
        return 'MEDIUM'
    return 'LOW'


def scrape_website_emails(
    website: str,
    first_name: str = '',
    last_name: str = '',
    max_pages: int = 4,
) -> List[Dict[str, str]]:
    """
    Fetch a website and extract emails. Returns list of dicts:
        [{"email": "john@plumbing.com", "match": "HIGH", "source_url": "..."}]

    Sorted with HIGH match first, then MEDIUM, LOW, GENERIC.
    """
    base = _normalize_url(website)
    if not base:
        return []

    target_domain = urlparse(base).netloc.lower()
    if target_domain.startswith('www.'):
        target_domain = target_domain[4:]

    pages_to_try = ['/'] + PRIORITY_PAGES[:max_pages]
    seen_emails: Dict[str, Dict[str, str]] = {}

    for path in pages_to_try:
        url = urljoin(base, path)
        html = _fetch_page(url)
        if not html:
            continue
        emails = _extract_emails_from_html(html, target_domain)
        for email in emails:
            match = _name_match_score(email, first_name, last_name)
            if email not in seen_emails or _better_match(match, seen_emails[email]['match']):
                seen_emails[email] = {
                    'email': email,
                    'match': match,
                    'source_url': url,
                }

    rank = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'GENERIC': 3}
    return sorted(seen_emails.values(), key=lambda e: rank.get(e['match'], 4))


def _better_match(a: str, b: str) -> bool:
    rank = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'GENERIC': 3}
    return rank.get(a, 99) < rank.get(b, 99)


if __name__ == "__main__":
    print("Test 1: Plumbing site without owner name hint")
    results = scrape_website_emails("https://example.com")
    for r in results:
        print(f"  [{r['match']}] {r['email']}  ({r['source_url']})")

    print("\nTest 2: With owner name (real site)")
    results = scrape_website_emails("https://amstillroofing.com", "Sam", "Stilley")
    for r in results:
        print(f"  [{r['match']}] {r['email']}  ({r['source_url']})")
