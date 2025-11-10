"""Quick utility to verify OpenAI API access.

Usage:
    export OPENAI_API_KEY=sk-...
    python scripts/test_openai_key.py
"""

import os
import sys

try:
    from openai import OpenAI
except ImportError as exc:
    sys.stderr.write(
        "openai package not found. Install with 'pip install openai'.\n"
    )
    raise


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set in the environment.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input="Quick connectivity test. Reply with a short confirmation message."
        )
    except Exception as exc:
        print(f"API call failed: {exc}")
        sys.exit(1)

    message = response.output_text.strip() if hasattr(response, "output_text") else response
    print("API call succeeded. Model response:\n")
    print(message)


if __name__ == "__main__":
    main()
