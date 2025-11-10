import os
import json
from datetime import datetime
from pathlib import Path
from typing import List

import gspread

ROOT_DIR = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT_DIR / "gen-lang-client-0811071215-3e0f9f2c4083.json"
SHEET_NAME = "Recently Funded Startups"


def get_client() -> gspread.client.Client | None:
    if not CREDS_PATH.exists():
        print(f"⚠️ Missing Google credentials JSON at {CREDS_PATH}")
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
        print("   Create the sheet and share it with the service account email shown in the credentials file.")
        return None

    headers = [
        "Company",
        "Domain",
        "Amount (USD)",
        "Round",
        "Investors",
        "Lead Investor",
        "Country",
        "Date Announced",
        "Hiring Tier",
        "Tech Roles",
        "ATS Provider",
        "Careers URL",
        "Source URL",
        "Last Updated",
    ]

    existing = sheet.get_values("A1:N1")
    if not existing:
        sheet.append_row(headers)
        sheet.format("A1:N1", {"textFormat": {"bold": True}})

    return sheet


def save_to_sheet(data_list: List[dict]) -> None:
    if not data_list:
        print("📊 Nothing to publish to Google Sheets (empty dataset).")
        return

    client = get_client()
    if not client:
        return

    sheet = init_sheet(client)
    if not sheet:
        return

    print(f"📊 Publishing {len(data_list)} rows to Google Sheets...")
    rows = []
    for item in data_list:
        investors = item.get("investors")
        if isinstance(investors, list):
            investors_str = ", ".join(investors)
        else:
            investors_str = investors or ""

        rows.append([
            item.get("company_name"),
            item.get("domain") or item.get("website_url"),
            item.get("amount_raised_usd"),
            item.get("funding_round"),
            investors_str,
            item.get("lead_investor"),
            item.get("headquarter_country"),
            (item.get("published_at") or "").split("T")[0],
            item.get("hiring_tier"),
            item.get("tech_roles"),
            item.get("ats_provider"),
            item.get("careers_url"),
            item.get("source_url") or item.get("url"),
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ])

    try:
        sheet.append_rows(rows, value_input_option="USER_ENTERED")
        print("✅ Successfully published to Google Sheets.")
    except Exception as exc:
        print(f"❌ Failed to publish to Google Sheets: {exc}")