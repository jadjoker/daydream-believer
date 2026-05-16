"use client";
import { useState, useCallback } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatPct, formatMarketCap, colorClass, rsiColor } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SlidersHorizontal, RefreshCw } from "lucide-react";

interface ScreenerProps {
  onTickerSelect: (ticker: string) => void;
}

interface ScreenerFilters {
  min_price: number;
  max_price: number;
  min_rel_volume: number;
  min_change_pct: number;
  max_change_pct: number;
  sort_by: string;
  limit: number;
}

const DEFAULT_FILTERS: ScreenerFilters = {
  min_price: 1,
  max_price: 10000,
  min_rel_volume: 1,
  min_change_pct: -50,
  max_change_pct: 50,
  sort_by: "score",
  limit: 25,
};

export default function StockScreener({ onTickerSelect }: ScreenerProps) {
  const [filters, setFilters] = useState<ScreenerFilters>(DEFAULT_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [appliedFilters, setAppliedFilters] = useState<ScreenerFilters>(DEFAULT_FILTERS);

  const { data, loading, refetch } = useData(
    () => api.screener(appliedFilters as any) as Promise<any>,
    [JSON.stringify(appliedFilters)],
    { refreshInterval: 300000 }
  );

  const applyFilters = useCallback(() => {
    setAppliedFilters({ ...filters });
  }, [filters]);

  const results = data?.results || [];

  return (
    <Card
      title="Stock Screener"
      titleRight={
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">{results.length} results</span>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-1 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <SlidersHorizontal size={12} />
          </button>
          <button onClick={refetch} className="text-zinc-400 hover:text-zinc-200 transition-colors">
            <RefreshCw size={12} />
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        {/* Filter panel */}
        {showFilters && (
          <div className="bg-zinc-800/50 rounded-lg p-3 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <FilterInput label="Min Price" value={filters.min_price} onChange={(v) => setFilters(f => ({ ...f, min_price: v }))} prefix="$" />
              <FilterInput label="Max Price" value={filters.max_price} onChange={(v) => setFilters(f => ({ ...f, max_price: v }))} prefix="$" />
              <FilterInput label="Min Rel. Volume" value={filters.min_rel_volume} onChange={(v) => setFilters(f => ({ ...f, min_rel_volume: v }))} suffix="x" step={0.1} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <FilterInput label="Min Change %" value={filters.min_change_pct} onChange={(v) => setFilters(f => ({ ...f, min_change_pct: v }))} suffix="%" />
              <FilterInput label="Max Change %" value={filters.max_change_pct} onChange={(v) => setFilters(f => ({ ...f, max_change_pct: v }))} suffix="%" />
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Sort By</label>
                <select
                  value={filters.sort_by}
                  onChange={(e) => setFilters(f => ({ ...f, sort_by: e.target.value }))}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-md text-sm text-zinc-200 px-2 py-1.5"
                >
                  {["score", "change_pct", "rel_volume", "rsi"].map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={applyFilters}
              className="w-full bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium py-1.5 rounded-lg transition-colors"
            >
              Apply Filters
            </button>
          </div>
        )}

        {/* Results table */}
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-10 bg-zinc-800 rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="overflow-auto max-h-96">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Price</th>
                  <th>Chg %</th>
                  <th>Rel Vol</th>
                  <th>RSI</th>
                  <th>Mkt Cap</th>
                  <th>Score</th>
                  <th>Signals</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r: any) => (
                  <tr
                    key={r.ticker}
                    className="cursor-pointer"
                    onClick={() => onTickerSelect(r.ticker)}
                  >
                    <td className="font-bold text-cyan-400">{r.ticker}</td>
                    <td className="tabular-nums">${formatNum(r.price, 2)}</td>
                    <td className={`tabular-nums font-medium ${colorClass(r.change_pct)}`}>
                      {formatPct(r.change_pct)}
                    </td>
                    <td className={`tabular-nums ${r.rel_volume > 2 ? "text-cyan-400 font-medium" : "text-zinc-400"}`}>
                      {formatNum(r.rel_volume, 1)}x
                    </td>
                    <td className={`tabular-nums ${rsiColor(r.rsi)}`}>
                      {formatNum(r.rsi, 0)}
                    </td>
                    <td className="text-zinc-400 tabular-nums">{formatMarketCap(r.market_cap)}</td>
                    <td className={`tabular-nums font-semibold ${r.score > 3 ? "text-emerald-400" : r.score < 0 ? "text-red-400" : "text-yellow-400"}`}>
                      {formatNum(r.score, 1)}
                    </td>
                    <td className="max-w-[120px]">
                      <div className="flex gap-1 flex-wrap">
                        {r.signals?.slice(0, 2).map((s: string, i: number) => (
                          <span key={i} className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded truncate max-w-[100px]" title={s}>
                            {s.split("(")[0].trim()}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

function FilterInput({
  label, value, onChange, prefix, suffix, step = 1
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  prefix?: string;
  suffix?: string;
  step?: number;
}) {
  return (
    <div>
      <label className="text-xs text-zinc-500 block mb-1">{label}</label>
      <div className="relative">
        {prefix && <span className="absolute left-2 top-1/2 -translate-y-1/2 text-xs text-zinc-500">{prefix}</span>}
        <input
          type="number"
          value={value}
          step={step}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className={`w-full bg-zinc-900 border border-zinc-700 rounded-md text-sm text-zinc-200 py-1.5 ${prefix ? "pl-5 pr-2" : "px-2"} ${suffix ? "pr-5" : ""}`}
        />
        {suffix && <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-zinc-500">{suffix}</span>}
      </div>
    </div>
  );
}
