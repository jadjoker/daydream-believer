from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class OHLCVBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class TechnicalSignals(BaseModel):
    ticker: str
    price: float
    change_pct: float
    rsi_14: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    macd_hist: Optional[float]
    bb_upper: Optional[float]
    bb_middle: Optional[float]
    bb_lower: Optional[float]
    bb_pct: Optional[float]
    ema_9: Optional[float]
    ema_21: Optional[float]
    ema_50: Optional[float]
    sma_200: Optional[float]
    atr_14: Optional[float]
    obv: Optional[float]
    vwap: Optional[float]
    rel_volume: Optional[float]
    stoch_k: Optional[float]
    stoch_d: Optional[float]
    adx: Optional[float]
    cci: Optional[float]
    signal_summary: str
    bull_signals: List[str]
    bear_signals: List[str]


class StockQuote(BaseModel):
    ticker: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    avg_volume: Optional[int]
    rel_volume: Optional[float]
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    eps: Optional[float]
    week_52_high: Optional[float]
    week_52_low: Optional[float]
    beta: Optional[float]
    short_float: Optional[float]
    short_ratio: Optional[float]
    float_shares: Optional[float]
    outstanding_shares: Optional[float]
    sector: Optional[str]
    industry: Optional[str]
    exchange: Optional[str]


class OptionsContract(BaseModel):
    strike: float
    expiry: str
    option_type: str
    last_price: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    vega: Optional[float]
    vol_oi_ratio: float
    unusual: bool


class OptionsFlow(BaseModel):
    ticker: str
    put_call_ratio: float
    max_pain: Optional[float]
    total_call_volume: int
    total_put_volume: int
    total_call_oi: int
    total_put_oi: int
    unusual_contracts: List[OptionsContract]
    iv_rank: Optional[float]
    expiries: List[str]


class SentimentScore(BaseModel):
    source: str
    score: float
    label: str
    mention_count: int
    bullish_count: int
    bearish_count: int
    details: Optional[Any]


class SentimentSummary(BaseModel):
    ticker: str
    composite_score: float
    composite_label: str
    reddit: Optional[SentimentScore]
    stocktwits: Optional[SentimentScore]
    news: Optional[SentimentScore]
    trend_direction: str
    top_posts: List[dict]


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: str
    summary: Optional[str]
    sentiment: Optional[str]
    tickers: List[str]
    category: Optional[str]


class InsiderTrade(BaseModel):
    ticker: str
    company: str
    insider_name: str
    insider_title: str
    trade_type: str
    shares: int
    price: float
    value: float
    filed_date: str
    trade_date: str


class EarningsEvent(BaseModel):
    ticker: str
    company: str
    report_date: str
    time: str
    eps_estimate: Optional[float]
    eps_actual: Optional[float]
    revenue_estimate: Optional[float]
    revenue_actual: Optional[float]
    surprise_pct: Optional[float]


class ScreenerResult(BaseModel):
    ticker: str
    name: str
    price: float
    change_pct: float
    volume: int
    rel_volume: float
    market_cap: Optional[float]
    rsi: Optional[float]
    short_float: Optional[float]
    sector: Optional[str]
    score: float
    signals: List[str]


class MarketOverview(BaseModel):
    spy_price: float
    spy_change_pct: float
    qqq_price: float
    qqq_change_pct: float
    vix: float
    vix_change_pct: float
    iwm_price: float
    iwm_change_pct: float
    dia_price: float
    dia_change_pct: float
    advance_decline: Optional[str]
    sector_performance: List[dict]
    trending_tickers: List[str]
    market_status: str
