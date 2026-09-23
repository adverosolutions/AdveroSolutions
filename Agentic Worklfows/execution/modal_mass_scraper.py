"""
Modal Cloud Scraper - Runs Google Maps scraping in the cloud
Scales to unlimited parallel workers without using your local machine.
"""

import modal
import os

# Create Modal app
app = modal.App("mass-lead-scraper")

# Create image with dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "playwright==1.41.0",
        "gspread==5.12.3",
        "google-auth==2.27.0",
        "python-dotenv==1.0.0",
    )
    .run_commands("playwright install chromium")
    .run_commands("playwright install-deps chromium")
)

# Secrets needed
secrets = [
    modal.Secret.from_name("google-sheets-credentials"),  # Your Google Sheets credentials
]

# Mount the scraper code
mounts = [
    modal.Mount.from_local_file(
        "google_maps_scraper.py",
        remote_path="/root/google_maps_scraper.py"
    ),
    modal.Mount.from_local_file(
        "us_metros.py",
        remote_path="/root/us_metros.py"
    ),
    modal.Mount.from_local_file(
        "scraper_sheets.py",
        remote_path="/root/scraper_sheets.py"
    ),
]

# Volume for storing progress database
volume = modal.Volume.from_name("scraper-progress", create_if_missing=True)

@app.function(
    image=image,
    secrets=secrets,
    mounts=mounts,
    volumes={"/data": volume},
    timeout=600,
    cpu=2,
)
async def scrape_location(industry: str, location: str):
    """Scrape a single location in the cloud."""
    import sys
    sys.path.insert(0, "/root")

    from google_maps_scraper import GoogleMapsScraper

    scraper = GoogleMapsScraper()
    await scraper.start()

    try:
        results = await scraper.search(industry, location)
        return {
            "location": location,
            "industry": industry,
            "leads": results,
            "count": len(results),
        }
    finally:
        await scraper.stop()


@app.function(
    image=image,
    secrets=secrets,
    mounts=mounts,
    volumes={"/data": volume},
    timeout=36000,  # 10 hours
    cpu=4,
)
def run_mass_scrape(industries: list[str], parallel: int = 10):
    """
    Run mass scraping in the cloud with specified parallelism.
    Much faster than local since Modal can run many containers simultaneously.
    """
    import sys
    import asyncio
    import sqlite3
    from datetime import datetime

    sys.path.insert(0, "/root")

    from us_metros import get_all_search_locations
    from scraper_sheets import ScraperSheets

    # Initialize sheets
    sheets = ScraperSheets()

    # Get all locations
    locations = get_all_search_locations()

    # Initialize database in volume
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

    def mark_completed(industry, location, count):
        conn.execute(
            "INSERT OR REPLACE INTO completed_searches VALUES (?, ?, ?, ?)",
            (industry, location, count, datetime.now().isoformat())
        )
        conn.commit()

    def save_leads(leads):
        data = [
            (l.get("company_name", "").lower().strip(),
             l.get("city", "").lower().strip(),
             l.get("state", "").upper().strip())
            for l in leads if l.get("company_name")
        ]
        conn.executemany("INSERT OR IGNORE INTO scraped_leads VALUES (?, ?, ?)", data)
        conn.commit()

    print(f"Starting cloud scraping with {parallel} parallel workers")
    print(f"Industries: {industries}")
    print(f"Locations per industry: {len(locations)}")

    total_leads = 0

    for industry in industries:
        print(f"\n{'='*60}")
        print(f"SCRAPING INDUSTRY: {industry.upper()}")
        print(f"{'='*60}")

        # Get remaining locations
        remaining = [loc for loc in locations if not is_completed(industry, loc)]
        print(f"Remaining locations: {len(remaining)}")

        if not remaining:
            print(f"Industry already complete!")
            continue

        # Run in batches using Modal's map
        batch_size = parallel
        industry_leads = 0

        for i in range(0, len(remaining), batch_size):
            batch = remaining[i:i+batch_size]
            print(f"\nProcessing batch {i//batch_size + 1}/{(len(remaining) + batch_size - 1)//batch_size}")

            # Map scrape_location across the batch in parallel
            results = list(scrape_location.map(
                [industry] * len(batch),
                batch
            ))

            # Process results
            for result in results:
                if result and result["leads"]:
                    save_leads(result["leads"])

                    # Write to sheets
                    try:
                        sheets.write_leads(result["leads"], industry, f"{industry} near {result['location']}")
                    except Exception as e:
                        print(f"Sheet write error: {e}")

                    mark_completed(industry, result["location"], result["count"])
                    industry_leads += result["count"]
                    total_leads += result["count"]

                    print(f"  ✓ {result['location']}: {result['count']} leads")

            volume.commit()  # Save progress

        print(f"\n{'='*60}")
        print(f"Industry complete: {industry}")
        print(f"Leads scraped: {industry_leads}")
        print(f"{'='*60}")

    conn.close()

    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"Total leads: {total_leads}")
    print(f"{'='*60}")

    return {"total_leads": total_leads}


@app.local_entrypoint()
def main(parallel: int = 10):
    """
    Local entrypoint - run this from your machine.
    It will dispatch work to Modal cloud.
    """
    industries = ["HVAC", "roofing"]

    print("🚀 Starting cloud scraper on Modal...")
    print(f"Parallel workers: {parallel}")

    result = run_mass_scrape.remote(industries, parallel)

    print(f"\n✅ Complete! Total leads: {result['total_leads']}")


if __name__ == "__main__":
    # To run locally and deploy to Modal:
    # modal run modal_mass_scraper.py --parallel 10
    pass
