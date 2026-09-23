#!/usr/bin/env python3
"""
scrape_maps.py - Free Google Maps scraper

Instant Data Scraper only reads the results LIST, where Google often shows a
"Book online" button instead of "Website" - so the real site is missing. This
script opens each business's Google Maps detail page and reads the actual
Website link from there. Completely free, runs locally, no accounts/API keys.

It writes a CSV with friendly headers that the med-spa cleaner (Part A) reads
directly:
    Business Name, Website URL, Rating, Review Count, Address, Google Maps URL

ONE-TIME SETUP (run both, once):
    python3 -m pip install playwright
    python3 -m playwright install chromium

RUN:
    python3 scrape_maps.py

A browser window opens so you can watch it work (and solve a "are you human?"
check by hand if Google ever shows one). Run one city at a time and keep the
volume reasonable to stay polite.
"""

import csv
import os
import re
import sys
import time

# Set to True to run without a visible browser window (faster, but you can't
# solve a CAPTCHA if Google shows one). Keep False for normal use.
HEADLESS = False

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright is not installed yet. Run these two commands once:")
    print("    python3 -m pip install playwright")
    print("    python3 -m playwright install chromium")
    sys.exit(1)


def _reviews(stars_label, review_label, f7_text, card_text):
    """Pull a review COUNT from whichever spot the render exposes it."""
    for src in (stars_label, review_label):       # "4.9 stars 1,234 reviews"
        if src:
            m = re.search(r"([\d,]+)\s*review", src, re.I)
            if m:
                return m.group(1).replace(",", "")
    if f7_text:                                    # detail header "4.9(1,234)"
        m = re.search(r"\(([\d,]+)\)", f7_text)
        if m:
            return m.group(1).replace(",", "")
    if card_text:                                  # feed card "4.9(57)"
        m = (re.search(r"\d[.,]\d\s*\(([\d,]+)\)", card_text)
             or re.search(r"\(([\d,]+)\)", card_text))
        if m:
            return m.group(1).replace(",", "")
    return ""


def scrape_maps(query, max_results, out_path):
    """Search Google Maps, open each result, pull website/rating/reviews."""
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(user_agent=UA, locale="en-US",
                                  viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto("https://www.google.com/maps/search/"
                  + query.replace(" ", "+"), timeout=60000)

        # Cookie / consent screen (shows in some regions) - click through it.
        for label in ("Accept all", "Reject all", "I agree"):
            try:
                page.get_by_role("button", name=re.compile(label, re.I)).click(
                    timeout=3000)
                break
            except Exception:
                pass

        # Wait for the results feed, then scroll it until results stop loading.
        try:
            page.wait_for_selector('div[role="feed"]', timeout=30000)
        except Exception:
            print("Couldn't load the results list. Check the search term and "
                  "try again.")
            browser.close()
            return
        feed = page.locator('div[role="feed"]')
        seen, stale = 0, 0
        while True:
            count = page.locator(
                'div[role="feed"] a[href*="/maps/place/"]').count()
            if count >= max_results:
                break
            stale = stale + 1 if count == seen else 0
            if stale >= 6:        # no new results after several scrolls
                break
            seen = count
            try:
                feed.evaluate("el => el.scrollBy(0, 2500)")
            except Exception:
                page.mouse.wheel(0, 2500)
            time.sleep(1.6)

        # Collect each result's link + name + (rating/reviews from the card).
        links = page.locator('div[role="feed"] a[href*="/maps/place/"]')
        total = min(links.count(), max_results)
        places = []
        for i in range(total):
            a = links.nth(i)
            href = a.get_attribute("href")
            if not href:
                continue
            name = (a.get_attribute("aria-label") or "").strip()
            rating, slab, ctext = "", "", ""
            try:
                card = a.locator(
                    "xpath=ancestor::div[parent::div[@role='feed']][1]")
                ctext = card.inner_text() if card.count() else ""
                st = card.locator('[role="img"][aria-label*="star" i]')
                if st.count():
                    slab = st.first.get_attribute("aria-label") or ""
                m = re.search(r"([\d.]+)\s*star", slab)
                rating = m.group(1) if m else ""
            except Exception:
                pass
            places.append({"name": name, "href": href, "rating": rating,
                           "reviews": _reviews(slab, "", "", ctext),
                           "stars": slab, "card": ctext})
        print("Found {} listings. Opening each for its website...\n".format(
            len(places)))

        # Visit each place page for the website (+ fill any missing fields).
        for i, pl in enumerate(places, 1):
            row = {"Business Name": pl["name"], "Website URL": "",
                   "Rating": pl["rating"], "Review Count": pl["reviews"],
                   "Address": "", "Google Maps URL": pl["href"]}
            try:
                page.goto(pl["href"], timeout=45000)
                page.wait_for_selector("h1", timeout=15000)
                if not row["Business Name"]:
                    row["Business Name"] = page.locator(
                        "h1").first.inner_text().strip()
                # Website = the "authority" action button (stable selector).
                try:
                    row["Website URL"] = page.locator(
                        'a[data-item-id="authority"]').first.get_attribute(
                        "href", timeout=2500) or ""
                except Exception:
                    pass
                # Detail-page rating + reviews (header block) as a backstop.
                f7 = ""
                try:
                    if page.locator("div.F7nice").count():
                        f7 = page.locator("div.F7nice").first.inner_text()
                except Exception:
                    pass
                rlab = ""
                try:
                    rl = page.locator('[aria-label*="review" i]')
                    for k in range(min(rl.count(), 6)):
                        lab = rl.nth(k).get_attribute("aria-label") or ""
                        if re.search(r"\d", lab) and "write" not in lab.lower():
                            rlab = lab
                            break
                except Exception:
                    pass
                if not row["Rating"] and f7:
                    m = re.search(r"([\d.]+)", f7)
                    row["Rating"] = m.group(1) if m else ""
                if not row["Review Count"]:
                    row["Review Count"] = _reviews("", rlab, f7, pl["card"])
                # Address.
                try:
                    ad = page.locator(
                        'button[data-item-id="address"]').first.get_attribute(
                        "aria-label", timeout=2000) or ""
                    row["Address"] = ad.replace("Address: ", "").strip()
                except Exception:
                    pass
            except Exception as e:
                print("  [{}/{}] {} - skipped ({})".format(
                    i, len(places), (pl["name"] or pl["href"])[:30],
                    type(e).__name__))
                results.append(row)
                continue
            results.append(row)
            print("  [{}/{}] {:<30} {:>5}revs -> {}".format(
                i, len(places), (row["Business Name"] or "?")[:30],
                row["Review Count"] or "?",
                row["Website URL"] or "(no website listed)"))
            time.sleep(0.8)        # be polite

        browser.close()

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "Business Name", "Website URL", "Rating", "Review Count",
            "Address", "Google Maps URL"])
        w.writeheader()
        w.writerows(results)

    got = sum(1 for r in results if r["Website URL"])
    revs = sum(1 for r in results if r["Review Count"])
    print("\n" + "=" * 54)
    print("SCRAPE DONE")
    print("  listings:          {}".format(len(results)))
    print("  with a website:    {}".format(got))
    print("  with review count: {}".format(revs))
    print("  output file:       {}".format(out_path))
    print("=" * 54)
    if revs < max(1, len(results) // 2):
        print("NOTE: review counts came back mostly blank. If that happens on")
        print("your Mac too, tell me - Google may be rendering them in a spot")
        print("the script doesn't read yet, and it's a quick selector fix.")
    print("Next: run Part A and give it this file.")


if __name__ == "__main__":
    print("Free Google Maps scraper\n")
    q = input("Search (e.g. 'med spa Dallas'): ").strip()
    if not q:
        print("No search entered. Exiting.")
        sys.exit(1)
    raw = input("Max listings to pull [200]: ").strip()
    try:
        mx = int(raw) if raw else 200
    except ValueError:
        mx = 200
    safe = re.sub(r"[^A-Za-z0-9]+", "_", q).strip("_") or "maps"
    out = os.path.join(os.path.expanduser("~/Downloads"), safe + "_maps.csv")
    try:
        scrape_maps(q, mx, out)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print("\nERROR: {}".format(e))
        sys.exit(1)
