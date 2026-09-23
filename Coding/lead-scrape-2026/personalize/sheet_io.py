#!/usr/bin/env python3
"""Google Sheets plumbing for the live personalization run.

  python3 personalize/sheet_io.py load  <sheet_id>   # push MASTER_for_sheets.csv into tab "Leads"
  python3 personalize/sheet_io.py check <sheet_id>   # confirm access + row counts

Auth: service account from AdveroSolutions/Agentic Worklfows/credentials.json.
The sheet must be shared with that account as Editor (it cannot create sheets).
"""
import csv, sys, time
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT.parents[1] / "Agentic Worklfows" / "credentials.json"
MASTER = ROOT / "output" / "FINAL" / "MASTER_for_sheets.csv"
TAB = "Leads"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def client():
    return gspread.authorize(Credentials.from_service_account_file(str(CREDS), scopes=SCOPES))


def open_tab(sheet_id: str):
    ss = client().open_by_key(sheet_id)
    try:
        return ss.worksheet(TAB)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(TAB, rows=7000, cols=40)


def load(sheet_id: str) -> None:
    rows = list(csv.reader(MASTER.open(encoding="utf-8-sig")))
    ws = open_tab(sheet_id)
    ws.clear()
    # one batched write per ~2,000 rows keeps well inside the 60 req/min quota
    for i in range(0, len(rows), 2000):
        ws.update(f"A{i+1}", rows[i:i+2000], value_input_option="RAW")
        print(f"  wrote rows {i+1}-{min(i+2000, len(rows))}")
        time.sleep(1)
    ws.freeze(rows=1, cols=3)
    print(f"[load] {len(rows)-1} leads -> tab '{TAB}' in {sheet_id}")


def check(sheet_id: str) -> None:
    ws = open_tab(sheet_id)
    hdr = ws.row_values(1)
    n = len(ws.col_values(1)) - 1
    print(f"[check] access OK | tab '{TAB}' | {n} data rows | {len(hdr)} cols")
    print("  personalization cols present:", all(c in hdr for c in
          ["personalization_status", "icebreaker", "angle", "research_notes", "personalized_at"]))


if __name__ == "__main__":
    cmd, sid = sys.argv[1], sys.argv[2]
    {"load": load, "check": check}[cmd](sid)
