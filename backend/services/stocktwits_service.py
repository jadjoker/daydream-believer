import httpx
from typing import Optional, Dict, List
import asyncio

BASE = "https://api.stocktwits.com/api/2"


async def _get(path: str, params: dict = {}) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BASE}{path}", params=params)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"[Stocktwits] error {path}: {e}")
    return None


async def get_ticker_sentiment(ticker: str) -> Optional[Dict]:
    data = await _get(f"/streams/symbol/{ticker}.json", {"limit": 30})
    if not data:
        return None

    symbol_data = data.get("symbol", {})
    messages = data.get("messages", [])

    bullish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish")
    bearish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish")
    total = len(messages)
    neutral = total - bullish - bearish

    bull_ratio = bullish / total if total > 0 else 0
    bear_ratio = bearish / total if total > 0 else 0
    score = bull_ratio - bear_ratio

    label = "Bullish" if score > 0.1 else ("Bearish" if score < -0.1 else "Neutral")

    top_posts = []
    for m in messages[:5]:
        top_posts.append({
            "text": m.get("body", ""),
            "user": m.get("user", {}).get("username", ""),
            "likes": m.get("likes", {}).get("total", 0),
            "sentiment": m.get("entities", {}).get("sentiment", {}).get("basic", ""),
            "created_at": m.get("created_at", ""),
        })

    return {
        "source": "Stocktwits",
        "score": round(score, 3),
        "label": label,
        "mention_count": symbol_data.get("messages_count", total),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "details": {
            "neutral_count": neutral,
            "watchlist_count": symbol_data.get("watchlist_count"),
        },
        "top_posts": top_posts,
    }


async def get_trending_tickers() -> List[str]:
    data = await _get("/trending/symbols.json")
    if not data:
        return []
    symbols = data.get("symbols", [])
    return [s["symbol"] for s in symbols[:20]]


async def get_trending_equities() -> List[Dict]:
    data = await _get("/trending/symbols/equities.json")
    if not data:
        return []
    return data.get("symbols", [])[:20]
