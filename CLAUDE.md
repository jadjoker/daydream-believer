# Daydream Believer — Claude Code Guide

## What This Is
AI-powered day-trader assistant. FastAPI backend + Next.js 14 frontend. Claude generates stock picks and single-stock analysis; Finnhub provides real-time market data; TradingView widgets render charts.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (React 19, TypeScript), Tailwind CSS 4, Radix UI, TradingView Lightweight Charts |
| Backend | FastAPI + Uvicorn, Python 3.11+, Pydantic v2, asyncio throughout |
| AI | Claude API (`claude-sonnet-4-6` default, configurable via `AI_MODEL` env var) |
| Market data | Finnhub (primary), yfinance (TA computation only) |
| Macro data | FRED API |
| Caching | `diskcache` (persistent, `./cache_data/`) + `cachetools` (in-memory) |
| Deployment | Render (backend) + Vercel (frontend) |

---

## Project Layout

```
daydream-believer/
├── backend/
│   ├── main.py                  # FastAPI app, CORS, router wiring, lifespan
│   ├── routers/
│   │   ├── ai.py                # /ai/* — picks generation, single-stock analysis
│   │   ├── stocks.py            # /stocks/* — quotes, technicals, fundamentals
│   │   ├── simulator.py         # /simulator/* — paper trading portfolio
│   │   ├── news.py              # /news/* — general + ticker news
│   │   ├── sentiment.py         # /sentiment/* — Reddit, Stocktwits, news
│   │   ├── options.py           # /options/* — flow, unusual activity
│   │   ├── insider.py           # /insider/* — SEC EDGAR filings
│   │   ├── earnings.py          # /earnings/* — calendar, ticker history
│   │   ├── market.py            # /market/overview — SPY/QQQ/VIX + FRED macro
│   │   └── screener.py          # /screener/* — filtered stock scans
│   └── services/
│       ├── ai_service.py        # All Claude prompts — picks + analysis (3000 lines)
│       ├── finnhub_service.py   # Finnhub API client (quotes, candles, analyst, insider, earnings)
│       ├── cache_service.py     # get_cached / set_cached / delete_cached wrappers
│       ├── technical_analysis.py # RSI, MACD, Bollinger, EMA, ATR, VWAP, ADX, CCI (yfinance)
│       ├── fred_service.py      # CPI, Fed rate, unemployment, GDP growth
│       ├── yahoo_finance.py     # Sector performance, treasury yields, TA fallback
│       ├── screener_service.py  # Candidate scoring + filtering
│       └── simulator_service.py # Paper portfolio: buy/sell/positions/P&L
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Main dashboard (search + charts + panels)
│   │   ├── picks/page.tsx       # AI picks page
│   │   └── simulator/page.tsx  # Paper trader page
│   ├── components/dashboard/
│   │   ├── AIPicks.tsx          # Pick list with polling, cache-age display, refresh
│   │   ├── StockSearch.tsx      # Search + AI analysis card + chat
│   │   ├── SimulatorPanel.tsx   # Paper portfolio UI
│   │   ├── StockChart.tsx       # TradingView Lightweight Charts
│   │   ├── TechnicalSignals.tsx # RSI/MACD/BB/EMA display
│   │   └── ...                  # Other panels (news, sentiment, options, insider, earnings)
│   └── lib/
│       ├── api.ts               # All 60+ API calls (typed wrappers around fetch)
│       └── utils.ts             # formatPrice, formatMarketCap, colorClass, timeAgo
└── render.yaml                  # Render deployment config
```

---

## Environment Variables

All in `backend/.env`. Never commit this file.

```
ANTHROPIC_API_KEY=          # Required — Claude API
FINNHUB_API_KEY=            # Required — market data (60 calls/min free tier)
FRED_API_KEY=               # Macro indicators (CPI, rates, GDP)
REDDIT_CLIENT_ID/SECRET=    # Sentiment (optional)
NEWS_API_KEY=               # News aggregation (optional)
CACHE_TTL_SECONDS=300       # Default cache TTL
DISK_CACHE_DIR=./cache_data # Persistent cache path
AI_MODEL=claude-sonnet-4-6  # Overrides the Claude model used
```

Frontend: `frontend/.env.local`
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Running Locally

```bash
# Backend (http://localhost:8000)
cd backend && .venv/Scripts/activate && uvicorn main:app --reload --port 8000

# Frontend (http://localhost:3000)
cd frontend && npm run dev
```

Or use the batch files: `start-backend.bat`, `start-frontend.bat`

---

## AI Picks Architecture

The picks flow is entirely non-blocking:

1. **`POST /ai/refresh`** — clears picks cache, fires `background_refresh_picks()` as an asyncio task, returns immediately. 60-second cooldown prevents wasted Claude calls. Use `POST /ai/force-refresh` to bypass cooldown.
2. **`GET /ai/picks-status`** — polls `has_picks` + `generating` flags. Frontend polls every 4s.
3. **`GET /ai/picks-all`** — returns cached picks or blocks until generation completes.

**Generation in `generate_quick_unified_picks()`:**
- Claude selects 3 LONG-TERM + 3 BARGAIN + 3 HIDDEN GEM picks from `_COMPANY_REGISTRY` (71 tickers with descriptions) using market context (VIX, regime, sectors, FRED macro).
- Finnhub `get_quote` fetches live prices for the ~9 selected tickers. Falls back to `pc` (prev_close) when `c=0` (after-hours), then to candle data if still missing.
- Picks with no price after both fallbacks are included with `null` price fields (shown as `—` in UI).
- Cache TTL = `None` (never expires). Only cleared on explicit refresh.

**`_COMPANY_REGISTRY`** — the single source of truth for what tickers Claude can pick. Edit this dict in `ai_service.py` to add/remove tickers.

---

## Single-Stock Analysis

Triggered when user searches a ticker and the analyze button fires. Route: `GET /ai/analyze-all/{ticker}`. Cached 24h per ticker.

The function `analyze_ticker_all_modes()` gathers in parallel:
- Yahoo Finance quote + TA (1y weekly)
- Finnhub quote (with `prev_close` fallback), fundamentals, analyst consensus, insider signal, earnings

**3 hold horizons** are computed with ATR-based stops:
- `1-3yr`: stop ~2× ATR, target +30%
- `3-5yr`: stop ~3.5× ATR, target +75%
- `5-10yr`: stop ~5× ATR, target +200%

Claude picks the best-fit horizon and adjusts levels. `max_tokens=1800`.

The older mode-specific routes (`/ai/analyze/{ticker}?mode=short|long|discovery`) use separate functions. Key notes:
- **Short mode**: includes analyst consensus, earnings proximity (warns if earnings ≤3 days), 52W range, short interest in prompt.
- **Long mode** (`_analyze_ticker_longterm`): uses ATR stops, `_LT_MODEL_LENS` dict for business model context. The model_context was previously broken (sent raw Python code to Claude) — now fixed.
- **Discovery mode**: 10-year horizon, 35% stop, 2.5x base target, includes analyst + earnings context.

---

## Caching

```python
from services.cache_service import get_cached, set_cached, delete_cached

set_cached("key", value, ttl=300)   # ttl=None → never expires
get_cached("key")                    # returns None if missing/expired
delete_cached("key")
```

Key TTLs:
- AI picks (`ai_picks_all`): **Never** — manual refresh only
- Finnhub quote (`fh_quote:{ticker}`): 600s
- TA signals (`ta_signals:{ticker}:...`): 3600s
- Single-stock analysis (`analyze_all:{ticker}`): 86400s (24h)
- Market snapshot: 300s (in-memory)

---

## Critical Constraints

- **No Yahoo Finance for picks** — yfinance is used only for TA computation (`technical_analysis.py`) and as a fallback in single-stock analysis. Never use `yf_svc.get_quote` in the picks generation flow.
- **Finnhub rate limit**: 60 calls/min = 1/sec sustained. Use `_batch_gather(coros, batch_size=3, delay=0.5)` for bulk calls.
- **Finnhub `c=0` after hours**: `get_quote` now falls back to `pc` (prev_close). Always use `fh_data.get("price") or fh_data.get("prev_close")` when consuming Finnhub quotes.
- **Picks cache key**: `ai_picks_all` (main), `ai_picks_{mode}` (per-mode). Clear all on refresh.
- **Double-refresh bug**: `AIPicks.tsx handleRefresh` must NOT call `setRunKey` — that triggers the `useEffect` which fires a second `aiRefresh()`. The fix is to manage state directly and call `startPolling()` instead.

---

## Frontend Patterns

- **API calls**: always through `lib/api.ts` typed wrappers. Never use raw `fetch` in components.
- **Prices**: use `formatPrice(n)` from `lib/utils.ts` — handles null/undefined as `"—"`, no `$0.00`.
- **Cache age**: `timeAgo(generatedAt)` in `AIPicks.tsx` parses `"YYYY-MM-DD HH:MM ET"` and returns `"Xm ago"` / `"Xh ago"`.
- **Polling**: `setInterval` stored in `pollRef`, always cleared on unmount. Max wait 2 minutes, error after 20s with no `generating` flag.

---

## Known Architecture Notes

- The simulator uses SQLite via `simulator_service.py`. No ORM — raw SQL.
- Screener universes (`EQUITY_UNIVERSE`, `BARGAIN_UNIVERSE`, `HIDDEN_GEMS_UNIVERSE`) in `ai_service.py` are the source of candidates for the old screener-based picks. The new `generate_quick_unified_picks` bypasses these entirely and uses `_COMPANY_REGISTRY` instead.
- `assess_market_regime()` in `ai_service.py` converts VIX + index changes + yield spread into a regime dict (`vix_regime`, `overall_bias`, `direction`) that's injected into all pick prompts.
- `_market_time_context()` generates time-aware context (pre-market / after-hours / weekend) so Claude knows whether it's analyzing for "tomorrow's open" or "next Monday."
