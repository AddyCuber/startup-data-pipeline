import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from duckduckgo_search import DDGS


def normalize(text: str) -> str:
    """Lowercase string stripped of non-alphanumeric characters."""
    return re.sub(r"\W+", "", text or "").lower()


def score_candidate(company_name: str, domain: Optional[str], url: str, title: str) -> int:
    """
    Heuristic scoring to pick the most likely official LinkedIn company page.
    We favour linkedin.com/company/* URLs and penalise people/search pages.
    """
    score = 0
    normalized_name = normalize(company_name)
    url_lower = url.lower()
    title_lower = (title or "").lower()

    # Strong positive signals
    if "linkedin.com/company/" in url_lower:
        score += 50

    if company_name.lower() in title_lower:
        score += 30

    slug = urlparse(url_lower).path.replace("/", " ").replace("-", " ")
    if normalized_name and normalized_name in normalize(slug):
        score += 20

    if domain and normalize(domain) in url_lower:
        score += 10

    # Negative signals
    if "linkedin.com/in/" in url_lower:
        score -= 30

    if "/jobs/" in url_lower or "/job/" in url_lower:
        score -= 20

    if "redirector" in url_lower or "trk=" in url_lower or "/posts/" in url_lower:
        score -= 10

    return score


def find_linkedin_candidates(company_name: str, domain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Run multiple DuckDuckGo queries to gather LinkedIn candidate URLs."""
    if not company_name:
        return []

    queries = [
        f'"{company_name}" site:linkedin.com/company',
        f'"{company_name}" "{domain}" site:linkedin.com' if domain else None,
        f'{company_name} linkedin company',
    ]

    seen_urls: set[str] = set()
    candidates: List[Dict[str, Any]] = []

    with DDGS() as ddgs:
        for q in filter(None, queries):
            try:
                results = list(ddgs.text(q, max_results=5))
            except Exception as exc:
                print(f"    - DDG search error: {exc}")
                continue

            for result in results:
                url = result.get("href")
                if not url or "linkedin.com" not in url:
                    continue

                clean_url = url.split("?")[0].rstrip("/")
                if clean_url in seen_urls:
                    continue

                seen_urls.add(clean_url)
                candidate_score = score_candidate(company_name, domain, clean_url, result.get("title", ""))
                if candidate_score > 0:
                    candidates.append(
                        {"url": clean_url, "title": result.get("title", ""), "score": candidate_score}
                    )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def find_best_linkedin_url(company_name: str, domain: Optional[str] = None) -> Optional[str]:
    """Return the highest-scoring LinkedIn URL, or None if no good matches are found."""
    candidates = find_linkedin_candidates(company_name, domain)
    if not candidates:
        return None
    return candidates[0]["url"]


if __name__ == "__main__":
    companies_to_test = [
        {"name": "Stripe", "domain": "stripe.com"},
        {"name": "Fastbreak AI", "domain": "fastbreak.ai"},
        {"name": "Upward", "domain": "withupward.com"},
    ]

    for company in companies_to_test:
        print(f"\n--- Testing: {company['name']} ---")
        print(f"Best match: {find_best_linkedin_url(company['name'], company['domain'])}")

