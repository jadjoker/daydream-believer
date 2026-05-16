const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    next: { revalidate: 0 },
    ...options,
  });
  if (!res.ok) {
    // Try to extract the detail message from FastAPI's error body
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail;
    } catch {}
    throw new Error(detail ?? `API ${path} → ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Market overview
  marketOverview: () => apiFetch("/market/overview"),

  // Stock data
  searchTicker: (q: string) => apiFetch(`/stocks/search?q=${encodeURIComponent(q)}`),
  quote: (ticker: string) => apiFetch(`/stocks/quote/${ticker}`),
  ohlcv: (ticker: string, period = "3mo", interval = "1d") =>
    apiFetch(`/stocks/ohlcv/${ticker}?period=${period}&interval=${interval}`),
  technicals: (ticker: string, period = "6mo", interval = "1d") =>
    apiFetch(`/stocks/technicals/${ticker}?period=${period}&interval=${interval}`),
  fundamentals: (ticker: string) => apiFetch(`/stocks/fundamentals/${ticker}`),
  profile: (ticker: string) => apiFetch(`/stocks/profile/${ticker}`),
  priceTarget: (ticker: string) => apiFetch(`/stocks/price-target/${ticker}`),
  basicFinancials: (ticker: string) => apiFetch(`/stocks/basic-financials/${ticker}`),
  multiQuote: (tickers: string[]) =>
    apiFetch(`/stocks/multi-quote?tickers=${tickers.join(",")}`),

  // Sentiment
  sentiment: (ticker: string) => apiFetch(`/sentiment/${ticker}`),
  trendingReddit: () => apiFetch("/sentiment/trending/reddit"),
  trendingStocktwits: () => apiFetch("/sentiment/trending/stocktwits"),

  // Options
  optionsFlow: (ticker: string) => apiFetch(`/options/flow/${ticker}`),
  unusualOptions: (tickers?: string) =>
    apiFetch(`/options/unusual${tickers ? `?tickers=${tickers}` : ""}`),

  // News
  generalNews: () => apiFetch("/news/general"),
  tickerNews: (ticker: string) => apiFetch(`/news/ticker/${ticker}`),
  marketSentiment: (ticker: string) => apiFetch(`/news/market-sentiment/${ticker}`),

  // Screener
  screener: (params: Record<string, string | number>) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch(`/screener/scan?${q}`);
  },
  screenerUniverse: () => apiFetch("/screener/universe"),

  // Insider
  insiderTrades: (ticker: string) => apiFetch(`/insider/trades/${ticker}`),
  secFilings: (ticker: string, formType = "8-K") =>
    apiFetch(`/insider/filings/${ticker}?form_type=${formType}`),

  // Earnings
  earningsCalendar: (weeks = 2) => apiFetch(`/earnings/calendar?weeks_ahead=${weeks}`),
  tickerEarnings: (ticker: string) => apiFetch(`/earnings/ticker/${ticker}`),

  // AI
  aiPicks: (mode: "short" | "long" | "discovery" = "short") => apiFetch(`/ai/picks?mode=${mode}`),
  aiPicksAll: () => apiFetch("/ai/picks-all"),
  aiPicksMore: (mode: string) => apiFetch(`/ai/picks-more/${mode}`),
  analyzeTicker: (ticker: string, mode: "short" | "long" | "discovery" = "short") =>
    apiFetch(`/ai/analyze/${encodeURIComponent(ticker)}?mode=${mode}`),
  analyzeTickerAll: (ticker: string) =>
    apiFetch(`/ai/analyze-all/${encodeURIComponent(ticker)}`),

  // Simulator (shared state via backend SQLite)
  simulatorState: () => apiFetch("/simulator/state"),
  simulatorBuy: (body: { ticker: string; name: string; shares: number; price: number; thesis: string }) =>
    apiFetch("/simulator/buy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  simulatorSell: (body: { ticker: string; name: string; shares: number; price: number; thesis: string }) =>
    apiFetch("/simulator/sell", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  simulatorAddFunds: (amount: number) =>
    apiFetch("/simulator/add-funds", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount }) }),
  simulatorReset: () =>
    apiFetch("/simulator/reset", { method: "POST" }),
  recurringPlans: () => apiFetch("/simulator/recurring"),
  recurringAdd: (body: {
    ticker: string; name?: string; amount: number; frequency: string;
    start_date: string; backfill?: boolean;
  }) => apiFetch("/simulator/recurring/add", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  recurringExecute: (planId: number, price: number, name?: string) =>
    apiFetch(`/simulator/recurring/execute/${planId}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ price, name: name ?? "" }),
    }),
  recurringDelete: (planId: number) =>
    apiFetch(`/simulator/recurring/${planId}`, { method: "DELETE" }),

};
