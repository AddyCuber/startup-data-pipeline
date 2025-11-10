import time
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def normalize_domain(url: str) -> str | None:
    """Normalize a URL down to the https://domain.tld form."""
    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        parsed = urlparse(url)
        clean_domain = parsed.netloc.lower().replace("www.", "")
        if not clean_domain:
            return f"https://{url.lower().replace('www.', '').split('/')[0]}"
        return f"https://{clean_domain}"
    except Exception:
        return None


def resolve_via_duckduckgo(company_name: str) -> tuple[str | None, float]:
    """Attempt to find the official site via DuckDuckGo results."""
    try:
        time.sleep(1.0)  # polite delay to avoid hammering the endpoint
        query = f"{company_name} official site"
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None, 0.0

        soup = BeautifulSoup(resp.content, "html.parser")
        link = soup.select_one("a.result__a")
        if not link:
            return None, 0.0

        href = link.get("href")
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            if "uddg" in qs:
                href = unquote(qs["uddg"][0])

        if "linkedin.com" in href or "crunchbase.com" in href:
            return None, 0.0

        return normalize_domain(href), 0.85
    except Exception:
        return None, 0.0


def resolve_via_guessing(company_name: str) -> tuple[str | None, float]:
    """Fallback: try common TLDs with a slugged company name."""
    slug = company_name.lower().replace(" ", "").replace(".", "").replace(",", "")
    tlds = [".com", ".io", ".ai", ".co"]

    for tld in tlds:
        candidate = f"https://{slug}{tld}"
        try:
            resp = requests.head(
                candidate,
                headers=HEADERS,
                timeout=3,
                allow_redirects=True,
            )
            if resp.status_code < 400:
                return normalize_domain(resp.url), 0.60
        except Exception:
            continue

    return None, 0.0


def resolve_company_domain(company_name: str) -> dict[str, str | float | None]:
    """Resolve the most likely domain for a company."""
    domain, conf = resolve_via_duckduckgo(company_name)
    if domain:
        return {"domain": domain, "confidence": conf, "source": "search"}

    print(f"⚠️ Search failed for '{company_name}', attempting active guessing...")
    domain, conf = resolve_via_guessing(company_name)
    if domain:
        return {"domain": domain, "confidence": conf, "source": "guess"}

    return {"domain": None, "confidence": 0.0, "source": "failed"}
