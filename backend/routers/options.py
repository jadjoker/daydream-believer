from fastapi import APIRouter, HTTPException
from services import yahoo_finance as yf_svc
from services.cache_service import cache

router = APIRouter(prefix="/options", tags=["options"])


@router.get("/flow/{ticker}")
@cache(ttl=180, key_prefix="options_flow")
async def get_options_flow(ticker: str):
    ticker = ticker.upper()
    data = await yf_svc.get_options_chain(ticker)
    if not data:
        raise HTTPException(404, f"No options data for {ticker}")
    return {"ticker": ticker, **data}


@router.get("/unusual")
@cache(ttl=300, key_prefix="unusual_options")
async def get_unusual_options(tickers: str = "SPY,QQQ,AAPL,MSFT,TSLA,NVDA,AMD"):
    from services import yahoo_finance as yf_svc
    import asyncio
    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    results = await asyncio.gather(*[yf_svc.get_options_chain(t) for t in ticker_list], return_exceptions=True)
    unusual = []
    for i, r in enumerate(results):
        if isinstance(r, dict) and r.get("unusual_contracts"):
            for contract in r["unusual_contracts"][:5]:
                unusual.append({**contract, "ticker": ticker_list[i]})
    unusual.sort(key=lambda x: x["volume"], reverse=True)
    return {"unusual_activity": unusual[:50]}
