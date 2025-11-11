import re
from datetime import datetime, timedelta, timezone

import feedparser

FEEDS = [
    "https://techcrunch.com/category/startups/funding/feed/",
    "https://venturebeat.com/category/venture-capital/feed/",
    "https://www.finsmes.com/feed",
    "https://inc42.com/buzz/funding/feed/",
    "https://entrackr.com/category/funding/feed/",
    "https://yourstory.com/feed/category/funding",
]

STRONG_KEYWORDS = {
    "raises",
    "secures",
    "bags",
    "closes round",
    "lands",
    "nabs",
    "funding",
    "invests",
}

CONTEXT_KEYWORDS = {
    "series a",
    "series b",
    "series c",
    "series d",
    "series e",
    "seed",
    "pre-seed",
    "angel",
    "valuation",
    "venture capital",
    "equity",
}

MONEY_INDICATORS = {"$", "million", "mn", "cr", "crore", "billion", "bn"}


def fetch_recent_articles(days_back: int = 3):
    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    for feed_url in FEEDS:
        parsed = feedparser.parse(feed_url)

        for entry in parsed.entries:
            title = entry.title.strip()
            title_lower = re.sub(r"[-–—]", " ", title).lower()

            is_strong = any(kw in title_lower for kw in STRONG_KEYWORDS)
            is_context = any(kw in title_lower for kw in CONTEXT_KEYWORDS)
            has_money = any(ind in title_lower for ind in MONEY_INDICATORS)

            if not (is_strong or (is_context and has_money)):
                continue

            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if published < cutoff:
                    continue
                published_at = published.isoformat()
                date_confidence = 1.0
            else:
                published_at = None
                date_confidence = 0.5

            articles.append(
                {
                    "title": title,
                    "url": entry.link,
                    "published_at": published_at,
                    "date_confidence": date_confidence,
                    "source": feed_url,
                }
            )

    return articles
