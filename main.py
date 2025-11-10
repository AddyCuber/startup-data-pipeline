from app.extract.llm_parse import enrich_articles
from app.ingest.rss_ingest import fetch_recent_articles
from app.resolve.domain_resolver import resolve_company_domain


def format_row(company: str, amount: int | None, round_name: str | None, country: str | None, domain_info: dict) -> str:
    amount_str = f"${amount}" if amount is not None else "N/A"
    round_str = round_name or "N/A"
    country_str = country or "N/A"

    domain = domain_info.get("domain") or "N/A"
    confidence = domain_info.get("confidence")
    conf_str = f" (conf={confidence:.2f})" if confidence else ""

    return (
        f"{company:<28} | {amount_str:<9} | "
        f"{round_str:<9} | {country_str:<13} | {domain}{conf_str}"
    )


def main(days_back: int = 3, max_preview: int = 10) -> None:
    articles = fetch_recent_articles(days_back=days_back)
    print(f"Fetched {len(articles)} recent funding-related articles.\n")

    enriched = enrich_articles(articles)
    print(f"\nEnriched {len(enriched)} articles.\n")

    rows = []
    for article in enriched[:max_preview]:
        company = article.get("company_name", "Unknown")
        amount = article.get("amount_raised_usd")
        round_name = article.get("funding_round")
        country = article.get("headquarter_country")

        domain_info = resolve_company_domain(company)
        rows.append(format_row(company, amount, round_name, country, domain_info))

    print("\n".join(rows))


if __name__ == "__main__":
    main()
