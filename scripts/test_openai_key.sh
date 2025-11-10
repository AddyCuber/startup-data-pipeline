#!/bin/zsh
# Usage: OPENAI_API_KEY=sk-... ./scripts/test_openai_key.sh

if [[ -z "$OPENAI_API_KEY" ]]; then
  echo "OPENAI_API_KEY is not set." >&2
  exit 1
fi

python3 <<'PY'
import os
import sys

from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

try:
    response = client.responses.create(
        model="gpt-4o-mini",
        input="Hello! Please respond with a single word confirmation."
    )
except Exception as exc:
    print(f"API call failed: {exc}")
    sys.exit(1)

print("API call succeeded. Model response:\n")
print(response.output_text.strip())
PY
