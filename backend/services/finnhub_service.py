import os
import httpx
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import asyncio

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
BASE = "https://finnhub.io/api/v1"


async def _get(path: str, params: dict = {}) -> Optional[dict]:
    if not FINNHUB_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BASE}{path}", params={"token": FINNHUB_KEY, **params})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[Finnhub] error {path}: {e}")
        return None


async def get_company_news(ticker: str, days_back: int = 7) -> List[Dict]:
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    data = await _get("/company-news", {"symbol": ticker, "from": start, "to": end})
    if not data:
        return []
    articles = []
    for item in data[:30]:
        articles.append({
            "title": item.get("headline", ""),
            "source": item.get("source", "Finnhub"),
            "url": item.get("url", ""),
            "published_at": datetime.fromtimestamp(item.get("datetime", 0)).isoformat() if item.get("datetime") else "",
            "summary": item.get("summary", ""),
            "sentiment": None,
            "tickers": [ticker],
            "category": item.get("category", ""),
        })
    return articles


async def get_general_news(category: str = "general") -> List[Dict]:
    data = await _get("/news", {"category": category})
    if not data:
        return []
    articles = []
    for item in data[:30]:
        articles.append({
            "title": item.get("headline", ""),
            "source": item.get("source", "Finnhub"),
            "url": item.get("url", ""),
            "published_at": datetime.fromtimestamp(item.get("datetime", 0)).isoformat() if item.get("datetime") else "",
            "summary": item.get("summary", ""),
            "sentiment": None,
            "tickers": item.get("related", "").split(",") if item.get("related") else [],
            "category": item.get("category", ""),
        })
    return articles


async def get_earnings_calendar(weeks_ahead: int = 2) -> List[Dict]:
    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(weeks=weeks_ahead)).strftime("%Y-%m-%d")
    data = await _get("/calendar/earnings", {"from": start, "to": end})
    if not data:
        return []
    events = data.get("earningsCalendar", [])
    results = []
    for e in events[:100]:
        results.append({
            "ticker": e.get("symbol", ""),
            "company": e.get("symbol", ""),
            "report_date": e.get("date", ""),
            "time": e.get("hour", ""),
            "eps_estimate": e.get("epsEstimate"),
            "eps_actual": e.get("epsActual"),
            "revenue_estimate": e.get("revenueEstimate"),
            "revenue_actual": e.get("revenueActual"),
            "surprise_pct": None,
        })
    return results


async def get_company_profile(ticker: str) -> Optional[Dict]:
    return await _get("/stock/profile2", {"symbol": ticker})


async def get_recommendation_trends(ticker: str) -> List[Dict]:
    data = await _get("/stock/recommendation", {"symbol": ticker})
    return data or []


async def get_insider_sentiment(ticker: str) -> Optional[Dict]:
    data = await _get("/stock/insider-sentiment", {"symbol": ticker, "from": "2024-01-01"})
    return data


async def get_price_target(ticker: str) -> Optional[Dict]:
    return await _get("/stock/price-target", {"symbol": ticker})


async def get_upgrade_downgrade(ticker: str) -> List[Dict]:
    data = await _get("/stock/upgrade-downgrade", {"symbol": ticker})
    return data or []


async def get_financials(ticker: str, statement: str = "ic", freq: str = "annual") -> Optional[Dict]:
    return await _get("/financials", {"symbol": ticker, "statement": statement, "freq": freq})


async def get_basic_financials(ticker: str) -> Optional[Dict]:
    return await _get("/stock/metric", {"symbol": ticker, "metric": "all"})


async def get_market_news_sentiment(ticker: str) -> Optional[Dict]:
    return await _get("/news-sentiment", {"symbol": ticker})
