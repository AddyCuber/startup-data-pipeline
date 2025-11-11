
import os
import sys

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError as exc:
    sys.stderr.write(
        "openai package not found. Install with 'pip install openai'.\n"
    )
    raise

def main() -> None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set in the environment.")
        sys.exit(1)

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello, OpenAI!"}],
        )
        message = response.output_text.strip() if hasattr(response, "output_text") else response
        print(f"API call successful. Response: {message}")
    except Exception as exc:
        print(f"API call failed: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
