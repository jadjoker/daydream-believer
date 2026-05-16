import os
import asyncio
import httpx
import feedparser
from typing import List, Dict, Optional
from datetime import datetime, timezone
import re

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "Benzinga": "https://www.benzinga.com/feed",
    "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
    "Yahoo Finance": "https://finance.yahoo.com/rss/",
    "Motley Fool": "https://www.fool.com/feeds/index.aspx",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "TheStreet": "https://www.thestreet.com/rss/feeds/TheStreet.com%20-%20All%20News.xml",
}

POSITIVE_KEYWORDS = {
    "surge", "soar", "rally", "gain", "rise", "jump", "spike", "beat",
    "exceed", "growth", "profit", "upgrade", "buy", "bullish", "strong",
    "positive", "record", "high", "boost", "outperform", "breakout",
}

NEGATIVE_KEYWORDS = {
    "crash", "drop", "fall", "decline", "loss", "miss", "downgrade",
    "sell", "bearish", "weak", "negative", "low", "cut", "warning",
    "lawsuit", "investigation", "fraud", "recall", "bankruptcy",
}


def _sentiment_from_text(text: str) -> str:
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    pos = len(words & POSITIVE_KEYWORDS)
    neg = len(words & NEGATIVE_KEYWORDS)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def _extract_tickers(text: str) -> List[str]:
    pattern = re.compile(r'\$([A-Z]{1,5})\b|(?<!\w)NYSE:([A-Z]{1,5})\b|(?<!\w)NASDAQ:([A-Z]{1,5})\b')
    matches = pattern.findall(text)
    tickers = []
    for m in matches:
        t = m[0] or m[1] or m[2]
        if t:
            tickers.append(t)
    return list(set(tickers))


async def _fetch_rss(source_name: str, url: str) -> List[Dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return []
            feed = feedparser.parse(r.text)
            articles = []
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                full_text = f"{title} {summary}"
                articles.append({
                    "title": title,
                    "source": source_name,
                    "url": entry.get("link", ""),
                    "published_at": _parse_date(entry),
                    "summary": summary[:500] if summary else "",
                    "sentiment": _sentiment_from_text(full_text),
                    "tickers": _extract_tickers(full_text),
                    "category": "general",
                })
            return articles
    except Exception as e:
        print(f"[RSS] {source_name} error: {e}")
        return []


def _parse_date(entry) -> str:
    try:
        import time
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.now(tz=timezone.utc).isoformat()


async def get_general_news(max_per_source: int = 8) -> List[Dict]:
    tasks = [_fetch_rss(name, url) for name, url in RSS_FEEDS.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_articles = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r[:max_per_source])
    all_articles.sort(key=lambda x: x["published_at"], reverse=True)
    return all_articles[:80]


async def get_ticker_news(ticker: str) -> List[Dict]:
    all_articles = await get_general_news()
    ticker_articles = []
    for a in all_articles:
        if (
            ticker.upper() in a["tickers"]
            or ticker.upper() in a["title"].upper()
            or f"${ticker.upper()}" in a["title"]
        ):
            a_copy = dict(a)
            if ticker.upper() not in a_copy["tickers"]:
                a_copy["tickers"] = [ticker.upper()] + a_copy["tickers"]
            ticker_articles.append(a_copy)
    return ticker_articles[:20]


async def get_newsapi_news(query: str = "stock market") -> List[Dict]:
    if not NEWS_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "sortBy": "publishedAt",
                    "pageSize": 20,
                    "language": "en",
                    "apiKey": NEWS_API_KEY,
                },
            )
            data = r.json()
            articles = []
            for a in data.get("articles", []):
                title = a.get("title", "") or ""
                desc = a.get("description", "") or ""
                full = f"{title} {desc}"
                articles.append({
                    "title": title,
                    "source": a.get("source", {}).get("name", "NewsAPI"),
                    "url": a.get("url", ""),
                    "published_at": a.get("publishedAt", ""),
                    "summary": desc[:500],
                    "sentiment": _sentiment_from_text(full),
                    "tickers": _extract_tickers(full),
                    "category": "newsapi",
                })
            return articles
    except Exception as e:
        print(f"[NewsAPI] error: {e}")
        return []


async def get_news_sentiment_for_ticker(ticker: str) -> Optional[Dict]:
    articles = await get_ticker_news(ticker)
    if not articles:
        return None
    positive = sum(1 for a in articles if a["sentiment"] == "positive")
    negative = sum(1 for a in articles if a["sentiment"] == "negative")
    neutral = len(articles) - positive - negative
    total = len(articles)
    score = (positive - negative) / total if total > 0 else 0
    label = "Bullish" if score > 0.1 else ("Bearish" if score < -0.1 else "Neutral")
    return {
        "source": "News",
        "score": round(score, 3),
        "label": label,
        "mention_count": total,
        "bullish_count": positive,
        "bearish_count": negative,
        "details": {"neutral_count": neutral, "sources": list({a["source"] for a in articles})},
        "top_posts": [{"title": a["title"], "source": a["source"], "url": a["url"], "sentiment": a["sentiment"]} for a in articles[:5]],
    }
