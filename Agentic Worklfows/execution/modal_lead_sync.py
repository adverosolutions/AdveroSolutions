"""
Modal Scheduled App — Instantly Lead Sync
Runs daily at 9:00 AM CT to sync all lead statuses from Instantly to the CRM.

Deploy:
    python3 -m modal deploy execution/modal_lead_sync.py

Manual trigger:
    python3 -m modal run execution/modal_lead_sync.py::run_sync_now
"""

import modal
from pathlib import Path

app = modal.App("advero-lead-sync")

# Build image with dependencies and the sync scripts
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "gspread>=5.12.4",
        "google-auth>=2.0.0",
        "requests>=2.28.0",
        "python-dotenv>=1.0.0",
        "pytz>=2023.0",
    )
    .add_local_file(
        str(Path(__file__).parent / "instantly_lead_sync.py"),
        "/root/instantly_lead_sync.py",
    )
    .add_local_file(
        str(Path(__file__).parent / "instantly_api.py"),
        "/root/instantly_api.py",
    )
)


def _run_sync(dry_run: bool = False):
    """
    Core sync logic. Writes credentials.json from env var,
    then runs the lead sync.
    """
    import os
    import sys
    import json

    # Write Google credentials from env var to a temp file
    # (the sync script expects credentials.json in the working directory)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if creds_json:
        with open("/root/credentials.json", "w") as f:
            f.write(creds_json)

    # Set working directory so credentials.json is found
    os.chdir("/root")

    # Import and run the sync
    sys.path.insert(0, "/root")
    from instantly_lead_sync import InstantlyLeadSync

    syncer = InstantlyLeadSync()
    results = syncer.sync(dry_run=dry_run)

    # Log summary
    summary = (
        f"Lead Sync Complete: "
        f"{results['stages_updated']} stages updated, "
        f"{results['timestamps_updated']} timestamps updated, "
        f"{results['matched_in_crm']} matched, "
        f"{results['errors']} errors"
    )
    print(summary)

    # Send Slack notification if webhook is configured
    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    if slack_url and not dry_run:
        try:
            import requests
            changes_text = ""
            if results["changes"]:
                changes_text = "\n".join(
                    f"  • {c['email']}: {c['from_stage']} → {c['to_stage']}"
                    for c in results["changes"][:20]  # Cap at 20 to avoid huge messages
                )
                if len(results["changes"]) > 20:
                    changes_text += f"\n  ... and {len(results['changes']) - 20} more"

            slack_msg = {
                "text": (
                    f"*Instantly Lead Sync Complete*\n"
                    f"• Stages updated: {results['stages_updated']}\n"
                    f"• Matched in CRM: {results['matched_in_crm']}\n"
                    f"• Not in CRM: {results['not_in_crm']}\n"
                    f"• Errors: {results['errors']}\n"
                    + (f"\n*Changes:*\n{changes_text}" if changes_text else "\nNo changes needed — CRM is up to date.")
                )
            }
            requests.post(slack_url, json=slack_msg, timeout=10)
        except Exception as e:
            print(f"Slack notification failed: {e}")

    return results


# ── Scheduled function: runs daily at 9:00 AM CT ──────────────────────────
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("advero-lead-sync")],
    schedule=modal.Cron("0 9 * * *"),  # 9:00 AM CT (Modal uses workspace timezone)
    timeout=600,  # 10 minute timeout
)
def sync_leads_daily():
    """Scheduled daily sync — runs automatically at 9 AM CT."""
    print("=== Scheduled Lead Sync Starting ===")
    return _run_sync(dry_run=False)


# ── Manual trigger function ───────────────────────────────────────────────
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("advero-lead-sync")],
    timeout=600,
)
def run_sync_now(dry_run: bool = False):
    """Manual trigger — run via: python3 -m modal run execution/modal_lead_sync.py::run_sync_now"""
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"=== Manual Lead Sync ({mode}) ===")
    return _run_sync(dry_run=dry_run)
