import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import time
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ---- BLOCKLIST: avoid parked domains / for-sale landing pages ----
DOMAIN_BLOCKLIST = [
    "domains.atom.com", "sedo.com", "godaddy.com", "namecheap.com",
    "dan.com", "hugedomains.com", "afternic.com", "wix.com",
    "squarespace.com", "uniregistry.com", "brandpa.com"
]

SOCIAL_DOMAINS = [
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "threads.net",
    "whatsapp.com",
    "api.whatsapp.com",
]

# Remove legal suffixes
LEGAL_SUFFIXES = re.compile(r'\b(inc|corp|co|llc|ltd|gmbh|ag|sas|bv)\b\.?$', re.I)

# Detect names that already contain a TLD, e.g. "IndustrialMind.ai"
TLD_MATCH = re.compile(r'([a-z0-9\-]+)\.([a-z]{2,})$', re.I)


def create_slug_and_tld(company_name: str):
    """Extract slug and detect TLD embedded in the company name."""
    name = company_name.strip()
    name = LEGAL_SUFFIXES.sub("", name).strip()

    t = TLD_MATCH.search(name)
    if t:
        return t.group(1).lower(), f".{t.group(2).lower()}"  # ("industrialmind", ".ai")

    return name.lower().replace(" ", "").replace(".", "").replace(",", ""), None


def normalize_domain(url: str):
    if not url:
        return None
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"

    parsed = urlparse(url)
    base = parsed.netloc.lower().replace("www.", "")
    if any(b in base for b in DOMAIN_BLOCKLIST):
        return None

    return f"https://{base}"


def resolve_from_press_release(article_url: str):
    """Attempt to extract a company website link directly from the source article."""
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=10)
        if resp.status_code >= 400:
            return None, 0.0

        soup = BeautifulSoup(resp.text, "html.parser")
        article_host = urlparse(article_url).netloc.lower().replace("www.", "")

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href.startswith("http"):
                continue
            if any(block in href for block in DOMAIN_BLOCKLIST):
                continue
            if any(social in href for social in SOCIAL_DOMAINS):
                continue

            clean = normalize_domain(href)
            if not clean:
                continue

            candidate_host = urlparse(clean).netloc.lower().replace("www.", "")
            if candidate_host == article_host:
                continue

            if any(social in candidate_host for social in SOCIAL_DOMAINS):
                continue

            if any(block in candidate_host for block in DOMAIN_BLOCKLIST):
                continue

            if "mailto:" in href:
                continue

            if clean:
                return clean, 0.92
    except Exception:
        pass

    return None, 0.0


def resolve_via_duckduckgo(company_name: str):
    try:
        time.sleep(1.0)  # polite delay
        query = f"{company_name} official site"
        resp = requests.get(f"https://duckduckgo.com/html/?q={quote_plus(query)}",
                            headers=HEADERS, timeout=10)

        soup = BeautifulSoup(resp.text, 'html.parser')
        link = soup.select_one("a.result__a")
        if not link:
            return None, 0.0

        href = link.get("href")

        # Handle DDG redirect format
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            href = unquote(qs.get("uddg", [href])[0])

        if any(block in href for block in ["linkedin.com", "crunchbase.com"]):
            return None, 0.0

        return normalize_domain(href), 0.85

    except:
        return None, 0.0


def resolve_via_guessing(company_name: str):
    slug, tld = create_slug_and_tld(company_name)

    tlds = [tld] if tld else [".com", ".io", ".ai", ".co"]

    for ext in tlds:
        candidate = f"https://{slug}{ext}"
        try:
            resp = requests.head(candidate, headers=HEADERS, timeout=4, allow_redirects=True)
            final = resp.url.lower()
            if resp.status_code < 400 and not any(b in final for b in DOMAIN_BLOCKLIST):
                return normalize_domain(final), 0.60
        except:
            continue

    return None, 0.0


def resolve_company_domain(company_name: str, article_url: str):
    domain, conf = resolve_from_press_release(article_url)
    if domain:
        return {"domain": domain, "confidence": conf, "source": "press_release"}

    domain, conf = resolve_via_duckduckgo(company_name)
    if domain:
        return {"domain": domain, "confidence": conf, "source": "search"}

    print(f"⚠️ Search failed for '{company_name}', attempting active guessing...")
    domain, conf = resolve_via_guessing(company_name)
    if domain:
        return {"domain": domain, "confidence": conf, "source": "guess"}

    return {"domain": None, "confidence": 0.0, "source": "failed"}