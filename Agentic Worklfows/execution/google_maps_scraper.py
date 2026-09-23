"""
Google Maps Scraper - Core Playwright Engine
Searches Google Maps for businesses by industry + location.
Extracts: name, phone, address, website by clicking each listing.
Scrolls to load up to 100 results per search (Google's max).

Note: an unauthenticated/automated Playwright session gets served a stripped
"limited view" of a place page (no reviews UI rendered at all, confirmed by
live testing 2026-07-01) -- review TEXT extraction is not viable through this
scraper. Review count/rating (already extracted) are unaffected.
"""

import asyncio
import logging
import random
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class GoogleMapsScraper:
    """
    Playwright-based Google Maps scraper.
    Clicks into each listing to extract website, phone, and address.
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None

    async def start(self):
        """Launch the browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )
        logger.info("Browser launched")

    async def stop(self):
        """Close browser and playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")

    async def _create_context(self) -> BrowserContext:
        """Create a new browser context with anti-detection settings."""
        ua = random.choice(USER_AGENTS)
        context = await self.browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        return context

    async def search(self, industry: str, location: str, timeout: int = 240) -> List[Dict]:
        """
        Search Google Maps and extract full details (including website) for each listing.
        Scrolls the results feed, then clicks each listing to get website/phone/address.

        Returns up to 100 results. Keeps partial results on timeout.
        """
        # Use shared list so partial results survive timeout
        businesses = []
        context = None
        try:
            context = await self._create_context()
            page = await context.new_page()
            await asyncio.wait_for(
                self._do_search(page, industry, location, businesses), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Search timed out after {timeout}s: {industry} near {location} "
                f"(keeping {len(businesses)} partial results)"
            )
        except Exception as e:
            logger.error(f"Error scraping {industry} near {location}: {e}")
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
        return businesses

    async def _do_search(self, page: Page, industry: str, location: str, businesses: List[Dict]):
        """Inner search implementation. Appends results to businesses list."""
        query = f"{industry} near {location}"
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

        logger.info(f"Searching: {query}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            await asyncio.sleep(5)

        await asyncio.sleep(random.uniform(1.5, 2.5))
        await self._dismiss_dialogs(page)

        results_panel = await page.query_selector('div[role="feed"]')
        if not results_panel:
            logger.warning(f"No results panel found for: {query}")
            return

        # Phase 1: Scroll through the feed and collect all listing elements
        listing_data = await self._scroll_and_collect(page)
        logger.info(f"Collected {len(listing_data)} listings for: {query}")

        # Phase 2: Click each listing to extract full details
        consecutive_errors = 0
        for i, data in enumerate(listing_data):
            try:
                biz = await asyncio.wait_for(
                    self._click_and_extract(page, data, location), timeout=8
                )
                if biz:
                    businesses.append(biz)
                consecutive_errors = 0
            except asyncio.TimeoutError:
                logger.debug(f"Listing {i} click timed out, skipping")
                consecutive_errors += 1
            except Exception as e:
                logger.debug(f"Error on listing {i}: {e}")
                consecutive_errors += 1

            # If 5 in a row fail, the page is likely broken - bail
            if consecutive_errors >= 5:
                logger.warning(f"5 consecutive extraction failures, stopping early at {i}/{len(listing_data)}")
                break

        logger.info(
            f"Extracted {len(businesses)} businesses for: {query} "
            f"({sum(1 for b in businesses if b.get('website'))} with websites)"
        )

    async def _dismiss_dialogs(self, page: Page):
        """Dismiss any consent/cookie popups."""
        try:
            consent_btn = await page.query_selector('button[aria-label="Accept all"]')
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _scroll_and_collect(self, page: Page) -> List[Dict]:
        """
        Scroll through the results feed and collect listing names + href.
        Returns list of {name, href, index} for each listing.
        """
        collected = []
        seen_names = set()
        max_results = 100
        no_new_count = 0
        max_no_new = 5

        while len(collected) < max_results and no_new_count < max_no_new:
            listings = await page.query_selector_all(
                'div[role="feed"] > div > div > a[href*="/maps/place/"]'
            )

            new_count = 0
            for listing in listings:
                if len(collected) >= max_results:
                    break
                try:
                    name = await listing.get_attribute("aria-label")
                    href = await listing.get_attribute("href")
                    if name and name not in seen_names and href:
                        seen_names.add(name)
                        collected.append({"name": name.strip(), "href": href})
                        new_count += 1
                except Exception:
                    continue

            if new_count == 0:
                no_new_count += 1
            else:
                no_new_count = 0

            # Check for end of list
            end_marker = await page.query_selector('span.HlvSq')
            if end_marker:
                break

            # Scroll
            await page.evaluate('''
                const feed = document.querySelector('div[role="feed"]');
                if (feed) feed.scrollTop = feed.scrollHeight;
            ''')
            await asyncio.sleep(random.uniform(1.5, 2.5))

        return collected

    async def _click_and_extract(self, page: Page, listing_data: Dict, location: str) -> Optional[Dict]:
        """
        Click a listing in the results feed to open its detail side panel,
        then extract website, phone, and address.
        The detail panel opens as an overlay - no page navigation happens.
        """
        name = listing_data["name"]

        biz = {
            "company_name": name,
            "phone": "",
            "address": "",
            "city": "",
            "state": "",
            "website": "",
        }

        # Parse city/state from location
        if ", " in location:
            parts = location.split(", ")
            biz["city"] = parts[0]
            biz["state"] = parts[1] if len(parts) > 1 else ""

        try:
            # Find and click the listing link - use href which is more reliable
            href = listing_data.get("href", "")
            link = None
            if href:
                link = await page.query_selector(f'a[href="{href}"]')

            if not link:
                # Fallback: search by aria-label
                links = await page.query_selector_all('a[href*="/maps/place/"]')
                for l in links:
                    label = await l.get_attribute("aria-label")
                    if label and label.strip() == name:
                        link = l
                        break

            if not link:
                return biz

            # Capture current URL before clicking
            old_url = page.url

            await link.click()

            # Wait for URL to change (Google Maps updates URL per listing)
            for _ in range(10):
                await asyncio.sleep(0.1)
                if page.url != old_url:
                    break

            # Wait for the DOM to fully update after URL change.
            await asyncio.sleep(0.6)

            # Extract all details from the side panel
            biz["website"] = await self._extract_website(page)
            biz["phone"] = await self._extract_phone(page)
            biz["address"] = await self._extract_address(page)

        except Exception as e:
            logger.debug(f"Click/extract error for {name}: {e}")

        return biz

    async def _extract_website(self, page: Page) -> str:
        """Extract website URL from the listing detail panel."""
        # Method 1: data-item-id="authority" (most reliable)
        try:
            el = await page.query_selector('a[data-item-id="authority"]')
            if el:
                href = await el.get_attribute("href")
                if href and "google.com" not in href:
                    return href
        except Exception:
            pass

        # Method 2: "Open website" tooltip
        try:
            el = await page.query_selector('a[data-tooltip="Open website"]')
            if el:
                href = await el.get_attribute("href")
                if href:
                    return href
        except Exception:
            pass

        # Method 3: aria-label containing "Website"
        try:
            els = await page.query_selector_all('a[aria-label]')
            for el in els:
                label = await el.get_attribute("aria-label")
                if label and "website" in label.lower():
                    href = await el.get_attribute("href")
                    if href and "google.com" not in href:
                        return href
        except Exception:
            pass

        # Method 4: Look for the website icon button (globe icon row)
        try:
            website_text = await page.evaluate('''() => {
                // Find all action buttons in the info section
                const buttons = document.querySelectorAll('button[data-item-id]');
                for (const btn of buttons) {
                    const itemId = btn.getAttribute('data-item-id');
                    if (itemId && itemId.startsWith('authority')) {
                        const textEl = btn.querySelector('.Io6YTe, .rogA2c');
                        return textEl ? textEl.textContent.trim() : '';
                    }
                }
                // Also check for links in the info panel
                const links = document.querySelectorAll('a[data-item-id="authority"]');
                for (const link of links) {
                    return link.href || '';
                }
                return '';
            }''')
            if website_text and "google.com" not in website_text:
                if not website_text.startswith("http"):
                    website_text = "https://" + website_text
                return website_text
        except Exception:
            pass

        return ""

    async def _extract_phone(self, page: Page) -> str:
        """Extract phone number from the listing detail panel."""
        # Method 1: button with data-item-id starting with "phone:"
        try:
            el = await page.query_selector('button[data-item-id^="phone:"]')
            if el:
                text = await el.inner_text()
                phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', text)
                if phone_match:
                    return phone_match.group(0)
        except Exception:
            pass

        # Method 2: tel: link
        try:
            el = await page.query_selector('a[href^="tel:"]')
            if el:
                href = await el.get_attribute("href")
                if href:
                    return href.replace("tel:", "").strip()
        except Exception:
            pass

        # Method 3: Copy phone number tooltip
        try:
            el = await page.query_selector('button[data-tooltip="Copy phone number"]')
            if el:
                text = await el.inner_text()
                phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', text)
                if phone_match:
                    return phone_match.group(0)
        except Exception:
            pass

        return ""

    async def _extract_address(self, page: Page) -> str:
        """Extract address from the listing detail panel."""
        # Method 1: Copy address button
        try:
            el = await page.query_selector('button[data-item-id="address"]')
            if el:
                text = await el.inner_text()
                if text:
                    return text.strip()
        except Exception:
            pass

        # Method 2: data-tooltip="Copy address"
        try:
            el = await page.query_selector('button[data-tooltip="Copy address"]')
            if el:
                text = await el.inner_text()
                if text:
                    return text.strip()
        except Exception:
            pass

        return ""


async def test_scraper():
    """Test: search for pest control in Houston, show websites."""
    logging.basicConfig(level=logging.INFO)

    scraper = GoogleMapsScraper()
    await scraper.start()

    try:
        results = await scraper.search("pest control", "Houston, TX")

        with_website = sum(1 for b in results if b.get("website"))
        with_phone = sum(1 for b in results if b.get("phone"))
        with_address = sum(1 for b in results if b.get("address"))

        print(f"\nFound {len(results)} businesses")
        print(f"  With website: {with_website} ({100*with_website//max(len(results),1)}%)")
        print(f"  With phone:   {with_phone} ({100*with_phone//max(len(results),1)}%)")
        print(f"  With address: {with_address} ({100*with_address//max(len(results),1)}%)")

        print(f"\n{'Name':<35} {'Phone':<16} {'Website':<40} {'Address'}")
        print("-" * 130)
        for biz in results[:15]:
            print(
                f"{biz['company_name'][:34]:<35} "
                f"{biz['phone'][:15]:<16} "
                f"{biz['website'][:39]:<40} "
                f"{biz['address'][:35]}"
            )

    finally:
        await scraper.stop()


if __name__ == "__main__":
    asyncio.run(test_scraper())
