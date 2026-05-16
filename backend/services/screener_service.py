import asyncio
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from .technical_analysis import analyze
from . import finnhub_service

_executor = ThreadPoolExecutor(max_workers=3)

# Curated universe — liquid, actively traded day-trade names, no dead tickers
SCAN_UNIVERSE = [
    # Mega cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    # Finance
    "JPM", "BAC", "GS", "V", "MA",
    # Healthcare
    "LLY", "UNH", "PFE",
    # Energy
    "XOM", "CVX",
    # Consumer
    "WMT", "COST", "NKE",
    # ETFs / leveraged
    "SPY", "QQQ", "IWM", "TQQQ", "SQQQ", "ARKK",
    # Semis
    "QCOM", "MU", "TSM",
    # High vol / meme
    "GME", "RIVN", "NIO",
    # Biotech
    "GILD", "VRTX",
]

_screener_cache: Dict = {"ts": 0.0, "data": []}
_CACHE_TTL = 7200  # 2 hours — avoids re-hammering Yahoo Finance on every request


def _fetch_ta_sync(ticker: str) -> Dict:
    """Fetch TA only via yfinance history — no .info or .fast_info calls."""
    ta = analyze(ticker, period="3mo", interval="1d")
    return {"ticker": ticker, "ta": ta}


async def _run_screener_fresh(universe: List[str]) -> List[Dict]:
    # Step 1: quotes via Finnhub — async, concurrent, zero Yahoo Finance calls
    quotes = await asyncio.gather(
        *[finnhub_service.get_quote(t) for t in universe],
        return_exceptions=True,
    )
    quote_map = {
        t: q for t, q in zip(universe, quotes)
        if isinstance(q, dict) and q.get("price")
    }

    # Step 2: TA in batches of 3 with 1s gaps to stay under Yahoo Finance rate limit
    loop = asyncio.get_running_loop()
    ta_map: Dict[str, Optional[Dict]] = {}
    tickers = list(quote_map.keys())
    for i in range(0, len(tickers), 3):
        batch = tickers[i:i + 3]
        futures = [loop.run_in_executor(_executor, _fetch_ta_sync, t) for t in batch]
        batch_results = await asyncio.gather(*futures, return_exceptions=True)
        for r in batch_results:
            if isinstance(r, dict):
                ta_map[r["ticker"]] = r["ta"]
        if i + 3 < len(tickers):
            await asyncio.sleep(1.0)

    # Step 3: merge quotes + TA
    out = []
    for ticker in universe:
        q = quote_map.get(ticker)
        if not q:
            continue
        ta = ta_map.get(ticker)
        rsi = ta.get("rsi_14") if ta else None
        rel_vol = ta.get("rel_volume", 1.0) if ta else 1.0
        signals = (ta.get("bull_signals", []) + ta.get("bear_signals", [])) if ta else []
        chg_pct = q.get("change_pct", 0)
        score = _compute_score(chg_pct, rel_vol, rsi, ta)
        out.append({
            "ticker": ticker,
            "name": q.get("name") or ticker,
            "price": q.get("price", 0),
            "change_pct": chg_pct,
            "volume": q.get("volume", 0),
            "rel_volume": rel_vol,
            "market_cap": q.get("market_cap"),
            "rsi": rsi,
            "short_float": q.get("short_float"),
            "sector": q.get("sector"),
            "score": score,
            "signals": signals[:4],
        })
    return out


def _compute_score(chg_pct: float, rel_vol: float, rsi: Optional[float], ta: Optional[Dict]) -> float:
    score = 0.0
    if rel_vol > 3:
        score += 3
    elif rel_vol > 2:
        score += 2
    elif rel_vol > 1.5:
        score += 1

    if chg_pct > 5:
        score += 3
    elif chg_pct > 2:
        score += 2
    elif chg_pct > 0:
        score += 1
    elif chg_pct < -5:
        score -= 2

    if rsi:
        if 40 <= rsi <= 60:
            score += 1
        elif rsi < 30:
            score += 2
        elif rsi > 75:
            score -= 1

    if ta:
        bull = len(ta.get("bull_signals", []))
        bear = len(ta.get("bear_signals", []))
        score += (bull - bear) * 0.5

    return round(score, 2)


async def run_screener(
    min_price: float = 1.0,
    max_price: float = 10000.0,
    min_rel_volume: float = 1.0,
    min_change_pct: float = -50.0,
    max_change_pct: float = 50.0,
    sector: Optional[str] = None,
    sort_by: str = "score",
    limit: int = 25,
    custom_tickers: Optional[List[str]] = None,
) -> List[Dict]:
    universe = custom_tickers or SCAN_UNIVERSE
    now = time.time()

    if not custom_tickers and _screener_cache["ts"] and (now - _screener_cache["ts"]) < _CACHE_TTL:
        raw = _screener_cache["data"]
    else:
        raw = await _run_screener_fresh(universe)
        if not custom_tickers:
            _screener_cache["ts"] = now
            _screener_cache["data"] = raw

    filtered = [
        r for r in raw
        if min_price <= r["price"] <= max_price
        and r["rel_volume"] >= min_rel_volume
        and min_change_pct <= r["change_pct"] <= max_change_pct
        and (not sector or r.get("sector", "").lower() == sector.lower())
    ]
    filtered.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return filtered[:limit]
