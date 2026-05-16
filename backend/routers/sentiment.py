from fastapi import APIRouter, HTTPException
from services import reddit_service, stocktwits_service, news_aggregator
from services.cache_service import cache

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/{ticker}")
@cache(ttl=300, key_prefix="sentiment")
async def get_sentiment(ticker: str):
    ticker = ticker.upper()
    reddit, stocktwits, news_sent = await _gather_sentiment(ticker)

    scores = []
    weights = []
    if reddit:
        scores.append(reddit["score"])
        weights.append(reddit["mention_count"])
    if stocktwits:
        scores.append(stocktwits["score"])
        weights.append(stocktwits["mention_count"] or 1)
    if news_sent:
        scores.append(news_sent["score"])
        weights.append(news_sent["mention_count"] or 1)

    if scores:
        total_weight = sum(weights)
        composite = sum(s * w for s, w in zip(scores, weights)) / total_weight if total_weight else 0
    else:
        composite = 0.0

    label = "Bullish" if composite > 0.1 else ("Bearish" if composite < -0.1 else "Neutral")

    all_posts = []
    for src in [reddit, stocktwits, news_sent]:
        if src and "top_posts" in src:
            all_posts.extend(src["top_posts"][:3])

    return {
        "ticker": ticker,
        "composite_score": round(composite, 3),
        "composite_label": label,
        "reddit": reddit,
        "stocktwits": stocktwits,
        "news": news_sent,
        "trend_direction": label,
        "top_posts": all_posts[:10],
    }


async def _gather_sentiment(ticker: str):
    import asyncio
    results = await asyncio.gather(
        reddit_service.get_ticker_sentiment(ticker),
        stocktwits_service.get_ticker_sentiment(ticker),
        news_aggregator.get_news_sentiment_for_ticker(ticker),
        return_exceptions=True,
    )
    return [r if not isinstance(r, Exception) else None for r in results]


@router.get("/trending/reddit")
@cache(ttl=600, key_prefix="trending_reddit")
async def get_reddit_trending():
    tickers = await reddit_service.get_trending_tickers()
    return {"source": "reddit/wallstreetbets", "trending": tickers}


@router.get("/trending/stocktwits")
@cache(ttl=300, key_prefix="trending_stocktwits")
async def get_stocktwits_trending():
    tickers = await stocktwits_service.get_trending_tickers()
    equities = await stocktwits_service.get_trending_equities()
    return {"tickers": tickers, "equities": equities}
