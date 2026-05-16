import os
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

# Keep the thread pool small — Yahoo Finance rate-limits aggressively on cloud IPs
_executor = ThreadPoolExecutor(max_workers=3)


def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


def _get_info_with_retry(ticker_obj, retries: int = 2) -> dict:
    """Fetch .info with simple retry on 429 rate-limit responses."""
    for attempt in range(retries + 1):
        try:
            info = ticker_obj.info
            return info or {}
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                time.sleep(2 ** attempt)  # 1s, 2s backoff
            else:
                raise
    return {}


async def get_quote(ticker: str) -> Optional[Dict]:
    # Use Finnhub as primary source when key is available — avoids Yahoo Finance rate limits
    if os.getenv("FINNHUB_API_KEY"):
        from services import finnhub_service
        fh = await finnhub_service.get_quote(ticker)
        if fh and fh.get("price"):
            return fh

    def _fetch():
        try:
            t = yf.Ticker(ticker)
            info = _get_info_with_retry(t)
            if not info or info.get("regularMarketPrice") is None:
                # fallback: use fast_info
                fi = t.fast_info
                return {
                    "ticker": ticker.upper(),
                    "name": info.get("longName") or info.get("shortName") or ticker,
                    "price": fi.last_price or 0,
                    "change": fi.last_price - fi.previous_close if fi.previous_close else 0,
                    "change_pct": ((fi.last_price - fi.previous_close) / fi.previous_close * 100) if fi.previous_close else 0,
                    "volume": fi.three_month_average_volume or 0,
                    "avg_volume": fi.three_month_average_volume,
                    "rel_volume": None,
                    "market_cap": fi.market_cap,
                    "pe_ratio": None,
                    "eps": None,
                    "week_52_high": fi.year_high,
                    "week_52_low": fi.year_low,
                    "beta": None,
                    "short_float": None,
                    "short_ratio": None,
                    "float_shares": fi.shares,
                    "outstanding_shares": fi.shares,
                    "sector": None,
                    "industry": None,
                    "exchange": fi.exchange,
                }
            price = info.get("regularMarketPrice", 0) or info.get("currentPrice", 0)
            prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
            volume = info.get("regularMarketVolume", 0) or 0
            avg_vol = info.get("averageVolume", 0) or 0
            return {
                "ticker": ticker.upper(),
                "name": info.get("longName") or info.get("shortName") or ticker,
                "price": price,
                "change": price - prev_close,
                "change_pct": ((price - prev_close) / prev_close * 100) if prev_close else 0,
                "volume": volume,
                "avg_volume": avg_vol,
                "rel_volume": round(volume / avg_vol, 2) if avg_vol else None,
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                "eps": info.get("trailingEps"),
                "week_52_high": info.get("fiftyTwoWeekHigh"),
                "week_52_low": info.get("fiftyTwoWeekLow"),
                "beta": info.get("beta"),
                "short_float": info.get("shortPercentOfFloat"),
                "short_ratio": info.get("shortRatio"),
                "float_shares": info.get("floatShares"),
                "outstanding_shares": info.get("sharesOutstanding"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "exchange": info.get("exchange"),
            }
        except Exception as e:
            print(f"[YF] get_quote error for {ticker}: {e}")
            return None
    return await _run_sync(_fetch)


async def get_ohlcv(ticker: str, period: str = "3mo", interval: str = "1d") -> List[Dict]:
    def _fetch():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period, interval=interval, auto_adjust=True)
            if hist.empty:
                return []
            bars = []
            for ts, row in hist.iterrows():
                bars.append({
                    "timestamp": ts.isoformat(),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": float(row["Volume"]),
                })
            return bars
        except Exception as e:
            print(f"[YF] get_ohlcv error for {ticker}: {e}")
            return []
    return await _run_sync(_fetch)


async def get_options_chain(ticker: str) -> Optional[Dict]:
    def _fetch():
        try:
            t = yf.Ticker(ticker)
            expiries = t.options
            if not expiries:
                return None

            # Use first 4 expiries
            result = {"expiries": list(expiries[:8]), "calls": [], "puts": []}
            price = t.fast_info.last_price or 0

            all_calls = []
            all_puts = []

            for exp in expiries[:4]:
                chain = t.option_chain(exp)

                for _, row in chain.calls.iterrows():
                    vol = int(row.get("volume", 0) or 0)
                    oi = int(row.get("openInterest", 0) or 0)
                    vol_oi = round(vol / oi, 2) if oi > 0 else 0
                    unusual = vol > 0 and oi > 0 and vol_oi > 2.0 and vol > 500
                    all_calls.append({
                        "strike": float(row["strike"]),
                        "expiry": exp,
                        "option_type": "call",
                        "last_price": float(row.get("lastPrice", 0) or 0),
                        "bid": float(row.get("bid", 0) or 0),
                        "ask": float(row.get("ask", 0) or 0),
                        "volume": vol,
                        "open_interest": oi,
                        "implied_volatility": round(float(row.get("impliedVolatility", 0) or 0) * 100, 2),
                        "delta": None,
                        "gamma": None,
                        "theta": None,
                        "vega": None,
                        "vol_oi_ratio": vol_oi,
                        "unusual": unusual,
                    })

                for _, row in chain.puts.iterrows():
                    vol = int(row.get("volume", 0) or 0)
                    oi = int(row.get("openInterest", 0) or 0)
                    vol_oi = round(vol / oi, 2) if oi > 0 else 0
                    unusual = vol > 0 and oi > 0 and vol_oi > 2.0 and vol > 500
                    all_puts.append({
                        "strike": float(row["strike"]),
                        "expiry": exp,
                        "option_type": "put",
                        "last_price": float(row.get("lastPrice", 0) or 0),
                        "bid": float(row.get("bid", 0) or 0),
                        "ask": float(row.get("ask", 0) or 0),
                        "volume": vol,
                        "open_interest": oi,
                        "implied_volatility": round(float(row.get("impliedVolatility", 0) or 0) * 100, 2),
                        "delta": None,
                        "gamma": None,
                        "theta": None,
                        "vega": None,
                        "vol_oi_ratio": vol_oi,
                        "unusual": unusual,
                    })

            total_call_vol = sum(c["volume"] for c in all_calls)
            total_put_vol = sum(p["volume"] for p in all_puts)
            total_call_oi = sum(c["open_interest"] for c in all_calls)
            total_put_oi = sum(p["open_interest"] for p in all_puts)
            pcr = round(total_put_vol / total_call_vol, 3) if total_call_vol > 0 else 0

            # Max pain: find strike where total OI value is minimized
            max_pain = _calc_max_pain(all_calls, all_puts, price)

            unusual_all = [c for c in all_calls if c["unusual"]] + [p for p in all_puts if p["unusual"]]
            unusual_all.sort(key=lambda x: x["volume"], reverse=True)

            return {
                "put_call_ratio": pcr,
                "max_pain": max_pain,
                "total_call_volume": total_call_vol,
                "total_put_volume": total_put_vol,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "unusual_contracts": unusual_all[:30],
                "iv_rank": None,
                "expiries": list(expiries[:8]),
            }
        except Exception as e:
            print(f"[YF] get_options error for {ticker}: {e}")
            return None
    return await _run_sync(_fetch)


def _calc_max_pain(calls: List[Dict], puts: List[Dict], price: float) -> Optional[float]:
    try:
        strikes = sorted(set(c["strike"] for c in calls) | set(p["strike"] for p in puts))
        if not strikes:
            return None
        pain = {}
        for s in strikes:
            call_pain = sum(max(0, s - c["strike"]) * c["open_interest"] for c in calls)
            put_pain = sum(max(0, p["strike"] - s) * p["open_interest"] for p in puts)
            pain[s] = call_pain + put_pain
        return min(pain, key=pain.get)
    except Exception:
        return None


async def get_multiple_quotes(tickers: List[str]) -> List[Dict]:
    def _fetch():
        try:
            data = yf.download(
                " ".join(tickers),
                period="2d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            results = []
            for ticker in tickers:
                try:
                    t = yf.Ticker(ticker)
                    info = t.fast_info
                    price = info.last_price or 0
                    prev = info.previous_close or price
                    chg = price - prev
                    chg_pct = (chg / prev * 100) if prev else 0
                    results.append({
                        "ticker": ticker.upper(),
                        "price": round(price, 2),
                        "change": round(chg, 2),
                        "change_pct": round(chg_pct, 2),
                        "volume": info.three_month_average_volume or 0,
                        "market_cap": info.market_cap,
                        "week_52_high": info.year_high,
                        "week_52_low": info.year_low,
                    })
                except Exception:
                    pass
            return results
        except Exception as e:
            print(f"[YF] get_multiple_quotes error: {e}")
            return []
    return await _run_sync(_fetch)


async def get_fundamentals(ticker: str) -> Optional[Dict]:
    def _fetch():
        try:
            t = yf.Ticker(ticker)
            info = _get_info_with_retry(t)
            return {
                "ticker": ticker.upper(),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "pb_ratio": info.get("priceToBook"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "gross_margins": info.get("grossMargins"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
                "free_cashflow": info.get("freeCashflow"),
                "dividend_yield": info.get("dividendYield"),
                "payout_ratio": info.get("payoutRatio"),
                "book_value": info.get("bookValue"),
                "eps_trailing": info.get("trailingEps"),
                "eps_forward": info.get("forwardEps"),
                "analyst_rating": info.get("recommendationKey"),
                "analyst_count": info.get("numberOfAnalystOpinions"),
                "target_price": info.get("targetMeanPrice"),
                "target_low": info.get("targetLowPrice"),
                "target_high": info.get("targetHighPrice"),
                "short_float": info.get("shortPercentOfFloat"),
                "short_ratio": info.get("shortRatio"),
                "insider_pct": info.get("heldPercentInsiders"),
                "institution_pct": info.get("heldPercentInstitutions"),
            }
        except Exception as e:
            print(f"[YF] fundamentals error for {ticker}: {e}")
            return None
    return await _run_sync(_fetch)
