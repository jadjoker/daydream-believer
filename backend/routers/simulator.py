from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
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


@router.get("/recurring")
def get_recurring():
    return simulator_service.get_recurring_plans()


class RecurringAddRequest(BaseModel):
    ticker: str
    name: str = ""
    amount: float
    frequency: str
    start_date: str
    backfill: bool = False


class RecurringExecuteRequest(BaseModel):
    price: float
    name: str = ""


@router.post("/recurring/add")
async def add_recurring(req: RecurringAddRequest):
    from datetime import date as dt
    today = dt.today().strftime("%Y-%m-%d")

    if req.frequency not in ("weekly", "biweekly", "monthly"):
        raise HTTPException(400, "Frequency must be weekly, biweekly, or monthly")
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be > 0")

    plan = simulator_service.add_recurring_plan(
        req.ticker, req.name, req.amount, req.frequency, req.start_date
    )

    backfill_result = None
    if req.backfill and req.start_date < today:
        from services import yahoo_finance as yf_svc
        try:
            ohlcv = await yf_svc.get_ohlcv_range(req.ticker.upper(), req.start_date, today)
            if ohlcv and len(ohlcv) >= 2:
                backfill_result = simulator_service.backfill_recurring_plan(plan["id"], ohlcv)
            else:
                backfill_result = {"ok": False, "error": "Not enough historical data to backfill"}
        except Exception as e:
            backfill_result = {"ok": False, "error": str(e)}

    return {
        "plans": simulator_service.get_recurring_plans(),
        "backfill": backfill_result,
    }


@router.post("/recurring/execute/{plan_id}")
def execute_recurring(plan_id: int, req: RecurringExecuteRequest):
    result = simulator_service.execute_recurring_plan(plan_id, req.price, req.name)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Execute failed"))
    return result


@router.delete("/recurring/{plan_id}")
def delete_recurring(plan_id: int):
    return simulator_service.delete_recurring_plan(plan_id)


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
