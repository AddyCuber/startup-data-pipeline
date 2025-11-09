from app.extract.llm_parse import enrich_articles
from app.ingest.rss_ingest import fetch_recent_articles


def main(days_back: int = 3, max_preview: int = 10) -> None:
    articles = fetch_recent_articles(days_back=days_back)
    print(f"Fetched {len(articles)} recent funding-related articles.\n")

    enriched = enrich_articles(articles)
    print(f"\nEnriched {len(enriched)} articles.\n")

    for article in enriched[:max_preview]:
        company = article.get("company_name", "Unknown")
        amount = article.get("amount_raised_usd")
        round_name = article.get("funding_round")
        headline = f"{company} — ${amount} ({round_name})"

        print(f"✅ {headline}\n")
        print(article)
        print("-" * 80)


if __name__ == "__main__":
    main()
