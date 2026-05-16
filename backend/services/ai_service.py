import os
import asyncio
import json
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=2)

# Module-level caches — keyed screening results survive across requests
_longterm_cache: Dict = {"ts": 0.0, "data": []}
_discovery_cache: Dict = {"ts": 0.0, "data": []}
_FUND_CACHE_TTL = 7200  # 2 hours — fundamentals don't change hourly


# ─── Anthropic client ────────────────────────────────────────────────────────

def _get_client():
    import anthropic
    from dotenv import load_dotenv
    # Use absolute path so this works regardless of server working directory
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(dotenv_path=_env_path, override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic(api_key=api_key)


# ─── Rate-limited gather ─────────────────────────────────────────────────────

async def _batch_gather(coros, batch_size: int = 5, delay: float = 0.8):
    """Run coroutines in small batches with a delay to avoid Yahoo Finance 429s."""
    results = []
    coro_list = list(coros)
    for i in range(0, len(coro_list), batch_size):
        batch = coro_list[i:i + batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        results.extend(batch_results)
        if i + batch_size < len(coro_list):
            await asyncio.sleep(delay)
    return results


# ─── Market regime ───────────────────────────────────────────────────────────

def assess_market_regime(market_overview: Dict) -> Dict:
    """Classify current market conditions to guide Haiku's trade type selection."""
    vix = market_overview.get("vix") or 20
    spy_c = market_overview.get("spy_change_pct") or 0
    qqq_c = market_overview.get("qqq_change_pct") or 0
    iwm_c = market_overview.get("iwm_change_pct") or 0
    avg_change = (spy_c + qqq_c + iwm_c) / 3

    if vix > 30:
        vix_regime = "extreme fear (VIX>30) — avoid momentum, look for oversold bounces only"
    elif vix > 20:
        vix_regime = "elevated fear (VIX 20-30) — reduced position sizes, favor reversals"
    elif vix < 13:
        vix_regime = "complacency (VIX<13) — momentum and breakouts work well"
    else:
        vix_regime = "normal (VIX 13-20) — all setups viable"

    if avg_change > 1.0:
        direction = "strong bullish — favor momentum and breakout longs"
    elif avg_change > 0.25:
        direction = "mild bullish — favor longs, avoid shorts"
    elif avg_change < -1.0:
        direction = "strong bearish — favor oversold bounces or avoid entirely"
    elif avg_change < -0.25:
        direction = "mild bearish — be selective, no chasing"
    else:
        direction = "flat/choppy — favor mean-reversion, avoid momentum chasing"

    sectors = market_overview.get("sector_performance", [])
    green = sum(1 for s in sectors if (s.get("change_pct") or 0) > 0)
    breadth = f"{green}/{len(sectors)} sectors green"

    top_sectors = [s["name"] for s in sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)[:3]]
    bot_sectors = [s["name"] for s in sorted(sectors, key=lambda x: x.get("change_pct", 0))[:2]]

    return {
        "vix": round(vix, 2),
        "vix_regime": vix_regime,
        "direction": direction,
        "avg_index_change": round(avg_change, 2),
        "breadth": breadth,
        "top_sectors": top_sectors,
        "weak_sectors": bot_sectors,
        "overall_bias": "bullish" if avg_change > 0.25 else ("bearish" if avg_change < -0.25 else "neutral"),
    }


# ─── ATR-based level computation ─────────────────────────────────────────────

def compute_atr_levels(price: float, atr: Optional[float]) -> Dict:
    """Compute stop-loss and targets using ATR — the standard day-trading approach."""
    if not atr or atr <= 0 or not price:
        # Percentage fallback when ATR isn't available
        risk = round(price * 0.02, 2)
        return {
            "entry_low": round(price * 0.998, 2),
            "entry_high": round(price * 1.003, 2),
            "stop_loss": round(price - risk, 2),
            "target_1r": round(price + risk, 2),
            "target_2r": round(price + risk * 2, 2),
            "risk_per_share": risk,
            "method": "2% fallback (no ATR)",
        }

    risk = round(atr * 1.5, 2)
    return {
        "entry_low": round(price - atr * 0.1, 2),
        "entry_high": round(price + atr * 0.2, 2),
        "stop_loss": round(price - risk, 2),
        "target_1r": round(price + risk, 2),
        "target_2r": round(price + risk * 2.0, 2),
        "risk_per_share": risk,
        "method": f"1.5x ATR (ATR=${atr:.2f})",
    }


# ─── Trade type detection ────────────────────────────────────────────────────

def detect_trade_type(result: Dict, ta: Optional[Dict], regime: Dict) -> str:
    rsi = (ta or {}).get("rsi_14")
    macd_hist = (ta or {}).get("macd_hist")
    change = result.get("change_pct", 0) or 0
    rel_vol = result.get("rel_volume", 1) or 1
    bias = regime.get("overall_bias", "neutral")

    if rsi and rsi < 32 and change < -2:
        return "bounce"
    if change > 4 and rel_vol > 2.5:
        return "breakout"
    if rsi and rsi > 55 and change > 1.5 and rel_vol > 1.8 and bias == "bullish":
        return "momentum"
    if macd_hist and macd_hist < 0 and rsi and rsi < 42:
        return "reversal"
    if rel_vol > 2 and abs(change) < 1.5:
        return "gap_fill"
    return "momentum"


# ─── Enhanced per-candidate scoring ──────────────────────────────────────────

def enhanced_score(result: Dict, ta: Optional[Dict], regime: Dict) -> float:
    score = result.get("score", 0)

    if ta:
        rsi = ta.get("rsi_14")
        macd_hist = ta.get("macd_hist")
        ema9 = ta.get("ema_9")
        ema21 = ta.get("ema_21")
        ema50 = ta.get("ema_50")
        price = ta.get("price") or 0
        vwap = ta.get("vwap")
        adx = ta.get("adx")
        stoch_k = ta.get("stoch_k")

        # RSI sweet spot (40–65 for momentum; <32 for bounces)
        if rsi:
            if 40 <= rsi <= 65:
                score += 2.0
            elif rsi < 32:
                score += 1.5
            elif rsi > 75:
                score -= 2.0

        # MACD histogram direction
        if macd_hist is not None:
            score += 1.5 if macd_hist > 0 else -1.0

        # EMA stack (bullish: ema9 > ema21 > ema50 or price)
        if ema9 and ema21:
            score += 1.0 if ema9 > ema21 else -0.5
        if ema50 and price and price > ema50:
            score += 0.5

        # VWAP — price above = institutional buying pressure
        if vwap and price and price > vwap:
            score += 1.0

        # Strong trend
        if adx and adx > 25:
            score += 1.0

        # Stochastic — not overbought
        if stoch_k and stoch_k > 80:
            score -= 1.0

    # Regime alignment
    bias = regime.get("overall_bias", "neutral")
    change = result.get("change_pct", 0) or 0
    if (bias == "bullish" and change > 0) or (bias == "bearish" and change < 0):
        score += 1.0

    # Volume confirmation
    rel_vol = result.get("rel_volume", 1) or 1
    if rel_vol > 3:
        score += 2.5
    elif rel_vol > 2:
        score += 1.5
    elif rel_vol > 1.5:
        score += 0.5

    return round(score, 2)


# ─── Pre-process candidates before sending to Haiku ─────────────────────────

async def preprocess_candidates(
    screener_results: List[Dict],
    regime: Dict,
    top_n: int = 6,
) -> List[Dict]:
    """
    Fetch full technicals for top screener candidates, compute ATR-based
    levels, enhanced scores, and trade types — so Haiku gets pre-digested data.
    """
    from services.technical_analysis import get_technical_signals

    # First pass: score with screener data only, take top_n * 2 for TA fetch
    candidates = sorted(screener_results, key=lambda x: x.get("score", 0), reverse=True)[:max(top_n * 2, 16)]

    # Reuse TA stored by the screener (avoids double Yahoo Finance fetch).
    # Fall back to a fresh fetch only for candidates where _ta is absent.
    ta_results: List = [r.get("_ta") for r in candidates]
    missing = [i for i, ta in enumerate(ta_results) if ta is None]
    if missing:
        fresh = await asyncio.gather(
            *[get_technical_signals(candidates[i]["ticker"], period="3mo", interval="1d") for i in missing],
            return_exceptions=True,
        )
        for idx, ta in zip(missing, fresh):
            ta_results[idx] = ta if isinstance(ta, dict) else None

    enriched = []
    for result, ta in zip(candidates, ta_results):
        ta_data = ta if isinstance(ta, dict) else None
        atr = ta_data.get("atr_14") if ta_data else None
        price = result.get("price") or (ta_data.get("price") if ta_data else 0)
        levels = compute_atr_levels(price, atr)
        trade_type = detect_trade_type(result, ta_data, regime)
        score = enhanced_score(result, ta_data, regime)

        # Build concise signal summary for prompt
        signals = []
        if ta_data:
            rsi = ta_data.get("rsi_14")
            macd_hist = ta_data.get("macd_hist")
            ema9 = ta_data.get("ema_9")
            ema21 = ta_data.get("ema_21")
            ema50 = ta_data.get("ema_50")
            adx = ta_data.get("adx")
            stoch_k = ta_data.get("stoch_k")
            vwap = ta_data.get("vwap")
            bb_pct = ta_data.get("bb_pct")

            if rsi:
                signals.append(f"RSI {rsi:.0f}{'(oversold)' if rsi < 30 else '(overbought)' if rsi > 70 else ''}")
            if macd_hist is not None:
                signals.append(f"MACD hist {'▲' if macd_hist > 0 else '▼'}{macd_hist:.3f}")
            if ema9 and ema21:
                signals.append(f"EMA9{'>' if ema9 > ema21 else '<'}EMA21")
            if ema50 and price:
                signals.append(f"Price{'>' if price > ema50 else '<'}EMA50")
            if adx:
                signals.append(f"ADX {adx:.0f}({'trending' if adx > 25 else 'ranging'})")
            if stoch_k:
                signals.append(f"Stoch {stoch_k:.0f}")
            if vwap and price:
                signals.append(f"{'Above' if price > vwap else 'Below'} VWAP")
            if bb_pct is not None:
                bb_pct_pct = bb_pct * 100
                if bb_pct_pct < 10:
                    signals.append("Near BB lower")
                elif bb_pct_pct > 90:
                    signals.append("Near BB upper")

        enriched.append({
            "ticker": result["ticker"],
            "name": result.get("name", result["ticker"]),
            "price": price,
            "change_pct": result.get("change_pct", 0),
            "rel_volume": result.get("rel_volume", 1),
            "sector": result.get("sector", ""),
            "market_cap": result.get("market_cap"),
            "rsi": ta_data.get("rsi_14") if ta_data else result.get("rsi"),
            "atr": atr,
            "enhanced_score": score,
            "trade_type": trade_type,
            "ta_signals": signals[:6],
            "ta_summary": (ta_data or {}).get("signal_summary", ""),
            "suggested_stop": levels["stop_loss"],
            "suggested_target": levels["target_2r"],
            "entry_low": levels["entry_low"],
            "entry_high": levels["entry_high"],
            "risk_per_share": levels["risk_per_share"],
            "level_method": levels["method"],
        })

    # Final sort by enhanced score
    enriched.sort(key=lambda x: x["enhanced_score"], reverse=True)
    return enriched[:top_n]


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_prompt(
    candidates: List[Dict],
    regime: Dict,
    market_overview: Dict,
    date_str: str,
    next_trading_day_label: str = "Tomorrow",
) -> str:
    regime_block = (
        f"VIX: {regime['vix']} — {regime['vix_regime']}\n"
        f"Market direction: {regime['direction']}\n"
        f"Breadth: {regime['breadth']}\n"
        f"Top sectors: {', '.join(regime['top_sectors'])}\n"
        f"Weak sectors: {', '.join(regime['weak_sectors'])}"
    )

    is_weekend = "Monday" in next_trading_day_label
    weekend_note = (
        f"\nNote: Markets are closed this weekend. All data reflects Friday's close. "
        f"You are preparing picks for {next_trading_day_label}'s open.\n"
        if is_weekend else ""
    )

    rows = []
    for i, c in enumerate(candidates, 1):
        rr = (c["suggested_target"] - c["price"]) / c["risk_per_share"] if c["risk_per_share"] > 0 else 0
        rows.append(
            f"#{i} {c['ticker']} — ${c['price']:.2f} | {c['change_pct']:+.1f}% | "
            f"RelVol:{c['rel_volume']:.1f}x | Score:{c['enhanced_score']:.1f} | "
            f"Setup:{c['trade_type'].upper()} | TA:{c['ta_summary']}\n"
            f"   Signals: {', '.join(c['ta_signals'])}\n"
            f"   Python-suggested: Entry ${c['entry_low']:.2f}-${c['entry_high']:.2f} | "
            f"Stop ${c['suggested_stop']:.2f} | Target ${c['suggested_target']:.2f} | "
            f"R/R 1:{rr:.1f} (via {c['level_method']})\n"
            f"   Sector: {c.get('sector','')}"
        )
    candidates_block = "\n".join(rows)

    return f"""You are an expert day trader. Today is {date_str}.{weekend_note}

Python analysis has already scored, ranked, and computed ATR-based entry/stop/target levels for the best candidates. Your job is to:
1. Select the BEST 8 from the list below (you may select fewer if the setups are weak — quality over quantity)
2. Validate or slightly adjust the Python-suggested price levels if needed
3. Write a specific 2-sentence thesis explaining WHY this ticker works for {next_trading_day_label}'s open based on the signals shown
4. Assign a realistic confidence score 1-10

=== MARKET REGIME ===
{regime_block}

=== PRE-ANALYZED CANDIDATES (ranked by composite score) ===
{candidates_block}

=== RULES ===
- Confidence above 7 only if: rel_vol > 2x AND TA confirms direction AND regime aligns
- Confidence 5-6 for mixed signals
- Never recommend a setup that goes against the market regime (e.g. no momentum longs in strong bearish regime)
- Stop loss must be BELOW entry for longs (these are all long setups)
- Thesis must reference specific signals from the data above (e.g. "RSI at 38 shows oversold conditions with MACD histogram turning positive")
- market_summary should mention {next_trading_day_label}'s open specifically

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on the current tape and what to expect at {next_trading_day_label}'s open",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "AAPL",
      "trade_type": "momentum",
      "entry_low": 185.00,
      "entry_high": 187.00,
      "stop_loss": 183.50,
      "target": 191.00,
      "risk_reward": "1:2.5",
      "confidence": 7,
      "thesis": "Specific reasoning citing the signals above."
    }}
  ],
  "avoid": ["TICKER1"],
  "avoid_reason": "Brief reason.",
  "generated_at": "{date_str}"
}}"""


# ─── Validate and clean Haiku output ─────────────────────────────────────────

def _validate_picks(picks_raw: List[Dict], candidates: List[Dict]) -> List[Dict]:
    """Fix common Haiku errors: stop above entry, bad R/R strings, missing fields."""
    candidate_map = {c["ticker"]: c for c in candidates}
    cleaned = []
    for i, p in enumerate(picks_raw):
        c = candidate_map.get(p.get("ticker", ""), {})
        entry = (p.get("entry_low", 0) + p.get("entry_high", 0)) / 2 or c.get("price", 0)
        stop = p.get("stop_loss") or c.get("suggested_stop", entry * 0.98)
        target = p.get("target") or c.get("suggested_target", entry * 1.04)

        # Fix inverted stop (stop must be below entry for longs)
        if stop >= entry:
            stop = c.get("suggested_stop", round(entry * 0.975, 2))

        # Fix inverted target (target must be above entry)
        if target <= entry:
            target = c.get("suggested_target", round(entry * 1.04, 2))

        risk = round(entry - stop, 2)
        reward = round(target - entry, 2)
        rr = f"1:{reward/risk:.1f}" if risk > 0 else "—"

        cleaned.append({
            "rank": i + 1,
            "ticker": p.get("ticker", ""),
            "trade_type": p.get("trade_type", c.get("trade_type", "momentum")),
            "entry_low": p.get("entry_low") or c.get("entry_low", entry),
            "entry_high": p.get("entry_high") or c.get("entry_high", entry),
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "risk_reward": rr,
            "confidence": max(1, min(10, int(p.get("confidence", 6)))),
            "thesis": p.get("thesis", ""),
        })
    return cleaned


# ─── Main entry point ─────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int = 1800) -> str:
    client = _get_client()
    model = os.getenv("AI_MODEL", "claude-haiku-4-5-20251001")
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _parse_response(raw: str) -> Dict:
    import re
    text = raw.strip()
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    # Regex: find largest {...} block (handles leading explanation text)
    matches = re.findall(r'\{[\s\S]*\}', text)
    for m in sorted(matches, key=len, reverse=True):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("No valid JSON found", text, 0)


async def generate_market_picks(
    market_overview: Dict,
    screener_results: List[Dict],
    date_str: str,
    next_trading_day_label: str = "Tomorrow",
    mode: str = "short",
) -> Dict:
    regime = assess_market_regime(market_overview)

    if mode == "long":
        candidates = await screen_longterm_candidates(top_n=10)
        if not candidates:
            return {"error": "No candidates", "picks": [], "market_summary": "Insufficient data.",
                    "bias": "neutral", "avoid": [], "avoid_reason": "", "generated_at": date_str}
        prompt = _build_longterm_prompt(candidates, market_overview, date_str)
    elif mode == "discovery":
        candidates = await screen_discovery_candidates(top_n=10)
        if not candidates:
            return {"error": "No candidates", "picks": [], "market_summary": "Insufficient data.",
                    "bias": "neutral", "avoid": [], "avoid_reason": "", "generated_at": date_str}
        prompt = _build_discovery_prompt(candidates, date_str)
    else:
        candidates = await preprocess_candidates(screener_results, regime, top_n=8)
        if not candidates:
            return {"error": "No candidates found from screener", "picks": [], "market_summary": "Insufficient data.",
                    "bias": regime["overall_bias"], "avoid": [], "avoid_reason": "", "generated_at": date_str}
        prompt = _build_prompt(candidates, regime, market_overview, date_str, next_trading_day_label)

    loop = asyncio.get_running_loop()
    # Long/discovery prompts need more tokens: 8 picks × thesis text easily exceeds 1800
    tokens = 2800 if mode in ("long", "discovery") else 1800
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=tokens))

    try:
        result = _parse_response(raw)
        result["picks"] = _validate_picks(result.get("picks", []), candidates)
        result["bias"] = result.get("bias") or regime["overall_bias"]
        result["regime"] = regime
        return result
    except json.JSONDecodeError as e:
        return {
            "error": f"JSON parse failed: {e}",
            "picks": [], "market_summary": "Analysis temporarily unavailable.",
            "bias": regime["overall_bias"], "avoid": [], "avoid_reason": "",
            "generated_at": date_str, "regime": regime,
        }


# ─── Long-term universe + screening ──────────────────────────────────────────

# Curated pool of individual stocks — the kind you'd actually hold 6-12 months.
# ETFs are intentionally excluded: SPY/QQQ/etc. are baskets, not individual businesses,
# and their fundamentals (P/E, revenue) are meaningless at the fund level.
LONGTERM_UNIVERSE = [
    # Mega-cap tech / AI
    "AAPL", "MSFT", "GOOGL", "NVDA", "META", "AMZN", "TSLA", "AMD",
    "AVGO", "ORCL", "CRM", "ADBE", "NOW", "QCOM", "NFLX",
    # Healthcare
    "UNH", "LLY", "ABBV", "JNJ", "MRK", "TMO", "ISRG", "ABT",
    # Financials
    "JPM", "BAC", "GS", "V", "MA", "AXP",
    # Consumer staples / discretionary
    "PG", "KO", "PEP", "WMT", "COST", "MCD", "NKE",
    # Industrials / Energy
    "CAT", "HON", "XOM", "CVX",
    # Other quality
    "UBER", "DIS", "SPOT", "COIN",
]


def _score_longterm(fund: Dict, price: float) -> float:
    """Score a stock for long-term holding quality. Higher = better fundamental profile."""
    score = 0.0

    # Revenue growth — most important signal of business momentum
    rev = fund.get("revenue_growth")
    if rev is not None:
        if rev > 0.25:    score += 6
        elif rev > 0.15:  score += 4
        elif rev > 0.05:  score += 2
        elif rev > 0:     score += 1
        else:             score -= 3

    # Earnings growth
    earn = fund.get("earnings_growth")
    if earn is not None:
        if earn > 0.20:   score += 4
        elif earn > 0.10: score += 2
        elif earn > 0:    score += 1
        else:             score -= 1

    # PEG ratio — best single "growth at reasonable price" metric
    peg = fund.get("peg_ratio")
    if peg is not None and peg > 0:
        if peg < 1.0:     score += 5
        elif peg < 1.5:   score += 3
        elif peg < 2.5:   score += 1
        elif peg > 3.5:   score -= 2

    # Forward P/E — valuation sanity check
    fwd_pe = fund.get("forward_pe")
    if fwd_pe is not None and fwd_pe > 0:
        if 10 <= fwd_pe <= 20:  score += 3
        elif 20 < fwd_pe <= 35: score += 1
        elif fwd_pe > 60:       score -= 2

    # Profit margin — quality of business
    margin = fund.get("profit_margin")
    if margin is not None:
        if margin > 0.25:   score += 4
        elif margin > 0.15: score += 2
        elif margin > 0.05: score += 1
        elif margin < 0:    score -= 4

    # ROE — how well management uses capital
    roe = fund.get("roe")
    if roe is not None:
        if roe > 0.30:   score += 3
        elif roe > 0.15: score += 2
        elif roe > 0.05: score += 1
        elif roe < 0:    score -= 2

    # Free cash flow — separates real earnings from accounting
    fcf = fund.get("free_cashflow")
    if fcf is not None:
        score += 2 if fcf > 0 else -2

    # Debt/Equity — balance sheet health
    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 30:    score += 2
        elif de < 80:  score += 1
        elif de > 200: score -= 2

    return round(score, 2)


async def screen_longterm_candidates(top_n: int = 8) -> List[Dict]:
    """
    Fetch fundamentals for the curated universe via Finnhub (no Yahoo 429 risk),
    score on fundamental quality, cache for 2 hours. Returns top N candidates.
    """
    now = time.time()
    if _longterm_cache["ts"] and (now - _longterm_cache["ts"]) < _FUND_CACHE_TTL and _longterm_cache["data"]:
        return _longterm_cache["data"][:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in LONGTERM_UNIVERSE], batch_size=5, delay=0.8)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in LONGTERM_UNIVERSE], batch_size=3, delay=0.5)

    candidates = []
    for ticker, quote, fund in zip(LONGTERM_UNIVERSE, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund if isinstance(fund, dict) else {}
        price = q.get("price") or 0
        if not price:
            continue

        score = _score_longterm(f, price)

        # Wide long-term levels: ±3% entry, 15% stop, 25% target
        entry_low  = round(price * 0.97, 2)
        entry_high = round(price * 1.03, 2)
        stop_loss  = round(price * 0.85, 2)
        target     = round(price * 1.25, 2)
        rr = round((target - price) / max(price - stop_loss, 0.01), 1)

        # Build a concise fundamental summary line for the Claude prompt
        parts = []
        if f.get("pe_ratio"):                    parts.append(f"P/E {f['pe_ratio']:.1f}")
        if f.get("forward_pe"):                   parts.append(f"FwdP/E {f['forward_pe']:.1f}")
        if f.get("peg_ratio"):                    parts.append(f"PEG {f['peg_ratio']:.2f}")
        if f.get("revenue_growth") is not None:   parts.append(f"RevGrowth {f['revenue_growth']*100:.1f}%")
        if f.get("earnings_growth") is not None:  parts.append(f"EPSGrowth {f['earnings_growth']*100:.1f}%")
        if f.get("profit_margin") is not None:    parts.append(f"Margin {f['profit_margin']*100:.1f}%")
        if f.get("roe") is not None:              parts.append(f"ROE {f['roe']*100:.1f}%")
        if f.get("debt_to_equity") is not None:   parts.append(f"D/E {f['debt_to_equity']:.0f}")
        if f.get("free_cashflow"):
            fcf = f["free_cashflow"]
            parts.append(f"FCF {'${:.1f}B'.format(fcf/1e9) if abs(fcf) >= 1e9 else '${:.0f}M'.format(fcf/1e6)}")

        candidates.append({
            "ticker": ticker,
            "name": q.get("name", ticker),
            "price": price,
            "sector": q.get("sector", ""),
            "fund_summary": " | ".join(parts) if parts else "Limited data",
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "target": target,
            "rr": rr,
            "score": score,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    _longterm_cache["ts"] = time.time()
    _longterm_cache["data"] = candidates
    return candidates[:top_n]


# ─── Long-term prompt builder ─────────────────────────────────────────────────

def _build_longterm_prompt(
    candidates: List[Dict],
    market_overview: Dict,
    date_str: str,
) -> str:
    rows = []
    for i, c in enumerate(candidates, 1):
        rows.append(
            f"#{i} {c['ticker']} ({c['name']}) — ${c['price']:.2f} | Sector: {c.get('sector', '')}\n"
            f"   Fundamentals: {c['fund_summary']}\n"
            f"   Suggested: Entry ${c['entry_low']:.2f}–${c['entry_high']:.2f} | "
            f"Stop ${c['stop_loss']:.2f} | 12mo Target ${c['target']:.2f} | R/R 1:{c['rr']}"
        )
    candidates_block = "\n".join(rows)
    spy_c = market_overview.get("spy_change_pct", 0)
    vix = market_overview.get("vix", 20)

    return f"""You are an expert long-term growth and value investor. Today is {date_str}.

Evaluate these stocks as 6–12 month conviction plays. Focus on business quality, fundamentals, and valuation — NOT short-term price action.

=== MACRO CONTEXT ===
SPY: {spy_c:+.1f}% | VIX: {vix:.1f}

=== CANDIDATES ===
{candidates_block}

=== YOUR JOB ===
1. Select the BEST 8 candidates for a 6–12 month hold (fewer is fine if quality is low)
2. Set realistic levels:
   - Entry zone: current price ±3% (accumulate over 1–2 weeks, NOT a one-day trade)
   - Stop loss: major weekly support, 10–20% below entry
   - Target: realistic 12-month price target (15–40% upside is typical)
3. Write a 2-sentence thesis on WHY this is a good business to own for 12 months
4. Confidence 8–10: strong growth + reasonable valuation + clear catalyst. Below 6: don't recommend.

RULES:
- Thesis must reference fundamental factors (revenue growth, P/E vs peers, moat, margin expansion)
- market_summary must discuss the macro backdrop for LONG-TERM investing, not day trading
- trade_type must be one of: growth, value, dividend, turnaround

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on macro conditions and whether now is a good time to build long-term positions",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "AAPL",
      "trade_type": "growth",
      "entry_low": 185.00,
      "entry_high": 191.00,
      "stop_loss": 162.00,
      "target": 235.00,
      "risk_reward": "1:2.5",
      "confidence": 7,
      "thesis": "2 sentences citing specific fundamental data."
    }}
  ],
  "avoid": ["TICKER1"],
  "avoid_reason": "Brief fundamental reason to avoid.",
  "generated_at": "{date_str}"
}}"""


# ─── Single-ticker analysis ───────────────────────────────────────────────────

def _compute_theoretical(entry_low: float, entry_high: float, stop: float, target: float, investment: float = 1000) -> Dict:
    entry_mid = (entry_low + entry_high) / 2
    if entry_mid <= 0:
        return {}
    shares = investment / entry_mid
    profit = round(shares * (target - entry_mid), 2)
    risk_amt = round(shares * (entry_mid - stop), 2)
    return_pct = round((profit / investment) * 100, 2)
    return {
        "investment": investment,
        "shares": round(shares, 3),
        "profit_target": profit,
        "risk_amount": risk_amt,
        "return_pct": return_pct,
    }


async def analyze_ticker(
    ticker: str,
    market_overview: Dict,
    next_trading_day_label: str = "Tomorrow",
    mode: str = "short",
) -> Dict:
    if mode == "long":
        return await _analyze_ticker_longterm(ticker)
    if mode == "discovery":
        return await _analyze_ticker_discovery(ticker)
    # ─── short-term path below ────
    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc

    regime = assess_market_regime(market_overview)

    quote, ta = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="3mo", interval="1d"),
        return_exceptions=True,
    )

    quote_data = quote if isinstance(quote, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}

    price = quote_data.get("price") or ta_data.get("price") or 0
    name = quote_data.get("name", ticker)
    change_pct = quote_data.get("change_pct", 0) or 0
    sector = quote_data.get("sector", "")

    if not price:
        return {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}

    atr = ta_data.get("atr_14")
    levels = compute_atr_levels(price, atr)

    # Build signals list for prompt
    signals = []
    if ta_data:
        rsi = ta_data.get("rsi_14")
        macd_hist = ta_data.get("macd_hist")
        ema9 = ta_data.get("ema_9")
        ema21 = ta_data.get("ema_21")
        ema50 = ta_data.get("ema_50")
        adx = ta_data.get("adx")
        stoch_k = ta_data.get("stoch_k")
        vwap = ta_data.get("vwap")
        bb_pct = ta_data.get("bb_pct")

        if rsi: signals.append(f"RSI {rsi:.0f}{'(oversold)' if rsi < 30 else '(overbought)' if rsi > 70 else ''}")
        if macd_hist is not None: signals.append(f"MACD hist {'▲' if macd_hist > 0 else '▼'}{abs(macd_hist):.3f}")
        if ema9 and ema21: signals.append(f"EMA9 {'>' if ema9 > ema21 else '<'} EMA21")
        if ema50 and price: signals.append(f"Price {'>' if price > ema50 else '<'} EMA50")
        if adx: signals.append(f"ADX {adx:.0f} ({'trending' if adx > 25 else 'ranging'})")
        if stoch_k: signals.append(f"Stoch {stoch_k:.0f}")
        if vwap and price: signals.append(f"{'Above' if price > vwap else 'Below'} VWAP")
        if bb_pct is not None:
            if bb_pct * 100 < 10: signals.append("Near BB lower band")
            elif bb_pct * 100 > 90: signals.append("Near BB upper band")

    ta_summary = ta_data.get("signal_summary", "")
    rr_est = round((levels["target_2r"] - price) / levels["risk_per_share"], 1) if levels["risk_per_share"] > 0 else 0
    signals_str = ", ".join(signals) or "Limited technical data"

    is_weekend = "Monday" in next_trading_day_label
    context_note = (
        f"Note: Markets are closed this weekend. Data reflects the most recent close."
        if is_weekend else
        f"Note: Using most recent available price and indicator data."
    )

    prompt = f"""You are an expert day trader. {context_note}
Analyze {ticker} ({name}) and decide: BUY, HOLD, or AVOID for {next_trading_day_label}'s open.

Stock data:
- Price: ${price:.2f} | Day change: {change_pct:+.1f}% | Sector: {sector}
- TA summary: {ta_summary}
- Signals: {signals_str}
- Python-suggested Entry: ${levels['entry_low']:.2f} – ${levels['entry_high']:.2f}
- Python-suggested Stop: ${levels['stop_loss']:.2f}
- Python-suggested Target: ${levels['target_2r']:.2f}
- Est. R/R: 1:{rr_est} ({levels['method']})

Market regime:
- Bias: {regime['overall_bias']} | VIX: {regime['vix']} ({regime['vix_regime']})
- Direction: {regime['direction']}

Decision criteria:
- BUY: setup is clear, TA signals align with regime, risk/reward is acceptable
- HOLD: mixed signals or unclear setup — wait for confirmation at the open
- AVOID: weak/broken setup or trade goes against market regime

Respond ONLY with valid JSON, no markdown:
{{
  "ticker": "{ticker}",
  "recommendation": "buy",
  "trade_type": "momentum",
  "entry_low": {levels['entry_low']},
  "entry_high": {levels['entry_high']},
  "stop_loss": {levels['stop_loss']},
  "target": {levels['target_2r']},
  "risk_reward": "1:{rr_est}",
  "confidence": 6,
  "thesis": "2 sentences citing specific signals explaining your BUY/HOLD/AVOID call for {next_trading_day_label}."
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, _call_claude, prompt)

    try:
        result = _parse_response(raw)
    except json.JSONDecodeError:
        result = {
            "ticker": ticker,
            "recommendation": "hold",
            "trade_type": "unknown",
            "entry_low": levels["entry_low"],
            "entry_high": levels["entry_high"],
            "stop_loss": levels["stop_loss"],
            "target": levels["target_2r"],
            "risk_reward": f"1:{rr_est}",
            "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
        }

    # Ensure stop is below entry for longs
    el = result.get("entry_low", levels["entry_low"])
    eh = result.get("entry_high", levels["entry_high"])
    stop = result.get("stop_loss", levels["stop_loss"])
    target = result.get("target", levels["target_2r"])
    entry_mid = (el + eh) / 2
    if stop >= entry_mid:
        stop = levels["stop_loss"]
    if target <= entry_mid:
        target = levels["target_2r"]
    result["stop_loss"] = round(stop, 2)
    result["target"] = round(target, 2)

    result["next_trading_day"] = next_trading_day_label
    result["theoretical"] = _compute_theoretical(el, eh, stop, target, investment=1000)
    return result


# ─── Long-term single-ticker analysis ────────────────────────────────────────

async def _analyze_ticker_longterm(ticker: str) -> Dict:
    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote, ta, fund = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="1y", interval="1wk"),
        finnhub_service.get_fundamentals_mapped(ticker),
        return_exceptions=True,
    )

    quote_data = quote if isinstance(quote, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}

    price = quote_data.get("price") or ta_data.get("price") or 0
    name = quote_data.get("name", ticker)
    sector = quote_data.get("sector", "")

    if not price:
        return {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}

    entry_low = round(price * 0.97, 2)
    entry_high = round(price * 1.03, 2)
    stop_loss = round(price * 0.85, 2)
    target = round(price * 1.25, 2)
    ema50 = ta_data.get("ema_50")
    if ema50 and ema50 < price * 0.92:
        stop_loss = round(ema50 * 0.97, 2)
    rr = round((target - price) / max(price - stop_loss, 0.01), 1)

    def _pct(v, label):
        return f"{label}: {v*100:.1f}%" if v is not None else None

    fund_lines = [x for x in [
        f"Trailing P/E: {fund_data['pe_ratio']:.1f}" if fund_data.get("pe_ratio") else None,
        f"Forward P/E: {fund_data['forward_pe']:.1f}" if fund_data.get("forward_pe") else None,
        f"PEG ratio: {fund_data['peg_ratio']:.2f}" if fund_data.get("peg_ratio") else None,
        _pct(fund_data.get("revenue_growth"), "Revenue growth YoY"),
        _pct(fund_data.get("earnings_growth"), "EPS growth YoY"),
        _pct(fund_data.get("profit_margin"), "Profit margin"),
        _pct(fund_data.get("gross_margins"), "Gross margin"),
        _pct(fund_data.get("roe"), "ROE"),
        f"Debt/Equity: {fund_data['debt_to_equity']:.1f}" if fund_data.get("debt_to_equity") is not None else None,
        f"Dividend yield: {fund_data['dividend_yield']*100:.1f}%" if fund_data.get("dividend_yield") else None,
        f"Free cash flow: ${fund_data['free_cashflow']/1e9:.1f}B" if fund_data.get("free_cashflow") else None,
    ] if x]
    fund_str = "\n".join(fund_lines) if fund_lines else "Fundamental data not available for this ticker."

    prompt = f"""You are an expert long-term investor. Analyze {ticker} ({name}) for a 6–12 month hold.

Stock: {ticker} | Price: ${price:.2f} | Sector: {sector}

FUNDAMENTALS:
{fund_str}

Decide: BUY (accumulate over 1–2 weeks), HOLD (wait for better conditions or entry), or AVOID (business concerns).

BUY criteria: positive revenue growth + healthy margins + reasonable valuation + clear long-term catalyst
HOLD criteria: good business but currently expensive, or unclear direction
AVOID criteria: declining revenue, margin compression, excessive debt, or structural headwinds

Suggested entry: ${entry_low:.2f}–${entry_high:.2f} (accumulate, not a one-day fill)
Suggested stop: ${stop_loss:.2f} (major weekly support — this is a wide long-term stop)
Suggested 12-month target: ${target:.2f} (adjust if your analysis suggests otherwise)
Est. R/R: 1:{rr}

Write a thesis that cites SPECIFIC fundamental data from above. Do not reference RSI, MACD, or day-trading signals.

Respond ONLY with valid JSON, no markdown:
{{
  "ticker": "{ticker}",
  "recommendation": "buy",
  "trade_type": "growth",
  "entry_low": {entry_low},
  "entry_high": {entry_high},
  "stop_loss": {stop_loss},
  "target": {target},
  "risk_reward": "1:{rr}",
  "confidence": 7,
  "thesis": "2 sentences citing specific fundamental data explaining the long-term BUY/HOLD/AVOID call."
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, _call_claude, prompt)

    try:
        result = _parse_response(raw)
    except json.JSONDecodeError:
        result = {
            "ticker": ticker, "recommendation": "hold", "trade_type": "growth",
            "entry_low": entry_low, "entry_high": entry_high, "stop_loss": stop_loss,
            "target": target, "risk_reward": f"1:{rr}", "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
        }

    el = result.get("entry_low", entry_low)
    eh = result.get("entry_high", entry_high)
    stop = result.get("stop_loss", stop_loss)
    tgt = result.get("target", target)
    mid = (el + eh) / 2
    if stop >= mid: stop = stop_loss
    if tgt <= mid: tgt = target
    result["stop_loss"] = round(stop, 2)
    result["target"] = round(tgt, 2)
    result["next_trading_day"] = "Long-term (6–12 months)"
    result["theoretical"] = _compute_theoretical(el, eh, stop, tgt, investment=1000)
    return result


# ─── Discovery universe (10+ year speculative plays) ─────────────────────────

# Small/mid-cap individual disruptors with genuine 10-year thesis potential.
# ETFs are excluded — they are baskets and their fund-level fundamentals
# are meaningless for the kind of 10-year disruptive thesis we want here.
DISCOVERY_UNIVERSE = [
    # AI & data infrastructure
    "PLTR", "NET", "DDOG", "SNOW", "MDB", "GTLB", "PATH", "SOUN", "AI",
    # Cybersecurity
    "S", "ZS",
    # Fintech disruptors
    "SOFI", "NU", "AFRM", "HOOD", "UPST",
    # Space & deep tech
    "RKLB", "ASTS", "IONQ",
    # Clean energy
    "ENPH", "FSLR", "ARRY",
    # Consumer disruptors
    "DUOL", "CAVA", "ONON", "CELH", "BROS",
    # Biotech / gene editing
    "RXRX", "CRSP", "BEAM",
    # Platform / social
    "RDDT",
    # International growth
    "GRAB", "SE",
    # EV / autonomous
    "RIVN",
]


def _score_discovery(fund: Dict, price: float) -> float:
    """Score a stock for 10+ year disruptive potential. Revenue growth dominates."""
    score = 0.0

    # Revenue growth — the single most important metric for a discovery pick
    rev = fund.get("revenue_growth")
    if rev is not None:
        if rev > 0.40:    score += 8
        elif rev > 0.25:  score += 6
        elif rev > 0.15:  score += 3
        elif rev > 0.05:  score += 1
        else:             score -= 5  # declining revenue kills the thesis

    # Gross margin — distinguishes software/platform from commodity businesses
    gm = fund.get("gross_margins")
    if gm is not None:
        if gm > 0.70:   score += 5
        elif gm > 0.50: score += 3
        elif gm > 0.30: score += 1
        elif gm < 0.20: score -= 2

    # Earnings growth — positive trajectory matters even if still unprofitable
    earn = fund.get("earnings_growth")
    if earn is not None:
        if earn > 0.50:    score += 4
        elif earn > 0.20:  score += 2
        elif earn > 0:     score += 1
        elif earn < -0.20: score -= 2

    # FCF — positive means self-funding; negative is acceptable for high-growth names
    fcf = fund.get("free_cashflow")
    if fcf is not None:
        score += 3 if fcf > 0 else 0

    # D/E — excessive leverage is deadly for volatile growth companies
    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 30:    score += 1
        elif de > 200: score -= 3

    return round(score, 2)


async def screen_discovery_candidates(top_n: int = 8) -> List[Dict]:
    """Fetch Finnhub fundamentals for the discovery universe, cache 2 hours, return top scored candidates."""
    now = time.time()
    if _discovery_cache["ts"] and (now - _discovery_cache["ts"]) < _FUND_CACHE_TTL and _discovery_cache["data"]:
        return _discovery_cache["data"][:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in DISCOVERY_UNIVERSE], batch_size=5, delay=0.8)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in DISCOVERY_UNIVERSE], batch_size=3, delay=0.5)

    candidates = []
    for ticker, quote, fund in zip(DISCOVERY_UNIVERSE, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund if isinstance(fund, dict) else {}
        price = q.get("price") or 0
        if not price:
            continue

        score = _score_discovery(f, price)

        # Wide levels — 35% stop, 2.5x (150%) target over 5–10 years
        entry_low  = round(price * 0.95, 2)
        entry_high = round(price * 1.05, 2)
        stop_loss  = round(price * 0.65, 2)
        target     = round(price * 2.50, 2)
        rr = round((target - price) / max(price - stop_loss, 0.01), 1)

        parts = []
        if f.get("revenue_growth") is not None:  parts.append(f"RevGrowth {f['revenue_growth']*100:.1f}%")
        if f.get("gross_margins") is not None:   parts.append(f"GrossMargin {f['gross_margins']*100:.1f}%")
        if f.get("earnings_growth") is not None: parts.append(f"EPSGrowth {f['earnings_growth']*100:.1f}%")
        if f.get("profit_margin") is not None:   parts.append(f"NetMargin {f['profit_margin']*100:.1f}%")
        if f.get("free_cashflow"):
            fcf = f["free_cashflow"]
            parts.append(f"FCF {'${:.1f}B'.format(fcf/1e9) if abs(fcf) >= 1e9 else '${:.0f}M'.format(fcf/1e6)}")
        if f.get("debt_to_equity") is not None:  parts.append(f"D/E {f['debt_to_equity']:.0f}")

        candidates.append({
            "ticker": ticker,
            "name": q.get("name", ticker),
            "price": price,
            "sector": q.get("sector", ""),
            "fund_summary": " | ".join(parts) if parts else "Limited data",
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "target": target,
            "rr": rr,
            "score": score,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    _discovery_cache["ts"] = time.time()
    _discovery_cache["data"] = candidates
    return candidates[:top_n]


def _build_discovery_prompt(candidates: List[Dict], date_str: str) -> str:
    rows = []
    for i, c in enumerate(candidates, 1):
        rows.append(
            f"#{i} {c['ticker']} ({c['name']}) — ${c['price']:.2f} | Sector: {c.get('sector', '')}\n"
            f"   Growth metrics: {c['fund_summary']}\n"
            f"   Suggested: Entry ${c['entry_low']:.2f}–${c['entry_high']:.2f} | "
            f"Stop ${c['stop_loss']:.2f} (35% below) | 10-Year Target ${c['target']:.2f} (2.5x) | R/R 1:{c['rr']}"
        )
    candidates_block = "\n".join(rows)

    return f"""You are an expert venture-minded long-term investor. Today is {date_str}.

Your goal: identify companies that could be 10x in 10 years — the next Google, Amazon, or Netflix.
These are speculative long-term holds, NOT short-term trades. Volatility is expected and acceptable.

For each pick, think about:
- What market are they disrupting and how large is that opportunity?
- Do they have a defensible advantage (network effects, switching costs, data moat, platform flywheel)?
- Is revenue growing fast enough to dominate their market in 10 years?
- Even if unprofitable today, is there a credible path to dominant profitability at scale?

=== CANDIDATES (ranked by growth quality score) ===
{candidates_block}

=== YOUR JOB ===
1. Select the BEST 8 from the list for a 10+ year speculative conviction hold (fewer is fine if the thesis is weak)
2. Adjust price targets if warranted — be bold, 3x–10x is realistic for true disruptors
3. Write a 2-sentence thesis on WHY this company could dominate its market in a decade — cite specific growth metrics
4. Confidence 8–10: clear disruption path + proven revenue growth + massive TAM. Below 6 = don't recommend.

RULES:
- trade_type must be one of: disruptor, platform, deep-tech, speculative
- market_summary must address whether current macro conditions are favorable for building long-horizon growth positions
- Stop losses should remain wide (30–40%) — these positions are held through volatility, not day-traded
- Do NOT reference day-trading concepts like RSI, MACD, or short-term momentum

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on whether now is a good time to accumulate 10-year growth positions",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "PLTR",
      "trade_type": "disruptor",
      "entry_low": 85.00,
      "entry_high": 95.00,
      "stop_loss": 60.00,
      "target": 250.00,
      "risk_reward": "1:6",
      "confidence": 8,
      "thesis": "2 sentences citing specific growth metrics and explaining why this company wins the next decade."
    }}
  ],
  "avoid": ["TICKER1"],
  "avoid_reason": "Brief reason: weak thesis, declining revenue, or high execution risk.",
  "generated_at": "{date_str}"
}}"""


async def analyze_ticker_all_modes(
    ticker: str,
    market_overview: Dict,
    next_trading_day_label: str = "Tomorrow",
) -> Dict:
    """
    Single-prompt analysis covering all 3 horizons at once — 1 Claude API call
    instead of 3 sequential calls.  Returns {"short": {...}, "long": {...}, "discovery": {...}}.
    """
    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    # Fetch all data concurrently
    quote, ta, fund = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="1y", interval="1d"),
        finnhub_service.get_fundamentals_mapped(ticker),
        return_exceptions=True,
    )

    quote_data = quote if isinstance(quote, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}

    price = quote_data.get("price") or ta_data.get("price") or 0
    name = quote_data.get("name", ticker)
    sector = quote_data.get("sector", "")

    if not price:
        err = {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}
        return {"short": err, "long": err, "discovery": err}

    regime = assess_market_regime(market_overview)

    # Short-term levels (ATR-based)
    atr = ta_data.get("atr_14")
    short_levels = compute_atr_levels(price, atr)

    # Long-term levels (wider)
    ema50 = ta_data.get("ema_50")
    long_stop = round(ema50 * 0.97, 2) if ema50 and ema50 < price * 0.92 else round(price * 0.85, 2)
    long_levels = {
        "entry_low": round(price * 0.97, 2), "entry_high": round(price * 1.03, 2),
        "stop_loss": long_stop, "target": round(price * 1.25, 2),
    }
    long_rr = round((long_levels["target"] - price) / max(price - long_levels["stop_loss"], 0.01), 1)

    # Discovery levels (very wide)
    disc_levels = {
        "entry_low": round(price * 0.95, 2), "entry_high": round(price * 1.05, 2),
        "stop_loss": round(price * 0.65, 2), "target": round(price * 2.50, 2),
    }
    disc_rr = round((disc_levels["target"] - price) / max(price - disc_levels["stop_loss"], 0.01), 1)

    # TA signals string
    signals = []
    if ta_data:
        rsi = ta_data.get("rsi_14")
        macd_hist = ta_data.get("macd_hist")
        ema9 = ta_data.get("ema_9"); ema21 = ta_data.get("ema_21")
        adx = ta_data.get("adx"); vwap = ta_data.get("vwap"); stoch_k = ta_data.get("stoch_k")
        if rsi: signals.append(f"RSI {rsi:.0f}{'(oversold)' if rsi < 30 else '(overbought)' if rsi > 70 else ''}")
        if macd_hist is not None: signals.append(f"MACD {'▲' if macd_hist > 0 else '▼'}{abs(macd_hist):.3f}")
        if ema9 and ema21: signals.append(f"EMA9{'>' if ema9 > ema21 else '<'}EMA21")
        if adx: signals.append(f"ADX {adx:.0f}")
        if vwap and price: signals.append(f"{'above' if price > vwap else 'below'} VWAP")
        if stoch_k: signals.append(f"Stoch {stoch_k:.0f}")

    def _pct(v, label): return f"{label}: {v*100:.1f}%" if v is not None else None
    fund_lines = [x for x in [
        f"P/E: {fund_data['pe_ratio']:.1f}" if fund_data.get("pe_ratio") else None,
        _pct(fund_data.get("revenue_growth"), "RevGrowth"),
        _pct(fund_data.get("gross_margins"), "GrossMargin"),
        _pct(fund_data.get("profit_margin"), "NetMargin"),
        _pct(fund_data.get("roe"), "ROE"),
        f"D/E: {fund_data['debt_to_equity']:.0f}" if fund_data.get("debt_to_equity") is not None else None,
        f"FCF: ${fund_data['free_cashflow']/1e9:.1f}B" if fund_data.get("free_cashflow") else None,
    ] if x]
    fund_str = " | ".join(fund_lines) if fund_lines else "Fundamental data limited"

    short_rr = round((short_levels["target_2r"] - price) / short_levels["risk_per_share"], 1) if short_levels["risk_per_share"] > 0 else 0

    prompt = f"""You are a multi-timeframe expert analyst. Analyze {ticker} ({name}) across 3 investment horizons simultaneously.

STOCK: {ticker} | Price: ${price:.2f} | Sector: {sector}
TA SIGNALS: {', '.join(signals) or 'limited data'} | Summary: {ta_data.get('signal_summary', '')}
FUNDAMENTALS: {fund_str}
MARKET: Bias {regime['overall_bias']} | VIX {regime['vix']} — {regime['vix_regime']}

━━━ HORIZON 1: DAY TRADING (for {next_trading_day_label}'s open) ━━━
Entry: ${short_levels['entry_low']:.2f}–${short_levels['entry_high']:.2f} | Stop: ${short_levels['stop_loss']:.2f} | Target: ${short_levels['target_2r']:.2f} | R/R 1:{short_rr}
Decision criteria: BUY if TA signals align and regime supports it. HOLD if mixed. AVOID if setup is broken.

━━━ HORIZON 2: LONG-TERM (6–12 months) ━━━
Entry: ${long_levels['entry_low']:.2f}–${long_levels['entry_high']:.2f} | Stop: ${long_levels['stop_loss']:.2f} | Target: ${long_levels['target']:.2f} | R/R 1:{long_rr}
Decision criteria: BUY if fundamentals are strong and valuation is reasonable. HOLD if good but expensive. AVOID if declining revenue or margins.

━━━ HORIZON 3: 10-YEAR DISCOVERY ━━━
Entry: ${disc_levels['entry_low']:.2f}–${disc_levels['entry_high']:.2f} | Stop: ${disc_levels['stop_loss']:.2f} | Target: ${disc_levels['target']:.2f} (2.5x) | R/R 1:{disc_rr}
Decision criteria: BUY if this company could dominate its market in 10 years. HOLD if interesting but unclear. AVOID if no defensible moat or declining growth.

For each horizon write a 2-sentence thesis citing specific data (TA signals for short-term, fundamentals for long/discovery).

Respond ONLY with valid JSON, no markdown:
{{
  "short": {{
    "ticker": "{ticker}", "recommendation": "buy", "trade_type": "momentum",
    "entry_low": {short_levels['entry_low']}, "entry_high": {short_levels['entry_high']},
    "stop_loss": {short_levels['stop_loss']}, "target": {short_levels['target_2r']},
    "risk_reward": "1:{short_rr}", "confidence": 6,
    "thesis": "2 sentences citing TA signals."
  }},
  "long": {{
    "ticker": "{ticker}", "recommendation": "hold", "trade_type": "growth",
    "entry_low": {long_levels['entry_low']}, "entry_high": {long_levels['entry_high']},
    "stop_loss": {long_levels['stop_loss']}, "target": {long_levels['target']},
    "risk_reward": "1:{long_rr}", "confidence": 6,
    "thesis": "2 sentences citing fundamental data."
  }},
  "discovery": {{
    "ticker": "{ticker}", "recommendation": "hold", "trade_type": "disruptor",
    "entry_low": {disc_levels['entry_low']}, "entry_high": {disc_levels['entry_high']},
    "stop_loss": {disc_levels['stop_loss']}, "target": {disc_levels['target']},
    "risk_reward": "1:{disc_rr}", "confidence": 6,
    "thesis": "2 sentences on 10-year disruption potential."
  }}
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=2400))

    try:
        parsed = _parse_response(raw)
    except json.JSONDecodeError:
        fallback = {
            "ticker": ticker, "recommendation": "hold", "trade_type": "unknown",
            "entry_low": 0, "entry_high": 0, "stop_loss": 0, "target": 0,
            "risk_reward": "—", "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
        }
        return {"short": {**fallback, "trade_type": "momentum"},
                "long": {**fallback, "trade_type": "growth"},
                "discovery": {**fallback, "trade_type": "disruptor"}}

    def _fix(result: Dict, levels_entry_low, levels_entry_high, levels_stop, levels_target) -> Dict:
        el = result.get("entry_low", levels_entry_low)
        eh = result.get("entry_high", levels_entry_high)
        stop = result.get("stop_loss", levels_stop)
        tgt = result.get("target", levels_target)
        mid = (el + eh) / 2
        if stop >= mid: stop = levels_stop
        if tgt <= mid: tgt = levels_target
        result["stop_loss"] = round(stop, 2)
        result["target"] = round(tgt, 2)
        result["theoretical"] = _compute_theoretical(el, eh, stop, tgt, 1000)
        return result

    short_r  = _fix(parsed.get("short", {}),  short_levels["entry_low"], short_levels["entry_high"],  short_levels["stop_loss"],  short_levels["target_2r"])
    long_r   = _fix(parsed.get("long", {}),   long_levels["entry_low"],  long_levels["entry_high"],  long_levels["stop_loss"],  long_levels["target"])
    disc_r   = _fix(parsed.get("discovery", {}), disc_levels["entry_low"], disc_levels["entry_high"], disc_levels["stop_loss"],  disc_levels["target"])

    short_r["next_trading_day"] = next_trading_day_label
    long_r["next_trading_day"] = "Long-term (6–12 months)"
    disc_r["next_trading_day"] = "10-Year Horizon"

    return {"ticker": ticker, "short": short_r, "long": long_r, "discovery": disc_r}


async def _analyze_ticker_discovery(ticker: str) -> Dict:
    """Single-ticker analysis for the 10+ year discovery / disruptor mode."""
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote, fund = await asyncio.gather(
        yf_svc.get_quote(ticker),
        finnhub_service.get_fundamentals_mapped(ticker),
        return_exceptions=True,
    )

    quote_data = quote if isinstance(quote, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}

    price = quote_data.get("price") or 0
    name = quote_data.get("name", ticker)
    sector = quote_data.get("sector", "")

    if not price:
        return {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}

    entry_low  = round(price * 0.95, 2)
    entry_high = round(price * 1.05, 2)
    stop_loss  = round(price * 0.65, 2)
    target     = round(price * 2.50, 2)
    rr = round((target - price) / max(price - stop_loss, 0.01), 1)

    def _pct(v, label):
        return f"{label}: {v*100:.1f}%" if v is not None else None

    fund_lines = [x for x in [
        _pct(fund_data.get("revenue_growth"), "Revenue growth YoY"),
        _pct(fund_data.get("gross_margins"), "Gross margin"),
        _pct(fund_data.get("earnings_growth"), "EPS growth YoY"),
        _pct(fund_data.get("profit_margin"), "Net margin"),
        f"Forward P/E: {fund_data['forward_pe']:.1f}" if fund_data.get("forward_pe") else None,
        _pct(fund_data.get("roe"), "ROE"),
        f"Debt/Equity: {fund_data['debt_to_equity']:.1f}" if fund_data.get("debt_to_equity") is not None else None,
        f"Free cash flow: ${fund_data['free_cashflow']/1e9:.1f}B" if fund_data.get("free_cashflow") else None,
    ] if x]
    fund_str = "\n".join(fund_lines) if fund_lines else "Fundamental data not available."

    prompt = f"""You are an expert venture-minded long-term investor. Evaluate {ticker} ({name}) as a potential 10-year disruptive hold.

Stock: {ticker} | Price: ${price:.2f} | Sector: {sector}

GROWTH METRICS:
{fund_str}

Assess whether this company could be 10x from here in 10 years. Consider:
1. What market is this company disrupting and how large is that TAM?
2. Does the revenue growth rate suggest they are winning market share?
3. Is there a defensible moat (network effects, platform lock-in, data advantage)?
4. Is there a credible path to dominant profitability even if currently unprofitable?

Decide: BUY (compelling 10-year disruptive thesis), HOLD (interesting but wait for better entry or more data), or AVOID (thesis is weak or execution risk too high)

Suggested entry zone: ${entry_low:.2f}–${entry_high:.2f} (accumulate over weeks, not a one-day fill)
Suggested stop: ${stop_loss:.2f} (~35% below — wide because these positions survive volatility)
Suggested 10-year target: ${target:.2f} (2.5x base case — adjust upward if thesis is very strong)

Do NOT reference RSI, MACD, VWAP, or any short-term technical concepts. Focus on business fundamentals and long-term potential.

Respond ONLY with valid JSON, no markdown:
{{
  "ticker": "{ticker}",
  "recommendation": "buy",
  "trade_type": "disruptor",
  "entry_low": {entry_low},
  "entry_high": {entry_high},
  "stop_loss": {stop_loss},
  "target": {target},
  "risk_reward": "1:{rr}",
  "confidence": 7,
  "thesis": "2 sentences citing specific growth metrics and explaining the 10-year disruptive thesis."
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, _call_claude, prompt)

    try:
        result = _parse_response(raw)
    except json.JSONDecodeError:
        result = {
            "ticker": ticker, "recommendation": "hold", "trade_type": "disruptor",
            "entry_low": entry_low, "entry_high": entry_high, "stop_loss": stop_loss,
            "target": target, "risk_reward": f"1:{rr}", "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
        }

    el = result.get("entry_low", entry_low)
    eh = result.get("entry_high", entry_high)
    stop = result.get("stop_loss", stop_loss)
    tgt = result.get("target", target)
    mid = (el + eh) / 2
    if stop >= mid: stop = stop_loss
    if tgt <= mid: tgt = target
    result["stop_loss"] = round(stop, 2)
    result["target"] = round(tgt, 2)
    result["next_trading_day"] = "10-Year Horizon"
    result["theoretical"] = _compute_theoretical(el, eh, stop, tgt, investment=1000)
    return result
