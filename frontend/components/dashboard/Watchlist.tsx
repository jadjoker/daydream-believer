"use client";
import { useState, useEffect } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatPct, colorClass } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Plus, X, TrendingUp, TrendingDown } from "lucide-react";

interface WatchlistProps {
  onTickerSelect: (ticker: string) => void;
  selectedTicker?: string;
}

const STORAGE_KEY = "daydream_watchlist";
const DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"];

export default function Watchlist({ onTickerSelect, selectedTicker }: WatchlistProps) {
  const [tickers, setTickers] = useState<string[]>(() => {
    if (typeof window === "undefined") return DEFAULT_WATCHLIST;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : DEFAULT_WATCHLIST;
    } catch {
      return DEFAULT_WATCHLIST;
    }
  });
  const [input, setInput] = useState("");

  const { data, loading, refetch } = useData(
    () => tickers.length > 0 ? api.multiQuote(tickers) as Promise<any> : Promise.resolve({ quotes: [] }),
    [tickers.join(",")],
    { refreshInterval: 30000 }
  );

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tickers));
  }, [tickers]);

  const addTicker = () => {
    const t = input.trim().toUpperCase();
    if (t && !tickers.includes(t)) {
      setTickers((prev) => [...prev, t]);
    }
    setInput("");
  };

  const removeTicker = (t: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTickers((prev) => prev.filter((x) => x !== t));
  };

  const quotes: Record<string, any> = {};
  for (const q of (data?.quotes || [])) {
    quotes[q.ticker] = q;
  }

  return (
    <Card title="Watchlist">
      <div className="space-y-3">
        {/* Add input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && addTicker()}
            placeholder="Add ticker…"
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-cyan-500/60"
          />
          <button
            onClick={addTicker}
            className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg px-3 py-1.5 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <Plus size={14} />
          </button>
        </div>

        {/* Ticker list */}
        <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
          {tickers.map((ticker) => {
            const q = quotes[ticker];
            const up = (q?.change_pct ?? 0) >= 0;
            return (
              <div
                key={ticker}
                onClick={() => onTickerSelect(ticker)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-all group ${
                  selectedTicker === ticker
                    ? "bg-cyan-600/20 border border-cyan-500/40"
                    : "hover:bg-zinc-800 border border-transparent"
                }`}
              >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  {q && (up ? <TrendingUp size={12} className="text-emerald-500 shrink-0" /> : <TrendingDown size={12} className="text-red-500 shrink-0" />)}
                  <span className="font-semibold text-sm truncate">{ticker}</span>
                </div>
                <div className="flex items-center gap-3">
                  {q ? (
                    <>
                      <span className="text-sm tabular-nums font-medium">${formatNum(q.price, 2)}</span>
                      <span className={`text-xs tabular-nums w-14 text-right ${colorClass(q.change_pct)}`}>
                        {formatPct(q.change_pct)}
                      </span>
                    </>
                  ) : loading ? (
                    <div className="w-20 h-4 bg-zinc-800 rounded animate-pulse" />
                  ) : (
                    <span className="text-xs text-zinc-600">—</span>
                  )}
                  <button
                    onClick={(e) => removeTicker(ticker, e)}
                    className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-all ml-1"
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
