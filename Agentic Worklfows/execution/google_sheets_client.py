"""
Google Sheets Client - Shared Utility
======================================

This module provides shared Google Sheets authentication and access utilities.
It is used by both free_value_tracker.py (Chat 3) and lead_enricher.py (Chat 5).

This is the ONLY shared utility between modules - the sole exception to the
one-direction dependency rule.

Dependencies:
    - gspread
    - google-auth
    - google-auth-oauthlib

Usage:
    from google_sheets_client import get_sheets_client, open_sheet

    client = get_sheets_client('path/to/credentials.json')
    worksheet = open_sheet(client, 'sheet_id', 'Tab Name')
"""

import json
import os
from typing import Union
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError as e:
    raise ImportError(
        "Missing required dependencies. Install with: "
        "pip install gspread google-auth google-auth-oauthlib"
    ) from e


# Cache for authenticated clients (avoid re-authenticating on every call)
_CLIENT_CACHE = {}


def get_sheets_client(credentials_source: Union[str, dict]) -> gspread.Client:
    """
    Get an authenticated Google Sheets client with connection pooling/caching.

    Args:
        credentials_source: Either:
            - Path to service account JSON file (str)
            - Service account credentials as dict
            - Service account JSON as string

    Returns:
        gspread.Client: Authenticated Google Sheets client

    Raises:
        ValueError: If credentials are invalid or missing
        FileNotFoundError: If credentials file path doesn't exist

    Example:
        # From file path
        client = get_sheets_client('/path/to/credentials.json')

        # From dict
        creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
        client = get_sheets_client(creds_dict)

        # From JSON string
        client = get_sheets_client(os.environ['GOOGLE_CREDENTIALS_JSON'])
    """
    # Generate cache key
    if isinstance(credentials_source, dict):
        cache_key = credentials_source.get('client_email', 'unknown')
    elif isinstance(credentials_source, str):
        if os.path.isfile(credentials_source):
            cache_key = f"file:{credentials_source}"
        else:
            # Assume it's a JSON string
            try:
                creds_dict = json.loads(credentials_source)
                cache_key = creds_dict.get('client_email', 'unknown')
            except json.JSONDecodeError:
                raise ValueError(
                    "credentials_source must be a valid file path, JSON string, or dict"
                )
    else:
        raise ValueError(
            "credentials_source must be a file path (str), JSON string (str), or dict"
        )

    # Return cached client if available
    if cache_key in _CLIENT_CACHE:
        print(f"[{_timestamp()}] Using cached Google Sheets client for {cache_key}")
        return _CLIENT_CACHE[cache_key]

    # Load credentials
    try:
        if isinstance(credentials_source, dict):
            creds_dict = credentials_source
        elif os.path.isfile(credentials_source):
            with open(credentials_source, 'r') as f:
                creds_dict = json.load(f)
        else:
            # JSON string
            creds_dict = json.loads(credentials_source)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Credentials file not found: {credentials_source}"
        )
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in credentials: {e}"
        )

    # Validate required fields
    required_fields = ['type', 'project_id', 'private_key', 'client_email']
    missing = [f for f in required_fields if f not in creds_dict]
    if missing:
        raise ValueError(
            f"Missing required credential fields: {', '.join(missing)}"
        )

    if creds_dict['type'] != 'service_account':
        raise ValueError(
            f"Expected service_account credentials, got: {creds_dict['type']}"
        )

    # Authenticate
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=scopes
        )
        client = gspread.authorize(credentials)

        print(f"[{_timestamp()}] ✓ Authenticated Google Sheets client: {creds_dict['client_email']}")

        # Cache the client
        _CLIENT_CACHE[cache_key] = client

        return client

    except Exception as e:
        raise ValueError(
            f"Failed to authenticate with Google Sheets: {e}"
        )


def open_sheet(
    client: gspread.Client,
    sheet_id: str,
    tab_name: str
) -> gspread.Worksheet:
    """
    Open a specific worksheet (tab) in a Google Sheet.

    Args:
        client: Authenticated gspread.Client (from get_sheets_client)
        sheet_id: Google Sheet ID (from URL)
        tab_name: Name of the tab/worksheet to open

    Returns:
        gspread.Worksheet: The opened worksheet

    Raises:
        ValueError: If sheet or tab cannot be opened

    Example:
        client = get_sheets_client('credentials.json')
        worksheet = open_sheet(client, '1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8', 'Free Value Sends')
    """
    try:
        spreadsheet = client.open_by_key(sheet_id)
        print(f"[{_timestamp()}] ✓ Opened spreadsheet: {spreadsheet.title}")

        worksheet = spreadsheet.worksheet(tab_name)
        print(f"[{_timestamp()}] ✓ Opened worksheet: {tab_name}")

        return worksheet

    except gspread.exceptions.SpreadsheetNotFound:
        raise ValueError(
            f"Spreadsheet not found: {sheet_id}. "
            "Make sure the service account has access to this sheet."
        )
    except gspread.exceptions.WorksheetNotFound:
        raise ValueError(
            f"Worksheet '{tab_name}' not found in spreadsheet {sheet_id}. "
            f"Available tabs: {[ws.title for ws in spreadsheet.worksheets()]}"
        )
    except Exception as e:
        raise ValueError(
            f"Failed to open sheet: {e}"
        )


def _timestamp() -> str:
    """Helper to generate timestamp for logging."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clear_client_cache():
    """
    Clear the client cache. Useful for testing or forcing re-authentication.

    Example:
        clear_client_cache()
    """
    global _CLIENT_CACHE
    _CLIENT_CACHE = {}
    print(f"[{_timestamp()}] Client cache cleared")


if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) < 3:
        print("Usage: python google_sheets_client.py <credentials_path> <sheet_id> <tab_name>")
        sys.exit(1)

    creds_path = sys.argv[1]
    sheet_id = sys.argv[2]
    tab_name = sys.argv[3] if len(sys.argv) > 3 else "Sheet1"

    try:
        client = get_sheets_client(creds_path)
        worksheet = open_sheet(client, sheet_id, tab_name)
        print(f"\n✓ Successfully connected to '{tab_name}'")
        print(f"  Rows: {worksheet.row_count}")
        print(f"  Cols: {worksheet.col_count}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
