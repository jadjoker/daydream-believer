import os
import asyncio
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import re

_executor = ThreadPoolExecutor(max_workers=2)
_reddit = None


def _get_reddit():
    global _reddit
    if _reddit is not None:
        return _reddit
    try:
        import praw
        client_id = os.getenv("REDDIT_CLIENT_ID", "")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        user_agent = os.getenv("REDDIT_USER_AGENT", "DaydreamBeliever/1.0")
        if not client_id or not client_secret:
            return None
        _reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            read_only=True,
        )
        return _reddit
    except Exception as e:
        print(f"[Reddit] init error: {e}")
        return None


SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "options",
    "SecurityAnalysis",
    "pennystocks",
    "Daytrading",
    "StockMarket",
    "ValueInvesting",
]

POSITIVE_WORDS = {
    "bull", "bullish", "moon", "rocket", "buy", "long", "calls", "squeeze",
    "breakout", "rally", "pump", "gain", "profit", "win", "yolo", "tendies",
    "strong", "growth", "undervalued", "buy the dip", "support", "bounce",
}

NEGATIVE_WORDS = {
    "bear", "bearish", "puts", "short", "crash", "dump", "fall", "drop",
    "sell", "loss", "tank", "overvalued", "bubble", "baghold", "rekt",
    "resist", "breakdown", "weak", "decline",
}


def _score_text(text: str) -> float:
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    bull = len(words & POSITIVE_WORDS)
    bear = len(words & NEGATIVE_WORDS)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def _fetch_ticker_mentions(ticker: str, subreddit_name: str, limit: int = 100) -> List[Dict]:
    reddit = _get_reddit()
    if not reddit:
        return []
    try:
        sub = reddit.subreddit(subreddit_name)
        posts = []
        patterns = [
            rf'\b{re.escape(ticker)}\b',
            rf'\${re.escape(ticker)}\b',
        ]
        for submission in sub.hot(limit=limit):
            text = f"{submission.title} {submission.selftext}"
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                score = _score_text(text)
                posts.append({
                    "subreddit": subreddit_name,
                    "title": submission.title,
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "url": f"https://reddit.com{submission.permalink}",
                    "created_utc": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
                    "sentiment_score": score,
                    "upvote_ratio": submission.upvote_ratio,
                })
        return posts
    except Exception as e:
        print(f"[Reddit] {subreddit_name} error: {e}")
        return []


def _fetch_trending(subreddit_name: str = "wallstreetbets", limit: int = 50) -> List[Dict]:
    reddit = _get_reddit()
    if not reddit:
        return []
    try:
        sub = reddit.subreddit(subreddit_name)
        ticker_pattern = re.compile(r'\$([A-Z]{1,5})\b|(?<!\w)([A-Z]{2,5})(?!\w)(?=\s|,|\.|\!)')
        ticker_counts = {}
        for submission in sub.hot(limit=limit):
            text = f"{submission.title} {submission.selftext}"
            matches = ticker_pattern.findall(text)
            for m in matches:
                t = (m[0] or m[1]).strip()
                if len(t) >= 2 and t not in {"US", "CEO", "IPO", "EPS", "GDP", "ATH", "DD", "OTC", "ETF", "SEC", "WSB", "AI", "OP", "THE", "FOR", "NOT", "AND", "BUT"}:
                    ticker_counts[t] = ticker_counts.get(t, 0) + submission.score + 1
        return sorted(
            [{"ticker": k, "mention_score": v} for k, v in ticker_counts.items()],
            key=lambda x: x["mention_score"],
            reverse=True,
        )[:20]
    except Exception as e:
        print(f"[Reddit] trending error: {e}")
        return []


async def get_ticker_sentiment(ticker: str) -> Optional[Dict]:
    loop = asyncio.get_event_loop()
    all_posts = []

    async def fetch_sub(sub):
        posts = await loop.run_in_executor(_executor, _fetch_ticker_mentions, ticker, sub, 100)
        all_posts.extend(posts)

    await asyncio.gather(*[fetch_sub(s) for s in SUBREDDITS[:4]])

    if not all_posts:
        return None

    total = len(all_posts)
    scores = [p["sentiment_score"] for p in all_posts]
    avg_score = sum(scores) / len(scores) if scores else 0
    bullish_count = sum(1 for s in scores if s > 0)
    bearish_count = sum(1 for s in scores if s < 0)

    label = "Bullish" if avg_score > 0.1 else ("Bearish" if avg_score < -0.1 else "Neutral")

    top_posts = sorted(all_posts, key=lambda x: x["score"], reverse=True)[:5]

    return {
        "source": "Reddit",
        "score": round(avg_score, 3),
        "label": label,
        "mention_count": total,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "details": {"posts_by_subreddit": {s: sum(1 for p in all_posts if p["subreddit"] == s) for s in SUBREDDITS}},
        "top_posts": top_posts,
    }


async def get_trending_tickers() -> List[str]:
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_executor, _fetch_trending, "wallstreetbets", 50)
    return [r["ticker"] for r in results[:15]]
