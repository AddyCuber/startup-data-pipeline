import os
import requests
from dotenv import load_dotenv

# Load .env variables
load_dotenv(override=True)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(data: dict):
    """
    Formats a rich Telegram message and sends it via the Bot API.
    """
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram alert skipped: BOT_TOKEN or CHAT_ID not set.")
        return

    # 1. Format the data (using HTML for rich text)
    company_name = data.get("company_name", "Unknown Company")
    amount_usd = data.get("amount_raised_usd", 0)
    funding_round = data.get("funding_round", "N/A")
    careers_url = data.get("careers_url", "")
    domain = data.get("domain", "")
    details = data.get("details", "N/A")
    
    amount_str = f"${amount_usd:,}" if amount_usd else "Undisclosed"

    # 2. Create the HTML message
    # Telegram supports <b> (bold), <i> (italic), <a> (links)
    message = (
        f"<b>🔥 New Tier A Lead: {company_name}</b>\n\n"
        f"<b>Amount:</b> {amount_str}\n"
        f"<b>Round:</b> {funding_round}\n"
        f"<b>Signal:</b> {details}\n\n"
        f"<a href='{domain}'>Visit Website</a>  •  <a href='{careers_url}'>View Careers</a>"
    )

    # 3. Build the API URL and payload
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    # 4. Send the request
    try:
        resp = requests.post(api_url, json=payload, timeout=5)
        if resp.status_code != 200:
            print(f"⚠️ Telegram API responded with {resp.status_code}: {resp.text}")
        else:
            print(f"✅ Telegram alert sent for {company_name}")
    except requests.RequestException as e:
        print(f"⚠️ Could not send Telegram alert: {e}")