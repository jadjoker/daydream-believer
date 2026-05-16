from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from services import simulator_service
import asyncio

router = APIRouter(prefix="/simulator", tags=["simulator"])


class TradeRequest(BaseModel):
    ticker: str
    name: str
    shares: float
    price: float
    thesis: str = ""


class FundsRequest(BaseModel):
    amount: float


@router.get("/state")
def get_state():
    return simulator_service.get_state()


@router.post("/buy")
def buy(req: TradeRequest):
    result = simulator_service.buy(req.ticker, req.name, req.shares, req.price, req.thesis)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Buy failed"))
    return result["state"]


@router.post("/sell")
def sell(req: TradeRequest):
    result = simulator_service.sell(req.ticker, req.name, req.shares, req.price, req.thesis)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Sell failed"))
    return result["state"]


@router.post("/add-funds")
def add_funds(req: FundsRequest):
    return simulator_service.add_funds(req.amount)


@router.post("/reset")
def reset():
    return simulator_service.reset()


@router.get("/dca")
async def dca(
    ticker: str = Query(..., description="Stock ticker symbol"),
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    initial: float = Query(10000, ge=1),
    recurring: float = Query(0, ge=0),
    frequency: str = Query("monthly", pattern="^(weekly|biweekly|monthly|none)$"),
):
    from services import yahoo_finance as yf_svc
    from datetime import date as dt

    # Clamp end date to yesterday (yfinance doesn't serve intraday for today reliably)
    today_str = dt.today().strftime("%Y-%m-%d")
    if end >= today_str:
        end = today_str

    if start >= end:
        raise HTTPException(400, f"Start date ({start}) must be before end date ({end}). Pick an earlier start date.")

    try:
        ohlcv, spy_ohlcv = await asyncio.gather(
            yf_svc.get_ohlcv_range(ticker.upper(), start, end),
            yf_svc.get_ohlcv_range("SPY", start, end),
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch price data: {e}")

    if not ohlcv or len(ohlcv) < 2:
        raise HTTPException(404, f"Not enough historical data for {ticker.upper()} between {start} and {end}. Try a wider date range or check the ticker symbol.")

    result = simulator_service.compute_dca(ohlcv, spy_ohlcv, initial, recurring, frequency)
    if not result:
        raise HTTPException(500, "DCA computation failed — check your inputs")

    result["ticker"] = ticker.upper()
    result["start"] = ohlcv[0]["date"]
    result["end"] = ohlcv[-1]["date"]
    result["frequency"] = frequency
    return result
