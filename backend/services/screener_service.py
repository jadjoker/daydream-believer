import asyncio
import time
from typing import List, Dict, Optional
from . import finnhub_service

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
_CACHE_TTL = 7200  # 2 hours


async def _run_screener_fresh(universe: List[str]) -> List[Dict]:
    # Quotes via Finnhub only — batched to avoid rate-limit burst (max 10 concurrent)
    out = []
    batch_size = 10
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i + batch_size]
        results = await asyncio.gather(
            *[finnhub_service.get_quote(t) for t in batch],
            return_exceptions=True,
        )
        for ticker, q in zip(batch, results):
            if not isinstance(q, dict) or not q.get("price"):
                continue
            chg_pct = q.get("change_pct", 0) or 0
            score = _compute_score(chg_pct, 1.0, None, None)
            out.append({
                "ticker": ticker,
                "name": q.get("name") or ticker,
                "price": q.get("price", 0),
                "change_pct": chg_pct,
                "volume": q.get("volume", 0),
                "rel_volume": 1.0,
                "market_cap": q.get("market_cap"),
                "rsi": None,
                "short_float": None,
                "sector": q.get("sector"),
                "score": score,
                "signals": [],
                "_ta": None,
            })
        if i + batch_size < len(universe):
            await asyncio.sleep(0.3)  # brief gap between batches
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
    min_rel_volume: float = 0.0,  # no rel_vol filtering — Finnhub doesn't provide avg volume
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
        and r["change_pct"] >= min_change_pct
        and r["change_pct"] <= max_change_pct
        and (not sector or r.get("sector", "").lower() == sector.lower())
    ]
    filtered.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return filtered[:limit]
