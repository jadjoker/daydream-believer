import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf

_executor = ThreadPoolExecutor(max_workers=4)


def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


def _compute_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _compute_macd(closes: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _compute_bollinger(closes: pd.Series, period=20, std_dev=2):
    sma = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    pct = (closes - lower) / (upper - lower)
    return upper, sma, lower, pct


def _compute_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k=14, d=3):
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    k_pct = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d_pct = k_pct.rolling(d).mean()
    return k_pct, d_pct


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm < minus_dm)] = 0
    minus_dm[(minus_dm < plus_dm)] = 0
    atr = _compute_atr(high, low, close, period)
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(span=period, adjust=False).mean()


def _compute_cci(high: pd.Series, low: pd.Series, close: pd.Series, period=20) -> pd.Series:
    tp = (high + low + close) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))))
    return (tp - sma) / (0.015 * mad.replace(0, np.nan))


def _compute_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()


def _compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def analyze(ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[Dict]:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        if df.empty or len(df) < 30:
            return None

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        rsi = _compute_rsi(close)
        macd_line, macd_sig, macd_hist = _compute_macd(close)
        bb_upper, bb_mid, bb_lower, bb_pct = _compute_bollinger(close)
        ema_9 = close.ewm(span=9, adjust=False).mean()
        ema_21 = close.ewm(span=21, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()
        sma_200 = close.rolling(200).mean()
        atr = _compute_atr(high, low, close)
        obv = _compute_obv(close, volume)
        vwap = _compute_vwap(df)
        stoch_k, stoch_d = _compute_stochastic(high, low, close)
        adx = _compute_adx(high, low, close)
        cci = _compute_cci(high, low, close)

        price = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else price
        change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0

        avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
        rel_vol = float(volume.iloc[-1] / avg_vol_20) if avg_vol_20 > 0 else 1.0

        def safe(series):
            v = series.iloc[-1] if len(series) > 0 else None
            if v is None:
                return None
            fv = float(v)
            return round(fv, 4) if not (np.isnan(fv) or np.isinf(fv)) else None

        rsi_val = safe(rsi)
        macd_val = safe(macd_line)
        macd_sig_val = safe(macd_sig)
        macd_hist_val = safe(macd_hist)
        bb_upper_val = safe(bb_upper)
        bb_mid_val = safe(bb_mid)
        bb_lower_val = safe(bb_lower)
        bb_pct_val = safe(bb_pct)
        ema9_val = safe(ema_9)
        ema21_val = safe(ema_21)
        ema50_val = safe(ema_50)
        sma200_val = safe(sma_200)
        atr_val = safe(atr)
        obv_val = safe(obv)
        vwap_val = safe(vwap)
        stoch_k_val = safe(stoch_k)
        stoch_d_val = safe(stoch_d)
        adx_val = safe(adx)
        cci_val = safe(cci)

        bull_signals = []
        bear_signals = []

        if rsi_val is not None:
            if rsi_val < 30:
                bull_signals.append(f"RSI oversold ({rsi_val:.1f})")
            elif rsi_val > 70:
                bear_signals.append(f"RSI overbought ({rsi_val:.1f})")
            elif 40 <= rsi_val <= 60:
                bull_signals.append(f"RSI neutral ({rsi_val:.1f})")

        if macd_hist_val is not None and macd_val is not None:
            if macd_hist_val > 0 and macd_val > 0:
                bull_signals.append("MACD bullish crossover above zero")
            elif macd_hist_val > 0 and macd_val < 0:
                bull_signals.append("MACD bullish crossover below zero")
            elif macd_hist_val < 0 and macd_val < 0:
                bear_signals.append("MACD bearish below zero")
            else:
                bear_signals.append("MACD bearish crossover")

        if bb_pct_val is not None:
            if bb_pct_val < 0.05:
                bull_signals.append("Price near lower Bollinger Band (oversold)")
            elif bb_pct_val > 0.95:
                bear_signals.append("Price near upper Bollinger Band (overbought)")

        if ema9_val and ema21_val:
            if ema9_val > ema21_val:
                bull_signals.append("EMA9 > EMA21 (short-term bullish)")
            else:
                bear_signals.append("EMA9 < EMA21 (short-term bearish)")

        if ema50_val and sma200_val:
            if ema50_val > sma200_val:
                bull_signals.append("Golden Cross (EMA50 > SMA200)")
            else:
                bear_signals.append("Death Cross (EMA50 < SMA200)")

        if vwap_val and price:
            if price > vwap_val:
                bull_signals.append(f"Price above VWAP ({vwap_val:.2f})")
            else:
                bear_signals.append(f"Price below VWAP ({vwap_val:.2f})")

        if rel_vol > 2.0:
            bull_signals.append(f"High relative volume ({rel_vol:.1f}x)")

        if stoch_k_val is not None:
            if stoch_k_val < 20:
                bull_signals.append(f"Stochastic oversold ({stoch_k_val:.1f})")
            elif stoch_k_val > 80:
                bear_signals.append(f"Stochastic overbought ({stoch_k_val:.1f})")

        if adx_val is not None and adx_val > 25:
            bull_signals.append(f"Strong trend (ADX {adx_val:.1f})")

        if cci_val is not None:
            if cci_val < -100:
                bull_signals.append(f"CCI oversold ({cci_val:.0f})")
            elif cci_val > 100:
                bear_signals.append(f"CCI overbought ({cci_val:.0f})")

        bull_count = len(bull_signals)
        bear_count = len(bear_signals)
        if bull_count > bear_count + 2:
            summary = "BULLISH"
        elif bear_count > bull_count + 2:
            summary = "BEARISH"
        elif bull_count > bear_count:
            summary = "SLIGHTLY BULLISH"
        elif bear_count > bull_count:
            summary = "SLIGHTLY BEARISH"
        else:
            summary = "NEUTRAL"

        return {
            "ticker": ticker.upper(),
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "rsi_14": rsi_val,
            "macd": macd_val,
            "macd_signal": macd_sig_val,
            "macd_hist": macd_hist_val,
            "bb_upper": bb_upper_val,
            "bb_middle": bb_mid_val,
            "bb_lower": bb_lower_val,
            "bb_pct": bb_pct_val,
            "ema_9": ema9_val,
            "ema_21": ema21_val,
            "ema_50": ema50_val,
            "sma_200": sma200_val,
            "atr_14": atr_val,
            "obv": obv_val,
            "vwap": vwap_val,
            "rel_volume": round(rel_vol, 2),
            "stoch_k": stoch_k_val,
            "stoch_d": stoch_d_val,
            "adx": adx_val,
            "cci": cci_val,
            "signal_summary": summary,
            "bull_signals": bull_signals,
            "bear_signals": bear_signals,
        }
    except Exception as e:
        print(f"[TA] analyze error for {ticker}: {e}")
        return None


async def get_technical_signals(ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[Dict]:
    return await _run_sync(analyze, ticker, period, interval)
