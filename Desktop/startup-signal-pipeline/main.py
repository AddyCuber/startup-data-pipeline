from app.ingest.rss_ingest import fetch_recent_articles

def main():
    articles = fetch_recent_articles(days_back=3)

    print(f"Fetched {len(articles)} recent funding-related articles.\n")
    
    for a in articles[:10]:
        print(a)

if __name__ == "__main__":
    main()