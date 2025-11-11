import os
import json
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel("models/gemini-2.5-flash")
HEADERS = {
    "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_article_text(url: str, max_len: int = 3000) -> str:
    """
    Fetch article content and extract readable text.
    We limit length to reduce LLM token usage and rate-limits.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.content, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs)
        return text[:max_len]
    except:
        return ""


PROMPT = """
You are a precise financial data extraction model. 
Your task is to read the funding news text and return a JSON object ONLY.

RULES:
- Do not guess. If a value is not clearly stated, return null.
- Extract website_url ONLY if explicitly mentioned in the text (e.g., hyperlinks, press release contact footer, "Visit: https://..."). Do NOT infer or invent one.
- Convert funding amounts to integer USD values.
  Examples:
    "$5M" → 5000000
    "₹20 Cr" → ~2400000 (approximate conversion acceptable)
    "€2.3M" → convert to USD using rough rate (1 EUR ≈ 1.1 USD)
- Investors must be a list of strings.
- No commentary. No backticks.

Return JSON exactly in this structure:

{{
  "company_name": string or null,
  "website_url": string or null,
  "amount_raised_usd": integer or null,
  "funding_round": string or null,
  "investors": list of strings,
  "lead_investor": string or null,
  "headquarter_country": string or null
}}

TEXT TO ANALYZE:
{context}
"""

def safe_parse_llm(context: str) -> dict:
    """Call Gemini and robustly parse JSON output."""
    try:
        prompt_text = PROMPT.format(context=context)

        if len(prompt_text) < 200:
            print("⚠️ DEBUG: Prompt too short — likely empty article body!")

        response = MODEL.generate_content(prompt_text)
        raw = getattr(response, "text", "").strip() or response.candidates[0].content.parts[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        stripped = raw.strip()
        if stripped and not stripped.startswith("{"):
            stripped = "{" + stripped
        if stripped and not stripped.endswith("}"):
            stripped = stripped + "}"
        raw = stripped

        try:
            return json.loads(raw)
        except json.JSONDecodeError as parse_err:
            print(f"⚠️ DEBUG: JSON decode error {parse_err}. Raw response: {raw}")
            raw = raw.replace(",}", "}").replace(", ]", "]")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as parse_err_2:
                print(f"⚠️ DEBUG: Second decode error {parse_err_2}. Raw response after cleanup: {raw}")
                return {}

    except Exception as exc:
        print(f"⚠️ LLM call failed: {exc}")
        return {}


def enrich_articles(articles: list) -> list:
    """
    Takes RSS articles → extracts structured funding data via the LLM.
    """
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️ GEMINI_API_KEY missing — skipping LLM enrichment.")
        return []

    if not articles:
        print("⚠️ No articles to enrich.")
        return []

    enriched = []
    print(f"\n🔍 Extracting structured funding details for {len(articles)} articles...\n")

    for article in articles:
        body = fetch_article_text(article["url"])
        if not body:
            print(f"⚠️ Skipped (no article text): {article['title']}")
            continue

        context = f"TITLE: {article['title']}\nBODY: {body}"

        data = safe_parse_llm(context)
        if not data or not data.get("company_name"):
            print(f"⚠️ No data extracted → {article['title']}")
            continue

        merged = {**article, **data}
        enriched.append(merged)

        print(f"✅ {merged['company_name']} — ${merged.get('amount_raised_usd')} ({merged.get('funding_round')})")

    print(f"\n✅ Enriched {len(enriched)} articles.\n")
    return enriched

