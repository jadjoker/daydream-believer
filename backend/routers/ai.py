from fastapi import APIRouter, HTTPException, Query
from services import ai_service
from services.screener_service import run_screener
from services import yahoo_finance as yf_svc, stocktwits_service
from services.cache_service import get_cached, set_cached
import asyncio
from datetime import datetime, timedelta
import pytz

router = APIRouter(prefix="/ai", tags=["ai"])

SECTOR_ETFS = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
    "Energy": "XLE", "Consumer Disc.": "XLY", "Consumer Staples": "XLP",
    "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU",
    "Real Estate": "XLRE", "Communication": "XLC",
}
INDEX_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "^VIX"]


def _next_trading_day(now: datetime) -> tuple[str, str]:
    """Return (human_label, YYYY-MM-DD) for the next market open day."""
    wd = now.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun
    if wd == 4:    # Friday → Monday
        delta = 3
    elif wd == 5:  # Saturday → Monday
        delta = 2
    elif wd == 6:  # Sunday → Monday
        delta = 1
    else:          # Mon–Thu → tomorrow
        delta = 1
    next_day = now + timedelta(days=delta)
    label = ("Monday" if delta > 1 else "Tomorrow") + " " + next_day.strftime("%b %d").replace(" 0", " ")
    return label, next_day.strftime("%Y-%m-%d")


async def _build_market_snapshot() -> dict:
    all_tickers = INDEX_TICKERS + list(SECTOR_ETFS.values())
    quotes = await asyncio.gather(
        *[yf_svc.get_quote(t) for t in all_tickers],
        return_exceptions=True,
    )
    idx = {t: (q if isinstance(q, dict) else None) for t, q in zip(all_tickers, quotes)}

    def pc(t):
        q = idx.get(t)
        return (q.get("price", 0), q.get("change_pct", 0)) if q else (0, 0)

    sector_perf = []
    for name, etf in SECTOR_ETFS.items():
        p, c = pc(etf)
        sector_perf.append({"name": name, "etf": etf, "price": p, "change_pct": c})
    sector_perf.sort(key=lambda x: x["change_pct"], reverse=True)

    trending = await stocktwits_service.get_trending_tickers()

    now = datetime.now(pytz.timezone("US/Eastern"))
    h, m, wd = now.hour, now.minute, now.weekday()
    if wd >= 5:
        status = "closed"
    elif (h == 9 and m >= 30) or (10 <= h <= 15) or (h == 16 and m == 0):
        status = "open"
    elif (4 <= h < 9) or (h == 9 and m < 30):
        status = "pre-market"
    elif (h == 16 and m > 0) or (17 <= h < 20):
        status = "after-hours"
    else:
        status = "closed"

    spy_p, spy_c = pc("SPY")
    qqq_p, qqq_c = pc("QQQ")
    iwm_p, iwm_c = pc("IWM")
    vix_p, vix_c = pc("^VIX")

    return {
        "spy_price": spy_p, "spy_change_pct": spy_c,
        "qqq_price": qqq_p, "qqq_change_pct": qqq_c,
        "iwm_price": iwm_p, "iwm_change_pct": iwm_c,
        "vix": vix_p, "vix_change_pct": vix_c,
        "sector_performance": sector_perf,
        "trending_tickers": trending[:10],
        "market_status": status,
    }


@router.get("/picks")
async def get_ai_picks(mode: str = Query("short", pattern="^(short|long|discovery)$")):
    """Generate Claude-powered stock picks. mode=short (day trade) or mode=long (12-month)."""
    cache_key = f"ai_picks_{mode}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        market_data, screener_data = await asyncio.gather(
            _build_market_snapshot(),
            run_screener(min_rel_volume=1.0, sort_by="score", limit=20),
        )
        now = datetime.now(pytz.timezone("US/Eastern"))
        date_str = now.strftime("%Y-%m-%d %H:%M ET")
        next_trading_day_label, next_trading_day_date = _next_trading_day(now)

        result = await ai_service.generate_market_picks(
            market_overview=market_data,
            screener_results=screener_data,
            date_str=date_str,
            next_trading_day_label=next_trading_day_label,
            mode=mode,
        )
        if mode == "discovery":
            result["next_trading_day_label"] = "10-Year Discovery Plays"
            result["next_trading_day_date"] = None
        elif mode == "long":
            result["next_trading_day_label"] = "Long-term (6–12 months)"
            result["next_trading_day_date"] = None
        else:
            result["next_trading_day_label"] = next_trading_day_label
            result["next_trading_day_date"] = next_trading_day_date
        result["mode"] = mode
        set_cached(cache_key, result, ttl=1800)
        return result
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        msg = str(e)
        if "credit balance is too low" in msg or "billing" in msg.lower():
            raise HTTPException(402, "Anthropic account has no credits. Add credits at console.anthropic.com/settings/billing")
        raise HTTPException(500, f"AI picks failed: {e}")


@router.get("/analyze/{ticker}")
async def analyze_ticker(ticker: str, mode: str = Query("short", pattern="^(short|long|discovery)$")):
    """Analyze a single ticker. mode=short (next open) or mode=long (6-12 month hold)."""
    try:
        now = datetime.now(pytz.timezone("US/Eastern"))
        next_trading_day_label, _ = _next_trading_day(now)
        # Long-term analysis doesn't need market snapshot (fundamentals-focused)
        market_data = {} if mode in ("long", "discovery") else await _build_market_snapshot()
        result = await ai_service.analyze_ticker(
            ticker=ticker.upper().strip(),
            market_overview=market_data,
            next_trading_day_label=next_trading_day_label,
            mode=mode,
        )
        result["mode"] = mode
        return result
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        msg = str(e)
        if "credit balance is too low" in msg or "billing" in msg.lower():
            raise HTTPException(402, "Anthropic account has no credits.")
        raise HTTPException(500, f"Ticker analysis failed: {e}")
