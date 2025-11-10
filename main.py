import requests
from app.ingest.rss_ingest import fetch_recent_articles
from app.extract.llm_parse import enrich_articles
from app.resolve.domain_resolver import resolve_company_domain
from app.hiring.detect_ats import detect_hiring_signal
from app.store.upsert import upsert_company, init_db
from app.publish.to_gsheet import save_to_sheet


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
    """Orchestrates article ingest, enrichment, domain resolution, hiring signals, storage, and publishing."""

    # --- STEP 0: Ensure DB exists before anything else ---
    init_db()

    print("\n=== STEP 1: Fetch Recent Funding Articles ===")
    # Limit to 20 items to keep the run affordable; extend days_back as needed for production
    articles = fetch_recent_articles(days_back=7)[:20]
    print(f"→ Found {len(articles)} funding-related articles (processing max 20).\n")
    if not articles:
        print("✅ No new articles found. Pipeline complete.")
        return []

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
                "domain": llm_url,
                "confidence": 0.98,
                "source": "llm_explicit",
            }
        else:
            resolved_entry = resolve_company_domain(company, item.get("url"))

        merged = {**item, **resolved_entry}
        resolved.append(merged)

        print(
            f"{company:<28} | "
            f"${merged.get('amount_raised_usd')} | "
            f"{merged.get('funding_round')} | "
            f"{merged.get('domain')}  "
            f"(conf={merged.get('confidence'):.2f}, src={merged.get('source')})"
        )

    print("\n=== STEP 4 & 5: Hiring Signal and Storage ===")
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

        upsert_company(merged)

    print(f"\n✅ Pipeline completed. Total companies processed & stored: {len(final_output)}\n")

    print("\n=== STEP 6: Publishing to Google Sheets ===")
    save_to_sheet(final_output)

    return final_output


if __name__ == "__main__":
    run_pipeline()