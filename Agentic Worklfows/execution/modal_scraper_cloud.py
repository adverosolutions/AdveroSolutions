"""
Modal Cloud Lead Scraper
Runs scraping entirely in the cloud with unlimited parallelism.
Zero load on your local machine.
"""

import modal
from pathlib import Path

app = modal.App("lead-scraper-cloud")

# Build container image with all dependencies
current_dir = Path(__file__).parent
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "playwright==1.41.0",
        "gspread==5.12.3",
        "google-auth==2.27.0",
        "python-dotenv==1.0.0",
    )
    .run_commands(
        "playwright install chromium",
        "playwright install-deps chromium"
    )
    .add_local_file(str(current_dir / "google_maps_scraper.py"), "/root/code/google_maps_scraper.py")
    .add_local_file(str(current_dir / "us_metros.py"), "/root/code/us_metros.py")
)

# Volume for persistent storage of progress database
volume = modal.Volume.from_name("scraper-db", create_if_missing=True)

# No mounts needed - we'll include files in image


@app.function(
    image=image,
    volumes={"/data": volume},
    timeout=300,
    cpu=2,
)
async def scrape_single_location(industry: str, location: str):
    """
    Scrape a single location in the cloud.
    Each call runs in its own isolated container.
    """
    import sys
    sys.path.insert(0, "/root/code")

    from google_maps_scraper import GoogleMapsScraper

    print(f"[CLOUD] Scraping {industry} near {location}")

    scraper = GoogleMapsScraper()
    await scraper.start()

    try:
        results = await scraper.search(industry, location, timeout=240)
        print(f"[CLOUD] ✓ {location}: Found {len(results)} leads")

        return {
            "industry": industry,
            "location": location,
            "leads": results,
            "count": len(results),
            "success": True,
        }
    except Exception as e:
        print(f"[CLOUD] ✗ {location}: Error - {str(e)}")
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
    memory=2048,
)
def orchestrate_scraping(industries: list, parallel_workers: int = 20):
    """
    Orchestrator function that manages the entire scraping operation.
    Runs in the cloud and spawns parallel workers.
    """
    import sys
    import sqlite3
    from datetime import datetime

    sys.path.insert(0, "/root/code")

    from us_metros import get_all_search_locations

    print(f"\n{'='*60}")
    print(f"🚀 CLOUD SCRAPER STARTING")
    print(f"{'='*60}")
    print(f"Industries: {industries}")
    print(f"Parallel workers: {parallel_workers}")

    # Get all locations to scrape
    locations = get_all_search_locations()
    print(f"Total locations per industry: {len(locations)}")

    # Initialize database in persistent volume
    db_path = "/data/scraper_progress.db"
    conn = sqlite3.connect(db_path)

    # Create tables
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

    def save_batch(results_batch):
        """Save a batch of results to database."""
        for result in results_batch:
            if not result["success"]:
                continue

            # Mark search complete
            conn.execute(
                "INSERT OR REPLACE INTO completed_searches VALUES (?, ?, ?, ?)",
                (result["industry"], result["location"], result["count"], datetime.now().isoformat())
            )

            # Save leads
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
                except Exception as e:
                    print(f"Error saving lead: {e}")

        conn.commit()
        volume.commit()  # Persist to cloud storage

    # Process each industry
    total_scraped = 0

    for industry in industries:
        print(f"\n{'='*60}")
        print(f"INDUSTRY: {industry.upper()}")
        print(f"{'='*60}")

        # Get remaining locations for this industry
        remaining = [loc for loc in locations if not is_completed(industry, loc)]
        print(f"Remaining locations: {len(remaining)}/{len(locations)}")

        if not remaining:
            print("✓ Already complete!")
            continue

        industry_leads = 0

        # Process in batches using Modal's parallel map
        batch_size = parallel_workers

        for batch_idx in range(0, len(remaining), batch_size):
            batch = remaining[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            total_batches = (len(remaining) + batch_size - 1) // batch_size

            print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} locations...")

            # Map scrape_single_location across the batch in parallel
            # Each location runs in its own isolated container!
            results = list(scrape_single_location.map(
                [industry] * len(batch),
                batch
            ))

            # Save results
            save_batch(results)

            # Count leads
            batch_leads = sum(r["count"] for r in results if r["success"])
            industry_leads += batch_leads
            total_scraped += batch_leads

            print(f"[Batch {batch_num}] ✓ Scraped {batch_leads} leads")
            print(f"[Industry total] {industry_leads} leads")

        print(f"\n{'='*60}")
        print(f"✓ INDUSTRY COMPLETE: {industry}")
        print(f"Total leads: {industry_leads}")
        print(f"{'='*60}")

    # Final stats
    total_searches = conn.execute("SELECT COUNT(*) FROM completed_searches").fetchone()[0]
    total_leads = conn.execute("SELECT COUNT(*) FROM scraped_leads").fetchone()[0]
    conn.close()

    print(f"\n{'='*60}")
    print(f"🎉 SCRAPING COMPLETE!")
    print(f"{'='*60}")
    print(f"Total searches: {total_searches}")
    print(f"Total unique leads: {total_leads}")
    print(f"{'='*60}\n")

    return {
        "total_searches": total_searches,
        "total_leads": total_leads,
    }


@app.local_entrypoint()
def main(
    industries: str = "HVAC,roofing",
    parallel: int = 20
):
    """
    Run this from your local machine.
    All work happens in Modal cloud - zero load on your computer!

    Usage:
        modal run modal_scraper_cloud.py --industries "HVAC,roofing" --parallel 20
    """
    industry_list = [i.strip() for i in industries.split(",")]

    print("\n🚀 Deploying scraper to Modal Cloud...")
    print(f"Industries: {industry_list}")
    print(f"Parallel workers: {parallel}")
    print("\nYour computer will be idle while scraping runs in the cloud!\n")

    result = orchestrate_scraping.remote(industry_list, parallel)

    print(f"\n✅ Cloud scraping complete!")
    print(f"Total leads: {result['total_leads']}")
    print(f"\nYou can close this terminal - data is saved in Modal cloud volume.\n")
