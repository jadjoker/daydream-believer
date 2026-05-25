import os
import asyncio
import json
import time
from collections import Counter
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)

# Module-level caches — keyed screening results survive across requests
_longterm_cache: Dict = {"ts": 0.0, "data": []}
_discovery_cache: Dict = {"ts": 0.0, "data": []}
_bargain_cache: Dict = {"ts": 0.0, "data": []}
_unknowns_cache: Dict = {"ts": 0.0, "data": []}
_FUND_CACHE_TTL = 7200  # 2 hours — fundamentals don't change hourly


# ─── Anthropic client ────────────────────────────────────────────────────────

def _get_client():
    import anthropic
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(dotenv_path=_env_path, override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic(api_key=api_key)


# ─── Rate-limited gather ─────────────────────────────────────────────────────

async def _batch_gather(coros, batch_size: int = 5, delay: float = 0.8):
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
    breadth = f"{green}/{len(sectors)} sectors green" if sectors else "breadth data unavailable"
    top_sectors = [s["name"] for s in sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)[:3]]
    bot_sectors = [s["name"] for s in sorted(sectors, key=lambda x: x.get("change_pct", 0))[:2]]

    # Sector rotation context (leading vs lagging)
    sector_rotation = ""
    if sectors:
        leaders = [f"{s['name']} {s['change_pct']:+.1f}%" for s in sectors[:3]]
        laggards = [f"{s['name']} {s['change_pct']:+.1f}%" for s in sectors[-2:]]
        sector_rotation = f"Leading: {', '.join(leaders)} | Lagging: {', '.join(laggards)}"

    # Treasury yield context
    yield_10yr = market_overview.get("yield_10yr")
    yield_spread = market_overview.get("yield_spread")
    yield_context = ""
    if yield_10yr:
        yield_context = f"10yr yield: {yield_10yr:.2f}%"
        if yield_spread is not None:
            if yield_spread < 0:
                yield_context += f" | Curve inverted ({yield_spread:+.2f}% spread) — recession signal"
            elif yield_spread < 0.5:
                yield_context += f" | Curve flat ({yield_spread:+.2f}%) — caution on rate-sensitive sectors"
            else:
                yield_context += f" | Normal curve ({yield_spread:+.2f}% spread)"

    # ── FRED macro context ───────────────────────────────────────────────────
    cpi_yoy      = market_overview.get("cpi_yoy")
    fed_rate     = market_overview.get("fed_rate")
    unemployment = market_overview.get("unemployment")
    gdp_growth   = market_overview.get("gdp_growth")

    macro_lines = []
    if fed_rate is not None:
        macro_lines.append(f"Fed rate: {fed_rate:.2f}%")
    if cpi_yoy is not None:
        macro_lines.append(f"CPI: {cpi_yoy:.1f}% YoY")
    if gdp_growth is not None:
        macro_lines.append(f"GDP: {gdp_growth:.1f}% annualized")
    if unemployment is not None:
        macro_lines.append(f"Unemployment: {unemployment:.1f}%")
    macro_stats = " | ".join(macro_lines) if macro_lines else ""

    policy_stance   = market_overview.get("policy_stance", "")
    inflation_trend = market_overview.get("inflation_trend", "")

    # ── Upcoming economic events ─────────────────────────────────────────────
    econ_events = market_overview.get("economic_events", [])
    events_lines = []
    for ev in (econ_events or [])[:5]:
        name = ev.get("event", "")
        date = ev.get("date", "")
        imp  = ev.get("impact", "")
        if name and date:
            flag = "⚠ " if imp == "high" else ""
            events_lines.append(f"{flag}{name} ({date})")
    upcoming_events_str = " | ".join(events_lines) if events_lines else ""

    raw_vix = market_overview.get("vix") or 0
    return {
        "vix": round(vix, 2),
        "vix_raw": raw_vix,
        "vix_regime": vix_regime,
        "direction": direction,
        "avg_index_change": round(avg_change, 2),
        "breadth": breadth,
        "top_sectors": top_sectors,
        "weak_sectors": bot_sectors,
        "sector_rotation": sector_rotation,
        "yield_context": yield_context,
        "macro_stats": macro_stats,
        "policy_stance": policy_stance,
        "inflation_trend": inflation_trend,
        "upcoming_events": upcoming_events_str,
        "overall_bias": "bullish" if avg_change > 0.25 else ("bearish" if avg_change < -0.25 else "neutral"),
        "market_status": market_overview.get("market_status", "open"),
    }


# ─── ATR-based level computation ─────────────────────────────────────────────

def compute_atr_levels(price: float, atr: Optional[float]) -> Dict:
    if not atr or atr <= 0 or not price:
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
        bb_pct = ta.get("bb_pct")

        # RSI sweet spot
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

        # EMA stack
        if ema9 and ema21:
            score += 1.0 if ema9 > ema21 else -0.5
        if ema50 and price and price > ema50:
            score += 0.5

        # VWAP
        if vwap and price and price > vwap:
            score += 1.0

        # ADX — gradient bonus proportional to trend strength (replaces flat +1.0)
        if adx and adx > 25:
            score += min((adx - 25) / 15, 2.0)

        # Stochastic
        if stoch_k and stoch_k > 80:
            score -= 1.0
        elif stoch_k and stoch_k < 20:
            score += 0.5

        # Bollinger Band position
        if bb_pct is not None:
            if bb_pct < 0.15:
                score += 1.0   # near lower band — potential bounce
            elif bb_pct > 0.90:
                score -= 0.5   # near upper band — overbought risk

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


# ─── Unified equity universe ──────────────────────────────────────────────────
#
# Single source of truth for all stocks across short / long / discovery modes.
# business_model tag controls which timeframes each stock is eligible for and
# how the scoring functions weight it:
#
#   mega       → long-term eligible; capped for discovery (too established to 10x)
#   saas       → all; recurring revenue + high gross margin platform economics
#   platform   → all; network effects / marketplace dynamics
#   fintech    → all; financial disruption with regulatory moat potential
#   deeptech   → discovery + long-term; pre-profit but massive TAM
#   healthcare → long-term; innovation + patent / regulatory moat
#   financial  → long-term; macro-sensitive incumbents
#   consumer   → long-term only; physical expansion ≠ platform moat (no discovery)
#   industrial → long-term only; cyclical, not speculative
#   energy     → long-term only; commodity-driven

EQUITY_UNIVERSE: List[tuple] = [
    # ── Mega-cap tech / AI ────────────────────────────────────────────────────
    ("AAPL",  "mega"),
    ("MSFT",  "mega"),
    ("GOOGL", "mega"),
    ("NVDA",  "mega"),
    ("META",  "mega"),
    ("AMZN",  "mega"),
    ("TSLA",  "mega"),
    ("AMD",   "mega"),
    # ── SaaS / Enterprise software ────────────────────────────────────────────
    ("CRM",   "saas"),
    ("NOW",   "saas"),
    ("PLTR",  "saas"),
    ("DDOG",  "saas"),
    ("NET",   "saas"),
    ("SNOW",  "saas"),
    # ── Platform / marketplace ────────────────────────────────────────────────
    ("NFLX",  "platform"),
    ("UBER",  "platform"),
    ("COIN",  "platform"),
    # ── Fintech ───────────────────────────────────────────────────────────────
    ("V",     "fintech"),
    ("MA",    "fintech"),
    # ── Deep tech / Semiconductors ────────────────────────────────────────────
    ("QCOM",  "deeptech"),
    ("AI",    "deeptech"),
    # ── Healthcare ────────────────────────────────────────────────────────────
    ("LLY",   "healthcare"),
    ("ABBV",  "healthcare"),
    ("UNH",   "healthcare"),
    # ── Financials ────────────────────────────────────────────────────────────
    ("JPM",   "financial"),
    ("GS",    "financial"),
    # ── Consumer ──────────────────────────────────────────────────────────────
    ("WMT",   "consumer"),
    ("CAVA",  "consumer"),
    ("ONON",  "consumer"),
    # ── Energy ────────────────────────────────────────────────────────────────
    ("XOM",   "energy"),
    ("CVX",   "energy"),
]

# Quick lookup: ticker → business_model
EQUITY_MODEL: Dict[str, str] = {t: m for t, m in EQUITY_UNIVERSE}

# Tags with genuine platform-economics potential — the only ones eligible for discovery
_DISCOVERY_ELIGIBLE = {"platform", "saas", "fintech", "deeptech"}


# ─── Pre-process candidates before sending to Haiku ─────────────────────────

async def preprocess_candidates(
    screener_results: List[Dict],
    regime: Dict,
    top_n: int = 6,
) -> List[Dict]:
    candidates = sorted(screener_results, key=lambda x: x.get("score", 0), reverse=True)[:max(top_n * 2, 16)]
    ta_results: List = [r.get("_ta") for r in candidates]

    enriched = []
    for result, ta in zip(candidates, ta_results):
        ta_data = ta if isinstance(ta, dict) else None
        atr = ta_data.get("atr_14") if ta_data else None
        price = result.get("price") or (ta_data.get("price") if ta_data else 0)
        if not price:
            continue
        levels = compute_atr_levels(price, atr)
        trade_type = detect_trade_type(result, ta_data, regime)
        score = enhanced_score(result, ta_data, regime)

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
        else:
            chg = result.get("change_pct", 0) or 0
            signals.append(f"Day change: {chg:+.1f}%")
            if chg > 3:
                signals.append("Strong bullish momentum")
            elif chg > 1:
                signals.append("Mild bullish")
            elif chg < -3:
                signals.append("Strong selling pressure")
            elif chg < -1:
                signals.append("Mild bearish")

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
            "ta_summary": (ta_data or {}).get("signal_summary", "Price-action based — TA unavailable"),
            "suggested_stop": levels["stop_loss"],
            "suggested_target": levels["target_2r"],
            "entry_low": levels["entry_low"],
            "entry_high": levels["entry_high"],
            "risk_per_share": levels["risk_per_share"],
            "level_method": levels["method"],
        })

    enriched.sort(key=lambda x: x["enhanced_score"], reverse=True)
    return enriched[:top_n]


# ─── Market time context ─────────────────────────────────────────────────────

def _market_time_context(market_overview: Dict, next_trading_day_label: str) -> str:
    status = market_overview.get("market_status", "open")
    if status == "open":
        return ""
    elif status == "pre-market":
        return (
            "\nNote: Markets are currently in PRE-MARKET hours. Regular session opens 9:30am ET. "
            "Pre-market prices may not hold at open. Do NOT write 'today' as if the regular session is live.\n"
        )
    elif status == "after-hours":
        return (
            f"\nNote: Markets closed at 4pm ET (AFTER-HOURS now). All prices reflect today's close. "
            f"Picks are for {next_trading_day_label}'s open. Do NOT reference 'today's trading' or intraday moves — the session is over.\n"
        )
    else:  # "closed" — weekend or overnight
        return (
            f"\nNote: Markets are CLOSED. All data reflects the most recent session's close. "
            f"Picks are for {next_trading_day_label}'s open. "
            f"Do NOT use phrases like 'today' or 'today's trading' — there is no active session.\n"
        )


# ─── Short-term prompt builder ────────────────────────────────────────────────

def _build_prompt(
    candidates: List[Dict],
    regime: Dict,
    market_overview: Dict,
    date_str: str,
    next_trading_day_label: str = "Tomorrow",
) -> str:
    vix_label = (
        f"VIX: {regime['vix']} (last close) — {regime['vix_regime']}"
        if regime.get("market_status") in ("closed", "pre-market", "after-hours")
        else f"VIX: {regime['vix']} — {regime['vix_regime']}"
    )
    regime_lines = [
        vix_label,
        f"Market direction: {regime['direction']}",
        f"Breadth: {regime['breadth']}",
    ]
    if regime.get("sector_rotation"):
        regime_lines.append(f"Sector rotation: {regime['sector_rotation']}")
    elif regime.get("top_sectors"):
        regime_lines.append(f"Top sectors: {', '.join(regime['top_sectors'])}")
        regime_lines.append(f"Weak sectors: {', '.join(regime['weak_sectors'])}")
    if regime.get("yield_context"):
        regime_lines.append(regime["yield_context"])
    if regime.get("macro_stats"):
        regime_lines.append(regime["macro_stats"])
    if regime.get("policy_stance"):
        regime_lines.append(f"Policy stance: {regime['policy_stance']}")
    if regime.get("upcoming_events"):
        regime_lines.append(f"Upcoming risk events: {regime['upcoming_events']}")
    regime_block = "\n".join(regime_lines)

    time_note = _market_time_context(market_overview, next_trading_day_label)

    # Sector concentration warning
    sector_counts = Counter(c.get("sector", "") for c in candidates if c.get("sector"))
    concentration_lines = []
    for sec, cnt in sector_counts.most_common(2):
        if cnt >= max(len(candidates) // 2, 3) and sec:
            concentration_lines.append(f"⚠ {cnt}/{len(candidates)} candidates are {sec} — flag concentration risk in market_summary")
    concentration_note = "\n".join(concentration_lines)

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
            f"   Sector: {c.get('sector', '')}"
        )
    candidates_block = "\n".join(rows)

    return f"""You are an expert day trader. Today is {date_str}.{time_note}

Python analysis has already scored, ranked, and computed ATR-based entry/stop/target levels for the best candidates. Your job:
1. Select 4–8 of the BEST setups below. If fewer than 4 have clean setups, return fewer — never force weak picks.
2. Validate or slightly adjust the Python-suggested price levels if needed.
3. Write a 2-sentence thesis for {next_trading_day_label}'s open. EACH sentence must cite at least one specific numeric value from the data (e.g. "RSI at 44", "2.3x relative volume" — not vague phrases like "strong momentum").
4. Name one specific catalyst and one key risk.
5. Assign a realistic confidence score 1–10.

=== MARKET REGIME ===
{regime_block}
{concentration_note}

=== PRE-ANALYZED CANDIDATES (ranked by composite score) ===
{candidates_block}

=== RULES ===
- Confidence above 7 only if: rel_vol > 2x AND TA confirms direction AND regime aligns
- Confidence 5–6 for mixed signals; do not include picks with confidence below 5
- Never recommend a setup that goes against the market regime
- Stop loss must be BELOW entry for longs
- market_summary must reference VIX {regime['vix']:.0f} and the specific market direction, and mention {next_trading_day_label}
- Do NOT write phrases like "today's trading" or "today's session" if the market is closed or after-hours

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences referencing VIX {regime['vix']:.0f} and specific conditions for {next_trading_day_label}'s open",
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
      "thesis": "RSI at 52 with MACD histogram turning positive at +0.18 signals early momentum. Relative volume at 2.1x confirms institutional participation on a +2.3% day.",
      "catalyst": "Specific trigger: e.g. technical breakout above $187 resistance, earnings catalyst, sector rotation into tech",
      "key_risk": "Main risk: e.g. SPY rejection at resistance pulling this down, or VIX spike reversing intraday gains"
    }}
  ],
  "generated_at": "{date_str}"
}}"""


# ─── Validate and clean Haiku output ─────────────────────────────────────────

def _validate_picks(picks_raw: List[Dict], candidates: List[Dict]) -> List[Dict]:
    candidate_map = {c["ticker"]: c for c in candidates}
    cleaned = []
    for i, p in enumerate(picks_raw):
        c = candidate_map.get(p.get("ticker", ""), {})
        entry = (p.get("entry_low", 0) + p.get("entry_high", 0)) / 2 or c.get("price", 0)
        stop = p.get("stop_loss") or c.get("suggested_stop", entry * 0.98)
        target = p.get("target") or c.get("suggested_target", entry * 1.04)

        if stop >= entry:
            stop = c.get("suggested_stop", round(entry * 0.975, 2))
        if target <= entry:
            target = c.get("suggested_target", round(entry * 1.04, 2))

        risk = round(entry - stop, 2)
        reward = round(target - entry, 2)
        rr = f"1:{reward/risk:.1f}" if risk > 0 else "—"

        pick = {
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
            "catalyst": p.get("catalyst", ""),
            "key_risk": p.get("key_risk", ""),
        }
        if p.get("hold_horizon"):
            pick["hold_horizon"] = p["hold_horizon"]
        pick["category"] = p.get("category") or c.get("hint_category", "long_term")
        cleaned.append(pick)
    return cleaned


# ─── Main entry point ─────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int = 1800) -> str:
    client = _get_client()
    model = os.getenv("AI_MODEL", "claude-sonnet-4-6")
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
        }],
    )
    return msg.content[0].text


def _parse_response(raw: str) -> Dict:
    import re
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    matches = re.findall(r'\{[\s\S]*\}', text)
    for m in sorted(matches, key=len, reverse=True):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("No valid JSON found", text, 0)


# ─── Quick picks: Claude selects from registry + Finnhub live prices ──────────
# (ticker, full_name, category, one-line description)
_COMPANY_REGISTRY: Dict[str, tuple] = {
    # ── Blue-chip (excluded from picks pool — too consensus/obvious) ─────────────
    "AAPL":  ("Apple",                "blue_chip",  "iPhone/Mac ecosystem + services, 94% gross margin on services"),
    "MSFT":  ("Microsoft",            "blue_chip",  "Azure cloud #2 globally, Copilot AI across all products"),
    "GOOGL": ("Alphabet",             "blue_chip",  "Search + YouTube + Google Cloud, Gemini AI integration"),
    "NVDA":  ("Nvidia",               "blue_chip",  "AI GPU monopoly, H100/Blackwell, data center + robotics"),
    "META":  ("Meta Platforms",       "blue_chip",  "Facebook/Instagram/WhatsApp + Reels growth, AI ad targeting"),
    "AMZN":  ("Amazon",               "blue_chip",  "AWS cloud leader + e-commerce + ads, expanding operating margins"),
    "TSLA":  ("Tesla",                "blue_chip",  "EV + energy storage + Full Self-Driving, robotaxi optionality"),
    "V":     ("Visa",                 "blue_chip",  "global payment network, 80%+ operating margin, pricing power"),
    "MA":    ("Mastercard",           "blue_chip",  "global payment network, value-added services, international mix"),
    "JPM":   ("JPMorgan Chase",       "blue_chip",  "largest US bank, AI adoption leader, consistent capital return"),
    "LLY":   ("Eli Lilly",            "blue_chip",  "GLP-1 drugs Mounjaro/Zepbound, massive obesity market TAM"),
    "UNH":   ("UnitedHealth Group",   "blue_chip",  "largest US managed care + Optum health services platform"),
    "WMT":   ("Walmart",              "blue_chip",  "retail dominance + e-commerce acceleration, ad business scaling"),
    "XOM":   ("ExxonMobil",           "blue_chip",  "oil/gas major, Pioneer acquisition synergies, strong FCF dividend"),
    "CVX":   ("Chevron",              "blue_chip",  "oil/gas major, Hess acquisition, consistent buyback program"),
    # ── Long-term (quality compounders, non-consensus) ─────────────────────────
    "AMD":   ("AMD",                  "long_term",  "MI300x data center GPUs + EPYC CPUs, market share gains vs Intel"),
    "CRM":   ("Salesforce",           "long_term",  "CRM SaaS leader, Agentforce AI agents, >$34B ARR"),
    "NOW":   ("ServiceNow",           "long_term",  "enterprise workflow SaaS, AI platform upsell, >99% renewal rates"),
    "PLTR":  ("Palantir",             "long_term",  "AIP AI platform, government + commercial data analytics"),
    "DDOG":  ("Datadog",              "long_term",  "cloud monitoring + security SaaS, land-and-expand NRR >120%"),
    "NET":   ("Cloudflare",           "long_term",  "networking + zero-trust security platform, Workers AI"),
    "SNOW":  ("Snowflake",            "long_term",  "cloud data warehouse, Cortex AI, Iceberg tables growth"),
    "NFLX":  ("Netflix",              "long_term",  "streaming leader, ad tier scaling, live sports + games"),
    "UBER":  ("Uber",                 "long_term",  "rides + delivery global marketplace, improving EBITDA margins"),
    "COIN":  ("Coinbase",             "long_term",  "leading US crypto exchange, base L2, institutional custody"),
    "QCOM":  ("Qualcomm",             "long_term",  "5G modem leader, Snapdragon AI edge chips, automotive design wins"),
    "AI":    ("C3.ai",                "long_term",  "enterprise AI software platform, pilot-to-production momentum"),
    "ABBV":  ("AbbVie",               "long_term",  "Skyrizi/Rinvoq offsetting Humira biosimilar pressure"),
    "GS":    ("Goldman Sachs",        "long_term",  "investment banking rebound cycle, asset/wealth management growing"),
    "CAVA":  ("Cava Group",           "long_term",  "fast-casual Mediterranean, same-store sales +14%, rapid expansion"),
    "ONON":  ("On Running",           "long_term",  "premium running/lifestyle brand, 30%+ revenue growth, DTC mix rising"),
    "CRWD":  ("CrowdStrike",          "long_term",  "next-gen EDR/XDR cybersecurity, Falcon platform NRR >120%, ARR $3.4B"),
    "PANW":  ("Palo Alto Networks",   "long_term",  "largest cybersecurity revenue, platformization shifting to annual contracts"),
    "ADBE":  ("Adobe",                "long_term",  "creative/document cloud monopoly, Firefly AI monetization, 90%+ gross margin"),
    "ANET":  ("Arista Networks",      "long_term",  "cloud spine networking, >40% gross margins, data center + AI infrastructure"),
    "TTD":   ("The Trade Desk",       "long_term",  "programmatic advertising platform, CTV growth, UID2 identity advantage"),
    "APP":   ("AppLovin",             "long_term",  "AI-driven mobile ad platform, AXON 2.0 engine, 70%+ adj EBITDA margins"),
    "AXON":  ("Axon Enterprise",      "long_term",  "law enforcement tech platform, Taser + cameras + AI software, 30%+ revenue growth"),
    # ── Bargain ($5–$20) ──────────────────────────────────────────────────────
    "SOFI":  ("SoFi Technologies",    "bargain",    "digital bank + financial services, bank charter, growing deposits"),
    "NU":    ("Nu Holdings",          "bargain",    "fastest-growing LatAm neobank, 100M+ customers, Brazil focus"),
    "PAYO":  ("Payoneer",             "bargain",    "B2B cross-border payments for SMBs + gig economy"),
    "GDOT":  ("Green Dot",            "bargain",    "banking-as-a-service, prepaid cards, steady FCF generation"),
    "SNAP":  ("Snap Inc",             "bargain",    "social media + AR glasses, improving ARPU, Spotlight growth"),
    "PATH":  ("UiPath",               "bargain",    "RPA automation SaaS, enterprise AI agents, strong ARR"),
    "FRSH":  ("Freshworks",           "bargain",    "CRM/support SaaS for SMBs, land-and-expand, improving margins"),
    "CLBT":  ("Cellebrite",           "bargain",    "digital intelligence SaaS for law enforcement, sticky gov contracts"),
    "SOUN":  ("SoundHound AI",        "bargain",    "voice AI platform, automotive + restaurant licensing RPO growing"),
    "IONQ":  ("IonQ",                 "bargain",    "quantum computing trapped-ion leader, DoD + AWS contracts"),
    "JOBY":  ("Joby Aviation",        "bargain",    "FAA-certified eVTOL air taxi, Toyota-backed, delta air lines partner"),
    "ERIC":  ("Ericsson",             "bargain",    "5G network equipment leader, cheap valuation vs peers, restructuring"),
    "NOK":   ("Nokia",                "bargain",    "5G IP portfolio + network infrastructure, recovering margins"),
    "F":     ("Ford Motor",           "bargain",    "EV + ICE auto, single-digit P/E, strong dividend yield"),
    "FTRE":  ("Fortrea",              "bargain",    "CRO spun from LabCorp, clinical trial services, growing backlog"),
    "MDXG":  ("MiMedx",              "bargain",    "regenerative medicine amniotic tissue, improving gross margins"),
    "LBRT":  ("Liberty Energy",       "bargain",    "oilfield services, hydraulic fracturing, FCF-positive operations"),
    "AMCX":  ("AMC Networks",          "bargain",    "cable TV network portfolio (AMC, IFC, Sundance), deep-value FCF yield 15%+, content IP library"),
    "KSS":   ("Kohl's",               "bargain",    "discount department retailer, strong FCF, high dividend yield"),
    "AAL":   ("American Airlines",    "bargain",    "airline turnaround, capacity discipline + debt reduction, recovering domestic + international load factors"),
    "TASK":  ("TaskUs",               "bargain",    "AI-enabled BPO, growing enterprise digital experience contracts"),
    "CTLP":  ("Cantaloupe",           "bargain",    "unattended retail IoT + SaaS, growing subscription revenue mix"),
    # ── Hidden Gems ───────────────────────────────────────────────────────────
    "FROG":  ("JFrog",                "hidden_gem", "universal DevOps artifact management SaaS, security + MLOps"),
    "GTLB":  ("GitLab",               "hidden_gem", "end-to-end DevSecOps platform, AI code review, 30%+ ARR growth, path to GAAP profitability"),
    "WK":    ("Workiva",              "hidden_gem", "financial reporting + ESG compliance SaaS, sticky enterprise"),
    "ACMR":  ("ACM Research",         "hidden_gem", "advanced wafer cleaning equipment, single-wafer processing leader"),
    "SMTC":  ("Semtech",              "hidden_gem", "LoRa IoT connectivity chips + data center optical transceivers"),
    "ALGM":  ("Allegro MicroSystems", "hidden_gem", "sensing + power ICs for automotive/industrial, EV exposure"),
    "COHU":  ("Cohu",                 "hidden_gem", "semiconductor test handlers, cyclical upcycle beneficiary"),
    "AMBA":  ("Ambarella",            "hidden_gem", "edge AI video processing SoCs, automotive camera leader"),
    "FLYW":  ("Flywire",              "hidden_gem", "vertical payment software for education + healthcare, global"),
    "PRCT":  ("Procept BioRobotics",  "hidden_gem", "robotic BPH prostate surgery system, high ASP + razor-blade model"),
    "NVST":  ("Envista Holdings",     "hidden_gem", "dental equipment + consumables, turnaround, margin expansion"),
    "LMAT":  ("LeMaitre Vascular",    "hidden_gem", "specialty vascular surgical devices, consistent compounder"),
    "AAON":  ("AAON Inc",             "hidden_gem", "HVAC manufacturer, 20%+ operating margins, founder-led culture"),
    "CRVL":  ("CorVel Corp",          "hidden_gem", "risk management + workers comp SaaS, 40-year track record"),
    "DOCS":  ("Doximity",             "hidden_gem", "physician digital platform, 80%+ gross margin, 80% of US doctors, healthcare SaaS with moat"),
    "WEAV":  ("Weave Communications", "hidden_gem", "patient + SMB communications SaaS, vertical CRM focus"),
}


def _build_quick_picks_prompt(market_overview: Dict, date_str: str) -> str:
    regime = assess_market_regime(market_overview)
    time_note = _market_time_context(market_overview, "the next session")
    vix  = market_overview.get("vix") or 20
    spy_c = market_overview.get("spy_change_pct") or 0
    qqq_c = market_overview.get("qqq_change_pct") or 0

    macro_parts = [f"SPY {spy_c:+.1f}% | QQQ {qqq_c:+.1f}% | VIX {vix:.1f}",
                   regime["direction"]]
    if regime.get("sector_rotation"):   macro_parts.append(regime["sector_rotation"])
    if regime.get("yield_context"):     macro_parts.append(regime["yield_context"])
    if regime.get("macro_stats"):       macro_parts.append(regime["macro_stats"])
    if regime.get("upcoming_events"):   macro_parts.append(f"Risk events: {regime['upcoming_events']}")
    macro_block = "\n".join(macro_parts)

    def section(cat):
        return "\n".join(
            f"  {t}: {name} — {desc}"
            for t, (name, c, desc) in _COMPANY_REGISTRY.items() if c == cat
        )

    return f"""You are an expert long-term investment advisor. Today is {date_str}.{time_note}

MARKET:
{macro_block}

INVESTMENT UNIVERSE — select ONLY tickers listed below:

LONG-TERM (quality compounders, non-consensus — NOT mega-cap household names, 6–18 month holds):
{section("long_term")}

BARGAIN ($5–$20 stocks, value + turnaround, 6–12 month holds):
{section("bargain")}

HIDDEN GEMS (small/mid-cap under-the-radar, 12–24 month holds):
{section("hidden_gem")}

YOUR JOB:
1. Select exactly 5 LONG-TERM, 5 BARGAIN, 5 HIDDEN GEM picks (15 total)
2. Base selection on company quality, business fundamentals, and current macro regime
3. For each pick:
   - stop_pct: stop distance below entry (e.g. 0.12 = 12%)
   - target_pct: upside to 12-month target (e.g. 0.30 = 30%)
   - thesis: 2 sentences with SPECIFIC data (revenue %, margins, market position, valuation)
   - catalyst: one specific near-term trigger
   - key_risk: one main downside risk
   - confidence: 1–10 (above 7 = conviction play with strong fundamental thesis)
   - trade_type: growth | value | dividend | turnaround | compounder | disruptor | platform | deep-tech | speculative
4. ONLY pick tickers from the lists above — no others

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on market conditions for the next session referencing VIX {vix:.0f}",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "CRWD",
      "category": "long_term",
      "trade_type": "compounder",
      "stop_pct": 0.12,
      "target_pct": 0.28,
      "confidence": 8,
      "thesis": "CrowdStrike ARR grew 23% YoY to $3.4B with Falcon platform NRR above 120% and 60%+ of customers using 5+ modules. At ~60x forward FCF with durable 20%+ revenue growth, it's a category-defining compounder with room to run.",
      "catalyst": "FY2025 Q4 earnings — expecting accelerated module adoption from platform consolidation deals",
      "key_risk": "Macro-driven IT budget cuts delay enterprise renewals and slow NRR expansion"
    }}
  ],
  "generated_at": "{date_str}"
}}"""


async def generate_quick_unified_picks(market_overview: Dict, date_str: str) -> Dict:
    """
    Fast picks: Claude selects 5 per category from registry (training knowledge),
    then Finnhub provides live prices for entry/stop/target. ~30s total, no Yahoo Finance.
    """
    from services import finnhub_service

    regime = assess_market_regime(market_overview)

    prompt = _build_quick_picks_prompt(market_overview, date_str)
    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=8000))

    try:
        parsed = _parse_response(raw)
    except json.JSONDecodeError:
        return {
            "picks": [], "market_summary": "Analysis temporarily unavailable.",
            "bias": regime["overall_bias"], "generated_at": date_str,
        }

    picks_raw = parsed.get("picks", [])
    if not picks_raw:
        return {
            "picks": [], "market_summary": parsed.get("market_summary", ""),
            "bias": parsed.get("bias", regime["overall_bias"]), "generated_at": date_str,
        }

    # Validate tickers against registry
    valid_tickers = [
        p["ticker"].upper() for p in picks_raw
        if p.get("ticker") and p["ticker"].upper() in _COMPANY_REGISTRY
    ]

    # Fetch live Finnhub quotes for selected tickers only
    quote_results = await _batch_gather(
        [finnhub_service.get_quote(t) for t in valid_tickers],
        batch_size=3, delay=0.5,
    )
    quote_map = {
        t: q for t, q in zip(valid_tickers, quote_results)
        if isinstance(q, dict) and q.get("price")
    }

    # Fallback: tickers with no quote → try last candle close
    missing = [t for t in valid_tickers if t not in quote_map]
    if missing:
        candle_results = await _batch_gather(
            [finnhub_service.get_candles(t, period="1mo", interval="1d") for t in missing],
            batch_size=3, delay=0.5,
        )
        for t, bars in zip(missing, candle_results):
            if isinstance(bars, list) and bars:
                last_close = bars[-1].get("close") or 0
                if last_close:
                    quote_map[t] = {"price": round(last_close, 2), "prev_close": round(last_close, 2)}

    final_picks = []
    for p in picks_raw:
        ticker = (p.get("ticker") or "").upper()
        if ticker not in _COMPANY_REGISTRY:
            continue

        q = quote_map.get(ticker, {})
        price = q.get("price", 0) or 0

        stop_pct   = max(0.05, min(0.35, float(p.get("stop_pct")   or 0.12)))
        target_pct = max(0.10, min(1.50, float(p.get("target_pct") or 0.25)))

        if price:
            entry_low  = round(price * 0.990, 2)
            entry_high = round(price * 1.015, 2)
            stop_loss  = round(entry_low * (1 - stop_pct), 2)
            target     = round(entry_low * (1 + target_pct), 2)
            risk       = max(entry_low - stop_loss, 0.01)
            reward     = max(target - entry_low, 0)
            rr         = f"1:{reward/risk:.1f}" if risk > 0 else "—"
        else:
            entry_low = entry_high = stop_loss = target = None
            rr = "—"

        reg = _COMPANY_REGISTRY[ticker]
        category = p.get("category", reg[1])
        if category not in ("long_term", "bargain", "hidden_gem"):
            category = reg[1]

        final_picks.append({
            "rank":        len(final_picks) + 1,
            "ticker":      ticker,
            "name":        reg[0],
            "category":    category,
            "trade_type":  p.get("trade_type", "growth"),
            "entry_low":   entry_low,
            "entry_high":  entry_high,
            "stop_loss":   stop_loss,
            "target":      target,
            "risk_reward": rr,
            "confidence":  max(1, min(10, int(p.get("confidence") or 7))),
            "thesis":      p.get("thesis", ""),
            "catalyst":    p.get("catalyst", ""),
            "key_risk":    p.get("key_risk", ""),
        })

    return {
        "picks":          final_picks,
        "market_summary": parsed.get("market_summary", ""),
        "bias":           parsed.get("bias", regime["overall_bias"]),
        "generated_at":   date_str,
    }


async def generate_replacement_pick(
    category: str,
    exclude_tickers: List[str],
    market_overview: Dict,
    date_str: str,
) -> Optional[Dict]:
    """
    Generate one replacement pick for a given category. ~350 tokens total — ~86% cheaper
    than a full refresh. Used by POST /ai/replace-pick.
    """
    from services import finnhub_service

    available = {
        t: entry
        for t, entry in _COMPANY_REGISTRY.items()
        if entry[1] == category and t not in exclude_tickers
    }
    if not available:
        return None

    regime = assess_market_regime(market_overview)
    vix   = market_overview.get("vix") or 20
    spy_c = market_overview.get("spy_change_pct") or 0

    cat_labels = {
        "long_term":  "LONG-TERM quality compounder (6–18 month, non-consensus name)",
        "bargain":    "BARGAIN value/turnaround ($5–$20, 6–12 month)",
        "hidden_gem": "HIDDEN GEM small/mid-cap under-the-radar (12–24 month)",
    }
    lines = "\n".join(
        f"  {t}: {entry[0]} — {entry[2]}" for t, entry in available.items()
    )

    prompt = f"""You are a stock picker. Today is {date_str}. Market: SPY {spy_c:+.1f}%, VIX {vix:.1f}, {regime["direction"]}.

Pick ONE {cat_labels[category]} from this list:
{lines}

Return ONLY valid JSON (no markdown):
{{"ticker":"X","trade_type":"compounder","stop_pct":0.12,"target_pct":0.30,"confidence":8,"thesis":"2 sentences with specific data (revenue %, margins, valuation).","catalyst":"one specific near-term trigger","key_risk":"one main downside risk"}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=300))

    try:
        pick_raw = _parse_response(raw)
    except Exception:
        return None

    ticker = (pick_raw.get("ticker") or "").upper()
    if ticker not in _COMPANY_REGISTRY or ticker in exclude_tickers:
        return None
    if _COMPANY_REGISTRY[ticker][1] != category:
        return None

    # Fetch live price
    fh_data = await finnhub_service.get_quote(ticker) or {}
    price = fh_data.get("price") or fh_data.get("prev_close")
    if not price:
        bars = await finnhub_service.get_candles(ticker, period="1mo", interval="1d")
        if isinstance(bars, list) and bars:
            price = bars[-1].get("close")

    stop_pct   = max(0.05, min(0.35, float(pick_raw.get("stop_pct")   or 0.12)))
    target_pct = max(0.10, min(1.50, float(pick_raw.get("target_pct") or 0.30)))

    if price:
        entry_low  = round(float(price) * 0.990, 2)
        entry_high = round(float(price) * 1.015, 2)
        stop_loss  = round(entry_low * (1 - stop_pct), 2)
        target     = round(entry_low * (1 + target_pct), 2)
        risk       = max(entry_low - stop_loss, 0.01)
        reward     = max(target - entry_low, 0)
        rr         = f"1:{reward/risk:.1f}"
    else:
        entry_low = entry_high = stop_loss = target = None
        rr = "—"

    return {
        "ticker":      ticker,
        "name":        _COMPANY_REGISTRY[ticker][0],
        "category":    category,
        "trade_type":  pick_raw.get("trade_type", "growth"),
        "entry_low":   entry_low,
        "entry_high":  entry_high,
        "stop_loss":   stop_loss,
        "target":      target,
        "risk_reward": rr,
        "confidence":  max(1, min(10, int(pick_raw.get("confidence") or 7))),
        "thesis":      pick_raw.get("thesis", ""),
        "catalyst":    pick_raw.get("catalyst", ""),
        "key_risk":    pick_raw.get("key_risk", ""),
    }


async def generate_market_picks(
    market_overview: Dict,
    screener_results: List[Dict],
    date_str: str,
    next_trading_day_label: str = "Tomorrow",
    mode: str = "short",
) -> Dict:
    regime = assess_market_regime(market_overview)

    earnings_lookup = market_overview.get("earnings_lookup") or {}

    if mode == "unified":
        try:
            lt_cands = await screen_longterm_candidates(top_n=5, earnings_lookup=earnings_lookup)
        except Exception:
            lt_cands = []
        try:
            bg_cands = await screen_bargain_candidates(top_n=4, earnings_lookup=earnings_lookup)
        except Exception:
            bg_cands = []
        try:
            un_cands = await screen_unknowns_candidates(top_n=5, earnings_lookup=earnings_lookup)
        except Exception:
            un_cands = []

        lt = lt_cands if isinstance(lt_cands, list) else []
        bg = bg_cands if isinstance(bg_cands, list) else []
        un = un_cands if isinstance(un_cands, list) else []

        for c in lt: c["hint_category"] = "long_term"
        for c in bg: c["hint_category"] = "bargain"
        for c in un: c["hint_category"] = "hidden_gem"

        candidates = lt + bg + un
        if not candidates:
            return {"error": "No candidates", "picks": [], "bias": "neutral", "generated_at": date_str}
        try:
            enriched = await asyncio.wait_for(
                _enrich_candidates(candidates, earnings_lookup),
                timeout=120.0,
            )
            candidates = enriched
        except Exception:
            pass  # proceed with raw fundamentals if enrich times out or fails
        prompt = _build_unified_prompt(candidates, market_overview, date_str)
    elif mode == "long":
        try:
            candidates = await screen_longterm_candidates(top_n=10, earnings_lookup=earnings_lookup)
        except Exception:
            candidates = []
        if not candidates:
            return {"error": "No candidates", "picks": [], "market_summary": "Insufficient data.",
                    "bias": "neutral", "generated_at": date_str}
        prompt = _build_longterm_prompt(candidates, market_overview, date_str)
    elif mode == "discovery":
        try:
            candidates = await screen_discovery_candidates(top_n=10, earnings_lookup=earnings_lookup)
        except Exception:
            candidates = []
        if not candidates:
            return {"error": "No candidates", "picks": [], "market_summary": "Insufficient data.",
                    "bias": "neutral", "generated_at": date_str}
        prompt = _build_discovery_prompt(candidates, date_str, market_overview)
    else:
        candidates = await preprocess_candidates(screener_results, regime, top_n=8)
        if not candidates:
            return {"error": "No candidates found from screener", "picks": [], "market_summary": "Insufficient data.",
                    "bias": regime["overall_bias"], "generated_at": date_str}
        prompt = _build_prompt(candidates, regime, market_overview, date_str, next_trading_day_label)

    loop = asyncio.get_running_loop()
    tokens = 3000 if mode == "unified" else (3200 if mode in ("long", "discovery") else 1800)

    for attempt in range(2):
        raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=tokens))
        try:
            result = _parse_response(raw)
            result["picks"] = _validate_picks(result.get("picks", []), candidates)
            result["bias"] = result.get("bias") or regime["overall_bias"]
            result["regime"] = regime
            return result
        except json.JSONDecodeError:
            if attempt == 1:
                return {
                    "error": "JSON parse failed after retry",
                    "picks": [], "market_summary": "Analysis temporarily unavailable.",
                    "bias": regime["overall_bias"],
                    "generated_at": date_str, "regime": regime,
                }


# ─── Long-term scoring ────────────────────────────────────────────────────────

def _score_longterm(fund: Dict, price: float, model: str = "") -> float:
    score = 0.0

    rev = fund.get("revenue_growth")
    if rev is not None:
        if rev > 0.25:    score += 6
        elif rev > 0.15:  score += 4
        elif rev > 0.05:  score += 2
        elif rev > 0:     score += 1
        else:             score -= 3

    earn = fund.get("earnings_growth")
    if earn is not None:
        if earn > 0.20:   score += 4
        elif earn > 0.10: score += 2
        elif earn > 0:    score += 1
        else:             score -= 1

    peg = fund.get("peg_ratio")
    if peg is not None and peg > 0:
        if peg < 1.0:     score += 5
        elif peg < 1.5:   score += 3
        elif peg < 2.5:   score += 1
        elif peg > 3.5:   score -= 2

    fwd_pe = fund.get("forward_pe")
    if fwd_pe is not None and fwd_pe > 0:
        if 10 <= fwd_pe <= 20:  score += 3
        elif 20 < fwd_pe <= 35: score += 1
        elif fwd_pe > 60:       score -= 2

    margin = fund.get("profit_margin")
    if margin is not None:
        if margin > 0.25:   score += 4
        elif margin > 0.15: score += 2
        elif margin > 0.05: score += 1
        elif margin < 0:    score -= 4

    roe = fund.get("roe")
    if roe is not None:
        if roe > 0.30:   score += 3
        elif roe > 0.15: score += 2
        elif roe > 0.05: score += 1
        elif roe < 0:    score -= 2

    fcf = fund.get("free_cashflow")
    if fcf is not None:
        score += 2 if fcf > 0 else -2

    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 30:    score += 2
        elif de < 80:  score += 1
        elif de > 200: score -= 2

    # Dividend yield — total return bonus for quality compounders
    div = fund.get("dividend_yield")
    if div:
        if div > 0.03:   score += 1.5
        elif div > 0.02: score += 0.75
        elif div > 0.01: score += 0.25

    # Business model modifier — platform/saas have structural advantages
    if model in ("mega",):
        score += 1.5
    elif model in ("saas", "platform"):
        score += 1.0
    elif model in ("fintech",):
        score += 0.5
    elif model in ("consumer", "industrial", "energy"):
        score -= 1.0  # lower multiple headroom for non-platform businesses

    return round(score, 2)


def _compute_support_entry(price: float, bars: list) -> tuple:
    """Derive a meaningful entry zone from candle data using EMA and recent swing lows.
    Returns (entry_low, entry_high, method_label).
    """
    if not bars or len(bars) < 10:
        return round(price * 0.95, 2), round(price * 1.01, 2), "5% pullback target"

    closes = [b["close"] for b in bars]
    lows   = [b["low"]   for b in bars]

    # EMA using all available bars (up to 50)
    period = min(50, len(closes))
    k = 2 / (period + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    ema = round(ema, 2)
    ema_label = f"EMA{period}"

    # Recent swing low: lowest daily wick in last 20 bars
    recent_lows = lows[-20:] if len(lows) >= 20 else lows
    swing_low = round(min(recent_lows), 2)

    dist_pct = (price - ema) / price  # positive = price above EMA

    if 0 < dist_pct <= 0.12:
        # Stock is above its EMA by < 12% — EMA is the natural limit-buy target
        return ema, round(ema * 1.02, 2), f"{ema_label} support (${ema:.2f})"
    elif dist_pct <= 0:
        # Already trading below its EMA — use swing low as floor
        entry_low = max(swing_low, round(price * 0.97, 2))
        return entry_low, round(price * 1.005, 2), f"Below {ema_label} — swing low (${swing_low:.2f})"
    else:
        # More than 12% above EMA — use swing low if it's meaningful, else 8% pullback
        if swing_low < price * 0.95:
            return swing_low, round(swing_low * 1.03, 2), f"Swing low (${swing_low:.2f})"
        return round(price * 0.92, 2), round(price * 0.97, 2), "8% pullback target"


async def _enrich_candidates(candidates: List[Dict], earnings_lookup: Dict = None) -> List[Dict]:
    """
    Enrich candidates with analyst consensus, insider signal, support-based entry zone,
    and earnings context. Finnhub-only — no Yahoo Finance.
    """
    if not candidates:
        return candidates
    from services import finnhub_service
    from datetime import date as _date

    tickers = [c["ticker"] for c in candidates]

    analyst_results = await _batch_gather(
        [finnhub_service.get_analyst_summary(t) for t in tickers],
        batch_size=3, delay=1.2,
    )
    insider_results = await _batch_gather(
        [finnhub_service.get_insider_summary(t) for t in tickers],
        batch_size=3, delay=1.2,
    )
    candle_results = await _batch_gather(
        [finnhub_service.get_candles(t, period="3mo", interval="1d") for t in tickers],
        batch_size=3, delay=1.2,
    )
    earnings_results = await _batch_gather(
        [finnhub_service.get_ticker_earnings_data(t) for t in tickers],
        batch_size=3, delay=1.0,
    )

    for c, analyst, insider, bars, earnings in zip(
        candidates, analyst_results, insider_results, candle_results, earnings_results
    ):
        a         = analyst  if isinstance(analyst,  dict) else {}
        ins       = insider  if isinstance(insider,  str)  else ""
        bars_list = bars     if isinstance(bars,     list) else []
        earn_data = earnings if isinstance(earnings, dict) else {}

        price = c.get("price", 0)

        # ATR fallback: 2% of price (no Yahoo Finance TA)
        atr_14 = price * 0.02
        c["atr_14"] = atr_14

        # ── Support-based entry zone (from Finnhub candles) ───────────────────
        if price and bars_list:
            entry_low, entry_high, entry_method = _compute_support_entry(price, bars_list)
            c["entry_low"]    = entry_low
            c["entry_high"]   = entry_high
            c["entry_method"] = entry_method
        else:
            entry_low = c.get("entry_low", round(price * 0.97, 2))
            c["entry_method"] = "near current price"

        c["stop_loss"] = round(max(entry_low - 2.0 * atr_14, entry_low * 0.82), 2)
        target_price = c.get("target", price * 1.40)
        risk   = max(entry_low - c["stop_loss"], 0.01)
        reward = max(target_price - entry_low, 0)
        c["rr"] = round(reward / risk, 1)
        c["ta_summary"] = ""

        # ── 52-week range ─────────────────────────────────────────────────────
        w52h = c.get("week_52_high")
        w52l = c.get("week_52_low")
        range_str = ""
        if w52h and w52l and w52h > w52l and price:
            pct_from_high = (w52h - price) / w52h * 100
            range_pct = (price - w52l) / (w52h - w52l) * 100
            range_str = (
                f"52W ${w52l:.2f}–${w52h:.2f} "
                f"({range_pct:.0f}% of range, {pct_from_high:.1f}% off high)"
            )
        c["range_str"] = range_str

        # ── Analyst consensus ─────────────────────────────────────────────────
        analyst_line = ""
        buy  = a.get("analyst_buy",  0) or 0
        hold = a.get("analyst_hold", 0) or 0
        sell = a.get("analyst_sell", 0) or 0
        if (buy + hold + sell) > 0:
            analyst_line = f"Analysts: {buy}B/{hold}H/{sell}S"
        tgt_mean = a.get("target_price")
        tgt_low  = a.get("target_low")
        tgt_high = a.get("target_high")
        if tgt_mean and price:
            upside = (tgt_mean - price) / price * 100
            analyst_line += f" | Target ${tgt_mean:.0f} ({upside:+.0f}%)"
            if tgt_low and tgt_high:
                analyst_line += f" range ${tgt_low:.0f}–${tgt_high:.0f}"

        # ── Insider signal ────────────────────────────────────────────────────
        insider_line = ""
        if ins == "buying":
            insider_line = "Insiders: buying ▲"
        elif ins == "selling":
            insider_line = "Insiders: selling ▼"

        # ── Earnings context ──────────────────────────────────────────────────
        earnings_line = ""
        next_date = earn_data.get("next_date")
        last_surprise = earn_data.get("last_surprise_pct")
        if next_date:
            try:
                nd = _date.fromisoformat(next_date)
                days_out = (nd - _date.today()).days
                if days_out >= 0:
                    earnings_line = f"Earnings: {next_date} ({days_out}d out)"
                    if last_surprise is not None:
                        earnings_line += f" | Last surprise: {last_surprise:+.1f}%"
            except Exception:
                pass
        if not earnings_line and earnings_lookup:
            ed = earnings_lookup.get(c["ticker"])
            if ed:
                earnings_line = f"Earnings: {ed}"

        extras = [x for x in [analyst_line, insider_line, earnings_line] if x]
        if extras:
            c["fund_summary"] = c.get("fund_summary", "") + " | " + " | ".join(extras)

        c["_analyst"]       = a
        c["_insider"]       = ins
        c["_earnings_date"] = next_date or (earnings_lookup.get(c["ticker"]) if earnings_lookup else None)

    return candidates


async def screen_longterm_candidates(top_n: int = 8, earnings_lookup: Dict = None) -> List[Dict]:
    from services.cache_service import get_cached, set_cached
    _ck = "screener:longterm_v2"
    cached = get_cached(_ck)
    if cached is not None:
        _longterm_cache["ts"] = time.time()
        _longterm_cache["data"] = cached
        return cached[:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    all_tickers = [t for t, _ in EQUITY_UNIVERSE]
    model_map = EQUITY_MODEL

    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in all_tickers], batch_size=1, delay=1.0)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in all_tickers], batch_size=1, delay=1.0)

    candidates = []
    for ticker, quote, fund in zip(all_tickers, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund if isinstance(fund, dict) else {}
        price = q.get("price") or 0
        if not price:
            continue

        sector = q.get("sector", "")
        industry = q.get("industry", "")

        # Auto-detect business model from sector/industry if not manually mapped
        manual_model = model_map.get(ticker, "")
        if manual_model:
            model = manual_model
        else:
            sl = sector.lower()
            il = industry.lower()
            if any(k in sl for k in ["technology", "information technology"]):
                model = "saas" if any(k in il for k in ["software", "internet", "cloud"]) else "deeptech"
            elif "financial" in sl or "bank" in sl:
                model = "fintech" if any(k in il for k in ["payment", "processing", "fintech"]) else "financial"
            elif any(k in sl for k in ["health", "pharma", "biotech"]):
                model = "healthcare"
            elif any(k in sl for k in ["consumer", "retail"]):
                model = "consumer"
            elif any(k in sl for k in ["energy", "oil", "gas"]):
                model = "energy"
            elif any(k in sl for k in ["industrial", "manufactur"]):
                model = "industrial"
            else:
                model = ""

        score = _score_longterm(f, price, model)

        # Short float bonus/penalty
        short_float = q.get("short_float")
        if short_float is not None:
            if short_float > 0.20:   score -= 1.0
            elif short_float > 0.10: score -= 0.5

        entry_low  = round(price * 0.97, 2)
        entry_high = round(price * 1.03, 2)
        stop_loss  = round(price * 0.85, 2)
        target     = round(price * 1.25, 2)
        rr = round((target - price) / max(price - stop_loss, 0.01), 1)

        parts = []
        if f.get("pe_ratio"):                     parts.append(f"P/E {f['pe_ratio']:.1f}")
        if f.get("forward_pe"):                   parts.append(f"FwdP/E {f['forward_pe']:.1f}")
        if f.get("peg_ratio"):                    parts.append(f"PEG {f['peg_ratio']:.2f}")
        if f.get("ps_ratio"):                     parts.append(f"P/S {f['ps_ratio']:.1f}")
        if f.get("pb_ratio"):                     parts.append(f"P/B {f['pb_ratio']:.1f}")
        if f.get("revenue_growth") is not None:   parts.append(f"RevGrowth {f['revenue_growth']*100:.1f}%")
        if f.get("earnings_growth") is not None:  parts.append(f"EPSGrowth {f['earnings_growth']*100:.1f}%")
        if f.get("gross_margins") is not None:    parts.append(f"GrossMargin {f['gross_margins']*100:.1f}%")
        if f.get("operating_margin") is not None: parts.append(f"OpMargin {f['operating_margin']*100:.1f}%")
        if f.get("profit_margin") is not None:    parts.append(f"NetMargin {f['profit_margin']*100:.1f}%")
        if f.get("roe") is not None:              parts.append(f"ROE {f['roe']*100:.1f}%")
        if f.get("debt_to_equity") is not None:   parts.append(f"D/E {f['debt_to_equity']:.0f}")
        if f.get("dividend_yield"):               parts.append(f"Div {f['dividend_yield']*100:.1f}%")
        if short_float is not None and short_float > 0.05:
            parts.append(f"Short {short_float*100:.0f}%")
        if f.get("short_ratio"):                  parts.append(f"ShortRatio {f['short_ratio']:.1f}d")
        if f.get("free_cashflow"):
            fcf = f["free_cashflow"]
            parts.append(f"FCF {'${:.1f}B'.format(fcf/1e9) if abs(fcf) >= 1e9 else '${:.0f}M'.format(fcf/1e6)}")

        candidates.append({
            "ticker": ticker,
            "name": q.get("name", ticker),
            "price": price,
            "sector": sector,
            "industry": industry,
            "business_model": model,
            "week_52_high": q.get("week_52_high"),
            "week_52_low": q.get("week_52_low"),
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
    set_cached("screener:longterm_v2", candidates, ttl=86400)
    return candidates[:top_n]


# ─── Long-term prompt builder ─────────────────────────────────────────────────

def _build_longterm_prompt(
    candidates: List[Dict],
    market_overview: Dict,
    date_str: str,
) -> str:
    rows = []
    for i, c in enumerate(candidates, 1):
        model_label = c.get("business_model", "")
        entry_basis = c.get("entry_method", "technical level")
        rows.append(
            f"#{i} {c['ticker']} ({c['name']}) [{model_label}] — ${c['price']:.2f} | Sector: {c.get('sector', '')}\n"
            f"   Fundamentals: {c['fund_summary']}\n"
            f"   Entry target: ${c['entry_low']:.2f}–${c['entry_high']:.2f} ({entry_basis}) | "
            f"Stop ${c['stop_loss']:.2f} | 12mo Target ${c['target']:.2f} | R/R 1:{c['rr']}"
        )
    candidates_block = "\n".join(rows)
    spy_c = market_overview.get("spy_change_pct", 0)
    vix = market_overview.get("vix") or 20
    ticker_map = " | ".join(f"{c['ticker']}={c['name']}" for c in candidates)
    time_note = _market_time_context(market_overview, "the next session")
    regime = assess_market_regime(market_overview)
    macro_lines = [f"SPY: {spy_c:+.1f}% | VIX: {vix:.1f}"]
    if regime.get("sector_rotation"):
        macro_lines.append(f"Sector rotation: {regime['sector_rotation']}")
    if regime.get("yield_context"):
        macro_lines.append(regime["yield_context"])
    if regime.get("macro_stats"):
        macro_lines.append(regime["macro_stats"])
    if regime.get("policy_stance"):
        macro_lines.append(f"Policy stance: {regime['policy_stance']}")
    if regime.get("upcoming_events"):
        macro_lines.append(f"Upcoming risk events: {regime['upcoming_events']}")
    macro_block = "\n".join(macro_lines)

    return f"""You are an expert long-term growth and value investor. Today is {date_str}.{time_note}

Evaluate these stocks as 6–12 month conviction plays. Focus on business quality, fundamentals, valuation, and what Wall Street analysts are saying.

Business model tags — use to calibrate your investment lens:
- mega: look for reasonable valuation and continued market dominance
- saas: prioritize ARR growth rate, net revenue retention, gross margin expansion
- platform: network effects and user growth trajectory matter most
- fintech: payment volume growth, take-rate expansion, regulatory moat
- deeptech: revenue acceleration and credible path to profitability
- healthcare: pipeline strength, patent moat, regulatory catalysts
- financial: NIM expansion, credit quality, capital return discipline
- consumer: same-store sales growth, unit economics, brand pricing power
- industrial/energy: cycle positioning, dividend yield, balance sheet health

HOW TO USE ANALYST & INSIDER DATA (shown in fund_summary):
- "Analysts: 18B/5H/2S | Target $425 (+22%)" → strong buy consensus with meaningful upside to target → positive signal
- "Analysts: 5B/8H/6S | Target $95 (-3%)" → divided consensus, target below current price → cautious
- "Insiders: buying ▲" → management buying own stock → strong bullish confirmation signal
- "Insiders: selling ▼" → insider distribution → investigate whether thesis is intact
- "Earnings: 2025-05-28" → upcoming earnings = near-term catalyst OR binary risk event

TICKER IDENTITY — memorize before writing any thesis:
{ticker_map}
Every pick's thesis must reference ONLY the company matched to that ticker above.

=== MACRO CONTEXT ===
{macro_block}

=== CANDIDATES ===
{candidates_block}

=== YOUR JOB ===
1. Select 6–8 of the best candidates for a 6–12 month hold (fewer is fine if quality is low)
2. Set realistic levels:
   - Entry zone: use the suggested technical entry (EMA50 / swing low shown above); adjust only if you have a stronger level
   - Stop loss: already set below entry — tighten only if there is a cleaner technical floor
   - Target: realistic 12-month price target (15–40% upside typical)
3. Write a 2-sentence thesis. EACH sentence must cite a specific numeric data point (e.g. "Revenue grew 28% YoY", "Forward P/E of 22x vs sector median of 31x", "18 of 25 analysts rate Buy with consensus target 22% above current price" — not vague claims like "strong fundamentals")
4. Name one specific near-term catalyst and one key risk that could impair the thesis
5. Confidence 8–10: strong growth + reasonable valuation + analyst consensus confirming + clear catalyst. Below 6 = don't include.

RULES:
- trade_type must be one of:
  growth (accelerating revenue, expanding market)
  value (quality business trading below intrinsic value)
  dividend (income + stability, yield-driven total return)
  turnaround (recovering from operational or structural setback)
- market_summary must reference VIX {vix:.1f}, SPY trend, and macro implications for long-term positioning
- Stop must be BELOW entry
- CRITICAL: thesis for ticker X must ONLY describe the company named for X in the TICKER IDENTITY table

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on macro backdrop and whether conditions favor building long-term positions now",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "MSFT",
      "trade_type": "growth",
      "entry_low": 420.00,
      "entry_high": 432.00,
      "stop_loss": 368.00,
      "target": 530.00,
      "risk_reward": "1:2.1",
      "confidence": 8,
      "thesis": "Azure cloud revenue grew 31% YoY in the most recent quarter, accelerating for the third consecutive period as AI workloads drive enterprise adoption. Forward P/E of 34x sits below the 3-year average of 38x despite a structurally higher earnings trajectory from Copilot monetization.",
      "catalyst": "Specific: Copilot enterprise seat expansion announcements at Build conference, or Azure market share gains from Google/AWS",
      "key_risk": "Key risk: margin compression if AI infrastructure capex outpaces Azure revenue growth in the next 2 quarters"
    }}
  ],
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

    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    regime = assess_market_regime(market_overview)

    quote_yf, ta, quote_fh, analyst, earnings_raw = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="3mo", interval="1d"),
        finnhub_service.get_quote(ticker),
        finnhub_service.get_analyst_summary(ticker),
        finnhub_service.get_ticker_earnings_data(ticker),
        return_exceptions=True,
    )

    quote_data = quote_yf if isinstance(quote_yf, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fh_data = quote_fh if isinstance(quote_fh, dict) else {}
    analyst_data = analyst if isinstance(analyst, dict) else {}
    earnings_data = earnings_raw if isinstance(earnings_raw, dict) else {}

    price = fh_data.get("price") or fh_data.get("prev_close") or quote_data.get("price") or ta_data.get("price") or 0
    name = quote_data.get("name") or fh_data.get("name") or ticker
    change_pct = fh_data.get("change_pct") or quote_data.get("change_pct", 0) or 0
    sector = quote_data.get("sector") or fh_data.get("sector") or ""

    if not price:
        return {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}

    atr = ta_data.get("atr_14")
    levels = compute_atr_levels(price, atr)

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
    else:
        signals.append(f"Day change: {change_pct:+.1f}%")
        high = fh_data.get("high") or 0
        low_price = fh_data.get("low") or 0
        if high and low_price and price and high != low_price:
            pct_pos = (price - low_price) / (high - low_price) * 100
            signals.append(f"At {pct_pos:.0f}% of day range (L${low_price:.2f}/H${high:.2f})")
        if change_pct > 3: signals.append("Strong bullish momentum")
        elif change_pct > 1: signals.append("Mild bullish momentum")
        elif change_pct < -3: signals.append("Strong selling pressure")
        elif change_pct < -1: signals.append("Mild bearish pressure")

    ta_summary = ta_data.get("signal_summary") or (f"Price action: {change_pct:+.1f}% (last close)" if change_pct else "Price action analysis")
    rr_est = round((levels["target_2r"] - price) / levels["risk_per_share"], 1) if levels["risk_per_share"] > 0 else 0
    signals_str = ", ".join(signals) if signals else f"Day change: {change_pct:+.1f}%"

    # ── Analyst consensus ─────────────────────────────────────────────────────
    a_buy  = analyst_data.get("analyst_buy", 0) or 0
    a_hold = analyst_data.get("analyst_hold", 0) or 0
    a_sell = analyst_data.get("analyst_sell", 0) or 0
    a_target = analyst_data.get("target_price")
    analyst_line = ""
    if (a_buy + a_hold + a_sell) > 0:
        analyst_line = f"Analyst consensus: {a_buy}B/{a_hold}H/{a_sell}S"
        if a_target and price:
            analyst_line += f" | Street target ${a_target:.0f} ({(a_target-price)/price*100:+.0f}%)"

    # ── Earnings proximity ────────────────────────────────────────────────────
    earnings_line = ""
    earnings_warning = ""
    if earnings_data:
        next_date = earnings_data.get("next_date")
        last_surprise = earnings_data.get("last_surprise_pct")
        if next_date:
            from datetime import date as _date
            try:
                nd = _date.fromisoformat(next_date)
                days_out = (nd - _date.today()).days
                if 0 <= days_out <= 14:
                    earnings_line = f"Earnings in {days_out} day{'s' if days_out != 1 else ''} ({next_date})"
                    if last_surprise is not None:
                        earnings_line += f" | Last EPS surprise: {last_surprise:+.1f}%"
                    if days_out <= 3:
                        earnings_warning = "⚠️ EARNINGS IN ≤3 DAYS — elevated IV risk; directional trades should be avoided unless thesis is earnings-driven."
            except Exception:
                pass

    # ── 52-week range context ─────────────────────────────────────────────────
    w52h = quote_data.get("week_52_high")
    w52l = quote_data.get("week_52_low")
    range_line = ""
    if w52h and w52l and w52h > w52l:
        range_pct = (price - w52l) / (w52h - w52l) * 100
        pct_from_high = (w52h - price) / w52h * 100
        range_line = f"52W: ${w52l:.2f}–${w52h:.2f} | at {range_pct:.0f}% of range ({pct_from_high:.1f}% off 52W high)"

    # ── Short interest ────────────────────────────────────────────────────────
    short_ratio = quote_data.get("short_ratio") or fh_data.get("short_ratio")
    short_line = f"Short ratio: {short_ratio:.1f}d to cover" if short_ratio else ""

    extra_lines = "\n".join(x for x in [analyst_line, earnings_line, range_line, short_line] if x)

    time_note = _market_time_context(market_overview, next_trading_day_label).strip()
    context_note = time_note if time_note else "Using most recent available price and indicator data."

    prompt = f"""You are an expert day trader. {context_note}
Analyze {ticker} ({name}) and decide: BUY, HOLD, or AVOID for {next_trading_day_label}'s open.

PRICE & TECHNICALS:
- Price: ${price:.2f} | Day change: {change_pct:+.1f}% | Sector: {sector}
- TA summary: {ta_summary}
- Signals: {signals_str}
- Entry: ${levels['entry_low']:.2f}–${levels['entry_high']:.2f} | Stop: ${levels['stop_loss']:.2f} | Target: ${levels['target_2r']:.2f} | R/R 1:{rr_est}

CONTEXT:
{extra_lines if extra_lines else "No additional context available."}
{earnings_warning}

MARKET: Bias {regime['overall_bias']} | VIX {regime['vix']} ({regime['vix_regime']}) | {regime['direction']}

DECISION RULES:
- BUY: clean TA setup + regime alignment + R/R ≥ 1:1.5
- HOLD: mixed signals, weak volume, or setup needs confirmation at open
- AVOID: broken setup, counter-regime, or earnings within 3 days without clear catalyst
- Lower confidence if analyst consensus is mostly SELL or Street target is below current price

Thesis must cite at least 2 specific numeric values (e.g. "RSI at 44, ADX 31 trending"). Do NOT use vague phrases like "strong momentum" without a number.

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
  "thesis": "2 sentences citing at least 2 specific numeric values each.",
  "catalyst": "Specific trigger for this trade at {next_trading_day_label}'s open",
  "key_risk": "Primary setup risk or invalidation level"
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, _call_claude, prompt)

    try:
        result = _parse_response(raw)
    except json.JSONDecodeError:
        result = {
            "ticker": ticker, "recommendation": "hold", "trade_type": "unknown",
            "entry_low": levels["entry_low"], "entry_high": levels["entry_high"],
            "stop_loss": levels["stop_loss"], "target": levels["target_2r"],
            "risk_reward": f"1:{rr_est}", "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
            "catalyst": "", "key_risk": "",
        }

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

_LT_MODEL_LENS: Dict[str, str] = {
    "mega":       "dominant incumbent — evaluate valuation vs moat sustainability and ability to compound at scale",
    "saas":       "recurring revenue flywheel — ARR growth, NRR >120%, gross margin expansion are the key metrics",
    "platform":   "network-effect compounder — user growth trajectory, take-rate expansion, moat defensibility",
    "fintech":    "financial infrastructure — payment volume growth, margin expansion, regulatory positioning",
    "deeptech":   "technology moat — R&D differentiation, path to dominant revenue",
    "healthcare": "innovation durability — pipeline, patent runway, pricing power",
    "consumer":   "brand compounder — unit economics, same-store sales growth, pricing power; not a platform moat thesis",
    "financial":  "capital allocator — NIM, credit quality cycle, ROE consistency, dividend growth",
    "industrial": "durable cash flow — cycle positioning, capital discipline, long-term demand tailwinds",
    "energy":     "commodity + capital return — reserve life, dividend sustainability, energy transition positioning",
}


async def _analyze_ticker_longterm(ticker: str) -> Dict:
    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote, ta, fund, analyst, insider, earnings_raw = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="1y", interval="1wk"),
        finnhub_service.get_fundamentals_mapped(ticker),
        finnhub_service.get_analyst_summary(ticker),
        finnhub_service.get_insider_summary(ticker),
        finnhub_service.get_ticker_earnings_data(ticker),
        return_exceptions=True,
    )

    quote_data = quote if isinstance(quote, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}
    analyst_data = analyst if isinstance(analyst, dict) else {}
    insider_signal = insider if isinstance(insider, str) else ""
    earnings_data = earnings_raw if isinstance(earnings_raw, dict) else {}

    price = quote_data.get("price") or ta_data.get("price") or 0
    name = quote_data.get("name", ticker)
    sector = quote_data.get("sector", "")
    model = EQUITY_MODEL.get(ticker.upper(), "")

    if not price:
        return {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}

    # ATR-based stops (falls back to fixed % if TA unavailable)
    atr_14 = ta_data.get("atr_14") or (price * 0.02)
    entry_low  = round(price * 0.97, 2)
    entry_high = round(price * 1.03, 2)
    stop_loss  = round(max(price - 3.0 * atr_14, price * 0.78), 2)
    target     = round(price * 1.45, 2)
    rr = round((target - price) / max(price - stop_loss, 0.01), 1)

    def _pct(v, label):
        return f"{label}: {v*100:.1f}%" if v is not None else None

    fund_lines = [x for x in [
        f"Trailing P/E: {fund_data['pe_ratio']:.1f}" if fund_data.get("pe_ratio") else None,
        f"Forward P/E: {fund_data['forward_pe']:.1f}" if fund_data.get("forward_pe") else None,
        f"PEG ratio: {fund_data['peg_ratio']:.2f}" if fund_data.get("peg_ratio") else None,
        f"P/S: {fund_data['ps_ratio']:.1f}" if fund_data.get("ps_ratio") else None,
        _pct(fund_data.get("revenue_growth"), "Revenue growth YoY"),
        _pct(fund_data.get("earnings_growth"), "EPS growth YoY"),
        _pct(fund_data.get("profit_margin"), "Net margin"),
        _pct(fund_data.get("gross_margins"), "Gross margin"),
        _pct(fund_data.get("operating_margin"), "Op margin"),
        _pct(fund_data.get("roe"), "ROE"),
        f"D/E: {fund_data['debt_to_equity']:.1f}" if fund_data.get("debt_to_equity") is not None else None,
        f"FCF: ${fund_data['free_cashflow']/1e9:.1f}B" if fund_data.get("free_cashflow") else None,
        f"Div yield: {fund_data['dividend_yield']*100:.1f}%" if fund_data.get("dividend_yield") else None,
    ] if x]
    fund_str = " | ".join(fund_lines) if fund_lines else "Fundamental data not available for this ticker."

    # Fixed bug: was embedding raw Python dict literal as text in the prompt
    model_context = (f"\nBusiness model: {model} — {_LT_MODEL_LENS.get(model, 'evaluate long-term compounding potential')}") if model else ""

    # 52-week range
    w52h = quote_data.get("week_52_high")
    w52l = quote_data.get("week_52_low")
    range_str = ""
    if w52h and w52l and w52h > w52l:
        pct = (price - w52l) / (w52h - w52l) * 100
        off_high = (w52h - price) / w52h * 100
        range_str = f"52W range: ${w52l:.2f}–${w52h:.2f} | at {pct:.0f}% of range ({off_high:.1f}% off high)"

    a_buy  = analyst_data.get("analyst_buy", 0) or 0
    a_hold = analyst_data.get("analyst_hold", 0) or 0
    a_sell = analyst_data.get("analyst_sell", 0) or 0
    a_target = analyst_data.get("target_price")
    a_target_low = analyst_data.get("target_low")
    a_target_high = analyst_data.get("target_high")
    analyst_str = ""
    if (a_buy + a_hold + a_sell) > 0:
        analyst_str = f"Analyst consensus: {a_buy}B/{a_hold}H/{a_sell}S"
        if a_target and price:
            analyst_str += f" | Target ${a_target:.0f} ({(a_target-price)/price*100:+.0f}%)"
            if a_target_low and a_target_high:
                analyst_str += f" range ${a_target_low:.0f}–${a_target_high:.0f}"
    insider_str = f"Insiders: {insider_signal} {'▲' if insider_signal == 'buying' else '▼' if insider_signal == 'selling' else ''}" if insider_signal else ""

    earnings_str = ""
    if earnings_data:
        nd = earnings_data.get("next_date")
        surprise = earnings_data.get("last_surprise_pct")
        if nd:
            from datetime import date as _date
            try:
                days_out = (_date.fromisoformat(nd) - _date.today()).days
                if days_out >= 0:
                    earnings_str = f"Next earnings: {nd} ({days_out}d out)"
                    if surprise is not None:
                        earnings_str += f" | Last EPS surprise: {surprise:+.1f}%"
            except Exception:
                pass

    extra_lines = "\n".join(x for x in [analyst_str, insider_str, earnings_str, range_str] if x)

    prompt = f"""You are an expert long-term investor. Analyze {ticker} ({name}) for a 6–18 month hold.
{model_context}

STOCK: {ticker} | Price: ${price:.2f} | Sector: {sector}

FUNDAMENTALS: {fund_str}

{extra_lines}

ATR-14: ${atr_14:.2f} | Entry: ${entry_low:.2f}–${entry_high:.2f} | Stop: ${stop_loss:.2f} (~3× ATR) | Target: ${target:.2f} | R/R 1:{rr}

DECISION:
- BUY: revenue growth + healthy margins + reasonable valuation + clear catalyst
- HOLD: sound business but expensive, uncertain trajectory, or better entry available
- AVOID: declining revenue, margin compression, excessive debt, or structural headwinds

TRADE_TYPE must be: growth | value | dividend | turnaround | compounder | disruptor | platform | deep-tech | speculative

Write 3 thesis sentences, EACH citing a specific numeric value from the data above. Do NOT reference RSI, MACD, ATR, or VWAP in the thesis.

Respond ONLY with valid JSON, no markdown:
{{
  "ticker": "{ticker}",
  "recommendation": "buy",
  "trade_type": "compounder",
  "entry_low": {entry_low},
  "entry_high": {entry_high},
  "stop_loss": {stop_loss},
  "target": {target},
  "risk_reward": "1:{rr}",
  "confidence": 7,
  "thesis": "3 sentences with specific numeric data explaining the BUY/HOLD/AVOID call.",
  "catalyst": "Specific event or development that could move the stock in the next 6–18 months",
  "key_risk": "Primary structural risk that could permanently impair the thesis"
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=1200))

    try:
        result = _parse_response(raw)
    except json.JSONDecodeError:
        result = {
            "ticker": ticker, "recommendation": "hold", "trade_type": "growth",
            "entry_low": entry_low, "entry_high": entry_high, "stop_loss": stop_loss,
            "target": target, "risk_reward": f"1:{rr}", "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
            "catalyst": "", "key_risk": "",
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


# ─── Discovery scoring ────────────────────────────────────────────────────────

def _score_discovery(fund: Dict, price: float, model: str = "") -> float:
    # Hard gate: only platform-economics businesses qualify for a 10-year disruption thesis.
    # Consumer brands, industrials, energy, and financials have physical-expansion or
    # commodity constraints that structurally limit 10x potential.
    if model in ("consumer", "industrial", "energy", "financial", "mega"):
        return -99.0

    score = 0.0

    rev = fund.get("revenue_growth")
    if rev is not None:
        if rev > 0.40:    score += 8
        elif rev > 0.25:  score += 6
        elif rev > 0.15:  score += 3
        elif rev > 0.05:  score += 1
        else:             score -= 5

    # Gross margin — distinguishes software/platform from commodity businesses
    gm = fund.get("gross_margins")
    if gm is not None:
        if gm > 0.70:   score += 5
        elif gm > 0.50: score += 3
        elif gm > 0.30: score += 1
        elif gm < 0.20: score -= 2

    earn = fund.get("earnings_growth")
    if earn is not None:
        if earn > 0.50:    score += 4
        elif earn > 0.20:  score += 2
        elif earn > 0:     score += 1
        elif earn < -0.20: score -= 2

    fcf = fund.get("free_cashflow")
    if fcf is not None:
        score += 3 if fcf > 0 else 0

    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 30:    score += 1
        elif de > 200: score -= 3

    # Platform / SaaS structural bonus — network effects compound over a decade
    if model in ("platform", "saas"):
        score += 2.0
    elif model == "fintech":
        score += 1.0

    return round(score, 2)


async def screen_discovery_candidates(top_n: int = 8, earnings_lookup: Dict = None) -> List[Dict]:
    now = time.time()
    if _discovery_cache["ts"] and (now - _discovery_cache["ts"]) < _FUND_CACHE_TTL and _discovery_cache["data"]:
        return _discovery_cache["data"][:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    # Only fetch discovery-eligible tickers — filtered by business model tag
    disc_entries = [(t, m) for t, m in EQUITY_UNIVERSE if m in _DISCOVERY_ELIGIBLE]
    tickers = [t for t, _ in disc_entries]
    model_map = {t: m for t, m in disc_entries}

    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in tickers], batch_size=5, delay=0.8)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in tickers], batch_size=3, delay=1.2)

    candidates = []
    for ticker, quote, fund in zip(tickers, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund if isinstance(fund, dict) else {}
        price = q.get("price") or 0
        if not price:
            continue

        model = model_map.get(ticker, "")
        score = _score_discovery(f, price, model)
        if score <= -99:
            continue  # hard-gated by business model

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
            "business_model": model,
            "fund_summary": " | ".join(parts) if parts else "Limited data",
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "target": target,
            "rr": rr,
            "score": score,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Enrich top candidates with analyst consensus + insider signal + earnings date
    top = candidates[:max(top_n + 4, 14)]
    top = await _enrich_candidates(top, earnings_lookup)
    top.sort(key=lambda x: x["score"], reverse=True)

    _discovery_cache["ts"] = time.time()
    _discovery_cache["data"] = top + candidates[len(top):]
    return top[:top_n]


# ─── Discovery prompt builder ─────────────────────────────────────────────────

def _build_discovery_prompt(candidates: List[Dict], date_str: str, market_overview: Dict = None) -> str:
    rows = []
    for i, c in enumerate(candidates, 1):
        model_label = c.get("business_model", "")
        rows.append(
            f"#{i} {c['ticker']} ({c['name']}) [{model_label}] — ${c['price']:.2f} | Sector: {c.get('sector', '')}\n"
            f"   Growth metrics: {c['fund_summary']}\n"
            f"   Suggested: Entry ${c['entry_low']:.2f}–${c['entry_high']:.2f} | "
            f"Stop ${c['stop_loss']:.2f} (~35% below) | 10-Year Base Target ${c['target']:.2f} (2.5x floor) | R/R 1:{c['rr']}"
        )
    candidates_block = "\n".join(rows)
    ticker_map = " | ".join(f"{c['ticker']}={c['name']}" for c in candidates)
    time_note = _market_time_context(market_overview or {}, "the next session")
    regime = assess_market_regime(market_overview or {})
    macro_lines = []
    if regime.get("sector_rotation"):
        macro_lines.append(f"Sector rotation: {regime['sector_rotation']}")
    if regime.get("yield_context"):
        macro_lines.append(regime["yield_context"])
    macro_note = ("\n\n=== MACRO CONTEXT ===\n" + "\n".join(macro_lines)) if macro_lines else ""

    return f"""You are an expert long-term investor focused on 10-year compounders. Today is {date_str}.{time_note}{macro_note}

Your goal: identify companies worth holding for 10 years — businesses that can compound returns through earnings growth, market expansion, and durable competitive advantages. These are higher-growth candidates pre-screened from the universe, but the core question is always: "Would a patient investor be meaningfully rewarded holding this through a full decade?"

Business model lens (calibrate your thesis accordingly):
- saas: ARR growth rate, net revenue retention >120%, gross margin expansion — recurring revenue flywheel
- platform: network effect durability, user growth trajectory, take-rate expansion over time
- fintech: payment volume compounding, margin expansion as scale grows, regulatory positioning
- deeptech: technology differentiation depth, path from R&D to dominant revenue, patent moat longevity

HOW TO USE ANALYST & INSIDER DATA (shown in growth metrics):
- Strong analyst buy consensus (e.g. "15B/3H/1S") → institutional conviction aligns with thesis
- "Insiders: buying ▲" → management putting own money in → long-term confidence signal
- "Earnings: date" → upcoming catalyst that could accelerate or de-risk the thesis

TICKER IDENTITY — memorize before writing any thesis:
{ticker_map}
Every pick's thesis must reference ONLY the company matched to that ticker above.
Do NOT confuse similar-looking tickers.

=== CANDIDATES (pre-screened for long-term growth potential, ranked by fundamentals score) ===
{candidates_block}

=== YOUR JOB ===
1. Select 6–8 of the best candidates for a 10-year hold — fewer is fine, never force weak picks
2. Set price targets reflecting realistic 10-year compounding:
   - confidence ≥ 8 with strong growth and durable advantages → target 4x–8x
   - confidence 6–7 with solid but uncertain position → target 2.5x–4x
   - confidence < 6 → do not include
3. Write a 2-sentence thesis. EACH sentence must cite a specific numeric value (e.g. "Revenue growing at 38% YoY", "Gross margin of 76%" — not vague phrases like "strong growth potential")
4. Name one specific catalyst that could accelerate the long-term thesis
5. Name one key structural risk that could permanently impair the thesis

RULES:
- trade_type must be one of: compounder (durable earnings growth), disruptor (redefining an industry), platform (network effects), deep-tech (proprietary technology moat), speculative (high risk/reward)
- Stop losses must stay wide (30–40%) — these positions are held through volatility
- market_summary must address whether macro conditions favor accumulating long-term positions now
- Do NOT reference RSI, MACD, VWAP, or any short-term technical signals
- CRITICAL: thesis for ticker X must ONLY describe the company named for X in TICKER IDENTITY above

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on whether macro conditions favor building 10-year speculative positions now",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "PLTR",
      "trade_type": "disruptor",
      "entry_low": 85.00,
      "entry_high": 95.00,
      "stop_loss": 60.00,
      "target": 600.00,
      "risk_reward": "1:10",
      "confidence": 8,
      "thesis": "Palantir's US commercial revenue grew 71% YoY in the most recent quarter, compounding on AIP platform adoption across 300+ enterprise customers. With a 42% adjusted operating margin already achieved and a $4B+ pipeline expanding into commercial AI workflows, the path to $200B+ market cap in a decade is structurally sound.",
      "catalyst": "Specific: US government AI contract expansion or S&P 500 inclusion triggering institutional accumulation",
      "key_risk": "Key risk: AI platform commoditization by hyperscalers (AWS, Azure, GCP) reducing Palantir's enterprise pricing power"
    }}
  ],
  "generated_at": "{date_str}"
}}"""


# ─── Bargain universe ────────────────────────────────────────────────────────
#
# Quality businesses that are cheap in absolute price or undervalued on
# fundamentals — value plays, turnarounds, beaten-down leaders.
# Distinct from the main growth universe; scoring favors value metrics.

BARGAIN_UNIVERSE: List[tuple] = [
    # ── Digital banks & fintech ──────────────────────────────────────────────
    ("SOFI",  "fintech"),    # SoFi — digital bank, strong member + revenue growth
    ("NU",    "fintech"),    # Nu Holdings — fastest-growing LatAm fintech
    ("PAYO",  "fintech"),    # Payoneer — B2B cross-border payments platform
    ("GDOT",  "fintech"),    # Green Dot — banking-as-a-service, steady FCF
    # ── Tech & software ─────────────────────────────────────────────────────
    ("SNAP",  "platform"),   # Snap — social media, improving margins + ARPU
    ("PATH",  "saas"),       # UiPath — automation SaaS, strong ARR
    ("FRSH",  "saas"),       # Freshworks — CRM/support SaaS, growing SMB base
    ("CLBT",  "saas"),       # Cellebrite — digital intelligence SaaS, gov contracts
    # ── AI & frontier tech ──────────────────────────────────────────────────
    ("SOUN",  "deeptech"),   # SoundHound — voice AI, licensing model, growing RPO
    ("IONQ",  "deeptech"),   # IonQ — quantum computing leader, DoD contracts
    ("JOBY",  "deeptech"),   # Joby Aviation — FAA-approved eVTOL, Toyota-backed
    # ── Telecom & infrastructure ─────────────────────────────────────────────
    ("ERIC",  "platform"),   # Ericsson — 5G global leader, cheap vs AT&T/VZ
    ("NOK",   "deeptech"),   # Nokia — 5G IP portfolio, network infrastructure
    # ── Auto ─────────────────────────────────────────────────────────────────
    ("F",     "consumer"),   # Ford — EV pivot, single-digit P/E, dividend
    # ── Healthcare ───────────────────────────────────────────────────────────
    ("FTRE",  "healthcare"), # Fortrea — CRO spun from LabCorp, growing backlog
    ("MDXG",  "healthcare"), # MiMedx — regenerative medicine, improving margins
    # ── Industrial & energy ──────────────────────────────────────────────────
    ("LBRT",  "industrial"), # Liberty Energy — oilfield services, FCF-positive
    # ── Consumer & retail ────────────────────────────────────────────────────
    ("AMCX",  "consumer"),   # AMC Networks — cable TV deep value, FCF 15%+ yield
    ("KSS",   "consumer"),   # Kohl's — deep discount retailer, strong FCF
    ("AAL",   "consumer"),   # American Airlines — airline turnaround, debt reduction
    # ── Business services ────────────────────────────────────────────────────
    ("TASK",  "platform"),   # TaskUs — AI-enabled BPO, growing enterprise contracts
    ("CTLP",  "fintech"),    # Cantaloupe — unattended retail IoT, growing SaaS rev
]

BARGAIN_MODEL: Dict[str, str] = {t: m for t, m in BARGAIN_UNIVERSE}


# ─── Hidden Gems universe ────────────────────────────────────────────────────
#
# Quality small/mid-cap businesses with low retail coverage. Under-the-radar
# compounders and innovators that most retail investors have never heard of.

HIDDEN_GEMS_UNIVERSE: List[tuple] = [
    # ── DevOps & data infrastructure ────────────────────────────────────────
    ("FROG",  "saas"),        # JFrog — universal artifact management SaaS
    ("GTLB",  "saas"),        # GitLab — end-to-end DevSecOps platform, AI code review
    ("WK",    "saas"),        # Workiva — financial reporting & compliance SaaS
    # ── Semiconductor & hardware ─────────────────────────────────────────────
    ("ACMR",  "deeptech"),    # ACM Research — advanced wafer cleaning equipment
    ("SMTC",  "deeptech"),    # Semtech — LoRa IoT connectivity chips
    ("ALGM",  "deeptech"),    # Allegro MicroSystems — sensing + power ICs
    ("COHU",  "deeptech"),    # Cohu — semiconductor test handlers
    ("AMBA",  "deeptech"),    # Ambarella — edge AI video processing chips
    # ── Vertical fintech ────────────────────────────────────────────────────
    ("FLYW",  "fintech"),     # Flywire — vertical payment software (edu/health)
    # ── Healthcare innovations ───────────────────────────────────────────────
    ("PRCT",  "healthcare"),  # Procept BioRobotics — robotic prostate surgery
    ("NVST",  "healthcare"),  # Envista Holdings — dental equipment + consumables
    ("LMAT",  "healthcare"),  # LeMaitre Vascular — specialty surgical devices
    # ── Durable compounders ──────────────────────────────────────────────────
    ("AAON",  "industrial"),  # AAON Inc — HVAC manufacturer, 20%+ margins
    ("CRVL",  "financial"),   # CorVel Corp — risk management, 40-yr track record
    # ── SMB & mid-market SaaS ────────────────────────────────────────────────
    ("DOCS",  "saas"),        # Doximity — physician digital platform, 80%+ gross margin
    ("WEAV",  "saas"),        # Weave Communications — patient/SMB comms SaaS
]

UNKNOWNS_UNIVERSE  = HIDDEN_GEMS_UNIVERSE   # alias used in screener
UNKNOWNS_MODEL: Dict[str, str] = {t: m for t, m in HIDDEN_GEMS_UNIVERSE}


async def screen_unknowns_candidates(top_n: int = 5, earnings_lookup: Dict = None) -> List[Dict]:
    from services.cache_service import get_cached, set_cached
    _ck = "screener:hidden_gems_v2"
    cached = get_cached(_ck)
    if cached is not None:
        _unknowns_cache["ts"] = time.time()
        _unknowns_cache["data"] = cached
        return cached[:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    tickers = [t for t, _ in UNKNOWNS_UNIVERSE]
    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in tickers], batch_size=1, delay=1.0)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in tickers], batch_size=1, delay=1.0)

    candidates = []
    for ticker, quote, fund in zip(tickers, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund  if isinstance(fund,  dict) else {}
        price = q.get("price") or 0
        if not price:
            continue

        model = UNKNOWNS_MODEL.get(ticker, "")
        score = _score_longterm(f, price, model)

        entry_low  = round(price * 0.97, 2)
        entry_high = round(price * 1.03, 2)
        stop_loss  = round(price * 0.85, 2)
        target     = round(price * 1.30, 2)
        rr = round((target - price) / max(price - stop_loss, 0.01), 1)

        parts = []
        if f.get("pe_ratio"):                     parts.append(f"P/E {f['pe_ratio']:.1f}")
        if f.get("forward_pe"):                   parts.append(f"FwdP/E {f['forward_pe']:.1f}")
        if f.get("revenue_growth") is not None:   parts.append(f"RevGrowth {f['revenue_growth']*100:.1f}%")
        if f.get("gross_margins") is not None:    parts.append(f"GrossMargin {f['gross_margins']*100:.1f}%")
        if f.get("profit_margin") is not None:    parts.append(f"NetMargin {f['profit_margin']*100:.1f}%")
        if f.get("roe") is not None:              parts.append(f"ROE {f['roe']*100:.1f}%")
        if f.get("debt_to_equity") is not None:   parts.append(f"D/E {f['debt_to_equity']:.0f}")

        candidates.append({
            "ticker": ticker,
            "name": q.get("name", ticker),
            "price": price,
            "sector": q.get("sector", ""),
            "industry": q.get("industry", ""),
            "business_model": model,
            "week_52_high": q.get("week_52_high"),
            "week_52_low":  q.get("week_52_low"),
            "fund_summary": " | ".join(parts) if parts else "Limited data",
            "entry_low": entry_low, "entry_high": entry_high,
            "stop_loss": stop_loss, "target": target, "rr": rr,
            "score": score,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    _unknowns_cache["ts"] = time.time()
    _unknowns_cache["data"] = candidates
    set_cached("screener:hidden_gems_v2", candidates, ttl=86400)
    return candidates[:top_n]


# ─── Bargain scoring ─────────────────────────────────────────────────────────

def _score_bargain(fund: Dict, price: float, model: str = "") -> float:
    """Score stocks on value metrics. Rewards cheap + quality; penalizes value traps."""
    score = 0.0

    # P/E — core value metric; anything above ~25x is not a bargain
    pe = fund.get("pe_ratio")
    if pe is not None and pe > 0:
        if pe < 10:      score += 6
        elif pe < 15:    score += 4
        elif pe < 20:    score += 2
        elif pe < 25:    score += 0.5
        elif pe < 35:    score -= 1.5  # premium valuation — not a bargain
        elif pe > 35:    score -= 3.0  # expensive; quality scores won't rescue it

    # P/S — important where P/E is unavailable (pre-profit)
    ps = fund.get("ps_ratio")
    if ps is not None and ps > 0:
        if ps < 2:       score += 4
        elif ps < 5:     score += 2
        elif ps < 10:    score += 0.5
        elif ps > 20:    score -= 2

    # FCF — clearest sign of real business (not just accounting profit)
    fcf = fund.get("free_cashflow")
    if fcf is not None:
        score += 3 if fcf > 0 else -3

    # Revenue trend — must not be in terminal decline
    rev = fund.get("revenue_growth")
    if rev is not None:
        if rev > 0.15:    score += 2
        elif rev > 0.05:  score += 1
        elif rev > -0.05: score += 0   # flat is okay for value
        elif rev < -0.15: score -= 4   # meaningful decline = value trap risk

    # Profit margin — quality gate
    margin = fund.get("profit_margin")
    if margin is not None:
        if margin > 0.15:   score += 3
        elif margin > 0.08: score += 2
        elif margin > 0:    score += 1
        elif margin < -0.05: score -= 4

    # ROE — capital efficiency
    roe = fund.get("roe")
    if roe is not None:
        if roe > 0.20:   score += 2
        elif roe > 0.10: score += 1
        elif roe < 0:    score -= 2

    # Dividend yield — income bonus; value stocks often pay dividends
    div = fund.get("dividend_yield")
    if div:
        if div > 0.05:   score += 3
        elif div > 0.03: score += 2
        elif div > 0.01: score += 1

    # Debt to equity — penalize over-levered traps
    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 50:    score += 1
        elif de > 200: score -= 3

    # Price accessibility bonus — absolute affordability for retail investors
    if price < 20:    score += 1.5
    elif price < 50:  score += 1.0
    elif price < 100: score += 0.5

    # Business model context — consumer/financial/industrial are traditional value sectors
    if model in ("financial", "consumer", "industrial", "energy"):
        score += 0.5

    return round(score, 2)


async def screen_bargain_candidates(top_n: int = 10, earnings_lookup: Dict = None) -> List[Dict]:
    from services.cache_service import get_cached, set_cached
    _ck = "screener:bargain_v2"
    cached = get_cached(_ck)
    if cached is not None:
        _bargain_cache["ts"] = time.time()
        _bargain_cache["data"] = cached
        return cached[:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    tickers = [t for t, _ in BARGAIN_UNIVERSE]

    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in tickers], batch_size=1, delay=1.0)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in tickers], batch_size=1, delay=1.0)

    candidates = []
    for ticker, quote, fund in zip(tickers, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund if isinstance(fund, dict) else {}
        price = q.get("price") or 0
        if not price or not (5.0 <= price <= 20.0):
            continue

        model = BARGAIN_MODEL.get(ticker, "")
        score = _score_longterm(f, price, model)

        # High short interest on a value stock can signal contrarian opportunity or value trap
        short_float = q.get("short_float")
        if short_float is not None and short_float > 0.15:
            score -= 1.0   # heavily shorted value stocks are often traps

        entry_low  = round(price * 0.97, 2)
        entry_high = round(price * 1.03, 2)
        stop_loss  = round(price * 0.82, 2)
        target     = round(price * 1.40, 2)
        rr = round((target - price) / max(price - stop_loss, 0.01), 1)

        parts = []
        if f.get("pe_ratio"):                   parts.append(f"P/E {f['pe_ratio']:.1f}")
        if f.get("ps_ratio"):                   parts.append(f"P/S {f['ps_ratio']:.1f}")
        if f.get("revenue_growth") is not None: parts.append(f"RevGrowth {f['revenue_growth']*100:.1f}%")
        if f.get("profit_margin") is not None:  parts.append(f"Margin {f['profit_margin']*100:.1f}%")
        if f.get("roe") is not None:            parts.append(f"ROE {f['roe']*100:.1f}%")
        if f.get("dividend_yield"):             parts.append(f"Div {f['dividend_yield']*100:.1f}%")
        if f.get("debt_to_equity") is not None: parts.append(f"D/E {f['debt_to_equity']:.0f}")
        if short_float is not None and short_float > 0.05:
            parts.append(f"Short {short_float*100:.0f}%")
        if f.get("free_cashflow"):
            fcf = f["free_cashflow"]
            parts.append(f"FCF {'${:.1f}B'.format(fcf/1e9) if abs(fcf) >= 1e9 else '${:.0f}M'.format(fcf/1e6)}")

        candidates.append({
            "ticker": ticker,
            "name": q.get("name", ticker),
            "price": price,
            "sector": q.get("sector", ""),
            "business_model": model,
            "fund_summary": " | ".join(parts) if parts else "Limited data",
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "target": target,
            "rr": rr,
            "score": score,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    _bargain_cache["ts"] = time.time()
    _bargain_cache["data"] = candidates
    set_cached("screener:bargain_v2", candidates, ttl=86400)
    return candidates[:top_n]


# ─── Bargain prompt builder ───────────────────────────────────────────────────

def _build_bargain_prompt(
    candidates: List[Dict],
    market_overview: Dict,
    date_str: str,
) -> str:
    rows = []
    for i, c in enumerate(candidates, 1):
        model_label = c.get("business_model", "")
        entry_basis = c.get("entry_method", "technical level")
        rows.append(
            f"#{i} {c['ticker']} ({c['name']}) [{model_label}] — ${c['price']:.2f} | Sector: {c.get('sector', '')}\n"
            f"   Value metrics: {c['fund_summary']}\n"
            f"   Entry target: ${c['entry_low']:.2f}–${c['entry_high']:.2f} ({entry_basis}) | Stop ${c['stop_loss']:.2f} | Target ${c['target']:.2f} | R/R 1:{c['rr']}"
        )
    candidates_block = "\n".join(rows)
    spy_c = market_overview.get("spy_change_pct", 0)
    vix = market_overview.get("vix") or 20
    ticker_map = " | ".join(f"{c['ticker']}={c['name']}" for c in candidates)
    time_note = _market_time_context(market_overview, "the next session")
    regime = assess_market_regime(market_overview)
    macro_lines = [f"SPY: {spy_c:+.1f}% | VIX: {vix:.1f}"]
    if regime.get("sector_rotation"):
        macro_lines.append(f"Sector rotation: {regime['sector_rotation']}")
    if regime.get("yield_context"):
        macro_lines.append(regime["yield_context"])
    if regime.get("macro_stats"):
        macro_lines.append(regime["macro_stats"])
    if regime.get("policy_stance"):
        macro_lines.append(f"Policy stance: {regime['policy_stance']}")
    if regime.get("upcoming_events"):
        macro_lines.append(f"Upcoming risk events: {regime['upcoming_events']}")
    macro_block = "\n".join(macro_lines)

    return f"""You are an expert value investor. Today is {date_str}.{time_note}

Your goal: identify quality businesses that are genuinely undervalued — true bargains where the current price does not reflect fundamental worth. These stocks are cheaper in price or valuation than the broader market, but the screen is intelligent: cheap alone is never enough.

A REAL "Bargain Buy" is:
- A fundamentally sound business with durable economics (positive FCF, real margins, defensible model)
- Trading at an attractive valuation due to market pessimism, sector rotation, or temporary headwinds
- Capable of rewarding patient investors through earnings recovery, multiple expansion, or dividend compounding

AVOID these value traps:
- Revenue in prolonged structural decline with no credible catalyst
- Dividends funded by debt or unsustainable payout ratios
- Over-levered balance sheets where a downturn could cause permanent impairment
- Commodity businesses with no pricing power trading cheap for good reasons
- High short interest (Short >15%) on a stock with declining fundamentals — the market is often right

BUSINESS MODEL LENSES (calibrate your thesis):
- financial: P/B, ROE trajectory, capital return. "1-3yr" or "3-5yr"
- consumer: brand durability, pricing power, cash generation. "1-3yr" or "3-5yr"
- industrial: cycle positioning, capex discipline, order backlog. "1-3yr" or "3-5yr"
- energy: FCF yield, dividend coverage, reserve life. "1-3yr" or "3-5yr"
- healthcare: pipeline replacement, patent runway, earnings quality. "3-5yr"
- fintech: payment network durability, margin recovery runway. "3-5yr"
- platform: user monetization trajectory even at low current multiples. "3-5yr"
- saas/deeptech: path to profitability, moat at discounted entry. "3-5yr" or "5-10yr"

HOW TO USE ANALYST & INSIDER DATA (shown in fund_summary):
- "Analysts: 12B/6H/2S | Target $85 (+35%)" → Street sees meaningful rerating catalyst → supports conviction
- "Analysts: 3B/10H/8S | Target $38 (-5%)" → analysts are skeptical → require stronger fundamental justification
- "Insiders: buying ▲" → management accumulating at these levels → strong contrarian confirmation
- "Insiders: selling ▼" → insiders exiting → be cautious, risk of further deterioration
- "Earnings: 2025-06-05" → imminent catalyst — frame as opportunity (beat = re-rate) or risk (miss = more pain)

TICKER IDENTITY — memorize before writing any thesis:
{ticker_map}
Every pick's thesis must reference ONLY the company matched to that ticker above.

=== MACRO CONTEXT ===
{macro_block}

=== VALUE CANDIDATES (ranked by fundamentals + valuation score) ===
{candidates_block}

=== YOUR JOB ===
1. Select 8–12 of the best candidates — genuine bargains, NOT just anything cheap
2. Assign hold_horizon: "1-3yr" (near-term catalyst), "3-5yr" (multi-year recovery), "5-10yr" (durable long-term compounder at great price)
3. Set realistic price targets: value reversion typically 25–80%; do NOT project the same 200–400% as speculative plays
4. trade_type must be one of: value, dividend, turnaround, compounder, growth
5. Write a 2-sentence thesis. EACH sentence must cite a specific numeric value (P/E, yield, margin, revenue growth %, analyst upside %). NO vague phrases.
6. Confidence ≥ 7: clear undervaluation + durable business + credible catalyst + analyst/insider support. Do not include < 6.

RULES:
- Stop must be BELOW entry
- market_summary must reference VIX {vix:.1f} and whether macro conditions favor value accumulation
- CRITICAL: thesis for ticker X must ONLY describe the company named for X in TICKER IDENTITY above

Respond ONLY with valid JSON, no markdown:
{{
  "market_summary": "2 sentences on macro context and whether value stocks look attractive relative to growth now",
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "PYPL",
      "hold_horizon": "3-5yr",
      "trade_type": "value",
      "entry_low": 60.00,
      "entry_high": 65.00,
      "stop_loss": 50.00,
      "target": 95.00,
      "risk_reward": "1:2.4",
      "confidence": 7,
      "thesis": "PayPal's trailing P/E of 14x sits at a 5-year low despite a payment volume base exceeding $1.5 trillion annually, with $5B in annual free cash flow funding buybacks at a historic discount. Operating margin recovery from 21% toward a 25%+ target as cost restructuring completes is the primary rerating catalyst.",
      "catalyst": "Margin recovery announcement or accelerating Venmo monetization in next 2 earnings",
      "key_risk": "Continued market share loss to Apple Pay, Cash App, and Stripe in checkout flows"
    }}
  ],
  "generated_at": "{date_str}"
}}"""


# ─── Unified prompt builder ──────────────────────────────────────────────────

def _build_unified_prompt(
    candidates: List[Dict],
    market_overview: Dict,
    date_str: str,
) -> str:
    cat_label_map = {"long_term": "LONG-TERM", "bargain": "BARGAIN", "hidden_gem": "HIDDEN GEM"}
    rows = []
    for i, c in enumerate(candidates, 1):
        model_label = c.get("business_model", "")
        entry_str = (
            f"${c['entry_low']:.2f}–${c['entry_high']:.2f}"
            if c.get("entry_low") else "near current price"
        )
        atr = c.get("atr_14")
        atr_str = f" | ATR ${atr:.2f}" if atr else ""
        ta_str  = c.get("ta_summary", "")
        range_str = c.get("range_str", "")
        cat = cat_label_map.get(c.get("hint_category", "long_term"), "LONG-TERM")
        row = (
            f"#{i} [{cat}] {c['ticker']} ({c['name']}) [{model_label}] — ${c['price']:.2f} | {c.get('sector','')}{atr_str}\n"
            f"   Fund: {c['fund_summary']}\n"
            f"   Entry: {entry_str} | Stop ${c['stop_loss']:.2f} | Target ${c.get('target',0):.2f} | R/R 1:{c['rr']}"
        )
        if ta_str:   row += f"\n   TA: {ta_str}"
        if range_str: row += f"\n   {range_str}"
        rows.append(row)

    candidates_block = "\n".join(rows)
    spy_c = market_overview.get("spy_change_pct", 0)
    vix   = market_overview.get("vix") or 20
    ticker_map = " | ".join(f"{c['ticker']}={c['name']}" for c in candidates)
    time_note  = _market_time_context(market_overview, "the next session")
    regime     = assess_market_regime(market_overview)
    macro_lines = [f"SPY {spy_c:+.1f}% | VIX {vix:.1f}"]
    if regime.get("sector_rotation"):   macro_lines.append(regime["sector_rotation"])
    if regime.get("yield_context"):     macro_lines.append(regime["yield_context"])
    if regime.get("macro_stats"):       macro_lines.append(regime["macro_stats"])
    if regime.get("upcoming_events"):   macro_lines.append(f"Risk events: {regime['upcoming_events']}")
    macro_block = " | ".join(macro_lines)

    return f"""You are an expert long-term investor. Today is {date_str}.{time_note}

TICKER IDENTITY — verify before writing any thesis:
{ticker_map}

CATEGORIES in this candidate pool:
- LONG-TERM: quality compounders, strong fundamentals, established businesses
- BARGAIN: quality stocks priced $5–$20/share — real businesses at accessible prices
- HIDDEN GEM: under-the-radar small/mid-cap; low retail coverage but strong fundamentals

MACRO: {macro_block}

=== CANDIDATES ===
{candidates_block}

=== YOUR JOB ===
1. Select best picks: 2–3 LONG-TERM, 2–3 BARGAIN, 2–3 HIDDEN GEM (total 6–9)
2. Assign matching category to each pick
3. Use suggested entry zone; calibrate stop/target to conviction level
4. trade_type: growth, value, dividend, turnaround, compounder, disruptor, platform, deep-tech, speculative
5. Write a 3-sentence thesis citing SPECIFIC numeric data (revenue %, P/E, margins, analyst upside, insider activity)
6. Confidence ≥ 7 requires strong thesis + multiple confirming signals. Omit picks below 6.
7. Stop must be BELOW entry for every pick.

CRITICAL: thesis for ticker X must ONLY describe the company shown for X in TICKER IDENTITY above.

Respond ONLY with valid JSON, no markdown:
{{
  "bias": "bullish",
  "picks": [
    {{
      "rank": 1,
      "ticker": "MSFT",
      "category": "long_term",
      "trade_type": "compounder",
      "entry_low": 420.00,
      "entry_high": 432.00,
      "stop_loss": 340.00,
      "target": 680.00,
      "risk_reward": "1:2.8",
      "confidence": 8,
      "thesis": "3 sentences with specific numeric data.",
      "catalyst": "Specific near-term catalyst",
      "key_risk": "Main risk to the thesis"
    }}
  ],
  "generated_at": "{date_str}"
}}"""


# ─── Combined all-modes single-ticker analysis ───────────────────────────────

async def analyze_ticker_all_modes(
    ticker: str,
    market_overview: Dict,
    next_trading_day_label: str = "Tomorrow",
) -> Dict:
    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote_yf, ta, fund, quote_fh, analyst, insider, earnings = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="1y", interval="1d"),
        finnhub_service.get_fundamentals_mapped(ticker),
        finnhub_service.get_quote(ticker),
        finnhub_service.get_analyst_summary(ticker),
        finnhub_service.get_insider_summary(ticker),
        finnhub_service.get_ticker_earnings_data(ticker),
        return_exceptions=True,
    )

    quote_data = quote_yf if isinstance(quote_yf, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}
    fh_data = quote_fh if isinstance(quote_fh, dict) else {}
    analyst_data = analyst if isinstance(analyst, dict) else {}
    insider_signal = insider if isinstance(insider, str) else ""
    earnings_data = earnings if isinstance(earnings, dict) else {}

    price = (fh_data.get("price") or fh_data.get("prev_close") or
             quote_data.get("price") or ta_data.get("price") or 0)
    name = quote_data.get("name") or fh_data.get("name") or ticker
    change_pct_atm = fh_data.get("change_pct") or quote_data.get("change_pct", 0) or 0
    sector = quote_data.get("sector") or fh_data.get("sector") or ""
    industry = quote_data.get("industry") or ""

    if not price:
        err = {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}
        return {"ticker": ticker, "unified": err}

    regime = assess_market_regime(market_overview)

    # ── ATR-based stop distances (replaces fixed-% math) ─────────────────────
    atr_14 = ta_data.get("atr_14") or (price * 0.02)
    ema50 = ta_data.get("ema_50")
    sma200 = ta_data.get("sma_200")

    # Floors prevent stops from being unrealistically tight or blown out
    h1_stop = round(max(price - 2.0 * atr_14, price * 0.82), 2)
    h2_stop = round(max(price - 3.5 * atr_14, price * 0.70), 2)
    h3_stop = round(max(price - 5.0 * atr_14, price * 0.55), 2)

    h1_levels = {
        "entry_low": round(price * 0.97, 2), "entry_high": round(price * 1.02, 2),
        "stop_loss": h1_stop, "target": round(price * 1.30, 2),
    }
    h2_levels = {
        "entry_low": round(price * 0.96, 2), "entry_high": round(price * 1.03, 2),
        "stop_loss": h2_stop, "target": round(price * 1.75, 2),
    }
    h3_levels = {
        "entry_low": round(price * 0.94, 2), "entry_high": round(price * 1.05, 2),
        "stop_loss": h3_stop, "target": round(price * 3.00, 2),
    }

    # ── Technical analysis (full signal set) ─────────────────────────────────
    ta_lines = []
    if ta_data:
        sig_summary = ta_data.get("signal_summary", "")
        bull_sigs = ta_data.get("bull_signals", [])
        bear_sigs = ta_data.get("bear_signals", [])
        if sig_summary:
            ta_lines.append("Trend: " + sig_summary)
        if bull_sigs:
            ta_lines.append("Bull: " + "; ".join(bull_sigs[:5]))
        if bear_sigs:
            ta_lines.append("Bear: " + "; ".join(bear_sigs[:5]))

        rsi = ta_data.get("rsi_14")
        adx = ta_data.get("adx")
        bb_pct = ta_data.get("bb_pct")
        rel_vol = ta_data.get("rel_volume")
        key_vals = []
        if rsi is not None: key_vals.append(f"RSI {rsi:.0f}")
        if adx is not None: key_vals.append(f"ADX {adx:.0f}")
        if atr_14: key_vals.append(f"ATR ${atr_14:.2f}")
        if rel_vol is not None: key_vals.append(f"RelVol {rel_vol:.1f}x")
        if bb_pct is not None: key_vals.append(f"BB%B {bb_pct:.2f}")
        if key_vals:
            ta_lines.append("Metrics: " + " | ".join(key_vals))

        if ema50 and sma200:
            cross = "Golden Cross" if ema50 > sma200 else "Death Cross"
            pct_vs_200 = (price - sma200) / sma200 * 100
            ta_lines.append(
                cross + " (EMA50 vs SMA200) | Price "
                + f"{pct_vs_200:+.1f}%" + " vs SMA200 ($" + f"{sma200:.2f})"
            )
    else:
        ta_lines.append(f"Day change: {change_pct_atm:+.1f}%")

    ta_block = "\n".join(ta_lines)

    # ── 52-week range context ─────────────────────────────────────────────────
    w52h = quote_data.get("week_52_high")
    w52l = quote_data.get("week_52_low")
    range_str = ""
    if w52h and w52l and w52h > w52l:
        pct_from_high = (w52h - price) / w52h * 100
        range_pct = (price - w52l) / (w52h - w52l) * 100
        range_str = (
            "52W Range: $" + f"{w52l:.2f}" + "–$" + f"{w52h:.2f}"
            + " | Price at " + f"{range_pct:.0f}%" + " of range ("
            + f"{pct_from_high:.1f}%" + " off 52W high)"
        )

    # ── Fundamentals (complete set) ───────────────────────────────────────────
    def _pct(v, label):
        return (label + ": " + f"{v*100:.1f}%") if v is not None else None

    fund_lines = [x for x in [
        ("P/E: " + f"{fund_data['pe_ratio']:.1f}") if fund_data.get("pe_ratio") else None,
        ("FwdP/E: " + f"{fund_data['forward_pe']:.1f}") if fund_data.get("forward_pe") else None,
        ("P/S: " + f"{fund_data['ps_ratio']:.1f}") if fund_data.get("ps_ratio") else None,
        ("P/B: " + f"{fund_data['pb_ratio']:.1f}") if fund_data.get("pb_ratio") else None,
        _pct(fund_data.get("revenue_growth"), "RevGrowth"),
        _pct(fund_data.get("earnings_growth"), "EPSGrowth"),
        _pct(fund_data.get("gross_margins"), "GrossMargin"),
        _pct(fund_data.get("operating_margin"), "OpMargin"),
        _pct(fund_data.get("profit_margin"), "NetMargin"),
        _pct(fund_data.get("roe"), "ROE"),
        ("D/E: " + f"{fund_data['debt_to_equity']:.0f}") if fund_data.get("debt_to_equity") is not None else None,
        ("FCF: $" + f"{fund_data['free_cashflow']/1e9:.1f}B") if fund_data.get("free_cashflow") else None,
        ("Div: " + f"{fund_data['dividend_yield']*100:.1f}%") if fund_data.get("dividend_yield") else None,
        ("ShortRatio: " + f"{fund_data['short_ratio']:.1f}d") if fund_data.get("short_ratio") else None,
    ] if x]
    fund_str = " | ".join(fund_lines) if fund_lines else "Fundamental data limited"

    # ── Analyst consensus ─────────────────────────────────────────────────────
    analyst_str = ""
    a_buy = analyst_data.get("analyst_buy", 0) or 0
    a_hold = analyst_data.get("analyst_hold", 0) or 0
    a_sell = analyst_data.get("analyst_sell", 0) or 0
    a_target = analyst_data.get("target_price")
    a_target_low = analyst_data.get("target_low")
    a_target_high = analyst_data.get("target_high")
    a_count = analyst_data.get("analyst_count", 0) or 0
    if (a_buy + a_hold + a_sell) > 0:
        analyst_str = f"Analysts ({a_count}): {a_buy}B/{a_hold}H/{a_sell}S"
        if a_target and price:
            upside = (a_target - price) / price * 100
            analyst_str += f" | Target ${a_target:.0f} ({upside:+.0f}%)"
            if a_target_low and a_target_high:
                analyst_str += f" range ${a_target_low:.0f}–${a_target_high:.0f}"

    insider_str = ""
    if insider_signal:
        arrow = "▲" if insider_signal == "buying" else ("▼" if insider_signal == "selling" else "")
        insider_str = ("Insiders: " + insider_signal + (" " + arrow if arrow else "")).strip()

    # ── Earnings context ──────────────────────────────────────────────────────
    earnings_str = ""
    if earnings_data:
        next_date = earnings_data.get("next_date")
        last_surprise = earnings_data.get("last_surprise_pct")
        if next_date:
            from datetime import date as _date
            try:
                nd = _date.fromisoformat(next_date)
                days_out = (nd - _date.today()).days
                if days_out >= 0:
                    earnings_str = f"Next earnings: {next_date} ({days_out}d out)"
                    if last_surprise is not None:
                        earnings_str += f" | Last EPS surprise: {last_surprise:+.1f}%"
            except Exception:
                pass

    # ── Auto-detect business model from sector/industry ───────────────────────
    manual_model = EQUITY_MODEL.get(ticker.upper(), "")
    if manual_model:
        model = manual_model
    else:
        sl = sector.lower()
        il = industry.lower()
        if any(k in sl for k in ["technology", "information technology"]):
            model = "saas" if any(k in il for k in ["software", "internet", "cloud"]) else "deeptech"
        elif "financial" in sl or "bank" in sl:
            model = "fintech" if any(k in il for k in ["payment", "processing", "fintech"]) else "financial"
        elif any(k in sl for k in ["health", "pharma", "biotech"]):
            model = "healthcare"
        elif any(k in sl for k in ["consumer", "retail"]):
            model = "consumer"
        elif any(k in sl for k in ["energy", "oil", "gas"]):
            model = "energy"
        elif any(k in sl for k in ["industrial", "manufactur"]):
            model = "industrial"
        else:
            model = ""

    model_lens_map = {
        "mega":       "dominant incumbent — value vs moat sustainability; usually 1-3yr or 3-5yr",
        "saas":       "recurring revenue flywheel — ARR growth, NRR >120%, gross margin expansion; often 3-5yr or 5-10yr",
        "platform":   "network-effect compounder — user growth, take-rate expansion; often 5-10yr",
        "fintech":    "financial infrastructure — payment volume growth, margin expansion; 3-5yr or 5-10yr",
        "deeptech":   "technology moat — R&D differentiation, path to dominant revenue; usually 5-10yr",
        "healthcare": "innovation durability — pipeline, patent runway, pricing power; 3-5yr or 5-10yr",
        "consumer":   "brand compounder — unit economics, same-store sales, pricing power; typically 3-5yr",
        "financial":  "capital allocator — ROE consistency, dividend growth; 1-3yr or 3-5yr",
        "industrial": "durable cash flow — cycle positioning, capital discipline; 1-3yr or 3-5yr",
        "energy":     "commodity + capital return — reserve life, dividend sustainability; 1-3yr or 3-5yr",
    }
    model_lens = model_lens_map.get(model, "evaluate long-term compounding potential")
    model_context = ("\nBUSINESS MODEL: " + model + " — " + model_lens) if model else ""

    time_note = _market_time_context(market_overview, next_trading_day_label)

    extra_lines = [x for x in [analyst_str, insider_str, earnings_str, range_str] if x]
    extra_block = "\n".join(extra_lines)

    prompt = (
        "You are a long-term investment expert. Analyze " + ticker + " (" + name
        + ") and assign it ONE best-fit hold horizon." + time_note + "\n\n"
        "STOCK: " + ticker + " | Price: $" + f"{price:.2f}" + " | Sector: " + sector + model_context + "\n"
        "ATR-14: $" + f"{atr_14:.2f}" + " — calibrate stop distances to this, not fixed percentages\n\n"
        "TECHNICAL ANALYSIS:\n" + ta_block + "\n\n"
        "FUNDAMENTALS: " + fund_str + "\n"
        + (extra_block + "\n" if extra_block else "")
        + "MARKET: Bias " + regime["overall_bias"] + " | VIX " + str(regime["vix"]) + "\n\n"
        "HOLD HORIZONS — choose the single best fit:\n"
        '- "1-3yr": near-term catalysts, valuation gap. Stop ~2x ATR. Target 25-50%.'
        " (Default: Entry $" + f"{h1_levels['entry_low']:.2f}" + "–$" + f"{h1_levels['entry_high']:.2f}"
        + ", Stop $" + f"{h1_levels['stop_loss']:.2f}" + ", Target $" + f"{h1_levels['target']:.2f}" + ")\n"
        '- "3-5yr": proven compounder, durable growth. Stop ~3.5x ATR. Target 50-120%.'
        " (Default: Entry $" + f"{h2_levels['entry_low']:.2f}" + "–$" + f"{h2_levels['entry_high']:.2f}"
        + ", Stop $" + f"{h2_levels['stop_loss']:.2f}" + ", Target $" + f"{h2_levels['target']:.2f}" + ")\n"
        '- "5-10yr": decade-long compounder/disruptor. Stop ~5x ATR. Target 150-400%.'
        " (Default: Entry $" + f"{h3_levels['entry_low']:.2f}" + "–$" + f"{h3_levels['entry_high']:.2f}"
        + ", Stop $" + f"{h3_levels['stop_loss']:.2f}" + ", Target $" + f"{h3_levels['target']:.2f}" + ")\n\n"
        "DECISION:\n"
        "- BUY: durable business, clear compounding path, attractive entry\n"
        "- HOLD: sound business but expensive or uncertain growth trajectory\n"
        "- AVOID: structural decline, broken economics, no pricing power — NOT merely because it lacks a platform moat\n\n"
        "trade_type must be: growth, value, dividend, turnaround, compounder, disruptor, platform, deep-tech, speculative\n"
        "Write 3-4 thesis sentences, each citing a specific numeric value from the data above. Do NOT mention RSI, MACD, ATR, or VWAP in the thesis.\n\n"
        "Respond ONLY with valid JSON, no markdown:\n"
        "{\n"
        '  "ticker": "' + ticker + '",\n'
        '  "hold_horizon": "3-5yr",\n'
        '  "recommendation": "buy",\n'
        '  "trade_type": "compounder",\n'
        "  \"entry_low\": " + str(h2_levels["entry_low"]) + ",\n"
        "  \"entry_high\": " + str(h2_levels["entry_high"]) + ",\n"
        "  \"stop_loss\": " + str(h2_levels["stop_loss"]) + ",\n"
        "  \"target\": " + str(h2_levels["target"]) + ",\n"
        '  "risk_reward": "1:2.5",\n'
        '  "confidence": 7,\n'
        '  "thesis": "3-4 sentences with specific numeric data from the data above.",\n'
        '  "catalyst": "Specific event or development that could accelerate the thesis",\n'
        '  "key_risk": "Main risk that could permanently impair the thesis"\n'
        "}"
    )

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=1800))

    try:
        parsed = _parse_response(raw)
    except json.JSONDecodeError:
        parsed = {}

    hz = parsed.get("hold_horizon", "3-5yr")
    default_levels = h1_levels if hz == "1-3yr" else (h3_levels if hz == "5-10yr" else h2_levels)

    el = parsed.get("entry_low", default_levels["entry_low"])
    eh = parsed.get("entry_high", default_levels["entry_high"])
    stop = parsed.get("stop_loss", default_levels["stop_loss"])
    tgt = parsed.get("target", default_levels["target"])
    mid = (el + eh) / 2
    if stop >= mid: stop = default_levels["stop_loss"]
    if tgt <= mid: tgt = default_levels["target"]
    risk = round(mid - stop, 2)
    reward = round(tgt - mid, 2)
    rr = f"1:{reward/risk:.1f}" if risk > 0 else "—"

    unified = {
        "ticker": ticker,
        "hold_horizon": hz,
        "recommendation": parsed.get("recommendation", "hold"),
        "trade_type": parsed.get("trade_type", "compounder"),
        "entry_low": round(el, 2),
        "entry_high": round(eh, 2),
        "stop_loss": round(stop, 2),
        "target": round(tgt, 2),
        "risk_reward": parsed.get("risk_reward") or rr,
        "confidence": max(1, min(10, int(parsed.get("confidence", 5)))),
        "thesis": parsed.get("thesis", "Analysis unavailable — AI response could not be parsed."),
        "catalyst": parsed.get("catalyst", ""),
        "key_risk": parsed.get("key_risk", ""),
        "theoretical": _compute_theoretical(el, eh, stop, tgt, 1000),
    }

    return {"ticker": ticker, "unified": unified}


# ─── Discovery single-ticker analysis ────────────────────────────────────────

async def _analyze_ticker_discovery(ticker: str) -> Dict:
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote, fund, quote_fh, analyst, earnings_raw = await asyncio.gather(
        yf_svc.get_quote(ticker),
        finnhub_service.get_fundamentals_mapped(ticker),
        finnhub_service.get_quote(ticker),
        finnhub_service.get_analyst_summary(ticker),
        finnhub_service.get_ticker_earnings_data(ticker),
        return_exceptions=True,
    )

    quote_data = quote if isinstance(quote, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}
    fh_data = quote_fh if isinstance(quote_fh, dict) else {}
    analyst_data = analyst if isinstance(analyst, dict) else {}
    earnings_data = earnings_raw if isinstance(earnings_raw, dict) else {}

    price = (fh_data.get("price") or fh_data.get("prev_close") or
             quote_data.get("price") or 0)
    name = quote_data.get("name", ticker)
    sector = quote_data.get("sector", "")
    model = EQUITY_MODEL.get(ticker.upper(), "")

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

    disc_lenses = {
        "mega":       "dominant incumbent — can it sustain compounding at scale and defend market share over a decade?",
        "saas":       "recurring revenue flywheel — ARR growth, net revenue retention, and gross margin expansion are key",
        "platform":   "network-effect compounder — user growth trajectory, take-rate expansion, and moat defensibility",
        "fintech":    "financial infrastructure — payment volume, margin expansion, and regulatory positioning",
        "deeptech":   "technology-moat play — R&D differentiation, patent depth, and path to dominant revenue",
        "healthcare": "innovation durability — pipeline, patent runway, and pricing power",
        "consumer":   "brand compounder — unit economics durability, same-store sales growth, geographic expansion runway, and pricing power over a decade",
        "financial":  "capital allocator — ROE consistency, dividend growth, and ability to compound book value",
        "industrial": "durable cash flow — cycle positioning, capital discipline, and long-term demand tailwinds",
        "energy":     "commodity + capital return — reserve life, dividend sustainability, and energy transition positioning",
    }
    model_note = f"Business model: {model} — {disc_lenses.get(model, 'evaluate long-term compounding potential')}" if model else ""

    # Analyst + earnings context
    a_buy  = analyst_data.get("analyst_buy", 0) or 0
    a_hold = analyst_data.get("analyst_hold", 0) or 0
    a_sell = analyst_data.get("analyst_sell", 0) or 0
    a_target = analyst_data.get("target_price")
    analyst_line = ""
    if (a_buy + a_hold + a_sell) > 0:
        analyst_line = f"Analyst consensus: {a_buy}B/{a_hold}H/{a_sell}S"
        if a_target and price:
            analyst_line += f" | Street target ${a_target:.0f} ({(a_target-price)/price*100:+.0f}%)"

    earnings_line = ""
    if earnings_data:
        nd = earnings_data.get("next_date")
        surprise = earnings_data.get("last_surprise_pct")
        if nd:
            from datetime import date as _date
            try:
                days_out = (_date.fromisoformat(nd) - _date.today()).days
                if days_out >= 0:
                    earnings_line = f"Next earnings: {nd} ({days_out}d out)"
                    if surprise is not None:
                        earnings_line += f" | Last EPS surprise: {surprise:+.1f}%"
            except Exception:
                pass

    extra_block = "\n".join(x for x in [analyst_line, earnings_line] if x)

    prompt = f"""You are an expert long-term investor evaluating 10-year holds. Evaluate {ticker} ({name}) for a patient, long-horizon investor.

Stock: {ticker} | Price: ${price:.2f} | Sector: {sector}
{model_note}

GROWTH METRICS:
{fund_str}
{(chr(10) + extra_block) if extra_block else ""}
The key question: "Would a patient investor be well-rewarded holding this for 10 years?"
Consider:
1. Durable competitive advantages (brand, scale, switching costs, network effects, regulatory moat)
2. Ability to grow earnings or revenue meaningfully over the next decade
3. Is the market expanding, and does it have room to take more share?
4. Can it survive and thrive through at least one full economic cycle?

Decide:
- BUY: durable business, clear compounding path, attractive entry
- HOLD: sound business but valuation or growth trajectory makes the 10-year return uncertain
- AVOID: structural decline risk, pricing power loss, broken economics — NOT merely for lacking a platform moat

Suggested entry: ${entry_low:.2f}–${entry_high:.2f} | Stop: ${stop_loss:.2f} (~35% wide) | Base target: ${target:.2f} (2.5x)
High conviction (confidence ≥ 8): adjust target to 4–8x if earnings compounding supports it.

Each thesis sentence must cite at least one specific numeric value. Do NOT reference RSI, MACD, or short-term technicals.

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
  "thesis": "3 sentences: moat quality, growth trajectory with specific metrics, valuation or risk-adjusted return rationale.",
  "catalyst": "Specific event or development that could accelerate the 10-year thesis",
  "key_risk": "Structural risk that could permanently impair the thesis (not just volatility)"
}}"""

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(_executor, lambda: _call_claude(prompt, max_tokens=1200))

    try:
        result = _parse_response(raw)
    except json.JSONDecodeError:
        result = {
            "ticker": ticker, "recommendation": "hold", "trade_type": "disruptor",
            "entry_low": entry_low, "entry_high": entry_high, "stop_loss": stop_loss,
            "target": target, "risk_reward": f"1:{rr}", "confidence": 5,
            "thesis": "Analysis unavailable — AI response could not be parsed.",
            "catalyst": "", "key_risk": "",
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


# ─── Chat follow-up ───────────────────────────────────────────────────────────

async def chat_about_ticker(
    ticker: str,
    question: str,
    history: list,
    analysis_context: str = "",
) -> dict:
    """Answer a follow-up question about a ticker using the prior analysis as context."""
    ctx_block = f"Prior analysis summary:\n{analysis_context}" if analysis_context else ""
    system = (
        f"You are a knowledgeable stock analyst assistant helping with research on {ticker}.\n"
        + (ctx_block + "\n\n" if ctx_block else "")
        + "Format rules:\n"
        + "- Use **bold** for key terms, risk labels, and section titles\n"
        + "- Use bullet points (- ) for lists of 3 or more items\n"
        + "- Separate distinct points with blank lines\n"
        + "- Keep total response under 250 words unless depth is genuinely needed\n"
        + "- Be direct — skip preamble like 'Great question' or 'Certainly'"
    )

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": question})

    loop = asyncio.get_running_loop()

    def _call():
        client = _get_client()
        resp = client.messages.create(
            model=os.getenv("AI_MODEL", "claude-sonnet-4-6"),
            max_tokens=450,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        return resp.content[0].text.strip()

    answer = await loop.run_in_executor(_executor, _call)
    return {"ticker": ticker, "answer": answer}
