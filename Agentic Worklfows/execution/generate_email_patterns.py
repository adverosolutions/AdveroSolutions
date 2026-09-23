"""
Generate Email Patterns
Given an owner's first name, last name, and company domain, returns a ranked list
of likely email patterns to check against a verifier.

Patterns are ranked by likelihood for SMB contractor businesses:
1. firstname@domain (most common for solo/small operators)
2. firstname.lastname@domain (common for established businesses)
3. flastname@domain (common for medium businesses)
4. firstinitial+lastname@domain (alt format)
5. lastnamefirstname@domain (rare but happens)

Generic patterns (info@, owner@, contact@) are EXCLUDED from this generator —
they should be handled separately as low-confidence fallbacks.
"""

import re
from typing import List, Optional
from urllib.parse import urlparse


def extract_domain(website: str) -> Optional[str]:
    """Extract clean domain from a website URL.

    Examples:
        https://www.abcplumbing.com/ → abcplumbing.com
        http://abcplumbing.com → abcplumbing.com
        abcplumbing.com → abcplumbing.com
    """
    if not website:
        return None

    website = website.strip()
    if not website.startswith(('http://', 'https://')):
        website = 'http://' + website

    try:
        parsed = urlparse(website)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        if not netloc or '.' not in netloc:
            return None
        return netloc
    except Exception:
        return None


def normalize_name(name: str) -> str:
    """Normalize a name for use in an email address."""
    if not name:
        return ''
    name = name.lower().strip()
    name = re.sub(r"[^a-z]", '', name)
    return name


def generate_owner_patterns(
    first_name: str,
    last_name: str,
    domain: str
) -> List[str]:
    """
    Generate ranked list of likely owner email patterns.

    Returns:
        List of email candidates, ranked by likelihood (most likely first).
        Empty list if inputs are insufficient.
    """
    fn = normalize_name(first_name)
    ln = normalize_name(last_name)

    if not domain:
        return []

    patterns = []

    # Most common, ranked by SMB contractor likelihood
    if fn:
        patterns.append(f"{fn}@{domain}")

    if fn and ln:
        # Standard combinations
        patterns.append(f"{fn}.{ln}@{domain}")           # john.smith
        patterns.append(f"{fn[0]}{ln}@{domain}")         # jsmith
        patterns.append(f"{fn}{ln[0]}@{domain}")         # johns
        patterns.append(f"{fn}{ln}@{domain}")            # johnsmith
        # Hyphenated and underscored
        patterns.append(f"{fn}-{ln}@{domain}")           # john-smith
        patterns.append(f"{fn}_{ln}@{domain}")           # john_smith
        # Initial-only and reverse
        patterns.append(f"{fn[0]}.{ln}@{domain}")        # j.smith
        patterns.append(f"{fn}.{ln[0]}@{domain}")        # john.s
        patterns.append(f"{ln}.{fn}@{domain}")           # smith.john
        patterns.append(f"{ln}{fn[0]}@{domain}")         # smithj
        patterns.append(f"{ln}{fn}@{domain}")            # smithjohn
        patterns.append(f"{ln}_{fn}@{domain}")           # smith_john
        patterns.append(f"{fn[0]}{ln[0]}@{domain}")      # js (rare but happens)

    if ln and not fn:
        patterns.append(f"{ln}@{domain}")

    if ln:
        patterns.append(f"{ln}@{domain}")

    seen = set()
    unique = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


def generate_generic_patterns(domain: str) -> List[str]:
    """
    Generate generic catch-all patterns (info@, contact@, etc.).
    These are LOW confidence — only use as last resort.
    """
    if not domain:
        return []

    return [
        f"info@{domain}",
        f"contact@{domain}",
        f"office@{domain}",
        f"hello@{domain}",
        f"admin@{domain}",
    ]


if __name__ == "__main__":
    print("Test 1: Standard contractor")
    print(generate_owner_patterns("John", "Smith", "abcplumbing.com"))
    print()
    print("Test 2: Single name only")
    print(generate_owner_patterns("Sam", "", "samtheplumber.com"))
    print()
    print("Test 3: Domain extraction")
    for url in [
        "https://www.abcplumbing.com/",
        "http://abcplumbing.com",
        "abcplumbing.com",
        "https://www.abcplumbing.com/about-us",
    ]:
        print(f"  {url} → {extract_domain(url)}")
    print()
    print("Test 4: Generic fallbacks")
    print(generate_generic_patterns("abcplumbing.com"))
