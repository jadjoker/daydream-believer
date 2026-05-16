from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import httpx
from services import yahoo_finance as yf_svc
from services import technical_analysis as ta_svc
from services import finnhub_service as fh
from services.cache_service import cache

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search")
@cache(ttl=300, key_prefix="search")
async def search_ticker(q: str = Query(..., min_length=1)):
    """Search by ticker symbol or company name via Yahoo Finance."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params={"q": q, "quotesCount": 10, "newsCount": 0, "enableFuzzyQuery": True},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data = r.json()
        results = []
        for item in data.get("quotes", []):
            symbol = item.get("symbol", "")
            if not symbol or "." in symbol:  # skip ADRs / foreign exchanges
                continue
            results.append({
                "ticker": symbol,
                "name": item.get("longname") or item.get("shortname") or symbol,
                "exchange": item.get("exchange", ""),
                "type": item.get("quoteType", ""),
            })
        return {"results": results}
    except Exception as e:
        return {"results": []}


@router.get("/quote/{ticker}")
@cache(ttl=60, key_prefix="quote")
async def get_quote(ticker: str):
    ticker = ticker.upper()
    quote = await yf_svc.get_quote(ticker)
    if not quote:
        raise HTTPException(404, f"No data for {ticker}")
    return quote


@router.get("/ohlcv/{ticker}")
@cache(ttl=120, key_prefix="ohlcv")
async def get_ohlcv(
    ticker: str,
    period: str = Query("3mo", description="1d 5d 1mo 3mo 6mo 1y 2y 5y"),
    interval: str = Query("1d", description="1m 5m 15m 30m 1h 1d 1wk 1mo"),
):
    # Try Finnhub first (more reliable on cloud); fall back to Yahoo Finance
    bars = await fh.get_candles(ticker.upper(), period, interval)
    if not bars:
        bars = await yf_svc.get_ohlcv(ticker.upper(), period, interval)
    if not bars:
        raise HTTPException(404, f"No OHLCV data for {ticker}")
    return {"ticker": ticker.upper(), "period": period, "interval": interval, "bars": bars}


@router.get("/technicals/{ticker}")
@cache(ttl=120, key_prefix="technicals")
async def get_technicals(
    ticker: str,
    period: str = Query("6mo"),
    interval: str = Query("1d"),
):
    signals = await ta_svc.get_technical_signals(ticker.upper(), period, interval)
    if not signals:
        raise HTTPException(404, f"No technical data for {ticker}")
    return signals


@router.get("/fundamentals/{ticker}")
@cache(ttl=3600, key_prefix="fundamentals")
async def get_fundamentals(ticker: str):
    data = await yf_svc.get_fundamentals(ticker.upper())
    if not data:
        raise HTTPException(404, f"No fundamental data for {ticker}")
    return data


@router.get("/profile/{ticker}")
@cache(ttl=3600, key_prefix="profile")
async def get_profile(ticker: str):
    profile = await fh.get_company_profile(ticker.upper())
    return profile or {}


@router.get("/price-target/{ticker}")
@cache(ttl=3600, key_prefix="price_target")
async def get_price_target(ticker: str):
    pt = await fh.get_price_target(ticker.upper())
    upgrades = await fh.get_upgrade_downgrade(ticker.upper())
    recommendations = await fh.get_recommendation_trends(ticker.upper())
    return {
        "price_target": pt,
        "upgrades_downgrades": upgrades[:10],
        "recommendation_trend": recommendations[:4],
    }


@router.get("/basic-financials/{ticker}")
@cache(ttl=3600, key_prefix="basic_financials")
async def get_basic_financials(ticker: str):
    data = await fh.get_basic_financials(ticker.upper())
    return data or {}


@router.get("/multi-quote")
async def get_multi_quote(tickers: str = Query(..., description="Comma-separated tickers")):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) > 50:
        raise HTTPException(400, "Max 50 tickers")
    quotes = await yf_svc.get_multiple_quotes(ticker_list)
    return {"quotes": quotes}
