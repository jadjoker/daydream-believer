"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatPct, formatPrice, formatMarketCap, formatVolume, colorClass } from "@/lib/utils";
import { Card, StatCard } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { TrendingUp, TrendingDown } from "lucide-react";

interface StockQuotePanelProps {
  ticker: string;
}

export default function StockQuotePanel({ ticker }: StockQuotePanelProps) {
  const { data: quote, loading: loadingQ } = useData(
    () => api.quote(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 30000 }
  );

  const { data: fundamentals, loading: loadingF } = useData(
    () => api.fundamentals(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 3600000 }
  );

  if (loadingQ) return <LoadingSkeleton />;

  const q = quote;
  const f = fundamentals;
  const up = (q?.change_pct ?? 0) >= 0;

  return (
    <Card title="Quote & Fundamentals">
      <div className="space-y-4">
        {/* Price hero */}
        {q && (
          <div className="flex items-end justify-between">
            <div>
              <div className="text-3xl font-bold tabular-nums">{formatPrice(q.price)}</div>
              <div className={`flex items-center gap-1.5 text-base font-medium mt-0.5 ${colorClass(q.change_pct)}`}>
                {up ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                {q.change >= 0 ? "+" : "-"}${Math.abs(q.change).toFixed(2)} ({formatPct(q.change_pct)})
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm text-zinc-400">{q.name}</div>
              <div className="text-xs text-zinc-600">{q.exchange} • {q.sector}</div>
              {f?.analyst_rating && (
                <Badge
                  variant={
                    f.analyst_rating === "buy" || f.analyst_rating === "strong_buy" ? "bullish" :
                    f.analyst_rating === "sell" || f.analyst_rating === "strong_sell" ? "bearish" : "neutral"
                  }
                  className="mt-1"
                >
                  {f.analyst_rating.replace("_", " ").toUpperCase()}
                </Badge>
              )}
            </div>
          </div>
        )}

        {/* Key market stats */}
        {q && (
          <div className="grid grid-cols-3 gap-2">
            <StatCard label="Volume" value={formatVolume(q.volume)} sub={`Avg: ${formatVolume(q.avg_volume)}`} />
            <StatCard label="Rel. Vol" value={q.rel_volume ? `${formatNum(q.rel_volume, 2)}x` : "—"} valueClass={q.rel_volume > 2 ? "text-cyan-400" : "text-zinc-300"} />
            <StatCard label="Mkt Cap" value={formatMarketCap(q.market_cap)} />
            <StatCard label="52W High" value={formatPrice(q.week_52_high)} valueClass="text-emerald-400" />
            <StatCard label="52W Low" value={formatPrice(q.week_52_low)} valueClass="text-red-400" />
            <StatCard label="Beta" value={formatNum(q.beta, 2)} />
          </div>
        )}

        {/* Short interest */}
        {q && (q.short_float != null || q.short_ratio != null) && (
          <div className="grid grid-cols-2 gap-2">
            <StatCard
              label="Short Float"
              value={q.short_float != null ? `${(q.short_float * 100).toFixed(1)}%` : "—"}
              valueClass={q.short_float > 0.2 ? "text-red-400" : q.short_float > 0.1 ? "text-yellow-400" : "text-zinc-300"}
              sub={q.short_float > 0.2 ? "High short interest" : undefined}
            />
            <StatCard label="Short Ratio (DTC)" value={formatNum(q.short_ratio, 1)} valueClass={q.short_ratio > 5 ? "text-red-400" : "text-zinc-300"} />
          </div>
        )}

        {/* Fundamental ratios */}
        {f && (
          <div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Fundamental Ratios</div>
            <div className="grid grid-cols-4 gap-2">
              <StatCard label="P/E (TTM)" value={formatNum(f.pe_ratio, 1)} />
              <StatCard label="Fwd P/E" value={formatNum(f.forward_pe, 1)} />
              <StatCard label="PEG" value={formatNum(f.peg_ratio, 2)} />
              <StatCard label="P/S" value={formatNum(f.ps_ratio, 2)} />
              <StatCard label="P/B" value={formatNum(f.pb_ratio, 2)} />
              <StatCard label="EV/EBITDA" value={formatNum(f.ev_ebitda, 1)} />
              <StatCard label="Profit Margin" value={f.profit_margin != null ? `${(f.profit_margin * 100).toFixed(1)}%` : "—"} />
              <StatCard label="ROE" value={f.roe != null ? `${(f.roe * 100).toFixed(1)}%` : "—"} />
            </div>
          </div>
        )}

        {/* Analyst target */}
        {f && f.target_price && (
          <div className="bg-zinc-800/40 rounded-lg p-3">
            <div className="text-xs text-zinc-500 mb-1">Analyst Price Target</div>
            <div className="flex items-center gap-3">
              <span className="font-semibold text-lg">{formatPrice(f.target_price)}</span>
              <span className="text-xs text-zinc-500">
                Range: {formatPrice(f.target_low)} — {formatPrice(f.target_high)}
              </span>
              <span className="text-xs text-zinc-500">
                {f.analyst_count} analysts
              </span>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 animate-pulse">
      <div className="h-8 bg-zinc-800 rounded w-32" />
      <div className="h-5 bg-zinc-800 rounded w-24" />
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-14 bg-zinc-800 rounded-lg" />)}
      </div>
    </div>
  );
}
