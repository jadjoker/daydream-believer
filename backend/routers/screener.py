from fastapi import APIRouter, Query
from typing import Optional, List
from services.screener_service import run_screener, SCAN_UNIVERSE
from services.cache_service import cache

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("/scan")
@cache(ttl=300, key_prefix="screener_scan")
async def scan(
    min_price: float = Query(1.0),
    max_price: float = Query(10000.0),
    min_rel_volume: float = Query(1.0),
    min_change_pct: float = Query(-50.0),
    max_change_pct: float = Query(50.0),
    sector: Optional[str] = Query(None),
    sort_by: str = Query("score", description="score, change_pct, rel_volume, rsi"),
    limit: int = Query(25, le=50),
    tickers: Optional[str] = Query(None, description="Comma-separated custom tickers to scan"),
):
    custom = [t.strip().upper() for t in tickers.split(",")] if tickers else None
    results = await run_screener(
        min_price=min_price,
        max_price=max_price,
        min_rel_volume=min_rel_volume,
        min_change_pct=min_change_pct,
        max_change_pct=max_change_pct,
        sector=sector,
        sort_by=sort_by,
        limit=limit,
        custom_tickers=custom,
    )
    return {"results": results, "count": len(results)}


@router.get("/universe")
async def get_universe():
    return {"tickers": SCAN_UNIVERSE}
