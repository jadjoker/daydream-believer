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


async def get_quote(ticker: str) -> Optional[Dict]:
    """Real-time quote via Finnhub — used as primary source when key is set."""
    data = await _get("/quote", {"symbol": ticker})
    if not data or not data.get("c"):
        return None
    price = data["c"]
    prev  = data.get("pc") or price
    chg   = data.get("d", 0) or 0
    chg_p = data.get("dp", 0) or 0
    return {
        "ticker": ticker.upper(),
        "name": ticker,
        "price": round(price, 2),
        "prev_close": round(prev, 2),
        "open": data.get("o"),
        "day_high": data.get("h"),
        "day_low": data.get("l"),
        "change": round(chg, 2),
        "change_pct": round(chg_p, 2),
        "volume": 0,
        "avg_volume": None,
        "rel_volume": None,
        "market_cap": None,
        "pe_ratio": None,
        "eps": None,
        "week_52_high": None,
        "week_52_low": None,
        "dividend_yield": None,
        "dividend_rate": None,
        "beta": None,
        "short_float": None,
        "short_ratio": None,
        "float_shares": None,
        "outstanding_shares": None,
        "sector": None,
        "industry": None,
        "exchange": None,
    }


_PERIOD_MAP = {
    # (period_str, interval_str) → (finnhub_resolution, days_back)
    ("1d",  "5m"):   ("5",  2),
    ("5d",  "15m"):  ("15", 6),
    ("1mo", "1d"):   ("D",  32),
    ("3mo", "1d"):   ("D",  95),
    ("6mo", "1d"):   ("D",  185),
    ("1y",  "1d"):   ("D",  370),
    ("2y",  "1wk"):  ("W",  740),
    ("5y",  "1wk"):  ("W",  1830),
}

async def get_candles(ticker: str, period: str = "3mo", interval: str = "1d") -> List[Dict]:
    """OHLCV candles from Finnhub. Returns same shape as yahoo_finance.get_ohlcv."""
    resolution, days = _PERIOD_MAP.get((period, interval), ("D", 95))
    now = int(datetime.utcnow().timestamp())
    frm = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    data = await _get("/stock/candle", {"symbol": ticker, "resolution": resolution, "from": frm, "to": now})
    if not data or data.get("s") != "ok":
        return []
    bars = []
    for i, t in enumerate(data["t"]):
        bars.append({
            "timestamp": datetime.utcfromtimestamp(t).isoformat(),
            "open":   round(data["o"][i], 4),
            "high":   round(data["h"][i], 4),
            "low":    round(data["l"][i], 4),
            "close":  round(data["c"][i], 4),
            "volume": float(data["v"][i]),
        })
    return bars


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


async def get_fundamentals_mapped(ticker: str) -> Optional[Dict]:
    """
    Fetch Finnhub basic financials and normalize to the same schema as
    yf_svc.get_fundamentals() so all scoring functions work unchanged.
    Replaces Yahoo Finance t.info calls — no 429 risk.
    """
    data = await get_basic_financials(ticker)
    if not data:
        return None
    m = data.get("metric") or {}
    if not m:
        return None

    def pct(key: str):
        """Finnhub reports percentages as whole numbers (45.6 → 0.456)."""
        v = m.get(key)
        return round(v / 100, 6) if v is not None else None

    # Prefer most recent (quarterly YoY), fall back to trailing/3Y
    rev_growth = pct("revenueGrowthQuarterlyYoy") or pct("revenueGrowthTTMYoy") or pct("revenueGrowth3Y")
    eps_growth = pct("epsGrowthQuarterlyYoy") or pct("epsGrowthTTMYoy") or pct("epsGrowth3Y")

    # FCF: Finnhub reports in USD millions — multiply to get absolute dollars
    fcf_m = m.get("freeCashFlowTTM") or m.get("freeCashFlowAnnual")
    free_cashflow = fcf_m * 1_000_000 if fcf_m is not None else None

    return {
        "ticker": ticker.upper(),
        "pe_ratio": m.get("peBasicExclExtraTTM") or m.get("peNormalizedAnnual"),
        "forward_pe": m.get("peNormalizedAnnual"),  # best free-tier approximation
        "peg_ratio": None,                           # Finnhub premium only
        "ps_ratio": m.get("priceToSalesTTM") or m.get("priceToSalesQuarterly"),
        "pb_ratio": m.get("priceToBookQuarterly"),
        "ev_ebitda": None,
        "profit_margin": pct("netProfitMarginTTM") or pct("netProfitMarginAnnual"),
        "operating_margin": pct("operatingMarginTTM") or pct("operatingMarginAnnual"),
        "roe": pct("roeTTM") or pct("roeAnnual"),
        "roa": pct("roaAnnual"),
        "revenue": None,
        "revenue_growth": rev_growth,
        "earnings_growth": eps_growth,
        "gross_margins": pct("grossMarginTTM") or pct("grossMarginAnnual"),
        "debt_to_equity": m.get("totalDebt/totalEquityAnnual"),
        "current_ratio": m.get("currentRatioAnnual") or m.get("currentRatioQuarterly"),
        "quick_ratio": None,
        "free_cashflow": free_cashflow,
        "dividend_yield": pct("dividendYieldIndicatedAnnual"),
        "payout_ratio": pct("payoutRatioAnnual"),
        "book_value": m.get("bookValuePerShareAnnual"),
        "eps_trailing": m.get("epsNormalizedAnnual"),
        "eps_forward": None,
        "analyst_rating": None,
        "analyst_count": None,
        "target_price": None,
        "target_low": None,
        "target_high": None,
        "short_float": None,
        "short_ratio": None,
        "insider_pct": None,
        "institution_pct": None,
    }
