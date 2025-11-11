import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import gspread

# --- Use your correct file paths ---
ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CREDS_FILENAME = "google_creds.json"
CREDS_FILENAME = os.getenv("GOOGLE_CREDS_JSON")
if not CREDS_FILENAME:
    # Prefer default filename if present, otherwise fall back to legacy name
    if (ROOT_DIR / DEFAULT_CREDS_FILENAME).exists():
        CREDS_FILENAME = DEFAULT_CREDS_FILENAME
    else:
        CREDS_FILENAME = "gen-lang-client-0811071215-3e0f9f2c4083.json"
CREDS_PATH = ROOT_DIR / CREDS_FILENAME
SHEET_NAME = "Recently Funded Startups"


def get_client() -> gspread.client.Client | None:
    if not CREDS_PATH.exists():
        print(f"⚠️ Missing Google credentials JSON at {CREDS_PATH}")
        print("   Set env var GOOGLE_CREDS_JSON to the filename, or place the key as 'google_creds.json' at repo root.")
        return None
    try:
        return gspread.service_account(filename=str(CREDS_PATH))
    except Exception as exc:
        print(f"❌ Failed to auth with Google Sheets: {exc}")
        return None


def init_sheet(client: gspread.client.Client):
    try:
        sheet = client.open(SHEET_NAME).sheet1
    except gspread.SpreadsheetNotFound:
        print(f"❌ Could not find a Google Sheet named '{SHEET_NAME}'.")
        print("   Create the sheet and share it with the service account email.")
        return None
    except Exception as e:
        print(f"❌ An error occurred opening the sheet: {e}")
        return None

    headers = [
        "Company", "Domain", "LinkedIn", "Amount (USD)", "Round", "Investors",
        "Lead Investor", "Country", "Date Announced", "Hiring Tier", 
        "Tech Roles", "ATS Provider", "Careers URL", "Source URL", "Last Updated",
    ]

    # ---
    # THE FIX: Check cell A1 directly instead of get_values()
    # ---
    try:
        first_row = sheet.row_values(1)
    except gspread.exceptions.CellNotFound:
        first_row = []

    if not first_row or first_row[0].strip() != headers[0]:
        print("Header row not found in Google Sheet. Updating header row...")
        sheet.update("A1:O1", [headers])
        try:
            sheet.format("A1:N1", {"textFormat": {"bold": True}})
        except Exception:
            pass  # Formatting requires Sheets API quota; ignore failures

    return sheet


def save_to_sheet(data_list: List[dict]) -> None:
    if not data_list:
        print("📊 Nothing to publish to Google Sheets (empty dataset).")
        return

    client = get_client()
    if not client: return

    sheet = init_sheet(client)
    if not sheet: return

    print(f"📊 Publishing {len(data_list)} rows to Google Sheets...")
    rows = []
    for item in data_list:
        investors = item.get("investors")
        if isinstance(investors, list):
            investors_str = ", ".join(investors)
        else:
            investors_str = investors or ""
            
        tech_roles = item.get("tech_roles")
        if tech_roles is None:
             tech_roles = 0 # Show 0 instead of blank

        rows.append([
            item.get("company_name"),
            item.get("domain") or item.get("website_url"),
            item.get("linkedin_url"),
            item.get("amount_raised_usd"),
            item.get("funding_round"),
            investors_str,
            item.get("lead_investor"),
            item.get("headquarter_country"),
            (item.get("published_at") or "").split("T")[0],
            item.get("hiring_tier"),
            tech_roles, # Use the new variable
            item.get("ats_provider"),
            item.get("careers_url"),
            item.get("source_url") or item.get("url"),
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        ])

    try:
        # Append rows, which starts at the first empty row (Row 2)
        sheet.append_rows(rows, value_input_option="USER_ENTERED")
        print("✅ Successfully published to Google Sheets.")
    except Exception as exc:
        print(f"❌ Failed to publish to Google Sheets: {exc}")