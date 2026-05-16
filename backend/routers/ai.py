import time
from fastapi import APIRouter, HTTPException, Query
from services import ai_service
from services.screener_service import run_screener
from services import yahoo_finance as yf_svc
from services.cache_service import get_cached, set_cached
import asyncio
from datetime import datetime, timedelta
import pytz

router = APIRouter(prefix="/ai", tags=["ai"])

# Core tickers for regime assessment — just enough for SPY/QQQ/VIX
_REGIME_TICKERS = ["SPY", "QQQ", "IWM", "^VIX"]

_snapshot_cache: dict = {"ts": 0.0, "data": None}
_SNAPSHOT_TTL = 300  # 5 minutes


def _next_trading_day(now: datetime) -> tuple[str, str]:
    wd = now.weekday()
    if wd == 4:
        delta = 3
    elif wd == 5:
        delta = 2
    elif wd == 6:
        delta = 1
    else:
        delta = 1
    next_day = now + timedelta(days=delta)
    label = ("Monday" if delta > 1 else "Tomorrow") + " " + next_day.strftime("%b %d").replace(" 0", " ")
    return label, next_day.strftime("%Y-%m-%d")


async def _build_market_snapshot() -> dict:
    """Fetch SPY/QQQ/IWM/VIX for regime assessment only. Cached 5 min."""
    now = time.time()
    if _snapshot_cache["ts"] and (now - _snapshot_cache["ts"]) < _SNAPSHOT_TTL and _snapshot_cache["data"]:
        return _snapshot_cache["data"]

    quotes = await asyncio.gather(
        *[yf_svc.get_quote(t) for t in _REGIME_TICKERS],
        return_exceptions=True,
    )
    idx = {t: (q if isinstance(q, dict) else None) for t, q in zip(_REGIME_TICKERS, quotes)}

    def pc(t):
        q = idx.get(t)
        return (q.get("price", 0), q.get("change_pct", 0)) if q else (0, 0)

    spy_p, spy_c = pc("SPY")
    qqq_p, qqq_c = pc("QQQ")
    iwm_p, iwm_c = pc("IWM")
    vix_p, vix_c = pc("^VIX")

    now_dt = datetime.now(pytz.timezone("US/Eastern"))
    h, m, wd = now_dt.hour, now_dt.minute, now_dt.weekday()
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

    result = {
        "spy_price": spy_p, "spy_change_pct": spy_c,
        "qqq_price": qqq_p, "qqq_change_pct": qqq_c,
        "iwm_price": iwm_p, "iwm_change_pct": iwm_c,
        "vix": vix_p, "vix_change_pct": vix_c,
        "sector_performance": [],
        "trending_tickers": [],
        "market_status": status,
    }
    _snapshot_cache["ts"] = time.time()
    _snapshot_cache["data"] = result
    return result


@router.get("/picks")
async def get_ai_picks(mode: str = Query("short", pattern="^(short|long|discovery)$")):
    cache_key = f"ai_picks_{mode}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        # Sequential: market snapshot first (4 Finnhub calls, cached 5 min),
        # then screener (Finnhub quotes + batched Yahoo Finance TA).
        # Prevents the burst of 60+ simultaneous calls that kills free-tier limits.
        market_data = await _build_market_snapshot()
        screener_data = await run_screener(min_rel_volume=1.0, sort_by="score", limit=20) if mode == "short" else []

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
            raise HTTPException(402, "🪙 The AI's coin jar is empty! Claude tried to think but found tumbleweeds where the credits should be. Head to console.anthropic.com/settings/billing and toss in some tokens — the robot is hungry.")
        raise HTTPException(500, f"AI picks failed: {e}")


@router.get("/analyze/{ticker}")
async def analyze_ticker(ticker: str, mode: str = Query("short", pattern="^(short|long|discovery)$")):
    """Analyze a single ticker on demand. API call fires only when user submits."""
    try:
        now = datetime.now(pytz.timezone("US/Eastern"))
        next_trading_day_label, _ = _next_trading_day(now)
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
            raise HTTPException(402, "🪙 The AI's coin jar is empty! Claude tried to think but found tumbleweeds where the credits should be. Head to console.anthropic.com/settings/billing and toss in some tokens — the robot is hungry.")
        raise HTTPException(500, f"Ticker analysis failed: {e}")
