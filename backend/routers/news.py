from fastapi import APIRouter, Query
from typing import Optional
from services import news_aggregator, finnhub_service as fh
from services.cache_service import cache

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/general")
@cache(ttl=300, key_prefix="news_general")
async def get_general_news():
    rss_news = await news_aggregator.get_general_news()
    fh_news = await fh.get_general_news()
    combined = rss_news + fh_news
    combined.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return {"articles": combined[:60]}


@router.get("/ticker/{ticker}")
@cache(ttl=180, key_prefix="news_ticker")
async def get_ticker_news(ticker: str):
    ticker = ticker.upper()
    rss = await news_aggregator.get_ticker_news(ticker)
    fh_news = await fh.get_company_news(ticker, days_back=7)
    combined = rss + fh_news
    seen = set()
    deduped = []
    for a in combined:
        key = a.get("title", "")[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(a)
    deduped.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return {"ticker": ticker, "articles": deduped[:30]}


@router.get("/market-sentiment/{ticker}")
@cache(ttl=300, key_prefix="news_mkt_sentiment")
async def get_market_news_sentiment(ticker: str):
    data = await fh.get_market_news_sentiment(ticker.upper())
    return data or {}
