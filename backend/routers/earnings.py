from fastapi import APIRouter, Query
from services import finnhub_service as fh
from services.cache_service import cache

router = APIRouter(prefix="/earnings", tags=["earnings"])


@router.get("/calendar")
@cache(ttl=3600, key_prefix="earnings_calendar")
async def get_earnings_calendar(weeks_ahead: int = Query(2, ge=1, le=8)):
    events = await fh.get_earnings_calendar(weeks_ahead)
    return {"events": events}


@router.get("/ticker/{ticker}")
@cache(ttl=3600, key_prefix="earnings_ticker")
async def get_ticker_earnings(ticker: str):
    ticker = ticker.upper()
    financials = await fh.get_financials(ticker, "ic", "quarterly")
    basic = await fh.get_basic_financials(ticker)
    return {
        "ticker": ticker,
        "income_statement": financials,
        "metrics": basic,
    }
