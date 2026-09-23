"""
Modal Cloud Lead Scraper - Production Version
Runs entirely in the cloud with Google Sheets integration.
Zero load on your computer.
"""

import modal
from pathlib import Path

app = modal.App("lead-scraper-production")

# Build container image with all dependencies
current_dir = Path(__file__).parent
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "playwright==1.41.0",
        "gspread==5.12.3",
        "google-auth==2.27.0",
        "python-dotenv==1.0.0",
        "pytz==2024.1",
    )
    .run_commands(
        "playwright install chromium",
        "playwright install-deps chromium"
    )
    .add_local_file(str(current_dir / "google_maps_scraper.py"), "/root/code/google_maps_scraper.py")
    .add_local_file(str(current_dir / "us_metros.py"), "/root/code/us_metros.py")
    .add_local_file(str(current_dir / "scraper_sheets.py"), "/root/code/scraper_sheets.py")
)

# Volume for persistent storage
volume = modal.Volume.from_name("scraper-production-db", create_if_missing=True)


@app.function(
    image=image,
    volumes={"/data": volume},
    timeout=300,
    cpu=2,
    secrets=[modal.Secret.from_name("google-sheets-scraper")],
)
async def scrape_single_location(industry: str, location: str):
    """
    Scrape a single location in the cloud.
    Each call runs in its own isolated container.
    """
    import sys
    import os
    sys.path.insert(0, "/root/code")

    from google_maps_scraper import GoogleMapsScraper

    # Set environment for scraper_sheets
    if not os.getenv("SCRAPER_SHEET_ID"):
        os.environ["SCRAPER_SHEET_ID"] = "1pqHEYgGOVgf5tcYdcuNQiUArVf3MvavJ9DRlyHsm_2A"

    scraper = GoogleMapsScraper()
    await scraper.start()

    try:
        results = await scraper.search(industry, location, timeout=240)

        return {
            "industry": industry,
            "location": location,
            "leads": results,
            "count": len(results),
            "success": True,
        }
    except Exception as e:
        print(f"[ERROR] {location}: {str(e)[:100]}")
        return {
            "industry": industry,
            "location": location,
            "leads": [],
            "count": 0,
            "success": False,
            "error": str(e),
        }
    finally:
        await scraper.stop()


@app.function(
    image=image,
    volumes={"/data": volume},
    timeout=43200,  # 12 hours max
    cpu=4,
    memory=4096,
    secrets=[modal.Secret.from_name("google-sheets-scraper")],
)
def orchestrate_scraping(industries: list, parallel_workers: int = 20, batch_size: int = 50):
    """
    Orchestrator function that manages the entire scraping operation.
    Runs in the cloud and spawns parallel workers.
    Writes to Google Sheets in batches.
    """
    import sys
    import os
    import sqlite3
    from datetime import datetime

    sys.path.insert(0, "/root/code")

    # Set environment
    if not os.getenv("SCRAPER_SHEET_ID"):
        os.environ["SCRAPER_SHEET_ID"] = "1pqHEYgGOVgf5tcYdcuNQiUArVf3MvavJ9DRlyHsm_2A"

    from us_metros import get_all_search_locations
    from scraper_sheets import ScraperSheets

    print("\n" + "="*60)
    print("🚀 CLOUD SCRAPER STARTING")
    print("="*60)

    # Initialize Google Sheets
    try:
        sheets = ScraperSheets()
        print("✓ Google Sheets connected")
    except Exception as e:
        print(f"✗ Google Sheets connection failed: {e}")
        print("Continuing without sheets integration...")
        sheets = None

    locations = get_all_search_locations()
    print(f"Industries: {industries}")
    print(f"Parallel workers: {parallel_workers}")
    print(f"Total locations per industry: {len(locations)}")
    print(f"Total searches: {len(locations) * len(industries)}")

    # Initialize database
    db_path = "/data/scraper_progress.db"
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS completed_searches (
            industry TEXT,
            location TEXT,
            result_count INTEGER,
            completed_at TEXT,
            PRIMARY KEY (industry, location)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scraped_leads (
            company_name TEXT,
            city TEXT,
            state TEXT,
            industry TEXT,
            phone TEXT,
            website TEXT,
            address TEXT,
            PRIMARY KEY (company_name, city, state)
        )
    """)
    conn.commit()

    def is_completed(industry, location):
        cur = conn.execute(
            "SELECT 1 FROM completed_searches WHERE industry=? AND location=?",
            (industry, location)
        )
        return cur.fetchone() is not None

    def save_and_write_batch(results_batch):
        """Save batch to database AND write to Google Sheets."""
        all_leads = []

        for result in results_batch:
            if not result["success"]:
                continue

            # Mark search complete
            conn.execute(
                "INSERT OR REPLACE INTO completed_searches VALUES (?, ?, ?, ?)",
                (result["industry"], result["location"], result["count"], datetime.now().isoformat())
            )

            # Save leads to database
            for lead in result["leads"]:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO scraped_leads VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            lead.get("company_name", "").lower().strip(),
                            lead.get("city", "").lower().strip(),
                            lead.get("state", "").upper().strip(),
                            result["industry"],
                            lead.get("phone", ""),
                            lead.get("website", ""),
                            lead.get("address", ""),
                        )
                    )
                    all_leads.append(lead)
                except Exception as e:
                    print(f"Error saving lead: {e}")

        conn.commit()
        volume.commit()

        # Write to Google Sheets
        if sheets and all_leads:
            try:
                industry = results_batch[0]["industry"] if results_batch else "unknown"
                sheets.write_leads(all_leads, industry, f"Cloud scraper batch")
                print(f"✓ Wrote {len(all_leads)} leads to Google Sheets")
            except Exception as e:
                print(f"✗ Sheet write error: {e}")

        return len(all_leads)

    # Process each industry
    total_leads = 0
    start_time = datetime.now()

    for industry_idx, industry in enumerate(industries):
        print(f"\n{'='*60}")
        print(f"INDUSTRY {industry_idx + 1}/{len(industries)}: {industry.upper()}")
        print(f"{'='*60}")

        remaining = [loc for loc in locations if not is_completed(industry, loc)]
        print(f"Remaining: {len(remaining)}/{len(locations)}")

        if not remaining:
            print("✓ Already complete!")
            continue

        industry_leads = 0
        industry_start = datetime.now()

        # Process in batches
        for batch_idx in range(0, len(remaining), parallel_workers):
            batch = remaining[batch_idx:batch_idx + parallel_workers]
            batch_num = batch_idx // parallel_workers + 1
            total_batches = (len(remaining) + parallel_workers - 1) // parallel_workers

            print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} locations...")

            # Map across batch in parallel (each in own container!)
            results = list(scrape_single_location.map(
                [industry] * len(batch),
                batch
            ))

            # Save and write to sheets
            batch_leads = save_and_write_batch(results)
            industry_leads += batch_leads
            total_leads += batch_leads

            # Progress
            successes = sum(1 for r in results if r["success"])
            elapsed = (datetime.now() - industry_start).total_seconds() / 3600
            rate = industry_leads / elapsed if elapsed > 0.01 else 0

            print(f"  ✓ Batch complete: {successes}/{len(batch)} succeeded, {batch_leads} leads")
            print(f"  Industry total: {industry_leads} leads | Rate: {rate:.0f} leads/hr")

            # Write to sheets every batch_size leads
            if industry_leads % batch_size == 0 and industry_leads > 0:
                volume.commit()
                print(f"  💾 Progress saved")

        elapsed_min = (datetime.now() - industry_start).total_seconds() / 60
        print(f"\n{'='*60}")
        print(f"✓ INDUSTRY COMPLETE: {industry}")
        print(f"  Leads: {industry_leads}")
        print(f"  Time: {elapsed_min:.1f} minutes")
        print(f"{'='*60}")

    # Final stats
    total_searches = conn.execute("SELECT COUNT(*) FROM completed_searches").fetchone()[0]
    total_unique = conn.execute("SELECT COUNT(*) FROM scraped_leads").fetchone()[0]
    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600

    conn.close()

    print(f"\n{'='*60}")
    print(f"🎉 SCRAPING COMPLETE!")
    print(f"{'='*60}")
    print(f"Total searches: {total_searches}")
    print(f"Total unique leads: {total_unique}")
    print(f"Total time: {elapsed_hours:.1f} hours")
    print(f"Rate: {total_unique / elapsed_hours:.0f} leads/hour")
    print(f"{'='*60}\n")

    return {
        "total_searches": total_searches,
        "total_leads": total_unique,
        "elapsed_hours": round(elapsed_hours, 2),
    }


@app.local_entrypoint()
def main(
    industries: str = "HVAC,roofing",
    parallel: int = 20,
    reset_sheets: bool = False,
):
    """
    Run from your local machine to start cloud scraping.

    Usage:
        modal run modal_scraper_final.py --industries "HVAC,roofing" --parallel 20
        modal run modal_scraper_final.py --reset-sheets  # Clear sheets first
    """
    import os
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    # Reset sheets if requested
    if reset_sheets:
        print("\n🗑️  Resetting Google Sheets...")
        sys.path.insert(0, os.path.dirname(__file__))
        from scraper_sheets import ScraperSheets

        sheets = ScraperSheets()
        # Clear HVAC and roofing tabs
        for industry in ["HVAC", "roofing"]:
            try:
                sheets.clear_tab(industry)
                print(f"  ✓ Cleared {industry} tab")
            except:
                print(f"  ℹ️  {industry} tab doesn't exist (will be created)")

        print("✓ Sheets reset complete\n")

    industry_list = [i.strip() for i in industries.split(",")]

    print("\n" + "="*60)
    print("🚀 DEPLOYING CLOUD SCRAPER TO MODAL")
    print("="*60)
    print(f"Industries: {industry_list}")
    print(f"Parallel workers: {parallel}")
    print("\nYour computer will remain idle!")
    print("All work happens in Modal's cloud.")
    print("="*60 + "\n")

    result = orchestrate_scraping.remote(industry_list, parallel)

    print(f"\n✅ CLOUD SCRAPING COMPLETE!")
    print(f"Total leads: {result['total_leads']:,}")
    print(f"Time: {result['elapsed_hours']} hours")
    print(f"\nCheck your Google Sheet for all results!\n")
