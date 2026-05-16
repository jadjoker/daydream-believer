import asyncio
import time
from fastapi import APIRouter, HTTPException, Query
from services import ai_service
from services.screener_service import run_screener
from services import yahoo_finance as yf_svc
from services.cache_service import get_cached, set_cached, delete_cached
from datetime import datetime, timedelta
import pytz

router = APIRouter(prefix="/ai", tags=["ai"])

# Core tickers for regime assessment — just enough for SPY/QQQ/VIX
_REGIME_TICKERS = ["SPY", "QQQ", "IWM", "^VIX"]

_snapshot_cache: dict = {"ts": 0.0, "data": None}
_SNAPSHOT_TTL = 300   # 5 minutes
_PICKS_TTL    = 86400 # 24 hours — picks survive the full trading day

# Prevent duplicate concurrent generation (startup pre-warm vs first user request)
_picks_lock = asyncio.Lock()
_is_generating: bool = False


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


async def _inner_generate_all_picks() -> dict:
    """
    Core generation logic. Called by the endpoint (holding _picks_lock) and
    the background startup pre-warm. Always writes to cache on success.
    """
    now = datetime.now(pytz.timezone("US/Eastern"))
    date_str = now.strftime("%Y-%m-%d %H:%M ET")
    next_trading_day_label, next_trading_day_date = _next_trading_day(now)

    # Phase 1: market snapshot (cached 5 min, only 4 calls)
    market_data = await _build_market_snapshot()

    # Phase 2a: short screener — batched Finnhub quotes (~1.5s)
    screener_data = await run_screener(sort_by="score", limit=20)

    # Phase 2b: pre-warm longterm + discovery caches in parallel
    await asyncio.gather(
        ai_service.screen_longterm_candidates(top_n=10),
        ai_service.screen_discovery_candidates(top_n=10),
    )

    # Phase 3: all 3 Claude calls in parallel (internal screenings hit module-level cache)
    short_result, long_result, disc_result = await asyncio.gather(
        ai_service.generate_market_picks(
            market_overview=market_data,
            screener_results=screener_data,
            date_str=date_str,
            next_trading_day_label=next_trading_day_label,
            mode="short",
        ),
        ai_service.generate_market_picks(
            market_overview=market_data,
            screener_results=[],
            date_str=date_str,
            next_trading_day_label=next_trading_day_label,
            mode="long",
        ),
        ai_service.generate_market_picks(
            market_overview=market_data,
            screener_results=[],
            date_str=date_str,
            next_trading_day_label=next_trading_day_label,
            mode="discovery",
        ),
    )

    short_result["next_trading_day_label"] = next_trading_day_label
    short_result["next_trading_day_date"] = next_trading_day_date
    short_result["mode"] = "short"
    long_result["next_trading_day_label"] = "Long-term (6–12 months)"
    long_result["next_trading_day_date"] = None
    long_result["mode"] = "long"
    disc_result["next_trading_day_label"] = "10-Year Discovery Plays"
    disc_result["next_trading_day_date"] = None
    disc_result["mode"] = "discovery"

    full = {"short": short_result, "long": long_result, "discovery": disc_result}

    # Cache the full 8-pick set for /picks-more/{mode}
    set_cached("ai_picks_all_full", full, ttl=_PICKS_TTL)

    # Return only first 5 picks per mode in the initial response
    trimmed = {}
    for mode_key, mode_result in full.items():
        all_picks = mode_result.get("picks", [])
        trimmed[mode_key] = {
            **mode_result,
            "picks": all_picks[:5],
            "has_more": len(all_picks) > 5,
            "total_picks": len(all_picks),
        }

    set_cached("ai_picks_all", trimmed, ttl=_PICKS_TTL)
    return trimmed


async def background_refresh_picks():
    """
    Background task: generate picks without blocking any HTTP request.
    Safe to fire from lifespan startup and POST /ai/refresh.
    Skips if generation is already in progress.
    """
    global _is_generating
    if _picks_lock.locked():
        return  # already generating
    _is_generating = True
    try:
        async with _picks_lock:
            # Double-check: another coroutine may have filled cache while we waited
            if get_cached("ai_picks_all") is not None:
                return
            await _inner_generate_all_picks()
    except Exception:
        pass  # swallow — background task; errors surface on next user request
    finally:
        _is_generating = False


@router.get("/picks")
async def get_ai_picks(mode: str = Query("short", pattern="^(short|long|discovery)$")):
    cache_key = f"ai_picks_{mode}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
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
        set_cached(cache_key, result, ttl=_PICKS_TTL)
        return result
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        msg = str(e)
        if "credit balance is too low" in msg or "billing" in msg.lower():
            raise HTTPException(402, "🪙 The AI's coin jar is empty! Claude tried to think but found tumbleweeds where the credits should be. Head to console.anthropic.com/settings/billing and toss in some tokens — the robot is hungry.")
        raise HTTPException(500, f"AI picks failed: {e}")


@router.get("/picks-all")
async def get_ai_picks_all():
    """
    Fetch short + long + discovery picks in one request.
    Returns 5 picks per mode. Full 8-pick set cached for /picks-more/{mode}.

    Uses an asyncio.Lock so the startup pre-warm and first user request
    don't both fire Claude — whichever arrives second hits the cache.
    """
    cached = get_cached("ai_picks_all")
    if cached is not None:
        return cached

    try:
        async with _picks_lock:
            # Re-check after acquiring lock (pre-warm may have just finished)
            cached = get_cached("ai_picks_all")
            if cached is not None:
                return cached
            return await _inner_generate_all_picks()

    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        msg = str(e)
        if "credit balance is too low" in msg or "billing" in msg.lower():
            raise HTTPException(402, "🪙 The AI's coin jar is empty! Claude tried to think but found tumbleweeds where the credits should be. Head to console.anthropic.com/settings/billing and toss in some tokens — the robot is hungry.")
        raise HTTPException(500, f"AI picks failed: {e}")


@router.get("/picks-more/{mode}")
async def get_ai_picks_more(mode: str):
    """
    Returns picks 6+ for a mode from the cached full result.
    Must call /picks-all first to populate the cache.
    Instant response — no Claude call needed.
    """
    if mode not in ("short", "long", "discovery"):
        raise HTTPException(400, "mode must be short, long, or discovery")
    full = get_cached("ai_picks_all_full")
    if not full or mode not in full:
        raise HTTPException(404, "No cached picks for this mode — load /ai/picks-all first")
    all_picks = full[mode].get("picks", [])
    return {
        "mode": mode,
        "picks": all_picks[5:],
        "total": len(all_picks),
    }


@router.get("/picks-status")
async def get_ai_picks_status():
    """Returns whether picks exist and if a background generation is in progress."""
    cached = get_cached("ai_picks_all")
    has_picks = cached is not None
    generated_at = None
    if has_picks:
        for mode in ("short", "long", "discovery"):
            entry = (cached or {}).get(mode, {})
            if entry:
                generated_at = entry.get("generated_at")
                break
    return {
        "has_picks": has_picks,
        "generating": _is_generating or _picks_lock.locked(),
        "generated_at": generated_at,
    }


@router.post("/refresh")
async def refresh_ai_picks():
    """
    Clear the picks cache and fire a background regeneration.
    Returns immediately — frontend can poll /ai/picks-status or just call /ai/picks-all
    (which will block until the new picks are ready).
    """
    delete_cached("ai_picks_all")
    delete_cached("ai_picks_all_full")
    for mode in ("short", "long", "discovery"):
        delete_cached(f"ai_picks_{mode}")
    asyncio.create_task(background_refresh_picks())
    return {"status": "refreshing", "message": "AI picks refresh started in background"}


@router.get("/analyze-all/{ticker}")
async def analyze_ticker_all(ticker: str):
    """Single-prompt analysis across all 3 horizons — 1 Claude call instead of 3."""
    try:
        now = datetime.now(pytz.timezone("US/Eastern"))
        next_trading_day_label, _ = _next_trading_day(now)
        market_data = await _build_market_snapshot()
        result = await ai_service.analyze_ticker_all_modes(
            ticker=ticker.upper().strip(),
            market_overview=market_data,
            next_trading_day_label=next_trading_day_label,
        )
        return result
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        msg = str(e)
        if "credit balance is too low" in msg or "billing" in msg.lower():
            raise HTTPException(402, "🪙 The AI's coin jar is empty! Claude tried to think but found tumbleweeds where the credits should be. Head to console.anthropic.com/settings/billing and toss in some tokens — the robot is hungry.")
        raise HTTPException(500, f"Ticker analysis failed: {e}")


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
