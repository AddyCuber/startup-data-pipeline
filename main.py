import os
import requests
from urllib.parse import urlparse

from app.ingest.rss_ingest import fetch_recent_articles
from app.extract.llm_parse import enrich_articles
from app.resolve.domain_resolver import resolve_company_domain
from app.hiring.detect_ats import detect_hiring_signal
from app.store.upsert import upsert_company, init_db, check_articles_exist
from app.publish.to_gsheet import save_to_sheet
from app.publish.telegram_alerts import send_telegram_alert  # <-- ADDED

ENABLE_LINKEDIN_FALLBACK = os.getenv("ENABLE_LINKEDIN_FALLBACK", "false").lower() in {"1", "true", "yes"}
if ENABLE_LINKEDIN_FALLBACK:
    from app.resolve.find_linkedin import find_best_linkedin_url
else:
    def find_best_linkedin_url(*_args, **_kwargs):
        return None

def validate_url(url: str) -> bool:
    """Returns True only if the website is reachable (status < 400)."""
    if not url:
        return False
    try:
        resp = requests.head(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
            allow_redirects=True,
        )
        return resp.status_code < 400
    except requests.RequestException:
        return False


def run_pipeline():
    """Orchestrates all steps: Ingest, Enrich, Resolve, Detect, Store, and Publish."""

    # --- STEP 0: Ensure DB exists before anything else ---
    init_db()

    print("\n=== STEP 1: Fetch Recent Funding Articles ===")
    all_articles = fetch_recent_articles(days_back=7)
    print(f"→ Found {len(all_articles)} funding-related articles (pre-filter).\n")
    if not all_articles:
        print("✅ No new articles found. Pipeline complete.")
        return []

    # --- PRE-FLIGHT DUPLICATE FILTER ---
    print("--- PRE-FLIGHT CHECK: Filtering already-processed articles ---")
    article_urls = [a.get("url") for a in all_articles if a.get("url")]
    existing_urls = check_articles_exist(article_urls)
    new_articles = [a for a in all_articles if a.get("url") not in existing_urls]
    print(f"→ {len(new_articles)} new articles to process.")
    print(f"→ Skipped {len(existing_urls)} articles already stored.\n")
    if not new_articles:
        print("✅ No unseen articles. Pipeline complete.")
        return []

    # Safety limit: process at most 20 new articles per run
    articles = new_articles[:20]
    if len(new_articles) > len(articles):
        print(f"⚠️ Truncating to {len(articles)} newest items due to safety limit.\n")

    print("\n=== STEP 2: Enrich Using LLM ===")
    enriched = enrich_articles(articles)
    print(f"\n→ Enriched {len(enriched)} with structured fields.\n")
    if not enriched:
        print("✅ No articles could be enriched. Pipeline complete.")
        return []

    print("\n=== STEP 3: Resolve Company Websites (LLM URL First, Fallback Otherwise) ===")
    resolved = []
    for item in enriched:
        company = item.get("company_name")
        if not company:
            print("⚠️ Skipping item with no company name.")
            continue

        llm_url = item.get("website_url")
        if llm_url and validate_url(llm_url):
            resolved_entry = {
                "domain": llm_url, "confidence": 0.98, "source": "llm_explicit",
            }
        else:
            # Pass original article URL for better DDG context if needed
            resolved_entry = resolve_company_domain(company, item.get("url"))

        merged = {**item, **resolved_entry}

        if ENABLE_LINKEDIN_FALLBACK and not merged.get("linkedin_url"):
            domain_hint = merged.get("domain")
            domain_host = urlparse(domain_hint).netloc if domain_hint else None
            guessed_linkedin = find_best_linkedin_url(company, domain_host)
            if guessed_linkedin:
                merged["linkedin_url"] = guessed_linkedin
        resolved.append(merged)

        print(
            f"{company:<28} | "
            f"${merged.get('amount_raised_usd')} | "
            f"{merged.get('funding_round')} | "
            f"{merged.get('domain')}  "
            f"(conf={merged.get('confidence'):.2f}, src={merged.get('source')})"
        )

    print("\n=== STEP 4 & 5: Hiring Signal, Storage, and Alerts ===")
    final_output = []
    for item in resolved:
        hiring = detect_hiring_signal(item.get("domain"))
        merged = {**item, **hiring}
        final_output.append(merged)

        print(
            f"{merged['company_name']:<28} | "
            f"Hiring Tier: {merged.get('hiring_tier')} | "
            f"{merged.get('details')}"
        )
        
        # --- STEP 5: Store in DB ---
        upsert_company(merged)

        # --- REAL-TIME TELEGRAM ALERT ---
        tier = merged.get("hiring_tier")
        if tier in {"A", "B"}:
            print(
                f"    🔔 Tier {tier} lead found! Sending Telegram alert for {merged['company_name']}"
            )
            send_telegram_alert(merged) # <-- ADDED

    print(f"\n✅ Pipeline completed. Total companies processed & stored: {len(final_output)}\n")

    print("\n=== STEP 6: Publishing to Google Sheets ===")
    save_to_sheet(final_output)

    return final_output


if __name__ == "__main__":
    run_pipeline()