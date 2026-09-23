"""
Mass Lead Scraper - Main Orchestrator
Runs one industry at a time with parallel Playwright browsers.
Self-annealing: auto-retries failed searches, restarts crashed browsers,
handles rate limits, and resumes from SQLite on crash.

Usage:
    python mass_scraper.py --test                   # Test: 1 industry, 1 city, no sheet
    python mass_scraper.py --test --save            # Test: 1 industry, 1 city, writes to sheet
    python mass_scraper.py                          # Full run (one industry at a time)
    python mass_scraper.py --resume                 # Resume from where we left off
    python mass_scraper.py --parallel 6             # Run with 6 parallel browsers
    python mass_scraper.py --industries "pest control"  # Single industry
    python mass_scraper.py --stats                  # Show progress
"""

import asyncio
import argparse
import logging
import os
import signal
import sqlite3
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# Load .env from project root (two levels up from execution/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_env_path = os.path.join(_project_root, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

from google_maps_scraper import GoogleMapsScraper
from us_metros import get_all_search_locations, get_base_locations

# Configure logging
LOG_FILE = os.path.join(os.path.dirname(__file__), "scraper.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Default industries - run ONE AT A TIME in this order
DEFAULT_INDUSTRIES = [
    "roofing",
]

DB_PATH = os.path.join(os.path.dirname(__file__), "scraper_progress.db")
BATCH_SIZE = 100  # Write to sheets every N leads
MAX_RETRIES = 3   # Retry failed searches up to 3 times
BROWSER_RESTART_THRESHOLD = 50  # Restart browser every N searches to prevent memory leaks


class ProgressTracker:
    """SQLite-based progress tracking for crash recovery."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS completed_searches (
                industry TEXT,
                location TEXT,
                result_count INTEGER,
                completed_at TEXT,
                PRIMARY KEY (industry, location)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS scraped_leads (
                company_name TEXT,
                city TEXT,
                state TEXT,
                PRIMARY KEY (company_name, city, state)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS failed_searches (
                industry TEXT,
                location TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                last_attempt TEXT,
                PRIMARY KEY (industry, location)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS run_stats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.conn.commit()

    def is_completed(self, industry: str, location: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM completed_searches WHERE industry=? AND location=?",
            (industry, location),
        )
        return cur.fetchone() is not None

    def mark_completed(self, industry: str, location: str, result_count: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO completed_searches VALUES (?, ?, ?, ?)",
            (industry, location, result_count, datetime.now().isoformat()),
        )
        # Clear from failed if it was there
        self.conn.execute(
            "DELETE FROM failed_searches WHERE industry=? AND location=?",
            (industry, location),
        )
        self.conn.commit()

    def mark_failed(self, industry: str, location: str, error: str):
        """Track failed searches for retry."""
        self.conn.execute("""
            INSERT INTO failed_searches (industry, location, error, retry_count, last_attempt)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(industry, location) DO UPDATE SET
                error = excluded.error,
                retry_count = retry_count + 1,
                last_attempt = excluded.last_attempt
        """, (industry, location, str(error)[:500], datetime.now().isoformat()))
        self.conn.commit()

    def get_retry_count(self, industry: str, location: str) -> int:
        cur = self.conn.execute(
            "SELECT retry_count FROM failed_searches WHERE industry=? AND location=?",
            (industry, location),
        )
        row = cur.fetchone()
        return row[0] if row else 0

    def get_failed_searches(self, industry: str) -> List[Tuple[str, str, int]]:
        """Get all failed searches for an industry that haven't exceeded max retries."""
        cur = self.conn.execute(
            "SELECT industry, location, retry_count FROM failed_searches WHERE industry=? AND retry_count < ?",
            (industry, MAX_RETRIES),
        )
        return cur.fetchall()

    def is_duplicate(self, name: str, city: str, state: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM scraped_leads WHERE company_name=? AND city=? AND state=?",
            (name.lower().strip(), city.lower().strip(), state.upper().strip()),
        )
        return cur.fetchone() is not None

    def bulk_add_leads(self, leads: List[Dict]):
        data = [
            (l.get("company_name", "").lower().strip(),
             l.get("city", "").lower().strip(),
             l.get("state", "").upper().strip())
            for l in leads if l.get("company_name")
        ]
        self.conn.executemany("INSERT OR IGNORE INTO scraped_leads VALUES (?, ?, ?)", data)
        self.conn.commit()

    def get_completed_count(self, industry: str = None) -> int:
        if industry:
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM completed_searches WHERE industry=?", (industry,)
            )
        else:
            cur = self.conn.execute("SELECT COUNT(*) FROM completed_searches")
        return cur.fetchone()[0]

    def get_total_leads(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM scraped_leads")
        return cur.fetchone()[0]

    def get_total_scraped_from_searches(self) -> int:
        cur = self.conn.execute("SELECT COALESCE(SUM(result_count), 0) FROM completed_searches")
        return cur.fetchone()[0]

    def get_industry_stats(self) -> Dict:
        """Get per-industry completion stats."""
        cur = self.conn.execute("""
            SELECT industry, COUNT(*), COALESCE(SUM(result_count), 0)
            FROM completed_searches GROUP BY industry
        """)
        stats = {}
        for row in cur.fetchall():
            stats[row[0]] = {"searches": row[1], "leads": row[2]}
        return stats

    def reset(self):
        self.conn.execute("DELETE FROM completed_searches")
        self.conn.execute("DELETE FROM scraped_leads")
        self.conn.execute("DELETE FROM failed_searches")
        self.conn.execute("DELETE FROM run_stats")
        self.conn.commit()

    def close(self):
        self.conn.close()


class MassScraper:
    """
    Orchestrates parallel Google Maps scraping.
    Runs ONE INDUSTRY AT A TIME for clean review.
    Self-annealing: retries failures, restarts browsers, handles errors.
    """

    def __init__(
        self,
        industries: List[str] = None,
        parallel: int = 4,
        use_sheets: bool = True,
        use_subdivisions: bool = True,
    ):
        self.industries = industries or DEFAULT_INDUSTRIES
        self.parallel = parallel
        self.use_sheets = use_sheets
        self.use_subdivisions = use_subdivisions
        self.tracker = ProgressTracker()
        self.sheets = None
        self.shutdown_requested = False
        self.lead_buffer: Dict[str, List[Dict]] = {}
        self.start_time = None
        self.session_leads = 0
        self._worker_search_counts: Dict[int, int] = {}

        if use_sheets:
            self._init_sheets()

    def _init_sheets(self):
        """Initialize Google Sheets with retry."""
        for attempt in range(3):
            try:
                from scraper_sheets import ScraperSheets
                self.sheets = ScraperSheets()
                return
            except Exception as e:
                logger.error(f"Google Sheets init attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(5)
        logger.warning("Google Sheets unavailable - continuing without sheet output")

    def _setup_signals(self):
        def handler(signum, frame):
            if self.shutdown_requested:
                logger.warning("Force shutdown - flushing buffers...")
                self._flush_all_buffers()
                sys.exit(1)
            logger.info("Shutdown requested - finishing current searches then flushing to sheets...")
            self.shutdown_requested = True

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def _get_locations(self) -> List[str]:
        if self.use_subdivisions:
            return get_all_search_locations()
        return get_base_locations()

    def _get_industry_queue(self, industry: str) -> List[str]:
        """Get remaining locations for a single industry."""
        locations = self._get_locations()
        remaining = [
            loc for loc in locations
            if not self.tracker.is_completed(industry, loc)
        ]
        return remaining

    async def _worker(self, worker_id: int, queue: asyncio.Queue, industry: str):
        """
        Worker with self-annealing: auto-restarts browser on crash,
        retries failed searches, and handles rate limiting.
        """
        scraper = None
        searches_since_restart = 0

        try:
            scraper = GoogleMapsScraper()
            await scraper.start()

            while not self.shutdown_requested:
                try:
                    location = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                # Self-anneal: restart browser periodically to prevent memory leaks
                if searches_since_restart >= BROWSER_RESTART_THRESHOLD:
                    logger.info(f"[Worker {worker_id}] Restarting browser (memory hygiene)")
                    await scraper.stop()
                    scraper = GoogleMapsScraper()
                    await scraper.start()
                    searches_since_restart = 0

                try:
                    results = await scraper.search(industry, location)
                    searches_since_restart += 1

                    # Deduplicate
                    unique_results = [
                        biz for biz in results
                        if biz.get("company_name") and
                        not self.tracker.is_duplicate(
                            biz["company_name"], biz.get("city", ""), biz.get("state", "")
                        )
                    ]

                    # Track
                    if unique_results:
                        self.tracker.bulk_add_leads(unique_results)
                        self.session_leads += len(unique_results)

                        if industry not in self.lead_buffer:
                            self.lead_buffer[industry] = []
                        self.lead_buffer[industry].extend(unique_results)

                        if len(self.lead_buffer[industry]) >= BATCH_SIZE:
                            self._flush_buffer(industry, f"{industry} near {location}")

                    self.tracker.mark_completed(industry, location, len(unique_results))

                    # Progress
                    total_done = self.tracker.get_completed_count(industry)
                    total_leads = self.tracker.get_total_leads()
                    elapsed = time.time() - self.start_time
                    rate = self.session_leads / (elapsed / 3600) if elapsed > 60 else 0
                    with_website = sum(1 for b in unique_results if b.get("website"))

                    logger.info(
                        f"[W{worker_id}] {location} | "
                        f"{len(unique_results)} new ({with_website} w/website) | "
                        f"Industry total: {total_done} searches | "
                        f"All leads: {total_leads:,} | "
                        f"{rate:.0f}/hr"
                    )

                except Exception as e:
                    error_msg = str(e)
                    retry_count = self.tracker.get_retry_count(industry, location)
                    self.tracker.mark_failed(industry, location, error_msg)

                    if "Timeout" in error_msg or "net::" in error_msg:
                        # Network issue - restart browser (self-anneal)
                        logger.warning(
                            f"[W{worker_id}] Network error on {location} "
                            f"(retry {retry_count + 1}/{MAX_RETRIES}): {error_msg[:100]}"
                        )
                        try:
                            await scraper.stop()
                        except Exception:
                            pass
                        scraper = GoogleMapsScraper()
                        await scraper.start()
                        searches_since_restart = 0
                        await asyncio.sleep(10)
                    elif "Target closed" in error_msg or "Browser" in error_msg:
                        # Browser crashed - restart (self-anneal)
                        logger.warning(f"[W{worker_id}] Browser crashed, restarting...")
                        try:
                            await scraper.stop()
                        except Exception:
                            pass
                        scraper = GoogleMapsScraper()
                        await scraper.start()
                        searches_since_restart = 0
                        await asyncio.sleep(5)
                    else:
                        logger.error(
                            f"[W{worker_id}] Error on {location} "
                            f"(retry {retry_count + 1}/{MAX_RETRIES}): {error_msg[:200]}"
                        )
                        await asyncio.sleep(5)

                queue.task_done()

        except Exception as e:
            logger.error(f"[W{worker_id}] Fatal worker error: {e}\n{traceback.format_exc()}")
        finally:
            if scraper:
                try:
                    await scraper.stop()
                except Exception:
                    pass

    def _flush_buffer(self, industry: str, source_query: str = ""):
        """Write buffered leads to Google Sheets with retry."""
        if not self.sheets or industry not in self.lead_buffer:
            return

        leads = self.lead_buffer[industry]
        if not leads:
            return

        for attempt in range(3):
            try:
                written = self.sheets.write_leads(leads, industry, source_query)
                logger.info(f"Flushed {written} {industry} leads to Google Sheets")
                self.lead_buffer[industry] = []
                return
            except Exception as e:
                logger.error(f"Sheet write attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(5)
                    # Re-init sheets connection (self-anneal)
                    try:
                        self._init_sheets()
                    except Exception:
                        pass

        # If all retries failed, keep leads in buffer for next flush
        logger.error(f"Failed to write {len(leads)} leads to sheets after 3 attempts")

    def _flush_all_buffers(self):
        for industry in list(self.lead_buffer.keys()):
            self._flush_buffer(industry)

    async def run(self):
        """
        Main run loop. Processes ONE INDUSTRY AT A TIME.
        After finishing each industry, prints a summary before moving to the next.
        """
        self._setup_signals()
        self.start_time = time.time()

        locations = self._get_locations()
        total_locations = len(locations)

        logger.info(f"\n{'='*60}")
        logger.info(f"MASS LEAD SCRAPER - SEQUENTIAL INDUSTRY MODE")
        logger.info(f"{'='*60}")
        logger.info(f"Industries (in order): {self.industries}")
        logger.info(f"Locations per industry: {total_locations}")
        logger.info(f"Total searches: {total_locations * len(self.industries)}")
        logger.info(f"Parallel browsers: {self.parallel}")
        logger.info(f"Sheets output: {'enabled' if self.sheets else 'disabled'}")
        logger.info(f"Already completed: {self.tracker.get_completed_count()} searches")
        logger.info(f"Already scraped: {self.tracker.get_total_leads():,} leads")
        logger.info(f"{'='*60}\n")

        for i, industry in enumerate(self.industries):
            if self.shutdown_requested:
                break

            remaining = self._get_industry_queue(industry)

            if not remaining:
                logger.info(f"\n[{industry.upper()}] Already complete - skipping")
                continue

            completed_for_industry = self.tracker.get_completed_count(industry)

            logger.info(f"\n{'='*60}")
            logger.info(f"STARTING INDUSTRY {i+1}/{len(self.industries)}: {industry.upper()}")
            logger.info(f"{'='*60}")
            logger.info(f"Remaining: {len(remaining)} / {total_locations} locations")
            logger.info(f"Already done: {completed_for_industry} locations")
            logger.info(f"{'='*60}\n")

            industry_start = time.time()
            industry_leads_start = self.session_leads

            # Build queue for this industry
            queue = asyncio.Queue()
            for loc in remaining:
                queue.put_nowait(loc)

            # Launch workers
            num_workers = min(self.parallel, len(remaining))
            workers = [
                asyncio.create_task(self._worker(w, queue, industry))
                for w in range(num_workers)
            ]
            await asyncio.gather(*workers)

            # Flush remaining buffer for this industry
            self._flush_buffer(industry)

            # Retry failed searches for this industry
            failed = self.tracker.get_failed_searches(industry)
            if failed and not self.shutdown_requested:
                logger.info(f"\nRetrying {len(failed)} failed searches for {industry}...")
                retry_queue = asyncio.Queue()
                for _, loc, _ in failed:
                    if not self.tracker.is_completed(industry, loc):
                        retry_queue.put_nowait(loc)

                if not retry_queue.empty():
                    retry_workers = [
                        asyncio.create_task(self._worker(w, retry_queue, industry))
                        for w in range(min(2, retry_queue.qsize()))
                    ]
                    await asyncio.gather(*retry_workers)
                    self._flush_buffer(industry)

            # Industry summary
            industry_elapsed = time.time() - industry_start
            industry_leads = self.session_leads - industry_leads_start
            industry_done = self.tracker.get_completed_count(industry)

            print(f"\n{'='*60}")
            print(f"INDUSTRY COMPLETE: {industry.upper()}")
            print(f"{'='*60}")
            print(f"Searches completed: {industry_done} / {total_locations}")
            print(f"Leads scraped: {industry_leads:,}")
            print(f"Duration: {industry_elapsed / 3600:.1f} hours")
            if industry_elapsed > 60:
                print(f"Rate: {industry_leads / (industry_elapsed / 3600):.0f} leads/hr")
            print(f"{'='*60}\n")

            if i < len(self.industries) - 1 and not self.shutdown_requested:
                next_industry = self.industries[i + 1]
                logger.info(f"Moving to next industry: {next_industry.upper()}")

        # Final flush
        self._flush_all_buffers()

        # Final stats
        stats = self._get_final_stats()
        self._print_stats(stats)
        return stats

    def _get_final_stats(self) -> Dict:
        elapsed = time.time() - self.start_time if self.start_time else 0
        total_leads = self.tracker.get_total_leads()
        completed = self.tracker.get_completed_count()
        industry_stats = self.tracker.get_industry_stats()

        sheet_stats = {}
        if self.sheets:
            try:
                sheet_stats = self.sheets.get_stats()
            except Exception:
                pass

        return {
            "total_leads": total_leads,
            "session_leads": self.session_leads,
            "searches_completed": completed,
            "elapsed_seconds": elapsed,
            "elapsed_hours": round(elapsed / 3600, 2),
            "leads_per_hour": round(self.session_leads / (elapsed / 3600), 0) if elapsed > 60 else 0,
            "industry_stats": industry_stats,
            "sheet_stats": sheet_stats,
            "shutdown_requested": self.shutdown_requested,
        }

    def _print_stats(self, stats: Dict):
        print(f"\n{'='*60}")
        print("SCRAPER SESSION SUMMARY")
        print(f"{'='*60}")
        print(f"Total leads in database: {stats['total_leads']:,}")
        print(f"Leads this session: {stats['session_leads']:,}")
        print(f"Searches completed: {stats['searches_completed']}")
        print(f"Duration: {stats['elapsed_hours']} hours")
        if stats['leads_per_hour']:
            print(f"Rate: {stats['leads_per_hour']:.0f} leads/hour")
        if stats["industry_stats"]:
            print(f"\nPer Industry:")
            for ind, ist in stats["industry_stats"].items():
                print(f"  {ind}: {ist['searches']} searches, {ist['leads']:,} leads")
        if stats["sheet_stats"]:
            print(f"\nGoogle Sheets:")
            for tab, count in stats["sheet_stats"].items():
                print(f"  {tab}: {count:,}" if isinstance(count, int) else f"  {tab}: {count}")
        if stats["shutdown_requested"]:
            print(f"\nShutdown requested. Run with --resume to continue.")
        print(f"{'='*60}\n")


async def run_test(save: bool = False):
    """Test mode: 1 industry, 1 city."""
    logger.info("RUNNING IN TEST MODE")

    scraper = MassScraper(
        industries=["pest control"],
        parallel=1,
        use_sheets=save,
        use_subdivisions=False,
    )

    from us_metros import US_METROS
    test_location = f"{US_METROS[3][0]}, {US_METROS[3][1]}"  # Houston, TX

    scraper.start_time = time.time()

    gms = GoogleMapsScraper()
    await gms.start()

    try:
        results = await gms.search("pest control", test_location)

        with_website = sum(1 for b in results if b.get("website"))
        with_phone = sum(1 for b in results if b.get("phone"))

        print(f"\nFound {len(results)} businesses for 'pest control' in {test_location}")
        print(f"  With website: {with_website}")
        print(f"  With phone: {with_phone}")
        print(f"\nFirst 10 results:")
        print(f"{'Name':<35} {'Phone':<16} {'Website':<35} {'Address'}")
        print("-" * 120)
        for biz in results[:10]:
            print(
                f"{biz['company_name'][:34]:<35} "
                f"{biz['phone'][:15]:<16} "
                f"{(biz.get('website') or 'N/A')[:34]:<35} "
                f"{biz['address'][:30]}"
            )

        if save and scraper.sheets:
            written = scraper.sheets.write_leads(results, "pest control", f"pest control near {test_location}")
            print(f"\nWrote {written} leads to Google Sheets")
            stats = scraper.sheets.get_stats()
            print(f"Sheet stats: {stats}")

        print(f"\nTest complete. {len(results)} leads found.")

    finally:
        await gms.stop()


def main():
    parser = argparse.ArgumentParser(description="Mass Google Maps Lead Scraper")

    parser.add_argument("--test", action="store_true", help="Test mode: 1 industry, 1 city")
    parser.add_argument("--save", action="store_true", help="Write to Google Sheets (with --test)")
    parser.add_argument("--resume", action="store_true", help="Resume from previous progress")
    parser.add_argument("--reset", action="store_true", help="Reset all progress")
    parser.add_argument("--parallel", type=int, default=2, help="Parallel browsers (default: 2)")
    parser.add_argument("--industries", nargs="+", default=None, help="Industries to scrape")
    parser.add_argument("--no-sheets", action="store_true", help="Skip Google Sheets output")
    parser.add_argument("--no-subdivisions", action="store_true", help="Base cities only")
    parser.add_argument("--stats", action="store_true", help="Show progress and exit")

    args = parser.parse_args()

    if args.stats:
        tracker = ProgressTracker()
        industry_stats = tracker.get_industry_stats()
        print(f"\nProgress Stats:")
        print(f"  Completed searches: {tracker.get_completed_count()}")
        print(f"  Total leads: {tracker.get_total_leads():,}")
        if industry_stats:
            print(f"\n  Per Industry:")
            for ind, ist in industry_stats.items():
                print(f"    {ind}: {ist['searches']} searches, {ist['leads']:,} leads")
        tracker.close()
        return

    if args.reset:
        tracker = ProgressTracker()
        tracker.reset()
        tracker.close()
        print("Progress reset. Starting fresh.")
        return

    if args.test:
        asyncio.run(run_test(save=args.save))
        return

    if not args.resume:
        tracker = ProgressTracker()
        if tracker.get_completed_count() > 0:
            print(f"\nExisting progress found: {tracker.get_completed_count()} searches, "
                  f"{tracker.get_total_leads():,} leads")
            print("Use --resume to continue or --reset to start fresh.")
            tracker.close()
            return
        tracker.close()

    scraper = MassScraper(
        industries=args.industries or DEFAULT_INDUSTRIES,
        parallel=args.parallel,
        use_sheets=not args.no_sheets,
        use_subdivisions=not args.no_subdivisions,
    )

    asyncio.run(scraper.run())


if __name__ == "__main__":
    main()
