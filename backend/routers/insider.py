from fastapi import APIRouter, HTTPException
from services import sec_edgar
from services.cache_service import cache

router = APIRouter(prefix="/insider", tags=["insider"])


@router.get("/trades/{ticker}")
@cache(ttl=3600, key_prefix="insider_trades")
async def get_insider_trades(ticker: str):
    ticker = ticker.upper()
    openinsider = await sec_edgar.get_openinsider_trades(ticker)
    sec_trades = await sec_edgar.get_insider_transactions(ticker)
    combined = openinsider if openinsider else sec_trades
    return {"ticker": ticker, "trades": combined}


@router.get("/filings/{ticker}")
@cache(ttl=3600, key_prefix="sec_filings")
async def get_filings(ticker: str, form_type: str = "8-K"):
    ticker = ticker.upper()
    filings = await sec_edgar.get_recent_filings(ticker, form_type)
    return {"ticker": ticker, "form_type": form_type, "filings": filings}
