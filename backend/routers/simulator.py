from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import simulator_service

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
