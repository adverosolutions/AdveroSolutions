"""
Scraper Monitor - Live Terminal Dashboard
Shows real-time progress for the mass lead scraper.

Usage:
    python3 scraper_monitor.py            # Live dashboard (refreshes every 5s)
    python3 scraper_monitor.py --once     # Print stats once and exit
"""

import os
import sys
import sqlite3
import time
import argparse
from datetime import datetime, timedelta
from collections import deque

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich import box

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_progress.db")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper.log")

INDUSTRIES = ["HVAC", "roofing"]
INDUSTRY_DISPLAY = {
    "HVAC": "HVAC",
    "roofing": "Roofing",
}

# Total locations per industry (from us_metros.py)
TOTAL_LOCATIONS = 864

console = Console()


def get_db_stats():
    """Read current stats from SQLite."""
    if not os.path.exists(DB_PATH):
        return None

    try:
        conn = sqlite3.connect(DB_PATH)

        # Overall stats
        total_leads = conn.execute("SELECT COUNT(*) FROM scraped_leads").fetchone()[0]
        total_searches = conn.execute("SELECT COUNT(*) FROM completed_searches").fetchone()[0]
        total_raw = conn.execute("SELECT COALESCE(SUM(result_count), 0) FROM completed_searches").fetchone()[0]

        # Per-industry stats
        industry_stats = {}
        for ind in INDUSTRIES:
            cur = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(result_count), 0) FROM completed_searches WHERE industry=?",
                (ind,),
            )
            row = cur.fetchone()
            searches = row[0]
            leads = row[1]

            # Failed count
            failed = conn.execute(
                "SELECT COUNT(*) FROM failed_searches WHERE industry=? AND retry_count < 3",
                (ind,),
            ).fetchone()[0]

            industry_stats[ind] = {
                "searches": searches,
                "leads": leads,
                "failed": failed,
                "pct": round(searches / TOTAL_LOCATIONS * 100, 1) if TOTAL_LOCATIONS > 0 else 0,
            }

        # Most recent search
        last_search = conn.execute(
            "SELECT industry, location, result_count, completed_at FROM completed_searches ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()

        # First search timestamp (for calculating runtime)
        first_search = conn.execute(
            "SELECT completed_at FROM completed_searches ORDER BY completed_at ASC LIMIT 1"
        ).fetchone()

        # Recent activity (last 10 searches)
        recent = conn.execute(
            "SELECT industry, location, result_count, completed_at FROM completed_searches ORDER BY completed_at DESC LIMIT 10"
        ).fetchall()

        # Failed searches
        total_failed = conn.execute(
            "SELECT COUNT(*) FROM failed_searches WHERE retry_count >= 3"
        ).fetchone()[0]

        conn.close()

        return {
            "total_leads": total_leads,
            "total_searches": total_searches,
            "total_raw": total_raw,
            "industry_stats": industry_stats,
            "last_search": last_search,
            "first_search": first_search,
            "recent": recent,
            "total_failed": total_failed,
        }
    except Exception as e:
        return {"error": str(e)}


def get_recent_log_lines(n=8):
    """Get the last N lines from the scraper log."""
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-n:]]
    except Exception:
        return []


def calc_eta(stats):
    """Calculate estimated time remaining."""
    if not stats or not stats.get("first_search"):
        return "N/A"

    try:
        first_time = datetime.fromisoformat(stats["first_search"][0])
        elapsed = (datetime.now() - first_time).total_seconds()

        if elapsed < 60 or stats["total_searches"] < 5:
            return "Calculating..."

        total_needed = TOTAL_LOCATIONS * len(INDUSTRIES)
        remaining = total_needed - stats["total_searches"]

        rate = stats["total_searches"] / elapsed  # searches per second
        if rate <= 0:
            return "N/A"

        seconds_left = remaining / rate
        hours = int(seconds_left // 3600)
        minutes = int((seconds_left % 3600) // 60)

        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"
    except Exception:
        return "N/A"


def calc_rate(stats):
    """Calculate leads per hour."""
    if not stats or not stats.get("first_search"):
        return 0

    try:
        first_time = datetime.fromisoformat(stats["first_search"][0])
        elapsed_hours = (datetime.now() - first_time).total_seconds() / 3600

        if elapsed_hours < 0.01:
            return 0

        return int(stats["total_leads"] / elapsed_hours)
    except Exception:
        return 0


def calc_runtime(stats):
    """Calculate total runtime."""
    if not stats or not stats.get("first_search"):
        return "Not started"

    try:
        first_time = datetime.fromisoformat(stats["first_search"][0])
        elapsed = datetime.now() - first_time
        hours = int(elapsed.total_seconds() // 3600)
        minutes = int((elapsed.total_seconds() % 3600) // 60)

        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"
    except Exception:
        return "N/A"


def determine_current_industry(stats):
    """Figure out which industry is currently being scraped."""
    if not stats or not stats.get("industry_stats"):
        return None

    for ind in INDUSTRIES:
        ist = stats["industry_stats"].get(ind, {})
        searches = ist.get("searches", 0)
        if 0 < searches < TOTAL_LOCATIONS:
            return ind

    # If none are in-progress, find the first one not started
    for ind in INDUSTRIES:
        ist = stats["industry_stats"].get(ind, {})
        if ist.get("searches", 0) == 0:
            return ind

    return None


def build_dashboard(stats):
    """Build the rich dashboard layout."""
    if not stats:
        return Panel("[yellow]No scraper data found. Waiting for scraper to start...[/yellow]",
                     title="Scraper Monitor", border_style="yellow")

    if "error" in stats:
        return Panel(f"[red]Database error: {stats['error']}[/red]",
                     title="Scraper Monitor", border_style="red")

    total_needed = TOTAL_LOCATIONS * len(INDUSTRIES)
    overall_pct = round(stats["total_searches"] / total_needed * 100, 1) if total_needed > 0 else 0
    rate = calc_rate(stats)
    eta = calc_eta(stats)
    runtime = calc_runtime(stats)
    current_industry = determine_current_industry(stats)

    # Header stats
    header = Table(show_header=False, box=None, padding=(0, 2))
    header.add_column(width=25)
    header.add_column(width=25)
    header.add_column(width=25)
    header.add_column(width=25)

    header.add_row(
        f"[bold cyan]Total Leads[/]\n[bold white]{stats['total_leads']:,}[/]",
        f"[bold cyan]Searches[/]\n[bold white]{stats['total_searches']:,} / {total_needed:,}[/]",
        f"[bold cyan]Rate[/]\n[bold white]{rate:,} leads/hr[/]",
        f"[bold cyan]ETA[/]\n[bold white]{eta}[/]",
    )

    # Progress bar
    filled = int(overall_pct / 2)
    bar_text = "█" * filled + "░" * (50 - filled)
    progress_str = f"[bold green]{bar_text}[/] {overall_pct}%"

    # Industry table
    ind_table = Table(
        title="Industry Progress",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
        width=100,
    )
    ind_table.add_column("Industry", style="bold", width=20)
    ind_table.add_column("Searches", justify="center", width=16)
    ind_table.add_column("Progress", width=32)
    ind_table.add_column("Leads", justify="right", width=10)
    ind_table.add_column("Status", justify="center", width=14)

    for ind in INDUSTRIES:
        ist = stats["industry_stats"].get(ind, {"searches": 0, "leads": 0, "failed": 0, "pct": 0})
        display_name = INDUSTRY_DISPLAY.get(ind, ind.title())
        pct = ist["pct"]
        searches = ist["searches"]
        leads = ist["leads"]

        # Mini progress bar
        bar_filled = int(pct / 2.5)
        bar = "█" * bar_filled + "░" * (40 - bar_filled)
        bar_str = f"{bar} {pct}%"

        # Status indicator
        if searches == 0:
            status = "[dim]Pending[/]"
        elif searches >= TOTAL_LOCATIONS:
            status = "[bold green]Complete[/]"
        elif ind == current_industry:
            status = "[bold yellow]Active[/]"
        else:
            status = "[dim]Waiting[/]"

        # Highlight active industry
        if ind == current_industry:
            ind_table.add_row(
                f"[bold yellow]>> {display_name}[/]",
                f"[yellow]{searches} / {TOTAL_LOCATIONS}[/]",
                f"[yellow]{bar_str}[/]",
                f"[yellow]{leads:,}[/]",
                status,
            )
        else:
            ind_table.add_row(
                display_name,
                f"{searches} / {TOTAL_LOCATIONS}",
                bar_str,
                f"{leads:,}",
                status,
            )

    # Recent activity
    recent_table = Table(
        title="Recent Activity",
        box=box.SIMPLE,
        border_style="dim",
        width=100,
    )
    recent_table.add_column("Time", width=12, style="dim")
    recent_table.add_column("Industry", width=18)
    recent_table.add_column("Location", width=30)
    recent_table.add_column("Leads", justify="right", width=8)

    for search in stats.get("recent", []):
        ind, loc, count, timestamp = search
        try:
            t = datetime.fromisoformat(timestamp)
            time_str = t.strftime("%H:%M:%S")
        except Exception:
            time_str = "?"
        display_ind = INDUSTRY_DISPLAY.get(ind, ind.title())
        recent_table.add_row(time_str, display_ind, loc[:29], str(count))

    # Log tail
    log_lines = get_recent_log_lines(6)
    log_text = "\n".join(log_lines) if log_lines else "[dim]No log entries yet[/]"

    # Compose the dashboard
    output = Table.grid(padding=(1, 0))
    output.add_row(
        Panel(header, title="[bold white]MASS LEAD SCRAPER[/]", border_style="bright_cyan", padding=(1, 2))
    )
    output.add_row(
        Panel(
            f"  Overall: {progress_str}    Runtime: [bold]{runtime}[/]    Failed: [red]{stats.get('total_failed', 0)}[/]",
            border_style="dim",
        )
    )
    output.add_row(ind_table)
    output.add_row(recent_table)
    output.add_row(
        Panel(log_text, title="[dim]Log Tail[/]", border_style="dim", padding=(0, 1))
    )
    output.add_row(
        Text("  Press Ctrl+C to exit monitor (scraper keeps running)", style="dim italic")
    )

    return output


def run_live():
    """Run the live dashboard that refreshes every 5 seconds."""
    console.clear()
    console.print("[bold cyan]Starting Scraper Monitor...[/]\n")

    with Live(build_dashboard(get_db_stats()), console=console, refresh_per_second=0.2, screen=True) as live:
        try:
            while True:
                time.sleep(5)
                stats = get_db_stats()
                live.update(build_dashboard(stats))
        except KeyboardInterrupt:
            console.print("\n[dim]Monitor stopped. Scraper continues running.[/]")


def run_once():
    """Print stats once and exit."""
    stats = get_db_stats()
    if not stats:
        console.print("[yellow]No scraper data found.[/]")
        return

    console.print(build_dashboard(stats))


def main():
    parser = argparse.ArgumentParser(description="Scraper Monitor - Live Dashboard")
    parser.add_argument("--once", action="store_true", help="Print stats once and exit")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_live()


if __name__ == "__main__":
    main()
