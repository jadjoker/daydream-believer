from fastapi import APIRouter
from services import yahoo_finance as yf_svc, stocktwits_service, reddit_service
from services.cache_service import cache
import asyncio

router = APIRouter(prefix="/market", tags=["market"])

INDEX_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "^VIX"]
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Consumer Disc.": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication": "XLC",
}


@router.get("/overview")
@cache(ttl=60, key_prefix="market_overview")
async def get_market_overview():
    all_tickers = INDEX_TICKERS + list(SECTOR_ETFS.values())
    quotes = await asyncio.gather(
        *[yf_svc.get_quote(t) for t in all_tickers],
        return_exceptions=True,
    )

    def safe_quote(q):
        return q if isinstance(q, dict) else None

    idx = {t: safe_quote(q) for t, q in zip(all_tickers, quotes)}

    def price_chg(t):
        q = idx.get(t)
        return (q.get("price", 0), q.get("change_pct", 0)) if q else (0, 0)

    spy_p, spy_c = price_chg("SPY")
    qqq_p, qqq_c = price_chg("QQQ")
    iwm_p, iwm_c = price_chg("IWM")
    dia_p, dia_c = price_chg("DIA")
    vix_p, vix_c = price_chg("^VIX")

    sector_perf = []
    for name, etf in SECTOR_ETFS.items():
        p, c = price_chg(etf)
        sector_perf.append({"name": name, "etf": etf, "price": p, "change_pct": c})
    sector_perf.sort(key=lambda x: x["change_pct"], reverse=True)

    trending_st = await stocktwits_service.get_trending_tickers()

    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("US/Eastern"))
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()
    if weekday >= 5:
        market_status = "closed"
    elif (hour == 9 and minute >= 30) or (10 <= hour <= 15) or (hour == 16 and minute == 0):
        market_status = "open"
    elif (4 <= hour < 9) or (hour == 9 and minute < 30):
        market_status = "pre-market"
    elif (hour == 16 and minute > 0) or (17 <= hour < 20):
        market_status = "after-hours"
    else:
        market_status = "closed"

    return {
        "spy_price": spy_p,
        "spy_change_pct": spy_c,
        "qqq_price": qqq_p,
        "qqq_change_pct": qqq_c,
        "vix": vix_p,
        "vix_change_pct": vix_c,
        "iwm_price": iwm_p,
        "iwm_change_pct": iwm_c,
        "dia_price": dia_p,
        "dia_change_pct": dia_c,
        "advance_decline": None,
        "sector_performance": sector_perf,
        "trending_tickers": trending_st[:10],
        "market_status": market_status,
    }
