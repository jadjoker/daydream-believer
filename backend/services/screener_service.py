import asyncio
from typing import List, Dict, Optional
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from .technical_analysis import analyze

_executor = ThreadPoolExecutor(max_workers=8)

# Common day-trade-worthy tickers to scan
SCAN_UNIVERSE = [
    # Mega cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD", "INTC",
    # Finance
    "JPM", "BAC", "GS", "MS", "C", "WFC", "V", "MA", "PYPL", "SQ",
    # Healthcare
    "JNJ", "PFE", "MRNA", "BNTX", "ABBV", "LLY", "UNH", "CVS",
    # Energy
    "XOM", "CVX", "COP", "SLB", "OXY",
    # Consumer
    "AMZN", "WMT", "TGT", "COST", "NKE", "MCD", "SBUX",
    # ETFs / Indexes
    "SPY", "QQQ", "IWM", "DIA", "ARKK", "SOXS", "TQQQ", "SQQQ",
    # Meme / high vol
    "GME", "AMC", "BBBY", "CLOV", "SPCE", "WISH", "TLRY",
    # Semis
    "NVDA", "AMD", "QCOM", "MU", "AMAT", "LRCX", "ASML", "TSM",
    # EV / clean energy
    "RIVN", "LCID", "XPEV", "NIO", "PLUG", "FCEL", "BE",
    # Biotech
    "BIIB", "REGN", "GILD", "VRTX", "SGEN", "BMRN",
]
SCAN_UNIVERSE = list(dict.fromkeys(SCAN_UNIVERSE))  # dedupe


def _fetch_screener_data(tickers: List[str]) -> List[Dict]:
    results = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            fi = t.fast_info
            info = {}
            try:
                info = t.info
            except Exception:
                pass
            price = fi.last_price or 0
            prev = fi.previous_close or price
            chg_pct = ((price - prev) / prev * 100) if prev else 0
            day_volume = int(fi.shares or 0)  # today's volume isn't on fast_info; use regularMarketVolume from info
            day_volume = info.get("regularMarketVolume") or 0
            avg_vol = info.get("averageVolume") or fi.three_month_average_volume or 1
            rel_vol = round(day_volume / avg_vol, 2) if avg_vol and day_volume else 1.0

            ta = analyze(ticker, period="3mo", interval="1d")
            rsi = ta.get("rsi_14") if ta else None
            signals = (ta.get("bull_signals", []) + ta.get("bear_signals", [])) if ta else []

            score = _compute_score(chg_pct, rel_vol, rsi, ta)

            results.append({
                "ticker": ticker,
                "name": info.get("longName") or info.get("shortName") or ticker,
                "price": round(price, 2),
                "change_pct": round(chg_pct, 2),
                "volume": int(day_volume),
                "rel_volume": rel_vol,
                "market_cap": fi.market_cap,
                "rsi": rsi,
                "short_float": info.get("shortPercentOfFloat"),
                "sector": info.get("sector"),
                "score": score,
                "signals": signals[:4],
            })
        except Exception as e:
            print(f"[Screener] error for {ticker}: {e}")
    return results


def _compute_score(chg_pct: float, rel_vol: float, rsi: Optional[float], ta: Optional[Dict]) -> float:
    score = 0.0
    # Volume premium
    if rel_vol > 3:
        score += 3
    elif rel_vol > 2:
        score += 2
    elif rel_vol > 1.5:
        score += 1

    # Price momentum
    if chg_pct > 5:
        score += 3
    elif chg_pct > 2:
        score += 2
    elif chg_pct > 0:
        score += 1
    elif chg_pct < -5:
        score -= 2

    # RSI
    if rsi:
        if 40 <= rsi <= 60:
            score += 1
        elif rsi < 30:
            score += 2  # potential bounce
        elif rsi > 75:
            score -= 1

    # TA signals
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
    loop = asyncio.get_running_loop()
    universe = custom_tickers or SCAN_UNIVERSE
    raw = await loop.run_in_executor(_executor, _fetch_screener_data, universe)

    filtered = [
        r for r in raw
        if min_price <= r["price"] <= max_price
        and r["rel_volume"] >= min_rel_volume
        and min_change_pct <= r["change_pct"] <= max_change_pct
        and (not sector or r.get("sector", "").lower() == sector.lower())
    ]

    filtered.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return filtered[:limit]
