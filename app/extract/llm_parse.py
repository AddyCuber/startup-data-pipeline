import os
import json
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini (Paid or Free Tier)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel("gemini-2.5-flash")

HEADERS = {
    "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_article_text(url: str, max_len: int = 1800) -> str:
    """
    Fetch article content and extract readable text.
    Limit ensures lower token cost & rate-limit stability.
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
Return ONLY valid JSON. No commentary.

RULES:
- Do not guess. If a value is not clearly stated, return null.
- Extract website_url AND linkedin_url ONLY if explicitly mentioned in the text. Do NOT guess.
- Convert funding amounts to integer USD values.
  Examples:
    "$5M" → 5000000
    "₹20 Cr" → ~2400000
    "€2.3M" → convert assuming 1 EUR ≈ 1.1 USD
- Investors must be a list of strings. If none, return [].

Return EXACT JSON structure:

{
  "company_name": string or null,
  "website_url": string or null,
  "linkedin_url": string or null,
  "amount_raised_usd": integer or null,
  "funding_round": string or null,
  "investors": list,
  "lead_investor": string or null,
  "headquarter_country": string or null
}

TEXT:
{context}
"""


def safe_parse_llm(context: str) -> dict:
    """
    Call Gemini → parse → clean → return dict.
    Uses new stable `.text` field (no `.candidates`).
    """
    try:
        prompt_text = PROMPT.replace("{context}", context)
        response = MODEL.generate_content(prompt_text)

        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        # JSON boundary cleanup
        if "{" in raw and "}" in raw:
            raw = raw[raw.find("{"): raw.rfind("}") + 1]
        else:
            trimmed = raw.strip().rstrip(",")
            if trimmed:
                raw = "{\n" + trimmed + "\n}"

        # Try parse
        try:
            return json.loads(raw)
        except:
            raw = raw.replace(",}", "}").replace(", ]", "]")
            return json.loads(raw)

    except Exception as exc:
        print(f"⚠️ LLM call failed: {exc}")
        return {}


def enrich_articles(articles: list) -> list:
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️ GEMINI_API_KEY missing — skipping enrichment.")
        return []

    if not articles:
        print("⚠️ No articles to enrich.")
        return []

    enriched = []
    print(f"\n🔍 Extracting structured data for {len(articles)} articles...\n")

    for article in articles:
        body = fetch_article_text(article["url"])
        if not body:
            print(f"⚠️ Skipped (no text): {article['title']}")
            continue

        context = f"TITLE: {article['title']}\nBODY: {body}"
        data = safe_parse_llm(context)

        if not data or not data.get("company_name"):
            print(f"⚠️ No data → {article['title']}")
            continue

        merged = {**article, **data}
        enriched.append(merged)

        print(f"✅ {merged['company_name']} — ${merged.get('amount_raised_usd')} ({merged.get('funding_round')})")

    print(f"\n✅ Enriched {len(enriched)} articles.\n")
    return enriched