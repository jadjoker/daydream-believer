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
    breadth = f"{green}/{len(sectors)} sectors green"
    top_sectors = [s["name"] for s in sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)[:3]]
    bot_sectors = [s["name"] for s in sorted(sectors, key=lambda x: x.get("change_pct", 0))[:2]]

    raw_vix = market_overview.get("vix") or 0
    return {
        "vix": round(vix, 2),
        "vix_raw": raw_vix,   # 0 means unavailable (market closed, index halted)
        "vix_regime": vix_regime,
        "direction": direction,
        "avg_index_change": round(avg_change, 2),
        "breadth": breadth,
        "top_sectors": top_sectors,
        "weak_sectors": bot_sectors,
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
    ("AVGO",  "mega"),
    ("ORCL",  "mega"),
    # ── SaaS / Enterprise software ────────────────────────────────────────────
    ("CRM",   "saas"),
    ("ADBE",  "saas"),
    ("NOW",   "saas"),
    ("PLTR",  "saas"),
    ("SNOW",  "saas"),
    ("DDOG",  "saas"),
    ("MDB",   "saas"),
    ("GTLB",  "saas"),
    ("PATH",  "saas"),
    ("NET",   "saas"),
    ("ZS",    "saas"),
    ("S",     "saas"),
    # ── Platform / marketplace ────────────────────────────────────────────────
    ("NFLX",  "platform"),
    ("UBER",  "platform"),
    ("SPOT",  "platform"),
    ("COIN",  "platform"),
    ("RDDT",  "platform"),
    ("DUOL",  "platform"),
    ("SE",    "platform"),
    ("GRAB",  "platform"),
    ("DIS",   "platform"),
    # ── Fintech ───────────────────────────────────────────────────────────────
    ("V",     "fintech"),
    ("MA",    "fintech"),
    ("AXP",   "fintech"),
    ("SOFI",  "fintech"),
    ("NU",    "fintech"),
    ("AFRM",  "fintech"),
    ("HOOD",  "fintech"),
    ("UPST",  "fintech"),
    # ── Deep tech / Space / Frontier ─────────────────────────────────────────
    ("QCOM",  "deeptech"),
    ("SOUN",  "deeptech"),
    ("AI",    "deeptech"),
    ("RKLB",  "deeptech"),
    ("ASTS",  "deeptech"),
    ("IONQ",  "deeptech"),
    ("RIVN",  "deeptech"),
    ("ENPH",  "deeptech"),
    ("FSLR",  "deeptech"),
    ("ARRY",  "deeptech"),
    ("RXRX",  "deeptech"),
    ("CRSP",  "deeptech"),
    ("BEAM",  "deeptech"),
    # ── Healthcare ────────────────────────────────────────────────────────────
    ("UNH",   "healthcare"),
    ("LLY",   "healthcare"),
    ("ABBV",  "healthcare"),
    ("JNJ",   "healthcare"),
    ("MRK",   "healthcare"),
    ("TMO",   "healthcare"),
    ("ISRG",  "healthcare"),
    ("ABT",   "healthcare"),
    # ── Financials ────────────────────────────────────────────────────────────
    ("JPM",   "financial"),
    ("BAC",   "financial"),
    ("GS",    "financial"),
    # ── Consumer ──────────────────────────────────────────────────────────────
    ("PG",    "consumer"),
    ("KO",    "consumer"),
    ("PEP",   "consumer"),
    ("WMT",   "consumer"),
    ("COST",  "consumer"),
    ("MCD",   "consumer"),
    ("NKE",   "consumer"),
    ("BROS",  "consumer"),
    ("CELH",  "consumer"),
    ("CAVA",  "consumer"),
    ("ONON",  "consumer"),
    # ── Industrials ───────────────────────────────────────────────────────────
    ("CAT",   "industrial"),
    ("HON",   "industrial"),
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
    regime_block = (
        f"{vix_label}\n"
        f"Market direction: {regime['direction']}\n"
        f"Breadth: {regime['breadth']}\n"
        f"Top sectors: {', '.join(regime['top_sectors'])}\n"
        f"Weak sectors: {', '.join(regime['weak_sectors'])}"
    )

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
            "catalyst": p.get("catalyst", ""),
            "key_risk": p.get("key_risk", ""),
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


async def generate_market_picks(
    market_overview: Dict,
    screener_results: List[Dict],
    date_str: str,
    next_trading_day_label: str = "Tomorrow",
    mode: str = "short",
) -> Dict:
    regime = assess_market_regime(market_overview)

    if mode == "long":
        try:
            candidates = await screen_longterm_candidates(top_n=10)
        except Exception:
            candidates = []
        if not candidates:
            return {"error": "No candidates", "picks": [], "market_summary": "Insufficient data.",
                    "bias": "neutral", "generated_at": date_str}
        prompt = _build_longterm_prompt(candidates, market_overview, date_str)
    elif mode == "discovery":
        try:
            candidates = await screen_discovery_candidates(top_n=10)
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
    tokens = 2800 if mode in ("long", "discovery") else 1800

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


async def screen_longterm_candidates(top_n: int = 8) -> List[Dict]:
    now = time.time()
    if _longterm_cache["ts"] and (now - _longterm_cache["ts"]) < _FUND_CACHE_TTL and _longterm_cache["data"]:
        return _longterm_cache["data"][:top_n]

    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    # All tickers in the universe are eligible for long-term
    all_tickers = [t for t, _ in EQUITY_UNIVERSE]
    model_map = EQUITY_MODEL

    quote_results = await _batch_gather([yf_svc.get_quote(t) for t in all_tickers], batch_size=5, delay=0.8)
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in all_tickers], batch_size=3, delay=0.5)

    candidates = []
    for ticker, quote, fund in zip(all_tickers, quote_results, fund_results):
        q = quote if isinstance(quote, dict) else {}
        f = fund if isinstance(fund, dict) else {}
        price = q.get("price") or 0
        if not price:
            continue

        model = model_map.get(ticker, "")
        score = _score_longterm(f, price, model)

        entry_low  = round(price * 0.97, 2)
        entry_high = round(price * 1.03, 2)
        stop_loss  = round(price * 0.85, 2)
        target     = round(price * 1.25, 2)
        rr = round((target - price) / max(price - stop_loss, 0.01), 1)

        parts = []
        if f.get("pe_ratio"):                    parts.append(f"P/E {f['pe_ratio']:.1f}")
        if f.get("forward_pe"):                   parts.append(f"FwdP/E {f['forward_pe']:.1f}")
        if f.get("peg_ratio"):                    parts.append(f"PEG {f['peg_ratio']:.2f}")
        if f.get("revenue_growth") is not None:   parts.append(f"RevGrowth {f['revenue_growth']*100:.1f}%")
        if f.get("earnings_growth") is not None:  parts.append(f"EPSGrowth {f['earnings_growth']*100:.1f}%")
        if f.get("profit_margin") is not None:    parts.append(f"Margin {f['profit_margin']*100:.1f}%")
        if f.get("roe") is not None:              parts.append(f"ROE {f['roe']*100:.1f}%")
        if f.get("debt_to_equity") is not None:   parts.append(f"D/E {f['debt_to_equity']:.0f}")
        if f.get("dividend_yield"):               parts.append(f"Div {f['dividend_yield']*100:.1f}%")
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
        model_label = c.get("business_model", "")
        rows.append(
            f"#{i} {c['ticker']} ({c['name']}) [{model_label}] — ${c['price']:.2f} | Sector: {c.get('sector', '')}\n"
            f"   Fundamentals: {c['fund_summary']}\n"
            f"   Suggested: Entry ${c['entry_low']:.2f}–${c['entry_high']:.2f} | "
            f"Stop ${c['stop_loss']:.2f} | 12mo Target ${c['target']:.2f} | R/R 1:{c['rr']}"
        )
    candidates_block = "\n".join(rows)
    spy_c = market_overview.get("spy_change_pct", 0)
    vix = market_overview.get("vix") or 20
    ticker_map = " | ".join(f"{c['ticker']}={c['name']}" for c in candidates)
    time_note = _market_time_context(market_overview, "the next session")

    return f"""You are an expert long-term growth and value investor. Today is {date_str}.{time_note}

Evaluate these stocks as 6–12 month conviction plays. Focus on business quality, fundamentals, and valuation.

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

TICKER IDENTITY — memorize before writing any thesis:
{ticker_map}
Every pick's thesis must reference ONLY the company matched to that ticker above.

=== MACRO CONTEXT ===
SPY: {spy_c:+.1f}% | VIX: {vix:.1f}

=== CANDIDATES ===
{candidates_block}

=== YOUR JOB ===
1. Select 6–8 of the best candidates for a 6–12 month hold (fewer is fine if quality is low)
2. Set realistic levels:
   - Entry zone: current price ±3% (accumulate over 1–2 weeks, not a one-day fill)
   - Stop loss: major support level, 10–20% below entry
   - Target: realistic 12-month price target (15–40% upside typical)
3. Write a 2-sentence thesis. EACH sentence must cite a specific numeric data point (e.g. "Revenue grew 28% YoY", "Forward P/E of 22x vs sector median of 31x" — not vague claims like "strong fundamentals")
4. Name one specific near-term catalyst and one key risk that could impair the thesis
5. Confidence 8–10: strong growth + reasonable valuation + clear catalyst. Below 6 = don't include.

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

    quote_yf, ta, quote_fh = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="3mo", interval="1d"),
        finnhub_service.get_quote(ticker),
        return_exceptions=True,
    )

    quote_data = quote_yf if isinstance(quote_yf, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fh_data = quote_fh if isinstance(quote_fh, dict) else {}

    price = fh_data.get("price") or quote_data.get("price") or ta_data.get("price") or 0
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

    time_note = _market_time_context(market_overview, next_trading_day_label).strip()
    context_note = time_note if time_note else "Using most recent available price and indicator data."

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

Thesis must cite specific numeric values from the data above (e.g. "RSI at 44", not "oversold conditions").

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
  "thesis": "2 sentences citing specific numeric signals for {next_trading_day_label}.",
  "catalyst": "Specific trigger for this trade",
  "key_risk": "Main risk to this setup"
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
    model = EQUITY_MODEL.get(ticker.upper(), "")

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

    model_context = f"\nBusiness model: {model} — {{\n  'mega': 'focus on valuation vs moat strength',\n  'saas': 'ARR growth rate and net revenue retention are key',\n  'platform': 'network effects and user monetization trajectory',\n  'fintech': 'payment volume growth and regulatory positioning',\n  'deeptech': 'technology differentiation and path to profitability',\n  'healthcare': 'pipeline, patent life, and regulatory catalysts',\n  'consumer': 'unit economics and brand durability — not a platform moat thesis',\n  'financial': 'NIM and credit quality cycle',\n  'industrial': 'cycle positioning and capital discipline',\n  'energy': 'commodity exposure and dividend sustainability',\n}}.get('{model}', '')" if model else ""

    prompt = f"""You are an expert long-term investor. Analyze {ticker} ({name}) for a 6–12 month hold.

Stock: {ticker} | Price: ${price:.2f} | Sector: {sector}{f' | Business model: {model}' if model else ''}

FUNDAMENTALS:
{fund_str}

Decide: BUY (accumulate over 1–2 weeks), HOLD (wait for better conditions), or AVOID (business concerns).

BUY criteria: positive revenue growth + healthy margins + reasonable valuation + clear catalyst
HOLD criteria: good business but currently expensive or unclear direction
AVOID criteria: declining revenue, margin compression, excessive debt, or structural headwinds

Suggested entry: ${entry_low:.2f}–${entry_high:.2f} | Stop: ${stop_loss:.2f} | 12-month target: ${target:.2f} | R/R 1:{rr}

Write a thesis citing SPECIFIC numeric data from above. Each sentence must include at least one number.

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
  "thesis": "2 sentences with specific numeric data explaining the long-term BUY/HOLD/AVOID call.",
  "catalyst": "Specific event or development that could move the stock in 6–12 months",
  "key_risk": "Main risk that could permanently impair the long-term thesis"
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


async def screen_discovery_candidates(top_n: int = 8) -> List[Dict]:
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
    fund_results  = await _batch_gather([finnhub_service.get_fundamentals_mapped(t) for t in tickers], batch_size=3, delay=0.5)

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
    _discovery_cache["ts"] = time.time()
    _discovery_cache["data"] = candidates
    return candidates[:top_n]


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

    return f"""You are an expert venture-minded long-term investor. Today is {date_str}.{time_note}

Your goal: identify companies that could be 10x in 10 years. All candidates have been pre-screened for platform economics potential — these are SaaS, marketplace, fintech, and deep-tech businesses only.

Business model lens (calibrate your thesis accordingly):
- saas: evaluate ARR growth rate, net revenue retention >120%, gross margin >70% as the gold standard
- platform: evaluate network effect moat, user growth compounding, take-rate expansion potential
- fintech: evaluate payment volume trajectory, underbanked market penetration, regulatory defensibility
- deeptech: evaluate technology differentiation, patent moat, credible path from R&D to dominant revenue

TICKER IDENTITY — memorize before writing any thesis:
{ticker_map}
Every pick's thesis must reference ONLY the company matched to that ticker above.
Do NOT confuse similar-looking tickers.

=== CANDIDATES (pre-screened for disruption potential, ranked by platform economics score) ===
{candidates_block}

=== YOUR JOB ===
1. Select 6–8 of the best candidates (fewer is better — only include genuine 10-year conviction plays)
2. Set price targets reflecting YOUR conviction — the 2.5x base is a floor, not a ceiling:
   - confidence ≥ 8 with clear platform dominance path → target 5x–10x
   - confidence 6–7 with strong but contested position → target 3x–5x
   - confidence < 6 → do not include
3. Write a 2-sentence thesis. EACH sentence must cite a specific numeric value (e.g. "Revenue growing at 38% YoY", "Gross margin of 76%" — not vague phrases like "strong growth potential")
4. Name one specific catalyst that could accelerate the 10-year thesis (product expansion, market share inflection, regulatory win)
5. Name one key risk that could permanently impair the thesis — not just volatility (e.g. competitive displacement, regulation, commoditization)

RULES:
- trade_type must be one of: disruptor (redefining an industry), platform (marketplace/network effects), deep-tech (proprietary technology moat), speculative (high risk/reward early stage)
- Stop losses must stay wide (30–40%) — these positions are held through volatility, not day-traded
- market_summary must address whether current macro conditions favor accumulating 10-year growth positions
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


# ─── Combined all-modes single-ticker analysis ───────────────────────────────

async def analyze_ticker_all_modes(
    ticker: str,
    market_overview: Dict,
    next_trading_day_label: str = "Tomorrow",
) -> Dict:
    from services.technical_analysis import get_technical_signals
    from services import yahoo_finance as yf_svc
    from services import finnhub_service

    quote_yf, ta, fund, quote_fh = await asyncio.gather(
        yf_svc.get_quote(ticker),
        get_technical_signals(ticker, period="1y", interval="1d"),
        finnhub_service.get_fundamentals_mapped(ticker),
        finnhub_service.get_quote(ticker),
        return_exceptions=True,
    )

    quote_data = quote_yf if isinstance(quote_yf, dict) else {}
    ta_data = ta if isinstance(ta, dict) else {}
    fund_data = fund if isinstance(fund, dict) else {}
    fh_data = quote_fh if isinstance(quote_fh, dict) else {}

    price = fh_data.get("price") or quote_data.get("price") or ta_data.get("price") or 0
    name = quote_data.get("name") or fh_data.get("name") or ticker
    change_pct_atm = fh_data.get("change_pct") or quote_data.get("change_pct", 0) or 0
    sector = quote_data.get("sector") or fh_data.get("sector") or ""

    # Look up business model tag — informs horizon-specific guidance
    model = EQUITY_MODEL.get(ticker.upper(), "")

    if not price:
        err = {"ticker": ticker, "error": f"Could not fetch price data for {ticker}"}
        return {"short": err, "long": err, "discovery": err}

    regime = assess_market_regime(market_overview)

    atr = ta_data.get("atr_14")
    short_levels = compute_atr_levels(price, atr)

    ema50 = ta_data.get("ema_50")
    long_stop = round(ema50 * 0.97, 2) if ema50 and ema50 < price * 0.92 else round(price * 0.85, 2)
    long_levels = {
        "entry_low": round(price * 0.97, 2), "entry_high": round(price * 1.03, 2),
        "stop_loss": long_stop, "target": round(price * 1.25, 2),
    }
    long_rr = round((long_levels["target"] - price) / max(price - long_levels["stop_loss"], 0.01), 1)

    disc_levels = {
        "entry_low": round(price * 0.95, 2), "entry_high": round(price * 1.05, 2),
        "stop_loss": round(price * 0.65, 2), "target": round(price * 2.50, 2),
    }
    disc_rr = round((disc_levels["target"] - price) / max(price - disc_levels["stop_loss"], 0.01), 1)

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
    else:
        signals.append(f"Day change: {change_pct_atm:+.1f}%")
        h = fh_data.get("high") or 0
        l = fh_data.get("low") or 0
        if h and l and price and h != l:
            signals.append(f"At {(price - l) / (h - l) * 100:.0f}% of day range")
        if change_pct_atm > 3: signals.append("Strong bullish momentum")
        elif change_pct_atm > 1: signals.append("Mild bullish")
        elif change_pct_atm < -3: signals.append("Strong selling pressure")
        elif change_pct_atm < -1: signals.append("Mild bearish")

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

    # Business model context — guides Claude to give horizon-appropriate recommendations
    model_context = ""
    if model:
        discovery_eligible = model in _DISCOVERY_ELIGIBLE
        model_context = f"""
BUSINESS MODEL: {model}
- Short-term: TA signals and regime are the primary lens regardless of business model
- Long-term: {'focus on ARR/revenue growth rate, gross margins, and platform moat' if model in ('saas','platform') else 'focus on fundamentals appropriate to this business type'}
- Discovery (10-year): {'this business has genuine platform economics — evaluate network effects, TAM, and growth compounding' if discovery_eligible else f'NOTE: {model} businesses rarely have the platform moat required for 10x in 10 years — be honest about structural limitations'}"""

    time_note = _market_time_context(market_overview, next_trading_day_label)
    change_label = "last close" if market_overview.get("market_status") in ("closed", "pre-market") else "today"

    prompt = f"""You are a multi-timeframe expert analyst. Analyze {ticker} ({name}) across 3 investment horizons simultaneously.{time_note}
STOCK: {ticker} | Price: ${price:.2f} | Sector: {sector}
TA SIGNALS: {', '.join(signals) if signals else f'Day change: {change_pct_atm:+.1f}%'} | Summary: {ta_data.get('signal_summary') or (f'Price action: {change_pct_atm:+.1f}% ({change_label})' if change_pct_atm else 'Price action analysis')}
FUNDAMENTALS: {fund_str}
MARKET: Bias {regime['overall_bias']} | VIX {regime['vix']} — {regime['vix_regime']}{model_context}

━━━ HORIZON 1: DAY TRADING (for {next_trading_day_label}'s open) ━━━
Entry: ${short_levels['entry_low']:.2f}–${short_levels['entry_high']:.2f} | Stop: ${short_levels['stop_loss']:.2f} | Target: ${short_levels['target_2r']:.2f} | R/R 1:{short_rr}
BUY if TA aligns with regime. HOLD if mixed. AVOID if setup is broken or against regime.

━━━ HORIZON 2: LONG-TERM (6–12 months) ━━━
Entry: ${long_levels['entry_low']:.2f}–${long_levels['entry_high']:.2f} | Stop: ${long_levels['stop_loss']:.2f} | Target: ${long_levels['target']:.2f} | R/R 1:{long_rr}
BUY if fundamentals are strong and valuation reasonable. HOLD if good but expensive. AVOID if declining metrics.

━━━ HORIZON 3: 10-YEAR DISCOVERY ━━━
Entry: ${disc_levels['entry_low']:.2f}–${disc_levels['entry_high']:.2f} | Stop: ${disc_levels['stop_loss']:.2f} | Target: ${disc_levels['target']:.2f} (2.5x base) | R/R 1:{disc_rr}
BUY only if this company could genuinely dominate its market in 10 years. HOLD if interesting but unclear. AVOID if no defensible platform moat or declining growth.

THESIS RULES — apply to ALL three horizons:
- Every thesis sentence must cite at least one specific number from the data above
- Short-term thesis: cite TA signal values (RSI, MACD, volume)
- Long-term thesis: cite fundamental metrics (revenue growth %, margins, valuation ratios)
- Discovery thesis: cite growth rate + explain the specific moat (network effects, switching costs, data advantage)
- For discovery, if the business model note says this is not a platform-economics business, be direct — AVOID with a clear explanation

Respond ONLY with valid JSON, no markdown:
{{
  "short": {{
    "ticker": "{ticker}", "recommendation": "buy", "trade_type": "momentum",
    "entry_low": {short_levels['entry_low']}, "entry_high": {short_levels['entry_high']},
    "stop_loss": {short_levels['stop_loss']}, "target": {short_levels['target_2r']},
    "risk_reward": "1:{short_rr}", "confidence": 6,
    "thesis": "2 sentences with specific TA signal values.",
    "catalyst": "Specific short-term trigger",
    "key_risk": "Main risk to this day trade setup"
  }},
  "long": {{
    "ticker": "{ticker}", "recommendation": "hold", "trade_type": "growth",
    "entry_low": {long_levels['entry_low']}, "entry_high": {long_levels['entry_high']},
    "stop_loss": {long_levels['stop_loss']}, "target": {long_levels['target']},
    "risk_reward": "1:{long_rr}", "confidence": 6,
    "thesis": "2 sentences with specific fundamental data points.",
    "catalyst": "Specific 6–12 month catalyst",
    "key_risk": "Main risk to the long-term thesis"
  }},
  "discovery": {{
    "ticker": "{ticker}", "recommendation": "hold", "trade_type": "disruptor",
    "entry_low": {disc_levels['entry_low']}, "entry_high": {disc_levels['entry_high']},
    "stop_loss": {disc_levels['stop_loss']}, "target": {disc_levels['target']},
    "risk_reward": "1:{disc_rr}", "confidence": 6,
    "thesis": "2 sentences on 10-year disruption potential with specific metrics, or honest AVOID reasoning if no platform moat.",
    "catalyst": "Specific 10-year thesis accelerant",
    "key_risk": "Structural risk that could permanently impair the 10-year thesis"
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
            "catalyst": "", "key_risk": "",
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

    short_r = _fix(parsed.get("short", {}),  short_levels["entry_low"], short_levels["entry_high"], short_levels["stop_loss"],  short_levels["target_2r"])
    long_r  = _fix(parsed.get("long", {}),   long_levels["entry_low"],  long_levels["entry_high"],  long_levels["stop_loss"],  long_levels["target"])
    disc_r  = _fix(parsed.get("discovery", {}), disc_levels["entry_low"], disc_levels["entry_high"], disc_levels["stop_loss"],  disc_levels["target"])

    short_r["next_trading_day"] = next_trading_day_label
    long_r["next_trading_day"]  = "Long-term (6–12 months)"
    disc_r["next_trading_day"]  = "10-Year Horizon"

    return {"ticker": ticker, "short": short_r, "long": long_r, "discovery": disc_r}


# ─── Discovery single-ticker analysis ────────────────────────────────────────

async def _analyze_ticker_discovery(ticker: str) -> Dict:
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

    discovery_eligible = model in _DISCOVERY_ELIGIBLE
    model_note = (
        f"Business model: {model} — this is a platform-economics business. Evaluate network effects, TAM, and growth compounding."
        if discovery_eligible else
        f"Business model: {model} — NOTE: this business type has physical-expansion or commodity constraints that structurally limit 10x potential. Be direct about whether a genuine 10-year disruption thesis exists."
    ) if model else ""

    prompt = f"""You are an expert venture-minded long-term investor. Evaluate {ticker} ({name}) as a potential 10-year disruptive hold.

Stock: {ticker} | Price: ${price:.2f} | Sector: {sector}
{model_note}

GROWTH METRICS:
{fund_str}

Assess whether this company could be 10x from here in 10 years. Consider:
1. What market is this company disrupting and how large is the TAM?
2. Does revenue growth rate suggest they are winning market share?
3. Is there a defensible moat (network effects, switching costs, data advantage, regulatory barrier)?
4. Is there a credible path to dominant profitability even if currently unprofitable?

Decide: BUY (compelling 10-year disruptive thesis), HOLD (interesting but needs more evidence), or AVOID (thesis is weak or no platform moat)

Suggested entry: ${entry_low:.2f}–${entry_high:.2f} | Stop: ${stop_loss:.2f} (~35% wide) | 10-year base target: ${target:.2f} (2.5x)
For high conviction (confidence ≥ 8) with clear platform dominance: adjust target to 5x–10x.

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
  "thesis": "2 sentences with specific growth metrics and moat explanation, or honest AVOID reasoning if no platform moat.",
  "catalyst": "Specific event or development that could accelerate the 10-year thesis",
  "key_risk": "Structural risk that could permanently impair the thesis (not just volatility)"
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
