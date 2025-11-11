import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def load_credentials():
    # Ensure .env (if present) is loaded so exports take precedence
    project_root = Path(__file__).resolve().parents[1]
    dotenv_path = project_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=True)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. "
            "Set them in your environment or the project's .env file."
        )
    return token, chat_id


def send_test_message(token: str, chat_id: str, text: str) -> dict:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(api_url, json=payload, timeout=10)
    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError("Telegram API returned a non-JSON response.")

    if response.status_code != 200 or not data.get("ok", False):
        raise RuntimeError(f"Telegram API error: {data}")
    return data


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Send a test Telegram message using credentials in the environment."
    )
    parser.add_argument(
        "--message",
        "-m",
        default="Test message from startup-signal-pipeline",
        help="The message text to send.",
    )
    args = parser.parse_args(argv)

    try:
        token, chat_id = load_credentials()
        result = send_test_message(token, chat_id, args.message)
    except Exception as exc:
        print(f"❌ Failed to send Telegram test message: {exc}")
        return 1

    print("✅ Telegram test message sent successfully.")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

