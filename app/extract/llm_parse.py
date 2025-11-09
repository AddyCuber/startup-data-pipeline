import json
import os
from typing import Any, Dict, List, Optional

import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

GENAI_API_KEY = os.getenv("GEMINI_API_KEY")

if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)
    MODEL = genai.GenerativeModel("models/gemini-2.5-flash")
else:
    MODEL = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

PROMPT = """
You are a precise financial data extraction model. 
Your task is to read the funding news text and return a JSON object ONLY.

RULES:
- Do not guess. If a value is not clearly stated, return null.
- Amounts must be converted to an integer USD value.
  Examples:
    "$5M" → 5000000
    "₹20 Cr" → ~2400000 (approx, but do convert)
    "€2.3M" → convert to USD using rough rate (1 EUR ≈ 1.1 USD)
- Investors must be a list of strings. If none mentioned, return [].
- Return no commentary, no explanations, no backticks.

Required JSON Fields:
{{
  "company_name": string or null,
  "amount_raised_usd": integer or null,
  "funding_round": string or null,
  "investors": list of strings,
  "lead_investor": string or null,
  "headquarter_country": string or null
}}

TEXT TO ANALYZE:
{context}
"""


def fetch_article_text(url: str, max_len: int = 3000) -> str:
    """Fetch article content and extract readable text."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(response.content, "html.parser")
    paragraphs = soup.find_all("p")
    text = " ".join(p.get_text(strip=True) for p in paragraphs)
    return text[:max_len]


def _clean_json_output(raw_text: str) -> Optional[Dict[str, Any]]:
    """Attempt to coerce the LLM output into valid JSON."""
    cleaned = (
        raw_text.replace("```json", "")
        .replace("```", "")
        .replace(",}", "}")
        .replace(", ]", "]")
        .strip()
    )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def safe_parse_llm(context: str) -> Dict[str, Any]:
    """Call Gemini Flash and safely parse JSON output."""
    if MODEL is None:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Set it in your environment before running enrichment."
        )

    try:
        response = MODEL.generate_content(PROMPT.format(context=context))
        text = response.candidates[0].content.parts[0].text.strip()
    except Exception as exc:
        raise RuntimeError(f"Gemini content generation failed: {exc}") from exc

    parsed = _clean_json_output(text)
    if parsed is None:
        raise ValueError("Unable to parse LLM output as JSON.")

    return parsed


def enrich_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Take raw RSS articles → Output enriched structured funding data."""
    if MODEL is None:
        print(
            "⚠️  GEMINI_API_KEY not set. Skipping LLM enrichment step. "
            "Provide the key to enable structured parsing."
        )
        return []

    if not articles:
        print("⚠️  No articles provided to enrichment.")
        return []

    enriched: List[Dict[str, Any]] = []

    for article in articles:
        body = fetch_article_text(article["url"])
        if not body:
            print(f"⚠️  Skipping '{article['title']}' (no article text fetched)")
            continue

        context = f"TITLE: {article['title']}\nBODY: {body}"

        try:
            data = safe_parse_llm(context)
        except Exception as exc:
            print(f"⚠️  Enrichment failed for '{article['title']}': {exc}")
            continue

        if not data or not data.get("company_name"):
            print(f"⚠️  No structured data extracted for '{article['title']}'")
            continue

        enriched.append({**article, **data})

    return enriched
