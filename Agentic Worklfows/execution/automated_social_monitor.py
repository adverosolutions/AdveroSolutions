"""
Automated Social Media Lead Monitor
Runs 24/7 in background monitoring Facebook Groups and Nextdoor
Sends instant notifications to phone when lawn care posts are detected
"""

import os
import sys
import time
import re
import asyncio
import json
import argparse
from datetime import datetime
from typing import List, Dict, Set
from dotenv import load_dotenv

try:
    from playwright.async_api import async_playwright, Page, Browser
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

import requests

load_dotenv()

# Session storage paths
SESSION_DIR = os.path.join(os.path.dirname(__file__), '.sessions')
FB_SESSION_FILE = os.path.join(SESSION_DIR, 'facebook_session.json')
ND_SESSION_FILE = os.path.join(SESSION_DIR, 'nextdoor_session.json')

# Persistent browser profile — survives restarts, preserves full auth state
# This is a real Chrome profile dir, not just cookies
NEXTDOOR_PROFILE_DIR = os.path.join(SESSION_DIR, 'nextdoor_profile')

# Configuration
NTFY_TOPIC = os.getenv('NTFY_TOPIC', '').strip()

# Latency mode: "home" (fast), "mobile" (slow wifi/hotspot), "auto" (detect)
# Override via env var LATENCY_MODE or --latency CLI flag
LATENCY_MODE = os.getenv('LATENCY_MODE', 'auto')

# Latency profiles — all timeouts scale from these
LATENCY_PROFILES = {
    'home': {
        'check_interval': 300,       # 5 min between cycles
        'scroll_pause': 2,           # seconds after each scroll
        'page_load_wait': 3,         # seconds after navigation
        'nav_timeout': 30000,        # ms for page.goto()
        'selector_timeout': 10000,   # ms for wait_for_selector()
        'sort_settle': 2,            # seconds after sorting
        'between_notifications': 2,  # seconds between ntfy sends
        'ntfy_timeout': 10,          # seconds for ntfy HTTP request
    },
    'mobile': {
        'check_interval': 420,       # 7 min (extra buffer for slow loads)
        'scroll_pause': 4,           # slower scroll = more time to load images/posts
        'page_load_wait': 8,         # pages take longer on slow wifi
        'nav_timeout': 60000,        # 60s for navigation
        'selector_timeout': 25000,   # 25s for selectors to appear
        'sort_settle': 4,            # more settle time after sort
        'between_notifications': 3,  # slightly more between sends
        'ntfy_timeout': 20,          # ntfy can be slow too
    },
}

# Active profile (set during startup)
TIMING = LATENCY_PROFILES['home']  # default, overwritten in main()


async def detect_latency(page: Page) -> str:
    """Ping a lightweight endpoint to measure connection speed"""
    try:
        start = time.time()
        await page.goto('https://www.gstatic.com/generate_204', timeout=15000)
        latency_ms = (time.time() - start) * 1000

        if latency_ms < 800:
            mode = 'home'
            print(f"  ⚡ Connection speed: {latency_ms:.0f}ms → using 'home' profile")
        else:
            mode = 'mobile'
            print(f"  🐢 Connection speed: {latency_ms:.0f}ms → using 'mobile' profile")

        return mode
    except Exception as e:
        print(f"  ⚠ Latency detection failed ({e}) → defaulting to 'mobile' profile")
        return 'mobile'

# Default groups to monitor (edit this list to add/remove groups)
DEFAULT_FACEBOOK_GROUPS = [
    'https://www.facebook.com/groups/hursttxneighborhood',
    'https://www.facebook.com/groups/299101299396300',
    'https://www.facebook.com/groups/citizensofeulesstx',
    'https://www.facebook.com/groups/eulesscitizens',
    'https://www.facebook.com/groups/richlandhillsresidentspage',
    'https://www.facebook.com/groups/442206752846706',
]

DEFAULT_NEXTDOOR_URLS = [
    'https://nextdoor.com/news_feed/',
]

# Lawn care keywords
KEYWORDS = [
    r'\blawn\b', r'\bmowing\b', r'\blandscaping\b', r'\byard work\b',
    r'\bgrass cutting\b', r'\blawn service\b', r'\blawn care\b',
    r'\blandscaping service\b', r'\bneed.*mow\b', r'\blooking for.*landscap\b',
    r'\brecommend.*lawn\b', r'\banyone.*mow\b', r'\bsomeone.*yard\b',
    r'\btrimming\b', r'\bedging\b', r'\bmulch\b', r'\byard cleanup\b'
]

KEYWORD_PATTERN = re.compile('|'.join(KEYWORDS), re.IGNORECASE)

# Track seen posts to avoid duplicates
seen_posts: Set[str] = set()


def contains_keywords(text: str) -> bool:
    """Check if text contains lawn care keywords"""
    if not text:
        return False
    return bool(KEYWORD_PATTERN.search(text))


def send_notification(post_data: Dict) -> bool:
    """Send notification via ntfy.sh"""
    if not NTFY_TOPIC:
        print("⚠ NTFY_TOPIC not set; skipping notification")
        return False
    try:
        platform = post_data.get('platform', 'social media')
        author = post_data.get('author', 'Unknown')
        text = post_data.get('text', '')[:150]
        url = post_data.get('url', '')
        group = post_data.get('group', 'Unknown')

        title = f"🌿 LAWN LEAD: {platform.title()}"
        message = f'"{text}..."\n\n'
        message += f"From: {author}\n"
        message += f"Group: {group}\n"
        message += f"Posted: {datetime.now().strftime('%I:%M %p')}"

        response = requests.post(
            f'https://ntfy.sh/{NTFY_TOPIC}',
            data=message.encode('utf-8'),
            headers={
                'Title': title,
                'Priority': 'high',
                'Tags': 'deciduous_tree,seedling',
                'Click': url
            },
            timeout=TIMING['ntfy_timeout']
        )

        if response.ok:
            print(f"✓ Notification sent: {author} - {text[:50]}...")
            return True
        else:
            print(f"✗ Failed to send notification: {response.status_code}")
            return False

    except Exception as e:
        print(f"✗ Notification error: {e}")
        return False


async def scroll_page(page: Page, scrolls: int = 3):
    """Scroll page to load more content"""
    for i in range(scrolls):
        await page.evaluate('window.scrollBy(0, window.innerHeight)')
        await asyncio.sleep(TIMING['scroll_pause'])

    # Scroll back to top
    await page.evaluate('window.scrollTo(0, 0)')
    await asyncio.sleep(TIMING['scroll_pause'] / 2)


async def extract_facebook_posts(page: Page) -> List[Dict]:
    """Extract posts from Facebook Group page"""
    posts = []

    try:
        # Wait for feed to load
        await page.wait_for_selector('div[role="article"]', timeout=TIMING['selector_timeout'])

        # Get all post elements
        post_elements = await page.query_selector_all('div[role="article"]')

        for element in post_elements:
            try:
                # Extract text content
                text_content = await element.inner_text()

                if not text_content or len(text_content) < 20:
                    continue

                # Check for keywords
                if not contains_keywords(text_content):
                    continue

                # Extract author
                author = "Unknown"
                author_elements = await element.query_selector_all('a[role="link"] strong, h2 a, h3 a, h4 a')
                if author_elements:
                    author = await author_elements[0].inner_text()

                # Extract post URL
                post_url = page.url
                link_elements = await element.query_selector_all('a[href*="/posts/"], a[href*="/permalink/"]')
                if link_elements:
                    href = await link_elements[0].get_attribute('href')
                    if href and '/posts/' in href:
                        post_url = href.split('?')[0]
                        if not post_url.startswith('http'):
                            post_url = 'https://facebook.com' + post_url

                # Create unique ID
                post_id = f"fb_{hash(text_content[:100])}"

                if post_id in seen_posts:
                    continue

                seen_posts.add(post_id)

                # Extract group name from page title
                group_name = await page.title()
                group_name = group_name.split('|')[0].strip()

                posts.append({
                    'platform': 'facebook',
                    'author': author.strip(),
                    'text': text_content[:500],
                    'url': post_url,
                    'group': group_name,
                    'detected_keywords': list(set(KEYWORD_PATTERN.findall(text_content.lower())))
                })

            except Exception as e:
                print(f"  Error extracting Facebook post: {e}")
                continue

    except Exception as e:
        print(f"  Error getting Facebook posts: {e}")

    return posts


async def extract_nextdoor_posts(page: Page) -> List[Dict]:
    """Extract posts from Nextdoor page"""
    posts = []

    try:
        # Wait for posts to load
        await page.wait_for_selector('[data-testid="post"], .post-card, article', timeout=TIMING['selector_timeout'])

        # Get all post elements
        post_elements = await page.query_selector_all('[data-testid="post"], .post-card, article')

        for element in post_elements:
            try:
                # Extract text
                text_content = await element.inner_text()

                if not text_content or len(text_content) < 20:
                    continue

                # Check for keywords
                if not contains_keywords(text_content):
                    continue

                # Extract author
                author = "Unknown"
                author_element = await element.query_selector('[data-testid="post-author"], .author-name, a[href*="/profile/"]')
                if author_element:
                    author = await author_element.inner_text()

                # Extract URL
                post_url = page.url
                link_element = await element.query_selector('a[href*="/p/"]')
                if link_element:
                    href = await link_element.get_attribute('href')
                    if href:
                        post_url = href if href.startswith('http') else 'https://nextdoor.com' + href

                # Create unique ID
                post_id = f"nd_{hash(text_content[:100])}"

                if post_id in seen_posts:
                    continue

                seen_posts.add(post_id)

                posts.append({
                    'platform': 'nextdoor',
                    'author': author.strip(),
                    'text': text_content[:500],
                    'url': post_url,
                    'group': 'Nextdoor',
                    'detected_keywords': list(set(KEYWORD_PATTERN.findall(text_content.lower())))
                })

            except Exception as e:
                print(f"  Error extracting Nextdoor post: {e}")
                continue

    except Exception as e:
        print(f"  Error getting Nextdoor posts: {e}")

    return posts


async def sort_by_recent_facebook(page: Page):
    """Sort Facebook Group feed by Most Recent using URL parameter"""
    try:
        # Best method: Add sorting parameter to URL
        current_url = page.url

        # Remove any existing sorting parameter
        if 'sorting_setting' in current_url:
            # Already has sorting - reload to ensure it's fresh
            print("  ✓ URL already has sorting parameter")
            return True

        # Add chronological sorting to URL
        if '?' in current_url:
            new_url = current_url + '&sorting_setting=CHRONOLOGICAL'
        else:
            new_url = current_url + '?sorting_setting=CHRONOLOGICAL'

        await page.goto(new_url, wait_until='domcontentloaded', timeout=TIMING['nav_timeout'])
        print("  ✓ Sorted by Most Recent (added URL parameter)")
        await asyncio.sleep(TIMING['sort_settle'])
        return True

    except Exception as e:
        print(f"  ⚠ Could not add sorting parameter: {e}")
        print("  ℹ Using default feed sort")
        return False


async def sort_by_recent_nextdoor(page: Page):
    """Click the Recent tab on Nextdoor (2nd tab in filter row)"""
    try:
        # Wait for page to fully load
        await asyncio.sleep(TIMING['page_load_wait'])

        print("  Searching for 'Recent' tab...")

        # Method 1: Find all buttons and click the one that says exactly "Recent"
        try:
            buttons = await page.query_selector_all('button')
            for button in buttons:
                text = await button.inner_text()
                if text and text.strip() == "Recent":
                    await button.click()
                    print("  ✓ Clicked 'Recent' tab on Nextdoor")
                    await asyncio.sleep(TIMING['sort_settle'])
                    return True
        except Exception as e:
            print(f"  Method 1 failed: {e}")

        # Method 2: Use Playwright's get_by_text
        try:
            recent_element = page.get_by_text("Recent", exact=True)
            await recent_element.click()
            print("  ✓ Clicked 'Recent' using get_by_text")
            await asyncio.sleep(TIMING['sort_settle'])
            return True
        except Exception as e:
            print(f"  Method 2 failed: {e}")

        # Method 3: Click using text locator
        try:
            await page.locator('text="Recent"').first.click()
            print("  ✓ Clicked 'Recent' using locator")
            await asyncio.sleep(TIMING['sort_settle'])
            return True
        except Exception as e:
            print(f"  Method 3 failed: {e}")

        # If we get here, couldn't click the button
        print("  ⚠ Could not find 'Recent' button - using default sort")
        print("  ℹ Feed may be showing 'For you' instead of 'Recent'")
        return False

    except Exception as e:
        print(f"  ⚠ Nextdoor sorting error: {e}")
        return False


async def monitor_page(page: Page, url: str, platform: str):
    """Monitor a single page for new posts"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking: {url}")

    try:
        # Navigate to page
        await page.goto(url, wait_until='domcontentloaded', timeout=TIMING['nav_timeout'])
        await asyncio.sleep(TIMING['page_load_wait'])

        # Sort by most recent
        if platform == 'facebook':
            await sort_by_recent_facebook(page)
        elif platform == 'nextdoor':
            await sort_by_recent_nextdoor(page)

        # Scroll to load more posts
        await scroll_page(page, scrolls=3)

        # Extract posts based on platform
        if platform == 'facebook':
            posts = await extract_facebook_posts(page)
        elif platform == 'nextdoor':
            posts = await extract_nextdoor_posts(page)
        else:
            posts = []

        print(f"  Found {len(posts)} new lead(s)")

        # Send notifications
        for post in posts:
            send_notification(post)
            # Small delay between notifications
            await asyncio.sleep(TIMING['between_notifications'])

    except Exception as e:
        print(f"  Error monitoring page: {e}")


async def setup_facebook_auth(browser: Browser) -> Page:
    """Setup Facebook authentication (saves session for reuse)"""
    # Create session directory if it doesn't exist
    os.makedirs(SESSION_DIR, exist_ok=True)

    # Try to load existing session
    if os.path.exists(FB_SESSION_FILE):
        print("\n✓ Found saved Facebook session, loading...")
        try:
            with open(FB_SESSION_FILE, 'r') as f:
                storage_state = json.load(f)

            context = await browser.new_context(storage_state=storage_state)
            page = await context.new_page()
            await page.goto('https://facebook.com', timeout=TIMING['nav_timeout'])
            await asyncio.sleep(TIMING['page_load_wait'])

            # Check if still logged in
            if 'login' not in page.url.lower():
                print("✓ Facebook session restored successfully!")
                return page, context, storage_state
            else:
                print("⚠ Saved session expired, need to log in again")
        except Exception as e:
            print(f"⚠ Could not load saved session: {e}")

    # No saved session or it expired - do fresh login
    print("\n=== Facebook Login Required ===")
    print("Opening browser for you to log in...")
    print("After logging in, the session will be saved for future runs.")

    context = await browser.new_context()
    page = await context.new_page()

    await page.goto('https://facebook.com')

    print("\nPlease log in to Facebook in the browser window.")
    print("Press Enter here when you're logged in and see your feed...")
    input()

    # Save session state (cookies + storage)
    storage_state = await context.storage_state()
    with open(FB_SESSION_FILE, 'w') as f:
        json.dump(storage_state, f)

    print(f"✓ Session saved! You won't need to log in again.")

    return page, context, storage_state


def _is_nextdoor_logged_in(url: str) -> bool:
    """Check if a Nextdoor URL indicates the user is logged in.

    Nextdoor redirects unauthenticated users to various login/signup paths.
    A logged-in user lands on /news_feed/, /neighborhood_feed/, or similar.
    """
    lower = url.lower()
    # All known unauthenticated landing paths
    logout_indicators = [
        '/login', '/sign_in', '/signin', '/signup', '/sign_up',
        '/register', '/join', '/verify',
        '/onboarding',
    ]
    # If URL contains any logout indicator, NOT logged in
    for indicator in logout_indicators:
        if indicator in lower:
            return False
    # Nextdoor's root page (nextdoor.com/) shows a marketing page when logged out,
    # but redirects to /news_feed/ when logged in
    if lower.rstrip('/').endswith('nextdoor.com'):
        return False
    return True


async def setup_nextdoor_auth(playwright_instance) -> Page:
    """Setup Nextdoor authentication using persistent browser profile.

    Nextdoor uses aggressive bot detection — cookies alone aren't enough.
    A persistent Chrome profile preserves cookies, localStorage, IndexedDB,
    and all browser state across restarts, just like a real Chrome profile.
    """
    os.makedirs(NEXTDOOR_PROFILE_DIR, exist_ok=True)

    print("\n--- NEXTDOOR AUTH (persistent profile) ---")

    context = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=NEXTDOOR_PROFILE_DIR,
        headless=False,
        viewport={'width': 1280, 'height': 900},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-first-run',
            '--no-default-browser-check',
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()

    # Hide Playwright's navigator.webdriver flag — Nextdoor checks this
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        // Chrome runtime stub so Nextdoor thinks it's real Chrome
        window.chrome = { runtime: {} };
    """)

    # Go directly to the feed (not the landing page which shows marketing)
    await page.goto('https://nextdoor.com/news_feed/', timeout=TIMING['nav_timeout'])
    await asyncio.sleep(TIMING['page_load_wait'])

    # Check if already logged in
    if _is_nextdoor_logged_in(page.url):
        print("✓ Nextdoor session restored from profile — already logged in!")
        return page, context, None

    # Need to log in
    print("\n=== Nextdoor Login Required ===")
    print("Log in to Nextdoor in the browser window.")
    print("If it asks you to confirm your address or neighborhood, complete that too.")
    print("")
    print("IMPORTANT: Wait until you can see your neighborhood feed,")
    print("then press Enter here.")
    input()

    # Give the page time to settle after login
    await asyncio.sleep(TIMING['page_load_wait'] + 2)

    # After login, Nextdoor may land on /choose_address/ or /choose_neighborhood/
    # These are post-login setup pages — user needs to complete them
    current = page.url.lower()
    if '/choose_address' in current or '/choose_neighborhood' in current:
        print("  Nextdoor is asking you to confirm your address/neighborhood.")
        print("  Complete that step in the browser, then press Enter here...")
        input()
        await asyncio.sleep(TIMING['page_load_wait'] + 2)

    # Try navigating to the feed explicitly after login
    if not _is_nextdoor_logged_in(page.url):
        print("  Navigating to feed after login...")
        await page.goto('https://nextdoor.com/news_feed/', timeout=TIMING['nav_timeout'])
        await asyncio.sleep(TIMING['page_load_wait'])

    if _is_nextdoor_logged_in(page.url):
        print("✓ Nextdoor login successful — saved to persistent profile.")
    else:
        print(f"⚠ Nextdoor may not be fully logged in (URL: {page.url})")
        print("  The monitor will try anyway. If it fails, delete the profile and retry:")
        print(f"  rm -rf \"{NEXTDOOR_PROFILE_DIR}\"")

    return page, context, None


async def main():
    """Main monitoring loop"""
    global TIMING

    # Parse CLI args
    parser = argparse.ArgumentParser(description='Automated Social Media Lead Monitor')
    parser.add_argument('--latency', choices=['home', 'mobile', 'auto'],
                        default=LATENCY_MODE,
                        help='Latency profile: home (fast wifi), mobile (slow/hotspot), auto (detect)')
    args = parser.parse_args()

    print("=" * 60)
    print("AUTOMATED SOCIAL MEDIA LEAD MONITOR")
    print("=" * 60)
    print(f"Notification topic: {'set' if NTFY_TOPIC else 'NOT SET (notifications disabled; set NTFY_TOPIC in .env)'}")
    print(f"Latency mode: {args.latency}")
    print("=" * 60)

    # Use default groups (configured at top of file)
    facebook_groups = DEFAULT_FACEBOOK_GROUPS.copy()
    nextdoor_urls = DEFAULT_NEXTDOOR_URLS.copy()

    print("\n--- CONFIGURED GROUPS ---")
    print(f"\nFacebook Groups ({len(facebook_groups)}):")
    for url in facebook_groups:
        print(f"  ✓ {url}")

    print(f"\nNextdoor Pages ({len(nextdoor_urls)}):")
    for url in nextdoor_urls:
        print(f"  ✓ {url}")

    print("\nℹ To add/remove groups, edit the DEFAULT_FACEBOOK_GROUPS list in this script.")
    print("=" * 60)

    # Start Playwright
    async with async_playwright() as p:
        print("\nLaunching browser...")
        browser = await p.chromium.launch(headless=False)  # Set to True for background

        # Detect or set latency profile
        if args.latency == 'auto':
            print("\n--- DETECTING CONNECTION SPEED ---")
            temp_context = await browser.new_context()
            temp_page = await temp_context.new_page()
            detected_mode = await detect_latency(temp_page)
            await temp_context.close()
            TIMING = LATENCY_PROFILES[detected_mode]
        else:
            TIMING = LATENCY_PROFILES[args.latency]
            print(f"\n  Using '{args.latency}' latency profile")

        print(f"  Check interval: {TIMING['check_interval'] // 60} min")
        print(f"  Page load wait: {TIMING['page_load_wait']}s")
        print(f"  Navigation timeout: {TIMING['nav_timeout'] // 1000}s")
        print(f"  Selector timeout: {TIMING['selector_timeout'] // 1000}s")

        # Setup authentication
        fb_page = None
        fb_context = None

        nd_page = None
        nd_context = None

        if facebook_groups:
            fb_page, fb_context, _ = await setup_facebook_auth(browser)

        if nextdoor_urls:
            # Nextdoor uses its own persistent browser profile (separate from FB)
            # because it needs full browser state to stay logged in
            nd_page, nd_context, _ = await setup_nextdoor_auth(p)

        print("\n" + "=" * 60)
        print("MONITORING STARTED - Running 24/7")
        print("Press Ctrl+C to stop")
        print("=" * 60)

        # Main monitoring loop
        cycle = 0
        try:
            while True:
                cycle += 1

                # Re-detect latency every 10 cycles in auto mode
                if args.latency == 'auto' and cycle % 10 == 0:
                    print("\n--- RE-CHECKING CONNECTION SPEED ---")
                    test_ctx = await browser.new_context()
                    test_page = await test_ctx.new_page()
                    new_mode = await detect_latency(test_page)
                    await test_ctx.close()
                    TIMING = LATENCY_PROFILES[new_mode]

                # Monitor Facebook Groups
                if facebook_groups and fb_page:
                    for url in facebook_groups:
                        await monitor_page(fb_page, url, 'facebook')

                # Monitor Nextdoor
                if nextdoor_urls and nd_page:
                    for url in nextdoor_urls:
                        await monitor_page(nd_page, url, 'nextdoor')

                # Wait before next check
                interval = TIMING['check_interval']
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sleeping for {interval // 60} minutes...")
                print(f"Next check at: {datetime.fromtimestamp(time.time() + interval).strftime('%I:%M %p')}")
                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
        finally:
            if fb_context:
                await fb_context.close()
            if nd_context:
                await nd_context.close()
            await browser.close()
            print("✓ Browser closed. Monitor stopped.")


if __name__ == "__main__":
    asyncio.run(main())
